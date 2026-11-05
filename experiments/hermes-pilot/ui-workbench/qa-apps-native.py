"""Actual native model -> configured MCP -> live broker -> requested Discord launch."""
import asyncio,json,subprocess,sys,time,tomllib
from pathlib import Path
from runtime.conversation import Worker
P=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(P))
from pilot import sandbox,PYTHON

async def main():
 config=tomllib.loads((P/'state/codex/config.toml').read_text())
 enabled=config['mcp_servers']['argos-workspace']['enabled_tools']
 assert 'apps' in enabled,'Application tool missing from actual native connector allowlist'
 cmd=sandbox([PYTHON,P/'checks/desktop_runtime.py','argos-discord-native-check-20261105'],network=True)
 i=cmd.index('--chdir');cmd[i:i]=['--ro-bind',str(P/'private/workspace.sock'),'/run/argos-workspace.sock','--setenv','HERMES_TERMINAL_SECURITY_MODE','approval-required']
 worker=Worker(cmd,prefix=b'ARGOS_JSON ',name='codex',startup_timeout=45)
 report={'connector_apps_enabled':True,'audio_workers':0,'events':[],'requested_app':'discord'}
 try:
  report['startup']=await worker.start();start=time.monotonic()
  async def event(e):
   if e.get('event')!='text.delta':report['events'].append({'seconds':time.monotonic()-start,**e})
  report['result']=await worker.call({'text':'Discord, the app. Can you open Discord, the app?','workspace':[]},on_event=event)
  for _ in range(30):
   clients=json.loads(subprocess.check_output(['hyprctl','-j','clients']))
   if any('discord' in c.get('class','').lower() for c in clients):report['discord_window_present']=True;break
   await asyncio.sleep(.2)
  else:report['discord_window_present']=False
  audit=P/'ui-workbench/reports/workspace-capability-audit.jsonl'
  report['app_tool_calls']=[json.loads(line) for line in audit.read_text().splitlines() if json.loads(line).get('time',0)>=time.time()-120 and json.loads(line).get('tool')=='apps']
  report['passed']=report['result'].get('ok') and report['discord_window_present'] and any(c.get('action')=='open' and c.get('ok') for c in report['app_tool_calls'])
 finally:
  await worker.close();(P/'ui-workbench/reports/apps-native-discord.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:report.get(k) for k in ['passed','result','discord_window_present','app_tool_calls']}),flush=True)
 if not report.get('passed'):raise SystemExit(1)
asyncio.run(main())
