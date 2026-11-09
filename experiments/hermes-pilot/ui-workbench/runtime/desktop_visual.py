"""Ephemeral headless Wayland adapter. Only fixed, offline application profiles.

The existing Desktop owns consent, scope, jobs and cancellation. This adapter
never receives host display, bus, input-device or credential paths.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import struct
import threading
import time

from .desktop import digest, launch_child, process_identity, run_json, TERMINAL
from .machine import PILOT


class Visual:
    def __init__(self, desktop):
        self.d = desktop
        self.settings = desktop.config.get('visual', {})
        self.ready = False
        try:
            self.root = Path(self.settings['root'])
            self.validate_installation()
            self.ready = True
        except (OSError, KeyError, ValueError):
            pass

    def validate_installation(self):
        root = self.root
        if not root.is_absolute() or root.is_symlink() or root.stat().st_mode & 0o022:
            raise ValueError('Untrusted visual installation')
        manifest = (root/'.argos-files.json').read_bytes()
        if hashlib.sha256(manifest).hexdigest() != self.settings['manifest_sha256']:
            raise ValueError('Visual manifest changed')
        files = json.loads(manifest)
        if not {'pointer-seat', 'key-combo', 'usr/bin/sway', 'usr/bin/grim', 'usr/bin/wtype'} <= files.keys():
            raise ValueError('Incomplete visual installation')
        for name, expected in files.items():
            path = root/name
            if not path.resolve().is_relative_to(root.resolve()) or path.stat().st_mode & 0o022 or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('Visual component changed')

    def proposal(self, args):
        if not self.ready: raise PermissionError('Prepare the pinned visual installation')
        profile = args.get('application', 'pad')
        if profile not in {'pad', 'comparison'} or (profile=='comparison' and not Path('/usr/bin/meld').is_file()): raise ValueError('Unknown isolated application')
        scale = args.get('scale', 1)
        outputs = args.get('outputs', 1)
        if type(scale) not in (int, float) or scale not in (1, 1.5, 2) or type(outputs) is not int or outputs not in (1, 2):
            raise ValueError('Supported layouts: 1–2 virtual outputs, scale 1, 1.5 or 2')
        record = {'kind':'visual_launch', 'application':profile, 'scale':scale, 'outputs':outputs,
                  'left':args.get('left'), 'right':args.get('right')}
        if profile == 'comparison' and (not isinstance(record['left'], str) or not isinstance(record['right'], str)):
            raise ValueError('Choose two authorized files for disposable copies')
        for p in self.d.access.pending.values():
            if p['status']=='pending' and time.monotonic()-p['created']<120 and all(p.get(k)==v for k,v in record.items()):
                return {'status':'needs_approval','proposal_id':p['id']}
        return self.d.access.proposal({**record, 'path':'Sesión visual aislada · '+profile,
            'content':'Autorizar captura, clic, scroll, texto, atajos y arrastre dentro de una sesión gráfica desechable sin red ni acceso al escritorio, cuentas o archivos habituales. Se cierra tras 5 minutos sin operaciones. Los cambios solo afectan a copias temporales. No autoriza entrada en tu escritorio.' +
            ('\nCopias de: '+record['left']+'\n'+record['right'] if profile=='comparison' else '')})

    def sandbox(self, scope, argv):
        home = scope['home']
        return ['/usr/bin/bwrap','--unshare-all','--die-with-parent','--new-session',
                '--ro-bind','/usr','/usr','--symlink','usr/lib','/lib','--symlink','usr/lib','/lib64',
                '--symlink','usr/bin','/bin','--proc','/proc','--dev','/dev','--tmpfs','/tmp',
                '--ro-bind',str(home/'run/passwd'),'/etc/passwd','--ro-bind',str(home/'run/group'),'/etc/group',
                '--ro-bind',str(home/'run/machine-id'),'/etc/machine-id','--ro-bind','/etc/fonts','/etc/fonts','--ro-bind','/etc/ld.so.cache','/etc/ld.so.cache',
                '--ro-bind',str(self.root),'/opt/visual','--ro-bind',str(PILOT/'desktop/visual'),'/opt/argos',
                '--bind',str(home/'run'),'/run/av','--bind',str(home/'private'),'/home/agent',
                '--bind',str(scope.get('work',home/'work')),'/work','--chdir','/work','--',*argv]

    def environment(self, scope):
        return {'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':'/home/agent','XDG_RUNTIME_DIR':'/run/av',
                'SWAYSOCK':'/run/av/ipc.sock','WAYLAND_DISPLAY':scope.get('display','wayland-1'),
                'WLR_BACKENDS':'headless','WLR_HEADLESS_OUTPUTS':str(scope['outputs']),
                'WLR_RENDERER':'pixman','WLR_LIBINPUT_NO_DEVICES':'1','LD_LIBRARY_PATH':'/opt/visual/usr/lib',
                'GDK_BACKEND':'wayland','QT_QPA_PLATFORM':'wayland','NO_AT_BRIDGE':'1','GSETTINGS_BACKEND':'memory','XDG_SESSION_TYPE':'wayland'}

    def launch(self, proposal):
        self.validate_installation()
        definition=proposal.get('definition')
        if definition and self.d.profiles.definition(definition['id'])!=definition:raise PermissionError('Application profile changed')
        d = self.d
        if any(s['application']=='isolated-visual' and not s['released'] and s['child'].poll() is None for s in d.scopes.values()):
            raise ValueError('Release the existing isolated session first')
        if sum(not s['released'] for s in d.scopes.values()) >= 3: raise ValueError('Release an existing scope first')
        ident = secrets.token_hex(12)
        home = Path(d.config['state'])/ident
        home.mkdir(mode=0o700, parents=True)
        for name in ('run','private','work'): (home/name).mkdir(mode=0o700)
        scope = {'id':ident,'home':home,'application':'isolated-visual','title':'Visual · '+proposal['application'],
                 'profile':proposal['application'],'outputs':proposal['outputs'],'scale':proposal['scale'],
                 'released':False,'used':time.monotonic(),'snapshot':None,'views':{},'child':None}
        if proposal.get('workspace'):scope['work']=Path(proposal['workspace']);scope['project']=proposal['project'];scope['task_id']=proposal['task_id'];scope['session_id']=proposal['session_id']
        d.scopes[ident] = scope
        try:
            if proposal['application']=='comparison':
                for name in ('left','right'):
                    value = d.files.read(proposal[name]) if d.files else {}
                    text = value.get('text')
                    if not value.get('editable') or value.get('truncated') or not isinstance(text,str) or len(text)>4096:
                        raise PermissionError('Comparison requires two small allowed UTF-8 files')
                    self.check_text(text)
                    (home/'work'/(name+'.txt')).write_text(text)
            if definition and not proposal.get('workspace'):
                work=scope.get('work',home/'work')
                for name,content in definition['seed'].items():
                    if not (work/name).exists():(work/name).write_text(content)
            (home/'run/session.json').write_text(json.dumps({'application':proposal['application'],**({'profile':definition} if definition else {})}))
            (home/'run/lease').touch()
            (home/'run/passwd').write_text(f'agent:x:{os.getuid()}:{os.getgid()}::/home/agent:/usr/bin/nologin\n')
            (home/'run/group').write_text(f'agent:x:{os.getgid()}:\n')
            (home/'run/machine-id').write_text(secrets.token_hex(16)+'\n')
            scale = proposal['scale']
            config = 'xwayland disable\nseat seat0 fallback true\nseat seat0 attach *\nfocus_follows_mouse no\nfont monospace 12\ndefault_border pixel 0\n'
            for i in range(proposal['outputs']):
                config += f'output HEADLESS-{i+1} resolution {int(1000*scale)}x{int(700*scale)} position {1000*i} 0 scale {scale}\n'
            (home/'run/sway.conf').write_text(config)
            child = launch_child(self.sandbox(scope,['/usr/bin/python3','/opt/argos/session.py']),self.environment(scope))
            scope.update(child=child,pid=child.pid,identity=process_identity(child.pid))
            until = time.monotonic()+9
            while time.monotonic()<until:
                if child.poll() is not None: raise RuntimeError('Private compositor or application failed to start')
                ready = home/'run/ready.json'
                if ready.exists():
                    scope['display']=json.loads(ready.read_text())['wayland']
                    try:
                        geometry=self.geometry(scope)
                        if definition and geometry['app_id']!=definition['app_id']:raise PermissionError('Unexpected application identity')
                        time.sleep(.3)  # First mapped buffer may precede the application's first paint.
                        return self.observe(scope)
                    except (PermissionError, FileNotFoundError): pass
                time.sleep(.06)
            raise TimeoutError('Isolated application not ready')
        except BaseException:
            d.release(scope)
            raise

    def ipc(self, scope, kind, payload=''):
        self.d.scope(scope['id'])
        path = scope['home']/'run/ipc.sock'
        if not path.is_socket() or path.stat().st_uid != os.getuid(): raise PermissionError('Private compositor unavailable')
        data = payload.encode()
        def read(sock, n):
            result = b''
            while len(result)<n:
                part = sock.recv(n-len(result))
                if not part: raise RuntimeError('Private compositor disconnected')
                result += part
            return result
        with socket.socket(socket.AF_UNIX) as sock:
            sock.settimeout(.7);sock.connect(str(path));sock.sendall(struct.pack('<6sII',b'i3-ipc',len(data),kind)+data)
            magic, length, reply = struct.unpack('<6sII',read(sock,14))
            if magic!=b'i3-ipc' or reply!=kind or length>262144: raise ValueError('Invalid private compositor response')
            result = json.loads(read(sock,length))
        if kind==0 and (not isinstance(result,list) or not all(v.get('success') for v in result)):
            raise RuntimeError('Private input delivery rejected')
        return result

    def geometry(self, scope):
        tree = self.ipc(scope,4); nodes=[tree];windows=[]
        while nodes:
            n=nodes.pop();nodes.extend(n.get('nodes',[])+n.get('floating_nodes',[]))
            if n.get('app_id') and n.get('focused'): windows.append(n)
        if len(windows)!=1: raise PermissionError('No unique focused isolated application window')
        w=windows[0];r=w['rect']
        if not 10<=r['width']<=1100 or not 10<=r['height']<=800: raise PermissionError('Window exceeds capture budget')
        outputs=[{'name':o['name'],'rect':o['rect'],'scale':o['scale']} for o in self.ipc(scope,3) if o.get('active')]
        return {'window':w['id'],'app_id':w['app_id'],'pid':w['pid'],'rect':r,'outputs':outputs}

    def capture(self, scope, cancel=None, deadline=None):
        geometry = self.geometry(scope);r=geometry['rect']
        region = f"{r['x']},{r['y']} {r['width']}x{r['height']}"
        data = run_json(self.sandbox(scope,['/opt/visual/usr/bin/grim','-s','1','-g',region,'-']),
                        self.environment(scope),raw=True,cancel=cancel,deadline=deadline,limit=1000000)
        if not data.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('Invalid private window capture')
        if geometry!=self.geometry(scope): raise PermissionError('Window changed during capture')
        return geometry,data

    def observe(self, scope, cancel=None, deadline=None):
        geometry,data=self.capture(scope,cancel,deadline)
        token=secrets.token_hex(12)
        scope['snapshot']=token
        scope['views']={token:{'geometry':geometry,'image':hashlib.sha256(data).hexdigest(),'created':time.monotonic()}}
        (scope['home']/'run/lease').touch()
        return {'ok':True,'scope':scope['id'],'application':'isolated-visual','snapshot':token,'ready':True,
                'interaction_mode':'isolated','host_input':False,'observation_untrusted':True,
                **{k:scope[k] for k in ('profile','project','task_id','session_id') if k in scope},
                'geometry':geometry,'width':geometry['rect']['width'],'height':geometry['rect']['height'],
                'data_url':'data:image/png;base64,'+base64.b64encode(data).decode()}

    @staticmethod
    def check_text(text):
        if not isinstance(text,str) or len(text)>4096 or len(text.encode())>8192 or re.search(r'(?i)(api[_ -]?key|password|secret|token)\s*[:=]|-----BEGIN .*PRIVATE KEY',text):
            raise PermissionError('Text exceeds budget or resembles credentials')
        if any(ord(c)<32 and c not in '\n\t' for c in text): raise ValueError('Control characters excluded')

    @classmethod
    def validate_actions(cls, actions, view):
        if not isinstance(actions,list) or not 1<=len(actions)<=16: raise ValueError('Use 1–16 structured actions')
        fields={'move':{'x','y'},'click':{'x','y','button'},'scroll':{'x','y','steps','direction'},
                'text':{'text'},'keys':{'keys'},'down':{'x','y','button'},'up':{'button'},
                'drag':{'x','y','to_x','to_y','duration_ms'}}
        held=set();total_text=0
        for a in actions:
            if not isinstance(a,dict) or a.get('type') not in fields or set(a)-fields[a['type']]-{'type'}: raise ValueError('Invalid visual action')
            typ=a['type'];r=view['geometry']['rect']
            for x,y in [('x','y'),('to_x','to_y')] if typ=='drag' else ([('x','y')] if typ in ('click','move','scroll','down') else []):
                if any(type(a.get(k)) is not int for k in (x,y)) or not 1<=a[x]<r['width'] or not 1<=a[y]<r['height']:
                    raise ValueError('Coordinates must be inside the observed window, excluding border zero')
            if typ in ('click','down','up') and a.get('button','left') not in ('left','middle','right'): raise ValueError('Invalid mouse button')
            if typ=='text':
                cls.check_text(a.get('text'));total_text+=len(a['text'])
            if typ=='keys':
                keys=a.get('keys')
                if not isinstance(keys,list) or not 1<=len(keys)<=4 or any(k not in {'ctrl','shift','alt','Return','Tab','Escape','BackSpace','Delete','Left','Right','Up','Down','Home','End','a','c','v','x','z','s'} for k in keys) or keys[-1] in {'ctrl','shift','alt'} or any(k not in {'ctrl','shift','alt'} for k in keys[:-1]):
                    raise ValueError('Use a supported key with optional ctrl/shift/alt modifiers')
            if typ=='scroll' and (type(a.get('steps')) is not int or not 1<=a['steps']<=10 or a.get('direction') not in ('up','down','left','right')): raise ValueError('Invalid scroll')
            if typ=='drag' and (type(a.get('duration_ms',500)) is not int or not 100<=a.get('duration_ms',500)<=3000): raise ValueError('Invalid drag duration')
            button=a.get('button','left')
            if typ=='down':
                if button in held: raise ValueError('Button already held')
                held.add(button)
            if typ=='up':
                if button not in held: raise ValueError('Unbalanced release')
                held.remove(button)
            if typ in ('drag','click') and held: raise ValueError('Release held input before click or drag')
        if held or total_text>4096: raise ValueError('Release every button within the bounded batch')

    def action(self, args):
        d=self.d;ident=args.get('scope');token=args.get('snapshot');actions=args.get('actions')
        key=digest([ident,token,actions])
        with d.lock:
            if key in d.jobs:return d.public_job(d.jobs[key])
            if d.active:raise RuntimeError('Desktop busy')
            scope=d.scope(ident)
            if scope['application']!='isolated-visual':raise PermissionError('Visual input requires an isolated scope')
            view=scope['views'].get(token)
            if not view or scope['snapshot']!=token or time.monotonic()-view['created']>30:raise PermissionError('Stale visual observation')
            self.validate_actions(actions,view)
            scope['snapshot']=None
            for old in list(d.jobs)[:-63]:
                if d.jobs[old]['state'] in TERMINAL:d.jobs.pop(old)
            job={'id':key,'scope':ident,'state':'running','completed_steps':0,'cancel':threading.Event(),'done':threading.Event(),
                 'started':time.monotonic(),'result':None,'interaction_mode':'isolated','host_input':False}
            d.jobs[key]=job;d.active=key
            d.publish({'type':'process.started','id':'desktop-'+key[:12],'kind':'desktop','title':'Sesión visual aislada','total_steps':len(actions)})
            job['thread']=threading.Thread(target=self.work,args=(job,scope,view,actions),daemon=True);job['thread'].start()
        job['done'].wait(.25)
        return d.public_job(job)

    def work(self, job, scope, view, actions):
        held=set();deadline=job['started']+12;d=self.d
        def guard():
            if job['cancel'].is_set():raise InterruptedError('Visual operation cancelled')
            if time.monotonic()>deadline:raise TimeoutError('Visual operation deadline')
            if self.geometry(scope)!=view['geometry']:raise PermissionError('Window/focus/layout changed')
        def pointer(command):
            self.d.scope(scope['id'])
            with socket.socket(socket.AF_UNIX) as sock:
                sock.settimeout(1);sock.connect(str(scope['home']/'run/pointer.sock'))
                sock.sendall((command+'\n').encode())
                if sock.recv(16)!=b'ok\n':raise RuntimeError('Private pointer rejected delivery')
        def move(x,y):
            guard();r=view['geometry']['rect'];pointer(f"M {r['x']+x} {r['y']+y} {1000*scope['outputs']} 700")
        def down(button):held.add(button);pointer('B '+{'button1':'272','button2':'274','button3':'273'}[button]+' 1')
        def up(button):pointer('B '+{'button1':'272','button2':'274','button3':'273'}[button]+' 0');held.discard(button)
        try:
            geometry,pixels=self.capture(scope,job['cancel'],deadline)
            if geometry!=view['geometry'] or hashlib.sha256(pixels).hexdigest()!=view['image']:raise PermissionError('Pixels changed since observation; observe again')
            for a in actions:
                guard();typ=a['type'];button={'left':'button1','middle':'button2','right':'button3'}[a.get('button','left')]
                if typ in ('move','click','down','scroll','drag'):move(a['x'],a['y'])
                if typ in ('click','down'):down(button)
                if typ in ('click','up'):up(button)
                if typ=='scroll':
                    axis=0 if a['direction'] in ('up','down') else 1
                    amount=-1 if a['direction'] in ('up','left') else 1
                    for _ in range(a['steps']):
                        guard();pointer(f'S {axis} {amount}')
                        if job['cancel'].wait(.02):raise InterruptedError('Scroll cancelled')
                if typ=='drag':
                    down('button1')
                    for i in range(1,21):
                        if job['cancel'].wait(a.get('duration_ms',500)/20000):raise InterruptedError('Drag cancelled')
                        move(round(a['x']+(a['to_x']-a['x'])*i/20),round(a['y']+(a['to_y']-a['y'])*i/20))
                    up('button1')
                if typ in ('text','keys'):
                    argv=['/opt/visual/usr/bin/wtype','-s','80','-d','1'];data=None
                    if typ=='text':argv+=['-'];data=a['text'].encode()
                    else:
                        codes={'a':30,'c':46,'v':47,'x':45,'z':44,'s':31,'Return':28,'Tab':15,'Escape':1,'BackSpace':14,'Delete':111,'Left':105,'Right':106,'Up':103,'Down':108,'Home':102,'End':107}
                        mods=sum({'shift':1,'ctrl':4,'alt':8}[mod] for mod in set(a['keys'][:-1]))
                        argv=['/opt/visual/key-combo',str(mods),str(codes[a['keys'][-1]])]
                    try:run_json(self.sandbox(scope,argv),self.environment(scope),raw=True,input_data=data,cancel=job['cancel'],deadline=deadline)
                    except BaseException:
                        # An interrupted key helper may have held modifiers. Destroy
                        # the entire private seat; never try releasing on the host.
                        d.release(scope);raise
                job['completed_steps']+=1
                d.publish({'type':'process.update','id':'desktop-'+job['id'][:12],'kind':'desktop','completed_steps':job['completed_steps'],'total_steps':len(actions)})
            if job['cancel'].wait(.08):raise InterruptedError('Visual operation cancelled')
            current=self.observe(scope,job['cancel'],deadline);current.pop('data_url')
            job.update(state='completed',result=current,verification='New screenshot available via observe; delivery alone does not prove the user goal')
        except InterruptedError:job.update(state='cancelled',error='Cancelled; partial effects may remain')
        except Exception as error:job.update(state='failed',error=str(error)[:180])
        finally:
            try:
                for button in list(held):up(button)
            except Exception:
                d.release(scope)
            if job['state']!='completed':scope['snapshot']=None
            job['held_input_released']=not held or scope['released']
            job['seconds']=round(time.monotonic()-job['started'],4)
            with d.lock:d.active=None
            d.publish({'type':'process.'+job['state'],'id':'desktop-'+job['id'][:12],'kind':'desktop','completed_steps':job['completed_steps'],'total_steps':len(actions),'status':'Sesión aislada · observa el resultado'})
            job['done'].set()
