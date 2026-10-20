"""Read-only, session-scoped projections for the two terminal monitors."""
import time

from .agents import AGENTS
from .models import ArgosError


NAMES = {"general": "General", "engineering": "Engineering", "computer": "Computer",
         "research": "Research", "design3d": "Design 3D", "printing3d": "Printing 3D"}
ACTIVE = ("RUNNING", "QUEUED")
WAITING = ("WAITING_INPUT", "WAITING_APPROVAL", "BLOCKED", "INTERRUPTED")
FINISHED = ("COMPLETED", "FAILED", "CANCELLED", "IDLE")


def offset(request, key="offset"):
    value = request.get(key, 0)
    if type(value) is not int or not 0 <= value <= 10_000_000:
        raise ArgosError("Página de monitor inválida.")
    return value


def snapshot(core, request):
    db, session = core.store.db, request.get("session", "default")
    kind, group, agent = request.get("kind", "tasks"), request.get("filter", "all"), request.get("agent")
    if kind not in ("tasks", "conversations") or group not in ("all", "active", "waiting", "finished"):
        raise ArgosError("Vista de monitor inválida.")
    if agent is not None and agent not in AGENTS:
        raise ArgosError("Agente desconocido.")
    start = offset(request)
    counts = {a: {} for a in AGENTS}
    for row in db.execute("SELECT agent,status,count(*) n FROM tasks WHERE session=? GROUP BY agent,status", (session,)):
        counts[row["agent"]][row["status"]] = row["n"]
    for row in db.execute("SELECT status,count(*) n FROM conversations WHERE session=? GROUP BY status", (session,)):
        counts["general"][row["status"]] = counts["general"].get(row["status"], 0) + row["n"]
    provider = core.interpreter.name if core.interpreter else "none"
    proc = getattr(core.interpreter, "process", None)
    connection = ("connected" if proc and proc.returncode is None and getattr(core.interpreter, "connected", False) else
                  "configured" if core.interpreter else "not_configured")
    agents = []
    for identifier, definition in AGENTS.items():
        totals = counts[identifier]
        running = totals.get("RUNNING", 0)
        queued = totals.get("QUEUED", 0)
        waiting = sum(totals.get(s, 0) for s in WAITING)
        current = db.execute(
            "SELECT objective FROM tasks WHERE session=? AND agent=? AND status='RUNNING' ORDER BY updated DESC LIMIT 1",
            (session, identifier)).fetchone()
        if identifier == "general":
            current = db.execute(
                "SELECT title FROM conversations WHERE session=? AND status='RUNNING' ORDER BY updated DESC LIMIT 1",
                (session,)).fetchone()
        agents.append({"id": identifier, "name": NAMES[identifier], "role": definition.role,
                       "capabilities": list(definition.capabilities), "provider": provider,
                       "connection": connection, "running": running, "queued": queued, "waiting": waiting,
                       "activity": current[0][:240] if current else None,
                       "state": "running" if running else "queued" if queued else "waiting" if waiting else "idle"})
    table = "tasks" if kind == "tasks" else "conversations"
    conditions, params = ["x.session=?"], [session]
    statuses = {"active": ACTIVE, "waiting": WAITING, "finished": FINISHED}.get(group)
    if statuses:
        conditions.append("x.status IN (" + ",".join("?" for _ in statuses) + ")")
        params.extend(statuses)
    if agent:
        conditions.append("x.agent=?" if kind == "tasks" else "'general'=?")
        params.append(agent)
    where = " AND ".join(conditions)
    total = db.execute(f"SELECT count(*) FROM {table} x WHERE {where}", params).fetchone()[0]
    columns = ("x.agent,x.objective AS title,x.capability" if kind == "tasks"
               else "'general' AS agent,x.title,'' AS capability")
    rows = [dict(r) for r in db.execute(
        f"""SELECT x.id,x.status,x.project,x.created,x.updated,x.thread_id,{columns},p.name AS project_name
        FROM {table} x LEFT JOIN projects p ON p.id=x.project WHERE {where}
        ORDER BY CASE WHEN x.status='RUNNING' THEN 0 WHEN x.status='QUEUED' THEN 1
        WHEN x.status IN ('WAITING_INPUT','WAITING_APPROVAL','BLOCKED','INTERRUPTED') THEN 2 ELSE 3 END,
        x.updated DESC,x.id LIMIT 24 OFFSET ?""", (*params, start))]
    for row in rows:
        row["title"] = row["title"][:240]
        if (kind == "conversations" and row["thread_id"] is None
                and core.conversation_ids.get((session, row["project"])) == row["id"]
                and hasattr(core.interpreter, "conversation_thread")):
            row["thread_id"] = core.interpreter.conversation_thread(
                {"session": session, "project": {"id": row["project"]} if row["project"] else None})
    return {"agents": agents, "rows": rows, "total": total, "offset": start, "page_size": 24,
            "kind": kind, "filter": group, "agent": agent, "session": session, "updated": time.time(),
            "counts": {"running": sum(c.get("RUNNING", 0) for c in counts.values()),
                       "queued": sum(c.get("QUEUED", 0) for c in counts.values()),
                       "waiting": sum(sum(c.get(s, 0) for s in WAITING) for c in counts.values())}}


