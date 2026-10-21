import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

from .models import ArgosError, Status
from .security import public_text, safe_data


TRANSITIONS = {
    Status.QUEUED: {Status.RUNNING, Status.CANCELLED, Status.INTERRUPTED},
    Status.RUNNING: {Status.WAITING_INPUT, Status.WAITING_APPROVAL, Status.BLOCKED,
                     Status.COMPLETED, Status.FAILED, Status.CANCELLED, Status.INTERRUPTED},
    Status.WAITING_INPUT: {Status.QUEUED, Status.BLOCKED, Status.CANCELLED},
    Status.WAITING_APPROVAL: {Status.QUEUED, Status.CANCELLED, Status.INTERRUPTED},
    Status.BLOCKED: {Status.QUEUED, Status.CANCELLED},
    Status.INTERRUPTED: {Status.QUEUED, Status.CANCELLED},
    Status.COMPLETED: set(),
    Status.FAILED: set(),
    Status.CANCELLED: set(),
}


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        self.directory = directory
        self.db = sqlite3.connect(directory / "argos.sqlite")
        os.chmod(directory / "argos.sqlite", 0o600)
        self.db.row_factory = sqlite3.Row
        if self.db.execute("PRAGMA user_version").fetchone()[0] not in (0, 1, 2):
            self.db.close()
            raise ArgosError("Esta base de datos requiere otra versión de ARGOS.")
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS projects(
                id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                root TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS tasks(
                id TEXT PRIMARY KEY, session TEXT NOT NULL, project TEXT REFERENCES projects(id),
                agent TEXT NOT NULL, objective TEXT NOT NULL, status TEXT NOT NULL,
                capability TEXT NOT NULL, arguments TEXT NOT NULL,
                result TEXT, question TEXT, thread_id TEXT,
                created REAL NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT, task TEXT REFERENCES tasks(id),
                kind TEXT NOT NULL, data TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS requests(
                id TEXT PRIMARY KEY, digest TEXT NOT NULL, response TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS task_session ON tasks(session,updated);
            CREATE INDEX IF NOT EXISTS task_activity ON tasks(session,agent,status,updated);
            CREATE TABLE IF NOT EXISTS conversations(
                id TEXT PRIMARY KEY, session TEXT NOT NULL, project TEXT REFERENCES projects(id),
                provider TEXT NOT NULL, thread_id TEXT, status TEXT NOT NULL,
                title TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS messages(
                seq INTEGER PRIMARY KEY AUTOINCREMENT, conversation TEXT NOT NULL REFERENCES conversations(id),
                role TEXT NOT NULL, content TEXT NOT NULL, task_id TEXT REFERENCES tasks(id), created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS conversation_session ON conversations(session,updated);
            CREATE INDEX IF NOT EXISTS conversation_activity ON conversations(session,status,updated);
            CREATE INDEX IF NOT EXISTS message_conversation ON messages(conversation,seq);
            CREATE INDEX IF NOT EXISTS event_task ON events(task,seq);
            PRAGMA user_version=2;
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def setting(self, key, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        safe_data(value)
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value)))

    def add_project(self, name, path):
        public_text(name, 80)
        root = Path(path).expanduser().resolve(strict=True)
        if not root.is_dir() or root == Path(root.anchor) or root == Path.home():
            raise ArgosError("Selecciona una carpeta de proyecto concreta.")
        existing = self.db.execute(
            "SELECT * FROM projects WHERE name=? COLLATE NOCASE OR root=?", (name, str(root))
        ).fetchone()
        if existing:
            if existing["name"].casefold() != name.casefold() or existing["root"] != str(root):
                raise ArgosError("Ese nombre o carpeta ya pertenece a otro proyecto.")
            return dict(existing)
        project = {"id": uuid.uuid4().hex, "name": name, "root": str(root)}
        safe_data(project)
        with self.db:
            self.db.execute("INSERT INTO projects VALUES (:id,:name,:root)", project)
        return project

    def projects(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM projects ORDER BY name")]

    def project(self, reference):
        if not reference:
            return None
        row = self.db.execute(
            "SELECT * FROM projects WHERE id=? OR name=? COLLATE NOCASE", (reference, reference)
        ).fetchone()
        if not row:
            raise ArgosError("Ese proyecto no está registrado.")
        return dict(row)

    def create_task(self, session, project, agent, objective, capability="", arguments=None,
                    status=Status.QUEUED, question=None):
        Status(status)
        task = dict(id=uuid.uuid4().hex, session=session, project=project, agent=agent,
                    objective=objective, status=str(status), capability=capability,
                    arguments=arguments or {}, question=question, result=None,
                    thread_id=None, created=time.time(), updated=time.time())
        safe_data(task)
        values = {**task, "arguments": json.dumps(task["arguments"])}
        with self.db:
            self.db.execute(
                """INSERT INTO tasks VALUES
                (:id,:session,:project,:agent,:objective,:status,:capability,:arguments,
                 :result,:question,:thread_id,:created,:updated)""", values)
            self._event(task["id"], str(status), {"agent": agent})
        return task

    @staticmethod
    def _task(row):
        if row is None:
            raise ArgosError("No existe esa tarea.")
        task = dict(row)
        task["arguments"] = json.loads(task["arguments"])
        task["result"] = json.loads(task["result"]) if task["result"] else None
        return task

    def task(self, reference):
        # IDs are exact: prefixes must never silently choose an ambiguous task.
        return self._task(self.db.execute("SELECT * FROM tasks WHERE id=?", (reference,)).fetchone())

    def tasks(self, session=None):
        rows = self.db.execute(
            """SELECT * FROM tasks WHERE (? IS NULL OR session=?)
            ORDER BY CASE WHEN status IN ('COMPLETED','FAILED','CANCELLED') THEN 1 ELSE 0 END,
            updated DESC LIMIT 100""",
            (session, session))
        return [self._task(r) for r in rows]

    def update(self, task_id, status, *, result=None, question=None, capability=None,
               arguments=None, project=None, thread_id=None):
        previous = Status(self.task(task_id)["status"])
        status = Status(status)
        if status != previous and status not in TRANSITIONS[previous]:
            raise ArgosError(f"Transición de tarea no válida: {previous} → {status}.")
        safe_data({"result": result, "question": question, "arguments": arguments})
        with self.db:
            self.db.execute(
                """UPDATE tasks SET status=?, result=?, question=?, updated=?,
                capability=COALESCE(?,capability), arguments=COALESCE(?,arguments),
                project=COALESCE(?,project), thread_id=COALESCE(?,thread_id) WHERE id=?""",
                (str(status), json.dumps(result) if result is not None else None,
                 question, time.time(), capability,
                 json.dumps(arguments) if arguments is not None else None,
                 project, thread_id, task_id))
            self._event(task_id, str(status), {"question": question, "result": result})
        return self.task(task_id)

    def event(self, task_id, kind, data):
        safe_data(data)
        with self.db:
            self._event(task_id, kind, data)

    def _event(self, task_id, kind, data):
        self.db.execute("INSERT INTO events(task,kind,data,created) VALUES (?,?,?,?)",
                        (task_id, kind, json.dumps(data), time.time()))

    def events(self, task_id):
        self.task(task_id)
        return [{**dict(r), "data": json.loads(r["data"])} for r in self.db.execute(
            "SELECT * FROM events WHERE task=? ORDER BY seq DESC LIMIT 100", (task_id,))]

    def recover(self):
        # Never replay an operation simply because a previous process stopped.
        ids = [row[0] for row in self.db.execute(
            "SELECT id FROM tasks WHERE status IN ('RUNNING','QUEUED')")]
        for task_id in ids:
            self.update(task_id, Status.INTERRUPTED,
                        question="El Core se detuvo. Revisa la tarea antes de reanudar.")
        with self.db:
            self.db.execute("UPDATE conversations SET status='INTERRUPTED',updated=? WHERE status='RUNNING'",
                            (time.time(),))

    def recent_messages(self, conversation_id, session, project):
        # Explicit public context for short follow-ups, including interpreters
        # without provider-side threads. Never mix projects or sessions.
        rows = self.db.execute(
            """SELECT m.role,m.content FROM messages m JOIN conversations c ON c.id=m.conversation
            WHERE c.id=? AND c.session=? AND c.project IS ?
            ORDER BY m.seq DESC LIMIT 8""", (conversation_id, session, project)).fetchall()
        selected, size = [], 0
        for row in rows:
            if size + len(row["content"]) > 24000:
                break
            selected.append(dict(row))
            size += len(row["content"])
        return list(reversed(selected))

    def begin_conversation(self, conversation_id, session, project, provider, text):
        public_text(text)
        now = time.time()
        with self.db:
            if conversation_id is None:
                conversation_id = uuid.uuid4().hex
                self.db.execute("INSERT INTO conversations VALUES (?,?,?,?,?,?,?,?,?)",
                                (conversation_id, session, project, provider, None, "RUNNING", text[:200], now, now))
            else:
                self.db.execute("UPDATE conversations SET status='RUNNING',updated=? WHERE id=?",
                                (now, conversation_id))
            self.db.execute("INSERT INTO messages(conversation,role,content,created) VALUES (?,?,?,?)",
                            (conversation_id, "user", text, now))
        return conversation_id

    def finish_conversation(self, conversation_id, text, status="IDLE", thread_id=None, task_id=None):
        safe_data({"text": text, "thread_id": thread_id})
        with self.db:
            self.db.execute("UPDATE conversations SET status=?,thread_id=COALESCE(?,thread_id),updated=? WHERE id=?",
                            (status, thread_id, time.time(), conversation_id))
            if text:
                self.db.execute(
                    "INSERT INTO messages(conversation,role,content,task_id,created) VALUES (?,?,?,?,?)",
                    (conversation_id, "assistant" if status == "IDLE" else "system", text, task_id, time.time()))

    def cached(self, key, digest):
        row = self.db.execute("SELECT * FROM requests WHERE id=?", (key,)).fetchone()
        if row and row["digest"] != digest:
            raise ArgosError("Ese identificador ya se utilizó para otra petición.")
        if row:
            response = json.loads(row["response"])
            if response.get("_uncertain"):
                raise ArgosError("La petición anterior no confirmó su resultado. Revisa el estado antes de repetirla.")
            return response
        return None

    def reserve(self, key, digest):
        with self.db:
            self.db.execute("INSERT INTO requests VALUES (?,?,?)",
                            (key, digest, '{"_uncertain":true}'))

    def cache(self, key, digest, response):
        safe_data(response)
        with self.db:
            self.db.execute("UPDATE requests SET response=? WHERE id=? AND digest=?",
                            (json.dumps(response), key, digest))
