"""Independent, read-only terminal surfaces. No model calls and no task control."""
import asyncio
import curses
import sys
import textwrap
import time
import unicodedata

from .models import ArgosError
from .transport import call


LABELS = {"RUNNING": "EN PROCESO", "QUEUED": "EN COLA", "WAITING_INPUT": "ESPERA RESPUESTA",
          "WAITING_APPROVAL": "ESPERA APROBACIÓN", "BLOCKED": "BLOQUEADA",
          "INTERRUPTED": "INTERRUMPIDA", "COMPLETED": "FINALIZADA", "FAILED": "FALLIDA",
          "CANCELLED": "CANCELADA", "IDLE": "SIN TURNO ACTIVO"}
STATE_COLOR = {"RUNNING": 1, "QUEUED": 4, "WAITING_INPUT": 4, "WAITING_APPROVAL": 4,
               "BLOCKED": 4, "INTERRUPTED": 4, "COMPLETED": 3, "FAILED": 5, "CANCELLED": 2, "IDLE": 2}


def clean(value):
    # External names and model prose never become terminal escape sequences.
    return "".join(c for c in str(value) if not unicodedata.category(c).startswith("C") or c in "\n\t")


def clipped(value, width):
    result, used = "", 0
    for char in clean(value).replace("\n", " ").replace("\t", " "):
        cells = 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
        if unicodedata.combining(char):
            continue
        if used + cells > width:
            break
        result += char
        used += cells
    return result


class Canvas:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.cells = [[(" ", 0) for _ in range(width)] for _ in range(height)]

    def put(self, x, y, value, color=0, width=None):
        if not 0 <= y < self.height:
            return
        for char in clipped(value, max(0, min(self.width - x, width if width is not None else self.width))):
            cells = 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
            if 0 <= x < self.width:
                self.cells[y][x] = (char, color)
                if cells == 2 and x + 1 < self.width:
                    self.cells[y][x + 1] = ("", color)
            x += cells

    def line(self, x1, y1, x2, y2, color=2):
        if y1 == y2:
            self.put(min(x1, x2), y1, "─" * (abs(x2 - x1) + 1), color)
        elif x1 == x2:
            for y in range(min(y1, y2), max(y1, y2) + 1):
                self.put(x1, y, "│", color)

    def box(self, x, y, width, height, title="", color=2):
        self.put(x, y, "╭" + "─" * (width - 2) + "╮", color)
        self.put(x, y + height - 1, "╰" + "─" * (width - 2) + "╯", color)
        for row in range(y + 1, y + height - 1):
            self.put(x, row, "│", color)
            self.put(x + width - 1, row, "│", color)
        if title:
            self.put(x + 2, y, " " + clipped(title, width - 7) + " ", color)

    def text(self):
        return "\n".join("".join(char for char, _ in row) for row in self.cells)

    def draw(self, screen):
        for y, row in enumerate(self.cells):
            x = 0
            while x < len(row):
                start, color = x, row[x][1]
                chars = []
                while x < len(row) and row[x][1] == color:
                    chars.append(row[x][0])
                    x += 1
                try:
                    screen.addstr(y, start, "".join(chars), curses.color_pair(color + 1))
                except curses.error:
                    pass
        screen.refresh()


def header(canvas, title, snapshot, error):
    canvas.put(2, 1, "A R G O S", 1)
    canvas.put(15, 1, "/  " + title, 0, canvas.width - 32)
    canvas.put(canvas.width - 14, 1, "● EN DIRECTO" if not error else "● SIN SEÑAL", 3 if not error else 5)
    counts = snapshot.get("counts", {})
    canvas.put(2, 3, f'{counts.get("running", 0):02} EN PROCESO   '
               f'{counts.get("queued", 0):02} EN COLA   {counts.get("waiting", 0):02} EN ESPERA', 2)
    canvas.line(2, 4, canvas.width - 3, 4)
    if error:
        canvas.put(2, canvas.height - 3, "Sin conexión con Core; los datos no se están actualizando.", 5)


