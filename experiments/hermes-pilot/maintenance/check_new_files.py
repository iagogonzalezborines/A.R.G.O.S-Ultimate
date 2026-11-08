"""Actual sandbox validation, new-file transactions and denied scope escapes; disposable roots only."""
import json,shutil,sys,tempfile,time,subprocess
from pathlib import Path
from unittest.mock import patch
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P))
from maintenance.controller import Maintenance,EDITABLE,read_regular,live_path,atomic,coding_sandbox
import maintenance.controller as controller
checks=[]
def check(name,ok):checks.append({'name':name,'ok':bool(ok)});assert ok,name
def denied(name,call):
 try:call()
 except (PermissionError,ValueError,FileNotFoundError):check(name,True)
 else:raise AssertionError(name)
old={'code':'PermissionError','message':'New application files require extending the trusted editable scope; not silently installed'}
check('old file-creation denial is explained as the previous scope limit',controller.incident_view(old)['status']=='previous_scope_limit')
with tempfile.TemporaryDirectory(prefix='argos-new-module-') as temporary:
 root=Path(temporary)/'installed';root.mkdir();m=Maintenance(root=root,state=Path(temporary)/'state')
 for name in EDITABLE:
  source=live_path(name)
  if source.exists():
   target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(read_regular(source))
 def draft(name='dist/new-widget.js',code='export const ready = true;\n'):
  ident=controller.secrets.token_hex(12);candidate=m.private/'proposals'/ident/'candidate';candidate.mkdir(parents=True)
  baseline=m.manifest()
  for file,sha in baseline.items():
   if sha is None:continue
   target=candidate/file;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(read_regular(root/file))
  target=candidate/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(code)
  row={'id':ident,'goal':'Disposable new-module transaction','status':'preparing','baseline':baseline,'expires':time.time()+3600};m.put(row);return row,candidate
 row,c=draft();review=m.validate(row['id']);check('new JS file has exact reviewed creation diff',review['changed_files']==[{'path':'dist/new-widget.js','before':None,'after':controller.digest(read_regular(c/'dist/new-widget.js')),'bytes':len(read_regular(c/'dist/new-widget.js'))}] and '+export const ready' in review['diff'])
 check('validation leaves installed module absent',not (root/'dist/new-widget.js').exists())
 denied('model cannot approve new source',lambda:m.request({'action':'confirm','proposal_id':row['id'],'review_digest':review['review_digest'],'approve':True},user=False))
 (root/'dist/new-widget.js').write_text('user file acquired destination\n');denied('new destination appearing after review blocks approval',lambda:m.confirm(row['id'],review['review_digest'],True));(root/'dist/new-widget.js').unlink()
 m.confirm(row['id'],review['review_digest'],True);m.apply_pending();check('new module installed only after exact approval',(root/'dist/new-widget.js').read_text()=='export const ready = true;\n')
 check('new module enters next source inventory','dist/new-widget.js' in m.manifest())
 Maintenance(root=root,state=m.private,recover=True);check('interrupted health removes newly created module',not (root/'dist/new-widget.js').exists() and m.get(row['id'])['status']=='rolled_back')
 row,c=draft('runtime/new_widget.py','VALUE = 1\n');r=m.validate(row['id']);m.confirm(row['id'],r['review_digest'],True);m.apply_pending();m.health_ok(row['id'])
 check('new Python module validates and installs',(root/'runtime/new_widget.py').read_text()=='VALUE = 1\n')
 next_row,next_c=draft('runtime/new_widget.py','VALUE = 2\n');r2=m.validate(next_row['id']);check('subsequent proposal includes installed extension baseline','runtime/new_widget.py' in next_row['baseline'] and r2['changed_files'][0]['before'] is not None)
 (root/'runtime/new_widget.py').write_text('VALUE = 3\n');denied('rollback of new module preserves later user edits',lambda:m.rollback(row['id']));(root/'runtime/new_widget.py').write_text('VALUE = 1\n');m.rollback(row['id']);check('explicit rollback removes new Python module',not (root/'runtime/new_widget.py').exists())
 row,c=draft('dist/new-widget.js');r=m.validate(row['id']);m.confirm(row['id'],r['review_digest'],True);(root/'dist/new-widget.js').write_text('concurrent file\n');denied('destination appearing before install blocks overwrite',m.apply_pending);(root/'dist/new-widget.js').unlink();(m.private/'pending.json').unlink()
 for name in ['desktop/main.cjs','checks/workspace_mcp.py','runtime/__init__.py','dist/.hidden.js','runtime/nested/new.py','dist/new-widget.mjs','maintenance/controller.py']:
  row,c=draft(name,'# forbidden\n');denied('deny path '+name,lambda ident=row['id']:m.validate(ident))
 (root/'dist/maintenance.js').write_text('// protected existing source\n');row,c=draft('dist/maintenance.js','// overwrite\n');denied('existing uneditable module cannot be adopted as new',lambda:m.validate(row['id']))
 row,c=draft();(c/'dist/new-widget.js').unlink()
 try:m.validate(row['id'])
 except controller.NoSourceChange:check('diagnostic with no patch is a typed no-change outcome',True)
 else:raise AssertionError('No-change diagnostic was not classified')
 row,c=draft();(c/'dist/new-widget.js').unlink();(c/'dist/new-widget.js').symlink_to('/etc/hosts');denied('new module symlink denied',lambda:m.validate(row['id']))
 row,c=draft();other=c/'dist/other.js';controller.os.link(c/'dist/new-widget.js',other);denied('new module hardlink denied',lambda:m.validate(row['id']))
 row,c=draft('runtime/new_widget.py','def broken(:\n');denied('new Python syntax failure blocks release',lambda:m.validate(row['id']))
 row,c=draft();r=m.validate(row['id']);(c/'dist/new-widget.js').write_text('export const ready = false;\n');denied('new module changed after review blocks approval',lambda:m.confirm(row['id'],r['review_digest'],True))
 row,c=draft()
 def mutate(candidate):
  (candidate/'dist/new-widget.js').write_text('export const raced = true;\n');return {'ok':True}
 with patch.object(controller,'validate_candidate',mutate):denied('source mutation during validation cannot authorize untested bytes',lambda:m.validate(row['id']))
 row,c=draft();controller.os.mkfifo(c/'tests-pipe');denied('special files cannot enter validation',lambda:m.validate(row['id']))

 row,c=draft();folder=c.parent;context=folder/'context';context.mkdir();(context/'host.txt').write_text('SYNTHETIC_READ_ONLY_ARCHITECTURE\n');(folder/'codex').mkdir();atomic(folder/'request.json',{})
 code="from pathlib import Path; assert Path('/context/host.txt').read_text().startswith('SYNTHETIC'); Path('/context/host.txt').write_text('forbidden')"
 r=subprocess.run(coding_sandbox(folder,['/usr/bin/python','-c',code]),capture_output=True,text=True,timeout=10);check('coder can read architecture but cannot edit it',r.returncode!=0 and 'Read-only file system' in r.stderr)
 check('context unchanged',(context/'host.txt').read_text()=='SYNTHETIC_READ_ONLY_ARCHITECTURE\n')
report={'checks':checks,'scope':'Disposable source and private canaries. No live update, audio, model inference, credentials or desktop actions.'};(P/'ui-workbench/reports/new-file-update-checks.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':len(checks)}))
