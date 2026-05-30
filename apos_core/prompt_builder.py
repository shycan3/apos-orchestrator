"""Build paste-ready APOS prompts from the current context pack."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from .context_pack import ContextPackBuilder


PROMPT_MODES = {"patch", "plan", "review"}


class PromptBuilder:
    def __init__(self, workspace_root: str | Path, history_db_path: str | Path | None = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.context_builder = ContextPackBuilder(self.workspace_root, history_db_path=history_db_path)

    def build(
        self,
        *,
        goal: str,
        mode: str = "patch",
        max_depth: int = 4,
        max_files: int = 120,
        max_file_preview_chars: int = 1200,
        max_total_chars: int = 12000,
        max_recent_history: int = 5,
        max_pending_approvals: int = 5,
        max_worklog_entries: int = 3,
    ) -> str:
        normalized_goal = self._normalize_goal(goal)
        normalized_mode = self._normalize_mode(mode)
        pack = self.context_builder.build(
            max_depth=max_depth,
            max_files=max_files,
            max_file_preview_chars=max_file_preview_chars,
            max_total_chars=max_total_chars,
            max_recent_history=max_recent_history,
            max_pending_approvals=max_pending_approvals,
            max_worklog_entries=max_worklog_entries,
        )
        return self.render_markdown(pack, goal=normalized_goal, mode=normalized_mode)

    def render_markdown(self, pack: Dict[str, Any], *, goal: str, mode: str) -> str:
        normalized_goal = self._normalize_goal(goal)
        normalized_mode = self._normalize_mode(mode)
        pack_markdown = self.context_builder.render_markdown(pack).rstrip()

        lines: List[str] = []
        lines.append("# APOS Prompt Builder")
        lines.append("")
        lines.append("## APOS Role Rules")
        for rule in self._role_rules(normalized_mode):
            lines.append(f"- {rule}")
        lines.append("")

        lines.append("## User Goal")
        lines.append(normalized_goal)
        lines.append("")

        lines.append("## Required Output Format")
        lines.extend(self.required_output_lines(normalized_mode))
        lines.append("")

        lines.append("## Safety Constraints")
        for rule in self._safety_constraints(pack, normalized_mode):
            lines.append(f"- {rule}")
        lines.append("")

        lines.append("## Current Context Pack")
        lines.append("")
        lines.append(pack_markdown)
        lines.append("")

        lines.append("## Recommended Response Style")
        for rule in self._response_style(normalized_mode):
            lines.append(f"- {rule}")

        return "\n".join(lines).rstrip() + "\n"

    def required_output_lines(self, mode: str) -> List[str]:
        return self._required_output_lines(mode)

    def render_recovery_markdown(
        self,
        pack: Dict[str, Any],
        *,
        recovery_goal: str,
        failure_summary: str,
        likely_cause: str,
        affected_files: List[str],
        relevant_context: List[str],
        constraints: List[str],
        required_llm_output: List[str],
        recommended_mode: str,
        safety_reminder: str,
    ) -> str:
        normalized_goal = self._normalize_goal(recovery_goal)
        normalized_mode = self._normalize_mode(recommended_mode)

        lines: List[str] = []
        lines.append("# APOS Recovery Prompt")
        lines.append("")
        lines.append("## APOS Role Rules")
        for rule in self._role_rules(normalized_mode):
            lines.append(f"- {rule}")
        lines.append("")

        lines.append("## Recovery Goal")
        lines.append(normalized_goal)
        lines.append("")

        lines.append("## Failure Summary")
        lines.append(failure_summary or "- No failure summary available")
        lines.append("")

        lines.append("## Likely Cause")
        lines.append(likely_cause or "unknown")
        lines.append("")

        lines.append("## Affected Files")
        if affected_files:
            for path in affected_files:
                lines.append(f"- {path}")
        else:
            lines.append("- No specific file could be confirmed")
        lines.append("")

        lines.append("## Relevant Context")
        if relevant_context:
            for item in relevant_context:
                lines.append(f"- {item}")
        else:
            lines.append("- No additional context available")
        lines.append("")

        lines.append("## Constraints")
        for rule in self._safety_constraints(pack, normalized_mode):
            lines.append(f"- {rule}")
        for rule in constraints:
            lines.append(f"- {rule}")
        lines.append("")

        lines.append("## Required LLM Output")
        for line in required_llm_output:
            lines.append(line)
        lines.append("")

        lines.append(f"## Recommended Mode: {normalized_mode}")
        lines.append(f"- {normalized_mode}")
        lines.append("")

        lines.append("## Safety Reminder")
        lines.append(safety_reminder)
        lines.append("")

        lines.append("## Recommended Response Style")
        for rule in self._response_style(normalized_mode):
            lines.append(f"- {rule}")

        return "\n".join(lines).rstrip() + "\n"

    def write_output(self, prompt_text: str, output_path: str | Path | None = None) -> None:
        if not output_path:
            return
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prompt_text, encoding="utf-8", newline="\n")

    def copy_to_clipboard(self, prompt_text: str) -> bool:
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(prompt_text)
            root.update()
            root.destroy()
            return True
        except Exception:
            pass

        if os.name == "nt":
            try:
                subprocess.run(["clip"], input=prompt_text, text=True, check=True, capture_output=True)
                return True
            except Exception:
                return False

        try:
            subprocess.run(["pbcopy"], input=prompt_text, text=True, check=True, capture_output=True)
            return True
        except Exception:
            return False

    def _normalize_goal(self, goal: str) -> str:
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("prompt build requires a non-empty goal")
        return goal.strip()

    def _normalize_mode(self, mode: str) -> str:
        normalized = str(mode or "").strip().lower()
        if normalized not in PROMPT_MODES:
            raise ValueError(f"unsupported prompt mode: {mode}")
        return normalized

    def _role_rules(self, mode: str) -> List[str]:
        return [
            "Web LLM is the proposer; APOS is the validator and executor.",
            "Do not claim direct access to local files, terminals, or the filesystem.",
            "Treat the current context pack as the only authoritative project snapshot.",
            f"Use the prompt mode '{mode}' exactly as requested and do not switch modes unless the request is unsafe.",
        ]

    def _required_output_lines(self, mode: str) -> List[str]:
        if mode == "patch":
            return self._patch_output_lines()
        if mode == "plan":
            return self._plan_output_lines()
        return self._review_output_lines()

    def _patch_output_lines(self) -> List[str]:
        return [
            "- Return one short user-facing summary first, then exactly one APOS patch proposal.",
            "- The response must contain exactly one fenced code block with the apos-patch language identifier.",
            "- The apos-patch block must contain one parseable JSON object and must not contain a diff.",
            "- Immediately after that block, provide one fenced source block containing the full final file content or the APOS-supported envelope content.",
            "- Use a single patch only; do not offer alternatives, diffs, or multi-file patch bundles.",
            "- Follow the validate-only / preview_patch / propose_patch workflow mentally before proposing the change.",
            "- If multiple files need changes, either split the work into safe APOS-supported pieces or switch to plan mode.",
            "- If the request is uncertain, do not draft a patch; prefer review or plan mode instead.",
            "- Required proposal shape:",
            "",
            "```apos-patch",
            '{',
            '  "patch_id": "unique-short-id",',
            f'  "project_root": "{self.workspace_root.as_posix()}",',
            '  "target": "workspace/example.py",',
            '  "language": "python",',
            '  "sha256": "..."',
            '}',
            "```",
            "",
            "```python",
            "# full final file content here",
            "```",
        ]

    def _plan_output_lines(self) -> List[str]:
        return [
            "- Return one short user-facing summary first, then one APOS plan envelope.",
            "- Use task_type=plan_only and put the plan steps in meta.plan_steps as a non-empty list.",
            "- Make each step independently reviewable, approvable, and runnable.",
            "- For each step, include the purpose, target files, expected risk, and the conditions required before execution.",
            "- Keep one step small; do not pack multiple unrelated edits or validation tasks into the same step.",
            "- Split risky commands into separate approval-worthy steps and keep test execution separate from change steps.",
            "- State stop conditions clearly so APOS can halt before unsafe execution if validation fails.",
            "- Use APOS plan-step status language consistently: pending, approved, rejected, running, executed, failed, skipped.",
            "- Required plan shape:",
            "",
            "```json",
            '{',
            '  "schema_version": "1.0",',
            '  "task_id": "plan-short-unique-id",',
            '  "task_type": "plan_only",',
            '  "created_by": "web_llm",',
            '  "workspace_root": ".",',
            '  "patches": [],',
            '  "commands": [],',
            '  "options": {',
            '    "enable_snapshots": false,',
            '    "enable_patch_dry_run": true,',
            '    "enable_command_policy": true,',
            '    "fail_on_snapshot_error": true,',
            '    "stop_on_first_failure": true',
            '  },',
            '  "meta": {',
            '    "plan_goal": "short goal summary",',
            '    "plan_steps": [',
            '      {',
            '        "title": "one reviewable step",',
            '        "description": "purpose, target files, risk, and execution conditions",',
            '        "task_type": "patch_and_run",',
            '        "patches": [],',
            '        "commands": []',
            '      }',
            '    ]',
            '  }',
            '}',
            "```",
        ]

    def _review_output_lines(self) -> List[str]:
        return [
            "- Return one short user-facing summary first, then an analysis-only review.",
            "- Do not produce file-edit JSON, patch JSON, or source code intended for modification.",
            "- Focus on current-state summary, risks, recommended actions, and a next prompt the user can reuse.",
            "- Mark uncertain claims as estimates or assumptions instead of presenting them as facts.",
            "- If the task is uncertain or incomplete, stay in review mode rather than inventing a patch or plan.",
            "- Provide a concrete next APOS-friendly prompt suggestion that can be used for patch or plan follow-up.",
            "- Required review shape:",
            "",
            "```text",
            "Summary: concise user-facing summary",
            "Risks: bullet list of concrete risks",
            "Recommended actions: bullet list of safest next steps",
            "Next prompt: one or two APOS-ready follow-up request sentences",
            "```",
        ]

    def _safety_constraints(self, pack: Dict[str, Any], mode: str) -> List[str]:
        protected_roots = ", ".join(pack.get("protected_roots", []))
        allowed_roots = ", ".join(pack.get("allowed_roots", []))
        return [
            "The web LLM cannot directly modify local files.",
            "Only APOS envelopes or plan formats are allowed; do not output ad hoc edit instructions.",
            f"Protected roots are off-limits for writes: {protected_roots}.",
            f"Allowed working roots are limited to the current safe scope: {allowed_roots}.",
            "Secret, token, key, password, and private-key values must stay redacted.",
            "Any command suggestions must still pass APOS policy before execution.",
            "If the request is ambiguous or risky, prefer review or plan mode instead of a patch proposal.",
            "Keep the user-facing summary separate from the APOS envelope or plan payload.",
            "Do not invent hidden commands or side effects that the user did not ask for.",
            "If local state is unclear, rely only on the Context Pack and say what is uncertain.",
            f"This prompt is currently tuned for {mode} mode only.",
        ]

    def _response_style(self, mode: str) -> List[str]:
        style = [
            "Be concise and explicit about assumptions.",
            "Prefer one recommended answer over multiple competing options.",
            "Reference the Context Pack when describing any file, path, or recent change.",
            "Keep the human summary and APOS structure separate.",
        ]
        if mode == "patch":
            style.append("Prefer a single minimal patch that is easy to validate.")
        elif mode == "plan":
            style.append("Prefer short steps with clear approval boundaries and no hidden side effects.")
        else:
            style.append("Prefer analysis, risks, and follow-up questions over implementation details.")
        return style
