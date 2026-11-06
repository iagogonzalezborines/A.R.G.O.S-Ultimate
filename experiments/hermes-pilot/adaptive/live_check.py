"""Explicit disposable integration: real Codex, native Engineering and local inference; no audio."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

P=Path(__file__).resolve().parents[1];sys.path[:0]=[str(P),str(P/'ui-workbench')]
from runtime.workspace_broker import WorkspaceBroker,Files
from runtime.projects import Projects
from pilot import sandbox,PYTHON
from maintenance.controller import validation_sandbox


class Conversation:
    def __init__(self):
        command=sandbox([PYTHON,P/'checks/desktop_runtime.py','adaptive-'+str(time.time_ns())],network=True)
        i=command.index('--chdir');command[i:i]=['--ro-bind',str(P/'private/workspace.sock'),'/run/argos-workspace.sock']
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
        self.rows=queue.Queue()
        def read():
            for line in self.process.stdout:
                if line.startswith('ARGOS_JSON '):self.rows.put(json.loads(line[11:]))
            self.rows.put({'closed':True})
        threading.Thread(target=read,daemon=True).start()
        while True:
            row=self.rows.get(timeout=65)
            if not row.get('event'):
                if not row.get('ready'):raise RuntimeError('General startup failed: '+str(row))
                self.startup=row;break
    def turn(self,prompt):
        start=time.monotonic();self.process.stdin.write(json.dumps({'text':prompt})+'\n');self.process.stdin.flush()
        while True:
            row=self.rows.get(timeout=100)
            if not row.get('event'):
                if not row.get('ok'):raise RuntimeError(str(row))
                return {'seconds':time.monotonic()-start,'speech':row['speech']}
    def close(self):
        self.process.stdin.close()
        try:self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=10)


def main():
    config=json.loads((P/'installation.json').read_text())
    if not config.get('adaptive_enabled'):raise PermissionError('Enable only in a disposable lab')
    if (P/'private/workspace.sock').exists():raise RuntimeError('A Broker is already using this installation')
    broker=WorkspaceBroker(lambda _:None,lambda x:x,files=Files({'QA':Path(config['project_roots'][0])}))
    broker.serve();conversation=None
    report={'audio':False,'checks':{},'turns':[]}
    out=P/'reports/adaptive-live.json'
    def save():out.write_text(json.dumps(report,indent=2)+'\n')
    def project_call(args):return broker.projects.request(args)
    def adaptive(operation,**args):return broker.request({'tool':'adaptive','arguments':{'operation':operation,'project':project['id'],'expected_revision':project['revision'],**args}})
    def check(name,value):
        report['checks'][name]=bool(value);save();print(name,bool(value),flush=True)
        assert value,name
    try:
        name='adaptive-live-'+str(int(time.time()))
        proposal=project_call({'action':'propose','name':name,'slug':name,'brief':{'objective':'Disposable inventory and note implementation','requirements':['Standard library only','No network'],'decisions':['UTF-8'],'verification':['Run unittest'],'aliases':[]}})
        project=broker.projects.request({'action':'confirm','proposal_id':proposal['id'],'approve':True},user=True)['project']
        report['project']=project
        repo=Path(project['path']);(repo/'sample.stl').write_text('synthetic fixture');(repo/'part.obj').write_text('synthetic fixture')
        conversation=Conversation();report['startup']=conversation.startup
        report['turns'].append(conversation.turn('Return only JSON with items: extract the exact list STL, OBJ, 3MF in that order. Do not use tools.'))
        report['turns'].append(conversation.turn('Create and execute a read-only workflow for project '+name+'. Use the adaptive tool: inventory its root files, then count their extensions with the inventory as dependency. Use only files.inventory and files.types. Persist the workflow now; do not create another project.'))
        tasks=adaptive('status')['tasks'];check('natural_workflow_persisted',len(tasks)==2)
        task=project_call({'action':'task_create','project':project['id'],'expected_revision':project['revision'],
            'title':'Implement fixture notes','goal':'Create fixture_notes.py append_note(path,text), preserving existing UTF-8 lines. Add and run a unittest for two appends. Do not change existing model fixtures. Compile the module. Request review with artifact paths. No network or installs.',
            'verification':['Both appends preserved','Unittest passes']})
        start=time.time()
        dispatch=project_call({'action':'dispatch','project':project['id'],'expected_revision':project['revision'],'task_id':task['id'],'task_revision':task['revision']})
        report['engineering_dispatch']=dispatch
        check('engineering_claimed',dispatch.get('current_run_id') is not None)
        helper=adaptive('submit',capability='items',payload={'format':'prose','text':'This project supports STL and OBJ, with 3MF planned later.'})
        report['helper_id']=helper['id']
        apps_start=time.monotonic();apps=broker.request({'tool':'apps','arguments':{'action':'list'}})
        report['foreground_apps_seconds']=time.monotonic()-apps_start
        report['turns'].append(conversation.turn('While the project works, answer briefly: what is the difference between a file and a folder? Do not wait for background work.'))
        state=project_call({'action':'task','project':project['id'],'task_id':task['id']})
        report['engineering_after_foreground']=state['status']
        conversation.close();conversation=None
        # Recreate the controller while its independently owned native workers continue.
        broker.close();broker=WorkspaceBroker(lambda _:None,lambda x:x,files=Files({'QA':repo}));broker.serve()
        deadline=time.monotonic()+330
        while time.monotonic()<deadline:
            state=project_call({'action':'task','project':project['id'],'task_id':task['id']})
            rows=adaptive('status')['tasks']
            if state['status'] not in {'ready','running'} and all(t['status'] not in {'ready','running','todo'} for t in rows):break
            time.sleep(2)
        report['engineering']=state;report['capabilities']=rows;report['total_seconds']=time.time()-start
        check('engineering_review',state['status']=='review')
        check('helper_review',next(t for t in rows if t['id']==helper['id'])['status']=='review')
        helper_run=next(t for t in rows if t['id']==helper['id'])['runs'][0]
        engineering_run=state['runs'][0]
        check('actual_execution_overlap',max(helper_run['started_at'],engineering_run['started_at'])<min(helper_run['ended_at'],engineering_run['ended_at']))
        test=subprocess.run(validation_sandbox(repo,['/usr/bin/python','-m','unittest','discover','-v']),capture_output=True,text=True,timeout=20)
        report['independent_test']={'exit':test.returncode,'output':test.stdout+test.stderr}
        check('generated_tests_pass',test.returncode==0 and 'Ran 0 tests' not in test.stderr)
        report['canvas']=adaptive('canvas');(P/'reports/adaptive-workflow.canvas').write_text(json.dumps(report['canvas'],indent=2))
        check('native_canvas',bool(report['canvas']['edges']))
        check('single_attempts',all(len(t['runs'])==1 for t in rows))
    finally:
        if conversation:conversation.close()
        broker.close();save()


if __name__=='__main__':main()
