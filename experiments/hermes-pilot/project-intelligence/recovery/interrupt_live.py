"""Stop only the disposable native owner while its real command is in progress."""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PILOT = HERE.parents[1]
sys.path.insert(0, str(PILOT / 'source'))
from hermes_cli.gateway import stop_profile_gateway
from hermes_cli.kanban_db_connect import connect_closing
from hermes_cli import kanban_db as kb

prepared = json.loads((HERE / 'prepared.json').read_text())
from hermes_constants import get_hermes_home
if Path(get_hermes_home()).resolve() != Path(prepared['root']).resolve():
    raise SystemExit('Refusing to operate outside the prepared disposable owner')
marker = Path(prepared['repository']) / 'recovery-effect-v2.txt'
if marker.exists():
    raise SystemExit('Trial already has effects; inspect evidence instead of replaying')
trial = HERE / 'recovery_trial.py'
subprocess.run([sys.executable, str(trial), 'prepare'], check=True)
task_id = json.loads((HERE / 'interruption-task-v2.json').read_text())['task_id']
with (HERE / 'interruption-v2-dispatch.log').open('w') as log:
    dispatcher = subprocess.Popen([sys.executable, str(trial), 'dispatch'], stdout=log, stderr=log)
    try:
        deadline = time.monotonic() + 100
        while not marker.exists():
            if time.monotonic() > deadline:
                raise RuntimeError('No effect observed; do not claim interruption verified')
            time.sleep(.1)
        with connect_closing(board=prepared['board']) as conn:
            task = kb.get_task(conn, task_id)
            if task.status != 'running':
                raise RuntimeError('Worker already ended; this is not an in-flight interruption')
            record = {'task_id': task_id, 'run_id': task.current_run_id, 'status_before': task.status,
                      'sha256': hashlib.sha256(marker.read_bytes()).hexdigest(),
                      'mtime_ns': marker.stat().st_mtime_ns, 'size': marker.stat().st_size}
        record['native_stop_requested'] = stop_profile_gateway()
        (HERE / 'interruption-v2-before.json').write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps(record), flush=True)
    finally:
        stop_profile_gateway()
        if dispatcher.poll() is None:
            dispatcher.terminate()
        dispatcher.wait(timeout=15)
