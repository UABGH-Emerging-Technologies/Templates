---
description: Board-driven session orientation (user-triggered only — run when invoked, never proactively) — sync the project board to ground truth, process cleared human gates, list the human's queue, claim the next Todo card and work it through to a PR
---

Read `process/next.md` in this repository and follow it exactly. It is the canonical, tool-neutral procedure; this file is only the OpenCode entry point. **Run the orientation passes (steps 0–3) by invoking `process/kanban_check.sh` in-process; never spawn another `opencode run`.** **The deliverable is the work step 4 selects — a PR, a merge, or a recorded blocker (step 5) — not the orientation report.** Work-selection filter (step 4): $ARGUMENTS
