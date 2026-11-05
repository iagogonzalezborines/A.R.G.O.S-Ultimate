"""Narrow host application launcher. Fixed executables, no shell or caller arguments."""
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

# Deliberately not .desktop Exec parsing: a downloaded launcher must not become
# an arbitrary command capability. Missing applications are simply unavailable.
CATALOG={
 'firefox':('Firefox','/usr/bin/firefox'),
 'code':('Visual Studio Code','/usr/bin/code'),
 'code-oss':('Code OSS','/usr/bin/code-oss'),
 'dolphin':('Dolphin','/usr/bin/dolphin'),
 'calculator':('Calculadora','/usr/bin/gnome-calculator'),
 'discord':('Discord','/usr/bin/discord'),
 'steam':('Steam','/usr/bin/steam'),
 'mpv':('mpv','/usr/bin/mpv'),
 'qview':('qView','/usr/bin/qview'),
}

class Apps:
 def __init__(self):self.children=[]
 def list(self):
  return {'applications':[{'id':k,'name':v[0]} for k,v in CATALOG.items() if Path(v[1]).is_file() and os.access(v[1],os.X_OK)],'browser':'firefox','arbitrary_commands':False}
 def open(self,app_id,url=None):
  if app_id not in {a['id'] for a in self.list()['applications']}:raise ValueError('Choose an installed application ID from apps.list')
  argv=[CATALOG[app_id][1]]
  if url is not None:
   if app_id!='firefox' or not isinstance(url,str) or not 0<len(url)<=2000 or any(ord(c)<32 for c in url):raise ValueError('Only Firefox accepts a public HTTPS URL')
   u=urlsplit(url);h=u.hostname or ''
   if u.scheme!='https' or '.' not in h or ':' in h or h.replace('.','').isdigit() or h.endswith(('.local','.internal','.localhost','.test','.invalid')) or u.username or u.password or u.port not in (None,443):raise ValueError('Use a public HTTPS URL')
   argv.append(url)
  env={'HOME':'/home/tyrant','PATH':'/usr/bin:/bin','LANG':os.environ.get('LANG','C.UTF-8')}
  for key in ('DISPLAY','WAYLAND_DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CURRENT_DESKTOP','XDG_SESSION_TYPE','MOZ_ENABLE_WAYLAND'):
   if os.environ.get(key):env[key]=os.environ[key]
  self.children=[p for p in self.children if p.poll() is None]
  child=subprocess.Popen(argv,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
  self.children.append(child)
  return {'ok':True,'status':'launch_dispatched','application':app_id,'name':CATALOG[app_id][0],'window_verified':False}
