import os,sys,json
from pathlib import Path
H=Path(__file__).resolve().parent;P=H.parents[1];sys.path.insert(0,str(P/'source'))
from agent.transports.codex_app_server_session import CodexAppServerSession
from agent.transports.codex_app_server import CodexAppServerClient
(H/'unlisted-canary.txt').write_text('SYNTHETIC_UNLISTED')
os.environ['ARGOS_SECRET_CANARY']='SYNTHETIC_ENV_SECRET'
os.environ.update(HERMES_KANBAN_TASK='t_synthetic_scope',HERMES_KANBAN_RUN_ID='1',HERMES_KANBAN_CLAIM_LOCK='synthetic',HERMES_KANBAN_DB=str(H/'native/kanban/boards/secure-proof/kanban.db'),HERMES_KANBAN_BOARD='secure-proof')
holder={}
def factory(**kw):holder['c']=CodexAppServerClient(**kw);return holder['c']
s=CodexAppServerSession(cwd=str(H/'repository'),codex_bin=str(H/'launch_policy.py'),codex_home=str(H/'codex'),model='gpt-6-luna',client_factory=factory)
try:
 s.ensure_started();c=holder['c'];e=c.request('config/read',{'includeLayers':False},timeout=10).get('config',{})

 r=c.request('mcpServerStatus/list',{},timeout=25);out={'inference_calls':0,'servers':[{'name':d['name'],'tool_names':sorted(d.get('tools',{})),'error':d.get('toolsError')} for d in r['data']]};(H/'mcp-surface.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out));print(holder['c'].stderr_tail(8))
finally:s.close()
