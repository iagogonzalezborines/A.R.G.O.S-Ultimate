"""Run only with the isolated voice Python. JSON protocol; no microphone or playback."""
import contextlib
import json
import os
import sys
import wave
from pathlib import Path

if __package__:
    from .language import choose_language, language_command
else:
    from language import choose_language, language_command


def transcribe(whisper, path, language="auto", previous="es"):
    def decode(selected):
        segments, info = whisper.transcribe(path, language=selected, beam_size=3, vad_filter=True,
                                            condition_on_previous_text=False,
                                            hotwords="ARGOS, español, inglés, Spanish, English.")
        segments = [segment for segment in segments if segment.no_speech_prob < .7]
        text = " ".join(segment.text.strip() for segment in segments).strip()
        score = sum(segment.avg_logprob for segment in segments) / len(segments) if segments else -100
        lexical_es = choose_language(text, "es")
        lexical_en = choose_language(text, "en")
        if text and lexical_es == lexical_en:
            score += .25 if lexical_es == info.language else -.25
        if language_command(text):
            score += .5
        return text, info, score

    best = decode(None if language == "auto" else language)
    original_language, confidence = best[1].language, best[1].language_probability
    if language == "auto" and (original_language not in ("es", "en") or confidence < .9):
        # Only uncertain clips get a second local decode. No second model or network call.
        alternate = ("es" if original_language == "en" else "en") if original_language in ("es", "en") else previous
        candidate = decode(alternate)
        if original_language not in ("es", "en") or candidate[2] > best[2]:
            best = candidate
            confidence = 0.0  # A forced decode is not an acoustic language confidence.
    return {"ok": True, "text": best[0], "language": best[1].language,
            "language_probability": confidence}


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
                    response = transcribe(whisper, request["path"], request.get("language", "auto"),
                                          request.get("previous_language", "es"))
                else:
                    response = {"ok": False, "error": "Operación de voz desconocida."}
        except Exception:
            response = {"ok": False, "error": "El modelo de voz no pudo completar la operación."}
        print(json.dumps(response, ensure_ascii=False), file=output, flush=True)


if __name__ == "__main__":
    main()
