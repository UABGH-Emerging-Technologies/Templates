#!/usr/bin/env python3
"""Read-only, repository-aware orientation for a labelled master-board initiative.

This is an opt-in companion to kanban_check.sh. It never edits a checkout or a
remote resource. A failed source is represented in the report, never as an empty
successful result.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ISSUE_URL = re.compile(r"^https://github\.com/([^/]+/[^/]+)/(issues|pull)/(\d+)(?:$|[/?#])")
MARKER = re.compile(r"^(?:Processed|Claiming|Claim|Agent):")
STALE_HOURS = 24
IDLE_DAYS = 7


@dataclass
class Source:
    value: Any
    error: str | None = None

    @property
    def complete(self) -> bool:
        return self.error is None


def command(*args: str, cwd: Path | None = None) -> Source:
    """Run a read verb and retain failures as evidence for the report."""
    try:
        result = subprocess.run(
            args, cwd=cwd, text=True, capture_output=True, check=False, timeout=120
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Source(None, str(exc))
    if result.returncode:
        return Source(None, (result.stderr or result.stdout).strip() or f"exit {result.returncode}")
    return Source(result.stdout)


def json_command(*args: str, cwd: Path | None = None) -> Source:
    """Parse a command's JSON without treating malformed output as an empty list."""
    result = command(*args, cwd=cwd)
    if not result.complete:
        return result
    try:
        return Source(json.loads(result.value))
    except json.JSONDecodeError as exc:
        return Source(None, f"invalid JSON: {exc}")


def rest_pages(endpoint: str) -> Source:
    """Read every REST page; gh exits nonzero if a later page fails."""
    result = json_command("gh", "api", "--paginate", "--slurp", endpoint)
    if not result.complete:
        return result
    if not isinstance(result.value, list) or any(not isinstance(p, list) for p in result.value):
        return Source(None, "unexpected paginated response")
    return Source([item for page in result.value for item in page])


def board_items(owner: str, number: int) -> Source:
    """Read the filtered board with a verified total and one bounded retry."""
    for limit in (200, 400):
        result = json_command(
            "gh", "project", "item-list", str(number), "--owner", owner,
            "--query", "-status:Done", "--limit", str(limit), "--format", "json",
        )
        if not result.complete:
            return result
        data = result.value
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            return Source(None, "board response lacks items")
        if not isinstance(data.get("totalCount"), int):
            return Source(None, "board response lacks totalCount")
        if len(data["items"]) == data["totalCount"]:
            return Source(data["items"])
    return Source(None, f"board truncated: {len(data['items'])} of {data['totalCount']}")


def issue_key(url: str | None) -> tuple[str, int, str] | None:
    """Parse a canonical GitHub issue or PR URL into a qualified identity."""
    match = ISSUE_URL.match(url or "")
    if not match:
        return None
    return match.group(1), int(match.group(3)), match.group(2)


def iso_age(value: str | None, hours: bool = True) -> float | None:
    """Return elapsed hours or days for a GitHub timestamp."""
    if not value:
        return None
    try:
        then = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    delta = (datetime.now(timezone.utc) - then).total_seconds()
    return delta / (3600 if hours else 86400)


