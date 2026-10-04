"""Temporary-only fixtures for the read-only shared coordination checker."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.check_coordination import _within, check_coordination


class CoordinationChecksTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "checkout"
        self.hub = self.base / "GTT coordination"
        self.root.mkdir()
        (self.hub / "workers").mkdir(parents=True)
        self.worker = {
            "id": "worker1", "checkout": str(self.root.resolve()),
            "branch": "codex/optimizer-polish", "status": "workers/worker1.md",
            "thread_id": "thread-1", "title": "Optimizer polish",
        }
        self.registry = {
            "schema": "gtt_shared_coordination_v1", "queue_owner": "worker1",
            "workers": [self.worker],
        }
        self.write(self.root / "coordination.json", json.dumps({
            "schema": "gtt_coordination_link_v1", "hub": "../GTT coordination",
        }))
        for name in ("README.md", "TODO.md", "BACKLOG.md"):
            self.write(self.hub / name, f"# {name}\n[Worker](workers/worker1.md)\n")
        self.save_registry()
        self.write(self.hub / "workers/worker1.md", self.status())
        self.write(self.root / "AGENTS.md", "See coordination.json.\n")
        self.write(self.root / "CODEX.md", "Use shared coordination.\n")
        self.write(self.root / "TODO.md", "<!-- coordination-router -->\n[Hub](../GTT coordination/TODO.md)\n")
        self.write(self.root / "docs/handoff/WORK_BACKLOG.md", "<!-- coordination-router -->\n")

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def status(self, integration="branch_work", extra=""):
        return ("<!-- coordination-worker: worker1 -->\n"
                "- Branch: `codex/optimizer-polish`\n"
                f"- Integration: `{integration}`\n{extra}")

    def save_registry(self):
        self.write(self.hub / "registry.json", json.dumps(self.registry))

    def codes(self, **kwargs):
        return {issue.code for issue in check_coordination(self.root, **kwargs)}

    def snapshot(self):
        return {path.relative_to(self.base): path.read_bytes()
                for path in self.base.rglob("*") if path.is_file()}

    def test_healthy_check_is_read_only(self):
        before = self.snapshot()
        self.assertEqual([], check_coordination(self.root))
        self.assertEqual(before, self.snapshot())

    def test_absent_link_is_pre_migration_but_explicit_hub_checks(self):
        (self.root / "coordination.json").unlink()
        self.assertEqual([], check_coordination(self.root))
        self.assertEqual([], check_coordination(self.root, self.hub))

    def test_missing_hub_and_malformed_link_or_registry(self):
        self.assertIn("missing-hub", self.codes(hub=self.base / "missing"))
        self.write(self.root / "coordination.json", "{bad")
        self.assertIn("invalid-json", self.codes())
        self.write(self.root / "coordination.json", json.dumps({"schema": "wrong", "hub": "../GTT coordination"}))
        self.assertIn("invalid-link", self.codes())
        self.write(self.hub / "registry.json", "{bad")
        self.assertIn("invalid-json", self.codes(hub=self.hub))

    def test_duplicate_ownership_and_unregistered_root(self):
        second = dict(self.worker, id="worker2", status="workers/worker2.md")
        self.registry["workers"].append(second)
        self.write(self.hub / "workers/worker2.md", self.status().replace("worker1", "worker2"))
        self.save_registry()
        self.assertIn("duplicate-checkout", self.codes())
        self.assertIn("unregistered-root", self.codes())
        second["checkout"] = str((self.base / "other").resolve())
        self.worker["checkout"] = str((self.base / "third").resolve())
        self.save_registry()
        self.assertIn("unregistered-root", self.codes())

    def test_root_dependent_relocation(self):
        moved = self.base / "moved-checkout"
        moved.mkdir()
        self.assertIn("unregistered-root", {i.code for i in check_coordination(moved, self.hub, False)})
        self.worker["checkout"] = str(moved.resolve())
        self.save_registry()
        self.assertEqual([], check_coordination(moved, self.hub, False))

    def test_path_escape_and_missing_target(self):
        self.worker["status"] = "../outside.md"
        self.save_registry()
        self.assertIn("status-escape", self.codes())
        self.worker["status"] = "workers/worker1.md"
        self.save_registry()
        self.write(self.hub / "TODO.md", "[Escape](../../outside.md)\n")
        self.assertIn("link-escape", self.codes())
        self.write(self.hub / "TODO.md", "[Missing](missing.md)\n")
        self.assertIn("broken-link", self.codes())

    def test_status_symlink_escape(self):
        link = self.hub / "workers/escape.md"
        try:
            link.symlink_to(self.root / "CODEX.md")
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable on this host")
        self.worker["status"] = "workers/escape.md"
        self.save_registry()
        self.assertIn("status-escape", self.codes())

    def test_workers_directory_escape_even_when_status_stays_beneath_it(self):
        workers = self.hub / "workers"
        original_within = _within

        def fake_within(path, directory):
            if path == workers and directory == self.hub:
                return False
            return original_within(path, directory)

        with patch("tools.check_coordination._within", side_effect=fake_within):
            self.assertIn("workers-escape", self.codes())
            self.assertIn("status-escape", self.codes())

    def test_checkout_must_exist_and_cannot_contain_hub(self):
        self.worker["checkout"] = str(self.base / "missing")
        self.save_registry()
        self.assertIn("missing-checkout", self.codes())
        self.worker["checkout"] = str(self.base.resolve())
        self.save_registry()
        self.assertIn("hub-inside-checkout", self.codes())

    def test_explicit_hub_must_match_valid_link(self):
        another = self.base / "other-hub"
        another.mkdir()
        self.assertIn("hub-mismatch", self.codes(hub=another))
        self.assertNotIn("hub-mismatch", self.codes(hub=self.hub))

    def test_null_paths_and_bounded_json(self):
        self.worker["status"] = "workers/bad\x00.md"
        self.save_registry()
        self.assertIn("invalid-status-path", self.codes())
        self.worker["status"] = "workers/worker1.md"
        self.worker["checkout"] = str(self.root) + "\x00"
        self.save_registry()
        self.assertIn("invalid-checkout", self.codes())
        self.worker["checkout"] = str(self.root)
        self.save_registry()
        self.write(self.root / "coordination.json", json.dumps({"schema": "gtt_coordination_link_v1", "hub": "bad\x00"}))
        self.assertIn("invalid-link", self.codes())
        self.assertIn("invalid-hub", self.codes(hub=Path("bad\x00")))
        self.write(self.root / "coordination.json", " " * 4_001)
        self.assertIn("oversize-file", self.codes(hub=self.hub))
        self.write(self.hub / "registry.json", " " * 40_001)
        self.assertIn("oversize-file", self.codes(hub=self.hub))

    def test_links_into_registered_checkout_and_optional_hub_documents(self):
        other = self.base / "worker2 GTT"
        self.write(other / "docs/optimizer-evidence/README.md", "# Evidence\n")
        self.registry["workers"].append({
            "id": "worker2", "checkout": str(other.resolve()),
            "branch": "codex/optimizer-polish", "status": "workers/worker2.md",
            "thread_id": "thread-2", "title": "Second worker",
        })
        self.save_registry()
        self.write(self.hub / "workers/worker2.md", self.status().replace("worker1", "worker2"))
        target = "../../worker2%20GTT/docs/optimizer-evidence/README.md"
        self.write(self.hub / "workers/worker1.md", self.status(extra=f"[Evidence]({target})\n"))
        self.write(self.hub / "DECISIONS.md", f"[Evidence](../worker2%20GTT/docs/optimizer-evidence/README.md)\n")
        self.write(self.hub / "GIT_POLICY.md", "[Queue](TODO.md)\n")
        self.write(self.hub / "GIT_JOURNAL.md", "[Policy](GIT_POLICY.md)\n")
        self.write(self.hub / "archive/MIGRATION.md", "[Queue](../TODO.md)\n")
        self.assertEqual([], check_coordination(self.root))
        self.write(self.hub / "archive/MIGRATION.md", "[Missing](../missing.md)\n")
        self.assertIn("broken-link", self.codes())
        self.write(self.hub / "GIT_POLICY.md", "[Missing](missing.md)\n")
        self.assertIn("broken-link", self.codes())
        self.write(self.hub / "GIT_JOURNAL.md", "x" * 20_001)
        self.assertIn("oversize-file", self.codes())

    def test_existing_link_outside_hub_and_registry_is_rejected(self):
        self.write(self.base / "outsider/readme.md", "# Outside\n")
        self.write(self.hub / "DECISIONS.md", "[Outside](../outsider/readme.md)\n")
        self.assertIn("link-escape", self.codes())

    def test_invalid_status_and_false_acceptance(self):
        self.write(self.hub / "workers/worker1.md", self.status("unknown"))
        self.assertIn("status-integration", self.codes())
        self.write(self.hub / "workers/worker1.md", self.status("accepted_on_master"))
        self.assertIn("false-acceptance", self.codes())
        self.write(self.hub / "workers/worker1.md", self.status("branch_work", "- Accepted commit: `" + "a" * 40 + "`\n"))
        self.assertIn("false-acceptance", self.codes())
        self.write(self.hub / "workers/worker1.md", self.status("accepted_on_master", "- Accepted commit: `" + "a" * 40 + "`\n- Evidence: reviewed\n"))
        self.assertEqual([], check_coordination(self.root))

    def test_old_route_duplication(self):
        self.write(self.root / "TODO.md", "- [ ] old work\n")
        self.assertIn("missing-route", self.codes())
        self.assertIn("duplicate-queue", self.codes())
        self.assertNotIn("duplicate-queue", self.codes(check_routes=False))


if __name__ == "__main__":
    unittest.main()
