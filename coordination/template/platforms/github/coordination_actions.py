#!/usr/bin/env python3
"""Guarded owning-issue claims; dry-run by default, with no board mutation.

The caller still judges stakeholder payloads and supplies complete recovery
evidence. This module never infers acceptance from prose or performs merges.
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

IDENTITY = re.compile(r"^([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([1-9][0-9]*)$")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{4,80}$")


class SafetyError(ValueError):
    """Required scope, identity, or complete evidence is missing."""


def qualified_issue(value: str) -> tuple[str, int]:
    """Require an explicit owning repository; bare issue numbers are unsafe."""
    match = IDENTITY.fullmatch(value)
    if not match:
        raise SafetyError("expected owner/repo#number")
    return match.group(1), int(match.group(2))


def live_claim(comment: dict[str, Any]) -> bool:
    """Recognize active work claims and unfinished gate-processing claims."""
    body = comment.get("body", "")
    if not isinstance(body, str) or any(
        marker in body for marker in ("(superseded", "(completed")
    ):
        return False
    return body.startswith("Claiming:") or (
        body.startswith("Processed:") and "(in progress" in body
    )


class GitHubTransport:
    """Small injectable gh transport. All comment pages must finish successfully."""

    def _run(self, *args: str) -> Any:
        result = subprocess.run(
            ["gh", *args], text=True, capture_output=True, timeout=120, check=False
        )
        if result.returncode:
            raise SafetyError("GitHub request failed; no complete evidence available")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise SafetyError("GitHub returned invalid JSON") from exc

    def viewer(self) -> str:
        return self._run("api", "user")["login"]

    def issue(self, repo: str, number: int) -> dict[str, Any]:
        return self._run("api", f"repos/{repo}/issues/{number}")

    def comments(self, repo: str, number: int) -> list[dict[str, Any]]:
        pages = self._run(
            "api", "--paginate", "--slurp", f"repos/{repo}/issues/{number}/comments?per_page=100"
        )
        if not isinstance(pages, list) or not pages or any(not isinstance(p, list) for p in pages):
            raise SafetyError("incomplete comment pagination")
        return [comment for page in pages for comment in page]

    def create_comment(self, repo: str, number: int, body: str) -> dict[str, Any]:
        return self._run("api", "--method", "POST", f"repos/{repo}/issues/{number}/comments",
                         "-f", f"body={body}")

    def edit_comment(self, repo: str, comment_id: int, body: str) -> dict[str, Any]:
        return self._run("api", "--method", "PATCH", f"repos/{repo}/issues/comments/{comment_id}",
                         "-f", f"body={body}")


class ClaimEngine:
    """Validate scope on every read and arbitrate concurrent claims by comment ID.

    Injected transports must return all comment pages or raise SafetyError; an
    incomplete read must never be represented as an empty successful list.
    """

    def __init__(self, manifest: dict[str, Any], transport: Any):
        repos = manifest.get("repositories")
        label = manifest.get("initiative_label")
        if manifest.get("schema_version") != 1 or not isinstance(repos, list) or not repos:
            raise SafetyError("invalid manifest schema/repositories")
        slugs = [repo.get("slug") for repo in repos if isinstance(repo, dict)]
        if len(slugs) != len(repos) or any(
            not isinstance(s, str) or not IDENTITY.fullmatch(s + "#1") for s in slugs
        ):
            raise SafetyError("invalid repository scope")
        if len(set(slugs)) != len(slugs) or not isinstance(label, str) or not label.strip():
            raise SafetyError("duplicate repositories or missing initiative label")
        self.manifest, self.transport = manifest, transport
        self.repositories, self.label = set(slugs), label

    def snapshot(
        self, identity: str, operator: str | None = None
    ) -> tuple[str, int, list[dict[str, Any]]]:
        repo, number = qualified_issue(identity)
        if repo not in self.repositories:
            raise SafetyError("owning repository is outside manifest scope")
        issue = self.transport.issue(repo, number)
        if (not isinstance(issue, dict) or issue.get("number") != number
                or issue.get("pull_request")):
            raise SafetyError("owning issue evidence is invalid")
        if issue.get("html_url") != f"https://github.com/{repo}/issues/{number}":
            raise SafetyError("owning issue identity does not match")
        if issue.get("state") != "open":
            raise SafetyError("cannot claim a closed issue")
        labels = issue.get("labels")
        if not isinstance(labels, list) or self.label not in [
            x.get("name") for x in labels if isinstance(x, dict)
        ]:
            raise SafetyError("issue lacks exact initiative label")
        if operator is not None:
            assignees = issue.get("assignees")
            if not isinstance(assignees, list) or operator not in [
                x.get("login") for x in assignees if isinstance(x, dict)
            ]:
                raise SafetyError("issue is not assigned to this operator")
        comments = self.transport.comments(repo, number)
        if not isinstance(comments, list):
            raise SafetyError("comments are incomplete")
        ids = [x.get("id") for x in comments if isinstance(x, dict)]
        if (len(ids) != len(comments) or any(type(i) is not int or i <= 0 for i in ids)
                or len(set(ids)) != len(ids)):
            raise SafetyError("comment IDs are incomplete or duplicated")
        if any(not isinstance(x.get("body"), str) for x in comments):
            raise SafetyError("comment bodies are incomplete")
        return repo, number, comments

    def _allow_write(self, operator: str) -> None:
        if self.manifest.get("automation_enabled") is not True:
            raise SafetyError("automation is disabled in this manifest")
        if self.transport.viewer() != operator:
            raise SafetyError("authenticated GitHub operator does not match")

    def claim(
        self, identity: str, operator: str, nonce: str, apply: bool = False
    ) -> dict[str, Any]:
        """Check, post a nonce claim, re-fetch, and supersede a losing claim."""
        if not TOKEN.fullmatch(nonce) or not re.fullmatch(r"[A-Za-z0-9-]+", operator):
            raise SafetyError("invalid operator or session nonce")
        repo, number, comments = self.snapshot(identity, operator)
        if any(live_claim(c) for c in comments):
            return {"issue": identity, "outcome": "held"}
        body = f"Claiming: {operator} · {nonce}"
        if not apply:
            return {"issue": identity, "outcome": "dry-run", "body": body}
        self._allow_write(operator)
        # The second complete snapshot closes stale-report and auth-check gaps.
        _, _, comments = self.snapshot(identity, operator)
        if any(live_claim(c) for c in comments):
            return {"issue": identity, "outcome": "held"}
        created = self.transport.create_comment(repo, number, body)
        own_id = created.get("id")
        if type(own_id) is not int or own_id <= 0:
            raise SafetyError("claim write lacks a valid comment ID; inspect owning issue")
        _, _, comments = self.snapshot(identity, operator)
        own = next((c for c in comments if c["id"] == own_id), None)
        if own is None or own["body"] != body:
            raise SafetyError("posted claim missing or changed; inspect owning issue")
        winner = min(c["id"] for c in comments if live_claim(c))
        if winner != own_id:
            self.transport.edit_comment(repo, own_id, body + " (superseded)")
            return {"issue": identity, "outcome": "lost", "comment_id": own_id, "winner": winner}
        return {"issue": identity, "outcome": "won", "comment_id": own_id, "nonce": nonce}

    def comment(
        self, identity: str, operator: str, nonce: str, body: str, apply: bool = False
    ) -> dict[str, Any]:
        """Post an owning-issue acknowledgment only under this session's winning claim."""
        if not body.startswith("Agent:") or not body.strip() or len(body) > 60000:
            raise SafetyError("acknowledgment must start Agent: and fit GitHub limits")
        if not TOKEN.fullmatch(nonce):
            raise SafetyError("invalid nonce")
        if apply:
            self._allow_write(operator)
        repo, number, comments = self.snapshot(identity, operator)
        claims = sorted((c for c in comments if live_claim(c)), key=lambda c: c["id"])
        if not claims or claims[0]["body"] != f"Claiming: {operator} · {nonce}":
            raise SafetyError("session does not own the winning live claim")
        if apply:
            result = self.transport.create_comment(repo, number, body)
            return {"issue": identity, "outcome": "commented", "comment_id": result["id"]}
        return {"issue": identity, "outcome": "dry-run", "body": body}


    def release(
        self, identity: str, operator: str, nonce: str, apply: bool = False
    ) -> dict[str, Any]:
        """Release only this session's marker, preserving all feature work."""
        if not TOKEN.fullmatch(nonce):
            raise SafetyError("invalid nonce")
        if apply:
            self._allow_write(operator)
        repo, _, comments = self.snapshot(identity, operator)
        body = f"Claiming: {operator} · {nonce}"
        own = [comment for comment in comments if comment["body"] == body]
        if len(own) != 1:
            raise SafetyError("expected exactly one live marker for this session")
        released = body + " (superseded — stakeholder handoff)"
        if apply:
            self.transport.edit_comment(repo, own[0]["id"], released)
        return {"issue": identity, "outcome": "released" if apply else "dry-run",
                "comment_id": own[0]["id"], "body": released}


