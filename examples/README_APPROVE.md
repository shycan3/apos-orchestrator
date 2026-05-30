# APOS Approve Demo

This example shows how to record a `plan_only` envelope into the workspace history DB and approve+execute a step.

Steps (run from repo root on Windows PowerShell):

1) Create a demo workspace and copy the example plan into it. The plan references `./workspace` as a relative path.

```powershell
New-Item -ItemType Directory -Force examples_demo\workspace | Out-Null
Copy-Item examples\plan_approve_demo_plan.json examples_demo\
```

2) Record the plan into the workspace history DB.

```powershell
.\.venv\Scripts\python.exe -c "import json; from apos_core.orchestrator import Orchestrator; payload=json.load(open('examples_demo/plan_approve_demo_plan.json','r',encoding='utf-8')); workspace=payload['workspace_root']; orch=Orchestrator(workspace_root=workspace, history_db_path=f'{workspace}/.apos/history.sqlite3'); orch.recorder.record_task(payload['task_id'], payload); print('recorded', payload['task_id'])"
```

3) Approve and execute step 0.

```powershell
.\.venv\Scripts\python.exe cli\plan_approve.py plan-approve-demo --workspace examples_demo\workspace --step 0 --approved-by tester --json
```

4) Verify the file exists.

```powershell
Get-Content examples_demo\workspace\approve_demo.py
```
