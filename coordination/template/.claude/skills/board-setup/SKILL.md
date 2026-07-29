---
name: board-setup
description: Bootstrap a new project's human+agent coordination in the current repo — ingest plan/ and explorations/, draft the implementation-plan md (human-reviewed), create and seed the GitHub Project board, and install the cross-tool conventions (AGENTS.md, process/ procedures, per-tool wrappers). Run inside the project repository. Stops and asks immediately when assumptions are unmet.
---

Follow the canonical, tool-neutral procedure in `process/board-setup.md`. If that file exists in the current repository, read and follow it. If it does not (normal when bootstrapping a brand-new project repo), fetch the canonical copy:

```
gh api repos/UABPeriopAI/Templates/contents/coordination/template/process/board-setup.md --jq .content | base64 -d
```

This file is only the Claude Code entry point.
