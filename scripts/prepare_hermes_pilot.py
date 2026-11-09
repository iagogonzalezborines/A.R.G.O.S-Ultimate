"""Materialize the archived pilot in a separate, non-destructive local installation.

Copies source only. Dependency builds, authentication and model downloads are
separate explicit steps; this command never launches the app or a model turn.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / 'experiments/hermes-pilot'
PIN = '0073fa98cfcf61c066a919df4b336924720f8463'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(destination, *, microphone=None, register=False, projects=None, project_map=None, adaptive=None, workspace_control=None, adopt_legacy=False):
    destination = Path(destination).expanduser().resolve()
    if destination == REPO or destination.is_relative_to(REPO):
        raise ValueError('Install outside the source repository')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest_path = destination / 'installed-source.json'
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    legacy = {}
    if adopt_legacy:
        archive = json.loads((SOURCE / 'snapshot-manifest.json').read_text())
        legacy = {row['path']: {row['source_sha256'], row['export_sha256']}
                  for row in archive['files']}
        # The first export renamed the installed README to LOCAL-NOTES.md.
        if 'LOCAL-NOTES.md' in legacy:
            legacy.setdefault('README.md', set()).update(legacy['LOCAL-NOTES.md'])
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
        accepted = {digest(path), previous.get(relative)}
        if adopt_legacy and not previous:
            accepted.update(legacy.get(relative, set()))
        if target.exists() and digest(target) not in accepted:
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
                  'hermes_revision': PIN, 'projects_enabled': False,
                  'pilot_root': str(destination), 'project_state': str(destination / 'state/projects'),
                  'project_roots': [str(Path.home() / 'Proyectos')]}
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
    if projects is not None:
        configure_projects(destination, projects)
    if adaptive is not None:
        configure_projects(destination, adaptive, capability='adaptive')
    if project_map is not None:
        settings=json.loads(config_path.read_text())
        if project_map and not settings.get('projects_enabled'):raise ValueError('Enable Projects before Project Map')
        settings['project_map_enabled']=bool(project_map)
        config_path.write_text(json.dumps(settings,indent=2)+'\n')
    if workspace_control is not None:
        configure_workspace_control(destination, workspace_control)
    if register:
        register_launcher(destination)
    return {'installation': str(destination), 'source_files': len(paths),
            'launched': False, 'projects_enabled': json.loads(config_path.read_text()).get('projects_enabled', False),
            'launcher_registered': register,
            'authentication_present': (destination / 'state/codex/auth.json').is_file()}


def configure_projects(destination, enabled, *, capability="projects"):
    """Explicit feature activation; native execution still requires a reviewed project scope."""
    if enabled:
        sys.path.insert(0, str(destination))
        from projects.worker import verify_pin
        verify_pin(destination)
    config_path = destination / 'installation.json'
    config = json.loads(config_path.read_text())
    if capability not in {'projects','adaptive'}:raise ValueError('Unknown integration')
    if capability=='adaptive' and enabled and not config.get('projects_enabled'):raise ValueError('Enable Projects first')
    config.setdefault('pilot_root', str(destination))
    config.setdefault('project_state', str(destination / 'state/projects'))
    config.setdefault('project_roots', [str(Path(config['user_home']) / 'Proyectos')])
    codex = destination / 'state/codex/config.toml'
    source = codex.read_text()
    parsed = tomllib.loads(source)
    names = parsed['mcp_servers']['argos-workspace']['enabled_tools']
    names = list(dict.fromkeys([*names, capability])) if enabled else [n for n in names if n != capability]
    pattern = r'(?ms)(^\[mcp_servers\.argos-workspace\]\s*\n)(.*?)(?=^\[|\Z)'
    match = re.search(pattern, source)
    if not match or not re.search(r'^enabled_tools\s*=\s*\[[^\n]*\]\s*$', match[2], re.M):
        raise ValueError('Review the existing MCP tools configuration before activation')
    body = re.sub(r'^enabled_tools[^\n]*', 'enabled_tools='+json.dumps(names), match[2], flags=re.M)
    source = source[:match.start(2)] + body + source[match.end(2):]
    section = '[mcp_servers.argos-workspace.tools.'+capability+']'
    if enabled and section not in source:
        source += '\n'+section+'\napproval_mode="approve"\n'
    if enabled and tomllib.loads(source)['mcp_servers']['argos-workspace']['tools'][capability].get('approval_mode') != 'approve':
        raise ValueError('Review the projects tool approval mode before activation')
    config[capability+'_enabled'] = bool(enabled)
    if capability=='adaptive':config.setdefault('adaptive',{'local':{},'min_available_bytes':2*1024**3})
    # Write transport config first: an interrupted enable remains denied by the Broker flag.
    codex.write_text(source)
    config_path.write_text(json.dumps(config, indent=2)+'\n')


def configure_workspace_control(destination, enabled):
    """Deliberate transport admission; Broker still owns every scope/approval."""
    codex=Path(destination)/'state/codex/config.toml'
    source=codex.read_text();parsed=tomllib.loads(source)
    server=parsed.get('mcp_servers',{}).get('argos-workspace',{})
    if server.get('command')!=str(Path(destination)/'env/bin/python') or server.get('args')!=[str(Path(destination)/'checks/workspace_mcp.py')] or 'workspace' not in server.get('enabled_tools',[]):
        raise ValueError('Workspace transport differs from the reviewed local Broker; preserved')
    section='[mcp_servers.argos-workspace.tools.workspace]'
    current=server.get('tools',{}).get('workspace',{}).get('approval_mode')
    if current is not None and current!='approve':raise ValueError('Custom workspace approval policy preserved; review it before activation')
    if enabled and section not in source:source+='\n'+section+'\napproval_mode="approve"\n'
    if not enabled:source=re.sub(r'(?ms)^\[mcp_servers\.argos-workspace\.tools\.workspace\]\s*\n.*?(?=^\[|\Z)','',source)
    tomllib.loads(source);codex.write_text(source)


def register_launcher(destination):
    """A separate menu entry; leaves older ARGOS launchers and autostart intact."""
    executable = destination / 'bin/argos-hermes'
    executable.write_text(
        '#!/usr/bin/python3\nimport os,sys\n'
        'os.execv("/usr/bin/python3", ["/usr/bin/python3", '
        + repr(str(destination / 'ui-workbench/launch.py')) + '] + sys.argv[1:])\n')
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
    parser.add_argument('--adopt-legacy', action='store_true', help='Adopt only source hashes recorded in the original snapshot; unknown local edits still block the update')
    parser.add_argument('--register', action='store_true', help='Install the separate ARGOS (Hermes) menu launcher')
    parser.add_argument('--projects', choices=['on','off'], help='Explicitly enable or disable the installed native project integration; never starts a worker')
    parser.add_argument('--project-map', choices=['on','off'], help='Enable the validated native Project Map panel; no worker starts')
    parser.add_argument('--adaptive', choices=['on','off'], help='Enable bounded native capabilities; local inference stays unavailable without its reviewed private configuration')
    parser.add_argument('--workspace-control', choices=['on','off'], help='Deliberately admit the reviewed workspace Broker tool in Codex; does not authorize files or Engineering')
    args = parser.parse_args()
    print(json.dumps(prepare(args.destination, microphone=args.microphone, register=args.register, projects=None if args.projects is None else args.projects=='on', project_map=None if args.project_map is None else args.project_map=='on', adaptive=None if args.adaptive is None else args.adaptive=='on', workspace_control=None if args.workspace_control is None else args.workspace_control=='on', adopt_legacy=args.adopt_legacy), indent=2))
