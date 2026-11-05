"""One authoritative preference for speech output, separate from interface chimes."""
import json
import os
from pathlib import Path
import tempfile

class SpeechSettings:
 def __init__(self,path):self.path=Path(path)
 def enabled(self):
  try:
   value=json.loads(self.path.read_text()).get('speech_enabled')
   return value if type(value) is bool else True
  except (OSError,ValueError,AttributeError):return True
 def save(self,enabled):
  if type(enabled) is not bool:raise ValueError('Speech preference must be a boolean')
  self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
  fd,temp=tempfile.mkstemp(prefix='.speech-',dir=self.path.parent)
  try:
   with os.fdopen(fd,'w') as stream:
    json.dump({'version':1,'speech_enabled':enabled},stream);stream.write('\n');stream.flush();os.fsync(stream.fileno())
   os.replace(temp,self.path)
  finally:
   try:os.unlink(temp)
   except FileNotFoundError:pass
