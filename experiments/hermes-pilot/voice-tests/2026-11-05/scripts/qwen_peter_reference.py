"""Native Qwen Base acoustic conditioning with Pocket's public Peter source, not actor audio."""
from pathlib import Path
import json,time
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

ROOT=Path(__file__).resolve().parents[1]
phrases=json.loads((ROOT/'phrases.json').read_text())
reference=json.loads((ROOT/'peter-reference-transcript.json').read_text())['text']
torch.set_num_threads(4)
start=time.monotonic()
model=Qwen3TTSModel.from_pretrained(str(ROOT/'models/qwen-base'),device_map='cuda:0',
                                  dtype=torch.bfloat16,attn_implementation='sdpa')
loaded=time.monotonic()-start
prompts={}
for name,embedding_only in [('qwen-peter-reference',False),('qwen-peter-identity',True)]:
    start=time.monotonic()
    prompt=model.create_voice_clone_prompt(ref_audio=str(ROOT/'peter-original.wav'),
        ref_text=reference,x_vector_only_mode=embedding_only)
    prompts[name]=(prompt,embedding_only,time.monotonic()-start)
    print('Reference prepared:',name,flush=True)

rows=[]
for lang,language in [('en','English'),('es','Spanish')]:
 for voice,(prompt,embedding_only,prepared) in prompts.items():
    torch.manual_seed(61);torch.cuda.manual_seed_all(61);torch.cuda.reset_peak_memory_stats()
    text=' '.join(p['text'] for p in phrases[lang])
    start=time.monotonic()
    with torch.inference_mode():
        wavs,rate=model.generate_voice_clone(text=text,language=language,
                                            voice_clone_prompt=prompt,max_new_tokens=600)
    torch.cuda.synchronize();elapsed=time.monotonic()-start
    path=ROOT/'outputs'/f'{voice}-{lang}.wav';sf.write(path,wavs[0],rate,subtype='PCM_16')
    row={'engine':'qwen-tts','variant':'1.7B-Base','voice':voice,'language':lang,'text':text,
         'file':path.name,'sample_rate':rate,'reference':'Public Kyutai Peter Yearsley sample',
         'reference_transcript':reference,'embedding_only':embedding_only,
         'model_load_seconds':loaded,'reference_preparation_seconds':prepared,
         'generation_seconds':elapsed,'audio_seconds':len(wavs[0])/rate,
         'first_chunk_seconds':None,'seed':61,
         'peak_cuda_allocated_mib':torch.cuda.max_memory_allocated()/2**20,
         'peak_cuda_reserved_mib':torch.cuda.max_memory_reserved()/2**20,
         'note':'Synthetic audition conditioned on Peter, not Paul Bettany. No actor identity match claimed.'}
    rows.append(row)
    temp=ROOT/'qwen-reference-metrics.tmp';temp.write_text(json.dumps(rows,ensure_ascii=False,indent=2));temp.replace(ROOT/'qwen-reference-metrics.json')
    print(json.dumps(row,ensure_ascii=False),flush=True)
