"""Download explicitly evaluated public STT weights into the isolated pilot only."""
from pathlib import Path
import json
from huggingface_hub import HfApi,snapshot_download
P=Path(__file__).resolve().parents[1];rows=[]
for name,repo in [('turbo','mobiuslabsgmbh/faster-whisper-large-v3-turbo'),('small','Systran/faster-whisper-small')]:
 info=HfApi(token=False).model_info(repo);target=P/'models/stt'/name;print(json.dumps({'model':name,'revision':info.sha,'stage':'downloading'}),flush=True)
 snapshot_download(repo,revision=info.sha,local_dir=str(target),token=False,allow_patterns=['config.json','preprocessor_config.json','model.bin','tokenizer.json','vocabulary.*'])
 rows.append({'model':name,'repo':repo,'revision':info.sha,'path':str(target)});(P/'models/stt/pins.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps({'model':name,'stage':'ready'}),flush=True)
