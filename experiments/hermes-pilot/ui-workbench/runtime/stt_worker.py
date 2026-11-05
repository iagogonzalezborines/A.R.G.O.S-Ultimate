"""Pinned multilingual CUDA recognition. PCM remains in memory, never on disk."""
import base64,contextlib,json,os,sys,time
from pathlib import Path
output=sys.stdout;ROOT=Path(__file__).resolve().parents[1];PILOT=ROOT.parent
os.environ['HF_HUB_OFFLINE']='1'
with contextlib.redirect_stdout(sys.stderr):
 import numpy as np
 from faster_whisper import WhisperModel
 sys.path.insert(0,'/home/tyrant/Proyectos/argos/src')
 from argos.language import choose_language
 pin=next(p for p in json.loads((PILOT/'models/stt/pins.json').read_text()) if p['model']=='turbo')
 model=WhisperModel(str(PILOT/'models/stt/turbo'),device='cuda',compute_type='int8_float16',cpu_threads=2,local_files_only=True)
 # Warm before enabling capture; do not spend a user's first turn initializing CUDA.
 list(model.transcribe(np.zeros(16000,dtype=np.float32),language='en',beam_size=3,temperature=0,vad_filter=False)[0])
print(json.dumps({'ready':True,'model':'large-v3-turbo','device':'cuda','compute_type':'int8_float16','revision':pin['revision']}),file=output,flush=True)
for line in sys.stdin:
 try:
  request=json.loads(line);raw=base64.b64decode(request['pcm'],validate=True)
  if len(raw)>16000*2*25 or len(raw)%2:raise ValueError()
  start=time.monotonic()
  with contextlib.redirect_stdout(sys.stderr):
   samples=np.frombuffer(raw,dtype='<i2').astype(np.float32)/32768
   segments,info=model.transcribe(samples,language=None,beam_size=3,temperature=0,vad_filter=True,condition_on_previous_text=False,
       hotwords='ARGOS, Codex, Hermes, Firefox, Bambu Studio.')
   kept=[s for s in segments if s.no_speech_prob<.7]
   text=' '.join(s.text.strip() for s in kept).strip()
   # No phonetic replacements: "bad man" must remain valid. No English primer
   # either: it can swallow the wake name or bias a Spanish utterance to English.
   language=choose_language(text,request.get('previous_language','en'),info.language,info.language_probability)
   result={'ok':bool(text),'text':text,'language':language,'language_probability':info.language_probability,
           'detected_language':info.language,'seconds':time.monotonic()-start,'decode_passes':1,'audio_seconds':len(samples)/16000}
 except Exception as error:result={'ok':False,'text':'','code':'recognition_failed','category':type(error).__name__}
 print(json.dumps(result,ensure_ascii=False),file=output,flush=True)
