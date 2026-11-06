"""Native lifecycle fault tests, including forged evidence and concurrent decisions."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import unittest

P=Path(__file__).resolve().parents[1];sys.path[:0]=[str(P),str(P/'projects')]
from qa import NativeProjectTests
from pilot import environment


class LifecycleTests(NativeProjectTests):
    def native_change(self,project,task,code):
        env=environment();env.update(HERMES_HOME=str(self.root/'native'),HERMES_KANBAN_HOME=str(self.root/'native'),PYTHONPATH=str(P)+':'+str(P/'source'))
        script="from hermes_cli import kanban_db as kb\nfrom hermes_cli.kanban_db_connect import connect_closing\nimport sys,json\nwith connect_closing(board=sys.argv[1]) as conn:\n task=sys.argv[2]\n"+''.join(' '+line+'\n' for line in code.splitlines())
        subprocess.run([str(P/'env/bin/python'),'-c',script,project['board'],task['id']],env=env,capture_output=True,check=True,timeout=10)
    def reviewed(self):
        p=self.create();t=self.task(p)
        self.native_change(p,t,"kb.unblock_task(conn,task)\nclaimed=kb.claim_task(conn,task)\nkb.request_review(conn,task,summary='Worker claim; not verification',expected_run_id=claimed.current_run_id)")
        return p,self.call({'action':'task','project':p['id'],'task_id':t['id']})
    def decision(self,p,t,operation,**extra):
        return self.call({'action':'lifecycle','project':p['id'],'task_id':t['id'],'expected_revision':p['revision'],
                          'task_revision':t['revision'],'operation':operation,**extra},user=True)
    def test_review_never_dispatches_and_forged_verification_fails(self):
        p,t=self.reviewed()
        for _ in range(3):self.call({'action':'dispatch','project':p['id'],'task_id':t['id'],'expected_revision':p['revision'],'task_revision':t['revision']})
        self.assertEqual(len(self.call({'action':'task','project':p['id'],'task_id':t['id']})['runs']),1)
        with self.assertRaises(PermissionError):self.call({'action':'lifecycle','operation':'accept','project':p['id'],'task_id':t['id'],'expected_revision':p['revision'],'task_revision':t['revision']})
        self.native_change(p,t,"kb.add_comment(conn,task,'argos-controller',json.dumps({'argos_evidence':{'task_id':task,'project_id':"+repr(p['id'])+",'kind':'verification','passed':True},'signature':'forged'}))")
        t=self.call({'action':'task','project':p['id'],'task_id':t['id']})
        with self.assertRaises(PermissionError):self.decision(p,t,'accept')
    def test_independent_verification_artifact_revision_and_concurrent_accept(self):
        p,t=self.reviewed();test=Path(p['path'])/'test_example.py'
        test.write_text('import unittest\nclass Check(unittest.TestCase):\n def test_one(self): self.assertEqual(2+2,4)\n')
        verified=self.decision(p,t,'verify');self.assertTrue(verified['controller_evidence'][-1]['passed'])
        test.write_text(test.read_text()+'# changed\n')
        with self.assertRaises(PermissionError):self.decision(p,verified,'accept')
        verified=self.decision(p,verified,'verify')
        def approve(_):
            try:return self.decision(p,verified,'accept')['status']
            except ValueError:return 'stale'
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(approve,range(2)))
        self.assertEqual(sorted(out),['done','stale'])
    def test_interruption_requires_explicit_bounded_retry(self):
        p,t=self.reviewed();blocked=self.decision(p,t,'reject',reason='Missing acceptance criterion')
        with self.assertRaises(PermissionError):self.call({'action':'dispatch','project':p['id'],'task_id':t['id'],'expected_revision':p['revision'],'task_revision':blocked['revision']})
        retry=self.decision(p,blocked,'retry',reason='Inspected outputs; repair one missing criterion')
        self.assertEqual(retry['status'],'ready');self.assertEqual(retry['controller_evidence'][-1]['number'],1)
        with self.assertRaises(ValueError):self.decision(p,blocked,'retry',reason='Duplicate click')
        # A native claim consumes that grant; a second claim cannot reuse it.
        self.native_change(p,t,"from projects.lifecycle import permit\nconfig=json.loads(open("+repr(str(self.config_path))+").read())\nc=kb.claim_task(conn,task)\npermit(conn,c,config,claimed=True)\nkb.reclaim_task(conn,task,reason='crash')\nc=kb.claim_task(conn,task)\ntry:\n permit(conn,c,config,claimed=True)\nexcept PermissionError: pass\nelse: raise AssertionError('Grant replayed')\nkb.reclaim_task(conn,task,reason='cleanup')")
    def test_changed_files_invalidate_retry_admission(self):
        p,t=self.reviewed();t=self.decision(p,t,'retry',reason='Inspected original effects')
        (Path(p['path'])/'new.txt').write_text('changed after approval')
        with self.assertRaisesRegex(PermissionError,'changed after retry'):
            self.call({'action':'dispatch','project':p['id'],'task_id':t['id'],'expected_revision':p['revision'],'task_revision':t['revision']})
        self.assertEqual(self.call({'action':'task','project':p['id'],'task_id':t['id']})['status'],'blocked')
    def test_native_files_metadata_is_observed_not_trusted(self):
        p,t=self.reviewed();file=Path(p['path'])/'example.py';file.write_text('print(1)\n')
        # Actual native metadata variant used by the live Codex worker.
        self.native_change(p,t,"conn.execute(\"UPDATE task_runs SET metadata=? WHERE task_id=?\", (json.dumps({'files':['example.py','../escape','.argos-project']}), task))\nconn.commit()")
        t=self.call({'action':'task','project':p['id'],'task_id':t['id']})
        self.assertEqual([a['path'] for a in t['artifacts']],['example.py'])
    def test_empty_or_failing_tests_never_accepted(self):
        p,t=self.reviewed();verified=self.decision(p,t,'verify');self.assertFalse(verified['controller_evidence'][-1]['passed'])
        with self.assertRaises(PermissionError):self.decision(p,verified,'accept')


if __name__=='__main__':unittest.main(verbosity=2)
