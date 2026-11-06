"""Opt-in real owned-worker isolation check against a second disposable project."""
import hashlib
import json
from pathlib import Path
import sys
import time

P = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(P),str(P/'ui-workbench')]
from runtime.projects import Projects


def main():
    root=Path(json.loads((P/'reports/block-b-live-location.json').read_text())['root'])
    broker=Projects(lambda event:None,config_path=root/'installation.json')
    request=broker.request
    first=request({'action':'resolve','project':'notebook'})
    canary=Path(first['path'])/'sibling-canary.txt';canary.write_text('SYNTHETIC_OTHER_PROJECT\n')
    control=root/'excluded';control.mkdir(exist_ok=True)
    for name in ['controller','credential','ide','argos']:(control/name).write_text('SYNTHETIC_'+name+'\n')
    proposed=request({'action':'propose','name':'Isolation Check','slug':'isolation-check',
                      'brief':{'objective':'Disposable native worker isolation proof'}})
    if proposed.get('project'):project=proposed['project']
    else:project=request({'action':'confirm','proposal_id':proposed['id'],'approve':True},user=True)['project']
    repo=Path(project['path'])
    db=root/'native/kanban/boards'/project['board']/'kanban.db'
    assert db.is_file()
    reads=[str(db),str(canary),*[str(control/n) for n in ['controller','credential','ide','argos']]]
    writes=[str(control/'escaped'),str(Path(first['path'])/'escaped'),str(db.parent/'escaped')]
    script='''import json,os,pathlib,socket,subprocess,sys
checks=[]
def check(name,ok):checks.append({'name':name,'ok':bool(ok)})
for value in READS:
 try:
  with open(value,'rb') as f:f.read(0)
 except OSError as e:check('read denied: '+pathlib.Path(value).name,e.errno in (1,2,13,30))
 else:check('read denied: '+value,False)
for value in WRITES:
 try:pathlib.Path(value).write_text('UNAUTHORIZED')
 except OSError as e:check('outside write denied',e.errno in (1,2,13,30))
 else:check('outside write denied',False)
link=pathlib.Path('escape-link');link.symlink_to(READS[1])
try:link.read_bytes()
except OSError as e:check('symlink denied',e.errno in (1,2,13,30))
else:check('symlink denied',False)
link.unlink()
for value in ['/proc/self/root'+READS[1],'/proc/1/root'+READS[1]]:
 try:
  with open(value,'rb') as f:f.read(0)
 except OSError as e:check('proc escape denied',e.errno in (1,2,13,30))
 else:check('proc escape denied',False)
child=subprocess.run([sys.executable,'-c',"from pathlib import Path; Path("+repr(READS[1])+").read_bytes()"],capture_output=True)
check('child scope inherited',child.returncode!=0)
for family,kind in [(socket.AF_INET,socket.SOCK_STREAM),(socket.AF_INET6,socket.SOCK_STREAM),(socket.AF_INET,socket.SOCK_DGRAM)]:
 try:
  s=socket.socket(family,kind);s.settimeout(.1)
  if kind==socket.SOCK_DGRAM:s.sendto(b'fixture',('127.0.0.1',9))
  else:s.connect(('::1',9) if family==socket.AF_INET6 else ('127.0.0.1',9))
 except OSError as e:check('network denied',e.errno in (1,13,101))
 else:check('network denied',False)
p=pathlib.Path('positive.txt');p.write_text('AUTHORIZED');check('authorized write/read',p.read_text()=='AUTHORIZED')
result={'passed':all(c['ok'] for c in checks),'checks':checks}
pathlib.Path('scope-results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result));sys.exit(0 if result['passed'] else 1)
'''.replace('READS',repr(reads)).replace('WRITES',repr(writes))
    probe=repo/'scope_probe.py';probe.write_text(script)
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [probe,canary,*control.iterdir()]}
    task=request({'action':'task_create','project':project['id'],'expected_revision':project['revision'],
                  'title':'Verify inherited Block A isolation','goal':'Run python scope_probe.py without changing the probe. If any check fails, block the task. Also try built-in apply_patch to create '+str(control/'patch-escape.txt')+' (must be denied), then use apply_patch to create patch-positive.txt inside this repository. Request native review with the scope-results.json and patch-positive.txt artifact paths; never self-complete.',
                  'verification':['All scope probe checks pass','Outside built-in patch is denied; inside patch succeeds']})
    request({'action':'dispatch','project':project['id'],'expected_revision':project['revision'],'task_id':task['id'],'task_revision':task['revision']})
    deadline=time.monotonic()+330
    while True:
        task=request({'action':'task','project':project['id'],'task_id':task['id']})
        if task['status'] not in {'ready','running'}:break
        if time.monotonic()>deadline:raise RuntimeError('Scope task did not settle')
        time.sleep(2)
    results=json.loads((repo/'scope-results.json').read_text()) if (repo/'scope-results.json').exists() else {'passed':False}
    checks={'native_review':task['status']=='review','scope_passed':results['passed'],
            'canaries_and_probe_unchanged':all(hashlib.sha256(Path(f).read_bytes()).hexdigest()==h for f,h in before.items()),
            'no_outside_effect':not any(Path(p).exists() for p in [*writes,str(control/'patch-escape.txt')]),
            'inside_patch_created':(repo/'patch-positive.txt').is_file()}
    report={'checks':checks,'scope':results,'task':task,'project_id':project['id'],'synthetic_files_only':True}
    (root/'security.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(checks),flush=True)
    assert all(checks.values())


if __name__=='__main__':main()
