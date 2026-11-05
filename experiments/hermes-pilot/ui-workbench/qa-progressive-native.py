"""Small real subscription test. No audio workers, host launch or arbitrary shell."""
import asyncio,json,sys,time,tempfile
from pathlib import Path
from runtime.conversation import Worker
from runtime.workspace_broker import WorkspaceBroker
from server import validate
P=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(P))
from pilot import sandbox,PYTHON

async def main():
 sid='argos-progressive-native-check-20261105-v2'
 events=[];broker=None
 def acknowledge(e):
  if 'intent' not in e:return
  intent=e['intent'];windows=list(broker.windows)
  if intent['type']=='window.open':windows=[w for w in windows if w['id']!=intent['id']]+[{k:intent[k] for k in ('id','kind','title','url') if k in intent}]
  elif intent['type']=='workspace.clear':windows=[]
  broker.state(windows,e['request_id'])
 temporary=tempfile.TemporaryDirectory(prefix='argos-progressive-');socket_path=Path(temporary.name)/'workspace.sock'
 broker=WorkspaceBroker(acknowledge,validate,socket_path=socket_path);broker.serve()
 cmd=sandbox([PYTHON,P/'checks/desktop_runtime.py',sid],network=True)
 i=cmd.index('--chdir');cmd[i:i]=['--ro-bind',str(socket_path),'/run/argos-workspace.sock','--setenv','HERMES_TERMINAL_SECURITY_MODE','approval-required']
 w=Worker(cmd,prefix=b'ARGOS_JSON ',name='codex',startup_timeout=45);report={'turns':[],'audio_workers':0,'host_app_launches':0,'renderer_simulated':True}
 try:
  report['startup']=await w.start();print(json.dumps({'ready':report['startup']['codex_ready'],'startup_seconds':report['startup']['startup_seconds']}),flush=True)
  for text in [
   'Research who created Batman. Use two primary sources and show what you find.',
   'What is seven times eight?',
   'I am planning a lamp. Its body is matte grey, 25 cm tall. Just acknowledge those details.',
   'Change its colour to dark blue. Keep everything else.',
   'What are its colour, finish and height?',
   'Is the sky green?',
  ]:
   broker.begin_turn();events=[];start=time.monotonic()
   async def event(e):
    events.append({'seconds':round(time.monotonic()-start,4),**e})
    if e.get('event')=='web.sources':
     outcome=await asyncio.to_thread(broker.observe_sources,e['sources'])
     print(json.dumps({'native_found_sources':outcome,'at':events[-1]['seconds']}),flush=True)
    if e.get('event')=='workspace.research':print(json.dumps({'event':e['delivery'],'sources':e.get('selected_sources'),'at':events[-1]['seconds']}),flush=True)
   result=await w.call({'text':text,'workspace':[]},on_event=event)
   report['turns'].append({'input':text,'result':result,'events':events})
   print(json.dumps({'input':text,'speech':result.get('speech'),'seconds':result.get('seconds'),'ok':result.get('ok')}),flush=True)
  checks=[]
  def check(name,ok):checks.append({'name':name,'ok':bool(ok)})
  research=report['turns'][0];deliveries=[e for e in research['events'] if e.get('event')=='workspace.research' and e.get('delivery')=='research_sources' and e.get('displayed')]
  final=next((e for e in research['events'] if e.get('delivery')=='research_result' and e.get('displayed')),None)
  check('native research succeeds',research['result']['ok'])
  check('first source is published individually',deliveries and deliveries[0].get('selected_sources')==1)
  check('additional sources append during the same turn',len(deliveries)>=2 and deliveries[-1]['selected_sources']>=2)
  observed=[e for e in research['events'] if e.get('event')=='web.sources']
  check('native results are available before model delivery',observed and deliveries and observed[0]['seconds']<deliveries[0]['seconds'])
  check('first source precedes report',bool(final and deliveries and deliveries[0]['seconds']<final['seconds']))
  check('new arithmetic topic is answered directly','56' in report['turns'][1]['result']['speech'] and 'batman' not in report['turns'][1]['result']['speech'].lower())
  check('correction retains other attributes',all(x in report['turns'][4]['result']['speech'].lower() for x in ['blue','matte','25']))
  check('unrelated banter is not tied to prior object','lamp' not in report['turns'][5]['result']['speech'].lower())
  check('no test turn compacts',not any(e.get('event')=='context.compaction' for t in report['turns'] for e in t['events']))
  report['checks']=checks
  print(json.dumps({'checks':checks}),flush=True)
 finally:
  await w.close();broker.close();temporary.cleanup();(P/'ui-workbench/reports/progressive-native.json').write_text(json.dumps(report,indent=2)+'\n')
asyncio.run(main())
