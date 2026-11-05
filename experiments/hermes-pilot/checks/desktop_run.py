"""Bounded GUI smoke check, private Wayland connection, no global desktop control."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pilot import ROOT, SOURCE, sandbox
from checks.validate import process_sample

command=sandbox([SOURCE/'node_modules/electron/dist/electron','--ozone-platform=wayland','--disable-gpu',ROOT/'checks/desktop.cjs'],desktop=True)
with (ROOT/'reports/desktop-run.log').open('w') as log:
    proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    samples=[]
    try:
        for _ in range(100):
            time.sleep(1)
            samples.append({'seconds':len(samples)+1,**process_sample(proc.pid)})
            text=(ROOT/'reports/desktop-run.log').read_text()
            if 'PILOT_DESKTOP_RESULT ' in text or proc.poll() is not None:
                break
        if proc.poll() is None:
            before=process_sample(proc.pid)
            time.sleep(15)
            after=process_sample(proc.pid)
            samples.append({'idle_interval':15,**after,'cpu_one_core_percent':max(0,after['cpu_seconds']-before['cpu_seconds'])/15*100})
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL);proc.wait()
(ROOT/'reports/desktop-resources.json').write_text(json.dumps(samples,indent=2))
print('Desktop smoke process exit:',proc.returncode)
