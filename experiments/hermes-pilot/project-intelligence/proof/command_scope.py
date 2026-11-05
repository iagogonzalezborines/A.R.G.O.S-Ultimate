"""Verify the actual native Codex command boundary in a claimed disposable task."""
import json,os,sys,time
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];P=BASE.parent
sys.path.insert(0,str(P/'source'))
from hermes_cli import kanban_db as kb
from hermes_cli.kanban_db_connect import connect_closing
from agent.transports.codex_app_server_session import CodexAppServerSession
from agent.transports.codex_app_server import CodexAppServerClient
state=json.loads((BASE/'proof/prepared.json').read_text());report={'stage':'A','inference_calls':0,'checks':[]}
with connect_closing(board=state['board']) as conn:
 scope_id=kb.create_task(conn,title='Native command-scope preflight',body='Controller-only security checks. No model inference.',assignee='engineering',workspace_kind='dir',workspace_path=state['repository'],project_id=state['project_id'],board=state['board'],max_runtime_seconds=60,max_retries=1)
 task=kb.claim_task(conn,scope_id,claimer='argos-stage-a-scope',ttl_seconds=180)
 if task is None:raise RuntimeError('Disposable security task cannot be claimed')
 os.environ.update(HERMES_KANBAN_TASK=task.id,HERMES_KANBAN_RUN_ID=str(task.current_run_id),HERMES_KANBAN_CLAIM_LOCK=task.claim_lock,HERMES_KANBAN_BOARD=state['board'],HERMES_KANBAN_DB=state['db'],HERMES_KANBAN_WORKSPACE=state['repository'])
 task_id=task.id;run_id=task.current_run_id
holder={}
def factory(**kwargs):holder['client']=CodexAppServerClient(**kwargs);return holder['client']
session=CodexAppServerSession(cwd=state['repository'],codex_bin=str(P/'bin/codex'),codex_home=state['codex_home'],model='gpt-6-luna',client_factory=factory,developer_instructions='No model turn is authorized in this command-scope check.')
probe='''import json,os,pathlib,socket,subprocess,sys
checks=[]
def check(name,ok):checks.append({'name':name,'ok':bool(ok)})
root=pathlib.Path(REPO)
f=root/'.scope-check';f.write_text('ok');f.unlink();check('authorized repository write',True)
for label,path in DENIED_WRITES:
 try:
  f=pathlib.Path(path)/'.argos-scope-negative';f.write_text('scope check');f.unlink()
 except OSError as e:check(label,e.errno in (1,13,30))
 else:check(label,False)
for label,path in DENIED_READS:
 try:
  with open(path,'rb') as f:f.read(0)
 except PermissionError:check(label,True)
 except FileNotFoundError:check(label+' (not exposed)',True)
 else:check(label,False)
try:
 sock=socket.socket();sock.settimeout(.2);sock.connect(('127.0.0.1',9))
except OSError as e:check('command network denied',e.errno in (1,13,101))
else:check('command network denied',False)
print(json.dumps({'checks':checks,'passed':all(c['ok'] for c in checks)}))
'''
probe=probe.replace('REPO',repr(state['repository'])).replace('DENIED_WRITES',repr([('cross-project write denied',str(BASE/'proof/other-project')),('direct board-root write denied',str(Path(state['db']).parent)),('controller write denied',str(BASE/'proof'))])).replace('DENIED_READS',repr([('worker credential read denied',str(Path(state['codex_home'])/'auth.json')),('Hermes credential read denied',str(Path(state['engineering'])/'auth.json')),('board read denied',state['db']),('operational ARGOS read denied','/home/tyrant/Proyectos/argos/AGENTS.md'),('IDE credential read denied','/home/tyrant/.codex/auth.json')]))
try:
 report['native_thread_started']=bool(session.ensure_started());report['run_id']=run_id
 result=holder['client'].request('command/exec',{'command':['/usr/bin/python','-c',probe],'cwd':state['repository'],'timeoutMs':10000},timeout=15)
 report['command_exit_code']=result.get('exitCode')
 if result.get('exitCode')==0:
  report.update(json.loads(result['stdout']))
 else:
  report.update(passed=False,error_category='native_command_preflight_failed',stderr_tail=result.get('stderr','')[-1400:])
except Exception as error:report.update(passed=False,error_category=type(error).__name__,detail=str(error)[:1400])
finally:
 session.close()
 (BASE/'proof/command-scope.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report),flush=True)
 # The native record remains inspectable. No implementation task is dispatched after a failed gate.
 with connect_closing(board=state['board']) as conn:
  kb.block_task(conn,task_id,reason='Stage A command-scope gate '+('passed' if report.get('passed') else 'failed')+'; see command-scope.json',expected_run_id=run_id,kind='capability')
 (BASE/'proof/command-scope.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
raise SystemExit(0 if report.get('passed') else 1)
