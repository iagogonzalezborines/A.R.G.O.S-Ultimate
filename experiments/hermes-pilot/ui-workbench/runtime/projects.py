"""Existing Broker approval boundary plus a native Hermes operation subprocess."""
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from .machine import PILOT, CONFIG_PATH
sys.path.insert(0, str(PILOT))
from projects.policy import proposal, digest
from pilot import environment


class Projects:
    def __init__(self, publish, *, config_path=CONFIG_PATH):
        self.publish = publish
        self.config_path = Path(config_path)
        self.config = json.loads(self.config_path.read_text()) if self.config_path.exists() else {}
        self.enabled = self.config.get('projects_enabled') is True
        self.pending = {}
        self.lock = threading.RLock()

    def native(self, arguments, *, authorized=False):
        env = environment()
        root = self.config['project_state']
        env.update(HERMES_HOME=root, HERMES_KANBAN_HOME=root, HOME=str(Path(root)/'home'), HERMES_QUIET='1')
        # This submits one native operation. Native workers/owner have independent lifetimes.
        result = subprocess.run([str(PILOT/'env/bin/python'), str(PILOT/'projects/native.py'), str(self.config_path)],
                    input=json.dumps({'arguments':arguments,'authorized':authorized}), env=env,
                    capture_output=True, text=True, timeout=55, cwd=PILOT)
        try:
            response = json.loads(result.stdout)
        except ValueError:
            raise RuntimeError('Native project operation did not return a result; inspect before retrying') from None
        if not response.get('ok'):
            kind = PermissionError if response.get('code') == 'PermissionError' else ValueError
            raise kind(response.get('error', 'Native project operation failed'))
        return response['result']

    def request(self, args, *, user=False):
        if not isinstance(args, dict):
            raise ValueError('Invalid project arguments')
        action = args.get('action')
        if action == 'availability' and set(args)=={'action'}:
            return {'enabled':self.enabled,'project_map':self.enabled and self.config.get('project_map_enabled') is True}
        if not self.enabled:
            raise PermissionError('Persistent Projects is disabled in this installation')
        if action == 'propose':
            prepared = proposal(args, self.config)
            existing = self.native({'action':'prepare',**{k:v for k,v in prepared.items() if k!='envelope'}})
            if existing.get('id'):
                return {'status':'registered','project':existing}
            ident = digest(prepared)[:24]
            with self.lock:
                self.pending[ident] = {'id':ident,'prepared':prepared,'expires':time.monotonic()+900}
                view = self.review(ident)
            self.publish({'type':'window.open','id':'project-scope-'+ident,'kind':'change',
                          'title':'Autorizar proyecto','text':json.dumps({'id':ident,'tool':'projects'})})
            return {**view, 'status':'awaiting_user_scope', 'created':False}
        if action in {'review','confirm'}:
            allowed = {'action','proposal_id'} | ({'approve'} if action=='confirm' else set())
            if set(args)-allowed or not user:
                raise PermissionError('Only the trusted user can review or approve a project scope')
            with self.lock:
                view = self.review(args.get('proposal_id'))
                if action == 'review':
                    return view
                if type(args.get('approve')) is not bool:
                    raise ValueError('Explicit approval choice required')
                if not args['approve']:
                    self.pending.pop(view['id'])
                    return {'status':'cancelled'}
                prepared = self.pending[view['id']]['prepared']
                arguments = {k:v for k,v in prepared.items() if k!='envelope'}
                result = self.native({'action':'create',**arguments},authorized=True)
                self.pending.pop(view['id'])
                return {'status':'applied','project':result}
        if action == 'create':
            raise PermissionError('Use a concrete scope proposal; the agent cannot authorize its own project')
        if action=='open_map':
            if set(args)-{'action','project'}:raise ValueError('Invalid map request')
            if self.config.get('project_map_enabled') is not True:raise PermissionError('Project Map is unavailable')
            project=args.get('project','')
            if project:project=self.native({'action':'resolve','project':project})['id']
            self.publish({'type':'window.open','id':'project-map','kind':'project','title':'Proyectos','text':project})
            return {'status':'requested','project':project}
        if action in {'lifecycle','map_action'}:
            if not user:raise PermissionError('Task decisions require the trusted user surface')
            return self.native(args,authorized=True)
        return self.native(args)

    def review(self, ident):
        item = self.pending.get(ident)
        if not item or item['expires'] < time.monotonic():
            raise ValueError('Project scope approval expired; prepare it again')
        return {'id':ident,'tool':'projects','operation':'project','path':item['prepared']['path'],
                'brief':item['prepared']['brief'],'name':item['prepared']['name'],
                'content':json.dumps(item['prepared'],ensure_ascii=False,indent=2)}
