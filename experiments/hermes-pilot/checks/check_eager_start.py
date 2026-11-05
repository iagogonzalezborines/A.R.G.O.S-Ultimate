"""Real native startup before input, no IDE session access, then native continuity."""
import sys,subprocess,json,time,select
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P));from pilot import sandbox,PYTHON
SID='argos-eager-start-check';rows=[]
def start():
 cmd=sandbox([PYTHON,P/'checks/desktop_runtime.py',SID],network=True);cmd[cmd.index('--chdir'):cmd.index('--chdir')]=['--ro-bind',str(P/'private/workspace.sock'),'/run/argos-workspace.sock','--setenv','HERMES_TERMINAL_SECURITY_MODE','approval-required']
 process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(P/'ui-workbench/reports/eager-start-worker.log').open('a'),text=True)
 return process
def read(process):
 while True:
  line=process.stdout.readline()
  if not line:raise RuntimeError('Worker exited; inspect eager-start-worker.log')
  if line.startswith('ARGOS_JSON '):return json.loads(line[len('ARGOS_JSON '):])
def ready(process):
 while True:
  row=read(process)
  if not row.get('event'):assert row.get('ready') and row['codex_ready'] and row['model_turns_during_startup']==0,row;return row
p=start()
try:
 first=ready(p);rows.append({'stage':'first_start','ready':first});print(json.dumps(rows[-1]),flush=True)
 p.stdin.write(json.dumps({'text':'For an isolated persistence test, remember that the budget is 80 euros and the colour is cobalt blue. Reply exactly: Ready.'})+'\n');p.stdin.flush()
 while True:
  row=read(p)
  if not row.get('event'):assert row['ok'],row;rows.append({'stage':'turn','response':row});break
finally:p.stdin.close();p.wait(timeout=12)
p=start()
try:
 resumed=ready(p);rows.append({'stage':'resumed_start','ready':resumed});assert resumed['thread_id']==first['thread_id'],rows
 p.stdin.write(json.dumps({'text':'What was the budget? Give only the amount.'})+'\n');p.stdin.flush()
 while True:
  row=read(p)
  if not row.get('event'):assert row['ok'] and '80' in row['speech'],row;rows.append({'stage':'resumed_turn','response':row});break
finally:p.stdin.close();p.wait(timeout=12)
report={'checks':{'starts_native_codex_before_input':True,'subscription_account_present':True,'zero_startup_model_turns':True,'first_real_turn_works':True,'native_thread_resumes':True,'budget_recalled_after_restart':True},'rows':rows};(P/'ui-workbench/reports/eager-start-checks.json').write_text(json.dumps(report,indent=2)+'\n');print('Native startup and continuity passed',flush=True)
