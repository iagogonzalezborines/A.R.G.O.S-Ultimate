import asyncio
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from argos.core import Core
from argos.language import choose_language, language_command
from argos.models import Decision
from argos.speech import Speech, Capture
from argos.store import Store
from argos.voice_worker import transcribe
from argos.router import Router


class LanguageSelectionTests(unittest.TestCase):
    def test_invocation_prefixes_keep_app_commands_local_and_preserve_names(self):
        for text in ("Argos, abre Firefox", "Argos por favor abre Firefox", "Please open Firefox"):
            with patch("argos.linux_tools.find_app", return_value={"id": "firefox.desktop"}) as find:
                result = Router().resolve(text)
            self.assertEqual(result.capability, "apps.open")
            find.assert_called_once_with("Firefox")
        with patch("argos.linux_tools.find_app") as find:
            for text in ('Argos, no abras Firefox', 'Argos, si digo "abre Firefox"', 'Argos, "abre Firefox"'):
                self.assertEqual(Router().resolve(text).kind, "interpret")
            find.assert_not_called()

    def test_uncertain_clip_rechecks_other_language_locally(self):
        calls = []
        def decode(path, language, **kwargs):
            calls.append(language)
            return ([SimpleNamespace(text="Camdia L." if language is None else "Cambia al inglés.",
                                     no_speech_prob=.05, avg_logprob=-.5)],
                    SimpleNamespace(language="en" if language is None else "es", language_probability=.77))
        result = transcribe(SimpleNamespace(transcribe=decode), "unused.wav")
        self.assertEqual(calls, [None, "es"])
        self.assertEqual(result["text"], "Cambia al inglés.")
        self.assertEqual(choose_language(result["text"]), "en")

    def test_confident_clip_does_not_repeat_recognition(self):
        calls = []
        def decode(path, language, **kwargs):
            calls.append(language)
            return ([SimpleNamespace(text="Hello, what can you do?", no_speech_prob=.01, avg_logprob=-.2)],
                    SimpleNamespace(language="en", language_probability=.97))
        result = transcribe(SimpleNamespace(transcribe=decode), "unused.wav")
        self.assertEqual(calls, [None])
        self.assertEqual(result["language"], "en")

    def test_explicit_commands_in_both_languages(self):
        for text in ("habla en inglés", "cambia al inglés", "Argos, puedes hablar en inglés",
                     "please switch to English", "can you speak English", "responde en ingles por favor"):
            self.assertEqual(language_command(text), "en", text)
        for text in ("cambia a español", "habla español", "speak Spanish", "please answer in Spanish"):
            self.assertEqual(language_command(text), "es", text)

    def test_quoted_negated_and_hypothetical_commands_are_not_actions(self):
        for text in ('dijo "habla en inglés"', "no cambies al inglés", "si digo habla inglés qué pasa",
                     "don't switch to English", "if I say speak Spanish"):
            self.assertIsNone(language_command(text), text)

    def test_short_clear_greetings_override_bad_audio_detection(self):
        self.assertEqual(choose_language("hola", "en", "en", .99), "es")
        self.assertEqual(choose_language("hello", "es", "es", .99), "en")
        self.assertEqual(choose_language("gracias", "en", "en", .99), "es")
        self.assertEqual(choose_language("thanks", "es", "es", .99), "en")

    def test_ambiguous_words_preserve_context(self):
        for text in ("okay", "ARGOS", "Python", "42"):
            self.assertEqual(choose_language(text, "es", "en", .99), "es")
            self.assertEqual(choose_language(text, "en", "es", .99), "en")

    def test_clear_text_and_confident_audio(self):
        self.assertEqual(choose_language("what can you do", "es"), "en")
        self.assertEqual(choose_language("qué puedes hacer", "en"), "es")
        self.assertEqual(choose_language("statistics versus calculus", "es", "en", .95), "en")
        self.assertEqual(choose_language("statistics versus calculus", "es", "en", .3), "es")


class LanguageCoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state")
        self.core = Core(self.store)
        await self.core.start()

    async def asyncTearDown(self):
        await self.core.close()
        self.store.close()
        self.temp.cleanup()

    async def say(self, text, **kwargs):
        return await self.core.request({"method": "say", "text": text, "request_id": uuid.uuid4().hex, **kwargs})

    async def test_switch_without_provider_then_follow_next_input(self):
        result = await self.say("cambia al inglés")
        self.assertEqual((result["speech"], result["language"]), ("I'll speak English.", "en"))
        self.assertIsNone(result["task_id"])
        result = await self.say("qué puedes hacer")
        self.assertEqual(result["language"], "es")
        self.assertTrue(result["speech"].startswith("Puedo"))
        result = await self.say("what can you do")
        self.assertEqual(result["language"], "en")
        self.assertTrue(result["speech"].startswith("I can"))
        result = await self.say("speak Spanish")
        self.assertEqual((result["speech"], result["language"]), ("Hablaré en español.", "es"))

    async def test_audio_guess_cannot_turn_hola_into_english_voice(self):
        result = await self.say("hola", detected_language="en", language_probability=.99)
        self.assertEqual((result["speech"], result["language"]), ("Hola.", "es"))

    async def test_concurrent_provider_requests_keep_their_context(self):
        observed = []
        class Provider:
            name = "test"
            async def decide(provider, text, context):
                await asyncio.sleep(.01)
                observed.append((text, context["response_language"]))
                return Decision("answer", speech="An answer." if context["response_language"] == "en" else "Una respuesta.")
        self.core.interpreter = Provider()
        english, spanish = await asyncio.gather(
            self.say("tell me something about rain", session="one"),
            self.say("dime algo sobre la lluvia", session="two"))
        self.assertEqual(english["language"], "en")
        self.assertEqual(spanish["language"], "es")
        self.assertIn(("tell me something about rain", "en"), observed)
        self.assertIn(("dime algo sobre la lluvia", "es"), observed)

    async def test_local_task_keeps_language_after_conversation_switch(self):
        result = await self.say("system info")
        task_id = result["task_id"]
        await self.say("hola")
        await asyncio.wait_for(self.core.queue.join(), 3)
        task = self.store.task(task_id)
        self.assertEqual(self.store.setting("task.language:" + task_id), "en")
        self.assertIn("logical CPUs", task["result"]["speech"])

    async def test_input_configuration_does_not_disable_auto_language(self):
        directory = Path(self.temp.name)
        self.core.speech = Speech(None, None, directory)
        self.core.capture = Capture(self.core, None, directory)
        response = await self.core.request({"method": "voice.configure", "request_id": uuid.uuid4().hex})
        self.assertEqual(response["data"]["language_mode"], "auto")
