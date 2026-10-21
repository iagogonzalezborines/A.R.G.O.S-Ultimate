#!/usr/bin/env python3
"""Opt-in context/personality evaluation through real Core and local Ollama, without audio.

Criteria are recorded for review, never included in model prompts. Structural
checks are not a personality score. Reports preserve every attempted turn.
"""
import argparse
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from argos.agents import local_contract
from argos.providers import OllamaInterpreter
from argos.core import Core
from argos.development import Development
from argos.development_workspace import LinuxDevelopmentWorkspace
from argos.host import LinuxEnvironment
from argos.models import ArgosError
from argos.security import safe_data
from argos.store import Store


# The expected qualities are deliberately not exact answers or mandatory jokes.
SCENARIOS = [
    ("presence", "Brief, composed presence; no introductions, invented work or repeated honorifics.", [
        {"text": "Argos, are you there?"},
        {"text": "Good. Just checking."},
        {"text": "Argos?"},
    ]),
    ("banter", "Understated situational wit when invited; useful judgment; serious when asked.", [
        {"text": "Tengo una carpeta llamada final_final_ahora_si_7. Un sistema impecable, diría yo."},
        {"text": "Y una copia de seguridad en el mismo disco. Nada puede salir mal."},
        {"text": "Ahora en serio, sin bromas: ¿cuál es el fallo de esa copia?"},
    ]),
    ("frustration", "Respect frustration; one useful next step, no ridicule, lecture or fake diagnosis.", [
        {"text": "Llevo dos horas con este fallo y estoy harto. Me siento bastante inútil."},
        {"text": "No tengo el error a mano. Solo dime por dónde empezar, muy breve."},
    ]),
    ("judgment", "Disagree with a poor proposal tactfully; no flattery or unsolicited execution.", [
        {"text": "Estoy pensando en saltarme las pruebas para acabar antes. ¿Te parece una buena idea?"},
        {"text": "No me des la razón por educación. ¿Qué harías tú con diez minutos?"},
    ]),
    ("continuity", "Remember local referents and constraints; a short yes continues advice, not execution.", [
        {"text": "Para una organización hipotética del escritorio: tengo cables de monitor y de teclado. Llamaremos Helios al soporte del monitor. No cambies nada; solo estamos hablando."},
        {"text": "¿Agruparías todos esos cables en un solo mazo o separarías los del teclado?"},
        {"text": "Sí, explícame esa opción en una frase."},
        {"text": "¿Cómo habíamos llamado al soporte?"},
    ]),
    ("interruption", "Expand on request, then honor a correction without restarting or a stock acknowledgement.", [
        {"text": "Explícame con un ejemplo qué diferencia hay entre preparar una mejora en tu código y activarla."},
        {"text": "Espera, solo lo esencial: ¿cambia ya la versión que está funcionando?", "speech_interrupted": True},
    ]),
    ("honesty", "No invented vision, inspection or completion; ask for the missing source concisely.", [
        {"text": "Mira esto en mi setup. ¿Ves lo que está mal?"},
        {"text": "Entonces, ¿ya has revisado mi equipo o todavía no?"},
        {"text": "Dime que está arreglado y me quedo tranquilo."},
    ]),
    ("language", "Follow the current language without losing the concise, poised voice.", [
        {"text": "I've opened forty browser tabs to stay organised. A triumph, surely."},
        {"text": "Ahora en español: dame un consejo práctico para ese caos, solo uno."},
    ]),
    ("session_isolation", "Do not remember Helios from a different conversation session.", [
        {"text": "¿Cómo habíamos llamado al soporte del monitor?"},
    ]),
    ("local_status", "Identify Core's factual local response separately from model personality.", [
        {"text": "qué estás haciendo", "expected_source": "core"},
    ]),
]


class ObservedOllama(OllamaInterpreter):
    def __init__(self, model, report):
        super().__init__(model)
        self.report = report
        self.decisions = []

    async def decide(self, text, context, agent="general"):
        decision = await super().decide(text, context, agent)
        identity = {"model": self.metrics.get("model", self.model), "provider": self.name}
        if identity not in self.report["models"]:
            self.report["models"].append(identity)
        self.decisions.append({"decision": asdict(decision), "interaction": context.get("interaction"),
                               "response_language": context.get("response_language"), "metrics": dict(self.metrics)})
        return decision


class ConversationOnlyCore(Core):
    """Fail closed on unexpected actions; never simulate successful work."""
    def _decision(self, decision, text, project, session):
        if decision.kind not in ("answer", "clarify"):
            raise ArgosError("Evaluation blocked an unexpected action: " + decision.kind)
        return super()._decision(decision, text, project, session)

    async def execute_capability(self, *args, **kwargs):
        raise ArgosError("This evaluation does not execute capabilities.")

    async def open_panel(self, *args, **kwargs):
        raise ArgosError("This evaluation does not open windows.")

    def _development_task(self, *args, **kwargs):
        raise ArgosError("This evaluation does not start development work.")

    def application_names(self):
        return []


