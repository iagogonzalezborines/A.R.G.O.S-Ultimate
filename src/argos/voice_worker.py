"""Run only with the isolated voice Python. JSON protocol; no microphone or playback."""
import contextlib
import json
import os
import sys
import wave
from pathlib import Path


def main():
    # Downloads are an explicit setup step, never an accidental voice operation.
    os.environ["HF_HUB_OFFLINE"] = "1"
    root = Path.home() / ".local/share/argos/models"
    tts, tts_state, tts_language, whisper = None, None, None, None
    output = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        import torch
        torch.set_num_threads(2)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                if request["op"] == "synthesize":
                    from pocket_tts import TTSModel
                    language = request.get("language", "es")
                    if tts_language != language:
                        tts, tts_state = None, None
                        tts = TTSModel.load_model(language={"es": "spanish", "en": "english"}[language])
                        tts_state = tts.get_state_for_audio_prompt(str(root / f"peter-{language}.safetensors"))
                        tts_language = language
                    audio = tts.generate_audio(tts_state, request["text"])
                    pcm = (audio.detach().cpu().flatten().clamp(-1, 1) * 32767).to(torch.int16).numpy()
                    with wave.open(request["path"], "wb") as file:
                        file.setnchannels(1)
                        file.setsampwidth(2)
                        file.setframerate(tts.sample_rate)
                        file.writeframes(pcm.tobytes())
                    response = {"ok": True, "seconds": len(pcm) / tts.sample_rate}
                elif request["op"] == "transcribe":
                    from faster_whisper import WhisperModel
                    if whisper is None:
                        whisper = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=2,
                                               download_root=str(root / "whisper"), local_files_only=True)
                    segments, info = whisper.transcribe(request["path"], beam_size=3, vad_filter=True,
                                                        condition_on_previous_text=False)
                    text = " ".join(segment.text.strip() for segment in segments
                                    if segment.no_speech_prob < 0.7).strip()
                    response = {"ok": True, "text": text, "language": info.language}
                else:
                    response = {"ok": False, "error": "Operación de voz desconocida."}
        except Exception:
            response = {"ok": False, "error": "El modelo de voz no pudo completar la operación."}
        print(json.dumps(response, ensure_ascii=False), file=output, flush=True)


if __name__ == "__main__":
    main()
