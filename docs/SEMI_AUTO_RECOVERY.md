# APOS Semi-auto Recovery Design Memo

APOS v0.3 candidate: semi-auto recovery is the smallest possible step between the current manual Recovery Prompt Loop and any future automation.

The goal is not automatic recovery. The goal is to make recovery prompt preparation feel more direct while keeping review, copy, approval, and execution fully human-controlled.

## Purpose

Semi-auto recovery should reduce the friction between a failure signal and a paste-ready recovery prompt.

It should help the user get from:

```text
failed item -> recovery report -> recovery prompt -> manual paste into web LLM
```

to a slightly shorter path:

```text
failed item -> prepared recovery prompt -> manual review/copy -> manual paste into web LLM
```

v0.3 최소 구현 후보는 `--mode auto`로 failure cause를 보고 patch / plan / review 중 하나를 추천한 다음, Prompt Builder 규칙이 들어간 recovery prompt를 더 빠르게 만드는 것이다.

## Current Recovery Prompt Loop

Today APOS already supports a manual recovery flow:

`--mode auto` only recommends the recovery prompt mode; it does not send, approve, or execute anything automatically.

- `apos recover prompt` can derive a prompt from the latest failure, a specific failure id, drift, or a plan-step failure
- `RecoveryPromptBuilder` reuses `PromptBuilder` and `ReportBuilder`
- the dashboard can show failure summaries, likely cause, affected files, and a copyable recovery prompt
- the user still has to review and copy the prompt before pasting it into the web LLM

That is a strong baseline, but it is still a manual loop.

## What Semi-auto Recovery Means

Semi-auto recovery means APOS may prepare recovery material more proactively, but it does not act on the user's behalf.

Allowed automation:

- choose a recommended recovery mode from the failure shape
- prepare a paste-ready recovery prompt from the latest failure signal
- prefill or surface the prompt in the dashboard detail panel
- copy prompt text to the clipboard only when the user explicitly asks
- keep the prompt format aligned with Prompt Builder rules
- make the dashboard wording clearly say that the recovery prompt is a preparation step, not an execution step

Forbidden automation:

- auto-send the prompt to the web LLM
- auto-approve any approval item
- auto-execute any patch or command
- bypass the approval queue
- create a Web Controller path
- hide uncertainty behind a forced retry

## Safety Boundary

Semi-auto recovery must stay inside the same APOS trust boundary as the current recovery flow.

- APOS may generate guidance, not authority
- the web LLM remains the proposal author only
- the human remains the sender, reviewer, and approver
- recovery prompts remain read-only artifacts until the user copies them
- execution policy still belongs to APOS Core and the existing approval flow

## Failure Mode Mapping

Recommended default behavior by failure shape:

- patch conflict, missing file, or single-file edit issue -> `patch`
- command failure, test failure, or multi-step repair -> `plan`
- drift, protected-path conflict, invalid envelope, or unclear root cause -> `review`
- plan-step failure -> `plan`

This recommendation should stay advisory. It should not auto-switch the user into execution.

## CLI Candidates

Possible v0.3 CLI shapes, in increasing ambition:

1. `apos recover prompt --failure <id> --mode auto`
2. `apos recover prompt --latest --mode auto`
3. `apos recover prompt --failure <id> --mode patch|plan|review`

Current implementation direction:

- `--mode auto` selects the mode from the failure cause using the recovery builder
- explicit `patch|plan|review` still overrides the recommendation when the user wants a fixed target mode

In this memo, `auto` should mean automatic recommendation selection only, not automatic execution.

## Dashboard UX Candidates

The dashboard can make the recovery path more obvious without becoming an auto-runner.

Possible labels and actions:

- `Build LLM Retry Prompt`
- `Open Recovery Prompt`
- `Copy Recovery Prompt`
- `Review Failure Detail`

The UI should include a short note like: `This does not auto-run or auto-approve.`

The dashboard should continue to show the full prompt in the detail panel and keep the approval queue separate from recovery guidance.

## v0.3 Minimal Scope

If APOS v0.3 implements only one small step, it should be this:

- make recovery prompt preparation more explicit and more discoverable
- keep mode recommendation advisory only
- keep manual copy/paste as the final step
- keep the existing report and prompt builders as the source of truth

## Deferred To Later Versions

These items should stay out of v0.3:

- automatic transmission to the web LLM
- automatic approval or rejection
- automatic execution or rerun loops
- Web Controller implementation
- background recovery retries
- multi-step autonomous repair orchestration

## Design Check

If a future change removes the need for the user to review or copy the recovery prompt, it has crossed the line from semi-auto recovery into auto recovery and should be rejected for v0.3.