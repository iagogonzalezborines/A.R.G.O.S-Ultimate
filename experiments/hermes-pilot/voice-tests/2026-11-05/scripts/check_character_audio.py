"""Offline short-response transcription and WAV checks, without speaker playback."""
from pathlib import Path
import json
import re
import wave
import sys
from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parents[1]
model = WhisperModel('base', device='cpu', compute_type='int8', cpu_threads=2,
                     download_root='/home/tyrant/.local/share/argos/models/whisper', local_files_only=True)
prefix = sys.argv[1] if len(sys.argv)>1 else ''
rows = json.loads((ROOT/'character-audio-checks.json').read_text()) if prefix and (ROOT/'character-audio-checks.json').exists() else []
rows = [row for row in rows if not row['file'].startswith(prefix)]
for metric in json.loads((ROOT/'character-voice-metrics.json').read_text()):
    if not metric['file'].startswith(prefix):continue
    path = ROOT/'character-audio'/metric['file']
    with wave.open(str(path), 'rb') as audio:
        assert audio.getnchannels() == 1 and audio.getsampwidth() == 2 and audio.getnframes() > 0
        duration = audio.getnframes()/audio.getframerate()
    language = 'en' if metric['language']=='English' else 'es'
    segments, _ = model.transcribe(str(path), language=language, beam_size=3)
    actual = ' '.join(s.text.strip() for s in segments)
    expected = metric['text']
    words = lambda s: re.findall(r'[^\W_]+', s.casefold())
    end_expected, end_actual = words(expected)[-3:], words(actual)[-3:]
    rows.append(dict(file=path.name, seconds=duration, expected=expected, transcript=actual,
                     final_three_words_match=end_expected == end_actual,
                     note='ASR content check; no validation of live playback endings, accent or naturalness.'))
(ROOT/'character-audio-checks.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
print(json.dumps(rows, ensure_ascii=False))
