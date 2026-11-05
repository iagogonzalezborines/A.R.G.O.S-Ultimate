"""Scoped clipboard/large-file copy and live read-only storage checks."""
import hashlib,json,tempfile
from pathlib import Path
from runtime.workspace_broker import Files,WorkspaceBroker
from runtime.storage import Storage
from server import validate
checks=[]
def check(name,result):
 checks.append({'name':name,'ok':bool(result)})
 if not result:raise AssertionError(name)
def reject(name,fn):
 try:fn()
 except (ValueError,PermissionError,OSError):check(name,True)
 else:check(name,False)
with tempfile.TemporaryDirectory(prefix='argos-clipboard-') as d:
 root=Path(d);(root/'source').mkdir();(root/'target').mkdir();source=root/'source/binary.bin';source.write_bytes(bytes(range(256))*20480);original=hashlib.sha256(source.read_bytes()).hexdigest();f=Files({'Test':root})
 f.copy('Test/source/binary.bin');check('clipboard has no disk effect',not (root/'target/binary.bin').exists());result=f.paste('Test/target',apply=False);check('model paste is a review proposal',result['status']=='awaiting_user_review' and not (root/'target/binary.bin').exists());f.confirm(result['id'],True);check('binary copy larger than old 1 MiB limit is exact',hashlib.sha256((root/'target/binary.bin').read_bytes()).hexdigest()==original)
 reject('existing destination is not overwritten',lambda:f.paste('Test/target',apply=True));check('source retained after copy',hashlib.sha256(source.read_bytes()).hexdigest()==original)
 check('user paste applies copy',f.paste('Test/source',apply=True)['status']=='applied' and (root/'source/binary - copy.bin').is_file());f.paste('Test/source',apply=True);check('same-folder paste chooses next unused copy name',(root/'source/binary - copy 2.bin').is_file())
 source.write_bytes(b'changed');reject('stale clipboard cannot paste',lambda:f.paste('Test/target',apply=True));reject('outside folders cannot be clipboard sources',lambda:f.copy('/etc/passwd'))
 f2=Files({'Test':root});reject('empty clipboard rejected',lambda:f2.paste('Test/target',apply=True));f2.copy('Test/source/binary.bin');f2.stopping.set();reject('closing cancels copy without publishing',lambda:f2.paste('Test/source',apply=True));check('cancelled copy cleans staging files',not list((root/'source').glob('.argos-copy-*')))
 b=WorkspaceBroker(lambda e:None,validate,files=f);reject('agent still cannot approve writes',lambda:b.request({'tool':'files','arguments':{'action':'confirm','proposal_id':'none','approve':True}}));check('workspace clear is a valid typed action',validate({'type':'workspace.clear'})=={'type':'workspace.clear'})
 s=Storage();data=s.inspect();check('real physical storage inventory',len(data['disks'])>0 and all(not n['name'].startswith('zram') for n in data['disks']));check('swap memory distinguished from disk capacity',any(n['name'].startswith('zram') for n in data['virtual_devices']))
 volumes=s.volumes();unmounted=[n for n in volumes if not n['mounted'] and n['type']=='part'];mounted=[n for n in volumes if n['mounted']]
 check('unmounted free space remains unknown',all(n['available_bytes'] is None for n in unmounted));check('mounted filesystem free space observed',any(n['available_bytes'] is not None for n in mounted))
 if unmounted:reject('unmounted partition is not pretended browsable',lambda:s.browse(unmounted[0]['device']))
 check('root filesystem browsing maps to personal files',any('/' in n['mountpoints'] and s.browse(n['device'])=='/home/tyrant' for n in mounted));reject('unknown device rejected',lambda:s.browse('/dev/not-a-device'))
report={'checks':checks,'scope':'Disposable synthetic copies; read-only real storage inspection. No mounting, formatting or partition changes.'};Path(__file__).with_name('reports').joinpath('storage-clipboard-checks.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':all(x['ok'] for x in checks),'checks':len(checks)}))
