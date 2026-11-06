"""Explicit, selected lab preparation. Never changes the operational installation."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'experiments/hermes-pilot/adaptive'


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    path.write_text(json.dumps(value,indent=2)+'\n' if not isinstance(value,str) else value)
    path.chmod(0o600)


def env(home):
    return {'HOME':str(home),'PATH':os.defpath,'LANG':'C.UTF-8'}


def init(args,manifest):
    from prepare_hermes_pilot import prepare
    if args.lab.exists():raise ValueError('Use a new disposable lab directory; existing state is never overwritten')
    if not args.base or not args.projects:raise ValueError('Supply a validated --base pilot and visible --projects fixture root')
    base=args.base.resolve()
    sys.path.insert(0,str(base))
    from projects.worker import verify_pin
    verify_pin(base)
    for name in ['source','env','tools','bin']:
        if not (base/name).is_dir():raise ValueError('Baseline dependency missing: '+name)
    if args.lab.is_relative_to(base) or base.is_relative_to(args.lab):raise ValueError('Lab and baseline must be separate')
    fixtures=args.projects.resolve()
    if any(fixtures==p or fixtures.is_relative_to(p) for p in [base,args.lab,ROOT]) or any(x.startswith('.') for x in fixtures.parts):
        raise ValueError('Use a visible fixture root outside the controller and repository')
    args.lab.mkdir(parents=True,mode=0o700)
    pilot=args.lab/'pilot';pilot.mkdir()
    for name in ['source','env','tools']:(pilot/name).symlink_to(base/name,target_is_directory=True)
    # The source installer may add a missing executable; keep the containing bin private.
    (pilot/'bin').mkdir()
    for entry in (base/'bin').iterdir():(pilot/'bin'/entry.name).symlink_to(entry)
    prepare(pilot,projects=True)
    settings=json.loads((pilot/'installation.json').read_text())
    settings.update(adaptive_enabled=True,project_state=str(pilot/'state/adaptive'),project_roots=[str(args.projects.resolve())],
        adaptive={'local':manifest['local'],'min_available_bytes':manifest['budgets']['min_available_bytes']})
    write(pilot/'installation.json',settings)
    write(pilot/'state/adaptive/config.yaml',{'kanban':{'review_dispatch':False,'dispatch_in_gateway':False,'notify_in_gateway':False,
        'auto_decompose':False,'max_spawn':1,'max_in_progress':2,'max_in_progress_per_profile':1},
        'memory':{'memory_enabled':False,'user_profile_enabled':False},'auxiliary':{'background_review':{'enabled':False}}})
    file=pilot/'state/codex/config.toml';content=file.read_text()
    content=re.sub(r'(?m)^(enabled_tools\s*=\s*\[[^\n]*)(\])',r'\1, "adaptive"\2',content,count=1)
    content+='\n[mcp_servers.argos-workspace.tools.adaptive]\napproval_mode="approve"\n'
    write(file,content)
    write(args.lab/'local/config.json',manifest['local']);write(args.lab/'manifest.json',manifest)
    args.projects.mkdir(parents=True,exist_ok=True)
    print('Prepared isolated pilot. Authentication is absent; use an independent login before live_check.')


def local(args,manifest):
    binary=Path(args.ollama or shutil.which('ollama') or '').resolve()
    if not binary.is_file():raise ValueError('Provide --ollama; this helper does not install another inference runtime')
    work=args.lab/'local';(work/'home').mkdir(parents=True,exist_ok=True,mode=0o700);(work/'models').mkdir(exist_ok=True)
    settings=json.loads((work/'config.json').read_text()) if (work/'config.json').exists() else manifest['local']
    sys.path.insert(0,str(SOURCE.parent));from adaptive.local import Local
    client=Local(settings)
    environment=env(work/'home');environment.update(OLLAMA_HOST=settings['url'].removeprefix('http://'),OLLAMA_MODELS=str(work/'models'),
        OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1',OLLAMA_MAX_QUEUE='2',OLLAMA_KEEP_ALIVE=settings['keep_alive'],OLLAMA_NO_CLOUD='1')
    if settings.get('options',{}).get('num_gpu',0)==0:environment['CUDA_VISIBLE_DEVICES']='-1'
    version=subprocess.check_output([str(binary),'--version'],env=environment,text=True,stderr=subprocess.STDOUT)
    if manifest['ollama_version'] not in version:raise ValueError('Review and update the manifest for this Ollama version')
    if args.action=='serve':
        try:client.loaded()
        except OSError:pass
        else:raise ValueError('Endpoint already occupied; do not share its model owner')
        os.execve(str(binary),[str(binary),'serve'],environment)
    subprocess.run([str(binary),'pull',settings['model']],env=environment,check=True)
    if not client.available():raise ValueError('Downloaded tag differs from reviewed digest; do not enable it')
    print('Reviewed model digest is installed')


def openclaw(args,manifest):
    target=args.lab/'openclaw'
    if target.exists():raise ValueError('OpenClaw directory already exists; preserve its state and inspect it')
    target.mkdir(parents=True,mode=0o700);(target/'home').mkdir()
    environment=env(target/'home');environment['OPENCLAW_STATE_DIR']=str(target/'state')
    npm=shutil.which('npm');node=shutil.which('node')
    if not npm or not node:raise ValueError('Install a compatible Node/npm runtime first (Node 26 tested)')
    subprocess.run([npm,'install','--prefix',str(target),'--ignore-scripts','--no-audit','--no-fund',
        'openclaw@'+manifest['openclaw_version']],env=environment,check=True)
    subprocess.run([node,str(target/'node_modules/openclaw/openclaw.mjs'),'plugins','install',
        '@openclaw/codex@'+manifest['openclaw_codex_plugin_version']],env=environment,check=True)
    print('Pinned candidate installed, not started. Configure with adaptive/openclaw_prepare.py before testing.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['plan','init','serve','pull','openclaw'])
    parser.add_argument('--lab',type=Path,required=True);parser.add_argument('--base',type=Path)
    parser.add_argument('--projects',type=Path);parser.add_argument('--ollama')
    parser.add_argument('--manifest',type=Path,default=SOURCE/'manifest.json')
    args=parser.parse_args();args.lab=args.lab.expanduser().resolve()
    if args.lab==ROOT or args.lab.is_relative_to(ROOT):raise ValueError('Keep private lab state outside the repository')
    manifest=json.loads(args.manifest.read_text())
    if args.action=='plan':print(json.dumps(manifest,indent=2));return
    if sys.platform!='linux':raise ValueError('This setup is Linux-validated only; Windows needs its isolation adapter')
    if args.action=='init':init(args,manifest)
    elif args.action in {'serve','pull'}:local(args,manifest)
    else:openclaw(args,manifest)


if __name__=='__main__':main()
