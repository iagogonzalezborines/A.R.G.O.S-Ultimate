"""Final actual worker check with synthetic fixtures; no microphone capture."""
import base64,json,os,subprocess,time,statistics
from pathlib import Path
P=Path(__file__).resolve().parents[1];U=P/'ui-workbench';V=P/'voice-tests/2026-11-05';D=U/'reports/stt-comparison'
env={**os.environ,'LD_LIBRARY_PATH':':'.join(str(V/'qwen-env/lib/python3.12/site-packages/nvidia'/n/'lib') for n in ['cublas','cudnn','cuda_runtime'])}
p=subprocess.Popen(['/home/tyrant/.local/share/argos/voice-env/bin/python',str(U/'runtime/stt_worker.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(D/'worker.log').open('w'),env=env,text=True)
rows=[]
try:
 ready=json.loads(p.stdout.readline());assert ready['ready'];import numpy as np
 for f in json.loads((D/'fixtures.json').read_text()):
  for noisy in [False,True]:
   pcm=(D/f['file']).read_bytes()
   if noisy:
    samples=np.frombuffer(pcm,dtype='<i2').astype(np.float32);samples+=np.random.default_rng(7).normal(0,np.sqrt(np.mean(samples**2))*.14,len(samples));pcm=np.clip(samples,-32768,32767).astype('<i2').tobytes()
   p.stdin.write(json.dumps({'pcm':base64.b64encode(pcm).decode(),'previous_language':'en'})+'\n');p.stdin.flush();r=json.loads(p.stdout.readline())
   assert r['ok'],r;assert f['expected'].casefold() in r['text'].casefold(),r;assert r['language']==f['expected_language'],r
   if f['input'].startswith('Argos'):assert r['text'].lower().startswith('argos'),r
   rows.append({**f,'noisy':noisy,**r});print(json.dumps({k:rows[-1][k] for k in ['expected','text','language','seconds','noisy']}),flush=True)
 result={'worker':ready,'checks':len(rows),'median_seconds':statistics.median(r['seconds'] for r in rows),'max_seconds':max(r['seconds'] for r in rows),'rows':rows,'limits':'Synthetic public Peter voice with clean and additive-noise variants; user microphone/accent not validated.'};(D/'final-worker.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='rows'}),flush=True)
finally:
 p.stdin.close();p.wait(timeout=10)
