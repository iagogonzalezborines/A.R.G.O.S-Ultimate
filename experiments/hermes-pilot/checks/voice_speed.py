"""Muted native Qwen comparison; no microphone or model/provider calls."""
import contextlib,io,json,sys,time
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P/'ui-workbench'))
sys.argv=['voice-speed','argos-speed-check'];sys.stdin=io.StringIO('')
with contextlib.redirect_stdout(sys.stderr):
 from runtime import tts_worker as t
text="I'll open the video in your workspace."
rows=[]
for mode,threads in [('baseline',4),('one-thread',1),('two-threads',2),('non-streaming',2),('baseline-repeat',4)]:
 t.torch.set_num_threads(threads);t.torch.manual_seed(61);t.torch.cuda.manual_seed_all(61)
 start=time.monotonic()
 with contextlib.redirect_stdout(sys.stderr),t.torch.inference_mode():
  wavs,rate=t.model.generate_voice_clone(text=text,language='English',voice_clone_prompt=t.prompt,max_new_tokens=4096,non_streaming_mode=mode=='non-streaming')
 elapsed=time.monotonic()-start;f=P/'ui-workbench/reports'/('speed-'+mode+'.wav');t.sf.write(f,wavs[0],rate,subtype='PCM_16');f.chmod(0o600)
 row={'mode':mode,'threads':threads,'generation_seconds':elapsed,'audio_seconds':len(wavs[0])/rate,'sample':str(f)};rows.append(row);print(json.dumps(row),flush=True)
(P/'ui-workbench/reports/voice-speed-check.json').write_text(json.dumps({'text':text,'rows':rows,'playback':'not played'},indent=2)+'\n')
