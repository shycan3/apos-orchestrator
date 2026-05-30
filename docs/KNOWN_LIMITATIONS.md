# APOS Known Limitations

This document records the current limitations for the APOS v0.3 baseline plus the candidate and experimental boundaries introduced by committed post-v0.3 runtime and bridge work.

## Current Limits

- Web LLMs do not receive direct automatic message forwarding from APOS.
- External browser automation and a Web Controller are still experimental future work.
- See [docs/WEB_CONTROLLER_EXPERIMENT.md](WEB_CONTROLLER_EXPERIMENT.md) for the current design notes; it is not implemented.
- Automatic background loops are not implemented.
- Recovery Prompt Loop is manual and does not auto-send to the web LLM.
- Users still need to inspect and approve the approval queue manually.
- The browser extension and web UI depend on DOM structure and can drift if the target site layout changes.
- Report generation is read-only and does not repair or execute anything by itself.
- The v0.2.1 dashboard polish resolved the earlier recovery prompt location ambiguity by pointing failed item cards to the detail panel, where the full prompt can be copied.
- The v0.3 semi-auto recovery implementation only adds prompt-preparation automation and `--mode auto`; auto-send, auto-approve, auto-execute, and Web Controller remain out of scope.

## Security Boundaries

- APOS Core validates and executes locally; it does not delegate trust to the web model.
- Protected roots still cannot be written directly.
- Prompt Builder and Failure / Drift Report only produce guidance text, not execution privileges.

## Future Work

- Web Controller support, if added later, should be introduced as a separate experimental layer.
- Any automatic loop must be designed with explicit opt-in, bounded retries, and audit logging.
- If later recovery automation is expanded, it should still stop at prompt preparation and never bypass human review.
