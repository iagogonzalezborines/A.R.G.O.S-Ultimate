"""Research presentation permissions and truthful delivery checks, no provider calls."""
import json
from pathlib import Path
from runtime.workspace_broker import WorkspaceBroker
from server import validate
checks=[]
def check(name,condition):
 checks.append({'name':name,'ok':bool(condition)});assert condition,name
def reject(name,args):
 before=len(events)
 try:b.request({'tool':'workspace','arguments':args})
 except (ValueError,PermissionError):check(name,len(events)==before)
 else:raise AssertionError(name)
events=[];b=None
def acknowledge(e):
 events.append(e)
 if 'intent' not in e:return
 intent=e['intent'];windows=list(b.windows)
 if intent['type']=='window.open':windows=[w for w in windows if w['id']!=intent['id']]+[{k:intent[k] for k in ['id','kind','title'] if k in intent}]
 elif intent['type']=='workspace.clear':windows=[]
 b.state(windows,e['request_id'])
b=WorkspaceBroker(acknowledge,validate)
for url in ['http://example.com/','https://127.0.0.1/','https://localhost/','https://host.internal/','file:///etc/passwd','https://user:pass@example.com/']:
 reject('reject source '+url,{'action':'research_sources','sources':[{'url':url,'title':'untrusted'}]})
reject('reject extra authorization field',{'action':'research_sources','sources':[{'url':'https://example.com','title':'x','shell':'no'}]})
reject('validate whole list before displaying',{'action':'research_sources','sources':[{'url':'https://example.com','title':'good'},{'url':'file:///etc/passwd','title':'bad'}]})
reject('bound automatic browser count',{'action':'research_sources','sources':[{'url':'https://example.com','title':'good'}],'open_sources':3})
r=b.request({'tool':'workspace','arguments':{'action':'research_sources','sources':[{'url':'https://example.com','title':'one'},{'url':'https://example.com','title':'duplicate'}]}})
check('distinct selected URLs only',r['selected_sources']==1);check('count actual acknowledged source panels',r['opened_windows']==1 and r['ok']);check('opening is not page verification',not r['page_load_verified'])
b.state([{'id':'existing-'+str(i),'kind':'browser'} for i in range(4)])
r=b.request({'tool':'workspace','arguments':{'action':'research_sources','sources':[{'url':'https://example.org','title':'next'}],'open_sources':2}})
check('full browser budget preserves user pages',r['opened_windows']==0 and len([w for w in b.windows if w['kind']=='browser'])==4)
r=b.request({'tool':'workspace','arguments':{'action':'research_result','text':'Full report\nhttps://example.com','speech':'A complete spoken conclusion.'}})
check('detailed report and spoken answer kept separately',r['ok'] and r['speech']=='A complete spoken conclusion.' and events[-1]['intent']['text'].startswith('Full report'))
b.begin_turn();b.request({'tool':'workspace','arguments':{'action':'clear'}});before=len(events)
r=b.request({'tool':'workspace','arguments':{'action':'research_result','text':'Late report','speech':'Late answer'}})
check('clear suppresses late native research delivery',not r['ok'] and len(events)==before)
b.begin_turn();r=b.request({'tool':'workspace','arguments':{'action':'research_result','text':'New report','speech':'New answer'}})
check('new native turn can display results again',r['ok'])
# Renderer refusal must never become success.
def refused(e):b.state([],e['request_id'],'Synthetic renderer failure')
b.publish=refused
r=b.request({'tool':'workspace','arguments':{'action':'research_result','text':'Report','speech':'Answer'}})
check('renderer refusal does not claim displayed',not r['ok'] and not r['displayed'] and 'failure' in r['error'])
report={'checks':checks};Path(__file__).with_name('reports').joinpath('research-boundaries.json').write_text(json.dumps(report,indent=2));print(json.dumps({'passed':len(checks)}))
