"""Read measured public answers into the chosen native Qwen/Peter voice; no playback."""
from pathlib import Path
import json
import re
import argparse
import time
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT.parents[1] / 'reports/character-2026-11-05'
parser = argparse.ArgumentParser()
parser.add_argument('--run', default='calibrated-focused', choices=['calibrated-focused','irony-v2'])
args = parser.parse_args()
prior = json.loads((ROOT/'character.json').read_text()) if (ROOT/'character.json').exists() else {'turns':[]}
prior_audio = {(x['run'],x['scenario'],x['turn']):x for x in prior['turns'] if x.get('audio_file')}
rows = []
for file in sorted(REPORTS.glob('*.jsonl')):
    for line in file.read_text().splitlines():
        item = json.loads(line)
        item['run'] = file.stem
        previous = prior_audio.get((item['run'],item['scenario'],item['turn']))
        if previous:
            for field in ['audio_file','synthesis_seconds','spoken_text','estimated_serial_text_and_synthesis_seconds','audio_review_note']:
                if field in previous:item[field] = previous[field]
        if item['scenario'] == 'context_corrections' and item['turn'] in (2,4):
            item['checks']['no_reintroduced_old_colour'] = 'gris' not in item['response'].casefold()
            if item['turn'] == 2:
                item['checks']['acknowledges_latest_colour'] = 'azul' in item['response'].casefold()
        rows.append(item)
selected = {('judgment',1), ('judgment',2), ('judgment',3), ('wit_to_serious',1),
            ('wit_to_serious',2), ('wit_to_serious',3), ('context_corrections',4),
            ('context_corrections',5)}
if args.run=='irony-v2':selected = {('sky_default',1),('sky_repeat',1),('new_premise',1)}
torch.set_num_threads(4)
start = time.monotonic()
model = Qwen3TTSModel.from_pretrained(str(ROOT/'models/qwen-base'), device_map='cuda:0',
                                    dtype=torch.bfloat16, attn_implementation='sdpa')
load_seconds = time.monotonic() - start
start = time.monotonic()
ref_text = json.loads((ROOT/'peter-reference-transcript.json').read_text())['text']
prompt = model.create_voice_clone_prompt(ref_audio=str(ROOT/'peter-original.wav'),
                                         ref_text=ref_text, x_vector_only_mode=False)
prepare_seconds = time.monotonic() - start
(ROOT/'character-audio').mkdir(exist_ok=True)
metrics = json.loads((ROOT/'character-voice-metrics.json').read_text()) if (ROOT/'character-voice-metrics.json').exists() else []
def publish():
    content = dict(summary=f'{len(rows)} turnos medidos · {len(metrics)} respuestas con voz · Codex gpt-6-luna, esfuerzo bajo · Contratos de prueba; ARGOS operativo sin cambios.', turns=rows)
    temp = ROOT/'character.tmp'
    temp.write_text(json.dumps(content, ensure_ascii=False, indent=2))
    temp.replace(ROOT/'character.json')
    (ROOT/'character-voice-metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
publish()
for row in rows:
    if row['run'] != args.run or (row['scenario'],row['turn']) not in selected:
        continue
    if row['error'] or not row['response'].strip():
        continue
    text = row['response']
    # Only remove presentation markup; the model's spoken words are not rewritten.
    text = re.sub(r'[*`#]', '', text)
    language = 'Spanish' if row['scenario'] == 'context_corrections' else 'English'
    torch.manual_seed(61);torch.cuda.manual_seed_all(61);torch.cuda.reset_peak_memory_stats()
    start = time.monotonic()
    with torch.inference_mode():
        wavs, rate = model.generate_voice_clone(text=text, language=language,
                                                voice_clone_prompt=prompt, max_new_tokens=800)
    torch.cuda.synchronize()
    elapsed = time.monotonic() - start
    filename = row['scenario'].replace('_','-')+'-'+str(row['turn'])+'.wav'
    if args.run=='irony-v2':filename='irony-v2-'+filename
    sf.write(ROOT/'character-audio'/filename, wavs[0], rate, subtype='PCM_16')
    row.update(audio_file=filename, synthesis_seconds=elapsed, spoken_text=text,
               estimated_serial_text_and_synthesis_seconds=row['seconds']+elapsed)
    metric = dict(file=filename, language=language, text=text, generation_seconds=elapsed,
                  audio_seconds=len(wavs[0])/rate, rate=rate, model_load_seconds=load_seconds,
                  reference_preparation_seconds=prepare_seconds,
                  peak_cuda_allocated_mib=torch.cuda.max_memory_allocated()/2**20,
                  first_streaming_audio_seconds=None,
                  note='Completed-WAV synthesis, not microphone-to-sound latency. No automatic speaker playback.')
    metrics = [x for x in metrics if x['file']!=filename]+[metric]
    publish()
    print(json.dumps(metric, ensure_ascii=False), flush=True)
