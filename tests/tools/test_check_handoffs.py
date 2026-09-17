"""Regressions for documentation debt; fixtures never touch app/account state."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.check_handoffs import ROOT_BUDGETS, check_repository


class HandoffChecksTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.owner = "docs/handoff/CURRENT.md"
        for name in ROOT_BUDGETS:
            self.write(name, "# Document\n")
        self.write("AGENTS.md", "Read CODEX.md and docs/handoff/HANDOFF_MAINTENANCE.md.\n")
        self.write("docs/handoff/README.md",
                   "[Protocol](HANDOFF_MAINTENANCE.md)\n[Current](CURRENT.md)\n")
        tick = chr(96)
        self.current = (
            "<!-- handoff-current: optimizer -->\n"
            f"- Active engine: {tick}new-engine{tick}\n"
            f"- Rollback engine: {tick}old-engine{tick}\n"
            f"- Active patch: {tick}patch.diff{tick}\n"
            f"- Patch SHA256: {tick}hash{tick}\n"
            "<!-- /handoff-current -->\n"
        )
        self.write(self.owner, self.current)
        self.manifest = {
            "current_state": {
                "handoff": self.owner,
                "active_engine_id": "new-engine",
                "rollback_engine_id": "old-engine",
                "active_patch": "patch.diff",
                "patch_sha256": "hash",
            },
            "current_next_block": {"resume": self.owner},
            "historical_pilot": {"active_engine_id": "obsolete-engine", "handoff": "gone.md"},
        }
        self.save_manifest()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def save_manifest(self):
        self.write("docs/handoff/state.json", json.dumps(self.manifest))

    def codes(self):
        return {item.code for item in check_repository(self.root)}

    def snapshot(self):
        return {p.relative_to(self.root): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file()}

    def test_healthy_check_is_read_only_and_ignores_historical_projections(self):
        before = self.snapshot()
        self.assertEqual([], check_repository(self.root))
        self.assertEqual(before, self.snapshot())

    def test_new_untracked_diagnostic_must_be_indexed_once(self):
        self.write("docs/handoff/DIAGNOSIS.md", "# Failed response\n")
        self.assertIn("index-coverage", self.codes())
        index = self.root / "docs/handoff/README.md"
        index.write_text(index.read_text() + "[Diagnosis](DIAGNOSIS.md)\n", encoding="utf-8")
        self.assertEqual(set(), self.codes())
        index.write_text(index.read_text() + "[Duplicate](DIAGNOSIS.md)\n", encoding="utf-8")
        self.assertIn("index-coverage", self.codes())

    def test_broken_links_inline_references_and_repo_escape(self):
        tick = chr(96)
        self.write("TODO.md", f"[Missing](missing.md)\n{tick}gone.md{tick}\n"
                   "[Escape](../outside.md)\n")
        self.assertEqual(
            {"broken-link", "broken-doc-reference", "invalid-link"}, self.codes()
        )

    def test_external_fragment_and_encoded_local_links(self):
        self.write("docs/handoff/space name.md", "# Details\n")
        self.write("docs/handoff/README.md",
                   "[Protocol](HANDOFF_MAINTENANCE.md)\n[Current](CURRENT.md)\n"
                   "[Space](space%20name.md#details)\n")
        self.write("TODO.md", "[Here](#todo)\n[External](https://example.org/missing.md)\n")
        self.assertEqual(set(), self.codes())

    def test_invalid_json(self):
        self.write("docs/handoff/state.json", "{")
        self.assertEqual({"invalid-json"}, self.codes())

    def test_live_pointer_and_projection_drift(self):
        self.manifest["current_next_block"]["resume"] = "docs/handoff/gone.md"
        self.manifest["current_state"]["active_engine_id"] = "wrong-engine"
        self.save_manifest()
        self.assertEqual({"current-pointer", "current-projection"}, self.codes())

    def test_non_object_live_section(self):
        self.manifest["current_state"] = None
        self.save_manifest()
        self.assertEqual({"invalid-current"}, self.codes())

    def optimizer_contract(self):
        self.manifest["contract"] = "gcsim_optimizer_trace_equation_cleanup_manifest_v1"
        self.manifest["status"] = "response_failed"
        self.manifest["current_state"]["acceptance_status"] = "response_failed"
        self.manifest["current_next_block"]["name"] = "repair_dependencies"
        self.write(self.owner, self.current.replace(
            "<!-- /handoff-current -->",
            "- Acceptance status: " + chr(96) + "response_failed" + chr(96) + "\n"
            "- Next block: " + chr(96) + "repair_dependencies" + chr(96) + "\n"
            "<!-- /handoff-current -->"))
        self.save_manifest()
        self.assertEqual(set(), self.codes())

    def test_acceptance_and_next_step_cannot_drift_from_owner(self):
        self.optimizer_contract()
        self.manifest["status"] = "old_pass"
        self.manifest["current_state"]["acceptance_status"] = "old_pass"
        self.manifest["current_next_block"]["name"] = "repeat_search"
        self.save_manifest()
        issues = check_repository(self.root)
        self.assertEqual({"current-projection"}, {item.code for item in issues})
        self.assertEqual(2, len(issues))
        self.manifest["status"] = "another_status"
        self.save_manifest()
        self.assertEqual(3, len(check_repository(self.root)))

    def test_required_fields_cannot_be_removed_and_diagnostic_must_exist(self):
        self.optimizer_contract()
        del self.manifest["current_state"]["acceptance_status"]
        self.manifest["current_next_block"]["diagnostic_handoff"] = "missing.md"
        self.save_manifest()
        self.assertEqual(
            {"missing-current-fields", "current-projection", "current-pointer"}, self.codes())

    def test_duplicate_scope(self):
        self.write("docs/handoff/HANDOFF_MAINTENANCE.md", self.current)
        self.assertEqual({"duplicate-current"}, self.codes())

    def test_missing_and_malformed_owner_markers(self):
        self.write(self.owner, "# No owner\n")
        self.assertEqual({"current-owner"}, self.codes())
        self.write(self.owner, self.current.replace("<!-- /handoff-current -->", ""))
        self.assertEqual({"current-markers", "current-owner"}, self.codes())

    def test_current_summary_size(self):
        self.write(self.owner, self.current.replace(
            "<!-- /handoff-current -->", ("word " * 401) + "\n<!-- /handoff-current -->"))
        self.assertEqual({"current-budget"}, self.codes())

    def test_root_bloat_and_completed_todo(self):
        self.write("CODEX.md", "x" * (ROOT_BUDGETS["CODEX.md"] + 1))
        self.write("TODO.md", "- [X] Already implemented\n")
        self.assertEqual({"root-budget", "completed-todo"}, self.codes())

    def test_line_ending_normalization_at_budget(self):
        size = ROOT_BUDGETS["TODO.md"]
        (self.root / "TODO.md").write_bytes(b"x\r\n" * (size // 2))
        self.assertEqual(set(), self.codes())

    def test_fenced_examples_do_not_create_false_debt(self):
        for fence in (chr(96) * 3, "~~~"):
            with self.subTest(fence=fence):
                self.write("TODO.md", fence + "markdown\n- [x] Example\n"
                           "[Missing](gone.md)\n" + self.current + fence + "\n- [ ] Open\n")
                self.assertEqual(set(), self.codes())

    def test_required_entrypoint_and_routing(self):
        (self.root / "AGENTS.md").unlink()
        self.assertEqual({"missing-entrypoint", "missing-routing"}, self.codes())
        self.write("AGENTS.md", "No instructions.\n")
        self.assertEqual({"missing-routing"}, self.codes())


if __name__ == "__main__":
    unittest.main()
