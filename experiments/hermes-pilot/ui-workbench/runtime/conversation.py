"""Voice/presentation I/O host. Native Hermes owns conversation and model execution."""
import asyncio
import base64
import collections
import contextlib
import json
import math
import os
from pathlib import Path
import re
import signal
import struct
import sys
import threading
import time
import wave

ROOT=Path(__file__).resolve().parents[1]
PILOT=ROOT.parent
VOICE=PILOT/'voice-tests/2026-11-05'
sys.path.insert(0,str(PILOT))
from .machine import ARGOS_SRC, STT_PYTHON, MICROPHONE, SPEECH_DEVICE
sys.path.insert(0,str(ARGOS_SRC))
from pilot import sandbox,PYTHON
from argos.wake import Endpoint
from argos.echo import EchoCancellation
from argos.language import voice_invocation,normalized,choose_language
from .speech_pipeline import SpeechPipeline
from .speech_settings import SpeechSettings
from .startup import StartupTrace,stderr_summary

def presentation_context(windows):
 focus=[w for w in windows if w.get('focused')][:1]
 maps=[w for w in windows if w.get('kind')=='project']
 related=maps if focus and focus[0].get('kind')=='conversation' and len(maps)==1 else []
 selected=focus+related+[w for w in windows if w.get('selected_path') and w not in focus]
 return [{k:w[k] for k in ('id','kind','title','path','selected_path','url','focused','project','task_id') if k in w} for w in selected[:2]]


class WorkerStartupError(RuntimeError):
 def __init__(self,component,detail,diagnostics=None,*,retryable=False):
  self.component=component;self.diagnostics=diagnostics or {};self.retryable=retryable;super().__init__(component+': '+detail)

class Worker:
 def __init__(self,command,env=None,prefix=b'',*,name='worker',startup_timeout=90):self.command=command;self.env=env;self.prefix=prefix;self.process=None;self.lock=asyncio.Lock();self.name=name;self.startup_timeout=startup_timeout
 async def read(self):
  while True:
   line=await asyncio.wait_for(self.process.stdout.readline(),240)
   if not line:raise RuntimeError('Worker disconnected')
   if self.prefix:
    if not line.startswith(self.prefix):continue
    line=line[len(self.prefix):]
   return json.loads(line)
 async def start(self,on_stage=None):
  started=time.monotonic();self.last_stage='starting';self.stderr_tail=bytearray();self.starting=True;self.stderr_task=None
  async def drain():
   while self.process:
    chunk=await self.process.stderr.read(4096)
    if not chunk:break
    if self.starting:self.stderr_tail.extend(chunk);self.stderr_tail[:]=self.stderr_tail[-16000:]
  try:
   if on_stage:await on_stage(self.name,'starting')
   self.process=await asyncio.create_subprocess_exec(*map(str,self.command),env=self.env,
       stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,start_new_session=True,limit=2**20)
   self.stderr_task=asyncio.create_task(drain())
   async with asyncio.timeout(self.startup_timeout):
    while True:
     ready=await self.read()
     if ready.get('event'):
      if ready['event']=='startup.stage':
       self.last_stage=ready.get('stage','starting')
       if on_stage:await on_stage(self.name,self.last_stage)
      continue
     if not ready.get('ready'):raise WorkerStartupError(self.name,ready.get('code','initialization_failed')+' ('+ready.get('category','unknown')+')')
     ready['startup_seconds']=time.monotonic()-started
     self.starting=False;self.stderr_tail.clear()
     if on_stage:await on_stage(self.name,'ready')
     return ready
  except TimeoutError as error:
   await self.close()
   diagnostics={'last_stage':self.last_stage,**stderr_summary(self.stderr_tail)}
   retryable=self.name=='codex' and self.last_stage in {'runtime_import','import_agent','import_state','import_provider'}
   raise WorkerStartupError(self.name,'readiness timed out after '+str(self.startup_timeout)+' seconds at '+self.last_stage,diagnostics,retryable=retryable) from error
  except BaseException as error:
   diagnostics={'last_stage':self.last_stage,**stderr_summary(self.stderr_tail)}
   if isinstance(error,WorkerStartupError):error.diagnostics=diagnostics
   await self.close()
   if isinstance(error,(asyncio.CancelledError,WorkerStartupError)):raise
   raise WorkerStartupError(self.name,type(error).__name__+' during initialization at '+self.last_stage,diagnostics) from error
 async def call(self,value,on_event=None):
  async with self.lock:
   if not self.process or self.process.returncode is not None:raise RuntimeError('Worker stopped')
   self.process.stdin.write((json.dumps(value,ensure_ascii=False)+'\n').encode());await self.process.stdin.drain()
   while True:
    response=await self.read()
    if response.get('event'):
     if on_event:await on_event(response)
     continue
    return response
 def interrupt(self):
  if self.process and self.process.returncode is None:
   with contextlib.suppress(ConnectionError,RuntimeError):self.process.stdin.write(b'{"op":"interrupt"}\n')
 async def close(self):
  if not self.process or self.process.returncode is not None:return
  self.process.stdin.close()
  try:await asyncio.wait_for(self.process.wait(),2)
  except TimeoutError:
   with contextlib.suppress(ProcessLookupError):os.killpg(self.process.pid,signal.SIGTERM)
   try:await asyncio.wait_for(self.process.wait(),3)
   except TimeoutError:
    with contextlib.suppress(ProcessLookupError):os.killpg(self.process.pid,signal.SIGKILL)
    await self.process.wait()
  if getattr(self,'stderr_task',None):
   try:await asyncio.wait_for(asyncio.shield(self.stderr_task),.5)
   except TimeoutError:
    self.stderr_task.cancel();await asyncio.gather(self.stderr_task,return_exceptions=True)

