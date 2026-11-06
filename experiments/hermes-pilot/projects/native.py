"""One bounded broker operation over native Hermes APIs; no daemon or secondary store."""
import contextlib
import fcntl
import hashlib
import json
from pathlib import Path
import sys

PILOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PILOT), str(PILOT/'source')]
from projects.policy import FORMAT, FIELDS, ENVELOPE, brief, digest, normalize, proposal, scope, text
from maintenance.controller import clean, read_regular
from hermes_cli import projects_db as projects, kanban_db as kanban
from hermes_cli.kanban_db_connect import connect_closing
from hermes_cli.kanban_db_dispatch import dispatch_once
from hermes_cli.sqlite_util import write_txn


def decode(project):
    try:
        data = json.loads(project.description or '')
        return data if data.get('format') == FORMAT else None
    except (ValueError, AttributeError):
        return None


def revision(project):
    return digest([project.description, project.primary_path, project.board_slug, project.name, project.archived])


class Adapter:
    def __init__(self, config):
        self.config = config
        from hermes_constants import get_hermes_home
        if Path(config['project_state']).resolve() != Path(get_hermes_home()).resolve():
            raise PermissionError('Wrong native project home')

    def authorize(self, project):
        data = decode(project) if project else None
        if not data or project.archived or data.get('envelope') != ENVELOPE:
            raise PermissionError('Project is not authorized through ARGOS')
        path = scope(project.primary_path, self.config)
        if data.get('state') == 'ready':
            stat = path.stat()
            if data.get('identity') != [stat.st_dev, stat.st_ino]:
                raise PermissionError('Authorized project folder was replaced')
        return data

    def selected(self, conn, query):
        rows = projects.list_projects(conn)
        found = [p for p in rows if decode(p) and (not query or normalize(query) in
                 [normalize(p.id), normalize(p.slug), normalize(p.name), *map(normalize, decode(p)['brief']['aliases'])])]
        if len(found) != 1:
            if query and not found:
                raise PermissionError('Project was not found in the authorized registry')
            return None, [{'id': p.id, 'name': p.name, 'slug': p.slug, 'created_at': p.created_at}
                          for p in found[-20:] if self.authorize(p)]
        self.authorize(found[0])
        return found[0], None

    def view(self, project):
        data = self.authorize(project)
        return {'id': project.id, 'name': project.name, 'slug': project.slug, 'path': project.primary_path,
                'board': project.board_slug, 'revision': revision(project), 'brief': data['brief'],
                'state': data['state'], 'scope': data['envelope'], 'data_is_untrusted': True}

    def compare(self, project, expected):
        if expected != revision(project):
            raise ValueError('Stale project revision; resolve the project again')

    def aliases(self, conn, own_id, aliases, name, slug):
        names = set(map(normalize, [name, slug, *aliases]))
        for other in projects.list_projects(conn):
            if other.id == own_id:
                continue
            data = decode(other)
            if names.intersection(map(normalize, [other.name, other.slug, *(data['brief']['aliases'] if data else [])])):
                raise ValueError('Project name or alias is already in use')

    def finish_provisioning(self, conn, project):
        data = self.authorize(project)
        if data['state'] == 'ready':
            return self.view(project)
        path = Path(project.primary_path)
        if not data['register']:
            path.mkdir(parents=True, exist_ok=True)
            marker = path/'.argos-project'
            if marker.exists():
                if read_regular(marker).decode() != project.id:
                    raise PermissionError('Folder belongs to another provisioning request')
            elif any(path.iterdir()):
                raise PermissionError('Provisioning destination acquired existing files')
            else:
                with marker.open('x') as stream:
                    stream.write(project.id)
        stat = path.stat()
        kanban.create_board(project.board_slug, name=project.name, project_id=project.id, default_workdir=str(path))
        data.update(state='ready', identity=[stat.st_dev, stat.st_ino])
        projects.update_project(conn, project.id, description=json.dumps(data, ensure_ascii=False))
        return self.view(projects.get_project(conn, project.id))

    def create(self, conn, args, authorized):
        prepared = proposal({k:v for k,v in args.items() if k != 'action'}, self.config)
        existing = projects.get_project(conn, prepared['slug'])
        if existing:
            data = self.authorize(existing)
            if data['creation_digest'] != digest(prepared):
                raise ValueError('Project already exists; resolve it instead of recreating or overwriting it')
            return self.finish_provisioning(conn, existing)
        if not authorized:
            return {'status':'needs_scope_approval'}
        path = Path(prepared['path'])
        if path.exists() and not prepared['register']:
            raise FileExistsError('Choose a new folder or explicitly register the existing one')
        for other in projects.list_projects(conn, include_archived=True):
            if other.primary_path:
                existing_path = Path(other.primary_path).resolve()
                if path == existing_path or path.is_relative_to(existing_path) or existing_path.is_relative_to(path):
                    raise PermissionError('Project scopes cannot overlap another registered project')
        self.aliases(conn, None, prepared['brief']['aliases'], prepared['name'], prepared['slug'])
        data = {'format': FORMAT, 'brief': prepared['brief'], 'envelope': ENVELOPE,
                'creation_digest': digest(prepared), 'register': prepared['register'], 'state': 'provisioning'}
        ident = projects.create_project(conn, name=prepared['name'], slug=prepared['slug'],
                primary_path=prepared['path'], board_slug='argos-'+prepared['slug'], description=json.dumps(data, ensure_ascii=False))
        return self.finish_provisioning(conn, projects.get_project(conn, ident))

    def update(self, conn, project, args):
        new_brief = brief(args['brief'])
        with write_txn(conn):
            current = projects.get_project(conn, project.id)
            self.compare(current, args.get('expected_revision'))
            data = self.authorize(current)
            self.aliases(conn, current.id, new_brief['aliases'], current.name, current.slug)
            if data['brief'] == new_brief:
                return self.view(current)
            data['brief'] = new_brief
            # Native update_project has no CAS parameter and opens its own transaction.
            # Update the native description under the same IMMEDIATE revision check; no new schema.
            conn.execute('UPDATE projects SET description=? WHERE id=?',
                         (json.dumps(data, ensure_ascii=False), current.id))
        return self.view(projects.get_project(conn, project.id))

    def task_view(self, conn, task, detailed=False):
        result = {k: getattr(task, k) for k in ['id', 'project_id', 'title', 'status', 'current_run_id', 'workspace_path', 'max_runtime_seconds']}
        result['last_failure']=clean(task.last_failure_error or '')[:1000]
        result['block_kind']=task.block_kind
        result['parents'] = kanban.parent_ids(conn, task.id)
        runs=kanban.list_runs(conn,task.id);events=kanban.list_events(conn,task.id)
        result['revision'] = digest([task.id, task.title, task.body, task.status, task.current_run_id, result['parents'],
                                     runs[-1].id if runs else None,events[-1].id if events else None])
        if not detailed:
            return result
        result['body'] = clean(task.body)
        result['runs'] = []
        for run in kanban.list_runs(conn, task.id)[-10:]:
            row = {k:getattr(run,k) for k in ['id','status','outcome','started_at','ended_at']}
            row['kind']='execution' if run.claim_lock else 'state_transition'
            row['summary'] = clean(run.summary or '')[:2000]
            public = {'artifacts','files','verification','tests','test_results','commands','exit_codes','tested_revision'}
            metadata = clean({k:v for k,v in (run.metadata or {}).items() if k in public})
            row['metadata_truncated'] = len(json.dumps(metadata)) > 8000
            row['metadata'] = {} if row['metadata_truncated'] else metadata
            result['runs'].append(row)
        result['comments'] = [clean({'author': c.author, 'text': c.body[:2000], 'at': c.created_at}) for c in kanban.list_comments(conn, task.id)[-10:]]
        result['events'] = [{'id': e.id, 'kind': e.kind, 'run_id': e.run_id, 'at': e.created_at} for e in kanban.list_events(conn, task.id)[-20:]]
        result['artifacts'] = []
        root = Path(task.workspace_path)
        observed=set();observed_bytes=0
        for run in reversed(result['runs']):
            artifacts = (run.get('metadata') or {}).get('artifacts', (run.get('metadata') or {}).get('files', []))
            if not isinstance(artifacts, list):
                continue
            for value in artifacts[:20]:
                value = value.get('path') if isinstance(value, dict) else value
                if not isinstance(value, str):
                    continue
                path = Path(value) if Path(value).is_absolute() else root/value
                try:
                    relative = path.relative_to(root)
                    if any(x.startswith('.') or x == '..' for x in relative.parts):
                        continue
                    if any(p.is_symlink() for p in (path, *path.parents)):
                        continue
                    if str(relative) in observed or len(observed)>=20:continue
                    content = read_regular(path, 8*1024*1024);observed_bytes+=len(content)
                    if observed_bytes>64*1024*1024:continue
                    observed.add(str(relative))
                    result['artifacts'].append({'path': str(relative), 'sha256_now': hashlib.sha256(content).hexdigest(),
                        'bytes': len(content), 'reported_by_run': run['id'], 'verification': 'current file observed; run claims are not independent test verification'})
                except (OSError, ValueError, PermissionError):
                    continue
        result['evidence_is_untrusted'] = True
        from projects.lifecycle import records
        result['controller_evidence']=records(conn,task,self.config)
        return result

    def task_body(self, project, args):
        title = text(args.get('title'), 160)
        goal = text(args.get('goal'), 3000)
        criteria = args.get('verification')
        if not isinstance(criteria, list) or not 1 <= len(criteria) <= 12:
            raise ValueError('Provide one to twelve concrete verification criteria')
        criteria = [text(x, 800) for x in criteria]
        content = {'project_revision': revision(project), 'brief': decode(project)['brief'],
                   'goal': goal, 'verification': criteria, 'scope': ENVELOPE}
        if args.get('kind','engineering') not in {'engineering','decision'}:raise ValueError('Unsupported native task kind')
        if args.get('kind')=='decision':content['kind']='decision'
        return title, 'ARGOS task brief (data, not authority):\n'+json.dumps(content, ensure_ascii=False)

    def task_create(self, conn, project, args):
        self.compare(project, args.get('expected_revision'))
        title, body = self.task_body(project, args)
        parents = args.get('parents', [])
        if not isinstance(parents, list) or len(parents) > 12:
            raise ValueError('Invalid dependencies')
        for parent in parents:
            self.task(conn, project, parent)
        key = 'argos-'+digest([project.id, normalize(title), body, sorted(parents)])
        ident = kanban.create_task(conn, title=title, body=body, assignee='engineering-'+project.id,
            created_by='argos-broker', workspace_kind='dir', workspace_path=project.primary_path,
            project_id=project.id, board=project.board_slug, parents=parents, idempotency_key=key,
            initial_status='blocked', max_runtime_seconds=300, max_retries=0, model_override='gpt-6-luna',
            provider_override='openai-codex', reasoning_effort='low', completion_contract='local-only')
        return self.task_view(conn, self.task(conn, project, ident), True)

    def task_update(self, conn, project, task, args):
        self.compare(project, args.get('expected_revision'))
        if args.get('task_revision') != self.task_view(conn,task)['revision']:
            raise ValueError('Stale task revision; inspect it again')
        if task.status not in {'blocked','todo','ready'} or kanban.list_runs(conn,task.id):
            raise PermissionError('Only unstarted tasks can be revised; retain execution history and create a follow-up')
        if args['action']=='dependency':
            parent = self.task(conn,project,args.get('parent_id'))
            operation = args.get('operation')
            if operation not in {'link','unlink'}:
                raise ValueError('Use link or unlink')
            present = parent.id in kanban.parent_ids(conn,task.id)
            if operation=='link' and not present:kanban.link_tasks(conn,parent.id,task.id)
            if operation=='unlink' and present:kanban.unlink_tasks(conn,parent.id,task.id)
        else:
            previous = json.loads(task.body.split('\n',1)[1])
            title,body = self.task_body(project, {'title':args.get('title',task.title),
                'kind':previous.get('kind','engineering'), 'goal':args.get('goal',previous['goal']), 'verification':args.get('verification',previous['verification'])})
            kanban.edit_task(conn,task.id,title=title,body=body,board=project.board_slug)
        return self.task_view(conn,self.task(conn,project,task.id),True)

    def task(self, conn, project, ident):
        task = kanban.get_task(conn, text(ident, 80))
        if not task or task.project_id != project.id or task.workspace_path != project.primary_path or task.assignee != 'engineering-'+project.id:
            raise PermissionError('Task is outside the authorized project scope')
        return task

    def dispatch(self, conn, registry, project, task, args):
        self.compare(project, args.get('expected_revision'))
        snapshot = self.task_view(conn, task)
        if task.current_run_id or task.status in {'review', 'done'}:
            return snapshot  # Lost reply/repeated dispatch never creates another attempt.
        if args.get('task_revision') != snapshot['revision']:
            raise ValueError('Stale task revision; inspect it again')
        if task.status not in {'blocked', 'ready', 'todo'}:
            raise ValueError('This native state is not dispatchable')
        content = json.loads(task.body.split('\n', 1)[1])
        if content.get('kind')=='decision':raise PermissionError('A decision must be answered by the user; it cannot dispatch Engineering')
        if content['project_revision'] != revision(project):
            raise ValueError('Task uses an older brief; revise the unstarted task or create a follow-up with current requirements')
        if kanban.unsatisfied_parents(conn, task.id):
            return {**snapshot, 'dispatch': 'waiting_for_dependencies'}
        from projects.lifecycle import permit
        try:permit(conn,task,self.config)
        except PermissionError:
            if task.status=='ready':kanban.block_task(conn,task.id,reason='Admission changed; inspect before retry',kind='needs_input')
            raise
        # One native writer across project profiles; all adapter operations share a process lock.
        for other in projects.list_projects(registry):
            if not decode(other):
                continue
            with connect_closing(board=other.board_slug) as other_conn:
                dispatch_once(other_conn, board=other.board_slug, max_spawn=0, failure_limit=2)
                if any(t.current_run_id for t in kanban.list_tasks(other_conn)):
                    return {**snapshot, 'dispatch': 'engineering_busy'}
        from projects.worker import provision
        from hermes_cli.gateway_runtime import ensure_gateway_runtime
        home = provision(project, self.config)
        ready = ensure_gateway_runtime(str(home), timeout=40, idle_exit=False)
        if ready.state != 'ready':
            raise RuntimeError('Native Engineering owner is unavailable; no task was dispatched')
        if task.status == 'blocked':
            kanban.unblock_task(conn, task.id)
        # No automatic replays: only this requested task may be ready when ticking its board.
        siblings = [t for t in kanban.list_tasks(conn) if t.id != task.id and t.status == 'ready']
        if siblings:
            raise ValueError('Another ready native task requires reconciliation before this dispatch')
        def guarded_spawn(claimed,workspace,board=None):
            from hermes_cli.kanban_db_dispatch import _default_spawn
            permit(conn,claimed,self.config,claimed=True)
            return _default_spawn(claimed,workspace,board=board)
        result = dispatch_once(conn, board=project.board_slug, spawn_fn=guarded_spawn, max_spawn=1, max_in_progress=2 if self.config.get('adaptive_enabled') is True else 1,
                               max_in_progress_per_profile=1, failure_limit=2)
        current = self.task_view(conn, self.task(conn, project, task.id), True)
        current['dispatch'] = 'native_claimed' if current['current_run_id'] else 'not_started'
        return current

    def request(self, args, authorized=False):
        action = args.get('action')
        if action in {'map','map_action','artifact'}:
            allowed={'action','project'}|({'task_id','path'} if action=='artifact' else {'task_id','expected_revision','task_revision','operation','reason','profile'} if action=='map_action' else set())
            if set(args)-allowed:raise ValueError('Unsupported Project Map fields')
            from projects.map import request
            return request(self,args,authorized)
        if action == 'adaptive':
            allowed={'action','operation','project','expected_revision','capability','title','payload','parents','task_id','task_revision','nodes'}
            if set(args)-allowed:raise ValueError('Unexpected adaptive fields')
            from adaptive.native import request
            return request(self,args,sys.argv[1])
        fields = {'create': {'name','slug','path','brief','register'}, 'prepare': {'name','slug','path','brief','register'}, 'list': set(), 'activity': set(), 'resolve': {'project'},
                  'update': {'project','expected_revision','brief'}, 'tasks': {'project'},
                  'task': {'project','task_id'},
                  'task_update': {'project','task_id','expected_revision','task_revision','title','goal','verification'},
                  'dependency': {'project','task_id','expected_revision','task_revision','parent_id','operation'}, 'task_create': {'project','expected_revision','title','goal','verification','parents','kind'},
                  'lifecycle': {'project','task_id','expected_revision','task_revision','operation','reason','profile'},
                  'dispatch': {'project','task_id','expected_revision','task_revision'}}
        if action not in fields or set(args)-({'action'}|fields[action]):
            raise ValueError('Unsupported project operation or fields')
        with projects.connect_closing() as conn:
            if action in {'create','prepare'}:
                return self.create(conn, args, authorized if action=='create' else False)
            if action == 'activity':
                active = []
                for item in projects.list_projects(conn):
                    if not decode(item):continue
                    self.authorize(item)
                    if decode(item)['state'] != 'ready':continue
                    with connect_closing(board=item.board_slug) as board:
                        dispatch_once(board,board=item.board_slug,max_spawn=0,failure_limit=2)
                        active.extend({**self.task_view(board,t),'project_name':item.name} for t in kanban.list_tasks(board,status='running') if t.project_id==item.id)
                return {'tasks':active[:20],'truncated':len(active)>20,'source':'native claims and runs'}
            if action == 'list':
                return {'projects': [dict(id=p.id,name=p.name,slug=p.slug,aliases=decode(p)['brief']['aliases'],created_at=p.created_at)
                        for p in projects.list_projects(conn)[-40:] if decode(p) and self.authorize(p)]}
            project, candidates = self.selected(conn, args.get('project', ''))
            if not project:
                return {'needs_selection': True, 'projects': candidates}
            if action == 'resolve':
                return self.view(project)
            if action == 'update':
                return self.update(conn, project, args)
            if decode(project)['state'] != 'ready':
                raise ValueError('Project provisioning is incomplete; repeat the approved creation')
            with connect_closing(board=project.board_slug) as board:
                if action == 'task_create':
                    return self.task_create(board, project, args)
                if action == 'tasks':
                    dispatch_once(board, board=project.board_slug, max_spawn=0, failure_limit=2)
                    return {'project_id':project.id, 'tasks':[self.task_view(board,t) for t in kanban.list_tasks(board,limit=30) if t.project_id==project.id]}
                task = self.task(board, project, args.get('task_id'))
                if action=='lifecycle':
                    from projects.lifecycle import act
                    return act(self,board,project,task,args,authorized)
                if action in {'task_update','dependency'}:
                    return self.task_update(board,project,task,args)
                if action == 'task':
                    dispatch_once(board, board=project.board_slug, max_spawn=0, failure_limit=2)
                    return self.task_view(board,self.task(board,project,task.id),True)
                return self.dispatch(board,conn,project,task,args)


def main():
    settings = json.loads(Path(sys.argv[1]).read_text())
    if not settings.get('projects_enabled'):
        raise PermissionError('Projects is disabled')
    root = Path(settings['project_state'])
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root/'argos-adapter.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not (root/'config.yaml').exists():
            from projects.worker import write
            write(root/'config.yaml',json.dumps({'kanban':{'review_dispatch':False,'dispatch_in_gateway':False,
                'notify_in_gateway':False,'auto_decompose':False,'max_spawn':1,'max_in_progress':1},
                'memory':{'memory_enabled':False,'user_profile_enabled':False},'auxiliary':{'background_review':{'enabled':False}}}))
        request = json.loads(sys.stdin.read(65537))
        with contextlib.redirect_stdout(sys.stderr):
            result = Adapter(settings).request(request['arguments'], request.get('authorized') is True)
        print(json.dumps({'ok':True,'result':result},ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'ok':False,'code':type(error).__name__,'error':clean(str(error))[:300]}))
        raise SystemExit(1)
