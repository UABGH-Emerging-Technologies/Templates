---
name: board-setup
description: Bootstrap a new project's human+agent coordination in the current repo — ingest plan/ and explorations/, draft the implementation-plan md (human-reviewed), create and seed the project board (GitHub Project or ADO Epic), and install the cross-tool conventions (AGENTS.md, process/ procedures, per-tool wrappers). Run inside the project repository. Stops and asks immediately when assumptions are unmet.
---

Follow the canonical, tool-neutral procedure in `process/board-setup.md`. If that file exists in the current repository, read and follow it. If it does not (normal when bootstrapping a brand-new project repo), copy it — with the whole `coordination/template/` tree, **including `platforms/`** — from the coordination template in `UABGH-Emerging-Technologies/Templates` (`coordination/template/process/board-setup.md` plus `coordination/template/platforms/`). **If that template does not yet ship `platforms/`, it is the pre-platform version and cannot bootstrap an ADO repo: stop and say so, rather than producing GitHub-only files.** This file is only the Claude Code entry point.
