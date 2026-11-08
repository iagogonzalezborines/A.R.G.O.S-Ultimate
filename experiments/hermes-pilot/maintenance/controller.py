"""Reviewable self-development transactions. Native Codex owns coding execution/history."""
from __future__ import annotations
import contextlib,difflib,hashlib,json,os,re,secrets,shutil,signal,stat,subprocess,threading,time,traceback
from pathlib import Path
P=Path(__file__).resolve().parents[1];U=P/'ui-workbench';BASE=Path(__file__).parent
EDITABLE={'runtime/conversation.py','runtime/speech_pipeline.py','runtime/stt_worker.py','runtime/tts_worker.py','dist/app.js','dist/progress.js','dist/files.js','dist/window-manager.js','dist/orbital.js','dist/style.css','dist/index.html','checks/desktop-voice-contract.txt'}
CONTEXT=('ui-workbench/runtime/workspace_broker.py','ui-workbench/runtime/projects.py','ui-workbench/runtime/apps.py','ui-workbench/runtime/machine.py','ui-workbench/desktop/main.cjs','ui-workbench/desktop/preload.cjs','ui-workbench/server.py','checks/workspace_mcp.py','checks/project_tool.py','checks/adaptive_tool.py')
def extension_name(name):
 return isinstance(name,str) and bool(re.fullmatch(r'(?:dist/[a-z][a-z0-9_-]{0,63}\.(?:js|css)|runtime/[a-z][a-z0-9_]{0,63}\.py)',name))
class NoSourceChange(ValueError):
 pass
LOCK=threading.RLock()
def clean(value):
 if isinstance(value,dict):return {k:('[redacted]' if type(v)!=bool and re.search(r'(^|_)token$|password|secret|credential|api.?key|authorization|access.?token|refresh.?token',k,re.I) else clean(v)) for k,v in value.items()}
 if isinstance(value,list):return [clean(v) for v in value[:100]]
 if not isinstance(value,str):return value
 value=re.sub(r'(?i)\b(?:nvapi-|sk-|Bearer\s+)[A-Za-z0-9_.-]{8,}','[redacted]',value)
 value=re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+','[redacted]',value)
 value=re.sub(r'(?i)((?:api.?key|password|access.?token|refresh.?token|authorization)\s*[=:]\s*)[^\s,;]+',r'\1[redacted]',value)
 return value[:100000]
def atomic(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);tmp=path.with_name(path.name+'.'+secrets.token_hex(6));data=(json.dumps(clean(value),ensure_ascii=False,indent=2)+'\n').encode()
 fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
 directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(directory)
 finally:os.close(directory)
def digest(data):return hashlib.sha256(data).hexdigest()
def read_regular(path,limit=262144):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  s=os.fstat(fd)
  if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_size>limit:raise PermissionError('Only bounded regular source files are allowed')
  return os.read(fd,limit+1)
 finally:os.close(fd)
def live_path(name,root=U):return P/'checks/desktop-voice-contract.txt' if name=='checks/desktop-voice-contract.txt' and root==U else root/name

def incident_view(row):
 result=dict(row)
 if row.get('code')=='PermissionError' and row.get('message')=='New application files require extending the trusted editable scope; not silently installed':
  result.update(repairable=False,status='previous_scope_limit',diagnosis='El actualizador actual ya admite nuevos módulos de aplicación con revisión exacta. Esta incidencia corresponde al límite anterior; no se instaló ni se reejecutó la propuesta. Una integración que requiera un adaptador del host sigue necesitando ese adaptador real.')
 elif row.get('code')=='PermissionError':
  result.update(repairable=False,status='blocked_by_policy',diagnosis='Operación bloqueada por los permisos actuales. Es una protección, no una avería que Codex deba corregir. Para mejorar ARGOS, usa desarrollo sobre la copia del piloto; la instalación original sigue protegida.')
 else:result['repairable']=True
 return result

