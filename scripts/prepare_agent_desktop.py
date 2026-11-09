"""Explicit, private Linux x86_64 desktop preparation. No global package changes.

Downloads fixed release archives with pinned hashes; activates only when asked.
The calculator package was checked against the Arch signing key in the report.
Requires existing GTK3, GI/AT-SPI, libquadmath and bubblewrap; no model download.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
import re
import tarfile
import tomllib
import urllib.request

REPO = Path(__file__).resolve().parents[1]
PIN = json.loads((REPO / 'experiments/hermes-pilot/desktop/pin.json').read_text())


def extract(url, expected, target, headers=None):
    if target.exists():
        manifest = target / '.argos-archive.json'
        if not manifest.is_file(): raise ValueError('Existing unmanaged destination: ' + str(target))
        recorded = json.loads(manifest.read_text())
        if recorded['archive'] != expected: raise ValueError('Archive pin changed')
        for name, value in recorded['files'].items():
            path = target / name
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != value:
                raise ValueError('Installed executable/resources changed: ' + name)
        return
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=35) as response: data = response.read(12000001)
    if len(data) > 12000000 or hashlib.sha256(data).hexdigest() != expected: raise ValueError('Archive digest mismatch')
    target.mkdir(parents=True, mode=0o700)
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            if sum(m.size for m in archive.getmembers()) > 50000000: raise ValueError('Archive too large')
            archive.extractall(target, filter='data')
        files = {str(p.relative_to(target)):hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file()}
        (target / '.argos-archive.json').write_text(json.dumps({'archive':expected,'files':files},indent=2)+'\n')
    except BaseException:
        import shutil
        shutil.rmtree(target); raise


def activate(pilot, settings):
    config_path = pilot / 'installation.json'; config = json.loads(config_path.read_text())
    path = pilot / 'state/codex/config.toml'; source = path.read_text(); parsed = tomllib.loads(source)
    section = parsed['mcp_servers']['argos-workspace']
    names = list(dict.fromkeys([*section['enabled_tools'], 'desktop']))
    match = re.search(r'(?ms)(^\[mcp_servers\.argos-workspace\]\s*\n)(.*?)(?=^\[|\Z)', source)
    if not match or not re.search(r'^enabled_tools\s*=\s*\[[^\n]*\]\s*$', match[2], re.M): raise ValueError('Review MCP configuration')
    body = re.sub(r'^enabled_tools[^\n]*', 'enabled_tools='+json.dumps(names), match[2], flags=re.M)
    source = source[:match.start(2)] + body + source[match.end(2):]
    heading = '[mcp_servers.argos-workspace.tools.desktop]'
    if heading not in source: source += '\n'+heading+'\napproval_mode="approve"\n'
    if tomllib.loads(source)['mcp_servers']['argos-workspace']['tools']['desktop'].get('approval_mode') != 'approve': raise ValueError('Review tool approval mode')
    if not (pilot/'ui-workbench/runtime/desktop.py').exists(): raise ValueError('Install the Broker adapter first')
    path.write_text(source); config.update(desktop_enabled=True, desktop=settings)
    config_path.write_text(json.dumps(config,indent=2)+'\n');config_path.chmod(0o600)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.home()/'.local/share/argos-desktop')
    parser.add_argument('--pilot',type=Path,default=Path.home()/'.local/share/argos-hermes-pilot')
    parser.add_argument('--activate',action='store_true',help='Enable the reviewed calculator/comparison profiles at next ARGOS startup')
    args=parser.parse_args()
    if platform.system()!='Linux' or platform.machine()!='x86_64': raise SystemExit('This pin is Linux x86_64 only')
    root=args.root.expanduser().resolve();root.mkdir(parents=True,exist_ok=True,mode=0o700)
    binary=root/'v1.2.0';calc=root/'galculator-2.1.4-12'
    extract('https://api.github.com/repos/vercel-labs/agent-desktop/releases/assets/'+str(PIN['asset_id']),PIN['archive_sha256'],binary,{'Accept':'application/octet-stream'})
    extract(PIN['calculator']['source'],PIN['calculator']['sha256'],calc)
    settings={'binary':str(binary/'agent-desktop'),'calculator':str(calc/'usr/bin/galculator'),
              'calculator_resources':str(calc/'usr/share/galculator'),'state':str(root/'scopes')}
    for name in ['binary','calculator']:settings[name+'_sha256']=hashlib.sha256(Path(settings[name]).read_bytes()).hexdigest()
    if args.activate:activate(args.pilot,settings)
    print(json.dumps({'version':PIN['version'],'settings':settings,'activated':args.activate,'restart_required':args.activate},indent=2))

if __name__=='__main__':main()
