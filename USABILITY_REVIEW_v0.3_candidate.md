# APOS v0.3 Candidate Usability Review

Review date: 2026-05-29

## Scope

This review checks whether the semi-auto recovery flow feels natural in the real user path, while still staying clearly non-automatic.

The review is intentionally documentation-first and flow-first. No new feature was added.

## Review Criteria

The review checks the following:

- the CLI supports the documented `recover prompt` flows
- `--mode auto` stays advisory and does not imply execution
- failure-cause mode recommendations remain conservative and sensible
- dashboard wording separates prompt preparation from approve / reject / run controls
- the recovery prompt continues to follow the patch / plan / review output contracts
- CLI usage examples and docs match the actual command surface

## Checked Flow

1. `recover prompt --failure <id> --mode auto`
2. `recover prompt --latest --mode auto`
3. `recover prompt --drift --mode auto`
4. Failure-cause mode recommendation coverage for:
   - `invalid_envelope`
   - `policy_denied`
   - `command_denied`
   - `protected_path`
   - `missing_file`
   - `stale_context_possible`
   - `patch_conflict`
   - `test_failed`
   - `execution_failed`
   - `unknown`
5. Dashboard wording for `Build LLM Retry Prompt`
6. Visual separation between `Copy Recovery Prompt` and approve / reject / run controls
7. Recovery prompt output contracts for patch / plan / review modes
8. CLI and documentation alignment

## CLI Usability Review

The CLI flows are understandable in practice.

- `recover prompt --failure <id> --mode auto` is present and behaves as a recommendation helper
- `recover prompt --latest --mode auto` still produces a reviewable prompt even when no recent failure is found
- `recover prompt --drift --mode auto` keeps the same read-only posture and does not act like an execution command
- the generated prompt clearly remains something the user copies back into the web LLM manually

## Dashboard Usability Review

The dashboard wording is now clear enough to avoid execution confusion.

- failed item cards are still visible and lead into recovery guidance
- `Build LLM Retry Prompt` reads like a preparation step rather than a run step
- `Copy Recovery Prompt` is visually separate from approve / reject / run controls
- the recovery textarea remains in the detail panel instead of blending into the action buttons
- `This does not auto-run or auto-approve.` closes the main ambiguity gap

## Recovery Prompt Output Contract Review

The recovery prompt still preserves the mode-specific output contract.

- patch mode still requires a single `apos-patch` block and keeps diffs out of the prompt
- plan mode still asks for independently reviewable, step-based work with execution split from change steps
- review mode still forbids file-edit JSON and asks for analysis plus a follow-up prompt suggestion
- the prompt text still tells the user to review before copying it back to the web LLM

## CLI and Docs Alignment

The command line examples and the written docs match the implementation.

- `cli/apos.py recover prompt --help` shows `--mode {auto,patch,plan,review}`
- the docs mention `--mode auto` as advisory only
- the dashboard wording matches the current UI labels
- the protocol and security docs still forbid auto-send, auto-approve, and auto-execute

## Findings

### 1) The semi-auto path is understandable

The current flow is easy to follow:

- failure or drift is detected
- APOS prepares a recovery prompt
- `--mode auto` recommends patch / plan / review based on failure shape
- the user still reviews and copies the prompt manually

That is a natural step up from the earlier manual-only recovery loop without becoming automatic recovery.

### 2) The mode recommendations are sensible for the intended boundary

The current recommendation set matches the stated policy well:

- `invalid_envelope` -> `review`
- `policy_denied` / `protected_path` -> `review`
- `command_denied` -> `plan`
- `missing_file` / `stale_context_possible` -> `review`
- `patch_conflict` -> `patch` or `plan` depending on context
- `test_failed` / `execution_failed` -> `plan`
- `unknown` -> `review`

That keeps the system conservative when the root cause is unclear and only becomes more actionable when the failure shape is explicit.

### 3) The dashboard wording no longer looks like execution

The label change to `Build LLM Retry Prompt` is a good compromise. It tells the user that APOS is preparing a follow-up prompt, not running one.

The detail panel copy note also helps:

- `Copy Recovery Prompt`
- `This does not auto-run or auto-approve.`

That makes the prompt-preparation step visually separate from the approval controls.

### 4) The prompt contract is still explicit enough

The recovery prompt continues to include the expected sections for patch, plan, and review modes.

The important point is that the prompt still asks the user to make the final human decision before sending anything back to the web LLM.

## Problems Discovered

- No blocking usability defect was found in the current semi-auto recovery flow.
- The only remaining usability risk is conceptual, not functional: users unfamiliar with APOS may still need one sentence of onboarding before they trust that `auto` means recommendation only, not execution.

## Immediate Documentation / Wording Adjustments

- [docs/SEMI_AUTO_RECOVERY.md](docs/SEMI_AUTO_RECOVERY.md) already describes `--mode auto` as advisory and prompt-preparation only.
- [docs/USAGE.md](docs/USAGE.md) already states that `--mode auto` only recommends a mode and does not transmit or execute anything.
- [docs/SERVICE_OVERVIEW.md](docs/SERVICE_OVERVIEW.md) already says the flow does not auto-send to the web LLM.
- [docs/PROTOCOL.md](docs/PROTOCOL.md) already frames `--mode auto` as a recommendation helper only.
- [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) already says auto recommendation is advisory and must be reviewed by a human.
- [server/approvals_ui.html](server/approvals_ui.html) already uses `Build LLM Retry Prompt`, `Copy Recovery Prompt`, and `This does not auto-run or auto-approve.`

## Follow-Up Items

- A future pass could add one short inline onboarding sentence near the recovery section header explaining that `auto` means mode recommendation only.
- If APOS later adds more recovery shortcuts, they should keep the prompt preview and the approval controls visually separate.
- No automatic send, approval, or execution should be added as part of that follow-up.

## Release Verdict

APOS v0.3 candidate is releasable-with-minor-notes from a usability standpoint.

Reason:

- The semi-auto recovery path is understandable.
- The auto recommendation boundary is still explicit.
- The dashboard wording does not imply automatic execution.
- The recovery prompt still preserves patch / plan / review contracts.
- The test suite passes.
- One short onboarding sentence near the recovery section header would reduce the remaining conceptual risk.

## Verification

- Focused recovery / prompt / dashboard tests: passed.
- Full pytest: 85 passed.
- Remaining warnings: none.