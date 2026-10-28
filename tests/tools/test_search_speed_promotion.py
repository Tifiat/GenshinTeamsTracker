"""Cheap contracts for the post-matrix product-adapter promotion gate."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools.experiments.gcsim.search_hypotheses import promotion_gate as gate
from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256
from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsRequest
from run_workspace.gcsim.optimizer_go_selected import _write_canonical


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def row():
    return {"group": "set", "rank": 1, "dps": 123.0, "ids": [("owner", "flower", 1)]}


class PromotionGateTests(unittest.TestCase):
    def test_default_all_sets_request_uses_actual_installed_consumer(self):
        request = GcsimOptimizerGoAllSetsRequest(
            db_path="unused", selected_team={}, team_index=0, rotation_shell_text="",
            product_timeout_ms=0)
        self.assertEqual(Path(request.optimizer_binary_path).resolve(), gate.INSTALLED.resolve())

    def test_file_request_hash_and_adapter_request_hash_are_distinct(self):
        request = {"schema_version": 1, "artifacts": [{"id": 2}, {"id": 1}]}
        with tempfile.TemporaryDirectory() as raw:
            work = Path(raw)
            _write_canonical(work / "expected.json", request)
            file_sha = digest(work / "expected.json")
            source = b'{"source":"active"}\n'
            source_sha = hashlib.sha256(source).hexdigest()
            class FakeSession:
                def _prepare_formula_inputs(self, *, prepared, run_dir, started):
                    self_prepared = prepared
                    assert self_prepared == {"request": request} and started > 0
                    (run_dir / "set-sources.json").write_bytes(source)
            gate.prepare_reused_input(work, request, FakeSession(),
                                      request_sha=file_sha, sources_sha=source_sha)
            adapter = gate.adapter_prepared({"request": request})
            self.assertEqual(adapter["request_sha256"], canonical_sha256(request))
            self.assertNotEqual(adapter["request_sha256"], file_sha)
            self.assertEqual(digest(work / "request.json"), file_sha)

    def test_reference_requires_pass_matching_variant_and_complete_candidate(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "accepted.json"
            candidate = {"name": "player_safe_wide", "legal_output_checked": True,
                         "rows": [row() for _ in range(49)], "leaders": [row()],
                         "captures": {"context/seed": {"canonical_sha256": "same"}},
                         "warnings": [], "search_seconds": 1.0}
            reference = {"status": "paired_formula_gate_pass", "variant": "player_safe_wide",
                         "installed_unchanged": True, "active_pointer_unchanged": True,
                         "engine_unchanged": True, "common_captures_equal": True,
                         "comparison": {"regressions": []},
                         "capture_key_difference": {"baseline_only": [], "candidate_only": []},
                         "case": "case", "request_sha256": "request", "sources_sha256": "sources",
                         "engine_sha256": "engine", "installed_sha256": "installed",
                         "manifest_sha256": "manifest", "source_sha256": "source",
                         "request": {"engine": {}}, "runs": [candidate]}
            path.write_text(json.dumps(reference), encoding="utf-8")
            with patch.object(gate, "EVIDENCE_ROOT", root):
                accepted = gate.accepted_reference(path, "player_safe_wide")[2]
                self.assertEqual(accepted["name"], candidate["name"])
                self.assertEqual(len(accepted["rows"]), 49)
                with self.assertRaisesRegex(ValueError, "variant"):
                    gate.accepted_reference(path, "player_refine_one")
                reference["status"] = "quality_regression"
                path.write_text(json.dumps(reference), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "accepted"):
                    gate.accepted_reference(path, "player_safe_wide")
                reference["status"] = "paired_formula_gate_pass"
                candidate["rows"].pop()
                path.write_text(json.dumps(reference), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "49-row"):
                    gate.accepted_reference(path, "player_safe_wide")

    def test_exact_rows_warnings_and_canonical_capture_keys_are_mandatory(self):
        baseline = {"rows": [row() for _ in range(49)], "leaders": [row()],
                    "warnings": ["warning"], "search_seconds": 2.0,
                    "captures": {"context/seed": {"canonical_sha256": "same", "member_sha256": "a"}}}
        candidate = {**baseline, "search_seconds": 1.0,
                     "captures": {"context/seed": {"canonical_sha256": "same", "member_sha256": "b"}}}
        passed = gate.parity(baseline, candidate)
        self.assertTrue(passed["passed"])
        self.assertFalse(passed["raw_captures_equal"])
        self.assertFalse(gate.parity(baseline, {**candidate, "warnings": []})["passed"])
        self.assertFalse(gate.parity(baseline, {**candidate, "captures": {}})["passed"])
        self.assertFalse(gate.parity(baseline, {**candidate, "rows": [row() for _ in range(48)]})["passed"])

    def test_algebraic_capture_needs_exact_49_rows(self):
        baseline = {"rows": [row() for _ in range(49)], "leaders": [row()],
                    "warnings": [], "search_seconds": 2.0,
                    "captures": {"context/seed": {"canonical_sha256": "old",
                                                   "independent_status_sha256_v1": "old",
                                                   "independent_status_constant_fold_sha256_v1": "old",
                                                   "algebraic_capture_sha256_v1": "same"}}}
        candidate = {**baseline, "search_seconds": 1.0,
                     "captures": {"context/seed": {"canonical_sha256": "new",
                                                    "independent_status_sha256_v1": "new",
                                                    "independent_status_constant_fold_sha256_v1": "new",
                                                    "algebraic_capture_sha256_v1": "same"}}}
        accepted = gate.parity(baseline, candidate)
        self.assertTrue(accepted["passed"])
        self.assertEqual({"context/seed": "algebraic"}, accepted["capture_comparison_kinds"])
        self.assertFalse(gate.parity(baseline, {**candidate, "rows": [row() for _ in range(48)]})["passed"])
        self.assertFalse(gate.parity({**baseline, "rows": [row() for _ in range(48)]},
                                     {**candidate, "rows": [row() for _ in range(48)]})["passed"])

    def test_install_needs_parent_attestation_and_rolls_back_on_postcheck(self):
        with self.assertRaisesRegex(ValueError, "parent approval"):
            gate.require_install_approval(install=True, parent_approved=False)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            native, job = root / "native", root / "job"
            native.mkdir()
            job.mkdir()
            installed, candidate = native / "installed.exe", job / "candidate.exe"
            installed.write_bytes(b"old")
            candidate.write_bytes(b"new")
            after = Mock(side_effect=ValueError("late identity mismatch"))
            with self.assertRaisesRegex(ValueError, "late identity mismatch"):
                gate.install_candidate(candidate, installed, job,
                                       old_sha=digest(installed), candidate_sha=digest(candidate),
                                       verify_after=after)
            after.assert_called_once()
            self.assertEqual(installed.read_bytes(), b"old")
            self.assertEqual(candidate.read_bytes(), b"new")
            self.assertFalse((job / "optimizer-promotion-stage.exe").exists())
            self.assertEqual(list(native.iterdir()), [installed])
            with self.assertRaisesRegex(ValueError, "changed"):
                gate.install_candidate(candidate, installed, job,
                                       old_sha="wrong", candidate_sha=digest(candidate))
            self.assertEqual(installed.read_bytes(), b"old")

    def test_postinstall_default_path_runs_fresh_process_on_only_frozen_inputs(self):
        with tempfile.TemporaryDirectory() as raw:
            job = Path(raw)
            installed = job / "installed.exe"
            installed.write_bytes(b"candidate")
            source = job / "adapter"
            source.mkdir()
            (source / "request.json").write_bytes(b'{"frozen":true}\n')
            (source / "set-sources.json").write_bytes(b'{"source":"current"}\n')
            (source / "finish-requested").write_text("old finish", encoding="utf-8")
            reference = {"request": {"frozen": True},
                         "request_sha256": digest(source / "request.json"),
                         "sources_sha256": digest(source / "set-sources.json")}
            candidate_run = {"rows": [row() for _ in range(49)], "leaders": [row()],
                             "warnings": [], "search_seconds": 1.0,
                             "captures": {"context/seed": {"canonical_sha256": "same"}},
                             "legal_output_checked": True}
            calls = []
            class FakeSession:
                def __init__(self, request, *, cache_dir):
                    self.request = request
                    self.cache_dir = cache_dir
                def _validate_optimizer_request(self, *, run_dir, started):
                    calls.append("preflight")
                    self.assert_inputs(run_dir)
                def _run_go_optimizer(self, *, prepared, compact, run_dir, started):
                    calls.append("process")
                    self.assert_inputs(run_dir)
                    self.assertEqual(prepared["request_sha256"], canonical_sha256(reference["request"]))
                    (run_dir / "verification").mkdir()
                    (run_dir / "optimizer-output.json").write_text("{}", encoding="utf-8")
                def assert_inputs(self, run_dir):
                    self.assertEqual(Path(self.request.optimizer_binary_path).resolve(), installed.resolve())
                    self.assertEqual(digest(run_dir / "request.json"), reference["request_sha256"])
                    self.assertEqual(digest(run_dir / "set-sources.json"), reference["sources_sha256"])
                    self.assertFalse((run_dir / "finish-requested").exists())
                    self.assertFalse((run_dir / "optimizer-output.json").exists())
            # Bind assertions to the test, not to the fake adapter instance.
            FakeSession.assertEqual = self.assertEqual
            FakeSession.assertFalse = self.assertFalse
            with patch.object(gate, "INSTALLED", installed), \
                 patch.object(gate, "adapter_request", return_value=SimpleNamespace(
                     optimizer_binary_path=str(installed), product_timeout_ms=0)) as request_mock, \
                 patch.object(gate, "CandidateSession", FakeSession), \
                 patch.object(gate, "summarize", return_value=candidate_run), \
                 patch.object(gate, "captures", return_value=candidate_run["captures"]):
                result = gate.postinstall_default_run(job, reference, candidate_run, source)
            request_mock.assert_called_once_with(job, reference, None)
            self.assertEqual(calls, ["preflight", "process"])
            self.assertTrue(result["parity_to_preinstall"]["passed"])
            self.assertEqual(result["optimizer_binary_path"], str(installed.resolve()))
            self.assertEqual(result["optimizer_sha256"], digest(installed))

    def test_postinstall_parity_failure_rolls_back_installed_bytes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            native, job = root / "native", root / "job"
            native.mkdir()
            job.mkdir()
            installed, candidate = native / "installed.exe", job / "candidate.exe"
            installed.write_bytes(b"old")
            candidate.write_bytes(b"new")
            old_sha, candidate_sha = digest(installed), digest(candidate)
            def verify_after():
                self.assertEqual(installed.read_bytes(), b"new")
                gate.require_postinstall_parity({"parity_to_preinstall": {
                    "passed": False, "reasons": ["canonical_capture_keys_or_hashes_differ"]}})
            with self.assertRaisesRegex(ValueError, "default-path run differs"):
                gate.install_candidate(candidate, installed, job, old_sha=old_sha,
                                       candidate_sha=candidate_sha, verify_after=verify_after)
            self.assertEqual(digest(installed), old_sha)
            self.assertFalse((job / "optimizer-promotion-stage.exe").exists())

    def test_install_keeps_old_file_when_replace_fails_and_rolls_back_bad_hash(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            native, job = root / "native", root / "job"
            native.mkdir()
            job.mkdir()
            installed, candidate = native / "installed.exe", job / "candidate.exe"
            installed.write_bytes(b"old")
            candidate.write_bytes(b"new")
            old_sha, new_sha = digest(installed), digest(candidate)
            with patch.object(gate.os, "replace", side_effect=OSError("replace denied")):
                with self.assertRaisesRegex(OSError, "replace denied"):
                    gate.install_candidate(candidate, installed, job,
                                           old_sha=old_sha, candidate_sha=new_sha)
            self.assertEqual(digest(installed), old_sha)
            self.assertEqual(list(native.iterdir()), [installed])
            self.assertFalse((job / "optimizer-promotion-stage.exe").exists())
            real_sha = gate.sha
            misread_once = False
            def sha_with_bad_new_install(path):
                nonlocal misread_once
                if Path(path) == installed and installed.read_bytes() == b"new" and not misread_once:
                    misread_once = True
                    return "bad-installed-hash"
                return real_sha(path)
            with patch.object(gate, "sha", side_effect=sha_with_bad_new_install):
                with self.assertRaisesRegex(ValueError, "Installed optimizer hash"):
                    gate.install_candidate(candidate, installed, job,
                                           old_sha=old_sha, candidate_sha=new_sha)
            self.assertTrue(misread_once)
            self.assertEqual(digest(installed), old_sha)
            self.assertEqual(list(native.iterdir()), [installed])
            self.assertFalse((job / "optimizer-promotion-stage.exe").exists())

    def test_receipt_is_bounded_new_evidence_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            job = root / "job"
            job.mkdir()
            evidence = root / "evidence"
            evidence.mkdir()
            child = evidence / "promotion"
            child.mkdir()
            path = child / "new.json"
            with patch.object(gate, "EVIDENCE_ROOT", evidence), patch(
                "tools.experiments.gcsim.search_hypotheses.matrix_pair.EVIDENCE_ROOT", evidence
            ):
                self.assertEqual(gate.receipt_path(path), path)
                with self.assertRaisesRegex(ValueError, "inside"):
                    gate.receipt_path(root / "outside.json")
                gate.save_receipt(path, job, {"status": "preparing"}, first=True)
                with self.assertRaisesRegex(ValueError, "new"):
                    gate.receipt_path(path)
                with self.assertRaises(FileExistsError):
                    gate.save_receipt(path, job, {"status": "other"}, first=True)
                self.assertEqual(json.loads(path.read_text())["status"], "preparing")
                self.assertTrue(job.exists())  # Managed wrapper, not this helper, owns cleanup.


if __name__ == "__main__":
    unittest.main()
