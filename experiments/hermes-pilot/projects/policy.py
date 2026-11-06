"""Controller-side validation; no provider, project store or conversation state."""
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from maintenance.controller import clean

FORMAT = 'argos-project-v1'
FIELDS = {'objective', 'requirements', 'decisions', 'verification', 'aliases'}
ENVELOPE = 'Local code edits and tests in this folder only; no network, installations, publishing, hardware or other projects. Engineering requests native review; it cannot approve completion.'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def text(value, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
        raise ValueError('Missing or oversized text')
    if clean(value) != value:
        raise PermissionError('Do not store credentials in project text')
    return value.strip()


def normalize(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def brief(value):
    if not isinstance(value, dict) or set(value) - FIELDS:
        raise ValueError('Unexpected brief fields')
    result = {'objective': text(value.get('objective'), 3000)}
    for field in FIELDS - {'objective'}:
        rows = value.get(field, [])
        if not isinstance(rows, list) or len(rows) > 20:
            raise ValueError('Use at most twenty entries per brief field')
        result[field] = list(dict.fromkeys(text(row, 120 if field == 'aliases' else 1200) for row in rows))
    if len(json.dumps(result)) > 16000:
        raise ValueError('Keep the selected project brief below 16 KB')
    return result


def scope(path, config):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or any(p.startswith('.') for p in path.parts):
        raise PermissionError('Use an absolute, visible project folder')
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise PermissionError('Symlink project scopes are not authorized')
    path = path.resolve()
    roots = [Path(p).resolve() for p in config['project_roots']]
    if not any(path != root and path.is_relative_to(root) for root in roots):
        raise PermissionError('Project is outside the configured project roots')
    protected = [Path(config['operational_root']).resolve(), Path(config['pilot_root']).resolve()]
    if any(path == p or path.is_relative_to(p) or p.is_relative_to(path) for p in protected):
        raise PermissionError('ARGOS, its controller and their ancestor folders are protected')
    return path


def proposal(args, config):
    if set(args) - {'action', 'name', 'slug', 'path', 'brief', 'register'}:
        raise ValueError('Unexpected project proposal fields')
    name = text(args.get('name'), 120)
    slug = args.get('slug') or re.sub('[^a-z0-9]+', '-', normalize(name)).strip('-')[:50]
    if not isinstance(slug, str) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,49}', slug):
        raise ValueError('Use a stable project slug of at most fifty lowercase letters/digits/hyphens')
    path = scope(args.get('path') or str(Path(config['project_roots'][0]) / slug), config)
    register = args.get('register', False)
    if type(register) is not bool:
        raise ValueError('register must be boolean')
    if register and not path.is_dir():
        raise ValueError('The folder to register does not exist')
    return {'name': name, 'slug': slug, 'path': str(path), 'brief': brief(args.get('brief')),
            'register': register, 'envelope': ENVELOPE}
