"""Controller-side reproducible checks against the native pilot."""
import json
import os
from pathlib import Path
import queue
import statistics
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pilot import ROOT, SOURCE, STATE, FIXTURE, PYTHON, Broker, sandbox

REPORT = {'checks': {}, 'metrics': {}}


def run_native(mode, *args):
    start = time.monotonic()
    proc = subprocess.run(sandbox([PYTHON, ROOT/'checks/native.py', mode, *args]),
                          text=True, capture_output=True, timeout=40)
    if proc.returncode:
        raise RuntimeError(proc.stderr[-3000:] or proc.stdout[-3000:])
    lines = proc.stdout.strip().splitlines()
    return json.loads(lines[-1]), time.monotonic() - start


def call(name, args):
    data, elapsed = run_native('tool', name, json.dumps(args))
    result = data['result']
    if isinstance(result, str):
        result = json.loads(result)
    REPORT['metrics'].setdefault('native_tool_seconds', []).append(data['tool_seconds'])
    return result


class RPC:
    def __init__(self):
        self.frames = queue.Queue()
        self.events = []
        self.nextid = 0
        self.error = (ROOT/'reports/gateway.stderr').open('a')
        start = time.monotonic()
        self.proc = subprocess.Popen(sandbox([PYTHON, '-m', 'tui_gateway.entry']),
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.error, text=True, bufsize=1)
        def reader():
            for line in self.proc.stdout:
                try:
                    self.frames.put(json.loads(line))
                except ValueError:
                    self.events.append({'non_rpc_stdout': line[:200]})
        threading.Thread(target=reader, daemon=True).start()
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            frame = self.frames.get(timeout=max(.1, deadline-time.monotonic()))
            self.events.append(frame)
            if frame.get('params', {}).get('type') == 'gateway.ready':
                self.startup = time.monotonic() - start
                break
        else:
            raise TimeoutError('Native gateway did not become ready')

    def request(self, method, params):
        self.nextid += 1
        ident = self.nextid
        start = time.monotonic()
        self.proc.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params})+'\n')
        self.proc.stdin.flush()
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            frame = self.frames.get(timeout=max(.1, deadline-time.monotonic()))
            self.events.append(frame)
            if frame.get('id') == ident:
                REPORT['metrics'].setdefault('rpc_seconds', {}).setdefault(method, []).append(time.monotonic()-start)
                return frame
            if frame.get('id') is not None and frame.get('method'):
                # Never silently approve a server request.
                self.proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':frame['id'],
                                                 'error':{'code':-32000,'message':'Pilot controller denies unattended requests'}})+'\n')
                self.proc.stdin.flush()
        raise TimeoutError(method)

    def close(self):
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.error.close()


def process_sample(pid):
    """Sum RSS for this process tree; RSS includes shared pages, so it is an upper bound."""
    info = {}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            raw = (path/'stat').read_text()
            fields = raw[raw.rfind(')')+2:].split()
            info[int(path.name)] = (int(fields[1]), int(fields[11])+int(fields[12]), int(fields[21])*os.sysconf('SC_PAGE_SIZE'))
        except (OSError, ValueError, IndexError):
            continue
    owned = {pid}
    while True:
        children = {p for p, (parent, _, _) in info.items() if parent in owned}
        if children <= owned:
            break
        owned |= children
    return {'rss_mib': sum(info[p][2] for p in owned if p in info)/2**20,
            'cpu_seconds': sum(info[p][1] for p in owned if p in info)/os.sysconf('SC_CLK_TCK'),
            'processes': len(owned)}


