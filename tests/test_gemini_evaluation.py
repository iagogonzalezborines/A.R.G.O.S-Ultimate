import io
import json
from pathlib import Path
import sys
import unittest
import urllib.error
from unittest.mock import Mock, patch

from argos.models import ArgosError

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from validate_gemini_live import ENDPOINT, GeminiEvaluation
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