def load_manifest(path: Path) -> dict[str, Any]:
    """Validate the small, opt-in v1 contract before any source is queried."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be an object")
    if data.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    if (
        not isinstance(data.get("project_owner"), str)
        or not data["project_owner"]
        or type(data.get("project_number")) is not int
    ):
        raise ValueError("manifest requires project_owner and project_number")
    if not isinstance(data.get("initiative_label"), str) or not data["initiative_label"]:
        raise ValueError("manifest requires initiative_label")
    repos = data.get("repositories")
    if not isinstance(repos, list) or len(repos) < 2:
        raise ValueError("multi-repository manifest requires at least two repositories")
    slugs = set()
    for repo in repos:
        if not isinstance(repo, dict):
            raise ValueError("every repository entry must be an object")
        slug = repo.get("slug")
        if not isinstance(slug, str) or not re.fullmatch(r"[\w.-]+/[\w.-]+", slug):
            raise ValueError(f"invalid repository slug: {slug!r}")
        if slug.lower() in slugs:
            raise ValueError(f"duplicate repository slug: {slug}")
        slugs.add(slug.lower())
        if (
            not isinstance(repo.get("integration_branch"), str)
            or not repo["integration_branch"]
            or not isinstance(repo.get("local_path"), str)
            or not repo["local_path"]
            or Path(repo["local_path"]).is_absolute()
        ):
            raise ValueError(f"{slug} requires integration_branch and relative local_path")
    review_repo = data.get("review_queue_repository")
    if review_repo is not None and review_repo not in {r["slug"] for r in repos}:
        raise ValueError("review_queue_repository must name a listed repository")
    return data


def freshness(repo: dict[str, Any], base: Path, no_fetch: bool) -> Source:
    """Inspect the owning checkout and its configured integration branch."""
    path = (base / repo["local_path"]).resolve()
    if not path.is_dir():
        return Source(None, f"checkout unavailable: {path}")
    branch = repo["integration_branch"]
    if not no_fetch:
        fetched = command("git", "fetch", "origin", branch, "-q", cwd=path)
        if not fetched.complete:
            return fetched
    status = command("git", "status", "--short", "--branch", cwd=path)
    if not status.complete:
        return status
    worktrees = command("git", "worktree", "list", cwd=path)
    branches = command("git", "branch", "--format=%(refname:short)", cwd=path)
    if not worktrees.complete or not branches.complete:
        return Source(None, "local worktree or branch list unavailable")
    head = command("git", "rev-parse", "HEAD", cwd=path)
    remote = command("git", "rev-parse", f"refs/remotes/origin/{branch}", cwd=path)
    if not head.complete or not remote.complete:
        return Source(None, f"integration ref unavailable: origin/{branch}")
    lines = status.value.splitlines()
    return Source({
        "path": str(path), "branch": branch, "status": lines[0] if lines else "unknown",
        "dirty": max(0, len(lines) - 1), "head": head.value.strip(),
        "integration": remote.value.strip(),
        "worktrees": [line for line in worktrees.value.splitlines() if line],
        "branches": [line for line in branches.value.splitlines() if line],
    })


def labels(issue: dict[str, Any]) -> set[str]:
    """Extract REST issue label names."""
    return {x["name"] for x in issue.get("labels", []) if isinstance(x, dict) and "name" in x}


def first_ask(body: str | None) -> str:
    """Extract the issue's first nonempty line for the human queue."""
    line = next((x.strip() for x in (body or "").splitlines() if x.strip()), "")
    line = re.sub(r"^#+\s+|\*\*", "", line)
    return line[:159] + "…" if len(line) > 160 else line


def pr_links(pr: dict[str, Any], slug: str, known: set[tuple[str, int]]) -> set[tuple[str, int]]:
    """Resolve qualified and same-repository closing references and branch names."""
    body = pr.get("body") or ""
    links: set[tuple[str, int]] = set()
    for match in re.finditer(r"(?i)\b(?:closes|fixes|resolves)\s+([\w.-]+/[\w.-]+)?#(\d+)", body):
        links.add((match.group(1) or slug, int(match.group(2))))
    branch = (pr.get("head") or {}).get("ref", "")
    match = re.match(r"issue-(\d+)(?:$|[^0-9])", branch)
    if match:
        links.add((slug, int(match.group(1))))
    canonical = {s.lower(): s for s, _ in known}
    return {(canonical.get(s.lower(), s), n) for s, n in links} & known


def closing_references(slug: str, number: int) -> Source:
    """Read the complete linked-development connection for an open PR."""
    owner, name = slug.split("/", 1)
    query = (
        "query($owner:String!,$name:String!,$number:Int!,$cursor:String){"
        "repository(owner:$owner,name:$name){pullRequest(number:$number){"
        "closingIssuesReferences(first:100,after:$cursor){"
        "nodes{number repository{nameWithOwner}} "
        "pageInfo{hasNextPage endCursor}}}}}"
    )
    cursor: str | None = None
    found: set[tuple[str, int]] = set()
    while True:
        args = ["gh", "api", "graphql", "-f", f"query={query}",
                "-F", f"owner={owner}", "-F", f"name={name}",
                "-F", f"number={number}"]
        if cursor:
            args.extend(("-f", f"cursor={cursor}"))
        result = json_command(*args)
        if not result.complete:
            return result
        if not isinstance(result.value, dict):
            return Source(None, "invalid linked-development response")
        if result.value.get("errors"):
            return Source(None, f"GraphQL errors: {result.value['errors']}")
        try:
            connection = result.value["data"]["repository"]["pullRequest"][
                "closingIssuesReferences"
            ]
            for node in connection["nodes"]:
                found.add((node["repository"]["nameWithOwner"], node["number"]))
            page = connection["pageInfo"]
            if not page["hasNextPage"]:
                return Source(found)
            cursor = page["endCursor"]
            if not cursor:
                return Source(None, "linked-development page has no cursor")
        except (KeyError, TypeError, AttributeError) as exc:
            return Source(None, f"invalid linked-development response: {exc}")


