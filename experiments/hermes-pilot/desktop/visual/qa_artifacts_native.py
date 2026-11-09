"""Real installed applications, saved work and native projects; /tmp-only opt-in QA."""
import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

P=Path(__file__).resolve().parents[2]
if not str(P).startswith('/tmp/argos-desktop-qa/'):raise RuntimeError('Materialize in the disposable QA installation first')
config=json.loads((P/'installation.json').read_text())
if not config.get('projects_enabled') or not config.get('project_roots') or any(not str(Path(p).resolve()).startswith('/tmp/argos-desktop-qa/home/') for p in config['project_roots']) or not Path(config['project_state']).resolve().is_relative_to(P):raise RuntimeError('QA projects must stay under disposable roots')
sys.path[:0]=[str(P/'ui-workbench'),str(P)]
from runtime.desktop import Desktop,run_json
from runtime.projects import Projects
from runtime.workspace_broker import Files
out=P/'reports/desktop-artifacts-native';out.mkdir(parents=True,exist_ok=True)
report={'checks':[],'profiles':{},'host_input':False,'audio':False,'max_rss_kib':0};d=None
sampling=threading.Event();sampled_pids=set()
def sample_resources():
    while not sampling.wait(.05):
        if d is None:continue
        try:
            rows={}
            for proc in Path('/proc').glob('[0-9]*'):
                try:
                    parts=(proc/'stat').read_text().rsplit(')',1)[1].split();rows[int(proc.name)]=(int(parts[1]),int(parts[21])*os.sysconf('SC_PAGE_SIZE')//1024)
                except (OSError,ValueError):pass
            selected={s['child'].pid for s in list(d.scopes.values()) if s.get('child') and s['child'].poll() is None}
            for _ in range(8):selected.update(pid for pid,(parent,rss) in rows.items() if parent in selected)
            sampled_pids.update(selected);report['max_rss_kib']=max(report['max_rss_kib'],sum(rows.get(pid,(0,0))[1] for pid in selected))
        except RuntimeError:pass
thread=threading.Thread(target=sample_resources,daemon=True);thread.start()

def check(name,ok):
    report['checks'].append({'name':name,'ok':bool(ok)});print(name,bool(ok),flush=True)
    if not ok:raise AssertionError(name)
def controller():return Desktop(lambda _:None,projects=Projects(lambda _:None),files=Files({'QA':Path('/tmp/argos-desktop-qa/home')}))
def approve(q):return d.request({'action':'confirm','proposal_id':q['proposal_id'],'approve':True},user=True)
def act(scope,actions):
    view=d.request({'action':'observe','scope':scope});j=d.request({'action':'visual_act','scope':scope,'snapshot':view['snapshot'],'actions':actions})
    while j['state']=='running':time.sleep(.03);j=d.request({'action':'status','job':j['id']})
    if j['state']!='completed':raise AssertionError(j)
    return j
def capture(scope,name):
    view=d.request({'action':'observe','scope':scope});(out/name).write_bytes(base64.b64decode(view['data_url'].split(',')[1]));return view

def main():
    global d
    d=controller()
    for name in ('meld-editor','thunar'):
        result=approve(d.request({'action':'enable_application','application':name}));check(name+' real enablement',result['validated'])
        report['profiles'][name]={'revision':d.profiles.selected(name)['revision'],'startup_capture':True}
    p=d.projects;proposal=p.request({'action':'propose','name':'Desktop artifact native '+str(time.time_ns()),'brief':{'objective':'Test private document delivery','requirements':['Preserve original files'],'decisions':['Offline'],'verification':['Read back approved output']}})
    project=p.request({'action':'confirm','proposal_id':proposal['id'],'approve':True},user=True)['project'];report['project']={'id':project['id'],'path':project['path']}
    task=p.request({'action':'task_create','project':project['id'],'expected_revision':project['revision'],'kind':'desktop','title':'Prepare document','goal':'Edit imported copy through real Meld','verification':['Export exact reviewed file']});bound={'project':project['id'],'task_id':task['id']}
    original=Path(project['path'])/'original.md';original.write_text('Original must remain unchanged.\n');original_hash=hashlib.sha256(original.read_bytes()).hexdigest()
    q=d.request({'action':'project_open',**bound,'application':'meld-editor','imports':[{'path':str(original),'name':'document.md'}]});check('scope proposal has no launch',not any(not s['released'] for s in d.scopes.values()))
    started=time.monotonic();view=approve(q);scope=view['scope'];session=view['session_id'];report['meld_launch_seconds']=time.monotonic()-started
    try:
        boundary=json.loads(run_json(d.visual.sandbox(d.scopes[scope],['/usr/bin/python3','-c',"import os,json,socket;from pathlib import Path;s=socket.socket();s.settimeout(.2)\ntry:s.connect(('1.1.1.1',443));network=True\nexcept OSError:network=False\nprint(json.dumps({'network':network,'host_input':Path('/dev/input').exists(),'host_home':Path('/home/iago').exists(),'host_bus':Path('/run/user/1000/bus').exists(),'gpu':Path('/dev/dri').exists()}))"]),d.visual.environment(d.scopes[scope]),raw=True))
        report['boundary']=boundary;check('real app has no host authority',not any(boundary.values()))
        text='Requirements: index STL and OBJ; preserve originals; searchable tags.\n'
        result=act(scope,[{'type':'click','x':150,'y':180},{'type':'keys','keys':['ctrl','a']},{'type':'text','text':text.rstrip('\n')},{'type':'keys','keys':['ctrl','s']}]);report['meld_edit_seconds']=result['seconds'];capture(scope,'meld-saved.png')
        scan=d.request({'action':'artifacts',**bound,'session_id':session});artifact=next(a for a in scan['artifacts'] if a['path']=='document.md');check('saved artifact detected from app filesystem',artifact['changed'] and artifact['text']==text)
        check('imported original unchanged',hashlib.sha256(original.read_bytes()).hexdigest()==original_hash)
        export={'action':'export',**bound,'session_id':session,'path':'document.md','sha256':artifact['sha256'],'destination':'docs/requirements.md'}
        pending=d.request(export);check('unapproved output remains absent',not (Path(project['path'])/'docs/requirements.md').exists())
        # Terminate the actual app inside its own PID namespace, not its host PID.
        pid=d.visual.geometry(d.scopes[scope])['pid']
        rows={}
        for proc in Path('/proc').glob('[0-9]*'):
            try:rows[int(proc.name)]=int((proc/'stat').read_text().rsplit(')',1)[1].split()[1])
            except (OSError,ValueError):pass
        descendants={d.scopes[scope]['child'].pid}
        for _ in range(8):descendants.update(i for i,parent in rows.items() if parent in descendants)
        candidates=[]
        for host_pid in descendants:
            try:
                status=(Path('/proc')/str(host_pid)/'status').read_text()
                ns=next(line.split()[1:] for line in status.splitlines() if line.startswith('NSpid:'))
                if len(ns)>1 and int(ns[-1])==pid:candidates.append(host_pid)
            except (OSError,StopIteration):pass
        check('fault injection identifies only owned application',len(candidates)==1)
        os.kill(candidates[0],signal.SIGKILL)
        time.sleep(.4);check('unexpected application close ends its supervisor',d.scopes[scope]['child'].poll() is not None)
        d.close();d=controller();check('restart restores no permission or input',not d.scopes and not d.access.pending)
        scan=d.request({'action':'artifacts',**bound,'session_id':session});check('restart recovers exact saved document',next(a for a in scan['artifacts'] if a['path']=='document.md')['sha256']==artifact['sha256'])
        check('restart does not export pending proposal',(Path(project['path'])/'docs/requirements.md').exists() is False)
        view=approve(d.request({'action':'project_open',**bound,'application':'meld-editor','session_id':session}));scope=view['scope'];capture(scope,'meld-reopened.png')
        receipt=approve(d.request(export));check('approved export matches observed artifact',hashlib.sha256(Path(receipt['path']).read_bytes()).hexdigest()==artifact['sha256']);report['receipt']=receipt['receipt']
        stamp=Path(receipt['path']).stat().st_mtime_ns;duplicate=d.request(export);check('duplicate does not rewrite',duplicate['status']=='already_exported' and Path(receipt['path']).stat().st_mtime_ns==stamp)
        context=d.request({'action':'artifacts',**bound});check('native task owns artifact receipt',len(context['exports'])==1 and context['task']['artifacts'][0]['origin']=='desktop')
    finally:
        for s in list(d.scopes.values()):d.release(s)
    # A second real application uses exactly the same profile, capture/input and
    # import/export path, without app-specific controller code.
    task=p.request({'action':'task_create','project':project['id'],'expected_revision':project['revision'],'kind':'desktop','title':'Copy document with Thunar','goal':'Duplicate a private imported document','verification':['Export copied text; original unchanged']});bound={'project':project['id'],'task_id':task['id']}
    view=approve(d.request({'action':'project_open',**bound,'application':'thunar','imports':[{'path':str(original),'name':'source.md'}]}));scope=view['scope'];session=view['session_id']
    act(scope,[{'type':'click','x':240,'y':110},{'type':'keys','keys':['ctrl','c']},{'type':'keys','keys':['ctrl','v']}]);time.sleep(.2)
    scan=d.request({'action':'artifacts',**bound,'session_id':session});copy=next(a for a in scan['artifacts'] if a.get('changed'))
    check('Thunar creates a genuine copied artifact',copy['sha256']==original_hash and copy['path']!='source.md');capture(scope,'thunar-copy.png')
    result=approve(d.request({'action':'export',**bound,'session_id':session,'path':copy['path'],'sha256':copy['sha256'],'destination':'docs/thunar-copy.md'}));check('Thunar export uses same native artifact contract',Path(result['path']).read_bytes()==original.read_bytes())
    report['profiles']['thunar']['copy_and_export']=True
    d.request({'action':'release','scope':scope})

try:main()
except Exception as e:report['failure']=str(e);raise
finally:
    if d:d.close()
    sampling.set();thread.join(timeout=2);time.sleep(.2)
    report['remaining_sampled_pids']=[pid for pid in sampled_pids if Path('/proc',str(pid)).exists()]
    (out/'execution.json').write_text(json.dumps(report,indent=2)+'\n')
