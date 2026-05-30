# APOS v0.1 Usability Review

Review date: 2026-05-29

## Scope

This review checks whether the stabilized v0.1 user flow feels coherent from the first context pack through prompt generation, plan handling, dashboard inspection, failure reporting, and recovery prompt generation.

The review is documentation-driven and based on the current CLI, dashboard, and docs state. No new features were added.

## Checked Flow

1. `apos context build`
2. `apos prompt build`
3. Copying or pasting the generated prompt into a web LLM
4. Creating `apos-patch` or `plan_only` examples
5. Registering approvals through Bridge Flow or manual queue entry
6. Confirming pending items in the dashboard
7. Approve / reject / run behavior for queue and plan steps
8. Failure report and recovery prompt workflow

## Findings

### 1) Windows-incompatible plan step example in USAGE

Before the latest document pass, [docs/USAGE.md](docs/USAGE.md) used a POSIX heredoc example for recording a `plan_only` payload.

That example was awkward for the primary Windows environment and could fail before the user ever reached `apos plans`.

Status: fixed in the current docs by replacing the heredoc with a PowerShell-friendly inline Python block.

### 2) Command flow is otherwise coherent

The main commands line up with the implementation:

- `python cli/apos.py context build --json`
- `python cli/apos.py prompt build --goal ... --mode patch|plan|review`
- `python cli/apos.py report failures|failure|drift|next-prompt`
- `python cli/apos.py recover prompt ...`
- `python cli/apos.py plans list|show|steps|approve-step|reject-step|run-step`
- `python server/list_approvals_endpoint.py`
- `python server/apos_server.py`

The dashboard routes documented in [docs/UI_OVERVIEW.md](docs/UI_OVERVIEW.md) match the local HTML UI and server routes.

## Improvement Candidates

- The README and usage docs could benefit from one short Windows-first note near the plan step recording example so users do not have to infer the shell requirement.
- The recovery prompt and report sections are correct, but they are dense; a short top-level flow diagram would make the sequence easier to scan.

## Immediate Documentation Correction

- Updated [docs/USAGE.md](docs/USAGE.md) to use a PowerShell-compatible plan step recording example.

## Follow-Up Work

- No code change is required for the usability issue found here.
- If a future release wants to reduce user confusion further, the next step is to add a short Windows-specific walkthrough page instead of expanding the CLI surface.

## Verification

- Full test suite: 81 passed.
- Remaining warnings: none.