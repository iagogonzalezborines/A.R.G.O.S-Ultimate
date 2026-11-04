import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from argos.core import Core
from argos.models import ArgosError, Decision
from argos.store import Store


class ProjectWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.root = self.home / 'some-and-co2'
        self.root.mkdir()
        (self.root / 'README.md').write_text('# SoMe&CO2\n\nPlataforma para calcular la huella de carbono.\n\n## Usage\nDetails.\n')
        (self.root / 'package.json').write_text(json.dumps({'name': 'co2-demo', 'description': 'Carbon accounting'}))
        self.store = Store(self.home / 'state')
        self.project = self.store.add_project('SoMe&CO2', self.root)
        self.core = Core(self.store)
        await self.core.start()

    async def asyncTearDown(self):
        await self.core.close()
        self.store.close()
        self.temp.cleanup()

    async def req(self, method, **kwargs):
        return await self.core.request({'method': method, 'request_id': uuid.uuid4().hex, **kwargs})

    async def operation(self, name, project=None, **kwargs):
        response = await self.req('run', capability=name,
            arguments={'project': project or self.project['id'], **kwargs})
        await asyncio.wait_for(self.core.queue.join(), 5)
        return self.store.task(response['task_id'])

    async def reopen(self):
        await self.core.close()
        self.store.close()
        self.store = Store(self.home / 'state')
        self.core = Core(self.store)
        await self.core.start()

    async def test_profile_is_measured_persistent_and_dated_not_a_runtime_claim(self):
        before = (self.root / 'README.md').read_bytes()
        task = await self.operation('projects.inspect')
        self.assertEqual(task['status'], 'COMPLETED')
        self.assertEqual(task['result']['verification'], 'project_inspected')
        profile = task['result']['evidence']['inspection']
        self.assertEqual(profile['description'], 'Plataforma para calcular la huella de carbono.')
        self.assertEqual(profile['description_basis'], 'documentation_excerpt')
        self.assertGreater(profile['observed_at'], 0)
        self.assertEqual(profile['sources'][0]['sha256'], hashlib.sha256(before).hexdigest())
        self.assertEqual((self.root / 'README.md').read_bytes(), before)
        await self.reopen()
        self.assertEqual(self.store.project_profile(self.project['id'])['inspection'], profile)
        (self.root / 'README.md').write_text('# New\n\nChanged documentation.\n')
        self.assertEqual((await self.operation('projects.context'))['result']['evidence']['inspection'], profile)
        self.assertEqual((await self.operation('projects.inspect'))['result']['evidence']['inspection']['description'], 'Changed documentation.')

    async def test_aliases_are_unique_idempotent_and_survive_restart(self):
        await self.operation('projects.alias', alias='Some and CO2')
        await self.operation('projects.alias', alias='some and co2')
        await self.reopen()
        self.assertEqual(self.store.project('SOME AND CO2'), self.project)
        self.assertEqual(len(self.store.project_profile(self.project['id'])['aliases']), 1)
        other = self.home / 'other'
        other.mkdir()
        second = self.store.add_project('Other', other)
        with self.assertRaises(ArgosError):
            self.store.add_project_alias(second['id'], 'Some and CO2')
        with self.assertRaises(ArgosError):
            self.store.add_project('Some and CO2', other)
        self.assertEqual((await self.operation('projects.alias', alias='Other'))['status'], 'FAILED')

    async def test_session_selection_survives_restart_without_effect_replay(self):
        response = await self.req('projects.select', project=self.project['id'], session='work')
        self.assertEqual(response['data'], self.project)
        self.assertIsNone(self.store.selected_project('other'))
        await self.reopen()
        self.assertEqual(self.store.selected_project('work'), self.project)
        self.assertEqual(self.store.tasks(), [])
        response = await self.req('projects.context', session='work')
        self.assertEqual(response['data']['project'], self.project)
        await self.req('projects.select', session='work')
        self.assertIsNone(self.store.selected_project('work'))

    async def test_selected_project_is_used_by_followup_and_explicit_override_is_temporary(self):
        self.store.select_project('default', self.project['id'])
        other = self.home / 'other'
        other.mkdir()
        second = self.store.add_project('Other', other)
        seen = []
        class Provider:
            name = 'fixture'
            async def decide(provider, text, context, agent='general'):
                seen.append(context)
                return Decision('answer', speech='Understood.')
        self.core.interpreter = Provider()
        await self.req('say', text='Tell me what we are working on.', conversation=True)
        await self.req('say', text='Discuss the other project.', project=second['id'])
        await self.req('say', text='Continue with my selected project.')
        self.assertEqual([c['project']['id'] for c in seen], [self.project['id'], second['id'], self.project['id']])
        self.assertEqual(self.store.selected_project('default'), self.project)
        self.assertEqual(self.core.context(second, 'engineering')['project_registry'], [{**second, 'aliases': []}])

    async def test_background_task_keeps_project_after_selection_changes(self):
        self.store.select_project('default', self.project['id'])
        entered, release = asyncio.Event(), asyncio.Event()
        observed = []
        class Provider:
            name = 'fixture'
            async def decide(provider, text, context, agent='general'):
                return Decision('delegate', agent='computer')
            async def work(provider, task, context, execute, save_thread, progress):
                entered.set()
                await release.wait()
                observed.append(context['project']['root'])
                result = await execute('files.read', {'file': 'README.md'})
                return {'kind': 'result', 'speech': 'Read the original project.', 'detail': result['evidence']['content']}
        self.core.interpreter = Provider()
        response = await self.req('say', text='Read my selected project.')
        await asyncio.wait_for(entered.wait(), 5)
        other = self.home / 'other'
        other.mkdir()
        second = self.store.add_project('Other', other)
        await self.req('projects.select', project=second['id'])
        release.set()
        await asyncio.wait_for(self.core.queue.join(), 5)
        task = self.store.task(response['task_id'])
        self.assertEqual(task['status'], 'COMPLETED')
        self.assertEqual(task['project'], self.project['id'])
        self.assertEqual(observed, [str(self.root)])
        self.assertEqual(self.store.selected_project('default'), second)

    async def test_specialist_cannot_inspect_another_project_and_profiles_exclude_secrets(self):
        other = self.home / 'other'
        other.mkdir()
        second = self.store.add_project('Other', other)
        task = self.store.create_task('default', self.project['id'], 'computer', 'Inspect')
        task = self.store.update(task['id'], 'RUNNING')
        with self.assertRaises(ArgosError):
            await self.core.execute_capability(task, self.project, 'projects.inspect', {'project': second['id']})
        (self.root / 'README.md').write_text('password=synthetic-private-fixture\n')
        (self.root / 'package.json').unlink()
        result = await self.operation('projects.inspect')
        encoded = json.dumps(result['result'])
        self.assertNotIn('synthetic-private-fixture', encoded)
        self.assertEqual(result['result']['evidence']['inspection']['description'], '')
        self.assertEqual(result['result']['evidence']['inspection']['sources'][0]['status'], 'protected_or_not_text')

    async def test_alias_cannot_be_a_long_term_permission_or_bypass_directory_validation(self):
        await self.operation('projects.alias', alias='My carbon project')
        await self.operation('projects.select', project='My carbon project')
        response = await self.req('run', capability='files.write', arguments={
            'file': 'new.txt', 'content': 'candidate', 'expected_sha256': ''})
        await asyncio.wait_for(self.core.queue.join(), 5)
        self.assertEqual(self.store.task(response['task_id'])['status'], 'WAITING_APPROVAL')
        self.assertFalse((self.root / 'new.txt').exists())
        moved = self.home / 'moved'
        self.root.rename(moved)
        result = await self.operation('projects.inspect')
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(self.store.selected_project('default'), self.project)

    async def test_v2_migration_keeps_projects_tasks_and_history(self):
        chat = self.store.begin_conversation(None, 'default', self.project['id'], 'fixture', 'Hello')
        self.store.finish_conversation(chat, 'Hi')
        self.store.db.executescript('DROP TABLE project_profiles; DROP TABLE project_aliases; DROP TABLE session_projects; PRAGMA user_version=2;')
        await self.reopen()
        self.assertEqual(self.store.db.execute('PRAGMA user_version').fetchone()[0], 3)
        self.assertEqual(self.store.project(self.project['id']), self.project)
        self.assertEqual(len(self.store.recent_messages(chat, 'default', self.project['id'])), 2)
        self.assertEqual(self.store.project_profile(self.project['id'])['aliases'], [])

    async def test_candidate_context_does_not_serialize_internal_executor(self):
        candidate = {**self.project, 'root': str(self.home / 'private-candidate'),
                     '_development_executor': lambda: None}
        context = self.core.context(candidate, 'engineering')
        encoded = json.dumps(context)
        self.assertNotIn('_development_executor', encoded)
        self.assertEqual(context['project']['root'], candidate['root'])
        self.assertEqual(context['project_registry'][0]['root'], str(self.root))

    async def test_large_project_profile_proposes_modules_without_reading_media(self):
        from unittest.mock import patch
        module = self.root / 'apps/backend-api'
        module.mkdir(parents=True)
        (module / 'pom.xml').write_text('<project/>')
        (self.root / 'video.mp4').write_bytes(b'x' * 200)
        with patch('argos.development_workspace.MAX_BYTES', 100):
            result = await self.operation('projects.inspect')
        metadata = result['result']['evidence']['inspection']['development']
        self.assertTrue(metadata['requires_scope'])
        self.assertFalse(metadata['complete'])
        self.assertIn({'path': 'apps/backend-api', 'manifests': ['pom.xml']}, metadata['modules'])
