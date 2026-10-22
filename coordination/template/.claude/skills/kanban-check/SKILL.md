---
name: kanban-check
description: Read-only project-board orientation report — freshness, sync findings, gate payloads (verbatim), the human queue, and Todo candidates. Touches nothing; reports intended actions instead. Implemented by process/kanban_check.sh, which is what /next runs for its orientation passes.
---

Run `process/kanban_check.sh` — it produces this report deterministically and is the normal path. `process/kanban-check.md` is its specification and the by-hand fallback if the script cannot run; follow it exactly in that case. It is the canonical, tool-neutral, strictly read-only procedure; this file is only the Claude Code entry point.


For explicitly installed GitHub multi-repository coordination, run orientation
with `process/kanban_check.sh --manifest plan/repositories.json`; add the
validated `--checkout-root` when using an isolated worktree. Retain the ordinary
invocation for single-repository projects and other platforms. An incomplete
report permits no selection or mutations. Manifest presence alone does not
activate coordination.
This wrapper remains strictly read-only; never invoke the guarded action CLI.
