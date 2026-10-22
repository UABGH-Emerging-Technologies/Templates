"""Offline claim races and scope failures; fake transport never reaches GitHub."""
import importlib.util
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "coordination_actions", Path(__file__).resolve().parents[1] / "template/platforms/github/coordination_actions.py"
)
actions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(actions)


class FakeTransport:
    def __init__(self):
        self.issue_data = {"number": 7, "html_url": "https://github.com/owner/product/issues/7",
                           "state": "open", "labels": [{"name": "initiative"}],
                           "assignees": [{"login": "operator"}]}
        self.entries = []
        self.writes = []
        self.reads = 0
        self.race = False
        self.login = "operator"
        self.fail_read = None

    def viewer(self):
        return self.login

    def issue(self, repo, number):
        return deepcopy(self.issue_data)

    def comments(self, repo, number):
        self.reads += 1
        if self.fail_read == self.reads:
            raise actions.SafetyError("later page failed")
        if self.race and self.reads == 3:
            self.entries.append({"id": 99, "body": "Claiming: other · other-nonce"})
        return deepcopy(self.entries)

    def create_comment(self, repo, number, body):
        self.writes.append(("create", repo, number, body))
        result = {"id": 100 + len(self.writes), "body": body}
        self.entries.append(result)
        return deepcopy(result)

    def edit_comment(self, repo, comment_id, body):
        self.writes.append(("edit", repo, comment_id, body))
        for comment in self.entries:
            if comment["id"] == comment_id:
                comment["body"] = body
                return deepcopy(comment)
        raise AssertionError("comment does not exist")


class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.manifest = {"schema_version": 1, "automation_enabled": True,
                         "initiative_label": "initiative",
                         "repositories": [{"slug": "owner/product"}, {"slug": "owner/library"}]}
        self.engine = actions.ClaimEngine(self.manifest, self.transport)

    def claim(self, apply=True):
        return self.engine.claim("owner/product#7", "operator", "session-123", apply)

    def test_default_dry_run_has_no_writes(self):
        result = self.engine.claim("owner/product#7", "operator", "session-123")
        self.assertEqual(result["outcome"], "dry-run")
        self.assertEqual(self.transport.writes, [])

    def test_winning_claim_posts_only_owning_issue(self):
        result = self.claim()
        self.assertEqual(result["outcome"], "won")
        self.assertEqual(self.transport.writes[0][1:3], ("owner/product", 7))
        self.assertEqual(self.transport.reads, 3)

    def test_race_loser_supersedes_only_own_comment_by_id(self):
        self.transport.race = True
        result = self.claim()
        self.assertEqual(result["outcome"], "lost")
        self.assertEqual(result["winner"], 99)
        self.assertEqual(self.transport.writes[-1][2], result["comment_id"])
        self.assertTrue(self.transport.writes[-1][-1].endswith("(superseded)"))

    def test_existing_live_claim_is_not_stolen(self):
        self.transport.entries = [{"id": 9, "body": "Claiming: another · abcdef"}]
        self.assertEqual(self.claim()["outcome"], "held")
        self.assertEqual(self.transport.writes, [])

    def test_finalized_processed_is_not_a_live_claim(self):
        self.transport.entries = [{"id": 9, "body": "Processed: approved and recorded"}]
        self.assertEqual(self.claim()["outcome"], "won")

    def test_in_progress_processed_blocks_claim(self):
        self.transport.entries = [{"id": 9, "body": "Processed: (in progress — operator · abcd)"}]
        self.assertEqual(self.claim()["outcome"], "held")
        self.assertEqual(self.transport.writes, [])

    def test_superseded_claim_does_not_block(self):
        self.transport.entries = [{"id": 9, "body": "Claiming: another · abcdef (superseded)"}]
        self.assertEqual(self.claim()["outcome"], "won")

    def test_bare_and_out_of_scope_identities_rejected(self):
        for identity in ("7", "#7", "other/product#7", "owner/product#0"):
            with self.subTest(identity=identity), self.assertRaises(actions.SafetyError):
                self.engine.claim(identity, "operator", "session-123", True)
        self.assertEqual(self.transport.writes, [])

    def test_colliding_numbers_cannot_cross_repository(self):
        with self.assertRaises(actions.SafetyError):
            self.engine.claim("owner/library#7", "operator", "session-123", True)
        self.assertEqual(self.transport.writes, [])

    def test_incomplete_paginated_read_blocks_writes(self):
        for read in (1, 2):
            with self.subTest(read=read):
                self.transport.reads = 0
                self.transport.fail_read = read
                with self.assertRaises(actions.SafetyError):
                    self.claim()
                self.assertEqual(self.transport.writes, [])

    def test_duplicate_comment_ids_rejected(self):
        self.transport.entries = [{"id": 2, "body": "ordinary"}] * 2
        with self.assertRaises(actions.SafetyError):
            self.claim()
        self.assertEqual(self.transport.writes, [])

    def test_label_assignee_and_issue_state_are_required(self):
        for field, value in (("labels", [{"name": "unrelated"}]), ("assignees", []),
                             ("state", "closed"), ("pull_request", {"url": "example"})):
            with self.subTest(field=field):
                original = deepcopy(self.transport.issue_data)
                self.transport.issue_data[field] = value
                with self.assertRaises(actions.SafetyError):
                    self.claim()
                self.transport.issue_data = original
        self.assertEqual(self.transport.writes, [])

    def test_disabled_manifest_and_spoofed_operator_block_writes(self):
        self.manifest["automation_enabled"] = False
        with self.assertRaises(actions.SafetyError):
            self.claim()
        self.manifest["automation_enabled"] = True
        self.transport.login = "someone-else"
        with self.assertRaises(actions.SafetyError):
            self.claim()
        self.assertEqual(self.transport.writes, [])

    def test_fresh_claim_between_check_and_write_blocks(self):
        original = self.transport.comments
        def changed(repo, number):
            if self.transport.reads == 1:
                self.transport.entries.append({"id": 42, "body": "Claiming: other · abcd"})
            return original(repo, number)
        self.transport.comments = changed
        self.assertEqual(self.claim()["outcome"], "held")
        self.assertEqual(self.transport.writes, [])

    def test_comment_requires_own_winning_nonce(self):
        self.claim()
        with self.assertRaises(actions.SafetyError):
            self.engine.comment("owner/product#7", "operator", "wrong-nonce", "Agent: status", True)
        result = self.engine.comment(
            "owner/product#7", "operator", "session-123", "Agent: status", True
        )
        self.assertEqual(result["outcome"], "commented")

    def test_release_changes_only_exact_session_marker(self):
        result = self.claim()
        with self.assertRaises(actions.SafetyError):
            self.engine.release("owner/product#7", "operator", "wrong-nonce", True)
        self.engine.release("owner/product#7", "operator", "session-123", True)
        self.assertEqual(self.transport.writes[-1][2], result["comment_id"])
        self.assertFalse(actions.live_claim(self.transport.entries[0]))

    def test_rest_pages_must_all_be_arrays(self):
        transport = actions.GitHubTransport()
        for value in ({"message": "failed"}, [], [[{"id": 1}], {"message": "failed"}]):
            with patch.object(transport, "_run", return_value=value):
                with self.assertRaises(actions.SafetyError):
                    transport.comments("owner/product", 7)
        with patch.object(transport, "_run", return_value=[[{"id": 1}], [{"id": 2}]]):
            self.assertEqual(len(transport.comments("owner/product", 7)), 2)


