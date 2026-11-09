"""Bounded presentation of task artifacts. HTML is always an opaque sandbox frame."""
import base64
import hashlib
from pathlib import Path
from maintenance.controller import read_regular,clean

POLICY="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"


def preview(path):
    data=read_regular(path,8*1024*1024)
    result={'path':str(path),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
    suffix=Path(path).suffix.lower()
    if suffix in {'.html','.htm'}:
        value=data.decode('utf-8')
        # CSP precedes every artifact byte, including its own meta tags and scripts.
        result.update(kind='html',html='<meta http-equiv="Content-Security-Policy" content="'+POLICY+'">'+value,
                      notice='Explanatory artifact; native Project Map remains authoritative. Network, host access and navigation blocked.')
    elif suffix=='.png' and data.startswith(b'\x89PNG\r\n\x1a\n'):
        result.update(kind='image',data_url='data:image/png;base64,'+base64.b64encode(data).decode())
    elif suffix in {'.blend','.glb','.stl','.step','.stp'}:
        result.update(kind='binary',text='Persistent project artifact: '+Path(path).name+'\n'+str(len(data))+' bytes. Inspect accompanying source, measurements and preview; opening does not execute it.')
    else:result.update(kind='text',text=clean(data[:262144].decode('utf-8')))
    return result
