#!/usr/bin/env python3
"""Opt-in Codex checks: real tools on temporary folders, no desktop or audio."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from argos.core import Core
from argos.models import ArgosError, Decision
from argos.store import Store
from validate_adaptive_persona_live import TracedCodex


class FixtureCore(Core):
    def context(self, project, agent='general'):
        with patch('pathlib.Path.home', return_value=self.fixture_home):
            return super().context(project, agent)

    @staticmethod
    def application_names():
        return []

    async def execute_capability(self, task, project, name, args, development_scope=False):
        if name not in ('files.list', 'files.list_page', 'projects.register'):
            raise ArgosError('Evaluation allows only directory listings and temporary registration.')
        path = Path(args['path']).resolve()
        if not path.is_relative_to(self.fixture_home / 'Proyectos'):
            raise ArgosError('Evaluation path is outside the temporary workspace.')
        return await super().execute_capability(task, project, name, args, development_scope)


async def evaluate(args):
    report = {'scope': __doc__, 'model': 'gpt-5.6-luna', 'effort': 'low', 'cases': []}
    for scenario in ('spoken_name', 'listing_followup', 'specialist_handoff'):
        with tempfile.TemporaryDirectory(prefix='argos-folder-context-') as tmp:
            home = Path(tmp)
            base = home / 'Proyectos'
            for name in ('argos', 'skyline-v2', 'some-and-co2'):
                (base / name).mkdir(parents=True)
            store = Store(home / 'state')
            store.add_project('ARGOS', base / 'argos')
            provider = TracedCodex(store.directory, model=report['model'], effort='low', conversation=True)
            core = FixtureCore(store, provider)
            core.fixture_home = home
            await core.start()
            async def request(method='say', **kwargs):
                return await core.request({'method': method, 'request_id': uuid.uuid4().hex,
                                           'session': scenario, **kwargs})
            async def settled(response):
                await asyncio.wait_for(core.queue.join(), 90)
                return store.task(response['task_id'])
            started = time.perf_counter()
            row = {'scenario': scenario}
            try:
                if scenario == 'spoken_name':
                    response = await request(text='Could you register a new project, which is Sum and CO2? It should be in my default Linux projects folder.')
                elif scenario == 'listing_followup':
                    await settled(await request('run', capability='files.list', arguments={'path': str(base)}))
                    response = await request(text='What folders can you see there in my projects directory? Give me their names.')
                else:
                    # Script only routing to guarantee the handoff is exercised;
                    # the Computer specialist and its tool calls use real Codex.
                    async def decide(text, context, agent='general'):
                        if text.startswith('Register'):
                            return Decision('clarify', speech='Which existing CO2 folder?')
                        return Decision('delegate', agent='computer')
                    provider.decide = decide
                    await request(text='Register my existing CO2 project in the Linux projects directory.')
                    response = await request(text='Some score and score CO2.')
                    row['routing'] = 'scripted General; real Computer specialist with captured history'
                row['response'] = response
                if response.get('task_id'):
                    task = await settled(response)
                    row['task'] = {key: task[key] for key in ('status', 'question', 'result')}
                row['projects'] = store.projects()
                row['decisions'] = provider.decisions
                if scenario == 'listing_followup':
                    row['passed'] = all(name in response['speech'] for name in ('argos', 'skyline-v2', 'some-and-co2'))
                else:
                    row['passed'] = any(p['root'] == str(base / 'some-and-co2') for p in store.projects())
            except (ArgosError, TimeoutError) as error:
                row.update(error=str(error), passed=False)
            finally:
                row.update(seconds=round(time.perf_counter()-started, 3), model_calls=provider.calls)
                await core.close()
                store.close()
            report['cases'].append(row)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
            print(json.dumps(row, ensure_ascii=False), flush=True)
    return all(row['passed'] for row in report['cases'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if not args.run:
        parser.error('Explicit --run is required for real inference.')
    raise SystemExit(0 if asyncio.run(evaluate(args)) else 1)
