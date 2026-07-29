# board-setup — instantiate the human+agent coordination pattern (tool-neutral procedure)

This is the canonical procedure; per-tool entry points are thin wrappers pointing here. It runs in any coding agent that can run `gh` and `git`, inside the new project's repository. It sets up coordination for **mixed-tool teams** (Claude Code, OpenCode, Codex, …) — tooling is per developer, so every artifact below is emitted unconditionally.

The pattern was developed on `UABGH-Emerging-Technologies/lead-infinitely` and its canonical home is the `coordination/` template in `UABPeriopAI/Templates` (`PROCESS.md` is the rationale; read it if in doubt). The premise: the board holds coordination state, md files hold knowledge; cards are attention-transfer events; every column answers "who acts next."

**Canonical assets live in the templates repo** — fetch them, don't reinvent:
`gh api repos/UABPeriopAI/Templates/contents/coordination/template/<path> --jq .content | base64 -d` for `PROCESS.md.jinja` (render its `{{ project_name }}`-style variables as you adapt it), `process/next.md` (fill its `<BOARD_NUMBER>`-style tokens in step 5), and this file (`process/board-setup.md`). If the repo was stamped with the `coordination` Copier template, these files already exist locally — fill the tokens instead of fetching.

## 0. Preconditions — verify ALL before doing anything; on any failure, ask the human immediately

Check, in order:

