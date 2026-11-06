"""Controller evidence in native comments; native tasks/claims retain ownership."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets

from hermes_cli import kanban_db as kb
from projects.policy import digest, text


def safe_dispatch():
    from hermes_cli.kanban_db_dispatch import review_dispatch_enabled
    if review_dispatch_enabled():raise PermissionError('Review dispatch must be disabled; no work was admitted')


def key(config):
    path=Path(config['project_state'])/'argos-evidence.key'
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:pass
    else:
        with os.fdopen(fd,'wb') as stream:stream.write(secrets.token_bytes(32))
    return path.read_bytes()


def records(conn,task,config):
    result=[]
    for comment in kb.list_comments(conn,task.id):
        try:
            item=json.loads(comment.body);value=item['argos_evidence']
            signature=hmac.new(key(config),json.dumps(value,sort_keys=True).encode(),'sha256').hexdigest()
            if value['task_id']==task.id and value['project_id']==task.project_id and hmac.compare_digest(signature,item['signature']):
                result.append(value)
        except (ValueError,KeyError,TypeError):continue
    return result


def record(conn,task,config,kind,**fields):
    value={'kind':kind,'task_id':task.id,'project_id':task.project_id,**fields}
    signature=hmac.new(key(config),json.dumps(value,sort_keys=True).encode(),'sha256').hexdigest()
    kb.add_comment(conn,task.id,'argos-controller',json.dumps({'argos_evidence':value,'signature':signature},sort_keys=True))
    return value


def permit(conn,task,config,*,claimed=False):
    """A prior run consumes its admission, including failed/ambiguous spawns."""
    safe_dispatch()
    runs=kb.list_runs(conn,task.id)
    if claimed:
        if task.status!='running' or not runs or runs[-1].id!=task.current_run_id:raise PermissionError('Claim is no longer current')
        runs=runs[:-1]
    if not runs:return
    grants=[v for v in records(conn,task,config) if v['kind']=='retry' and v.get('after_run')==runs[-1].id]
    if not grants or grants[-1].get('number',99)>2:
        raise PermissionError('Prior attempt requires inspected effects and an explicit user retry')
    if task.assignee!='argos-capabilities' and grants[-1].get('inspected_files')!=fingerprint(task.workspace_path):
        raise PermissionError('Artifacts changed after retry authorization; inspect before another grant')


def fingerprint(root):
    """Bounded regular-file snapshot; never follow links or read private hidden files."""
    from maintenance.controller import read_regular
    root=Path(root);items={};total=0
    for directory,folders,files in os.walk(root,followlinks=False):
        folders[:]=sorted(x for x in folders if not x.startswith('.') and x!='__pycache__')
        if any((Path(directory)/x).is_symlink() for x in folders):raise PermissionError('Linked directories are not verifiable')
        for name in sorted(files):
            if name.startswith('.') or name.endswith('.pyc'):continue
            path=Path(directory)/name
            content=read_regular(path,8*1024*1024);total+=len(content)
            if len(items)>=512 or total>64*1024*1024:raise ValueError('Verification scope exceeds its file budget')
            items[str(path.relative_to(root))]=hashlib.sha256(content).hexdigest()
    return items


def act(adapter,conn,project,task,args,authorized):
    if not authorized:raise PermissionError('Only the trusted user surface can decide task lifecycle actions')
    adapter.compare(project,args.get('expected_revision'))
    current=adapter.task_view(conn,task)
    if args.get('task_revision')!=current['revision']:raise ValueError('Stale task revision; refresh before acting')
    operation=args['operation'];runs=kb.list_runs(conn,task.id);last=runs[-1].id if runs else None
    auxiliary=task.assignee=='argos-capabilities'
    if auxiliary and operation in {'verify','accept','decide'}:raise PermissionError('Use explicit semantic acceptance for a local model draft')
    if operation in {'verify','accept'} and any(t.current_run_id for t in kb.list_tasks(conn)):
        raise ValueError('Wait until Engineering stops writing this workspace before verification or acceptance')
    if operation=='decide':
        body=json.loads(task.body.split('\n',1)[1])
        if body.get('kind')!='decision' or task.status in {'done','archived','running'}:raise ValueError('Not a pending user decision')
        reason=text(args.get('reason'),800)
        if not kb.complete_task(conn,task.id,result=reason):raise ValueError('Decision dependencies are not satisfied')
        record(conn,kb.get_task(conn,task.id),adapter.config,'decision',answer=reason)
    elif operation=='accept_semantic':
        if not auxiliary or task.status!='review' or task.current_run_id:raise ValueError('Not a settled auxiliary draft')
        reason=text(args.get('reason'),800)
        previous=kb.latest_run(conn,task.id).metadata or {}
        if not kb.complete_task(conn,task.id,result='User accepted the draft semantics',metadata=previous):raise ValueError('Dependencies changed')
        record(conn,kb.get_task(conn,task.id),adapter.config,'semantic_acceptance',answer=reason,run_id=last)
    elif operation=='cancel':
        if task.status in {'done','archived'}:raise ValueError('Task is already terminal')
        kb.archive_task(conn,task.id)
    elif operation=='retry':
        safe_dispatch()
        if task.status not in {'review','blocked'} or task.current_run_id:raise ValueError('Only a settled review or blocked task can be retried')
        if not runs:raise ValueError('Use Start for a task with no attempts')
        reason=text(args.get('reason'),800)
        history=[v for v in records(conn,task,adapter.config) if v['kind']=='retry']
        if len(history)>=2:raise PermissionError('Two explicit retries exhausted; create a reviewed follow-up')
        record(conn,task,adapter.config,'retry',after_run=last,number=len(history)+1,reason=reason,
               inspected_files=fingerprint(project.primary_path))
        if task.status=='review':kb.reopen_review_task(conn,task.id)
        else:kb.unblock_task(conn,task.id)
        # This authorizes one attempt, but does not start it. Start remains explicit.
    elif operation=='reject':
        if task.status!='review':raise ValueError('Only a review can be rejected')
        reason=text(args.get('reason'),800)
        kb.reopen_review_task(conn,task.id)
        kb.block_task(conn,task.id,reason=reason,kind='needs_input')
        record(conn,kb.get_task(conn,task.id),adapter.config,'rejected',after_run=last,reason=reason)
    elif operation=='verify':
        if task.status!='review' or task.current_run_id:raise ValueError('Wait for a settled review before verifying')
        from projects.verification import verify
        evidence=verify(project.primary_path,args.get('profile','python_unittest'))
        record(conn,task,adapter.config,'verification',run_id=last,**evidence)
    elif operation=='accept':
        if task.status!='review' or task.current_run_id:raise ValueError('Task is not awaiting acceptance')
        evidence=[v for v in records(conn,task,adapter.config) if v['kind']=='verification' and v.get('run_id')==last]
        if not evidence or not evidence[-1].get('passed'):raise PermissionError('Independent verification must pass before acceptance')
        if evidence[-1]['files']!=fingerprint(project.primary_path):raise PermissionError('Artifacts changed after verification; verify again')
        if not kb.complete_task(conn,task.id,result='User accepted independently verified artifacts',metadata={'verification':evidence[-1]}):
            raise ValueError('Native acceptance refused; inspect dependencies')
        record(conn,kb.get_task(conn,task.id),adapter.config,'accepted',verified_run=last)
    else:raise ValueError('Unsupported lifecycle action')
    return adapter.task_view(conn,kb.get_task(conn,task.id),True)
