"""Bounded AT-SPI supplement and semantic actions for an authorized native window.

Runs out of process with a controller deadline. Generic mutations require a fresh
full-tree fingerprint and a controller-approved request on stdin; no physical input.
"""
import json
import sys
import re
import hashlib
import gi

gi.require_version('Atspi', '2.0')
from gi.repository import Atspi


def root(pid, window_id):
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
    return windows[0]


def read(pid, window_id):
    queue = [(root(pid, window_id), 0)]; result = []; visited = 0
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


SENSITIVE = re.compile(r"(?i)(password|passwd|secret|token|api[_ -]?key|contrase[ñn]a)|-----BEGIN .*PRIVATE KEY|(?:sk-|ghp_)[A-Za-z0-9_-]{16,}")


def inspect(pid, window_id):
    queue = [(root(pid, window_id), 0)]; elements = []; nodes = {}; visited = 0; total = 0
    while queue:
        node, depth = queue.pop(0); visited += 1
        if visited > 256 or depth > 16:
            raise ValueError('Tree exceeds budget')
        if not node: continue
        states = node.get_state_set()
        if states.contains(Atspi.StateType.DEFUNCT): raise ValueError('Defunct tree')
        if not states.contains(Atspi.StateType.SHOWING): continue
        name = node.get_name() or ''
        # Fail closed before reading masked/sensitive controls or traversing them.
        if node.get_role() == Atspi.Role.PASSWORD_TEXT or SENSITIVE.search(name): continue
        value = ''
        text = node.get_text_iface()
        if text:
            count = Atspi.Text.get_character_count(text)
            if count > 4096: raise ValueError('Text exceeds budget')
            value = Atspi.Text.get_text(text, 0, count)
            if SENSITIVE.search(value): raise ValueError('Sensitive content excluded')
        total += len(name) + len(value)
        if total > 16384: raise ValueError('Observation exceeds budget')
        actions = []
        action = node.get_action_iface()
        if action and name.strip() and node.get_role_name() in {'button','push button','toggle button','check box','radio button','menu','menu item','check menu item','radio menu item'} and states.contains(Atspi.StateType.ENABLED):
            for index in range(min(Atspi.Action.get_n_actions(action), 16)):
                label = Atspi.Action.get_action_name(action, index).lower()
                if label in {'click', 'activate', 'toggle', 'press'}:
                    actions.append('click'); break
        if states.contains(Atspi.StateType.EDITABLE) and node.get_editable_text_iface():
            actions.append('replace_text')
        if name or value or actions:
            item = {'ref': node.path, 'name': name[:160], 'role': node.get_role_name(),
                    'text': value, 'actions': actions,
                    'states':[key.lower() for key in ('CHECKED','SELECTED','EXPANDED','ENABLED','EDITABLE')
                              if states.contains(getattr(Atspi.StateType,key))]}
            component = node.get_component_iface()
            if component:
                box = Atspi.Component.get_extents(component, Atspi.CoordType.SCREEN)
                item['bounds'] = [box.x, box.y, box.width, box.height]
            elements.append(item); nodes[node.path] = node
        children = node.get_child_count()
        if children > 128: raise ValueError('Too many controls')
        queue.extend((node.get_child_at_index(i), depth+1) for i in range(children))
    fingerprint = hashlib.sha256(json.dumps(elements, sort_keys=True).encode()).hexdigest()
    return {'elements':elements, 'fingerprint':fingerprint}, nodes


def semantic(pid, window_id, request):
    observed, nodes = inspect(pid, window_id)
    if request.get('operation') == 'observe': return observed
    if request.get('fingerprint') != observed['fingerprint']: raise ValueError('Stale observation')
    ref = request.get('ref'); operation = request.get('operation')
    rows = [e for e in observed['elements'] if e['ref'] == ref and operation in e['actions']]
    if len(rows) != 1: raise ValueError('Unsupported or absent control')
    node = nodes[ref]
    if operation == 'replace_text':
        value = request.get('text')
        if not isinstance(value, str) or len(value.encode()) > 4096 or SENSITIVE.search(value):
            raise ValueError('Invalid or sensitive text')
        delivered = Atspi.EditableText.set_text_contents(node.get_editable_text_iface(), value)
    elif operation == 'click':
        action = node.get_action_iface()
        indices = [i for i in range(Atspi.Action.get_n_actions(action))
                   if Atspi.Action.get_action_name(action, i).lower() in {'click','activate','toggle','press'}]
        if len(indices) != 1: raise ValueError('Ambiguous semantic action')
        delivered = Atspi.Action.do_action(action, indices[0])
    else: raise ValueError('Unsupported action')
    if not delivered: raise ValueError('Application refused semantic operation')
    # Delivery is separate from effect verification by the controller.
    return {'delivered':True, 'method':'atspi', 'physical_input':False}


if __name__ == '__main__':
    try:
        pid, window = int(sys.argv[1]), sys.argv[2]
        if len(sys.argv) == 4 and sys.argv[3] == '--semantic':
            raw = sys.stdin.buffer.read(8193)
            if len(raw) > 8192: raise ValueError('Request exceeds budget')
            data = semantic(pid, window, json.loads(raw))
        else: data = read(pid, window)
        print(json.dumps({'ok': True, 'data': data}))
    except Exception:
        print(json.dumps({'ok': False, 'error': {'code': 'SEMANTIC_OBSERVATION_OR_ACTION_REFUSED'}}))
