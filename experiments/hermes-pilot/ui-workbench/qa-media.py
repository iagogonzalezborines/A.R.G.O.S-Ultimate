"""Scoped Firefox connector checks with a disposable mock native host."""
import json,socket,tempfile,threading
from pathlib import Path
from runtime import media
checks=[]
def check(name,value):
 assert value,name
 checks.append({'name':name,'ok':True})
def rejects(name,fn):
 try:fn()
 except (ValueError,RuntimeError):check(name,True)
 else:check(name,False)
with tempfile.TemporaryDirectory() as d:
 old=media.SOCKET;media.SOCKET=Path(d)/'bridge.sock'
 check('disconnected status is honest',not media.status()['connected'])
 rejects('query is bounded',lambda:media.play('x'*301));rejects('control characters rejected',lambda:media.play('song\ncommand'))
 def host(reply):
  server=socket.socket(socket.AF_UNIX);media.SOCKET.unlink(missing_ok=True);server.bind(str(media.SOCKET));server.listen(1)
  def run():
   with server:
    conn,_=server.accept()
    with conn:
     request=json.loads(conn.makefile('rb').readline());check('only narrow play request sent',set(request)=={'action','query'} and request['action']=='play');conn.sendall((json.dumps(reply)+'\n').encode())
  t=threading.Thread(target=run);t.start();return t
 t=host({'status':'autoplay_blocked'});r=media.play('AC/DC Thunderstruck');t.join();check('autoplay block is not reported as playing',not r['ok'] and r['status']=='autoplay_blocked')
 t=host({'status':'playing','title':'AC/DC - Thunderstruck','url':'https://www.youtube.com/watch?v=v2AC41dglnM'});r=media.play('AC/DC Thunderstruck');t.join();check('valid playback evidence retained',r['ok'] and r['verification']=='requested_video_advancing_and_not_showing_ad_at_check');check('no permanent ad-free guarantee invented',not r['ad_free_guaranteed'])
 t=host({'status':'playing','title':'Invalid result','url':'file:///etc/passwd'});rejects('invalid playback URL rejected',lambda:media.play('song'));t.join();media.SOCKET=old
Path(__file__).with_name('reports').joinpath('media-connector-checks.json').write_text(json.dumps({'checks':checks},indent=2)+'\n');print(json.dumps({'passed':True,'checks':len(checks)}))
