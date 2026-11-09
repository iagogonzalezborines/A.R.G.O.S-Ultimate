"""Real Hyprland/AT-SPI isolation checks on disposable windows only.

Requires explicit foreground-test consent. This harness may focus its windows and
inject bounded test events into its own foreground receiver. Those operations are
NOT exposed by ARGOS. Never run while someone needs uninterrupted foreground input.
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import types

BASE=Path(__file__).resolve().parents[1]
pkg=types.ModuleType('argos_background_qa');pkg.__path__=[str(BASE/'ui-workbench/runtime')];sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+'.desktop')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--foreground-consent',action='store_true');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.foreground_consent:raise SystemExit('Explicit foreground test authorization required')
    args.output.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='argos-background-',dir='/tmp'));work.chmod(0o700)
    config=json.loads((Path.home()/'.local/share/argos-hermes-pilot/installation.json').read_text())
    config['desktop']['state']=str(work/'scopes');(work/'config.json').write_text(json.dumps(config));(work/'config.json').chmod(0o600)
    report={'checks':[],'input':'synthetic compositor events confined to QA receiver; no claim of human input coverage','work':str(work)}
    d=m.Desktop(lambda e:None,config_path=work/'config.json');env={**d.env,'NO_AT_BRIDGE':'0','GDK_BACKEND':'wayland','GTK_MODULES':'gail:atk-bridge'}
    children=[];original=d.access.hypr.seat();foreground=None
    def check(name,ok):
        report['checks'].append({'name':name,'ok':bool(ok)});print(name,bool(ok),flush=True)
        if not ok:raise AssertionError(name)
    def spawn(name):
        p=subprocess.Popen(['/usr/bin/python3',str(BASE/'desktop/qa_semantic_app.py'),str(work/name)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);children.append(p)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            rows=d.request({'action':'discover'})['windows'];matches=[w for w in rows if w['pid']==p.pid]
            if matches:return p,matches[0]
            time.sleep(.1)
        raise RuntimeError('Fixture did not register')
    def dispatch(code):
        r=subprocess.run(['/usr/bin/hyprctl','dispatch',code],env=d.env,capture_output=True,text=True,timeout=2)
        if r.returncode or 'error' in r.stdout.lower():raise RuntimeError('QA compositor operation refused: '+r.stdout[:150])
    def focus(pid):
        address=d.access.hypr.window(pid)['address'];dispatch('hl.dsp.focus({window="address:'+address+'"})');time.sleep(.1)
        check('QA focus verified',d.access.hypr.seat()['focus']==address);return address
    def events(name):return json.loads((work/name/'events.json').read_text())
    def mutate(v,op,name,text=None):
        e=next(e for e in v['elements'] if (e['name']==name if name else op in e['actions']))
        request={'action':'prepare','scope':v['scope'],'snapshot':v['snapshot'],'operation':op,'ref':e['ref']}
        if text is not None:request['text']=text
        p=d.request(request)
        # A real trusted approval boundary, using the harness as the user.
        try:d.request({'action':'confirm','proposal_id':p['proposal_id'],'approve':True});raise AssertionError('model approved')
        except PermissionError:pass
        job=d.request({'action':'confirm','proposal_id':p['proposal_id'],'approve':True},user=True)
        d.jobs[job['id']]['done'].wait(14);return d.request({'action':'status','job':job['id']})
    try:
        target,candidate=spawn('target')
        proposal=d.request({'action':'select','candidate':candidate['candidate']});check('model selection requires read approval',proposal['status']=='needs_approval')
        v=d.request({'action':'confirm','proposal_id':proposal['proposal_id'],'approve':True},user=True)
        foreground,_=spawn('foreground');fa=focus(foreground.pid)
        # Moving only our disposable windows exercises both physical outputs.
        geometry=d.access.hypr.window(target.pid);report['outputs']=d.access.hypr.layout()
        fgmon=d.access.hypr.window(foreground.pid)['monitor']
        other=next((o for o in report['outputs'] if o['id']!=fgmon),None)
        if other:
            dispatch('hl.dsp.window.move({monitor="'+other['name']+'",follow=false,window="address:'+geometry['address']+'"})')
            time.sleep(.2)
            report['different_outputs']=d.access.hypr.window(target.pid)['monitor']!=d.access.hypr.window(foreground.pid)['monitor']
            check('target and foreground on different outputs',report['different_outputs'])
        focus(foreground.pid)
        before=d.access.hypr.seat();ev=events('foreground')
        v=d.request({'action':'observe','scope':v['scope']})
        job=mutate(v,'replace_text','Draft','Background draft: models STL and OBJ')
        report['text_job']={k:job.get(k) for k in ('state','seconds','verified_text','input_observation')}
        check('background replacement verified',job['state']=='completed' and job.get('verified_text'))
        check('foreground input receiver untouched',events('foreground')==ev)
        check('static focus and cursor unchanged',d.access.hypr.seat()==before)
        v=job['result'];job=mutate(v,'click','Apply draft');check('background button delivered',job['state']=='completed' and events('target')['applied']==1)
        check('foreground has no unintended key/button events',events('foreground')==ev)
        v=job['result'];noise_stop=threading.Event();errors=[]
        fg=d.access.hypr.window(foreground.pid);x,y=fg['at'];x+=fg['size'][0]//2;y+=fg['size'][1]//2
        def noise():
            try:
                for i in range(12):
                    if noise_stop.is_set():break
                    dispatch('hl.dsp.send_shortcut({mods="",key="z",window="address:'+fa+'"})')
                    dispatch(f'hl.dsp.cursor.move({{x={x+i%2},y={y}}})');time.sleep(.035)
            except Exception as e:errors.append(str(e))
        thread=threading.Thread(target=noise);thread.start()
        job=mutate(v,'replace_text','Draft','Concurrent background text')
        thread.join();check('concurrent semantic edit succeeds',job['state']=='completed' and not errors)
        fge=events('foreground');tge=events('target')
        check('foreground receives test keys only',fge['keys']-ev['keys']==12 and fge['text']=='z'*12)
        check('background target receives no physical events',tge['keys']==0 and tge['buttons']==0 and tge['text']=='Concurrent background text')
        report['input_counts']={'foreground':fge,'target':tge}
        # Capture source-owned widget rendering, not a screen/portal capture.
        time.sleep(.2)
        import shutil
        for name in ('foreground','target'):
            if (work/name/'widget-render.png').exists():shutil.copyfile(work/name/'widget-render.png',args.output/(name+'-widget.png'))
        v=job['result'];p=d.request({'action':'prepare','scope':v['scope'],'snapshot':v['snapshot'],'ref':next(e['ref'] for e in v['elements'] if e['name']=='Draft'),'operation':'replace_text','text':'must not happen'})
        d.request({'action':'stop'});r=d.request({'action':'confirm','proposal_id':p['proposal_id'],'approve':True},user=True)
        check('emergency stop invalidates pending effects',r['status']=='cancelled' and events('target')['text']=='Concurrent background text')
        v=d.request({'action':'observe','scope':v['scope']});job=mutate(v,'click','Options')
        report['menu']={'state':job['state'],'error':job.get('error'),'input_observation':job.get('input_observation')}
        # Menu success is recorded as observed, never generalized across toolkits.
        if job['state']=='completed':
            menu_items=[e['name'] for e in job['result']['elements']];report['menu']['items']=menu_items
            if 'Mark draft' in menu_items:
                marked=mutate(job['result'],'click','Mark draft');check('native menu item activated',marked['state']=='completed' and events('target')['marked']==1)
        d.request({'action':'release','scope':v['scope']});check('release leaves user-owned target alive',target.poll() is None)
        target.terminate();target.wait(timeout=2)
        # Actual existing application, copies only: a separate generic grant permits
        # editing a copy; the original comparison profile remains read-only.
        class Files:
            def read(self,path):return {'editable':True,'truncated':False,'text':Path(path).read_text()}
        d.files=Files();left=work/'left.txt';right=work/'right.txt';left.write_text('Original left\n');right.write_text('Original right\n')
        comparison=d.request({'action':'open','application':'comparison','left':str(left),'right':str(right)},user=True)
        pid=d.scopes[comparison['scope']]['pid'];candidate=next(w for w in d.request({'action':'discover'})['windows'] if w['pid']==pid)
        v=d.request({'action':'select','candidate':candidate['candidate']},user=True);focus(foreground.pid)
        v=d.request({'action':'observe','scope':v['scope']});ev=events('foreground');job=mutate(v,'replace_text',None,'Edited disposable Meld draft')
        check('real Meld text replacement verified',job['state']=='completed' and job.get('verified_text'))
        check('Meld edit preserves foreground receiver',events('foreground')==ev)
        check('source files unchanged',left.read_text()=='Original left\n' and right.read_text()=='Original right\n')
        report['meld']={k:job.get(k) for k in ('state','seconds','verified_text','input_observation')}
        d.request({'action':'release','scope':comparison['scope']})
        try:d.request({'action':'observe','scope':v['scope']});raise AssertionError('closed window accepted')
        except (OSError,PermissionError):check('closed application rejected',True)
        d.request({'action':'release','scope':v['scope']})
        calc=d.request({'action':'open','application':'calculator'},user=True);focus(foreground.pid);ev=events('foreground');before=d.access.hypr.seat()
        calc=d.request({'action':'observe','scope':calc['scope']});job=d.request({'action':'act','scope':calc['scope'],'snapshot':calc['snapshot'],'buttons':['AC','1','2','+','2','5','=']})
        d.jobs[job['id']]['done'].wait(14);job=d.request({'action':'status','job':job['id']})
        check('calculator background result 37',job['state']=='completed' and job['result']['texts'][0]['text']=='37')
        check('calculator preserves focus cursor and receiver',before==d.access.hypr.seat() and events('foreground')==ev)
        calc=d.request({'action':'observe','scope':calc['scope']});job=d.request({'action':'act','scope':calc['scope'],'snapshot':calc['snapshot'],'buttons':['1']*16});d.request({'action':'cancel','job':job['id']});d.jobs[job['id']]['done'].wait(14)
        check('real running sequence cancels',d.jobs[job['id']]['state']=='cancelled')
        report['cancelled_steps']=d.jobs[job['id']]['completed_steps']
        report['held_input']=False;report['physical_backend']='not implemented or advertised'
    except Exception as error:
        report['failure']=type(error).__name__+': '+str(error);raise
    finally:
        d.close()
        for child in children:
            if child.poll() is None:child.terminate();child.wait(timeout=3)
        # Explicit test-session restoration only, never a background-adapter workaround.
        live={w['address'] for w in d.access.hypr.query('clients')}
        if original['focus'] in live:
            dispatch('hl.dsp.focus({window="address:'+original['focus']+'"})')
        dispatch(f"hl.dsp.cursor.move({{x={original['cursor']['x']},y={original['cursor']['y']}}})")
        (args.output/'execution.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
