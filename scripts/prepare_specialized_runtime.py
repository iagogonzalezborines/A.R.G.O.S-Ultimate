#!/usr/bin/env python3
"""Explicit, selective private CAD/Blender preparation. No system package changes."""
import argparse
import hashlib
import json
import shutil
import tempfile
import sys
from pathlib import Path
import subprocess
import tarfile
import urllib.request

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'experiments/hermes-pilot'))
from adaptive.specialized import SPECS,digest_tree
BLENDER='blender-5.2.3-linux-x64'
SHA256='78486c018b4443efe5e75ab54c290ed8c15abafd249b862c2c9ce2530a918eec'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot',type=Path,default=Path.home()/'.local/share/argos-hermes-pilot')
    parser.add_argument('--cad',action='store_true');parser.add_argument('--blender',action='store_true')
    args=parser.parse_args()
    if not (args.cad or args.blender):parser.error('Select --cad and/or --blender deliberately')
    root=args.pilot/'tools/specialized';root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if args.cad:
        record=json.loads((root/'text-to-cad.json').read_text())
        if record.get('revision')!=SPECS['cad.parametric']['revision'] or digest_tree(root/'text-to-cad')!=record['files']:raise PermissionError('CAD source differs from reviewed manifest')
        uv=args.pilot/'tools/uv-0.13.5-linux-x64/uv';environment=root/'cad-env'
        if environment.exists():raise FileExistsError('CAD environment exists; validate it, do not silently replace it')
        subprocess.run([str(uv),'venv',str(environment),'--python','/usr/bin/python3.14'],check=True)
        subprocess.run([str(uv),'pip','install','--python',str(environment/'bin/python'),'--require-hashes','--only-binary',':all:','-r',str(REPO/'experiments/hermes-pilot/adaptive/cad-requirements.lock')],check=True)
        with tempfile.TemporaryDirectory(prefix='argos-cad-build-') as temporary:
            package=Path(temporary)/'cad';shutil.copytree(root/'text-to-cad/packages/cad',package)
            subprocess.run([str(uv),'pip','install','--python',str(environment/'bin/python'),'--no-deps','--build-constraint',str(REPO/'experiments/hermes-pilot/adaptive/cad-build-constraints.txt'),str(package)],check=True)
    if args.blender:
        if (root/BLENDER).exists():raise FileExistsError('Blender exists; validate it, do not silently replace it')
        archive=root/(BLENDER+'.tar.xz')
        if not archive.exists():
            temporary=archive.with_suffix('.download')
            with urllib.request.urlopen('https://download.blender.org/release/Blender5.2/'+archive.name,timeout=60) as source,temporary.open('wb') as output:
                size=0
                while block:=source.read(1024*1024):
                    size+=len(block)
                    if size>400*1024*1024:raise ValueError('Archive exceeds reviewed size budget')
                    output.write(block)
            temporary.rename(archive)
        with archive.open('rb') as source:
            if hashlib.file_digest(source,'sha256').hexdigest()!=SHA256:raise ValueError('Blender SHA-256 mismatch')
        with tarfile.open(archive) as package:package.extractall(root,filter='data')
        archive.unlink()
    print('Runtime prepared; run validate_specialized.py before capability activation')


if __name__=='__main__':main()
