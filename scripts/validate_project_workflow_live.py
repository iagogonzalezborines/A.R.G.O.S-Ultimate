#!/usr/bin/env python3
"""Opt-in project lifecycle with real Codex, temporary files and isolated tests.

No microphone, speakers, desktop actions or writes to user projects. --run also
permits approving the measured plan for this temporary fixture only.
"""
import argparse
import asyncio
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from argos.core import Core
from argos.development import Development
from argos.development_workspace import LinuxDevelopmentWorkspace, digest, tree
from argos.filesystem import path_for
from argos.inference_config import read
from argos.models import ArgosError
from argos.store import Store
from argos.transport import state_directory
from validate_adaptive_persona_live import TracedCodex


class FixtureCore(Core):
    def context(self, project, agent='general'):
        with patch('pathlib.Path.home', return_value=self.fixture_home):
            return super().context(project, agent)

    @staticmethod
    def application_names():
        return []

    async def execute_capability(self, task, project, name, args, development_scope=False):
        if not name.startswith(('files.', 'projects.', 'development.')):
            raise ArgosError('Evaluation permits project/file operations in its temporary fixture only.')
        for key in ('path', 'file', 'source', 'destination'):
            if key in args and not path_for(project, args[key]).is_relative_to(self.fixture_home):
                raise ArgosError('Evaluation path is outside its temporary fixture.')
        return await super().execute_capability(task, project, name, args, development_scope)


