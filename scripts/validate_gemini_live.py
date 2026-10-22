#!/usr/bin/env python3
"""Explicit, text-only Gemini comparison; does not configure the ARGOS daemon."""
import argparse
import asyncio
from dataclasses import asdict
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

from validate_personality_live import ROOT, SCENARIOS, ConversationOnlyCore, evaluate, save_report
from argos.agents import local_contract
from argos.models import ArgosError
from argos.providers import decision_messages, local_schema, validate_decision
from argos.security import safe_data


MODEL = "gemini-3.1-flash-lite"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


def evaluation_contract():
    # Preserve the same personality/decisions, but accurately identify remote inference.
    return local_contract().replace("interaction contract — local", "interaction contract — Gemini evaluation").replace(
        "Conversation and routine work always stay local.",
        "This evaluation uses Gemini for conversation; operations remain owned by Core.")


def gemini_schema(value):
    if isinstance(value, list):
        return [gemini_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    # Each branch has a unique discriminator; anyOf preserves those alternatives.
    return {("anyOf" if key == "oneOf" else "enum" if key == "const" else key):
            [item] if key == "const" else gemini_schema(item) for key, item in value.items()}


class EvaluationCore(ConversationOnlyCore):
    def context(self, project, agent="general"):
        context = super().context(project, agent)
        # Send synthetic scenarios and registry, not this PC's inventory or paths.
        context["identity"] = {"name": "ARGOS", "mode": "isolated evaluation"}
        context["filesystem"]["home"] = "/home/evaluation"
        context["inference"]["policy"] = "explicit_Gemini_evaluation_no_Codex"
        context["environment"] = {"status": "not_checked", "facts": {}}
        return context


class GeminiEvaluation:
    name = "gemini-evaluation"
    model = MODEL

    def __init__(self, api_key, report):
        if not api_key or len(api_key) > 256 or not api_key.isascii() or any(c.isspace() for c in api_key):
            raise ArgosError("Falta una clave válida de Gemini.")
        self._api_key = api_key
        self.report, self.decisions, self.metrics = report, [], {}
        self.last_public_decision = None
        self.connected = False
        self._failed = False
        self.http_attempts = 0
        self._slot = asyncio.Semaphore(1)

    @property
    def stopped(self):
        return self._failed

    def _opener(self):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    async def decide(self, text, context, agent="general"):
        if agent != "general":
            raise ArgosError("Esta prueba solo compara conversación; no ejecuta especialistas.")
        safe_data(context)
        self.last_public_decision, self.metrics = None, {}
        self.http_attempts = 0
        messages = decision_messages(text, context)
        payload = {
            "systemInstruction": {"parts": [{"text": evaluation_contract()}]},
            "contents": [{"role": "model" if m["role"] == "assistant" else "user",
                          "parts": [{"text": m["content"]}]} for m in messages[1:]],
            "generationConfig": {"responseMimeType": "application/json",
                                 "responseJsonSchema": gemini_schema(local_schema(context)),
                                 "maxOutputTokens": 4096,
                                 "thinkingConfig": {"includeThoughts": False}},
        }

        def request():
            req = urllib.request.Request(ENDPOINT, json.dumps(payload).encode(),
                                         {"Content-Type": "application/json", "x-goog-api-key": self._api_key},
                                         method="POST")
            with self._opener().open(req, timeout=60) as reply:
                body = reply.read(128001)
            if len(body) > 128000:
                raise ArgosError("Gemini excedió el límite de respuesta.")
            envelope = json.loads(body)
            candidates = envelope.get("candidates", [])
            if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
                raise ArgosError("Gemini no completó la respuesta; no se acepta texto truncado.")
            parts = candidates[0]["content"]["parts"]
            public = "".join(p["text"] for p in parts if "text" in p and not p.get("thought"))
            wire = json.loads(public)
            if not isinstance(wire, dict) or set(wire) != {"kind", "speech", "target_agent", "tool", "tool_arguments"}:
                raise ArgosError("Gemini devolvió una decisión inválida.")
            data = {"kind": wire["kind"], "speech": wire["speech"], "agent": wire["target_agent"],
                    "capability": wire["tool"], "arguments": wire["tool_arguments"]}
            decision = validate_decision(data)
            self.last_public_decision = data
            usage = envelope.get("usageMetadata", {})
            self.metrics = {k: usage[k] for k in ("promptTokenCount", "candidatesTokenCount", "totalTokenCount")
                            if isinstance(usage.get(k), int)}
            return decision

        async with self._slot:
            if self._failed:
                raise ArgosError("Prueba detenida tras un error del proveedor; sin más peticiones ni fallback.")
            try:
                # Only retry explicit service-unavailable responses. No tools are
                # executed here; quota/auth/schema/network failures stop immediately.
                for attempt in range(3):
                    self.http_attempts += 1
                    try:
                        decision = await asyncio.to_thread(request)
                        break
                    except urllib.error.HTTPError as error:
                        error.close()
                        if error.code != 503 or attempt == 2:
                            raise
                        await asyncio.sleep(2 ** attempt)
            except Exception as error:
                self.connected, self._failed = False, True
                if isinstance(error, urllib.error.HTTPError):
                    error.close()
                    if error.code == 429:
                        raise ArgosError("Cuota gratuita de Gemini: límite de uso alcanzado; prueba detenida sin reintentos.") from None
                    if error.code == 503:
                        raise ArgosError("Gemini sigue temporalmente no disponible (HTTP 503) tras tres intentos; prueba detenida.") from None
                    raise ArgosError(f"Gemini rechazó la prueba (HTTP {error.code}); revisa clave, modelo y configuración.") from None
                if isinstance(error, ArgosError):
                    raise
                raise ArgosError("Gemini no respondió correctamente; prueba detenida.") from None
            self.connected = True
            identity = {"model": MODEL, "provider": self.name}
            if identity not in self.report["models"]:
                self.report["models"].append(identity)
            self.decisions.append({"decision": asdict(decision), "interaction": context.get("interaction"),
                                   "response_language": context.get("response_language"), "metrics": dict(self.metrics)})
            return decision


async def run(args, api_key):
    report = {"started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "mode": "real-Core-and-Gemini-evaluation-no-Codex", "audio": "not_used", "codex_connected": False,
              "free_tier_confirmed_by_operator": True,
              "contract_sha256": hashlib.sha256(evaluation_contract().encode()).hexdigest(),
              "provider_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "shared_provider_sha256": hashlib.sha256((ROOT / "src/argos/providers.py").read_bytes()).hexdigest(),
              "scenario_sha256": hashlib.sha256(json.dumps(SCENARIOS, ensure_ascii=False).encode()).hexdigest(),
              "models": [], "turns": [], "repetitions": 1,
              "personality_verdict": "requires_qualitative_review",
              "limits": ["Synthetic scenarios; no host inventory, audio or user conversation history.",
                         "No capabilities executed, no Codex, no daemon configuration changes.",
                         "Contract identifies Gemini; environment is not_checked, unlike local hardware evaluations.",
                         "API key remains in memory, outside prompts, reports and SQLite.",
                         "Free tier is an operator declaration, not a billing check by the API client.",
                         "Only HTTP 503 is retried: at most twice, after 1 and 2 seconds. Latency includes retries.",
                         "Structural success does not certify conversational quality."]}
    args.ollama_model, args.repeat = MODEL, 1  # Shared scenario runner's provider factory interface.
    try:
        await evaluate(args, report, lambda _, r: GeminiEvaluation(api_key, r), EvaluationCore, False)
    except Exception as error:
        report["error"] = str(error) if isinstance(error, ArgosError) else type(error).__name__
    expected = sum(len(turns) for name, _, turns in SCENARIOS if not args.scenario or name in args.scenario)
    report["skipped_turns"] = expected - len(report["turns"])
    report["http_attempts"] = sum(t.get("http_attempts", 0) for t in report["turns"])
    report["structural_checks_passed"] = (
        "error" not in report and report.get("no_tasks_created", False)
        and len(report["turns"]) == expected
        and all("error" not in t and all(t["checks"].values()) for t in report["turns"]))
    save_report(args.report, report)
    print(json.dumps({"report": str(args.report), "structural_checks_passed": report["structural_checks_passed"],
                      "attempted_turns": len(report["turns"]), "skipped_turns": report["skipped_turns"],
                      "http_attempts": report["http_attempts"]}))
    return 0 if report["structural_checks_passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--confirm-free-tier", action="store_true",
                        help="Confirm the key belongs to an AI Studio project with billing disabled")
    parser.add_argument("--scenario", action="append", choices=[name for name, _, _ in SCENARIOS])
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.run or not args.confirm_free_tier:
        parser.error("Requiere --run y --confirm-free-tier; comprueba antes que el proyecto no tiene facturación.")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        if not sys.stdin.isatty():
            parser.error("Ejecuta desde una terminal para introducir la clave de forma oculta.")
        api_key = getpass.getpass("Clave de Gemini (entrada oculta, no se guarda): ").strip()
    return asyncio.run(run(args, api_key))


if __name__ == "__main__":
    raise SystemExit(main())
