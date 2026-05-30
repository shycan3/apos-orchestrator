# APOS v0.1 Release Snapshot

APOS is a personal local orchestration layer that lets web-based LLMs such as ChatGPT or Gemini safely create, modify, and run local project files through structured JSON task envelopes.

## Core User Flow

1. Build a safe Context Pack from the current workspace.
2. Ask the web LLM for a task envelope, patch prompt, plan prompt, report prompt, or recovery prompt.
3. Validate the request locally in APOS Core.
4. Apply approved patches or run approved commands through the existing policy flow.
5. Review the result envelope, dashboard, report output, or recovery prompt summary before the next step.

## Major Features

- Task Envelope validation and execution.
- apos-patch Bridge Flow for browser-based patch approval.
- Approval Queue management for pending, approved, rejected, executed, and failed items.
- Plan Step lifecycle management through `apos plans`.
- Context Pack generation and inspection.
- Prompt Builder for patch, plan, review, and recovery prompts.
- Failure / Drift Report generation.
- Recovery Prompt Loop for paste-ready recovery prompts.
- Local dashboard for approvals and plan state.

## Security Boundary

- APOS Core remains the authority for validation, policy checks, execution, and logging.
- The web LLM only produces structured input and never receives direct filesystem access.
- Protected roots remain blocked from direct writes.
- Manual approval stays required for human-facing decision points.
- No automatic approval, no automatic execution loop, and no hidden browser automation are introduced by this release.

## Web Controller Status

External browser automation and a Web Controller are not implemented in APOS v0.1.

The only Web Controller material in the repository is [docs/WEB_CONTROLLER_EXPERIMENT.md](docs/WEB_CONTROLLER_EXPERIMENT.md), which is an experimental design note and not a shipped feature.

## Known Limitations

- Web LLMs do not receive direct automatic message forwarding from APOS.
- External browser automation and a Web Controller remain experimental future work.
- Automatic background loops are not implemented.
- Recovery Prompt Loop is manual and does not auto-send to the web LLM.
- Users still need to inspect and approve the approval queue manually.
- DOM-driven bridge flows can still drift if the target site changes.

See [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) for the full list.

## Verification

- Full test suite: 81 passed.
- Remaining warnings: none.
