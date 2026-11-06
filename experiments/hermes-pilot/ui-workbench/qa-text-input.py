"""Bounded trusted text ingress uses the existing conversation queue; no audio/models."""
import asyncio,sys
from pathlib import Path
from runtime.conversation import Conversation,presentation_context
async def main():
 selected={'id':'project-map','kind':'project','project':'p_example','task_id':'t_example','focused':False}
 conversation={'id':'conversation','kind':'conversation','focused':True}
 assert presentation_context([selected,conversation])[1]['task_id']=='t_example'
 assert presentation_context([selected,{'id':'browser','kind':'browser','focused':True}])==[{'id':'browser','kind':'browser','focused':True}]
 assert len(presentation_context([selected,{**selected,'id':'other-map'},conversation]))==1
 host=Conversation(lambda _:None,text_only=True,session_id='argos-text-ingress-check')
 try:
  try:await host.command('text',text='Hola')
  except ValueError:pass
  else:raise AssertionError('preparing accepted text')
  host.status['ready']=True;host.queue=asyncio.Queue(maxsize=2)
  for value in ['', 'x'*12001,'password=synthetic-secret']:
   try:await host.command('text',text=value)
   except ValueError:pass
   else:raise AssertionError('unsafe text admitted')
  await host.command('text',text='Crear biblioteca');await host.command('text',text='Continuar biblioteca')
  try:await host.command('text',text='Una tercera petición')
  except ValueError:pass
  else:raise AssertionError('unbounded conversation queue')
  assert host.queue.get_nowait()[0]=='Crear biblioteca'
  assert host.queue.get_nowait()[0]=='Continuar biblioteca'
  try:await host.command('output',enabled=True)
  except ValueError:pass
  else:raise AssertionError('text mode unexpectedly enabled speech')
  assert host.status['output_muted'] and host.no_capture
 finally:host.loop.close()
asyncio.run(main());print('Text ingress: readiness, bounds, secrets, FIFO and no audio passed')
