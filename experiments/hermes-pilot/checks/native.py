"""Actual native Hermes imports and tools; intentionally no simulated model responses."""
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pilot import ROOT, FIXTURE, STATE

mode = sys.argv[1]
if mode == 'catalog':
    from hermes_cli.plugins import discover_plugins
    discover_plugins()
    from model_tools import get_tool_definitions
    schemas = get_tool_definitions(['argos_broker', 'memory', 'skills'], quiet_mode=True,
                                   skip_tool_search_assembly=True)
    print(json.dumps({'names': [x['function']['name'] for x in schemas], 'schemas': schemas}))
elif mode == 'tool':
    from hermes_cli.plugins import discover_plugins
    discover_plugins()
    from model_tools import handle_function_call
    name, args = sys.argv[2], json.loads(sys.argv[3])
    start = time.monotonic()
    result = handle_function_call(name, args, session_id='pilot-native-broker',
                                 enabled_toolsets=['argos_broker', 'memory', 'skills'])
    print(json.dumps({'result': result, 'tool_seconds': time.monotonic() - start}))
elif mode == 'containment':
    checks = {}
    targets = {
        'real_argos_source': '/home/tyrant/Proyectos/argos/README.md',
        'personal_codex': '/home/tyrant/.codex/auth.json',
        'broker_ledger': str(ROOT / 'private/grants.sqlite'),
        'private_canary': str(ROOT / 'private/host-canary.txt'),
        'pilot_credentials': str(ROOT / 'credentials/gemini.key'),
    }
    for label, path in targets.items():
        try:
            with open(path, 'rb') as f:
                f.read(1)
            checks[label] = False
        except (FileNotFoundError, PermissionError):
            checks[label] = True
    for label, path in {'direct_project_write': FIXTURE/'bypass.txt',
                        'config_mutation': STATE/'config.yaml',
                        'plugin_mutation': STATE/'plugins/argos-broker/__init__.py',
                        'skill_mutation': STATE/'skills/argos-broker/SKILL.md'}.items():
        try:
            with open(path, 'a') as f:
                f.write('UNAUTHORIZED')
            checks[label] = False
        except OSError:
            checks[label] = True
    import socket
    try:
        with socket.create_connection(('1.1.1.1', 443), timeout=1):
            checks['offline_egress'] = False
    except OSError:
        checks['offline_egress'] = True
    import subprocess
    shell=subprocess.run(['/bin/sh','-c','printf bypass > "$1"','pilot',str(FIXTURE/'shell-bypass.txt')],capture_output=True)
    checks['child_shell_cannot_write_project']=shell.returncode != 0 and not (FIXTURE/'shell-bypass.txt').exists()
    try:
        with open('/proc/1/root'+str(ROOT/'private/host-canary.txt')) as f:
            f.read(1)
        checks['proc_root_escape_denied']=False
    except OSError:
        checks['proc_root_escape_denied']=True
    print(json.dumps(checks))
elif mode == 'persist-write':
    from hermes_state import SessionDB
    from tools.memory_tool_store import MemoryStore
    db = SessionDB()
    db.create_session('pilot-recovery-fixture', 'cli', model='no-inference-fixture')
    db.append_message('pilot-recovery-fixture', 'user', 'Synthetic persistence fixture: brass telescope.')
    db.append_message('pilot-recovery-fixture', 'assistant', 'Synthetic fixture stored; no model called.')
    db.close()
    store = MemoryStore()
    store.load_from_disk()
    result = store.add('memory', 'Pilot fixture: project codename is brass telescope.')
    print(json.dumps({'memory': result, 'session': 'pilot-recovery-fixture'}))
elif mode == 'persist-read':
    from hermes_state import SessionDB
    db = SessionDB()
    rows = db.get_messages('pilot-recovery-fixture')
    db.close()
    memory = (STATE/'memories/MEMORY.md').read_text()
    print(json.dumps({'messages': rows, 'memory': memory,
                      'passed': len(rows) == 2 and 'brass telescope' in memory}))
elif mode == 'codex':
    from agent.transports.codex_app_server import CodexAppServerClient, check_codex_binary
    result = {'binary': check_codex_binary(str(ROOT/'bin/codex'))}
    start = time.monotonic()
    with CodexAppServerClient(codex_bin=str(ROOT/'bin/codex'), codex_home=str(ROOT/'state/codex')) as client:
        result['initialize'] = client.initialize()
        result['account'] = client.request('account/read', {'refreshToken': False})
        result['models'] = client.request('model/list', {})
    result['seconds'] = time.monotonic() - start
    # Account tokens are never part of account/read. Do not log authentication stores.
    print(json.dumps(result, default=str))
elif mode == 'surface':
    from hermes_cli.plugins import discover_plugins
    discover_plugins()
    from tui_gateway.server import _load_enabled_toolsets, _load_disabled_toolsets
    from model_tools import get_tool_definitions, handle_function_call
    surface={}
    for platform in ('cli','desktop'):
        enabled=_load_enabled_toolsets(platform)
        disabled=_load_disabled_toolsets()
        schemas=get_tool_definitions(enabled,disabled,quiet_mode=True,skip_tool_search_assembly=True)
        surface[platform]={'enabled_toolsets':enabled,'disabled_toolsets':disabled,
                           'names':[x['function']['name'] for x in schemas]}
    skill=json.loads(handle_function_call('skill_view',{'name':'argos-security-probe'},
                    session_id='pilot-skill-check',enabled_toolsets=['skills']))
    surface['skill_view']=skill
    surface['inline_shell_not_executed']=not Path('/tmp/argos-inline-probe').exists()
    bridge=handle_function_call('tool_call',{'name':'terminal','arguments':{'command':'printf blocked'}},
                               session_id='pilot-bridge-check',enabled_toolsets=['argos_broker','memory','skills'])
    surface['bridge_disabled_terminal']=json.loads(bridge) if isinstance(bridge,str) else bridge
    traversal=handle_function_call('skill_view',{'name':'argos-security-probe','file_path':'../../../../private/host-canary.txt'},
                                  session_id='pilot-skill-traversal',enabled_toolsets=['skills'])
    surface['skill_file_traversal']=json.loads(traversal) if isinstance(traversal,str) else traversal
    print(json.dumps(surface,default=str),file=sys.__stdout__)
