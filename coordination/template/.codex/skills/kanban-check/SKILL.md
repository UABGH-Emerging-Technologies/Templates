---
name: kanban-check
description: Read-only project-board orientation report — sync findings, gate payloads, human queue, Todo candidates. Touches nothing.
metadata:
  short-description: Board status snapshot, read-only
---

# kanban-check

Run `process/kanban_check.sh` — it produces this report deterministically and is the normal path. `process/kanban-check.md` is its specification and the by-hand fallback if the script cannot run; follow it exactly in that case. It is the canonical, tool-neutral, strictly read-only procedure; this file is only the Codex entry point.

In this repository's managed Codex sandbox, run the procedure's `git fetch` and every `gh` CLI command with escalated permissions on the first attempt (the sandbox cannot write `.git/FETCH_HEAD` or reach the GitHub API).
