"""Explicit disposable interruption trial using native task APIs, never a scheduler."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PILOT = HERE.parents[1]
sys.path.insert(0, str(PILOT / 'source'))
from hermes_cli import kanban_db as kb
from hermes_cli.kanban_db_connect import connect_closing
from hermes_cli.kanban_db_dispatch import dispatch_once

prepared = json.loads((HERE / 'prepared.json').read_text())
from hermes_constants import get_hermes_home
if Path(get_hermes_home()).resolve() != Path(prepared['root']).resolve():
    raise SystemExit('Refusing to operate outside the prepared disposable owner')
record = HERE / 'interruption-task-v2.json'
action = sys.argv[1]
with connect_closing(board=prepared['board']) as conn:
    if action == 'prepare':
        task_id = kb.create_task(
            conn, title='Disposable interruption and effect reconciliation proof',
            body=(
                'This is a controlled interruption test. Inspect recovery-effect-v2.txt first. '
                'If it exists, do not recreate, append, overwrite or execute the original effect again: '
                'read it, verify its content is EXACTLY ONCE, post a native Kanban comment that the '
                'existing effect was reconciled, and request review with that artifact. '
                'If absent, use one Python command that opens recovery-effect-v2.txt in exclusive x mode, '
                'writes EXACTLY ONCE followed by a newline, closes it, then sleeps for 120 seconds. '
                'The controller will interrupt this first attempt. Do not repeat this command on a retry. '
                'Do not mark yourself complete. No installs, network or changes outside this repository.'
            ), assignee='engineering', workspace_kind='dir', workspace_path=prepared['repository'],
            project_id=prepared['project_id'], board=prepared['board'],
            idempotency_key='controlled-interruption-v2', max_runtime_seconds=180,
            max_retries=1, model_override='gpt-6-luna', provider_override='openai-codex',
            reasoning_effort='low', completion_contract='local-only',
        )
        record.write_text(json.dumps({'task_id': task_id}) + '\n')
        print(json.dumps({'task_id': task_id}))
    else:
        task_id = json.loads(record.read_text())['task_id']
        if action in {'dispatch', 'reconcile'}:
            dispatch_once(conn, board=prepared['board'], max_spawn=1 if action == 'dispatch' else 0, max_in_progress=1,
                          max_in_progress_per_profile=1, failure_limit=1)
        elif action == 'unblock':
            print(json.dumps({'unblocked': kb.unblock_task(conn, task_id)}))
        elif action != 'status':
            raise SystemExit('Unknown trial action')
        task = kb.get_task(conn, task_id)
        runs = [dict(r) for r in conn.execute(
            'SELECT id,status,outcome,error FROM task_runs WHERE task_id=?', (task_id,))]
        print(json.dumps({'task_id': task_id, 'status': task.status, 'run_id': task.current_run_id,
                          'runs': runs}))
