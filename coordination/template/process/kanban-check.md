# kanban-check — read-only board orientation report (tool-neutral procedure)

Produces the orientation *report* for the `next` procedure without acting on anything. It is implemented by `process/kanban_check.sh`, which a `next` session runs directly; this file is that script's specification and the procedure to follow by hand if it cannot run. Either way it is directly useful to a human who wants a board snapshot with nothing touched.

## Run the script

```
process/kanban_check.sh                 # the report, on stdout
process/kanban_check.sh --comments full # verbatim candidate comments instead of first lines
```

`process/kanban_check.sh` computes this report deterministically and is the normal way to produce it — a session running `next` invokes it directly, no delegate involved. It prints the report between `=== KANBAN-CHECK REPORT ===` and `=== END KANBAN-CHECK REPORT ===`, so extraction from any log is one command:

```
sed -n '/=== KANBAN-CHECK REPORT ===/,/=== END KANBAN-CHECK REPORT ===/p' <output-file>
```

**Why a script and not a model** (pilot evidence, 2026-09-01). Every finding below is a predicate over board/issue/PR JSON — a join, a date comparison, a regex on a comment prefix. None of it needs judgement, and delegating it went wrong in ways a script cannot: a delegated run reported three issue numbers that **did not exist**, six closed issues as open Todo candidates, swapped two cards' titles, and wrote a file into the launch checkout in direct violation of the READ-ONLY rule below. Measured cost of the script against that delegated run: ~12 s and ~4 KB, versus several minutes and a 212 KB transcript. The script also makes the read-only rule structural rather than aspirational — it is a short file you can audit, and it calls no mutating verb.

**What the script deliberately does NOT do**, because these are judgement and belong to the session reading the report:

- **Classify a post-horizon comment** as decision / change request / question / ambiguous. The script prints such comments verbatim and labels them unclassified.
- **Decide HRQ consolidation by category** (see step 2). It resolves links in both directions — an item naming a card, and a card whose title or body names the item (`HRQ #5`) — and reports what it found; whether an unlinked item falls into a consolidated *category* is the reader's call.
- **Any mutation whatsoever.** Claims, card moves, comments, closes and follow-on cards are the orchestrating session's, always.

The rest of this file is the specification the script implements, and the procedure to follow by hand if it cannot run.

It also exists so that a *model* running these passes — still permitted, just no longer the default — never reads `process/next.md`'s write-bearing steps, which is what makes a delegation loop impossible by construction: **this file contains no delegation policy, no writes, and no instruction to open `next.md`; whoever runs it does all of its steps themselves.** That third clause is load-bearing, and the pilot shipped it missing: step 0 used to tell the delegate to read `next.md` for conventions, so the isolation the paragraph claimed was contradicted by the procedure itself, and a real delegate run read the whole file. Every rule this procedure needs is restated here in full — where a rule originated in `next.md`, it is quoted inline rather than cross-referenced, so there is never a reason to go look.

## Absolute rules

