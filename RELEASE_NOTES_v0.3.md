# APOS v0.3 Release Notes

## Release Summary

APOS v0.3 is the Semi-auto Recovery release.

It is not automatic recovery execution. The release automates recovery prompt preparation for failure and drift situations, but the user still reviews the generated prompt, copies it, and pastes it back into the web LLM manually.

APOS still does not bypass the approval queue, and it still does not turn recovery into auto-send, auto-approve, or auto-execute behavior.

## What Changed

- `recover prompt --mode auto` was added.
- Failure cause can now recommend `patch`, `plan`, or `review`.
- PromptBuilder output contracts are reused for recovery prompts.
- Dashboard recovery UX wording was clarified.
- Failed item and drift flows now more clearly lead into retry prompt preparation.
- The docs now state explicitly that this is not automatic execution.

## Semi-auto Recovery Scope

Allowed:

- failure/drift based recovery prompt generation
- mode recommendation
- user-copyable retry prompt output
- reuse of PromptBuilder output contracts

Not allowed:

- automatic web LLM transmission
- automatic approve
- automatic execute
- automatic retry loop
- approval queue bypass
- Web Controller integration

## Safety Boundaries

Web LLMs are the proposers.
APOS Core is the validator and executor.
The user is the approver.

v0.3 keeps that boundary intact. Recovery prompt preparation became easier, but authority did not move away from APOS Core or the human reviewer.

## CLI Changes

The following commands are now supported for recovery prompt preparation:

```bash
apos recover prompt --failure <id> --mode auto
apos recover prompt --latest --mode auto
apos recover prompt --drift --mode auto
```

Each command prepares a prompt and does not execute anything automatically.

## Dashboard Changes

The dashboard recovery UX now uses clearer wording:

- `Build LLM Retry Prompt`
- `Copy Recovery Prompt`
- `This does not auto-run or auto-approve.`

These labels are kept visually separate from approve / reject / run controls so the recovery prompt path does not look like an execution path.

## Documentation Updates

The following documents were updated for the v0.3 boundary:

- `SEMI_AUTO_RECOVERY.md`
- `USAGE.md`
- `SERVICE_OVERVIEW.md`
- `PROTOCOL.md`
- `SECURITY_MODEL.md`
- `KNOWN_LIMITATIONS.md`
- `WORKLOG.md`
- `README.md`
- `USABILITY_REVIEW_v0.3_candidate.md`

## Validation

- focused tests: 15 passed
- full pytest: 85 passed
- `USABILITY_REVIEW_v0.3_candidate.md` result: releasable-with-minor-notes

## Known Notes

A small onboarding note near the recovery section may further clarify that auto mode is recommendation-only.

This is a minor polish note, not a blocking issue.

## Release Decision

v0.3 release decision: releasable-with-minor-notes

The release is ready as a semi-auto recovery snapshot. The remaining note is small enough to leave for a later polish pass.