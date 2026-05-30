# APOS v0.2 Candidate Usability Review

Review date: 2026-05-29

## Scope

This review checks whether the Dashboard Recovery UX introduced after the v0.1 snapshot feels natural in the real user flow.

The review is intentionally documentation-first. No new feature was added.

## Checked Flow

1. Dashboard home with failed items present.
2. Drift banner visibility when the workspace looks stale.
3. Failed item cards and whether the failure summary is understandable.
4. Approval / detail view and recovery prompt textarea visibility.
5. Copy-button fallback to manual textarea copy when clipboard access fails.
6. Recovery prompt handoff back into the APOS flow through the existing recovery prompt commands and dashboard guidance.
7. Whether approve / reject / run remain visually distinct from recovery guidance.

## Findings

### 1) The recovery path is now coherent

The dashboard home, approval detail panel, failure report, and recovery prompt loop now form a readable sequence:

- dashboard home shows failed item count and drift warning state
- failed item cards show a short failure summary, likely cause, and affected files
- approval detail shows failure detail, stdout/stderr/exit_code, recommended human action, and a recovery prompt textarea
- copy actions are available, but the textarea remains the manual fallback

That makes the recovery path understandable without introducing auto-retry or auto-send behavior.

### 2) The main usability constraint is intentional

The UI still separates "review" from "action":

- home cards are summary-first
- the full recovery prompt lives in the detail panel
- approve / reject / run buttons remain visibly separate from the recovery prompt controls

This is the right boundary for APOS v0.2 candidate because it avoids collapsing recovery guidance into execution.

### 3) Early empty-dashboard state is fine

When no failure exists yet, the dashboard home correctly shows zero failed items and no failed-item cards.

That is not a bug; it simply means the recovery UI becomes visible only after a failure or drift signal exists.

## Problems Discovered

- No blocking usability defect was found in the current Dashboard Recovery UX.
- The only thing that can still feel slightly indirect is that the full recovery prompt is in the approval detail panel, not inline in the home card.

## Immediate Documentation / Wording Adjustments

- [docs/UI_OVERVIEW.md](docs/UI_OVERVIEW.md) now describes the failed-item cards, drift banner, and recovery prompt textarea/copy behavior.
- [docs/SERVICE_OVERVIEW.md](docs/SERVICE_OVERVIEW.md) now explains the dashboard recovery UX as a read-only helper built on `report_builder` and `recovery_prompt_builder`.
- [docs/USAGE.md](docs/USAGE.md) now points users from failure report review to the recovery prompt preview path.
- [README.md](README.md) now includes a short note that failed item cards provide a copyable recovery prompt preview.

## Follow-Up Items

- A future release could add a short one-line hint near the failed-item cards saying that the full recovery prompt is available in the detail panel.
- If the dashboard ever grows more controls, the recovery controls should stay visually separated from approve / reject / run.
- No browser automation or auto-retry should be added as part of that follow-up.

## Release Verdict

APOS v0.2 candidate is releasable from a usability standpoint.

Reason:

- The recovery path is understandable.
- The dashboard state and failure details are now discoverable.
- The manual fallback remains explicit.
- No regression appeared in approve / reject / run behavior.
- The test suite still passes at 81 passed.

## Verification

- Narrow dashboard / failure / recovery tests: passed.
- Full pytest: 81 passed.
- Remaining warnings: none.