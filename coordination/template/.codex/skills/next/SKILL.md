---
name: next
description: Board-driven session orientation — sync cards to ground truth, process cleared human gates, list the human's queue, pick up the next Todo card. User-triggered only; never run proactively.
metadata:
  short-description: What's next on the project board
---

# next

Read `process/next.md` in this repository and follow it exactly. It is the canonical, tool-neutral procedure; this file is only the Codex entry point, and it marks an orchestrator session: delegate the orientation passes (steps 0–3) per that file's Delegation section (opencode running `process/kanban-check.md`). Pass any user-supplied argument through as the work-selection filter in its step 4.

In this repository's managed Codex sandbox, run the procedure's required
`git fetch` and every `gh` CLI command with escalated permissions on the first
attempt. The sandbox cannot write `.git/FETCH_HEAD` or reach the GitHub API, so
do not spend a probe call retrying either command inside the sandbox first.
