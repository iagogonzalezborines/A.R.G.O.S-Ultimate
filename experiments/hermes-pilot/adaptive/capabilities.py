"""Small explicit registry; no plugins are imported and no model is loaded by discovery."""
import os
from pathlib import Path
from adaptive.local import Local, normalize, validate_items

REGISTRY = {
    'text.normalize': {'purpose':'Normalize an explicit newline list','location':'local','permissions':['provided_text'], 'resource':'tiny','quality':'exact transformation','latency':'measured sub-ms on fixture','cost':'none','parallel':True,'lifecycle':'function'},
    'local.extract': {'purpose':'Extract named items from short prose','location':'local','permissions':['provided_text','configured_loopback_model'], 'resource':'one model','quality':'experimental; semantic review required','latency':'measure cold and warm','cost':'CPU/RAM','parallel':False,'lifecycle':'Ollama keep_alive; explicit pressure release'},
    'files.inventory': {'purpose':'List visible regular files at the authorized project root','location':'local','permissions':['project_metadata_read'],'resource':'bounded directory scan','quality':'observed metadata','latency':'filesystem dependent','cost':'none','parallel':True,'lifecycle':'function'},
    'files.types': {'purpose':'Count extensions from an inventory result','location':'local','permissions':['same_project_parent_result'],'resource':'tiny','quality':'exact aggregation','latency':'sub-ms expected, unmeasured','cost':'none','parallel':True,'lifecycle':'function'},
}


def catalog(config):
    rows=[]
    for name,entry in REGISTRY.items():
        available=True
        if name=='local.extract':
            try:available=Local(config['local']).available()
            except (OSError,ValueError,KeyError):available=False
        rows.append({'id':name,**entry,'available':available})
    return rows


def select(operation, payload):
    if operation=='items':
        # Callers explicitly mark a list versus prose: no routing LLM or heuristic authority.
        if payload.get('format') not in {'lines','prose'}:raise ValueError('Specify lines or prose')
        return 'text.normalize' if payload['format']=='lines' else 'local.extract'
    if operation not in REGISTRY:raise ValueError('Unregistered capability')
    return operation


def validate_payload(kind, payload):
    from projects.policy import text
    if not isinstance(payload,dict) or set(payload)-{'text','format'}:raise ValueError('Unsupported payload')
    if 'format' in payload and payload['format'] not in {'lines','prose'}:raise ValueError('Invalid format')
    if kind in {'text.normalize','local.extract'}:
        return {**payload,'text':text(payload.get('text'),2000)}
    if payload:raise ValueError('File capabilities accept no input payload')
    return {}


def execute(kind, payload, project, parent_results, config):
    if kind=='text.normalize':return normalize(payload['text']), {'verification':'deterministic list transformation'}
    if kind=='local.extract':
        result,metrics=Local(config['local']).generate('Extract the explicitly named items into items, without adding anything:\n'+payload['text'])
        return validate_items(result), {'verification':'schema only; semantics need review',**metrics}
    if kind=='files.inventory':
        entries=[]
        with os.scandir(project.primary_path) as paths:
            for index,p in enumerate(paths):
                if index>=512:raise ValueError('Directory exceeds 512 entries; narrow scope')
                if p.name.startswith('.') or p.is_symlink() or not p.is_file(follow_symlinks=False):continue
                s=p.stat(follow_symlinks=False)
                if s.st_nlink!=1:continue
                entries.append({'name':p.name,'bytes':s.st_size,'mtime_ns':s.st_mtime_ns})
        return {'files':sorted(entries,key=lambda x:x['name'])}, {'verification':'read-only metadata observed now'}
    if kind=='files.types':
        if len(parent_results)!=1 or 'files' not in parent_results[0]:raise ValueError('One inventory parent is required')
        counts={}
        for entry in parent_results[0]['files']:
            suffix=Path(entry['name']).suffix.lower() or '(none)';counts[suffix]=counts.get(suffix,0)+1
        return {'counts':counts}, {'verification':'deterministic aggregation of recorded inventory'}
    raise ValueError('Unimplemented capability')
