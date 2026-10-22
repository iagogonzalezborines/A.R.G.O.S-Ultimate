#!/usr/bin/env python3
"""Explicit, text-only Nemotron comparison; does not configure the ARGOS daemon."""
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


MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"


def validate_api_key(api_key):
    # Treat provider credentials as opaque header values, not fixed-length keys.
    if not isinstance(api_key, str) or not api_key:
        raise ArgosError("No se recibió ninguna clave. Pégala en la terminal y pulsa Enter.")
    if len(api_key) > 8192:
        raise ArgosError("La entrada supera el límite de la cabecera; copia solo la clave API.")
    if any(not 33 <= ord(c) <= 126 for c in api_key):
        raise ArgosError("La entrada contiene espacios o caracteres no admitidos; copia solo la clave API, sin comillas ni comandos.")


def read_api_key():
    api_key = os.environ.get("NVIDIA_API_KEY")
    if api_key:
        validate_api_key(api_key)
        return api_key
    if not sys.stdin.isatty():
        raise ArgosError("Ejecuta desde una terminal para introducir la clave de forma oculta.")
    for _ in range(3):
        api_key = getpass.getpass("Clave API de NVIDIA (entrada oculta, no se guarda): ").strip()
        try:
            validate_api_key(api_key)
            return api_key
        except ArgosError as error:
            print(str(error), file=sys.stderr)
    raise ArgosError("No se pudo leer la clave tras tres entradas; no se ha contactado con NVIDIA.")


def evaluation_contract():
    # Preserve the same personality/decisions, but accurately identify remote inference.
    return local_contract().replace("interaction contract — local", "interaction contract — Nemotron evaluation").replace(
        "Conversation and routine work always stay local.",
        "This evaluation uses Nemotron for conversation; operations remain owned by Core.")


class EvaluationCore(ConversationOnlyCore):
    def context(self, project, agent="general"):
        context = super().context(project, agent)
        # Send synthetic scenarios and registry, not this PC's inventory or paths.
        context["identity"] = {"name": "ARGOS", "mode": "isolated evaluation"}
        context["filesystem"]["home"] = "/home/evaluation"
        context["inference"]["policy"] = "explicit_Nemotron_evaluation_no_Codex"
        context["environment"] = {"status": "not_checked", "facts": {}}
        return context


class NemotronEvaluation:
    name = "nemotron-evaluation"
    model = MODEL

    def __init__(self, api_key, report):
        validate_api_key(api_key)
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
        messages[0]["content"] = evaluation_contract()
        payload = {
            "model": MODEL, "messages": messages, "stream": False,
            "temperature": 1.0, "top_p": 0.95, "max_tokens": 4096,
            "reasoning_effort": "none",
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "argos_decision", "strict": True, "schema": local_schema(context)}},
        }

        def request():
            req = urllib.request.Request(ENDPOINT, json.dumps(payload).encode(),
                                         {"Content-Type": "application/json", "Accept": "application/json",
                                          "Authorization": "Bearer " + self._api_key},
                                         method="POST")
            with self._opener().open(req, timeout=60) as reply:
                if reply.status != 200:
                    raise ArgosError("NVIDIA no devolvió una respuesta completa; prueba detenida.")
                body = reply.read(128001)
            if len(body) > 128000:
                raise ArgosError("Nemotron excedió el límite de respuesta.")
            envelope = json.loads(body)
            choices = envelope.get("choices", [])
            if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
                raise ArgosError("Nemotron no completó la respuesta; no se acepta texto truncado.")
            message = choices[0]["message"]
            if message.get("tool_calls") or message.get("function_call"):
                raise ArgosError("La prueba requiere decisiones JSON, no llamadas nativas a herramientas.")
            # Only public content is read; reasoning_content never enters history or reports.
            wire = json.loads(message["content"])
            if not isinstance(wire, dict) or set(wire) != {"kind", "speech", "target_agent", "tool", "tool_arguments"}:
                raise ArgosError("Nemotron devolvió una decisión inválida.")
            data = {"kind": wire["kind"], "speech": wire["speech"], "agent": wire["target_agent"],
                    "capability": wire["tool"], "arguments": wire["tool_arguments"]}
            decision = validate_decision(data)
            self.last_public_decision = data
            usage = envelope.get("usage", {})
            self.metrics = {k: usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens")
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
                        raise ArgosError("NVIDIA: límite de uso del endpoint gratuito alcanzado; prueba detenida sin reintentos.") from None
                    if error.code == 503:
                        raise ArgosError("Nemotron sigue temporalmente no disponible (HTTP 503) tras tres intentos; prueba detenida.") from None
                    raise ArgosError(f"Nemotron rechazó la prueba (HTTP {error.code}); revisa clave, modelo y configuración.") from None
                if isinstance(error, ArgosError):
                    raise
                raise ArgosError("Nemotron no respondió correctamente; prueba detenida.") from None
            self.connected = True
            identity = {"model": MODEL, "provider": self.name}
            if identity not in self.report["models"]:
                self.report["models"].append(identity)
            self.decisions.append({"decision": asdict(decision), "interaction": context.get("interaction"),
                                   "response_language": context.get("response_language"), "metrics": dict(self.metrics)})
            return decision


async def run(args, api_key):
    report = {"started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "mode": "real-Core-and-Nemotron-evaluation-no-Codex", "audio": "not_used", "codex_connected": False,
              "endpoint": ENDPOINT, "reasoning_effort": "none",
              "contract_sha256": hashlib.sha256(evaluation_contract().encode()).hexdigest(),
              "provider_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "shared_provider_sha256": hashlib.sha256((ROOT / "src/argos/providers.py").read_bytes()).hexdigest(),
              "scenario_sha256": hashlib.sha256(json.dumps(SCENARIOS, ensure_ascii=False).encode()).hexdigest(),
              "models": [], "turns": [], "repetitions": 1,
              "personality_verdict": "requires_qualitative_review",
              "limits": ["Synthetic scenarios; no host inventory, audio or user conversation history.",
                         "No capabilities executed, no Codex, no daemon configuration changes.",
                         "Contract identifies Nemotron; environment is not_checked, unlike local hardware evaluations.",
                         "API key remains in memory, outside prompts, reports and SQLite.",
                         "NVIDIA hosted prototype endpoint; no paid provider or endpoint fallback.",
                         "Only HTTP 503 is retried: at most twice, after 1 and 2 seconds. Latency includes retries.",
                         "Structural success does not certify conversational quality."]}
    args.ollama_model, args.repeat = MODEL, 1  # Shared scenario runner's provider factory interface.
    try:
        await evaluate(args, report, lambda _, r: NemotronEvaluation(api_key, r), EvaluationCore, False)
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
                      "http_attempts": report["http_attempts"], "error": report.get("error")}))
    return 0 if report["structural_checks_passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--scenario", action="append", choices=[name for name, _, _ in SCENARIOS])
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.run:
        parser.error("Requiere --run para enviar escenarios de prueba al endpoint de NVIDIA.")
    try:
        api_key = read_api_key()
        return asyncio.run(run(args, api_key))
    except (EOFError, KeyboardInterrupt):
        print("Entrada cancelada.", file=sys.stderr)
        return 2
    except ArgosError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
