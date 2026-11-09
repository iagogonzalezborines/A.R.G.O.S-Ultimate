"""Bounded Project Map projection and user actions over the existing native records."""
import json
from pathlib import Path

from hermes_cli import projects_db as projects,kanban_db as kb
from hermes_cli.kanban_db_connect import connect_closing
from maintenance.controller import clean,read_regular
from projects.policy import digest,text


def board_task(adapter,project,ident):
    """Resolve against a fixed pair of native boards, never a caller-supplied DB path."""
    with connect_closing(board=project.board_slug) as conn:
        task=kb.get_task(conn,ident)
        if task:
            adapter.task(conn,project,ident)
            return project.board_slug
    if adapter.config.get('adaptive_enabled'):
        from adaptive.native import BOARD,selected_task
        with connect_closing(board=BOARD) as conn:selected_task(conn,project,ident)
        return BOARD
    raise PermissionError('Task not in this project')


def row(adapter,conn,task,board,fingerprints=None):
    result=adapter.task_view(conn,task,True)
    result['board']=board
    if task.assignee=='argos-capabilities':
        from adaptive.native import data,view
        result.update(capability=data(task)['capability'],kind='auxiliary',runs=view(conn,task)['runs'])
    else:
        body=json.loads(task.body.split('\n',1)[1]);result.update(kind=body.get('kind','engineering'),goal=body['goal'],criteria=body['verification'],capability='Codex Engineering')
        if body.get('specialized'):result['capability']=body['specialized']['id']+' · Codex Engineering'
        if result['kind']=='decision':result['capability']='User decision'
        if result['kind']=='desktop':result['capability']='Isolated desktop · reviewed artifacts'
    verified=[e for e in result['controller_evidence'] if e['kind']=='verification' and e.get('passed')]
    if verified and result['artifacts']:
        # Verification covers the whole authorized workspace, including other tasks.
        # Cache it once per map projection instead of rehashing for each task.
        from projects.lifecycle import fingerprint
        if fingerprints is None:fingerprints={}
        if task.workspace_path not in fingerprints:
            try:fingerprints[task.workspace_path]=fingerprint(task.workspace_path)
            except (OSError,ValueError,PermissionError):fingerprints[task.workspace_path]=None
        result['verification_snapshot_current']=fingerprints[task.workspace_path]==verified[-1]['files']
    if task.status=='blocked' and result['runs']:result['blocked_reason']=result['runs'][-1].get('summary') or result['last_failure']
    result['state']=('decision' if result['kind']=='decision' and task.status not in {'done','archived'} else
                     'queued' if task.status in {'todo','ready'} or task.status=='blocked' and not result['runs'] else task.status)
    if result['kind']=='desktop' and task.status not in {'done','archived'}:
        result['state']='artifacts_delivered' if any(e['kind']=='desktop_exported' for e in result['controller_evidence']) else 'desktop_pending'
    return result


def request(adapter,args,authorized=False):
    if adapter.config.get('project_map_enabled') is not True:raise PermissionError('Project Map is not enabled in this installation')
    action=args['action']
    with projects.connect_closing() as registry:
        project,candidates=adapter.selected(registry,args.get('project',''))
        if not project:return {'needs_selection':True,'projects':candidates}
        if action=='map_action':
            board=board_task(adapter,project,text(args.get('task_id'),80))
            with connect_closing(board=board) as conn:
                from projects.lifecycle import act
                result=act(adapter,conn,project,kb.get_task(conn,args['task_id']),args,authorized)
                if board!=project.board_slug and args['operation'] in {'accept_semantic','retry'}:
                    from adaptive.native import tick
                    import sys
                    tick(conn,sys.argv[1],adapter.config)
                return result
        if action=='artifact':
            board=board_task(adapter,project,text(args.get('task_id'),80))
            with connect_closing(board=board) as conn:
                task=kb.get_task(conn,args['task_id']);view=adapter.task_view(conn,task,True)
                path=text(args.get('path'),2048)
                if path not in {a['path'] for a in view['artifacts']}:raise PermissionError('Only an observed artifact of this task can be opened')
                file=Path(project.primary_path)/path
                import hashlib
                if any(a.get('origin')=='desktop' and a['path']==path for a in view['artifacts']):
                    from projects.desktop import file_text
                    value,_=file_text(file);content=value.encode()
                else:
                    from projects.artifact_preview import preview
                    return {**preview(file),'path':path}
                return {'path':path,'text':clean(content.decode('utf-8')),'sha256':hashlib.sha256(content).hexdigest()}
        boards=[project.board_slug]
        if adapter.config.get('adaptive_enabled'):
            from adaptive.native import BOARD
            if kb.board_exists(BOARD):boards.append(BOARD)
        tasks=[];truncated=False;fingerprints={}
        for board in boards:
            with connect_closing(board=board) as conn:
                ids=conn.execute('SELECT id FROM tasks WHERE project_id=? ORDER BY created_at,id LIMIT 101',(project.id,)).fetchall()
                truncated|=len(ids)>100
                tasks.extend(row(adapter,conn,kb.get_task(conn,r['id']),board,fingerprints) for r in ids[:100])
        result={'project':adapter.view(project),'tasks':tasks,'truncated':truncated,'source':'native Projects / Kanban'}
        result['revision']=digest(result)
        return result
