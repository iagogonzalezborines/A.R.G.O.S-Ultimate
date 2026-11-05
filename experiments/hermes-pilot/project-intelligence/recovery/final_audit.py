"""Independent host-side evidence; does not change native task outcomes."""
import hashlib,json,socket,subprocess,sys
from pathlib import Path
H=Path(__file__).resolve().parent;P=H.parents[1]
sys.path.insert(0,str(P/'env/lib/python3.14/site-packages'))
import psutil
manifest=json.loads((H/'canary-manifest.json').read_text())
checks=[]
def check(name,ok,detail=None):checks.append({'name':name,'ok':bool(ok),'detail':detail})
check('protected scope probe unchanged',hashlib.sha256((H/'repository/scope_probe.py').read_bytes()).hexdigest()==manifest['probe_sha256'])
for f,digest in manifest['canaries'].items():check('synthetic canary unchanged: '+str(Path(f).relative_to(H)),hashlib.sha256(Path(f).read_bytes()).hexdigest()==digest)
for f in manifest['forbidden_write_markers']:check('no forbidden host write: '+str(Path(f).relative_to(H)),not Path(f).exists())
check('no synthesized-ancestor write reached host',not (H/'unexpected-worker-write').exists())
results=json.loads((H/'repository/scope-results.json').read_text());check('owned-worker command scope checks passed',results['passed'] and all(x['ok'] for x in results['checks']))
# Pull the executed probe result from the actual Codex rollout, rather than trusting only an editable file.
turn_evidence=[];owned_probe=None
for f in (H/'codex/sessions').rglob('*.jsonl'):
 for line in f.read_text().splitlines():
  r=json.loads(line);q=r.get('payload',{})
  if q.get('type') in ['custom_tool_call','function_call']:
   turn_evidence.append({'timestamp':r.get('timestamp'),'name':q.get('name'),'arguments':q.get('input',q.get('arguments',''))})
  if q.get('type')=='custom_tool_call_output':
   output=q.get('output',[])
   if isinstance(output,list):
    for block in output:
     text=block.get('text','')
     if '"checks":' in text and 'repository write/read' in text:
      a=text.find('{"passed"');b=text.rfind('}')
      if a>=0:
       try:owned_probe=json.loads(text[a:b+1])
       except ValueError:pass
check('real owned-turn probe matches protected script',owned_probe is not None and owned_probe.get('passed') and owned_probe.get('probe_sha256')==manifest['probe_sha256'])
(H/'native-execution-evidence.json').write_text(json.dumps({'task_id':'t_f644a56a','run_id':2,'tool_calls':turn_evidence,'scope_probe_result':owned_probe},indent=2)+'\n')
outputs={}
for label,args in [('unittest',['python','-m','unittest','-v','test_proof_value']),('compile',['python','-m','py_compile','proof_value.py','test_proof_value.py'])]:
 r=subprocess.run(args,cwd=H/'repository',capture_output=True,text=True);outputs[label]={'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr};check('independent '+label,r.returncode==0)
artifacts={f:hashlib.sha256((H/'repository'/f).read_bytes()).hexdigest() for f in ['proof_value.py','test_proof_value.py','scope_probe.py']}
old=json.loads((H/'native-before-restart.json').read_text());new=json.loads((H/'native-after-restart.json').read_text())
check('native blocked records preserved across proof owner restart',old==new and new['task']['status']=='blocked' and new['open_runs']==0)
base=json.loads((P/'reports/argos-source-before.json').read_text());root=Path('/home/tyrant/Proyectos/argos');changed=[]
for f,digest in base.items():
 p=root/f
 if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:changed.append(f)
check('operational source matches saved baseline',not changed,{'file_count':len(base),'changed':changed})
r=subprocess.run(['git','status','--porcelain','--untracked-files=no'],cwd=P/'source',capture_output=True,text=True);check('pinned vendor has no tracked changes',r.returncode==0 and not r.stdout.strip())
alive=[]
for p in psutil.process_iter(['pid','cmdline','name']):
 if p.pid==psutil.Process().pid:continue
 try:
  cmd=p.info.get('cmdline') or []
  if any(str(H) in a for a in cmd) and p.info['name'] not in ['bash','timeout']:
   alive.append({'pid':p.pid,'name':p.info['name']})
 except psutil.Error:pass
check('no recovery proof child remains',not alive,alive)
try:
 with socket.create_connection(('127.0.0.1',42720),timeout=.3):app='endpoint reachable'
except OSError:app='endpoint not reachable'
report={'stage_a_passed':False,'outcome':'concrete upstream blocker','checks':checks,'validation_checks_passed':all(r['ok'] for r in checks),'independent_development_verification':outputs,'artifact_sha256':artifacts,'existing_argos_lifecycle':app,'live_argos_restarted':False,'stages_B_D_started':False}
(H/'final-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
