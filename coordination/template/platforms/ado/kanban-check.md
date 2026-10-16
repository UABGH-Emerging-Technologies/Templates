# kanban-check — read-only board orientation report (tool-neutral procedure)

Produces the orientation *report* for the `next` procedure without acting on anything. It is implemented by `process/kanban_check.sh`, which a `next` session runs directly; this file is that script's specification and the procedure to follow by hand if it cannot run. Either way it is directly useful to a human who wants a board snapshot with nothing touched.

**The board is one Epic's subtree, not a whole project.** Data Science holds ~22,779 work items, so a GitHub-style "read the whole board" pass is impossible — the read *must* be scoped. A coordination board is a single **Epic** (or a **Feature**), and the board is that item plus its `Hierarchy-Forward` descendants, read with WIQL. Tens of items, not thousands. The scope is therefore a required argument. (Model and rationale: `docs/coordination-ado/PLAN.md`.)

## Run the script

```
process/kanban_check.sh --scope <Epic|Feature id>          # the report, on stdout
process/kanban_check.sh --scope <id> --comments full       # verbatim candidate comments instead of first lines
process/kanban_check.sh --scope <id> --operator "Name"     # override the operator (default: the PAT's user)
process/kanban_check.sh --scope <id> --no-fetch            # skip the `git fetch` freshness step
```

`process/kanban_check.sh` computes this report deterministically and is the normal way to produce it — a session running `next` invokes it directly, no delegate involved. It prints the report between `=== KANBAN-CHECK REPORT ===` and `=== END KANBAN-CHECK REPORT ===`, so extraction from any log is one command:

```
sed -n '/=== KANBAN-CHECK REPORT ===/,/=== END KANBAN-CHECK REPORT ===/p' <output-file>
```

**Why a script and not a model** (pilot evidence, 2026-09-01). Every finding below is a predicate over work-item/PR JSON — a join, a date comparison, a regex on a comment prefix. None of it needs judgement, and delegating it went wrong in ways a script cannot: a delegated run reported three issue numbers that **did not exist**, six closed issues as open Todo candidates, swapped two cards' titles, and wrote a file into the launch checkout in direct violation of the READ-ONLY rule below. Measured cost of the script against that delegated run: seconds and a few KB, versus several minutes and a 212 KB transcript. The script also makes the read-only rule structural rather than aspirational — it is a short file you can audit, and the transport it sources (`process/ado_api.sh`) refuses every mutating call before it builds a request.

**What the script deliberately does NOT do**, because these are judgement and belong to the session reading the report:

- **Classify a post-horizon comment** as decision / change request / question / ambiguous. The script prints such comments verbatim and labels them unclassified.
- **Decide HRQ consolidation by category** (see step 2). It resolves links in both directions — an item naming a card, and a card whose title or body names the item (`HRQ #5`) — and reports what it found; whether an unlinked item falls into a consolidated *category* is the reader's call.
- **Any mutation whatsoever.** Claims, card moves, comments, closes and follow-on cards are the orchestrating session's, always.

The rest of this file is the specification the script implements, and the procedure to follow by hand if it cannot run.

It also exists so that a *model* running these passes — still permitted, just no longer the default — never reads `process/next.md`'s write-bearing steps, which is what makes a delegation loop impossible by construction: **this file contains no delegation policy, no writes, and no instruction to open `next.md`; whoever runs it does all of its steps themselves.** Every rule this procedure needs is restated here in full — where a rule originated in `next.md`, it is quoted inline rather than cross-referenced, so there is never a reason to go look.

## Absolute rules

