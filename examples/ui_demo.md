# APOS UI Demo

This walkthrough shows the minimal browser dashboard for approvals and plan steps.

## 1. Start the dashboard server

```bash
python server/list_approvals_endpoint.py
```

The server listens on `http://127.0.0.1:8082`.

## 2. Open the dashboard

Open one of these routes in a browser:

```text
http://127.0.0.1:8082/
http://127.0.0.1:8082/ui
http://127.0.0.1:8082/ui/approvals
http://127.0.0.1:8082/ui/plans
```

## 3. Point the UI at your workspace

Use the workspace field in the top bar and set it to the project you want to inspect.

Examples:

```text
.
/path/to/project
C:/Users/DO/Documents/apos-orchestrator
```

If the server requires `APOS_APPROVE_TOKEN`, paste the token into the token field before refreshing.

## 4. Inspect approvals

The Approvals section shows:

- `id`
- `type`
- `status`
- `target`
- `created_at`
- `decided_at`

Use the buttons to approve or reject a queue item, or open the detail panel to view the original payload and the latest result summary.

## 5. Inspect plans

The Plans section shows:

- `task_id`
- plan summary
- step count
- latest status

Open a plan to inspect each step, then use the buttons to approve, reject, or run a step.

## 6. What happens behind the UI

The dashboard calls the local JSON endpoints under `/api/*` and routes every action through the same APOS policy code that the CLI uses.

That means:

- it does not edit SQLite directly
- it does not bypass plan step rules
- it does not bypass approval checks
- it does not reveal protected file bodies

For the written overview of the UI routes, see [docs/UI_OVERVIEW.md](../docs/UI_OVERVIEW.md).
