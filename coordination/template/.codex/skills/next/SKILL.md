---
name: next
description: Board-driven session orientation — sync cards to ground truth, process cleared human gates, list the human's queue, claim the next Todo card and work it through to a PR. User-triggered only; never run proactively.
metadata:
  short-description: What's next on the project board
---

# next

Read `process/next.md` in this repository and follow it exactly. It is the canonical, tool-neutral procedure; this file is only the Codex entry point, and it marks an orchestrator session: produce the orientation passes (steps 0–3) by running `process/kanban_check.sh` per that file's "Orientation passes" section, then do the judgment and the writes yourself. Pass any user-supplied argument through as the work-selection filter in its step 4. **The session's deliverable is the work step 4 selects — a PR, a merge, or a recorded blocker (step 5) — not the orientation report.**

In this repository's managed Codex sandbox, run the procedure's required
`git fetch` and every `gh` CLI command with escalated permissions on the first
attempt. The sandbox cannot write `.git/FETCH_HEAD` or reach the GitHub API, so
do not spend a probe call retrying either command inside the sandbox first.
