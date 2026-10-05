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

1. **Check**: re-fetch the issue's comments; a live claim marker (`Processed:` for gates, `Claiming:` for cards/poaches, not marked superseded) → someone else has it; skip. Exception: a gate whose only live marker is a `Processed: (in progress — …)` claim **older than 24 h** has been abandoned — edit it to append `(superseded — abandoned)` and claim afresh. Only a *finalized* `Processed:` acknowledgment marks a gate as done.
2. **Claim**: comment your marker, including a session nonce — two sessions of the *same* operator share a gh login, so the operator name alone can't distinguish them (e.g. `Claiming: <operator> · <hhmm + 4 random chars>`).
3. **Verify**: re-fetch once more. If a competing claim has a **lower comment ID** than yours (comment ID, not timestamp — timestamps have ties), you lost: edit yours to append `(superseded)` and move on. Only after winning do the slow part.

Status/assignee moves still happen — they're the human-visible signal on the board — but they never *arbitrate*: field edits carry no visible order or author. Losing this race costs one extra API call; skipping the verify step costs duplicated work (never corruption — code changes still serialize through git, and duplicate PRs collide loudly at review — but wasted agent-hours are real).

## Orientation passes — run the script

**Steps 0–3 are produced by `process/kanban_check.sh`.** Run it directly in this session; there is no delegate and no round-trip:

```
process/kanban_check.sh                       # report on stdout
process/kanban_check.sh --comments full       # verbatim candidate comments
sed -n '/=== KANBAN-CHECK REPORT ===/,/=== END KANBAN-CHECK REPORT ===/p' <log>   # extract from any captured log
```

The script implements `process/kanban-check.md`, which remains the specification and the by-hand fallback. It emits the report between `=== KANBAN-CHECK REPORT ===` and `=== END KANBAN-CHECK REPORT ===`.

**Why this replaced delegation to a local model (pilot, 2026-09-01).** The orientation cost is dominated by reading board/PR/HRQ state, and the original fix was to move that reading to a free local agent (measured 2026-07-29: flawless orientation 6/6 dry runs, ~70–85k session tokens saved). What later runs showed is that the passes are not judgement at all — every finding is a join, a date comparison, or a regex on a comment prefix — and that a model doing them can get them *wrong*: the 2026-08-29 delegate reported three issue numbers that do not exist, six closed issues as open candidates, swapped two cards' titles, and wrote a file into the launch checkout in direct violation of `kanban-check.md`'s bold READ-ONLY rule. A script cannot invent an issue number, cannot decide a different `git` invocation is equivalent, and cannot quietly paraphrase a comment it was told to quote. Measured: ~12 s and ~4 KB at the default `--comments brief`, against a delegated run's several minutes and 212 KB transcript.

It also retires a hazard rather than managing it. The delegation split existed so that a delegate never read this file's write-bearing steps — prevention "by construction" that was **false** for as long as `kanban-check.md` still told delegates to come here for conventions, which a real delegate duly did. A script has no context to poison and no identity to misjudge (a 2026-07-29 loop test found 1 of 3 local sessions misidentified its own runtime). Delegating orientation to a local model is still *permissible* — the read-only rules in `kanban-check.md` are written for exactly that — but it is no longer the default, and nothing in this procedure depends on it.

**What never comes from the script:** step 2 payload *interpretation* (classifying a human comment as decision / change request / ambiguous), the HRQ consolidation category match, and **every mutation** — claims, card moves, follow-on card creation, comments, closes. The script reports; this session judges and writes.

**Trust but verify:** the report is an input, not an authority. Re-run any step yourself when it conflicts with something you already know, and note that it is stale the moment it prints — at claim time run the full check → claim → verify loop from scratch rather than trusting a reported "unclaimed".

## 0. Pull state

