"""Pinned Qwen/Peter continuous PCM adapter; no playback or conversation reasoning."""
import faulthandler
import base64,contextlib,hashlib,json,os,queue,re,sys,threading,time,uuid
from collections import OrderedDict
from pathlib import Path
from machine import SPEECH_DEVICE
output=sys.stdout
ROOT=Path(__file__).resolve().parents[1];VOICE=ROOT.parent/'voice-tests/2026-11-05'
ENGINE_PIN='b8db6ff1cebc0d6554cf0977045850bcc796b383'
ENGINE=ROOT.parent/'tools/qwen-streaming-eval'
if (ENGINE/'.git/HEAD').read_text().strip()!=ENGINE_PIN:raise RuntimeError('Speech engine pin mismatch')
sys.path.insert(0,str(ENGINE))
namespace=sys.argv[1] if len(sys.argv)>1 else 'argos-workspace-default'
if not re.fullmatch(r'[a-zA-Z0-9-]{1,80}',namespace):raise SystemExit('Invalid audio namespace')
AUDIO=ROOT/'state/audio'/namespace;CACHE=ROOT/'private/speech-cache'
if os.environ.get('ARGOS_STARTUP_EVENTS')=='1':print(json.dumps({'event':'startup.stage','stage':'loading','component':'speech'}),file=output,flush=True)
faulthandler.dump_traceback_later(30,repeat=True)
with contextlib.redirect_stdout(sys.stderr):
 import numpy as np
 import torch,soundfile as sf
 from qwen_tts import Qwen3TTSModel
 torch.set_num_threads(2);torch.set_float32_matmul_precision('high')
 if os.environ.get('ARGOS_STARTUP_EVENTS')=='1':print(json.dumps({'event':'startup.stage','stage':'model_loading','component':'speech'}),file=output,flush=True)
 model=Qwen3TTSModel.from_pretrained(str(VOICE/'models/qwen-base'),device_map='cuda:0' if SPEECH_DEVICE=='cuda' else 'cpu',dtype=torch.bfloat16 if SPEECH_DEVICE=='cuda' else torch.float32,attn_implementation='sdpa')
 if os.environ.get('ARGOS_STARTUP_EVENTS')=='1':print(json.dumps({'event':'startup.stage','stage':'voice_reference','component':'speech'}),file=output,flush=True)
 prompt=model.create_voice_clone_prompt(ref_audio=str(VOICE/'peter-original.wav'),ref_text=json.loads((VOICE/'peter-reference-transcript.json').read_text())['text'])
 model.enable_streaming_optimizations(decode_window_frames=64,use_compile=SPEECH_DEVICE=='cuda',use_cuda_graphs=SPEECH_DEVICE=='cuda',compile_codebook_predictor=SPEECH_DEVICE=='cuda')
 AUDIO.mkdir(parents=True,exist_ok=True,mode=0o700);CACHE.mkdir(parents=True,exist_ok=True,mode=0o700)
 cache_version=hashlib.sha256((VOICE/'models/qwen-base/config.json').read_bytes()+(VOICE/'peter-reference-transcript.json').read_bytes()+(VOICE/'peter-original.wav').read_bytes()+ENGINE_PIN.encode()).hexdigest()
 def cached_file(text,language):return CACHE/(hashlib.sha256((cache_version+'\0'+language+'\0'+' '.join(text.replace('’',"'").split())).encode()).hexdigest()+'.wav')
 def generate(text,language):
  torch.manual_seed(61);torch.cuda.manual_seed_all(61)
  return model.stream_generate_voice_clone(text=text,language='Spanish' if language=='es' else 'English',voice_clone_prompt=prompt,emit_every_frames=8,decode_window_frames=64,overlap_samples=256,first_chunk_emit_every=6,first_chunk_decode_window=48,first_chunk_frames=36,max_frames=4096)
 if os.environ.get('ARGOS_STARTUP_EVENTS')=='1':print(json.dumps({'event':'startup.stage','stage':'compiling' if SPEECH_DEVICE=='cuda' else 'warming','component':'speech'}),file=output,flush=True)
 # Compile both decoder phases before microphone readiness, never in a spoken turn.
 with torch.inference_mode():
  warmup=[("The workspace is clear. Your files are unchanged. I'm ready for the next task.",'en'),('El espacio está despejado. Tus archivos siguen intactos. Estoy listo para la siguiente tarea.','es')] if SPEECH_DEVICE=='cuda' else [('Ready.','en')]
  for text,language in warmup:
   for _audio,_rate in generate(text,language):pass
faulthandler.cancel_dump_traceback_later()
print(json.dumps({'ready':True,'streaming':True,'engine_pin':ENGINE_PIN,'device':SPEECH_DEVICE}),file=output,flush=True)
requests=queue.Queue(maxsize=4);cancelled=threading.Event()
def incoming():
 for line in sys.stdin:
  try:request=json.loads(line)
  except ValueError:continue
  if request.get('op')=='interrupt':cancelled.set()
  else:requests.put(request)
 cancelled.set();requests.put(None)
threading.Thread(target=incoming,daemon=True).start()
while True:
 request=requests.get()
 if request is None:break
 try:
  text=request['text'];language=request.get('language','en');stream=request.get('stream',False)
  if not isinstance(text,str) or not 0<len(text)<=12000:raise ValueError()
  cancelled.clear();start=time.monotonic();saved=cached_file(text,language);hit=saved.exists();chunks=[];seconds=0
  if hit:
   cached,rate=sf.read(saved,dtype='float32');saved.touch();iterator=((cached[i:i+12000],rate) for i in range(0,len(cached),12000))
  else:iterator=generate(text,language)
  with contextlib.redirect_stdout(sys.stderr),torch.inference_mode():
   for audio,rate in iterator:
    if cancelled.is_set():break
    chunks.append(audio);seconds+=len(audio)/rate
    if stream:
     pcm=(np.clip(audio,-1,1)*32767).astype('<i2').tobytes()
     print(json.dumps({'event':'audio.chunk','pcm':base64.b64encode(pcm).decode(),'rate':rate,'seconds':len(audio)/rate,'cache_hit':hit}),file=output,flush=True)
  if cancelled.is_set():result={'ok':False,'interrupted':True}
  else:
   audio=np.concatenate(chunks)
   if not hit and len(text)<=100:
    sf.write(saved,audio,rate,subtype='PCM_16');saved.chmod(0o600)
    for old in sorted(CACHE.glob('*.wav'),key=lambda f:f.stat().st_mtime,reverse=True)[32:]:old.unlink(missing_ok=True)
   result={'ok':True,'seconds':seconds,'generation_seconds':time.monotonic()-start,'cache_hit':hit,'streaming':bool(stream)}
   if not stream:
    ident=uuid.uuid4().hex;file=AUDIO/f'{ident}.wav';sf.write(file,audio,rate,subtype='PCM_16');file.chmod(0o600);result['audio_id']=ident
 except Exception as error:result={'ok':False,'code':'speech_unavailable','category':type(error).__name__}
 print(json.dumps(result),file=output,flush=True)
