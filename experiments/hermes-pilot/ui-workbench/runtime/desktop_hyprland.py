"""Read-only compositor identity. Never focus, warp or inject input implicitly."""
import json
import os
import subprocess


class Hyprland:
    def __init__(self, env):
        self.env = env

    def query(self, command):
        if command not in {'clients', 'activewindow', 'cursorpos', 'monitors', 'version'}:
            raise ValueError('Unsupported compositor observation')
        if not self.env.get('HYPRLAND_INSTANCE_SIGNATURE'):
            raise RuntimeError('Hyprland session unavailable')
        result = subprocess.run(['/usr/bin/hyprctl', '-j', command], env=self.env,
                                capture_output=True, timeout=2, check=True)
        if len(result.stdout) > 262144:
            raise ValueError('Compositor observation exceeds budget')
        return json.loads(result.stdout)

    def window(self, pid, address=None):
        rows = [w for w in self.query('clients') if w.get('pid') == pid and w.get('mapped')
                and (address is None or w.get('address') == address)]
        if len(rows) != 1:
            raise PermissionError('Window/compositor identity ambiguous or gone')
        w = rows[0]
        return {k:w.get(k) for k in ('address', 'pid', 'class', 'stableId', 'at', 'size', 'monitor', 'workspace', 'xwayland')}

    def seat(self):
        # Only identity and coordinates; unrelated window titles/content stay private.
        return {'focus': self.query('activewindow').get('address'), 'cursor': self.query('cursorpos')}

    def layout(self):
        return [{k:m.get(k) for k in ('id','name','x','y','width','height','scale','transform')}
                for m in self.query('monitors')]

    def capabilities(self):
        try:
            return {'available': True, 'outputs': self.layout(), 'input_backend': None,
                    'foreground_available': False,
                    'reason': 'No validated isolated input backend; physical input is never a background fallback'}
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            return {'available': False, 'foreground_available': False, 'input_backend': None}
