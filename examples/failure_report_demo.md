# APOS Failure / Drift Report Demo

This example shows the read-only report commands that help you decide what to do after a failure or when the workspace looks stale.

## 1. Generate a failure report

```bash
python cli/apos.py report failures --workspace . --format markdown
```

Use this when you want the recent failure summary, likely causes, affected files, and the recommended next prompt.

## 2. Inspect a single failure

```bash
python cli/apos.py report failure plan-approve-demo --workspace . --format markdown
```

Use this when you want to focus on one task id, approval item, or patch identifier.

## 3. Check for drift

```bash
python cli/apos.py report drift --workspace . --format markdown
```

Use this when the workspace may have changed after the current Context Pack was generated.

## 4. Print the next prompt

```bash
python cli/apos.py report next-prompt --workspace .
```

Use this when you want the next APOS-ready prompt without re-reading the full report.

## 5. Open the dashboard

```bash
python server/list_approvals_endpoint.py
```

The local dashboard shows the same failed item summary and drift warning banner that the report builder produces.