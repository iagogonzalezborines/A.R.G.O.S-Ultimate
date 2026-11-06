# ARGOS restoration and Stage A verification — 2026-11-06

The separate Hermes pilot is installed on the current Linux machine, with its own Codex subscription login and an **ARGOS (Hermes)** application-menu entry. The Stage A persistence blocker is repaired and the disposable native execution, isolation and interruption/recovery proof passes for the tested configuration. Persistent Projects is still off; B–D are not implemented or advertised.

This result supersedes the *current status* in the [November 5 recovery report](project-intelligence-stage-a-recovery.md), without changing that historical evidence. It is not a production migration or a claim that every existing feature has been exercised on this hardware. Firefox music still needs the signed extension from the other computer, and CPU speech is slow.

## Installation and preservation

Installation: `~/.local/share/argos-hermes-pilot`. Start it from **ARGOS (Hermes)**, or run `~/.local/share/argos-hermes-pilot/bin/argos-hermes`. No graphical-login autostart was added. The launcher opens the existing workspace and starts voice preparation. Test hosts and proof owners were stopped after validation.

Hermes remains pinned to `0073fa98cfcf61c066a919df4b336924720f8463`. Its environment was built with native `pm.build_env`, including MCP support. The desktop dependencies and Electron were installed from its npm lock. Codex `0.164.0-alpha.11.1` uses a new device login completed by the user; IDE authentication was not imported or changed. No API-key provider was introduced.

The new [source preparation script](../../../scripts/prepare_hermes_pilot.py) copies the pilot outside the development checkout, retains configuration/authentication, detects locally edited source before updating, and optionally registers the separate menu entry:

```sh
python scripts/prepare_hermes_pilot.py --register
```

This is a source installer, not an unattended dependency/model downloader. It does not start a model or enable Projects. The dependency environments, models and independent authentication described here have already been installed on this machine. A future clean-machine installation must provision those prerequisites separately.

Controller-owned `installation.json` supplies the actual user home, operational checkout, microphone, recognition interpreter and speech device. Files, storage, applications and Firefox no longer depend on `/home/tyrant`. File changes still need confirmation; the operational checkout and installed controller are protected, while the named ARGOS files workspace remains available. The original CUDA branch is retained.

All 47 tracked files under `src/argos` match the pre-work hashes. No existing capability implementation was removed. The source installer has regression coverage for updates, local source edits, private configuration/authentication preservation and rejecting installation inside the development repository.

## Speech and Firefox on this computer

The machine has a GT 1030 with 2 GB VRAM. Speech is explicitly configured for CPU while retaining Qwen3-TTS 1.7B Base, the public Peter reference and Whisper large-v3-turbo. Model and engine revisions are recorded in [restoration-2026-11-06.json](restoration-2026-11-06.json); the [CPU dependency snapshot](../voice-tests/2026-11-05/requirements-cpu-2026-11-06.txt) uses Python 3.12.15 and PyTorch/torchaudio 2.11.0 CPU wheels. These wheels require the official CPU package index when reproducing the environment.

The complete recognition, speech and Codex startup reached readiness. A fresh synthesis of “Listo.” generated 0.629 seconds of audio in **15.506 seconds** (15.519 seconds end to end). This confirms synthesis, not acceptable interactive latency or parity with the previous GPU. No smaller model or different voice was substituted. Microphone selection points to the available analog input; tests used no capture and muted playback, so live recognition and speaker quality remain unverified on this device.

Firefox native-host registration is installed. The signed `argos-media-0.1.4-firmado.xpi` was excluded from the backup, and the user confirmed it exists only on the other computer. Its source and media capability are preserved. Normal Firefox music cannot be declared restored until that signed file is copied and installed; no browser signing restrictions were bypassed.

## Stage A: native persistence repair

The root cause identified on November 5 remains valid: native owned-task launch overrides conflicted with the intended named filesystem policy, and the native worker receipt schema separately rejected its own `codex_thread_id` sidecar.

The [tested upstream patch](../project-intelligence/recovery/upstream-tested-change-2026-11-06.diff) adds only the bounded thread-binding sidecar and its regression test. It is applied to the isolated Hermes checkout, not submitted or merged upstream. The historical proposal remains unchanged. Applying the exported patch to the pinned original was independently checked against the installed files.

The binding regression failed before the repair and passes afterward. Native tests cover persistence after reopen, lost acknowledgement with idempotent receipt retry, clearing the binding, unknown/malformed keys, cross-session rejection, stale epochs, worker loss, read fences and gateway restart handoff. The patch does not grant shell access to the native database or replace Hermes's owner, claims, receipts, runs or recovery logic.

The launch adapter uses the existing `model.codex_bin` hook. The final proof configuration denies filesystem access by default, grants the disposable repository write access, exposes trusted runtime/tool paths read-only, disables command networking, and excludes controller/board/credential scopes. Apps and default plugins are disabled. The required native MCP bridge advertises only `kanban_show`, `kanban_heartbeat`, `kanban_comment`, `kanban_block` and `kanban_request_review`; those exact handoffs have explicit tool approval configuration. Worker self-completion is not advertised.

