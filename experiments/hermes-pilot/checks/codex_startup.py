"""Eager initialization using the pinned native Hermes lifecycle, without a model turn."""
import time

def prepare_codex(agent,db,sid):
 # These are pinned Hermes lifecycle helpers, reused rather than a second runtime.
 from agent.conversation_loop import _restore_or_build_system_prompt
 from agent.codex_runtime import _ensure_codex_session,_start_codex_thread
 started=time.monotonic();history=db.get_messages_as_conversation(sid) or []
 agent._ensure_db_session()
 if agent._cached_system_prompt is None:_restore_or_build_system_prompt(agent,None,history or None)
 # Native history seeding excludes the current user row. There is no current turn
 # during startup; this temporary empty framing row is never persisted or sent as input.
 _ensure_codex_session(agent,history+[{'role':'user','content':''}])
 thread_id=_start_codex_thread(agent)
 account=agent._codex_session._client.request('account/read',{'refreshToken':False},timeout=10)
 authenticated=(account.get('account') or {}).get('type')=='chatgpt'
 if not authenticated:raise RuntimeError('Codex subscription login is unavailable in the isolated pilot')
 return {'codex_ready':True,'subscription_account_present':True,'thread_id':thread_id,'startup_seconds':time.monotonic()-started,'model_turns_during_startup':0}
