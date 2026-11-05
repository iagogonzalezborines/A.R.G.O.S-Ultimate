"""Cancel a real native research turn during its brief dispatch speech, then recover."""
import concurrent.futures,json,time,urllib.request
from pathlib import Path
P=Path(__file__).resolve().parents[1];U=P/'ui-workbench';headers={'Authorization':'Bearer '+(U/'private/presentation.token').read_text().strip(),'Content-Type':'application/json'}
def call(body):
 with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:42721/api/voice',data=json.dumps(body).encode(),headers=headers),timeout=180) as r:return json.load(r)
with concurrent.futures.ThreadPoolExecutor() as pool:
 start=time.monotonic();future=pool.submit(call,{'op':'test-text','text':'Research the current state of reusable rockets and show the sources as you find them.'});time.sleep(.25);call({'op':'interrupt'});result=future.result(timeout=90);cancel_seconds=time.monotonic()-start
call({'op':'test-text','text':'Say exactly: Ready for the next task.'})
m=[json.loads(s) for s in (U/'reports/voice-latency.jsonl').read_text().splitlines() if json.loads(s).get('session_id')=='argos-incremental-voice-check'][-1]
assert m['audio_packets'] and not m['web_calls'] and all(c['kind']=='answer' for c in m['chunks']),m
report={'cancel_seconds':cancel_seconds,'recovery_metrics':m,'playback':'Muted duration simulation; real native model and Qwen PCM.'};(U/'reports/incremental-cancel.json').write_text(json.dumps(report,indent=2));print(json.dumps({'cancel_seconds':cancel_seconds,'recovery_first_audio':m['first_audio_ready_seconds'],'no_stale_progress':True}),flush=True)
