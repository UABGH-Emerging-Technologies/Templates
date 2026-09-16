# coordination — human+agent project-board pattern (Copier template)

**Status: PROPOSAL (draft PR).** This graduates the coordination pattern piloted on `UABGH-Emerging-Technologies/lead-infinitely` into the templates repo, per that repo's PROCESS.md canonical-home note ("if the team adopts the paradigm, the canonical resources move to the team's templates repo"). Until this merges and the migration checklist below runs, lead-infinitely remains the canonical home.

## What the pattern is (one paragraph)

Coding agents made writing code cheap; the scarce resource is human judgment. A shared GitHub Project board is the queue-management UI for it: agents enqueue judgment requests as cards (reviews, sign-offs, decisions), humans drain them in batches, and everything tool-shaped lives in md files that any agent (Claude Code, OpenCode, Codex, …) can follow. Columns: **Unshaped** (the fluid plan, as cheap draft items) → **Todo** (shaped, self-contained) → **Agent working** → **Awaiting code review** → **Awaiting human action** → **Done**. Deliberately no Blocked column — every column answers "who acts next." Full rationale: `template/PROCESS.md.jinja` (rendered into each project).

## What this template stamps

```
AGENTS.md               cross-tool conventions (rules index + board section; IDs filled by board-setup)
CLAUDE.md               one-line @AGENTS.md import (Claude Code reads the same conventions)
PROCESS.md              the rationale document, project-name rendered
process/next.md         canonical orientation procedure (board tokens filled by board-setup)
process/kanban-check.md read-only orientation spec + by-hand fallback (self-contained on purpose)
process/kanban_check.sh the executable orientation report `next` actually runs
process/board-setup.md  canonical bootstrap procedure (self-contained; can also be fetched cross-repo)
.claude/skills/…        thin entry-point wrappers (next, kanban-check, board-setup)  — Claude Code
.opencode/command/…     thin entry-point wrappers                                     — OpenCode
.codex/skills/…         thin entry-point wrappers                    — Codex (repo-level discovery verified on 0.145.0)
```

All wrapper sets are emitted unconditionally: tooling is per developer, not per team.

`kanban_check.sh` ships with `<REPO_SLUG>` / `<BOARD_OWNER>` / `<BOARD_NUMBER>` placeholders and **refuses to run while any of them remain** — a half-substituted orientation script would report some other project's board into this one's, and a wrong-data run looks exactly like a good one.

## How it's used

**Greenfield**: apply this template (alongside `common`/`fastapi_app`/…), put planning artifacts in `plan/` and feasibility spikes in `explorations/`, then have any coding agent run the `board-setup` procedure — it ingests `plan/` + `explorations/`, drafts IMPLEMENTATION-PLAN.md for human review, creates and seeds the board, and fills the `<BOARD_NUMBER>`-style tokens the template leaves behind.

```
$ copier copy --trust Templates/coordination path/to/destination
```

