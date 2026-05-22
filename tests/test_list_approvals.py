import tempfile
from pathlib import Path
import uuid

from apos_core.orchestrator import Orchestrator


def test_list_approvals_returns_recorded_approvals():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        history_db = workspace / ".apos" / "history.sqlite3"
        orch = Orchestrator(workspace_root=str(workspace), history_db_path=history_db)

        task_id = "list-approvals-test"
        # record an approval
        approval_id = str(uuid.uuid4())
        orch.recorder.record_approval(approval_id, task_id, 0, "unittest", {"note": "ok"})

        approvals = orch.list_approvals(task_id)
        assert isinstance(approvals, list)
        assert any(a.get("id") == approval_id for a in approvals)

        try:
            orch.stop()
        except Exception:
            pass