def plan_decision(card_kind: str, classification: str, *, selected_feature: bool = False,
                  merge_requested: bool = False) -> dict[str, Any]:
    """Plan from an explicitly agent-classified stakeholder payload.

    ``close_issue`` and ``mark_done`` describe gate-only bookkeeping. Feature
    acceptance never completes an issue. ``follow_on_work`` authorizes only
    work unblocked by an affirmative gate decision; rejection and deferral
    never unblock work. A complete gate rejection may close that gate with
    attribution, whereas deferral keeps it open for a later decision.
    """
    if (card_kind not in {"feature", "gate-only"}
            or classification not in {"accept", "reject", "defer", "feedback", "ambiguous"}):
        raise SafetyError("explicit card kind and payload classification required")
    plan = {"close_issue": False, "mark_done": False, "merge_authorized": False,
            "follow_on_work": False}
    if classification == "ambiguous":
        return {**plan, "action": "clarify"}
    if classification == "defer":
        return {**plan, "action": "record-deferral"}
    if classification == "reject":
        return {**plan, "action": "record-rejection", "close_issue": card_kind == "gate-only",
                "mark_done": card_kind == "gate-only"}
    if card_kind == "feature":
        return {**plan, "action": ("record-acceptance" if classification == "accept" else
                                   "fix-selected-feature" if selected_feature else "requeue"),
                "merge_authorized": classification == "accept" and merge_requested}
    return {**plan, "action": "process-gate" if classification == "accept" else "requeue",
            "close_issue": classification == "accept", "mark_done": classification == "accept",
            "follow_on_work": classification == "accept"}


def recovery_eligible(*, status: str, responsible: str, last_activity: datetime,
                      now: datetime, session_active: bool | None, evidence_complete: bool,
                      has_pr: bool = False) -> bool:
    """PRs preserve work but do not exempt expired agent-owned feature leases."""
    del has_pr
    return (evidence_complete and session_active is False and responsible == "AI agent"
            and status in {"Agent working", "Awaiting code review"}
            and last_activity.tzinfo is not None and now.tzinfo is not None
            and now - last_activity >= timedelta(hours=24))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--nonce", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text())
        result = ClaimEngine(manifest, GitHubTransport()).claim(
            args.issue, args.operator, args.nonce or secrets.token_hex(8), args.apply
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (SafetyError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        parser.exit(2, f"coordination action refused: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