def qualified(slug: str, number: int) -> str:
    """Format the only issue identity accepted by the multi-repo report."""
    return f"{slug}#{number}"


def hrq_items(markdown: str) -> list[tuple[int, str, bool, str]]:
    """Parse numbered human-review entries and their checked state."""
    items = []
    current: tuple[int, str] | None = None
    body: list[str] = []
    for line in markdown.splitlines() + ["## end"]:
        match = re.match(r"^##\s+(\d+)\.\s+(.+)", line)
        if match or line == "## end":
            if current:
                text = "\n".join(body)
                items.append((current[0], current[1], "- [ ]" in text, text))
            current = (int(match.group(1)), match.group(2)) if match else None
            body = []
        elif current:
            body.append(line)
    return items


def render(manifest: dict[str, Any], base: Path, operator: str | None, no_fetch: bool,
           comments_full: bool) -> tuple[str, bool]:
    """Collect scoped evidence, then render an explicitly completeness-aware report."""
    sources: list[str] = []
    failed = False

    def record(name: str, result: Source) -> Any:
        nonlocal failed
        if result.complete:
            sources.append(f"  {name}: complete")
            return result.value
        failed = True
        sources.append(f"  {name}: INCOMPLETE — {result.error}")
        return None

    if operator is None:
        login = record("operator", command("gh", "api", "user", "--jq", ".login"))
        operator = (login.strip() or None) if isinstance(login, str) else None
        if operator is None and login is not None:
            failed = True
            sources.append("  operator: INCOMPLETE — empty login")
    board = record(
        "master board", board_items(manifest["project_owner"], manifest["project_number"])
    )
    repos = {r["slug"]: r for r in manifest["repositories"]}
    canonical_slugs = {slug.lower(): slug for slug in repos}
    scoped_cards: dict[tuple[str, int, str], dict[str, Any]] = {}
    if board is not None:
        for card in board:
            content = card.get("content") or {}
            key = issue_key(content.get("url"))
            if key and key[0].lower() in canonical_slugs:
                scoped_cards[(canonical_slugs[key[0].lower()], key[1], key[2])] = card
            elif key:
                # A shared project can include unrelated repository cards.
                continue
            elif content.get("number") is not None:
                failed = True
                sources.append(
                    f"  board item {card.get('id', 'unknown')}: INCOMPLETE — "
                    "numbered content has no qualified GitHub URL"
                )
    steps = []
    issues: dict[tuple[str, int], dict[str, Any]] = {}
    prs: dict[tuple[str, int], dict[str, Any]] = {}
    pr_references: dict[tuple[str, int], set[tuple[str, int]]] = {}
    pr_complete: dict[str, bool] = {}
    references_complete: dict[str, bool] = {}
    remote_branches: dict[str, set[str]] = {}
    review_queue: list[tuple[int, str, bool, str]] | None = None
    review_repo = manifest.get("review_queue_repository") or manifest["repositories"][0]["slug"]
    scoped_issue_keys: set[tuple[str, int]] = set()
    for slug, repo in repos.items():
        state = record(f"{slug} checkout", freshness(repo, base, no_fetch))
        if state:
            extra = [b for b in state["branches"] if b != state["branch"]]
            steps.append(
                f"  {slug} origin/{state['branch']}={state['integration'][:12]} "
                f"HEAD={state['head'][:12]} dirty={state['dirty']} "
                f"worktrees={len(state['worktrees'])} {state['status']}"
            )
            if extra:
                steps.append(f"    local branches beyond {state['branch']}: {', '.join(extra)}")
            for worktree in state["worktrees"][1:]:
                steps.append(f"    extra worktree: {worktree}")
        else:
            steps.append(f"  {slug} checkout: unavailable")
        if state:
            branch_result = record(
                f"{slug} remote branches",
                command("git", "ls-remote", "--heads", "origin", cwd=Path(state["path"])),
            )
            if branch_result is not None:
                remote_branches[slug] = {
                    line.split("refs/heads/", 1)[1]
                    for line in branch_result.splitlines() if "refs/heads/" in line
                }
            if slug == review_repo:
                markdown = record(
                    "human review queue",
                    command(
                        "git", "show",
                        f"origin/{repo['integration_branch']}:HUMAN-REVIEW-QUEUE.md",
                        cwd=Path(state["path"]),
                    ),
                )
                if markdown is not None:
                    review_queue = hrq_items(markdown)
        elif slug == review_repo:
            failed = True
            sources.append("  human review queue: INCOMPLETE — checkout unavailable")
        endpoint = f"repos/{slug}/issues?state=all&per_page=100"
        fetched_issues = record(f"{slug} issues", rest_pages(endpoint))
        if fetched_issues is not None:
            for issue in fetched_issues:
                if "pull_request" in issue:
                    continue
                key = (slug, issue["number"])
                issues[key] = issue
                if (
                    manifest["initiative_label"] in labels(issue)
                    or (slug, issue["number"], "issues") in scoped_cards
                ):
                    scoped_issue_keys.add(key)
        fetched_prs = record(
            f"{slug} PRs", rest_pages(f"repos/{slug}/pulls?state=all&per_page=100")
        )
        pr_complete[slug] = fetched_prs is not None
        references_complete[slug] = fetched_prs is not None
        if fetched_prs is not None:
            for pr in fetched_prs:
                prs[(slug, pr["number"])] = pr
                if pr.get("state") == "open":
                    linked = record(
                        f"{qualified(slug, pr['number'])} linked issues",
                        closing_references(slug, pr["number"]),
                    )
                    if linked is not None:
                        pr_references[(slug, pr["number"])] = {
                            (canonical_slugs.get(ref_slug.lower(), ref_slug), ref_number)
                            for ref_slug, ref_number in linked
                        }
                    else:
                        references_complete[slug] = False
    comments: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for slug, number in sorted(scoped_issue_keys):
        result = rest_pages(f"repos/{slug}/issues/{number}/comments?per_page=100")
        fetched = record(f"{qualified(slug, number)} comments", result)
        if fetched is not None:
            comments[(slug, number)] = fetched

    sync: list[str] = []
    gates: list[str] = []
    queue: list[str] = []
    candidates: list[tuple[str, int, str]] = []
    for (slug, number, kind), card in scoped_cards.items():
        identity = qualified(slug, number)
        status = card.get("status", "unknown")
        if kind == "issues":
            issue = issues.get((slug, number))
            if issue is None:
                failed = True
                sources.append(f"  {identity}: INCOMPLETE — board issue record unavailable")
                continue
            if manifest["initiative_label"] not in labels(issue):
                sync.append(f"  {identity} is on the master board but lacks initiative label")
            if issue.get("state") == "closed" and status != "Done":
                sync.append(f"  {identity} issue CLOSED but Status={status} → set Done")
                continue
            if status == "Awaiting human action":
                trail = comments.get((slug, number))
                if trail is None:
                    gates.append(f"  {identity} NOT CHECKABLE — comments unavailable")
                else:
                    horizon = max(
                        (i for i, c in enumerate(trail) if MARKER.match(c.get("body") or "")),
                        default=-1,
                    )
                    pending = trail[horizon + 1:]
                    if pending:
                        gates.append(f"  {identity} POST-HORIZON comment(s):")
                        for comment in pending:
                            gates.append(f"    ┌ {comment.get('created_at', 'unknown time')}")
                            gates.extend(
                                f"    │ {line}"
                                for line in (comment.get("body") or "").splitlines()
                            )
                assignees = card.get("assignees") or []
                if operator in assignees:
                    queue.append(
                        f"  {identity} — {issue.get('title', card.get('title', ''))}"
                        f"\n    ask: {first_ask(issue.get('body'))}"
                    )
                elif operator is not None:
                    age = iso_age(issue.get("updated_at"), hours=False)
                    if age is not None and age >= IDLE_DAYS:
                        title = issue.get("title", "")
                        queue.append(
                            f"  other lane idle {int(age)}d: {identity} — {title}"
                        )
            if status == "Todo" and card.get("responsible") == "AI agent":
                candidates.append((slug, number, issue.get("title", card.get("title", ""))))
            if status == "Agent working":
                trail = comments.get((slug, number))
                branches = remote_branches.get(slug)
                if (
                    trail is None or branches is None
                    or not all(pr_complete.values())
                    or not all(references_complete.values())
                ):
                    sync.append(
                        f"  {identity} stale claim NOT CHECKABLE — "
                        "comments, PRs, links, or branches unavailable"
                    )
                else:
                    markers = [c for c in trail if MARKER.match(c.get("body") or "")]
                    marker = markers[-1] if markers else None
                    age = iso_age(marker.get("created_at")) if marker else float("inf")
                    linked_prs = [
                        p for (p_slug, _), p in prs.items()
                        if p.get("state") == "open"
                        and (slug, number) in (
                            pr_links(p, p_slug, scoped_issue_keys)
                            | (pr_references.get((p_slug, p["number"])) or set())
                        )
                    ]
                    has_branch = any(re.match(rf"^issue-{number}(?:$|[^0-9])", b) for b in branches)
                    if marker is not None and age is None:
                        failed = True
                        sources.append(f"  {identity} marker: INCOMPLETE — invalid timestamp")
                        sync.append(
                            f"  {identity} stale claim NOT CHECKABLE — invalid marker time"
                        )
                    elif age > STALE_HOURS and not linked_prs and not has_branch:
                        sync.append(
                            f"  STALE CLAIM {identity} — "
                            f"marker {str(int(age)) + 'h old' if marker else 'missing'}; "
                            "no linked open PR or issue branch; verify then re-queue; "
                            f"marker: {(marker or {}).get('body', 'none')!r}"
                        )
                    elif linked_prs:
                        sync.append(
                            f"  {identity} Agent working with open PR — set Awaiting code review"
                        )
        else:
            pr = prs.get((slug, number))
            if pr is None:
                failed = True
                sources.append(f"  {identity} PR: INCOMPLETE — board PR record unavailable")
            elif pr.get("merged_at") and status != "Done":
                sync.append(f"  {identity} PR MERGED but Status={status} → set Done")
            elif pr.get("state") == "closed" and not pr.get("merged_at"):
                sync.append(
                    f"  {identity} PR CLOSED unmerged but Status={status} → confirm intent"
                )

    for key in sorted(scoped_issue_keys):
        issue = issues[key]
        if issue.get("state") != "closed" or "human-review" not in labels(issue):
            continue
        trail = comments.get(key)
        identity = qualified(*key)
        if trail is None:
            gates.append(f"  {identity} closed gate NOT CHECKABLE — comments unavailable")
            continue
        processed = [c for c in trail if (c.get("body") or "").startswith("Processed:")]
        finalized = [
            c for c in processed
            if "(in progress" not in (c.get("body") or "")
            and "(superseded" not in (c.get("body") or "")
        ]
        if finalized:
            continue
        live = [
            c for c in processed
            if "(in progress" in (c.get("body") or "")
            and "(superseded" not in (c.get("body") or "")
        ]
        if live:
            age = iso_age(live[-1].get("created_at"))
            if age is None:
                failed = True
                sources.append(f"  {identity} gate claim: INCOMPLETE — invalid timestamp")
                gates.append(f"  {identity} closed gate claim NOT CHECKABLE — invalid timestamp")
            else:
                state = "ABANDONED" if age > STALE_HOURS else "in progress"
                gates.append(f"  {identity} closed gate claim {state} — {issue.get('title', '')}")
        else:
            gates.append(f"  UNPROCESSED closed gate {identity} — {issue.get('title', '')}")

    if review_queue is not None:
        for number, title, is_open, body in review_queue:
            refs = {
                (canonical_slugs.get(s.lower(), s), int(n))
                for s, n in re.findall(r"\b([\w.-]+/[\w.-]+)#(\d+)\b", body)
            }
            refs.update(
                (review_repo, int(n))
                for n in re.findall(r"(?<![\w/])#(\d+)\b", body)
            )
            refs.update(
                (slug, n) for (slug, n), issue in issues.items()
                if (slug, n) in scoped_issue_keys and re.search(
                    rf"\bHRQ\s*(?:item\s*)?#?{number}\b",
                    (issue.get("title") or "") + " " + (issue.get("body") or ""),
                    re.IGNORECASE,
                )
            )
            if is_open and refs:
                sync.append(
                    f"  HRQ item {number} — refs "
                    + ", ".join(qualified(s, n) for s, n in sorted(refs))
                    + f" — {title} (consolidation requires judgment)"
                )
            elif is_open:
                sync.append(
                    f"  HRQ item {number} — NO CARD REF — {title} "
                    "(consolidation requires judgment)"
                )
            elif any(
                key in issues
                and key in scoped_issue_keys
                and issues[key].get("state") == "open"
                and "human-review" in labels(issues[key])
                for key in refs
            ):
                sync.append(f"  HRQ item {number} checked off but open human-review card remains")

    # An unrelated repository PR is never called an orphan merely because it was
    # returned in a complete repository-level fetch.
    scoped_prs = {(slug, n) for slug, n, kind in scoped_cards if kind == "pull"}
    for (slug, number), pr in prs.items():
        if pr.get("state") != "open":
            continue
        if (slug, number) not in pr_references:
            continue
        links = pr_links(pr, slug, scoped_issue_keys) | (
            pr_references[(slug, number)] & scoped_issue_keys
        )
        if not links and (slug, number) not in scoped_prs:
            continue
        if (slug, number) in scoped_prs:
            continue
        tracked = any(
            (s, n, "issues") in scoped_cards
            and scoped_cards[(s, n, "issues")].get("status") == "Awaiting code review"
            for s, n in links
        )
        if not tracked:
            sync.append(f"  in-scope open PR {qualified(slug, number)} lacks a review card")

    if failed:
        fallback = "  UNKNOWN — required source incomplete; no no-work or approval inference"
        sources.append("  overall: INCOMPLETE — no global no-work or approval conclusion")
    else:
        fallback = "  none"
    lines = ["=== KANBAN-CHECK REPORT ===", "STEP0:", *(steps or ["  unavailable"]),
             "SOURCES:", *sources, "SYNC:", *(sync or [fallback]),
             "GATES:", *(gates or [fallback]), "QUEUE:", *(queue or [fallback]),
             "CANDIDATES:"]
    mine = [
        (s, n, t) for s, n, t in candidates
        if board and operator in (scoped_cards[(s, n, "issues")].get("assignees") or [])
    ]
    selection = mine if mine else candidates
    if operator is None:
        lines.append("  UNKNOWN — operator unavailable; lane selection suppressed")
        lines.append("=== END KANBAN-CHECK REPORT ===")
        return "\n".join(lines) + "\n", False
    if selection:
        prefix = "" if mine else "POACHABLE "
        for slug, number, title in sorted(selection):
            lines.append(f"  {prefix}{qualified(slug, number)} — {title}")
            if (slug, number) not in comments:
                lines.append("    NOT CHECKABLE — issue comments unavailable")
            else:
                for comment in comments[(slug, number)]:
                    if comments_full:
                        lines.append(f"    ┌ {comment.get('created_at', 'unknown time')}")
                        lines.extend(
                            f"    │ {line}"
                            for line in (comment.get("body") or "").splitlines()
                        )
                    else:
                        lines.append(f"    · {first_ask(comment.get('body'))}")
    else:
        lines.append(fallback)
    lines.append("=== END KANBAN-CHECK REPORT ===")
    return "\n".join(lines) + "\n", not failed


def main() -> int:
    """Parse the opt-in CLI and print the complete or explicitly partial report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--operator")
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--comments", choices=("brief", "full"), default="brief")
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"invalid manifest: {exc}", file=sys.stderr)
        return 2
    manifest_dir = args.manifest.resolve().parent
    checkout_root = manifest_dir.parent if manifest_dir.name == "plan" else manifest_dir
    report, complete = render(manifest, checkout_root, args.operator,
                              args.no_fetch, args.comments == "full")
    print(report, end="")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
