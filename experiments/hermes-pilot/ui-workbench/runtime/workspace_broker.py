"""Scoped desktop capabilities. No model loop, conversation memory or task ownership."""
import base64
import ctypes
import hashlib
import json
import mimetypes
import os
import re
from pathlib import Path
import secrets
import socket
import stat
import subprocess
import threading
import time
from urllib.parse import urlsplit, parse_qs
from .storage import Storage
from . import media
from .apps import Apps

ROOT=Path(__file__).resolve().parents[1]
SOCKET=ROOT.parent/'private/workspace.sock'
KINDS={'desktop','project','conversation','summary','note','sources','progress','browser','video','agents','files','document','change','storage','maintenance'}
DENIED={'node_modules','__pycache__','credentials','secrets','venv','env','qwen-env'}

def public_url(value):
 u=urlsplit(value);h=u.hostname or ''
 if u.scheme!='https' or '.' not in h or ':' in h or h.replace('.','').isdigit() or h.endswith(('.local','.internal','.localhost','.test','.invalid')) or u.username or u.password or u.port not in (None,443):raise ValueError('Use a public HTTPS URL')
 return value

def video_url(value):
 public_url(value);u=urlsplit(value);h=u.hostname.lower();ident=None
 if h in {'youtu.be','www.youtu.be'}:ident=u.path.strip('/').split('/')[0]
 elif h in {'youtube.com','www.youtube.com','m.youtube.com'}:
  ident=parse_qs(u.query).get('v',[None])[0]
  if u.path.startswith(('/shorts/','/embed/','/live/')):ident=u.path.split('/')[2]
 if ident:
  import re
  if not re.fullmatch(r'[a-zA-Z0-9_-]{11}',ident):raise ValueError('Invalid YouTube video')
  return 'https://www.youtube.com/watch?v='+ident
 return value

def visible(name):
 low=name.lower()
 return not name.startswith('.') and name not in DENIED and not any(x in low for x in ('secret','credential','api_key','apikey','private_key','password','access_token','auth_token')) and not low.endswith(('.pem','.key','.p12','.pfx','.kdbx'))

from .machine import USER_HOME, PROTECTED_ROOTS

