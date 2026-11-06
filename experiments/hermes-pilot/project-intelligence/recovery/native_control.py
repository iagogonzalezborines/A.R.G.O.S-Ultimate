"""Bounded Stage A test actions over native Hermes APIs. No scheduling/agent loop."""
import json,os,sys
from pathlib import Path
H=Path(__file__).resolve().parent;P=H.parents[1];sys.path.insert(0,str(P/'source'))
from hermes_cli import kanban_db as kb
from hermes_cli.kanban_db_connect import connect_closing
from hermes_cli.kanban_db_dispatch import dispatch_once
s=json.loads((H/'prepared.json').read_text());op=sys.argv[1]
if op=='ensure':
 from hermes_cli.gateway_runtime import ensure_gateway_runtime
 r=ensure_gateway_runtime(s['engineering'],timeout=45,idle_exit=False)
 print(json.dumps({'state':r.state,'reason':r.reason_code,'detail':r.detail,'endpoint':{'profile_id':r.endpoint.profile_id,'instance_id':r.endpoint.instance_id} if r.endpoint else None}),flush=True)
 if r.state!='ready':raise SystemExit(1)
elif op=='dispatch':
 with connect_closing(board=s['board']) as c:
  r=dispatch_once(c,board=s['board'],max_spawn=1,max_in_progress=1,max_in_progress_per_profile=1,failure_limit=1)
  print(json.dumps({'spawned':r.spawned,'spawn_failed':r.spawn_failed if hasattr(r,'spawn_failed') else None,'skipped_unassigned':r.skipped_unassigned,'skipped_nonspawnable':r.skipped_nonspawnable,'task':vars(kb.get_task(c,s['task_id']))}),flush=True)
elif op=='park':
 with connect_closing(board=s['board']) as c:
  t=kb.get_task(c,s['task_id'])
  result=kb.block_task(c,t.id,reason='Stage A recovery stopped: native worker session.sidecars rejects codex_thread_id; owner outcome is unknown. Preserve run evidence; do not replay.',kind='capability',expected_run_id=t.current_run_id) if t.status=='running' else False
  print(json.dumps({'controller_parked':result,'status':kb.get_task(c,t.id).status}),flush=True)
elif op=='stop':
 from hermes_cli.gateway import _owned_gateway_pid,stop_profile_gateway
 from hermes_constants import get_hermes_home
 from hermes_cli.gateway_runtime import discover_gateway_endpoint
 home=Path(get_hermes_home()).resolve();assert home==Path(s['root']).resolve()
 r=discover_gateway_endpoint(home);assert not r.endpoint or (r.endpoint.profile_id==str(home) and r.endpoint.control_home in (None,str(home)))
 pid=_owned_gateway_pid();print(json.dumps({'proof_owner_pid':pid,'stop_requested':stop_profile_gateway()}),flush=True)
elif op=='unblock':
 with connect_closing(board=s['board']) as c:
  print(json.dumps({'unblocked':kb.unblock_task(c,s['task_id'])}),flush=True)
elif op=='snapshot':
 with connect_closing(board=s['board']) as c:
  t=kb.get_task(c,s['task_id']);rows={'task':vars(t),'runs':[dict(r) for r in c.execute('SELECT * FROM task_runs WHERE task_id=?',(t.id,))],'events':[dict(r) for r in c.execute('SELECT * FROM task_events WHERE task_id=? ORDER BY id',(t.id,))],'open_runs':c.execute('SELECT count(*) FROM task_runs WHERE ended_at IS NULL').fetchone()[0]}
  (H/('native-'+sys.argv[2]+'.json')).write_text(json.dumps(rows,indent=2,default=str)+'\n')
  print(json.dumps({'status':t.status,'run_count':len(rows['runs']),'event_count':len(rows['events']),'open_runs':rows['open_runs']}),flush=True)
elif op=='status':
 with connect_closing(board=s['board']) as c:
  t=kb.get_task(c,s['task_id']);print(json.dumps({'task':vars(t),'runs':[dict(r) for r in c.execute('SELECT id,status,outcome,worker_pid,error,summary FROM task_runs WHERE task_id=?',(t.id,))],'events':[dict(r) for r in c.execute('SELECT id,kind,run_id,payload FROM task_events WHERE task_id=? ORDER BY id DESC LIMIT 15',(t.id,))]},default=str),flush=True)
elif op in {'trial-prepare','trial-status','trial-dispatch','trial-reconcile','trial-unblock','interrupt'}:
 import runpy
 from hermes_constants import get_hermes_home
 if Path(get_hermes_home()).resolve()!=Path(s['root']).resolve():raise SystemExit('Wrong disposable owner')
 script=H/('interrupt_live.py' if op=='interrupt' else 'recovery_trial.py')
 sys.argv=[str(script)]+([] if op=='interrupt' else [op.removeprefix('trial-')])
 runpy.run_path(str(script),run_name='__main__')
else:raise SystemExit('Unknown test action')
