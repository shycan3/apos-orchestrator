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

    def record_task(self, task_id: str, payload: dict):
        c = self._conn.cursor()
        c.execute("INSERT OR REPLACE INTO tasks (id, created_at, payload) VALUES (?, ?, ?)",
                  (task_id, time.time(), json.dumps(payload)))
        self._conn.commit()

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
