# kanban-check — read-only board orientation report (tool-neutral procedure)

Produces the orientation *report* for the `next` procedure without acting on anything. This is the procedure a `next` orchestrator delegates to opencode (see next.md, "Delegation"), and it is directly useful to a human who wants a board snapshot with nothing touched. It exists so a delegate never reads next.md's write-bearing steps — which is what makes a delegation loop impossible by construction: **this file contains no delegation policy; whoever runs it does all of its steps themselves.**

## Absolute rules

- **READ-ONLY.** Never run `gh project item-edit`/`item-add`/`item-create`/`item-delete`, `gh issue create/comment/close/edit/reopen`, any `gh pr` mutation, `gh api -X POST/PATCH/PUT/DELETE`, any git write (checkout/pull/commit/push), or any repo file edit. Where the board would need a write, report the exact intended command instead.
- **NON-RECURSIVE.** Run every step yourself; never spawn another agent or `opencode run`.
- Comments quoted for the GATES/CANDIDATES sections are reported **verbatim** — interpretation (decision vs change request vs ambiguous) belongs to the orchestrator, not to this report.

## Steps

The operator is `gh api user --jq .login` unless the invoker names one.

0. **Freshness**: `git fetch origin main -q && git status --short --branch` — report branch, ahead/behind, dirty state. Read conventions from `origin/main` (`git show origin/main:AGENTS.md`, `git show origin/main:process/next.md`) rather than the working tree when the tree is stale or on a feature branch.
1. **Pull state**: `gh project item-list <BOARD_NUMBER> --owner <BOARD_OWNER> --limit 100 --format json` (never omit `--limit`); `gh pr list --json number,title,isDraft,url`; `HUMAN-REVIEW-QUEUE.md` from origin/main.
2. **Sync findings**: cards whose issue is closed / PR merged but Status ≠ Done; open non-draft PRs with no card *and not already tracked* (detection per next.md: `Closes #N` / `issue-N` branch → that issue's card in Awaiting code review); open HRQ items with no card; checked-off HRQ items whose cards are still open.
3. **Gate findings**: closed `human-review` issues with no `Processed:` comment; open Awaiting-human-action cards with human comments newer than the last agent-marker comment (`Processed:` / `Claiming:` / `Agent:`) — quote them verbatim.
4. **Queue + candidates**: the operator's Awaiting-human-action cards (issue number + one-line ask), plus a one-line note for any *other* lane's Awaiting-human card idle ≥ 7 days (mirrors next.md step 3's staleness visibility); Todo cards with Responsible = AI agent in the operator's lane (plus poachable agent-work Todos in other lanes if the lane is empty), each with any comments quoted verbatim.

## Report format

```
STEP0: <freshness, one line>
SYNC: <intended action per line with exact commands, or "none">
GATES: <each gate + verbatim payload quotes, or "none">
QUEUE: <one line per awaiting-human card>
CANDIDATES: <Todo candidates + verbatim comments, or "none">
```
