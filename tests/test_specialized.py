import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

PILOT=Path(__file__).resolve().parents[1]/'experiments/hermes-pilot'
spec=importlib.util.spec_from_file_location('specialized_under_test',PILOT/'adaptive/specialized.py')
specialized=importlib.util.module_from_spec(spec);spec.loader.exec_module(specialized)


class SpecializedTests(unittest.TestCase):
    def test_sources_do_not_imply_executability(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            rows=specialized.catalog(root)
            self.assertTrue(all(not row['available'] for row in rows))
            self.assertEqual(rows[-1]['status'],'unsupported')
            with self.assertRaises(PermissionError):specialized.context('cad.parametric',root)
            with self.assertRaises(ValueError):specialized.context('arbitrary.shell',root)

    def test_validation_tampering_and_missing_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'anatomy';folder.mkdir();(folder/'SKILL.md').write_text('Reviewed')
            executable=root/'node';executable.write_bytes(b'fixture binary')
            record={'revision':specialized.SPECS['diagram.technical']['revision'],'validated':False,'required':['node'],
                    'commands':{'node':str(executable)},'files':specialized.digest_tree(folder),
                    'executables':{str(executable):hashlib.sha256(executable.read_bytes()).hexdigest()}}
            manifest=root/'anatomy.json';manifest.write_text(json.dumps(record))
            self.assertEqual(specialized.catalog(root)[1]['status'],'installed_unverified')
            record['validated']=True;manifest.write_text(json.dumps(record))
            self.assertEqual(specialized.context('diagram.technical',root)['id'],'diagram.technical')
            executable.write_bytes(b'changed')
            with self.assertRaises(PermissionError):specialized.context('diagram.technical',root)
            executable.write_bytes(b'fixture binary');(folder/'SKILL.md').write_text('changed instructions')
            with self.assertRaises(PermissionError):specialized.context('diagram.technical',root)
            executable.unlink();self.assertFalse(specialized.catalog(root)[1]['available'])

    def test_symlink_is_not_reviewed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'escape').symlink_to('/etc/passwd')
            with self.assertRaises(PermissionError):specialized.digest_tree(root)

    def test_validation_does_not_execute_or_bless_changed_sources(self):
        from unittest.mock import patch
        installer_spec=importlib.util.spec_from_file_location('validate_specialized_test',PILOT.parents[1]/'scripts/validate_specialized.py')
        validator=importlib.util.module_from_spec(installer_spec);installer_spec.loader.exec_module(validator)
        with tempfile.TemporaryDirectory() as temporary:
            pilot=Path(temporary)/'pilot';root=pilot/'tools/specialized';source=root/'anatomy';source.mkdir(parents=True)
            (source/'SKILL.md').write_text('reviewed');files=specialized.digest_tree(source)
            (source/'SKILL.md').write_text('modified after review')
            (root/'anatomy.json').write_text(json.dumps({'revision':specialized.SPECS['diagram.technical']['revision'],'files':files,'validated':False}))
            with patch.object(sys,'argv',['validate','diagram.technical','--pilot',str(pilot),'--evidence',str(Path(temporary)/'evidence')]),patch.object(validator,'run') as execute:
                self.assertEqual(validator.main(),1);execute.assert_not_called()
            self.assertFalse(json.loads((root/'anatomy.json').read_text())['validated'])


if __name__=='__main__':unittest.main()
