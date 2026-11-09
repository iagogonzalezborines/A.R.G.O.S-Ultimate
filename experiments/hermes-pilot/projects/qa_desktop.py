"""Native artifact security/recovery regressions using disposable projects only."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

P=Path(__file__).resolve().parents[1];sys.path[:0]=[str(P/'projects'),str(P/'ui-workbench'),str(P)]
from qa import NativeProjectTests


class DesktopArtifactTests(NativeProjectTests):
    def prepare(self):
        project=self.create();task=self.task(project,kind='desktop',title='Document requirements')
        bound={'project':project['id'],'task_id':task['id']};context=self.native({'operation':'context',**bound})
        session='0123456789abcdef01234567'
        workspace=self.native({'operation':'session',**self.bound(context),'session_id':session,'profile':'meld-editor','profile_revision':'a'*64,'imports':[], 'seed':{'document.md':''},'output_directory':'docs'})
        file=Path(workspace['workspace'])/'document.md';file.write_text('STL and OBJ; preserve originals.\n')
        return project,task,session,file

    def native(self,args,authorized=True):return self.broker.projects.native({'action':'desktop_artifacts',**args},authorized=authorized)
    def bound(self,ctx):return {'project':ctx['project']['id'],'task_id':ctx['task']['id'],'expected_revision':ctx['project']['revision'],'task_revision':ctx['task']['revision']}
    def export_review(self,p,t,s,f,destination='docs/requirements.md'):
        ctx=self.native({'operation':'context','project':p['id'],'task_id':t['id']});a={'session_id':s,'path':'document.md','sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'destination':destination}
        review=self.native({'operation':'prepare_export',**self.bound(ctx),**a})
        return {'operation':'export',**self.bound(ctx),**a,**{k:review[k] for k in ('export_id','before','parent_identity','task_revision')}}

    def test_actual_native_export_duplicate_and_restart(self):
        p,t,s,f=self.prepare();request=self.export_review(p,t,s,f);result=self.native(request)
        self.assertEqual(Path(result['path']).read_bytes(),f.read_bytes())
        self.broker=self.fresh();ctx=self.native({'operation':'context','project':p['id'],'task_id':t['id']})
        self.assertEqual(len(ctx['exports']),1);self.assertEqual(ctx['task']['artifacts'][0]['path'],'docs/requirements.md')
        duplicate=self.native({'operation':'prepare_export',**self.bound(ctx),**{k:request[k] for k in ('session_id','path','sha256','destination')}})
        self.assertEqual(duplicate['status'],'already_exported')
        self.assertEqual(len(self.native({'operation':'context','project':p['id'],'task_id':t['id']})['exports']),1)

    def test_model_cannot_forge_controller_operation_or_dispatch_desktop(self):
        p,t,s,f=self.prepare()
        with self.assertRaises(PermissionError):self.native({'operation':'context','project':p['id'],'task_id':t['id']},False)
        with self.assertRaises(PermissionError):self.call({'action':'dispatch','project':p['id'],'task_id':t['id'],'expected_revision':p['revision'],'task_revision':self.call({'action':'task','project':p['id'],'task_id':t['id']})['revision']})

    def test_source_change_stale_destination_and_parent_identity(self):
        p,t,s,f=self.prepare();request=self.export_review(p,t,s,f);f.write_text('Changed artifact')
        with self.assertRaises(PermissionError):self.native(request)
        request=self.export_review(p,t,s,f);target=Path(p['path'])/'docs/requirements.md';target.write_text('External file')
        with self.assertRaises(PermissionError):self.native(request)
        self.assertEqual(target.read_text(),'External file')
        request=self.export_review(p,t,s,f);folder=target.parent;folder.rename(folder.with_name('old-docs'));folder.mkdir();target.write_text('External file')
        with self.assertRaises(PermissionError):self.native(request)
        self.assertEqual(target.read_text(),'External file')

    def test_unapproved_destination_and_cross_project_access(self):
        p,t,s,f=self.prepare()
        for dest in ('../escape.md','outside.md','docs/../escape.md','docs/script.sh'):
            with self.assertRaises((PermissionError,ValueError)):self.export_review(p,t,s,f,dest)
        idea={**self.idea,'name':'Another','slug':'another','brief':{**self.idea['brief'],'aliases':['another desktop project']}};other=self.create(idea)
        with self.assertRaises(PermissionError):self.native({'operation':'context','project':other['id'],'task_id':t['id']})

    def test_links_credentials_binary_and_empty_documents_blocked(self):
        p,t,s,f=self.prepare();original=f.read_text();outside=self.root/'outside.md';outside.write_text('Outside')
        f.unlink();f.symlink_to(outside)
        with self.assertRaises((PermissionError,ValueError)):self.export_review(p,t,s,f)
        f.unlink()
        for content in ('password=synthetic-test-secret','binary\x00data',''):
            f.write_text(content)
            with self.assertRaises(PermissionError):self.export_review(p,t,s,f)
        f.write_text(original);other=f.with_name('linked.md');__import__('os').link(f,other)
        with self.assertRaises(PermissionError):self.export_review(p,t,s,f)

    def test_recovery_after_write_before_receipt_never_replays(self):
        p,t,s,f=self.prepare();request=self.export_review(p,t,s,f)
        # Inject a crash boundary in the native comment API after real atomic Files
        # publication. No fake export data or secondary project store.
        code="""import json,sys
