"""Explicit real model test: sanitized results only; no audio or external actions."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adaptive.local import Local,normalize,validate_items


def run(config):
    client=Local(config)
    sample='- STL\n- OBJ\n- 3MF'
    expected={'items':['STL','OBJ','3MF']}
    client.release()
    report={'model':config['model'],'digest':config['digest'],'before':client.loaded(),'samples':[]}
    start=time.monotonic();direct=normalize(sample)
    report['deterministic']={'seconds':time.monotonic()-start,'valid':direct==expected}
    try:
        for label in ['cold','warm','warm_repeat']:
            value,metrics=client.generate('Extract the following list, preserving its exact order and names, into items:\n'+sample)
            report['samples'].append({'label':label,'metrics':metrics,'result':validate_items(value),'correct':value==expected,'loaded':client.loaded()})
            print(label,round(metrics['wall_seconds'],3),value==expected,flush=True)
    finally:
        start=time.monotonic();client.release()
        deadline=time.monotonic()+10
        while client.loaded() and time.monotonic()<deadline:time.sleep(.1)
        report['release']={'seconds':time.monotonic()-start,'remaining':client.loaded()}
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('config');parser.add_argument('report');args=parser.parse_args()
    result=run(json.loads(Path(args.config).read_text()))
    Path(args.report).write_text(json.dumps(result,indent=2)+'\n')
