"""Loopback presentation host. No agent loop, project access or task ownership."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import collections
import hmac
import json
import mimetypes
import secrets
import threading
import time
from urllib.parse import urlsplit, unquote

ROOT=Path(__file__).resolve().parent
DIST=ROOT/'dist'
ALLOWED_HOSTS={'science.nasa.gov','www.nasa.gov','en.wikipedia.org','es.wikipedia.org','www.swpc.noaa.gov'}
KINDS={'desktop','project','conversation','progress','summary','sources','browser','video','agents','note','files','document','change','storage','maintenance'}
events=collections.deque(maxlen=128)
changed=threading.Condition()
sequence=0

def publish(event):
    global sequence
    with changed:
        sequence+=1;events.append({'sequence':sequence,**event});changed.notify_all()

def validate(intent):
    if not isinstance(intent,dict) or set(intent)-{'type','id','kind','title','text','url','path','x','y','width','height','status'}:
        raise ValueError('Unsupported presentation fields')
    if intent.get('type') not in {'window.open','window.close','window.focus','window.minimize','window.restore','window.maximize','window.move','window.update','workspace.arrange','workspace.clear'}:
        raise ValueError('Unknown presentation intent')
    if intent['type'] not in {'workspace.arrange','workspace.clear'}:
        import re
        if not re.fullmatch(r'[a-zA-Z0-9-]{1,64}',intent.get('id','')):raise ValueError('Invalid window ID')
    if intent['type']=='window.open' and intent.get('kind') not in KINDS:raise ValueError('Unknown panel kind')
    for key,limit in [('title',100),('text',12000),('status',100),('path',2048)]:
        if key in intent and (not isinstance(intent[key],str) or len(intent[key])>limit):raise ValueError('Invalid text')
    for key in ['x','y','width','height']:
        if key in intent and (type(intent[key]) not in [int,float] or not -10000<intent[key]<10000):raise ValueError('Invalid geometry')
    if 'url' in intent:
        u=urlsplit(intent['url'])
        host=u.hostname or ''
        if u.scheme!='https' or '.' not in host or host.replace('.','').isdigit() or ':' in host or host.endswith(('.local','.internal','.localhost','.test','.invalid')) or u.username or u.password or u.port not in (None,443):raise ValueError('URL must be public HTTPS')
    return intent

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(DIST),**kwargs)
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-src https://science.nasa.gov https://en.wikipedia.org https://es.wikipedia.org https://www.swpc.noaa.gov; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        super().end_headers()
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/events':return self.stream()
        if path=='/health':
            voice=self.server.voice;status=voice.status if voice else {}
            conversation_ready=bool(status.get('ready') and status.get('phase')!='error')
            voice_ready=bool(status.get('voice_ready'))
            return self.reply(200,{'ready':not voice or (conversation_ready and (status.get('text_only') or voice_ready)),
                'presentation_ready':True,'mode':'argos-app' if voice else 'presentation-pilot',
                'agent_connected':conversation_ready,'voice_ready':voice_ready,
                'renderer_connected':bool(self.server.workspace.connected_at and time.monotonic()-self.server.workspace.connected_at<45)})
        if path=='/voice-state':
            if not self.authorized():return self.send_error(401)
            return self.reply(200,dict(self.server.voice.status) if self.server.voice else {'ready':False,'phase':'off','listening':False})
        if path=='/':self.path='/index.html'
        elif path not in {'/index.html','/style.css','/app.js','/desktop-control.js','/project-map.js','/window-manager.js','/files.js','/orbital.js','/sounds.js','/maintenance.js','/progress.js','/demo.json'} and not path.startswith('/assets/'):
            # New renderer modules are public only after the trusted release
            # journal admits them; candidates and arbitrary files stay private.
            development=getattr(self.server.workspace,'development',None)
            if development and 'dist'+path in development.extensions():
                from maintenance.controller import read_regular
                file=DIST/path.lstrip('/')
                try:body=read_regular(file)
                except (OSError,ValueError):return self.send_error(404)
                self.send_response(200);self.send_header('Content-Type','text/javascript' if path.endswith('.js') else 'text/css');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
            return self.send_error(404)
        decoded=unquote(path)
        if '..' in decoded.split('/') or not (DIST/decoded.lstrip('/')).resolve().is_relative_to(DIST):return self.send_error(404)
        if path.startswith('/assets/') and self.headers.get('Range'):
            import re
            file=DIST/decoded.lstrip('/')
            match=re.fullmatch(r'bytes=(\d+)-(\d*)',self.headers['Range'])
            if not file.is_file() or not match:return self.send_error(416)
            size=file.stat().st_size;start=int(match[1]);end=min(int(match[2]) if match[2] else size-1,size-1)
            if start>end:return self.send_error(416)
            self.send_response(206);self.send_header('Content-Type',mimetypes.guess_type(str(file))[0] or 'application/octet-stream');self.send_header('Content-Length',str(end-start+1));self.send_header('Content-Range',f'bytes {start}-{end}/{size}');self.send_header('Accept-Ranges','bytes');self.end_headers()
            try:
                with file.open('rb') as f:
                    f.seek(start);left=end-start+1
                    while left:
                        chunk=f.read(min(65536,left))
                        if not chunk:break
                        self.wfile.write(chunk);left-=len(chunk)
            except (BrokenPipeError,ConnectionResetError):pass
            return
        return super().do_GET()
    def list_directory(self,path):self.send_error(404)
    def reply(self,status,data):
        try:
            body=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
    def do_POST(self):
        global sequence
        if self.path not in {'/api/presentation','/api/voice','/api/workspace','/api/capability','/api/diagnostic'}:return self.send_error(404)
        if self.headers.get('Origin') not in (None,f'http://127.0.0.1:{self.server.server_port}'):return self.send_error(403)
        if not self.authorized():return self.send_error(401)
        try:
            size=int(self.headers.get('Content-Length',0))
            if not 0<size<=524288:raise ValueError('Invalid size')
            body=json.loads(self.rfile.read(size))
            if self.path=='/api/diagnostic':
                if not isinstance(body,dict) or set(body)-{'component','message'} or body.get('component') not in {'renderer','browser'} or not isinstance(body.get('message'),str) or len(body['message'])>800:raise ValueError('Invalid diagnostic')
                incident=self.server.workspace.development.incident(body['component'],RuntimeError(body['message']),notify=body['component']=='renderer')
                return self.reply(200,{'recorded':True,'incident_id':incident['id']})
            if self.path=='/api/workspace':
                if not isinstance(body,dict) or set(body)-{'windows','ack','error'}:raise ValueError('Invalid desktop acknowledgement')
                return self.reply(200,self.server.workspace.state(body.get('windows'),body.get('ack'),body.get('error')))
            if self.path=='/api/capability':return self.reply(200,self.server.workspace.request(body,user=True))
            if self.path=='/api/voice':
                if not self.server.voice:raise ValueError('Voice unavailable')
                if not isinstance(body,dict) or set(body)-{'op','enabled','text','language'}:raise ValueError('Invalid voice fields')
                op=body.get('op')
                if op not in {'text','listen','interrupt','output','retry','test-text','test-speech','test-tts'}:raise ValueError('Unknown voice command')
                if op in {'listen','output'} and type(body.get('enabled')) is not bool:raise ValueError('Invalid voice control')
                if op in {'test-text','test-speech','test-tts'} and (not self.server.voice.no_capture or not isinstance(body.get('text'),str) or not 0<len(body['text'])<=12000):raise ValueError('Test entry disabled')
                if op=='text' and (not isinstance(body.get('text'),str) or not 0<len(body['text'].strip())<=12000):raise ValueError('Invalid text')
                future=self.server.voice.post(**body)
                if op=='text':return self.reply(202,future.result(timeout=5))
                if op in {'test-text','test-speech','test-tts'}:return self.reply(200,future.result(timeout=240))
                return self.reply(202,{'accepted':True})
            intent=validate(body)
        except (ValueError,TypeError) as error:
            if self.server.workspace.development:self.server.workspace.development.incident('desktop.request',error,notify=False)
            import traceback
            frames=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)]
            with (ROOT/'reports/host-errors.jsonl').open('a') as log:log.write(json.dumps({'category':type(error).__name__,'frames':frames})+'\n')
            return self.reply(400,{'error':str(error)[:200] or 'Invalid workspace request'})
        except PermissionError as error:
            if self.server.workspace.development:self.server.workspace.development.incident('desktop.permission',error,notify=False)
            return self.reply(403,{'error':str(error)[:200]})
        except (FileNotFoundError,NotADirectoryError):return self.reply(404,{'error':'The file or folder is not available in this workspace.'})
        except FileExistsError:return self.reply(409,{'error':'The destination already exists. Choose another name.'})
        except OSError as error:
            if self.server.workspace.development:self.server.workspace.development.incident('desktop.files',error,notify=False)
            import errno
            message={errno.ENOSPC:'The destination does not have enough free space.',errno.EROFS:'The destination filesystem is read-only.',errno.EXDEV:'Moving across filesystems is not enabled. Copy the file instead.'}.get(error.errno,'The filesystem operation failed.')
            return self.reply(507 if error.errno==errno.ENOSPC else 409,{'error':message})
        except Exception as error:
            if self.server.workspace.development:self.server.workspace.development.incident('desktop.request',error)
            return self.reply(503,{'error':'Conversation unavailable'})
        publish({'actor':'argos','intent':intent})
        return self.reply(202,{'accepted':True,'sequence':sequence,'execution':'pending UI acknowledgement'})
    def authorized(self):
        return hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+self.server.token)
    def stream(self):
        if self.headers.get('Origin') not in (None,f'http://127.0.0.1:{self.server.server_port}'):return self.send_error(403)
        if not self.authorized():return self.send_error(401)
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Connection','keep-alive');self.end_headers()
        try:
            cursor=int(self.headers.get('Last-Event-ID',sequence))
            while True:
                with changed:
                    pending=[e for e in events if e['sequence']>cursor]
                    if not pending:changed.wait(timeout=5)
                if not pending:self.wfile.write(b': heartbeat\n\n')
                for event in pending:
                    self.wfile.write(f"id: {event['sequence']}\ndata: {json.dumps(event)}\n\n".encode());cursor=event['sequence']
                self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError):pass
    def log_message(self,*args):pass

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=42720);parser.add_argument('--voice',action='store_true');parser.add_argument('--text-only',action='store_true');parser.add_argument('--no-capture',action='store_true');parser.add_argument('--mute-playback',action='store_true');parser.add_argument('--session',default='argos-workspace-default');args=parser.parse_args()
    private=ROOT/'private';private.mkdir(exist_ok=True,mode=0o700)
    tokenfile=private/'presentation.token'
    if not tokenfile.exists():tokenfile.write_text(secrets.token_urlsafe(32));tokenfile.chmod(0o600)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.daemon_threads=True;server.token=tokenfile.read_text().strip()
    from runtime.workspace_broker import WorkspaceBroker
    server.workspace=WorkspaceBroker(publish,validate)
    import sys
    sys.path.insert(0,str(ROOT.parent))
    from maintenance.controller import Maintenance, BASE
    server.workspace.development=Maintenance(publish,lambda:list(server.workspace.windows),state=(BASE/'qa'/args.session) if args.no_capture else None,auto_diagnose=not args.no_capture)
    def thread_error(args):
        try:server.workspace.development.incident('backend.thread',args.exc_value)
        except Exception:pass
    threading.excepthook=thread_error
    server.workspace.serve()
    server.voice=None
    if args.voice or args.text_only:
        from runtime.conversation import Conversation
        server.voice=Conversation(publish,text_only=args.text_only,no_capture=args.no_capture,mute=args.mute_playback,session_id=args.session,workspace=server.workspace);server.voice.start()
    (ROOT/'server.json').write_text(json.dumps({'url':f'http://127.0.0.1:{args.port}','port':args.port}))
    print(f'ARGOS workspace: http://127.0.0.1:{args.port}',flush=True)
    import signal
    def stop(*_):threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:server.serve_forever()
    finally:
        server.workspace.files.stopping.set()
        server.server_close()
        if server.voice:server.voice.close()
        server.workspace.close()
