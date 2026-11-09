"""Specialized capability admission and native persistence; disposable projects only."""
import json
from pathlib import Path
import unittest
from projects.qa import NativeProjectTests


class SpecializedNativeTests(NativeProjectTests):
    def test_specialized_native_snapshot_deduplication_and_restart(self):
        project=self.create();task=self.task(project,capability='diagram.architecture')
        self.assertEqual(task['id'],self.task(project,capability='diagram.architecture')['id'])
        updated=self.call({'action':'task_update','project':project['id'],'task_id':task['id'],'expected_revision':project['revision'],'task_revision':task['revision'],'goal':'Show the revised current native snapshot'})
        body=json.loads(updated['body'].split('\n',1)[1]);self.assertEqual(body['specialized']['id'],'diagram.architecture');self.assertEqual(body['native_snapshot']['project_id'],project['id'])
        self.broker=self.fresh()
        self.assertEqual(self.call({'action':'task','project':project['id'],'task_id':task['id']})['id'],task['id'])
        with self.assertRaises(ValueError):self.task(project,capability='diagram.architecture',kind='desktop')
        with self.assertRaises(PermissionError):self.task(project,capability='learning.learnharness')
        with self.assertRaises(ValueError):self.task(project,capability='unregistered')

    def test_catalog_and_scope_remain_separate(self):
        rows=self.call({'action':'catalog'})['capabilities']
        self.assertTrue(any(r['id']=='diagram.architecture' and r['available'] for r in rows))
        with self.assertRaises(PermissionError):self.call({'action':'task_create','project':'foreign','capability':'diagram.architecture','expected_revision':'fake','title':'escape','goal':'escape','verification':['escape']})


from projects.qa_lifecycle import LifecycleTests


class SpecializedMapVerificationTests(LifecycleTests):
    def test_workspace_hash_includes_other_task_files(self):
        self.config['project_map_enabled']=True;self.config_path.write_text(json.dumps(self.config));self.broker=self.fresh()
        p,t=self.reviewed();root=Path(p['path'])
        (root/'test_example.py').write_text('import unittest\nclass Check(unittest.TestCase):\n def test_one(self): self.assertEqual(2+2,4)\n')
        (root/'other-task.txt').write_text('Another task artifact')
        self.native_change(p,t,"conn.execute(\"UPDATE task_runs SET metadata=? WHERE task_id=?\",(json.dumps({'artifacts':['test_example.py']}),task))\nconn.commit()")
        t=self.call({'action':'task','project':p['id'],'task_id':t['id']});verified=self.decision(p,t,'verify')
        self.assertTrue(verified['controller_evidence'][-1]['passed'])
        self.assertTrue(self.call({'action':'map','project':p['id']})['tasks'][0]['verification_snapshot_current'])
        (root/'other-task.txt').write_text('Changed')
        self.assertFalse(self.call({'action':'map','project':p['id']})['tasks'][0]['verification_snapshot_current'])


def load_tests(loader,tests,pattern):
    return unittest.TestSuite(cls(name) for cls in [SpecializedNativeTests,SpecializedMapVerificationTests] for name in cls.__dict__ if name.startswith('test_'))


if __name__=='__main__':unittest.main(verbosity=2)
