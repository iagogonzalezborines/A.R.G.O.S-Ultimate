"""Restoring source must not overwrite local edits or private installation state."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'prepare_hermes_pilot', Path(__file__).resolve().parents[1] / 'scripts/prepare_hermes_pilot.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class PilotInstallerTests(unittest.TestCase):
    def test_legacy_adoption_requires_recorded_source_hash_and_preserves_private_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);repo=root/'repo';source=repo/'experiments/hermes-pilot'
            source.mkdir(parents=True);destination=root/'installed';destination.mkdir()
            runtime=source/'runtime.py';runtime.write_text('new version')
            old=destination/'runtime.py';old.write_text('known old version')
            manifest={'files':[{'path':'runtime.py','source_sha256':installer.digest(old),
                                'export_sha256':installer.digest(old)}]}
            (source/'snapshot-manifest.json').write_text(json.dumps(manifest))
            templates=source/'config-templates';templates.mkdir()
            for name in ['plugins','desktop-plugins']:
                (templates/name).mkdir();(templates/name/'entry.txt').write_text('plugin')
            for name in ['hermes-config.yaml','codex-config.toml']:(templates/name).write_text('template')
            private=destination/'state/codex';private.mkdir(parents=True)
            (private/'auth.json').write_text('synthetic credential')
            (private/'config.toml').write_text('local configuration')
            inventory='\0'.join(str(p.relative_to(repo)) for p in source.rglob('*') if p.is_file()).encode()
            with patch.object(installer,'REPO',repo),patch.object(installer,'SOURCE',source),patch.object(
                    installer.subprocess,'check_output',return_value=inventory),patch.object(installer.shutil,'which',return_value=None):
                with self.assertRaisesRegex(RuntimeError,'Local changes preserved'):installer.prepare(destination)
                old.write_text('unknown local edit')
                with self.assertRaisesRegex(RuntimeError,'Local changes preserved'):installer.prepare(destination,adopt_legacy=True)
                self.assertFalse((destination/'installed-source.json').exists())
                old.write_text('known old version');installer.prepare(destination,adopt_legacy=True)
                self.assertEqual(old.read_text(),'new version')
                self.assertEqual((private/'auth.json').read_text(),'synthetic credential')
                self.assertEqual((private/'config.toml').read_text(),'local configuration')

    def test_updates_managed_source_preserving_configuration_and_local_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, destination = root / 'repo', root / 'installed'
            source = repo / 'experiments/hermes-pilot'
            templates = source / 'config-templates'
            templates.mkdir(parents=True)
            for name in ('plugins', 'desktop-plugins'):
                (templates / name).mkdir()
                (templates / name / 'entry.txt').write_text('plugin')
            for name in ('hermes-config.yaml', 'codex-config.toml'):
                (templates / name).write_text('initial configuration')
            runtime = source / 'runtime.py'
            runtime.write_text('version one')
            inventory = '\0'.join(str(p.relative_to(repo)) for p in source.rglob('*') if p.is_file()).encode()
            with patch.object(installer, 'REPO', repo), patch.object(installer, 'SOURCE', source), patch.object(
                    installer.subprocess, 'check_output', return_value=inventory), patch.object(
                    installer.shutil, 'which', return_value=None):
                result = installer.prepare(destination)
                self.assertFalse(result['launched'])
                config = destination / 'state/codex/config.toml'
                auth = destination / 'state/codex/auth.json'
                config.write_text('deliberate local configuration')
                auth.write_text('synthetic fixture')
                local = destination / 'installation.json'
                settings = json.loads(local.read_text())
                settings['microphone'] = 'chosen-input'
                local.write_text(json.dumps(settings))
                runtime.write_text('version two')
                installer.prepare(destination)
                self.assertEqual((destination / 'runtime.py').read_text(), 'version two')
                self.assertEqual(config.read_text(), 'deliberate local configuration')
                self.assertEqual(auth.read_text(), 'synthetic fixture')
                self.assertEqual(json.loads(local.read_text())['microphone'], 'chosen-input')
                (destination / 'runtime.py').write_text('local runtime change')
                with self.assertRaisesRegex(RuntimeError, 'Local changes preserved'):
                    installer.prepare(destination)
                self.assertEqual((destination / 'runtime.py').read_text(), 'local runtime change')
                self.assertEqual(auth.read_text(), 'synthetic fixture')

    def test_rejects_installation_inside_the_development_checkout(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(installer, 'REPO', Path(directory)):
            with self.assertRaisesRegex(ValueError, 'outside the source repository'):
                installer.prepare(Path(directory) / 'nested')
            self.assertFalse((Path(directory) / 'nested').exists())
