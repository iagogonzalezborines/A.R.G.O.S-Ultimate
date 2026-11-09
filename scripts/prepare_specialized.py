#!/usr/bin/env python3
"""Selective private source preparation. No upstream installers or global skills."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'experiments/hermes-pilot'))
from adaptive.specialized import SPECS,digest_tree


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capabilities',nargs='+',choices=[n for n in SPECS if n!='learning.learnharness'])
    parser.add_argument('--pilot',type=Path,default=Path.home()/'.local/share/argos-hermes-pilot')
    parser.add_argument('--reviewed-checkouts',type=Path,help='Optional existing checkouts; HEAD must match pin and tracked files must be clean')
    args=parser.parse_args();root=args.pilot/'tools/specialized';root.mkdir(parents=True,exist_ok=True,mode=0o700)
    shutil.copyfile(REPO/'experiments/hermes-pilot/adaptive/SPECIALIZED.md',root/'ARGOS.md')
    with tempfile.TemporaryDirectory(prefix='argos-skills-') as temporary:
        for name in args.capabilities:
            spec=SPECS[name];folder=spec['folder'];source=(args.reviewed_checkouts or Path(temporary))/folder
            if not args.reviewed_checkouts:
                subprocess.run(['git','clone','--filter=blob:none','--no-checkout','https://github.com/'+spec['repo']+'.git',str(source)],check=True)
                subprocess.run(['git','checkout','--detach',spec['revision']],cwd=source,check=True)
            if subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()!=spec['revision'] or subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=source):raise ValueError('Unreviewed checkout')
            destination=root/folder
            if destination.exists():raise FileExistsError(str(destination)+' exists; retain it or remove this private toolchain deliberately before preparing again')
            # Copy only the useful skill/library surface, preserving upstream licenses.
            selected={'archify':['archify'], 'anatomy':['SKILL.md','LICENSE','kit','scripts/inline-kit.mjs','references','examples/dial-indicator'],
                'blender-skills':['LICENSE','skills','shared'], 'text-to-cad':['LICENSE','skills/cad','packages/cad']}[folder]
            for item in selected:
                src=source/item;dst=destination/item;dst.parent.mkdir(parents=True,exist_ok=True)
                for candidate in ([src]+list(src.rglob('*')) if src.is_dir() else [src]):
                    if candidate.is_symlink() and not candidate.resolve().is_relative_to(source.resolve()):raise PermissionError('Source link escapes reviewed checkout')
                if src.is_dir():shutil.copytree(src,dst,ignore=shutil.ignore_patterns('__pycache__','*.html','*.png','*.pdf') if folder=='anatomy' else None)
                else:shutil.copyfile(src,dst)
            commands={}
            node=args.pilot/'tools/node-26.12.1-linux-x64/bin/node'
            if folder in {'archify','anatomy'}:commands['node']=str(node)
            record={'revision':spec['revision'],'files':digest_tree(destination),'validated':False,'required':[], 'commands':commands}
            (root/(folder+'.json')).write_text(json.dumps(record,indent=2)+'\n')
            print(name+': installed_unverified')


if __name__=='__main__':main()
