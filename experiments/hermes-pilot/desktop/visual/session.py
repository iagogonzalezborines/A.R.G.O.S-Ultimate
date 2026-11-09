"""Private graphics lifetime supervisor, inside the disposable mount/PID namespace."""
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import time

# The supervisor sees neither the user's home nor their graphical/audio sockets.
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
resource.setrlimit(resource.RLIMIT_AS,(1536*1024**2,1536*1024**2))
resource.setrlimit(resource.RLIMIT_NOFILE,(256,256))
resource.setrlimit(resource.RLIMIT_FSIZE,(32*1024**2,32*1024**2))
config=json.loads(Path('/run/av/session.json').read_text());children=[];stopping=False

def stop(*_):
 global stopping
 stopping=True
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)

def start(argv,**kwargs):
 child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**kwargs);children.append(child);return child

try:
 sway=start(['/opt/visual/usr/bin/sway','--unsupported-gpu','-c','/run/av/sway.conf'])
 deadline=time.monotonic()+6
 while not Path('/run/av/ipc.sock').is_socket() or not list(Path('/run/av').glob('wayland-*.lock')):
  if sway.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Compositor unavailable')
  time.sleep(.03)
 os.environ['WAYLAND_DISPLAY']=next(Path('/run/av').glob('wayland-*.lock')).name.removesuffix('.lock')
 holder=subprocess.Popen(['/opt/visual/pointer-seat'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL);children.append(holder)
 import select
 if not select.select([holder.stdout],[],[],2)[0] or holder.stdout.readline()!=b'ready\n':raise RuntimeError('Private pointer unavailable')
 if config['application']=='pad':argv=['/usr/bin/python3','/opt/argos/pad.py']
 elif config['application']=='comparison':argv=['/usr/bin/meld','--newtab','/work/left.txt','/work/right.txt']
 elif 'profile' in config:
  argv=config['profile']['argv']
  if config['profile']['private_bus']:argv=['/usr/bin/dbus-run-session','--config-file=/opt/argos/private-bus.conf','--',*argv]
 else:raise ValueError('Unknown profile')
 app=start(argv)
 ready=Path('/run/av/ready.tmp');ready.write_text(json.dumps({'wayland':os.environ['WAYLAND_DISPLAY'],'pid':app.pid}));ready.replace('/run/av/ready.json')
 # Idle lease is renewed only by Broker operations; no permanent service.
 while not stopping and all(c.poll() is None for c in children):
  if time.time()-Path('/run/av/lease').stat().st_mtime>300:break
  time.sleep(.1)
finally:
 for child in reversed(children):
  if child.poll() is None:
   child.terminate()
   try:child.wait(timeout=1)
   except subprocess.TimeoutExpired:child.kill();child.wait()
 Path('/run/av/ready.json').unlink(missing_ok=True)
