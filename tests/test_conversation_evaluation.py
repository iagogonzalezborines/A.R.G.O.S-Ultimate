import io
import json
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from validate_conversation_live import CASES, TracedProvider, assess, run, save_report, summarize
from argos.providers import decision_messages
from argos.capabilities import CAPABILITIES
from test_nemotron_evaluation import response
sys.path.pop(0)


class ConversationEvaluationTests(unittest.IsolatedAsyncioTestCase):
    def test_compact_context_retains_tool_semantics_and_effects(self):
        cap = CAPABILITIES['files.delete'].public()
        content = decision_messages('¿Qué hace borrar?', {'capabilities': [cap]})[1]['content']
        compact = json.loads(content.split('\n', 1)[1])['capabilities'][0]
        self.assertEqual(compact['description'], cap['description'])
        self.assertEqual(compact['effect'], 'write')
        self.assertEqual(compact['needs_project'], cap['needs_project'])
        self.assertIn('papelera', compact['description'])

    def test_large_audit_is_validated_per_record_and_written_completely(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.json'
            report = {'turns': [{'input': 'synthetic ' * 5000} for _ in range(8)]}
            save_report(path, report)
            self.assertEqual(json.loads(path.read_text()), report)
            self.assertFalse(path.with_suffix('.json.tmp').exists())

    async def test_history_survives_restart_and_does_not_cross_sessions(self):
        opener = Mock()
        opener.open.side_effect = [response(speech='Entendido: Lumen, 18 centímetros.'),
                                   response(speech='Lumen, 18 centímetros.'),
                                   response(kind='clarify', speech='¿De qué maqueta hablamos?')]
        with tempfile.TemporaryDirectory() as tmp, patch.object(TracedProvider, '_opener', return_value=opener), redirect_stdout(io.StringIO()):
            args = Namespace(contract=None, scenario=['restart', 'isolation'], repeat=1, report=Path(tmp) / 'report.json')
            self.assertEqual(await run(args, 'fixture-secret'), 0)
            report = json.loads(args.report.read_text())
        self.assertTrue(all(all(t['checks'].values()) for t in report['turns']))
        self.assertEqual([t['trace']['history_messages'] for t in report['turns']], [0, 2, 0])
        self.assertNotIn('fixture-secret', json.dumps(report))
        self.assertNotIn('private fixture reasoning', json.dumps(report))

    async def test_twenty_turn_core_trace_keeps_only_latest_sixteen_complete_pairs(self):
        opener = Mock()
        opener.open.side_effect = [response(speech='Azul mate, madera, 35 euros.') for _ in CASES['long_context']]
        with tempfile.TemporaryDirectory() as tmp, patch.object(TracedProvider, '_opener', return_value=opener), redirect_stdout(io.StringIO()):
            args = Namespace(contract=None, scenario=['long_context'], repeat=1, report=Path(tmp) / 'report.json')
            self.assertEqual(await run(args, 'fixture-secret'), 0)
            report = json.loads(args.report.read_text())
        self.assertEqual(len(report['turns']), 20)
        final_history = report['turns'][-1]['trace']['context']['recent_conversation']
        self.assertEqual(len(final_history), 32)
        self.assertEqual(final_history[0]['content'], CASES['long_context'][3]['text'])
        self.assertTrue(all(t['checks']['history_exact'] for t in report['turns']))

    async def test_expected_action_is_observed_but_never_executed(self):
        opener = Mock()
        opener.open.return_value = response(kind='capability', speech='Crear la carpeta.',
            target_agent='engineering', tool='files.mkdir', tool_arguments={'path': '/tmp/argos-evaluation-example'})
        with tempfile.TemporaryDirectory() as tmp, patch.object(TracedProvider, '_opener', return_value=opener), redirect_stdout(io.StringIO()):
            args = Namespace(contract=None, scenario=['routing_file'], repeat=1, report=Path(tmp) / 'report.json')
            self.assertEqual(await run(args, 'fixture-secret'), 0)
            report = json.loads(args.report.read_text())
        self.assertTrue(report['no_tasks_created'])
        self.assertIn('blocked an unexpected action', report['turns'][0]['error'])
        self.assertTrue(all(report['turns'][0]['checks'].values()))

    async def test_core_routing_needs_no_model_and_panel_is_advertised_without_opening(self):
        opener = Mock()
        opener.open.return_value = response(kind='panel', speech='Mostrar agentes.', tool_arguments={'view': 'agents'})
        with tempfile.TemporaryDirectory() as tmp, patch.object(TracedProvider, '_opener', return_value=opener), redirect_stdout(io.StringIO()):
            args = Namespace(contract=None, scenario=['routing_research', 'routing_panel'], repeat=1, report=Path(tmp) / 'report.json')
            self.assertEqual(await run(args, 'fixture-secret'), 0)
            report = json.loads(args.report.read_text())
        first, second = report['turns']
        self.assertEqual(first['decision_source'], 'core')
        self.assertEqual(first['http_attempts'], 0)
        self.assertEqual(first['decision']['agent'], 'research')
        self.assertEqual(second['trace']['context']['panels'], ['agents', 'tasks'])
        self.assertIn('blocked a panel', second['error'])
        self.assertEqual(opener.open.call_count, 1)
        self.assertTrue(report['no_tasks_created'])

    async def test_contract_override_is_exact_and_rubric_never_sent(self):
        opener = Mock()
        opener.open.return_value = response()
        provider = TracedProvider('fixture-secret', {'models': []}, 'Explicit candidate contract')
        with patch.object(provider, '_opener', return_value=opener):
            await provider.decide('Hello', {'recent_conversation': []})
        payload = json.loads(opener.open.call_args.args[0].data)
        self.assertEqual(payload['messages'][0]['content'], 'Explicit candidate contract')
        self.assertNotIn('proportional_length', str(payload))
        self.assertNotIn('budget', str(payload))

    async def test_failed_provider_stops_and_reports_unattempted_turns(self):
        opener = Mock()
        opener.open.side_effect = TimeoutError('private server detail')
        with tempfile.TemporaryDirectory() as tmp, patch.object(TracedProvider, '_opener', return_value=opener), redirect_stdout(io.StringIO()):
            args = Namespace(contract=None, scenario=['obvious'], repeat=1, report=Path(tmp) / 'report.json')
            self.assertEqual(await run(args, 'fixture-secret'), 1)
            report = json.loads(args.report.read_text())
        self.assertEqual(report['summary']['attempted_turns'], 1)
        self.assertEqual(report['skipped_turns'], len(CASES['obvious']) - 1)
        self.assertEqual(report['summary']['provider_failures'], 1)
        self.assertNotIn('private server detail', json.dumps(report))

    def test_length_is_a_diagnostic_and_never_changes_speech(self):
        record = {'decision': {'kind': 'answer', 'speech': 'One two three four.'}}
        self.assertFalse(assess(record, {'kinds': ['answer'], 'budget': 2})['proportional_length'])
        self.assertEqual(record['decision']['speech'], 'One two three four.')

    async def test_independent_scenarios_skip_failed_turns_and_stop_after_three_failures(self):
        opener = Mock()
        opener.open.side_effect = TimeoutError('private')
        with tempfile.TemporaryDirectory() as tmp, patch.object(TracedProvider, '_opener', return_value=opener), redirect_stdout(io.StringIO()):
            args = Namespace(contract=None, scenario=['obvious', 'heldout', 'nuance', 'isolation'], repeat=1,
                             independent_scenarios=True, report=Path(tmp) / 'report.json')
            self.assertEqual(await run(args, 'fixture-secret'), 1)
            report = json.loads(args.report.read_text())
        self.assertEqual(opener.open.call_count, 3)
        self.assertEqual([t['scenario'] for t in report['turns']], ['obvious', 'heldout', 'nuance'])
        self.assertTrue(all(t['turn'] == 1 for t in report['turns']))
        self.assertEqual(report['skipped_turns'], report['planned_turns'] - 3)

    async def test_independent_scenarios_never_continue_after_quota(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError('https://example.invalid', 429, 'private', {}, io.BytesIO())
        with tempfile.TemporaryDirectory() as tmp, patch.object(TracedProvider, '_opener', return_value=opener), redirect_stdout(io.StringIO()):
            args = Namespace(contract=None, scenario=['obvious', 'heldout'], repeat=1,
                             independent_scenarios=True, report=Path(tmp) / 'report.json')
            self.assertEqual(await run(args, 'fixture-secret'), 1)
            report = json.loads(args.report.read_text())
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual(report['turns'][0]['request_trace']['attempts'][0]['status'], 429)
        self.assertNotIn('fixture-secret', json.dumps(report))

    def test_latency_includes_failures_without_counting_them_as_valid_replies(self):
        report = summarize([
            {'seconds': 2, 'decision': {'kind': 'answer'}, 'http_attempts': 1, 'checks': {'intent': True}},
            {'seconds': 60, 'decision': None, 'provider_stopped': True, 'http_attempts': 1, 'checks': {'intent': False}}])
        self.assertEqual(report['median_seconds'], 2)
        self.assertEqual(report['over_5_seconds_including_failures'], 1)
        self.assertEqual(report['provider_failures'], 1)
        self.assertEqual(report['http_attempts'], 2)
