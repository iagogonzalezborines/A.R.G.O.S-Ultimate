"""Actual raw-PCM player lifecycle through a temporary null sink; no audible playback."""
import asyncio,json,subprocess,time,wave,sys
from pathlib import Path
from types import SimpleNamespace
from runtime.conversation import Conversation
ROOT=Path(__file__).resolve().parent
async def main(sink):
 host=Conversation(lambda e:None,no_capture=True,session_id='argos-pcm-output-check');host.echo=SimpleNamespace(active=True,sink=sink)
 rate=24000;seconds=.8;pcm=b'\x00\x00'*round(rate*seconds)
 probe={'chunks':[{'at':i*.1,'audio_seconds':.1} for i in range(8)]}
 began=time.monotonic();stream=await host.start_pcm(rate,host.generation);offset=0;first=probe['chunks'][0]['at']
 for chunk in probe['chunks']:
  await asyncio.sleep(max(0,chunk['at']-first-(time.monotonic()-began)));count=round(chunk['audio_seconds']*rate)*2;await host.write_pcm(stream,pcm[offset:offset+count]);offset+=count
 await host.finish_pcm(stream,host.generation);elapsed=time.monotonic()-began
 assert offset==len(pcm) and elapsed>=seconds-.08 and elapsed<seconds+2
 assert not host.speaking and stream[0].returncode==0
 stream=await host.start_pcm(rate,host.generation);await host.write_pcm(stream,pcm);await asyncio.sleep(.15);host.generation+=1;await host.stop_player();await host.finish_pcm(stream,host.generation-1);assert not host.speaking
 host.loop.close();report={'raw_pcm_playback_passed':True,'source_seconds':seconds,'actual_player_seconds':elapsed,'all_source_bytes_written':offset==len(pcm),'eof_drains_audio_tail':True,'interruption_stops_player':True,'playback':'temporary null sink, not speakers'};(ROOT/'reports/pcm-output-checks.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
sink='argos-qa-stream-output';module=subprocess.check_output(['pactl','load-module','module-null-sink','sink_name='+sink,'rate=24000','channels=1','channel_map=mono'],text=True).strip()
try:asyncio.run(main(sink))
finally:subprocess.run(['pactl','unload-module',module],check=True)
