"""Reviewed Engineering toolchains, not another dispatcher or task store."""
import hashlib
import json
from pathlib import Path

PILOT = Path(__file__).resolve().parents[1]
ROOT = PILOT / 'tools/specialized'
SPECS = {
    'diagram.architecture': dict(repo='tt-a1i/archify', revision='11b0d6031853bdae89eed57e7979aabbf0034097', license='Apache-2.0', folder='archify', skill='archify/SKILL.md', purpose='Interactive architecture and workflow HTML from a dated native project snapshot; explanatory, never authoritative', outputs=['.json','.html'], memory_mib=768),
    'diagram.technical': dict(repo='wheresryan22/anatomy', revision='1482e8469b0a9e0d8cc18ea2740a01423d29ae80', license='MIT', folder='anatomy', skill='SKILL.md', purpose='Interactive technical mechanisms using Anatomy SVG; explanatory, not mechanical simulation', outputs=['.mjs','.html'], memory_mib=768),
    'cad.parametric': dict(repo='earthtojake/text-to-cad', revision='1cfd73cbbf0be943e0ff7aa0c672f824935b98a7', license='MIT', folder='text-to-cad', skill='skills/cad/SKILL.md', purpose='Editable build123d geometry and text-to-cad geometry inspection, STEP/STL exports; no fabrication or structural certification', outputs=['.py','.step','.stl','.json'], memory_mib=2048),
    'design.blender': dict(repo='EL4CTEO/blender-skills', revision='389f28addc79b87b28764898e38e7bf408d14b77', license='MIT', folder='blender-skills', skill='skills/blender-core/SKILL.md', purpose='Headless Blender modeling, materials, editable scenes, exports and CPU previews', outputs=['.py','.blend','.glb','.png'], memory_mib=3072),
    'learning.learnharness': dict(repo='amosblomqvist/learnharness', revision='da08cb5f7d098598ba963c6689b22054c9f2a5a3', license='AGPL-3.0-only', folder='learnharness', skill='README.md', purpose='Candidate independent learning application; separate runtime, knowledge graph and unvalidated subscription integration', outputs=[], memory_mib=0),
}


def digest_tree(root):
    """Executable/resources integrity; installation is controller-owned and worker read-only."""
    result = {}
    for path in sorted(root.rglob('*')):
        if '.git' in path.parts or '__pycache__' in path.parts:continue
        if path.is_symlink():raise PermissionError('Toolchain contains an unexpected symlink')
        if path.is_file():result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def catalog(root=ROOT):
    rows=[]
    for name,spec in SPECS.items():
        status='missing_dependencies';reason='Run the selective preparation procedure';record={}
        if name=='learning.learnharness':status='unsupported';reason='Independent knowledge/runtime and provider access not authorized or validated'
        else:
            try:
                record=json.loads((root/(spec['folder']+'.json')).read_text())
                if record.get('revision')!=spec['revision']:raise ValueError('Different revision')
                status='installed_unverified';reason='Installed source; validation not completed'
                if record.get('validated') and all((root/p).is_file() for p in record.get('required',[])) and all(Path(p).is_file() for p in record.get('commands',{}).values()):
                    status='available_validated';reason='Bounded Engineering workflow validated; individual outputs still require verification'
                elif record.get('validated'):
                    status='missing_dependencies';reason='A validated runtime is missing; prepare it and validate again'
            except (OSError,ValueError):pass
        rows.append({'id':name,**spec,'available':status=='available_validated','status':status,'reason':reason,
                     'executor':'native Engineering','permissions':['authorized_project_write','offline_tools_read'],
                     'parallel':False,'lifecycle':'native task process; no persistent specialist','location':'local','cost':'existing Codex subscription and local resources'})
    return rows


def context(name,root=ROOT,check=True):
    if name not in SPECS:raise ValueError('Unregistered Engineering capability')
    entry=next(r for r in catalog(root) if r['id']==name)
    if not entry['available']:raise PermissionError(entry['reason']+' ('+name+')')
    spec=SPECS[name];record=json.loads((root/(spec['folder']+'.json')).read_text())
    if check and digest_tree(root/spec['folder'])!=record['files']:
        raise PermissionError('Reviewed capability files changed; prepare and validate again')
    if check:
        for filename,expected in record.get('executables',{}).items():
            with open(filename,'rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=expected:
                    raise PermissionError('Validated executable changed')
    return {'id':name,'revision':spec['revision'],'skill':str(root/spec['folder']/spec['skill']),
            'instructions':str(root/'ARGOS.md'),'commands':record['commands'],'outputs':spec['outputs'],
            'boundary':'Use only assigned workspace, no network/install/publishing. Skill setup and global configuration advice is superseded by ARGOS policy. Report artifacts in native review metadata. Never claim mechanical certification.'}


def memory_ready(name):
    values=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    return int(values['MemAvailable'].split()[0]) >= (SPECS[name]['memory_mib']+1024)*1024
