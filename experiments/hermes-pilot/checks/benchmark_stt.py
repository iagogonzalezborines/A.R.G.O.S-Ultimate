"""Synthetic public-voice fixtures only; compare recognition in the real TTS GPU budget."""
import json,os,subprocess,time,sys
from pathlib import Path
P=Path(__file__).resolve().parents[1];U=P/'ui-workbench';V=P/'voice-tests/2026-11-05';OUT=U/'reports/stt-comparison';OUT.mkdir(exist_ok=True)
if '--decode' in sys.argv:
 import numpy as np
 from faster_whisper import WhisperModel
 name=sys.argv[-1];gpu=name!='base'
 model=WhisperModel(str(P/'models/stt'/name) if gpu else 'base',device='cuda' if gpu else 'cpu',compute_type='int8_float16' if gpu else 'int8',cpu_threads=2,download_root='/home/tyrant/.local/share/argos/models/whisper',local_files_only=True)
 list(model.transcribe(np.zeros(16000,dtype=np.float32),language='en',beam_size=1,vad_filter=False)[0]);rows=[]
 for fixture in json.loads((OUT/'fixtures.json').read_text()):
  pcm=(OUT/fixture['file']).read_bytes();samples=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768
  for noisy in [False,True]:
   audio=samples.copy()
   if noisy:audio+=np.random.default_rng(7).normal(0,np.sqrt(np.mean(audio**2))*.14,len(audio)).astype(np.float32)
   begin=time.monotonic()
   if gpu:
    segments,info=model.transcribe(audio,language=None,beam_size=3,vad_filter=True,condition_on_previous_text=False,hotwords='ARGOS, Codex, Hermes, Firefox, Bambu Studio.',initial_prompt='A bilingual English and Spanish conversation with ARGOS.')
    text=' '.join(s.text.strip() for s in segments if s.no_speech_prob<.7);lang=info.language
   else:
    sys.path.insert(0,'/home/tyrant/Proyectos/argos/src');from argos.voice_worker import transcribe
    result=transcribe(model,audio,'auto','en');text=result.get('text','');lang=result.get('language')
   row={**fixture,'noisy':noisy,'text':text,'language':lang,'seconds':round(time.monotonic()-begin,3)};rows.append(row);print(json.dumps(row),flush=True)
 (OUT/(name+'.json')).write_text(json.dumps(rows,indent=2));sys.exit()
fixtures=[('en','Argos, research Batman and show me the sources.','Batman'),('en','He is a bad man, not a superhero.','bad man'),('en','Argos, open Firefox and search for Thunderstruck.','Firefox'),('en','Compare Nvidia and AMD graphics cards.','AMD'),('es','Argos, investiga a Batman y abre las fuentes.','Batman'),('es','Abre la carpeta de proyectos y muéstrame los archivos.','proyectos'),('en','Argos, are you there?','there'),('es','Busca información sobre Cervantes y Don Quijote.','Cervantes')]
env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_IMPLICIT_TOKEN':'1','TOKENIZERS_PARALLELISM':'false','TORCHINDUCTOR_CACHE_DIR':str(P/'cache/torch-streaming')}
tts=subprocess.Popen([str(V/'qwen-env/bin/python'),str(U/'runtime/tts_worker.py'),'argos-stt-fixtures'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(OUT/'tts.log').open('w'),env=env,text=True)
try:
 ready=json.loads(tts.stdout.readline());assert ready['ready'];print('TTS ready',flush=True);rows=[]
 for i,(lang,text,expected) in enumerate(fixtures):
  tts.stdin.write(json.dumps({'text':text,'language':lang})+'\n');tts.stdin.flush();result=json.loads(tts.stdout.readline());assert result['ok'],result
  wav=U/'state/audio/argos-stt-fixtures'/(result['audio_id']+'.wav');name=str(i)+'.pcm'
  subprocess.run(['ffmpeg','-v','error','-y','-i',str(wav),'-f','s16le','-ar','16000','-ac','1',str(OUT/name)],check=True);wav.unlink()
  rows.append({'file':name,'input':text,'expected':expected,'expected_language':lang});print('Fixture '+str(i),flush=True)
 (OUT/'fixtures.json').write_text(json.dumps(rows,indent=2))
 libs=V/'qwen-env/lib/python3.12/site-packages/nvidia';env['LD_LIBRARY_PATH']=':'.join(str(libs/n/'lib') for n in ['cublas','cudnn','cuda_runtime'])
 for name in ['base','small','turbo']:
  print('BENCH '+name,flush=True);subprocess.run(['/home/tyrant/.local/share/argos/voice-env/bin/python',__file__,'--decode',name],env=env,check=True)
  print(subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader'],text=True).strip(),flush=True)
finally:
 tts.stdin.close()
 try:tts.wait(timeout=10)
 except subprocess.TimeoutExpired:tts.terminate();tts.wait(timeout=10)
