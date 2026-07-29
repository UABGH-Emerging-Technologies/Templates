# coordination — human+agent project-board pattern (Copier template)

**Status: PROPOSAL (draft PR).** This graduates the coordination pattern piloted on `UABGH-Emerging-Technologies/lead-infinitely` into the templates repo, per that repo's PROCESS.md canonical-home note ("if the team adopts the paradigm, the canonical resources move to the team's templates repo"). Until this merges and the migration checklist below runs, lead-infinitely remains the canonical home.

## What the pattern is (one paragraph)

Coding agents made writing code cheap; the scarce resource is human judgment. A shared GitHub Project board is the queue-management UI for it: agents enqueue judgment requests as cards (reviews, sign-offs, decisions), humans drain them in batches, and everything tool-shaped lives in md files that any agent (Claude Code, OpenCode, Codex, …) can follow. Columns: **Unshaped** (the fluid plan, as cheap draft items) → **Todo** (shaped, self-contained) → **Agent working** → **Awaiting code review** → **Awaiting human action** → **Done**. Deliberately no Blocked column — every column answers "who acts next." Full rationale: `template/PROCESS.md.jinja` (rendered into each project).

## What this template stamps

```
AGENTS.md              cross-tool conventions (rules index + board section; IDs filled by board-setup)
CLAUDE.md              one-line @AGENTS.md import (Claude Code reads the same conventions)
PROCESS.md             the rationale document, project-name rendered
process/next.md        canonical orientation procedure (board tokens filled by board-setup)
process/board-setup.md canonical bootstrap procedure (self-contained; can also be fetched cross-repo)
.claude/skills/…       thin entry-point wrappers (next, board-setup)   — Claude Code
.opencode/command/…    thin entry-point wrappers                        — OpenCode
.codex/skills/…        thin entry-point wrappers                        — Codex (repo-level discovery verified on 0.145.0)
```

All wrapper sets are emitted unconditionally: tooling is per developer, not per team.

## How it's used

**Greenfield**: apply this template (alongside `common`/`fastapi_app`/…), put planning artifacts in `plan/` and feasibility spikes in `explorations/`, then have any coding agent run the `board-setup` procedure — it ingests `plan/` + `explorations/`, drafts IMPLEMENTATION-PLAN.md for human review, creates and seeds the board, and fills the `<BOARD_NUMBER>`-style tokens the template leaves behind.

```
$ copier copy --trust Templates/coordination path/to/destination
```

(House convention: a local clone of this repo, same as the app templates. **Apply coordination AFTER `common`** if you use both — both emit AGENTS.md; this one supersedes common's by including its rules-index block plus the board conventions.)

**Existing repo without the template**: an agent runs `board-setup` directly (personal copy in `~/.claude/skills/` or `~/.codex/skills/`); the procedure fetches everything it needs from this repo.

**Day-to-day**: developers type `/next` (or "what's next?") in their tool of choice — user-triggered only, never proactive. The procedure syncs cards to ground truth, processes cleared human gates (comment = payload, close = signal), lists the human's queue, and picks up the next Todo card in the operator's lane.

## Migration checklist (runs when this PR merges — not before)

1. Flip the canonical-fetch URLs in `lead-infinitely` (`process/board-setup.md`, the board-setup wrappers) from `UABGH-Emerging-Technologies/lead-infinitely` to `UABPeriopAI/Templates` paths, and update its PROCESS.md canonical-home note.
2. Update personal wrapper copies (`~/.claude/skills/board-setup/`, `~/.codex/skills/next/`, `~/.codex/prompts/next.md`) to fetch from this repo.
3. Future pattern improvements land here first; lead-infinitely consumes them like any other project.

## Open questions for review

- **AGENTS.md composition**: `common/template/AGENTS.md.jinja` also emits AGENTS.md (the `.agents/rules/` index). Current decision (documented in copier.yml + above): apply coordination *after* common; its AGENTS.md includes common's rules-index block plus the board section. Two known costs: the embedded rules-index can drift if common's list changes, and applying in the wrong order silently drops the board section (copier enforces no ordering). The collision-safe alternative — the board section as `.agents/rules/coordination.md` referenced from common's AGENTS.md — trades that for one more indirection. **Reviewers: pick one.**
- **Org defaults**: the board lives under the project's GitHub owner; nothing here assumes UABGH vs UABPeriopAI.
- Note (pre-existing, separate from this PR): the repo-root `CLAUDE.md` describes the NCVV project — it appears to have been copied from another repo and should be replaced or removed.
