"""A small sampling change with Peter's existing voice embedding; no pitch/time effects."""
from pathlib import Path
import json,time,wave
import numpy as np
import torch
from pocket_tts import TTSModel

ROOT=Path(__file__).resolve().parents[1]
cases=json.loads((ROOT/'phrases.json').read_text())
torch.set_num_threads(2)
rows=[]
for lang,full in [('en','english'),('es','spanish')]:
    model=TTSModel.load_model(language=full,temp=0.45)
    state=model.get_state_for_audio_prompt(str(ROOT/f'peter-{lang}.safetensors'))
    all_audio=[]
    for case in cases[lang]:
        torch.manual_seed(42);start=time.monotonic();pieces=[];first=None
        for piece in model.generate_audio_stream(state,case['text']):
            if first is None:first=time.monotonic()-start
            pieces.append(piece.detach().cpu().flatten().numpy())
        audio=np.concatenate(pieces)
        all_audio.extend([audio,np.zeros(int(model.sample_rate*.65),dtype=np.float32)])
        rows.append({'voice':'pocket-peter-b','language':lang,'phrase':case['id'],
                     'temperature':0.45,'seed':42,'first_chunk_seconds':first,
                     'generation_seconds':time.monotonic()-start,'audio_seconds':len(audio)/model.sample_rate})
    path=ROOT/'outputs'/f'pocket-peter-b-{lang}.wav'
    with wave.open(str(path),'wb') as f:
        f.setparams((1,2,model.sample_rate,0,'NONE','not compressed'))
        f.writeframes((np.clip(np.concatenate(all_audio),-1,1)*32767).astype('<i2').tobytes())
    (ROOT/'peter-b-metrics.json').write_text(json.dumps(rows,indent=2))
    print('Peter B ready',lang,flush=True)
    del model
