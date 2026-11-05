"""Finite capability-boundary checks using disposable files only."""
import json
import base64
import os
from pathlib import Path
import tempfile
from runtime.workspace_broker import Files,WorkspaceBroker,video_url
from server import validate

checks=[]
def check(name,condition):
 checks.append({'name':name,'ok':bool(condition)})
 if not condition:raise AssertionError(name)
def reject(name,call):
 try:call()
 except (PermissionError,ValueError,OSError):check(name,True)
 else:check(name,False)
with tempfile.TemporaryDirectory(prefix='argos-files-') as d:
 root=Path(d);f=Files({'Pruebas':root});(root/'notes.txt').write_text('A blue enclosure, budget 80 euros.\n');(root/'nested').mkdir();(root/'nested/model.stl').write_text('solid example\nendsolid\n');(root/'.env').write_text('SYNTHETIC_NOT_A_SECRET');(root/'demo.key').write_text('SYNTHETIC');(root/'escape').symlink_to('/etc',target_is_directory=True)
 check('list roots',f.list()['roots'][0]['path']==d)
 check('hidden and credential files excluded',not any(e['name'] in {'.env','demo.key','escape'} for e in f.list('Pruebas')['entries']))
 check('recursive filename search',f.search('model.stl')['entries'][0]['name']=='model.stl')
 check('bounded text read',f.read('Pruebas/notes.txt')['text'].startswith('A blue enclosure'))
 (root/'image.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2S8sAAAAASUVORK5CYII='))
 check('image preview encoded safely',f.read('Pruebas/image.png')['data_url'].startswith('data:image/png;base64,'))
 reject('traversal rejected',lambda:f.read('Pruebas/../etc/passwd'))
 reject('symlink traversal rejected',lambda:f.read('Pruebas/escape/passwd'))
 reject('credential path rejected',lambda:f.read('Pruebas/demo.key'))
 os.link(root/'notes.txt',root/'linked.txt');reject('hardlink read rejected',lambda:f.read('Pruebas/linked.txt'));(root/'linked.txt').unlink()
 p=f.propose('write','Pruebas/notes.txt',content='Updated blue enclosure.');check('proposal does not write',f.read('Pruebas/notes.txt')['text'].startswith('A blue'))
 check('user review applies exact proposal',f.confirm(p['id'],True)['status']=='applied' and (root/'notes.txt').read_text()=='Updated blue enclosure.')
 reject('approval cannot be replayed',lambda:f.confirm(p['id'],True))
 p=f.propose('write','Pruebas/notes.txt',content='Stale edit');(root/'notes.txt').write_text('External update');reject('stale edit rejected',lambda:f.confirm(p['id'],True))
 p=f.propose('rename','Pruebas/notes.txt','Pruebas/renamed.txt');f.confirm(p['id'],True);check('rename applied',not (root/'notes.txt').exists() and (root/'renamed.txt').exists())
 p=f.propose('copy','Pruebas/renamed.txt','Pruebas/copy.txt');f.confirm(p['id'],True);check('copy applied',(root/'copy.txt').read_text()=='External update')
 p=f.propose('move','Pruebas/copy.txt','Pruebas/nested/moved.txt');f.confirm(p['id'],True);check('move applied',(root/'nested/moved.txt').is_file() and not (root/'copy.txt').exists())
 p=f.propose('mkdir','Pruebas/new-folder');f.confirm(p['id'],True);check('mkdir applied',(root/'new-folder').is_dir())
 p=f.propose('write','Pruebas/new.txt',content='Exact text');check('new file deferred',not (root/'new.txt').exists());f.confirm(p['id'],False);check('cancel leaves disk unchanged',not (root/'new.txt').exists())
 p=f.propose('write','Pruebas/new.txt',content='Exact text');(root/'new.txt').write_text('Concurrent');reject('concurrent creation rejected',lambda:f.confirm(p['id'],True))
 b=WorkspaceBroker(lambda e:None,validate,files=f)
 reject('agent cannot approve',lambda:b.request({'tool':'files','arguments':{'action':'confirm','proposal_id':'anything','approve':True}}))
 reject('unknown fields rejected',lambda:b.request({'tool':'files','arguments':{'action':'read','path':'Pruebas/renamed.txt','shell':'anything'}}))
 reject('private media URL rejected',lambda:video_url('http://127.0.0.1/a.mp4'))
 check('YouTube link normalized',video_url('https://youtu.be/dQw4w9WgXcQ?si=abc')=='https://www.youtube.com/watch?v=dQw4w9WgXcQ')
 protected=Files({'Proyectos':Path('/home/tyrant/Proyectos')});reject('operational ARGOS writes excluded',lambda:protected.writable('Proyectos/argos/README.md'))
report={'checks':checks,'passed':all(c['ok'] for c in checks),'scope':'Disposable synthetic files only; finite boundary checks, not a production security certification'}
Path(__file__).with_name('reports').joinpath('files-capability-checks.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':report['passed'],'checks':len(checks)}))
