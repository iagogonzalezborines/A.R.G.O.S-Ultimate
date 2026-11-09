"""Prepare the disposable Electron/native desktop test from a working pilot.

No models/packages are downloaded. Dependencies are shared read-only in the native
sandbox; credentials are derived privately and must be removed with --cleanup.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil

REPO = Path(__file__).resolve().parents[3]
TARGET = Path('/tmp/argos-desktop-qa/pilot')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installed',type=Path,default=Path.home()/'.local/share/argos-hermes-pilot')
    parser.add_argument('--cleanup',action='store_true')
    args=parser.parse_args()
    if args.cleanup:
        for relative in ('state/codex/auth.json','state/hermes/auth.json'):
            (TARGET/relative).unlink(missing_ok=True)
        print('Derived test credentials removed; test evidence retained privately');return
    if TARGET.exists():raise SystemExit('Disposable target already exists; inspect/clean the previous run before replacing it')
    p=args.installed.resolve();q=TARGET
    spec=importlib.util.spec_from_file_location('prepare',REPO/'scripts/prepare_hermes_pilot.py')
    materializer=importlib.util.module_from_spec(spec);spec.loader.exec_module(materializer);materializer.prepare(q)
    for name in ('source','env','tools'):(q/name).symlink_to(p/name,target_is_directory=True)
    for name in ('codex','codex-code-mode-host','rg'):
        if not (q/'bin'/name).exists() and (p/'bin'/name).exists():shutil.copy2(p/'bin'/name,q/'bin'/name)
    for directory,names in [('state/codex',['config.toml','auth.json']),('state/hermes',['config.yaml','auth.json'])]:
        for name in names:
            src=p/directory/name;dst=q/directory/name
            if src.exists():
                if name.startswith('config.'):dst.write_text(src.read_text().replace(str(p),str(q)))
                else:shutil.copyfile(src,dst)
                dst.chmod(0o600)
    settings=json.loads((p/'installation.json').read_text())['desktop'];settings['state']='/tmp/argos-desktop-qa/scopes'
    config=json.loads((q/'installation.json').read_text())
    config.update(desktop_enabled=True,desktop=settings,user_home='/tmp/argos-desktop-qa/home',projects_enabled=False,project_map_enabled=False,adaptive_enabled=False)
    (q/'installation.json').write_text(json.dumps(config,indent=2));Path(config['user_home']).mkdir(exist_ok=True)
    import re,tomllib
    cp=q/'state/codex/config.toml';source=cp.read_text()
    names=tomllib.loads(source)['mcp_servers']['argos-workspace']['enabled_tools']
    names=[n for n in names if n not in {'projects','adaptive'}]
    if 'desktop' not in names:names.append('desktop')
    source=re.sub(r'^enabled_tools\s*=.*$', 'enabled_tools='+json.dumps(names),source,flags=re.M)
    cp.write_text(source)
    print(q)

if __name__=='__main__':main()
