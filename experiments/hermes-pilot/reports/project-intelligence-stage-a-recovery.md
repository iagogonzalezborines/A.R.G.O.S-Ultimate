# Stage A recovery — isolated commands work; native recovery remains blocked

2026-11-05. **Outcome B: concrete upstream blocker. Stage A has not passed; B–D remain stopped.**

The original command-isolation failure is reproduced and a supported launch-hook workaround has been exercised by a real native Kanban-owned Engineering worker. That worker could develop and test code inside its authorized repository. A second, independent defect in the pinned Hermes worker-persistence contract prevents accepting this as a working native execution/recovery integration. No vendor patch or operational deployment was made.

## Root cause of the original failure

Pinned Hermes revision: `0073fa98cfcf61c066a919df4b336924720f8463`.

In [the native transport](https://github.com/NousResearch/hermes-agent/blob/0073fa98cfcf61c066a919df4b336924720f8463/agent/transports/codex_app_server.py), an owned Kanban task adds legacy `sandbox_mode="workspace-write"`, a board-directory writable root, and disabled command networking. These settings override the intended named filesystem policy in the tested binary. Workspace-write's broad reads and the additional board write grant explain the original results. This was not command execution accidentally going through a different ARGOS runtime.

The [official permissions documentation](https://learn.chatgpt.com/docs/permissions) describes named permissions and legacy sandbox settings as alternative systems. It also distinguishes command permissions from MCP, apps and other capability controls. The experiment below establishes the behaviour of this actual pinned integration rather than relying on that documentation alone.

The no-inference [ablation](../project-intelligence/recovery/ablation.json) used the native App Server client and synthetic private files:

| Launch | Result |
|---|---|
| Named policy, no owned-task overrides | 14/14 command-scope checks passed |
| Same policy, native owned-task overrides | Board read/write and excluded private reads were allowed; network remained denied |
| Owned-task launch through fixed policy adapter | 14/14 checks passed; effective legacy sandbox fields were absent |

These ablation runs diagnose configuration composition. They are not the native dispatcher end-to-end gate.

## Small supported adapter, without a new runtime

[launch_policy.py](../project-intelligence/recovery/launch_policy.py) is selected using Hermes's existing `model.codex_bin` configuration hook. It launches the unchanged Codex executable and leaves native Hermes responsible for projects, task claims, worker admission, runs, receipts and reconciliation.

The proof adapter removes conflicting permission overrides, reapplies a fixed named policy from a controller-owned file, disables command networking and hosted web search, strips the command environment to a small allowlist, and uses repository-local home/temp/cache directories. Its effective policy denies the filesystem by default, then grants the project write access and the trusted tool/runtime paths read access. Controller, board and credential paths remain excluded. The protected scope-probe script is read-only to commands.

The adapter also disables Codex apps and default plugin activation. Those controls matter independently of shell isolation. The proof's only configured MCP server is the native Hermes bridge, with five enabled tools: `kanban_show`, `kanban_heartbeat`, `kanban_comment`, `kanban_block`, and `kanban_request_review`. Worker self-completion is not advertised. These apps/plugin controls were completed after run 2; the final hardened configuration was inventoried without a new owned inference turn, because the native persistence gate had already failed.

The first actual inference attempt lacked the optional `mcp` package in the existing environment. This was a proof setup error, not an upstream impossibility: `mcp==2.3.0`, matching the vendor lock, and its dependencies were installed into a separate proof-only target. Explicit MCP environment configuration supplies that target and the isolated Hermes home. `required=true` makes a missing bridge a startup failure. The subsequent [actual App Server MCP inventory](../project-intelligence/recovery/mcp-surface.json) lists exactly those five tools, no `codex_apps` server, and no startup error. **No further model turn was dispatched after the persistence defect was identified.** Consequently this inventory is not evidence of a successful model-driven review handoff.

## Actual native owned-task execution

The proof used native project `p_9f1177bb`, board `secure-proof`, task `t_f644a56a`, and a disposable repository under `project-intelligence/recovery/`. Native `dispatch_once` used its default spawn path, which submitted the task to the native profile owner. `owner_admitted`, `worker_bound`, claim and heartbeat events identify the real task-owned execution. No custom spawn implementation, scheduler or agent loop replaced it.

There were two attempts:

1. Run 1 failed before inference because the initial proof policy hid the Codex executable. The overlapping ancestor denials were removed in favour of a default deny with explicit grants. The base config was corrected as well, avoiding stale merged policy entries. Native unblock/retry retained the failed run.
2. Run 2 started a real Codex subscription turn. It ran the protected scope probe, wrote `proof_value.py` and `test_proof_value.py`, and ran unittest and compilation. The rollout, native events and independently checked artifacts substantiate those operations. It did not claim to have performed the unavailable native review handoff.

The [executed-turn evidence](../project-intelligence/recovery/native-execution-evidence.json) contains the scope result extracted from the actual Codex rollout, not just a worker-editable result file. All **25 scope checks** passed in that real turn:

| Boundary | Evidence |
|---|---|
| Authorized repository | File creation/read succeeded; model-created Python code and tests work |
| Board database | Direct open denied; board-directory write denied |
| Credentials | Separate synthetic Hermes and Codex credential files could not be opened; credential-directory writes denied |
| Controller | Existing synthetic controller file unreadable; protected controller-directory write denied |
| Other project, operational ARGOS, IDE | Separate synthetic roots denied for both reads and writes |
| Escape attempts | Symlink and `/proc/.../root` access denied; child interpreter inherited the boundary |
| Network | IPv4 TCP, IPv6 TCP and UDP denied |
| Environment | Synthetic secret variable absent from command environment |

Credential probes used synthetic files; the recovery worker was not directed to read real IDE/provider credentials. The board probe opened the actual disposable board database with `read(0)`, proving denial without extracting records.

Independent host verification found unchanged canary hashes, an unchanged protected probe, no prohibited host marker files, and passing unittest/compilation for the generated artifacts. Their hashes are in [final-audit.json](../project-intelligence/recovery/final-audit.json).

One harness distinction is retained explicitly: creating a file in a synthesized ancestor directory succeeded inside the sandbox namespace, but no file appeared at that host path. The corrected controller-write check targets the actual excluded controller subtree; existing controller files are tested separately. This is not presented as a denied syscall for every virtual ancestor location.

These results establish command isolation and ordinary development in the tested launch. They do **not** certify all built-in file-edit tools, future repository configuration changes, tool handoff authorization, or successful execution recovery. Those remain release-gate work.

## New blocker: the native receipt contract rejects its own Codex binding

The actual run reached `agent/codex_runtime.py`, which publishes the durable `codex_thread_id` after committing projected messages. It calls `WorkerSessionDB.patch_session_model_config`, sending a native `worker.persist` operation of `session.sidecars`.

However, [hermes_state_worker_context.py](https://github.com/NousResearch/hermes-agent/blob/0073fa98cfcf61c066a919df4b336924720f8463/hermes_state_worker_context.py) allows only `_usage_anchor`, `_proactive_prune_rearm_tokens`, and `_anthropic_rejected_thinking` in `SIDECAR_KEYS`. `codex_thread_id` is absent. The owner therefore returns `invalid_params`.

The real worker's pending durable journal retains sequence 35, operation `session.sidecars`, patch key `codex_thread_id`, value type string. [upstream-blocker.json](../project-intelligence/recovery/upstream-blocker.json) records this structural evidence without copying its authentication scope. [diagnose_blocker.py](../project-intelligence/recovery/diagnose_blocker.py) reproduces the same rejection with a synthetic thread ID against the unmodified pinned validator, without inference.

`WorkerSessionDB` retains the failed pending receipt and failure flag. Later persistence/lease cleanup therefore cannot finish normally. The native owner recorded `worker_lost: managed_worker_failed`, the submitter reported an unknown owner outcome, and the native dispatcher ultimately recorded a crashed attempt and parked the task as blocked. A successful worker command/result exit code did not override that canonical failure.

This is distinct from the initial missing MCP dependency and from the command-sandbox policy. Repairing those configurations does not change the closed native sidecar schema.

## Minimal upstream change for review

[upstream-change-proposal.diff](../project-intelligence/recovery/upstream-change-proposal.diff) is a proposed patch only; **it has not been applied**. It adds the single `codex_thread_id` sidecar key and validates its value as a bounded nonempty string or `None` for clearing. Existing authenticated execution/session ownership checks, receipt ordering and transactional persistence remain intact. Arbitrary metadata keys stay forbidden.

Before accepting that change, upstream validation must exercise:

- a real managed Codex worker publishing its thread binding and finishing its receipt stream;
- owner restart and legitimate task-owned continuation using that binding;
- clearing an invalid binding through the native fallback;
- rejection of unknown keys, malformed values, stale executions and cross-session mutations;
- interruption with one native writer and no replayed effects;
- model-driven native progress/block/review handoffs with the corrected MCP setup.

The existing `test_codex_app_server_thread_resume.py` exercises direct `SessionDB` persistence with a wire stand-in. It does not establish that the managed worker's closed receipt schema accepts that same binding.

The supported launch hook fixes process configuration; it cannot extend the owner's hardcoded persistence allowlist. MCP configuration cannot repair `WorkerSessionDB`'s receipt stream either. An external OS sandbox would not repair this native contract. Dropping the failed receipt/thread binding, giving shell direct database access, or resuming the transcript as unrestricted chat would sacrifice requirements rather than solve the defect. No supported hook resolving that contract was found in the pin. This is the concrete reason an upstream change is now needed.

An optional separate native transport improvement would stop adding the legacy board-wide shell grant when a named policy is selected. The proof adapter already avoids that conflict, so this is not the remaining persistence blocker.

## Recovery, preservation and cleanup

After the failed turn, only the disposable proof owner was stopped and restarted through native lifecycle APIs. The blocked task, two ended run records and 19 events were unchanged; no new attempt or inference was started. [Before](../project-intelligence/recovery/native-before-restart.json) and [after](../project-intelligence/recovery/native-after-restart.json) snapshots match. This demonstrates durable record preservation, **not successful interrupted execution recovery**.

The proof owner was stopped again. No proof child remained at final inspection, no task claim/run remained active, and the three derived proof credential copies were removed. [Cleanup evidence](../project-intelligence/recovery/cleanup.json) records removal and the isolated MCP dependency versions. Native stores, sanitized evidence and generated disposable artifacts remain for review. No parallel ARGOS-owned project/task store, agent runtime or persistent worker service was introduced; the disposable stores use the native Hermes APIs.

All 152 operational ARGOS source hashes still match the saved baseline; pinned Hermes has no tracked changes. No operational ARGOS source/config was edited or restarted, no IDE session was controlled, and no original authentication store was written by the controller. The existing ARGOS local endpoint was unreachable at final inspection; its absence was not used as permission to restart it.

**Next action:** review the bounded native persistence change, then repeat Stage A through the real owned-task path. Until the complete security, handoff and recovery gates pass, there is no promotion to ARGOS and no work on B–D.
