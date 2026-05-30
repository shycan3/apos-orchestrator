"""Recorder: simple SQLite-backed history of tasks and results."""
from __future__ import annotations

import sqlite3
import json
import time
from typing import Optional, Union
from pathlib import Path


class Recorder:
    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        # Normalize to Path and ensure parent exists
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path.cwd() / ".apos_history.sqlite3"

        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Use string path for sqlite3
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._ensure_tables()

    def _ensure_tables(self):
        c = self._conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                created_at REAL,
                payload TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                timestamp REAL,
                exit_code INTEGER,
                stdout TEXT,
                stderr TEXT,
                meta TEXT,
                snapshot_id TEXT,
                snapshot_commit TEXT,
                policy_blocked INTEGER,
                blocked_reason TEXT,
                patch_blocked INTEGER,
                patch_blocked_reason TEXT,
                patch_preview TEXT,
                result_envelope TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS suggestions (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                timestamp REAL,
                suggestion TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                step_index INTEGER,
                approved_by TEXT,
                timestamp REAL,
                meta TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS approval_items (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                patch_id TEXT,
                item_type TEXT,
                title TEXT,
                status TEXT,
                workspace_root TEXT,
                target TEXT,
                step_index INTEGER,
                payload TEXT,
                meta TEXT,
                created_at REAL,
                updated_at REAL,
                decided_at REAL,
                decided_by TEXT,
                decision_reason TEXT
            )
            """
        )
        # Backward-compatible migration for existing DBs
        c.execute("PRAGMA table_info(results)")
        cols = {row[1] for row in c.fetchall()}
        if "snapshot_id" not in cols:
            c.execute("ALTER TABLE results ADD COLUMN snapshot_id TEXT")
        if "snapshot_commit" not in cols:
            c.execute("ALTER TABLE results ADD COLUMN snapshot_commit TEXT")
        if "policy_blocked" not in cols:
            c.execute("ALTER TABLE results ADD COLUMN policy_blocked INTEGER")
        if "blocked_reason" not in cols:
            c.execute("ALTER TABLE results ADD COLUMN blocked_reason TEXT")
        if "patch_blocked" not in cols:
            c.execute("ALTER TABLE results ADD COLUMN patch_blocked INTEGER")
        if "patch_blocked_reason" not in cols:
            c.execute("ALTER TABLE results ADD COLUMN patch_blocked_reason TEXT")
        if "patch_preview" not in cols:
            c.execute("ALTER TABLE results ADD COLUMN patch_preview TEXT")
        if "result_envelope" not in cols:
            c.execute("ALTER TABLE results ADD COLUMN result_envelope TEXT")
        self._conn.commit()

    def _row_to_approval_item(self, row) -> dict:
        try:
            payload = json.loads(row[9]) if row[9] else None
        except Exception:
            payload = None
        try:
            meta = json.loads(row[10]) if row[10] else {}
        except Exception:
            meta = {}
        return {
            "id": row[0],
            "task_id": row[1],
            "patch_id": row[2],
            "item_type": row[3],
            "title": row[4],
            "status": row[5],
            "workspace_root": row[6],
            "target": row[7],
            "step_index": row[8],
            "payload": payload,
            "meta": meta,
            "created_at": row[11],
            "updated_at": row[12],
            "decided_at": row[13],
            "decided_by": row[14],
            "decision_reason": row[15],
        }

    def record_approval_item(
        self,
        item_id: str,
        task_id: str,
        item_type: str,
        title: str,
        payload: dict,
        *,
        patch_id: Optional[str] = None,
        step_index: Optional[int] = None,
        workspace_root: Optional[str] = None,
        target: Optional[str] = None,
        status: str = "pending",
        meta: Optional[dict] = None,
        decided_by: Optional[str] = None,
        decision_reason: Optional[str] = None,
    ) -> dict:
        now = time.time()
        c = self._conn.cursor()
        c.execute(
            """
            INSERT OR REPLACE INTO approval_items
            (id, task_id, patch_id, item_type, title, status, workspace_root, target, step_index, payload, meta, created_at, updated_at, decided_at, decided_by, decision_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM approval_items WHERE id = ?), ?), ?, ?, ?, ?)
            """,
            (
                item_id,
                task_id,
                patch_id,
                item_type,
                title,
                status,
                workspace_root,
                target,
                step_index,
                json.dumps(payload or {}),
                json.dumps(meta or {}),
                item_id,
                now,
                now,
                now if status != "pending" else None,
                decided_by,
                decision_reason,
            ),
        )
        self._conn.commit()
        return self.get_approval_item(item_id) or {}

    def get_approval_item(self, item_id: str) -> Optional[dict]:
        c = self._conn.cursor()
        c.execute(
            "SELECT id, task_id, patch_id, item_type, title, status, workspace_root, target, step_index, payload, meta, created_at, updated_at, decided_at, decided_by, decision_reason FROM approval_items WHERE id = ?",
            (item_id,),
        )
        row = c.fetchone()
        if not row:
            return None
        return self._row_to_approval_item(row)

    def list_approval_items(
        self,
        task_id: Optional[str] = None,
        patch_id: Optional[str] = None,
        item_id: Optional[str] = None,
        status: Optional[str] = None,
        item_type: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> list[dict]:
        c = self._conn.cursor()
        query = (
            "SELECT id, task_id, patch_id, item_type, title, status, workspace_root, target, step_index, payload, meta, created_at, updated_at, decided_at, decided_by, decision_reason "
            "FROM approval_items WHERE 1=1"
        )
        params: list[object] = []
        if item_id:
            query += " AND id = ?"
            params.append(item_id)
        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)
        if patch_id:
            query += " AND patch_id = ?"
            params.append(patch_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        if item_type:
            query += " AND item_type = ?"
            params.append(item_type)
        query += " ORDER BY created_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))
            if offset is not None:
                query += " OFFSET ?"
                params.append(int(offset))
        elif offset is not None:
            query += " LIMIT -1 OFFSET ?"
            params.append(int(offset))

        c.execute(query, tuple(params))
        return [self._row_to_approval_item(row) for row in c.fetchall()]

    def update_approval_item_status(
        self,
        item_id: str,
        status: str,
        decided_by: Optional[str] = None,
        decision_reason: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> Optional[dict]:
        existing = self.get_approval_item(item_id)
        if not existing:
            return None

        if existing.get("status") in {"rejected", "executed"} and status in {"approved", "rejected"}:
            return existing

        merged_meta = dict(existing.get("meta") or {})
        if meta:
            merged_meta.update(meta)
        now = time.time()
        c = self._conn.cursor()
        c.execute(
            """
            UPDATE approval_items
            SET status = ?, updated_at = ?, decided_at = ?, decided_by = COALESCE(?, decided_by), decision_reason = COALESCE(?, decision_reason), meta = ?
            WHERE id = ?
            """,
            (
                status,
                now,
                now if status != "pending" else existing.get("decided_at"),
                decided_by,
                decision_reason,
                json.dumps(merged_meta),
                item_id,
            ),
        )
        self._conn.commit()
        return self.get_approval_item(item_id)

    def record_pending_plan_steps(self, task_payload: dict):
        task_id = task_payload.get("task_id") or task_payload.get("id")
        if not task_id or task_payload.get("task_type") != "plan_only":
            return []

        meta = task_payload.get("meta") if isinstance(task_payload.get("meta"), dict) else {}
        plan_steps = meta.get("plan_steps") if isinstance(meta.get("plan_steps"), list) else []
        recorded = []
        for index, step in enumerate(plan_steps):
            if not isinstance(step, dict):
                continue
            item_id = f"{task_id}:step:{index}"
            title = str(step.get("title") or f"step {index}")
            step_payload = {
                "task_id": task_id,
                "step_index": index,
                "step": step,
                "plan_goal": meta.get("plan_goal") or meta.get("goal") or "",
            }
            recorded.append(
                self.record_approval_item(
                    item_id,
                    task_id,
                    "plan_step",
                    title,
                    step_payload,
                    step_index=index,
                    workspace_root=task_payload.get("workspace_root"),
                    status="pending",
                    meta={"plan_goal": meta.get("plan_goal") or meta.get("goal") or ""},
                )
            )
        return recorded

    def record_task(self, task_id: str, payload: dict):
        c = self._conn.cursor()
        c.execute("INSERT OR REPLACE INTO tasks (id, created_at, payload) VALUES (?, ?, ?)",
                  (task_id, time.time(), json.dumps(payload)))
        self._conn.commit()
        try:
            if isinstance(payload, dict) and payload.get("task_type") == "plan_only":
                self.record_pending_plan_steps(payload)
        except Exception:
            pass

    def list_tasks(self, task_type: Optional[str] = None, limit: Optional[int] = None, offset: Optional[int] = None) -> list[dict]:
        c = self._conn.cursor()
        query = "SELECT id, created_at, payload FROM tasks ORDER BY created_at DESC"
        params: list[object] = []
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))
            if offset is not None:
                query += " OFFSET ?"
                params.append(int(offset))
        elif offset is not None:
            query += " LIMIT -1 OFFSET ?"
            params.append(int(offset))

        c.execute(query, tuple(params))
        rows = c.fetchall()
        tasks: list[dict] = []
        for row in rows:
            try:
                payload = json.loads(row[2]) if row[2] else {}
            except Exception:
                payload = {}
            if task_type and payload.get("task_type") != task_type:
                continue
            tasks.append({"id": row[0], "created_at": row[1], "payload": payload})
        return tasks

    def get_latest_result(self, task_id: str) -> Optional[dict]:
        c = self._conn.cursor()
        c.execute(
            "SELECT id, task_id, timestamp, exit_code, stdout, stderr, meta, snapshot_id, snapshot_commit, policy_blocked, blocked_reason, patch_blocked, patch_blocked_reason, patch_preview, result_envelope FROM results WHERE task_id = ? ORDER BY timestamp DESC LIMIT 1",
            (task_id,),
        )
        row = c.fetchone()
        if not row:
            return None
        try:
            meta = json.loads(row[6]) if row[6] else {}
        except Exception:
            meta = {}
        try:
            result_envelope = json.loads(row[14]) if row[14] else {}
        except Exception:
            result_envelope = {}
        return {
            "id": row[0],
            "task_id": row[1],
            "timestamp": row[2],
            "exit_code": row[3],
            "stdout": row[4],
            "stderr": row[5],
            "meta": meta,
            "snapshot_id": row[7],
            "snapshot_commit": row[8],
            "policy_blocked": row[9],
            "blocked_reason": row[10],
            "patch_blocked": row[11],
            "patch_blocked_reason": row[12],
            "patch_preview": row[13],
            "result_envelope": result_envelope,
        }

    def record_result(
        self,
        result_id: str,
        task_id: str,
        exit_code: int,
        stdout: str,
        stderr: str,
        meta: dict,
        snapshot_id: Optional[str] = None,
        snapshot_commit: Optional[str] = None,
        policy_blocked: Optional[bool] = None,
        blocked_reason: Optional[str] = None,
        patch_blocked: Optional[bool] = None,
        patch_blocked_reason: Optional[str] = None,
        patch_preview: Optional[dict] = None,
        result_envelope: Optional[dict] = None,
    ):
        c = self._conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO results (id, task_id, timestamp, exit_code, stdout, stderr, meta, snapshot_id, snapshot_commit, policy_blocked, blocked_reason, patch_blocked, patch_blocked_reason, patch_preview, result_envelope) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                result_id,
                task_id,
                time.time(),
                exit_code,
                stdout,
                stderr,
                json.dumps(meta or {}),
                snapshot_id,
                snapshot_commit,
                1 if policy_blocked else 0 if policy_blocked is not None else None,
                blocked_reason,
                1 if patch_blocked else 0 if patch_blocked is not None else None,
                patch_blocked_reason,
                json.dumps(patch_preview) if patch_preview is not None else None,
                json.dumps(result_envelope) if result_envelope is not None else None,
            ),
        )
        self._conn.commit()

    def record_suggestion(self, sug_id: str, task_id: str, suggestion: str):
        c = self._conn.cursor()
        c.execute("INSERT OR REPLACE INTO suggestions (id, task_id, timestamp, suggestion) VALUES (?, ?, ?, ?)",
                  (sug_id, task_id, time.time(), suggestion))
        self._conn.commit()

    def record_approval(self, approval_id: str, task_id: str, step_index: int, approved_by: str, meta: Optional[dict] = None):
        c = self._conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO approvals (id, task_id, step_index, approved_by, timestamp, meta) VALUES (?, ?, ?, ?, ?, ?)",
            (approval_id, task_id, step_index, approved_by, time.time(), json.dumps(meta or {})),
        )
        self._conn.commit()

    def get_approvals(
        self,
        task_id: str,
        approver: Optional[str] = None,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ):
        c = self._conn.cursor()
        # Build query with optional filters
        query = "SELECT id, task_id, step_index, approved_by, timestamp, meta FROM approvals WHERE task_id = ?"
        params = [task_id]
        if approver:
            query += " AND approved_by = ?"
            params.append(approver)
        if start_ts is not None:
            query += " AND timestamp >= ?"
            params.append(float(start_ts))
        if end_ts is not None:
            query += " AND timestamp <= ?"
            params.append(float(end_ts))
        query += " ORDER BY timestamp"
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))
            if offset is not None:
                query += " OFFSET ?"
                params.append(int(offset))
        elif offset is not None:
            # sqlite requires LIMIT when OFFSET is used; use large LIMIT
            query += " LIMIT -1 OFFSET ?"
            params.append(int(offset))

        c.execute(query, tuple(params))
        rows = c.fetchall()
        result = []
        for r in rows:
            try:
                meta = json.loads(r[5]) if r[5] else {}
            except Exception:
                meta = {}
            result.append({"id": r[0], "task_id": r[1], "step_index": r[2], "approved_by": r[3], "timestamp": r[4], "meta": meta})
        return result

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def get_task(self, task_id: str) -> Optional[dict]:
        c = self._conn.cursor()
        c.execute("SELECT payload FROM tasks WHERE id = ?", (task_id,))
        row = c.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None
