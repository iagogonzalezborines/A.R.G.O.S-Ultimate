"""A native AIAgent session using the supported App Server mode, not another loop."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pilot import ROOT, FIXTURE
from run_agent import AIAgent
from hermes_state import SessionDB
from hermes_cli.runtime_provider import resolve_runtime_provider

db=SessionDB()
sid='pilot-native-agent-subscription'
started=time.monotonic()
runtime=resolve_runtime_provider(requested='openai-codex',target_model='gpt-6-luna')
agent=AIAgent(provider=runtime['provider'],api_mode=runtime['api_mode'],model='gpt-6-luna',
    api_key=runtime.get('api_key'),base_url=runtime.get('base_url'),
    quiet_mode=True,enabled_toolsets=['argos_broker','memory','skills'],
    disabled_toolsets=['terminal','browser','file','code_execution','delegation','connections'],
    session_id=sid,session_db=db,cwd=str(FIXTURE),max_iterations=4,
    reasoning_config={'effort':'low'},skip_background_review=True,
    ephemeral_system_prompt='ARGOS pilot. Be concise and match the user language. Read-only disposable project. No writes or credential reads authorized. Report verified tool results only.')
print(json.dumps({'kind':'init','seconds':time.monotonic()-started,'api_mode':agent.api_mode}),flush=True)
try:
    prompts=(['¿Cuál era el título del archivo que leíste en esta sesión? Una frase.']
             if 'resume' in sys.argv else ['Lee README.md con una herramienta y dime su título, sin explicación.',
                   'En una frase: ¿cuál era el título que acabas de leer?'])
    history=db.get_messages_as_conversation(sid) if 'resume' in sys.argv else None
    for prompt in prompts:
        start=time.monotonic();result=agent.run_conversation(prompt,conversation_history=history)
        # Public answer only, never dump the native result's reasoning or full messages.
        print(json.dumps({'kind':'turn','seconds':time.monotonic()-start,
             'input':prompt,'public':{k:result.get(k) for k in ['final_response','completed','error','iterations']}}),flush=True)
finally:
    agent.close()
    row=db.get_session(sid)
    print(json.dumps({'kind':'native_persistence','session_exists':bool(row),
                     'model_config':(row or {}).get('model_config'),
                     'message_count':len(db.get_messages(sid))}),flush=True)
    db.close()
