"""Real child startup deadlines/stages/cleanup and component graph failure checks."""
import asyncio,json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from runtime.conversation import Worker,WorkerStartupError,Conversation
from maintenance.controller import Maintenance,incident_view
checks=[]
def check(name,ok):checks.append({'name':name,'ok':bool(ok)});assert ok,name
async def main():
 stages=[]
 async def stage(name,value):stages.append((name,value))
 script="import json,sys;print(json.dumps({'event':'startup.stage','stage':'compiling'}),flush=True);print(json.dumps({'ready':True}),flush=True);sys.stdin.read()"
 w=Worker([sys.executable,'-c',script],name='speech',startup_timeout=2)
 r=await w.start(stage);check('startup progress is not mistaken for readiness',r['ready'] and ('speech','compiling') in stages and stages[-1]==('speech','ready'));await w.close();check('ready worker closes',w.process.returncode is not None)
 w=Worker([sys.executable,'-c','import time;time.sleep(10)'],name='speech',startup_timeout=.05)
 try:await w.start()
 except WorkerStartupError as e:check('timeout identifies actual component',e.component=='speech' and '0.05' in str(e))
 else:raise AssertionError('missing timeout')
 check('timed out worker is reaped',w.process.returncode is not None)
 w=Worker([sys.executable,'-c',"import json,sys;print(json.dumps({'ready':False,'code':'codex_startup_failed','category':'RuntimeError'}),flush=True);sys.stdin.read()"],name='codex',startup_timeout=2)
 try:await w.start()
 except WorkerStartupError as e:check('reported startup failure retains component and code',e.component=='codex' and 'codex_startup_failed' in str(e))
 else:raise AssertionError('missing failure')
 w=Worker([sys.executable,'-c','import time;time.sleep(10)'],name='recognition',startup_timeout=30);task=asyncio.create_task(w.start());await asyncio.sleep(.05);task.cancel();await asyncio.gather(task,return_exceptions=True);check('cancelled startup reaps child',w.process.returncode is not None)
 created=[]
 class FakeWorker:
  def __init__(self,*args,name='worker',**kwargs):self.name=name;self.closed=False;created.append(self)
  async def start(self,on_stage):
   await on_stage(self.name,'starting')
   if self.name=='codex':raise WorkerStartupError('codex','synthetic handshake failure')
   await asyncio.sleep(30)
  async def close(self):self.closed=True
 host=Conversation(lambda event:None,no_capture=True,session_id='argos-startup-graph-check')
 with patch('runtime.conversation.Worker',FakeWorker):await host.prepare()
 check('one failure closes all startup workers',len(created)==3 and all(w.closed for w in created));check('partial initialization never reports ready',not host.status['ready'] and host.status['startup_error_component']=='codex' and not host.status['codex_ready']);host.loop.close()
 with tempfile.TemporaryDirectory() as d:
  m=Maintenance(state=Path(d));r=m.incident('capability',PermissionError('Operational ARGOS is protected'),notify=False);view=m.status()['incidents'][0]
  check('existing permission denials are displayed as protection',view['repairable'] is False and view['status']=='blocked_by_policy')
  try:m.propose('Weaken protection to repair the denial',r['id'])
  except PermissionError:check('policy denial cannot be submitted as a repair',True)
  else:raise AssertionError('denial repair accepted')
report=None
asyncio.run(main());Path(__file__).with_name('reports').joinpath('startup-lifecycle-checks.json').write_text(json.dumps({'checks':checks},indent=2)+'\n');print(json.dumps({'passed':len(checks)}))
