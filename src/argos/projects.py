"""Persistent project facts. Metadata never grants file or command authority."""
import asyncio
import hashlib
import json
import os
import re
import stat
import time
from pathlib import Path

from .filesystem import open_file, path_for, project_directory, observe_project_folders
from .models import ArgosError
from .security import public_text, safe_data

OPERATIONS = ('projects.inspect', 'projects.context', 'projects.select', 'projects.alias')


def development_metadata(root):
    from .development_workspace import EXCLUDED, MAX_BYTES, MAX_FILES
    count = total = 0
    complete = True
    def on_error(error):
        nonlocal complete
        complete = False
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=on_error):
        def allowed(name):
            path = Path(directory) / name
            try:
                path_for(None, str(path))
                return name not in EXCLUDED and not path.is_symlink()
            except ArgosError:
                return False
        dirs[:] = [d for d in dirs if allowed(d)]
        for name in files:
            if not allowed(name):
                continue
            try:
                info = (Path(directory) / name).lstat()
            except OSError:
                complete = False
                continue
            if stat.S_ISREG(info.st_mode):
                count += 1
                total += info.st_size
            if count > MAX_FILES or total > MAX_BYTES:
                complete = False
                break
        if not complete:
            break
    modules = []
    for container in ('apps', 'packages'):
        listing = observe_project_folders(root / container)
        for entry in listing['entries'][:20]:
            directory = Path(entry['path'])
            manifests = []
            for filename in ('package.json', 'pom.xml', 'build.gradle', 'build.gradle.kts', 'pyproject.toml', 'Cargo.toml', 'go.mod'):
                try:
                    with open_file(path_for(None, str(directory / filename))):
                        manifests.append(filename)
                except (OSError, ArgosError):
                    pass
            if manifests:
                modules.append({'path': str(directory.relative_to(root)), 'manifests': manifests})
    return {'max_bytes': MAX_BYTES, 'max_files': MAX_FILES, 'observed_bytes': total,
            'observed_files': count, 'complete': complete,
            'requires_scope': total > MAX_BYTES or count > MAX_FILES, 'modules': modules,
            'basis': 'Bounded metadata scan; counts are lower bounds when incomplete. No code or binary contents read.'}


def inspect_project(project):
    root = project_directory(None, project['root'])
    sources, description, package = [], '', {}
    for name in ('README.md', 'README.rst', 'README.txt', 'README', 'package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod', 'pom.xml'):
        path = path_for(None, str(root / name))
        try:
            with open_file(path) as file:
                raw = file.read(65537)
            if len(raw) > 65536:
                sources.append({'file': name, 'status': 'too_large'})
                continue
            text = raw.decode('utf-8')
            public_text(text, 65536)
        except FileNotFoundError:
            continue
        except (ArgosError, UnicodeError):
            sources.append({'file': name, 'status': 'protected_or_not_text'})
            continue
        except OSError:
            sources.append({'file': name, 'status': 'unavailable'})
            continue
        sources.append({'file': name, 'status': 'read', 'sha256': hashlib.sha256(raw).hexdigest()})
        if name.startswith('README') and not description:
            # A quoted documentation excerpt, not an inferred implementation claim.
            paragraphs = re.split(r'\n\s*\n', text)
            description = next((' '.join(p.split())[:1200] for p in paragraphs
                if p.strip() and not p.lstrip().startswith(('#', '```', '[!', '<', '|', '.. '))), '')
        if name == 'package.json':
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    package = {k: data[k][:300] for k in ('name', 'description') if isinstance(data.get(k), str)}
            except ValueError:
                pass
    result = {'observed_at': time.time(), 'description': description,
              'description_basis': 'documentation_excerpt', 'package_metadata': package,
              'sources': sources, 'development': development_metadata(root),
              'limits': 'Documentation, root manifests and bounded file metadata only; code, tests and runtime behavior not verified. Stored observations may be stale.'}
    return safe_data(result)


async def requires_core(project, args):
    raise ArgosError('La operación de proyecto necesita el registro del Core.')


class ProjectService:
    def __init__(self, store):
        self.store = store

    async def execute(self, task, project, name, args):
        target = self.store.project(args['project'])
        if project and target['id'] != project['id']:
            raise ArgosError('El proyecto está fuera del ámbito de esta tarea.')
        if name == 'projects.inspect':
            inspection = await asyncio.to_thread(inspect_project, target)
            self.store.save_project_inspection(target['id'], inspection)
            speech, verification = 'Ficha del proyecto actualizada.', 'project_inspected'
        elif name == 'projects.select':
            self.store.select_project(task['session'], target['id'])
            speech, verification = f"Proyecto {target['name']} seleccionado.", 'project_selected'
        elif name == 'projects.alias':
            self.store.add_project_alias(target['id'], args['alias'])
            speech, verification = 'Alias del proyecto guardado.', 'project_alias_saved'
        else:
            speech, verification = 'Ficha del proyecto consultada.', 'project_context_observed'
        evidence = self.store.project_profile(target['id'])
        evidence['tasks'] = [{'id': t['id'], 'objective': t['objective'][:300], 'status': t['status'],
                              'verification': (t['result'] or {}).get('verification')}
                             for t in self.store.tasks(task['session']) if t['project'] == target['id'] and t['id'] != task['id']][:8]
        return {'speech': speech, 'verification': verification, 'evidence': evidence}


def capabilities(C):
    return [
        C('projects.inspect', 'computer', 'Leer documentación/manifiestos de un proyecto registrado y guardar su ficha con fuentes', ('project',), False, requires_core),
        C('projects.context', 'computer', 'Consultar ficha persistente y tareas de este proyecto en la sesión', ('project',), False, requires_core),
        C('projects.select', 'computer', 'Seleccionar proyecto de esta sesión para próximas peticiones; no cambia tareas en curso', ('project',), False, requires_core, 'routine'),
        C('projects.alias', 'computer', 'Guardar alias confirmado por el usuario para un proyecto registrado', ('project', 'alias'), False, requires_core, 'routine'),
    ]
