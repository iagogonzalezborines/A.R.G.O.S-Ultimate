"""Prepare pinned private headless graphics. No services or system portal changes."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

REPO=Path(__file__).resolve().parents[1]
SOURCE=REPO/'experiments/hermes-pilot/desktop/visual'

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--root',type=Path,default=Path.home()/'.local/share/argos-desktop/visual-1')
 parser.add_argument('--pilot',type=Path,default=Path.home()/'.local/share/argos-hermes-pilot')
 parser.add_argument('--activate',action='store_true');args=parser.parse_args()
 import platform
 if platform.system()!='Linux' or platform.machine()!='x86_64':raise ValueError('This pin supports Linux x86_64 only')
 root=args.root.resolve();root.mkdir(parents=True,exist_ok=True,mode=0o700)
 spec=importlib.util.spec_from_file_location('desktop_setup',REPO/'scripts/prepare_agent_desktop.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 pin=json.loads((SOURCE/'pin.json').read_text())
 for protocol in pin['protocols']:
  if hashlib.sha256((SOURCE/protocol['file']).read_bytes()).hexdigest()!=protocol['sha256']:raise ValueError('Protocol source changed')
 # Separate archives preserve verifiable per-package manifests and allow retries.
 import shutil
 for i,package in enumerate(pin['packages']):
  archive=root/'packages'/str(i)
  if archive.exists():
   saved=json.loads((archive/'.argos-archive.json').read_text())
   if saved['archive']!=package['sha256'] or any(not (archive/n).resolve().is_relative_to(archive) or hashlib.sha256((archive/n).read_bytes()).hexdigest()!=h for n,h in saved['files'].items()): raise ValueError('Cached package changed')
  else: module.extract(package['url'],package['sha256'],archive)
  for p in (archive/'usr').rglob('*'):
   dest=root/p.relative_to(archive)
   if p.is_symlink() and dest.is_symlink():dest.unlink()
  shutil.copytree(archive/'usr',root/'usr',dirs_exist_ok=True,symlinks=True)
 with tempfile.TemporaryDirectory() as tmp:
  tmp=Path(tmp)
  subprocess.run(['wayland-scanner','client-header',str(SOURCE/'wlr-virtual-pointer-unstable-v1.xml'),str(tmp/'virtual-pointer.h')],check=True)
  subprocess.run(['wayland-scanner','private-code',str(SOURCE/'wlr-virtual-pointer-unstable-v1.xml'),str(tmp/'virtual-pointer.c')],check=True)
  subprocess.run(['cc','-Wall','-Wextra','-Werror','-O2','-I'+str(tmp),str(SOURCE/'pointer-seat.c'),str(tmp/'virtual-pointer.c'),'-lwayland-client','-o',str(root/'pointer-seat')],check=True)
 with tempfile.TemporaryDirectory() as tmp:
  tmp=Path(tmp)
  subprocess.run(['wayland-scanner','client-header',str(SOURCE/'virtual-keyboard-unstable-v1.xml'),str(tmp/'virtual-keyboard.h')],check=True)
  subprocess.run(['wayland-scanner','private-code',str(SOURCE/'virtual-keyboard-unstable-v1.xml'),str(tmp/'virtual-keyboard.c')],check=True)
  subprocess.run(['cc','-Wall','-Wextra','-Werror','-O2','-I'+str(tmp),str(SOURCE/'key-combo.c'),str(tmp/'virtual-keyboard.c'),'-lwayland-client','-lxkbcommon','-o',str(root/'key-combo')],check=True)
 files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and not p.is_relative_to(root/'packages') and not p.name.startswith('.argos')}
 (root/'.argos-files.json').write_text(json.dumps(files,indent=2)+'\n')
 settings={'root':str(root),'manifest_sha256':hashlib.sha256((root/'.argos-files.json').read_bytes()).hexdigest()}
 if args.activate:
  path=args.pilot/'installation.json';config=json.loads(path.read_text())
  if not (args.pilot/'desktop/visual/session.py').exists():raise ValueError('Materialize ARGOS sources before activation')
  config['desktop']['visual']=settings;path.write_text(json.dumps(config,indent=2)+'\n');path.chmod(0o600)
 print(json.dumps({'root':str(root),'activated':args.activate,'bytes':sum((root/n).stat().st_size for n in files),'settings':settings}))

if __name__=='__main__':main()
