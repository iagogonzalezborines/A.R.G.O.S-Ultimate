"""Local STL/OBJ model catalogue backed by the Python standard library."""

from __future__ import annotations

import hashlib
import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Iterable


def _build_parser():
    parser = argparse.ArgumentParser(description="Catálogo local de modelos STL/OBJ")
    parser.add_argument("--db", required=True, help="ruta de la base SQLite")
    commands = parser.add_subparsers(dest="command", required=True)

    index_parser = commands.add_parser("index", help="indexar archivos STL/OBJ de una carpeta")
    index_parser.add_argument("folder", help="carpeta que se recorrerá recursivamente")

    tag_parser = commands.add_parser("tag", help="reemplazar las etiquetas de un modelo")
    tag_parser.add_argument("absolute_path", help="ruta absoluta de un modelo ya indexado")
    tag_parser.add_argument("tags", nargs="+", help="una o más etiquetas")

    note_parser = commands.add_parser("note", help="añadir una nota a un modelo")
    note_parser.add_argument("absolute_path", help="ruta absoluta de un modelo ya indexado")
    note_parser.add_argument("text", nargs="+", help="texto de la nota (se acepta entre comillas)")

    search_parser = commands.add_parser("search", help="buscar por nombre, etiquetas o notas")
    search_parser.add_argument("query", nargs="+", help="consulta (se acepta entre comillas)")
    return parser


def main(argv=None):
    """Run the command-line interface and return its process status."""
    args = _build_parser().parse_args(argv)
    library = ModelLibrary(args.db)
    try:
        if args.command == "index":
            print(library.index(args.folder))
        elif args.command == "tag":
            library.tag(args.absolute_path, args.tags)
        elif args.command == "note":
            library.note(args.absolute_path, " ".join(args.text))
        else:
            print(json.dumps(library.search(" ".join(args.query)), ensure_ascii=False))
    finally:
        library.close()
    return 0


class ModelLibrary:
    """Index local STL/OBJ files and persist tags and notes in SQLite."""

    def __init__(self, db_path):
        self.db_path = os.fspath(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS models (
                path TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                extension TEXT NOT NULL,
                size INTEGER NOT NULL,
                sha256 TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tags (
                model_path TEXT NOT NULL REFERENCES models(path) ON DELETE CASCADE,
                tag TEXT NOT NULL,
                PRIMARY KEY (model_path, tag)
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_path TEXT NOT NULL REFERENCES models(path) ON DELETE CASCADE,
                text TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS models_name_idx ON models(name COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS tags_tag_idx ON tags(tag COLLATE NOCASE);
            """
        )
        self._db.commit()

    @staticmethod
    def _absolute(path) -> str:
        return str(Path(path).expanduser().resolve())

    def index(self, folder):
        """Index supported files under *folder*. Return the number discovered."""
        root = Path(folder).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise NotADirectoryError(str(root))
        discovered = []
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs.sort()
            for filename in sorted(files):
                path = Path(directory) / filename
                if path.suffix.lower() not in {".stl", ".obj"} or not path.is_file():
                    continue
                digest = hashlib.sha256()
                with path.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
                stat = path.stat()
                discovered.append((str(path.resolve()), path.name, path.suffix[1:].lower(), stat.st_size, digest.hexdigest()))
        with self._db:
            self._db.executemany(
                "INSERT INTO models(path,name,extension,size,sha256) VALUES(?,?,?,?,?) "
                "ON CONFLICT(path) DO UPDATE SET name=excluded.name, extension=excluded.extension, "
                "size=excluded.size, sha256=excluded.sha256",
                discovered,
            )
        return len(discovered)

    def tag(self, absolute_path, tags):
        """Replace a model's tags with the supplied iterable of tag strings."""
        path = self._absolute(absolute_path)
        if isinstance(tags, str):
            tags = [tags]
        clean = sorted({str(tag).strip() for tag in tags if str(tag).strip()}, key=str.casefold)
        with self._db:
            if self._db.execute("SELECT 1 FROM models WHERE path=?", (path,)).fetchone() is None:
                raise KeyError(path)
            self._db.execute("DELETE FROM tags WHERE model_path=?", (path,))
            self._db.executemany("INSERT INTO tags(model_path,tag) VALUES(?,?)", [(path, t) for t in clean])

    def note(self, absolute_path, text):
        """Append a note to an indexed model."""
        path = self._absolute(absolute_path)
        if not isinstance(text, str):
            raise TypeError("note text must be a string")
        with self._db:
            if self._db.execute("SELECT 1 FROM models WHERE path=?", (path,)).fetchone() is None:
                raise KeyError(path)
            self._db.execute("INSERT INTO notes(model_path,text) VALUES(?,?)", (path, text))

    def search(self, query):
        """Search case-insensitively across filename, tags, and notes."""
        term = str(query).strip()
        pattern = f"%{term}%"
        rows = self._db.execute(
            """SELECT DISTINCT m.path,m.name,m.extension,m.size,m.sha256
               FROM models m LEFT JOIN tags t ON t.model_path=m.path
               LEFT JOIN notes n ON n.model_path=m.path
               WHERE m.name LIKE ? COLLATE NOCASE OR t.tag LIKE ? COLLATE NOCASE
                  OR n.text LIKE ? COLLATE NOCASE
               ORDER BY m.name COLLATE NOCASE,m.path""",
            (pattern, pattern, pattern),
        ).fetchall()
        result = []
        for row in rows:
            model = dict(row)
            model["tags"] = [r[0] for r in self._db.execute(
                "SELECT tag FROM tags WHERE model_path=? ORDER BY tag COLLATE NOCASE", (row["path"],)
            )]
            model["notes"] = [r[0] for r in self._db.execute(
                "SELECT text FROM notes WHERE model_path=? ORDER BY id", (row["path"],)
            )]
            result.append(model)
        return result

    def close(self):
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


if __name__ == "__main__":
    raise SystemExit(main())