def event_message(event):
    """Only public commentary, questions, answers and verified outcome summaries."""
    kind, data = event["kind"], event["data"]
    if kind == "PROGRESS":
        return "Codex", data.get("summary", "")
    if kind == "USER_ANSWER":
        return "Tú", data.get("answer", "")
    if kind == "CAPABILITY_RESULT":
        result = data.get("result") or {}
        return "Herramienta", f'{data.get("capability", "")}: {result.get("speech", "")}'
    result = data.get("result") or {}
    content = data.get("question") or result.get("detail") or result.get("speech") or ""
    return "Core", kind + ("\n" + content if content else "")


def detail(core, request):
    import json
    db, session = core.store.db, request.get("session", "default")
    kind, identifier = request.get("kind", "tasks"), request.get("id")
    if kind not in ("tasks", "conversations") or not isinstance(identifier, str):
        raise ArgosError("Detalle de monitor inválido.")
    start = offset(request)
    table = "tasks" if kind == "tasks" else "conversations"
    row = db.execute(f"SELECT * FROM {table} WHERE id=? AND session=?", (identifier, session)).fetchone()
    if row is None:
        raise ArgosError("El registro no existe en esta sesión.")
    if kind == "tasks":
        title, thread = row["objective"], row["thread_id"]
        total = db.execute("SELECT count(*) FROM events WHERE task=?", (identifier,)).fetchone()[0]
        messages = []
        for event in db.execute("SELECT * FROM events WHERE task=? ORDER BY seq DESC LIMIT 12 OFFSET ?",
                                (identifier, start)):
            event = {**dict(event), "data": json.loads(event["data"])}
            role, content = event_message(event)
            messages.append({"role": role, "content": content, "created": event["created"]})
    else:
        title, thread = row["title"], row["thread_id"]
        total = db.execute("SELECT count(*) FROM messages WHERE conversation=?", (identifier,)).fetchone()[0]
        messages = [dict(r) for r in db.execute(
            "SELECT role,content,task_id,created FROM messages WHERE conversation=? ORDER BY seq DESC LIMIT 12 OFFSET ?",
            (identifier, start))]
        if (thread is None and core.conversation_ids.get((session, row["project"])) == identifier
                and hasattr(core.interpreter, "conversation_thread")):
            thread = core.interpreter.conversation_thread(
                {"session": session, "project": {"id": row["project"]} if row["project"] else None})
    return {"id": identifier, "kind": kind, "title": title, "status": row["status"], "thread_id": thread,
            "messages": list(reversed(messages)), "offset": start, "total": total, "page_size": 12}
