"""Opt-in real headless QA; host compositor is read-only, no speakers/user files.
Run from repository or materialized pilot with --installed and --output (in /tmp).
"""
import argparse
import base64
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--installed',type=Path,default=Path.home()/'.local/share/argos-hermes-pilot');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    out=args.output.resolve()
    if not out.is_relative_to('/tmp') or out.exists():raise ValueError('Choose a new /tmp evidence directory')
    out.mkdir(mode=0o700)
    source=Path(__file__).resolve().parents[2]
    package=types.ModuleType('argos_visual_qa');package.__path__=[str(source/'ui-workbench/runtime')];sys.modules[package.__name__]=package
    m=importlib.import_module('argos_visual_qa.desktop');v=importlib.import_module('argos_visual_qa.desktop_visual');v.PILOT=source
    config=json.loads((args.installed/'installation.json').read_text())
    toolroot=Path.home()/'.local/share/argos-desktop/visual-1'
    config['desktop']['visual']={'root':str(toolroot),'manifest_sha256':hashlib.sha256((toolroot/'.argos-files.json').read_bytes()).hexdigest()}
    config['desktop']['state']=str(out/'scopes');(out/'private-config.json').write_text(json.dumps(config));(out/'private-config.json').chmod(0o600)
    d=m.Desktop(lambda _:None,config_path=out/'private-config.json');other=None
    report={'checks':[],'audio':False,'host_input_injected':False,'samples':0,'focus_changes':0,'cursor_changes':0,'focus_events':0,'focus_event_transitions':0,'max_rss_kib':0,'max_sample_gap_ms':0};stop=threading.Event();pids=set();sample_errors=[]
    def check(name,ok):
        report['checks'].append({'name':name,'ok':bool(ok)});print(name,bool(ok),flush=True)
        if not ok:raise AssertionError(name)
    def observe(scope):return d.request({'action':'observe','scope':scope})
    def state(scope):return json.loads((d.scopes[scope]['home']/'work/result.json').read_text())
    def wait(job,controller=d):
        while job['state']=='running':time.sleep(.03);job=controller.request({'action':'status','job':job['id']})
        return job
    def act(scope,actions):
        o=observe(scope);job=wait(d.request({'action':'visual_act','scope':scope,'snapshot':o['snapshot'],'actions':actions}))
        if job['state']!='completed':raise AssertionError(job)
        return job
    def launch(profile='pad',**kwargs):
        p=d.request({'action':'visual_open','application':profile,**kwargs});check('scope consent precedes launch',p['status']=='needs_approval')
        return d.request({'action':'confirm','proposal_id':p['proposal_id'],'approve':True},user=True)
    def capture(o,name):(out/name).write_bytes(base64.b64decode(o['data_url'].split(',')[1]))
    def sample():
        previous=None;last_sample=None
        while not stop.is_set():
            try:
                current=d.access.hypr.seat()
                if previous:
                    report['focus_changes']+=current['focus']!=previous['focus'];report['cursor_changes']+=current['cursor']!=previous['cursor']
                previous=current;report['samples']+=1
                now=time.monotonic()
                if last_sample is not None:report['max_sample_gap_ms']=max(report['max_sample_gap_ms'],round((now-last_sample)*1000,2))
                last_sample=now
                rows={}
                for p in Path('/proc').glob('[0-9]*'):
                    try:
                        stat=(p/'stat').read_text().rsplit(')',1)[1].split();rows[int(p.name)]=(int(stat[1]),int(stat[21])*os.sysconf('SC_PAGE_SIZE')//1024)
                    except (OSError,ValueError):pass
                selected={s['child'].pid for controller in (d,other) if controller for s in controller.scopes.values() if s['child'] and s['child'].poll() is None}
                for _ in range(8):selected.update(pid for pid,(parent,rss) in rows.items() if parent in selected)
                pids.update(selected);report['max_rss_kib']=max(report['max_rss_kib'],sum(rows.get(pid,(0,0))[1] for pid in selected))
            except Exception as error:sample_errors.append(type(error).__name__)
            stop.wait(.05)
    def events():
        path=Path(os.environ['XDG_RUNTIME_DIR'])/'hypr'/os.environ['HYPRLAND_INSTANCE_SIGNATURE']/'.socket2.sock'
        last_focus=(d.access.hypr.query('activewindow').get('address') or '').removeprefix('0x')
        with socket.socket(socket.AF_UNIX) as sock:
            sock.settimeout(.2);sock.connect(str(path));buffer=b''
            while not stop.is_set():
                try:data=sock.recv(8192)
                except TimeoutError:continue
                if not data:break
                buffer+=data
                while b'\n' in buffer:
                    line,buffer=buffer.split(b'\n',1)
                    if line.startswith(b'activewindowv2>>'):
                        report['focus_events']+=1
                        focused=line.split(b'>>',1)[1].decode().removeprefix('0x')
                        report['focus_event_transitions']+=focused!=last_focus
                        last_focus=focused
    watcher=threading.Thread(target=sample);listener=threading.Thread(target=events);watcher.start();listener.start()
    try:
        started=time.monotonic();o=launch();report['launch_seconds']=time.monotonic()-started;s=o['scope'];capture(o,'initial.png')
        check('private output and canvas window observed',o['geometry']['app_id']=='pad.py' and o['width']==1000)
        actions=[{'type':'click','x':100,'y':120},{'type':'text','text':'ARGOS independiente'},{'type':'click','x':110,'y':200},{'type':'scroll','x':700,'y':150,'steps':3,'direction':'down'},{'type':'drag','x':120,'y':370,'to_x':720,'to_y':460}]
        request={'action':'visual_act','scope':s,'snapshot':o['snapshot'],'actions':actions};job=wait(d.request(request));report['sequence_seconds']=job['seconds']
        check('actual visual batch completes',job['state']=='completed');result=state(s);report['canvas']=result
        check('text click scroll and drag verified by application',result['applied']=='ARGOS independiente' and result['scroll']==3 and result['dropped'] and not result['dragging'])
        check('duplicate delivery does not replay',d.request(request)['id']==job['id'] and state(s)==result)
        capture(observe(s),'verified.png')
        # Inspect boundaries inside the very same bwrap mount/network profile.
        code="import json,os,socket;from pathlib import Path;s=socket.socket();s.settimeout(.2);network=False\ntry:s.connect(('1.1.1.1',443));network=True\nexcept OSError:pass\nprint(json.dumps({'network':network,'host_runtime':Path('/run/user').exists(),'input':Path('/dev/input').exists(),'gpu':Path('/dev/dri').exists(),'bus':Path('/run/dbus').exists(),'host_home':Path('/home/iago').exists(),'proc_count':len(list(Path('/proc').glob('[0-9]*')))}))"
        boundary=json.loads(m.run_json(d.visual.sandbox(d.scopes[s],['/usr/bin/python3','-c',code]),d.visual.environment(d.scopes[s]),raw=True));report['boundary']=boundary
        check('no host devices bus home network or process namespace',not any(boundary[k] for k in ('network','host_runtime','input','gpu','bus','host_home')) and boundary['proc_count']<8)
        # Positive independent-input control: a second disposable seat receives its
        # own typing while ARGOS drags. No synthetic input goes to the host seat.
        second=json.loads(json.dumps(config));second['desktop']['state']=str(out/'recipient-scopes');(out/'recipient-config.json').write_text(json.dumps(second))
        other=m.Desktop(lambda _:None,config_path=out/'recipient-config.json');p=other.request({'action':'visual_open','application':'pad'});u=other.request({'action':'confirm','proposal_id':p['proposal_id'],'approve':True},user=True)
        o=observe(s);running=d.request({'action':'visual_act','scope':s,'snapshot':o['snapshot'],'actions':[{'type':'drag','x':720,'y':460,'to_x':800,'to_y':500,'duration_ms':3000}]})
        check('long action returns without blocking conversation slot',running['state']=='running')
        timer=time.monotonic();d.request({'action':'status'});report['status_ms']=(time.monotonic()-timer)*1000
        independent=wait(other.request({'action':'visual_act','scope':u['scope'],'snapshot':u['snapshot'],'actions':[{'type':'click','x':100,'y':120},{'type':'text','text':'USER independent input'},{'type':'move','x':250,'y':200}]}),other)
        check('independent seat receives typing during ARGOS drag',independent['state']=='completed' and d.request({'action':'status','job':running['id']})['state']=='running')
        recipient=json.loads((other.scopes[u['scope']]['home']/'work/result.json').read_text());check('input arrives exclusively at intended seats',recipient['text']=='USER independent input' and state(s)['text']=='ARGOS independiente')
        check('drag completes independently',wait(running)['state']=='completed');other.close();other=None
        act(s,[{'type':'click','x':100,'y':120},{'type':'keys','keys':['ctrl','a']},{'type':'text','text':'Atajo verificado'}]);check('key combination edits intended canvas',state(s)['text']=='Atajo verificado')
        act(s,[{'type':'down','x':100,'y':120},{'type':'move','x':140,'y':120},{'type':'up'}]);check('balanced mouse press and release accepted',True)
        o=observe(s);cancel=d.request({'action':'visual_act','scope':s,'snapshot':o['snapshot'],'actions':[{'type':'drag','x':800,'y':500,'to_x':100,'to_y':350,'duration_ms':3000}]});d.request({'action':'cancel','job':cancel['id']});cancel=wait(cancel);report['cancel']={k:cancel[k] for k in ('state','completed_steps','held_input_released','seconds')}
        check('cancel releases held pointer without touching host',cancel['state']=='cancelled' and cancel['held_input_released']);time.sleep(.1);check('application no longer dragging after cancellation',not state(s)['dragging'])
        old=observe(s);act(s,[{'type':'text','text':' changed'}])
        try:d.request({'action':'visual_act','scope':s,'snapshot':old['snapshot'],'actions':[{'type':'click','x':100,'y':200}]});denied=False
        except PermissionError:denied=True
        check('stale observation rejected',denied)
        home=d.scopes[s]['home'];d.request({'action':'release','scope':s});check('release removes session files',not home.exists())
        for scale in (1.5,2):
            o=launch(scale=scale,outputs=2);s=o['scope'];check('two virtual monitors at scale '+str(scale),len(o['geometry']['outputs'])==2 and o['width']==1000)
            act(s,[{'type':'click','x':100,'y':120},{'type':'text','text':'Scaled input'},{'type':'drag','x':120,'y':370,'to_x':720,'to_y':460}]);check('scaled coordinate mapping text and drag '+str(scale),state(s)['text']=='Scaled input' and state(s)['dropped']);capture(observe(s),'scale-'+str(scale)+'.png');d.request({'action':'release','scope':s})
        # Real useful application, copies only; API receives paths checked by Files.
        (out/'left.txt').write_text('Left original\n');(out/'right.txt').write_text('Right original\n')
        class Files:
            def read(self,path):
                path=Path(path)
                if path not in (out/'left.txt',out/'right.txt'):raise PermissionError('Outside QA files')
                return {'editable':True,'text':path.read_text()}
        d.files=Files();o=launch('comparison',left=str(out/'left.txt'),right=str(out/'right.txt'),scale=1.5,outputs=2);s=o['scope'];time.sleep(.3);capture(observe(s),'meld-before.png')
        act(s,[{'type':'click','x':100,'y':105},{'type':'keys','keys':['ctrl','a']},{'type':'text','text':'Edited disposable copy'},{'type':'keys','keys':['ctrl','s']}]);time.sleep(.1)
        check('Meld actual saved copy edited', (d.scopes[s]['home']/'work/left.txt').read_text()=='Edited disposable copy\n')
        check('Meld originals preserved',(out/'left.txt').read_text()=='Left original\n');capture(observe(s),'meld-after.png')
        # Application closed and idle lease end fail closed without resumption.
        d.visual.ipc(d.scopes[s],0,'[app_id="org.gnome.Meld"] kill');time.sleep(.4)
        try:observe(s);closed=False
        except (OSError,PermissionError,RuntimeError):closed=True
        check('closed application rejects observations',closed);d.request({'action':'release','scope':s})
        o=launch();s=o['scope'];a={'action':'visual_act','scope':s,'snapshot':o['snapshot'],'actions':[{'type':'click','x':100,'y':120}]}
        d.visual.ipc(d.scopes[s],0,'output HEADLESS-1 scale 2');time.sleep(.1)
        rejected=wait(d.request(a));check('layout changed after observation rejects delivery',rejected['state']=='failed' and rejected['completed_steps']==0);d.request({'action':'release','scope':s})
        o=launch();s=o['scope'];act(s,[{'type':'click','x':100,'y':120}]);o=observe(s)
        typing=d.request({'action':'visual_act','scope':s,'snapshot':o['snapshot'],'actions':[{'type':'text','text':'x'*1200}]});d.request({'action':'cancel','job':typing['id']});typing=wait(typing)
        check('interrupted keyboard destroys private seat',typing['state']=='cancelled' and d.scopes[s]['released'] and typing['held_input_released'])
        o=launch();s=o['scope'];lease=d.scopes[s]['home']/'run/lease';os.utime(lease,(time.time()-310,)*2);time.sleep(.5)
        check('idle compositor and application terminate',d.scopes[s]['child'].poll() is not None)
        d.close();restarted=m.Desktop(lambda _:None,config_path=out/'private-config.json');check('restart does not restore grants or replay input',not restarted.scopes and not restarted.jobs);restarted.close()
    finally:
        d.close()
        if other:other.close()
        stop.set();watcher.join(3);listener.join(3)
        report['sampling_errors']=sample_errors;report['sample_period_target_ms']=50
        report['remaining_child_pids']=[p for p in pids if Path('/proc',str(p)).exists()]
        report['limits']='Host sampling plus compositor focus events; concurrent synthetic input validated on a second disposable seat, not physical human input or games.'
        (out/'execution.json').write_text(json.dumps(report,indent=2)+'\n')
        (out/'private-config.json').unlink(missing_ok=True);(out/'recipient-config.json').unlink(missing_ok=True)
    check('all sampled child processes released',not report['remaining_child_pids'])
    (out/'execution.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out)

if __name__=='__main__':main()
