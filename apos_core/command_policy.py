"""Command execution policy for safe local process launches."""
from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any, Dict, List, Sequence, Union


CommandInput = Union[str, Sequence[str]]


class CommandPolicy:
    def __init__(self):
        self.allowed_binaries = {
            "python",
            "python.exe",
            "python3",
            "py",
            "pytest",
            "pytest.exe",
            "node",
            "node.exe",
            "npm",
            "npm.cmd",
            "git",
        }
        self.allowed_git_subcommands = {"status", "diff"}
        self.blocked_commands = {
            "rm",
            "del",
            "rmdir",
            "format",
            "shutdown",
            "reboot",
            "curl",
            "wget",
            "sudo",
            "runas",
        }
        self.blocked_tokens = {
            "invoke-webrequest",
            "invoke-expression",
            "iex",
        }
        self.injection_tokens = {"&&", ";", "||", "|", ">", "<"}

    def _split(self, cmd: CommandInput) -> Dict[str, Any]:
        if isinstance(cmd, (list, tuple)):
            argv = [str(x) for x in cmd]
            raw = " ".join(argv)
            return {"ok": True, "argv": argv, "raw": raw}
        if isinstance(cmd, str):
            raw = cmd
            try:
                argv = shlex.split(cmd, posix=(os.name != "nt"))
            except Exception as exc:
                return {"ok": False, "argv": [], "raw": raw, "reason": f"parse_error: {exc}"}
            return {"ok": True, "argv": argv, "raw": raw}
        return {"ok": False, "argv": [], "raw": "", "reason": "command_must_be_str_or_list"}

    def validate_command(self, cmd: CommandInput) -> Dict[str, Any]:
        parsed = self._split(cmd)
        if not parsed["ok"]:
            return {
                "allowed": False,
                "policy_blocked": True,
                "blocked_reason": parsed.get("reason", "invalid_command"),
                "normalized_command": [],
            }

        argv = parsed["argv"]
        raw = parsed["raw"]
        if not argv:
            return {
                "allowed": False,
                "policy_blocked": True,
                "blocked_reason": "empty_command",
                "normalized_command": [],
            }

        lower_argv = [x.lower() for x in argv]
        first = Path(argv[0]).name.lower()

        if any(tok in raw for tok in self.injection_tokens) or any(x in self.injection_tokens for x in argv):
            return {
                "allowed": False,
                "policy_blocked": True,
                "blocked_reason": "shell_injection_pattern_detected",
                "normalized_command": argv,
            }

        if first in self.blocked_commands:
            return {
                "allowed": False,
                "policy_blocked": True,
                "blocked_reason": f"blocked_command: {first}",
                "normalized_command": argv,
            }

        if first in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
            if any(x in {"-encodedcommand", "/encodedcommand"} for x in lower_argv):
                return {
                    "allowed": False,
                    "policy_blocked": True,
                    "blocked_reason": "blocked_powershell_encodedcommand",
                    "normalized_command": argv,
                }
            if any(x in self.blocked_tokens for x in lower_argv):
                return {
                    "allowed": False,
                    "policy_blocked": True,
                    "blocked_reason": "blocked_powershell_dangerous_token",
                    "normalized_command": argv,
                }
            return {
                "allowed": False,
                "policy_blocked": True,
                "blocked_reason": "powershell_not_in_allowlist",
                "normalized_command": argv,
            }

        if any(x in self.blocked_tokens for x in lower_argv):
            return {
                "allowed": False,
                "policy_blocked": True,
                "blocked_reason": "blocked_dangerous_token",
                "normalized_command": argv,
            }

        if first == "chmod" and len(argv) > 1 and argv[1] == "777":
            return {
                "allowed": False,
                "policy_blocked": True,
                "blocked_reason": "blocked_chmod_777",
                "normalized_command": argv,
            }

        if first not in self.allowed_binaries:
            return {
                "allowed": False,
                "policy_blocked": True,
                "blocked_reason": f"command_not_allowlisted: {first}",
                "normalized_command": argv,
            }

        if first == "git":
            if len(argv) < 2:
                return {
                    "allowed": False,
                    "policy_blocked": True,
                    "blocked_reason": "git_subcommand_required",
                    "normalized_command": argv,
                }
            sub = argv[1].lower()
            if sub not in self.allowed_git_subcommands:
                return {
                    "allowed": False,
                    "policy_blocked": True,
                    "blocked_reason": f"git_subcommand_not_allowlisted: {sub}",
                    "normalized_command": argv,
                }

        return {
            "allowed": True,
            "policy_blocked": False,
            "blocked_reason": "",
            "normalized_command": argv,
        }


class AllowAllCommandPolicy:
    def validate_command(self, cmd: CommandInput) -> Dict[str, Any]:
        if isinstance(cmd, (list, tuple)):
            argv = [str(x) for x in cmd]
        elif isinstance(cmd, str):
            argv = shlex.split(cmd, posix=(os.name != "nt"))
        else:
            argv = []
        return {
            "allowed": True,
            "policy_blocked": False,
            "blocked_reason": "",
            "normalized_command": argv,
        }
