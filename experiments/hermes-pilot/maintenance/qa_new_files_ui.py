"""Real Electron approval for a new module; isolated source/journal, no model/audio/live release."""
from pathlib import Path
import json,sys,tempfile,threading,time,subprocess,urllib.request,urllib.error
P=Path(__file__).resolve().parents[1];sys.path[:0]=[str(P),str(P/'ui-workbench')]
import server
from maintenance.controller import Maintenance,EDITABLE,live_path,read_regular,secrets
with tempfile.TemporaryDirectory(prefix='argos-update-ui-') as temporary:
 base=Path(temporary);root=base/'app';root.mkdir();m=Maintenance(root=root,state=base/'private')
 for name in EDITABLE:
  source=live_path(name)
  if source.exists():target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(read_regular(source))
 ident=secrets.token_hex(12);candidate=m.private/'proposals'/ident/'candidate';candidate.mkdir(parents=True)
 baseline=m.manifest()
 for name,sha in baseline.items():
  if sha is not None:target=candidate/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(read_regular(root/name))
 (candidate/'dist/review-fixture.js').write_text('export const fixture = "new module exact review";\n')
 m.put({'id':ident,'goal':'Disposable new-module UI approval test; not Agent Desktop integration','status':'preparing','baseline':baseline,'expires':time.time()+600});m.validate(ident)
 class Workspace:
  development=m;connected_at=None
  def state(self,*args):self.connected_at=time.monotonic();return {'ok':True}
  def request(self,args,*,user=False):
   if args.get('tool')!='development':raise PermissionError('Fixture only permits development review')
   return m.request(args['arguments'],user=user)
 host=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);host.workspace=Workspace();host.voice=None;host.token=(P/'ui-workbench/private/presentation.token').read_text().strip();m.publish=server.publish
 thread=threading.Thread(target=host.serve_forever,daemon=True);thread.start()
 try:
  node=P/'tools/node-26.12.1-linux-x64/bin/node';out=P/'ui-workbench/reports'
  r=subprocess.run([str(node),str(P/'maintenance/qa_new_files_ui.cjs'),str(host.server_port),ident],timeout=60)
  if r.returncode:raise RuntimeError('New-file review UI failed')
  assert m.get(ident)['status']=='approved' and m.load('pending.json')['id']==ident
  assert not(root/'dist/review-fixture.js').exists()
  original_dist=server.DIST;server.DIST=root/'dist'
  def missing(path):
   try:urllib.request.urlopen(f'http://127.0.0.1:{host.server_port}'+path,timeout=3)
   except urllib.error.HTTPError as error:assert error.code==404
   else:raise AssertionError('Unreleased source was served')
  missing('/review-fixture.js')
  m.apply_pending();assert(root/'dist/review-fixture.js').read_text().startswith('export const fixture')
  with urllib.request.urlopen(f'http://127.0.0.1:{host.server_port}/review-fixture.js',timeout=3) as response:
   assert response.headers['Content-Type']=='text/javascript' and response.read()==read_regular(root/'dist/review-fixture.js')
  (root/'dist/unapproved.js').write_text('export const unapproved = true;\n');missing('/unapproved.js');missing('/../runtime/conversation.py')
  m.recover();assert m.get(ident)['status']=='rolled_back' and not(root/'dist/review-fixture.js').exists()
  missing('/review-fixture.js');server.DIST=original_dist
  data=json.loads((out/'new-file-update-ui.json').read_text());data.update(exact_approval_received=True,no_hot_write=True,approved_new_file_installed=True,approved_module_http_served=True,unapproved_module_http_denied=True,rolled_back_module_http_denied=True,interrupted_health_removed_new_file=True,scope='Disposable source/journal only; no production update or desktop action.');(out/'new-file-update-ui.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(data))
 finally:host.shutdown();host.server_close()
