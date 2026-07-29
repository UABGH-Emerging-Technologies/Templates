# next — board-driven session orientation (tool-neutral procedure)

This is the canonical procedure; the per-tool entry points (`.claude/skills/next/`, `.opencode/command/next.md`, `.codex/skills/next/`) are thin wrappers that point here. It works in any coding agent that can run `gh` and `git`.

**Run this only when the human invokes it** (the command, or asking "what's next?") — never proactively at session start: a session may be opened for anything, and the human decides when board orientation is wanted. When invoked, you are doing in batch what a live watch (Claude Code Monitor loop, or a background shell polling loop) does moment-to-moment: reconcile the board with ground truth, react to everything humans did since the last session, then choose work. Board conventions, field/option IDs, and the plumbing recipe are in AGENTS.md ("Project board" section); the rationale is in PROCESS.md.

## Lane rules — which steps are global, which are scoped

The operator is `gh api user --jq .login`. Cards assigned to the operator are "your lane." Scoping is **by action type**, not uniform:

| Action | Scope | Why |
|---|---|---|
| Ground-truth sync (step 1) | **Global** | Idempotent bookkeeping — concurrent runs converge; a stale board helps nobody. |
| Cleared-gate processing (step 2) | **Global, claim-guarded** | If only the gate-owner's operator could process it, follow-on work would wait for *that human to start a session* — an anti-pattern dressed up as waiting-on-a-human. Any active session processes any cleared gate; the `Processed:` acknowledgment is the claim. |
| Human nudge (step 3) | **Your lane** (others' staleness surfaced, not nagged) | Their queue is their schedule. |
| Starting work (step 4) | **Your lane, poach-by-reassign allowed** | Starting a card is a commitment; the assignee field is the visible claim. Agent-work must never wait on a specific human's presence — so an empty lane may claim from another lane by reassigning first. |

**Claims, because two sessions may run this at once (possibly different tools):** before acting on anything contested, re-fetch it and check the claim marker — `Processed:` comment for gates, Status = Agent working for cards, assignee for poaches. Marker present → someone else has it; skip. Place your own marker *before* doing the slow part.

## 0. Pull state

- **Freshness check first**: `git fetch origin main -q && git status --short --branch` — if the launch tree is behind origin/main and clean, offer to `git pull --ff-only` (merged conventions/procedures are invisible until pulled; if a new command/skill arrived, tell the human a session restart may be needed for their tool to discover it). Dirty or on a feature branch → report, don't touch.
- `gh project item-list <BOARD_NUMBER> --owner <BOARD_OWNER> --limit 100 --format json` (never omit `--limit`)
- `gh pr list --json number,title,isDraft,url`

## 1. Sync pass — make the board match ground truth (global; do without asking)

- Card whose issue is CLOSED or PR is MERGED but Status ≠ Done → set Status Done.
- Open non-draft PR with no card → add the PR to the board, Status = Awaiting code review, **Responsible = Copilot (AI reviewer)** — the reviewer is who acts next on it.
- Open item in `HUMAN-REVIEW-QUEUE.md` with no corresponding card → file one: label `human-review` (+ `stakeholder` when the decision belongs to the non-GitHub stakeholder — relay delivery), Responsible = the human it names, assignee = operator, Status = Awaiting human action if its packet/materials are ready, else Todo; body self-contained per conventions, linking the HRQ entry.
- Checked-off HRQ items whose cards are still open → surface to the user rather than silently closing (the human may have skipped the comment payload).

## 2. Cleared-gate pass — react to human decisions (global, claim-guarded)

For each **closed** `human-review` issue with no comment starting with `Processed:` — any lane:

1. Re-fetch the issue's comments now (claim check — another session may have gotten here first). Still unclaimed → comment `Processed: (in progress — <operator>)` immediately; that's your claim. Finish by editing/replacing it with the real acknowledgment.
2. Read the closing comment(s) — that's the payload. A close with no contrary comment = approved.
3. Do what the card said it unblocks: file follow-on Todo cards (self-contained, Responsible = the AI-agent option, **assignee = you, the running operator** — the accountable human who is actually present; anyone may reassign later, wrong human beats no human), update gates in related Unshaped drafts, check off the HRQ entry if the card's ask covered it.
4. Mine the payload for *new information* beyond the approval (stakeholder observations, constraints) — each actionable insight becomes its own card rather than evaporating.
5. Finalize the acknowledgment: `Processed: <what you did, with links>`.
6. Payload ambiguous (partial approval, unclear caveat)? Leave the claim comment saying so, ask the user; do not guess.

**Markdown edits from this pass (HRQ check-offs, note updates) go through a temporary git worktree + the standard PR flow — never edit the launch working tree.** Another session may be mid-commit there (the pilot project has a scar: a parallel session's `commit -a` once swept 50 staged files into an unrelated commit). Git then serializes concurrent md writes: disjoint hunks merge cleanly, same-line collisions surface as loud PR conflicts instead of lost updates — and the gate claim already guarantees no two sessions touch the same HRQ entry. Batch all md edits from one run into a single PR.

## 3. Human nudge — report, don't nag

List Awaiting human action cards **assigned to the operator**: title, link, one-line ask each. Then, in one line, note any *other* lane's Awaiting-human card idle ≥ 7 days ("stale in X's lane: …") — visibility without nagging someone else's queue.

## 4. Pick work and start (your lane; poach if empty)

- Candidates: Status = Todo, Responsible = `AI agent`, assignee = operator.
- If the user passed an argument (e.g. `next report`), use it to filter/pick the matching card.
- Otherwise pick the lowest issue number (earlier cards tend to set up later ones); say what you picked and why in one line.
- **Claim before work**: re-fetch the card; if Status is already Agent working, another session took it — pick the next. Otherwise move it to Agent working and begin, following the card body and repo conventions (PR flow, review chain, verification).
- **Lane empty?** You may poach: a Todo card in another lane with the AI-agent Responsible (never a human-action card) → reassign it to your operator *first* (the reassignment is the claim), comment "Reassigned from 〈previous〉 — lane empty, picking this up", then proceed as above. This is what keeps agent-work from silently waiting on another developer's next session.
- Nothing anywhere? Say the board is drained, summarize the 2–3 most actionable Unshaped drafts (their gates permitting) and offer to shape one.

## Output shape

Keep the orientation report short: what was synced (one line per fix), gates processed (what each unblocked), the human's queue, and the pick. Then get to work.