def render_map(snapshot, width, height, selected=0, error=None):
    canvas = Canvas(width, height)
    if width < 76 or height < 24:
        canvas.put(1, 1, "Amplía la ventana a 76 × 24 para ver el diagrama.", 4)
        canvas.put(1, 3, "Q: cerrar · Las tareas continúan en segundo plano.", 2)
        return canvas
    header(canvas, "MAPA DE AGENTES", snapshot, error)
    agents = snapshot.get("agents", [])
    if not agents:
        canvas.put(3, 7, "Esperando datos de Core…", 2)
        return canvas
    node_width = min(32, (width - 30) // 2)
    left, right = 2, width - node_width - 2
    center_x, center_w = width // 2 - 9, 18
    ys = [6, (6 + height - 9) // 2, height - 9]
    mid = ys[1] + 2
    for x, endpoint in ((left + node_width + 1, center_x - 1), (right - 2, center_x + center_w)):
        canvas.line(x, ys[0] + 2, x, ys[-1] + 2)
        canvas.line(x, mid, endpoint, mid, 1)
    for index, agent in enumerate(agents[:6]):
        x, y = (left if index < 3 else right), ys[index % 3]
        endpoint, bus = ((x + node_width, left + node_width + 1) if index < 3 else (x - 1, right - 2))
        color = {"running": 1, "queued": 4, "waiting": 4, "idle": 3}[agent["state"]]
        canvas.line(endpoint, y + 2, bus, y + 2, color)
        canvas.put(bus, y + 2, "├" if index < 3 else "┤", color)
        canvas.box(x, y, node_width, 4, agent["name"], 1 if index == selected else color)
        label = {"running": f'● OCUPADO · {agent["running"]}',
                 "queued": f'◷ EN COLA · {agent["queued"]}',
                 "waiting": f'◷ EN ESPERA · {agent["waiting"]}', "idle": "○ DISPONIBLE"}[agent["state"]]
        canvas.put(x + 2, y + 1, label, color, node_width - 4)
        sub = agent.get("activity") or ("Conversación" if agent["id"] == "general" else f'{len(agent["capabilities"])} capacidades')
        canvas.put(x + 2, y + 2, sub, 2, node_width - 4)
    canvas.box(center_x, ys[1], center_w, 4, "CORE", 1)
    canvas.put(center_x + 4, ys[1] + 1, "A.R.G.O.S.", 1, center_w - 5)
    canvas.put(center_x + 3, ys[1] + 2, "ORQUESTADOR", 2)
    agent = agents[selected % len(agents)]
    canvas.line(2, height - 5, width - 3, height - 5)
    canvas.put(2, height - 4, f'{agent["name"]}  /  {agent["role"]}', 0, width - 4)
    if not error:
        connection = {"connected": "conectado", "configured": "configurado, sin verificar",
                      "not_configured": "sin proveedor de IA"}[agent["connection"]]
        caps = ", ".join(agent["capabilities"]) or "Intenciones locales y conversación"
        canvas.put(2, height - 3, f'{agent["provider"]} · {connection}  |  {caps}', 2, width - 4)
    canvas.put(2, height - 1, "TAB / ↑↓ agente   T abrir monitor de tareas   Q cerrar", 2, width - 4)
    return canvas


def detail_lines(detail, width):
    if not detail:
        return [("Selecciona un registro para ver su actividad.", 2)]
    lines = []
    def paragraph(text, color):
        for part in clean(text).expandtabs(2).splitlines() or [""]:
            for line in textwrap.wrap(part, max(12, width), replace_whitespace=False) or [""]:
                lines.append((line, color))
    paragraph(detail["title"], 0)
    lines.append(("", 0))
    paragraph("ID  " + detail["id"], 2)
    paragraph("HILO  " + (detail.get("thread_id") or "Operación local / hilo aún no asignado"), 2)
    lines.append(("", 0))
    for message in detail.get("messages", []):
        role = {"user": "TÚ", "assistant": "ARGOS", "system": "CORE"}.get(message["role"], message["role"].upper())
        stamp = time.strftime("%d/%m %H:%M:%S", time.localtime(message["created"]))
        lines.append((stamp + "  " + role, 1 if role in ("ARGOS", "CODEX") else 7))
        content = message["content"]
        if role == "CORE":
            first, separator, rest = content.partition("\n")
            content = LABELS.get(first, first) + separator + rest
        paragraph(content, 0)
        if message.get("task_id"):
            paragraph("Tarea vinculada: " + message["task_id"], 2)
        lines.append(("", 0))
    return lines


def scroll_limit(detail, width, height):
    split = max(28, min(42, width // 3))
    return max(0, len(detail_lines(detail, max(12, width - split - 9))) - max(1, height - 13))


def render_tasks(snapshot, detail, width, height, selected=0, scroll=0, error=None):
    canvas = Canvas(width, height)
    if width < 76 or height < 20:
        canvas.put(1, 1, "Amplía la ventana a 76 × 20 para ver el monitor.", 4)
        canvas.put(1, 3, "Q: cerrar", 2)
        return canvas
    kind = snapshot.get("kind", "tasks")
    header(canvas, "TAREAS" if kind == "tasks" else "CONVERSACIONES", snapshot, error)
    filters = [("all", "1 Todas"), ("active", "2 En proceso"), ("waiting", "3 En espera"),
               ("finished", "4 Finalizadas" if kind == "tasks" else "4 Sin turno")]
    x = 2
    for value, label in filters:
        canvas.put(x, 5, " " + label + " ", 6 if snapshot.get("filter") == value else 2)
        x += len(label) + 4
    if snapshot.get("agent"):
        canvas.put(x, 5, snapshot["agent"] + " · A: todos", 4, width - x - 2)
    split = max(28, min(42, width // 3))
    panel_h = height - 11
    canvas.box(2, 7, split, panel_h, "ACTIVIDAD", 2)
    canvas.box(split + 3, 7, width - split - 5, panel_h, "CONVERSACIÓN / EVENTOS", 2)
    rows = snapshot.get("rows", [])
    visible = max(1, (panel_h - 2) // 3)
    list_start = selected // visible * visible
    for index, row in enumerate(rows[list_start:list_start + visible], list_start):
        y = 8 + (index - list_start) * 3
        color = STATE_COLOR.get(row["status"], 2)
        canvas.put(4, y, ("▸ " if index == selected else "  ") + LABELS.get(row["status"], row["status"]),
                   6 if index == selected else color, split - 4)
        canvas.put(4, y + 1, row["title"], 0 if index == selected else 2, split - 4)
        canvas.put(4, y + 2, f'{row["agent"]} · {row.get("project_name") or "Sin proyecto"}', 2, split - 4)
    if not rows:
        canvas.put(4, 9, "Sin registros en esta vista.", 2, split - 4)
        canvas.put(4, 11, "La actividad aparecerá aquí.", 2, split - 4)
    lines = detail_lines(detail, width - split - 9)
    scroll = min(scroll, max(0, len(lines) - (panel_h - 2)))
    for index, (line, color) in enumerate(lines[scroll:scroll + panel_h - 2]):
        canvas.put(split + 5, 8 + index, line, color, width - split - 9)
    total, start = snapshot.get("total", 0), snapshot.get("offset", 0)
    if not error:
        canvas.put(2, height - 3, f'{start + 1 if total else 0}–{min(start + len(rows), total)} de {total}'
                   + "  ·  ←→ página  ↑↓ registro  PgUp/PgDn texto  [ ] historial  F seguir", 2, width - 4)
    canvas.put(2, height - 1, "M abrir mapa   T tareas   C conversaciones   G agente   1–4 filtro   Q cerrar", 2, width - 4)
    return canvas


async def monitor(directory, view="agents", session="default"):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ArgosError("El monitor necesita una terminal interactiva.")
    # Fail before taking over the terminal on initial connection errors.
    snapshot = (await call(directory, {"method": "monitor.snapshot", "session": session}))["data"]
    screen = curses.initscr()
    curses.noecho()
    curses.cbreak()
    screen.keypad(True)
    screen.nodelay(True)
    try:
        try:
            curses.curs_set(0)
            curses.start_color()
            curses.use_default_colors()
            palette = (252, 81, 245, 84, 221, 203, 16, 141) if curses.COLORS >= 256 else (7, 6, 7, 2, 3, 1, 0, 5)
            for index, foreground in enumerate(palette):
                curses.init_pair(index + 1, foreground, (81 if curses.COLORS >= 256 else 6) if index == 6 else -1)
        except curses.error:
            pass
        kind, group, agent = "tasks", "all", None
        page, selected, map_selected, scroll, detail_page = 0, 0, 0, 0, 0
        detail, selected_id, error = None, None, None
        follow = True
        refresh = 0
        while True:
            key = screen.getch()
            while key != -1:
                if key in (ord("q"), ord("Q"), 27):
                    return
                if (view == "agents" and key in (ord("t"), 10, 13)) or (view == "tasks" and key == ord("m")):
                    try:
                        await call(directory, {"method": "monitor.open", "session": session,
                                              "view": "tasks" if view == "agents" else "agents"})
                    except ArgosError:
                        pass
                elif view == "tasks" and key in (ord("t"), ord("c")):
                    kind = "conversations" if key == ord("c") else "tasks"
                    page = selected = scroll = detail_page = 0
                    selected_id = None
                    detail = None
                    agent = None
                    follow = True
                elif view == "agents":
                    if key in (9, curses.KEY_DOWN, curses.KEY_RIGHT):
                        map_selected = (map_selected + 1) % 6
                    elif key in (curses.KEY_UP, curses.KEY_LEFT):
                        map_selected = (map_selected - 1) % 6
                else:
                    if key in (ord("1"), ord("2"), ord("3"), ord("4"), ord("a"), ord("g")):
                        if key == ord("a"):
                            agent = None
                        elif key == ord("g"):
                            options = [None] + [a["id"] for a in snapshot.get("agents", [])]
                            agent = options[(options.index(agent) + 1) % len(options)]
                        else:
                            group = ("all", "active", "waiting", "finished")[key - ord("1")]
                        page = selected = scroll = detail_page = 0
                        detail, selected_id = None, None
                        follow = True
                    elif key in (curses.KEY_DOWN, ord("j"), curses.KEY_UP, ord("k")):
                        selected += 1 if key in (curses.KEY_DOWN, ord("j")) else -1
                        selected = max(0, min(selected, len(snapshot.get("rows", [])) - 1))
                        selected_id = None
                        scroll = detail_page = 0
                        follow = True
                    elif key in (curses.KEY_LEFT, curses.KEY_RIGHT):
                        target = page + (-24 if key == curses.KEY_LEFT else 24)
                        if 0 <= target < snapshot.get("total", 0):
                            page = target
                            selected = scroll = detail_page = 0
                            selected_id = None
                            detail = None
                            follow = True
                    elif key in (curses.KEY_NPAGE, curses.KEY_PPAGE):
                        h, w = screen.getmaxyx()
                        limit = scroll_limit(detail, w, h)
                        scroll = max(0, min(limit, scroll + (h - 14) * (1 if key == curses.KEY_NPAGE else -1)))
                        follow = scroll == limit
                    elif key == ord("f"):
                        detail_page, follow = 0, True
                    elif key in (ord("["), ord("]")) and detail:
                        target = detail_page + (detail["page_size"] if key == ord("[") else -detail["page_size"])
                        if 0 <= target < detail["total"]:
                            detail_page, scroll = target, 0
                            follow = target == 0
                refresh = 0
                key = screen.getch()
            if time.monotonic() >= refresh:
                try:
                    snapshot = (await call(directory, {"method": "monitor.snapshot", "session": session,
                                "kind": kind, "filter": group, "agent": agent, "offset": page}))["data"]
                    rows = snapshot["rows"]
                    if page >= snapshot["total"] and page:
                        page = max(0, (snapshot["total"] - 1) // 24 * 24)
                        selected = 0
                    if selected_id:
                        selected = next((i for i, row in enumerate(rows) if row["id"] == selected_id), selected)
                    selected = max(0, min(selected, len(rows) - 1))
                    if view != "agents" and rows:
                        next_id = rows[selected]["id"]
                        if selected_id and selected_id != next_id:
                            scroll = detail_page = 0
                        selected_id = next_id
                        detail = (await call(directory, {"method": "monitor.detail", "session": session,
                                  "kind": kind, "id": selected_id, "offset": detail_page}))["data"]
                    else:
                        detail, selected_id = None, None
                    error = None
                except (ArgosError, OSError, ValueError, TimeoutError):
                    error = "Core desconectado"
                refresh = time.monotonic() + .75
            height, width = screen.getmaxyx()
            if follow:
                scroll = scroll_limit(detail, width, height)
            canvas = (render_map(snapshot, width, height, map_selected, error) if view == "agents"
                      else render_tasks(snapshot, detail, width, height, selected, scroll, error))
            canvas.draw(screen)
            await asyncio.sleep(.08)
    finally:
        screen.keypad(False)
        curses.nocbreak()
        curses.echo()
        curses.endwin()
