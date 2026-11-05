"""Muted continuous Qwen/Peter audio benchmark using existing local model weights."""
import contextlib,json,sys,time
from pathlib import Path
P=Path(__file__).resolve().parents[1];V=P/'voice-tests/2026-11-05';out=P/'ui-workbench/reports/streaming-voice';out.mkdir(exist_ok=True)
sys.path.insert(0,str(P/'tools/qwen-streaming-eval'))
import numpy as np
import torch,soundfile as sf
from qwen_tts import Qwen3TTSModel
torch.set_num_threads(2);torch.set_float32_matmul_precision('high')
with contextlib.redirect_stdout(sys.stderr):
 model=Qwen3TTSModel.from_pretrained(str(V/'models/qwen-base'),device_map='cuda:0',dtype=torch.bfloat16,attn_implementation='sdpa')
 prompt=model.create_voice_clone_prompt(ref_audio=str(V/'peter-original.wav'),ref_text=json.loads((V/'peter-reference-transcript.json').read_text())['text'])
rows=[];text="The workspace is clear. Your files are unchanged. I'm ready for the next task."
for label,compile_,graphs,codebook in [('plain',False,False,False),('cuda-graphs',False,True,False),('compiled',True,True,True)]:
 with contextlib.redirect_stdout(sys.stderr):model.enable_streaming_optimizations(decode_window_frames=64,use_compile=compile_,use_cuda_graphs=graphs,compile_codebook_predictor=codebook)
 for repetition in range(2):
  torch.manual_seed(61);torch.cuda.manual_seed_all(61);start=time.monotonic();chunks=[];metrics=[]
  with contextlib.redirect_stdout(sys.stderr),torch.inference_mode():
   for chunk,rate in model.stream_generate_voice_clone(text=text,language='English',voice_clone_prompt=prompt,emit_every_frames=8,decode_window_frames=64,overlap_samples=256,first_chunk_emit_every=6,first_chunk_decode_window=48,first_chunk_frames=36,max_frames=360,use_optimized_decode=graphs):
    metrics.append({'at':time.monotonic()-start,'audio_seconds':len(chunk)/rate});chunks.append(chunk)
  total=time.monotonic()-start;audio=np.concatenate(chunks);file=out/f'{label}-{repetition}.wav';sf.write(file,audio,rate,subtype='PCM_16')
  play_start=metrics[0]['at'];elapsed_audio=0;underruns=[]
  for m in metrics:
   gap=max(0,m['at']-play_start-elapsed_audio)
   if gap>.02:underruns.append(gap);play_start+=gap
   elapsed_audio+=m['audio_seconds']
  row={'mode':label,'repetition':repetition,'first_audio_seconds':metrics[0]['at'],'total_seconds':total,'audio_seconds':len(audio)/rate,'rtf':total/(len(audio)/rate),'chunks':metrics,'simulated_underrun_seconds':underruns,'sample':str(file)};rows.append(row);print(json.dumps(row),flush=True)
  (out/'probe.json').write_text(json.dumps({'pin':'b8db6ff1cebc0d6554cf0977045850bcc796b383','text':text,'rows':rows,'playback':'muted; scheduling simulation only'},indent=2)+'\n')