from pathlib import Path
from pilot import environment
from projects.native import Adapter
import projects.desktop as module
original=module.record
def crash(conn,task,config,kind,**fields):
 if kind=='desktop_exported':raise RuntimeError('simulated crash after publication')
 return original(conn,task,config,kind,**fields)
module.record=crash
try:Adapter(json.loads(Path(sys.argv[1]).read_text())).request(json.loads(sys.argv[2]),True)
except RuntimeError:pass
"""
        import subprocess
        from pilot import environment
        env=environment();env.update(HERMES_HOME=self.config['project_state'],HERMES_KANBAN_HOME=self.config['project_state'],PYTHONPATH=str(P)+':'+str(P/'source'))
        result=subprocess.run([str(P/'env/bin/python'),'-c',code,str(self.config_path),json.dumps({'action':'desktop_artifacts',**request})],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        target=Path(p['path'])/'docs/requirements.md';self.assertEqual(target.read_bytes(),f.read_bytes());before=target.stat().st_mtime_ns
        self.broker=self.fresh();ctx=self.native({'operation':'context','project':p['id'],'task_id':t['id']})
        self.assertEqual(len(ctx['exports']),1);self.assertTrue(ctx['exports'][0]['recovered']);self.assertEqual(target.stat().st_mtime_ns,before)

    def test_valid_overwrite_records_latest_receipt_and_unsafe_import_has_no_effect(self):
        p,t,s,f=self.prepare();first=self.native(self.export_review(p,t,s,f))
        f.write_text('Reviewed second document.\n');second=self.native(self.export_review(p,t,s,f))
        self.assertEqual(Path(second['path']).read_bytes(),f.read_bytes())
        ctx=self.native({'operation':'context','project':p['id'],'task_id':t['id']})
        self.assertEqual(len(ctx['exports']),2)
        self.assertEqual(ctx['task']['artifacts'][0]['export_id'],second['receipt']['export_id'])
        self.assertIn('current hash matches',ctx['task']['artifacts'][0]['verification'])
        other='abcdef0123456789abcdef01';folder=Path(p['path'])/'unapproved-copy'
        content='password=synthetic-only'
        with self.assertRaises(PermissionError):self.native({'operation':'session',**self.bound(ctx),'session_id':other,'profile':'meld-editor','profile_revision':'a'*64,'seed':{},'imports':[{'name':'copy.md','text':content,'sha256':hashlib.sha256(content.encode()).hexdigest(),'source':str(self.root/'synthetic.md')}],'output_directory':'unapproved-copy'})
        self.assertFalse(folder.exists());self.assertFalse((Path(self.config['project_state'])/'desktop-artifacts'/other).exists())

    def test_new_revision_does_not_admit_stale_brief(self):
        p,t,s,f=self.prepare()
        updated=self.call({'action':'update','project':p['id'],'expected_revision':p['revision'],'brief':{**p['brief'],'requirements':['New requirements']}})
        ctx=self.native({'operation':'context','project':p['id'],'task_id':t['id']})
        self.assertEqual(ctx['project']['revision'],updated['revision'])
        for operation in ('resume','prepare_export'):
            with self.assertRaises(ValueError):self.native({'operation':operation,**self.bound(ctx),'session_id':s,'path':'document.md','sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'destination':'docs/requirements.md'})
        self.assertTrue(self.native({'operation':'scan',**self.bound(ctx),'session_id':s})['artifacts'])

    def test_native_dependencies_guard_desktop_admission(self):
        p=self.create();parent=self.task(p,kind='decision',title='Choose document scope')
        task=self.task(p,kind='desktop',title='Dependent document',parents=[parent['id']]);ctx=self.native({'operation':'context','project':p['id'],'task_id':task['id']})
        with self.assertRaises(PermissionError):self.native({'operation':'session',**self.bound(ctx),'session_id':'0123456789abcdef01234567','profile':'meld-editor','profile_revision':'a'*64,'seed':{},'imports':[],'output_directory':'docs'})
        self.assertFalse((Path(p['path'])/'docs').exists())

    def test_replaced_workspace_and_stale_project_revision(self):
        p,t,s,f=self.prepare();request=self.export_review(p,t,s,f)
        self.call({'action':'update','project':p['id'],'expected_revision':p['revision'],'brief':{**p['brief'],'requirements':['New requirements']}})
        with self.assertRaises(ValueError):self.native(request)
        work=f.parent;work.rename(work.with_name('old-work'));work.mkdir();(work/'document.md').write_text('replacement')
        ctx=self.native({'operation':'context','project':p['id'],'task_id':t['id']})
        with self.assertRaises(PermissionError):self.native({'operation':'scan',**self.bound(ctx),'session_id':s})

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(DesktopArtifactTests)
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
