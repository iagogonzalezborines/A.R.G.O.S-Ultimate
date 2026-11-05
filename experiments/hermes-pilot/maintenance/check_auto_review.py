"""Automatic diagnosis admits bounded candidates, never self-approval or retry loops."""
from pathlib import Path
import sys,tempfile,json
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P))
from maintenance.controller import Maintenance,clean
checks=[]
def check(name,value):checks.append({'name':name,'ok':bool(value)});assert value,name
with tempfile.TemporaryDirectory(prefix='argos-auto-review-') as d:
 m=Maintenance(state=Path(d),auto_diagnose=True);calls=[];m.propose=lambda goal,incident_id: calls.append((goal,incident_id)) or {'proposal_id':'synthetic'}
 m.incident('renderer',RuntimeError('Synthetic renderer crash'),notify=True);check('new runtime incident starts one diagnostic candidate',len(calls)==1)
 m.incident('renderer',RuntimeError('Synthetic renderer crash'),notify=True);check('repeated incident does not create a loop',len(calls)==1)
 m.incident('renderer',RuntimeError('Another crash'),notify=True);check('cooldown bounds new error bursts',len(calls)==1)
 m.save('auto-policy.json',{'day':int(__import__('time').time()//86400),'count':3,'last_start':0});m.incident('renderer',RuntimeError('Daily limit'),notify=True);check('daily budget caps automatic Codex runs',len(calls)==1)
 m.save('auto-policy.json',{});m.incident('voice.turn',PermissionError('Denied operation'),notify=True);check('denied permissions do not trigger a bypass repair',len(calls)==1)
 m.incident('development',RuntimeError('Coding failed'),notify=True);check('coding failures cannot recursively self-repair',len(calls)==1)
 check('redaction retains non-secret permission evidence',clean({'credential_reads_denied':True,'access_token':'secret'})=={'credential_reads_denied':True,'access_token':'[redacted]'})
 check('automatic diagnosis never creates an approval grant',not m.load('pending.json'))
(P/'ui-workbench/reports/self-development-auto-review.json').write_text(json.dumps({'checks':checks},indent=2)+'\n');print(json.dumps({'passed':len(checks)}))
