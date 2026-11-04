import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from argos.codex import Codex, DECISION_SCHEMA, RESULT_SCHEMA
from argos.core import Core
from argos.inference_config import read, write
from argos.models import ArgosError
from argos.store import Store
from argos.telemetry import snapshot


class ProfilesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'state')
        self.light = Codex(self.root, model='test-light', effort='low', conversation=True)
        self.strong = Codex(self.root, model='test-strong', effort='high')
        self.core = Core(self.store, self.light, escalation_provider=self.strong)

    async def asyncTearDown(self):
        await self.light.close()
        await self.strong.close()
        self.store.close()
        self.temp.cleanup()

    async def test_role_profiles_are_pinned_and_monitor_matches(self):
        for agent in ('computer', 'research', 'engineering', 'design3d', 'printing3d'):
            task = self.store.create_task('default', None, agent, 'Fixture')
            expected = self.light if agent in ('computer', 'research') else self.strong
            self.assertIs(self.core.task_provider(task), expected)
            binding = self.store.setting('task.provider:' + task['id'])
            self.assertEqual((binding['model'], binding['effort']), (expected.model, expected.effort))
        agents = {a['id']: a for a in snapshot(self.core, {})['agents']}
        self.assertEqual(agents['engineering']['model'], 'test-strong')
        self.assertEqual(agents['general']['model'], 'test-light')
        self.assertEqual(self.core.inference_status()['policy'], 'codex_profiles')

    async def test_same_provider_name_cannot_resume_task_with_different_model_or_effort(self):
        task = self.store.create_task('default', None, 'engineering', 'Fixture')
        self.core.task_provider(task)
        self.strong.model = 'changed'
        with self.assertRaises(ArgosError):
            self.core.task_provider(task)
        self.strong.model = 'test-strong'
        self.strong.effort = 'low'
        with self.assertRaises(ArgosError):
            self.core.task_provider(task)

    async def test_general_uses_one_turn_with_history_and_releases_remote_thread(self):
        context = {'session': 'voice', 'recent_conversation': [
            {'role': 'user', 'content': 'My project is Orion.'},
            {'role': 'assistant', 'content': 'Orion. Understood.'}]}
        with patch.object(self.light, 'thread', AsyncMock(side_effect=['one', 'two'])) as thread, \
             patch.object(self.light, 'rpc', AsyncMock()) as rpc, \
             patch.object(self.light, 'turn', AsyncMock(side_effect=[
                 {'kind': 'answer', 'speech': 'Orion.', 'agent': '', 'capability': '', 'arguments_json': '{}'},
                 {'kind': 'answer', 'speech': 'Here.', 'agent': '', 'capability': '', 'arguments_json': '{}'}])) as turn:
            await self.light.prepare(context)
            result = await self.light.decide('What is it called?', context)
            self.assertEqual(result.speech, 'Orion.')
            self.assertEqual(turn.await_count, 1)
            payload = json.loads(turn.call_args.args[1])
            self.assertIn(context['recent_conversation'][0], payload['messages'])
            self.assertEqual(turn.call_args.kwargs['effort'], 'low')
            self.assertFalse(self.light.chat_threads)
            self.assertEqual(self.light.conversation_thread(context), 'one')
            rpc.assert_awaited_with('thread/unsubscribe', {'threadId': 'one'})
            await self.light.decide('Are you there?', context)
            self.assertEqual(thread.await_count, 2)

    async def test_malformed_arguments_never_become_an_action(self):
        with patch.object(self.light, 'thread', AsyncMock(return_value='one')), \
             patch.object(self.light, 'rpc', AsyncMock()), \
             patch.object(self.light, 'turn', AsyncMock(return_value={
                 'kind': 'capability', 'speech': 'Opening.', 'agent': 'computer',
                 'capability': 'apps.open', 'arguments_json': ''})):
            with self.assertRaises(ArgosError):
                await self.light.decide('Open Firefox', {})

    async def test_thread_model_is_explicit_and_mismatch_prevents_turn(self):
        with patch.object(self.light, 'start', AsyncMock()), patch.object(self.light, 'rpc', AsyncMock(
                return_value={'model': 'test-light', 'thread': {'id': 'one'}})) as rpc:
            await self.light.thread('general', ephemeral=True)
            params = rpc.call_args.args[1]
            self.assertEqual(params['model'], 'test-light')
            self.assertEqual(params['dynamicTools'], [])
            self.assertTrue(params['ephemeral'])
            rpc.return_value = {'model': 'wrong', 'thread': {'id': 'two'}}
            with self.assertRaises(ArgosError):
                await self.light.thread('general')

    async def test_profile_configuration_needs_no_ollama(self):
        expected = write(self.root, None, True, 'codex', codex_model='test-light', codex_effort='low',
                         codex_complex_model='test-strong', codex_complex_effort='high')
        self.assertEqual(read(self.root), expected)
        with self.assertRaises(ArgosError):
            write(self.root, None, True, 'codex')
        with self.assertRaises(ArgosError):
            Codex(self.root, conversation=True)
