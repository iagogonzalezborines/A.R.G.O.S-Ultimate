"""Opt-in real subscription test, disposable files only; no audio or production project."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time

P = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(P), str(P/'ui-workbench')]
from runtime.workspace_broker import WorkspaceBroker, Files
from runtime.projects import Projects
from pilot import sandbox, PYTHON
from maintenance.controller import validation_sandbox


def main():
    root = Path(tempfile.mkdtemp(prefix='argos-block-b-live-'))
    (root/'repositories').mkdir()
    config = {'projects_enabled':True,'pilot_root':str(P),'operational_root':str(P.parents[2]/'Proyectos/A.R.G.O.S-Ultimate'),
              'project_roots':[str(root/'repositories')],'project_state':str(root/'native')}
    file = root/'installation.json';file.write_text(json.dumps(config))
    events = []
    broker = WorkspaceBroker(events.append,lambda x:x,files=Files({'QA':root}))
    broker.projects = Projects(lambda intent:broker.intent(intent,wait=False),config_path=file)
    broker.serve()
    report = {'root':str(root),'checks':{},'turns':[],'audio':'No voice workers, microphone or playback'}
    (P/'reports/block-b-live-location.json').write_text(json.dumps({'root':str(root)}))
    process = None
    def start(sid):
        cmd = sandbox([PYTHON,P/'checks/desktop_runtime.py',sid],network=True)
        cmd[cmd.index('--chdir'):cmd.index('--chdir')] = ['--ro-bind',str(P/'private/workspace.sock'),'/run/argos-workspace.sock',
                             '--setenv','HERMES_TERMINAL_SECURITY_MODE','approval-required']
        child = subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(root/'conversation.log').open('a'),text=True)
        rows=queue.Queue()
        def reader():
            for line in child.stdout:
                if line.startswith('ARGOS_JSON '):rows.put(json.loads(line[11:]))
            rows.put({'closed':True})
        threading.Thread(target=reader,daemon=True).start()
        while True:
            row=rows.get(timeout=70)
            if not row.get('event'):
                assert row.get('ready'),row
                assert row['model_turns_during_startup']==0
                break
        return child,rows
    def turn(child,rows,text):
        child.stdin.write(json.dumps({'text':text})+'\n');child.stdin.flush()
        while True:
            row=rows.get(timeout=150)
            if not row.get('event'):
                assert row.get('ok'),row
                report['turns'].append({'request':text,'speech':row['speech']})
                return row
    def call(args,user=False):return broker.request({'tool':'projects','arguments':args},user=user)
    def check(name,ok):
        report['checks'][name]=bool(ok)
        (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(name,bool(ok),flush=True)
        assert ok,name
    try:
        process,rows=start('argos-block-b-create-'+root.name[-8:])
        turn(process,rows,"Let's create a persistent project called Fixture Notes, slug fixture-notes, alias notebook. It should keep plain-text notes in its own folder. Requirements: standard library only and no network. Decision: UTF-8 files. Verification: run a unittest. Prepare the concrete project folder for my review; do not start coding yet.")
        pending=list(broker.projects.pending.values())
        check('natural_request_prepared_scope',len(pending)==1)
        project=call({'action':'confirm','proposal_id':pending[0]['id'],'approve':True},user=True)['project']
        report['project_id']=project['id']
        check('native_project_created_after_trusted_review',project['state']=='ready')
        process.stdin.close();process.wait(timeout=20);process=None
        # A fresh conversation has no previous transcript; native project registry supplies the identity.
        process,rows=start('argos-block-b-later-'+root.name[-8:])
        turn(process,rows,'Continue the notebook project. Read its saved requirements and decisions, and report them briefly. Do not create another project or start coding yet.')
        selected=call({'action':'resolve','project':'notebook'})
        check('later_conversation_resolved_native_project',selected['id']==project['id'] and len(call({'action':'list'})['projects'])==1)
        turn(process,rows,'Change the requirements of notebook: also preserve existing notes when adding a new one. Keep all previous requirements and the UTF-8 decision. Save this change now; do not start coding.')
        project=call({'action':'resolve','project':'notebook'})
        check('natural_update_persisted',project['revision']!=selected['revision'] and len(project['brief']['requirements'])>=len(selected['brief']['requirements']))
        # A tiny fixture implementation validates B's dispatch, not Block C's model-manager application.
        turn(process,rows,'For notebook, create one Engineering task titled Verify fixture notes. Implement fixture_notes.py with append_note(path, text) that appends one UTF-8 line, preserving existing lines. Create a unittest with a temporary file, run it and compile the module. Verification: two appends preserve both lines. No installations or network. Dispatch this authorized local task now and return without waiting for it to finish. It must request native review with artifact paths rather than marking itself complete.')
        tasks=call({'action':'tasks','project':project['id']})['tasks']
        check('natural_task_created',len(tasks)==1)
        task=tasks[0];report['task_id']=task['id']
        check('native_dispatch_has_run_evidence',task['current_run_id'] is not None or task['status']=='review')
        process.stdin.close();process.wait(timeout=20);process=None
        # Disconnect the entire conversation and Broker; native owner must continue.
        broker.close()
        broker=WorkspaceBroker(events.append,lambda x:x,files=Files({'QA':root}))
        broker.projects=Projects(lambda intent:broker.intent(intent,wait=False),config_path=file)
        broker.serve()
        deadline=time.monotonic()+330
        while True:
            state=call({'action':'task','project':project['id'],'task_id':task['id']})
            if state['status'] not in {'ready','running'}:break
            if time.monotonic()>deadline:raise RuntimeError('Native task did not settle within its bound')
            time.sleep(2)
        report['task']=state
        check('native_review_after_broker_restart',state['status']=='review' and bool(state['runs']))
        repo=Path(project['path'])
        test=subprocess.run(validation_sandbox(repo,['/usr/bin/python','-m','unittest','discover','-v']),capture_output=True,text=True,timeout=30)
        report['independent_test']={'exit_code':test.returncode,'output':test.stdout+test.stderr,'sandbox':'maintenance.validation_sandbox'}
        check('independent_generated_fixture_tests',test.returncode==0 and 'Ran 0 tests' not in test.stderr)
        check('artifact_paths_and_hashes_observed',bool(state['artifacts']))
        duplicate=call({'action':'dispatch','project':project['id'],'task_id':task['id'],'expected_revision':project['revision'],'task_revision':task['revision']})
        check('duplicate_dispatch_does_not_replay',duplicate['status']=='review' and len(call({'action':'task','project':project['id'],'task_id':task['id']})['runs'])==len(state['runs']))
        report['passed']=all(report['checks'].values())
    finally:
        if process:
            process.stdin.close()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10)
        broker.close()
        (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print('Evidence:',root/'report.json',flush=True)


if __name__=='__main__':main()
