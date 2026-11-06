"""Offline integration checks through the actual Broker and native Hermes databases."""
import concurrent.futures
import json
from pathlib import Path
import sys
import tempfile
import unittest

PILOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PILOT), str(PILOT/'ui-workbench')]
from runtime.workspace_broker import WorkspaceBroker, Files
from runtime.projects import Projects


class NativeProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='argos-project-test-')
        self.root = Path(self.temporary.name)
        self.config = {'projects_enabled':True, 'pilot_root':str(PILOT),
                       'operational_root':str(self.root/'operational'),
                       'project_roots':[str(self.root/'repositories')], 'project_state':str(self.root/'native')}
        (self.root/'repositories').mkdir()
        (self.root/'operational').mkdir()
        self.config_path = self.root/'installation.json'
        self.config_path.write_text(json.dumps(self.config))
        self.events = []
        self.broker = self.fresh()
        self.idea = {'action':'propose','name':'Model Library','slug':'model-library',
                     'brief':{'objective':'Manage model file references', 'requirements':['Never move the original library'],
                              'decisions':['Use read-only indexing'], 'verification':['Records survive restart'], 'aliases':['models']}}

    def fresh(self):
        broker = WorkspaceBroker(self.events.append, lambda value:value, files=Files({'QA':self.root}),socket_path=self.root/'broker.sock')
        broker.projects = Projects(lambda intent:broker.intent(intent,wait=False),config_path=self.config_path)
        return broker

    def call(self, args, user=False):
        return self.broker.request({'tool':'projects','arguments':args},user=user)

    def create(self, idea=None):
        pending = self.call(idea or self.idea)
        if pending.get('project'):return pending['project']
        result = self.call({'action':'confirm','proposal_id':pending['id'],'approve':True},user=True)
        return result['project']

    def task(self, project, **values):
        return self.call({'action':'task_create','project':project['id'],'expected_revision':project['revision'],
                          'title':'Index fixtures','goal':'Implement a bounded fixture index',
                          'verification':['Run the fixture test'],**values})

    def tearDown(self):
        self.temporary.cleanup()

    def test_scope_review_and_restart_resolution(self):
        pending = self.call(self.idea)
        self.assertFalse((self.root/'repositories/model-library').exists())
        with self.assertRaises(PermissionError):
            self.call({'action':'confirm','proposal_id':pending['id'],'approve':True})
        project = self.call({'action':'confirm','proposal_id':pending['id'],'approve':True},user=True)['project']
        self.broker = self.fresh()
        resolved = self.call({'action':'resolve','project':'models'})
        self.assertEqual(project,resolved)
        self.assertEqual(resolved['brief']['decisions'],['Use read-only indexing'])
        self.assertEqual(self.call({'action':'resolve'})['id'],project['id'])
        self.assertTrue((self.root/'native/projects.db').is_file())
        with self.assertRaises(ValueError):
            self.call({'action':'confirm','proposal_id':pending['id'],'approve':True},user=True)

    def test_requirements_cas_and_tasks_cannot_use_old_brief(self):
        project = self.create()
        task = self.task(project)
        unchanged = self.call({'action':'update','project':project['id'],'expected_revision':project['revision'],'brief':project['brief']})
        self.assertEqual(unchanged['revision'],project['revision'])
        updated = self.call({'action':'update','project':project['id'],'expected_revision':project['revision'],
                'brief':{**project['brief'],'requirements':['Preserve originals','Allow tags']}})
        with self.assertRaisesRegex(ValueError,'Stale'):
            self.call({'action':'update','project':project['id'],'expected_revision':project['revision'],'brief':project['brief']})
        with self.assertRaisesRegex(ValueError,'older brief'):
            self.call({'action':'dispatch','project':project['id'],'task_id':task['id'],
                       'expected_revision':updated['revision'],'task_revision':task['revision']})
        self.assertEqual(self.call({'action':'task','project':project['id'],'task_id':task['id']})['runs'],[])

    def test_concurrent_duplicates_and_native_dependencies(self):
        project = self.create()
        self.assertEqual(self.create()['id'],project['id'])
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            tasks = list(pool.map(lambda _:self.task(project), range(4)))
        self.assertEqual(len({t['id'] for t in tasks}),1)
        parent = tasks[0]
        child = self.task(project,title='Follow-up',parents=[parent['id']])
        self.assertEqual(child['parents'],[parent['id']])
        waiting = self.call({'action':'dispatch','project':project['id'],'task_id':child['id'],
                           'expected_revision':project['revision'],'task_revision':child['revision']})
        self.assertEqual(waiting['dispatch'],'waiting_for_dependencies')
        self.broker = self.fresh()
        self.assertEqual(len(self.call({'action':'tasks','project':project['id']})['tasks']),2)
        self.assertEqual(self.call({'action':'activity'})['tasks'],[])

    def test_unauthorized_paths_aliases_tasks_and_replaced_directory(self):
        for path in [self.root/'outside',self.root/'operational',PILOT]:
            with self.assertRaises(PermissionError):
                self.call({**self.idea,'path':str(path)})
        (self.root/'repositories/link').symlink_to(self.root/'operational',target_is_directory=True)
        with self.assertRaises(PermissionError):
            self.call({**self.idea,'path':str(self.root/'repositories/link/escape')})
        project = self.create()
        first = self.task(project)
        other = self.create({**self.idea,'name':'Other','slug':'other','brief':{'objective':'Other project'}})
        with self.assertRaises(PermissionError):
            self.call({'action':'task','project':other['id'],'task_id':first['id']})
        with self.assertRaises(ValueError):
            self.call({'action':'update','project':other['id'],'expected_revision':other['revision'],
                       'brief':{'objective':'Other project','aliases':['models']}})
        nested = self.call({**self.idea,'name':'Nested','slug':'nested','path':project['path']+'/nested',
                           'brief':{'objective':'Nested'}})
        with self.assertRaises(PermissionError):
            self.call({'action':'confirm','proposal_id':nested['id'],'approve':True},user=True)
        Path(project['path']).rename(project['path']+'-old')
        Path(project['path']).mkdir()
        with self.assertRaises(PermissionError):
            self.call({'action':'resolve','project':project['id']})

    def test_partial_provisioning_recovers_without_duplicate_or_overwrite(self):
        # Force a native board provisioning error after the project row/folder exist.
        boards = self.root/'native/kanban/boards'
        boards.parent.mkdir(parents=True)
        boards.write_text('synthetic obstruction')
        pending = self.call(self.idea)
        try:
            with self.assertRaises(ValueError):
                self.call({'action':'confirm','proposal_id':pending['id'],'approve':True},user=True)
        finally:
            boards.unlink()
        project = self.call({'action':'confirm','proposal_id':pending['id'],'approve':True},user=True)['project']
        marker = Path(project['path'])/'.argos-project'
        before = marker.stat().st_mtime_ns
        self.assertEqual(self.create()['id'],project['id'])
        self.assertEqual(marker.stat().st_mtime_ns,before)
        self.assertEqual(len(self.call({'action':'list'})['projects']),1)

    def test_task_revision_dependency_edits_and_cycles_use_native_records(self):
        project = self.create()
        first, second = self.task(project), self.task(project,title='Follow-up')
        args = {'action':'dependency','project':project['id'],'expected_revision':project['revision'],
                'task_id':second['id'],'task_revision':second['revision'],'parent_id':first['id'],'operation':'link'}
        linked = self.call(args)
        self.assertEqual(linked['parents'],[first['id']])
        with self.assertRaisesRegex(ValueError,'Stale'):
            self.call({**args,'operation':'unlink'})
        with self.assertRaisesRegex(ValueError,'cycle'):
            self.call({**args,'task_id':first['id'],'task_revision':first['revision'],'parent_id':second['id']})
        unlinked = self.call({**args,'task_revision':linked['revision'],'operation':'unlink'})
        self.assertEqual(unlinked['parents'],[])
        revised = self.call({'action':'task_update','project':project['id'],'expected_revision':project['revision'],
                            'task_id':second['id'],'task_revision':unlinked['revision'],'title':'Revised follow-up'})
        self.assertEqual(revised['title'],'Revised follow-up')
        self.assertNotEqual(revised['revision'],unlinked['revision'])
        with self.assertRaisesRegex(ValueError,'Stale'):
            self.call({'action':'task_update','project':project['id'],'expected_revision':project['revision'],
                       'task_id':second['id'],'task_revision':unlinked['revision'],'title':'Obsolete edit'})

    def test_feature_gate_and_approval_cannot_be_forged(self):
        config = {**self.config,'projects_enabled':False}
        self.config_path.write_text(json.dumps(config));self.broker=self.fresh()
        self.assertEqual(self.call({'action':'availability'}),{'enabled':False})
        with self.assertRaises(PermissionError):self.call(self.idea)
        self.config_path.write_text(json.dumps(self.config));self.broker=self.fresh()
        with self.assertRaises(PermissionError):self.call({**self.idea,'action':'create'})
        with self.assertRaises(ValueError):self.call({**self.idea,'authorized':True})
        with self.assertRaises(PermissionError):
            self.call({**self.idea,'brief':{'objective':'password=synthetic-sensitive-value'}})


if __name__ == '__main__':
    unittest.main(verbosity=2)
