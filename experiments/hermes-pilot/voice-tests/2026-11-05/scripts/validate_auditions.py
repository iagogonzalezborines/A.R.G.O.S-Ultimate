"""Check finished WAVs, local HTTP playback and the original ARGOS source hashes."""
from pathlib import Path
import ast
import hashlib
import json
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[1]
state = json.loads((ROOT / 'web-server.json').read_text())
url = state['url']
with urllib.request.urlopen(url + '/manifest.json', timeout=10) as response:
    manifest = json.load(response)
rows = []
for voice in manifest['voices']:
    for language, sample in voice['samples'].items():
        if not sample['ready']:
            continue
        path = ROOT / 'outputs' / (voice['id'] + '-' + language + '.wav')
        with wave.open(str(path), 'rb') as audio:
            row = dict(voice=voice['id'], language=language, file=path.name,
                       frames=audio.getnframes(), rate=audio.getframerate(),
                       channels=audio.getnchannels(), sample_width=audio.getsampwidth())
        assert row['channels'] == 1 and row['sample_width'] == 2 and row['frames'] > 0
        request = urllib.request.Request(url + sample['url'], headers={'Range': 'bytes=0-63'})
        with urllib.request.urlopen(request, timeout=10) as response:
            row.update(range_status=response.status, range_bytes=len(response.read()))
        assert row['range_status'] == 206 and row['range_bytes'] == 64
        row.update(seconds=row['frames'] / row['rate'], ready=True,
                   sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        rows.append(row)
baseline = json.loads((ROOT.parents[1] / 'reports/argos-source-before.json').read_text())
source = Path('/home/tyrant/Proyectos/argos')
changes = [name for name, digest in baseline.items()
           if not (source / name).is_file() or hashlib.sha256((source / name).read_bytes()).hexdigest() != digest]
for script in (ROOT / 'scripts').glob('*.py'):
    ast.parse(script.read_text())
result = dict(audio_files=rows, source_baseline_count=len(baseline), argos_source_changes=changes,
              all_audios_ready=all(s['ready'] for v in manifest['voices'] for s in v['samples'].values()))
(ROOT / 'validation.json').write_text(json.dumps(result, indent=2))
assert not changes, changes
print(json.dumps(dict(ready_reels=len(rows), all_audios_ready=result['all_audios_ready'],
                     argos_source_changes=changes)))
