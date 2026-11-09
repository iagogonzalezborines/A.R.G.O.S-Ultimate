"""Desktop artifact records in native Kanban comments and controller-owned files.

No project/task database here. The native adapter lock serializes this journal
with Engineering admission; exports use the existing Files validation/writer.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys

from hermes_cli import projects_db as projects, kanban_db as kb
from hermes_cli.kanban_db_connect import connect_closing
from projects.lifecycle import record, records
from projects.policy import digest, text
from maintenance.controller import read_regular, clean


def relative(value):
    if not isinstance(value,str) or len(value)>240:raise ValueError('Use a short relative artifact path')
    path=Path(value)
    if path.is_absolute() or not path.parts or any(p in ('.','..') or p.startswith('.') or not re.fullmatch(r'[\w .()-]+',p) for p in path.parts):raise PermissionError('Unsafe artifact path')
    return path


def storage(config, session):
    if not isinstance(session,str) or not re.fullmatch('[a-f0-9]{24}',session):raise PermissionError('Unknown artifact session')
    root=Path(config['project_state'])/'desktop-artifacts'/session
    if any(p.is_symlink() for p in (root,*root.parents)):raise PermissionError('Linked artifact storage')
    return root


def file_text(path):
    path=Path(path)
    if not path.is_absolute() or '..' in path.parts:raise PermissionError('Invalid artifact path')
    if path.suffix.lower() not in {'.txt','.md','.csv','.json'}:raise PermissionError('Only reviewed UTF-8 document formats can be delivered')
    parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);os.close(parent);parent=nxt
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        try:
            before=os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>262144:raise PermissionError('Only bounded regular documents')
            data=os.read(fd,262145);after=os.fstat(fd);named=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
            identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            if identity(before)!=identity(after) or identity(after)!=identity(named) or len(data)!=after.st_size:raise PermissionError('Artifact changed while reading')
        finally:os.close(fd)
    finally:os.close(parent)
    return document(data,path.suffix)


def document(data,suffix):
    value=data.decode('utf-8')
    if '\x00' in value or clean(value)!=value or re.search(r'(?i)(api[_ -]?key|password|secret|token)\s*[:=]|-----BEGIN .*PRIVATE KEY',value):raise PermissionError('Credential-like or binary document excluded')
    if suffix.lower()=='.json':json.loads(value)
    return value,hashlib.sha256(data).hexdigest()


def authority(adapter,registry,args):
    project,_=adapter.selected(registry,text(args.get('project'),80))
    if not project:raise PermissionError('Select one authorized project')
    return project


def session_record(conn,task,config,session):
    found=[r for r in records(conn,task,config) if r['kind']=='desktop_session' and r['session_id']==session]
    if len(found)!=1:raise PermissionError('Session is outside this project/task')
    root=storage(config,session)/'work'
    st=root.stat()
    if root.is_symlink() or found[0].get('workspace_identity')!=[st.st_dev,st.st_ino]:raise PermissionError('Private workspace identity changed')
    return found[0]


def snapshot(conn,task,config,session):
    scope=session_record(conn,task,config,session);work=storage(config,session)/'work';result=[];seen=0
    for directory,folders,files in os.walk(work,followlinks=False):
        if any((Path(directory)/p).is_symlink() for p in folders):raise PermissionError('Linked workspace directory')
        folders[:]=[n for n in sorted(folders) if not n.startswith('.')]
        if len(Path(directory).relative_to(work).parts)>4:raise ValueError('Artifact tree exceeds depth budget')
        for name in sorted(files):
            seen+=1
            if seen>64:raise ValueError('Artifact tree exceeds file budget')
            path=Path(directory)/name;rel=str(path.relative_to(work))
            if name.startswith('.'):continue
            try:
                value,sha=file_text(path)
                initial=scope['initial'].get(rel)
                result.append({'path':rel,'sha256':sha,'bytes':len(value.encode()),'changed':initial!=sha,
                    'origin':'imported copy' if rel in scope['imports'] else 'private application workspace',
                    'text':value[:24000],'truncated':len(value)>24000})
            except (OSError,ValueError,UnicodeError) as error:result.append({'path':rel,'blocked':True,'reason':str(error)[:160]})
    return result


def files_for(project,work):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ui-workbench'))
    from runtime.workspace_broker import Files
    return Files({'Project':Path(project.primary_path),'Session':work})


def directory_identity(files,path):
    fd,_,_=files.parent(str(path))
    try:
        s=os.fstat(fd);return [s.st_dev,s.st_ino]
    finally:os.close(fd)


def committed(conn,task,config):
    return [r for r in records(conn,task,config) if r['kind']=='desktop_exported']


def reconcile(conn,task,config,project):
    history=records(conn,task,config);done={r['export_id'] for r in history if r['kind']=='desktop_exported'}
    for intent in [r for r in history if r['kind']=='desktop_export_intent' and r['export_id'] not in done]:
        # Recovery observes an already-published approved snapshot; never replays a write.
        try:
            path=Path(project.primary_path)/relative(intent['destination'])
            files=files_for(project,storage(config,intent['session_id'])/'work')
            if directory_identity(files,path)!=intent['parent_identity']:continue
            value,sha=file_text(path)
            if sha==intent['sha256']:
                record(conn,task,config,'desktop_exported',**{k:v for k,v in intent.items() if k not in ('kind','task_id','project_id')},recovered=True,
                    verification='Approved snapshot matches current destination; recovered without writing')
        except (OSError,ValueError,PermissionError):continue


def request(adapter,args,authorized):
    if not authorized:raise PermissionError('Desktop artifact operations require the controller, never direct model authority')
    allowed={'action','operation','project','task_id','expected_revision','task_revision','session_id','profile','profile_revision','imports','output_directory','path','sha256','destination','export_id','before','parent_identity','seed'}
    if set(args)-allowed:raise ValueError('Unexpected desktop artifact fields')
    op=args.get('operation');config=adapter.config
    with projects.connect_closing() as registry:
        project=authority(adapter,registry,args)
        with connect_closing(board=project.board_slug) as conn:
            task=adapter.task(conn,project,args.get('task_id'))
            body=json.loads(task.body.split('\n',1)[1])
            if body.get('kind')!='desktop':raise PermissionError('Use a native desktop task, not an Engineering execution')
            if op in ('context','list'):
                reconcile(conn,task,config,project)
                history=records(conn,task,config)
                sessions=[r for r in history if r['kind']=='desktop_session']
                return {'project':adapter.view(project),'task':adapter.task_view(conn,kb.get_task(conn,task.id),True),'sessions':sessions,'exports':committed(conn,task,config)}
            adapter.compare(project,args.get('expected_revision'))
            if op!='scan' and (task.status in ('archived','done') or task.current_run_id):raise PermissionError('Task is terminal or owned by an execution')
            if args.get('task_revision')!=adapter.task_view(conn,task)['revision']:raise ValueError('Stale desktop task; refresh its context')
            if op!='scan':
                if body['project_revision']!=adapter.view(project)['revision']:raise ValueError('Task uses an older brief; revise the task before desktop work')
                if kb.unsatisfied_parents(conn,task.id):raise PermissionError('Native task dependencies are not satisfied')
            if op=='session':
                session=args['session_id'];root=storage(config,session)
                prior=[r for r in records(conn,task,config) if r['kind']=='desktop_session' and r['session_id']==session]
                if prior:return prior[0]
                if len([r for r in records(conn,task,config) if r['kind']=='desktop_session'])>=8:raise ValueError('Review existing retained workspaces first')
                output=relative(args.get('output_directory','docs'))
                if len(output.parts)>3:raise ValueError('Output folder too deep')
                imports=args.get('imports',[]);seed=args.get('seed',{})
                if not isinstance(imports,list) or len(imports)>8 or len(json.dumps(imports).encode())>32000:raise ValueError('At most eight explicit imports')
                if not isinstance(seed,dict) or len(seed)>8:raise ValueError('Invalid seed files')
                prepared={};initial={};sources={}
                for name,content in seed.items():
                    name=relative(name)
                    if len(name.parts)!=1 or not isinstance(content,str) or len(content)>4096:raise ValueError('Invalid seed document')
                    document(content.encode(),name.suffix);prepared[str(name)]=content
                for item in imports:
                    if not isinstance(item,dict) or set(item)!={'name','text','sha256','source'}:raise ValueError('Invalid import')
                    name=relative(item['name'])
                    if len(name.parts)!=1 or str(name) in sources:raise ValueError('Import names must be unique basenames')
                    content=item['text'].encode();_,sha=document(content,name.suffix)
                    if len(content)>262144 or sha!=item['sha256']:raise PermissionError('Import fingerprint changed')
                    prepared[str(name)]=item['text'];sources[str(name)]={'source':item['source'],'sha256':sha}
                if any(Path(name).suffix.lower() not in {'.md','.txt','.csv','.json'} for name in prepared):raise PermissionError('Unsupported import format')
                files=files_for(project,root/'work');current=Path(project.primary_path)
                # Folder creation is explicitly included in the trusted session review.
                for part in output.parts:
                    current/=part
                    try:fd,_=files.directory(str(current));os.close(fd)
                    except FileNotFoundError:
                        p=files.propose('mkdir',str(current));files.confirm(p['id'],True)
                root.mkdir(parents=True,exist_ok=False,mode=0o700);work=root/'work';work.mkdir(mode=0o700);(root/'verified').mkdir(mode=0o700)
                for name,content in prepared.items():
                    (work/name).write_text(content);_,initial[name]=file_text(work/name)
                value=record(conn,task,config,'desktop_session',session_id=session,profile=text(args['profile'],80),profile_revision=text(args['profile_revision'],80),imports=sources,initial=initial,workspace_identity=[work.stat().st_dev,work.stat().st_ino],output_directory=str(output))
                return {**value,'workspace':str(work)}
            session=args.get('session_id');scope=session_record(conn,task,config,session);root=storage(config,session);work=root/'work'
            if op=='resume':
                snapshot(conn,task,config,session)
                return {'workspace':str(work),'session_id':session}
            if op=='scan':return {'session_id':session,'artifacts':snapshot(conn,task,config,session),'profile':scope['profile']}
            if op not in ('prepare_export','export'):raise ValueError('Unknown desktop artifact operation')
            path=relative(args.get('path'));value,sha=file_text(work/path)
            if not value.strip():raise PermissionError('Empty documents are not deliverable artifacts')
            if args.get('sha256')!=sha:raise PermissionError('Artifact changed since observation')
            destination=relative(args.get('destination'))
            if destination.parent!=Path(scope['output_directory']):raise PermissionError('Export is outside the approved project directory')
            if destination.suffix.lower() not in {'.md','.txt','.csv','.json'}:raise PermissionError('Unsupported export format')
            if destination.suffix.lower()=='.json':json.loads(value)
            target=Path(project.primary_path)/destination;files=files_for(project,work);files.writable(str(target))
            reconcile(conn,task,config,project)
            for receipt in committed(conn,task,config):
                if all(receipt[k]==v for k,v in [('session_id',session),('path',str(path)),('sha256',sha),('destination',str(destination))]):
                    if files.fingerprint(str(target))!=sha:raise PermissionError('Previously exported destination changed')
                    return {'status':'already_exported','receipt':receipt}
            if any(t.current_run_id for t in kb.list_tasks(conn)):raise PermissionError('Wait for project writers before export')
            before=files.fingerprint(str(target));parent=directory_identity(files,target)
            if op=='prepare_export':
                frozen=root/'verified'/sha
                if not frozen.exists():
                    fd=os.open(frozen,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                    with os.fdopen(fd,'wb') as stream:stream.write(value.encode());stream.flush();os.fsync(stream.fileno())
                # Native evidence records hashes, not document contents.
                export_id=secrets.token_hex(12)
                record(conn,task,config,'desktop_verified',export_id=export_id,session_id=session,path=str(path),sha256=sha,bytes=len(value.encode()),destination=str(destination),before=before,parent_identity=parent,
                       profile=scope['profile'],verification='Bounded regular UTF-8 file observed in authorized private application workspace')
                return {'export_id':export_id,'before':before,'parent_identity':parent,'sha256':sha,'path':str(path),'destination':str(destination),
                        'content':value,'previous_content':file_text(target)[0] if before else '',
                        'task_revision':adapter.task_view(conn,kb.get_task(conn,task.id))['revision']}
            verification=[r for r in records(conn,task,config) if r['kind']=='desktop_verified' and r['export_id']==args.get('export_id')]
            if len(verification)!=1:raise PermissionError('Missing verified export snapshot')
            verified=verification[0]
            for k in ('session_id','path','sha256','destination','before','parent_identity'):
                if verified[k]!=args.get(k):raise PermissionError('Export scope changed since review')
            if before!=verified['before'] or parent!=verified['parent_identity']:raise PermissionError('Destination changed since export review')
            content=read_regular(root/'verified'/sha,262144).decode()
            if hashlib.sha256(content.encode()).hexdigest()!=sha:raise PermissionError('Frozen artifact changed')
            # Write-ahead native comment covers crash between filesystem publication
            # and receipt. A later context read reconciles matching output only.
            record(conn,task,config,'desktop_export_intent',**{k:v for k,v in verified.items() if k not in ('kind','task_id','project_id','verification')})
            prepared=files.propose('write',str(target),content=content)
            if prepared['previous_sha256']!=before:raise PermissionError('Destination changed before commit')
            files.confirm(prepared['id'],True)
            if files.fingerprint(str(target))!=sha:raise PermissionError('Export verification failed; inspect without replay')
            receipt=record(conn,task,config,'desktop_exported',**{k:v for k,v in verified.items() if k not in ('kind','task_id','project_id','verification')},recovered=False,verification='Approved content atomically written and read back')
            return {'status':'applied','receipt':receipt,'path':str(target)}