1. **Repo**: `gh repo view --json owner,name,isPrivate` succeeds (we're in a git repo with a GitHub remote). Capture owner/name; note whether owner is an org or a user (affects `--owner` below).
2. **Inputs**: `plan/` exists and is non-empty. `explorations/` exists (empty or absent is tolerable — confirm with the human that there are genuinely no spikes).
3. **Token**: `gh auth status` shows the `project` scope (fix: `gh auth refresh -s project`, which the human must do interactively).
4. **No duplicate board**: `gh project list --owner <owner> --format json` — if a project title matches this repo/project, ask: reuse it or create a new one?
5. **Existing conventions**: does the repo already have AGENTS.md / CLAUDE.md / IMPLEMENTATION-PLAN.md / branch protections (`gh api repos/<o>/<r>/rulesets` or protected main)? Never overwrite existing docs without asking.

Then ask the human up front, in one batch (plus anything the checks surfaced):
- **Board title** (default: the repo/project name).
- **Stakeholders without GitHub accounts** (names → Responsible options; their cards get the `stakeholder` label and relay delivery).
- **Other developers** (GitHub logins → lanes). Do NOT ask which coding tools they use — tooling is per developer and all entry points are emitted regardless.
- **Commit flow**: PR flow with review, or direct commits (if the repo has no protections yet, ask which to use; recommend PR flow).

Do not proceed past a failed assumption on your own judgment — the human said what they meant by `plan/` and `explorations/`; if the shape on disk doesn't match, that's their call, not yours.

## 1. Ingest plan/ and explorations/

- Inventory both trees recursively. Read natively: md, txt, transcripts, PDFs, and **images (whiteboard photos, UML) — read them visually**. Convert docx/pptx via `pandoc` (or macOS `textutil`) when available; if files remain unreadable, list them and ask the human for exports **before** drafting — a plan built on half the inputs looks complete and isn't.
- Large corpus and your tool supports parallel subagents → fan out per file cluster, you keep the synthesis; otherwise process clusters sequentially.
- Collect: goals; constraints/invariants (especially owner-decided things that must not be re-litigated); milestones/modules with dependencies and *what resource unblocks what*; open questions; from `explorations/`: what each spike proved or disproved, and what it de-risks.

## 2. Draft the plan docs — then STOP for human review

Write drafts (do not seed anything yet):

- **IMPLEMENTATION-PLAN.md** — the source of truth for module/milestone status, dependencies, and gates. Include: a decisions section (owner-decided, with provenance to the `plan/` file each came from), an open-questions section, and per-item gates ("needs X before actionable"). Spike outcomes from `explorations/` annotate the items they de-risk.
- **HUMAN-REVIEW-QUEUE.md** — skeleton, pre-populated with any human gates the plan already implies (sign-offs, legal reads, approvals).
- **PROCESS.md** — fetch the canonical (`coordination/template/PROCESS.md.jinja`) and render/adapt names/links (project title, repo, board URL).

**Checkpoint: present the drafts and wait.** The human reviews/edits IMPLEMENTATION-PLAN.md before anything fans out from it — the board seed, the Unshaped column, and every future orientation run inherit its errors. Resume only on their confirmation.

## 3. Create the board — order matters (hard-won hazards)

1. `gh project create --owner <owner> --title "<board title>" --format json` → capture project number + ID.
2. `gh project field-list <number> --owner <owner> --format json` → capture the Status field's ID (needed for the mutation below).
3. **Immediately, BEFORE adding any items**, replace the Status options via the `updateProjectV2Field` GraphQL mutation (single call): Unshaped (PURPLE, "Believed-future work — cheap one-liners, not yet shaped") · Todo (GRAY, "Shaped and ready to be picked up") · Agent working (BLUE) · Awaiting code review (YELLOW, "A PR/diff exists and awaits review") · Awaiting human action (ORANGE, "Decision, sign-off, or real-world action — no diff") · Done (GREEN). **Editing options later regenerates ALL option IDs and silently clears every item's Status** — that's why options come first and why any later edit requires snapshot + re-apply + re-wiring the built-in workflows.
4. Create the **Responsible** single-select field: `AI agent` (tool-neutral — never a specific product name), one option per developer, one per stakeholder (suffix "(stakeholder)"), `Copilot (AI reviewer)`.
5. Create repo labels: `human-review`, `agent-work`, `stakeholder`.
6. Record project number/ID and every field/option ID — they go in AGENTS.md in step 5.

## 4. Seed the board from the confirmed plan

- **Unshaped**: one *draft item* (`gh project item-create <n> --owner <o> --title … --body …` — NOT an issue) per plan module/milestone/deferred feature/governance/ops item. Body = one line: source + gate + "(Unshaped: shape into a self-contained issue before pickup.)".
- **Todo**: items the plan marks shaped-and-actionable now → real issues with self-contained bodies, `agent-work` or `human-review` label, assignee (every card gets one — wrong human beats no one), Responsible.
- **Awaiting human action**: human gates whose materials already exist (from HUMAN-REVIEW-QUEUE.md), `human-review` (+ `stakeholder`) label.
- **Done** (optional — ask): completed spikes from `explorations/` as closed issues, so the board opens with honest history rather than an empty Done column.
- Verify counts with `gh project item-list <n> --owner <o> --limit 100 --format json` (never omit `--limit`; the default 30 silently truncates).

## 5. Install the conventions — emit ALL of these, unconditionally (tooling is per developer)

- **AGENTS.md** (the cross-tool conventions file Codex/OpenCode/others read natively): create or append the "Project board" section — copy the canonical wording (columns incl. Unshaped semantics and no-Blocked rationale; self-contained card bodies; assignee + Responsible + multi-dev lane rule with action-type scoping; signals-vs-payload; session pickup via the next procedure; plumbing recipe) with THIS board's number/owner/IDs substituted. Include the per-tool entry-points note.
- **CLAUDE.md containing the single line `@AGENTS.md`** (Claude Code import — safer than a symlink on Windows/WSL setups). If a CLAUDE.md already exists with content, merge instead (ask first).
- **`process/next.md`**: fetch the canonical and fill its `<BOARD_NUMBER>`/`<BOARD_OWNER>` tokens (step-0 commands). Everything else is generic.
- **`process/board-setup.md`**: copy this file in, so the repo carries its own bootstrap procedure.
- **Entry-point wrappers, all of them**:
  - `.claude/skills/next/SKILL.md` (Claude Code): frontmatter + "Read `process/next.md` and follow it exactly; pass arguments through as the work-selection filter."
  - `.opencode/command/next.md` (OpenCode): its command frontmatter + the same one-line body with `$ARGUMENTS`.
  - `.codex/skills/next/SKILL.md` (Codex): repo-level skill discovery verified on Codex 0.145.0; same thin pointer. The AGENTS.md entry-points note remains the fallback for tools without discovery; Codex devs wanting the literal `/next` slash also copy the body to `~/.codex/prompts/next.md`.
- Commit per the flow chosen in step 0 (PR + review, or direct). Use a temporary worktree if other sessions may share the working tree.

## 6. Hand the human their checklist (the API cannot do these)

- Board UI → default view: **Board layout grouped by Status** (nice second view: group by Responsible).
- Board **⋯ → Workflows**: *Item closed* → Status Done; *Pull request merged* → Status Done; *Auto-close issue* when Status = Done. Leave *Item added* OFF (statuses are set deliberately per card type).
- **Manage access**: share the project with the team.
- Each developer, regardless of tool: `gh auth refresh -s project` once. Codex users: sandbox/approval settings must permit `gh` and `git`; optionally install `~/.codex/prompts/next.md`.

## Output shape

End with: docs written (paths), board URL, per-column seed counts, the human checklist above, and the suggestion to run the next procedure for the first work pickup.
