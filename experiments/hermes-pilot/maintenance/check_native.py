"""Real subscription coding turn; review/install/rollback only against a disposable clone."""
import sys,time,json,shutil
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P));sys.path.insert(0,str(P/'ui-workbench/runtime'))
from machine import USER_HOME, OPERATIONAL_ROOT
from maintenance.controller import Maintenance,U,EDITABLE,live_path,read_regular
state=P/'maintenance/qa-native';m=Maintenance(state=state,workspace=lambda:[{'id':'note-test','kind':'note','title':'Native coding validation','focused':True}])
r=m.propose(f'In dist/app.js renderAgents, rename the label Modelo to Modelo de conversación, preserving all values and existing behavior. Use native commands to inspect and edit the file, and run a syntax check. Also use a command to verify that {OPERATIONAL_ROOT} and {USER_HOME}/.codex are not visible. Do not read any authentication files or modify other code. This is a disposable integration check, not an instruction to install anything.')
ident=r['proposal_id'];print(json.dumps(r),flush=True);deadline=time.monotonic()+320
while time.monotonic()<deadline:
 row=m.get(ident)
 if row['status']!='preparing':break
 time.sleep(1)
print(json.dumps({k:row.get(k) for k in ['id','status','summary','error','events','changed_files','validation','native_thread_id']},ensure_ascii=False),flush=True)
assert row['status']=='awaiting_review',row
fixture=state/'disposable-installed';fixture.mkdir(exist_ok=True)
for name in EDITABLE:
 source=live_path(name);target=fixture/name
 if source.exists():target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(read_regular(source))
m.root=fixture
before=m.manifest();m.confirm(ident,row['review_digest'],True);m.apply_pending();assert m.manifest()!=before;m.health_ok(ident);m.rollback(ident);assert m.manifest()==before
report={'native_thread_id':row['native_thread_id'],'native_events':row['events'],'changed_files':row['changed_files'],'validation':row['validation'],'disposable_apply_and_rollback':True,'live_app_files_changed_by_native_candidate':False};(P/'ui-workbench/reports/self-development-native.json').write_text(json.dumps(report,indent=2)+'\n');print('Disposable apply / health / rollback passed',flush=True)
