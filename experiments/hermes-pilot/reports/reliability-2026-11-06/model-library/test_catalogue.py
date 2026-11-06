"""Standard-library tests: run with python3 -m unittest -v."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from catalogue import ModelLibrary


class ModelLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.models = self.root / "models"
        self.models.mkdir()
        (self.models / "Cube.STL").write_bytes(b"solid cube\nendsolid cube\n")
        (self.models / "nested").mkdir()
        (self.models / "nested" / "bracket.obj").write_text("v 0 0 0\nf 1 1 1\n", encoding="utf-8")
        (self.models / "ignore.3mf").write_bytes(b"not indexed")
        self.db = self.root / "catalogue.sqlite"
        self.lib = ModelLibrary(self.db)

    def tearDown(self):
        self.lib.close()
        self.tmp.cleanup()

    def test_indexes_stl_and_obj_idempotently_without_changing_sources(self):
        original = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.models.rglob("*") if p.is_file()}
        self.assertEqual(self.lib.index(self.models), 2)
        self.assertEqual(self.lib.index(self.models), 2)
        matches = self.lib.search("")
        self.assertEqual(len(matches), 2)
        self.assertEqual({m["extension"] for m in matches}, {"stl", "obj"})
        self.assertEqual(original, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in original})

    def test_searches_filename_tags_and_notes(self):
        self.lib.index(self.models)
        cube = str((self.models / "Cube.STL").resolve())
        self.lib.tag(cube, ["Mechanical", "prototype"])
        self.lib.note(cube, "print slowly with supports")
        for query in ("cube", "MECHANICAL", "supports"):
            found = self.lib.search(query)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["path"], cube)
            self.assertEqual(found[0]["tags"], ["Mechanical", "prototype"])
            self.assertEqual(found[0]["notes"], ["print slowly with supports"])

    def test_metadata_survives_close_and_reopen(self):
        self.lib.index(self.models)
        obj = str((self.models / "nested" / "bracket.obj").resolve())
        self.lib.tag(obj, ["hardware"])
        self.lib.note(obj, "M4 mount")
        self.lib.close()
        self.lib = ModelLibrary(self.db)
        found = self.lib.search("M4")
        self.assertEqual(found[0]["tags"], ["hardware"])
        self.assertEqual(found[0]["notes"], ["M4 mount"])

    def test_rejects_unknown_model_for_metadata(self):
        with self.assertRaises(KeyError):
            self.lib.tag(self.models / "missing.stl", ["x"])
        with self.assertRaises(KeyError):
            self.lib.note(self.models / "missing.obj", "x")


class CatalogueCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.models = self.root / "models"
        self.models.mkdir()
        self.model = self.models / "Cube.stl"
        self.model.write_text("synthetic STL", encoding="utf-8")
        self.db = self.root / "cli.sqlite"
        self.script = Path(__file__).with_name("catalogue.py")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(self.script), "--db", str(self.db), *map(str, args)],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
        )

    def test_index_tag_note_and_search_commands(self):
        indexed = self.run_cli("index", self.models)
        self.assertEqual(indexed.stdout.strip(), "1")
        self.run_cli("tag", self.model.resolve(), "prototype", "bracket")
        self.run_cli("note", self.model.resolve(), "print with supports")

        result = self.run_cli("search", "supports")
        found = json.loads(result.stdout)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["path"], str(self.model.resolve()))
        self.assertEqual(found[0]["tags"], ["bracket", "prototype"])
        self.assertEqual(found[0]["notes"], ["print with supports"])

    def test_search_outputs_empty_json_array_when_unmatched(self):
        self.run_cli("index", self.models)
        result = self.run_cli("search", "absent")
        self.assertEqual(json.loads(result.stdout), [])


if __name__ == "__main__":
    unittest.main()
