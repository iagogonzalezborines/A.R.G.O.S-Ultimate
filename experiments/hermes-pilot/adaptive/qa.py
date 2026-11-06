"""Integration checks use real native SQLite and subprocesses, never speakers or real projects."""
import json
import subprocess
from pathlib import Path
import sys
import tempfile
import time
import unittest
P=Path(__file__).resolve().parents[1];sys.path[:0]=[str(P),str(P/'ui-workbench')]
from runtime.workspace_broker import WorkspaceBroker,Files
from runtime.projects import Projects
from adaptive.workflow import validate
from adaptive.local import Local,validate_items
from pilot import environment


class AdaptiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='argos-adaptive-qa-');self.root=Path(self.tmp.name)
        (self.root/'repos').mkdir();(self.root/'native').mkdir()
        self.config={'projects_enabled':True,'adaptive_enabled':True,'pilot_root':str(P),'operational_root':str(self.root/'protected'),
            'project_roots':[str(self.root/'repos')],'project_state':str(self.root/'native'),
            'adaptive':{'local':{'url':'http://127.0.0.1:1','model':'absent','digest':'absent'},'min_available_bytes':0}}
        self.file=self.root/'installation.json';self.save()
        (self.root/'native/config.yaml').write_text(json.dumps({'kanban':{'review_dispatch':False,'dispatch_in_gateway':False,'max_in_progress':1}}))
        self.fresh()
        self.project=self.create('first')
    def save(self):self.file.write_text(json.dumps(self.config))
    def fresh(self):
        self.broker=WorkspaceBroker(lambda _:None,lambda x:x,files=Files({'QA':self.root}),socket_path=self.root/'broker.sock')
        self.broker.projects=Projects(lambda _:None,config_path=self.file)
    def create(self,name):
        p=self.broker.projects.request({'action':'propose','name':name,'slug':name,'brief':{'objective':'Disposable test'}})
        return self.broker.projects.request({'action':'confirm','proposal_id':p['id'],'approve':True},user=True)['project']
    def call(self,operation,**args):
        return self.broker.request({'tool':'adaptive','arguments':{'operation':operation,'project':self.project['id'],
            'expected_revision':self.project['revision'],**args}})
    def settled(self):
        for _ in range(70):
            rows=self.call('status')['tasks']
            if all(t['status'] not in {'ready','running','todo'} for t in rows):return rows
            time.sleep(.1)
        self.fail('Native tasks did not settle')
    def tearDown(self):
        # All test jobs are bounded functions; wait before deleting their native state.
        self.tmp.cleanup()
    def test_native_execution_dedup_restart_and_no_replay(self):
        args={'capability':'items','payload':{'format':'lines','text':'STL\nOBJ\nSTL'}}
        first=self.call('submit',**args);rows=self.settled()
        self.assertEqual(rows[0]['status'],'done')
        self.assertEqual(rows[0]['runs'][0]['metadata']['result']['items'],['STL','OBJ'])
        self.fresh();self.assertEqual(self.call('submit',**args)['id'],first['id'])
        self.call('tick');self.assertEqual(len(self.call('status')['tasks'][0]['runs']),1)
    def test_workflow_dependencies_actual_canvas(self):
        (Path(self.project['path'])/'fixture.stl').write_text('synthetic')
        nodes=[{'id':'types','title':'Count types','capability':'files.types','parents':['scan']},
               {'id':'scan','title':'Inventory','capability':'files.inventory','parents':[]}]
        result=self.call('workflow',nodes=nodes);rows=self.settled()
        self.assertEqual(len(rows),2);self.assertTrue(all(t['status']=='done' for t in rows))
        types=next(t for t in rows if t['capability']=='files.types')
        self.assertEqual(types['runs'][0]['metadata']['result'],{'counts':{'.stl':1}})
        canvas=self.call('canvas');self.assertEqual(len(canvas['nodes']),2);self.assertEqual(len(canvas['edges']),1)
        self.assertEqual(self.call('workflow',nodes=nodes)['tasks'],result['tasks'])
    def test_resource_queue_cancellation_and_stale_revision(self):
        self.config['adaptive']['min_available_bytes']=10**18;self.save();self.fresh()
        task=self.call('submit',capability='text.normalize',payload={'text':'queued'})
        self.assertEqual(task['admission'],'waiting_for_memory');self.assertEqual(task['runs'],[])
        with self.assertRaises(ValueError):self.call('cancel',task_id=task['id'],task_revision='stale')
        state=self.call('cancel',task_id=task['id'],task_revision=task['revision']);self.assertEqual(state['status'],'archived')
        self.config['adaptive']['min_available_bytes']=0;self.save();self.fresh();self.call('tick')
        self.assertEqual(self.call('status')['tasks'],[]) # native list omits archived cards
    def test_access_feature_gate_and_missing_model(self):
        other=self.create('second')
        task=self.call('submit',capability='text.normalize',payload={'text':'test'});self.settled()
        with self.assertRaises(PermissionError):self.call('cancel',project=other['id'],expected_revision=other['revision'],task_id=task['id'],task_revision=task['revision'])
        with self.assertRaises(ValueError):self.call('submit',expected_revision='old',capability='text.normalize',payload={'text':'test'})
        with self.assertRaises(ValueError):self.call('submit',capability='shell',payload={})
        model=self.call('submit',capability='local.extract',payload={'text':'STL and OBJ'});rows=self.settled()
        self.assertEqual(next(t for t in rows if t['id']==model['id'])['status'],'blocked')
        self.config['adaptive_enabled']=False;self.save();self.fresh()
        with self.assertRaises(PermissionError):self.call('catalog')
    def test_reject_unsafe_native_review_dispatch(self):
        (self.root/'native/config.yaml').write_text(json.dumps({'kanban':{'review_dispatch':True}}))
        with self.assertRaises(PermissionError):self.call('submit',capability='text.normalize',payload={'text':'never start'})
        self.assertFalse((self.root/'native/kanban/boards/argos-capabilities').exists())
    def test_validation_before_execution(self):
        for value in [{'items':['password=synthetic-secret']},{'items':['ok'],'command':'shell'},{'items':'bad'}]:
            with self.assertRaises((ValueError,PermissionError)):validate_items(value)
        with self.assertRaises(PermissionError):Local({'url':'https://external.example','model':'x','digest':'x'})
        with self.assertRaises(ValueError):validate([{'id':'x','title':'x','capability':'files.inventory','parents':['x']}])
        with self.assertRaises(PermissionError):self.call('workflow',nodes=[
            {'id':'ok','title':'First','capability':'files.inventory','parents':[]},
            {'id':'bad','title':'Invalid','capability':'local.extract','parents':['ok'],'payload':{'text':'password=synthetic-secret'}}])
        self.assertEqual(self.call('status')['tasks'],[])
        with self.assertRaises(ValueError):self.call('submit',capability='items',payload={'text':'ambiguous'})
    def test_interrupted_native_attempt_is_not_replayed(self):
        self.config['adaptive']['min_available_bytes']=10**18;self.save();self.fresh()
        task=self.call('submit',capability='text.normalize',payload={'text':'interrupted'})
        env=environment();env.update(HERMES_HOME=str(self.root/'native'),HERMES_KANBAN_HOME=str(self.root/'native'))
        # Native APIs create and reclaim a real attempt without executing any effect.
        code='''import sys
from hermes_cli import kanban_db as kb
from hermes_cli.kanban_db_connect import connect_closing
with connect_closing(board='argos-capabilities') as conn:
 assert kb.claim_task(conn,sys.argv[1])
 assert kb.reclaim_task(conn,sys.argv[1],reason='test interrupted before worker spawn')
'''
        subprocess.run([str(P/'env/bin/python'),'-c',code,task['id']],env=env,check=True,capture_output=True,timeout=10)
        self.config['adaptive']['min_available_bytes']=0;self.save();self.fresh();self.call('tick')
        row=self.call('status')['tasks'][0]
        self.assertEqual(row['status'],'blocked')
        # Hermes records the explicit park as a zero-duration administrative run.
        self.assertEqual(len(row['runs']),2);self.assertEqual(row['runs'][-1]['outcome'],'blocked')
        self.assertEqual(row['runs'][-1]['started_at'],row['runs'][-1]['ended_at'])
        self.assertNotIn('result',row['runs'][-1]['metadata'])
        self.call('tick');self.assertEqual(self.call('status')['tasks'][0]['runs'],row['runs'])


if __name__=='__main__':unittest.main(verbosity=2)