class Conversation:
 def __init__(self,emit,*,no_capture=False,mute=False,text_only=False,session_id='argos-workspace-default',workspace=None):
  self.text_only=text_only;no_capture=no_capture or text_only
  self.emit=emit;self.no_capture=no_capture;self.mute=mute;self.sid=session_id;self.workspace=workspace
  if not re.fullmatch(r'[a-zA-Z0-9-]{1,80}',session_id):raise ValueError('Invalid native session ID')
  self.audio_root=ROOT/'state/audio'/session_id
  self.speech_settings=SpeechSettings(ROOT/'private'/('voice-settings.json' if not no_capture else 'qa-voice-settings-'+session_id+'.json'))
  self.status={'phase':'preparing','ready':False,'listening':False,'dialogue_open':False,'microphone':MICROPHONE,'model':'gpt-6-luna','voice':'Qwen + Peter · Referencia','session_id':session_id,'echo_cancellation':False,'output_muted':False}
  self.status['output_muted']=text_only or not self.speech_settings.enabled()
  self.status['text_only']=text_only
  self.status.update(playback_simulated=bool(mute),microphone_capture_disabled=bool(no_capture))
  self.status.update(speech_ready=False,recognition_ready=False)
  self.startup_trace=StartupTrace(ROOT/'private/startup'/session_id/'latest.json')
  self.loop=asyncio.new_event_loop();self.thread=threading.Thread(target=self.run,daemon=True)
  self.generation=0;self.language='en';self.record=None;self.player=None;self.echo=EchoCancellation();self.closed=False;self.last_answer='';self.speaking=False;self.turn_running=False;self.tasks=[]
 def start(self):self.thread.start()
 def run(self):
  asyncio.set_event_loop(self.loop)
  def unhandled(loop,context):
   if self.workspace and self.workspace.development:self.workspace.development.incident('voice.loop',context.get('exception') or RuntimeError(context.get('message','Asynchronous voice failure')))
  self.loop.set_exception_handler(unhandled);self.prepare_task=self.loop.create_task(self.prepare());self.loop.run_forever()
 def state(self,phase=None,**values):
  self.status.update(values)
  if phase:self.status['phase']=phase
  self.emit({'type':'voice.state',**self.status})
 def post(self,op,**values):
  return asyncio.run_coroutine_threadsafe(self.command(op,**values),self.loop)
 async def prepare(self):
  self.state('preparing',ready=False,codex_ready=False,voice_ready=False,speech_ready=False,recognition_ready=False,error=None,startup_error_component=None,startup_retries=0,components={})
  self.queue=asyncio.Queue(maxsize=2)
  env={'HOME':str(VOICE/'home'),'PATH':'/usr/bin:/bin','HF_HOME':str(VOICE/'hf'),'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_IMPLICIT_TOKEN':'1','TOKENIZERS_PARALLELISM':'false','ARGOS_STARTUP_EVENTS':'1','PYTHONDONTWRITEBYTECODE':'1','TORCHINDUCTOR_CACHE_DIR':str(PILOT/'cache/torch-streaming')}
  libraries=VOICE/'qwen-env/lib/python3.12/site-packages/nvidia'
  stt_env={**env,'LD_LIBRARY_PATH':':'.join(str(libraries/name/'lib') for name in ['cublas','cudnn','cuda_runtime'])}
  self.stt=Worker([STT_PYTHON,ROOT/'runtime/stt_worker.py'],stt_env,name='recognition',startup_timeout=60)
  self.tts=Worker([VOICE/'qwen-env/bin/python',ROOT/'runtime/tts_worker.py',self.sid],env,name='speech',startup_timeout=180 if SPEECH_DEVICE=='cuda' else 600)
  cmd=sandbox([PYTHON,PILOT/'checks/desktop_runtime.py',self.sid],network=True)
  cmd[cmd.index('--chdir'):cmd.index('--chdir')]=['--ro-bind',str(PILOT/'private/workspace.sock'),'/run/argos-workspace.sock']
  # Native permission profile + existing read-only fixture and controller deny policy.
  cmd[cmd.index('--chdir'):cmd.index('--chdir')]=['--setenv','HERMES_TERMINAL_SECURITY_MODE','approval-required']
  cmd[cmd.index('--chdir'):cmd.index('--chdir')]=['--setenv','ARGOS_STARTUP_EVENTS','1']
  self.model=Worker(cmd,prefix=b'ARGOS_JSON ',name='codex',startup_timeout=45)
  async def stage(name,value):
   self.startup_trace.record(name,value)
   self.state(components={**self.status.get('components',{}),name:value},**({'codex_ready':value=='ready'} if name=='codex' else {}))
   labels={'codex':'Codex','recognition':'reconocimiento','speech':'voz'}
   if value!='ready':self.emit({'type':'voice.caption','text':'Preparando '+labels[name]+(' · compilando audio local' if value=='compiling' else '…')})
  # Establish native conversation before competing with multi-GB audio model
  # loads. This changes startup ordering only; ordinary turns remain unchanged.
  initializers=[];turn_task=None
  try:
   for attempt in range(2):
    task=asyncio.create_task(self.model.start(stage));initializers.append(task)
    try:
     model_ready=await task;break
    except WorkerStartupError as error:
     if attempt or not error.retryable:raise
     self.startup_trace.record('codex','retrying_import',error=error,diagnostics=error.diagnostics)
     self.state(startup_retries=1)
     self.emit({'type':'voice.caption','text':'Recuperando el inicio de Codex…'})
   self.status['api_mode']=model_ready.get('api_mode');self.status['codex_ready']=model_ready.get('codex_ready',False)
   self.status['startup_seconds']={'codex':model_ready['startup_seconds']}
   self.state('preparing' if not self.text_only else 'standby',ready=True)
   turn_task=asyncio.create_task(self.turns());self.tasks.append(turn_task)
   if not self.text_only:
    audio_workers=(self.stt,self.tts)
    audio_tasks=[asyncio.create_task(worker.start(stage)) for worker in audio_workers];initializers.extend(audio_tasks)
    audio=await asyncio.gather(*audio_tasks,return_exceptions=True)
    failures=[]
    for worker,result in zip(audio_workers,audio):
     if isinstance(result,BaseException):
      failures.append(worker.name);self.startup_trace.record(worker.name,'failed',error=result,diagnostics=getattr(result,'diagnostics',None))
      if self.workspace and self.workspace.development:self.workspace.development.incident('voice.prepare',result)
     else:
      self.status['startup_seconds'][worker.name]=result['startup_seconds']
      if worker.name=='recognition':self.status.update(recognition_ready=True,recognition_model=result.get('model'),recognition_device=result.get('device'))
      else:self.status.update(speech_ready=True,voice_streaming=result.get('streaming',False),speech_engine_pin=result.get('engine_pin'))
    self.status['startup_failures']=failures
   self.state('standby',ready=True,voice_ready=self.status['speech_ready'] and self.status['recognition_ready'])
   self.startup_trace.record('application','ready' if self.text_only or self.status.get('voice_ready') else 'degraded')
   if not self.no_capture and self.status['recognition_ready']:await self.listen(True)
  except BaseException as error:
   if turn_task:
    turn_task.cancel();await asyncio.gather(turn_task,return_exceptions=True)
    if turn_task in self.tasks:self.tasks.remove(turn_task)
   for task in initializers:
    if not task.done():task.cancel()
   await asyncio.gather(*initializers,return_exceptions=True)
   await asyncio.gather(self.stt.close(),self.tts.close(),self.model.close(),return_exceptions=True)
   if isinstance(error,asyncio.CancelledError) or self.closed:raise
   component=getattr(error,'component','startup')
   self.startup_trace.record(component,'failed',error=error,diagnostics=getattr(error,'diagnostics',None))
   if self.workspace and self.workspace.development:self.workspace.development.incident('voice.prepare',error)
   self.state('error',ready=False,codex_ready=False,components={name:('failed' if name==component else 'stopped') for name in ('codex','recognition','speech')},startup_error_component=component,error='No se pudo iniciar '+{'codex':'Codex','recognition':'el reconocimiento','speech':'la voz'}.get(component,'la conversación')+'. Pulsa el micrófono para reintentar; el detalle está en el autolog.')
 async def listen(self,enabled):
  self.generation+=1
  if getattr(self,'tts_active',False):self.tts.interrupt()
  if hasattr(self,'model') and self.turn_running:self.model.interrupt()
  await self.stop_player()
  if self.record and self.record.returncode is None:
   self.record.terminate();await self.record.wait()
  self.record=None
  if getattr(self,'capture_task',None):self.capture_task.cancel()
  await self.echo.stop()
  self.status['dialogue_open']=False
  if not enabled:
   self.state('off',listening=False,echo_cancellation=False)
   self.emit({'type':'voice.caption','text':'Microphone off.' if self.language=='en' else 'Micrófono apagado.'});return
  if self.no_capture:self.state('standby',listening=False);return
  target=MICROPHONE
  probe=await asyncio.create_subprocess_exec('pactl','-f','json','list','sources','short',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
  data,_=await probe.communicate()
  if target not in {s['name'] for s in json.loads(data)}:
   self.state('error',listening=False,error='El micrófono configurado no está conectado.');return
  await self.echo.start(target)
  source=self.echo.source if self.echo.active else target
  self.record=await asyncio.create_subprocess_exec('pw-record','--target',source,'--raw','--rate=16000','--channels=1','--format=s16','-',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
  self.capture_task=asyncio.create_task(self.capture())
  self.state('standby',listening=True,echo_cancellation=self.echo.active,error=None)
 async def capture(self):
  endpoint=Endpoint();claimed=False;active_at=0
  try:
   while self.record and self.record.returncode is None:
    frame=await self.record.stdout.readexactly(640)
    if self.speaking and not self.echo.active:
     endpoint.reset();claimed=False;continue
    audio=endpoint.feed(frame)
    if endpoint.consecutive>=8 and not claimed:
     claimed=True;active_at=time.monotonic()
     if self.status['dialogue_open']:
      self.generation+=1
      if getattr(self,'tts_active',False):self.tts.interrupt()
      if self.turn_running:self.model.interrupt()
      await self.stop_player()
      self.state('listening')
    if audio:
     claimed=False
     if self.queue.full():self.queue.get_nowait();self.queue.task_done()
     self.queue.put_nowait((audio,self.generation))
    elif not endpoint.frames:claimed=False
  except asyncio.CancelledError:pass
  except asyncio.IncompleteReadError:
   if self.status['listening'] and not self.closed:self.state('error',listening=False,error='El micrófono dejó de enviar audio.')
  except Exception:self.state('error',listening=False,error='Se interrumpió la captura del micrófono.')
 async def turns(self):
  while not self.closed:
   audio,generation=await self.queue.get()
   try:
    if generation!=self.generation:continue
    if isinstance(audio,str):
     await self.accept(audio,generation=generation,direct=True);continue
    self.state('transcribing')
    result=await self.stt.call({'pcm':base64.b64encode(audio).decode(),'previous_language':self.language})
    if generation!=self.generation:continue
    await self.accept(result.get('text',''),result.get('language'),result.get('language_probability',0),generation,recognition={k:result[k] for k in ('seconds','decode_passes','audio_seconds') if k in result})
   except Exception as error:
    if self.workspace and self.workspace.development:self.workspace.development.incident('voice.turn',error)
    self.state('error',error='La petición no pudo completarse. Puedes volver a hablar.')
   finally:
    self.queue.task_done()
    if self.status['listening'] and not self.speaking:self.state('listening' if self.status['dialogue_open'] else 'standby')
 async def accept(self,text,detected=None,probability=0,generation=None,*,direct=False,recognition=None):
  if not text.strip():return
  generation=self.generation if generation is None else generation
  invocation=voice_invocation(text)
  if invocation is not None:self.status['dialogue_open']=True;text=invocation
  norm=normalized(text)
  if norm in {'stop listening','turn off the microphone','deja de escuchar','apaga el microfono','no escuches'}:
   self.language=choose_language(text,self.language,detected,probability);await self.listen(False);return
  if not self.status['dialogue_open'] and not direct:return
  if not text.strip():self.state('listening',dialogue_open=True,error=None);return
  # A recorded failure belongs to the previous request. Clear it only after
  # accepting a new addressed turn; passive standby audio must not erase it.
  self.status['error']=None
  self.language=choose_language(text,self.language,detected,probability)
  self.emit({'type':'voice.transcript','text':text,'language':self.language})
  if norm in {'eso es todo','hasta luego',"that's all",'that is all','goodbye'}:
   self.status['dialogue_open']=False
   await self.reply('Goodbye.' if self.language=='en' else 'Hasta luego.',generation)
   return
  if norm in {'stop','silence','silencio','basta','para de hablar'}:
   self.generation+=1;await self.stop_player();self.state('listening');return
  if norm in {'unmute your voice','turn your voice on','enable speech','activa la voz','activa tu voz'}:
   await self.command('output',enabled=True)
   await self.reply('Voice enabled.' if self.language=='en' else 'Voz activada.',generation);return
  if self.workspace and norm in {'clear workspace','clear the workspace','clear the screen','close all windows','close all workspace windows','limpia el workspace','limpia el espacio de trabajo','limpiar el espacio de trabajo','cierra todas las ventanas','cierra todas las ventanas del workspace'}:
   result=await asyncio.to_thread(self.workspace.request,{'tool':'workspace','arguments':{'action':'clear'}})
   message=('Workspace cleared.' if self.language=='en' else 'Espacio de trabajo despejado.') if result.get('ok') else ('The workspace did not confirm the clear action.' if self.language=='en' else 'El espacio de trabajo no confirmó el cierre.')
   await self.reply(message,generation);return
  launch=re.fullmatch(r'(?:(?:can you|could you|puedes|por favor|please) )?(?:open|launch|start|abre|abrir|inicia)(?: (?:the|el|la))? (firefox|browser|navegador|calculadora|calculator|dolphin|discord|steam|vs code|visual studio code|code oss)',norm)
  if self.workspace and launch:
   app={'browser':'firefox','navegador':'firefox','calculadora':'calculator','vs code':'code','visual studio code':'code','code oss':'code-oss'}.get(launch[1],launch[1])
   try:
    result=await asyncio.to_thread(self.workspace.request,{'tool':'apps','arguments':{'action':'open','id':app}})
    await self.reply(('Opening '+result['name']+'.') if self.language=='en' else ('Abriendo '+result['name']+'.'),generation)
   except (ValueError,OSError):await self.reply('That application is not available.' if self.language=='en' else 'Esa aplicación no está disponible.',generation)
   return
  panels={'agentes':'agents','agents':'agents','fuentes':'sources','sources':'sources','navegador':'browser','browser':'browser','ultima respuesta':'summary','last answer':'summary','resumen':'summary','wikipedia':'browser'}
  match=re.fullmatch(r'(?:(?:can you|could you|puedes|por favor|please) )?(?:show me|show|open|muestrame|muestra|abre)(?: (?:the|your|el|los|las|tus|mis|un|una))? (agents|agentes|fuentes|sources|navegador|browser|ultima respuesta|last answer|resumen|wikipedia)',norm)
  if match:
   selected=match[1]
   for term,kind in panels.items():
    if term==selected:
     intent={'type':'window.open','id':kind,'kind':kind,'title':{'agents':'Agentes','sources':'Fuentes','browser':'Navegador','summary':'Última respuesta'}[kind]}
     if kind=='summary':intent['text']=self.last_answer or ('No previous answer yet.' if self.language=='en' else 'Todavía no hay una respuesta anterior.')
     if term=='wikipedia':intent['url']='https://es.wikipedia.org/'
     self.emit({'type':'presentation','actor':'argos','intent':intent});self.state('listening');return
  if norm in {'organiza las ventanas','ordena las ventanas','arrange the windows','arrange windows'}:
   self.emit({'type':'presentation','actor':'argos','intent':{'type':'workspace.arrange'}});return
  if norm in {'cierra argos','cerrar argos','close argos','quit argos'}:
   self.emit({'type':'app.close'});return
  self.state('thinking');self.turn_running=True
  if self.workspace:self.workspace.begin_turn()
  pipeline=SpeechPipeline(self,generation,self.language);web_calls=0;started=time.monotonic();presentation_epoch=self.workspace.epoch if self.workspace else 0
  # Presentation hint only: native Hermes still interprets the request and owns tools.
  explicit=bool(re.match(r'^(?:(?:can|could|would) you |please |puedes |podrias |por favor )?(?:research|investigate|investiga|investigar|busca informacion|investiga informacion)\b',norm))
  delivered=False;seen_deliveries=set();stage_times={};selected_urls=set();compactions=0;last_source_speech=-10;process_started=False
  def start_process():
   nonlocal process_started
   if process_started:return
   process_started=True;self.emit({'type':'process.started','id':'web-research','title':'Research' if self.language=='en' else 'Investigación web','language':self.language,'status':'Searching sources…' if self.language=='en' else 'Buscando fuentes…'})
  if explicit:
   pipeline.public_speech=False;start_process()
   await pipeline.status("I'll look into it." if self.language=='en' else 'Lo investigo.')
  async def event(packet):
   nonlocal web_calls,delivered,compactions,last_source_speech
   if generation!=self.generation:return
   if packet.get('event')=='text.delta':await pipeline.feed(packet['text'])
   elif packet.get('event')=='text.boundary':await pipeline.boundary()
   elif packet.get('event')=='web.tool':
    if self.workspace and presentation_epoch!=self.workspace.epoch:return
    if packet['stage']=='tool.started':
     web_calls+=1
     if web_calls==1:
      pipeline.public_speech=False;stage_times['search_started_seconds']=time.monotonic()-started
      start_process()
      if not explicit or time.monotonic()-started>3:await pipeline.status('Searching sources.' if self.language=='en' else 'Buscando fuentes.')
    self.emit({'type':'process.update','id':'web-research','title':'Research' if self.language=='en' else 'Investigación web','status':('Consulting sources' if self.language=='en' else 'Consultando fuentes') if packet['stage']=='tool.started' else ('Search step finished' if self.language=='en' else 'Consulta procesada'),'web_calls':web_calls})
   elif packet.get('event')=='context.compaction':
    if packet['stage']=='started':compactions+=1
    self.emit({'type':'context.compaction','stage':packet['stage'],'language':self.language})
   elif packet.get('event')=='context.usage':
    stage_times['context_usage']=packet.get('last');stage_times['context_window']=packet.get('modelContextWindow')
   elif packet.get('event')=='web.sources' and self.workspace and presentation_epoch==self.workspace.epoch:
    delivery=await asyncio.to_thread(self.workspace.observe_sources,packet['sources'])
    if delivery.get('ok'):stage_times.setdefault('first_found_source_seconds',time.monotonic()-started)
   elif packet.get('event')=='web.source' and self.workspace and presentation_epoch==self.workspace.epoch:
    url=packet['url']
    if url in selected_urls or len(selected_urls)>=12:return
    try:
     delivery=await asyncio.to_thread(self.workspace.request,{'tool':'workspace','arguments':{'action':'research_sources','sources':[{'url':url,'title':packet['title']}],'open_sources':1}})
    except (ValueError,PermissionError):return
    if delivery.get('ok'):
     selected_urls.add(url);stage_times.setdefault('first_source_displayed_seconds',time.monotonic()-started)
   elif packet.get('event')=='workspace.research':
    if not packet.get('ok') or not packet.get('displayed') or (self.workspace and presentation_epoch!=self.workspace.epoch):return
    ident=packet.get('call_id')
    if ident in seen_deliveries:return
    seen_deliveries.add(ident);pipeline.public_speech=False
    if packet['delivery']=='research_sources':
     n=packet['selected_sources'];windows=packet.get('total_opened_windows',packet['opened_windows']);stage_times['sources_displayed_seconds']=time.monotonic()-started;stage_times.setdefault('first_source_displayed_seconds',time.monotonic()-started)
     message=(f'{n} sources selected.'+(f' {windows} source windows opened.' if windows else '')) if self.language=='en' else (f'{n} fuentes seleccionadas.'+(f' {windows} ventanas de fuentes abiertas.' if windows else ''))
     self.emit({'type':'process.update','id':'web-research','status':message,'selected_sources':n,'opened_windows':windows});
     if time.monotonic()-started-last_source_speech>=3:
      await pipeline.status(message);last_source_speech=time.monotonic()-started
    elif packet['delivery']=='research_result':
     delivered=True;stage_times['report_displayed_seconds']=time.monotonic()-started
     await pipeline.result(packet['speech'])
  try:
   snapshot=presentation_context(self.workspace.windows if self.workspace else [])
   result=await self.model.call({'text':text,'workspace':snapshot},on_event=event)
   self.turn_running=False
   if generation!=self.generation:
    self.emit({'type':'process.cancelled','id':'web-research','status':'Interrupted' if self.language=='en' else 'Interrumpido'}) if process_started else None
    await pipeline.cancel();return
   if not result.get('ok'):
    if self.workspace and self.workspace.development:self.workspace.development.incident('conversation',RuntimeError(result.get('code') or 'Native conversation did not complete'))
    if process_started:self.emit({'type':'process.failed','id':'web-research','status':'The search did not complete' if self.language=='en' else 'La búsqueda no pudo completarse'})
    await pipeline.cancel();self.state('error',error='La conversación no respondió correctamente. Puedes intentarlo de nuevo.');return
   self.last_answer=result['speech'];self.emit({'type':'voice.answer','text':result['speech'],'language':self.language})
   if process_started and (not self.workspace or presentation_epoch==self.workspace.epoch):
    self.emit({'type':'process.completed','id':'web-research','status':'Consulta finalizada','web_calls':web_calls})
    if not delivered:self.emit({'type':'presentation','actor':'argos','intent':{'type':'window.open','id':'research-summary','kind':'summary','title':'Resultado de investigación','text':result['speech'][:12000]}})
    urls=list(dict.fromkeys(re.findall(r'https://[^\s)>\]"\uE000-\uF8FF]+',result['speech'])))
    if urls and not delivered:self.emit({'type':'presentation','actor':'argos','intent':{'type':'window.open','id':'sources','kind':'sources','title':'Fuentes citadas','text':'\n'.join(urls[:20])}})
   metrics=await pipeline.finish(result['speech']);metrics.update(total_seconds=time.monotonic()-started,web_calls=web_calls,model_seconds=result.get('seconds'),native_compactions=compactions,provider_usage=result.get('usage'),session_id=self.sid,playback_simulated=self.mute,research_delivery=delivered,recognition=recognition,**stage_times)
   with (ROOT/'reports/voice-latency.jsonl').open('a') as report:report.write(json.dumps(metrics)+'\n')
  except BaseException:
   await pipeline.cancel();raise
  finally:self.turn_running=False
 async def reply(self,text,generation):
  if generation!=self.generation:return
  self.last_answer=text;self.emit({'type':'voice.answer','text':text,'language':self.language});self.state('synthesizing')
  if self.status['output_muted']:
   self.state('listening' if self.status['listening'] else 'off');return
  pipeline=SpeechPipeline(self,generation,self.language)
  try:await pipeline.finish(text)
  except BaseException:await pipeline.cancel();raise
 async def start_pcm(self,rate,generation):
  await self.stop_player()
  command=['pw-play','--raw','--rate='+str(rate),'--channels=1','--format=s16']
  if self.echo.active:command+=['--target',self.echo.sink]
  player=await asyncio.create_subprocess_exec(*command,'-',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
  self.tasks=[task for task in self.tasks if not task.done()]
  self.player=player;self.speaking=True;self.state('speaking');meter=asyncio.Queue();task=asyncio.create_task(self.meter_pcm(meter,player,rate));self.tasks.append(task)
  return player,meter,task
 async def write_pcm(self,stream,pcm):
  player,meter,_=stream;player.stdin.write(pcm);await player.stdin.drain();await meter.put(pcm)
 async def finish_pcm(self,stream,generation):
  player,meter,task=stream
  if not player.stdin.is_closing():player.stdin.close()
  await player.wait();task.cancel();await asyncio.gather(task,return_exceptions=True)
  if self.player is player:self.player=None;self.speaking=False
  self.emit({'type':'voice.level','level':0})
  if generation==self.generation and player.returncode and not self.status['output_muted']:raise RuntimeError('Audio output failed')
 async def meter_pcm(self,queue,player,rate):
  try:
   while player.returncode is None:
    pcm=await queue.get()
    for start in range(0,len(pcm),int(rate*.08)*2):
     if player.returncode is not None:return
     frame=pcm[start:start+int(rate*.08)*2];values=struct.unpack('<'+'h'*(len(frame)//2),frame);rms=math.sqrt(sum(v*v for v in values)/max(1,len(values)))/32768
     self.emit({'type':'voice.level','level':min(1,rms*5)});await asyncio.sleep(len(frame)/(rate*2))
  except asyncio.CancelledError:pass
 async def play(self,ident,generation,pipeline=False):
  file=self.audio_root/f'{ident}.wav'
  if self.mute:
   self.emit({'type':'voice.audio-ready','audio_id':ident})
   if pipeline:
    with wave.open(str(file),'rb') as audio:await asyncio.sleep(audio.getnframes()/audio.getframerate())
   else:self.state('standby')
   return
  await self.stop_player();self.speaking=True;self.state('speaking')
  command=['pw-play']
  if self.echo.active:command+=['--target',self.echo.sink]
  self.player=await asyncio.create_subprocess_exec(*command,str(file),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
  self.tasks=[task for task in self.tasks if not task.done()]
  self.tasks.append(asyncio.create_task(self.meter(file,self.player)))
  await self.player.wait();self.speaking=False
  if generation==self.generation and not pipeline:
   await asyncio.sleep(.3)
   self.state('listening' if self.status['dialogue_open'] else 'standby')
  self.emit({'type':'voice.level','level':0});file.unlink(missing_ok=True)
 async def meter(self,file,player):
  with wave.open(str(file),'rb') as audio:
   rate=audio.getframerate()
   while player.returncode is None:
    raw=audio.readframes(max(1,int(rate*.08)))
    if not raw:break
    values=struct.unpack('<'+'h'*(len(raw)//2),raw)
    rms=math.sqrt(sum(x*x for x in values)/max(1,len(values)))/32768
    self.emit({'type':'voice.level','level':min(1,rms*5)})
    await asyncio.sleep(.08)
 async def stop_player(self):
  if self.player and self.player.returncode is None:
   self.player.terminate()
   with contextlib.suppress(ProcessLookupError):await self.player.wait()
  self.speaking=False;self.emit({'type':'voice.level','level':0})
 async def command(self,op,**values):
  if op=='retry':
   if self.closed:raise ValueError('La aplicación se está cerrando')
   if getattr(self,'prepare_task',None) and not self.prepare_task.done():return {'ok':False,'error':'startup_in_progress'}
   if self.status['ready'] or not self.status.get('startup_error_component'):return {'ok':False,'error':'startup_retry_unavailable'}
   self.prepare_task=asyncio.create_task(self.prepare())
   return {'ok':True,'status':'startup_requested'}
  elif op=='listen':
   if not self.status['ready']:return {'ok':False,'error':'preparing'}
   if values.get('enabled') and not self.status.get('recognition_ready'):return {'ok':False,'error':'recognition_unavailable'}
   await self.listen(bool(values.get('enabled')))
  elif op=='interrupt':
   self.generation+=1
   if getattr(self,'tts_active',False):self.tts.interrupt()
   if self.turn_running:self.model.interrupt()
   await self.stop_player();self.state('listening' if self.status['listening'] else 'off')
  elif op=='text':
   if not self.status['ready']:raise ValueError('La conversación todavía se está preparando')
   text=values.get('text')
   if not isinstance(text,str) or not 0<len(text.strip())<=12000:raise ValueError('Invalid text')
   from maintenance.controller import clean
   if clean(text)!=text:raise ValueError('No envíes credenciales en la conversación')
   if self.queue.full():raise ValueError('Hay peticiones pendientes; espera a que termine una')
   self.queue.put_nowait((text,self.generation))
  elif op=='output':
   if self.text_only and values.get('enabled'):raise ValueError('La voz no está iniciada en esta sesión de texto')
   self.speech_settings.save(bool(values.get('enabled')))
   self.status['output_muted']=not bool(values.get('enabled'))
   if self.status['output_muted']:
    if getattr(self,'tts_active',False):self.tts.interrupt()
    await self.stop_player()
   self.state()
  elif op=='test-text' and self.no_capture:
   await self.accept(values['text'],direct=True)
  elif op=='test-speech' and self.no_capture:
   fixture=await self.tts.call({'text':values['text'],'language':values.get('language','en')})
   file=self.audio_root/f"{fixture['audio_id']}.wav"
   converter=await asyncio.create_subprocess_exec('ffmpeg','-v','error','-i',str(file),'-f','s16le','-ar','16000','-ac','1','pipe:1',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
   pcm,_=await converter.communicate();file.unlink(missing_ok=True)
   recognized=await self.stt.call({'pcm':base64.b64encode(pcm).decode(),'previous_language':self.language})
   # Test speech is synthetic and explicitly opted in; never retain microphone standby transcripts.
   recognition={k:recognized[k] for k in ('seconds','decode_passes','audio_seconds') if k in recognized}
   self.emit({'type':'test.recognition','text':recognized.get('text',''),'language':recognized.get('language'),**recognition})
   await self.accept(recognized.get('text',''),recognized.get('language'),recognized.get('language_probability',0),recognition=recognition)
  elif op=='test-tts' and self.no_capture:
   result=await self.tts.call({'text':values['text'],'language':values.get('language','en')})
   if result.get('audio_id'):(self.audio_root/f"{result['audio_id']}.wav").unlink(missing_ok=True)
   return result
  else:raise ValueError('Unsupported voice command')
  return {'ok':True,**self.status}
 async def shutdown(self):
  self.closed=True
  if getattr(self,'prepare_task',None) and not self.prepare_task.done():
   self.prepare_task.cancel();await asyncio.gather(self.prepare_task,return_exceptions=True)
  with contextlib.suppress(Exception):await self.listen(False)
  for task in self.tasks:task.cancel()
  await asyncio.gather(*(w.close() for w in [getattr(self,'model',None),getattr(self,'stt',None),getattr(self,'tts',None)] if w),return_exceptions=True)
  await asyncio.gather(*self.tasks,return_exceptions=True)
  for file in self.audio_root.glob('*.wav'):file.unlink(missing_ok=True)
 def close(self):
  if not self.loop.is_running():return
  with contextlib.suppress(Exception):asyncio.run_coroutine_threadsafe(self.shutdown(),self.loop).result(timeout=12)
  self.loop.call_soon_threadsafe(self.loop.stop)
