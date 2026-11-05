"""Loopback-only audition page. Serves only allowlisted synthesized audio, never credentials/models."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import array
import json
import math
import os
import re
import sys
import time
import wave

ROOT=Path(__file__).resolve().parents[1]
VOICES=[
 {'id':'pocket-peter','title':'Peter','engine':'Pocket TTS · Voz actual','description':'Referencia masculina que utiliza ARGOS actualmente.'},
 {'id':'pocket-peter-b','title':'Peter · Variante B','engine':'Pocket TTS · Mismo timbre','description':'Un poco más de variación en la generación. Compárala con Peter original.'},
 {'id':'pocket-alba','title':'Alba','engine':'Pocket TTS · Alternativa','description':'Voz femenina para comparar el timbre y la naturalidad.'},
 {'id':'qwen-female','title':'Qwen · Femenina','engine':'Qwen3-TTS · Voice Design','description':'Diseño original con una interpretación serena y conversacional.'},
 {'id':'qwen-male','title':'Qwen · Masculina','engine':'Qwen3-TTS · Voice Design','description':'Diseño original con una interpretación serena y conversacional.'},
]
CACHE={}


def catalog():
    path=ROOT/'voices.json'
    if not path.exists():return VOICES
    try:
        items=json.loads(path.read_text())
        if not isinstance(items,list) or not items:return VOICES
        if any(not isinstance(v,dict) or not re.fullmatch(r'[a-z0-9-]{1,64}',v.get('id','')) for v in items):return VOICES
        return items
    except (ValueError,OSError):return VOICES


def envelope(path):
    key=(str(path),path.stat().st_mtime_ns,path.stat().st_size)
    if key in CACHE:return CACHE[key]
    with wave.open(str(path),'rb') as f:
        if f.getsampwidth()!=2:raise ValueError('Only PCM16 auditions')
        data=array.array('h',f.readframes(f.getnframes()))
        if sys.byteorder!='little':data.byteswap()
    step=max(1,len(data)//64)
    bins=[math.sqrt(sum(float(x)*x for x in data[i:i+step])/max(1,len(data[i:i+step]))) for i in range(0,len(data),step)][:64]
    scale=max(bins,default=1) or 1
    CACHE[key]=[round(v/scale,3) for v in bins]
    return CACHE[key]


def manifest():
    voices=[]
    qwen_files=set()
    for metrics in ROOT.glob('qwen*-metrics.json'):
        try:qwen_files.update(x['file'] for x in json.loads(metrics.read_text()))
        except json.JSONDecodeError:pass
    for voice in catalog():
        samples={}
        for lang in ['es','en']:
            filename=voice['id']+'-'+lang+'.wav';path=ROOT/'outputs'/filename
            ready=path.is_file() and path.stat().st_size>100 and (not voice['id'].startswith('qwen') or filename in qwen_files)
            samples[lang]={'ready':ready,'url':'/audio/'+filename,'waveform':envelope(path) if ready else []}
        voices.append({**voice,'samples':samples})
    return {'voices':voices,'phrases':json.loads((ROOT/'phrases.json').read_text())}


class Handler(BaseHTTPRequestHandler):
    def send_headers(self,code,length,kind,extra=None):
        self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(length))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; media-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        for k,v in (extra or {}).items():self.send_header(k,v)
        self.end_headers()

    def do_GET(self):self.get(False)
    def do_HEAD(self):self.get(True)

    def get(self,head):
        path=self.path.split('?',1)[0]
        if path=='/':body=(ROOT/'web/dist/index.html').read_bytes();kind='text/html; charset=utf-8'
        elif path=='/character':body=(ROOT/'web/dist/character.html').read_bytes();kind='text/html; charset=utf-8'
        elif path=='/character.json':body=(ROOT/'character.json').read_bytes();kind='application/json; charset=utf-8'
        elif path.startswith('/character-audio/'):
            filename=path[len('/character-audio/'):]
            data=json.loads((ROOT/'character.json').read_text())
            allowed={row['audio_file'] for row in data['turns'] if row.get('audio_file')}
            if filename not in allowed or not re.fullmatch(r'[a-z0-9-]+\.wav',filename):self.send_error(404);return
            file=ROOT/'character-audio'/filename
            if not file.is_file():self.send_error(404);return
            body=file.read_bytes();kind='audio/wav'
        elif path=='/manifest.json':body=json.dumps(manifest(),ensure_ascii=False).encode();kind='application/json; charset=utf-8'
        elif path.startswith('/audio/') and path[len('/audio/'):] in {v['id']+'-'+lang+'.wav' for v in catalog() for lang in ['es','en']}:
            filename=path[len('/audio/'):];file=ROOT/'outputs'/filename
            if not file.is_file():self.send_error(404);return
            size=file.stat().st_size;start=0;end=size-1;code=200
            extra={'Accept-Ranges':'bytes'}
            if value:=self.headers.get('Range'):
                match=re.fullmatch(r'bytes=(\d+)-(\d*)',value)
                if not match:self.send_error(416);return
                start=int(match[1]);end=min(int(match[2]) if match[2] else end,end)
                if start>end:self.send_error(416);return
                code=206;extra['Content-Range']=f'bytes {start}-{end}/{size}'
            self.send_headers(code,end-start+1,'audio/wav',extra)
            if not head:
                try:
                    with file.open('rb') as f:
                        f.seek(start);remaining=end-start+1
                        while remaining:
                            chunk=f.read(min(65536,remaining))
                            if not chunk:break
                            self.wfile.write(chunk);remaining-=len(chunk)
                except (BrokenPipeError,ConnectionResetError):pass
            return
        else:self.send_error(404);return
        self.send_headers(200,len(body),kind)
        if not head:self.wfile.write(body)

    def do_POST(self):
        expected=f'http://127.0.0.1:{self.server.server_port}'
        if self.path!='/feedback' or self.headers.get('Origin',expected)!=expected:self.send_error(403);return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=1024:raise ValueError()
            data=json.loads(self.rfile.read(size))
            if set(data)!={'voice','language'} or data['voice'] not in {v['id'] for v in catalog()} or data['language'] not in ['es','en']:raise ValueError()
            temp=ROOT/'feedback.tmp';temp.write_text(json.dumps({**data,'time':time.time()},indent=2));os.replace(temp,ROOT/'feedback.json')
        except (ValueError,TypeError,KeyError):self.send_error(400);return
        body=b'{"saved":true}';self.send_headers(200,len(body),'application/json');self.wfile.write(body)

    def log_message(self,fmt,*args):pass


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    state={'pid':os.getpid(),'url':f'http://127.0.0.1:{server.server_port}','port':server.server_port}
    (ROOT/'web-server.json').write_text(json.dumps(state,indent=2))
    print(state['url'],flush=True)
    server.serve_forever()
