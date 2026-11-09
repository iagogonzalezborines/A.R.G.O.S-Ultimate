"""Scoped host desktop I/O. General reasons; the Broker owns admission and evidence.

One transient action slot, no task scheduler and no replay across restarts. Only
controller-launched profiles and explicitly authorized accessible windows are exposed.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import signal
import subprocess
import threading
import time

from .machine import CONFIG_PATH, PILOT

BUTTONS = set('0123456789') | {'+', '-', '*', '/', '=', '.', '(', ')', 'AC', 'C', '<-', '+/-', '%', 'sqrt'}
TERMINAL = {'completed', 'failed', 'cancelled'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def process_identity(pid):
    p = Path('/proc') / str(pid)
    return (p.stat().st_uid, str((p / 'exe').resolve(strict=True)), (p / 'stat').read_text().rsplit(')', 1)[1].split()[19])


def run_json(argv, env, *, cancel=None, timeout=3, limit=131072, deadline=None, input_data=None):
    """No shell, bounded output, timeout and cancellation reap the child group."""
    p = subprocess.Popen(argv, env=env, stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    data = bytearray(); deadline = min(time.monotonic() + timeout, deadline if deadline is not None else float("inf"))
    try:
        if input_data is not None:
            if len(input_data) > 8192: raise ValueError('Input exceeds budget')
            p.stdin.write(input_data); p.stdin.close()
        with selectors.DefaultSelector() as sel:
            sel.register(p.stdout, selectors.EVENT_READ)
            while sel.get_map():
                if cancel is not None and cancel.is_set():
                    raise InterruptedError('Desktop operation cancelled; inspect before continuing')
                if time.monotonic() > deadline:
                    raise TimeoutError('Desktop deadline exceeded; inspect before continuing')
                for key, _ in sel.select(.03):
                    chunk = os.read(key.fd, 8192)
                    if not chunk:
                        sel.unregister(key.fileobj); continue
                    data.extend(chunk)
                    if len(data) > limit:
                        raise ValueError('Desktop output limit exceeded')
        p.wait(timeout=max(.01, deadline-time.monotonic()))
        result = json.loads(data)
        if not isinstance(result, dict) or not result.get('ok'):
            code = result.get('error', {}).get('code', 'DESKTOP_FAILED') if isinstance(result, dict) else 'DESKTOP_FAILED'
            raise RuntimeError('Desktop backend: ' + re.sub('[^A-Z_]', '', str(code))[:80])
        return result['data']
    finally:
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGKILL); p.wait()
        p.stdout.close()


def launch_child(argv, env):
    # Linux PDEATHSIG follows the creating *thread*. A socket/HTTP request thread
    # ends after open(), so a short-lived caller must never own the GUI child.
    # This bounded watcher lives exactly as long as its child; no task queue.
    ready = threading.Event(); result = {}
    def watch():
        try:
            result['child'] = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except Exception as error:
            result['error'] = error
        finally:
            ready.set()
        if 'child' in result: result['child'].wait()
    threading.Thread(target=watch, daemon=True).start(); ready.wait()
    if 'error' in result: raise result['error']
    return result['child']


class Desktop:
    def __init__(self, publish, *, files=None, config_path=CONFIG_PATH, present=None):
        all_config = json.loads(Path(config_path).read_text()) if Path(config_path).exists() else {}
        self.config = all_config.get('desktop', {})
        self.enabled = all_config.get('desktop_enabled') is True
        self.publish = publish; self.files = files
        self.lock = threading.RLock(); self.scopes = {}; self.jobs = {}; self.active = None; self.closed = False
        self.env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}
        for k in ('DISPLAY', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_SESSION_TYPE', 'HYPRLAND_INSTANCE_SIGNATURE'):
            if os.environ.get(k): self.env[k] = os.environ[k]
        from .desktop_windows import Windows
        self.access = Windows(self, present)
        self.available = False
        if self.enabled:
            try:
                for name in ('binary', 'calculator'):
                    p = Path(self.config[name]); info = p.stat()
                    if p.is_symlink() or not p.is_absolute() or info.st_mode & 0o022:
                        raise ValueError('Untrusted executable')
                    if hashlib.sha256(p.read_bytes()).hexdigest() != self.config[name + '_sha256']:
                        raise ValueError('Executable changed')
                probe_home = Path(self.config['state']) / 'availability'
                probe_home.mkdir(parents=True, exist_ok=True, mode=0o700)
                probe = run_json([self.config['binary'], 'status'], {**self.env, 'HOME': str(probe_home), 'AGENT_DESKTOP_HOME': str(probe_home)})
                self.available = probe.get('permissions', {}).get('accessibility', {}).get('state') == 'granted'
            except (OSError, KeyError, ValueError, RuntimeError, subprocess.TimeoutExpired): pass

    def availability(self):
        return {'enabled': self.available and not self.closed, 'configured': self.enabled,
                'version': '1.2.0', 'semantic_wayland': True,
                'physical_input': False, 'arbitrary_launch': False,
                'interaction_modes': {'background': 'semantic only; application behavior must be verified',
                                      'foreground': 'unavailable; never escalated silently'},
                'window_selection': True, 'generic_effects_require_review': True, 'launch_requires_user_consent': True,
                'screenshots': False, 'shortcuts': False, 'drag': False,
                'applications': ['calculator'] + (['comparison'] if Path('/usr/bin/meld').is_file() else []),
                'active_job': self.active,
                'scopes':[{'scope':s['id'],'application':s['application'],'title':s.get('title',s['application']),'expired':time.monotonic()-s['used']>900} for s in self.scopes.values() if not s['released']]}

    identity = staticmethod(process_identity)
    hash = staticmethod(digest)

    def semantic(self, scope, payload, cancel=None, deadline=None):
        return run_json(['/usr/bin/python3', str(PILOT/'desktop/atspi_read.py'), str(scope['pid']), scope['window'], '--semantic'],
                        self.env, cancel=cancel, timeout=3, deadline=deadline, input_data=json.dumps(payload,ensure_ascii=False).encode())

    def cli(self, scope, *args, cancel=None, deadline=None):
        env = {**self.env, 'HOME': str(scope['home']), 'AGENT_DESKTOP_HOME': str(scope['home'] / 'agent-state')}
        return run_json([self.config['binary'], *args], env, cancel=cancel, deadline=deadline)

    def scope(self, ident):
        if not isinstance(ident, str) or ident not in self.scopes:
            raise PermissionError('Choose an actual desktop scope from open')
        scope = self.scopes[ident]
        if scope['released']:
            raise PermissionError('Desktop scope released; open again')
        if time.monotonic() - scope['used'] > 900:
            raise PermissionError('Desktop scope expired; release and open again')
        scope['used'] = time.monotonic()
        try:
            live = (scope['child'] is None or scope['child'].poll() is None) and process_identity(scope['pid']) == scope['identity']
        except OSError:
            live = False
        if not live:
            scope['snapshot'] = None
            raise PermissionError('Application closed or process identity changed')
        return scope

    def windows(self, scope, cancel=None, deadline=None):
        rows = self.cli(scope, 'list-windows', '--app', scope['app'], cancel=cancel, deadline=deadline)
        return [w for w in rows if w.get('pid') == scope['pid'] and w.get('id') == scope['window']]

    def launch(self, application, left=None, right=None):
        if application not in self.availability()['applications']:
            raise PermissionError('Application profile unavailable')
        with self.lock:
            if self.active: raise RuntimeError('Desktop busy; status or cancel the active job')
            for scope in self.scopes.values():
                if not scope['released'] and scope['child'] is not None and scope['child'].poll() is not None: self.release(scope)
                if scope['application'] == application and not scope['released'] and scope['child'] is not None and scope['child'].poll() is None:
                    if application == 'comparison': raise ValueError('Release the existing comparison before opening another')
                    return self.observe(scope)
            if sum(not s['released'] for s in self.scopes.values()) >= 2:
                raise ValueError('Release an existing desktop scope first')
            self.scopes = {k:s for k,s in self.scopes.items() if not s['released']}
            ident = secrets.token_hex(12)
            home = Path(self.config['state']) / ident; home.mkdir(parents=True, mode=0o700)
            (home / '.config').mkdir(mode=0o700)
            (home / 'agent-state').mkdir(mode=0o700)
            env = {**self.env, 'HOME': str(home), 'GSETTINGS_BACKEND': 'memory', 'GTK_MODULES': 'gail:atk-bridge'}
            if self.env.get('WAYLAND_DISPLAY'): env['GDK_BACKEND'] = 'wayland'
            # Private writable home, read-only host and no network. AT-SPI/session
            # buses are still ambient authority: this is not an app security sandbox.
            cmd = ['/usr/bin/bwrap', '--die-with-parent', '--unshare-net', '--ro-bind', '/', '/',
                   '--tmpfs', '/tmp', '--bind', str(home), str(home), '--dev', '/dev', '--proc', '/proc']
            expected_documents = []
            if application == 'calculator':
                cmd += ['--tmpfs', '/usr/share']
                for name in ('glib-2.0', 'locale', 'icons', 'themes', 'fonts', 'fontconfig', 'mime', 'X11', 'xkeyboard-config-2'):
                    p = Path('/usr/share') / name
                    if p.exists(): cmd += ['--ro-bind', str(p), str(p)]
                cmd += ['--ro-bind', self.config['calculator_resources'], '/usr/share/galculator', '--', self.config['calculator']]
                app = 'galculator'; executable = self.config['calculator']
            else:
                if not self.files: raise ValueError('File capability unavailable')
                for label, path in [('left.txt', left), ('right.txt', right)]:
                    value = self.files.read(path)
                    if not value.get('editable') or value.get('truncated') or 'text' not in value:
                        raise ValueError('Comparison requires two small UTF-8 files from allowed file roots')
                    text = value['text']
                    if len(text) > 4096: raise ValueError('Comparison is limited to 4096 characters per file')
                    if re.search(r'(?i)(api[_ -]?key|password|secret|token)\s*[:=]|-----BEGIN .*PRIVATE KEY', text):
                        raise PermissionError('Credential-like content excluded')
                    (home / label).write_text(text)
                    expected_documents.append(text.rstrip('\n'))
                cmd += ['--', '/usr/bin/meld', '--newtab', str(home / 'left.txt'), str(home / 'right.txt')]
                app = Path('/usr/bin/python3').resolve().name; executable = str(Path('/usr/bin/python3').resolve())
            child = launch_child(cmd, env)
            scope = {'id': ident, 'home': home, 'child': child, 'application': application, 'app': app,
                     'released': False, 'used': time.monotonic(), 'snapshot': None, 'views': {}, 'expected_documents': expected_documents}
            self.scopes[ident] = scope
            try:
                deadline = time.monotonic() + 7
                while time.monotonic() < deadline:
                    if child.poll() is not None: raise RuntimeError('Application launch failed')
                    try: rows = self.cli(scope, 'list-windows', '--app', app)
                    except RuntimeError: rows = []
                    # bwrap owns a private process group. Never adopt an existing
                    # window on name/title alone (including single-instance handoff).
                    candidates = []
                    for w in rows:
                        pid = w.get('pid')
                        try:
                            identity = process_identity(pid)
                            if os.getpgid(pid) == child.pid and identity[0] == os.getuid() and (executable is None or identity[1] == executable):
                                candidates.append((w, identity))
                        except (OSError, TypeError): pass
                    if len(candidates) == 1:
                        w, identity = candidates[0]
                        scope.update(pid=w['pid'], window=w['id'], identity=identity)
                        observed = self.observe(scope)
                        while not observed['ready'] and time.monotonic() < deadline:
                            time.sleep(.1); observed = self.observe(scope)
                        return observed
                    if len(candidates) > 1: raise ValueError('Ambiguous application windows')
                    time.sleep(.1)
                raise TimeoutError('Application did not expose a unique accessible window')
            except BaseException:
                self.release(scope); raise

    def observe(self, scope, cancel=None, deadline=None):
        self.scope(scope['id'])
        if scope['application'] == 'accessible-window': return self.access.observe(scope, cancel, deadline)
        rows = self.windows(scope, cancel, deadline)
        if len(rows) != 1: raise PermissionError('Authorized window disappeared')
        raw = self.cli(scope, 'snapshot', '--app', scope['app'], '--window-id', scope['window'], '--compact', '--timeout-ms', '900', cancel=cancel, deadline=deadline)
        if raw.get('complete') is not True or raw.get('window', {}).get('id') != scope['window']:
            raise ValueError('Incomplete or mismatched desktop observation')
        elements = []; queue = [raw['tree']]; count = 0
        while queue:
            node = queue.pop(0); count += 1
            if count > 512: raise ValueError('Desktop tree too large')
            if set(node.get('states', [])) & {'hidden', 'offscreen', 'disabled'}: continue
            if scope['application'] == 'calculator' and node.get('name') in BUTTONS and 'Click' in node.get('available_actions', []) and node.get('role') in {'button', 'switch'}:
                elements.append({'ref': node['ref_id'], 'name': node['name'], 'role': node['role'], 'actions': ['click']})
            queue.extend(node.get('children', []))
        # Supplement reads only the same pid and unique native window; no global
        # screenshot, clipboard, focused-app fallback or persisted raw UI trace.
        texts = run_json(['/usr/bin/python3', str(PILOT / 'desktop/atspi_read.py'), str(scope['pid']), scope['window']], self.env, cancel=cancel, timeout=2, deadline=deadline)
        self.scope(scope['id'])
        if scope['application'] == 'calculator':
            texts = [t for t in texts if t['role'] == 'text']
            if len(texts) != 1 or not re.fullmatch(r'[\d\s.,+−*/()eE%\-infNaN]+', texts[0]['text']):
                raise ValueError('Calculator display could not be verified')
        canonical = {'elements': [{k:v for k,v in e.items() if k != 'ref'} for e in elements], 'texts': texts}
        revision = secrets.token_hex(12)
        scope['snapshot'] = revision
        scope['views'] = {revision: {'elements': elements, 'fingerprint': digest(canonical), 'created': time.monotonic()}}
        return {'ok': True, 'scope': scope['id'], 'application': scope['application'], 'snapshot': revision,
                'elements': elements, 'texts': texts, 'read_only': scope['application'] != 'calculator',
                'process_verified': True, 'window_verified': True, 'observation_untrusted': True,
                'ready': all(any(t['text'].rstrip('\n') == expected for t in texts) for expected in scope.get('expected_documents', []))}

    def release(self, scope):
        scope['released'] = True; scope['snapshot'] = None
        child = scope['child']
        if child is not None and child.poll() is None:
            try: os.killpg(child.pid, signal.SIGTERM); child.wait(timeout=1)
            except subprocess.TimeoutExpired: os.killpg(child.pid, signal.SIGKILL); child.wait()
        # Agent Desktop refs carry UI text; scope storage is transient, not memory.
        import shutil
        shutil.rmtree(scope['home'], ignore_errors=True)

    def action(self, args):
        ident = args.get('scope'); snapshot = args.get('snapshot'); refs = args.get('refs'); buttons = args.get('buttons')
        if (refs is None) == (buttons is None): raise ValueError('Choose observed buttons or refs, not both')
        selected = buttons if buttons is not None else refs
        if not isinstance(selected, list) or not 1 <= len(selected) <= 16 or any(not isinstance(r, str) or len(r) > 80 for r in selected):
            raise ValueError('Use 1–16 observed click references')
        key = digest([ident, snapshot, refs, buttons])
        with self.lock:
            # Exact duplicate delivery returns evidence, never repeats the action.
            if key in self.jobs: return self.public_job(self.jobs[key])
            if self.active: raise RuntimeError('Desktop busy; status or cancel the active job')
            scope = self.scope(ident)
            if scope['application'] != 'calculator': raise PermissionError('This application is read-only')
            view = scope['views'].get(snapshot)
            if not view or scope['snapshot'] != snapshot or time.monotonic() - view['created'] > 30:
                raise PermissionError('Stale snapshot; observe before acting')
            by_ref = {e['ref']: e for e in view['elements']}
            if buttons is not None:
                refs = []
                for name in buttons:
                    matches = [e for e in view['elements'] if e['name'] == name]
                    if len(matches) != 1: raise PermissionError('Button is missing or ambiguous in the current observation')
                    refs.append(matches[0]['ref'])
            if any(r not in by_ref for r in refs): raise PermissionError('Reference outside authorized controls')
            names = [by_ref[r]['name'] for r in refs]
            # Evicted results cannot replay: their consumed snapshots are no longer
            # in the scope's single current view. A late duplicate fails stale.
            for old in list(self.jobs)[:-63]:
                if self.jobs[old]['state'] in TERMINAL: self.jobs.pop(old)
            scope['snapshot'] = None  # Admission consumes the view before any effect.
            job = {'id': key, 'scope': ident, 'state': 'running', 'completed_steps': 0, 'cancel': threading.Event(),
                   'done': threading.Event(), 'started': time.monotonic(), 'result': None, 'buttons': names}
            self.jobs[key] = job; self.active = key
            self.publish({'type': 'process.started', 'id': 'desktop-' + key[:12], 'title': 'Control de calculadora', 'kind':'desktop', 'total_steps':len(names), 'completed_steps':0})
            thread = threading.Thread(target=self.work, args=(job, scope, view, names), daemon=True)
            job['thread'] = thread; thread.start()
        job['done'].wait(.25)  # Bound the foreground handoff, independent of job length.
        return self.public_job(job)

    def work(self, job, scope, view, names):
        try:
            current = self.observe(scope, job['cancel'], deadline=job['started']+12)
            if scope['views'][current['snapshot']]['fingerprint'] != view['fingerprint']:
                raise PermissionError('Application changed since snapshot; no action delivered')
            for name in names:
                if job['cancel'].is_set(): raise InterruptedError('Desktop operation cancelled')
                if time.monotonic() - job['started'] > 12: raise TimeoutError('Sequence budget exceeded')
                matches = [e for e in current['elements'] if e['name'] == name]
                if len(matches) != 1: raise PermissionError('Ambiguous or missing control')
                self.scope(scope['id'])
                delivery = self.cli(scope, 'click', matches[0]['ref'], '--timeout-ms', '700', cancel=job['cancel'], deadline=job['started']+12)
                job['completed_steps'] += 1
                self.publish({'type':'process.update','id':'desktop-'+job['id'][:12],'status':'Comprobando la pantalla…','kind':'desktop','completed_steps':job['completed_steps'],'total_steps':len(names)})
                job['last_delivery'] = delivery.get('disposition', {}).get('delivery', 'unknown')
                current = self.observe(scope, job['cancel'], deadline=job['started']+12)
            job.update(state='completed', result=current)
        except InterruptedError:
            job.update(state='cancelled', error='Cancelled; partial effects may remain. Observe before a new action.')
            scope['snapshot'] = None
        except Exception as error:
            job.update(state='failed', error=str(error)[:180]); scope['snapshot'] = None
        finally:
            job['seconds'] = round(time.monotonic() - job['started'], 4)
            with self.lock: self.active = None
            self.publish({'type': 'process.' + job['state'], 'id': 'desktop-' + job['id'][:12], 'kind':'desktop','completed_steps':job['completed_steps'],'total_steps':len(names), 'status': {'completed':'Acciones terminadas · pantalla observada','failed':'Acción fallida · revisa el estado','cancelled':'Acción cancelada · puede haber cambios parciales'}[job['state']]})
            job['done'].set()

    def public_job(self, job):
        return {'ok':job['state'] not in {'failed','cancelled'}, **{k:v for k,v in job.items() if k not in {'cancel', 'done', 'thread', 'started'}}}

    def request(self, args, *, user=False):
        action = args.get('action')
        allowed = {'availability': set(), 'status': {'job'}, 'open': {'application','left','right'},
                   'observe': {'scope'}, 'act': {'scope','snapshot','refs','buttons'}, 'cancel': {'job'}, 'release': {'scope'},
                   'discover':set(), 'select':{'candidate'}, 'prepare':{'scope','snapshot','operation','ref','text'},
                   'review':{'proposal_id'}, 'confirm':{'proposal_id','approve'}, 'stop':set()}
        if action not in allowed or set(args) - allowed[action] - {'action'}: raise ValueError('Unsupported desktop operation or fields')
        if action == 'availability': return self.availability()
        if not self.available or self.closed: raise PermissionError('Desktop capability unavailable; prepare the pinned installation')
        if action == 'stop':
            with self.lock:
                for job in self.jobs.values(): job['cancel'].set()
                for p in self.access.pending.values():
                    if p['status']=='pending': p['status']='cancelled'
                for scope in self.scopes.values(): scope['snapshot']=None
            return {'ok':True,'cancellation_requested':True,'held_input':False}
        if action == 'review':
            with self.lock:
                p=self.access.review(args.get('proposal_id'))
                return {k:p[k] for k in ('id','tool','operation','path','content','status')}
        if action == 'status':
            with self.lock:
                ident = args.get('job', self.active)
                if ident is None: return {**self.availability(), 'state': 'idle'}
                if ident not in self.jobs: raise ValueError('Unknown desktop job; no action was replayed after restart')
                return self.public_job(self.jobs[ident])
        if action == 'cancel':
            with self.lock:
                job = self.jobs.get(args.get('job', self.active))
                if job is None: raise ValueError('No matching desktop operation')
                job['cancel'].set()
                return {'id':job['id'], 'state':job['state'], 'cancellation_requested':job['state'] not in TERMINAL}
        if action == 'act': return self.action(args)
        with self.lock:
            if self.active: raise RuntimeError('Desktop busy; status or cancel the active job')
            if action == 'discover': return self.access.discover()
            if action == 'select': return self.access.select(args.get('candidate'),user)
            if action == 'prepare': return self.access.prepare(args)
            if action == 'confirm': return self.access.confirm(args.get('proposal_id'),args.get('approve'),user)
            if action == 'open': return self.access.open(args.get('application'), args.get('left'), args.get('right'), user)
            if action == 'observe': return self.observe(self.scope(args.get('scope')))
            scope = self.scopes.get(args.get('scope'))
            if not scope: raise PermissionError('Unknown desktop scope')
            self.release(scope)
            return {'state':'released','scope':scope['id']}

    def close(self):
        self.closed = True
        with self.lock:
            jobs = list(self.jobs.values())
            for job in jobs: job['cancel'].set()
        for job in jobs: job['done'].wait(4)
        for scope in self.scopes.values():
            self.release(scope)
