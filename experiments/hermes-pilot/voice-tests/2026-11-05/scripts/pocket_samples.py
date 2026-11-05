"""Offline voice auditions using ARGOS's existing Pocket version in private caches."""
from pathlib import Path
import json
import time
import wave
import copy
import numpy as np
import torch
from pocket_tts import TTSModel

ROOT = Path(__file__).resolve().parents[1]
torch.set_num_threads(2)
cases = json.loads((ROOT/'phrases.json').read_text())
metrics = []


def save(path, data, rate):
    with wave.open(str(path), 'wb') as out:
        out.setparams((1,2,rate,0,'NONE','not compressed'))
        out.writeframes((np.clip(data,-1,1)*32767).astype('<i2').tobytes())


for lang, full_lang in [('en','english'),('es','spanish')]:
    started=time.monotonic()
    model=TTSModel.load_model(language=full_lang)
    load=time.monotonic()-started
    for label, state_path in [('pocket-peter',ROOT/f'peter-{lang}.safetensors'),
                              ('pocket-alba',ROOT/f'alba-{full_lang}.safetensors')]:
        state=model.get_state_for_audio_prompt(str(state_path))
        for case in cases[lang]:
            torch.manual_seed(42)
            start=time.monotonic()
            pieces=[]
            first=None
            for piece in model.generate_audio_stream(state,case['text']):
                if first is None:first=time.monotonic()-start
                pieces.append(piece.detach().cpu().flatten().numpy())
            audio=np.concatenate(pieces)
            path=ROOT/'outputs'/f'{label}-{lang}-{case["id"]}.wav'
            save(path,audio,model.sample_rate)
            row={'engine':'pocket-tts','version':'3.3.0','voice':label,'language':lang,
                 'phrase':case['id'],'text':case['text'],'file':path.name,
                 'model_load_seconds':load,'first_chunk_seconds':first,
                 'generation_seconds':time.monotonic()-start,
                 'audio_seconds':len(audio)/model.sample_rate,'sample_rate':model.sample_rate,
                 'device':'cpu','threads':2,'seed':42}
            metrics.append(row)
            (ROOT/'pocket-metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
            print(json.dumps(row,ensure_ascii=False),flush=True)
    del model
