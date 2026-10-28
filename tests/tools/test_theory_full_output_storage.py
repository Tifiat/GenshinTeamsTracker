from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from tools.experiments.gcsim.theory_full_output.storage import cleanup_public_exports
from tools.experiments.gcsim.theory_full_output.prepare import _job_paths


class RetainedPublicLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.receipt = {"schema_kind": "gtt_theory_real_full_output_validation_v1", "retained_public_files": []}
        for name in ("first-snapshot.json.gz", "full-table.csv"):
            body = (name + " public bytes").encode()
            (self.root / name).write_bytes(body)
            self.receipt["retained_public_files"].append(
                {"path": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})
        (self.root / "initial.json").write_text("pins")
        (self.root / "validation-01.json").write_text("receipt")
        (self.root / "foreign.csv").write_text("preserve")

    def test_no_acceptance_preserves_everything(self):
        with self.assertRaisesRegex(ValueError, "acceptance"):
            cleanup_public_exports(self.root, self.receipt)
        self.assertTrue((self.root / "first-snapshot.json.gz").exists())

    def test_exact_cleanup_preserves_receipts_pins_and_unowned_files(self):
        result = cleanup_public_exports(self.root, self.receipt, accepted_or_consolidated=True)
        self.assertEqual(result["removed_files"], 2)
        self.assertFalse((self.root / "full-table.csv").exists())
        for name in ("initial.json", "validation-01.json", "foreign.csv"):
            self.assertTrue((self.root / name).exists())

    def test_changed_late_member_blocks_all_deletion(self):
        (self.root / "full-table.csv").write_text("changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            cleanup_public_exports(self.root, self.receipt, accepted_or_consolidated=True)
        self.assertTrue((self.root / "first-snapshot.json.gz").exists())

    def test_escape_and_receipt_names_are_rejected(self):
        for name in ("../outside.csv", "initial.json", "validation-01.json"):
            self.receipt["retained_public_files"][-1]["path"] = name
            with self.assertRaisesRegex(ValueError, "invalid"):
                cleanup_public_exports(self.root, self.receipt, accepted_or_consolidated=True)
            self.assertTrue((self.root / "first-snapshot.json.gz").exists())

    def test_duplicate_blocks_all_deletion(self):
        self.receipt["retained_public_files"].append(self.receipt["retained_public_files"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            cleanup_public_exports(self.root, self.receipt, accepted_or_consolidated=True)
        self.assertTrue((self.root / "first-snapshot.json.gz").exists())


class ManagedPreparationPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve()
        for name in ("hoyolab_export", "run_workspace"):
            (self.repo / name).mkdir()
        self.job = self.repo / ".codex_tmp/theory-full-output" / ("job-" + "1" * 32)
        self.assembly = self.job / "assembly"
        self.assembly.mkdir(parents=True)
        for name in ("hoyolab_export/paths.py", "run_workspace/gcsim/optimizer_go_inputs.py",
                     "run_workspace/gcsim/optimizer_go_all_sources.py"):
            path = self.assembly / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        self.lease = self.job.parent / ".theory-release.lease"
        self.lease.write_text("1" * 32 + "\n", encoding="ascii", newline="")

    def test_actual_managed_hex_job_and_lease_are_accepted(self):
        paths = _job_paths(assembly_arg=self.assembly, repo_arg=self.repo, job_arg=self.job)
        self.assertEqual(paths, (self.assembly, self.repo, self.job))

    def test_wrong_lease_and_extra_scratch_member_are_rejected(self):
        self.lease.write_text("2" * 32 + "\n", encoding="ascii", newline="")
        with self.assertRaisesRegex(ValueError, "lease"):
            _job_paths(assembly_arg=self.assembly, repo_arg=self.repo, job_arg=self.job)
        self.lease.write_text("1" * 32 + "\n", encoding="ascii", newline="")
        (self.job.parent / "foreign").touch()
        with self.assertRaisesRegex(ValueError, "members"):
            _job_paths(assembly_arg=self.assembly, repo_arg=self.repo, job_arg=self.job)

    def test_repository_and_outside_assembly_are_rejected(self):
        for assembly in (self.repo, self.repo / "run_workspace"):
            with self.assertRaises(ValueError):
                _job_paths(assembly_arg=assembly, repo_arg=self.repo, job_arg=self.job)


if __name__ == "__main__":
    unittest.main()
