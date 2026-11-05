# ARGOS voice auditions — 5 November 2026

Local listening page: <http://127.0.0.1:42705>. The server is loopback-only. Playback is manual and only one sample plays at once. The native HTML audio player supports seeking through HTTP byte ranges. No microphone capture or automatic speaker playback is used.

This is a voice audition, not an operational ARGOS migration. Conversational model tests were deferred when the user selected **voice samples first**. No Ministral/Gemma model was downloaded or enabled. Existing ARGOS code/configuration, its voice environment, native Hermes runtime source and active Codex sessions were not modified.

## Listening progression

1. Pocket TTS Peter: existing ARGOS voice, same English/Spanish models and voice embeddings.
2. Pocket TTS Alba: alternate public preset, for a female comparison.
3. Peter variant B: same preset/phrases, temperature 0.45 instead of the English default 0.3. This is a sampling variation, not a demonstrated naturalness improvement.
4. Qwen3-TTS VoiceDesign: original male/female designs, then mature British-style designs using instructions. The video speaker was not cloned.
5. Qwen3-TTS Base: acoustic conditioning using the public original Peter Yearsley recording. Full reference conditioning and speaker-embedding-only conditioning are compared. This recording is **not Paul Bettany**.

The user's initial preference was Peter in English, with slightly less robotic delivery desired. The user subsequently preferred Qwen's naturalness, but found its initial voice too young. The instruction-only mature British designs still sounded American to the user. The current target is a mature, experienced British male delivery, closer in character to Paul Bettany's JARVIS. Therefore the next comparison changes the method to audio-conditioned generation rather than declaring another text prompt successful.

## Comparable material

All listening reels use the same three utterances per language in `phrases.json`: presence, dry situational wit, serious operation status. They are synthetic reading examples, not claims of executed actions. Pocket reels concatenate three individually synthesized utterances with 650 ms presentation gaps. Qwen designs synthesize the full passage in one call. Raw phrase files are retained for Pocket.

No pitch-shifting, speed changes, denoising or post-generation voice effects were applied. Do not infer a model quality ranking from waveform amplitudes or voice gender. The static waveform in each web card is computed from its real audio. The same wording helps compare pronunciation and delivery; it does not establish long-session conversational behavior.

## Runtime and pinned inputs

- Existing Pocket TTS 3.3.0 runs in CPU with two Torch threads. Public caches and voice states were copied to this test directory; new preset downloads use private paths. Peter's existing `.safetensors` voice states and the alternate Alba states are separate per language.
- Qwen uses a separate Python 3.12 environment under `qwen-env/`, Torch/Torchaudio 2.11.0 + CUDA 12.8, BF16 and native PyTorch SDPA. The Qwen package is pinned to upstream commit `022e286b98fbec7e1e916cb940cdf532cd9f488e` (package 0.1.1). `qwen-requirements.lock.txt` records installed versions.
- VoiceDesign revision: `5ecdb67327fd37bb2e042aab12ff7391903235d3`.
- Base revision: `fd4b254389122332181a7c3db7f27e918eec64e3`. The speech codec was reused only after the pinned repository trees matched.
- Peter reference source/revision is in `peter-reference-source.json`. Its separate reference text differs from the test passage. The audio is from Kyutai's public Pocket voice collection, not from a movie actor.
- Synthesis uses local weights with Hugging Face/Transformers offline settings after explicit downloads. These flags are not an OS network sandbox. No paid speech API or subscription was enabled.

## Measurements and limits

Pocket produced the first audio chunk in approximately 77 ms at the median across the initial twelve utterances, after model loading. Median generation time/audio duration was approximately 0.23. These are native synthesis timings, **not** microphone-to-first-sound or live ARGOS latency. They exclude playback buffering, speech recognition and conversation generation.

The initial Qwen VoiceDesign calls generated 11–17 seconds of audio in approximately 12–22 seconds; the median real-time factor was about 0.95. The mature designs had a median factor about 0.94. GPU allocations were about 4.1–4.3 GiB, with allocator reservations up to about 4.8 GiB. First-call effects and concurrent downloads/CPU work make these preliminary measurements, not a controlled performance benchmark.

