"""Original designed voices, local inference; does not clone the reference video's speaker."""
from pathlib import Path
import json
import time
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

ROOT=Path(__file__).resolve().parents[1]
cases=json.loads((ROOT/'phrases.json').read_text())
torch.set_num_threads(4)
start=time.monotonic()
model=Qwen3TTSModel.from_pretrained(str(ROOT/'models/qwen-voice-design'),
    device_map='cuda:0',dtype=torch.bfloat16,attn_implementation='sdpa')
loaded=time.monotonic()-start
styles={
 'qwen-female':'An adult female assistant with a warm clear medium-low voice. Calm, precise, conversational and confident. Natural phrase-level intonation, short meaningful pauses and a lightly dry understated wit. Speak at a fluent conversational pace. Use clear native pronunciation in the requested language. Keep the voice grounded and consistent throughout the passage.',
 'qwen-male':'An adult male assistant with a warm resonant medium-low voice. Calm, precise, conversational and confident. Natural phrase-level intonation, short meaningful pauses and a lightly dry understated wit. Speak at a fluent conversational pace. Use clear native pronunciation in the requested language. Keep the voice grounded and consistent throughout the passage.',
}
metrics=[]
for voice,instruction in styles.items():
 for lang,full_language in [('en','English'),('es','Spanish')]:
    torch.manual_seed(42)
    torch.cuda.manual_seed_all(42)
    torch.cuda.reset_peak_memory_stats()
    text=' '.join(case['text'] for case in cases[lang])
    start=time.monotonic()
    with torch.inference_mode():
        wavs,rate=model.generate_voice_design(text=text,language=full_language,
            instruct=instruction,max_new_tokens=600)
    torch.cuda.synchronize()
    elapsed=time.monotonic()-start
    path=ROOT/'outputs'/f'{voice}-{lang}.wav'
    sf.write(path,wavs[0],rate,subtype='PCM_16')
    row={'engine':'qwen-tts','version':'0.1.1','voice':voice,'language':lang,'text':text,
         'style_instruction':instruction,'file':path.name,'sample_rate':rate,
         'model_load_seconds':loaded,'generation_seconds':elapsed,
         'audio_seconds':len(wavs[0])/rate,'first_chunk_seconds':None,
         'first_chunk_note':'Official generate_voice_design returns a completed waveform; streaming latency was not measured.',
         'device':'cuda:0','dtype':'bfloat16','attention':'sdpa','seed':42,
         'peak_cuda_allocated_mib':torch.cuda.max_memory_allocated()/2**20,
         'peak_cuda_reserved_mib':torch.cuda.max_memory_reserved()/2**20,
         'identity_note':'Original voice design on each call; cross-language speaker identity is not guaranteed by this test.'}
    metrics.append(row)
    (ROOT/'qwen-metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
    print(json.dumps(row,ensure_ascii=False),flush=True)
