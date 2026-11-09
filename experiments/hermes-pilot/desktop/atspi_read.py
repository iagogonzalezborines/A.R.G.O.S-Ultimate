"""Bounded read-only text supplement for AT-SPI documents omitted by Agent Desktop.

Runs out of process with a controller deadline. Never accepts an action or a path.
"""
import json
import sys
import re
import gi

gi.require_version('Atspi', '2.0')
from gi.repository import Atspi


def read(pid, window_id):
    match = re.fullmatch(r"w-[0-9.]+-org-a11y-atspi-accessible-([0-9]+)", window_id)
    if not match: raise ValueError("Unsupported accessibility window identity")
    window_path = "/org/a11y/atspi/accessible/" + match[1]
    Atspi.set_timeout(400, 400)
    desktop = Atspi.get_desktop(0)
    apps = [desktop.get_child_at_index(i) for i in range(min(desktop.get_child_count(), 256))]
    apps = [a for a in apps if a and a.get_process_id() == pid]
    if len(apps) != 1:
        raise ValueError('Application identity unavailable')
    app = apps[0]
    windows = [app.get_child_at_index(i) for i in range(min(app.get_child_count(), 32))]
    windows = [w for w in windows if w and w.path == window_path]
    if len(windows) != 1:
        raise ValueError('Ambiguous window')
    queue = [(windows[0], 0)]; result = []; visited = 0
    while queue and visited < 256:
        node, depth = queue.pop(0); visited += 1
        states = node.get_state_set()
        if states.contains(Atspi.StateType.DEFUNCT):
            raise ValueError('Defunct accessibility tree')
        if not states.contains(Atspi.StateType.SHOWING):
            continue
        if node.get_role() != Atspi.Role.PASSWORD_TEXT:
            text = node.get_text_iface()
            if text:
                count = Atspi.Text.get_character_count(text)
                if count > 4096:
                    raise ValueError('Text exceeds observation budget')
                value = Atspi.Text.get_text(text, 0, count)
                if value.strip():
                    result.append({'role': node.get_role_name(), 'name': node.get_name()[:100], 'text': value})
        if depth < 14:
            queue.extend((node.get_child_at_index(i), depth + 1) for i in range(min(node.get_child_count(), 128)))
    if queue:
        raise ValueError('Accessibility tree exceeds observation budget')
    return result


if __name__ == '__main__':
    try:
        print(json.dumps({'ok': True, 'data': read(int(sys.argv[1]), sys.argv[2])}))
    except Exception:
        print(json.dumps({'ok': False, 'error': {'code': 'TEXT_OBSERVATION_UNAVAILABLE'}}))
