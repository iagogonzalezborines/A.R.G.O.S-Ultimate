"""Prepare a private candidate, not a runtime migration. Reuses Block A launch policy."""
import argparse
import json
from pathlib import Path
import secrets
import sys


def prepare(candidate,base):
    candidate=candidate.resolve();base=base.resolve()
    if candidate==base or candidate.is_relative_to(base) or base.is_relative_to(candidate):
        raise ValueError('Candidate and operational runtime must be separate')
    config=candidate/'state/openclaw.json'
    # Plugin installation can have created a minimal config; never overwrite an active setup.
    existing=json.loads(config.read_text()) if config.exists() else {}
    if 'agents' in existing or 'gateway' in existing:raise ValueError('Existing configured candidate preserved')
    sys.path.insert(0,str(base));from projects.worker import verify_pin
    verify_pin(base)
    for part in ['home','workspace','codex','state']:(candidate/part).mkdir(parents=True,exist_ok=True,mode=0o700)
    repository=candidate/'workspace'
    for part in ['.tool-home','.tmp']:(repository/part).mkdir(exist_ok=True)
    policy={'repository':str(repository),'filesystem':{':root':'deny',':minimal':'read',str(repository):'write',
        str(candidate/'codex'):'deny',str(candidate/'state'):'deny'}}
    (candidate/'policy.json').write_text(json.dumps(policy));(candidate/'policy.json').chmod(0o600)
    launcher=candidate/'launch.py'
    launcher.write_text('#!/usr/bin/python3\nimport sys,os,json\nfrom pathlib import Path\n'
        +'sys.path.insert(0,'+repr(str(base/'project-intelligence/recovery'))+')\nfrom launch_policy import arguments\n'
        +'args=sys.argv[1:]\nif "app-server" in args:\n i=args.index("app-server");args=["app-server",*args[:i],*args[i+1:]]\n'
        +'result=arguments(args,json.loads(Path('+repr(str(candidate/'policy.json'))+').read_text()))\n'
        +'command=result[0] if isinstance(result,tuple) else result\nos.execv(command[0],command)\n')
    launcher.chmod(0o700)
    tools=['exec','process','workboard_heartbeat','workboard_complete','workboard_block']
    manifest=json.loads(Path(__file__).with_name('manifest.json').read_text())
    entries=existing.setdefault('plugins',{}).setdefault('entries',{})
    entries.update({'workboard':{'enabled':True},'memory-core':{'enabled':False},'codex':{'enabled':True,'config':{
        'appServer':{'command':str(launcher),'homeScope':'user','approvalPolicy':'never','sandbox':'workspace-write'}}}})
    existing['plugins']['allow']=['workboard','codex']
    existing.update(gateway={'mode':'local','port':19831,'bind':'loopback','auth':{'mode':'token','token':secrets.token_hex(24)}},
        agents={'defaults':{'workspace':str(repository),'maxConcurrent':1,'model':'openai/gpt-6-luna','thinkingDefault':'low',
            'models':{'openai/gpt-6-luna':{'agentRuntime':{'id':'codex'}}},'modelPolicy':{'allow':['openai/gpt-6-luna']},
            'heartbeat':{'every':'0m'},'subagents':{'maxConcurrent':1,'maxSpawnDepth':1},
            'sandbox':{'mode':'all','scope':'session','workspaceAccess':'rw','docker':{'image':manifest['openclaw_docker_image'],
                'network':'none','readOnlyRoot':True,'capDrop':['ALL'],'pidsLimit':64,'memory':'512m','cpus':1}}}},
        tools={'allow':tools,'deny':['message','browser','sessions_spawn'],'sandbox':{'tools':{'allow':tools}}},cron={'enabled':False})
    config.write_text(json.dumps(existing,indent=2)+'\n');config.chmod(0o600)
    (candidate/'codex/config.toml').write_text('forced_login_method="chatgpt"\ncli_auth_credentials_store="file"\nweb_search="disabled"\n[features]\napps=false\n[plugins._default]\nenabled=false\n')
    print('Candidate configured, stopped and unauthenticated. Review Docker image digest before dispatch.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--base',type=Path,required=True)
    args=parser.parse_args();prepare(args.candidate,args.base)
