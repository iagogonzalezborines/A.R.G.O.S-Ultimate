"""Sanitized test-process launcher. Leaves native task/owner lifecycle to Hermes."""
import os,subprocess,sys
from pathlib import Path
H=Path(__file__).resolve().parent;P=H.parents[1];sys.path.insert(0,str(P))
from pilot import environment
e=environment();e.update(HOME=str(H/'home'),HERMES_HOME=str(H/'native'),HERMES_KANBAN_HOME=str(H/'native'),CODEX_HOME=str(H/'codex'),HERMES_QUIET='1',ARGOS_SECRET_CANARY='SYNTHETIC_ENV_SECRET')
r=subprocess.run([str(P/'env/bin/python'),str(H/'native_control.py'),*sys.argv[1:]],env=e,cwd=H/'repository')
raise SystemExit(r.returncode)
