"""Trusted app lifecycle and reviewed release health/rollback supervisor."""
from pathlib import Path
import fcntl,json,os,subprocess,sys,time,urllib.request
ROOT=Path(__file__).resolve().parent;ELECTRON=ROOT.parent/'source/node_modules/electron/dist/electron';URL='http://127.0.0.1:42720'
sys.path.insert(0,str(ROOT.parent))
from maintenance.controller import Maintenance

def health():
 try:
  with urllib.request.urlopen(URL+'/health',timeout=.5) as r:return json.load(r)
 except (OSError,ValueError):return {}
def ready():return health().get('mode')=='argos-app'
def stop(process):
 if process and process.poll() is None:
  process.terminate()
  try:process.wait(timeout=20)
  except subprocess.TimeoutExpired:process.kill();process.wait()

def main():
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--text-only',action='store_true',help='Use the existing conversation without starting microphone or synthesis workers');args=parser.parse_args()
 home=ROOT/'state/home';home.mkdir(parents=True,exist_ok=True,mode=0o700)
 env={'HOME':str(home),'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','ARGOS_UI_PLATFORM':'x11','XDG_CONFIG_HOME':str(ROOT/'state/config'),'XDG_CACHE_HOME':str(ROOT/'state/cache'),'XDG_DATA_HOME':str(ROOT/'state/data'),'XDG_STATE_HOME':str(ROOT/'state/state')}
 for key in ['DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS']:
  if os.environ.get(key):env[key]=os.environ[key]
 private=ROOT/'private';private.mkdir(exist_ok=True,mode=0o700);lease=(private/'app.lock').open('a')
 try:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  alive=False
  try:
   pid=json.loads((ROOT/'state/live-process.json').read_text())['pid'];alive=str(ROOT/'desktop/main.cjs').encode() in Path(f'/proc/{pid}/cmdline').read_bytes()
  except (OSError,ValueError,KeyError):pass
  if alive:
   with (ROOT/'reports/desktop-live.log').open('a') as log:subprocess.run([str(ELECTRON),str(ROOT/'desktop/main.cjs')],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=15)
   return
  for _ in range(150):
   try:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB);break
   except BlockingIOError:time.sleep(.1)
  else:raise SystemExit('ARGOS is still closing. Try again in a moment.')
 maintenance=Maintenance(recover=True);server=None;child=None
 try:
  while True:
   update=None
   try:update=maintenance.apply_pending()
   except Exception as error:
    maintenance.incident('update.install',error,notify=False)
    # Do not launch over an unfinished install; recover/restore first.
    maintenance.recover()
    if maintenance.load('pending.json'):
     (maintenance.private/'pending.json').unlink();maintenance.audit('stale_update_discarded')
   if not ready():
    server_log=(ROOT/'reports/conversation-live.log').open('a');server=subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--text-only' if args.text_only else '--voice'],stdout=server_log,stderr=subprocess.STDOUT)
    for _ in range(40):
     if ready():break
     if server.poll() is not None:break
     time.sleep(.1)
    if not ready():
     stop(server)
     if update:maintenance.rollback(update,reason='backend_start_failed');continue
     raise RuntimeError('ARGOS conversation host did not start')
   with (ROOT/'reports/desktop-live.log').open('a') as log:child=subprocess.Popen([str(ELECTRON),str(ROOT/'desktop/main.cjs')],env=env,stdout=log,stderr=subprocess.STDOUT)
   (ROOT/'state/live-process.json').write_text(json.dumps({'pid':child.pid,'url':URL,'backend':'XWayland/software','started':time.time()}))
   print('ARGOS — conversación y workspace',flush=True);deadline=time.monotonic()+210;failed=False
   while child.poll() is None:
    if server and server.poll() is not None:failed=True;stop(child);break
    if update:
     state=health()
     if state.get('agent_connected') and state.get('renderer_connected'):
      maintenance.health_ok(update);update=None
     elif time.monotonic()>deadline:failed=True;stop(child);break
    time.sleep(.3)
   stop(server);server=None
   if update:
    maintenance.rollback(update,reason='startup_health_failed' if failed else 'closed_before_health_confirmation');maintenance.incident('update.health',RuntimeError('Candidate did not reach voice and renderer readiness; previous source restored'),notify=False);continue
   if maintenance.load('pending.json'):continue
   if failed:maintenance.incident('application',RuntimeError('Conversation host stopped unexpectedly'),notify=False)
   break
 except KeyboardInterrupt:pass
 except Exception as error:maintenance.incident('launcher',error,notify=False);raise
 finally:stop(child);stop(server);maintenance.close();lease.close()
if __name__=='__main__':main()
