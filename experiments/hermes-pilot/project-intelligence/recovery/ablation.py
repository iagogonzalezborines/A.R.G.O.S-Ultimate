"""No-inference policy comparison, with synthetic files and actual native transport."""
import json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;P=HERE.parents[1];sys.path.insert(0,str(P/'source'))
from agent.transports.codex_app_server_session import CodexAppServerSession
from agent.transports.codex_app_server import CodexAppServerClient
repo=HERE/'repository';repo.mkdir(exist_ok=True)
private=HERE/'private';private.mkdir(exist_ok=True,mode=0o700)
for folder in ['board','credentials','controller','other-project','operational-argos','ide']:
 f=private/folder;f.mkdir(exist_ok=True,mode=0o700);(f/'canary.txt').write_text('SYNTHETIC_'+folder+'\n')
home=HERE/'codex';home.mkdir(exist_ok=True,mode=0o700)
fs={':minimal':'read',str(repo):'write','/tmp':'write',str(private):'deny',str(home):'deny',str(HERE/'launch_policy.py'):'deny',str(HERE/'policy.json'):'deny','/home/tyrant/.codex':'deny','/home/tyrant/Proyectos':'deny'}
fs.update({str(x):'read' for x in [P/'bin',P/'tools',P/'env',P/'source']})
policy={'filesystem':fs};(HERE/'policy.json').write_text(json.dumps(policy,indent=2)+'\n')
config='default_permissions="argos-proof"\napproval_policy="never"\nweb_search="disabled"\n[permissions.argos-proof.filesystem]\n'+''.join(json.dumps(k)+'='+json.dumps(v)+'\n' for k,v in fs.items())+'[permissions.argos-proof.network]\nenabled=false\n'
config+='[mcp_servers.hermes-tools]\ncommand='+json.dumps(str(P/'env/bin/python'))+'\nargs=[\"-m\",\"agent.transports.hermes_tools_mcp_server\"]\nenabled_tools=[\"kanban_comment\",\"kanban_heartbeat\",\"kanban_block\",\"kanban_request_review\",\"kanban_show\"]\nstartup_timeout_sec=10\n'
(home/'config.toml').write_text(config)
probe='''import json,pathlib,socket
repo=pathlib.Path(REPO);private=pathlib.Path(PRIVATE);rows=[]
f=repo/'artifact.txt';f.write_text('working');rows.append({'name':'repository write/read','ok':f.read_text()=='working'})
for folder in ['board','credentials','controller','other-project','operational-argos','ide']:
 p=private/folder
 try: data=(p/'canary.txt').read_text()
 except OSError as e: rows.append({'name':folder+' read denied','ok':e.errno in (1,2,13,30)})
 else: rows.append({'name':folder+' read denied','ok':False})
 try:
  f=p/'negative-write';f.write_text('probe');f.unlink()
 except OSError as e: rows.append({'name':folder+' write denied','ok':e.errno in (1,2,13,30)})
 else: rows.append({'name':folder+' write denied','ok':False})
try:
 s=socket.socket();s.settimeout(.2);s.connect(('127.0.0.1',9))
except OSError as e: rows.append({'name':'network denied','ok':e.errno in (1,13,101)})
else: rows.append({'name':'network denied','ok':False})
print(json.dumps(rows))
'''.replace('REPO',repr(str(repo))).replace('PRIVATE',repr(str(private)))
report={'inference_calls':0,'cases':[]}
for label,owned,adapter in [('named_without_owned_overrides',False,False),('native_owned_legacy_overrides',True,False),('owned_with_fixed_launcher',True,True)]:
 for key in ['HERMES_KANBAN_TASK','HERMES_KANBAN_RUN_ID','HERMES_KANBAN_CLAIM_LOCK','HERMES_KANBAN_DB','HERMES_KANBAN_BOARD']:os.environ.pop(key,None)
 if owned:os.environ.update(HERMES_KANBAN_TASK='t_synthetic_scope',HERMES_KANBAN_RUN_ID='1',HERMES_KANBAN_CLAIM_LOCK='synthetic',HERMES_KANBAN_DB=str(private/'board/kanban.db'),HERMES_KANBAN_BOARD='proof')
 holder={}
 def factory(**kwargs):holder['client']=CodexAppServerClient(**kwargs);return holder['client']
 session=CodexAppServerSession(cwd=str(repo),codex_bin=str(HERE/'launch_policy.py' if adapter else P/'bin/codex'),codex_home=str(home),model='gpt-6-luna',client_factory=factory)
 try:
  session.ensure_started();client=holder['client']
  effective=client.request('config/read',{'includeLayers':False},timeout=10).get('config',{})
  result=client.request('command/exec',{'command':['/usr/bin/python','-c',probe],'cwd':str(repo),'timeoutMs':10000},timeout=15)
  case={'case':label,'exit_code':result.get('exitCode'),'effective':{k:effective.get(k) for k in ['default_permissions','sandbox_mode','sandbox_workspace_write']}}
  if result.get('exitCode')==0:case['checks']=json.loads(result['stdout']);case['passed']=all(c['ok'] for c in case['checks'])
  else:case.update(passed=False,stderr=result.get('stderr','')[-1000:])
 except Exception as error:case={'case':label,'passed':False,'error':type(error).__name__,'detail':str(error)[:1000],'stderr':holder['client'].stderr_tail(5) if holder.get('client') else []}
 finally:session.close()
 report['cases'].append(case);print(json.dumps(case),flush=True)
(HERE/'ablation.json').write_text(json.dumps(report,indent=2)+'\n')
