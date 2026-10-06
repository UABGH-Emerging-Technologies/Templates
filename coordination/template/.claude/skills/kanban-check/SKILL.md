---
name: kanban-check
description: Read-only project-board orientation report — freshness, sync findings, gate payloads (verbatim), the human queue, and Todo candidates. Touches nothing; reports intended actions instead. Implemented by process/kanban_check.sh, which is what /next runs for its orientation passes.
---

Run `process/kanban_check.sh` — it produces this report deterministically and is the normal path. `process/kanban-check.md` is its specification and the by-hand fallback if the script cannot run; follow it exactly in that case. It is the canonical, tool-neutral, strictly read-only procedure; this file is only the Claude Code entry point.
