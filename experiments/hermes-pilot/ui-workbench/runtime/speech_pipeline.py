"""Continuous PCM speech: one native generation per completed public message."""
import asyncio
import base64
import re
import time

def spoken(text):
 # Source-only footnotes belong in the workspace, not in the spoken sentence.
 if re.fullmatch(r'\s*(?:(?:Sources?|Fuentes?):?\s*)?(?:\[[^\]]+\]\(https?://[^)]+\)[\s·,;]*)+',text,re.I):return ''
 text=re.sub(r'[^]*','',text)
 text=re.sub(r'\[([^\]]+)\]\(https?://[^)]+\)',r'\1',text)
 text=re.sub(r'https?://\S+','',text)
 text=re.sub(r'[*`#]','',text)
 return re.sub(r'\s+',' ',text).strip()

class SpeechPipeline:
 def __init__(self,host,generation,language):
  self.host=host;self.generation=generation;self.language=language;self.buffer='';self.raw='';self.closed=False;self.texts=asyncio.Queue();self.audio=asyncio.Queue();self.start=time.monotonic();self.first_text=None
  self.metrics={'chunks':[],'audio_packets':[],'first_audio_ready_seconds':None,'first_playback_start_seconds':None,'streamed_characters':0,'continuous_pcm':True}
  self.synthesis=asyncio.create_task(self.synthesize());self.playback=asyncio.create_task(self.play())
  self.public_speech=True;self.conclusion=None
 def valid(self):return not self.closed and self.generation==self.host.generation
 async def feed(self,text):
  if not self.valid() or not isinstance(text,str) or not text:return
  if self.first_text is None:self.first_text=time.monotonic()-self.start
  self.raw+=text;self.buffer+=text;self.host.emit({'type':'voice.delta','text':text})
  # A full stop controls prosody inside Qwen; it is never an audio-job boundary.
 async def boundary(self):
  if not self.valid():return
  clean=spoken(self.buffer);self.buffer=''
  if clean and self.public_speech:await self.texts.put((clean,'answer'))
 async def status(self,text):
  if not self.valid():return
  # A newer stage replaces an unspoken older stage; never queue stale narration.
  self.drop_statuses()
  await self.texts.put((text,'progress'))
 def drop_statuses(self):
  keep=[]
  while not self.texts.empty():
   entry=self.texts.get_nowait()
   if entry is None or entry[1]!='progress':keep.append(entry)
  for entry in keep:self.texts.put_nowait(entry)
 async def result(self,text):
  if not self.valid() or self.conclusion is not None:return
  self.conclusion=text;self.drop_statuses()
  await self.texts.put((spoken(text),'conclusion'))
 async def finish(self,final):
  if not self.raw:await self.feed(final)
  elif final and final not in self.raw:
   normal=lambda text:re.sub(r'\s+',' ',text).strip()
   if normal(final).startswith(normal(self.raw)):await self.feed(final[len(self.raw):])
  await self.boundary()
  if not self.public_speech and self.conclusion is None:await self.result(final)
  self.metrics['streamed_characters']=len(self.raw);self.metrics['first_text_seconds']=self.first_text
  await self.texts.put(None);await self.synthesis;await self.playback;return self.metrics
 async def synthesize(self):
  try:
   while True:
    entry=await self.texts.get()
    if entry is None:break
    text,kind=entry
    if not self.valid() or self.host.status['output_muted']:continue
    metric={'ordinal':len(self.metrics['chunks'])+1,'kind':kind,'characters':len(text),'synthesis_start_seconds':time.monotonic()-self.start,'duration_seconds':0,'cache_hit':False};self.metrics['chunks'].append(metric)
    if not self.host.speaking:self.host.state('synthesizing')
    async def packet(event):
     if event.get('event')!='audio.chunk' or not self.valid() or self.host.status['output_muted']:return
     now=time.monotonic()-self.start
     if self.metrics['first_audio_ready_seconds'] is None:self.metrics['first_audio_ready_seconds']=now
     pcm=base64.b64decode(event['pcm'],validate=True);rate=event['rate']
     if rate!=24000 or len(pcm)>24000*2*5:raise ValueError('Invalid audio packet')
     self.metrics['audio_packets'].append({'ready_seconds':now,'duration_seconds':event['seconds']});metric['cache_hit']=event.get('cache_hit',False);metric['duration_seconds']+=event['seconds']
     await self.audio.put((pcm,rate,metric))
    self.host.tts_active=True
    try:result=await self.host.tts.call({'text':text,'language':self.language,'stream':True},on_event=packet)
    finally:self.host.tts_active=False
    metric['synthesis_end_seconds']=time.monotonic()-self.start
    if not result.get('ok') and self.valid() and not self.host.status['output_muted']:raise RuntimeError('Speech synthesis failed')
  finally:await self.audio.put(None)
 async def play(self):
  stream=None
  try:
   while True:
    entry=await self.audio.get()
    if entry is None:break
    pcm,rate,metric=entry
    if not self.valid() or self.host.status['output_muted']:continue
    if 'playback_start_seconds' not in metric:
     metric['playback_start_seconds']=time.monotonic()-self.start
     if self.metrics['first_playback_start_seconds'] is None:self.metrics['first_playback_start_seconds']=metric['playback_start_seconds']
    if self.host.mute:
     await asyncio.sleep(len(pcm)/(rate*2))
    else:
     if stream is None:stream=await self.host.start_pcm(rate,self.generation)
     await self.host.write_pcm(stream,pcm)
    metric['playback_end_seconds']=time.monotonic()-self.start
  except (BrokenPipeError,ConnectionResetError):
   if self.valid() and not self.host.status['output_muted']:raise
  finally:
   if stream is not None:
    await self.host.finish_pcm(stream,self.generation)
    if self.metrics['chunks']:self.metrics['chunks'][-1]['playback_end_seconds']=time.monotonic()-self.start
  if self.valid():self.host.state('listening' if self.host.status['listening'] and self.host.status['dialogue_open'] else 'standby' if self.host.status['listening'] else 'off')
 async def cancel(self):
  self.closed=True
  if getattr(self.host,'tts_active',False):self.host.tts.interrupt()
  await self.texts.put(None);await asyncio.gather(self.synthesis,self.playback,return_exceptions=True)
