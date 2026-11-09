"""Authorized semantic windows, using the existing Desktop job slot and Broker UI.

No new scheduler or persistent grants. Generic effects are reviewed separately
from read access; neither an app title nor model prose grants authority.
"""
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time

from .desktop_hyprland import Hyprland


class Windows:
    def __init__(self, desktop, present):
        self.d = desktop; self.present = present; self.pending = {}; self.candidates = {}
        self.hypr = Hyprland(desktop.env)

    def discover(self):
        d = self.d
        home = Path(d.config['state']) / 'discovery'; home.mkdir(mode=0o700, parents=True, exist_ok=True)
        rows = d.cli({'home':home}, 'list-windows')
        if len(rows) > 128: raise ValueError('Too many windows')
        result = []; self.candidates = {}
        for w in rows:
            try:
                identity = d.identity(w['pid'])
                if identity[0] != os.getuid(): continue
                compositor = self.hypr.window(w['pid'])
                self.deny_control_plane(w['pid'], compositor)
                token = secrets.token_hex(12)
                candidate = {'candidate':token, 'pid':w['pid'], 'window':w['id'], 'app':Path(identity[1]).name,
                             'identity':identity, 'compositor':compositor, 'created':time.monotonic(),
                             'title':str(w.get('title', ''))[:160]}
                self.candidates[token] = candidate
                result.append({k:candidate[k] for k in ('candidate','pid','app','title')})
            except (OSError, ValueError, PermissionError): continue
        return {'ok':True, 'windows':result, 'content_read':False, 'hyprland':self.hypr.capabilities()}

    def open(self, application, left, right, user):
        d = self.d
        if application not in d.availability()['applications']:
            raise PermissionError('Application profile unavailable')
        # Reusing an owned live calculator needs no focus or new consent.
        if application == 'calculator':
            for scope in d.scopes.values():
                if scope['application']==application and not scope['released'] and scope['child'] is not None and scope['child'].poll() is None:
                    return d.observe(scope)
        if user: return d.launch(application, left, right)
        for p in self.pending.values():
            if p.get('kind')=='launch' and p.get('application')==application and p.get('left')==left and p.get('right')==right and p['status']=='pending' and time.monotonic()-p['created']<120:
                return {'status':'needs_approval','proposal_id':p['id']}
        return self.proposal({'kind':'launch','application':application,'left':left,'right':right,
                             'path':application,'content':'Abrir '+application+' puede cambiar temporalmente el foco y la distribución de ventanas. Autoriza únicamente este lanzamiento; no concede control del teclado o ratón.'+
                             (('\nComparar copias de:\n'+str(left)+'\n'+str(right)) if application=='comparison' else '')})

    def proposal(self, record):
        for key in list(self.pending):
            if time.monotonic()-self.pending[key]['created'] > 120: self.pending.pop(key)
        if len(self.pending) >= 16: raise ValueError('Resolve pending desktop reviews first')
        ident = secrets.token_hex(12)
        record.update(id=ident, created=time.monotonic(), status='pending', tool='desktop', operation='desktop')
        self.pending[ident] = record
        if self.present:
            self.present({'type':'window.open','id':'desktop-review-'+ident,'kind':'change',
                          'title':'Autorizar acceso al escritorio','text':json.dumps({'tool':'desktop','id':ident})})
        return {'status':'needs_approval','proposal_id':ident,'summary':record['content']}

    def select(self, candidate, user):
        w = self.candidates.get(candidate)
        if not w or time.monotonic()-w['created'] > 120: raise PermissionError('Refresh window discovery')
        if user: return self.attach(w)
        return self.proposal({'kind':'attach','window':w,'path':w['app']+' · '+w['title'],
                             'content':'Leer los controles y el texto de esta ventana durante esta sesión (máximo 15 minutos de inactividad). No autoriza escribir, enviar, borrar ni controlar el teclado o ratón.'})

    @staticmethod
    def deny_control_plane(pid, window):
        # Accessibility must never become a path for an agent to click its own
        # trusted approval surface. Metadata only; no controller content is read.
        if str(window.get('class','')).lower() in {'argos','argos-workspace','argos-workspace.desktop'}:
            raise PermissionError('ARGOS approval surfaces cannot be automated')
        with (Path('/proc')/str(pid)/'cmdline').open('rb') as stream:
            if b'ui-workbench/desktop/main.cjs' in stream.read(16384):
                raise PermissionError('ARGOS approval surfaces cannot be automated')

    def validate_window(self, w):
        try: live = self.d.identity(w['pid']) == w['identity']
        except OSError: live = False
        if not live: raise PermissionError('Application closed or process identity changed')
        current = self.hypr.window(w['pid'], w['compositor']['address'])
        self.deny_control_plane(w['pid'], current)
        if current.get('stableId') != w['compositor'].get('stableId'): raise PermissionError('Window replaced')
        return current

    def attach(self, w):
        d = self.d; self.validate_window(w)
        for scope in d.scopes.values():
            if scope['application']=='accessible-window' and not scope['released'] and scope.get('window') == w['window'] and scope.get('identity') == w['identity']:
                return d.observe(scope)
        if sum(not s['released'] for s in d.scopes.values()) >= 4: raise ValueError('Release an existing scope first')
        ident = secrets.token_hex(12); home = Path(d.config['state']) / ident
        home.mkdir(mode=0o700, parents=True); (home/'agent-state').mkdir(mode=0o700)
        scope = {**w, 'id':ident,'home':home,'application':'accessible-window','child':None,
                 'released':False,'used':time.monotonic(),'snapshot':None,'views':{}}
        d.scopes[ident] = scope
        try: return d.observe(scope)
        except BaseException: d.release(scope); raise

    def observe(self, scope, cancel=None, deadline=None):
        d = self.d; before = self.validate_window(scope)
        raw = d.semantic(scope, {'operation':'observe'}, cancel, deadline)
        after = self.validate_window(scope)
        if before != after: raise PermissionError('Window moved during observation')
        revision = secrets.token_hex(12)
        scope['snapshot'] = revision
        scope['views'] = {revision:{**raw,'created':time.monotonic(),'geometry':after,'layout':self.hypr.layout()}}
        return {'ok':True,'scope':scope['id'],'application':scope['app'],'snapshot':revision,
                'elements':raw['elements'],'texts':[{'role':e['role'],'name':e['name'],'text':e['text']} for e in raw['elements'] if e['text']],
                'read_only':False,'mutation_requires_review':True,'ready':True,'observation_untrusted':True,
                'interaction_mode':'background','method':'atspi','physical_input':False,
                'application_focus_side_effects':'not guaranteed for arbitrary applications',
                'window_verified':True,'process_verified':True,'geometry':after}

    def prepare(self, args):
        d = self.d; scope = d.scope(args.get('scope'))
        if scope['application'] != 'accessible-window': raise PermissionError('Use the existing profile operation')
        snapshot = args.get('snapshot'); view = scope['views'].get(snapshot)
        if not view or scope['snapshot'] != snapshot or time.monotonic()-view['created'] > 120:
            raise PermissionError('Stale snapshot; observe again')
        operation = args.get('operation'); ref = args.get('ref')
        rows = [e for e in view['elements'] if e['ref'] == ref and operation in e['actions']]
        if len(rows) != 1: raise PermissionError('Unsupported or unauthorized control')
        text = args.get('text', '')
        if operation == 'replace_text':
            if not isinstance(text,str) or len(text.encode()) > 4096 or re.search(r'(?i)password|secret|token|api[_ -]?key|contrase[ñn]a|-----BEGIN|(?:sk-|ghp_)[\w-]{16,}',text):
                raise ValueError('Text too large or credential-like')
        elif operation != 'click' or text: raise ValueError('Unsupported semantic operation')
        payload = {'operation':operation,'ref':ref,'text':text,'fingerprint':view['fingerprint']}
        key = d.hash([scope['id'],snapshot,payload])
        for p in self.pending.values():
            if p.get('key') == key: return {'status':p['status'],'proposal_id':p['id']}
        content = ('Texto actual:\n'+rows[0].get('text','')+'\n\nReemplazar el texto por:\n'+text if operation == 'replace_text' else
                   'Activar este control una vez. Revisa su efecto: enviar, publicar, borrar o instalar requiere tu autorización explícita aquí.')
        content += '\nMétodo: accesibilidad semántica, sin teclado/ratón global. La aplicación podría abrir otra ventana; ARGOS detendrá la secuencia si cambia el foco.'
        return self.proposal({'kind':'effect','scope':scope['id'],'snapshot':snapshot,'view':view,'payload':payload,'key':key,
                              'path':scope['app']+' · '+rows[0]['role']+' · '+rows[0]['name'],'content':content})

    def review(self, ident):
        p = self.pending.get(ident)
        if not p or time.monotonic()-p['created'] > 120: raise PermissionError('Review expired; observe again')
        return p

    def confirm(self, ident, approve, user):
        if not user: raise PermissionError('Only a trusted user interaction may approve desktop access')
        if type(approve) is not bool: raise ValueError('Explicit approval required')
        p = self.review(ident)
        if p['status'] != 'pending': return {'status':p['status'], 'job':p.get('job')}
        if not approve: p['status']='cancelled'; return {'status':'cancelled'}
        if self.d.active: raise RuntimeError('Desktop busy')
        p['status'] = 'consumed'  # A failed start never replays an approved effect.
        if p['kind'] == 'visual_launch':
            result = self.d.visual.launch(p); p['status']='applied'
            return {'status':'applied',**result}
        if p['kind'] == 'launch':
            result = self.d.launch(p['application'], p['left'], p['right']); p['status']='applied'
            return {'status':'applied',**result}
        if p['kind'] == 'attach':
            result = self.attach(p['window']); p['status']='applied'; return {'status':'applied',**result}
        d = self.d; scope = d.scope(p['scope'])
        if scope['snapshot'] != p['snapshot']: raise PermissionError('Stale approval; observe again')
        scope['snapshot'] = None
        for old in list(d.jobs)[:-63]:
            if d.jobs[old]['state'] in {'completed','failed','cancelled'}: d.jobs.pop(old)
        job = {'id':p['key'],'scope':scope['id'],'state':'running','completed_steps':0,'cancel':threading.Event(),
               'done':threading.Event(),'started':time.monotonic(),'result':None,'interaction_mode':'background'}
        d.jobs[job['id']]=job; d.active=job['id']; p['job']=job['id']; p['status']='started'
        d.publish({'type':'process.started','id':'desktop-'+job['id'][:12],'kind':'desktop','title':'Acción semántica autorizada','total_steps':1,'completed_steps':0})
        thread=threading.Thread(target=self.work,args=(job,scope,p),daemon=True);job['thread']=thread;thread.start()
        return {'status':'started',**d.public_job(job)}

    def work(self, job, scope, proposal):
        d=self.d; deadline=job['started']+12
        try:
            d.scope(scope['id'])
            if self.validate_window(scope) != proposal['view']['geometry'] or self.hypr.layout() != proposal['view']['layout']:
                raise PermissionError('Window or output layout changed; no effect delivered')
            before = self.hypr.seat()
            delivery = d.semantic(scope, proposal['payload'], job['cancel'], deadline)
            job['completed_steps']=1; job['delivery']=delivery
            current = d.observe(scope, job['cancel'], deadline)
            after = self.hypr.seat()
            job['input_observation']={'focus_unchanged':before['focus']==after['focus'], 'cursor_unchanged':before['cursor']==after['cursor'],
                                      'physical_input_sent':False,'sampled_only':True}
            if before['focus'] != after['focus']:
                raise PermissionError('Focus changed during action; stopped without restoring or replaying input')
            if proposal['payload']['operation'] == 'replace_text':
                rows=[e for e in current['elements'] if e['ref']==proposal['payload']['ref']]
                if len(rows)!=1 or rows[0]['text'] != proposal['payload']['text']:
                    raise ValueError('Text delivery could not be verified')
                job['verified_text']=True
            job.update(state='completed',result=current)
        except InterruptedError: job.update(state='cancelled',error='Cancelled; inspect partial effects before continuing')
        except Exception as error: job.update(state='failed',error=str(error)[:180])
        finally:
            if job['state']!='completed':scope['snapshot']=None
            job['seconds']=round(time.monotonic()-job['started'],4)
            with d.lock: d.active=None
            d.publish({'type':'process.'+job['state'],'id':'desktop-'+job['id'][:12],'kind':'desktop','total_steps':1,
                       'completed_steps':job['completed_steps'],'status':'Acción terminada; revisa la evidencia' if job['state']=='completed' else 'Detenido; observa antes de continuar'})
            job['done'].set()
