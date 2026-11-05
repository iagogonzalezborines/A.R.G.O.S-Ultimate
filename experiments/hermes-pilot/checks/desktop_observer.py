"""Read-only presentation hook for the pinned Hermes native Codex transport.

No model loop or transcript storage. Hermes keeps the authoritative lifecycle;
the original event callback always receives every event unchanged.
"""
from urllib.parse import urlsplit

def observe_session(agent,emit):
 session=getattr(agent,'_codex_session',None)
 if session is None or getattr(session,'_argos_observed',False):return
 original=session._on_event
 def callback(note):
  try:
   params=note.get('params') or {};method=note.get('method');item=params.get('item') or {}
   if method in {'item/started','item/completed'} and item.get('type')=='contextCompaction':
    emit({'event':'context.compaction','stage':'started' if method=='item/started' else 'completed'})
   if method=='item/completed' and (item.get('type')=='webSearch' or item.get('type')=='extension' and item.get('kind')=='web.search'):
    sources=[{'url':r['url'],'title':r.get('title') or urlsplit(r['url']).hostname or 'Source'} for r in (item.get('results') or [])[:12] if isinstance(r,dict) and isinstance(r.get('url'),str) and isinstance(r.get('title',''),str)]
    if sources:emit({'event':'web.sources','sources':sources,'provenance':'native_search_results'})
    action=item.get('action') or {};url=action.get('url')
    if action.get('type')=='openPage' and isinstance(url,str) and len(url)<=2000:
     emit({'event':'web.source','url':url,'title':urlsplit(url).hostname or 'Source','provenance':'native_open_page_completed'})
   if method=='thread/tokenUsage/updated':
    usage=params.get('tokenUsage') or {}
    emit({'event':'context.usage',**{k:usage[k] for k in ('last','modelContextWindow') if k in usage}})
  finally:
   if original:original(note)
 session._on_event=callback;session._argos_observed=True
