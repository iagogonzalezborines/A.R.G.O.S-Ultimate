"""Incremental delivery, launch boundaries and native observer regressions (offline)."""
import asyncio,json,os,sys,time,tomllib,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from runtime.workspace_broker import WorkspaceBroker
from runtime.apps import Apps
from runtime.conversation import Conversation
from server import validate
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from checks.desktop_observer import observe_session

checks=[]
def check(name,ok):
 checks.append({'name':name,'ok':bool(ok)});assert ok,name
events=[];b=None
def acknowledge(e):
 events.append(e)
 if 'intent' not in e:return
 intent=e['intent'];windows=list(b.windows)
 if intent['type']=='window.open':windows=[w for w in windows if w['id']!=intent['id']]+[{k:intent[k] for k in ('id','kind','title','url') if k in intent}]
 elif intent['type']=='workspace.clear':windows=[]
 b.state(windows,e['request_id'])
b=WorkspaceBroker(acknowledge,validate);b.begin_turn()
def source(url,title):return b.request({'tool':'workspace','arguments':{'action':'research_sources','sources':[{'url':url,'title':title}],'open_sources':1}})
first=source('https://science.nasa.gov/','NASA')
check('first source displayed without waiting for a second',first['ok'] and first['selected_sources']==1 and first['opened_windows']==1)
first_events=len(events)
second=source('https://www.esa.int/','ESA')
check('later source appends rather than replaces',second['selected_sources']==2 and 'NASA' in next(e['intent']['text'] for e in reversed(events) if e.get('intent',{}).get('id')=='sources'))
check('individual opening progress is visible between sources',any(e.get('stage')=='opened' for e in events[:first_events]) and any(e.get('stage')=='opening' for e in events[first_events:]))
count=len([e for e in events if e.get('intent',{}).get('kind')=='browser'])
again=source('https://science.nasa.gov/','NASA')
check('duplicate URL never navigates or opens twice',again['new_sources']==0 and again['opened_windows']==0 and count==len([e for e in events if e.get('intent',{}).get('kind')=='browser']))
prior=len(events)
try:source('file:///etc/passwd','Bad')
except ValueError:pass
else:raise AssertionError('Unsafe source accepted')
check('unsafe streaming source cannot alter display',len(events)==prior and len(b.research_sources)==2)
b.request({'tool':'workspace','arguments':{'action':'clear'}});prior=len(events)
late=source('https://example.com/','Late')
check('clear suppresses late source and progress',not late['ok'] and len(events)==prior)
b.begin_turn();new=source('https://example.org/','New')
check('source counts belong to current native turn',new['selected_sources']==1)

apps=Apps();launched=[]
def spawn(argv,**kw):
 launched.append((argv,kw));return SimpleNamespace(poll=lambda:None)
with patch('runtime.apps.Path.is_file',return_value=True),patch('runtime.apps.os.access',return_value=True),patch('runtime.apps.subprocess.Popen',side_effect=spawn),patch.dict(os.environ,{'NVIDIA_API_KEY':'placeholder-secret','CODEX_HOME':'/private-ide','DISPLAY':':test'}):
 r=apps.open('firefox','https://example.com/')
 check('launch uses fixed executable and argv without a shell',launched[-1][0]==['/usr/bin/firefox','https://example.com/'] and not launched[-1][1].get('shell'))
 check('launch does not inherit provider or IDE credentials',not {'NVIDIA_API_KEY','CODEX_HOME'}&launched[-1][1]['env'].keys())
 check('launch reports dispatch without inventing window confirmation',r['status']=='launch_dispatched' and not r['window_verified'])
 for ident,url in [('sh',None),('firefox','file:///etc/passwd'),('firefox','https://127.0.0.1/'),('firefox','https://example.com/\n--profile'),('calculator','https://example.com/')]:
  prior=len(launched)
  try:apps.open(ident,url)
  except ValueError:pass
  else:raise AssertionError('Unsafe app request accepted')
  check('reject unsafe app input '+ident+' '+str(url),len(launched)==prior)

forwarded=[];notes=[];agent=SimpleNamespace(_codex_session=SimpleNamespace(_on_event=forwarded.append))
observe_session(agent,notes.append);observe_session(agent,notes.append)
for method,item in [('item/started',{'type':'contextCompaction'}),('item/completed',{'type':'contextCompaction'}),('item/completed',{'type':'webSearch','action':{'type':'openPage','url':'https://science.nasa.gov/'}})]:
 agent._codex_session._on_event({'method':method,'params':{'item':item}})
check('observer preserves all original native callbacks once',len(forwarded)==3)
check('actual native compaction stages are observable',sum(n['event']=='context.compaction' for n in notes)==2)
check('native opened source is forwarded before final answer',notes[-1]['event']=='web.source' and notes[-1]['url']=='https://science.nasa.gov/')
b.begin_turn();before=len(events)
observed=b.observe_sources([{'url':'https://www.esa.int/','title':'ESA result'},{'url':'file:///etc/passwd','title':'Unsafe result'}])
check('native discovered results display before model selection',observed['ok'] and observed['found_sources']==1 and any(e.get('stage')=='found' for e in events[before:]))
check('discovery does not pretend to be selected citations',not b.research_sources)
old=b.epoch;b.request({'tool':'workspace','arguments':{'action':'clear'}});before=len(events)
stale=b.intent({'type':'window.open','id':'late','kind':'note','text':'Late'},expected_epoch=old)
check('epoch guard rejects source open racing with clear',not stale['ok'] and len(events)==before)
agent._codex_session._on_event({'method':'item/completed','params':{'item':{'type':'webSearch','results':[{'url':'https://www.esa.int/','title':'ESA result'}]}}})
check('native result metadata streams without a model round trip',notes[-1]['event']=='web.sources' and notes[-1]['sources'][0]['title']=='ESA result')
async def local_launch():
 calls=[];replies=[]
 host=Conversation.__new__(Conversation);host.generation=0;host.language='en';host.status={'dialogue_open':True};host.emit=lambda e:None
 host.workspace=SimpleNamespace(request=lambda req:calls.append(req) or {'name':'Firefox'})
 async def reply(text,generation):replies.append(text)
 host.reply=reply
 started=time.monotonic();await host.accept('Argos, open Firefox',direct=True)
 check('simple launch bypasses model latency',calls[-1]['tool']=='apps' and calls[-1]['arguments']['id']=='firefox' and time.monotonic()-started<.2)
 check('simple launch preserves English response',replies[-1]=='Opening Firefox.')
 await host.accept('Argos, abre el navegador',direct=True)
 check('Spanish browser request launches usual browser',calls[-1]['arguments']['id']=='firefox' and replies[-1]=='Abriendo Firefox.')
asyncio.run(local_launch())
# Check the real connector, not just a mock broker or advertised schema.
pilot=Path(__file__).resolve().parent.parent
reply=subprocess.run([sys.executable,str(pilot/'checks/workspace_mcp.py')],input=json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/list'})+'\n',capture_output=True,text=True,check=True)
advertised={tool['name'] for tool in json.loads(reply.stdout)['result']['tools']}
configured=set(tomllib.loads((pilot/'state/codex/config.toml').read_text())['mcp_servers']['argos-workspace']['enabled_tools'])
check('every advertised desktop capability is enabled in the actual Codex connector',advertised==configured)
report={'checks':checks,'provider_calls':0,'real_apps_launched':0}
Path(__file__).with_name('reports').joinpath('progressive-desktop-offline.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':len(checks)}))
