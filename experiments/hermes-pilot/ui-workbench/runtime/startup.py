"""Bounded startup metadata only: never persist worker output or conversation text."""
import json
import os
from pathlib import Path
import re
import secrets
import time


def release_ready(state,*,text_only=False):
    return bool(state.get('agent_connected') and state.get('renderer_connected') and (text_only or state.get('voice_ready')))


def stderr_summary(data):
    text=data.decode(errors='replace') if isinstance(data,(bytes,bytearray)) else str(data)
    frames=[{'file':Path(p).name,'line':int(n),'function':f[:80]}
            for p,n,f in re.findall(r'File "([^"\n]+)", line (\d+), in ([^\n]+)',text)][-6:]
    types=sorted(set(re.findall(r'(?m)^([A-Za-z_][\w.]*(?:Error|Exception))(?::|$)',text)))[:8]
    codes=[name for name in ['CERTIFICATE_VERIFY_FAILED','ECONNREFUSED','ENETUNREACH',
           'invalid_grant','reauthenticationRequired','Permission denied','ModuleNotFoundError'] if name in text]
    return {'frames':frames,'exception_types':types,'codes':codes}


class StartupTrace:
    def __init__(self,path):
        self.path=Path(path);self.started=time.monotonic();self.attempt=secrets.token_hex(8)
        self.rows=[];self.write_error=None

    def record(self,component,stage,*,error=None,diagnostics=None):
        valid=lambda s:isinstance(s,str) and re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}',s)
        if not valid(component) or not valid(stage):return
        row={'component':component,'stage':stage,'elapsed_seconds':round(time.monotonic()-self.started,4)}
        if error:row['error_type']=type(error).__name__
        if diagnostics:row['diagnostics']=diagnostics
        self.rows=(self.rows+[row])[-80:]
        payload={'attempt':self.attempt,'events':self.rows}
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            temp=self.path.with_name(self.path.name+'.tmp')
            fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as stream:json.dump(payload,stream)
            os.replace(temp,self.path)
        except OSError as error:self.write_error=type(error).__name__
