# Isolated ARGOS / Hermes pilot

See the [decision, measurements and comparison](reports/M1-pilot.md).

This directory is independent of `/home/tyrant/Proyectos/argos`. Hermes source is pinned; no migration is installed. The offline General profile still selects Gemini without a provider key. The desktop voice app explicitly uses native Hermes Codex App Server with the isolated subscription login. Its Linux menu entry and graphical-login autostart are installed. Credentials are private and must not be pasted into reports or chat.

The native gateway, memories and session DB belong to Hermes. `pilot.py` supplies environment/filesystem containment and a restricted external capability broker. It is not another agent runtime. `checks/` contains test controllers, not product orchestration.

Run the offline native gateway using:

```sh
python /home/tyrant/.local/share/argos-hermes-pilot/pilot.py run
```

This is a JSON-RPC stdio server, not the operational ARGOS voice console. If broker tools are needed, start the pilot broker in another terminal first:

```sh
python /home/tyrant/.local/share/argos-hermes-pilot/pilot.py broker
```

The broker can read/propose changes only in the disposable fixture. A model cannot approve its own proposal. No production approval UI is provided by this pilot.

Repeat the meaningful offline integration checks with:

```sh
python /home/tyrant/.local/share/argos-hermes-pilot/checks/validate.py
```

Repeat the bounded native Desktop/SDK/HUD check with:

```sh
python /home/tyrant/.local/share/argos-hermes-pilot/checks/desktop_run.py
```

Run checks sequentially; do not start another gateway while Desktop owns the same Hermes home. The Desktop check opens temporary pilot windows and closes its own process group afterwards. General inference remains unavailable until a provider is configured deliberately. The empty `credentials/gemini.key` is only a prepared private input location; it is not automatically injected or loaded by the offline launcher.

Live Codex tests were run using native Hermes interfaces and subscription authentication. They consume subscription quota and should not be automatically repeated. See the report for the exact evidence and configuration used. Test scripts default to the pilot paths and disposable project; they must not be repointed at real projects without a new scope and permission review.


## ARGOS app

Open **ARGOS** from the Linux application menu, or run `python /home/tyrant/.local/share/argos-hermes-pilot/ui-workbench/launch.py`. Once preparation finishes, say **Argos** using the SteelSeries Arctis Nova 5X microphone; follow-up conversation does not require Space. Closing the app stops its microphone, audio workers and presentation host. The app is registered for graphical user login; an actual reboot has not been tested.

This is a general conversation workspace: no automatic research demo, start-research button, permanent chat input or sidebar. Click the ARGOS circle for contextual windows and speech controls. The microphone control really stops capture; the visible speaker button and **Silenciar voz** control spoken output, while the music-note control only controls interface chimes. A muted speaker is highlighted. Speech preferences are stored by the audio backend, independently of stale browser settings and QA sessions. You can also say “Argos, turn your voice on” or “Argos, activa tu voz”. Drag window titles to move, lower-right corners to resize; use their buttons to minimize, maximize or close. Alt+A arranges windows and F11 toggles fullscreen.

Native Hermes owns conversation history and session recovery. The voice app uses `gpt-6-luna / low` through Codex App Server and the separate pilot subscription login. Actual hosted web search opens real results and cited sources in the workspace. Local Qwen/Peter speech now generates continuous PCM for each completed public message, preserving sentence boundaries inside one utterance. It uses a pinned streaming implementation with compiled codebook prediction and CUDA decoder graphs, with both decoder phases warmed before microphone readiness. The cylinder animation appears only when an actual process starts, not while answering an ordinary question.

ARGOS can now inspect and control its actual workspace through native MCP tools: open, close, focus, minimize, restore, maximize, move, resize and arrange windows. Summaries and videos receive larger areas; cited sources and process status stay compact. Actual video pages and direct videos open inside the app. Site-specific ads, sign-in, consent or playback restrictions can still require interaction; opening a panel is not proof of playback.

Choose **Archivos** from the circle menu, or ask ARGOS to open/find a file. The explorer covers Personal (your visible home files), Proyectos, Descargas, Documentos, Escritorio, a separate ARGOS working folder and accessible mounted data volumes. It searches filenames, exposes the selected file to ARGOS, previews text/images and extracts PDF text. Text can be edited in its document window. Select a regular file and use **Copiar** or Ctrl+C; choose a destination folder and use **Pegar** or Ctrl+V. The ARGOS file clipboard is internal to this app. Direct user paste creates a non-overwriting copy; same-folder paste chooses a new copy name. Agent paste and other proposed file changes open a concrete review window; the agent cannot approve its own proposal. Copies stream binary data and support files larger than the former 1 MiB limit. Existing destinations are never overwritten automatically. Directory copying is not implemented. Hidden/credential files, symlink escapes and writes to operational ARGOS are excluded. This is a bounded initial explorer, not a universal viewer or CAD editor.

**Discos y particiones** opens the actual Linux storage inventory. ARGOS can query device capacity, filesystem, mount state and mounted-filesystem free space. Unmounted partitions remain visible with unknown free space; this version does not mount/unmount, format or modify partitions. Mounted data volumes can open in the explorer; the Linux system partition's file button opens Personal. Virtual swap is distinguished from physical storage.

