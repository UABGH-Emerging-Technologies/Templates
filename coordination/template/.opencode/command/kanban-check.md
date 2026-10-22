---
description: Read-only project-board orientation report — sync findings, gate payloads, human queue, Todo candidates. Touches nothing.
---

Run `process/kanban_check.sh` — it produces this report deterministically and is the normal path. `process/kanban-check.md` is its specification and the by-hand fallback if the script cannot run; follow it exactly in that case. It is the canonical, tool-neutral, strictly read-only procedure; this file is only the OpenCode entry point. Run every step yourself — never spawn another agent or `opencode run`.


For explicitly installed GitHub multi-repository coordination, run orientation
with `process/kanban_check.sh --manifest plan/repositories.json`; add the
validated `--checkout-root` when using an isolated worktree. Retain the ordinary
invocation for single-repository projects and other platforms. An incomplete
report permits no selection or mutations. Manifest presence alone does not
activate coordination.
This wrapper remains strictly read-only; never invoke the guarded action CLI.
