#!/usr/bin/python3
"""Fixed proof-only Codex launch policy; native Hermes still owns all task state."""
import json,os,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent;P=BASE.parents[1]
POLICY=BASE/'policy.json'

def arguments(argv,policy):
 if argv==['--version']:return [str(P/'bin/codex'),'--version']
 if not argv or argv[0]!='app-server':raise ValueError('Only the native app-server entry point is supported')
 cleaned=['app-server'];i=1;removed=[]
 while i<len(argv):
  arg=argv[i]
  if arg in {'-c','--config'}:
   if i+1>=len(argv):raise ValueError('Missing config override')
   value=argv[i+1];key=value.split('=',1)[0].strip()
   if key in {'sandbox_mode','sandbox_workspace_write','default_permissions','permissions','approval_policy'} or key.startswith(('sandbox_workspace_write.','permissions.')):removed.append(key)
   else:cleaned.extend([arg,value])
   i+=2;continue
  if arg.startswith(('-c=','--config=')):raise ValueError('Unsupported configuration syntax')
  if arg in {'--dangerously-bypass-approvals-and-sandbox','--yolo','--full-auto'}:raise ValueError('Unsafe execution option')
  cleaned.append(arg);i+=1
 # Authoritative CLI overrides outrank project configuration. Policy data comes
 # from a controller-owned file outside the only writable project directory.
 for key,value in [('default_permissions','argos-proof'),('approval_policy','never'),('web_search','disabled'),('features.apps',False),('plugins._default.enabled',False),('permissions.argos-proof.filesystem',policy['filesystem']),('permissions.argos-proof.network',{'enabled':False}),('shell_environment_policy.filters',{'PATH':'include','LANG':'include','LC_*':'include','HOME':'include','TERM':'include','TMPDIR':'include'}),('shell_environment_policy.set',{'HOME':policy['repository']+'/.tool-home','TMPDIR':policy['repository']+'/.tmp','XDG_CACHE_HOME':policy['repository']+'/.cache'})]:
  encoded=('{'+','.join(json.dumps(k)+'='+json.dumps(v) for k,v in value.items())+'}') if isinstance(value,dict) else json.dumps(value)
  cleaned.extend(['-c',key+'='+encoded])
 return [str(P/'bin/codex'),*cleaned],removed

if __name__=='__main__':
 try:
  policy=json.loads(POLICY.read_text())
  if sys.argv[1:]==['--version']:os.execv(str(P/'bin/codex'),[str(P/'bin/codex'),'--version'])
  command,removed=arguments(sys.argv[1:],policy)
  # Public policy metadata only; never log inherited env, tokens or raw argv.
  with (BASE/'launch-audit.jsonl').open('a') as f:f.write(json.dumps({'pid':os.getpid(),'removed_policy_keys':removed,'policy':'argos-proof'})+'\n')
  os.environ['CODEX_HOME']=str(BASE/'codex')
  os.execv(command[0],command)
 except (OSError,ValueError,KeyError) as error:
  print('ARGOS proof launch refused: '+type(error).__name__,file=sys.stderr);raise SystemExit(2)
