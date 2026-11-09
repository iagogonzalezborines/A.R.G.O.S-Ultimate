"""Fixed, independent verification profiles in the existing read-only sandbox."""
import os
import resource
import signal
import subprocess
import time

from maintenance.controller import validation_sandbox,clean
from projects.lifecycle import fingerprint

MODEL_LIBRARY = '''import tempfile, pathlib
from catalogue import ModelLibrary
with tempfile.TemporaryDirectory() as d:
 root=pathlib.Path(d); models=root/'models';models.mkdir()
 (models/'dragon.stl').write_text('synthetic STL');(models/'gear.obj').write_text('synthetic OBJ')
 (models/'ignore.txt').write_text('not a model')
 original={p.name:p.read_bytes() for p in models.iterdir()}
 db=root/'catalogue.sqlite';lib=ModelLibrary(db);lib.index(models)
 assert len(lib.search(''))==2, 'index only supported 3D models'
 lib.index(models);assert len(lib.search(''))==2, 'index idempotency'
 path=str((models/'dragon.stl').resolve());lib.tag(path,['miniatura','fantasía']);lib.note(path,'Dragón de prueba')
 assert len(lib.search('miniatura'))==1, 'search tags'
 assert len(lib.search('Dragón'))==1, 'search notes'
 assert len(lib.search('gear'))==1, 'search file names'
 lib.close();lib=ModelLibrary(db)
 row=lib.search('fantasía')[0];assert (row['notes']=='Dragón de prueba' or row['notes']==['Dragón de prueba']) and 'miniatura' in row['tags'], 'restart persistence'
 lib.close();assert original=={p.name:p.read_bytes() for p in models.iterdir()}, 'preserve originals'
 print('ARGOS_ACCEPTANCE: indexing, idempotency, tags, notes, search, persistence, preservation passed')
'''


CLI_DOCUMENTATION = '''
def documented_cli(root):
 import ast
 readme=root/'README.md'
 documentation=readme.read_text() if readme.is_file() else (ast.get_docstring(ast.parse((root/'catalogue.py').read_text())) or '')
 return '--db' in documentation
'''

MODEL_LIBRARY_V2 = MODEL_LIBRARY + CLI_DOCUMENTATION + '''
import subprocess,sys,json
with tempfile.TemporaryDirectory() as d:
 root=pathlib.Path(d); models=root/'models';models.mkdir();part=models/'widget.stl';part.write_text('synthetic STL')
 db=root/'cli.sqlite'
 def cli(*args):
  return subprocess.run([sys.executable,'-B','/workspace/catalogue.py','--db',str(db),*args],capture_output=True,text=True,check=True,timeout=5).stdout
 cli('index',str(models));cli('tag',str(part),'fixture','quick');cli('note',str(part),'CLI persistence note')
 rows=json.loads(cli('search','quick'));assert len(rows)==1 and 'fixture' in rows[0]['tags'], 'CLI tags and search'
 rows=json.loads(cli('search','CLI persistence note'));assert len(rows)==1, 'CLI note persistence across processes'
 assert documented_cli(pathlib.Path('/workspace')), 'documented CLI commands in README or module documentation'
 assert part.read_text()=='synthetic STL', 'CLI preserves model file'
 print('ARGOS_CLI_ACCEPTANCE: index, tag, note, search, persistence and documentation passed')
'''


def limits():
    resource.setrlimit(resource.RLIMIT_CPU,(20,20))
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))


def verify(root,profile,*,capability=None,artifacts=None):
    if profile=='specialized_integrity':return verify_specialized(root,capability,artifacts)
    if profile not in {'python_unittest','model_library_v1','model_library_v2'}:raise ValueError('Unregistered verification profile')
    before=fingerprint(root);start=time.monotonic()
    argv=['/usr/bin/python','-B','-c',MODEL_LIBRARY_V2 if profile=='model_library_v2' else MODEL_LIBRARY] if profile.startswith('model_library_') else ['/usr/bin/python','-B','-m','unittest','discover','-v']
    # A regular temporary file bounds child output with RLIMIT_FSIZE; no unbounded pipe buffer.
    import tempfile
    with tempfile.TemporaryFile() as output:
        child=subprocess.Popen(validation_sandbox(root,argv),stdout=output,stderr=output,start_new_session=True,preexec_fn=limits)
        try:code=child.wait(timeout=25)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGKILL);child.wait();code=-1
        output.seek(0);result=clean(output.read(16384).decode('utf-8','replace'))
    after=fingerprint(root)
    meaningful=('ARGOS_CLI_ACCEPTANCE:' in result if profile=='model_library_v2' else 'ARGOS_ACCEPTANCE:' in result) if profile.startswith('model_library_') else 'Ran ' in result and 'Ran 0 tests' not in result
    return {'profile':profile,'passed':code==0 and meaningful and before==after,'exit_code':code,
            'output':result,'seconds':time.monotonic()-start,'files':after,'snapshot_unchanged':before==after}


def verify_specialized(root,capability,artifacts):
    import json,tempfile
    from pathlib import Path
    from adaptive.specialized import context,ROOT
    selected=context(capability)
    before=fingerprint(root);paths=list(dict.fromkeys(artifacts or []))
    if not paths or len(paths)>20 or any(p not in before for p in paths):raise ValueError('Select observed native task artifacts')
    executable=str(ROOT/'cad-env/bin/python') if capability=='cad.parametric' else '/usr/bin/python'
    argv=[executable,'-B','/verify.py',capability,json.dumps(paths),selected['commands'].get('blender',selected['commands'].get('node','')),str(ROOT)]
    cmd=validation_sandbox(root,argv)
    index=cmd.index('--')
    pilot=Path(__file__).resolve().parents[1]
    cmd[index:index]=['--ro-bind',str(pilot/'tools'),str(pilot/'tools'),'--ro-bind',str((pilot/'tools').resolve()),str((pilot/'tools').resolve()),'--ro-bind',str(pilot/'adaptive/verify_artifacts.py'),'/verify.py','--setenv','OPENBLAS_NUM_THREADS','2','--setenv','OMP_NUM_THREADS','2']
    def bounded():
        resource.setrlimit(resource.RLIMIT_CPU,(40,40));resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
    start=time.monotonic()
    with tempfile.TemporaryFile() as output:
        child=subprocess.Popen(cmd,stdout=output,stderr=output,start_new_session=True,preexec_fn=bounded)
        try:code=child.wait(timeout=45)
        except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait();code=-1
        output.seek(0);result=clean(output.read(16384).decode('utf-8','replace'))
    after=fingerprint(root)
    return {'profile':'specialized_integrity','passed':code==0 and 'ARGOS_SPECIALIZED_INTEGRITY:' in result and before==after,'exit_code':code,'output':result,'seconds':time.monotonic()-start,'files':after,'snapshot_unchanged':before==after,'scope':'Artifact integrity; requirements and mechanical suitability need separate review'}
