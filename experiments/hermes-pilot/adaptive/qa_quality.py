"""Semantic scorer and measured profile boundaries, without inference downloads."""
import json
from pathlib import Path
import sys
import unittest
P=Path(__file__).resolve().parents[1];sys.path[:0]=[str(P),str(P/'ui-workbench')]
from adaptive.capabilities import reviewed_local,select
from adaptive.quality import score,CASES
class QualityTests(unittest.TestCase):
 def test_semantics_not_json(self):
  self.assertFalse(score({'items':['printing']},['tags'])['exact'])
  self.assertEqual(score({'items':['tags','cloud']},['tags','notes'])['hallucinations'],['cloud'])
  self.assertEqual(score({'items':['tags']},['tags','notes'])['completeness'],.5)
  self.assertFalse(score({'items':['tags','tags']},['tags'])['exact'])
 def test_measured_model_identity_and_no_router(self):
  profile=json.loads((P/'adaptive/quality-profiles.json').read_text());config={'local':{k:profile[k] for k in ['model','digest']}}
  self.assertTrue(reviewed_local(config)['profiles']['literal_items']['eligible'])
  for field in ['model','digest']:
   with self.assertRaises(PermissionError):reviewed_local({'local':{**config['local'],field:'unreviewed'}})
  self.assertEqual(select('items',{'format':'lines'}),'text.normalize')
  with self.assertRaises(ValueError):select('classify',{'text':'open app'})
  self.assertFalse(any(p['eligible'] for k,p in profile['profiles'].items() if k!='literal_items'))
 def test_representative_suite(self):
  self.assertEqual(len(CASES),18);self.assertEqual(len({c[0] for c in CASES}),7)
if __name__=='__main__':unittest.main(verbosity=2)
