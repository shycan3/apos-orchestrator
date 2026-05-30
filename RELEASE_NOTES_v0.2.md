# APOS v0.2 Release Snapshot

APOS v0.2 is the Recovery-aware Dashboard release: the same local orchestration core, now with a dashboard that makes failure review, drift awareness, and recovery prompt handoff easier to inspect.

## v0.1 to v0.2

Compared with v0.1, this snapshot keeps the same execution and approval model, but improves how users move from a failure to a recovery decision.

The core behavioral changes are in the dashboard recovery UX and its supporting documentation:

- failed item cards now summarize failure state more clearly
- drift warnings are surfaced at the top of the dashboard
- approval detail now exposes a recovery prompt textarea and copy action
- approve / reject / run remain separate from recovery guidance
- automatic retry is still not part of the system

## Dashboard Recovery UX

The dashboard now makes the recovery path easier to follow:

- failed item card
- drift banner
- approval detail recovery prompt textarea
- recovery prompt copy button

The dashboard still stays read-only with respect to data storage and execution policy. It only presents information that comes from `report_builder` and `recovery_prompt_builder`.

## Core User Flow

1. Open the dashboard and inspect pending approvals, failed items, and drift warnings.
2. Open a failed item card or approval detail.
3. Review the failure summary, likely cause, affected files, stdout/stderr/exit_code, and recommended human action.
4. Copy the recovery prompt textarea if you want to paste it back into the web LLM.
5. Use the existing `report`, `recover prompt`, `plans`, and approval commands as needed.

## Security Boundary

- APOS Core remains the source of truth for validation, approval, and execution.
- The dashboard does not modify SQLite directly.
- The dashboard does not auto-approve, auto-execute, or auto-retry anything.
- Protected path contents remain hidden from raw display.
- Secret-like values remain masked through the existing report and prompt builders.

## Web Controller Status

Web Controller support is still not implemented.

The only Web Controller material in the repository remains [docs/WEB_CONTROLLER_EXPERIMENT.md](docs/WEB_CONTROLLER_EXPERIMENT.md), which is an experimental design note only.

## Known Limitations Summary

- Recovery Prompt Loop is still manual.
- Failed item cards may not inline the full recovery prompt on the home surface; the full textarea lives in the detail panel.
- The user still needs to inspect and decide whether to use patch, plan, or review mode.
- External browser automation remains experimental future work.
- Automatic background loops remain out of scope.

See [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) for the longer list.

## Usability Review

The v0.2 candidate usability review judged the release releasable.

Result:

- releasable

## Verification

- Full test suite: 81 passed.
- Remaining warnings: none.
