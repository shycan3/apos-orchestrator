# APOS Prompt Builder Demo

This example shows how to generate a paste-ready prompt for ChatGPT or Gemini from the current workspace context.

## 1. Build a patch prompt

```bash
python cli/apos.py prompt build --goal "Add a new status summary command" --mode patch --output prompt.md
```

The output includes:

- APOS Role Rules
- User Goal
- Required Output Format
- Safety Constraints
- Current Context Pack
- Recommended Response Style

The patch template explicitly asks for exactly one `apos-patch` block plus one source block, and it tells the web LLM to fall back to review or plan mode if the task is uncertain.

## 2. Build a plan prompt

```bash
python cli/apos.py prompt build --goal "Plan a staged refactor" --mode plan
```

The generated prompt asks the web LLM to return one `plan_only` envelope with a non-empty `meta.plan_steps` list.

Each step should state its purpose, target files, expected risk, execution conditions, and stop conditions.

## 3. Build a review prompt

```bash
python cli/apos.py prompt build --goal "Review the workspace for risks" --mode review --copy
```

The review mode asks for analysis only, with no file-edit JSON.

The review template also asks for a next APOS-ready prompt that can be reused for patch or plan follow-up.

If clipboard copying is unavailable on the current OS, the prompt generation still succeeds and the text is printed to stdout.