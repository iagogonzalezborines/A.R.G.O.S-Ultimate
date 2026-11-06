"""Controller-owned installation paths; never derived from model/tool arguments."""
import json
from pathlib import Path
import pwd
import os

PILOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PILOT / 'installation.json'
CONFIG = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
USER_HOME = Path(CONFIG.get('user_home', pwd.getpwuid(os.getuid()).pw_dir))
OPERATIONAL_ROOT = Path(CONFIG.get('operational_root', PILOT.parents[1]))
ARGOS_SRC = OPERATIONAL_ROOT / 'src'
PROTECTED_ROOTS = (OPERATIONAL_ROOT.resolve(), PILOT.resolve())
STT_PYTHON = Path(CONFIG.get('stt_python', USER_HOME / '.local/share/argos/voice-env/bin/python'))
MICROPHONE = CONFIG.get('microphone', 'alsa_input.usb-SteelSeries_SteelSeries_Arctis_Nova_5X-00.mono-fallback')

# Explicit device selection preserves the existing CUDA path on the original host.
SPEECH_DEVICE = CONFIG.get('speech_device', 'cuda')
if SPEECH_DEVICE not in {'cpu', 'cuda'}:
    raise ValueError('speech_device must be cpu or cuda')
