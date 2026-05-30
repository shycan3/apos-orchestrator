# APOS Plan Step Demo

This tutorial shows the standard `plan_only` flow with the canonical `apos plans` CLI.

It assumes you already have the project virtual environment active and a workspace available.

## 1. Record a plan-only task

Use the existing demo payload and record it into the workspace history DB.

```bash
python - <<'PY'
import json
from apos_core.orchestrator import Orchestrator

with open('examples/plan_approve_demo_plan.json', 'r', encoding='utf-8') as handle:
    payload = json.load(handle)

workspace = payload['workspace_root']
orch = Orchestrator(workspace_root=workspace, history_db_path=f"{workspace}/.apos/history.sqlite3")
orch.recorder.record_task(payload['task_id'], payload)
print(payload['task_id'])
PY
```

Save the printed `task_id`. The rest of the tutorial uses that value.

For the bundled demo payload, the recorded task id is `plan-approve-demo` and the workspace root is `./workspace`.

## 2. Inspect the plan

List recorded plans:

```bash
python cli/apos.py plans list --workspace ./workspace --json
```

Show one plan:

```bash
python cli/apos.py plans show plan-approve-demo --workspace ./workspace --json
```

Show the step list:

```bash
python cli/apos.py plans steps plan-approve-demo --workspace ./workspace --json
```

## 3. Approve or reject a step

Approve step 0:

```bash
python cli/apos.py plans approve-step plan-approve-demo 0 --workspace ./workspace --approved-by alice --json
```

Reject step 1:

```bash
python cli/apos.py plans reject-step plan-approve-demo 1 --workspace ./workspace --rejected-by bob --reason "not needed" --json
```

## 4. Execute a step

Run the approved step:

```bash
python cli/apos.py plans run-step plan-approve-demo 0 --workspace ./workspace --approved-by alice --json
```

The command returns a result envelope. Look for:

- `status`: `success`, `failed`, or `skipped`
- `exit_code`
- `meta.plan_step_index`
- `meta.command_results`

## 5. Understand rerun policy

- `pending` or `rejected` steps do not execute and return `skipped`.
- `executed` or `failed` steps do not rerun unless you pass `--force`.
- Invalid `task_id` or invalid step index values cause the CLI to fail.

## 6. Optional wrappers

If you already have a plan file and want to run one step directly, use the compatibility wrapper:

```bash
python cli/plan_step.py /path/to/plan.json --step 0 --json
```

If the plan is already recorded in history and you want the approval-and-run wrapper:

```bash
python cli/plan_approve.py plan-123 --workspace /path/to/project --step 0 --approved-by alice --json
```

The same flow is covered by [tests/test_plan_management.py](../tests/test_plan_management.py).