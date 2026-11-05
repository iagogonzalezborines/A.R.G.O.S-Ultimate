"""Actual native Hermes/Codex MCP turns; synthetic fixture, muted UI, no microphone."""
import json,sys,time
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P));from pilot import sandbox,PYTHON
import subprocess
cmd=sandbox([PYTHON,P/'checks/desktop_runtime.py','argos-workspace-capability-check'],network=True);cmd[cmd.index('--chdir'):cmd.index('--chdir')]=['--ro-bind',str(P/'private/workspace.sock'),'/run/argos-workspace.sock','--setenv','HERMES_TERMINAL_SECURITY_MODE','approval-required']
fixture=P/'workspaces/files/workspace-pilot-context.txt';fixture.write_text('Disposable validation project: enclosure colour cobalt blue. Budget: 80 euros. No other projects are described.\n')
rows=[]
p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,start_new_session=True)
def read():
 while True:
  line=p.stdout.readline()
  if not line:raise RuntimeError('Native adapter disconnected')
  if line.startswith('ARGOS_JSON '):return json.loads(line[11:])
try:
 ready=read();print(json.dumps(ready),flush=True)
 turns=[
 'Open your custom file explorer in the ARGOS folder, inside this workspace.',
 'Find workspace-pilot-context.txt in that folder and open it inside the workspace.',
 'What enclosure colour and budget does that file actually specify? Read the file.',
 'Make that document window 950 pixels wide and 650 high and move it to x=24 y=30. Use the actual workspace controls.',
 'Open https://www.youtube.com/watch?v=dQw4w9WgXcQ as a video window inside this workspace. Do not search or play anything externally.',
 'Minimize that video window and focus the file explorer.',
 'Rename workspace-pilot-context.txt to workspace-pilot-context-renamed.txt in the same folder. Prepare the concrete change for review; do not apply it.'
 ]
 for text in turns:
  start=time.monotonic();p.stdin.write(json.dumps({'text':text})+'\n');p.stdin.flush();events=[]
  while True:
   result=read()
   if result.get('event'):events.append({k:v for k,v in result.items() if k!='text'});continue
   break
  row={'input':text,'response':result,'seconds':time.monotonic()-start,'event_types':[e.get('event') for e in events]};rows.append(row);print(json.dumps(row),flush=True)
finally:
 p.stdin.close()
 try:p.wait(timeout=5)
 except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=5)
 (P/'ui-workbench/reports/workspace-native-checks.json').write_text(json.dumps({'turns':rows,'provider':'native Hermes Codex App Server / gpt-6-luna low','audio':'muted','fixture':str(fixture)},indent=2)+'\n')
