"""No-inference reproduction against unmodified pinned native validation."""
import hashlib,json,sys
from pathlib import Path
H=Path(__file__).resolve().parent;P=H.parents[1];sys.path.insert(0,str(P/'source'))
from hermes_state_worker_context import worker_sidecars,SIDECAR_KEYS
from hermes_state_runtime import RuntimeStoreError
try:worker_sidecars(None,None,'synthetic-session',{'patch':{'codex_thread_id':'synthetic-thread'}})
except RuntimeStoreError as e:repro={'rejected':True,'reason':str(e)}
else:repro={'rejected':False}
rows=[]
for p in (H/'native/profiles/engineering/worker-outboxes').glob('*/pending.json'):
 s=json.loads(p.read_text())
 for e in s.get('pending',[]):
  q=e.get('payload',{});patch=q.get('patch',{})
  rows.append({'journal':str(p.relative_to(H)), 'sequence':e['sequence'],'operation':e['operation'],'payload_keys':list(q),'patch_types':{k:type(v).__name__ for k,v in patch.items()},'unsupported_keys':sorted(set(patch)-SIDECAR_KEYS)})
r={'revision':'0073fa98cfcf61c066a919df4b336924720f8463','inference_calls':0,'native_reproduction':repro,'allowed_sidecars':sorted(SIDECAR_KEYS),'real_owned_worker_pending_operations':rows}
(H/'upstream-blocker.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
