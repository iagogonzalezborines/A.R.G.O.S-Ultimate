# Persistent Project Intelligence — Stage A result

Recovery follow-up: [command-isolation workaround and native persistence blocker](project-intelligence-stage-a-recovery.md). Stage A remains unpassed; this original report is retained as historical evidence.

2026-11-05. **Stage A failed its command-isolation gate. Stages B–D have not started.**

The approved implementation brief explicitly requires stopping and reporting when a security/correctness gate fails. No replacement runtime, patched vendor, weaker permission mode or second project/task store has been introduced.

## What was implemented and exercised

A disposable proof lives at `../project-intelligence/proof/`. It uses pinned native Hermes revision `0073fa98cfcf61c066a919df4b336924720f8463` without tracked vendor changes.

- Created a native named Engineering profile through `create_profile` with no aliases or bundled skills, separate configuration and an isolated credential context derived only from the existing pilot login.
- Created a native Project (`p_4f3dcef6`) and named Kanban board (`argos-proof`) through native APIs, with a new disposable Git repository. No real user project was registered, modified or used as a development target.
- Used native task creation, claim/run records, typed blocking and the actual `CodexAppServerSession` / `CodexAppServerClient` initialization and command RPC.
- Configured an explicit native named command policy intended to allow repository writes, deny direct board/controller/cross-project writes and credential reads, and disable command networking.
- Configured the existing native `hermes-tools` MCP bridge with a narrow set of Kanban handoff tools. Its model-driven question/review behaviour was not relied on because the command gate failed first.
- Executed a real native command in the claimed task's repository. **No model inference turn was started.** The README was created by the test controller; it is not a Codex-generated application.

## Final boundary checks

| Check | Result |
|---|---|
| Write in authorized disposable repository | Passed |
| Write in another disposable project | Correctly denied |
| Write beside the native board database | **Not denied** |
| Write in the proof controller directory | Correctly denied |
| Open the worker credential file | **Not denied** |
| Open the Hermes profile credential file | **Not denied** |
| Open the task board database | **Not denied** |
| Open a file in operational ARGOS | **Not denied** |
| Open the IDE credential file | **Not denied** |
| Command TCP networking | Correctly denied |

The file-read probe performed `open(path, 'rb')` and `read(0)`: it proved that the file was openable, without reading or logging credential contents. Write probes used only temporary marker files inside disposable proof directories and removed them immediately. They did not modify database bytes or user files.

This is a failure of the tested worker launch/policy composition, not a claim that every Hermes deployment has the same boundary. The configured explicit exclusions were not enforced in this owned-task launch.

## Concrete native limitation

In the pinned native transport, `agent/transports/codex_app_server.py:129–136` recognizes an owned Kanban task and appends these legacy executor settings:

```text
sandbox_mode = "workspace-write"
sandbox_workspace_write.writable_roots = [<board directory>]
sandbox_workspace_write.network_access = false
```

The broad board-directory write grant corresponds directly to the successful negative write probe. In this launch, credential/filesystem exclusions from the configured named permissions profile also did not take effect: the command could open the excluded files.

The board's durable ownership must remain with native Hermes operations. A shell that can directly edit that state can bypass the intended broker/claim/review boundary. A default workspace-write filesystem with broad read access does not satisfy credential exclusion. Instruction text telling Codex not to read/edit those files is not a substitute for the missing enforced boundary.

The current ARGOS self-maintenance path previously demonstrated a different containment arrangement. That does not establish the native Kanban worker launch meets the same restrictions.

## Corrections during harness setup

The first harness attempt used a facade helper that this pin exposes through `kanban_db_connect`, and a block-reason keyword from a different API shape. Those calls were corrected against the actual pinned signatures. The initial standalone command also used the controller's working directory; setting its process working directory to the authorized repository allowed the positive write check. The negative-write check was corrected to accept the sandbox's `EROFS` denial alongside permission errors. These were test-harness corrections, not vendor changes or passed security results.

The final table above is the completed check run after those corrections. Native run history retains the earlier attempts; they are not silently presented as successful Engineering work. All three native run records are ended/blocked; there is no active execution claim. The intended implementation card is parked in triage and the scope-check card is blocked.

## State and cleanup

- The working ARGOS app's source/configuration, operational repository, IDE sessions and vendor source were not changed by this stage.
- All 152 protected operational ARGOS source hashes still match their original values.
- The three derived proof credential files were removed after the failed gate. Originals in the existing pilot/IDE stores were not deleted or edited by the controller.
- Native test records, nonsecret configuration and validation evidence remain in the isolated proof directory.
- No Engineering gateway/dispatcher service was started, no model-generated implementation was dispatched, and no worker was left running by this proof. Native app-server clients were closed after the command checks.
- The existing ARGOS app was not serving its local endpoint at the final check and its recorded desktop PID no longer existed. No application lifecycle action was taken during this proof; do not describe it as still running or infer why it closed from this evidence.

## Requested outcome status

| Area | Current result |
|---|---|
| Native Projects/Kanban record reuse | Demonstrated in disposable stores |
| Engineering initialization and actual commands | Native transport/command execution exercised; required isolation failed |
| Native dispatch/progress/questions/approval/completion | Not completed; stopped before inference at the security gate |
| Interruption/restart recovery | Not validated for the new project workflow |
| Project persistence/memory | Native records persist; project memory and cross-session execution not validated |
| Generated 3D model manager/artifacts | Not built; no claim of a completed application |
| Project Map | Not implemented |
| Existing functionality and latency | No working-app code/config changes; no new per-turn calls or project loads added. No post-integration latency claim is possible because integration was not enabled. |
| Resource impact | No added persistent project worker/service. Peak proof resources were not benchmarked. |
| Security | Gate failed; no promotion into the live app |

## Next decision

Resolve the native worker launch boundary first, then repeat Stage A from the actual owned-task path. A viable solution must preserve native Projects, Kanban claims/runs and owner recovery while enforcing the exact filesystem scope, denying credential/controller/board access to commands, and routing handoffs through the trusted native capability path.

A constrained launch-policy adapter using supported configuration hooks is a candidate to investigate, not a validated fix. The native transport's extra board-wide grant must not silently override it. If that cannot be achieved with supported extension/configuration mechanisms, return the precise upstream change required for review before modifying the vendor or choosing another execution path. Do not build B, C or D on this failed gate.

Evidence: [final command checks](../project-intelligence/proof/command-scope.json), [native record identities](../project-intelligence/proof/prepared.json), [proof preparation](../project-intelligence/proof/prepare.py), [actual command probe](../project-intelligence/proof/command_scope.py), [native owned-task launch](https://github.com/NousResearch/hermes-agent/blob/0073fa98cfcf61c066a919df4b336924720f8463/agent/transports/codex_app_server.py).
