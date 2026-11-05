"""Summarize measured runs and review findings, without treating tone as a Boolean test."""
from pathlib import Path
import hashlib
import json
import statistics

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT.parents[1]
REPORTS = PILOT/'reports/character-2026-11-05'
old = json.loads((ROOT/'character.json').read_text())
audio = {(x['run'],x['scenario'],x['turn']):x for x in old['turns'] if x.get('audio_file')}
audio_checks = json.loads((ROOT/'character-audio-checks.json').read_text())
turns, cohorts = [], {}
for file in sorted(REPORTS.glob('*.jsonl')):
    rows = [json.loads(line) for line in file.read_text().splitlines()]
    for row in rows:
        row['run'] = file.stem
        if row['scenario']=='context_corrections' and row['turn'] in (2,4):
            row['checks']['no_reintroduced_old_colour'] = 'gris' not in row['response'].casefold()
            if row['turn']==2:
                row['checks']['acknowledges_latest_colour'] = 'azul' in row['response'].casefold()
        key = (row['run'],row['scenario'],row['turn'])
        if key in audio:
            for field in ['audio_file','synthesis_seconds','spoken_text','estimated_serial_text_and_synthesis_seconds']:
                row[field] = audio[key][field]
            if row['scenario']=='context_corrections':
                row['audio_review_note'] = 'La transcripción automática presenta diferencias en español. Revisa la pronunciación al escuchar; el texto y la voz se evalúan por separado.'
        turns.append(row)
    cohorts[file.stem] = dict(turns=len(rows), median_text_complete_seconds=statistics.median(x['seconds'] for x in rows),
        median_first_public_text_seconds=statistics.median(x['first_text_seconds'] for x in rows if x['first_text_seconds'] is not None),
        failed_automatic_controls=[dict(scenario=x['scenario'],turn=x['turn'],failed=[k for k,v in x['checks'].items() if not v])
                                   for x in rows if not all(x['checks'].values())],
        error_count=sum(bool(x['error']) for x in rows),tool_iterations=sum(x['tool_iterations'] for x in rows),
        contract_sha256=rows[0]['contract_sha256'])
baseline = json.loads((PILOT/'reports/argos-source-before.json').read_text())
source = Path('/home/tyrant/Proyectos/argos')
changes = [name for name,digest in baseline.items() if not (source/name).is_file() or hashlib.sha256((source/name).read_bytes()).hexdigest()!=digest]
assert not changes, changes
voice = json.loads((ROOT/'character-voice-metrics.json').read_text())
report = dict(date='2026-11-05', timezone='Europe/Madrid', model='gpt-6-luna', reasoning_effort='low',
    runtime='Unmodified Hermes CodexAppServerSession native transport, pinned pilot installation',
    authentication='Existing isolated pilot ChatGPT subscription login; no API key or paid API fallback enabled',
    total_turns=len(turns), cohorts=cohorts,
    method='Sequential conversational turns within separate native threads per scenario; native thread resume after closing transport. Rubrics and expected facts stay outside prompts.',
    contract_scope='Existing ARGOS personality section copied, with an explicit native-pilot binding. Core JSON routing/task/permission sections are not advertised as working native Hermes tools.',
    reviewed_findings=[
      'Baseline copied the exact sky-green illustration from the original contract. Removing examples reduced that scripted imitation but also weakened the desired wit on that input.',
      'Baseline and revision retained an obsolete grey colour inside the finish after a colour correction. Initial keyword checks missed this; stricter checks and independent-attribute instructions were added.',
      'Calibrated focused run corrected both the immediate colour acknowledgement and later final recall.',
      'Native long-context tests exercised two fictional objects, intervening questions, corrections and transport restart. This is within-thread history recovery, not proof of durable cross-session memory curation.',
      'The user subsequently accepted the other audition answers, response times and the branding punchline. The disliked part was the unsolicited storm-warning clause. The irony-v2 contract separates the ordinary answer/dry aside from meaningful exceptions and was tested in ten additional turns.',
      'Serious loss and beginner questions caused a serious explanatory response rather than continued banter. Ordinary copper question remained a direct factual answer.',
    ],
    voice=dict(candidate='Qwen + Peter · Referencia', samples=len(voice),
        median_complete_waveform_seconds=statistics.median(x['generation_seconds'] for x in voice),
        median_audio_duration_seconds=statistics.median(x['audio_seconds'] for x in voice),
        median_generation_to_duration_ratio=statistics.median(x['generation_seconds']/x['audio_seconds'] for x in voice),
        peak_cuda_allocated_mib=max(x['peak_cuda_allocated_mib'] for x in voice),
        first_streaming_audio_seconds=None,
        content_check=f"{sum(x['language']=='English' for x in voice)} English recordings have offline ASR content checks. Both Spanish recordings show recognition/pronunciation differences and need listening review; this is not proof of a hardware playback fault.",
        automatic_transcripts=str(ROOT/'character-audio-checks.json')),
    latest_user_feedback=json.loads((ROOT/'user-preference.json').read_text()).get('character_feedback'),
    limitations=[
      'Synthetic text-driven scenarios, not microphone/wake-word/interrupt/echo tests or live audible-ending validation.',
      'No real app/file/project/printer operations were executed. Tool intentions and conversation honesty are reviewed; this is not a new Tool Broker security audit.',
      'Uses native Hermes transport, not a fresh complete AIAgent/gateway/desktop/end-to-end comparison. Local LLM quality and model-driven Hermes memory recall are untested here.',
      'Focused reruns reuse previously reviewed examples; they are regressions, not unseen heldout evidence. No statistical tone score or guaranteed token/quota savings.',
      'Latency is a small uncontrolled host/provider sample. Voice and text were timed separately; summed values are estimates, not measured live conversation latency.',
      'Qwen returns completed waveforms in this implementation. Streaming and coexistence with an on-GPU conversational model remain unvalidated.',
      'Length thresholds are diagnostic checks, not output truncation or proof of quality. Human review found failures that the original automatic checks missed.',
    ],
    protection=dict(source_files_checked=len(baseline),argos_source_changes=changes,operational_voice_changed=False),
    usage_note='Per-turn last-request usage counters are stored with public answers. No account billing/quota measurement is inferred.',
    references=['https://learn.chatgpt.com/docs/app-server','https://learn.chatgpt.com/docs/auth'])
(REPORTS/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
(ROOT/'character.json').write_text(json.dumps(dict(summary=f'{len(turns)} turnos medidos · {len(voice)} respuestas con voz · Codex gpt-6-luna, esfuerzo bajo · Personalidad en evaluación; ARGOS operativo sin cambios.',turns=turns),ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
