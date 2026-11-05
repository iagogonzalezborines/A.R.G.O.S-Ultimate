"""Use the already installed narrow Firefox native host; never import browser credentials."""
import configparser,json,os,re,socket,subprocess,time
from pathlib import Path
SOCKET=Path('/home/tyrant/.local/state/argos/firefox.sock')
PROFILE_BASES=(Path('/home/tyrant/.config/mozilla/firefox'),Path('/home/tyrant/.mozilla/firefox'))
def installation():
 # Read extension registration only. Never inspect cookies, logins or browser history.
 for base in PROFILE_BASES:
  try:
   config=configparser.ConfigParser();config.read(base/'profiles.ini')
   selected=next((config[s]['Default'] for s in config.sections() if s.startswith('Install') and 'Default' in config[s]),None)
   if selected is None:selected=next((config[s]['Path'] for s in config.sections() if s.startswith('Profile') and config[s].get('Name')=='default-release'),None)
   if not selected:continue
   profile=Path(selected) if Path(selected).is_absolute() else base/selected
   file=profile/'extensions.json'
   if file.stat().st_size>2097152:continue
   row=next((a for a in json.loads(file.read_text()).get('addons',[]) if a.get('id')=='firefox@argos.local'),None)
   if row:
    permanent=row.get('location')!='app-temporary' and not row.get('temporarilyInstalled',False)
    return {'permanent':permanent,'enabled':bool(row.get('active')) and not row.get('userDisabled') and not row.get('appDisabled'),'version':row.get('version'),'signed_state':row.get('signedState')}
  except (OSError,ValueError,configparser.Error,KeyError,TypeError):continue
 return {'permanent':False,'enabled':False,'version':None,'signed_state':None}
def firefox_running():
 for process in Path('/proc').glob('[0-9]*'):
  try:
   if Path(os.readlink(process/'exe')).name in {'firefox','firefox-bin'}:return True
  except OSError:pass
 return False
def open_installed_firefox():
 addon=installation()
 if not addon['permanent'] or not addon['enabled'] or firefox_running():return False
 env={'HOME':'/home/tyrant','PATH':'/usr/bin:/bin','LANG':os.environ.get('LANG','C.UTF-8')}
 for key in ['DISPLAY','WAYLAND_DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS','XDG_CONFIG_HOME','XDG_SESSION_TYPE','MOZ_ENABLE_WAYLAND']:
  if os.environ.get(key):env[key]=os.environ[key]
 subprocess.Popen(['/usr/bin/firefox'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
 return True
def connection():
 client=socket.socket(socket.AF_UNIX);client.settimeout(55)
 try:client.connect(str(SOCKET));return client
 except OSError:
  client.close()
  if not open_installed_firefox():raise
 deadline=time.monotonic()+10
 while time.monotonic()<deadline:
  client=socket.socket(socket.AF_UNIX);client.settimeout(55)
  try:client.connect(str(SOCKET));return client
  except OSError:client.close();time.sleep(.2)
 raise RuntimeError('Firefox started but the permanent ARGOS media extension did not connect')
def status():
 try:
  with socket.socket(socket.AF_UNIX) as client:client.settimeout(1);client.connect(str(SOCKET))
  connected=True
 except OSError:connected=False
 return {'connected':connected,'browser':'Firefox habitual','profile':'Existing Firefox session; no cookie or account copying','ad_free_guaranteed':False,'installation':installation(),'note':'Uses the browser\u2019s installed blocker. Playback verification excludes an ad at the moment checked, not all future ads.'}
def play(query):
 if not isinstance(query,str) or not 0<len(query.strip())<=300 or any(ord(c)<32 for c in query):raise ValueError('Use a song title and artist, at most 300 characters.')
 try:
  with connection() as client:
   client.sendall((json.dumps({'action':'play','query':query})+'\n').encode());raw=client.makefile('rb').readline(16385)
  if len(raw)>16384:raise ValueError('Invalid Firefox result')
  result=json.loads(raw)
 except (OSError,ValueError) as error:raise RuntimeError('Firefox media bridge unavailable. Install the Mozilla-signed permanent ARGOS Media Bridge extension and enable it in your normal Firefox.') from error
 if result.get('status')!='playing':
  messages={'autoplay_blocked':'Firefox blocked autoplay. Allow audio/video autoplay for YouTube.','page_blocked':'YouTube requires attention in Firefox (consent or login).','no_match':'No video title matched the requested artist and song.','timeout':'The video did not confirm playback; do not claim it is playing.','busy':'Firefox is already handling another ARGOS music request.'}
  return {'ok':False,'status':result.get('status','unavailable'),'message':messages.get(result.get('status'),'Firefox did not confirm playback.')}
 if not isinstance(result.get('title'),str) or len(result['title'])>1000 or not re.fullmatch(r'https://www\.youtube\.com/watch\?v=[a-zA-Z0-9_-]{11}',result.get('url','')):raise ValueError('Invalid playback evidence')
 return {'ok':True,'status':'playing','title':result['title'],'url':result['url'],'browser':'Firefox habitual','verification':'requested_video_advancing_and_not_showing_ad_at_check','ad_free_guaranteed':False}
