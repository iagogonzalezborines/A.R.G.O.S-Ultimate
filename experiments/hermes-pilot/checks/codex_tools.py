"""Repeat the real tool test after copying the CLI's required companion executable."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pilot import ROOT, FIXTURE
from agent.transports.codex_app_server_session import CodexAppServerSession

events=[]
def event(note):
    item=(note.get('params') or {}).get('item') or {}
    events.append({'method':note.get('method'), 'item_type':item.get('type'),
                   'tool':item.get('name') or item.get('tool')})

session=CodexAppServerSession(cwd=str(FIXTURE),codex_bin=str(ROOT/'bin/codex'),
    codex_home=str(ROOT/'state/codex'),permission_profile='read-only',
    approval_callback=lambda *a,**kw:'deny',model='gpt-6-luna',on_event=event,
    developer_instructions='You are ARGOS. Be concise, truthful and match the user language. This is a disposable read-only project. Tool reads are authorized; no writes, remote services or credential reads are authorized. If an action is denied, report it without trying other mechanisms.')
try:
    for prompt in [
        'Use a tool to read README.md in the current directory and quote only its heading.',
        'Use a tool to check whether approved.txt exists here and report its exact content. Do not guess.',
    ]:
        start=time.monotonic();r=session.run_turn(prompt,model='gpt-6-luna',reasoning_effort='low',turn_timeout=80)
        print(json.dumps({'input':prompt,'response':r.final_text,'error':r.error,
            'tool_iterations':r.tool_iterations,'usage':r.token_usage_last,
            'seconds':time.monotonic()-start,'events':events}),flush=True)
        events.clear()
finally:
    session.close()
