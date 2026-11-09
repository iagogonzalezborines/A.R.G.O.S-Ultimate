"""Isolated native EN/ES conversation check; copied credentials removed, all broker actions denied. No audio."""
import asyncio,json,shutil,sys,tempfile,time,socketserver,threading
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path[:0]=[str(P),str(P/'ui-workbench')]
from pilot import sandbox,PYTHON,STATE
from runtime.conversation import Worker
async def main():
 with tempfile.TemporaryDirectory(prefix='argos-startup-native-') as temporary:
  base=Path(temporary);state=base/'hermes';codex=base/'codex';state.mkdir();codex.mkdir()
  for name in ['config.yaml','auth.json']:
   if (STATE/name).exists():shutil.copyfile(STATE/name,state/name);(state/name).chmod(0o600)
  for name in ['plugins','skills','desktop-plugins']:
   if (STATE/name).exists():shutil.copytree(STATE/name,state/name)
  for name in ['config.toml','auth.json']:
   shutil.copyfile(P/'state/codex'/name,codex/name);(codex/name).chmod(0o600)
  tool_calls=[]
  class Handler(socketserver.StreamRequestHandler):
   def handle(self):
    request=json.loads(self.rfile.readline(65536))
    if request.get('tool')=='desktop' and request.get('arguments',{}).get('action')=='availability':reply={'ok':True,'result':{'enabled':False}}
    elif request.get('tool') in {'projects','adaptive'} and (request.get('arguments',{}).get('action')=='availability' or request.get('arguments',{}).get('operation')=='availability'):reply={'ok':True,'result':{'enabled':True,'project_map':True}}
    else:tool_calls.append(request.get('tool'));reply={'ok':False,'error':'Test broker denies all actions'}
    self.wfile.write((json.dumps(reply)+'\n').encode())
  host=socketserver.ThreadingUnixStreamServer(str(base/'workspace.sock'),Handler);threading.Thread(target=host.serve_forever,daemon=True).start()
  cmd=sandbox([PYTHON,P/'checks/desktop_runtime.py','argos-startup-repair-check'],network=True)
  index=cmd.index('--chdir');cmd[index:index]=['--ro-bind',str(base/'workspace.sock'),'/run/argos-workspace.sock','--bind',str(state),str(STATE),'--bind',str(codex),str(P/'state/codex'),'--setenv','ARGOS_STARTUP_EVENTS','1','--setenv','HERMES_TERMINAL_SECURITY_MODE','approval-required']
  worker=Worker(cmd,prefix=b'ARGOS_JSON ',name='codex',startup_timeout=45);report={'audio_workers':0,'microphone_capture':False,'speaker_playback':False,'isolated_credential_copy':True,'turns':[]}
  try:
   ready=await worker.start();report['startup']={k:ready.get(k) for k in ['startup_seconds','codex_ready','subscription_account_present','registered_tool_count','model_turns_during_startup']}
   for text in ['Argos, are you there? Answer in English in one short sentence. Do not use tools.','¿Estás ahí, Argos? Contesta en español con una frase breve. No uses herramientas.']:
    events=[];started=time.monotonic()
    async def event(e):
     if e.get('event')=='text.delta' and not events:events.append(time.monotonic()-started)
    response=await asyncio.wait_for(worker.call({'text':text,'workspace':[]},on_event=event),30)
    report['turns'].append({'ok':response.get('ok'),'speech':response.get('speech'),'seconds':response.get('seconds'),'first_text_seconds':events[0] if events else None,'usage':response.get('usage')})
   assert all(t['ok'] and t['speech'] for t in report['turns'])
  finally:
   await worker.close();host.shutdown();host.server_close()
  report['unexpected_tool_calls']=tool_calls;assert not tool_calls
 report['derived_stores_removed']=not base.exists()
 (P/'reports/startup-native-conversation-2026-11-09.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
asyncio.run(main())