class Maintenance:
 def __init__(self,publish=lambda event:None,workspace=lambda:[],*,root=U,state=None,recover=False,auto_diagnose=False):
  self.root=Path(root);self.private=Path(state) if state else BASE/'private';self.private.mkdir(parents=True,exist_ok=True,mode=0o700)
  self.publish=publish;self.workspace=workspace;self.process=None;self.closed=False;self.auto_diagnose=auto_diagnose
  if recover:self.recover()
 def load(self,name,default=None):
  try:return json.loads(read_regular(self.private/name,2097152))
  except FileNotFoundError:return default
 def save(self,name,value):atomic(self.private/name,value)
 def audit(self,event,**fields):
  path=self.private/'audit.jsonl';row=clean({'time':time.time(),'event':event,**fields})
  with LOCK:
   if path.exists() and path.stat().st_size>524288:
    for n in range(2,0,-1):
     old=path.with_suffix('.jsonl.'+str(n));new=path.with_suffix('.jsonl.'+str(n+1))
     if old.exists():os.replace(old,new)
    os.replace(path,path.with_suffix('.jsonl.1'))
   fd=os.open(path,os.O_APPEND|os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600)
   with os.fdopen(fd,'a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
 def incident(self,component,error,*,notify=True):
  frames=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(getattr(error,'__traceback__',None))][-12:]
  message=clean(str(error));code=type(error).__name__;fingerprint=digest(json.dumps([component,code,message,frames],sort_keys=True).encode())
  with LOCK:
   rows=self.load('incidents.json',[]);existing=next((r for r in rows if r['fingerprint']==fingerprint and time.time()-r['last_seen']<3600),None)
   if existing:existing.update(last_seen=time.time(),count=existing['count']+1);row=existing
   else:
    row={'id':secrets.token_hex(12),'fingerprint':fingerprint,'component':component[:60],'code':code,'message':message[:600],'frames':frames,'first_seen':time.time(),'last_seen':time.time(),'count':1,'status':'needs_review','diagnosis':'Execution failed in '+component[:60]+'. The trace is evidence, not an established root cause. Codex can inspect an isolated source copy; a correction requires user approval before installation.'};rows.append(row)
   self.save('incidents.json',rows[-100:]);self.audit('incident',incident_id=row['id'],component=component,code=code,count=row['count'])
  if notify and not existing:
   self.show()
   self.auto_review(row)
  return row
 def auto_review(self,incident):
  # Diagnostic/candidate preparation only; installation always requires exact user review.
  if not self.auto_diagnose or self.closed or incident['component'] not in {'renderer','voice.turn','voice.prepare'} or incident['code'] in {'PermissionError','ValueError','FileNotFoundError'}:return
  with LOCK:
   policy=self.load('auto-policy.json',{});now=time.time();day=int(now//86400)
   if policy.get('day')!=day:policy={'day':day,'count':0,'last_start':0}
   if policy.get('count',0)>=3 or now-policy.get('last_start',0)<600:return
   if any(r['status']=='preparing' for r in self.status()['proposals']):return
   policy.update(count=policy.get('count',0)+1,last_start=now);self.save('auto-policy.json',policy)
  try:
   result=self.propose('Diagnose this recorded ARGOS execution error from its actual trace and the isolated source copy. If a specific source defect can be established, prepare a minimal tested correction for user review. Do not weaken permissions, bypass denials, change unrelated behavior or invent a root cause. If it is a missing device/service or cannot be reproduced from this evidence, report that limitation without modifying source.',incident['id'])
   self.audit('automatic_diagnosis_started',incident_id=incident['id'],proposal_id=result['proposal_id'])
  except Exception as error:self.audit('automatic_diagnosis_deferred',incident_id=incident['id'],reason=clean(str(error)))
 def get(self,ident):
  if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{24}',ident):raise ValueError('Use an existing proposal ID')
  row=self.load('proposals/'+ident+'/proposal.json')
  if not row:raise FileNotFoundError('Proposal not found')
  return row
 def put(self,row):self.save('proposals/'+row['id']+'/proposal.json',row)
 def status(self):
  proposals=[]
  for file in sorted((self.private/'proposals').glob('*/proposal.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20] if (self.private/'proposals').exists() else []:
   row=json.loads(read_regular(file,2097152));proposals.append({k:row.get(k) for k in ['id','goal','status','created','native_thread_id','changed_files','error']})
  return {'scope':'ARGOS isolated desktop pilot only','coding_model':'gpt-6-luna / low','executor':'Native Hermes CodexAppServerSession with existing pilot subscription','commands':'Shell and programming tools in the isolated candidate only; no arbitrary host shell','editable_files':sorted(EDITABLE|self.extensions()),'new_modules':['dist/*.js','dist/*.css','runtime/*.py'],'read_only_context':list(CONTEXT),'protected':'Release/approval controller, broker, launcher, credentials, operational ARGOS, user projects and active IDE sessions','capabilities':['conversation','EN/ES local voice','workspace windows and selected paths','public web search','scoped file explorer and reviewed changes','read-only storage','normal Firefox music','allowlisted installed Linux app launch','incremental native research sources','isolated Codex programming','reviewed update and rollback','bounded redacted incident log'],'workspace':self.workspace(),'incidents':[incident_view(r) for r in self.load('incidents.json',[])[-20:]],'proposals':proposals,'pending_restart':bool(self.load('pending.json'))}
 def show(self):
  self.publish({'type':'presentation','actor':'argos','intent':{'type':'window.open','id':'maintenance','kind':'maintenance','title':'ARGOS · Desarrollo y autolog'}})
  return {'ok':True,'status':'presentation_requested'}
 def extensions(self):
  # Installed source identity comes from the existing release journal.
  names=set()
  for path in (self.private/'proposals').glob('*/proposal.json'):
   row=json.loads(read_regular(path,2097152))
   if row.get('status') not in {'installing','awaiting_health','installed','rolling_back'}:continue
   for change in row.get('changed_files',[]):
    name=change.get('path')
    if name not in EDITABLE and extension_name(name):names.add(name)
  if len(names)>128:raise ValueError('Installed extension inventory exceeds bound')
  return names
 def manifest(self,candidate=False,ident=None,*,names=None):
  result={};folder=self.private/'proposals'/ident/'candidate' if candidate else None
  for name in sorted(set(names) if names is not None else EDITABLE|self.extensions()):
   if name not in EDITABLE and not extension_name(name):raise PermissionError('Invalid source manifest path')
   path=folder/name if candidate else live_path(name,self.root)
   if any(parent.is_symlink() for parent in path.parents):raise PermissionError('Source parent symlinks forbidden')
   try:result[name]=digest(read_regular(path))
   except FileNotFoundError:result[name]=None
  return result
 def source_snapshot(self,row,*,candidate=False):
  return self.manifest(candidate,row['id'],names=set(row['baseline'])|set(row.get('candidate_manifest',{})))
 def expected_baseline(self,row):
  return {**{name:None for name in row.get('candidate_manifest',{})},**row['baseline']}
 def propose(self,goal,incident_id=None):
  if not isinstance(goal,str) or not 4<=len(goal)<=2000 or '\x00' in goal:raise ValueError('Describe a bounded ARGOS change')
  with LOCK:
   if any(r['status'] in {'preparing','queued'} for r in self.status()['proposals']):raise ValueError('A Codex development turn is already running')
   incident=next((i for i in self.load('incidents.json',[]) if i['id']==incident_id),None) if incident_id else None
   if incident_id and not incident:raise ValueError('Use an actual incident from autolog')
   if incident and not incident_view(incident)['repairable']:raise PermissionError('An authorization denial is not a defect to repair; use the scoped pilot development capability')
   ident=secrets.token_hex(12);folder=self.private/'proposals'/ident;candidate=folder/'candidate';candidate.mkdir(parents=True,mode=0o700)
   baseline=self.manifest()
   for name,sha in baseline.items():
    if sha is None:continue
    source=live_path(name,self.root);target=candidate/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(read_regular(source));target.chmod(0o600)
   context=folder/'context';context.mkdir(mode=0o700)
   for name in CONTEXT:
    source=P/name
    if source.is_file():
     target=context/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(read_regular(source))
   instructions='ARGOS isolated development candidate. Edit the copied application source; new flat dist/*.js or dist/*.css modules and runtime/*.py modules are allowed when the live target does not already exist. Tests may be created under tests/. The host architecture is read-only at /context; it is evidence, never an editable release path. The running installation is not mounted. Do not modify permissions, credentials, broker, desktop host, or release controller. If a requested capability needs an absent protected host adapter, report that exact integration gap; do not present a frontend stub as a working integration. Use native commands to implement and test the requested change. This copy need not be a Git repository: the controller produces the exact diff. Return a concise truthful summary; controller validation and exact user review follow.\n'
   (candidate/'AGENTS.md').write_text(instructions)
   row={'id':ident,'goal':clean(goal),'incident_id':incident_id,'created':time.time(),'expires':time.time()+86400,'status':'preparing','baseline':baseline,'workspace':clean(self.workspace()),'incident':incident,'events':[]}
   self.put(row);self.audit('candidate_created',proposal_id=ident)
   threading.Thread(target=self.run,args=(ident,),daemon=True).start()
  self.publish({'type':'process.started','id':'development-'+ident,'title':'Programación · Codex'})
  self.show();return {'ok':True,'proposal_id':ident,'status':'preparing','message':'Native Codex is programming in an isolated copy. No installed files have changed. Review will be requested after validation.'}
 def run(self,ident):
  row=self.get(ident);folder=self.private/'proposals'/ident
  try:
   if self.root!=U:raise RuntimeError('Native development is limited to the real isolated pilot; fixture checks call validation directly')
   codex=folder/'codex';codex.mkdir(mode=0o700);shutil.copyfile(P/'state/codex/auth.json',codex/'auth.json');(codex/'auth.json').chmod(0o600)
   (codex/'config.toml').write_text('forced_login_method="chatgpt"\ncli_auth_credentials_store="file"\ndefault_permissions="argos-candidate"\napproval_policy="never"\nweb_search="disabled"\n[permissions.argos-candidate.filesystem]\n":minimal"="read"\n"/workspace"="write"\n"/context"="read"\n"/tmp"="write"\n'+''.join(json.dumps(str(p))+'="read"\n' for p in [P/'bin',P/'tools',P/'env'])+json.dumps(str(codex))+'="deny"\n[permissions.argos-candidate.network]\nenabled=false\n');(codex/'config.toml').chmod(0o600)
   # Explicit inputs only; neither host context nor logs are scraped by the coder.
   atomic(folder/'request.json',{'goal':row['goal'],'workspace':row['workspace'],'incident':row.get('incident')})
   command=coding_sandbox(folder,[str(P/'env/bin/python'),str(BASE/'codex_worker.py')])
   process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,start_new_session=True);self.process=process
   watchdog=threading.Timer(330,lambda:terminate(process));watchdog.start()
   try:
    for line in process.stdout:
     if len(line)>100000:raise ValueError('Coding output exceeded bound')
     try:event=clean(json.loads(line))
     except ValueError:continue
     current=self.get(ident)
     if current['status']!='preparing':break
     if event.get('thread_id'):current['native_thread_id']=event['thread_id']
     if event.get('type')=='item/completed' and event.get('item_type')=='commandExecution' and event.get('exit_code') not in (None,0):self.incident('codex.command',RuntimeError('Command exit '+str(event['exit_code'])+': '+event.get('output','')[:900]),notify=False)
     current['events']=(current.get('events',[])+[event])[-40:];self.put(current)
     if event.get('type')=='result':
      if not event.get('ok'):raise RuntimeError(event.get('error') or 'Native Codex did not complete')
      current['summary']=event.get('summary','');current['usage']=event.get('usage');self.put(current)
     self.publish({'type':'maintenance.changed','proposal_id':ident})
    process.wait(timeout=5)
    if process.returncode:raise RuntimeError('Native Codex worker stopped without success')
    current=self.get(ident)
    if not current.get('summary'):raise RuntimeError('Native coding result missing')
   finally:watchdog.cancel();terminate(process);self.process=None;(folder/'codex/auth.json').unlink(missing_ok=True)
   self.validate(ident)
  except NoSourceChange:
   current=self.get(ident)
   if current['status']=='preparing':current.update(status='no_change',error=None);self.put(current)
   self.audit('preparation_report_without_patch',proposal_id=ident)
  except Exception as error:
   current=self.get(ident)
   if current['status']=='preparing':current.update(status='failed',error=clean(str(error))[:700]);self.put(current)
   if not self.closed:self.incident('development',error,notify=False)
  outcome=self.get(ident)['status']
  self.publish({'type':'process.completed','id':'development-'+ident,'status':'Cambio listo para revisión' if outcome=='awaiting_review' else 'Informe listo · sin cambio instalable' if outcome=='no_change' else 'Programación finalizada con incidencias'})
  self.publish({'type':'maintenance.changed','proposal_id':ident});self.show()
 def validate(self,ident):
  row=self.get(ident);folder=self.private/'proposals'/ident;candidate=folder/'candidate';changes=[];diff=[]
  # Refuse symlinked parent directories, special files, hardlinks and unexpected edits.
  import itertools
  entries=list(itertools.islice(candidate.rglob('*'),5001))
  if len(entries)>5000:raise ValueError('Candidate tree exceeds bound')
  total=0
  for path in entries:
   if path.is_symlink():raise PermissionError('Candidate symlinks are forbidden')
   if not path.is_dir() and not path.is_file():raise PermissionError('Candidate special files are forbidden')
   relative=path.relative_to(candidate)
   if path.is_file() and relative.parts[0] not in {'.git','__pycache__'} and '__pycache__' not in relative.parts:
    total+=len(read_regular(path))
    if total>4194304:raise ValueError('Candidate content exceeds bound')
   if not path.is_file() or str(relative) in row['baseline'] or relative.parts[0] in {'tests','.git','__pycache__'} or str(relative)=='AGENTS.md' or '__pycache__' in relative.parts:continue
   name=str(relative);target=live_path(name,self.root)
   if not extension_name(name) or target.exists() or target.is_symlink():raise PermissionError('Only new application modules in dist/ or runtime/ are reviewable; existing protected files remain excluded')
  names=set(row['baseline'])|{str(p.relative_to(candidate)) for p in entries if p.is_file() and extension_name(str(p.relative_to(candidate)))}
  for name in sorted(names):
   old=row['baseline'].get(name)
   if name not in EDITABLE and name not in self.extensions() and not extension_name(name):raise PermissionError('Manifest contains an unauthorized path')
   path=candidate/name
   data=read_regular(path) if path.exists() else None;sha=digest(data) if data is not None else None
   if sha==old:continue
   if data is None:raise PermissionError('Source deletion is not enabled')
   original=read_regular(live_path(name,self.root)) if old else b''
   if old and digest(original)!=old:raise PermissionError('Installed source changed during coding')
   after=data.decode('utf-8');before=original.decode('utf-8');changes.append({'path':name,'before':old,'after':sha,'bytes':len(data)})
   diff.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='before/'+name,tofile='after/'+name))
  if not changes:raise NoSourceChange('Codex produced no source change')
  if len(changes)>20 or sum(c['bytes'] for c in changes)>1048576:raise ValueError('Change exceeds bounded review size')
  snapshot=self.manifest(True,ident,names=names)
  if any(snapshot[c['path']]!=c['after'] for c in changes):raise PermissionError('Candidate changed while generating its diff')
  result=validate_candidate(candidate)
  if not result['ok']:raise ValueError('Controller validation failed: '+result['error'])
  if self.manifest(True,ident,names=names)!=snapshot:raise PermissionError('Candidate changed during validation')
  content=''.join(diff)
  if clean(content)!=content:raise PermissionError('Sensitive material detected in patch; a redacted diff cannot authorize hidden source changes')
  if len(content)>100000:raise ValueError('Diff too large for one review')
  row.update(status='awaiting_review',changed_files=changes,diff=content,validation=result,candidate_manifest=snapshot);row['review_digest']=digest(json.dumps([changes,row['candidate_manifest'],row['baseline']],sort_keys=True).encode());self.put(row);self.audit('validation_passed',proposal_id=ident,review_digest=row['review_digest']);return row
 def review(self,ident):
  row=self.get(ident)
  return {k:v for k,v in row.items() if k not in {'baseline','candidate_manifest','workspace'}}
 def confirm(self,ident,sha,approve):
  if type(approve)!=bool:raise ValueError('Explicit review decision required')
  with LOCK:
   row=self.get(ident)
   if row['status']!='awaiting_review' or row['expires']<time.time():raise PermissionError('Review expired or already consumed')
   if sha!=row.get('review_digest'):raise PermissionError('Approval does not match this exact change')
   if not approve:row['status']='rejected';self.put(row);self.audit('rejected',proposal_id=ident);return {'ok':True,'status':'rejected'}
   if self.load('pending.json'):raise PermissionError('Another update awaits restart')
   if self.source_snapshot(row)!=self.expected_baseline(row) or self.source_snapshot(row,candidate=True)!=row['candidate_manifest']:raise PermissionError('Source changed since review; prepare a fresh proposal')
   row['status']='approved';self.put(row);self.save('pending.json',{'id':ident,'review_digest':sha});self.audit('approved',proposal_id=ident,review_digest=sha)
  self.publish({'type':'app.restart','reason':'approved_update'});return {'ok':True,'status':'approved_restart_pending'}
 def apply_pending(self):
  with LOCK:
   pending=self.load('pending.json')
   if not pending:return None
   row=self.get(pending['id']);ident=row['id'];folder=self.private/'proposals'/ident
   if pending.get('rollback'):
    if pending['review_digest']!=row['review_digest']:raise PermissionError('Invalid rollback grant')
    self.rollback(ident);return None
   if row['status']!='approved' or pending['review_digest']!=row['review_digest']:raise PermissionError('No exact user grant')
   if self.source_snapshot(row)!=self.expected_baseline(row) or self.source_snapshot(row,candidate=True)!=row['candidate_manifest']:raise PermissionError('Approved content changed before installation')
   backup=folder/'backup';backup.mkdir(exist_ok=True,mode=0o700)
   for change in row['changed_files']:
    name=change['path'];target=backup/name;target.parent.mkdir(parents=True,exist_ok=True)
    if change['before']:replace_bytes(target,read_regular(live_path(name,self.root)))
   row['status']='installing';self.put(row) # durable journal before first source write
   try:
    for change in row['changed_files']:
     target=live_path(change['path'],self.root);data=read_regular(folder/'candidate'/change['path'])
     if digest(data)!=change['after']:raise PermissionError('Candidate changed during installation')
     replace_bytes(target,data)
    row['status']='awaiting_health';self.put(row);(self.private/'pending.json').unlink();self.audit('installed_awaiting_health',proposal_id=ident);return ident
   except BaseException:self.rollback(ident,reason='installation_failure');raise
 def health_ok(self,ident):
  row=self.get(ident)
  if row['status']!='awaiting_health':raise PermissionError('No pending health gate')
  row['status']='installed';row['installed']=time.time();self.put(row);self.audit('healthy_release',proposal_id=ident)
 def rollback(self,ident,*,reason='user_rollback'):
  with LOCK:
   row=self.get(ident)
   if row['status'] not in {'installing','awaiting_health','installed','rolling_back'}:raise PermissionError('Release is not rollback eligible')
   snapshot=self.source_snapshot(row)
   if row['status']=='installed' and any(snapshot[c['path']]!=c['after'] for c in row['changed_files']):raise PermissionError('Installed code changed; do not overwrite newer work')
   for c in row['changed_files']:
    current=snapshot[c['path']]
    if current not in {c['before'],c['after']}:raise PermissionError('Do not overwrite newer source during rollback')
    if c['before'] and digest(read_regular(self.private/'proposals'/ident/'backup'/c['path']))!=c['before']:raise PermissionError('Backup integrity check failed')
   row['status']='rolling_back';self.put(row)
   for c in row['changed_files']:
    target=live_path(c['path'],self.root)
    if c['before']:replace_bytes(target,read_regular(self.private/'proposals'/ident/'backup'/c['path']))
    else:target.unlink(missing_ok=True)
   row.update(status='rolled_back',rollback_reason=reason);self.put(row);(self.private/'pending.json').unlink(missing_ok=True);self.audit('rolled_back',proposal_id=ident,reason=reason)
 def recover(self):
  for path in (self.private/'proposals').glob('*/proposal.json') if (self.private/'proposals').exists() else []:
   row=json.loads(read_regular(path,2097152))
   if row['status'] in {'installing','awaiting_health','rolling_back'}:self.rollback(row['id'],reason='interrupted_install_or_failed_start')
   elif row['status']=='preparing':row.update(status='interrupted',error='The app closed during native Codex preparation. Nothing was installed.');self.put(row)
 def request(self,args,*,user=False):
  if not isinstance(args,dict) or set(args)-{'action','goal','incident_id','proposal_id','review_digest','approve'}:raise ValueError('Invalid development fields')
  action=args.get('action','status')
  if action=='status':
   result=self.status()
   if not user:
    result['incidents']=[{k:r[k] for k in ('id','component','code','message','frames','count','status','repairable')} for r in result['incidents'][-5:]]
    result['proposals']=result['proposals'][:8]
   return result
  if action=='show':return self.show()
  if action=='review':return self.review(args.get('proposal_id'))
  if action=='propose':return self.propose(args.get('goal'),args.get('incident_id'))
  if action=='rollback' and user:
   row=self.get(args.get('proposal_id'))
   if row['status']!='installed' or row['review_digest']!=args.get('review_digest'):raise PermissionError('Select an installed release')
   if self.load('pending.json'):raise PermissionError('Another update awaits restart')
   self.save('pending.json',{'id':row['id'],'review_digest':row['review_digest'],'rollback':True});self.audit('rollback_approved',proposal_id=row['id']);self.publish({'type':'app.restart','reason':'approved_rollback'});return {'ok':True,'status':'rollback_restart_pending'}
  if action=='confirm' and user:return self.confirm(args.get('proposal_id'),args.get('review_digest'),args.get('approve'))
  raise PermissionError('The model cannot approve, install or roll back its own changes')
 def close(self):
  self.closed=True
  for row in self.status()['proposals']:
   if row['status']=='preparing':
    current=self.get(row['id']);current.update(status='interrupted',error='The application closed during preparation. Nothing was installed.');self.put(current)
  terminate(self.process)