class DecisionTests(unittest.TestCase):
    def test_feature_acceptance_never_completes_issue(self):
        for merge in (False, True):
            plan = actions.plan_decision("feature", "accept", merge_requested=merge)
            self.assertFalse(plan["close_issue"])
            self.assertFalse(plan["mark_done"])
            self.assertEqual(plan["merge_authorized"], merge)

    def test_feedback_resumes_only_selected_feature(self):
        self.assertEqual(actions.plan_decision("feature", "feedback")["action"], "requeue")
        self.assertEqual(
            actions.plan_decision("feature", "feedback", selected_feature=True)["action"],
                         "fix-selected-feature")

    def test_gate_decision_and_ambiguity(self):
        self.assertTrue(actions.plan_decision("gate-only", "accept")["close_issue"])
        self.assertFalse(actions.plan_decision("gate-only", "feedback")["close_issue"])
        self.assertEqual(actions.plan_decision("feature", "ambiguous")["action"], "clarify")
        with self.assertRaises(actions.SafetyError):
            actions.plan_decision("unknown", "accept")

    def test_rejection_and_deferral_never_unblock_work(self):
        for kind in ("feature", "gate-only"):
            for classification in ("reject", "defer"):
                plan = actions.plan_decision(kind, classification, merge_requested=True)
                self.assertFalse(plan["follow_on_work"])
                self.assertFalse(plan["merge_authorized"])
                self.assertNotEqual(plan["action"], "process-gate")
        self.assertTrue(actions.plan_decision("gate-only", "reject")["close_issue"])
        self.assertFalse(actions.plan_decision("gate-only", "defer")["close_issue"])
        self.assertFalse(actions.plan_decision("feature", "reject")["close_issue"])
        self.assertTrue(actions.plan_decision("gate-only", "accept")["follow_on_work"])

    def test_pr_backed_recovery_requires_complete_inactive_agent_state(self):
        now = datetime.now(timezone.utc)
        args = dict(status="Agent working", responsible="AI agent", now=now,
                    last_activity=now - timedelta(hours=25), session_active=False,
                    evidence_complete=True, has_pr=True)
        self.assertTrue(actions.recovery_eligible(**args))
        for field, value in (("status", "Awaiting human action"), ("responsible", "operator"),
                             ("session_active", True), ("session_active", None),
                             ("evidence_complete", False), ("last_activity", now)):
            changed = {**args, field: value}
            self.assertFalse(actions.recovery_eligible(**changed))


if __name__ == "__main__":
    unittest.main()