- **READ-ONLY.** The transport is pinned read-only — `kanban_check.sh` exports `ADO_READONLY=1`, and `process/ado_api.sh` makes every mutation helper (`ado_post`, `ado_patch`) refuse before it builds a request. Never call those helpers with the guard off, never `PATCH` a work item, never post a comment, never create or complete a PR. Where the board would need a write, report the exact intended call instead.
- **The permitted git commands are exactly these** — an allowlist, because "no git writes" invites a judgement call and loses it (pilot, 2026-08-24: a delegate substituted `git fetch origin --prune` for step 0's fetch and deleted two remote-tracking refs; harmless that day, but pruning rewrites the local ref store and changes what the orchestrator's own hygiene check sees afterwards):
  - `git fetch origin main -q` — **exactly this, no `--prune`, no bare `git fetch`** (step 0's freshness check)
  - `git status --short --branch` — branch, ahead/behind, dirty state (step 0)
  - `git show origin/main:<path>` — reading AGENTS.md and HUMAN-REVIEW-QUEUE.md from the remote tip (steps 0 and 1)
  - `git worktree list`, `git branch --format=…` — local hygiene reporting (step 0)
  - `git ls-remote --heads origin` — **this is the form that answers step 2's "no remote branch" question.** `git branch -r` cannot: the fetch above is pinned to `main`, so remote-tracking refs for other branches are never materialised locally and a branch listing would report every one of them as absent. `ls-remote` asks the remote directly and writes nothing.

  Anything else with a `git` in front of it — including flags that only touch local refs — is a write for the purposes of this procedure. Report it as intended instead of running it.

  The precise invariant is **no working-tree writes and no remote mutations**, not "no writes at all": `git fetch` updates `.git/FETCH_HEAD`, and the ADO transport keeps no on-disk state. Neither changes a tracked file, a branch, a work item, or a PR.
- **NON-RECURSIVE.** Run every step yourself; never spawn another agent or `opencode run`.
- Comments quoted for the GATES/CANDIDATES sections are reported **verbatim** — interpretation (decision vs change request vs ambiguous) belongs to the orchestrator, not to this report.

## The status machine (read from state + tags, not from columns)

ADO's native Agile states cannot express the six coordination statuses, so the script derives them. **The board's columns are a view; the script keys on `System.State` plus the tag `human-review`**, because "Awaiting code review" and "Awaiting human action" both map to `User Story: Resolved`:

| Coordination status | Native state | Carrier |
|---|---|---|
| Unshaped | `Feature: New` | Feature type (the Features board's "Unshaped") |
| Todo | `User Story: New` | User Story |
| Agent working | `User Story: Active` | User Story |
| Awaiting code review | `User Story: Resolved` | User Story (no tag) |
| Awaiting human action | `User Story: Resolved` | **tag `human-review`** |
| Done | `User Story: Closed` | User Story |

Tags carry the rest: **`agent-work`** is the "Responsible = AI agent" carrier (a custom picklist field would need process customization / a Collection Admin, and is not assumed), **`human-review`** is "Awaiting human action" (D6), and **`stakeholder`** routes a card to relay delivery. `System.AssignedTo` is an identity object — match on `.displayName`. The script reads `System.BoardColumn` too, but only to report; it never keys on board position.

## Steps

The operator is the PAT's user (`GET _apis/connectionData` → `.authenticatedUser.providerDisplayName`) unless the invoker names one.

0. **Freshness**: `git fetch origin main -q && git status --short --branch` — report branch, ahead/behind, dirty state. Also report local hygiene: `git worktree list` and local branches beyond `main`, so drift is visible (cleanup itself belongs at merge time and is the orchestrator's call, never this procedure's). Board conventions (team, area, tags, states, the plumbing recipe, card-body rules) come from `git show origin/main:AGENTS.md` — read from `origin/main`, not the working tree, since the tree may be stale or on a feature branch. **Do not open `process/next.md`.** It is the write-bearing procedure and the one file this one exists to keep out of a delegate's context; everything you need from it is already restated below.
1. **Pull state** — the scope's subtree is the board:
   - **The subtree**: WIQL `SELECT [System.Id] FROM WorkItemLinks WHERE ([Source].[System.Id] = <scope>) AND ([System.Links.LinkType] = 'System.LinkTypes.Hierarchy-Forward') MODE(Recursive)`. **`MODE(Recursive)`, not `MODE(MustContain)`** — MustContain returns only *direct* children and silently drops grandchildren (a User Story under a Feature under the Epic); verified 2026-10-15. The source item itself appears as a rel-less first relation and is collected too.
   - **The items**: `GET …/_apis/wit/workitems?ids=<ids>&fields=…` — **ADO caps a batch at 200 ids**, so the transport chunks and merges; a subtree bigger than one chunk is normal. Fields read: `System.Id`, `System.WorkItemType`, `System.Title`, `System.State`, `System.Tags`, `System.AssignedTo`, `System.AreaPath`, `System.BoardColumn`, `System.CreatedDate`, `System.ChangedDate`.
   - **Comments** for every card: `GET …/_apis/wit/workItems/<id>/comments` — **this API is still preview on this server and needs `api-version=6.0-preview`** (`6.0` returns HTTP 400; verified 2026-10-15). N calls, but the subtree is tens of items.
   - **PRs**: `GET …/_apis/git/repositories/<repo-id>/pullrequests?searchCriteria.status=all`. This is the **only unbounded fetch** (capped at `$top=1000` in the transport); a full page is ambiguous ("exactly 1000" vs "at least 1000"), so the script reports a `LIMITS:` line rather than aborting — a short list the reader knows about is recoverable, no report at all is not. One retry, never a loop.
   - **PR → work-item links**: `GET …/pullrequests/<pr-id>/workitems` — the ADO analogue of GitHub's closing-issues reference, and what the sync pass matches a card against.
   - `HUMAN-REVIEW-QUEUE.md` from origin/main.
   - There is **no separate "closed gates come from the issue API" split** as on GitHub: the subtree read returns every state, so closed gates and open gates both come from the same fetch.
2. **Sync findings**: cards whose work item is closed / PR completed but status ≠ Done; cards in Agent working whose PR exists (draft or ready) and so belong in Awaiting code review; open PRs (draft or ready) with no card *and not already tracked* (detection: a `Fixes #N` in the PR body, an `issue-N` branch name, or the PR's linked-work-items call — if that work item has a card in Awaiting code review the PR is covered, so don't report it as an orphan); open HRQ items with no card — **excluding items already covered by a consolidated tracking card**, i.e. where the item itself names the card that tracks it, or a note at the top of `HUMAN-REVIEW-QUEUE.md` names a card for a whole *category* the item falls into (match by category, not by enumeration; report these as covered, not as orphans). **The exception covers *review* items only** — items a human decides. An HRQ item describing executable build work is not consolidated by it, and a missing card for such work is a real finding. Checked-off HRQ items whose cards are still open; **stale work claims** — cards in **Agent working** whose newest agent-marker comment (`Claiming:` / `Agent:`) is older than 24 h with no open PR referencing them (any of the three routes above: body keyword, `issue-N` branch, linked-work-items entry) and no remote branch (report the card, the marker's age, and the marker quoted verbatim; a card with a PR is not stale — say so and move on).

   State only what you actually tested. Reporting "remote branch present" for a card whose claim was simply younger than the threshold — where no branch was ever checked — is a fabricated justification, and the script is written to avoid exactly that.
3. **Gate findings**: closed items tagged `human-review` with no **finalized** `Processed:` comment — an in-progress claim (`Processed: (in progress — …)`) or a `(superseded)` one does not count, because a session that dies mid-claim, or stops to ask the human a question, must not hide the decision from every later run. Report a gate whose only live marker is an in-progress claim as *in progress* while that claim is under 24 h old, and as an **abandoned claim** (supersede it and process the gate) once it is older; open Awaiting-human-action cards (state `Resolved` + tag `human-review`) with human comments newer than the last agent-marker comment (`Processed:` / `Claiming:` / `Agent:`) — quote them verbatim.
4. **Queue + candidates**: the operator's Awaiting-human-action cards (work-item number, title, and the one-line ask taken from the first non-empty line of the work-item body — the "lead with the ask" rule in AGENTS.md is what makes that mechanical; a card that breaks the rule degrades to its title rather than reporting something that is not the ask), plus a one-line note for any *other* lane's Awaiting-human card idle ≥ 7 days (visibility without nagging someone else's queue); Todo cards tagged `agent-work` assigned to the operator (plus poachable `agent-work` Todos in other lanes if the lane is empty), **each carrying its work-item number as `#<number> — <title>`** and sorted by number. Selection upstream is by lowest work-item number, so a candidate list without numbers cannot drive the pick it exists to drive. Comments: the first line of each is enough to show guidance exists (the session reads the picked card's comments in full before starting anyway); `--comments full` quotes them verbatim. **Post-horizon gate comments in step 3 are always verbatim** — those are payload, not signal.

## Report format

The report begins with a fixed marker line on its own, with nothing of the report before it, and ends with the closing marker:

```
=== KANBAN-CHECK REPORT ===
STEP0: <freshness, one line; plus operator, scope, dirty state, worktrees>
SYNC: <intended action per line, with the exact call where the action is determinate, or "none">
GATES: <each gate + verbatim payload quotes, or "none">
QUEUE: <#number — title, then an indented "ask:" line per awaiting-human card>
CANDIDATES: <#number — title, sorted by number, plus comments, or "none">
LIMITS: <only when the PR list filled its cap — the list that may be short; absent otherwise>
=== END KANBAN-CHECK REPORT ===
```
