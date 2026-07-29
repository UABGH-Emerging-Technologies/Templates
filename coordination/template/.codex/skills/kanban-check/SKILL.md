---
name: kanban-check
description: Read-only project-board orientation report — sync findings, gate payloads, human queue, Todo candidates. Touches nothing.
metadata:
  short-description: Board status snapshot, read-only
---

# kanban-check

Read `process/kanban-check.md` in this repository and follow it exactly. It is the canonical, tool-neutral, strictly read-only procedure; this file is only the Codex entry point.

In this repository's managed Codex sandbox, run the procedure's `git fetch` and every `gh` CLI command with escalated permissions on the first attempt (the sandbox cannot write `.git/FETCH_HEAD` or reach the GitHub API).
