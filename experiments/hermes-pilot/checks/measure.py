"""Native gateway measurements without a model, audio or user project access."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pilot import ROOT, FIXTURE
from checks.validate import RPC, process_sample

report={'gateway_startup_seconds':[], 'samples':[], 'methodology':'Three sequential native stdio gateway starts. Five-second warmup then thirty-second idle interval on first instance. Summed process-tree RSS includes shared pages. Warm filesystem cache; not a cold-machine benchmark.'}
for attempt in range(3):
    rpc=RPC()
    try:
        report['gateway_startup_seconds'].append(rpc.startup)
        response=rpc.request('session.create',{'cwd':str(FIXTURE),'idempotency_key':f'pilot-measure-{attempt}'})
        if 'error' in response:raise RuntimeError(response['error'])
        if attempt==0:
            time.sleep(5)
            before=process_sample(rpc.proc.pid)
            for i in range(30):
                time.sleep(1)
                report['samples'].append({'seconds':i+1,**process_sample(rpc.proc.pid)})
            after=report['samples'][-1]
            report['steady_idle']={**after,'interval_seconds':30,
                'cpu_one_core_percent':max(0,after['cpu_seconds']-before['cpu_seconds'])/30*100}
    finally:
        rpc.close()
(ROOT/'reports/gateway-resources.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='samples'},indent=2))
