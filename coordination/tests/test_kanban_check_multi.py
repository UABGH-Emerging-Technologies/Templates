"""Acceptance fixtures for repository-aware, read-only orientation."""

import importlib.util
import unittest
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "template/platforms/github/kanban_check_multi.py"
SPEC = importlib.util.spec_from_file_location("kanban_check_multi", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
import sys
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def issue(number, title, labels, state="open", body="Please review this.", comments=None):
    return {
        "number": number, "title": title, "labels": [{"name": label} for label in labels],
        "state": state, "body": body, "updated_at": "2026-01-01T00:00:00Z",
        "comments": comments or [],
    }


def card(slug, number, status, assignee, kind="issues"):
    return {
        "id": f"card-{slug}-{number}", "status": status, "responsible": "AI agent",
        "assignees": [assignee], "title": f"Card {number}",
        "content": {"url": f"https://github.com/{slug}/{kind}/{number}"},
    }


class OrientationTests(unittest.TestCase):
    def setUp(self):
        deny_commands = patch.object(
            MODULE.subprocess, "run", side_effect=AssertionError("offline fixture attempted a command")
        )
        deny_commands.start()
        self.addCleanup(deny_commands.stop)
        self.slugs = ("Example/product", "Example/library", "Example/lead")
        self.manifest = {
            "schema_version": 1, "project_owner": "Example", "project_number": 12,
            "initiative_label": "mac-transition",
            "repositories": [
                {"slug": slug, "local_path": slug.split("/")[1],
                 "integration_branch": "develop" if slug.endswith("library") else "main"}
                for slug in self.slugs
            ],
        }
        self.board = [
            card(self.slugs[0], 7, "Todo", "alice"),
            card(self.slugs[1], 7, "Todo", "bob"),
            card(self.slugs[0], 8, "Awaiting human action", "alice"),
        ]
        self.issues = {
            self.slugs[0]: [issue(7, "Product work", ["mac-transition"]),
                            issue(8, "Closed gate", ["mac-transition", "human-review"], "closed")],
            self.slugs[1]: [issue(7, "Library work", ["mac-transition"])],
            self.slugs[2]: [issue(7, "Unrelated Lead gate", ["human-review"], "closed")],
        }
        self.prs = {slug: [] for slug in self.slugs}
        self.comments = {(self.slugs[0], 8): []}

    def render(self, board=None, unavailable=None, bad_comments=None, pr_refs=None,
               review_md=""):
        self.read_commands = []
        board = self.board if board is None else board
        unavailable = unavailable or set()
        bad_comments = bad_comments or set()
        pr_refs = pr_refs or {}

        def fetch(endpoint):
            slug = endpoint.split("/issues", 1)[0].split("/pulls", 1)[0].removeprefix("repos/")
            if slug in unavailable:
                return MODULE.Source(None, "repository unavailable")
            if "/comments?" in endpoint:
                number = int(endpoint.split("/issues/")[1].split("/")[0])
                if (slug, number) in bad_comments:
                    return MODULE.Source(None, "comment page failed")
                return MODULE.Source(self.comments.get((slug, number), []))
            if "/pulls?" in endpoint:
                return MODULE.Source(self.prs[slug])
            return MODULE.Source(self.issues[slug])

        def fresh(repo, _base, _no_fetch):
            if repo["slug"] in unavailable:
                return MODULE.Source(None, "checkout unavailable")
            branch = repo["integration_branch"]
            return MODULE.Source({"path": "/tmp/checkout", "branch": branch,
                                  "integration": "a" * 40, "head": "b" * 40,
                                  "dirty": 0, "status": "## main",
                                  "worktrees": ["/tmp/checkout"], "branches": [branch]})

        def read_command(*args, **_kwargs):
            self.read_commands.append(args)
            if args[:2] == ("git", "show"):
                return MODULE.Source(review_md)
            return MODULE.Source("")

        with patch.object(MODULE, "board_items", return_value=MODULE.Source(board)), \
             patch.object(MODULE, "rest_pages", side_effect=fetch), \
             patch.object(MODULE, "freshness", side_effect=fresh), \
             patch.object(
                 MODULE, "closing_references",
                 side_effect=lambda slug, number: MODULE.Source(
                     pr_refs.get((slug, number), set())
                 ),
             ), \
             patch.object(MODULE, "command", side_effect=read_command):
            return MODULE.render(self.manifest, Path("/tmp"), "alice", True, False)

    def test_colliding_numbers_branches_lanes_and_archived_gate(self):
        report, complete = self.render()
        self.assertTrue(complete)
        self.assertIn("Example/product#7 — Product work", report)
        self.assertNotIn("Example/library#7 — Library work", report.split("CANDIDATES:")[1])
        self.assertIn("Example/library origin/develop", report)
        self.assertIn("UNPROCESSED closed gate Example/product#8", report)
        self.assertNotIn("Unrelated Lead gate", report)

    def test_unavailable_repo_never_reports_all_clear(self):
        report, complete = self.render(unavailable={self.slugs[1]})
        self.assertFalse(complete)
        self.assertIn("Example/library issues: INCOMPLETE", report)
        self.assertIn("overall: INCOMPLETE — no global no-work or approval conclusion", report)

    def test_incomplete_comments_are_visible(self):
        report, complete = self.render(bad_comments={(self.slugs[0], 8)})
        self.assertFalse(complete)
        self.assertIn("closed gate NOT CHECKABLE", report)
        self.assertNotIn("UNPROCESSED closed gate Example/product#8", report)

    def test_truncated_board_is_an_incomplete_source(self):
        with patch.object(MODULE, "json_command", return_value=MODULE.Source({
            "totalCount": 401, "items": [{}] * 400
        })) as fetch:
            result = MODULE.board_items("Example", 12)
        self.assertFalse(result.complete)
        self.assertIn("truncated", result.error)
        self.assertEqual(2, fetch.call_count)

    def test_url_identity_does_not_collapse_repositories(self):
        self.assertEqual(("Example/product", 7, "issues"), MODULE.issue_key(
            "https://github.com/Example/product/issues/7"))
        self.assertEqual(("Example/library", 7, "issues"), MODULE.issue_key(
            "https://github.com/Example/library/issues/7"))

    def test_sidebar_only_pr_link_is_scoped_by_full_identity(self):
        self.prs[self.slugs[1]] = [{
            "number": 99, "state": "open", "body": "", "head": {"ref": "other"},
        }]
        report, complete = self.render(pr_refs={
            (self.slugs[1], 99): {(self.slugs[1], 7)}
        })
        self.assertTrue(complete)
        self.assertNotIn("lacks an owning feature card", report)
        self.assertNotIn("Example/product#99", report)

    def test_pr_list_failure_is_not_an_empty_list(self):
        self.prs[self.slugs[1]] = []
        report, complete = self.render(unavailable={self.slugs[1]})
        self.assertFalse(complete)
        self.assertIn("Example/library PRs: INCOMPLETE", report)

    def test_malformed_paginated_response_is_incomplete(self):
        with patch.object(MODULE, "json_command", return_value=MODULE.Source({"items": []})):
            result = MODULE.rest_pages("repos/Example/product/issues?state=all&per_page=100")
        self.assertFalse(result.complete)

    def test_linked_development_cursor_pages(self):
        first = {"data": {"repository": {"pullRequest": {"closingIssuesReferences": {
            "nodes": [{"number": 7, "repository": {"nameWithOwner": self.slugs[0]}}],
            "pageInfo": {"hasNextPage": True, "endCursor": "next"},
        }}}}}
        second = {"data": {"repository": {"pullRequest": {"closingIssuesReferences": {
            "nodes": [{"number": 7, "repository": {"nameWithOwner": self.slugs[1]}}],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }}}}}
        with patch.object(
            MODULE, "json_command",
            side_effect=[MODULE.Source(first), MODULE.Source(second)],
        ) as fetch:
            result = MODULE.closing_references(self.slugs[1], 99)
        self.assertTrue(result.complete)
        self.assertEqual({(self.slugs[0], 7), (self.slugs[1], 7)}, result.value)
        self.assertEqual(2, fetch.call_count)

    def test_review_queue_parser_keeps_open_and_checked_items_distinct(self):
        items = MODULE.hrq_items(
            "## 1. Decide packaging\n- [ ] Waiting\nSee #8\n"
            "## 2. Pick icon\n- [x] Done\n"
        )
        self.assertEqual(2, len(items))
        self.assertTrue(items[0][2])
        self.assertFalse(items[1][2])

    def test_expired_cross_repository_pr_feature_is_recoverable(self):
        self.board.append(card(self.slugs[0], 7, "Agent working", "alice"))
        self.prs[self.slugs[1]] = [{
            "number": 99, "state": "open", "body": "", "head": {"ref": "other"},
        }]
        report, complete = self.render(pr_refs={
            (self.slugs[1], 99): {(self.slugs[0], 7)}
        })
        self.assertTrue(complete)
        self.assertIn("EXPIRED FEATURE LEASE Example/product#7", report)
        self.assertIn("open PRs=1", report)
        self.assertIn("preserve all work", report)
        self.assertNotIn("set Awaiting code review", report)

    def test_unrelated_board_repository_does_not_invalidate_report(self):
        board = self.board + [card("Other/maintenance", 7, "Todo", "alice")]
        report, complete = self.render(board=board)
        self.assertTrue(complete)
        self.assertNotIn("Other/maintenance#7", report)

    def test_invalid_manifest_fails_before_queries(self):
        import json
        import tempfile

        bad = dict(self.manifest)
        bad["repositories"] = [{"slug": self.slugs[0], "local_path": 3,
                                "integration_branch": "main"}, self.manifest["repositories"][1]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repositories.json"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE.load_manifest(path)

    def test_explicit_review_queue_ref_is_exact_and_visible(self):
        import json

        revision = "a5c2f0866e866afc6da287ae7dbb954f5010a1af"
        self.manifest["review_queue_ref"] = revision
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repositories.json"
            path.write_text(json.dumps(self.manifest), encoding="utf-8")
            self.assertEqual(revision, MODULE.load_manifest(path)["review_queue_ref"])
        report, complete = self.render()
        self.assertTrue(complete)
        self.assertIn(("git", "show", f"{revision}:HUMAN-REVIEW-QUEUE.md"), self.read_commands)
        self.assertIn(f"documentation ref: {revision} (explicit branch-local commit)", report)
        self.assertIn(f"documentation ref {revision} (explicit branch-local commit): complete", report)
        self.assertNotIn(("git", "show", "origin/main:HUMAN-REVIEW-QUEUE.md"), self.read_commands)

    def test_review_queue_defaults_to_integration_ref(self):
        report, complete = self.render()
        self.assertTrue(complete)
        self.assertIn(("git", "show", "origin/main:HUMAN-REVIEW-QUEUE.md"), self.read_commands)
        self.assertIn("documentation ref: origin/main (integration branch)", report)

    def test_malformed_explicit_review_queue_ref_is_rejected(self):
        import json

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repositories.json"
            for invalid in (None, "main", "a" * 39, "z" * 40, "a" * 40 + ":other", 123):
                with self.subTest(ref=invalid):
                    path.write_text(json.dumps({**self.manifest, "review_queue_ref": invalid}),
                                    encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "review_queue_ref"):
                        MODULE.load_manifest(path)

    def test_operator_unavailable_suppresses_poaching(self):
        with patch.object(MODULE, "board_items", return_value=MODULE.Source(self.board)), \
             patch.object(MODULE, "rest_pages", return_value=MODULE.Source([])), \
             patch.object(MODULE, "freshness", return_value=MODULE.Source(None, "missing")), \
             patch.object(MODULE, "command", return_value=MODULE.Source(None, "auth missing")):
            report, complete = MODULE.render(self.manifest, Path("/tmp"), None, True, False)
        self.assertFalse(complete)
        self.assertIn("operator unavailable; lane selection suppressed", report)
        self.assertNotIn("POACHABLE", report)

    def test_missing_claim_marker_is_stale_when_evidence_is_complete(self):
        self.board.append(card(self.slugs[0], 7, "Agent working", "alice"))
        report, complete = self.render()
        self.assertTrue(complete)
        self.assertIn("EXPIRED FEATURE LEASE Example/product#7 — marker missing", report)

    def test_checked_hrq_item_with_open_gate_is_reported(self):
        self.issues[self.slugs[0]][1]["state"] = "open"
        report, complete = self.render(review_md="## 1. Resource gate\n- [x] Done\nSee #8\n")
        self.assertTrue(complete)
        self.assertIn("HRQ item 1 checked off but open human-review card remains", report)

    def test_closed_unmerged_pr_card_requires_intent(self):
        self.board.append(card(self.slugs[1], 99, "Awaiting code review", "bob", "pull"))
        self.prs[self.slugs[1]] = [{"number": 99, "state": "closed", "merged_at": None}]
        report, complete = self.render()
        self.assertTrue(complete)
        self.assertIn("Example/library#99 PR CLOSED unmerged", report)

    def test_closed_issue_is_not_a_pickup_candidate(self):
        self.issues[self.slugs[0]][0]["state"] = "closed"
        report, complete = self.render()
        self.assertTrue(complete)
        self.assertIn("Example/product#7 issue CLOSED", report)
        self.assertNotIn("Example/product#7 — Product work", report.split("CANDIDATES:")[1])

    def test_candidate_comment_failure_suppresses_selection(self):
        report, complete = self.render(bad_comments={(self.slugs[0], 7)})
        self.assertFalse(complete)
        self.assertIn("Example/product#7 comments: INCOMPLETE", report)
        candidates = report.split("CANDIDATES:")[1]
        self.assertIn("required source incomplete; lane selection suppressed", candidates)
        self.assertNotIn("Product work", candidates)

    def test_live_pr_feature_retains_agent_ownership(self):
        self.board[0]["status"] = "Agent working"
        self.comments[(self.slugs[0], 7)] = [{
            "body": "Claiming: alice · test", "created_at": datetime.now(timezone.utc).isoformat(),
        }]
        self.prs[self.slugs[0]] = [{
            "number": 99, "state": "open", "body": "Closes #7", "head": {"ref": "issue-7-work"},
        }]
        report, complete = self.render()
        self.assertTrue(complete)
        self.assertIn("active feature with open PR — retain agent ownership", report)
        self.assertNotIn("EXPIRED FEATURE LEASE Example/product#7", report)
        self.assertNotIn("lacks an owning feature card", report)

    def test_reviewing_expired_agent_feature_recovers_but_human_wait_does_not(self):
        self.board[0]["status"] = "Awaiting code review"
        report, complete = self.render()
        self.assertTrue(complete)
        self.assertIn("EXPIRED FEATURE LEASE Example/product#7", report)
        self.board[0]["status"] = "Awaiting human action"
        report, complete = self.render()
        self.assertTrue(complete)
        self.assertNotIn("EXPIRED FEATURE LEASE Example/product#7", report)

    def test_checkout_origin_mismatch_stops_before_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = {"slug": "Example/product", "local_path": ".", "integration_branch": "main"}
            with patch.object(MODULE, "command", return_value=MODULE.Source(
                "https://github.com/Other/repository.git\n"
            )) as command:
                result = MODULE.freshness(repo, Path(directory), False)
            self.assertFalse(result.complete)
            self.assertIn("does not match Example/product", result.error)
            self.assertEqual(2, command.call_count)
            self.assertNotIn("fetch", [part for call in command.call_args_list for part in call.args])

    def test_verified_origin_redirect_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = {"slug": "Example/product", "local_path": ".", "integration_branch": "main"}

            def read(*args, **kwargs):
                if args[:4] == ("git", "remote", "get-url", "origin"):
                    return MODULE.Source("https://github.com/OldOwner/product.git")
                if args[:2] == ("gh", "api"):
                    self.assertEqual("repos/OldOwner/product", args[2])
                    return MODULE.Source("Example/product\n")
                if args[:2] == ("git", "status"):
                    return MODULE.Source("## main\n")
                if args[:2] == ("git", "rev-parse"):
                    return MODULE.Source("a" * 40)
                return MODULE.Source("")

            with patch.object(MODULE, "command", side_effect=read) as command:
                result = MODULE.freshness(repo, Path(directory), True)
            self.assertTrue(result.complete)
            self.assertEqual("OldOwner/product", result.value["origin_alias"])
            self.assertFalse(any("set-url" in call.args for call in command.call_args_list))

    def test_failed_origin_redirect_suppresses_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = {"slug": "Example/product", "local_path": ".", "integration_branch": "main"}
            with patch.object(MODULE, "command", side_effect=[
                MODULE.Source("git@github.com:OldOwner/product.git"),
                MODULE.Source(None, "GitHub unavailable"),
            ]) as command:
                result = MODULE.freshness(repo, Path(directory), False)
            self.assertFalse(result.complete)
            self.assertIn("redirect unverified", result.error)
            self.assertEqual(2, command.call_count)

    def test_origin_url_formats_and_naive_time(self):
        for url in ("https://github.com/Example/product.git",
                    "git@github.com:Example/product.git",
                    "ssh://git@github.com/Example/product.git"):
            self.assertEqual("Example/product", MODULE.origin_slug(url))
        self.assertIsNone(MODULE.origin_slug("https://other.example/Example/product.git"))
        self.assertIsNone(MODULE.iso_age("2026-01-01T00:00:00"))

    def test_repeated_graphql_cursor_is_incomplete(self):
        response = {"data": {"repository": {"pullRequest": {"closingIssuesReferences": {
            "nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "same"},
        }}}}}
        with patch.object(MODULE, "json_command", return_value=MODULE.Source(response)) as fetch:
            result = MODULE.closing_references("Example/product", 1)
        self.assertFalse(result.complete)
        self.assertIn("repeated cursor", result.error)
        self.assertEqual(2, fetch.call_count)

    def test_nonobject_rest_record_is_incomplete(self):
        with patch.object(MODULE, "json_command", return_value=MODULE.Source([[None]])):
            self.assertFalse(MODULE.rest_pages("repos/Example/product/issues?state=all").complete)

    def test_cross_repository_hrq_back_reference(self):
        self.issues[self.slugs[1]][0]["title"] = "HRQ #5 implementation tracking"
        report, complete = self.render(review_md="## 5. Choose runtime\n- [ ] Waiting\n")
        self.assertTrue(complete)
        self.assertIn("HRQ item 5 — refs Example/library#7", report)

    def test_invalid_gate_claim_time_does_not_look_live(self):
        self.comments[(self.slugs[0], 8)] = [{
            "body": "Processed: (in progress — worker)", "created_at": "invalid"
        }]
        report, complete = self.render()
        self.assertFalse(complete)
        self.assertIn("closed gate claim NOT CHECKABLE", report)
        self.assertNotIn("closed gate claim in progress", report)


if __name__ == "__main__":
    unittest.main()