class Files:
 def __init__(self,roots=None,storage=None,progress=None):
  scratch=ROOT.parent/'workspaces/files';scratch.mkdir(exist_ok=True,mode=0o700)
  self.roots=roots or {n:p for n,p in [('Proyectos',USER_HOME/'Proyectos'),('Descargas',USER_HOME/'Descargas'),('Documentos',USER_HOME/'Documentos'),('Escritorio',USER_HOME/'Escritorio'),('ARGOS',scratch),('Personal',USER_HOME)] if p.is_dir()}
  self.base_roots=dict(self.roots);self.storage=storage if roots is None else None
  self.lock=threading.RLock();self.proposals={};self.clipboard=None;self.stopping=threading.Event();self.progress=progress or (lambda event:None)
 def refresh_roots(self):
  if self.storage:self.roots={**self.base_roots,**self.storage.roots()}
 def resolve(self,value):
  self.refresh_roots()
  if not isinstance(value,str) or len(value)>2048 or '\x00' in value:raise ValueError('Invalid path')
  value=value.replace('~/',str(USER_HOME)+'/',1) if value.startswith('~/') else value
  if value in self.roots:return self.roots[value],[]
  for alias,root in self.roots.items():
   for prefix in (alias+'/',str(root)+'/'):
    if value.startswith(prefix):
     parts=value[len(prefix):].split('/')
     if any(p in ('','..','.') or not visible(p) for p in parts):raise PermissionError('Hidden, credential or traversal paths are excluded')
     return root,parts
   if value==str(root):return root,[]
  raise PermissionError('Choose an allowed workspace folder')
 def directory(self,value):
  root,parts=self.resolve(value);fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
  try:
   for part in parts:
    nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nxt
   return fd,root.joinpath(*parts)
  except BaseException:os.close(fd);raise
 def parent(self,value):
  root,parts=self.resolve(value)
  if not parts:raise PermissionError('Cannot operate on a folder root')
  fd,path=self.directory(str(root.joinpath(*parts[:-1])))
  return fd,parts[-1],path/parts[-1]
 def list(self,path=''):
  self.refresh_roots()
  if not path:return {'roots':[{'name':k,'path':str(v)} for k,v in self.roots.items()]}
  fd,full=self.directory(path)
  try:
   entries=[]
   for name in os.listdir(fd):
    if not visible(name):continue
    info=os.stat(name,dir_fd=fd,follow_symlinks=False)
    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):continue
    entries.append({'name':name,'path':str(full/name),'directory':stat.S_ISDIR(info.st_mode),'size':info.st_size,'modified':int(info.st_mtime)})
   entries.sort(key=lambda x:(not x['directory'],x['name'].casefold()))
   return {'path':str(full),'entries':entries[:500],'truncated':len(entries)>500}
  finally:os.close(fd)
 def search(self,query,path=''):
  if not isinstance(query,str) or not 1<=len(query)<=120:raise ValueError('Use a short filename query')
  roots=[path] if path else list(self.roots);queue=[(p,0) for p in roots];found=[];visited=0;deadline=time.monotonic()+2
  while queue and visited<8000 and len(found)<100 and time.monotonic()<deadline:
   current,depth=queue.pop(0)
   try:listing=self.list(current)
   except OSError:continue
   for entry in listing.get('entries',[]):
    visited+=1
    if query.casefold() in entry['name'].casefold():found.append(entry)
    if entry['directory'] and depth<7:queue.append((entry['path'],depth+1))
  return {'query':query,'entries':found[:100],'truncated':bool(queue) or len(found)>100,'searched_entries':visited}
 def read(self,path,*,preview=False):
  fd,name,full=self.parent(path)
  try:
   file=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
   try:
    info=os.fstat(file)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise PermissionError('Only regular files with one link')
    mime=mimetypes.guess_type(name)[0] or 'application/octet-stream'
    result={'path':str(full),'name':name,'size':info.st_size,'mime':mime}
    if mime in {'image/png','image/jpeg','image/webp','image/gif'} and info.st_size<=1500000:
     result['data_url']='data:'+mime+';base64,'+base64.b64encode(os.read(file,1500001)).decode();return result
    if mime=='application/pdf' and info.st_size<=20000000:
     extracted=subprocess.run(['pdftotext','-f','1','-l','10',f'/proc/self/fd/{file}','-'],pass_fds=(file,),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=8)
     if extracted.returncode:raise ValueError('PDF text extraction unavailable')
     data=extracted.stdout;result['text']=data[:32000].decode('utf-8',errors='replace');result['truncated']=len(data)>32000;result['editable']=False;return result
    data=os.read(file,262145)
    if b'\x00' in data:result['text']='Binary file. A format-specific viewer is not connected.';result['editable']=False;return result
    try:text=data[:262144].decode('utf-8')
    except UnicodeDecodeError:result['text']='This format has no text preview.';result['editable']=False;return result
    limit=262144 if preview else 24000
    result.update(text=text[:limit],truncated=info.st_size>limit,editable=info.st_size<=262144,sha256=hashlib.sha256(data).hexdigest() if info.st_size<=262144 else None)
    return result
   finally:os.close(file)
  finally:os.close(fd)
 def writable(self,path):
  root,parts=self.resolve(path);full=root.joinpath(*parts)
  scratch=ROOT.parent/'workspaces/files'
  for protected in PROTECTED_ROOTS:
   if full==protected or full.is_relative_to(protected):
    # The named ARGOS files workspace remains writable; controller files do not.
    if protected==ROOT.parent.resolve() and (full==scratch or full.is_relative_to(scratch)):continue
    raise PermissionError('Operational ARGOS and pilot controller are protected')
  return full
 def fingerprint(self,path):
  fd,name,_=self.parent(path)
  try:
   try:
    f=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
   except FileNotFoundError:return None
   try:
    return self.fingerprint_fd(f)
   finally:os.close(f)
  finally:os.close(fd)
 def fingerprint_fd(self,file):
  s=os.fstat(file)
  if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1:raise PermissionError('Only regular files with one link')
  if s.st_size<=1048576:
   position=os.lseek(file,0,os.SEEK_CUR);os.lseek(file,0,os.SEEK_SET)
   digest=hashlib.sha256(os.read(file,1048577)).hexdigest();os.lseek(file,position,os.SEEK_SET);return digest
  return 'version:'+hashlib.sha256(json.dumps([s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode]).encode()).hexdigest()
 def propose(self,operation,path,destination='',content=''):
  if operation not in {'write','rename','move','copy','mkdir'}:raise ValueError('Unsupported file change')
  if not isinstance(content,str) or len(content.encode())>262144:raise ValueError('Text is too large')
  if operation!='copy':self.writable(path)
  fd,name,full=self.parent(path);os.close(fd)
  before=self.fingerprint(path) if operation!='mkdir' else None
  if operation=='write' and before and self.read(path,preview=True)['size']>262144:raise ValueError('Text edits are limited to 256 KiB; copying and moving larger files are supported.')
  if operation in {'rename','move','copy'}:
   self.writable(destination);fd,n,dest=self.parent(destination)
   try:
    if before is None:raise FileNotFoundError('Source does not exist')
    try:os.stat(n,dir_fd=fd,follow_symlinks=False)
    except FileNotFoundError:pass
    else:raise FileExistsError('Destination already exists')
   finally:os.close(fd)
  if operation=='mkdir' and full.exists():raise FileExistsError('Folder already exists')
  proposal={'id':secrets.token_hex(16),'operation':operation,'path':str(full),'destination':destination,'content':content,'previous_sha256':before,'expires':time.monotonic()+600}
  with self.lock:
   self.proposals={k:v for k,v in self.proposals.items() if v['expires']>time.monotonic()}
   if len(self.proposals)>=30:raise ValueError('Review existing changes first')
   self.proposals[proposal['id']]=proposal
  return {**{k:v for k,v in proposal.items() if k not in {'expires','content'}},'preview':content[:3000],'status':'awaiting_user_review'}
 def confirm(self,ident,approve):
  with self.lock:
   p=self.proposals.pop(ident,None)
   if not p or p['expires']<time.monotonic():raise PermissionError('Change expired or already consumed')
   if not approve:return {'status':'cancelled'}
   op=p['operation'];path=p['path']
   if op!='copy':self.writable(path)
   if op in {'copy','move','rename'}:self.writable(p['destination'])
   if op!='mkdir' and self.fingerprint(path)!=p['previous_sha256']:raise PermissionError('File changed since proposal; review again')
   fd,name,full=self.parent(path)
   try:
    if op=='mkdir':os.mkdir(name,mode=0o755,dir_fd=fd)
    elif op=='write':
     temp='.argos-'+secrets.token_hex(16)
     try:
      out=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
      if p['previous_sha256']:os.fchmod(out,stat.S_IMODE(os.stat(name,dir_fd=fd,follow_symlinks=False).st_mode)&0o777)
      with os.fdopen(out,'wb') as stream:stream.write(p['content'].encode());stream.flush();os.fsync(stream.fileno())
      if self.fingerprint(path)!=p['previous_sha256']:raise PermissionError('File changed while preparing atomic write')
      # New files are never allowed to overwrite a concurrently created target.
      if p['previous_sha256'] is None:os.link(temp,name,src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False);os.unlink(temp,dir_fd=fd)
      else:os.replace(temp,name,src_dir_fd=fd,dst_dir_fd=fd)
     finally:
      try:os.unlink(temp,dir_fd=fd)
      except FileNotFoundError:pass
    else:
     dfd,dname,_=self.parent(p['destination'])
     try:
      if op=='copy':
       source=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
       temp='.argos-copy-'+secrets.token_hex(16)
       try:
        info=os.fstat(source)
        if self.fingerprint_fd(source)!=p['previous_sha256']:raise PermissionError('Source changed since review')
        out=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=dfd)
        os.fchmod(out,stat.S_IMODE(info.st_mode)&0o777)
        copied=0;updated=0
        with os.fdopen(out,'wb') as stream:
         while True:
          if self.stopping.is_set():raise InterruptedError('Copy cancelled because ARGOS is closing')
          data=os.read(source,1048576)
          if not data:break
          stream.write(data);copied+=len(data)
          if time.monotonic()-updated>.2 or copied==info.st_size:
           updated=time.monotonic();self.progress({'type':'files.progress','bytes':copied,'total_bytes':info.st_size,'name':name})
         stream.flush();os.fsync(stream.fileno())
        if self.fingerprint(path)!=p['previous_sha256']:raise PermissionError('Source changed during copying; destination was not published')
        os.link(temp,dname,src_dir_fd=dfd,dst_dir_fd=dfd,follow_symlinks=False)
       finally:
        os.close(source)
        try:os.unlink(temp,dir_fd=dfd)
        except FileNotFoundError:pass
      else:
       libc=ctypes.CDLL(None,use_errno=True)
       if libc.renameat2(fd,os.fsencode(name),dfd,os.fsencode(dname),1):raise OSError(ctypes.get_errno(),'Move rejected; target may exist or be on another filesystem')
      os.fsync(dfd)
     finally:os.close(dfd)
    os.fsync(fd)
   finally:os.close(fd)
   return {'status':'applied','operation':op,'path':path,'destination':p['destination']}
 def copy(self,path):
  fd,name,full=self.parent(path);os.close(fd)
  if self.fingerprint(path) is None:raise FileNotFoundError('File not found')
  with self.lock:self.clipboard={'path':str(full),'fingerprint':self.fingerprint(path),'operation':'copy'}
  return {'status':'copied_to_clipboard','path':str(full),'operation':'copy'}
 def paste(self,directory,*,apply=False):
  with self.lock:clip=dict(self.clipboard) if self.clipboard else None
  if not clip:raise ValueError('The ARGOS file clipboard is empty. Copy a file first.')
  if self.fingerprint(clip['path'])!=clip['fingerprint']:raise PermissionError('The copied file changed. Copy it again before pasting.')
  fd,target=self.directory(directory);os.close(fd);destination=target/Path(clip['path']).name
  if str(destination)==clip['path']:
   base=destination
   for index in range(1,1000):
    candidate=base.with_name(base.stem+' - copy'+(' '+str(index) if index>1 else '')+base.suffix)
    if not os.path.lexists(candidate):destination=candidate;break
   else:raise FileExistsError('No unused copy name available')
  proposal=self.propose('copy',clip['path'],str(destination))
  return self.confirm(proposal['id'],True) if apply else proposal

