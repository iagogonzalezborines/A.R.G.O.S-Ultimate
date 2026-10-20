import json
import struct
import tempfile
import unittest
from pathlib import Path

from argos.agents import AGENTS, contract
from argos.capabilities import stl_data
from argos.console import frame
from argos.models import ArgosError
from argos.policy import Operation, Policy
from argos.providers import OllamaInterpreter, validate_decision
from argos.router import Router
from argos.store import Store
from argos.voice import rms16


class BoundaryTests(unittest.TestCase):
    def test_registered_contracts_load(self):
        for agent in AGENTS:
            content = contract(agent)
            self.assertIn("ARGOS interaction contract", content)
            self.assertIn("specialists", content)

    def test_negation_quotes_and_hypotheticals_do_not_execute(self):
        router = Router()
        for sentence in ("no actives modo gaming", 'dijo "activa modo gaming"',
                         "si digo activa modo gaming, qué pasa", "no quiero usar engineering",
                         "don't fix anything", "explica cómo imprimir en 3d"):
            with self.subTest(sentence=sentence):
                self.assertEqual(router.resolve(sentence).kind, "interpret")

    def test_unregistered_provider_capability_rejected(self):
        data = {"kind": "capability", "speech": "", "agent": "computer",
                "capability": "shell.exec", "arguments": {"command": "echo unsafe"}}
        with self.assertRaises(ArgosError):
            validate_decision(data)

    def test_unknown_argument_rejected(self):
        data = {"kind": "capability", "speech": "", "agent": "computer",
                "capability": "system.info", "arguments": {"command": "unsafe"}}
        with self.assertRaises(ArgosError):
            validate_decision(data)

    def test_provider_cannot_request_other_role(self):
        data = {"kind": "capability", "speech": "", "agent": "computer",
                "capability": "system.info", "arguments": {}}
        with self.assertRaises(ArgosError):
            validate_decision(data, "engineering")

    def test_remote_provider_rejected(self):
        for endpoint in ("https://example.com", "http://example.com", "http://user:secret@localhost"):
            with self.assertRaises(ArgosError):
                OllamaInterpreter("test", endpoint)

    def test_binary_stl_with_solid_header(self):
        data = b"solid binary".ljust(80, b" ") + struct.pack("<I", 1)
        data += struct.pack("<12fH", 0, 0, 1, 0, 0, 0, 3, 0, 0, 0, 4, 0, 0)
        result = stl_data(data)
        self.assertEqual(result["dimensions"], [3, 4, 0])
        self.assertEqual(result["encoding"], "binary")

    def test_non_finite_geometry_rejected(self):
        data = b"x" * 80 + struct.pack("<I", 1)
        data += struct.pack("<12fH", 0, 0, 1, float("nan"), 0, 0, 3, 0, 0, 0, 4, 0, 0)
        with self.assertRaises(ArgosError):
            stl_data(data)

    def test_policy_requires_exact_single_use_fingerprint(self):
        p = Policy()
        operation = Operation("print.start", {"sha256": "artifact-1", "printer": "P"}, "project", "physical")
        changed = Operation("print.start", {"sha256": "artifact-2", "printer": "P"}, "project", "physical")
        with self.assertRaises(ArgosError):
            p.authorize(operation)
        with self.assertRaises(ArgosError):
            p.approve(changed, operation.fingerprint)
        p.approve(operation, operation.fingerprint)
        p.authorize(operation)
        with self.assertRaises(ArgosError):
            p.authorize(operation)

    def test_audio_meter_uses_pcm(self):
        self.assertEqual(rms16(b"\0\0" * 100), 0)
        self.assertAlmostEqual(rms16(struct.pack("<h", 16384) * 100), 0.5)
        self.assertNotEqual(frame(40, 15, 0, 1), frame(40, 15, 0.7, 1))

    def test_sphere_contains_no_logs_or_transcript(self):
        content = frame(40, 15, 0.7, 1)
        self.assertEqual(len(content.splitlines()), 15)
        self.assertTrue(set(content) <= set(" .:-=+*#%@\n"))

    def test_database_reopen_preserves_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "source"
            project.mkdir()
            store = Store(root / "state")
            saved = store.add_project("Alpha", project)
            task = store.create_task("session-a", saved["id"], "engineering", "inspect",
                                     status="WAITING_INPUT", question="Which file?")
            store.close()
            reopened = Store(root / "state")
            try:
                self.assertEqual(reopened.project("alpha"), saved)
                self.assertEqual(reopened.task(task["id"])["question"], "Which file?")
                self.assertEqual((root / "state" / "argos.sqlite").stat().st_mode & 0o777, 0o600)
            finally:
                reopened.close()
