"""Original mature British voice designs, following the user's audition feedback."""
from pathlib import Path
import json,time
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

ROOT=Path(__file__).resolve().parents[1]
phrases=json.loads((ROOT/'phrases.json').read_text())
torch.set_num_threads(4)
start=time.monotonic()
model=Qwen3TTSModel.from_pretrained(str(ROOT/'models/qwen-voice-design'),
    device_map='cuda:0',dtype=torch.bfloat16,attn_implementation='sdpa')
loaded=time.monotonic()-start
styles={
 'qwen-british-seasoned': 'A mature male British assistant in his late fifties to early sixties. Educated southern English accent with clear British English vowels and non-rhotic pronunciation. A warm, resonant medium-low baritone with a lightly textured, seasoned timbre. Quiet authority, experience and composure, with a hint of understated British dry wit. Speak naturally and conversationally at an ordinary fluent pace, with connected phrasing, subtle melodic variation and short meaningful pauses. Keep the delivery relaxed, articulate and grounded throughout the passage.',
 'qwen-british-warm': 'An older male British speaker, around sixty, with an experienced, approachable presence. A natural educated English accent, non-rhotic, with clear British English pronunciation. A mellow low-mid voice, slightly husky and warm, with gentle breath and a lived-in timbre. Sound quietly confident and perceptive, speaking directly to one familiar person. Fluid conversational rhythm, natural small shifts in pitch and emphasis, relaxed phrasing and restrained dry humour. Maintain a normal conversational pace and a consistent vocal identity throughout the passage.',
}
rows=[]
for lang,language in [('en','English'),('es','Spanish')]:
 for voice,instruction in styles.items():
    torch.manual_seed(52)
    torch.cuda.manual_seed_all(52)
    torch.cuda.reset_peak_memory_stats()
    text=' '.join(p['text'] for p in phrases[lang])
    actual_instruction=instruction
    if lang=='es':actual_instruction+=' Speak the Spanish text clearly while retaining the mature timbre and calm conversational character.'
    start=time.monotonic()
    with torch.inference_mode():
        wavs,rate=model.generate_voice_design(text=text,language=language,
            instruct=actual_instruction,max_new_tokens=600)
    torch.cuda.synchronize();elapsed=time.monotonic()-start
    path=ROOT/'outputs'/f'{voice}-{lang}.wav'
    sf.write(path,wavs[0],rate,subtype='PCM_16')
    row={'engine':'qwen-tts','voice':voice,'language':lang,'text':text,
         'style_instruction':actual_instruction,'file':path.name,'sample_rate':rate,
         'model_load_seconds':loaded,'generation_seconds':elapsed,
         'audio_seconds':len(wavs[0])/rate,'first_chunk_seconds':None,'seed':52,
         'peak_cuda_allocated_mib':torch.cuda.max_memory_allocated()/2**20,
         'peak_cuda_reserved_mib':torch.cuda.max_memory_reserved()/2**20,
         'note':'Original voice design from text instructions. No reference audio cloning. Human accent/age/naturalness review required.'}
    rows.append(row)
    temp=ROOT/'qwen-mature-metrics.tmp';temp.write_text(json.dumps(rows,ensure_ascii=False,indent=2));temp.replace(ROOT/'qwen-mature-metrics.json')
    print(json.dumps(row,ensure_ascii=False),flush=True)
