# Working on ARGOS

Read README.md and docs/architecture.md before changing the runtime.
This is a new Linux foundation, not a recovered copy of the Windows 0.6.9 code.
Historical requirements are in ../argos-recuperacion; current user decisions
take precedence.

- Keep the Core independent of presentation, providers and platform adapters.
- No extra model call just for routing, acknowledgement or Persona.
- Agents request registered capabilities; Core owns authorization and evidence.
- Never claim work started/completed based on model prose alone.
- Task affinity belongs to a task, not a global specialist mode.
- A disconnected console must not cancel background work.
- No raw credentials, audio or model reasoning in prompts, SQLite or logs.
- Never enable an unimplemented capability in the advertised registry.
- Preserve explicit scope, idempotency and recovery without effect replay.
- Linux normal console contains voice feedback only; diagnostics use CLI commands.
- Model or provider changes, installation of large models, printer actuation
  and activation of a new executable must be deliberate, reviewable operations.
- Test with `PYTHONPATH=src python -m unittest discover -s tests -v`.
- No tests should play through the user's speakers or change real projects.

Runtime agent instructions are in src/argos/contracts. This file governs
development; it is not silently injected as the assistant's personality.
