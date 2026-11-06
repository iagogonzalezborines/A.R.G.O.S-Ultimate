"""Materialize the archived pilot in a separate, non-destructive local installation.

Copies source only. Dependency builds, authentication and model downloads are
separate explicit steps; this command never launches the app or a model turn.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / 'experiments/hermes-pilot'
PIN = '0073fa98cfcf61c066a919df4b336924720f8463'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(destination, *, microphone=None, register=False):
    destination = Path(destination).expanduser().resolve()
    if destination == REPO or destination.is_relative_to(REPO):
        raise ValueError('Install outside the source repository')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest_path = destination / 'installed-source.json'
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    # Git supplies the source inventory; no runtime state, credentials, or caches
    # are inferred from the contents of a developer's working directory.
    tracked = subprocess.check_output(
        ['git', 'ls-files', '-z', '--', str(SOURCE)], cwd=REPO
    ).decode().split('\0')
    paths = [REPO / p for p in tracked if p]
    paths += [SOURCE / name for name in (
        'ui-workbench/runtime/machine.py',
        'project-intelligence/recovery/test_runtime_worker_codex_binding.py',
        'project-intelligence/recovery/recovery_trial.py',
        'project-intelligence/recovery/interrupt_live.py',
        'project-intelligence/recovery/upstream-tested-change-2026-11-06.diff',
        'project-intelligence/recovery/verified-2026-11-06.json',
        'reports/restoration-2026-11-06.md',
        'reports/restoration-2026-11-06.json',
        'voice-tests/2026-11-05/requirements-cpu-2026-11-06.txt',
    )]
    paths = sorted(set(p for p in paths if p.is_file()))
    conflicts = []
    for path in paths:
        relative = str(path.relative_to(SOURCE))
        target = destination / relative
        if target.exists() and digest(target) not in {digest(path), previous.get(relative)}:
            conflicts.append(relative)
    if conflicts:
        raise RuntimeError('Local changes preserved; review before updating: ' + ', '.join(conflicts))
    for path in paths:
        target = destination / path.relative_to(SOURCE)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not target.exists() or digest(target) != digest(path):
            shutil.copy2(path, target)
    for name in ('private', 'state/hermes', 'state/codex', 'home', 'cache',
                 'reports', 'workspaces/disposable', 'workspaces/files', 'bin',
                 'ui-workbench/reports', 'ui-workbench/private', 'ui-workbench/state'):
        (destination / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    config_path = destination / 'installation.json'
    if not config_path.exists():
        config = {'user_home': str(Path.home()), 'operational_root': str(REPO),
                  'hermes_revision': PIN, 'projects_enabled': False}
        if microphone:
            config['microphone'] = microphone
        config_path.write_text(json.dumps(config, indent=2) + '\n')
        config_path.chmod(0o600)
    templates = destination / 'config-templates'
    for name, target in [('hermes-config.yaml', 'state/hermes/config.yaml'),
                         ('codex-config.toml', 'state/codex/config.toml')]:
        file = destination / target
        if not file.exists():
            content = (templates / name).read_text().replace(
                '/home/tyrant/.local/share/argos-hermes-pilot', str(destination))
            file.write_text(content)
            file.chmod(0o600)
    for directory in ('plugins', 'desktop-plugins'):
        target = destination / 'state/hermes' / directory
        if not target.exists():
            shutil.copytree(templates / directory, target)
    (destination / 'state/hermes/skills').mkdir(exist_ok=True)
    codex = shutil.which('codex')
    if codex:
        for name in ('codex', 'codex-code-mode-host', 'rg'):
            source = Path(codex).parent / name
            target = destination / 'bin' / name
            if source.is_file() and not target.exists():
                shutil.copy2(source, target)
    manifest_path.write_text(json.dumps(
        {str(p.relative_to(SOURCE)): digest(p) for p in paths}, indent=2) + '\n')
    if register:
        register_launcher(destination)
    return {'installation': str(destination), 'source_files': len(paths),
            'launched': False, 'projects_enabled': False,
            'launcher_registered': register,
            'authentication_present': (destination / 'state/codex/auth.json').is_file()}


def register_launcher(destination):
    """A separate menu entry; leaves older ARGOS launchers and autostart intact."""
    executable = destination / 'bin/argos-hermes'
    executable.write_text(
        '#!/usr/bin/python3\nimport os\n'
        'os.execv("/usr/bin/python3", ["/usr/bin/python3", '
        + repr(str(destination / 'ui-workbench/launch.py')) + '])\n')
    executable.chmod(0o700)
    applications = Path.home() / '.local/share/applications'
    applications.mkdir(parents=True, exist_ok=True)
    # Escape desktop-entry Exec metacharacters, independently of shell syntax.
    command = str(executable).replace('%', '%%')
    for character in ('\\', '"', '`', '$'):
        command = command.replace(character, '\\' + character)
    entry = ('[Desktop Entry]\nType=Application\nName=ARGOS (Hermes)\n'
             'Comment=Workspace y conversación local de ARGOS\n'
             f'Exec="{command}"\n'
             f'Icon={destination / "ui-workbench/dist/assets/argos.svg"}\n'
             'Terminal=false\nCategories=Utility;\nStartupNotify=true\n')
    (applications / 'argos-hermes.desktop').write_text(entry)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path,
                        default=Path.home() / '.local/share/argos-hermes-pilot')
    parser.add_argument('--microphone', help='Exact PipeWire input name selected for this installation')
    parser.add_argument('--register', action='store_true', help='Install the separate ARGOS (Hermes) menu launcher')
    args = parser.parse_args()
    print(json.dumps(prepare(args.destination, microphone=args.microphone, register=args.register), indent=2))
