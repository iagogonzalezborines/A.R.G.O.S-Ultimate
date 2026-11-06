"""Capability adapter over native tasks/claims/dispatcher; no scheduler or task database."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

P=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(P),str(P/'source')]
from hermes_cli import projects_db as projects,kanban_db as kb
from hermes_cli.kanban_db_connect import connect_closing
from hermes_cli.kanban_db_dispatch import dispatch_once
from projects.native import Adapter,revision
from projects.policy import digest,text
from maintenance.controller import clean
from adaptive.capabilities import REGISTRY,catalog,select,execute,validate_payload
from adaptive.local import Local

BOARD='argos-capabilities'
PROFILE='argos-capabilities'


def data(task):
    value=json.loads(task.body)
    if value.get('format')!='argos-capability-v1' or value['capability'] not in REGISTRY:raise PermissionError('Not an ARGOS capability task')
    return value


def view(conn,task):
    value=data(task)
    result={'id':task.id,'project_id':task.project_id,'title':task.title,'capability':value['capability'],
            'status':task.status,'parents':kb.parent_ids(conn,task.id),'run_id':task.current_run_id}
    result['revision']=digest([task.body,task.status,task.current_run_id,result['parents'],[r.id for r in kb.list_runs(conn,task.id)],[e.id for e in kb.list_events(conn,task.id)]])
    result['runs']=[{'id':r.id,'kind':'execution' if r.claim_lock else 'state_transition','status':r.status,'outcome':r.outcome,'started_at':r.started_at,'ended_at':r.ended_at,'summary':clean(r.summary or '')[:1000],'metadata':clean(r.metadata or {})} for r in kb.list_runs(conn,task.id)[-5:]]
    return result


def selected_task(conn,project,ident):
    task=kb.get_task(conn,text(ident,80))
    if not task or task.project_id!=project.id or task.workspace_path!=project.primary_path or task.assignee!=PROFILE:
        raise PermissionError('Task belongs to another scope')
    data(task)
    return task


def setup():
    from hermes_cli.profiles import create_profile,profile_exists
    if not profile_exists(PROFILE):create_profile(PROFILE,no_alias=True,no_skills=True)
    kb.create_board(BOARD,name='ARGOS bounded capabilities')


def tick(conn,config_path,config):
    from hermes_cli.kanban_db_dispatch import review_dispatch_enabled
    if review_dispatch_enabled():raise PermissionError('Disable native review dispatch before enabling adaptive experiments')
    # Recovery parks an interrupted task; it never replays even a read-only model call.
    for task in kb.list_tasks(conn):
        if task.status in {'ready','running'} and task.current_run_id is None and kb.list_runs(conn,task.id):
            from projects.lifecycle import permit
            try:permit(conn,task,config)
            except PermissionError:kb.block_task(conn,task.id,reason='Prior attempt requires inspection; no automatic replay',kind='needs_input')
    # Native global board cap is shared by every project/session of this adapter.
    # Interrupted effects never retry automatically: each auxiliary task has max_retries=0.
    def spawn(task,workspace,board=None):
        from projects.lifecycle import safe_dispatch
        safe_dispatch()
        data(task)
        from projects.lifecycle import permit
        permit(conn,task,config,claimed=True)
        child=subprocess.Popen([str(P/'env/bin/python'),str(Path(__file__)),str(config_path),task.id,str(task.current_run_id)],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            env=dict(os.environ),start_new_session=True)
        return child.pid
    enough=True
    if Path('/proc/meminfo').exists():
        values=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
        enough=int(values['MemAvailable'].split()[0])*1024>=config['adaptive'].get('min_available_bytes',2*1024**3)
    if not enough and not any(t.current_run_id for t in kb.list_tasks(conn)):
        try:Local(config['adaptive']['local']).release()
        except (OSError,ValueError,PermissionError,KeyError):pass
    # Hermes max_in_progress is host-wide, including Engineering on other boards.
    dispatch_once(conn,board=BOARD,spawn_fn=spawn,max_spawn=1 if enough else 0,max_in_progress=2,
                  max_in_progress_per_profile=1,failure_limit=1)
    return {'admission':'available' if enough else 'waiting_for_memory'}


def submit(conn,project,args):
    payload=args.get('payload',{})
    if not isinstance(payload,dict) or set(payload)-{'text','format'}:raise ValueError('Unsupported payload')
    kind=select(args.get('capability'),payload)
    payload=validate_payload(kind,payload)
    parents=args.get('parents',[])
    if not isinstance(parents,list) or len(parents)>8:raise ValueError('Too many dependencies')
    for parent in parents:selected_task(conn,project,parent)
    value={'format':'argos-capability-v1','capability':kind,'payload':payload,'project_revision':revision(project)}
    ident=kb.create_task(conn,title=text(args.get('title',kind),160),body=json.dumps(value,sort_keys=True),
        assignee=PROFILE,created_by='argos-broker',project_id=project.id,workspace_kind='dir',workspace_path=project.primary_path,
        board=BOARD,parents=parents,idempotency_key='adaptive-'+digest([project.id,value,sorted(parents)]),
        max_runtime_seconds=120,max_retries=0,completion_contract='local-only')
    return selected_task(conn,project,ident)


def request(adapter,args,config_path):
    config=adapter.config
    if config.get('adaptive_enabled') is not True:raise PermissionError('Adaptive experiments are disabled')
    operation=args.get('operation')
    if operation not in {'catalog','submit','status','canvas','cancel','tick','workflow'}:raise ValueError('Unsupported adaptive operation')
    if operation=='catalog':return {'capabilities':catalog(config['adaptive'])}
    if operation not in {'status','canvas','cancel'}:
        from hermes_cli.kanban_db_dispatch import review_dispatch_enabled
        if review_dispatch_enabled():raise PermissionError('Native review dispatch must be disabled')
    with projects.connect_closing() as registry:
        project,candidates=adapter.selected(registry,args.get('project',''))
        if not project:return {'needs_selection':True,'projects':candidates}
        if operation not in {'status','canvas'}:adapter.compare(project,args.get('expected_revision'))
        setup()
        with connect_closing(board=BOARD) as conn:
            if operation=='submit':
                task=submit(conn,project,args);admission=tick(conn,config_path,config)
                return {**view(conn,selected_task(conn,project,task.id)),**admission}
            if operation=='cancel':
                task=selected_task(conn,project,args.get('task_id'))
                if args.get('task_revision')!=view(conn,task)['revision']:raise ValueError('Stale capability task revision')
                kb.archive_task(conn,task.id)
                return view(conn,selected_task(conn,project,task.id))
            if operation=='tick':tick(conn,config_path,config)
            if operation=='workflow':
                from adaptive.workflow import validate
                nodes=validate(args.get('nodes'))
                ids={}
                for node in nodes:
                    task=submit(conn,project,{'title':node['title'],'capability':node['capability'],
                        'payload':node.get('payload',{}),'parents':[ids[p] for p in node['parents']]})
                    ids[node['id']]=task.id
                tick(conn,config_path,config)
                return {'project_id':project.id,'tasks':ids,'source':'native Kanban'}
            if operation not in {'status','tick','canvas'}:raise ValueError('Unsupported adaptive operation')
            # The native list API has no project filter. Select scoped IDs before loading bodies/evidence.
            ids=conn.execute("SELECT id FROM tasks WHERE project_id=? AND assignee=? AND status!='archived' ORDER BY created_at DESC,id LIMIT 201",
                             (project.id,PROFILE)).fetchall()
            truncated=len(ids)>200
            tasks=[view(conn,selected_task(conn,project,row['id'])) for row in ids[:200]]
            if operation=='canvas':
                from adaptive.workflow import canvas
                if truncated:raise ValueError('Project exceeds the bounded Canvas view; inspect native Kanban')
                return canvas(tasks)
            return {'tasks':tasks,'truncated':truncated,'source':'native Kanban'}


def worker(config_path,ident,run_id):
    config=json.loads(Path(config_path).read_text());adapter=Adapter(config)
    if config.get('adaptive_enabled') is not True:raise PermissionError('Adaptive experiments disabled')
    # Serialize local resource ownership across cancellation/reconciliation, not only task states.
    with (Path(config['project_state'])/'adaptive-resource.lock').open('a') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX)
        with projects.connect_closing() as registry,connect_closing(board=BOARD) as conn:
            task=kb.get_task(conn,ident);value=data(task)
            project=projects.get_project(registry,task.project_id);adapter.authorize(project)
            selected_task(conn,project,ident)
            if task.status!='running' or task.current_run_id!=run_id:return
            from projects.lifecycle import safe_dispatch
            safe_dispatch()
            from projects.lifecycle import permit
            permit(conn,task,config,claimed=True)
            def interrupt(*_):raise InterruptedError('Capability execution interrupted')
            signal.signal(signal.SIGTERM,interrupt);signal.signal(signal.SIGALRM,interrupt);signal.alarm(115)
            started=time.monotonic()
            try:
                if value['project_revision']!=revision(project):raise ValueError('Project requirements changed before execution')
                parents=[]
                for parent_id in kb.parent_ids(conn,ident):
                    parent=selected_task(conn,project,parent_id)
                    if parent.status!='done':raise ValueError('Dependency not verified')
                    parents.append(kb.latest_run(conn,parent_id).metadata['result'])
                result,metrics=execute(value['capability'],value['payload'],project,parents,config['adaptive'])
                metadata={'result':clean(result),'verification':metrics,'wall_seconds':time.monotonic()-started,
                          'capability':value['capability'],'project_revision':value['project_revision']}
                # A schema check does not certify model semantics; keep model outputs in review.
                if value['capability']=='local.extract':
                    kb.request_review(conn,ident,summary='Structured model result needs semantic review',metadata=metadata,expected_run_id=run_id)
                else:
                    kb.complete_task(conn,ident,result='Deterministic bounded capability verified',metadata=metadata,expected_run_id=run_id)
            except Exception as error:
                kb.block_task(conn,ident,reason=clean(str(error))[:300],kind='needs_input',expected_run_id=run_id)
            finally:
                signal.alarm(0)
                if value['capability']=='local.extract':
                    # Normal idle expiry remains Ollama's responsibility; release on cancellation/error.
                    current=kb.get_task(conn,ident)
                    if current.status!='review':
                        try:Local(config['adaptive']['local']).release()
                        except OSError:pass
    # Completion event advances the native queue once; no separate polling daemon.
    lock=Path(config['project_state'])/'argos-adapter.lock'
    with lock.open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        with connect_closing(board=BOARD) as conn:tick(conn,config_path,config)


if __name__=='__main__':worker(sys.argv[1],sys.argv[2],int(sys.argv[3]))
