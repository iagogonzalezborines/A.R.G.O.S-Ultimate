"""Native Hermes/Codex capability regression: clear, storage, clipboard. Synthetic files only."""
import json,sys,subprocess,time
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P));from pilot import sandbox,PYTHON
cmd=sandbox([PYTHON,P/'checks/desktop_runtime.py','argos-storage-clear-check'],network=True);cmd[cmd.index('--chdir'):cmd.index('--chdir')]=['--ro-bind',str(P/'private/workspace.sock'),'/run/argos-workspace.sock','--setenv','HERMES_TERMINAL_SECURITY_MODE','approval-required'];p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,start_new_session=True)
def read():
 while True:
  line=p.stdout.readline()
  if not line:raise RuntimeError('Native adapter disconnected')
  if line.startswith('ARGOS_JSON '):return json.loads(line[11:])
rows=[]
try:
 print(json.dumps(read()),flush=True)
 for text in [
  'Clear the workspace.',
  'Show my actual PC disks and partitions in the workspace. Is nvme0n1p4 mounted, and do you know its free space? Check, do not guess.',
  'Open the file explorer in Personal.',
  'Copy ARGOS/qa-storage/source/clip.txt into your file clipboard. Then paste it into ARGOS/qa-storage/target. Prepare the concrete paste for review; do not claim it is already on disk.'
 ]:
  start=time.monotonic();p.stdin.write(json.dumps({'text':text})+'\n');p.stdin.flush()
  while True:
   result=read()
   if not result.get('event'):break
  row={'input':text,'response':result,'seconds':time.monotonic()-start};rows.append(row);print(json.dumps(row),flush=True)
finally:
 p.stdin.close()
 try:p.wait(timeout=6)
 except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=6)
 (P/'ui-workbench/reports/storage-clear-native-checks.json').write_text(json.dumps({'turns':rows,'runtime':'native Hermes AIAgent/Codex App Server gpt-6-luna low','speaker_audio':'muted'},indent=2)+'\n')
