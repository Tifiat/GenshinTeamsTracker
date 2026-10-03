"""Temporary promotion-gate controls; no actual engine or account mutation.

The managed runner owns staged-directory cleanup; these tests pin restoration
and preservation at the explicit integration gate owned by GP-3.
"""
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from run_workspace.gcsim.engine_store import GcsimEngineManifest, GcsimEngineStore
from tools.experiments.gcsim.parametric_effects import install_neutral as gate


class NeutralInstallTests(unittest.TestCase):
    def test_application_gate_keeps_actual_source_generator_evidence(self):
        report = SimpleNamespace(to_dict=lambda: {"engine_id": "candidate"})
        for metadata, expected in (({}, (False, False)),
            ({"source_manifest_required": "true", "source_manifest_ready": "false"}, (True, False)),
            ({"source_manifest_required": "true", "source_manifest_ready": "true"}, (True, True))):
            result = gate.application_build_report(report, metadata)
            self.assertEqual((result.source_manifest_required, result.source_manifest_ready), expected)
            self.assertEqual(result.engine_id, "candidate")

    def test_delta_keeps_original_and_omits_unchanged_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            a.mkdir(); b.mkdir()
            (a / "same.go").write_text("same\n")
            (b / "same.go").write_text("same\n")
            (b / "new.go").write_text("new\n")
            value = gate.export_delta(a, b, ["same.go", "new.go"])
            self.assertNotIn("same.go", value)
            self.assertIn("--- /dev/null", value)
            self.assertEqual((a / "same.go").read_text(), "same\n")

    def test_overlay_relocation_rejects_foreign_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "build").mkdir()
            (root / "source.go").write_bytes(b"source")
            (root / "build/gtt-source-overlay.json").write_text(json.dumps({"Replace": {str(root / "source.go"): str(root.parent / "outside.go")}}))
            with self.assertRaises(ValueError):
                gate.relocate_overlay(root, root)

    def test_delta_deletes_removed_source_instead_of_leaving_invalid_empty_go_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before, after = root / "before", root / "after"
            before.mkdir(); after.mkdir()
            (before / "obsolete.go").write_text("package old\n", encoding="utf-8")
            (before / "empty.go").write_text("", encoding="utf-8")
            (after / "new-empty.go").write_text("", encoding="utf-8")
            delta = gate.export_delta(before, after, ["obsolete.go", "empty.go", "new-empty.go"])
            self.assertIn("deleted file mode 100644", delta)
            self.assertIn("+++ /dev/null", delta)
            patch_file = root / "delta.patch"
            patch_file.write_text(delta, encoding="utf-8", newline="\n")
            subprocess.run(["git", "apply", str(patch_file)], cwd=before, check=True, capture_output=True)
            self.assertFalse((before / "obsolete.go").exists())
            self.assertFalse((before / "empty.go").exists())
            self.assertTrue((before / "new-empty.go").is_file())

    def test_relocated_capture_comparison_keeps_gate_and_reports_bounded_paths(self):
        from tools.experiments.gcsim.parametric_effects.repair_hit_identity import require_identical_capture
        require_identical_capture({'nodes': [{'node_id': 1}]}, {'nodes': [{'node_id': 1}]})
        with self.assertRaisesRegex(ValueError, r'\$\.nodes\[0\]\.node_id: 1 -> 2'):
            require_identical_capture({'nodes': [{'node_id': 1}]}, {'nodes': [{'node_id': 2}]})
        for before, after, diagnostic in (({'seed': 1}, {}, '<missing>'),
            ({'nodes': []}, {'nodes': [1]}, 'length: 0 -> 1'),
            ({'seed': 1}, {'seed': True}, '1 -> True')):
            with self.subTest(diagnostic=diagnostic), self.assertRaisesRegex(ValueError, diagnostic):
                require_identical_capture(before, after)
        with self.assertRaises(ValueError) as caught:
            require_identical_capture(list(range(100)), [100] * 100)
        self.assertEqual(str(caught.exception).count(' -> '), 8)

    def test_promotion_success_and_failed_activation_restore_visible_bundle(self):
        for fail, replacing in ((False, False), (True, False), (False, True), (True, True), ("capture", True)):
            with self.subTest(fail=fail, replacing=replacing), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                store = GcsimEngineStore(root / "store")
                store.engines_dir.mkdir(parents=True)
                before = b'{"schema_version":1,"active_engine_id":"original","rollback_engine_id":null}'
                store.active_state_path.write_bytes(before)
                production = root / "run_workspace/gcsim/patch_stack"
                production.mkdir(parents=True)
                (production / "existing.patch").write_bytes(b"preserved")
                job = root / "job"; job.mkdir()
                candidate = job / "candidate"; (candidate / "build").mkdir(parents=True)
                (candidate / "build/gtt-gcsim.exe").write_bytes(b"engine")
                (candidate / "source.go").write_bytes(b"source")
                (candidate / "build/gtt-source-overlay.json").write_text(json.dumps({"Replace": {str(candidate / "source.go"): str(candidate / "source.go")}}))
                manifest = GcsimEngineManifest(engine_id="candidate", source_label="synthetic", source_path=str(candidate),
                    source_tree_hash="a"*64, engine_tree_hash="b"*64, prepared_at_utc="2026-09-26T00:00:00Z", patch_backend="test", patch_count=1)
                (candidate / "gtt_engine_manifest.json").write_text(json.dumps(asdict(manifest)))
                consumer, old_consumer, delta = job / "new.exe", root / "old.exe", job / "delta.patch"
                consumer.write_bytes(b"new"); old_consumer.write_bytes(b"old"); delta.write_bytes(b"patch")
                expected = {"pointer": gate.sha(store.active_state_path), "consumer": gate.sha(old_consumer)}
                if replacing:
                    (production / gate.PATCH_NAME).write_bytes(b"old observer patch")
                    expected["patch"] = gate.sha(production / gate.PATCH_NAME)
                activate = store.activate_engine
                def activation(engine_id):
                    result = activate(engine_id)
                    if fail is True:
                        raise RuntimeError("injected failure after pointer change")
                    return result
                def check_installed(destination):
                    if fail == "capture":
                        raise RuntimeError("injected failure after pointer change")
                with patch.object(gate, "ROOT", root), patch.object(gate, "CONSUMER", old_consumer), patch.object(store, "activate_engine", side_effect=activation), patch(
                    "run_workspace.gcsim.optimizer_engine_context.load_active_gcsim_optimizer_engine_context",
                    return_value=SimpleNamespace(artifact_sha256=gate.sha(candidate / "build/gtt-gcsim.exe"))):
                    if fail:
                        with self.assertRaisesRegex(RuntimeError, "injected failure"):
                            gate.promote(store, candidate, consumer, delta, job, expected, verify_installed=check_installed)
                        self.assertEqual(store.active_state_path.read_bytes(), before)
                        self.assertEqual(old_consumer.read_bytes(), b"old")
                        self.assertTrue(candidate.is_dir())
                        self.assertFalse((store.engines_dir / "candidate").exists())
                        if replacing:
                            self.assertEqual((production / gate.PATCH_NAME).read_bytes(), b"old observer patch")
                        else:
                            self.assertFalse((production / gate.PATCH_NAME).exists())
                    else:
                        destination = gate.promote(store, candidate, consumer, delta, job, expected)
                        self.assertTrue(destination.is_dir())
                        self.assertFalse(candidate.exists())
                        self.assertEqual(store.rollback_engine_id(), "original")
                        self.assertEqual(old_consumer.read_bytes(), b"new")
                        self.assertEqual((production / gate.PATCH_NAME).read_bytes(), b"patch")
                self.assertEqual((production / "existing.patch").read_bytes(), b"preserved")


if __name__ == "__main__":
    unittest.main()