class WorkspaceBroker:
 def __init__(self,publish,validate,*,socket_path=SOCKET,files=None):
  self.publish=publish;self.validate=validate;self.storage=Storage();self.files=files or Files(storage=self.storage,progress=publish);self.condition=threading.Condition();self.windows=[];self.pending={};self.connected_at=0;self.socket_path=Path(socket_path);self.closed=False;self.epoch=0;self.research_epoch=None;self.development=None;self.apps=Apps();self.research_sources={};self.research_opened=set();self.research_found={};self.research_lock=threading.RLock()
  from .projects import Projects
  self.projects=Projects(lambda intent:self.intent(intent,wait=False))
  from .desktop import Desktop
  self.desktop=Desktop(publish,files=self.files,projects=self.projects,present=lambda intent:self.intent(intent,wait=False))
 def begin_turn(self):
  # Transient display permission only. Native Hermes owns the actual turn/task.
  with self.condition:self.research_epoch=self.epoch;self.research_sources={};self.research_opened=set();self.research_found={}
 def state(self,windows,ack=None,error=None):
  if not isinstance(windows,list) or len(windows)>40:raise ValueError('Invalid workspace snapshot')
  clean=[]
  for w in windows:
   if not isinstance(w,dict) or set(w)-{'id','kind','title','x','y','width','height','minimized','maximized','actor','path','selected_path','url','focused','project','task_id'}:raise ValueError('Invalid window state')
   if not isinstance(w.get('id'),str) or w.get('kind') not in KINDS:raise ValueError('Invalid window state')
   for field in ('project','task_id'):
    if field in w and (w.get('kind')!='project' or not isinstance(w[field],str) or not re.fullmatch('[A-Za-z0-9_-]{1,80}',w[field])):raise ValueError('Invalid project observation')
   clean.append(w)
  with self.condition:
   self.windows=clean;self.connected_at=time.monotonic()
   if ack in self.pending:self.pending[ack]={'ok':not error,'error':str(error)[:200] if error else None,'windows':clean}
   self.condition.notify_all()
  return {'ok':True}
 def intent(self,intent,*,wait=True,actor='argos',expected_epoch=None):
  intent=self.validate(intent);ident=secrets.token_hex(12)
  with self.condition:
   if expected_epoch is not None and expected_epoch!=self.epoch:return {'ok':False,'status':'workspace_cleared'}
   if wait:self.pending[ident]=None
   self.publish({'type':'presentation','actor':actor,'request_id':ident,'intent':intent})
  if not wait:return {'status':'pending','request_id':ident}
  deadline=time.monotonic()+9
  with self.condition:
   while self.pending.get(ident) is None and time.monotonic()<deadline:self.condition.wait(max(0,deadline-time.monotonic()))
   result=self.pending.pop(ident,None)
  return result or {'ok':False,'status':'not_acknowledged','message':'The desktop has not confirmed this action. Do not claim it happened.'}
 def observe_sources(self,sources):
  """Immediate display of native search results, distinct from selected citations."""
  with self.research_lock:
   epoch=self.research_epoch
   if epoch is None or epoch!=self.epoch:return {'ok':False}
   fresh=[]
   for source in sources[:12]:
    try:
     url=source['url'];title=source['title']
     if not isinstance(url,str) or len(url)>2000 or not isinstance(title,str) or not title:continue
     self.validate({'type':'window.open','id':'source-check','kind':'browser','url':url})
    except (ValueError,KeyError,TypeError):continue
    if url not in self.research_found and len(self.research_found)<12:
     row={'url':url,'title':title[:100]};self.research_found[url]=row;fresh.append(row)
   for row in fresh:
    if epoch!=self.epoch:return {'ok':False}
    self.publish({'type':'process.source','id':'web-research','source':row,'stage':'found','found_sources':len(self.research_found)})
   # Open the first actual result as soon as the native search returns, without
   # waiting for another model/tool round. This is a result, not an endorsed citation.
   if fresh:
    row=fresh[0];ident='source-'+hashlib.sha256(row['url'].encode()).hexdigest()[:10]
    with self.condition:slots=sum(w['kind'] in {'browser','video'} for w in self.windows);exists=any(w['id']==ident for w in self.windows)
    if not exists and slots<4 and epoch==self.epoch:
     self.publish({'type':'process.source','id':'web-research','source':row,'stage':'opening','found_sources':len(self.research_found)})
     result=self.intent({'type':'window.open','id':ident,'kind':'browser','title':row['title'],'url':row['url']},expected_epoch=epoch)
     if result.get('ok') and epoch==self.epoch:
      self.research_opened.add(ident)
      self.publish({'type':'process.source','id':'web-research','source':row,'stage':'opened','found_sources':len(self.research_found),'opened_windows':len(self.research_opened)})
   return {'ok':epoch==self.epoch,'found_sources':len(self.research_found)}
 def research(self,a):
  with self.research_lock:return self._research(a)
 def _research(self,a):
  """Deliver native-agent output only. No search, inference or task/memory owner."""
  action=a['action'];epoch=self.epoch
  if self.research_epoch is not None and self.research_epoch!=epoch:
   return {'ok':False,'delivery':action,'displayed':False,'error':'The user cleared the workspace during this turn. Do not reopen research panels.'}
  if action=='research_result':
   text=a.get('text','');speech=a.get('speech','')
   if not isinstance(text,str) or not 0<len(text)<=12000:raise ValueError('A bounded research report is required')
   if not isinstance(speech,str) or not 0<len(speech)<=3000:raise ValueError('Supply the complete spoken conclusion separately')
   result=self.intent({'type':'window.open','id':'research-summary','kind':'summary','title':a.get('title','Research results'),'text':text},expected_epoch=epoch)
   return {'ok':bool(result.get('ok')) and epoch==self.epoch,'delivery':'research_result','speech':speech,'report_characters':len(text),'displayed':bool(result.get('ok')) and epoch==self.epoch,'error':result.get('error') or result.get('message')}
  sources=a.get('sources');count=a.get('open_sources',1)
  if not isinstance(sources,list) or not 1<=len(sources)<=12 or type(count)!=int or not 0<=count<=2:raise ValueError('Use 1–12 selected sources and at most two page panels')
  selected=[];seen=set()
  for source in sources:
   if not isinstance(source,dict) or set(source)-{'url','title'}:raise ValueError('Invalid source')
   url=source.get('url');title=source.get('title','Source')
   if not isinstance(url,str) or len(url)>2000 or not isinstance(title,str) or not 0<len(title)<=150:raise ValueError('Invalid source text')
   self.validate({'type':'window.open','id':'source-check','kind':'browser','url':url})
   if url not in seen:selected.append({'url':url,'title':title});seen.add(url)
  # Accumulate only this native turn's selected URLs; never wait for a final batch.
  with self.condition:
   fresh=[s for s in selected if s['url'] not in self.research_sources]
   if len(self.research_sources)+len(fresh)>12:raise ValueError('At most twelve sources per research turn')
   for source in selected:self.research_sources[source['url']]=source
   accumulated=list(self.research_sources.values())
  result=self.intent({'type':'window.open','id':'sources','kind':'sources','title':a.get('title','Selected sources'),'text':'\n'.join(s['title']+'\n'+s['url'] for s in accumulated)},expected_epoch=epoch)
  opened=[];errors=[]
  if result.get('ok'):
   for source in fresh:
    if epoch!=self.epoch:break
    self.publish({'type':'process.source','id':'web-research','source':source,'selected_sources':len(accumulated),'opened_windows':len(self.research_opened),'stage':'selected'})
   for source in selected[:count]:
    if epoch!=self.epoch:break
    ident='source-'+hashlib.sha256(source['url'].encode()).hexdigest()[:10]
    with self.condition:
     exists=any(w['id']==ident for w in self.windows)
     slots=sum(w['kind'] in {'browser','video'} for w in self.windows)
    if exists:
     self.research_opened.add(ident);continue
    if slots>=4:break
    self.publish({'type':'process.source','id':'web-research','source':source,'stage':'opening','selected_sources':len(accumulated),'opened_windows':len(self.research_opened)})
    delivery=self.intent({'type':'window.open','id':ident,'kind':'browser','title':source['title'][:100],'url':source['url']},expected_epoch=epoch)
    if delivery.get('ok') and epoch==self.epoch and any(w['id']==ident for w in delivery.get('windows',[])):
     opened.append(ident);self.research_opened.add(ident)
     self.publish({'type':'process.source','id':'web-research','source':source,'stage':'opened','selected_sources':len(accumulated),'opened_windows':len(self.research_opened)})
    elif not delivery.get('ok'):errors.append(delivery.get('error') or delivery.get('message') or 'Page panel not acknowledged')
  return {'ok':bool(result.get('ok')) and epoch==self.epoch,'delivery':'research_sources','selected_sources':len(accumulated),'new_sources':len(fresh),'displayed':bool(result.get('ok')) and epoch==self.epoch,'opened_windows':len(opened),'total_opened_windows':len(self.research_opened),'page_load_verified':False,'error':result.get('error') or result.get('message'),'page_errors':errors}

 def request(self,request,*,user=False):
  if not isinstance(request,dict) or set(request)-{'tool','arguments'}:raise ValueError('Invalid tool request')
  tool=request.get('tool');a=request.get('arguments',{})
  if not isinstance(a,dict):raise ValueError('Invalid arguments')
  if tool=='desktop':return self.desktop.request(a,user=user)
  if tool=='projects':
   result=self.projects.request(a,user=user)
   if a.get('action') in {'lifecycle','map_action'} and a.get('operation')=='cancel':
    # Native authorization/CAS succeeds first. Only that task's private seats close.
    with self.desktop.lock:
     for scope in list(self.desktop.scopes.values()):
      if scope.get('task_id')==result.get('id') and scope.get('project')==result.get('project_id'):self.desktop.release(scope)
   return result
  if tool=='adaptive':
   if a=={'operation':'availability'}:return {'enabled':self.projects.enabled and self.projects.config.get('adaptive_enabled') is True}
   return self.projects.request({**a,'action':'adaptive'},user=user)
  if tool=='development':
   if not self.development:raise ValueError('Development capability is not attached')
   if a.get('action')=='show':
    if set(a)!={'action'}:raise ValueError('Unexpected display fields')
    return self.intent({'type':'window.open','id':'maintenance','kind':'maintenance','title':'ARGOS · Desarrollo y autolog'})
   return self.development.request(a,user=user)
  if tool=='workspace':
   if set(a)-{'action','id','kind','title','text','url','path','x','y','width','height','sources','open_sources','speech'}:raise ValueError('Unexpected workspace fields')
   action=a.get('action','inspect')
   if action in {'research_sources','research_result'}:return self.research(a)
   if action=='inspect':
    with self.condition:return {'windows':list(self.windows),'connected':bool(self.connected_at and time.monotonic()-self.connected_at<45),'file_roots':self.files.list()['roots']}
   if action=='arrange':return self.intent({'type':'workspace.arrange'})
   if action=='clear':
    with self.condition:
     self.epoch+=1
     result=self.intent({'type':'workspace.clear'})
    if result.get('ok') and result.get('windows'):return {'ok':False,'message':'The desktop still reports open windows.'}
    return result
   if action=='open':
    intent={'type':'window.open','id':a.get('id') or a.get('kind','note'),'kind':a.get('kind','note'),'title':a.get('title','ARGOS')}
    for k in ('text','url','path','x','y','width','height'):
     if k in a:intent[k]=a[k]
    if intent['kind']=='video':
     if not intent.get('url'):raise ValueError('Choose an actual video URL first')
     intent['url']=video_url(intent['url'])
    if not a.get('id') and intent.get('url'):intent['id']=intent['kind']+'-'+hashlib.sha256(intent['url'].encode()).hexdigest()[:10]
    if intent['kind'] in {'files','document'} and a.get('path'):
     data=self.files.list(a['path']) if intent['kind']=='files' else self.files.read(a['path']);intent['path']=data['path']
    return self.intent(intent)
   if action not in {'close','focus','minimize','restore','maximize','move'}:raise ValueError('Unsupported window action')
   with self.condition:
    if not any(w['id']==a.get('id') for w in self.windows):raise ValueError('Inspect the workspace and use an existing window ID')
   intent={k:v for k,v in a.items() if k in {'id','x','y','width','height'}};intent['type']='window.'+action
   return self.intent(intent)
  if tool=='apps':
   if set(a)-{'action','id','url'}:raise ValueError('Unexpected application fields')
   if a.get('action')=='list':
    result=self.apps.list()
    if self.desktop.availability()['enabled'] and not any(x['id']=='calculator' for x in result['applications']):result['applications'].append({'id':'calculator','name':'Calculadora'})
    return result
   if a.get('action')=='open':
    if a.get('id')=='calculator' and self.desktop.availability()['enabled']:
     if a.get('url') is not None:raise ValueError('Calculator does not accept URLs')
     result=self.desktop.request({'action':'open','application':'calculator'},user=user)
     return {**result,'status':'window_verified' if result.get('window_verified') else result['status'],'name':'Calculadora'}
    return self.apps.open(a.get('id'),a.get('url'))
   raise ValueError('Unknown application action')
  if tool=='media':
   if set(a)-{'action','query'}:raise ValueError('Unexpected media fields')
   if a.get('action')=='status':return media.status()
   if a.get('action')=='play':
    self.publish({'type':'process.started','id':'firefox-media','title':'Música en Firefox'})
    result=media.play(a.get('query'))
    self.publish({'type':'process.completed','id':'firefox-media','status':('Reproduciendo: '+result['title'][:75]) if result.get('ok') else result.get('message','No se confirmó reproducción')[:100]})
    if result.get('ok'):self.intent({'type':'window.open','id':'now-playing','kind':'note','title':'Música · Firefox habitual','text':result['title']+'\n'+result['url']+'\nReproducción comprobada en tu Firefox, con tus ajustes y bloqueador.'},wait=False)
    return result
   raise ValueError('Unsupported media action')
  if tool=='storage':
   if set(a)-{'action','device'}:raise ValueError('Unexpected storage fields')
   action=a.get('action','inspect')
   if action=='inspect':return self.storage.inspect()
   if action=='show':return self.intent({'type':'window.open','id':'storage','kind':'storage','title':'Almacenamiento'})
   if action=='browse':return self.request({'tool':'files','arguments':{'action':'open','path':self.storage.browse(a.get('device'))}},user=user)
   raise ValueError('Unknown read-only storage action')
  if tool!='files':raise ValueError('Unknown capability')
  if set(a)-{'action','path','query','operation','destination','content','proposal_id','approve'}:raise ValueError('Unexpected file fields')
  action=a.get('action','list');path=a.get('path','')
  if action=='copy':return self.files.copy(path)
  if action=='clipboard':
   with self.files.lock:return {'clipboard':{k:v for k,v in self.files.clipboard.items() if k!='fingerprint'} if self.files.clipboard else None}
  if action=='paste':
   result=self.files.paste(path,apply=user)
   if user:self.publish({'type':'files.changed','result':result})
   else:self.intent({'type':'window.open','id':'change-'+result['id'],'kind':'change','title':'Revisar copia de archivo','text':json.dumps(result,ensure_ascii=False)},wait=False)
   return result
  if action=='list':return self.files.list(path)
  if action=='search':return self.files.search(a.get('query',''),path)
  if action=='read':return self.files.read(path,preview=user)
  if action=='review' and user:
   with self.files.lock:p=self.files.proposals.get(a.get('proposal_id'))
   if not p or p['expires']<time.monotonic():raise ValueError('Change expired')
   previous=self.files.read(p['path'],preview=True).get('text','') if p['operation']=='write' and p['previous_sha256'] else ''
   return {**{k:v for k,v in p.items() if k!='expires'},'previous_content':previous}
  if action=='open':
   try:data=self.files.list(path);kind='files'
   except NotADirectoryError:data=self.files.read(path);kind='document'
   return self.intent({'type':'window.open','id':'files' if kind=='files' else 'file-'+hashlib.sha256(data['path'].encode()).hexdigest()[:12],'kind':kind,'title':Path(data['path']).name,'path':data['path']},wait=not user,actor='user' if user else 'argos')
  if action=='propose':
   proposal=self.files.propose(a.get('operation'),path,a.get('destination',''),a.get('content',''))
   self.intent({'type':'window.open','id':'change-'+proposal['id'],'kind':'change','title':'Revisar cambio de archivo','text':json.dumps(proposal,ensure_ascii=False)},wait=False)
   return proposal
  if action=='confirm' and user:
   if type(a.get('approve')) is not bool:raise ValueError('Explicit review choice required')
   result=self.files.confirm(a.get('proposal_id'),a['approve']);self.publish({'type':'files.changed','result':result});return result
  raise PermissionError('The agent cannot approve file changes')
 def serve(self):
  self.socket=socket.socket(socket.AF_UNIX);self.socket_path.parent.mkdir(exist_ok=True,mode=0o700)
  if self.socket_path.exists():self.socket_path.unlink()
  self.socket.bind(str(self.socket_path));self.socket_path.chmod(0o600);self.socket.listen(8);self.socket.settimeout(.5)
  def client(conn):
   with conn:
    request=None
    try:
     conn.settimeout(12);f=conn.makefile('rb');line=f.readline(524289)
     if len(line)>524288:raise ValueError('Request too large')
     request=json.loads(line);result={'ok':True,'result':self.request(request)}
    except Exception as e:
     result={'ok':False,'error':str(e)[:250]}
     if self.development:self.development.incident('capability',e,notify=False)
    with (ROOT/'reports/workspace-capability-audit.jsonl').open('a') as log:
     outcome=result.get('result',{})
     log.write(json.dumps({'time':time.time(),'tool':request.get('tool') if isinstance(request,dict) else None,'action':request.get('arguments',{}).get('action') if isinstance(request,dict) else None,'ok':result['ok'] and outcome.get('ok',True),'error':result.get('error') or outcome.get('error'),'status':outcome.get('status') or outcome.get('state')})+'\n')
    try:conn.sendall((json.dumps(result,ensure_ascii=False)+'\n').encode())
    except (BrokenPipeError,ConnectionResetError):
     if self.development:self.development.audit('capability_client_disconnected')
  def accept():
   while not self.closed:
    try:conn,_=self.socket.accept()
    except TimeoutError:continue
    except OSError:break
    threading.Thread(target=client,args=(conn,),daemon=True).start()
  self.thread=threading.Thread(target=accept,daemon=True);self.thread.start()
 def close(self):
  self.desktop.close()
  if self.development:self.development.close()
  self.closed=True;self.files.stopping.set();self.socket.close();self.thread.join(timeout=1);self.socket_path.unlink(missing_ok=True)
