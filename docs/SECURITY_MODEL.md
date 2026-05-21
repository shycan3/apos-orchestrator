# APOS v3.2 Security Model

APOS follows this operating sentence:

```text
Web LLMs propose, local APOS validates, humans approve.
```

The web LLM is never trusted as an authority.

## Trust Boundaries

Trusted:

- local APOS CLI
- local APOS WebSocket server
- human approval

Untrusted:

- ChatGPT output
- Gemini output
- web page DOM content
- copied code blocks

## Localhost Only

The server binds to:

```text
127.0.0.1:8765
```

Non-local WebSocket clients are rejected.

## Protected Areas

The following paths are protected:

```text
specifications/
context/
.apos/
.codex/
```

They store durable project direction, decisions, system rules, and AI instructions.

Direct writes to these areas are forbidden. A proposal targeting a protected area is appended to:

```text
workspace/scratchpad.md
```

The actual protected file is not modified by the server.

## Direct Candidate Areas

The following areas may be written after validation and human sign-off:

```text
workspace/
src/
app/
scripts/
tests/
```

Even in these areas, `propose_patch` does not write files. It only validates and stores a pending patch. `commit_patch` is required to write.

## Forbidden Target Paths

The server rejects:

- absolute target paths
- paths containing null bytes
- `../` traversal
- paths resolving outside `project_root`
- targets outside protected or direct-candidate policy

## Content Validation

The server verifies:

- content is a string
- content size is below the configured maximum
- SHA-256 matches the supplied `sha256`
- `language: python` passes `py_compile.compile(..., doraise=True)`

Unsupported languages fail explicitly.

## Retry Limit

The extension may inject an automatic retry prompt for `validation_failed`.

Maximum retry count:

```text
2
```

After that, human intervention is required.

## Non-Goals

APOS does not do the following:

- call AI APIs
- run an autonomous background agent loop
- send project files to external servers
- use a database
- modify protected areas directly
- commit without human sign-off
- execute arbitrary shell commands from web output
