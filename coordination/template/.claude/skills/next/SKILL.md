---
name: next
description: Orient a fresh session against the project board and decide what's next — sync cards to ground truth, process cleared human gates, list what's waiting on the human, then claim the next Todo card and work it through to a PR. User-triggered only — run when invoked, or when the user asks what's next; never proactively.
---

Read `process/next.md` in this repository and follow it exactly. It is the canonical, tool-neutral procedure; this file is only the Claude Code entry point, and it marks an orchestrator session: produce the orientation passes (steps 0–3) by running `process/kanban_check.sh` per that file's "Orientation passes" section, then do the judgment and the writes yourself. Pass any arguments through as the work-selection filter in its step 4. **The session's deliverable is the work step 4 selects — a PR, a merge, or a recorded blocker (step 5) — not the orientation report.**
