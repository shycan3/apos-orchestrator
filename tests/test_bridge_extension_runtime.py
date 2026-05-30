import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_bridge_extension_runtime_script_passes():
    proc = subprocess.run(
        ["node", str(REPO_ROOT / "tests" / "bridge_extension_runtime_test.js")],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "bridge extension runtime tests passed" in proc.stdout
