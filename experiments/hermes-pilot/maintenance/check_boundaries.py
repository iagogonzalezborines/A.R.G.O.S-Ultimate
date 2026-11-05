"""Finite update transaction, OS containment, secret redaction and recovery tests."""
import sys,tempfile,json,shutil,subprocess,os
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P))
from maintenance.controller import *
checks=[]
def check(name,condition):checks.append({'name':name,'ok':bool(condition)});assert condition,name
def reject(name,call):
 try:call()
 except (PermissionError,ValueError,FileNotFoundError):check(name,True)
 else:check(name,False)
with tempfile.TemporaryDirectory(prefix='argos-update-') as d:
 root=Path(d)/'installed';root.mkdir();state=Path(d)/'private';m=Maintenance(root=root,state=state);events=[];m.publish=events.append
 for name in EDITABLE:
  source=live_path(name);dest=root/name
  if source.exists():dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(read_regular(source))
 def proposal():
  ident=secrets.token_hex(12);folder=state/'proposals'/ident/'candidate';folder.mkdir(parents=True)
  for name in EDITABLE:
   source=root/name
   if source.exists():target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(read_regular(source))
  (folder/'dist/style.css').write_text((folder/'dist/style.css').read_text()+'\n/* disposable validation change */\n')
  row={'id':ident,'goal':'Disposable CSS change','status':'preparing','baseline':m.manifest(),'expires':time.time()+3600};m.put(row);return m.validate(ident)
 r=proposal();ident=r['id'];check('candidate validation produces reviewable diff',r['validation']['ok'] and 'disposable validation' in r['diff']);check('installed source unchanged during preparation',m.manifest()==r['baseline'])
 reject('native agent cannot approve',lambda:m.request({'action':'confirm','proposal_id':ident,'review_digest':r['review_digest'],'approve':True},user=False))
 reject('native agent cannot rollback',lambda:m.request({'action':'rollback','proposal_id':ident,'review_digest':r['review_digest']},user=False))
 reject('mismatched digest denied',lambda:m.confirm(ident,'wrong',True));reject('path traversal denied',lambda:m.get('../secrets'))
 f=state/'proposals'/ident/'candidate/dist/style.css';original=f.read_text();f.write_text(original+'\n/* changed */');reject('candidate changed after review denied',lambda:m.confirm(ident,r['review_digest'],True));f.write_text(original)
 live=root/'dist/style.css';before=live.read_text();live.write_text(before+'\n/* concurrent edit */');reject('live code changed after review denied',lambda:m.confirm(ident,r['review_digest'],True));live.write_text(before)
 m.confirm(ident,r['review_digest'],True);check('user approval queues restart without hot-writing',m.manifest()==r['baseline'] and events[-1]['type']=='app.restart');reject('approval replay denied',lambda:m.confirm(ident,r['review_digest'],True))
 m.apply_pending();check('exact approved candidate installed',m.manifest()==r['candidate_manifest']);check('health still pending after file write',m.get(ident)['status']=='awaiting_health')
 restored=Maintenance(root=root,state=state,recover=True);check('failed/interrupted startup rolls back',restored.manifest()==r['baseline'] and restored.get(ident)['status']=='rolled_back')
 r=proposal();m.confirm(r['id'],r['review_digest'],True);m.apply_pending();m.health_ok(r['id']);check('explicit health completion marks release installed',m.get(r['id'])['status']=='installed')
 m.request({'action':'rollback','proposal_id':r['id'],'review_digest':r['review_digest']},user=True);m.apply_pending();check('user-requested rollback restores baseline',m.manifest()==r['baseline'])
 r=proposal();m.confirm(r['id'],r['review_digest'],False);check('reject never installs',m.manifest()==r['baseline'] and m.get(r['id'])['status']=='rejected')
 r=proposal();m.confirm(r['id'],r['review_digest'],True);f=state/'proposals'/r['id']/'candidate/dist/style.css';f.write_text('changed after approval');reject('candidate changed before restart denied',m.apply_pending);(state/'pending.json').unlink()
 r=proposal();m.confirm(r['id'],r['review_digest'],True);m.apply_pending();m.health_ok(r['id']);live.write_text(live.read_text()+'\n/* newer work */');reject('rollback preserves later source edits',lambda:m.rollback(r['id']));live.write_bytes(read_regular(state/'proposals'/r['id']/'candidate/dist/style.css'));m.rollback(r['id'])
 r=proposal();candidate=state/'proposals'/r['id']/'candidate';(candidate/'escape').symlink_to('/etc');reject('candidate symlinks denied',lambda:m.validate(r['id']));(candidate/'escape').unlink()
 source=candidate/'runtime/speech_pipeline.py';source.write_text('def broken(:\n');reject('broken Python blocks review',lambda:m.validate(r['id']))
 try:raise RuntimeError('Synthetic failure with password=DO_NOT_STORE and Bearer abcdefghijklmnop')
 except Exception as e:first=m.incident('test',e,notify=False);second=m.incident('test',e,notify=False)
 check('incidents deduplicate',first['id']==second['id'] and second['count']==2);stored=(state/'incidents.json').read_text();check('secrets absent from autolog','DO_NOT_STORE' not in stored and 'abcdefghijklmnop' not in stored);check('trace preserved without raw user audio',bool(second['frames']) and 'audio' not in second)
 for i in range(105):m.incident('bounded',RuntimeError(str(i)),notify=False)
 check('incident retention bounded to 100',len(m.load('incidents.json'))==100)
 # No credentials, host projects, release approval files or broker socket are mounted.
 folder=Path(d)/'sandbox';(folder/'candidate').mkdir(parents=True);(folder/'codex').mkdir();(folder/'request.json').write_text('{}')
 probe="import pathlib,json; paths=['/home/tyrant/Proyectos','/home/tyrant/.codex','/run/argos-workspace.sock','"+str(BASE/'private/pending.json')+"']; assert not any(pathlib.Path(p).exists() for p in paths); pathlib.Path('/workspace/sandbox-marker').write_text('ok'); print('contained')"
 run=subprocess.run(coding_sandbox(folder,['/usr/bin/python','-c',probe]),capture_output=True,text=True,timeout=15);check('coding outer sandbox hides host projects/IDE/broker/approval files',run.returncode==0)
 probe="import socket; s=socket.socket(); s.settimeout(.1); s.connect(('127.0.0.1',42720))"
 run=subprocess.run(validation_sandbox(folder/'candidate',['/usr/bin/python','-c',probe]),capture_output=True,text=True,timeout=15);check('validation sandbox has no host loopback access',run.returncode!=0)
 report={'checks':checks,'limits':'Finite containment and transaction checks, not a complete security certification. Native coder has its own isolated subscription credential context.'};(P/'ui-workbench/reports/self-development-boundaries.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':len(checks)}))
