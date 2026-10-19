# ADO setup — create the board container (adapter reference)

The ADO-specific board-creation steps. `process/board-setup.md` calls this at its install step, **once per project**. The statuses are the native Agile states; the two collisions are carried by tags. There are no Projects-v2 fields to create.

1. **Confirm the team + area path.** Everything below is scoped to them. On this server the existing coordination surface is the **Signal Intelligence** team, area `Data Science\Signal Intelligence`; a new project creates its own. **Creating a team or an area path is a Project Collection Administrator act the API may not grant** — if it is missing, stop and hand it to the human.

2. **Create the container Epic** — `POST {base}/{project}/_apis/wit/workitems/$Epic?api-version=6.0` with `[{"op":"add","path":"/fields/System.Title","value":"<board title>"},{"op":"add","path":"/fields/System.AreaPath","value":"<area path>"}]`. Capture its id — that id is **`BOARD_SCOPE`**, the argument every later `board.sh orient`/`next` run takes.

3. **Rename the team's backlog columns** to carry the coordination statuses (the board is a view; the script reads `System.State`). Epics board → Planning / Open / Closed; Features board → Unshaped / Active / Resolved / Closed; Stories board → Todo / Agent working / Awaiting code review / Awaiting human action / Done. Fastest in the board UI, or `PATCH {base}/{project}/{team}/_apis/work/boards/<board-id>?api-version=6.0` with the `columns` array.

4. **Note the two-to-one column/state mapping.** "Awaiting code review" and "Awaiting human action" both map to `User Story: Resolved` — a **split column**, native to ADO. The tag `human-review` is what distinguishes them for the script; the split column is a visual convenience only. **No custom state is needed, and none is possible without a Collection Admin.**

5. **Create the tags** `agent-work`, `human-review`, `stakeholder` — **implicitly, by tagging a work item.** This server's tag route is read-only (`POST/PATCH/PUT/DELETE …/_apis/wit/tags` → 405); there is no standalone create call.

6. **Record the ids** — project, team, area path, Epic id (`BOARD_SCOPE`), repo id (`BOARD_REPO_ID`) — into `board.conf` at the repo root.
