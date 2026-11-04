#!/usr/bin/env python3
"""Opt-in General decision check; synthetic paths/history, no operations or audio."""
import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from argos.codex import Codex
from argos.core import Core
from argos.models import ArgosError
from argos.store import Store

BASE = '/home/argos/Proyectos'
CASES = {
    'english': ('Can you register a new project called Faro in my default Linux projects directory?', 'en'),
    'spanish': ('Registra el proyecto Faro que está en mi carpeta de proyectos de Linux.', 'es'),
    'history': ('Yes, register that existing project now.', 'en'),
    'ambiguous_base': ('Register Faro from my projects directory.', 'en'),
    'explicit_override': ('Register Faro from /home/argos/Elsewhere/Faro, not the default location.', 'en'),
    'missing_name': ('Register a project from my Linux projects directory.', 'en'),
    'discovery': ('Find my existing lighthouse project in my Linux projects directory and register it. I do not remember its exact folder name.', 'en'),
}


async def evaluate(args):
    report = {'model': args.model, 'effort': 'low', 'scope': __doc__, 'turns': []}
    with tempfile.TemporaryDirectory(prefix='argos-registration-check-') as tmp:
        store = Store(Path(tmp) / 'state')
        provider = Codex(store.directory, model=args.model, effort='low', conversation=True)
        core = Core(store, provider)
        await core.start()
        try:
            for scenario in args.scenario or CASES:
                prompt, language = CASES[scenario]
                context = core.context(None)
                context['filesystem'] = {'home': '/home/argos', 'absolute_paths': True,
                    'project_locations': {'default': BASE, 'candidates': [
                        {'path': BASE, 'sources': ['home_convention', 'registered_project_parent']}],
                        'registered': [{'name': 'ARGOS', 'root': BASE + '/argos'}],
                        'directories': [{'path': BASE, 'status': 'observed', 'truncated': False,
                            'entries': [{'name': name, 'path': BASE + '/' + name} for name in ('argos', 'Faro')]}]}}
                locations = context['filesystem']['project_locations']
                if scenario == 'ambiguous_base':
                    locations['default'] = None
                    locations['candidates'].append({'path': '/home/argos/Projects', 'sources': ['home_convention']})
                context.update(response_language=language, session=scenario,
                               interaction={'channel': 'voice', 'continuous_dialogue': True})
                if scenario == 'history':
                    context['recent_conversation'] = [
                        {'role': 'user', 'content': 'The existing project is Faro, in my default Linux projects directory. We are discussing registration only.'},
                        {'role': 'assistant', 'content': 'Understood. Faro, in your Linux projects directory.'}]
                before = time.perf_counter()
                row = {'scenario': scenario, 'input': prompt}
                try:
                    decision = await provider.decide(prompt, context)
                    row['decision'] = asdict(decision)
                    if scenario in ('english', 'spanish', 'history', 'explicit_override'):
                        path = '/home/argos/Elsewhere/Faro' if scenario == 'explicit_override' else BASE + '/Faro'
                        row['passed'] = (decision.kind == 'capability' and decision.agent == 'computer'
                            and decision.capability == 'projects.register'
                            and decision.arguments == {'name': 'Faro', 'path': path})
                    else:
                        # Investigation or a focused clarification is appropriate;
                        # neither should silently choose/create an ambiguous folder.
                        row['passed'] = (decision.kind == 'clarify' or
                            (decision.kind == 'delegate' and decision.agent == 'computer'))
                except ArgosError as error:
                    row.update(error=str(error), passed=False)
                row['seconds'] = round(time.perf_counter() - before, 3)
                row['metrics'] = dict(provider.metrics)
                report['turns'].append(row)
                args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
                print(json.dumps(row, ensure_ascii=False), flush=True)
        finally:
            await core.close()
            store.close()
    return all(row['passed'] for row in report['turns'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--model', default='gpt-5.6-luna')
    parser.add_argument('--scenario', action='append', choices=CASES)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if not args.run:
        parser.error('Explicit --run is required for real inference')
    raise SystemExit(0 if asyncio.run(evaluate(args)) else 1)
