"""Trusted controller helper for presentation-only intents. Reads one JSON object from stdin."""
import json
from pathlib import Path
import sys
import urllib.request

ROOT=Path(__file__).resolve().parent
intent=json.load(sys.stdin)
token=(ROOT/'private/presentation.token').read_text().strip()
request=urllib.request.Request('http://127.0.0.1:42720/api/presentation',json.dumps(intent).encode(),
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
with urllib.request.urlopen(request,timeout=5) as response:print(response.read().decode())
