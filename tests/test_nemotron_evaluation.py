import io
import json
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import AsyncMock, Mock, patch

from argos.models import ArgosError

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from validate_nemotron_live import ENDPOINT, NemotronEvaluation, read_api_key, run, validate_api_key
sys.path.pop(0)


def response(finish="stop", **wire_changes):
    wire = {"kind": "answer", "speech": "Lo llamamos Helios.", "target_agent": "", "tool": "", "tool_arguments": {}}
    wire.update(wire_changes)
    reply = io.BytesIO(json.dumps({
        "choices": [{"finish_reason": finish, "message": {
            "role": "assistant", "content": json.dumps(wire), "reasoning_content": "private fixture reasoning"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "private": "discard"}
    }).encode())
    reply.status = 200
    return reply



class NemotronEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_opaque_token_is_accepted_only_in_authorization_header(self):
        key = "nvapi-" + "a" * 1500
        provider = NemotronEvaluation(key, {"models": []})
        opener = Mock()
        opener.open.return_value = response()
        with patch.object(provider, "_opener", return_value=opener):
            await provider.decide("Hola", {})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer " + key)
        self.assertNotIn(key.encode(), request.data)
        self.assertNotIn(key, json.dumps(provider.decisions))

    def test_empty_and_invalid_header_input_can_be_corrected_without_echo(self):
        diagnostics = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), patch("sys.stdin.isatty", return_value=True), patch(
                "validate_nemotron_live.getpass.getpass", side_effect=["", "private invalid token", "fixture-key"]) as prompt, redirect_stderr(diagnostics):
            self.assertEqual(read_api_key(), "fixture-key")
        self.assertEqual(prompt.call_count, 3)
        self.assertIn("No se recibió", diagnostics.getvalue())
        self.assertNotIn("private invalid token", diagnostics.getvalue())
        self.assertNotIn("fixture-key", diagnostics.getvalue())

    def test_header_controls_and_excessive_input_are_rejected_without_echo(self):
        for key in ("private\x00key", "private\r\nkey", "private key", "privateé", "a" * 8193):
            with self.subTest(length=len(key)), self.assertRaises(ArgosError) as caught:
                validate_api_key(key)
            self.assertNotIn(key, str(caught.exception))

    async def test_pending_and_native_tool_responses_are_not_accepted_as_answers(self):
        for pending in (True, False):
            with self.subTest(pending=pending):
                provider = NemotronEvaluation("fixture-key", {"models": []})
                reply = response()
                if pending:
                    reply.status = 202
                else:
                    data = json.loads(reply.getvalue())
                    data["choices"][0]["message"]["tool_calls"] = [{"id": "unexecuted"}]
                    reply = io.BytesIO(json.dumps(data).encode())
                    reply.status = 200
                opener = Mock()
                opener.open.return_value = reply
                with patch.object(provider, "_opener", return_value=opener), self.assertRaises(ArgosError):
                    await provider.decide("Hola", {})
                self.assertTrue(provider.stopped)
                self.assertEqual(provider.decisions, [])

    async def test_auth_failure_stops_without_exposing_response_or_retrying(self):
        provider = NemotronEvaluation("fixture-key", {"models": []})
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError(ENDPOINT, 401, "fixture-key", {}, io.BytesIO(b"private"))
        with patch.object(provider, "_opener", return_value=opener), self.assertRaises(ArgosError) as caught:
            await provider.decide("Hola", {})
        self.assertIn("401", str(caught.exception))
        self.assertNotIn("fixture-key", str(caught.exception))
        self.assertEqual(opener.open.call_count, 1)
        self.assertTrue(provider.stopped)

    async def test_temporary_503_retries_same_turn_and_preserves_answer_once(self):
        provider = NemotronEvaluation("fixture-key", {"models": []})
        opener = Mock()
        opener.open.side_effect = [
            urllib.error.HTTPError(ENDPOINT, 503, "private server detail", {}, io.BytesIO()),
            urllib.error.HTTPError(ENDPOINT, 503, "private server detail", {}, io.BytesIO()), response()]
        with patch.object(provider, "_opener", return_value=opener), patch(
                "validate_nemotron_live.asyncio.sleep", new_callable=AsyncMock) as sleep:
            decision = await provider.decide("¿Cómo lo llamamos?", {})
        self.assertEqual(decision.speech, "Lo llamamos Helios.")
        self.assertEqual(provider.http_attempts, 3)
        self.assertEqual(len(provider.decisions), 1)
        self.assertFalse(provider.stopped)
        self.assertEqual([c.args[0] for c in sleep.await_args_list], [1, 2])
        self.assertEqual(len({c.args[0].data for c in opener.open.call_args_list}), 1)

    async def test_repeated_503_stops_after_three_attempts(self):
        provider = NemotronEvaluation("fixture-key", {"models": []})
        opener = Mock()
        opener.open.side_effect = [urllib.error.HTTPError(ENDPOINT, 503, "private", {}, io.BytesIO()) for _ in range(3)]
        with patch.object(provider, "_opener", return_value=opener), patch(
                "validate_nemotron_live.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaisesRegex(ArgosError, "temporalmente no disponible") as caught:
                await provider.decide("Hola", {})
            with self.assertRaisesRegex(ArgosError, "detenida"):
                await provider.decide("¿Hola?", {})
        self.assertNotIn("private", str(caught.exception))
        self.assertNotIn("clave", str(caught.exception))
        self.assertEqual(opener.open.call_count, 3)
        self.assertEqual(provider.decisions, [])

    async def test_runner_reports_remaining_turns_as_unattempted_after_failure(self):
        opener = Mock()
        opener.open.side_effect = [response(), urllib.error.HTTPError(ENDPOINT, 429, "private", {}, io.BytesIO())]
        with tempfile.TemporaryDirectory() as temp, patch.object(NemotronEvaluation, "_opener", return_value=opener), redirect_stdout(io.StringIO()):
            args = Namespace(report=Path(temp) / "report.json", scenario=None)
            result = await run(args, "fixture-key")
            report = json.loads(args.report.read_text())
        self.assertEqual(result, 1)
        self.assertEqual(len(report["turns"]), 2)
        self.assertEqual(report["skipped_turns"], 21)
        self.assertEqual(report["http_attempts"], 2)
        self.assertEqual(report["stopped_after"]["turn"], 2)
        self.assertTrue(report["no_tasks_created"])
        self.assertFalse(report["structural_checks_passed"])
        self.assertNotIn("fixture-key", json.dumps(report))

    async def test_one_request_preserves_public_history_and_discards_reasoning(self):
        report = {"models": []}
        provider = NemotronEvaluation("fixture-secret-value", report)
        opener = Mock()
        opener.open.return_value = response()
        history = [{"role": "user", "content": "El soporte es Helios."},
                   {"role": "assistant", "content": "Entendido."}]
        with patch.object(provider, "_opener", return_value=opener):
            decision = await provider.decide("¿Cómo lo llamamos?", {"recent_conversation": history})
        self.assertEqual(decision.speech, "Lo llamamos Helios.")
        self.assertEqual(opener.open.call_count, 1)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, ENDPOINT)
        self.assertEqual(request.get_header("Authorization"), "Bearer fixture-secret-value")
        self.assertNotIn(b"fixture-secret-value", request.data)
        payload = json.loads(request.data)
        self.assertEqual([item["role"] for item in payload["messages"]], ["system", "user", "user", "assistant", "user"])
        self.assertEqual(payload["messages"][2]["content"], history[0]["content"])
        self.assertNotIn("always stay local", payload["messages"][0]["content"])
        self.assertNotIn("private fixture reasoning", json.dumps(provider.decisions))
        self.assertNotIn("private", provider.metrics)
        self.assertEqual(payload["reasoning_effort"], "none")
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertFalse(payload["stream"])

    async def test_truncation_is_rejected_and_stops_subsequent_network_calls(self):
        provider = NemotronEvaluation("fixture-key", {"models": []})
        opener = Mock()
        opener.open.return_value = response("length")
        with patch.object(provider, "_opener", return_value=opener):
            with self.assertRaisesRegex(ArgosError, "truncado"):
                await provider.decide("Hola", {})
            with self.assertRaisesRegex(ArgosError, "detenida"):
                await provider.decide("Otra vez", {})
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual(provider.decisions, [])

    async def test_quota_error_is_safe_and_never_retries(self):
        provider = NemotronEvaluation("fixture-key", {"models": []})
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError(
            ENDPOINT, 429, "secret server detail", {}, io.BytesIO(b"private error body"))
        with patch.object(provider, "_opener", return_value=opener):
            with self.assertRaises(ArgosError) as caught:
                await provider.decide("Hola", {})
        self.assertIn("límite de uso", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))
        self.assertNotIn("private", str(caught.exception))
        self.assertEqual(opener.open.call_count, 1)

    async def test_unregistered_capability_is_rejected(self):
        provider = NemotronEvaluation("fixture-key", {"models": []})
        opener = Mock()
        opener.open.return_value = response(kind="capability", tool="invented.action", target_agent="computer")
        with patch.object(provider, "_opener", return_value=opener), self.assertRaises(ArgosError):
            await provider.decide("Hola", {})
        self.assertEqual(provider.decisions, [])

    def test_redirects_cannot_forward_the_key(self):
        provider = NemotronEvaluation("fixture-key", {"models": []})
        handler = next(h for h in provider._opener().handlers if hasattr(h, "redirect_request"))
        self.assertIsNone(handler.redirect_request(None, None, 302, "", {}, "https://example.invalid"))


if __name__ == "__main__":
    unittest.main()
