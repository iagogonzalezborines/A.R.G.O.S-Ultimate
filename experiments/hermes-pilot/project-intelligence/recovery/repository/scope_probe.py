import errno,hashlib,json,os,pathlib,socket,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parent
ROWS=[]
def check(name,ok,code=None):ROWS.append({'name':name,'ok':bool(ok),'errno':code})
allowed=ROOT/'allowed-artifact.txt';allowed.write_text('AUTHORIZED_ARTIFACT\n');check('repository write/read',allowed.read_text()=='AUTHORIZED_ARTIFACT\n')
for name,path in [('board database', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/native/kanban/boards/secure-proof/kanban.db'), ('board synthetic secret', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/native/kanban/boards/secure-proof/synthetic-board-canary.txt'), ('Hermes synthetic credential', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/native/profiles/engineering/synthetic-credential.txt'), ('Codex synthetic credential', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/codex/synthetic-credential.txt'), ('controller', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/synthetic-controller.txt'), ('other-project', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/private/other-project/canary.txt'), ('operational-argos', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/private/operational-argos/canary.txt'), ('ide', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/private/ide/canary.txt')]:
 try:
  with open(path,'rb') as f:f.read(0)
 except OSError as e:check(name+' read denied',e.errno in (errno.EACCES,errno.EPERM,errno.EROFS,errno.ENOENT),e.errno)
 else:check(name+' read denied',False)
for name,path in [('board', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/native/kanban/boards/secure-proof'), ('Hermes', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/native/profiles/engineering'), ('Codex', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/codex'), ('controller', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/private/controller'), ('other-project', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/private/other-project'), ('operational-argos', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/private/operational-argos'), ('ide', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/private/ide')]:
 try:(pathlib.Path(path)/'unexpected-worker-write').write_text('UNAUTHORIZED_EFFECT')
 except OSError as e:check(name+' write denied',e.errno in (errno.EACCES,errno.EPERM,errno.EROFS,errno.ENOENT),e.errno)
 else:check(name+' write denied',False)
target=[('board database', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/native/kanban/boards/secure-proof/kanban.db'), ('board synthetic secret', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/native/kanban/boards/secure-proof/synthetic-board-canary.txt'), ('Hermes synthetic credential', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/native/profiles/engineering/synthetic-credential.txt'), ('Codex synthetic credential', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/codex/synthetic-credential.txt'), ('controller', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/synthetic-controller.txt'), ('other-project', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/private/other-project/canary.txt'), ('operational-argos', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/private/operational-argos/canary.txt'), ('ide', '/home/tyrant/.local/share/argos-hermes-pilot/project-intelligence/recovery/private/ide/canary.txt')][2][1]
link=ROOT/'outside-link'
if link.is_symlink():link.unlink()
link.symlink_to(target)
try:link.read_bytes()
except OSError as e:check('symlink escape denied',e.errno in (1,2,13,30),e.errno)
else:check('symlink escape denied',False)
link.unlink()
for prefix in ['/proc/1/root','/proc/'+str(os.getppid())+'/root','/proc/self/root']:
 try:
  with open(prefix+target,'rb') as f:f.read(0)
 except OSError as e:check(prefix+' escape denied',e.errno in (1,2,13,30),e.errno)
 else:check(prefix+' escape denied',False)
child=subprocess.run([sys.executable,'-c',"import pathlib,sys; p=pathlib.Path(sys.argv[1]);\ntry:p.read_bytes()\nexcept OSError:sys.exit(0)\nelse:sys.exit(1)",target],capture_output=True)
check('child interpreter inherits read boundary',child.returncode==0)
for family,kind,label in [(socket.AF_INET,socket.SOCK_STREAM,'IPv4 TCP'),(socket.AF_INET6,socket.SOCK_STREAM,'IPv6 TCP'),(socket.AF_INET,socket.SOCK_DGRAM,'UDP')]:
 try:
  sock=socket.socket(family,kind);sock.settimeout(.1)
  if kind==socket.SOCK_DGRAM:sock.sendto(b'canary',('127.0.0.1',9))
  else:sock.connect(('::1',9) if family==socket.AF_INET6 else ('127.0.0.1',9))
 except OSError as e:check(label+' network denied',e.errno in (1,13,101),e.errno)
 else:check(label+' network denied',False)
check('synthetic credential environment stripped','ARGOS_SECRET_CANARY' not in os.environ)
result={'passed':all(r['ok'] for r in ROWS),'checks':ROWS,'probe_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}
(ROOT/'scope-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result));sys.exit(0 if result['passed'] else 1)
