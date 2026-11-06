"""Actual native projection, boundaries and decision state, no worker/provider mocks."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).parent))
from qa import NativeProjectTests

class MapTests(NativeProjectTests):
 def setUp(self):
  super().setUp();self.config['project_map_enabled']=True;self.config_path.write_text(json.dumps(self.config));self.broker=self.fresh()
 def test_map_decision_and_scope(self):
  p=self.create();t=self.task(p,kind='decision',title='Choose indexed formats')
  m=self.call({'action':'map','project':p['id']});self.assertEqual(m['tasks'][0]['state'],'decision')
  with self.assertRaises(PermissionError):self.call({'action':'dispatch','project':p['id'],'task_id':t['id'],'expected_revision':p['revision'],'task_revision':t['revision']})
  a={'action':'map_action','operation':'decide','reason':'STL and OBJ only','project':p['id'],'task_id':t['id'],'expected_revision':p['revision'],'task_revision':t['revision']}
  with self.assertRaises(PermissionError):self.call(a)
  decided=self.call(a,user=True);self.assertEqual(decided['status'],'done');self.assertEqual(decided['controller_evidence'][-1]['answer'],'STL and OBJ only')
  with self.assertRaises(ValueError):self.call(a,user=True)
  other=self.create({**self.idea,'name':'Other','slug':'other','brief':{'objective':'Other'}})
  with self.assertRaises(PermissionError):self.call({**a,'project':other['id'],'expected_revision':other['revision']},user=True)
  self.broker=self.fresh();self.assertEqual(self.call({'action':'map','project':'models'})['tasks'][0]['status'],'done')
 def test_empty_auxiliary_board(self):
  p=self.create();self.config['adaptive_enabled']=True;self.config_path.write_text(json.dumps(self.config));self.broker=self.fresh()
  self.assertEqual(self.call({'action':'map','project':p['id']})['tasks'],[])
 def test_map_unstarted_edit_and_artifact_scope(self):
  p=self.create();t=self.task(p,kind='decision')
  t=self.call({'action':'task_update','project':p['id'],'task_id':t['id'],'expected_revision':p['revision'],'task_revision':t['revision'],'goal':'Choose formats'})
  self.assertEqual(self.call({'action':'map','project':p['id']})['tasks'][0]['kind'],'decision')
  for path in ['../installation.json','/etc/passwd','not-observed.txt']:
   with self.assertRaises(PermissionError):self.call({'action':'artifact','project':p['id'],'task_id':t['id'],'path':path})
  self.config['project_map_enabled']=False;self.config_path.write_text(json.dumps(self.config));self.broker=self.fresh()
  with self.assertRaises(PermissionError):self.call({'action':'map','project':p['id']})

def load_tests(loader,tests,pattern):
 return unittest.TestSuite(MapTests(name) for name in MapTests.__dict__ if name.startswith('test_'))
if __name__=='__main__':unittest.main(verbosity=2)
