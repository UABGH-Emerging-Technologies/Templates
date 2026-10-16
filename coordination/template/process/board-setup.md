# board-setup — instantiate the human+agent coordination pattern (tool-neutral procedure)

This is the canonical procedure; per-tool entry points are thin wrappers pointing here. It runs in any coding agent that can run `git` and the platform's transport, inside the new project's repository. It sets up coordination for **mixed-tool teams** (Claude Code, OpenCode, Codex, …) — tooling is per developer, so every artifact below is emitted unconditionally.

**Two platforms, one procedure.** The pattern runs on **GitHub** (a Project board + `gh`) and **Azure DevOps Server** (an Epic subtree + REST). This procedure is the same for both: it **detects the platform once** from the repo's origin, installs the matching `platforms/<p>/` bundle into `process/`, and writes `board.conf`. The platform is chosen **here, once** — never at run time. The rationale is `PROCESS.md`; the pattern's origin is the `coordination/` template in `UABGH-Emerging-Technologies/Templates`.

The premise is unchanged: the board holds coordination state, md files hold knowledge; cards are attention-transfer events; every status answers "who acts next."

## 0. Preconditions — verify ALL before doing anything; on any failure, ask the human immediately

Check, in order:

1. **Repo + remote**: we are in a git repo with a remote. Capture `git remote get-url origin` — its host decides the platform in step 3.
2. **Inputs**: `plan/` exists and is non-empty. `explorations/` exists (empty or absent is tolerable — confirm with the human that there are genuinely no spikes).
3. **Credentials** (per platform):
   - **GitHub**: `gh auth status` shows the `project` scope (fix: `gh auth refresh -s project`, which the human must do interactively).
   - **ADO**: `ADO_PAT` is set and reaches the collection (`GET {base}/_apis/connectionData` → 200), with scopes `vso.work_write`, `vso.code_write`, `vso.project`.
4. **Board surface**:
   - **GitHub**: no duplicate project — `gh project list --owner <owner>`; if a project matches, ask: reuse or create new?
   - **ADO**: a **team + area path** for the coordination board, **and no existing coordination Epic in it**. **Creating a team or area path is a Project Collection Administrator act the API may not grant** — if the team/area is missing, stop and hand it to the human. For the Epic, query the area's Epics (`SELECT [System.Id] FROM WorkItems WHERE [System.WorkItemType] = 'Epic' AND [System.AreaPath] UNDER '<area path>'`); **if one matches, ask: reuse it or create a new one?** A second coordination Epic in the same area is a duplicate board — the same trap the GitHub check exists to catch.
5. **Existing conventions**: does the repo already have AGENTS.md / CLAUDE.md / IMPLEMENTATION-PLAN.md / branch protections? Never overwrite existing docs without asking.

Then ask the human up front, in one batch (plus anything the checks surfaced):
- **Board title** (default: the repo/project name).
- **Stakeholders without accounts** (names → the `stakeholder` tag; their cards are delivered by relay).
- **Other developers** (logins / display names → lanes). Do NOT ask which coding tools they use — tooling is per developer and all entry points are emitted regardless.
- **Commit flow**: PR flow with review, or direct commits (recommend PR flow).

Do not proceed past a failed assumption on your own judgment — the human said what they meant by `plan/` and `explorations/`; if the shape on disk doesn't match, that's their call, not yours.

## 1. Ingest plan/ and explorations/

- Inventory both trees recursively. Read natively: md, txt, transcripts, PDFs, and **images (whiteboard photos, UML) — read them visually**. Convert docx/pptx via `pandoc` (or macOS `textutil`) when available; if files remain unreadable, list them and ask the human for exports **before** drafting — a plan built on half the inputs looks complete and isn't.
- Large corpus and your tool supports parallel subagents → fan out per file cluster, you keep the synthesis; otherwise process clusters sequentially.
- Collect: goals; constraints/invariants (especially owner-decided things that must not be re-litigated); milestones/modules with dependencies and *what resource unblocks what*; open questions; from `explorations/`: what each spike proved or disproved, and what it de-risks.

## 2. Draft the plan docs — then STOP for human review

Write drafts (do not seed anything yet):

- **IMPLEMENTATION-PLAN.md** — the source of truth for module/milestone status, dependencies, and gates. Include: a decisions section (owner-decided, with provenance to the `plan/` file each came from), an open-questions section, and per-item gates ("needs X before actionable"). Spike outcomes from `explorations/` annotate the items they de-risk.
- **HUMAN-REVIEW-QUEUE.md** — skeleton, pre-populated with any human gates the plan already implies (sign-offs, legal reads, approvals).
- **PROCESS.md** — adapt this repo's `PROCESS.md` (project title, repo, board link).

**Checkpoint: present the drafts and wait.** The human reviews/edits IMPLEMENTATION-PLAN.md before anything fans out from it — the board seed, the Unshaped items, and every future orientation run inherit its errors. Resume only on their confirmation.

## 3. Detect the platform (the once-made choice)

`git remote get-url origin` — `github.com` → `github`; the ADO collection host → `ado`. The platform is chosen **here, once**; it is never re-decided at run time. Nothing is installed or removed yet — the `platforms/` tree stays intact until step 5, because step 4 reads from it.

## 4. Create the board container — dispatch to `platforms/<p>/setup.md`

Read `platforms/<p>/setup.md` and follow it. It creates the board container and its statuses:

