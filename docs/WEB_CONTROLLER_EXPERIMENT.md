# Experimental Web Controller Design

## Purpose

This document describes a future experimental Web Controller layer that could help APOS interact with a browser-based LLM interface more directly.

It is a design note only. It is not implemented in the current APOS codebase.

## Boundary with APOS Core

APOS Core remains the authority for validation, policy checks, task execution, approval queue handling, reporting, and recovery prompt generation.

The Web Controller, if it is ever added, would sit outside APOS Core and would only act as a bounded bridge to a browser session. It must not bypass Core validation, approval flow, or task logging.

## Allowed Work

- Detect page readiness in a browser session.
- Locate the LLM composer or prompt input area.
- Paste a prepared prompt into the browser UI.
- Read visible assistant responses for human review.
- Collect minimal UI state needed to confirm that a prompt was submitted.

## Forbidden Work

- Automatic approval of APOS actions.
- Automatic execution of patches or commands.
- Hidden background loops that keep retrying without user review.
- Broad scraping of unrelated page content.
- Circumventing site security, login flows, or browser protections.
- Writing directly into protected APOS files or bypassing APOS Core policies.

## Safety Principles

- Human review stays mandatory before any action is treated as accepted.
- The controller should be opt-in and explicitly bounded by scope.
- APOS Core must remain the source of truth for policy and execution.
- Browser automation should be minimized to the smallest possible interaction surface.
- Any recovered prompt or browser action must be auditable.

## Expected Implementation Stages

1. Define a narrow browser interaction contract for prompt submission only.
2. Add a read-only browser state probe that can confirm input focus and visible response state.
3. Add bounded prompt submission with explicit user confirmation.
4. Add audit logging for each browser interaction.
5. Add failure handling that falls back to manual copy and paste.
6. Re-check compatibility against APOS report and recovery prompt workflows.

## What Is Not Implemented Now

APOS does not currently include a Web Controller implementation, external browser automation, or semi-automatic retry loop.

Any future work in this area should remain a separate experimental layer and should not change the current approval, report, or recovery prompt flows.