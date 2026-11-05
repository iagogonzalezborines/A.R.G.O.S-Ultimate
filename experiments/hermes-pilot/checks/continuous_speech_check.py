"""Native-model and continuous PCM scheduling checks; microphone/playback muted."""
from pathlib import Path
import concurrent.futures,json,time,urllib.request
P=Path(__file__).resolve().parents[1];U=P/'ui-workbench';base='http://127.0.0.1:42721';headers={'Authorization':'Bearer '+(U/'private/presentation.token').read_text().strip(),'Content-Type':'application/json'}
def call(body):
 with urllib.request.urlopen(urllib.request.Request(base+'/api/voice',data=json.dumps(body).encode(),headers=headers),timeout=180) as r:return json.load(r)
def latest():return [json.loads(s) for s in (U/'reports/voice-latency.jsonl').read_text().splitlines() if json.loads(s).get('session_id')=='argos-continuous-speech-check'][-1]
rows=[]
for text in ["For a speech timing test, repeat exactly: The workspace is clear. Your files are unchanged. I'm ready for the next task.",'Para una prueba de voz, repite exactamente: La primera frase termina aquí. La siguiente continúa con naturalidad. Sin pausas interminables.']:
 call({'op':'test-text','text':text});m=latest();assert m['continuous_pcm'] and len(m['chunks'])==1,m
 assert len(m['audio_packets'])>2
 playhead=m['first_playback_start_seconds'];gaps=[]
 for packet in m['audio_packets']:
  gap=max(0,packet['ready_seconds']-playhead)
  if gap>.03:gaps.append(gap)
  playhead=max(playhead,packet['ready_seconds'])+packet['duration_seconds']
 assert not gaps,gaps
 row={'input':text,'metrics':m,'simulated_queue_gaps':gaps};rows.append(row);print(json.dumps({'language':'es' if text.startswith('Para') else 'en','utterances':len(m['chunks']),'first_audio_ready':m['first_audio_ready_seconds'],'model_seconds':m['model_seconds'],'packets':len(m['audio_packets']),'gaps':gaps}),flush=True)
with concurrent.futures.ThreadPoolExecutor() as pool:
 future=pool.submit(call,{'op':'test-text','text':'For a speech test, say five sentences about an ordinary desk, one after another.'});time.sleep(4);call({'op':'interrupt'});future.result(timeout=90)
call({'op':'test-text','text':'Say exactly: Ready for the next task.'});recovery=latest();assert recovery['audio_packets']
report={'turns':rows,'recovery':recovery,'playback':'muted duration simulation with real model and PCM generation','engine_pin':'b8db6ff1cebc0d6554cf0977045850bcc796b383'};(U/'reports/continuous-speech-checks.json').write_text(json.dumps(report,indent=2)+'\n');print('Cancellation/recovery passed',flush=True)
