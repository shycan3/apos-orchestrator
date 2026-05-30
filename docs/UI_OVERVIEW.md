# APOS UI Overview

APOS includes a minimal local dashboard for reading approval queues and plan step state in a browser.

The dashboard is served by `server/list_approvals_endpoint.py` and the HTML view is stored in `server/approvals_ui.html`.

## Entry Points

Open one of these routes after starting the dashboard server:

```text
http://127.0.0.1:8082/
http://127.0.0.1:8082/ui
http://127.0.0.1:8082/ui/approvals
http://127.0.0.1:8082/ui/plans
```

## JSON Endpoints

The UI reads and acts through same-origin JSON endpoints:

- `GET /api/dashboard`
- `GET /api/approvals`
- `GET /api/plans`
- `POST /api/approvals/approve`
- `POST /api/approvals/reject`
- `POST /api/plans/approve-step`
- `POST /api/plans/reject-step`
- `POST /api/plans/run-step`

## What It Shows

Home / Dashboard:

- pending approvals count
- failed items count
- recent executed items
- recent plan summaries
- failed item cards with failure summary, likely cause, affected files, and recovery prompt copy action
- failed item cards also note that the full recovery prompt lives in the detail panel
- drift banner plus recovery guidance when the workspace looks stale

Approvals:

- id
- type
- status
- target
- created_at
- decided_at
- approve / reject buttons
- detail panel with stored payload, latest result summary, failure summary, stdout/stderr/exit code, recommended human action, and recovery prompt textarea + copy button
- recovery prompt panel copy text that makes the manual fallback explicit

Plans:

- task_id
- title / summary
- step count
- status summary
- step list with approve / reject / run actions
- step result summary

## Safety

- The UI does not write to SQLite directly.
- Actions go through `Orchestrator` and `PlanStepManager` policy paths.
- Protected file content is not shown as raw source.
- If `APOS_APPROVE_TOKEN` is set, paste the token into the dashboard token field before refreshing.

## When To Use It

Use the dashboard when you want a quick browser view of:

- pending approvals
- failed plan steps
- recent executed steps
- current plan status

Use the CLI when you want repeatable scripted actions or automation-friendly output.
