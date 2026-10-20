"""Explicit voice installation. Run with Python 3; uses uv and an isolated Python 3.12."""
import shutil
import subprocess
from pathlib import Path


root = Path.home() / ".local/share/argos"
uv = shutil.which("uv") or str(root / "tools/uv")
if not Path(uv).is_file():
    raise SystemExit("Instala uv primero: https://docs.astral.sh/uv/getting-started/installation/")
environment = root / "voice-env"
python = environment / "bin/python"
if not python.exists():
    subprocess.run([uv, "venv", "--python", "3.12", str(environment)], check=True)
subprocess.run([uv, "pip", "install", "--python", str(python), "torch==2.14.1+cpu",
                "--index-url", "https://download.pytorch.org/whl/cpu"], check=True)
subprocess.run([uv, "pip", "install", "--python", str(python),
                "pocket-tts==3.3.0", "faster-whisper==1.2.1", "av==16.1.0"], check=True)
subprocess.run([str(python), "-c", """
from pathlib import Path
import torch
from pocket_tts import TTSModel
from pocket_tts.models.tts_model import export_model_state
from faster_whisper import WhisperModel
torch.set_num_threads(2)
root = Path.home() / '.local/share/argos/models'
root.mkdir(parents=True, exist_ok=True)
for language, tag in [('spanish', 'es'), ('english', 'en')]:
    model = TTSModel.load_model(language=language)
    state = model.get_state_for_audio_prompt('peter_yearsley')
    export_model_state(state, root / f'peter-{tag}.safetensors')
    del model, state
WhisperModel('base', device='cpu', compute_type='int8', cpu_threads=2,
             download_root=str(root / 'whisper'))
print('Modelos de voz preparados.')
"""], check=True)