The official `generate_voice_design`/`generate_voice_clone` calls used here return completed waveforms. First streaming-audio latency was **not measured** for Qwen. Playing completed WAV files in the web page does not validate real-time synthesis. Streaming/optimization and coexistence with a local conversational model on the same 8 GiB GPU remain separate gates.

VoiceDesign generates each passage from a description; a stable speaker identity across independently generated passages/languages is not guaranteed by that test. The acoustic-reference experiment addresses this more directly. British pronunciation and perceived age require human listening review; user feedback already rejected the first instruction-only British attempts. Whisper transcripts are automatic content checks, not proof of accent, naturalness or exact wording. In particular, the Spanish mature-design A transcript contains suspicious recognition differences and needs listening review.

## Acoustic-reference results

Both Base variants completed in English and Spanish and are available on the same listening page as **Qwen + Peter · Referencia** (audio and transcript conditioning) and **Qwen + Peter · Identidad** (speaker embedding only). Native generation took 11.22–13.95 seconds for 11.36–14.56 seconds of audio; median generation/audio factor was 0.977. Peak allocated CUDA memory was 4434 MiB, reserved up to 4988 MiB. These measurements do not establish live first-audio latency.

Offline Whisper recovered the full English passage in both variants. The Spanish full-reference transcript showed several suspicious recognition differences, including the opening and the sentence about final versions; the Spanish identity-only variant was substantially closer in the automated check. Human listening is still required. No claim is made that either variant sounds like Bettany or that the rejected accent has been resolved.

Final local validation found 18 ready listening reels with mono PCM16 audio and working HTTP byte-range playback. All 152 protected ARGOS source hashes still match the baseline. No operational voice was changed.

## Artifacts

- `outputs/`: individual WAVs and listening reels.
- `*-metrics.json`: native measurements, seeds and actual voice-conditioning instructions.
- `*-transcripts.json`: offline Whisper checks.
- `user-preference.json`: latest explicit feedback for this audition; not production assistant memory.
- `feedback.json`: optional voice selection made in the page.
- `validation.json`: WAV/HTTP checks and ARGOS source protection comparison.
- `scripts/serve_auditions.py`, `web/dist/index.html`: local audition UI. The server exposes only allowlisted audio, its page/manifest and the audition selection endpoint, not model caches or credentials.

References: [Pocket TTS](https://github.com/kyutai-labs/pocket-tts), [Qwen3-TTS native API](https://github.com/QwenLM/Qwen3-TTS/tree/022e286b98fbec7e1e916cb940cdf532cd9f488e), [Pocket voice collection](https://huggingface.co/kyutai/tts-voices).

## User selection

The user selected **Qwen + Peter · Referencia**, English (`qwen-peter-reference`, `en`), in the listening page and confirmed the choice in chat. This is the preferred audition candidate. Operational integration is still pending; short-turn consistency and first-audio latency need validation before changing ARGOS. The source remains Peter Yearsley, not Paul Bettany.


## Character/context listening tests

After the user approved conversation testing, 125 native Codex/Hermes transport turns exercised obvious versus sincere questions, fiction/exceptions, banter-to-serious transitions, quoted/hypothetical/negated commands, ambiguous follow-ups, language switching, project observations, corrected facts, two-object 15-turn history, native thread recovery and new-thread isolation. Pilot-only contract revisions corrected a colour/finish recall error. Some wit remains forced, and one acknowledgement remains overly long; no universal personality score is claimed.

Eight actual replies from the final focused run have Qwen + Peter reference audio at <http://127.0.0.1:42705/character>. Text completion in that run had median 2.15 seconds. Completed audio generation had median 6.25 seconds across the eight selected replies (median duration 6.44 seconds); no live or streaming first-audio timing was established. English ASR recovered the final words in all six English clips. Spanish clips show content/pronunciation differences and need listening review. The UI preserves the original favorite choice.

See `character-voice-metrics.json`, `character-audio-checks.json`, `character-web-checks.json`, and [the measured evaluation summary](../../reports/character-2026-11-05/summary.json). This follow-up does not connect a microphone, modify operational ARGOS or establish durable model-managed memory.
