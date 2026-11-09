"""Bounded presentation of task artifacts. HTML is always an opaque sandbox frame."""
import base64
import hashlib
from pathlib import Path
from maintenance.controller import read_regular,clean

THEME='<style>:root{color-scheme:dark}html[data-theme=light]{color-scheme:light}html:not([data-theme=light]) body{background-color:#040c17;color:#c9e5f7}html[data-theme=dark]{--bg:#040c17;--panel:#081c2de6;--panel-border:#285b7a;--grid:#16314a;--text:#d7edfa;--text-muted:#9dbcd1}.iso:not([data-theme=light]){--anatomy-page:#040c17;--anatomy-card:#081c2d;--anatomy-text:#a6c9df;--anatomy-strong:#e0f2ff;--anatomy-paper:#0b2132;--anatomy-face:#123449;--anatomy-top:#18445b;--anatomy-hi:#bceaff;--anatomy-mid:#6ea8c6;--anatomy-lo:#3a6b88;--anatomy-faint:#244d68}button:focus-visible,a:focus-visible,[tabindex]:focus-visible{outline:2px solid #65d5ff;outline-offset:2px}@media(prefers-reduced-motion:reduce){*{animation-duration:.01ms!important;transition-duration:.01ms!important}}</style>'
POLICY="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"


def preview(path):
    data=read_regular(path,8*1024*1024)
    result={'path':str(path),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
    suffix=Path(path).suffix.lower()
    if suffix in {'.html','.htm'}:
        value=data.decode('utf-8')
        # CSP precedes every artifact byte, including its own meta tags and scripts.
        result.update(kind='html',html='<meta http-equiv="Content-Security-Policy" content="'+POLICY+'">'+value+THEME,
                      notice='Explanatory artifact; native Project Map remains authoritative. Network, host access and navigation blocked.')
    elif suffix=='.png' and data.startswith(b'\x89PNG\r\n\x1a\n'):
        result.update(kind='image',data_url='data:image/png;base64,'+base64.b64encode(data).decode())
    elif suffix in {'.glb','.stl','.step','.stp'}:
        from projects.model_preview import html
        result.update(kind='html',html='<meta http-equiv="Content-Security-Policy" content="'+POLICY+'">'+html(data,suffix),notice='Vista técnica o estilizada; no modifica el original ni acredita seguridad mecánica.')
    elif suffix=='.blend':
        result.update(kind='binary',text='Persistent project artifact: '+Path(path).name+'\n'+str(len(data))+' bytes. Inspect accompanying source, measurements and preview; opening does not execute it.')
    else:result.update(kind='text',text=clean(data[:262144].decode('utf-8')))
    return result
