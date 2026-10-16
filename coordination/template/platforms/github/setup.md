# GitHub setup — create the board container (adapter reference)

The GitHub-specific board-creation steps. `process/board-setup.md` calls this at its install step, **once per project**.

1. **Create the project** — `gh project create --owner <owner> --title "<board title>" --format json` → capture number, id **and `url`** (org boards are `/orgs/<owner>/projects/<n>`, user-owned `/users/<owner>/projects/<n>` — use the returned URL).
2. **Capture the Status field id** — `gh project field-list <number> --owner <owner> --format json`.
3. **Set the Status options first, before adding items** — via `updateProjectV2Field` (single call): Unshaped · Todo · Agent working · Awaiting code review · Awaiting human action · Done. **Editing options later regenerates all option ids and clears every item's Status.**
4. **Create the Responsible single-select field**: `AI agent`, one option per developer, one per stakeholder (`(stakeholder)`), `Copilot (AI reviewer)`.
5. **Create repo labels**: `human-review`, `agent-work`, `stakeholder`.
6. **Record** project number/id/url, owner, and every field/option id into `board.conf`.
