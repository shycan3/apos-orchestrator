import subprocess
import tempfile
from pathlib import Path

from apos_core.snapshot import SnapshotManager
from cli.snapshot_tools import create_parser


def _git(cwd: Path, *args: str):
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def _init_repo(repo: Path):
    repo.mkdir(parents=True, exist_ok=True)
    assert _git(repo, "init").returncode == 0
    assert _git(repo, "config", "user.email", "apos@example.local").returncode == 0
    assert _git(repo, "config", "user.name", "APOS Test").returncode == 0


def _commit_file(repo: Path, rel: str, content: str, message: str):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    assert _git(repo, "add", "-A").returncode == 0
    assert _git(repo, "commit", "-m", message).returncode == 0


def test_commit_exists_success_and_failure():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        _init_repo(repo)
        _commit_file(repo, "a.txt", "v1\n", "init")

        head = _git(repo, "rev-parse", "HEAD").stdout.strip()
        m = SnapshotManager(repo)

        ok = m.commit_exists(head)
        bad = m.commit_exists("deadbeef")

        assert ok["ok"] is True
        assert bad["ok"] is False


def test_list_changed_files_since_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        _init_repo(repo)
        _commit_file(repo, "src/app.py", "print('v1')\n", "init")

        m = SnapshotManager(repo)
        snap = m.create_snapshot("t-1")
        assert snap["ok"] is True
        commit = snap["snapshot_commit"]

        (repo / "src" / "app.py").write_text("print('v2')\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "update")

        diff = m.list_changed_files_since(commit)
        assert diff["ok"] is True
        assert "src/app.py" in diff["files"]


def test_restore_specific_file_from_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        _init_repo(repo)
        _commit_file(repo, "src/app.py", "print('v1')\n", "init")

        m = SnapshotManager(repo)
        snap = m.create_snapshot("restore-task")
        assert snap["ok"] is True
        commit = snap["snapshot_commit"]

        (repo / "src" / "app.py").write_text("print('v2')\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "change")

        restore = m.restore_file_from_snapshot(commit, "src/app.py")
        assert restore["ok"] is True
        assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "print('v1')\n"


def test_restore_rejects_absolute_and_traversal_paths():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        _init_repo(repo)
        _commit_file(repo, "src/app.py", "print('v1')\n", "init")

        m = SnapshotManager(repo)
        snap = m.create_snapshot("path-guard")
        assert snap["ok"] is True
        commit = snap["snapshot_commit"]

        abs_path = str((repo / "src" / "app.py").resolve())
        r1 = m.restore_file_from_snapshot(commit, abs_path)
        r2 = m.restore_file_from_snapshot(commit, "../outside.txt")

        assert r1["ok"] is False
        assert r1["message"] == "absolute_path_not_allowed"
        assert r2["ok"] is False
        assert r2["message"] == "path_traversal_not_allowed"


def test_cli_does_not_expose_full_rollback_by_default():
    parser = create_parser()
    subparsers_action = next(a for a in parser._actions if getattr(a, "dest", None) == "command")
    choices = set(subparsers_action.choices.keys())

    assert "rollback" not in choices
    assert {"check-commit", "diff", "restore-file"}.issubset(choices)
