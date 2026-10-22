import io
import json
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import AsyncMock, Mock, patch

from argos.models import ArgosError

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from validate_gemini_live import ENDPOINT, GeminiEvaluation, run
sys.path.pop(0)


def response(finish="STOP", **wire_changes):
    wire = {"kind": "answer", "speech": "Lo llamamos Helios.", "target_agent": "", "tool": "", "tool_arguments": {}}
    wire.update(wire_changes)
    return io.BytesIO(json.dumps({
        "candidates": [{"finishReason": finish, "content": {"parts": [
            {"thought": True, "text": "private fixture reasoning"}, {"text": json.dumps(wire)}]}}],
        "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 20, "private": "discard"}
    }).encode())


class GeminiEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_temporary_503_retries_same_turn_and_preserves_answer_once(self):
        provider = GeminiEvaluation("fixture-key", {"models": []})
        opener = Mock()
        opener.open.side_effect = [
            urllib.error.HTTPError(ENDPOINT, 503, "private server detail", {}, io.BytesIO()),
            urllib.error.HTTPError(ENDPOINT, 503, "private server detail", {}, io.BytesIO()), response()]
        with patch.object(provider, "_opener", return_value=opener), patch(
                "validate_gemini_live.asyncio.sleep", new_callable=AsyncMock) as sleep:
            decision = await provider.decide("¿Cómo lo llamamos?", {})
        self.assertEqual(decision.speech, "Lo llamamos Helios.")
        self.assertEqual(provider.http_attempts, 3)
        self.assertEqual(len(provider.decisions), 1)
        self.assertFalse(provider.stopped)
        self.assertEqual([c.args[0] for c in sleep.await_args_list], [1, 2])
        self.assertEqual(len({c.args[0].data for c in opener.open.call_args_list}), 1)

    async def test_repeated_503_stops_after_three_attempts(self):
        provider = GeminiEvaluation("fixture-key", {"models": []})
        opener = Mock()
        opener.open.side_effect = [urllib.error.HTTPError(ENDPOINT, 503, "private", {}, io.BytesIO()) for _ in range(3)]
        with patch.object(provider, "_opener", return_value=opener), patch(
                "validate_gemini_live.asyncio.sleep", new_callable=AsyncMock):
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
        with tempfile.TemporaryDirectory() as temp, patch.object(GeminiEvaluation, "_opener", return_value=opener), redirect_stdout(io.StringIO()):
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
        provider = GeminiEvaluation("fixture-secret-value", report)
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
        self.assertEqual(request.get_header("X-goog-api-key"), "fixture-secret-value")
        self.assertNotIn(b"fixture-secret-value", request.data)
        payload = json.loads(request.data)
        self.assertEqual([item["role"] for item in payload["contents"]], ["user", "user", "model", "user"])
        self.assertEqual(payload["contents"][1]["parts"][0]["text"], history[0]["content"])
        self.assertNotIn("always stay local", payload["systemInstruction"]["parts"][0]["text"])
        self.assertNotIn("private fixture reasoning", json.dumps(provider.decisions))
        self.assertNotIn("private", provider.metrics)

    async def test_truncation_is_rejected_and_stops_subsequent_network_calls(self):
        provider = GeminiEvaluation("fixture-key", {"models": []})
        opener = Mock()
        opener.open.return_value = response("MAX_TOKENS")
        with patch.object(provider, "_opener", return_value=opener):
            with self.assertRaisesRegex(ArgosError, "truncado"):
                await provider.decide("Hola", {})
            with self.assertRaisesRegex(ArgosError, "detenida"):
                await provider.decide("Otra vez", {})
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual(provider.decisions, [])

    async def test_quota_error_is_safe_and_never_retries(self):
        provider = GeminiEvaluation("fixture-key", {"models": []})
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError(
            ENDPOINT, 429, "secret server detail", {}, io.BytesIO(b"private error body"))
        with patch.object(provider, "_opener", return_value=opener):
            with self.assertRaises(ArgosError) as caught:
                await provider.decide("Hola", {})
        self.assertIn("Cuota gratuita", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))
        self.assertNotIn("private", str(caught.exception))
        self.assertEqual(opener.open.call_count, 1)

    async def test_unregistered_capability_is_rejected(self):
        provider = GeminiEvaluation("fixture-key", {"models": []})
        opener = Mock()
        opener.open.return_value = response(kind="capability", tool="invented.action", target_agent="computer")
        with patch.object(provider, "_opener", return_value=opener), self.assertRaises(ArgosError):
            await provider.decide("Hola", {})
        self.assertEqual(provider.decisions, [])

    def test_redirects_cannot_forward_the_key(self):
        provider = GeminiEvaluation("fixture-key", {"models": []})
        handler = next(h for h in provider._opener().handlers if hasattr(h, "redirect_request"))
        self.assertIsNone(handler.redirect_request(None, None, 302, "", {}, "https://example.invalid"))


if __name__ == "__main__":
    unittest.main()
