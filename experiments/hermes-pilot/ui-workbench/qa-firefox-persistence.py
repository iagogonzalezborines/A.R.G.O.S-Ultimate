"""Firefox registration and launch behavior using disposable metadata and mock processes."""
from pathlib import Path
import tempfile,json
from unittest.mock import patch,MagicMock
from runtime import media
checks=[]
def check(name,condition):checks.append({'name':name,'ok':bool(condition)});assert condition,name
with tempfile.TemporaryDirectory() as d:
 base=Path(d);(base/'profile').mkdir();(base/'profiles.ini').write_text('[Profile0]\nName=default-release\nPath=profile\nIsRelative=1\n[InstallExample]\nDefault=profile\n');file=base/'profile/extensions.json'
 def write(**kwargs):file.write_text(json.dumps({'addons':[{'id':'firefox@argos.local','version':'0.1.4','active':True,'location':'app-profile','signedState':2,**kwargs}]}))
 with patch.object(media,'PROFILE_BASES',(base,)):
  check('missing extension registration is not permanent',not media.installation()['permanent']);write();info=media.installation();check('registered active extension recognized',info['permanent'] and info['enabled'] and info['version']=='0.1.4')
  write(temporarilyInstalled=True,location='app-temporary');check('temporary extension is never called permanent',not media.installation()['permanent'])
  write(userDisabled=True);check('disabled extension not treated as enabled',not media.installation()['enabled'])
  write(appDisabled=True);check('Firefox-blocked extension not treated as enabled',not media.installation()['enabled']);write()
  with patch.object(media,'firefox_running',return_value=True),patch.object(media.subprocess,'Popen') as spawn:check('existing Firefox session is left alone',not media.open_installed_firefox() and not spawn.called)
  with patch.object(media,'firefox_running',return_value=False),patch.object(media.subprocess,'Popen') as spawn,patch.dict(media.os.environ,{'PRIVATE_PROVIDER_KEY':'SYNTHETIC_DO_NOT_INHERIT'}):
   check('closed browser can be launched for permanent extension',media.open_installed_firefox());args,kwargs=spawn.call_args;check('normal Firefox launched without a copied profile',args[0]==['/usr/bin/firefox']);check('launch environment excludes unrelated secrets','PRIVATE_PROVIDER_KEY' not in kwargs['env'])
  file.write_text('{broken');check('partial or malformed registry handled',not media.installation()['permanent'])
  with patch.object(media.subprocess,'Popen') as spawn:check('missing extension does not launch blank windows',not media.open_installed_firefox() and not spawn.called)
 first=MagicMock();first.connect.side_effect=ConnectionRefusedError();second=MagicMock()
 with patch.object(media.socket,'socket',side_effect=[first,second]),patch.object(media,'open_installed_firefox',return_value=True) as launch:
  check('bridge connection retried after browser launch',media.connection() is second and launch.call_count==1);check('failed socket is closed before retry',first.close.called)
Path(__file__).with_name('reports').joinpath('firefox-persistence-checks.json').write_text(json.dumps({'checks':checks,'limits':'Mock registration/launch checks; no real Firefox close/reopen or signed install performed by these tests.'},indent=2)+'\n');print(json.dumps({'passed':len(checks)}))
