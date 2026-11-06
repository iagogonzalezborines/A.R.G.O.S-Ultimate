# Isolated ARGOS / Hermes pilot — source snapshot

Source and reviewed evidence exported from the separate local pilot on 2026-11-05. This directory does not replace, migrate or activate the operational ARGOS runtime in `src/argos`.

The desktop pilot includes the electric-blue workspace/window manager, bilingual hands-free conversation, streaming speech adapters, incremental research, files/storage, app launch, Firefox media integration and reviewed maintenance tooling. Sources are preserved here so that the work is versioned independently of the installation under `~/.local/share/argos-hermes-pilot`.

**2026-11-06: the pilot is installed locally and the isolated Stage A proof passes with a tested native persistence patch.** Persistent Project Intelligence remains off; B–D have not started. The signed Firefox extension is still on the other computer, and retaining the existing voice models on CPU introduces substantial latency. The original November 5 reports remain historical evidence.

- [Current installation, Stage A result and remaining limitations](reports/restoration-2026-11-06.md)
- [November 5 Stage A recovery blocker](reports/project-intelligence-stage-a-recovery.md)
- [Original Stage A evidence](reports/project-intelligence-stage-a.md)
- [Project intelligence architecture](reports/project-intelligence-proposal.md)
- [Pilot implementation history](reports/M1-pilot.md)
- [Local installation notes](LOCAL-NOTES.md)
- [File provenance and hashes](snapshot-manifest.json)

## Layout

| Directory | Contents |
|---|---|
| `ui-workbench/` | Desktop shell, presentation host, voice/workspace/file adapters and QA source |
| `ui-workbench/dist/` | Handwritten HTML/CSS/JavaScript used by this pilot; included despite the historical directory name |
| `checks/` | Native integration probes and voice/personality contract sources |
| `maintenance/` | Existing isolated candidate, review, install and rollback controller sources |
| `integrations/firefox-media/` | Readable ARGOS Media Bridge 0.1.4 source; signing/install state is not exported |
| `project-intelligence/` | Disposable Stage A harnesses, synthetic fixtures, sanitized evidence, original proposal and tested upstream patch |
| `config-templates/` | Nonsecret configuration and first-party plugin templates; not active runtime state |
| `voice-tests/` | Audition harnesses, selected-voice metadata, public reference provenance and dependency lock; no audio or model weights |

## Restoration boundary

The source installer `scripts/prepare_hermes_pilot.py` (at the repository root) materializes a separate installation and preserves local configuration and edits. It does not download dependencies/models, authenticate or launch the app. Current runtime paths come from controller-owned `installation.json`; historical evidence retains its original paths. Do not run proof setup scripts directly from this checkout against an existing installation: they provision disposable stores and derive isolated credentials deliberately. Read the scope in their reports first.

Restore into a separate pilot root after reviewing the local notes and paths. Obtain Hermes from `https://github.com/NousResearch/hermes-agent.git` at commit `0073fa98cfcf61c066a919df4b336924720f8463`, then reproduce the pinned tool/dependency environments described in the reports. The streaming speech adapter additionally requires its pinned external engine and local Qwen/Whisper models. Voice reference metadata records the public Peter source revision without redistributing its audio. Authentication must be established separately in the isolated homes.

Credentials, native session/memory/task databases, browser profiles, private worker journals, raw conversation/agent logs, audio/video, screenshots, models, executables, environments, caches and vendor checkouts are excluded. Historical reports may reference local measurements/media that are not part of this source export; those references are not installation requirements or claims of new verification.

No app launch, installation, model inference or vendor patch application occurs by checking out this snapshot. The Stage A harness scripts are retained as experimental test controllers, not a new runtime or scheduler.
