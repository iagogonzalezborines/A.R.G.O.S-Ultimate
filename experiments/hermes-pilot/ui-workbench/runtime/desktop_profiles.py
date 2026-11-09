"""Reviewable application definitions; metadata/configuration, never arbitrary argv."""
import hashlib
import json
import os
from pathlib import Path

from .machine import PILOT


class Profiles:
    def __init__(self, desktop):
        self.d=desktop
        self.path=Path(desktop.config.get('state','/nonexistent'))/'visual-profiles.json'
        self.catalogue=PILOT/'desktop/visual/applications.json'

    def definition(self, name):
        profiles=json.loads(self.catalogue.read_text())
        if name not in profiles:raise PermissionError('Application has no reviewed capability profile')
        p=profiles[name]
        if set(p)!={'name','executable','argv','resources','app_id','private_bus','memory_mib','network','filesystem','operations','seed'} or p['network'] is not False or p['memory_mib']!=1536 or p['argv'][0]!=p['executable']:
            raise ValueError('Unsupported application profile')
        for arg in p['argv']:
            if not isinstance(arg,str) or '\x00' in arg:raise ValueError('Invalid profile argv')
        hashes={}
        for value in [p['executable'],*p['resources']]:
            path=Path(value)
            if not path.is_absolute() or not path.is_relative_to('/usr') or not path.exists():raise ValueError('Required application/resource unavailable')
            if path.is_file():hashes[value]=hashlib.sha256(path.read_bytes()).hexdigest()
            elif path.is_dir():
                entries=sorted(x for x in path.rglob('*') if x.is_file())
                if len(entries)>4096 or sum(x.stat().st_size for x in entries)>32*1024**2:raise ValueError('Resource exceeds review budget')
                hashes[value]=hashlib.sha256(json.dumps([(str(x.relative_to(path)),hashlib.sha256(x.read_bytes()).hexdigest()) for x in entries]).encode()).hexdigest()
        if not os.access(p['executable'],os.X_OK):raise ValueError('Application executable unavailable')
        definition={**p,'id':name,'hashes':hashes}
        definition['revision']=hashlib.sha256(json.dumps(definition,sort_keys=True).encode()).hexdigest()
        return definition

    def grants(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def selected(self, name):
        p=self.definition(name);grant=self.grants().get(name)
        if not grant or grant['revision']!=p['revision']:raise PermissionError('Application needs current user enablement and validation')
        return p

    def discover(self):
        rows=[];grants=self.grants()
        for name in json.loads(self.catalogue.read_text()):
            try:
                p=self.definition(name);rows.append({**p,'enabled':grants.get(name,{}).get('revision')==p['revision'],'validation':grants.get(name,{}).get('validation')})
            except (OSError,ValueError) as error:rows.append({'id':name,'enabled':False,'available':False,'reason':str(error)[:160]})
        return {'applications':rows,'unlisted_executables':'unavailable; add a reviewed data profile, never model-supplied argv','no_installation':True,'scope_review_created':False,'next_step':'Discovery does not create a review. For a requested project task, call project_open with an enabled application and the native project/task IDs; only its needs_approval plus proposal_id means a review was presented.'}

    def propose(self, name):
        p=self.definition(name)
        return self.d.access.proposal({'kind':'visual_enable','profile':p,'path':p['name'],
            'content':'Habilitar este perfil instalado y probar su arranque/captura en una sesión desechable. No instala paquetes, no concede red, cuentas ni acceso al escritorio habitual.\n'+json.dumps(p,ensure_ascii=False,indent=2)})

    def enable(self, p):
        if self.definition(p['id'])!=p:raise PermissionError('Application changed after review')
        result=self.d.visual.launch({'application':p['id'],'scale':1,'outputs':1,'definition':p})
        scope=self.d.scopes[result['scope']]
        try:
            if result['geometry']['app_id']!=p['app_id']:raise PermissionError('Application did not expose the expected identity')
            grants=self.grants();grants[p['id']]={'revision':p['revision'],'validation':'actual private launch and window capture'}
            self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(grants));temporary.chmod(0o600);temporary.replace(self.path)
            return {'status':'applied','application':p['id'],'validated':True,'scope_closed':True}
        finally:self.d.release(scope)