(House convention: a local clone of this repo, same as the app templates. **Apply coordination AFTER `common`** if you use both — both emit AGENTS.md; this one supersedes common's by including its rules-index block plus the board conventions.)

**Existing repo without the template**: an agent runs `board-setup` directly (personal copy in `~/.claude/skills/` or `~/.codex/skills/`); the procedure fetches everything it needs from this repo.

**Day-to-day**: developers type `/next` (or "what's next?") in their tool of choice — user-triggered only, never proactive. The procedure syncs cards to ground truth, processes cleared human gates (comment = payload, close = signal), lists the human's queue, picks up the next Todo card in the operator's lane, **and works it through to a PR** — the orientation report is the preamble, not the deliverable.

## Second sync: what ~7 weeks of pilot use changed (2026-07-31 → 2026-09-15)

The first draft of this template mirrored the pilot as of 2026-07-29. Everything below is a lesson the pilot paid for after that date, now folded in. Two of them **retire** a mechanism this template previously shipped, which is the main reason to re-read rather than skim the diff.

**Structural**

- **Orientation is a script, not a delegate** (pilot 2026-09-02). This template used to ship the delegate-to-a-local-model structure as its headline feature. The pilot deleted it: a delegated run reported three nonexistent issue numbers, six closed issues as open candidates, swapped two cards' titles, and wrote a file into the checkout in direct violation of the READ-ONLY rule. Every finding in those passes is a join, a date comparison or a regex — so `process/kanban_check.sh` computes them (~12 s, ~4 KB) instead of a model recalling them (minutes, 212 KB). Delegation remains *permitted*; it is no longer the default, and nothing depends on it.
- **`next` gained a step 5: do the work** (2026-09-03). Sessions were ending on a claim comment and a board move — no work, and a card now marked as being worked by a session that had stopped. This got *worse* once orientation became cheap: the session arrives at the pick with no momentum and a tidy report that reads like a finished answer. The deliverable is now stated outright: a PR, a merge, or a recorded blocker.
- **`kanban-check.md` must be self-contained** (2026-08-24). Its claim to prevent delegation loops "by construction" was false while its own step 0 told the delegate to read `next.md` — and a real delegate did. Rules are now restated inline rather than cross-referenced, and the permitted git commands are an **allowlist** (a delegate swapped in `git fetch --prune` and deleted two remote-tracking refs; `git ls-remote` is the only form that correctly answers "is there a remote branch?", since the pinned fetch never materialises other refs).
- **board-setup installs all of it** (2026-08-17): kanban-check + the script are not optional, and there are now six wrappers (two per tool). Substitutions are verified by grepping for leftover placeholders and for the *source* project's literals, not by trusting a step number.

**Board mechanics**

- **Truncation is a hard failure, not a caveat** (2026-08-14). `--limit 100` was outgrown; the symptom was a new card appearing not to exist. Filter server-side (`--query` drops `totalCount` itself; a `jq` filter cannot help), guard board fetches with a `totalCount` comparison, and guard `gh issue list` / `gh pr list` with a returned-equals-limit tripwire since they have no `totalCount`. **Never filter out Done when hunting cleared gates** — closed gate cards live there.
- **Stale work-claim sweep** (2026-08-04). Step 4 skips Agent-working cards by design, so a card an agent abandoned is invisible to every future session forever. 24 h + no PR + no remote branch → verify nothing landed, supersede the claim, re-queue to Todo. A draft PR exempts it; a deliberate pause does not (a parked card and an abandoned one look identical from outside).
- **One work card per session** (2026-07-31) — a limit on *selection*, not effort.
- **Branch naming `issue-<n>` is load-bearing**, because it is how the sweep answers "is there a branch?"; and post-merge cleanup cannot use `git branch --merged`, which under squash merging lists only `main` and never a feature branch — the pilot accumulated 12 stale branches and a worktree behind that false all-clear.

**Card conventions**

- **Lead with the ask** (owner rule, 2026-08-19): first line of a card body, and first line of the last comment, is the ask itself in plain language — "nothing right now, this is FYI" included. A thread whose current ask can only be reconstructed by reading every comment in order has failed. This also lets the orientation report extract each card's ask mechanically.
- **Reviewable artifacts are committed and linked by permalink**; "regenerate it with this script" strands the reviewer on one machine and makes the approved thing unrecoverable.
- **Consolidated gate cards** (2026-08-10), with the correction that followed a week later: consolidation applies to **gates, not work**. The first wording read as "stop making cards about this topic" and left the next session hesitant to card real build work. Test: a human *decides* it → consolidate; an agent *does* it → card it.
- **A change request re-queues a gate to Todo** rather than auto-starting it — the re-armed gate competes for selection like any other card.

**A process lesson about this document set itself**: one pilot PR corrected the truncation advice in four files and missed a fifth; a second fixed the fifth as a drive-by; a third reverted the second wholesale, restoring the bad wording. A revert is scoped to a PR, not to a topic, so drive-by fixes die with it. Land corrections on their own card.

## Migration checklist (runs when this PR merges — not before)

1. Flip the canonical-fetch URLs in `lead-infinitely` (`process/board-setup.md`, the board-setup wrappers) from `UABGH-Emerging-Technologies/lead-infinitely` to `UABGH-Emerging-Technologies/Templates` paths, and update its PROCESS.md canonical-home note.
2. Update personal wrapper copies (`~/.claude/skills/board-setup/`, `~/.codex/skills/next/`, `~/.codex/prompts/next.md`) to fetch from this repo.
3. Future pattern improvements land here first; lead-infinitely consumes them like any other project.

## Open questions for review

- **AGENTS.md composition**: `common/template/AGENTS.md.jinja` also emits AGENTS.md (the `.agents/rules/` index). Current decision (documented in copier.yml + above): apply coordination *after* common; its AGENTS.md includes common's rules-index block plus the board section. Two known costs: the embedded rules-index can drift if common's list changes, and applying in the wrong order silently drops the board section (copier enforces no ordering). The collision-safe alternative — the board section as `.agents/rules/coordination.md` referenced from common's AGENTS.md — trades that for one more indirection. **Reviewers: pick one.**
- **Org defaults**: the board lives under the project's GitHub owner, asked as the `github_owner` copier question. That is separate from the canonical-fetch URLs, which name where *this* repo actually lives (`UABGH-Emerging-Technologies/Templates`). The `github_owner` **default** is still `UABPeriopAI`, matching the sibling app templates — deliberately left alone here, since which org new projects belong to is a team call rather than a fact about this repo. **Reviewers: confirm or change it repo-wide**, not just in `coordination/`.
- Note (pre-existing, separate from this PR): the repo-root `CLAUDE.md` describes the NCVV project — it appears to have been copied from another repo and should be replaced or removed.