- **Freshness check first**: `git fetch origin main -q && git status --short --branch` — if the launch tree is behind origin/main and clean, offer to `git pull --ff-only` (merged conventions/procedures are invisible until pulled; if a new command/skill arrived, tell the human a session restart may be needed for their tool to discover it). Dirty or on a feature branch → report, don't touch.
- **Local-hygiene backstop**: `git worktree list` and `git branch -vv`. Cleanup belongs at merge time (AGENTS.md, "After a merge, clean up locally"), but sessions end before they get there, so this is where the drift surfaces. Anything beyond the launch tree and `main` → *report it, with what you verified*; clean only what you have confirmed is patch-contained in a merged PR and free of uncommitted changes. Do not run a blanket `git branch --merged` sweep and conclude all is well: under squash merging that command lists only `main` and never a feature branch, which is exactly how the pilot accumulated 12 stale branches and a worktree unnoticed before 2026-08-13.
- **Board, live work only** — `gh project item-list <BOARD_NUMBER> --owner <BOARD_OWNER> --query "-status:Done" --limit 200 --format json`. `--query` is applied **server-side** (`totalCount` itself drops: 101 → 44 on the pilot's board, 2026-08-13), so it shrinks what `--limit` has to cover. A `jq` filter would not help at all — `--limit` truncates at fetch, before anything client-side runs.
- **Check every board fetch for truncation.** The pilot's board outgrew `--limit 100` on 2026-08-13 and the symptom was a freshly-created card that simply appeared not to exist — silence, not an error. Never work from a possibly-short list:

  ```
  … --format json | jq -e '.totalCount as $t | (.items|length) as $n |
      if $t == $n then . else error("TRUNCATED: \($n) of \($t)") end'
  ```

- **Never filter `Done` out when looking for cleared gates.** A closed gate card is *in* Done by definition, so a `-status:Done` board query would hide exactly the human decisions step 2 exists to process. The closed-gate scan therefore uses the issue API, which no board filter can affect — and asks for `comments` in the same call, since what step 2 actually needs is whether a `Processed:` marker is present:

  ```
  gh issue list -R <REPO_SLUG> --label human-review --state closed \
    --json number,title,comments
  ```

  (`process/kanban_check.sh` fetches a deliberate superset of this — `--state all`, unlabelled, plus bodies — because the QUEUE ask lines, HRQ link resolution and the stale-claim sweep all need issues this narrow query excludes. See `kanban-check.md` step 1.)

  **This one cannot use the `totalCount` guard** — `gh issue list` has no such field (asking for it errors). Use the returned-vs-limit tripwire instead: if the number of issues returned equals the limit, treat it as truncated and raise the limit, because you cannot distinguish "exactly 100" from "at least 100".

  Open gates still come from the board (`status:"Awaiting human action"`), which the Done filter leaves untouched.
- `gh pr list -R <REPO_SLUG> --json number,title,isDraft,url`

## 1. Sync pass — make the board match ground truth (global; do without asking)

- Card whose issue is CLOSED or PR is MERGED but Status ≠ Done → set Status Done.
- Open non-draft PR with no card **and not already tracked** → add the PR to the board, Status = Awaiting code review, **Responsible = Copilot (AI reviewer)** — the reviewer is who acts next on it. **Already tracked (2026-07-29): if an issue card for the same work is sitting in Awaiting code review, the PR is covered — don't double-card one piece of work.** Detection: check the PR body/branch for the issue it closes (`Closes #N`, `Fixes #N`, or an `issue-N` branch name) and the issue's linked-development section; if that issue has a board card in Awaiting code review, the PR is tracked. When tracked but the link isn't visible on the issue, add it (an `Agent:`-prefixed comment with the PR URL).
- Open item in `HUMAN-REVIEW-QUEUE.md` with no corresponding card → file one: label `human-review` (+ `stakeholder` when the decision belongs to the non-GitHub stakeholder — relay delivery), Responsible = the human it names, assignee = operator, Status = Awaiting human action if its packet/materials are ready, else Todo; body self-contained per conventions, **first line the ask**, linking the HRQ entry. **Exception — consolidated tracking cards: if the HRQ item names a card that already tracks it, or a note at the top of the file names a card for a whole *category* the item falls into, that item is already covered.** Add a comment to the named card instead; never file a second. Match by category, not by enumeration: a note reading "every 〈topic〉 item is tracked on #〈n〉" covers a *newly added* item of that kind that no one has listed yet. Without that clause the rule silently regrows the very cards the consolidation was meant to collapse — the pilot refiled five separate cards on one consolidated topic, once per HRQ item.

  **Scope: this consolidates *gates*, not *work*.** It applies to cards a human decides — reviews, approvals, sign-offs — on the theory that one successful review clears them together. **Build cards are exempt**: distinct executable work always gets its own card, including work that falls out of a consolidated topic, and filing one is not a violation. Test: does a human *decide* it (consolidate) or does an agent *do* it (card it)? The pilot's first draft of this exception omitted that line and read as "stop making cards about this topic", which left the next session hesitant to card real build work.
- Checked-off HRQ items whose cards are still open: if the card carries an unambiguous decision comment, leave it to step 2's open-gate scan (which processes and closes it); if there is **no** comment payload, surface to the user rather than silently closing — the check-off alone doesn't say what was decided.
- **Stale work-claim sweep:** a card in **Agent working** whose newest agent-marker comment (`Claiming:` / `Agent:`) is older than **24 h**, with **no open PR** referencing it (body keyword, `issue-<n>` branch, or the issue's linked-development sidebar) and **no remote branch** for it, is not being worked — it's parked. Nothing else repairs this: step 4 skips Agent-working cards by design ("another session took it"), so a card an agent abandoned stays invisible to every future session until a human notices. Repair it here:
  1. **Verify nothing landed** before touching anything: `gh pr list --state all --search <issue-number>`, remote branches, and whether the card's described change is present on `origin/main`. Anything landed → this is a missed sync, set Status per the rules above instead.
  2. Edit the live `Claiming:` marker to append `(superseded — <one-line reason>)`.
  3. Post an `Agent:` comment recording what you verified, and **name any partial work that might survive elsewhere** — an abandoned branch, an uncommitted worktree on another machine — so the next picker recovers or consciously discards it instead of silently writing a second version. **Never delete a branch or worktree, and never report as gone anything you could not inspect** (another machine's working tree is out of your reach, not empty).
  4. Status → **Todo**; Responsible and assignee unchanged.
  - **A draft PR exempts the card** — a draft PR means the agent got somewhere and Agent working is the correct column. Don't re-queue it; note it in this pass's own output ("stale draft: …") so the orientation report carries it. It's a nudge for the card's operator, not a board repair — step 3 is the wrong home for it, since that pass covers Awaiting-human-action cards.
  - **A deliberate pause does not exempt it.** The case that produced this rule (pilot, 2026-08-04, a card parked four days) was a session that correctly refused to overwrite another worktree's uncommitted work and left a handoff note — but a card parked for a handoff that never comes is indistinguishable from an abandoned one, and both are invisible. The note belongs in the card's comments; the card belongs in Todo.

## 2. Cleared-gate pass — react to human decisions (global, claim-guarded)

For each **closed** `human-review` issue with no *finalized* `Processed:` comment — any lane. An in-progress claim (`Processed: (in progress — …)`) or a `(superseded)` one doesn't count; `kanban_check.sh` reports a gate held only by an in-progress claim older than 24 h as an abandoned claim:

1. Claim per the protocol above: re-fetch comments (still unclaimed?) → comment `Processed: (in progress — <operator> · <nonce>)` → re-fetch and verify yours is the earliest claim (lowest comment ID; lost → mark yours `(superseded)`, skip this gate). Finish by editing/replacing your winning claim with the real acknowledgment.
2. Read the closing comment(s) — that's the payload. A close with no contrary comment = approved.
3. Do what the card said it unblocks: file follow-on Todo cards (self-contained, Responsible = the AI-agent option, **assignee = you, the running operator** — the accountable human who is actually present; anyone may reassign later, wrong human beats no human), update gates in related Unshaped drafts, check off the HRQ entry if the card's ask covered it.
4. Mine the payload for *new information* beyond the approval (stakeholder observations, constraints) — each actionable insight becomes its own card rather than evaporating.
5. Finalize the acknowledgment: `Processed: <what you did, with links>`.
6. Payload ambiguous (partial approval, unclear caveat)? Leave the claim **in progress** (do not finalize it — a finalized `Processed:` would hide the gate from every later run), add a note saying what is unclear, ask the user; do not guess. If nobody answers, the claim ages past 24 h and the next session sees it reported as abandoned, which is the point: the gate is still unprocessed.

**Also scan OPEN gates for unacknowledged human comments** — humans sometimes deliver the payload without the signal (a comment, no close), and a closed-only scan leaves that input invisible until someone remembers to close. The authoritative query is **board Status = Awaiting human action** (open issues; any lane) — not the `human-review` label, which is convention and can be missed (the closed-gate pass above keys on the label only because closed cards have left the status columns). Scan each such card for a human comment newer than the last agent-marker comment:

Key on what the comment *asks for*:

- **Explicit, complete decision** ("approved", "use option B", the ask answered in full) → treat it as a cleared gate: claim per the protocol, process as above, and **restore the signal yourself** — close the issue with attribution ("Closing per 〈user〉's approval comment above"). The close-is-the-signal convention survives because the agent repairs it.
- **Change request / actionable feedback** ("revise the packet — X is wrong", "tighten this and show me again") → the gate is **re-armed** for agent work. **Edit your gate-claim marker** (the `Processed: (in progress — …)` from the claim protocol) **to append `(superseded)`** — the gate is out of your session's hands — **then post an `Agent:` acknowledgment** summarizing what was asked and that the card is being re-queued. Move the card to **Todo** with **Responsible = AI agent** and **assignee = the running operator**. **Do not start it now** — the re-armed gate is just another Todo candidate. **Normal step-4 lowest-issue-number selection decides whether this session's one work card is the re-armed gate or some other Todo; it is never automatically selected.** If step 4 picks it, move it to **Agent working**, do the requested work (normal conventions — md edits via worktree + PR, verification), reply on the issue with what changed and where to look, then move it **back to Awaiting human action**. One card oscillates across revision rounds — same semantics as change-requests on a PR. Never close it for the human: close is reserved for "my decision on this gate is complete" (approve, or reject-outright — which arrives as contrary-comment-then-close and is handled by the closed-gate pass above).
- **A question to the agent** → answer in a reply comment.
- **Ambiguous or partial** (mid-thought, caveat whose scope is unclear, feedback whose intended action you'd have to guess) → do **not** act and do **not** close; list it in step 3's queue output as "unacknowledged comment awaiting your read" and, if it's the operator's lane, ask them directly. Never guess a human's intent from a partial comment.

In every branch, an agent reply lands on the issue, and **every agent-authored comment on a gate card starts with a marker** — `Processed:`, `Claiming:`, or `Agent:` (for replies and re-presentations). The marker is what makes the scan boundary detectable: on a single-account repo, author gives you nothing, so *the last marker comment is the acknowledgment horizon* — any later comment without a marker is unacknowledged human input.

**After the marker, the first line states the ask.** `Agent:` / `Processed:` / `Claiming:`, then — on that same first line — what the human is being asked to do or decide right now, in plain language that needs no repo context. "Nothing right now, this is FYI" counts and should be said outright. Narrative, evidence and reasoning follow; they do not precede. The card's *last* comment is what a human actually reads, so it is the one that must carry a legible ask; when a comment changes what is being asked, the new ask goes on top rather than into a later paragraph. The same rule governs any new card this pass files: **first line of the body is the ask.** (Rationale: `PROCESS.md`, "Lead with the ask". It is also what lets `kanban_check.sh` extract a card's ask mechanically — a card that breaks the rule degrades to its bare title in the queue report.)

**Anything the human must read to clear a gate is committed and linked by permalink** — packets, transcripts, rendered artifacts. Never tell a reviewer to re-run a generator on the machine that produced it: that strands them on that machine and makes the approved thing unrecoverable later. If a gitignore rule would swallow the artifact, un-ignore it in the same PR.

**Markdown edits from this pass (HRQ check-offs, note updates) go through a temporary git worktree + the standard PR flow — never edit the launch working tree.** Another session may be mid-commit there (the pilot project has a scar: a parallel session's `commit -a` once swept 50 staged files into an unrelated commit). Git then serializes concurrent md writes: disjoint hunks merge cleanly, same-line collisions surface as loud PR conflicts instead of lost updates — and the gate claim already guarantees no two sessions touch the same HRQ entry. Batch all md edits from one run into a single PR.

## 3. Human nudge — report, don't nag

List Awaiting human action cards **assigned to the operator**: title, link, one-line ask each. Then, in one line, note any *other* lane's Awaiting-human card idle ≥ 7 days ("stale in X's lane: …") — visibility without nagging someone else's queue.

## 4. Pick work and start (your lane; poach if empty)

**One work card per session:** A session claims and works on **exactly one step-4 work card**. The limit is on *selection*, not on effort — winning a step-4 claim means the session selects no further cards; it does not mean the session is done. Every other Todo candidate stays Todo for a future session. The limit applies to step-4 work claims only — steps 0–3 may freely process multiple gates (each leaving its own `Processed:` claim marker) and re-queue cards to Todo without counting against it. Steps 0–3 must not leave additional cards in Agent working or with live step-4 `Claiming:` markers. If a gate's feedback created runnable work while another card is already selected, acknowledge it and return it to Todo rather than claiming it. This keeps the board available to other agents and makes the session's commitment unambiguous.

- Candidates: Status = Todo, Responsible = `AI agent`, assignee = operator.
- If the user passed an argument (e.g. `next report`), use it to filter/pick the matching card.
- Otherwise pick the lowest issue number (earlier cards tend to set up later ones); say what you picked and why in one line.
- **Claim before work** (protocol above): only this one selected card may be claimed (the invariant above). If Status is already Agent working, or a live `Claiming:` comment exists, another session took it — pick the next candidate (step 1's stale work-claim sweep is what keeps "took it" from meaning "forever"). Otherwise comment `Claiming: <operator> · <nonce>`, verify yours is the earliest (lowest comment ID; lost → next card), *then* move it to Agent working and begin **with step 5 (plan with the human)** — no edits before the plan is approved — following the card body and repo conventions (PR flow, review chain, verification). **Read the card's comments before starting (2026-07-29): humans attach guidance to Todo cards** (constraints, access routes, changed context) **that the open-gate scan deliberately doesn't cover — at pickup, the comments are part of the spec.** If a comment contradicts the card body (scope narrowed, approach changed), the comment is newer but don't guess: surface the conflict to the operator before starting.
- **Lane empty?** You may poach: a Todo card in another lane with the AI-agent Responsible (never a human-action card) → win the `Claiming:` arbitration first (note `(poaching from 〈previous assignee〉 — lane empty)` in the comment), then reassign it to your operator and proceed as above. This is what keeps agent-work from silently waiting on another developer's next session.
- Nothing anywhere? Say the board is drained, summarize the 2–3 most actionable Unshaped drafts (their gates permitting) and offer to shape one.

## 5. Plan with the human — the first human-in-the-loop gate

**After the claim is won and before any change is made, the human approves a plan.** `next` is user-triggered, so the operator is present; this step makes sure they engage with *what* gets built, not only with the PR at the end. It applies in every harness — Claude Code, OpenCode, Codex, or anything else that runs this file.

1. **Investigate first, read-only.** Read the card body and every comment (the spec), the files and symbols it touches, and the conventions that govern them. Nothing is edited, branched, or committed in this step.
2. **Ask questions while you plan — that is encouraged, not a failure.** Wherever the card leaves a real choice open (scope edges, approach, user-facing wording, trade-offs, what "done" looks like), ask the human rather than picking silently. Prefer a few sharp questions with concrete options and your recommendation over a long questionnaire. Use your tool's question or plan-approval interface if it has one (e.g. a plan mode or a multiple-choice prompt); otherwise ask in plain text and **stop and wait for the answer** — do not continue in the same turn on an assumed answer.
3. **Present the plan**, short and concrete: the outcome in one line; the files/areas that change; the approach and any decision the human made when answering your questions; what is explicitly out of scope; how it will be verified; and **whether the change alters what a user sees or does** (this decides the shape of step 7's hand-off — say which now so the human can disagree).
4. **Wait for explicit approval.** "Yes", "go", or an edited plan counts; silence, or a reply to a different question, does not. Requested changes → revise and present again. Do not begin step 6 without approval.
5. **Record the approved plan on the card** as an `Agent:` comment (first line: "Plan approved by 〈operator〉 — nothing needed from you right now"), so the next session, the reviewer, and the human all see the same spec. A plan the human trimmed or redirected is the spec from here on; if the card body now disagrees with it, say so in that comment.

If the session ends before the plan is approved, that is a recorded blocker (step 6's third end state): post the draft plan and the open questions as an `Agent:` comment whose first line is the question the human must answer, and return the card to **Todo**.

## 6. Do the work — this is what the session delivers

**Winning the claim is the start of the work, not the end of it.** Steps 0–4 produce a report and a claim, step 5 produces an approved plan; the session produces a *change*. With the plan approved and the card in Agent working, keep going: do the work the plan describes, verify it the way this repo verifies things (the relevant test suites, a headless-browser check for UI, the review chain in AGENTS.md), then run step 7 **before** opening the PR. If the work reveals that the approved plan is wrong or incomplete in a way that changes what gets built, stop and re-confirm with the human rather than drifting from what they approved.

A finished session ends in exactly one of these states:

- a **PR open for review** (only after step 7's hand-off was accepted), linked from the card, with the `Claiming:` marker followed by an `Agent:` comment saying what landed and where to look — card in Awaiting code review; or
- the work **merged**, local branch and worktree cleaned up per AGENTS.md — card in Done; or
- a **recorded blocker**: what you tried, what stopped you, and what the next session needs, commented on the card, with the card returned to **Todo** (or left in Agent working behind a *draft* PR — that is what a draft PR is for, and step 1's sweep exempts it). An unapproved plan (step 5) and an unaccepted hand-off (step 7) are both recorded blockers of this kind.

Anything else is an unfinished session. In particular, **a session that ends with a claim comment and a board move has produced no work at all** — it leaves the card marked as being worked by a session that has stopped, which is worse for the board than never having claimed it. Step 1's stale work-claim sweep exists to clean up after exactly this, 24 hours later. Pausing at step 5 or step 7 *to wait for the human's answer* is not stopping — those are the two places this procedure deliberately hands the turn back; ending the session there without recording the blocker is.

**Why this needs saying (pilot, 2026-09-03).** Stopping at the claim became a recurring failure once the orientation passes moved into `process/kanban_check.sh`. When orientation was expensive, a session reached step 4 with warm context and real momentum and carried straight into the card. Twelve seconds of script removes that: the session arrives at the pick having read no code, invested nothing, and holding a clean terminal state — marker posted, board truthful, plus a report that reads like a delivered answer. Stopping there *feels* like completion. It is not. The report is a preamble; the human invoked `next` to get the work.

## 7. Hand-off before the PR — the second human-in-the-loop gate

**Before the PR is published for review** (before a ready-for-review `gh pr create`, and before marking a draft ready — a *draft* PR opened to park unfinished work as a recorded blocker is exempt), the human gets two things and decides whether to publish:

1. **A fresh-eyes review, with its results.** Have a reviewer with *no* access to this session's context review the change: a fresh subagent in your harness, or a separate agent process (another tool's non-interactive mode works) — given only the card number, the branch/diff, and "review this for defects; report findings, do not edit". Context-blindness is the point: it reviews what was built, not what you meant. Judge each finding against the code, fix the ones that hold, and say why for any you decline. Re-review after substantive fixes. Then show the human the findings and what you did about each — not just "review passed". (This is in addition to any review gate AGENTS.md requires on the open PR, not a replacement for it.)
2. **Testing — shaped by whether the user experience changed** (as declared in the plan; re-check against the actual diff):
   - **No user-visible change** (refactors, internal plumbing, build/CI, docs, back-end logic with no change to what anyone sees or does): a **testing report** — what was run (exact commands), results with counts, what new or changed tests cover, and what is *not* covered.
   - **The user experience changed** (new or changed screens, copy, flows, outputs, commands a person runs): the testing report **plus a proposed manual test** for the human to go do — how to launch or reach it (exact commands/URLs), concrete steps to see, play with, and try the new or changed behaviour, what they should observe, and one or two edge cases worth poking. Write it so it can be followed without this conversation. Then wait: the human runs it and reports back (or explicitly chooses to defer it to PR review — record that in the PR body).

Publish only after the human says to. Issues they find become fixes in this branch (re-run the affected parts of this step), not follow-up cards, unless they say otherwise. Put the testing report and, where applicable, the manual test (and its outcome) in the PR body, so the code reviewer sees the same evidence the human did.

## Output shape — the preamble

**The orientation report is the preamble, not the deliverable.** Keep it short: what was synced (one line per fix, plus any stale-draft note from step 1's sweep), gates processed (what each unblocked), the human's queue, and the pick with a one-line why. Then stop reporting and start planning (step 5) — the session ends per step 6, on a PR, a merge, or a recorded blocker, with the two human hand-offs (steps 5 and 7) along the way.
