# Coordination process — UML diagrams

UML/design diagrams for the two canonical coordination procedures and their
associated processes, rendered as PNG via the team UMLBot API.

**Sources of truth (do not let these diagrams drift):**

- [`../template/process/board-setup.md`](../template/process/board-setup.md) — bootstrap procedure
- [`../template/process/next.md`](../template/process/next.md) — session orientation procedure
- [`../template/process/kanban-check.md`](../template/process/kanban-check.md) + [`kanban_check.sh`](../template/process/kanban_check.sh) — read-only orientation report
- [`../README.md`](../README.md) — the pattern and its rationale

## Diagram set

| Diagram | Type | Models |
|---|---|---|
| [`board-setup-use-case.png`](diagrams/board-setup-use-case.png) | Use case | Actors and use cases of the bootstrap: preconditions, plan review, board creation, seeding, conventions |
| [`board-setup-activity.png`](diagrams/board-setup-activity.png) | Activity | The step 0–6 flow, the human plan checkpoint, and the "options before items" hazard |
| [`board-setup-sequence.png`](diagrams/board-setup-sequence.png) | Sequence | Agent ↔ `gh` ↔ GitHub Projects ↔ Templates repo for board creation and seeding |
| [`next-use-case.png`](diagrams/next-use-case.png) | Use case | Orientation, gate processing, work pickup, the two human gates, and the draft-PR end state |
| [`next-activity.png`](diagrams/next-activity.png) | Activity | Steps 0–7 including the sync, cleared-gate, claim, plan, work, and hand-off passes |
| [`next-sequence.png`](diagrams/next-sequence.png) | Sequence | Operator ↔ agent ↔ `kanban_check.sh` ↔ GitHub ↔ fresh-eyes reviewer |
| [`kanban-check-use-case.png`](diagrams/kanban-check-use-case.png) | Use case | The read-only report and its read-only / non-recursive constraints |
| [`kanban-check-activity.png`](diagrams/kanban-check-activity.png) | Activity | Freshness → pull state → sync → gates → queue, with the truncation guards |
| [`claim-protocol-sequence.png`](diagrams/claim-protocol-sequence.png) | Sequence | Comment-ID arbitration for contested claims (two sessions, same operator) |

Each `.png` has its PlantUML source next to it as a `.puml` file.

## Regenerating

The rendered images are committed (reviewable artifacts), so a reviewer never has to
run a generator. To rebuild them anyway:

```bash
docs/diagrams/render.sh          # renders every .puml next to it
```

`render.sh` POSTs each source to the team UMLBot render endpoint
(`UMLBOT_RENDER_URL`, default `http://10.23.16.220/umlbot/v01/render`) and writes
the returned PNG beside the source. The render endpoint is unauthenticated; the
`/generate` endpoints (natural-language → PlantUML) require `Authorization: Bearer
<key>` and are not used here — the diagrams are authored by hand so they can be
reviewed in source form.

> Experimental MCP alternative: `origin/feature/mcp` of
> `UABGH-Emerging-Technologies/UMLBot` exposes `render_plantuml` and
> `generate_diagram` tools over MCP (`UMLBot/mcp_server.py`). The HTTP render
> endpoint above is equivalent for the light path and needs no MCP client.
