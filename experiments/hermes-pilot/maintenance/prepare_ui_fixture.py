"""Synthetic candidate for isolated QA review; never installed into ARGOS."""
from pathlib import Path
import sys,time,secrets,json
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P))
from maintenance.controller import *
m=Maintenance(state=BASE/'qa/argos-self-development-check');ident=secrets.token_hex(12);folder=m.private/'proposals'/ident/'candidate';folder.mkdir(parents=True)
for name in EDITABLE:
 source=live_path(name)
 if source.exists():target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(read_regular(source))
p=folder/'dist/style.css';p.write_text(p.read_text()+'\n/* Synthetic QA review fixture: no live installation */\n')
m.put({'id':ident,'goal':'Synthetic review fixture — do not install into the live app','status':'preparing','baseline':m.manifest(),'created':time.time(),'expires':time.time()+3600,'events':[]});r=m.validate(ident);(P/'ui-workbench/reports/development-ui-fixture.json').write_text(json.dumps({'id':ident,'baseline':r['baseline']})+'\n');print('Prepared synthetic UI review fixture')