def replace_bytes(target,data):
 target=Path(target)
 if target.is_symlink() or any(p.is_symlink() for p in target.parents):raise PermissionError('Source symlinks forbidden')
 target.parent.mkdir(parents=True,exist_ok=True);temp=target.with_name('.argos-update-'+secrets.token_hex(8));fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 try:
  with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
  os.replace(temp,target)
  directory=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(directory)
  finally:os.close(directory)
 finally:temp.unlink(missing_ok=True)
def terminate(process):
 if process and process.poll() is None:
  with contextlib.suppress(ProcessLookupError):os.killpg(process.pid,signal.SIGTERM)
  try:process.wait(timeout=3)
  except subprocess.TimeoutExpired:
   with contextlib.suppress(ProcessLookupError):os.killpg(process.pid,signal.SIGKILL)

def coding_sandbox(folder,argv):
 """Outer OS scope around unmodified Codex; its command sandbox denies network."""
 from pilot import SOURCE
 folder=Path(folder);candidate=folder/'candidate';codex=folder/'codex'
 cmd=['/usr/bin/bwrap','--die-with-parent','--new-session','--unshare-all','--share-net']
 for p in ['/usr','/bin','/sbin','/lib','/lib64']:
  if Path(p).exists():cmd+=['--ro-bind',p,p]
 cmd+=['--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/run','--dir','/workspace','--bind',str(candidate),'/workspace','--bind',str(codex),str(codex)]
 if (folder/'context').is_dir():cmd+=['--ro-bind',str(folder/'context'),'/context']
 for p in [P/'source',P/'env',P/'tools',P/'bin',BASE/'codex_worker.py',folder/'request.json']:
  cmd+=['--ro-bind',str(p),'/request.json' if p.name=='request.json' else str(p)]
 for p in ['/etc/ssl','/etc/ca-certificates','/etc/resolv.conf','/etc/hosts','/etc/nsswitch.conf','/etc/ld.so.cache']:
  if Path(p).exists():cmd+=['--ro-bind',p,p]
 cmd+=['--clearenv']
 for k,v in {'HOME':'/tmp','PATH':str(P/'bin')+':'+str(P/'tools/node-26.12.1-linux-x64/bin')+':/usr/bin:/bin','PYTHONPATH':str(SOURCE),'CODEX_HOME':str(codex),'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'}.items():cmd+=['--setenv',k,v]
 return cmd+['--chdir','/workspace','--',*argv]
