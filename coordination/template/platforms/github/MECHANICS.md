# GitHub mechanics — the plumbing recipe (adapter reference)

The platform-specific half of the coordination pattern on **GitHub**. Read this when you are **writing or changing** the GitHub adapter (`next.md`, `kanban-check.md`, `kanban_check.sh`, `setup.md`). A session running `next` never needs it.

## Auth + transport

- **`gh` CLI**, authenticated with the `project` scope (`gh auth refresh -s project`). The operator is `gh api user --jq .login`.

## The board = a GitHub Project

- **Board**: one Projects v2 project. `gh project item-list <BOARD_NUMBER> --owner <BOARD_OWNER> --query "-status:Done" --limit 200 --format json`. `--query` filters **server-side** (shrinks `totalCount` itself).
- **Cards**: issues; **drafts** are board-only items (the "Unshaped" plan).
- **Fields**: Status (single-select, 6 options), Responsible (single-select).
- **Labels**: `human-review`, `agent-work`, `stakeholder`.

## Status = a single-select field

| Coordination status | Status option |
|---|---|
| Unshaped | Unshaped |
| Todo | Todo |
| Agent working | Agent working |
| Awaiting code review | Awaiting code review |
| Awaiting human action | Awaiting human action |
| Done | Done |

**Renaming or adding options via `updateProjectV2Field` regenerates every option id and silently clears every item's Status** — snapshot `item-list` first, re-apply, then re-wire the built-in workflows.

## Truncation guards

- **Board fetch**: compare `totalCount` to the items returned — `jq -e '.totalCount as $t | (.items|length) as $n | if $t == $n then . else error("TRUNCATED: \($n) of \($t)") end'`.
- **`gh issue list` / `gh pr list` have no `totalCount`** — use the returned-equals-limit tripwire; refetch once at double, then a `LIMITS:` line. Never `-status:Done` when hunting cleared gates (closed gate cards live in Done).
- **Ad-hoc lookups** are the real trap — use `gh issue view <n>`, which cannot truncate.

## The verbs (what the procedure maps them to)

| Verb | `gh` |
|---|---|
| `orient` | `gh project item-list` + `gh issue list` + `gh pr list` |
| `status` / `tag` / `assign` | `gh project item-edit --field-id … --single-select-option-id …` |
| `comment` | `gh issue comment <n> --body …` |
| `create` | `gh issue create` then `gh project item-add` |
| `claim` | comment `Claiming: …`; arbitrate by comment id |
| `pr` | `gh pr create --draft` |

**No `pr-ready` / `pr-merge` verb** — only the human promotes (`gh pr ready`) and merges. The procedure never calls those.

## Repo scoping

`<REPO_SLUG>`, `<BOARD_OWNER>`, `<BOARD_NUMBER>`, `<PROJECT_ID>`, `<STATUS_FIELD_ID>`, `<RESPONSIBLE_FIELD_ID>`, `<OPT_*>` live in `board.conf`.
