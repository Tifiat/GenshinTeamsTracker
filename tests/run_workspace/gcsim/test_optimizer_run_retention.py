from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from run_workspace.gcsim.optimizer_run_retention import (
    RUN_LEASE, RUN_PIN, prune_go_optimizer_runs, run_directory_lease,
)
from run_workspace.gcsim.optimizer_go_selected import (
    GcsimOptimizerGoSelectedRequest, GcsimOptimizerGoSelectedSession,
    GcsimOptimizerGoSelectedError,
)
from run_workspace.gcsim.optimizer_go_all import (
    GcsimOptimizerGoAllSetsRequest, GcsimOptimizerGoAllSetsSession,
)
from run_workspace.gcsim.optimizer_go_theory import (
    GcsimOptimizerGoTheoryRequest, GcsimOptimizerGoTheorySession,
)


def completed(root: Path, name: str, timestamp: int) -> Path:
    path = root / name
    path.mkdir()
    result_name = "theory-result.json" if name.startswith("theory-") else "selected-result.json"
    (path / result_name).write_text("{}", encoding="utf-8")
    (path / "large.bin").write_bytes(b"x" * 128)
    os.utime(path, (timestamp, timestamp))
    return path


class OptimizerRunRetentionTest(unittest.TestCase):
    def test_preview_then_apply_counts_bytes_preserves_newest_and_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = completed(root, "selected-old", 100)
            new = completed(root, "all_sets-new", 200)
            unknown = completed(root, "user-evidence", 50)
            preview = prune_go_optimizer_runs(root, keep_count=1, max_bytes=1)
            self.assertEqual(preview["deleted_paths"], [str(old)])
            self.assertTrue(old.exists())
            self.assertTrue(preview["over_budget_bytes"] > 0)
            applied = prune_go_optimizer_runs(root, keep_count=1, max_bytes=1, dry_run=False)
            self.assertEqual(applied["deleted_bytes"], 130)
            self.assertFalse(old.exists())
            self.assertTrue(new.exists())
            self.assertTrue(unknown.exists())

    def test_active_and_pinned_runs_survive_zero_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = completed(root, "selected-active", 100)
            pinned = completed(root, "all_sets-pinned", 200)
            stale = completed(root, "selected-stale", 50)
            (pinned / RUN_PIN).write_text("manual diagnostic pin", encoding="utf-8")
            with run_directory_lease(active):
                report = prune_go_optimizer_runs(root, keep_count=0, max_bytes=0, dry_run=False)
            self.assertEqual(set(report["protected_paths"]), {str(active), str(pinned)})
            self.assertFalse(stale.exists())
            (pinned / RUN_PIN).unlink()
            prune_go_optimizer_runs(root, keep_count=0, max_bytes=0, dry_run=False)
            self.assertFalse(active.exists())
            self.assertFalse(pinned.exists())

    def test_current_result_consumes_budget_without_retaining_an_extra_oversize_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = completed(root, "selected-old", 100)
            new = completed(root, "selected-new", 200)
            result = prune_go_optimizer_runs(root, protected_paths=(new,), max_bytes=1, dry_run=False)
            self.assertFalse(old.exists())
            self.assertTrue(new.exists())
            self.assertEqual(result["kept_paths"], [])

    def test_completed_theory_runs_use_the_shared_retention_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            theory = completed(root, "theory-old", 100)
            result = prune_go_optimizer_runs(
                root, keep_count=0, max_bytes=0, dry_run=False
            )
            self.assertEqual(result["deleted_paths"], [str(theory)])
            self.assertFalse(theory.exists())

    def test_live_unknown_and_outside_links_are_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs"
            root.mkdir()
            unknown = root / "selected-not-yet-leased"
            unknown.mkdir()
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / "precious.txt").write_text("keep", encoding="utf-8")
            link = root / "selected-link"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError:
                link = None
            result = prune_go_optimizer_runs(root, keep_count=0, dry_run=False)
            self.assertTrue(unknown.exists())
            self.assertTrue((outside / "precious.txt").exists())
            if link is not None:
                self.assertIn(str(link), result["skipped_paths"])

    def test_failure_is_reported_and_does_not_delete_other_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = completed(root, "selected-old", 100)
            with patch("run_workspace.gcsim.optimizer_run_retention.shutil.rmtree", side_effect=PermissionError("busy")):
                result = prune_go_optimizer_runs(root, keep_count=0, dry_run=False)
            self.assertEqual(result["status"], "partial_failure")
            self.assertTrue(old.exists())

    def test_both_real_session_entrypoints_cleanup_after_success_failure_and_cancel(self):
        for request_type, session_type in (
            (GcsimOptimizerGoSelectedRequest, GcsimOptimizerGoSelectedSession),
            (GcsimOptimizerGoAllSetsRequest, GcsimOptimizerGoAllSetsSession),
            (GcsimOptimizerGoTheoryRequest, GcsimOptimizerGoTheorySession),
        ):
            for outcome in ("success", "failed", "cancelled"):
                with self.subTest(mode=session_type.run_mode, outcome=outcome), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    old = completed(root, "selected-old", 100)
                    request = request_type(db_path="unused", selected_team={}, team_index=0,
                                           rotation_shell_text="", run_root=tmp)
                    session = session_type(request)
                    original = prune_go_optimizer_runs

                    def bounded_cleanup(root, run_dir):
                        return original(root, protected_paths=(run_dir,), keep_count=0, dry_run=False)

                    failure = None if outcome == "success" else GcsimOptimizerGoSelectedError(outcome, "expected")
                    with patch("run_workspace.gcsim.optimizer_go_selected._prepare_inputs", return_value={"request_sha256": "hash"}, side_effect=failure), \
                         patch.object(session, "_validate_optimizer_request"), \
                         patch.object(session, "_prepare_formula_inputs", return_value={}), \
                         patch.object(session, "_run_go_optimizer", return_value={"measured": {}}), \
                         patch("run_workspace.gcsim.optimizer_go_selected.prune_go_optimizer_runs_best_effort", side_effect=bounded_cleanup):
                        payload = session.run()
                    self.assertEqual(payload["status"], outcome)
                    self.assertFalse(old.exists())
                    current = Path(payload["run_dir"])
                    self.assertTrue(current.exists())
                    self.assertTrue((current / RUN_LEASE).exists())
                    self.assertEqual(json.loads((current / "retention.json").read_text())["deleted_paths"], [str(old)])
                    with run_directory_lease(current):
                        pass  # the session released its OS lease


if __name__ == "__main__":
    unittest.main()