The distinction between command permissions and MCP tool controls follows the official [permissions](https://learn.chatgpt.com/docs/permissions) and [MCP configuration](https://learn.chatgpt.com/docs/extend/mcp) documentation. Actual native execution, rather than configuration text alone, supplies the evidence below.

## Actual native execution and recovery

The new disposable proof lives under the installation's `project-intelligence/recovery-2026-11-06`. It uses native Projects/Kanban records and the default native dispatcher/owner path. There is no replacement scheduler or project database.

| Check | Observed result |
|---|---|
| Authorized development | Worker created Python implementation/tests, ran unittest and compilation, posted native progress and requested review |
| Command scope | 25 positive/negative checks passed, including board/credential/controller exclusions, synthetic unrelated-project/ARGOS/IDE roots, child processes, symlink/proc escapes, IPv4/IPv6/UDP and environment filtering |
| Built-in patch tool | Patch outside the repository was rejected; `patch-positive.txt` inside the repository was created |
| Repository policy mutation | Writing `.codex/config.toml` was rejected as read-only in a separate no-inference command check |
| Interrupted execution | Controller observed task `t_e05d5d9c` running after its exclusive file creation, then stopped the native owner during the command |
| Canonical interruption | Run 6 ended with exit 130 and native owner admission settled as interrupted; it was not treated as completed |
| Controlled recovery | Reconciliation with `max_spawn=0`, explicit native unblock, then run 7 verified the existing effect and requested review |
| No repeated effect | The 13-byte marker retained its exact SHA-256 and nanosecond modification time |
| Durable records | Four tasks, eight ended runs and 68 events were identical across the final stop/restart; no open runs remained |

The [sanitized audit](../project-intelligence/recovery/verified-2026-11-06.json) records checks, task/run outcomes, marker fingerprints, restart digest and cleanup. Binding regressions and conversation-continuity tests are separate evidence: the interrupted task proof establishes native recovery from stored state and its existing artifact, not replay of a suspended instruction or a guarantee of reusing every interrupted Codex thread.

Failed attempts remain visible. Run 1 completed useful code work but its MCP handoffs were denied before the exact tool approval rules were corrected. Run 2 reached review. An obsolete `kanban.enabled=false` setting did not disable native review dispatch, causing unwanted run 3; the original task remains blocked with that history. The final harness uses the actual `dispatch_in_gateway=false`, `review_dispatch=false`, `notify_in_gateway=false` and `auto_decompose=false` settings.

The first interruption trial (runs 4–5) missed the in-flight stop and cannot prove interruption; its protocol failure and later reconciliation are retained. The second trial (runs 6–7) supplies the actual interruption evidence. Run 8 independently verified patch isolation and reached review. No failed attempt was erased or promoted based on model prose.

The source harness now exposes `run_action.py interrupt`, `trial-status`, `trial-reconcile`, `trial-unblock` and `trial-dispatch` for a deliberately prepared disposable proof. The interruption controller refuses an existing effect and checks the prepared native home. These are test controls, not production capabilities; do not run them from the archived checkout or replay an existing completed proof.

The proof owner was stopped and its three derived authentication copies removed. The main pilot login is retained. Canonical stores and disposable artifacts remain locally for inspection; credentials, raw conversations, reasoning, audio and vendor environments are not exported into this repository.

## Validation and remaining boundary

`PYTHONPATH=src python -m unittest discover -s tests -v`: **353 passed**. Native Hermes `scripts/run_tests.sh`: **63 passed across nine files**, covering the new binding regression and related transport, persistence and recovery tests. This is targeted native coverage, not a claim of running the whole Hermes test suite.

Pilot checks passed: files 25, storage/clipboard 21, research boundaries 17, startup lifecycle 10, maintenance boundaries 26, automatic diagnosis/review 8, general desktop UI 20, speech settings 10 and progressive sources 7. PCM drain/interruption used synthetic silence routed to a temporary null sink. Native conversation continuity passed two subscription turns across transport restart, with zero startup inference calls. Detailed counts are in the restoration JSON.

QA fixtures now use this machine's paths, the actual test session's speech settings, observed voice events rather than a transient subtitle, and immediate progress rather than an obsolete animation expectation. The window-drag test closes the preceding panel so the existing focus-protection behavior does not leave its target covered. No runtime UI behavior was changed to satisfy those assertions.

**Stage A outcome: verified solution for this pinned disposable configuration.** This finite proof does not certify all future repositories/tools, release Persistent Projects, or establish voice performance parity. The next development slice is B's thin native project adapter: idempotent brief/provisioning/dispatch and selective retrieval, behind the existing off-by-default feature boundary. C's generated application and D's project map/continuity are still pending. The signed Firefox extension and usable speech latency remain installation acceptance gaps.
