"""Eager initialization using the pinned native Hermes lifecycle, without a model turn."""
import time
import os
import tomllib
from pathlib import Path

def prepare_codex(agent,db,sid,on_stage=lambda stage:None):
 # These are pinned Hermes lifecycle helpers, reused rather than a second runtime.
 from agent.conversation_loop import _restore_or_build_system_prompt
 from agent.codex_runtime import _ensure_codex_session,_start_codex_thread
 started=time.monotonic();on_stage('session_history');history=db.get_messages_as_conversation(sid) or []
 agent._ensure_db_session()
 if agent._cached_system_prompt is None:
  on_stage('prompt_restore');_restore_or_build_system_prompt(agent,None,history or None)
 # Native history seeding excludes the current user row. There is no current turn
 # during startup; this temporary empty framing row is never persisted or sent as input.
 on_stage('app_server_connect')
 _ensure_codex_session(agent,history+[{'role':'user','content':''}])
 wanted=getattr(agent._codex_session,'_resume_thread_id',None)
 on_stage('session_recovery');thread_id=_start_codex_thread(agent)
 on_stage('authentication')
 account=agent._codex_session._client.request('account/read',{'refreshToken':False},timeout=10)
 authenticated=(account.get('account') or {}).get('type')=='chatgpt'
 if not authenticated:raise RuntimeError('Codex subscription login is unavailable in the isolated pilot')
 on_stage('capability_registration')
 config=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'config.toml'
 expected=set(tomllib.loads(config.read_text()).get('mcp_servers',{}).get('argos-workspace',{}).get('enabled_tools',[])) if config.exists() else set()
 tools=[]
 if expected:
  surface=agent._codex_session._client.request('mcpServerStatus/list',{},timeout=10)
  server=next((r for r in surface.get('data',[]) if r.get('name')=='argos-workspace'),{})
  tools=list(server.get('tools',{}))
  if server.get('toolsError') or expected-set(tools):raise RuntimeError('Required ARGOS workspace capabilities are unavailable')
 return {'registered_tool_count':len(tools),'session_resumed':bool(wanted and thread_id==wanted),'codex_ready':True,'subscription_account_present':True,'thread_id':thread_id,'startup_seconds':time.monotonic()-started,'model_turns_during_startup':0}