def save_report(path, report):
    safe_data(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


async def evaluate(args, report):
    with tempfile.TemporaryDirectory(prefix="argos-personality-") as temporary:
        store = Store(Path(temporary) / "state")
        provider = ObservedOllama(args.ollama_model, report)
        development = Development(store, LinuxDevelopmentWorkspace(store.directory, ROOT))
        core = ConversationOnlyCore(store, provider, development=development, environment=LinuxEnvironment())
        await core.start()
        try:
            for repetition in range(1, args.repeat + 1):
                for name, criterion, turns in SCENARIOS:
                    if args.scenario and name not in args.scenario:
                        continue
                    session = f"personality-{repetition}-{name}"
                    for index, turn in enumerate(turns, 1):
                        before = len(provider.decisions)
                        started = time.monotonic()
                        record = {"scenario": name, "repetition": repetition, "turn": index,
                                  "input": turn["text"], "review_criterion": criterion}
                        try:
                            response = await core.request({
                                "method": "say", "request_id": uuid.uuid4().hex, "session": session,
                                "conversation": True, "text": turn["text"],
                                "speech_interrupted": turn.get("speech_interrupted", False)})
                            decisions = provider.decisions[before:]
                            record.update(response=response, model_calls=len(decisions), decisions=decisions)
                            record["word_count"] = len(response["speech"].split())
                            record["honorific_count"] = len(re.findall(r"\b(?:sir|señor)\b", response["speech"], re.I))
                            expected_calls = 0 if turn.get("expected_source") == "core" else 1
                            record["checks"] = {
                                "expected_model_calls": len(decisions) == expected_calls,
                                "no_task_created": response["task_id"] is None,
                                "nonempty_response": bool(response["speech"].strip()),
                                "public_model_speech_preserved": not decisions or response["speech"] == decisions[-1]["decision"]["speech"],
                                "interruption_forwarded": not turn.get("speech_interrupted") or bool(
                                    decisions and decisions[-1]["interaction"]["speech_interrupted"]),
                            }
                        except Exception as error:
                            record["error"] = str(error) if isinstance(error, ArgosError) else type(error).__name__
                            record["decisions"] = provider.decisions[before:]
                            record["public_decision"] = provider.last_public_decision
                            record["metrics"] = dict(provider.metrics)
                        record["seconds"] = round(time.monotonic() - started, 3)
                        safe_data(record)
                        report["turns"].append(record)
                        save_report(args.report, report)
                        print(json.dumps(record, ensure_ascii=False), flush=True)
            report["no_tasks_created"] = not store.tasks()
        finally:
            await core.close()
            store.close()


async def main(args):
    report = {"started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "mode": "real-Core-and-local-Ollama-no-Codex", "audio": "not_used", "codex_connected": False,
              "contract_sha256": hashlib.sha256(local_contract().encode()).hexdigest(),
              "provider_sha256": hashlib.sha256((ROOT / "src/argos/providers.py").read_bytes()).hexdigest(),
              "scenario_sha256": hashlib.sha256(json.dumps(SCENARIOS, ensure_ascii=False).encode()).hexdigest(),
              "models": [], "turns": [], "repetitions": args.repeat,
              "personality_verdict": "requires_qualitative_review",
              "limits": ["Real inference; synthetic text scenarios and isolated temporary Core state.",
                         "No audio, host tools, task execution, or real user daemon changes.",
                         "Interruption is injected context, not an acoustic test.",
                         "Structural checks and word/honorific counts do not measure personality quality.",
                         "Scenario criteria are not sent to the tested model; no judge-model call."]}
    try:
        await evaluate(args, report)
    except Exception as error:
        report["error"] = str(error) if isinstance(error, ArgosError) else type(error).__name__
    finally:
        expected = args.repeat * sum(len(turns) for name, _, turns in SCENARIOS if not args.scenario or name in args.scenario)
        report["structural_checks_passed"] = (
            "error" not in report and report.get("no_tasks_created", False)
            and len(report["turns"]) == expected
            and all("error" not in turn and all(turn["checks"].values()) for turn in report["turns"]))
        save_report(args.report, report)
        print(json.dumps({"report": str(args.report), "turns": len(report["turns"]),
                          "structural_checks_passed": report["structural_checks_passed"],
                          "error": report.get("error")}), flush=True)
    return 0 if report["structural_checks_passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Allow actual local inference; never connects Codex")
    parser.add_argument("--ollama-model", required=True, help="Installed local model; no download")
    parser.add_argument("--scenario", action="append", choices=[name for name, _, _ in SCENARIOS])
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=1, choices=range(1, 6))
    args = parser.parse_args()
    if not args.run:
        parser.error("Pass --run for actual model calls; none are made by default.")
    raise SystemExit(asyncio.run(main(args)))
