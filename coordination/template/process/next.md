# next — board-driven session orientation (tool-neutral procedure)

This is the canonical procedure; the per-tool entry points (`.claude/skills/next/`, `.opencode/command/next.md`, `.codex/skills/next/`) are thin wrappers that point here. It works in any coding agent that can run `gh` and `git`.

**Run this only when the human invokes it** (the command, or asking "what's next?") — never proactively at session start: a session may be opened for anything, and the human decides when board orientation is wanted. When invoked, you are doing in batch what a live watch (Claude Code Monitor loop, or a background shell polling loop) does moment-to-moment: reconcile the board with ground truth, react to everything humans did since the last session, then choose work. Board conventions, field/option IDs, and the plumbing recipe are in AGENTS.md ("Project board" section); the rationale is in PROCESS.md.

## Lane rules — which steps are global, which are scoped

The operator is `gh api user --jq .login`. Cards assigned to the operator are "your lane." Scoping is **by action type**, not uniform:

| Action | Scope | Why |
|---|---|---|
| Ground-truth sync (step 1) | **Global** | Idempotent bookkeeping — concurrent runs converge; a stale board helps nobody. |
| Gate processing (step 2 — closed gates *and* unacknowledged comments on open ones) | **Global, claim-guarded** | If only the gate-owner's operator could process it, follow-on work would wait for *that human to start a session* — an anti-pattern dressed up as waiting-on-a-human. Any active session processes any cleared gate — and any open gate with an actionable human comment; the `Processed:`/`Claiming:` acknowledgment is the claim. |
| Human nudge (step 3) | **Your lane** (others' staleness surfaced, not nagged) | Their queue is their schedule. |
| Starting work (step 4) | **Your lane, poach-by-reassign allowed** | Starting a card is a commitment; a `Claiming:` comment is the claim (Status/assignee are the visible signal). Agent-work must never wait on a specific human's presence — so an empty lane may claim from another lane by winning the claim then reassigning. |

**Claims, because two sessions may run this at once (possibly different tools):** check-then-claim alone has a race window — GitHub has no atomic test-and-set, so two simultaneous runs can both read "unclaimed" before either marker lands. The arbiter is the **issue comment stream**: comments are append-only, attributed, and totally ordered by comment ID. Protocol for anything contested (gates, starting a card, poaches):

1. **Check**: re-fetch the issue's comments; a live claim marker (`Processed:` for gates, `Claiming:` for cards/poaches, not marked superseded) → someone else has it; skip.
2. **Claim**: comment your marker, including a session nonce — two sessions of the *same* operator share a gh login, so the operator name alone can't distinguish them (e.g. `Claiming: <operator> · <hhmm + 4 random chars>`).
3. **Verify**: re-fetch once more. If a competing claim has a **lower comment ID** than yours (comment ID, not timestamp — timestamps have ties), you lost: edit yours to append `(superseded)` and move on. Only after winning do the slow part.

Status/assignee moves still happen — they're the human-visible signal on the board — but they never *arbitrate*: field edits carry no visible order or author. Losing this race costs one extra API call; skipping the verify step costs duplicated work (never corruption — code changes still serialize through git, and duplicate PRs collide loudly at review — but wasted agent-hours are real).

## 0. Pull state

- **Freshness check first**: `git fetch origin main -q && git status --short --branch` — if the launch tree is behind origin/main and clean, offer to `git pull --ff-only` (merged conventions/procedures are invisible until pulled; if a new command/skill arrived, tell the human a session restart may be needed for their tool to discover it). Dirty or on a feature branch → report, don't touch.
- `gh project item-list <BOARD_NUMBER> --owner <BOARD_OWNER> --limit 100 --format json` (never omit `--limit`)
- `gh pr list --json number,title,isDraft,url`

## 1. Sync pass — make the board match ground truth (global; do without asking)

- Card whose issue is CLOSED or PR is MERGED but Status ≠ Done → set Status Done.
- Open non-draft PR with no card **and not already tracked** → add the PR to the board, Status = Awaiting code review, **Responsible = Copilot (AI reviewer)** — the reviewer is who acts next on it. **Already tracked (2026-07-29): if an issue card for the same work is sitting in Awaiting code review, the PR is covered — don't double-card one piece of work.** Detection: check the PR body/branch for the issue it closes (`Closes #N`, `Fixes #N`, or an `issue-N` branch name) and the issue's linked-development section; if that issue has a board card in Awaiting code review, the PR is tracked. When tracked but the link isn't visible on the issue, add it (an `Agent:`-prefixed comment with the PR URL).
- Open item in `HUMAN-REVIEW-QUEUE.md` with no corresponding card → file one: label `human-review` (+ `stakeholder` when the decision belongs to the non-GitHub stakeholder — relay delivery), Responsible = the human it names, assignee = operator, Status = Awaiting human action if its packet/materials are ready, else Todo; body self-contained per conventions, linking the HRQ entry.
- Checked-off HRQ items whose cards are still open: if the card carries an unambiguous decision comment, leave it to step 2's open-gate scan (which processes and closes it); if there is **no** comment payload, surface to the user rather than silently closing — the check-off alone doesn't say what was decided.

## 2. Cleared-gate pass — react to human decisions (global, claim-guarded)

For each **closed** `human-review` issue with no comment starting with `Processed:` — any lane:

1. Claim per the protocol above: re-fetch comments (still unclaimed?) → comment `Processed: (in progress — <operator> · <nonce>)` → re-fetch and verify yours is the earliest claim (lowest comment ID; lost → mark yours `(superseded)`, skip this gate). Finish by editing/replacing your winning claim with the real acknowledgment.
2. Read the closing comment(s) — that's the payload. A close with no contrary comment = approved.
3. Do what the card said it unblocks: file follow-on Todo cards (self-contained, Responsible = the AI-agent option, **assignee = you, the running operator** — the accountable human who is actually present; anyone may reassign later, wrong human beats no human), update gates in related Unshaped drafts, check off the HRQ entry if the card's ask covered it.
4. Mine the payload for *new information* beyond the approval (stakeholder observations, constraints) — each actionable insight becomes its own card rather than evaporating.
5. Finalize the acknowledgment: `Processed: <what you did, with links>`.
6. Payload ambiguous (partial approval, unclear caveat)? Leave the claim comment saying so, ask the user; do not guess.

**Also scan OPEN gates for unacknowledged human comments** — humans sometimes deliver the payload without the signal (a comment, no close), and a closed-only scan leaves that input invisible until someone remembers to close. The authoritative query is **board Status = Awaiting human action** (open issues; any lane) — not the `human-review` label, which is convention and can be missed (the closed-gate pass above keys on the label only because closed cards have left the status columns). Scan each such card for a human comment newer than the last agent-marker comment:

Key on what the comment *asks for*:

- **Explicit, complete decision** ("approved", "use option B", the ask answered in full) → treat it as a cleared gate: claim per the protocol, process as above, and **restore the signal yourself** — close the issue with attribution ("Closing per 〈user〉's approval comment above"). The close-is-the-signal convention survives because the agent repairs it.
- **Change request / actionable feedback** ("revise the packet — X is wrong", "tighten this and show me again") → the gate isn't cleared, it's **re-armed**: claim, move the card to **Agent working** (the column must not say a human acts next while an agent is revising), do the asked work (normal conventions — md edits via worktree + PR, verification), reply on the issue with what changed and where to look, then move it **back to Awaiting human action**. One card oscillates across revision rounds — same semantics as change-requests on a PR. Never close it for the human: close is reserved for "my decision on this gate is complete" (approve, or reject-outright — which arrives as contrary-comment-then-close and is handled by the closed-gate pass above).
- **A question to the agent** → answer in a reply comment.
- **Ambiguous or partial** (mid-thought, caveat whose scope is unclear, feedback whose intended action you'd have to guess) → do **not** act and do **not** close; list it in step 3's queue output as "unacknowledged comment awaiting your read" and, if it's the operator's lane, ask them directly. Never guess a human's intent from a partial comment.

In every branch, an agent reply lands on the issue, and **every agent-authored comment on a gate card starts with a marker** — `Processed:`, `Claiming:`, or `Agent:` (for replies and re-presentations). The marker is what makes the scan boundary detectable: on a single-account repo, author gives you nothing, so *the last marker comment is the acknowledgment horizon* — any later comment without a marker is unacknowledged human input.

**Markdown edits from this pass (HRQ check-offs, note updates) go through a temporary git worktree + the standard PR flow — never edit the launch working tree.** Another session may be mid-commit there (the pilot project has a scar: a parallel session's `commit -a` once swept 50 staged files into an unrelated commit). Git then serializes concurrent md writes: disjoint hunks merge cleanly, same-line collisions surface as loud PR conflicts instead of lost updates — and the gate claim already guarantees no two sessions touch the same HRQ entry. Batch all md edits from one run into a single PR.

## 3. Human nudge — report, don't nag

List Awaiting human action cards **assigned to the operator**: title, link, one-line ask each. Then, in one line, note any *other* lane's Awaiting-human card idle ≥ 7 days ("stale in X's lane: …") — visibility without nagging someone else's queue.

## 4. Pick work and start (your lane; poach if empty)

- Candidates: Status = Todo, Responsible = `AI agent`, assignee = operator.
- If the user passed an argument (e.g. `next report`), use it to filter/pick the matching card.
- Otherwise pick the lowest issue number (earlier cards tend to set up later ones); say what you picked and why in one line.
- **Claim before work** (protocol above): if Status is already Agent working or a live `Claiming:` comment exists, another session took it — pick the next. Otherwise comment `Claiming: <operator> · <nonce>`, verify yours is the earliest (lowest comment ID; lost → next card), *then* move it to Agent working and begin, following the card body and repo conventions (PR flow, review chain, verification). **Read the card's comments before starting (2026-07-29): humans attach guidance to Todo cards** (constraints, access routes, changed context) **that the open-gate scan deliberately doesn't cover — at pickup, the comments are part of the spec.** If a comment contradicts the card body (scope narrowed, approach changed), the comment is newer but don't guess: surface the conflict to the operator before starting.
- **Lane empty?** You may poach: a Todo card in another lane with the AI-agent Responsible (never a human-action card) → win the `Claiming:` arbitration first (note `(poaching from 〈previous assignee〉 — lane empty)` in the comment), then reassign it to your operator and proceed as above. This is what keeps agent-work from silently waiting on another developer's next session.
- Nothing anywhere? Say the board is drained, summarize the 2–3 most actionable Unshaped drafts (their gates permitting) and offer to shape one.

## Output shape

Keep the orientation report short: what was synced (one line per fix), gates processed (what each unblocked), the human's queue, and the pick. Then get to work.
