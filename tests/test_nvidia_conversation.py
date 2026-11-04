import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
import uuid
from unittest.mock import Mock, patch

from argos.core import Core
from argos.inference_config import read, write
from argos.models import ArgosError
from argos.nvidia import ENDPOINT, NvidiaConversation, read_private_key
from argos.store import Store
from argos.providers import VOICE_DELIVERY, decision_messages
from test_nemotron_evaluation import response


class LocalTrap:
    name = 'ollama'
    model = 'fixture-local'
    calls = 0

    async def decide(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError('No conversation fallback allowed')


class NvidiaConversationTests(unittest.IsolatedAsyncioTestCase):
    def test_voice_delivery_is_immediately_before_current_question_without_rewriting_history(self):
        history = [{'role': 'user', 'content': 'Explain in detail.'},
                   {'role': 'assistant', 'content': 'A previous long explanation.'}]
        context = {'interaction': {'channel': 'voice'}, 'recent_conversation': history}
        messages = decision_messages('Is eight greater than three?', context)
        self.assertEqual(messages[2:4], history)
        self.assertEqual(messages[-2], {'role': 'system', 'content': VOICE_DELIVERY})
        self.assertEqual(messages[-1], {'role': 'user', 'content': 'Is eight greater than three?'})
        self.assertEqual(sum(m.get('content') == VOICE_DELIVERY for m in messages), 1)
        self.assertNotIn(VOICE_DELIVERY, str(decision_messages('Explain', {'interaction': {'channel': 'text'}})))
        self.assertNotIn(VOICE_DELIVERY, str(decision_messages('Work', context, 'engineering')))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.key = self.directory / 'nvidia.key'
        self.key.write_text('fixture-private-key')
        self.key.chmod(0o600)
        self.provider = NvidiaConversation(self.key)

    def tearDown(self):
        self.temp.cleanup()

    async def test_headers_only_credential_history_and_only_public_content(self):
        opener = Mock()
        opener.open.return_value = response()
        history = [{'role': 'user', 'content': 'El soporte es Helios.'},
                   {'role': 'assistant', 'content': 'Entendido.'}]
        with patch.object(self.provider, '_opener', return_value=opener):
            result = await self.provider.decide('¿Cómo lo llamamos?', {'recent_conversation': history})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, ENDPOINT)
        self.assertEqual(request.get_header('Authorization'), 'Bearer fixture-private-key')
        self.assertNotIn(b'fixture-private-key', request.data)
        payload = json.loads(request.data)
        self.assertEqual(payload['messages'][2:4], history)
        self.assertNotIn('always stay local', payload['messages'][0]['content'])
        self.assertEqual(payload['reasoning_effort'], 'none')
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 20)
        self.assertEqual(result.speech, 'Lo llamamos Helios.')
        self.assertNotIn('private', json.dumps(self.provider.metrics))
        self.assertTrue(self.provider.connected)

    async def test_core_conversation_is_remote_tasks_and_status_stay_local(self):
        store = Store(self.directory / 'state')
        local = LocalTrap()
        core = Core(store, local, conversation_provider=self.provider)
        await core.start()
        opener = Mock()
        opener.open.side_effect = [response(), response()]
        try:
            with patch.object(self.provider, '_opener', return_value=opener):
                for text in ('El soporte se llama Helios. Solo hablamos.', '¿Cómo se llama el soporte?'):
                    result = await core.request({'method': 'say', 'text': text, 'session': 'test',
                        'conversation': True, 'request_id': uuid.uuid4().hex})
            self.assertEqual(result['speech'], 'Lo llamamos Helios.')
            self.assertEqual(local.calls, 0)
            self.assertEqual(core.inference_status()['conversation'], 'nvidia')
            self.assertEqual(core.inference_status()['routine_tasks'], 'ollama')
            agents = {a['id']: a for a in core.agent_catalogue()}
            self.assertEqual(agents['general']['provider'], 'nvidia')
            self.assertEqual(agents['engineering']['provider'], 'ollama')
            self.assertIs(core.task_provider({'id': 'a' * 32}), local)
            self.assertEqual(store.tasks(), [])
            history = [m for m in json.loads(opener.open.call_args.args[0].data)['messages'][2:-1]
                       if m['role'] != 'system']
            self.assertEqual(len(history), 2)
        finally:
            await core.close()
            store.close()

    async def test_failure_does_not_retry_or_fallback_and_next_user_turn_can_recover(self):
        store = Store(self.directory / 'state')
        local, escalation = LocalTrap(), LocalTrap()
        core = Core(store, local, conversation_provider=self.provider, escalation_provider=escalation)
        await core.start()
        opener = Mock()
        opener.open.side_effect = [urllib.error.HTTPError(ENDPOINT, 503, 'fixture-private-key', {}, io.BytesIO(b'private')), response()]
        try:
            with patch.object(self.provider, '_opener', return_value=opener):
                with self.assertRaises(ArgosError) as caught:
                    await core.request({'method': 'say', 'text': 'Un turno que falla.', 'request_id': uuid.uuid4().hex})
                self.assertNotIn('fixture-private-key', str(caught.exception))
                self.assertEqual(opener.open.call_count, 1)
                await core.request({'method': 'say', 'text': 'Ahora dime algo breve.', 'request_id': uuid.uuid4().hex})
            self.assertTrue(self.provider.connected)
            self.assertEqual(local.calls + escalation.calls, 0)
            self.assertEqual(len(json.loads(opener.open.call_args.args[0].data)['messages']), 3)
            self.assertEqual(store.tasks(), [])
        finally:
            await core.close()
            store.close()

    async def test_invalid_or_truncated_decisions_are_rejected(self):
        for reply in (response('length'), response(target_agent='computer'),
                      response(speech=''), response(kind='panel', tool_arguments={'view': 'agents'})):
            opener = Mock()
            opener.open.return_value = reply
            with patch.object(self.provider, '_opener', return_value=opener), self.assertRaises(ArgosError):
                await self.provider.decide('Hola', {})
            self.assertFalse(self.provider.connected)

    async def test_voice_keeps_network_budget_and_reports_safe_timeout_without_retry(self):
        opener = Mock()
        opener.open.side_effect = TimeoutError('fixture-private-key')
        with patch.object(self.provider, '_opener', return_value=opener):
            with self.assertRaisesRegex(ArgosError, 'NVIDIA tarda demasiado'):
                await self.provider.decide('Hello', {'interaction': {'channel': 'voice'}})
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 20)
        self.assertFalse(self.provider.connected)
        # Voice retains the same complete-output budget as text.
        payload = json.loads(opener.open.call_args.args[0].data)
        self.assertEqual(payload['max_tokens'], 4096)

    async def test_specialists_and_redirects_are_rejected(self):
        with self.assertRaises(ArgosError):
            await self.provider.decide('Work', {}, agent='engineering')
        handler = next(h for h in self.provider._opener().handlers if hasattr(h, 'redirect_request'))
        self.assertIsNone(handler.redirect_request(None, None, 302, '', {}, 'https://example.invalid'))

    def test_private_file_and_config_backwards_compatibility(self):
        self.assertEqual(read_private_key(self.key), 'fixture-private-key')
        self.key.chmod(0o644)
        with self.assertRaises(ArgosError):
            read_private_key(self.key)
        self.key.chmod(0o600)
        link = self.directory / 'link'
        link.symlink_to(self.key)
        with self.assertRaises(ArgosError):
            read_private_key(link)
        write(self.directory, 'fixture-local', True)
        self.assertEqual(read(self.directory), {'ollama_model': 'fixture-local', 'codex_escalation': True})
        write(self.directory, 'fixture-local', True, 'nvidia')
        self.assertEqual(read(self.directory)['conversation_provider'], 'nvidia')
        with self.assertRaises(ArgosError):
            write(self.directory, 'fixture-local', True, 'unknown')
