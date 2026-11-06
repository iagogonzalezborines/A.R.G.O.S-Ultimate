"""Portable pilot roots must retain file protection and reviewed writes."""
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

PILOT = Path(__file__).resolve().parents[1] / 'experiments/hermes-pilot'
package = types.ModuleType('argos_pilot_runtime_tests')
package.__path__ = [str(PILOT / 'ui-workbench/runtime')]
sys.modules[package.__name__] = package
from argos_pilot_runtime_tests.workspace_broker import Files
from argos_pilot_runtime_tests import workspace_broker


class PilotPortabilityTests(unittest.TestCase):
    def test_actual_installation_and_operational_roots_are_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            protected = home / 'Projects/ARGOS renamed'
            installed = home / 'pilot'
            protected.mkdir(parents=True)
            installed.mkdir()
            with patch.object(workspace_broker, 'USER_HOME', home), patch.object(
                    workspace_broker, 'PROTECTED_ROOTS', (protected, installed)), patch.object(
                    workspace_broker, 'ROOT', home / 'pilot/ui-workbench'):
                (home / 'pilot/workspaces').mkdir()
                files = Files({'Personal': home, 'ARGOS': installed / 'workspaces/files'})
                for target in (protected / 'source.py', installed / 'installation.json'):
                    with self.assertRaises(PermissionError):
                        files.propose('write', str(target), content='forbidden')
                    self.assertFalse(target.exists())
                scratch = files.propose('write', 'ARGOS/note.txt', content='workspace preserved')
                files.confirm(scratch['id'], True)
                self.assertEqual((installed / 'workspaces/files/note.txt').read_text(), 'workspace preserved')
                proposal = files.propose('write', '~/notes.txt', content='approved')
                self.assertFalse((home / 'notes.txt').exists())
                files.confirm(proposal['id'], True)
                self.assertEqual((home / 'notes.txt').read_text(), 'approved')
                with self.assertRaises((PermissionError, ValueError)):
                    files.confirm(proposal['id'], True)

    def test_portable_roots_still_reject_credential_and_symlink_access(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / 'workspaces').mkdir()
            (home / 'visible').mkdir()
            (home / 'visible/escape').symlink_to('/etc', target_is_directory=True)
            with patch.object(workspace_broker, 'ROOT', home / 'ui-workbench'):
                files = Files({'Personal': home / 'visible'})
                for name in ('../outside', '.codex/auth.json', 'credential.key', 'escape/passwd'):
                    with self.assertRaises((PermissionError, OSError)):
                        files.read('Personal/' + name)


if __name__ == '__main__':
    unittest.main()
