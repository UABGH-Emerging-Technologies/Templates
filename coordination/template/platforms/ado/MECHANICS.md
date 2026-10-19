# ADO mechanics — the plumbing recipe (adapter reference)

The platform-specific half of the coordination pattern on **Azure DevOps Server (on-prem)**. Read this when you are **writing or changing** the ADO adapter (`board.sh`, `kanban_check.sh`, `ado_api.sh`, `setup.md`). A session running `next` never needs it — it calls `process/board.sh <verb>`.

## Auth + transport

- **REST + PAT.** `az devops` / `az boards` / `az repos` are cloud-only and reject this host — there is no command-swap path; the port is a REST rewrite. Do not reintroduce them.
- `process/ado_api.sh` is the transport: source it. It holds the base URL (`ADO_BASE`), the project (`ADO_PROJECT`), the api-version pin (`ADO_API=6.0`), the comments version (`ADO_COMMENTS_API=6.0-preview`), the read-only guard (`ADO_READONLY`), and the helpers `ado_get`/`ado_query`/`ado_post`/`ado_patch`/`ado_wiql`/`ado_subtree`/`ado_workitems`/`ado_comments`/`ado_prs`/`ado_pr_workitems`.
- **Auth**: `Authorization: Basic base64(":" + $ADO_PAT)`. The PAT is read from the environment (`ADO_PAT`, kept in `~/.profile`), never written to disk. Scopes: `vso.work_write`, `vso.code_write`, `vso.project` (collection-scoped).
- **IIS Basic Authentication must be disabled** on the server, or PATs cannot reach ADO.
- **api-version is pinned** — a wrong version is the top on-prem failure mode. `6.0` is GA for everything read here; the **work-item comments API is still preview** and needs `6.0-preview` (`6.0` → HTTP 400).

## The board = one Epic's subtree

Data Science holds ~22,779 work items, so a whole-project read is impossible. The board is a single **Epic** and its `Hierarchy-Forward` descendants, in a team scoped to an area path.

- **Subtree read**: `SELECT [System.Id] FROM WorkItemLinks WHERE ([Source].[System.Id] = <scope>) AND ([System.Links.LinkType] = 'System.LinkTypes.Hierarchy-Forward') MODE(Recursive)`.
- **`MODE(Recursive)`, never `MODE(MustContain)`** — MustContain returns only *direct* children and silently drops grandchildren (a User Story under a Feature under the Epic). Verified 2026-10-15.
- **Work-items batch caps at 200 ids** — `ado_workitems` chunks and merges; a subtree bigger than one chunk is normal.
- **The PR list is the only unbounded fetch** (`$top=1000`); a full page is ambiguous, so the report warns with a `LIMITS:` line rather than aborting.

## Status = state + tags

The board columns are a view; the script keys on `System.State` plus the tag `human-review`. Two of the six coordination statuses collide on `Resolved`:

| Coordination status | Native state | Carrier |
|---|---|---|
| Unshaped | `Feature: New` | the Feature type |
| Todo | `User Story: New` | User Story (tag `agent-work`) |
| Agent working | `User Story: Active` | User Story |
| Awaiting code review | `User Story: Resolved` | User Story, **no** `human-review` tag |
| Awaiting human action | `User Story: Resolved` | **tag `human-review`** |
| Done | `User Story: Closed` | User Story |

`agent-work` is the "Responsible = AI agent" carrier; `human-review` is "Awaiting human action"; `stakeholder` routes a card to relay delivery.

## The verbs (what `board.sh` maps them to)

| Verb | REST |
|---|---|
| `status <id> <coord>` | `PATCH …/_apis/wit/workitems/<id>` `[{op:add,path:/fields/System.State,value:<state>}]` + the tag patch below |
| `tag <id> <tag>` | `PATCH` `System.Tags`. **`add` appends**; **`replace` sets the whole set** (read current tags, re-send all). `--remove` drops one. |
| `assign <id> <human>` | `PATCH` `System.AssignedTo` to the display name (ADO resolves the identity). |
| `comment <id>` | `POST …/_apis/wit/workItems/<id>/comments` (**api-version `6.0-preview`**) `{"text":…}` → `.id` |
| `create` | `POST …/_apis/wit/workitems/$<Type>` (types `$Epic`, `$Feature`, `$User Story`) with `System.Title`, `System.Description`, `System.AreaPath`, optional `System.Tags`/`System.AssignedTo`, and a `System.LinkTypes.Hierarchy-Reverse` relation to the parent. **The board is the Epic's subtree — a card not parented into the Epic does not appear.** |
| `claim` | read comments → if a live `Claiming:`/`Processed:` (not `(superseded)`) exists, lose; else `POST` the `Claiming: <op> · <nonce>` comment, re-read, lowest comment `id` wins; the loser `PATCH`es its comment to append `(superseded)`. |
| `pr` | `POST …/_apis/git/repositories/<repo-id>/pullrequests` `{sourceRefName,targetRefName,title,description,isDraft:true}` |

**There is no `pr-ready` or `pr-merge` verb, deliberately** — only the human promotes and merges, in the UI. That makes "the agent never promotes or merges" structural, the same way `ADO_READONLY=1` makes orientation read-only.

## Tags are created implicitly

There is **no standalone create-tag call** on this server — `POST`/`PATCH`/`PUT`/`DELETE …/_apis/wit/tags` all return **405**. A tag is created by the first work item that carries it.

## Repo scoping

Repos are project-scoped; work-item links are project-scoped. The repo id is `b65b2ef6-085b-4e36-af32-ea4046a7639e` for WaveformExtractionGUI; it lives in `board.conf` (`BOARD_REPO_ID`).
