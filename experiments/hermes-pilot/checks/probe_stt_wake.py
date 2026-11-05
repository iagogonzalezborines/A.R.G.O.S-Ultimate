import json,os,time
from pathlib import Path
P=Path(__file__).resolve().parents[1];V=P/'voice-tests/2026-11-05';libs=V/'qwen-env/lib/python3.12/site-packages/nvidia'
os.environ['LD_LIBRARY_PATH']=':'.join(str(libs/n/'lib') for n in ['cublas','cudnn','cuda_runtime'])
# dlopen uses LD_LIBRARY_PATH from process startup, so this script is launched with it set.
import numpy as np
from faster_whisper import WhisperModel
m=WhisperModel(str(P/'models/stt/turbo'),device='cuda',compute_type='int8_float16',cpu_threads=2)
D=P/'ui-workbench/reports/stt-comparison';rows=[]
for prompt in [None,'Proper names: ARGOS, Codex, Hermes, Firefox, Bambu Studio.']:
 for f in json.loads((D/'fixtures.json').read_text()):
  samples=np.frombuffer((D/f['file']).read_bytes(),dtype='<i2').astype(np.float32)/32768;t=time.monotonic()
  seg,info=m.transcribe(samples,beam_size=3,vad_filter=True,condition_on_previous_text=False,initial_prompt=prompt,hotwords='ARGOS, Codex, Hermes, Firefox, Bambu Studio.',temperature=0)
  text=' '.join(s.text for s in seg);row={'prompt':prompt,'input':f['input'],'text':text,'language':info.language,'probability':info.language_probability,'seconds':time.monotonic()-t};rows.append(row);print(json.dumps(row),flush=True)
(D/'wake-probe.json').write_text(json.dumps(rows,indent=2))