async def evaluate(args):
    settings = read(state_directory())
    report = {'scope': __doc__, 'stages': [], 'models': {key: value for key, value in settings.items() if key.startswith('codex_')}}
    def save():
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    with tempfile.TemporaryDirectory(prefix='argos-lifecycle-') as temporary:
        home = Path(temporary)
        project_root = home / 'Proyectos' / 'some-and-co2'
        source = project_root / args.scope if args.scope else project_root
        (source / 'tests').mkdir(parents=True)
        (source / 'README.md').write_text('# SoMe&CO2\n\nDemostración de contabilidad de carbono con normalización de identificadores.\n')
        (source / 'normalize.py').write_text('def normalize_label(value):\n    return value.strip()\n')
        (source / 'tests/test_normalize.py').write_text('import unittest\nfrom normalize import normalize_label\nclass NormalizeTests(unittest.TestCase):\n    def test_whitespace(self):\n        self.assertEqual(normalize_label("  demo  "), "demo")\n')
        (project_root / 'README.md').write_text('# SoMe&CO2\n\nDemostración de contabilidad de carbono con normalización de identificadores.\n')
        if args.scope:
            (source / 'pyproject.toml').write_text('[project]\nname = "co2-demo"\nversion = "0.0.1"\n')
        original = digest(tree(project_root))
        def make_core():
            store = Store(home / 'state')
            routine = TracedCodex(store.directory, model=settings['codex_model'], effort=settings['codex_effort'], conversation=True)
            strong = TracedCodex(store.directory / 'complex', model=settings['codex_complex_model'], effort=settings['codex_complex_effort'])
            development = Development(store, LinuxDevelopmentWorkspace(store.directory, ROOT))
            core = FixtureCore(store, routine, development=development, escalation_provider=strong)
            core.fixture_home = home
            return core, store, routine, strong
        core, store, routine, strong = make_core()
        await core.start()
        async def request(method='say', **kwargs):
            return await core.request({'method': method, 'request_id': uuid.uuid4().hex,
                                       'session': 'pilot', 'conversation': True, **kwargs})
        async def settle(response):
            await asyncio.wait_for(core.queue.join(), 240)
            return store.task(response['task_id'])
        async def turn(label, text):
            before = time.perf_counter()
            response = await request(text=text)
            task = await settle(response) if response.get('task_id') else None
            row = {'stage': label, 'input': text, 'response': response, 'seconds': round(time.perf_counter()-before, 3)}
            if task:
                row['task'] = {key: task[key] for key in ('id', 'project', 'status', 'question', 'result')}
            report['stages'].append(row)
            save()
            print(json.dumps({'stage': label, 'seconds': row['seconds'], 'speech': response['speech'], 'status': task['status'] if task else None}, ensure_ascii=False), flush=True)
            return response, task
        try:
            _, task = await turn('discover_register_select_inspect', 'Busca mi proyecto existente Sum and CO2 en mi carpeta de proyectos Linux. Regístralo como SoMe&CO2, selecciónalo para trabajar y dime brevemente de qué trata según su documentación.')
            selected = store.selected_project('pilot')
            if not selected or selected['root'] != str(project_root) or not store.project_profile(selected['id'])['inspection']:
                raise ArgosError('The model did not finish discovery/registration/selection/inspection.')
            await turn('confirmed_alias', 'Guarda "mi proyecto de carbono" como alias de este proyecto.')
            if store.project('mi proyecto de carbono')['id'] != selected['id']:
                raise ArgosError('Confirmed alias was not persisted.')
            task_count = len(store.tasks('pilot'))
            await core.close()
            store.close()
            core, store, routine, strong = make_core()
            await core.start()
            if len(store.tasks('pilot')) != task_count or store.selected_project('pilot')['id'] != selected['id']:
                raise ArgosError('Restart changed selection or replayed tasks.')
            await turn('resume_after_restart', '¿Qué proyecto tenemos seleccionado y para qué sirve? Responde brevemente sin ejecutar nuevas tareas.')
            response, plan_task = await turn('prepare_candidate_plan', ('En el módulo ' + args.scope + ', ' if args.scope else '') + 'Prepara una mejora pequeña del proyecto seleccionado: normalize_label debe quitar espacios exteriores y convertir las letras a minúsculas. Conserva la prueba actual, añade regresiones para mayúsculas y texto vacío, y comprueba todo con python3 -m unittest discover -s tests -v. Trabaja en una candidata aislada y presenta el plan antes de editar; no apliques la candidata al origen.')
            if not plan_task or plan_task['status'] != 'WAITING_APPROVAL':
                raise ArgosError('The development request did not stop at plan approval.')
            state = core.development.state(plan_task['id'])
            if state['source'] != str(source) or digest(tree(project_root)) != original:
                raise ArgosError('The plan is not bound to the fixture or changed its source.')
            plan = plan_task['result']['pending_plan']
            if not plan['checks'] or any(check[:3] != ['python3', '-m', 'unittest'] for check in plan['checks']):
                raise ArgosError('The temporary plan proposed an unexpected check; not approved.')
            await request('approve', task_id=plan_task['id'], fingerprint=plan['fingerprint'])
            other_root = home / 'Proyectos' / 'other'
            other_root.mkdir()
            other = store.add_project('Other', other_root)
            await request('projects.select', project=other['id'])
            done = await settle(response)
            result = done['result'] or {}
            passed = (done['status'] == 'COMPLETED' and done['project'] == selected['id']
                      and result.get('verification') == 'command_passed' and not result.get('activated')
                      and digest(tree(project_root)) == original and store.selected_project('pilot')['id'] == other['id'])
            report['stages'].append({'stage': 'candidate_checks_with_independent_session_switch', 'passed': passed, 'result': result})
            if result.get('patch'):
                shutil.copyfile(result['patch'], args.report.with_suffix('.patch'))
            report['passed'] = passed
            report['limits'] = 'Text simulates recognized voice; real model/tool/restart/sandbox checks. No acoustic, latency-to-first-audio or real project edits validated.'
            save()
            print(json.dumps({'passed': passed, 'verification': result.get('verification'), 'changed_files': result.get('changed_files')}), flush=True)
        except (ArgosError, TimeoutError) as error:
            report.update(passed=False, error=str(error))
            save()
            print(json.dumps({'passed': False, 'error': str(error)}, ensure_ascii=False), flush=True)
        finally:
            await core.close()
            store.close()
    return report.get('passed', False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--scope', default='', help='Optional relative fixture module, e.g. apps/backend-api')
    args = parser.parse_args()
    if Path(args.scope).is_absolute() or '..' in Path(args.scope).parts:
        parser.error('Scope must be a relative fixture module.')
    if not args.run:
        parser.error('Explicit --run is required for real inference and fixture-only plan approval.')
    raise SystemExit(0 if asyncio.run(evaluate(args)) else 1)