Say **“Clear the workspace”** or **“Limpia el espacio de trabajo”** to close all internal windows, including minimized windows and embedded browsers. This preserves disk files and keeps ARGOS running. Exact common clear commands use a local presentation route to avoid a model round trip; the native workspace tool also exposes `clear` for other phrasing. Clear cancels a delayed process-panel opening and suppresses late automatic research panels from an older presentation generation.

The new streaming engine avoids a separate full-WAV generation at every full stop. First PCM arrived around 0.3 s from synthesis start in the warm benchmark; model/recognition time remains additional. The first compilation can take tens of seconds and happens during preparation. Exact short responses can reuse a bounded private audio cache; the cache does not generate or replace the model's wording.

Music requests use the `media` tool and your **normal Firefox**, retaining its accounts, appearance and installed blocker. The native bridge verifies that the selected YouTube video advances with sound enabled and no ad active at the check. Permanent ad-free playback is not guaranteed by a blocker. ARGOS Media Bridge 0.1.4 is now Mozilla-signed and installed permanently in the normal Firefox profile; it does not need a public store listing or temporary loading. The native bridge connection was verified. A backup is in `/home/tyrant/Descargas/argos-media-0.1.4-firmado.xpi`; install that signed file through Add-ons and themes → gear → Install Add-on From File if reinstalling. Keep audio/video autoplay allowed specifically for YouTube. An actual browser restart/reboot after this installation has not been tested. Workspace browser panels retain their separate session for other content. No browser cookies or passwords are imported into Electron.

Recognition now uses local CUDA Whisper large-v3-turbo with automatic Spanish/English selection, warmed before listening. Research acknowledges dispatch promptly, narrates actual search/delivery stages, opens selected sources during the work and puts the detailed report in a large window. The native agent supplies a separate complete spoken conclusion. Pending old progress is replaced, and clearing the workspace blocks late research panels from that turn. Synthetic recognition and warm latency evidence are in the latest pilot report; live microphone accuracy and variable subscription-provider latency remain practical limits.

ARGOS can now launch supported installed Linux apps through a fixed executable catalogue (Firefox, VS Code/Code OSS, Dolphin, Calculator, Discord, Steam, mpv and qView when installed). Simple English/Spanish launch requests use a local route. App-internal automation, engineering project execution, CAD and printer operations are not connected to this adapter. This isolated app does not replace operational ARGOS. See the latest follow-up in [the pilot report](reports/M1-pilot.md) and [current implementation summary](ui-workbench/reports/general-app-summary.json) for evidence and remaining limits.


The circle menu now includes **Desarrollo y autolog**. You can say “Argos, abre desarrollo y autolog”, “Argos, revisa el autolog” or request a concrete ARGOS improvement. Native Codex programs and executes commands in an isolated candidate while conversation stays available. The panel shows native command events, validation limits and the actual diff. Click **Aprobar actualización y reiniciar** only for the change you want; rejection preserves the running source. Approval applies after app shutdown, restarts and checks readiness; failed startup restores the backup. Installed changes offer **Restaurar versión anterior y reiniciar**. Generic voice yes and model tool calls cannot approve a release.

New internal voice/renderer failures are logged with redacted diagnostics and may prepare a bounded automatic candidate, at most three per day with a ten-minute cooldown. Installation always waits for your concrete review. Self-development currently covers the controller's listed existing pilot UI/voice/contract files. Host-wide shell access, package installation, new application modules and changes to the release/permission controller are outside that source scope. Native sessions remain the history owners. See the latest pilot report for actual disposable rollback tests and the untested production-update-cycle limit.


At app startup ARGOS now initializes its own Codex app-server and subscription thread before enabling conversation. VS Code can remain closed. No test conversation or model inference is generated during that preparation. The agent panel shows actual Codex readiness. Local speech may still need model loading/compilation; startup state and errors distinguish Codex, recognition and speech. Startup failures close the owned workers before reporting an error. Authorization denials in autolog are explained as protections and do not offer a repair action. The latest startup evidence and limits are in the pilot report.


Research now displays the native search result feed as soon as each search finishes, before the model publishes its selected citations or final report. Its compact loading panel distinguishes found results, selected sources and opened page windows; it has an indeterminate bar while the true total is unknown. The first result page can open immediately from native metadata; later model selections append and reuse the same URL rather than reloading it. Four browser views remain the limit, existing user pages are preserved, and clearing the workspace suppresses late opens. Found results are not claims of source endorsement or verified page load.

Only the current focused/selected workspace observations accompany a conversation turn; other windows can be inspected with the workspace tool when relevant. The interaction contract gives clear new topics priority and preserves genuine follow-ups/corrections. Existing native history and memory remain intact. Idle-triggered compression is explicitly off; necessary native Codex compaction remains enabled and its actual events/context usage are measured. There is no new memory or task owner. Evidence and test scope: [progressive desktop summary](ui-workbench/reports/progressive-desktop-summary.json).
