Approve demo

This example shows how to record a `plan_only` envelope into the workspace history DB and approve+execute a step.

Steps (run from repo root):

1) Create a demo workspace and copy the example plan into it (the plan references `./workspace` relative path):

```bash
mkdir -p examples_demo/workspace
cp examples/plan_approve_demo_plan.json examples_demo/
```

2) Record the plan into the workspace history DB (this uses Python one-liner to call the Recorder):

```bash
python - <<'PY'
import json
from apos_core.orchestrator import Orchestrator
payload = json.load(open('examples_demo/plan_approve_demo_plan.json','r',encoding='utf-8'))
workspace = payload.get('workspace_root')
orch = Orchestrator(workspace_root=workspace, history_db_path=f"{workspace}/.apos/history.sqlite3")
orch.recorder.record_task(payload['task_id'], payload)
print('recorded', payload['task_id'])
PY
```

3) Approve and execute step 0:

```bash
python cli/plan_approve.py plan-approve-demo --workspace examples_demo/workspace --step 0 --approved-by tester --json
```

4) Verify the file exists:

```bash
cat examples_demo/workspace/workspace/approve_demo.py
```