- **READ-ONLY.** Never run `gh project item-edit`/`item-add`/`item-create`/`item-delete`, `gh issue create/comment/close/edit/reopen`, any `gh pr` mutation, `gh api -X POST/PATCH/PUT/DELETE`, or any repo file edit. Where the board would need a write, report the exact intended command instead.
- **The permitted git commands are exactly these** — an allowlist, because "no git writes" invites a judgement call and loses it (pilot, 2026-08-24: a delegate substituted `git fetch origin --prune` for step 0's fetch and deleted two remote-tracking refs; harmless that day, but pruning rewrites the local ref store and changes what the orchestrator's own hygiene check sees afterwards):
  - `git fetch origin main -q` — **exactly this, no `--prune`, no bare `git fetch`** (step 0's freshness check)
  - `git status --short --branch` — branch, ahead/behind, dirty state (step 0)
  - `git show origin/main:<path>` — reading AGENTS.md and HUMAN-REVIEW-QUEUE.md from the remote tip (steps 0 and 1)
  - `git worktree list`, `git branch --format=…` — local hygiene reporting (step 0)
  - `git ls-remote --heads origin` — **this is the form that answers step 2's "no remote branch" question.** `git branch -r` cannot: the fetch above is pinned to `main`, so remote-tracking refs for other branches are never materialised locally and a branch listing would report every one of them as absent. `ls-remote` asks the remote directly and writes nothing.

  Anything else with a `git` in front of it — including flags that only touch local refs — is a write for the purposes of this procedure. Report it as intended instead of running it.

  The precise invariant is **no working-tree writes and no remote mutations**, not "no writes at all": `git fetch` updates `.git/FETCH_HEAD`, and `gh` maintains its own caches. Neither changes a tracked file, a branch, an issue, a PR, or the board.
- **NON-RECURSIVE.** Run every step yourself; never spawn another agent or `opencode run`.
- Comments quoted for the GATES/CANDIDATES sections are reported **verbatim** — interpretation (decision vs change request vs ambiguous) belongs to the orchestrator, not to this report.

## Steps

The operator is `gh api user --jq .login` unless the invoker names one.

0. **Freshness**: `git fetch origin main -q && git status --short --branch` — report branch, ahead/behind, dirty state. Also report local hygiene: `git worktree list` and local branches beyond `main`, so drift is visible (cleanup itself belongs at merge time and is the orchestrator's call, never this procedure's). Board conventions (field and option IDs, the plumbing recipe, card-body rules) come from `git show origin/main:AGENTS.md` — read from `origin/main`, not the working tree, since the tree may be stale or on a feature branch. **Do not open `process/next.md`.** It is the write-bearing procedure and the one file this one exists to keep out of a delegate's context; everything you need from it is already restated below.
1. **Pull state**:
   - Board, live work only: `gh project item-list <BOARD_NUMBER> --owner <BOARD_OWNER> --query "-status:Done" --limit 200 --format json`. `--query` filters **server-side**, so it shrinks what `--limit` must cover (the pilot's board went 101 → 44 items this way on 2026-08-13); a `jq` filter would not, since `--limit` truncates at fetch, before anything client-side runs.
   - **Guard every board fetch against truncation** — compare `totalCount` to the number of items returned and stop if they differ. The pilot's board outgrew `--limit 100` on 2026-08-13 and the only symptom was a card that appeared not to exist:
     `… | jq -e '.totalCount as $t | (.items|length) as $n | if $t == $n then . else error("TRUNCATED: \($n) of \($t)") end'`
   - **Closed gates do NOT come from the board** — they sit in Done, which the query above excludes on purpose. Use the issue API, asking for `comments` in the same call since step 3 needs to know whether a `Processed:` marker is present: `gh issue list -R <REPO_SLUG> --label human-review --state closed --limit 100 --json number,title,comments`. **This call cannot use the `totalCount` guard** (`gh issue list` has no such field — asking for it errors); guard it by comparing the number returned against the limit, and treating equality as truncation, since "exactly 100" and "at least 100" are indistinguishable. Open gates still come from the board (`status:"Awaiting human action"`).
   - `gh pr list -R <REPO_SLUG> --json number,title,isDraft,url`; `HUMAN-REVIEW-QUEUE.md` from origin/main.
2. **Sync findings**: cards whose issue is closed / PR merged but Status ≠ Done; open non-draft PRs with no card *and not already tracked* (detection: a `Closes #N` / `Fixes #N` in the PR body, an `issue-N` branch name, or an entry in the issue's linked-development section — if that issue has a card in Awaiting code review the PR is covered, so don't report it as an orphan); open HRQ items with no card — **excluding items already covered by a consolidated tracking card**, i.e. where the item itself names the card that tracks it, or a note at the top of `HUMAN-REVIEW-QUEUE.md` names a card for a whole *category* the item falls into (match by category, not by enumeration; report these as covered, not as orphans). **The exception covers *review* items only** — items a human decides. An HRQ item describing executable build work is not consolidated by it, and a missing card for such work is a real finding. Checked-off HRQ items whose cards are still open; **stale work claims** — cards in **Agent working** whose newest agent-marker comment (`Claiming:` / `Agent:`) is older than 24 h with no open PR referencing them and no remote branch (report the card, the marker's age, and the marker quoted verbatim; a draft PR means not stale — say so and move on).

   State only what you actually tested. Reporting "remote branch present" for a card whose claim was simply younger than the threshold — where no branch was ever checked — is a fabricated justification, and the script is written to avoid exactly that.
3. **Gate findings**: closed `human-review` issues with no `Processed:` comment; open Awaiting-human-action cards with human comments newer than the last agent-marker comment (`Processed:` / `Claiming:` / `Agent:`) — quote them verbatim.
4. **Queue + candidates**: the operator's Awaiting-human-action cards (issue number, title, and the one-line ask taken from the first non-empty line of the issue body — the "lead with the ask" rule in AGENTS.md is what makes that mechanical; a card that breaks the rule degrades to its title rather than reporting something that is not the ask), plus a one-line note for any *other* lane's Awaiting-human card idle ≥ 7 days (visibility without nagging someone else's queue); Todo cards with Responsible = AI agent in the operator's lane (plus poachable agent-work Todos in other lanes if the lane is empty), **each carrying its issue number as `#<number> — <title>`** and sorted by number. Selection upstream is by lowest issue number, so a candidate list without numbers cannot drive the pick it exists to drive. Comments: the first line of each is enough to show guidance exists (the session reads the picked card's comments in full before starting anyway); `--comments full` quotes them verbatim. **Post-horizon gate comments in step 3 are always verbatim** — those are payload, not signal.

## Report format

The report begins with a fixed marker line on its own, with nothing of the report before it, and ends with the closing marker:

```
=== KANBAN-CHECK REPORT ===
STEP0: <freshness, one line>
SYNC: <intended action per line, with the exact command where the action is determinate, or "none">
GATES: <each gate + verbatim payload quotes, or "none">
QUEUE: <#number — title, then an indented "ask:" line per awaiting-human card>
CANDIDATES: <#number — title, sorted by number, plus comments, or "none">
=== END KANBAN-CHECK REPORT ===
```
