#!/usr/bin/env python3
"""Run offline private toolchain smoke checks before enabling Engineering capabilities."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import signal
import resource
import os
import subprocess
import sys
import tempfile
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'experiments/hermes-pilot'))
from adaptive.specialized import SPECS,digest_tree


def sandbox(pilot,workspace,command):
    return ['bwrap','--unshare-all','--die-with-parent','--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib','/lib64',
            '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--ro-bind',str(pilot/'tools'),str(pilot/'tools'),'--bind',str(workspace),'/workspace','--clearenv',
            '--setenv','HOME','/tmp','--setenv','PATH','/usr/bin:/bin','--setenv','OPENBLAS_NUM_THREADS','2','--setenv','OMP_NUM_THREADS','2','--chdir','/workspace','--',*command]


def run(pilot,workspace,command):
    start=time.monotonic()
    with tempfile.TemporaryFile() as log:
        def bounded():
            resource.setrlimit(resource.RLIMIT_CPU,(90,90));resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
        child=subprocess.Popen(sandbox(pilot,workspace,command),stdout=log,stderr=log,start_new_session=True,preexec_fn=bounded)
        peak_rss=0;previous_sample=time.monotonic();max_gap=0
        while True:
            now=time.monotonic();max_gap=max(max_gap,now-previous_sample);previous_sample=now
            peak_rss=max(peak_rss,tree_rss(child.pid))
            pid,status,usage=os.wait4(child.pid,os.WNOHANG)
            if pid:
                code=os.waitstatus_to_exitcode(status);child.returncode=code;break
            if time.monotonic()-start>120:os_kill(child);raise RuntimeError('Toolchain exceeded 120 seconds')
            time.sleep(.05)
        log.seek(0);output=log.read(16000).decode('utf-8','replace')
    if code:raise RuntimeError(output[-4000:])
    return {'exit_code':code,'seconds':time.monotonic()-start,'resources':{'peak_sampled_rss_sum_kib':peak_rss,'max_sample_gap_seconds':max_gap,'note':'50 ms target; summed RSS may count shared pages, not unique system peak'},'output':output[-4000:]}


def tree_rss(pid):
    total=0;pending=[pid];seen=set()
    while pending:
        current=pending.pop()
        if current in seen:continue
        seen.add(current)
        try:
            fields=dict(line.split(':',1) for line in Path(f'/proc/{current}/status').read_text().splitlines())
            total+=int(fields.get('VmRSS','0').split()[0])
            pending.extend(map(int,Path(f'/proc/{current}/task/{current}/children').read_text().split()))
        except (OSError,ValueError):pass
    return total


def os_kill(child):
    import os
    os.killpg(child.pid,signal.SIGKILL);child.wait()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('capabilities',nargs='+',choices=[n for n in SPECS if n!='learning.learnharness'])
    parser.add_argument('--pilot',type=Path,default=Path.home()/'.local/share/argos-hermes-pilot');parser.add_argument('--evidence',type=Path,required=True)
    args=parser.parse_args();root=args.pilot/'tools/specialized';args.evidence.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(REPO/'experiments/hermes-pilot/adaptive/SPECIALIZED.md',root/'ARGOS.md')
    results={};failed=False
    for name in args.capabilities:
        spec=SPECS[name];folder=spec['folder'];record_path=root/(folder+'.json');record=json.loads(record_path.read_text());record['validated']=False
        with tempfile.TemporaryDirectory(prefix='argos-specialized-') as temporary:
            work=Path(temporary);node=args.pilot/'tools/node-26.12.1-linux-x64/bin/node';commands={}
            try:
                if record.get('revision')!=spec['revision'] or digest_tree(root/folder)!=record['files']:
                    raise PermissionError('Reviewed sources changed; prepare the pinned checkout again before executing')
                if folder=='anatomy':
                    source=(root/'anatomy/examples/dial-indicator/build.mjs').read_text()
                    for relative in ['kit/iso-kit.mjs','scripts/inline-kit.mjs']:source=source.replace('"../../'+relative+'"',json.dumps(str(root/'anatomy'/relative)))
                    (work/'build.mjs').write_text(source);command=[str(node),'/workspace/build.mjs'];commands={'node':str(node)};outputs=['dial-indicator.html']
                elif folder=='archify':
                    value=json.loads((root/'archify/archify/examples/cache-miss-request.sequence.json').read_text());value['meta']['output']='architecture.html'
                    (work/'architecture.json').write_text(json.dumps(value));command=[str(node),str(root/'archify/archify/renderers/sequence/render-sequence.mjs'),'architecture.json','architecture.html'];commands={'node':str(node)};outputs=['architecture.html']
                elif folder=='text-to-cad':
                    shutil.copyfile(REPO/'experiments/hermes-pilot/adaptive/fixtures/cad_smoke.py',work/'model.py');commands={'python':str(root/'cad-env/bin/python')};command=[commands['python'],'/workspace/model.py'];outputs=['part.step','part.stl']
                else:
                    shutil.copyfile(REPO/'experiments/hermes-pilot/adaptive/fixtures/blender_smoke.py',work/'scene.py');commands={'blender':str(root/'blender-5.2.3-linux-x64/blender')};command=[commands['blender'],'--background','--factory-startup','--disable-autoexec','--threads','2','--python-exit-code','1','--python','/workspace/scene.py'];outputs=['scene.blend','scene.glb','preview.png']
                result=run(args.pilot,work,command)
                for file in outputs:
                    assert (work/file).stat().st_size>100,file
                    shutil.copyfile(work/file,args.evidence/(folder+'-'+file))
                if outputs[0].endswith('.html'):assert '<svg' in (work/outputs[0]).read_text()
                if folder=='archify':result['static_check']=run(args.pilot,work,[str(node),str(root/'archify/archify/scripts/check-render-output.mjs'),'architecture.html'])
                if folder=='blender-skills':
                    result['reopen']=run(args.pilot,work,[commands['blender'],'--background','--factory-startup','--disable-autoexec','/workspace/scene.blend','--threads','2','--python-exit-code','1','--python-expr',"import bpy; assert bpy.data.objects.get('DecorativeSphere'); print('REOPEN_OK')"])
                record.update(validated=True,commands=commands,required=[str(Path(v).relative_to(root)) for v in commands.values() if Path(v).is_relative_to(root)],files=digest_tree(root/folder),executables={v:hashlib.file_digest(open(v,'rb'),'sha256').hexdigest() for v in commands.values()},validation=result)
                results[name]={'passed':True,**result}
            except Exception as exc:results[name]={'passed':False,'error':str(exc)};failed=True
            record_path.write_text(json.dumps(record,indent=2)+'\n')
            print(name,results[name]['passed'],flush=True)
    (args.evidence/'toolchains.json').write_text(json.dumps(results,indent=2)+'\n')
    return int(failed)


if __name__=='__main__':raise SystemExit(main())