- **GitHub**: a Project, its Status + Responsible fields/options, and the repo labels.
- **ADO**: the container **Epic**, the backlog column renames, and the tags (created implicitly).

**Capture the ids it yields** — the Epic id (ADO) or project/field/option ids (GitHub). They go in `board.conf` (step 5) and AGENTS.md (step 7).

## 5. Install the bundle and record the choice

Now that the board ids exist:

1. **Install** the chosen variant into its final place: copy `platforms/<p>/next.md` → `process/next.md`, `…/kanban-check.md` → `process/kanban-check.md`, `…/kanban_check.sh` → `process/kanban_check.sh`, `…/board.sh` → `process/board.sh`, and the transport (`platforms/ado/ado_api.sh` → `process/ado_api.sh`).
2. **Write `board.conf`** at the repo root — `BOARD_PLATFORM=<p>` plus the ids from step 4 and the repo id — and **commit it**. This is the record of the once-made choice, not a runtime switch.
3. **Remove** the unchosen variant and the `platforms/` staging tree.
4. `chmod +x process/board.sh process/kanban_check.sh`.

## 6. Seed the board from the confirmed plan

- **Unshaped**: one item per plan module/milestone/deferred feature/governance/ops item — a GitHub **draft item**, an ADO **Feature** under the Epic. Body = one line: source + gate + "(Unshaped: shape into a self-contained card before pickup.)".
- **Todo**: items the plan marks shaped-and-actionable now → cards with self-contained bodies, the `agent-work` (AI-agent work) or `human-review` (a human gate) tag, an assignee (every card gets one — wrong human beats no one), status Todo.
- **Awaiting human action**: human gates whose materials already exist (from HUMAN-REVIEW-QUEUE.md), tagged `human-review`.
- **Done** (optional — ask): completed spikes from `explorations/` as closed cards, so the board opens with honest history.
- Verify with the orientation read (`process/board.sh orient --scope <id>` on ADO) and confirm the counts/states are what you seeded. Check for orphaned coordination items — on ADO an item not parented into the Epic does not appear on the board.

## 7. Install the conventions — emit ALL of these, unconditionally (tooling is per developer)

- **AGENTS.md** (the cross-tool conventions file Codex/OpenCode/others read natively): create or append the "Project board" section — the platform-neutral conventions (the board model, statuses incl. Unshaped semantics and no-Blocked rationale; self-contained card bodies; assignee + tag-based Responsible + multi-dev lane rule with action-type scoping; signals-vs-payload; session pickup via the next procedure) plus this platform's board block, with THIS board's team/area/Epic/repo id (ADO) or number/owner/field/option ids (GitHub) substituted. The platform's `MECHANICS.md` is the plumbing recipe the block summarizes.
- **CLAUDE.md containing the single line `@AGENTS.md`** (Claude Code import — safer than a symlink on Windows/WSL). If a CLAUDE.md already exists with content, merge instead (ask first).
- **`process/next.md`, `process/kanban-check.md`, `process/kanban_check.sh`, `process/board.sh`, and the transport** — **not optional**, and installed by step 5. `next`'s orientation passes *are* this bundle, so a repo that ships `next.md` without them ships a procedure with no orientation.
- **`process/board-setup.md`** (this file): copy it in, so the new repo can bootstrap others.
- **Entry-point wrappers — two per tool, emit all six.** Each `next` wrapper points at `process/next.md` and says the deliverable is the work its step-4 selection produces — a **draft** PR or a recorded blocker, and that only the human promotes the draft to ready-for-review. Each `kanban-check` wrapper runs `process/kanban_check.sh` as the normal path and names `process/kanban-check.md` as its specification and by-hand fallback, strictly read-only either way. The non-recursion rule lives in that procedure's own Absolute rules.
  - `.claude/skills/{next,kanban-check}/SKILL.md` (Claude Code): frontmatter + "Read `process/<file>` and follow it exactly"; the next wrapper passes arguments through as the work-selection filter.
  - `.opencode/command/{next,kanban-check}.md` (OpenCode): command frontmatter + the same bodies, with `$ARGUMENTS` on next. Orientation is a script every tool runs directly, so no wrapper needs a delegation clause; if you reintroduce model-delegated orientation, the opencode `next` wrapper needs a line telling it to run the passes in-process and never spawn another `opencode run`.
  - `.codex/skills/{next,kanban-check}/SKILL.md` (Codex): same thin pointers, plus any sandbox note the developer's setup needs (a managed Codex sandbox typically cannot write `.git/FETCH_HEAD` or reach the platform API/host, so tell it to escalate on the first attempt).
- Commit per the flow chosen in step 0. Use a temporary worktree if other sessions may share the working tree.

## 8. Hand the human their checklist (the API cannot do these)

- **GitHub**: board UI → default view grouped by Status (and by Responsible); ⋯ → Workflows (Item closed → Done; PR merged → Done; Auto-close when Done); share the project with the team; each developer runs `gh auth refresh -s project`.
- **ADO**: team + area path exist (Collection Admin); confirm the backlog columns; each developer mints a PAT with `vso.work_write`/`vso.code_write`/`vso.project` and exports `ADO_PAT`; **IIS Basic Authentication disabled**; the optional `Responsible` picklist field needs a Collection Admin (tags carry it until then).
- Codex users: sandbox/approval settings must permit the platform transport and `git`.

## Output shape

End with: docs written (paths), the board link (GitHub project URL / ADO Epic URL), per-status seed counts, the human checklist above, and the suggestion to run the next procedure for the first work pickup.
