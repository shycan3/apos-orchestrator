# APOS Recovery Prompt Demo

This walkthrough shows how to generate a paste-ready recovery prompt from the current workspace history.

## 1. Generate a recovery prompt for the latest failure

```bash
python cli/apos.py recover prompt --latest --workspace . --output recovery_prompt.md --copy
```

This is the normal path after a recent failure or plan-step failure when you want a ready-to-paste Markdown prompt.

## 2. Recover from a specific failure

```bash
python cli/apos.py recover prompt --failure patch-failure --workspace .
```

Use this when you already know the failure id from the report or dashboard.

## 3. Recover from drift

```bash
python cli/apos.py recover prompt --drift --workspace .
```

Use this when the workspace may have changed since the current Context Pack was generated.

## 4. Recover from a plan step failure

```bash
python cli/apos.py recover prompt --plan-step plan-recover-demo 0 --workspace .
```

Use this when a specific `plan_only` step failed and you want a safe follow-up prompt.

## 5. Override the recommended mode

```bash
python cli/apos.py recover prompt --latest --workspace . --mode review
```

The recovery builder still shows the recommendation, but this lets you force a different output mode when needed.