def validation_sandbox(candidate,argv):
 cmd=['/usr/bin/bwrap','--die-with-parent','--unshare-all']
 for p in ['/usr','/bin','/lib','/lib64']:
  if Path(p).exists():cmd+=['--ro-bind',p,p]
 cmd+=['--proc','/proc','--dev','/dev','--tmpfs','/tmp','--ro-bind',str(candidate),'/workspace','--clearenv','--setenv','HOME','/tmp','--setenv','PATH','/usr/bin:/bin','--chdir','/workspace','--',*argv];return cmd

def validate_candidate(candidate):
 script='''import ast,json,pathlib,importlib.util
root=pathlib.Path('/workspace');count=0
for p in root.rglob('*.py'):
 if len(p.parts)>12:raise ValueError('Deep tree')
 ast.parse(p.read_text());count+=1
spec=importlib.util.spec_from_file_location('speech_pipeline',root/'runtime/speech_pipeline.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert m.spoken('Ready. Next sentence.')=='Ready. Next sentence.'
assert m.spoken('[NASA](https://science.nasa.gov/)')==''
assert m.spoken('See [NASA](https://science.nasa.gov/).')=='See NASA.'
print(json.dumps({'python_files':count,'speech_checks':3}))
'''
 try:
  r=subprocess.run(validation_sandbox(candidate,['/usr/bin/python','-c',script]),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25,start_new_session=True)
  if r.returncode:return {'ok':False,'error':clean(r.stderr.decode(errors='replace'))[:1200]}
  checks=json.loads(r.stdout)
  # Parser only: do not run candidate JS with access to the host.
  node=P/'tools/node-26.12.1-linux-x64/bin/node'
  for file in (candidate/'dist').glob('*.js'):
   r=subprocess.run([str(node),'--check',str(file)],env={'PATH':'/usr/bin:/bin'},stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=10)
   if r.returncode:return {'ok':False,'error':clean(r.stderr.decode())[:1200]}
  return {'ok':True,**checks,'javascript':'syntax checked','limits':'Python syntax, JS syntax and three fixed speech-rendering regressions; feature correctness still requires diff/user review and startup health.'}
 except Exception as error:return {'ok':False,'error':clean(str(error))[:1200]}
