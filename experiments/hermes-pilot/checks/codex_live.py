"""Real subscription turns through Hermes's unmodified native Codex session."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pilot import ROOT, FIXTURE
from agent.transports.codex_app_server_session import CodexAppServerSession

events = []
current = {}


def on_event(event):
    # Capture public event types/timing only. Never persist model reasoning or tokens.
    method = event.get('method', event.get('type', 'unknown'))
    events.append({'method': method, 'seconds': time.monotonic()-current.get('start',time.monotonic())})


kwargs = dict(cwd=str(FIXTURE), codex_bin=str(ROOT/'bin/codex'),
              codex_home=str(ROOT/'state/codex'), permission_profile='read-only',
              approval_callback=lambda *a, **kw: 'deny', model='gpt-6-luna',
              developer_instructions='You are ARGOS. Be serious, efficient and concise. Match the language of the user. Use understated situational irony when invited, never an explanation of an obvious fact unless asked. Be candid about actual tool results. All fixture files are read-only. No changes or credential reads are authorized.',
              on_event=on_event)
session = CodexAppServerSession(**kwargs)
rows = []


def turn(prompt):
    current['start'] = time.monotonic()
    result = session.run_turn(prompt, model='gpt-6-luna', reasoning_effort='low', turn_timeout=70)
    rows.append({'input':prompt,'seconds':time.monotonic()-current['start'],
                 'response':result.final_text,'error':result.error,
                 'tool_iterations':result.tool_iterations,'usage':result.token_usage_last,
                 'interrupted':result.interrupted, 'thread_id':session._thread_id})
    print(json.dumps({'kind':'turn',**rows[-1]}),flush=True)
    return result


try:
    turn('Argos, is the sky green?')
    turn('Read README.md in this disposable project and tell me its exact heading. Use a tool; do not guess.')
    turn('Recuerda solo en esta conversación: la etiqueta de esta prueba es latón 47. ¿Entendido?')
    thread_id = session._thread_id
    session.close()
    session = CodexAppServerSession(**kwargs, resume_thread_id=thread_id)
    turn('¿Cuál era la etiqueta de la prueba? Una frase.')
finally:
    session.close()
    print(json.dumps({'kind':'events','events':events}),flush=True)
