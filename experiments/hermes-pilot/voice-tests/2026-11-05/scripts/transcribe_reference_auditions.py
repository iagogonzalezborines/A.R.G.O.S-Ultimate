"""Offline content check; does not assess accent, age, likeness or naturalness."""
from pathlib import Path
import json
from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parents[1]
model = WhisperModel('base', device='cpu', compute_type='int8', cpu_threads=2,
                     download_root='/home/tyrant/.local/share/argos/models/whisper', local_files_only=True)
rows = []
for item in json.loads((ROOT / 'qwen-reference-metrics.json').read_text()):
    segments, _ = model.transcribe(str(ROOT / 'outputs' / item['file']),
                                   language=item['language'], beam_size=3)
    rows.append(dict(file=item['file'], language=item['language'],
                     transcript=' '.join(segment.text.strip() for segment in segments),
                     note='Automatic content check only; accent and naturalness require listening.'))
(ROOT / 'qwen-reference-transcripts.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
print(json.dumps(rows, ensure_ascii=False))