def broker_tests():
    broker = Broker()
    threading.Thread(target=broker.serve, daemon=True).start()
    try:
        Broker()
        REPORT['checks']['second_broker_owner_rejected'] = False
    except BlockingIOError:
        REPORT['checks']['second_broker_owner_rejected'] = True
    import socket
    from pilot import SOCKET
    with socket.socket(socket.AF_UNIX) as abandoned:
        abandoned.connect(str(SOCKET))
    REPORT['checks']['disconnected_client_no_effect'] = broker_request('health',{}).get('ready') is True
    catalog, _ = run_native('catalog')
    (ROOT/'reports/native-catalog.json').write_text(json.dumps(catalog, indent=2))
    allowed = {'argos_read','argos_propose','argos_apply','memory','skills_list','skill_view','skill_manage'}
    REPORT['checks']['catalog_exact_allowlist'] = set(catalog['names']) <= allowed and {'argos_read','memory'} <= set(catalog['names'])
    read = call('argos_read', {'path':'README.md'})
    REPORT['checks']['native_plugin_read'] = 'Disposable ARGOS' in read.get('content','')
    proposal = call('argos_propose', {'path':'approved.txt','content':'Authorized isolated change.\n'})
    args = {k:proposal[k] for k in ('proposal_id','sha256')}
    REPORT['checks']['unapproved_apply_denied'] = 'error' in call('argos_apply',args)
    REPORT['checks']['agent_cannot_approve'] = 'error' in broker_request('approve',args)
    REPORT['checks']['mutation_denied'] = 'error' in call('argos_apply',{**args,'content':'tampered'})
    REPORT['checks']['digest_mismatch_denied'] = 'error' in call('argos_apply',{**args,'sha256':'0'*64})
    broker.grant(**{'ident':args['proposal_id'],'digest':args['sha256']})
    REPORT['checks']['exact_external_grant_applied'] = call('argos_apply',args).get('applied') is True
    REPORT['checks']['effect_verified'] = (FIXTURE/'approved.txt').read_text() == 'Authorized isolated change.\n'
    REPORT['checks']['replay_denied'] = 'error' in call('argos_apply',args)
    REPORT['checks']['traversal_denied'] = 'error' in call('argos_read',{'path':'../../private/host-canary.txt'})
    REPORT['checks']['absolute_path_denied'] = 'error' in call('argos_read',{'path':str(ROOT/'private/host-canary.txt')})
    link = FIXTURE/'escape-link'
    if not link.exists():
        link.symlink_to(ROOT/'private/host-canary.txt')
    REPORT['checks']['symlink_denied'] = 'error' in call('argos_read',{'path':'escape-link'})
    (FIXTURE/'changed.txt').unlink(missing_ok=True)
    changed = call('argos_propose',{'path':'changed.txt','content':'proposal'})
    (FIXTURE/'changed.txt').write_text('changed by controller after proposal')
    broker.grant(changed['proposal_id'],changed['sha256'])
    REPORT['checks']['changed_target_denied'] = 'error' in call('argos_apply',{k:changed[k] for k in ('proposal_id','sha256')})
    containment, _ = run_native('containment')
    REPORT['checks'].update(containment)
    readback, _ = run_native('persist-read')
    REPORT['checks']['native_memory_and_sqlite_process_recovery'] = readback['passed']
    (ROOT/'reports/persistence.json').write_text(json.dumps(readback,indent=2))
    surface, _ = run_native('surface')
    (ROOT/'reports/effective-surface.json').write_text(json.dumps(surface,indent=2))
    REPORT['checks']['desktop_cli_same_surface'] = surface['cli']['names'] == surface['desktop']['names']
    REPORT['checks']['desktop_exact_allowlist'] = set(surface['desktop']['names']) == allowed
    REPORT['checks']['native_inline_shell_suppressed'] = surface['inline_shell_not_executed']
    REPORT['checks']['native_tool_search_cannot_enable_shell'] = 'not available' in surface['bridge_disabled_terminal'].get('error','')
    REPORT['checks']['native_skill_file_traversal_denied'] = surface['skill_file_traversal'].get('success') is False


def broker_request(op,args):
    import socket
    from pilot import SOCKET
    with socket.socket(socket.AF_UNIX) as conn:
        conn.connect(str(SOCKET))
        conn.sendall(json.dumps({'op':op,'args':args}).encode()+b'\n')
        return json.loads(conn.recv(131072))


def gateway_tests():
    rpc = RPC()
    try:
        REPORT['metrics']['gateway_startup_seconds'] = rpc.startup
        caps = rpc.request('client.capabilities',{'server_requests':True})
        first = rpc.request('session.create',{'cwd':str(FIXTURE),'idempotency_key':'pilot-create-1'})
        again = rpc.request('session.create',{'cwd':str(FIXTURE),'idempotency_key':'pilot-create-1'})
        REPORT['checks']['native_gateway_create_idempotent'] = first.get('result',{}).get('session_id') is not None and first.get('result',{}).get('session_id') == again.get('result',{}).get('session_id')
        resumed = rpc.request('session.resume',{'session_id':'pilot-recovery-fixture'})
        REPORT['checks']['gateway_resumes_native_db'] = 'error' not in resumed
        sid = resumed.get('result',{}).get('session_id')
        if sid:
            history = rpc.request('session.history',{'session_id':sid})
            REPORT['checks']['gateway_recovers_synthetic_transcript'] = 'brass telescope' in json.dumps(history)
        before = process_sample(rpc.proc.pid)
        time.sleep(5)
        after = process_sample(rpc.proc.pid)
        REPORT['metrics']['gateway_idle'] = {**after, 'interval_seconds':5,
            'cpu_one_core_percent':max(0,after['cpu_seconds']-before['cpu_seconds'])/5*100}
        (ROOT/'reports/gateway-rpc.json').write_text(json.dumps(rpc.events,indent=2))
    finally:
        rpc.close()


if __name__ == '__main__':
    try:
        broker_tests()
        gateway_tests()
    except Exception as exc:
        REPORT['error'] = str(exc)
        raise
    finally:
        REPORT['all_recorded_checks_passed'] = all(REPORT['checks'].values()) and 'error' not in REPORT
        (ROOT/'reports/validation.json').write_text(json.dumps(REPORT,indent=2))
        print(json.dumps(REPORT,indent=2))
