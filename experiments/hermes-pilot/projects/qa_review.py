"""Real Electron review controls with a disposable native registry; no audio."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

P = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(P),str(P/'ui-workbench')]
import server
from runtime.workspace_broker import WorkspaceBroker,Files
from runtime.projects import Projects

with tempfile.TemporaryDirectory(prefix='argos-project-review-') as temporary:
    root=Path(temporary);(root/'repositories').mkdir()
    config=root/'installation.json'
    config.write_text(json.dumps({'projects_enabled':True,'pilot_root':str(P),
        'operational_root':str(root/'protected'),'project_roots':[str(root/'repositories')],
        'project_state':str(root/'native')}))
    broker=WorkspaceBroker(server.publish,server.validate,files=Files({'QA':root}),socket_path=root/'broker.sock')
    broker.projects=Projects(lambda intent:broker.intent(intent,wait=False),config_path=config)
    broker.serve()
    host=server.ThreadingHTTPServer(('127.0.0.1',42722),server.Handler)
    host.workspace=broker;host.voice=None
    token=P/'ui-workbench/private/presentation.token'
    token.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not token.exists():
        import secrets
        token.write_text(secrets.token_urlsafe(32));token.chmod(0o600)
    host.token=(P/'ui-workbench/private/presentation.token').read_text().strip()
    thread=threading.Thread(target=host.serve_forever,daemon=True);thread.start()
    try:
        result=subprocess.run(['node',str(P/'projects/qa_review.cjs'),str(root)],timeout=90)
        if result.returncode:raise SystemExit(result.returncode)
    finally:
        host.shutdown();host.server_close();broker.close()
