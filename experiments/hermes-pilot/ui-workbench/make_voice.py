"""Prepared presentation cues in the user-selected voice. Does not play audio."""
from pathlib import Path
import json,time
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel
ROOT=Path(__file__).resolve().parent
VOICE=ROOT.parent/'voice-tests/2026-11-05'
torch.set_num_threads(4)
model=Qwen3TTSModel.from_pretrained(str(VOICE/'models/qwen-base'),device_map='cuda:0',dtype=torch.bfloat16,attn_implementation='sdpa')
reference=json.loads((VOICE/'peter-reference-transcript.json').read_text())['text']
prompt=model.create_voice_clone_prompt(ref_audio=str(VOICE/'peter-original.wav'),ref_text=reference,x_vector_only_mode=False)
rows=[]
for file,text in [('ack','On it. Opening your research workspace.'),('ready','Ready. Your sources, video, and summary are on the workspace.')]:
 torch.manual_seed(61);torch.cuda.manual_seed_all(61);start=time.monotonic()
 with torch.inference_mode():wavs,rate=model.generate_voice_clone(text=text,language='English',voice_clone_prompt=prompt,max_new_tokens=400)
 sf.write(ROOT/'dist/assets'/f'{file}.wav',wavs[0],rate,subtype='PCM_16')
 rows.append({'file':file+'.wav','text':text,'generation_seconds':time.monotonic()-start,'audio_seconds':len(wavs[0])/rate,'prepared':True})
(ROOT/'reports/voice-cues.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows),flush=True)
