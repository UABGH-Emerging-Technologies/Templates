---
description: Read-only project-board orientation report — sync findings, gate payloads, human queue, Todo candidates. Touches nothing.
---

Run `process/kanban_check.sh` — it produces this report deterministically and is the normal path. `process/kanban-check.md` is its specification and the by-hand fallback if the script cannot run; follow it exactly in that case. It is the canonical, tool-neutral, strictly read-only procedure; this file is only the OpenCode entry point. Run every step yourself — never spawn another agent or `opencode run`.
