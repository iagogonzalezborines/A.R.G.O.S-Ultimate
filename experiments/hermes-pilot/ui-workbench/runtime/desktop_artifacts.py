"""Thin consent/UI bridge to native project artifact evidence and Files exports."""
import json
from pathlib import Path
import secrets


class Artifacts:
    def __init__(self,desktop):self.d=desktop

    def native(self, args):
        if not self.d.projects or not self.d.projects.enabled:raise PermissionError('Persistent Projects is unavailable')
        return self.d.projects.native({'action':'desktop_artifacts',**args},authorized=True)

    def context(self, args):
        return self.native({'operation':'context','project':args.get('project'),'task_id':args.get('task_id')})

    def bound(self, args, context):
        return {'project':context['project']['id'],'task_id':context['task']['id'],
                'expected_revision':context['project']['revision'],'task_revision':context['task']['revision']}

    def propose_session(self,args):
        context=self.context(args);p=self.d.profiles.selected(args.get('application'))
        retained=next((s for s in context['sessions'] if s['session_id']==args.get('session_id')),None)
        if args.get('session_id') and not retained:raise PermissionError('Session not associated with this task')
        if retained and (retained['profile']!=p['id'] or retained['profile_revision']!=p['revision']):raise PermissionError('Resume requires the original reviewed application revision')
        imports=args.get('imports',[])
        if not isinstance(imports,list) or len(imports)>8:raise ValueError('At most eight explicit imports')
        copies=[];import_bytes=0
        for item in imports:
            if not isinstance(item,dict) or set(item)!={'path','name'}:raise ValueError('Import needs source path and local basename')
            value=self.d.files.read(item['path'],preview=True)
            if not value.get('editable') or value.get('truncated'):raise PermissionError('Import must be a small authorized UTF-8 file')
            import_bytes+=len(json.dumps(value['text']).encode())
            if import_bytes>28000:raise ValueError('Imports exceed the 28 KB serialized text budget')
            if not value['text'].strip():raise ValueError('Choose a nonempty document to import')
            copies.append({'source':value['path'],'name':item['name'],'sha256':value['sha256']})
        if retained and imports:raise ValueError('Resume does not import or overwrite existing work')
        output=retained['output_directory'] if retained else args.get('output_directory','docs')
        # Validate names/format before the review, without creating any workspace.
        import re
        for path in [output,*[i['name'] for i in copies]]:
            if not isinstance(path,str) or len(path)>240 or Path(path).is_absolute() or any(x.startswith('.') or not re.fullmatch(r'[\w .()-]+',x) for x in Path(path).parts):raise ValueError('Use safe relative paths')
        if any(len(Path(i['name']).parts)!=1 for i in copies):raise ValueError('Use import basenames')
        session=retained['session_id'] if retained else secrets.token_hex(12)
        return self.d.access.proposal({'kind':'desktop_project','profile':p,'bound':self.bound(args,context),'session_id':session,
            'imports':copies,'retained':bool(retained),'output_directory':output,'path':context['project']['path']+'/'+output,
            'content':('Reabrir' if retained else 'Abrir')+' '+p['name']+' para «'+context['project']['name']+'» / '+context['task']['title']+'.\n'
            'Solo workspace privado sin red, cuentas ni entrada en tu escritorio. General puede interpretar las capturas mediante Codex. Se conservarán los archivos guardados para recuperación; el texto sin guardar depende de la aplicación.\n'
            'Crear si falta la carpeta de entrega: '+output+'. La exportación de archivos exige otra revisión concreta.\nImportaciones: '+json.dumps(copies,ensure_ascii=False)})

    def launch(self,p):
        current=self.context(p['bound'])
        if self.bound(p['bound'],current)!=p['bound']:raise PermissionError('Project/task changed since session review')
        definition=self.d.profiles.selected(p['profile']['id'])
        if definition!=p['profile']:raise PermissionError('Profile changed since consent')
        copies=[]
        for item in p['imports']:
            value=self.d.files.read(item['source'],preview=True)
            if value.get('sha256')!=item['sha256']:raise PermissionError('Import changed since consent')
            copies.append({**item,'text':value['text']})
        if p['retained']:
            session=next(s for s in current['sessions'] if s['session_id']==p['session_id'])
            if session['profile_revision']!=definition['revision']:raise PermissionError('Retained application revision changed')
            self.native({'operation':'resume',**p['bound'],'session_id':session['session_id']})
            work=Path(self.d.projects.config['project_state'])/'desktop-artifacts'/session['session_id']/'work'
        else:
            session=self.native({'operation':'session',**p['bound'],'session_id':p['session_id'],'profile':definition['id'],
                'profile_revision':definition['revision'],'imports':copies,'seed':definition['seed'],'output_directory':p['output_directory']})
            work=Path(session['workspace'])
        return self.d.visual.launch({'application':definition['id'],'definition':definition,'scale':1,'outputs':1,
            'workspace':str(work),'project':p['bound']['project'],'task_id':p['bound']['task_id'],'session_id':p['session_id']})

    def inspect(self,args):
        context=self.context(args)
        if not args.get('session_id'):return context
        return self.native({'operation':'scan',**self.bound(args,context),'session_id':args['session_id']})

    def propose_export(self,args):
        if self.d.active:raise RuntimeError('Wait for the current input batch before reviewing artifacts')
        context=self.context(args)
        request={'operation':'prepare_export',**self.bound(args,context),**{k:args.get(k) for k in ('session_id','path','sha256','destination')}}
        prepared=self.native(request)
        if prepared.get('status')=='already_exported':return prepared
        bound={**self.bound(args,context),'task_revision':prepared['task_revision']}
        result=self.d.access.proposal({'kind':'desktop_export','bound':bound,'prepared':prepared,'session_id':args['session_id'],
            'path':context['project']['path']+'/'+prepared['destination'],
            'content':'Exportar el archivo verificado de '+context['project']['name']+' / '+context['task']['title']+'.\nSHA-256: '+prepared['sha256']+
            '\nOrigen: '+prepared['path']+'\nDestino: '+prepared['destination']+'\nANTES:\n'+(prepared['previous_content'] or '(no existe)')+'\nDESPUÉS:\n'+prepared['content']})
        result['summary']='Revisar entrega de '+prepared['path']+' a '+prepared['destination']+'; contenido verificado, pendiente de aprobación.'
        return result

    def export(self,p):
        return self.native({'operation':'export',**p['bound'],'session_id':p['session_id'],
            **{k:p['prepared'][k] for k in ('path','sha256','destination','export_id','before','parent_identity')}})
