---
name: next
description: Board-driven session orientation — sync cards to ground truth, process cleared human gates, list the human's queue, claim the next Todo card, agree a plan with the human, and work it through to a draft PR (only the human promotes it to ready-for-review, and only the human merges). User-triggered only; never run proactively.
metadata:
  short-description: What's next on the project board
---

# next

Read `process/next.md` in this repository and follow it exactly. It is the canonical, tool-neutral procedure; this file is only the Codex entry point, and it marks an orchestrator session: produce the orientation passes (steps 0–3) by running `process/kanban_check.sh` per that file's "Orientation passes" section, then do the judgment and the writes yourself. Pass any user-supplied argument through to its step 4 — a card number selects that card; other text filters the candidates. **The session's deliverable is the work step 4 selects — a draft PR or a recorded blocker (step 6) — not the orientation report. The agent opens a *draft* PR only: only the human promotes it to ready-for-review, and only the human merges.** **Two human gates are mandatory in every harness: after the claim, present a plan (asking the human questions while you form it) and wait for explicit approval before editing anything (step 5); before opening the draft PR, show the human a fresh-eyes review's results plus a testing report — and, if the user experience changed, a proposed manual test — then open a draft PR, which moves the card to Awaiting code review, and stop; only the human promotes it to ready-for-review, and only the human merges (step 7).**

In this repository's managed Codex sandbox, run the procedure's required
`git fetch` and every `gh` CLI command with escalated permissions on the first
attempt. The sandbox cannot write `.git/FETCH_HEAD` or reach the GitHub API, so
do not spend a probe call retrying either command inside the sandbox first.
