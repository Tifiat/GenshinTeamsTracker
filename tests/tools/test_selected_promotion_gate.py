"""Mock-only Selected source-gate contracts; no engine or optimizer process."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256
from run_workspace.gcsim.optimizer_go_selected import _write_canonical
from run_workspace.gcsim.engine_store import GcsimEngineManifest, MANIFEST_FILE_NAME
from run_workspace.gcsim.source_manifest_build import canonical_json as canonical_source_manifest_json
from tools.experiments.gcsim.search_hypotheses import selected_promotion_gate as gate


def fixture():
    slots = ("flower", "plume", "sands", "goblet", "circlet")
    wearers = [f"actor{i}" for i in range(4)]
    artifacts = []
    assignment = []
    for wearer_index, wearer in enumerate(wearers):
        for slot_index, slot in enumerate(slots):
            ident = wearer_index * 5 + slot_index + 1
            artifacts.append({"artifact_id": ident, "slot": slot, "set_uid": "known"})
            assignment.append({"wearer_key": wearer, "slot": slot, "artifact_id": ident})
    request = {"wearers": [{"wearer_key": w} for w in wearers], "artifacts": artifacts,
               "stochastic": {"seeds": [11, 12]},
               "result_options": {"builds_per_group": 7, "fast_mode": True, "set_group_limit": 1}}
    row = {"rank": 1, "set_group_key": "group", "set_group_rank": 1,
           "alternative_rank": 1, "artifacts": assignment, "formula_dps": "100.000"}
    product = {"request_sha256": canonical_sha256(request), "ranking_basis": "formula",
               "candidates": [row], "winner": assignment, "formula_dps": "100",
               "warnings": ["formula_only_unverified"]}
    return request, {"product_result": product, "verification_policy": "formula_only",
                     "search_elapsed_ms": 2000}


class SelectedPromotionGateTests(unittest.TestCase):
    def test_staging_copies_only_new_request_and_compact_not_old_finish_or_result(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            captured, target = root / "captured", root / "candidate"
            captured.mkdir()
            (captured / "request.json").write_bytes(b'{"request":1}\n')
            (captured / "compact.json").write_bytes(b'{"fresh":true}\n')
            (captured / "finish-requested").write_bytes(b"")
            (captured / "optimizer-output.json").write_bytes(b"old partial result")
            gate.stage_inputs(captured, target)
            self.assertEqual({p.name for p in target.iterdir()}, {"request.json", "compact.json"})
            self.assertEqual((target / "compact.json").read_bytes(), (captured / "compact.json").read_bytes())

    def test_saved_fast_request_is_pinned_and_ordinary_clone_has_new_hash(self):
        request, _ = fixture()
        request["cancellation"] = {"mode": "process_interrupt_v1"}
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "request.json"
            _write_canonical(source, request)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            with patch.object(gate, "SAVED_REQUEST", source), patch.object(gate, "SAVED_REQUEST_SHA256", digest):
                saved = gate.retained_request()
                self.assertEqual(saved, request)
                ordinary = gate.ordinary_request(saved)
                self.assertTrue(saved["result_options"]["fast_mode"])
                self.assertEqual(ordinary["result_options"],
                                 {"builds_per_group": 3, "fast_mode": False, "set_group_limit": 1})
                self.assertNotEqual(canonical_sha256(ordinary), canonical_sha256(saved))
                self.assertNotEqual(canonical_sha256(saved), digest)  # file has a trailing newline
                source.write_bytes(source.read_bytes() + b" ")
                with self.assertRaisesRegex(ValueError, "Pinned Selected request changed"):
                    gate.retained_request()

    def test_fast_parity_checks_exact_legal_ids_and_dps(self):
        request, wrapper = fixture()
        summary = gate.summarize_selected(wrapper, request, ordinary=False)
        self.assertTrue(summary["legal_output_checked"])
        self.assertEqual(len(summary["rows"][0]["ids"]), 20)
        self.assertTrue(gate.exact_fast_parity(summary, json.loads(json.dumps(summary)))["passed"])
        changed = json.loads(json.dumps(summary))
        changed["rows"][0]["formula_dps"] = "99"
        self.assertEqual(gate.exact_fast_parity(summary, changed)["differences"], ["rows"])
        illegal = json.loads(json.dumps(wrapper))
        illegal["product_result"]["candidates"][0]["artifacts"][1]["artifact_id"] = 1
        with self.assertRaisesRegex(ValueError, "legality"):
            gate.summarize_selected(illegal, request, ordinary=False)
        measured_fast = json.loads(json.dumps(wrapper))
        measured_fast["product_result"]["candidates"][0]["measured"] = {
            "iterations": 500, "dps": "99", "standard_error": "1", "engine_result_sha256": "hash"}
        with self.assertRaisesRegex(ValueError, "unexpectedly carries measured"):
            gate.summarize_selected(measured_fast, request, ordinary=False)

    def test_ordinary_requires_actual_n500_result_not_fast_formula(self):
        request, wrapper = fixture()
        ordinary = gate.ordinary_request(request)
        wrapper["product_result"]["request_sha256"] = canonical_sha256(ordinary)
        wrapper["product_result"]["ranking_basis"] = "gcsim"
        wrapper["product_result"]["warnings"] = ["formula_rank_not_measurement_authority"]
        measured = {"iterations": 500, "dps": "99.125", "standard_error": "0.75",
                    "engine_result_sha256": "engine-hash"}
        wrapper["product_result"]["measured"] = dict(measured)
        wrapper["product_result"]["formula_residual"] = "-0.125"
        wrapper["product_result"]["candidates"][0]["measured"] = dict(measured)
        wrapper["product_result"]["candidates"][0]["formula_residual"] = "-0.125"
        wrapper["verification_policy"] = "single_n500"
        summary = gate.summarize_selected(wrapper, ordinary, ordinary=True)
        self.assertEqual(summary["winner_measured"], summary["rows"][0]["measured"])
        self.assertEqual(summary["rows"][0]["measured"], {
            "iterations": 500, "dps": "99.125", "standard_error": "0.75",
            "engine_result_sha256": "engine-hash", "formula_residual": "-0.125"})
        wrapper["verification_policy"] = "formula_only"
        with self.assertRaisesRegex(ValueError, "n500"):
            gate.summarize_selected(wrapper, ordinary, ordinary=True)

    def test_ordinary_every_alternative_needs_n500_measurement_and_sound_numbers(self):
        request, wrapper = fixture()
        ordinary = gate.ordinary_request(request)
        ordinary["artifacts"].append({"artifact_id": 21, "slot": "flower", "set_uid": "known"})
        product = wrapper["product_result"]
        product["request_sha256"] = canonical_sha256(ordinary)
        product["ranking_basis"] = "gcsim"
        product["warnings"] = ["formula_rank_not_measurement_authority"]
        measured = {"iterations": 500, "dps": "99", "standard_error": "0.5",
                    "engine_result_sha256": "engine-hash"}
        product["measured"] = dict(measured)
        product["formula_residual"] = "1"
        product["candidates"][0].update(measured=dict(measured), formula_residual="1")
        alternative = json.loads(json.dumps(product["candidates"][0]))
        alternative.update(rank=2, alternative_rank=2, formula_dps="98", formula_residual="2")
        alternative["artifacts"][0]["artifact_id"] = 21
        product["candidates"].append(alternative)
        wrapper["verification_policy"] = "single_n500"
        self.assertEqual(len(gate.summarize_selected(wrapper, ordinary, ordinary=True)["rows"]), 2)
        del alternative["measured"]
        with self.assertRaisesRegex(ValueError, "n500 measurement"):
            gate.summarize_selected(wrapper, ordinary, ordinary=True)
        alternative["measured"] = dict(measured)
        alternative["measured"]["standard_error"] = "-1"
        with self.assertRaisesRegex(ValueError, "uncertainty"):
            gate.summarize_selected(wrapper, ordinary, ordinary=True)
        alternative["measured"]["standard_error"] = "NaN"
        with self.assertRaisesRegex(ValueError, "uncertainty"):
            gate.summarize_selected(wrapper, ordinary, ordinary=True)
        alternative["measured"]["standard_error"] = "0.5"
        alternative["measured"]["engine_result_sha256"] = ""
        with self.assertRaisesRegex(ValueError, "identity"):
            gate.summarize_selected(wrapper, ordinary, ordinary=True)

    def test_adapter_requires_fresh_compact_identity_and_unchanged_inputs(self):
        request, wrapper = fixture()
        compact = {"request_sha256": canonical_sha256(request), "members": []}
        wrapper["product_result"]["compact_ir_sha256"] = canonical_sha256(compact)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            captured = root / "captured"
            captured.mkdir()
            _write_canonical(captured / "request.json", request)
            _write_canonical(captured / "compact.json", compact)
            class FakeSession:
                def _validate_optimizer_request(self, *, run_dir, started):
                    assert (run_dir / "request.json").exists() and started > 0
                def _run_go_optimizer(self, *, prepared, compact, run_dir, started):
                    assert prepared["request_sha256"] == canonical_sha256(request)
                    (run_dir / "optimizer-output.json").write_text(json.dumps(wrapper), encoding="utf-8")
            result, timing = gate.run_adapter(FakeSession(), captured, root / "candidate",
                                              {"request": request, "request_sha256": canonical_sha256(request)},
                                              compact, request, ordinary=False)
            self.assertTrue(result["legal_output_checked"])
            self.assertGreaterEqual(timing["process_seconds"], 0)
            wrapper["product_result"]["compact_ir_sha256"] = "wrong"
            with self.assertRaisesRegex(ValueError, "freshly captured compact"):
                gate.run_adapter(FakeSession(), captured, root / "bad-candidate",
                                 {"request": request, "request_sha256": canonical_sha256(request)},
                                 compact, request, ordinary=False)

    def test_adapter_uses_default_installed_path_and_no_product_timeout(self):
        request, _ = fixture()
        with tempfile.TemporaryDirectory() as raw:
            job = Path(raw)
            built = job / "candidate.exe"
            prepared = gate.adapter_request(job, request, built)
            self.assertEqual(Path(prepared.optimizer_binary_path), built)
            self.assertEqual(prepared.product_timeout_ms, 0)
            self.assertEqual(prepared.seeds, (11, 12))
            with patch.object(gate, "INSTALLED", job / "different.exe"):
                with self.assertRaisesRegex(ValueError, "Default Selected adapter"):
                    gate.adapter_request(job, request, built)

    def test_active_engine_binding_guard_rejects_wrong_artifact(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            binary = root / "engine.exe"
            binary.write_bytes(b"engine")
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            patch_sha = "a" * 64
            body = {"schema_version": 1, "kind": "gtt.source_manifest.body",
                    "patch_stack_sha256": patch_sha, "entries": []}
            source = root / "build/gtt-source-manifest-body.json"
            source.parent.mkdir()
            source.write_text(json.dumps(body), encoding="utf-8")
            source_sha = hashlib.sha256(canonical_source_manifest_json(body).encode()).hexdigest()
            manifest = GcsimEngineManifest(
                engine_id="mock", source_label="mock", source_path="", source_tree_hash="",
                engine_tree_hash="", prepared_at_utc="", patch_backend="mock", patch_count=1,
                patch_metadata={"patch_stack_sha256": patch_sha})
            (root / MANIFEST_FILE_NAME).write_text(json.dumps(manifest.to_dict()), encoding="utf-8")
            standalone = canonical_sha256({"kind": "gtt.standalone_engine_binding.v1",
                                           "artifact_sha256": digest,
                                           "source_manifest_sha256": source_sha,
                                           "patch_manifest_sha256": patch_sha})
            reference = {"request": {"engine": {"binary_path": str(binary),
                        "artifact_sha256": digest, "binding_sha256": standalone,
                        "source_manifest_sha256": source_sha,
                        "patch_manifest_sha256": patch_sha}},
                        "engine_sha256": digest}
            active = SimpleNamespace(artifact_path=str(binary), artifact_sha256=digest,
                                     engine_root=str(root), binding_sha256="different-legacy-context-binding")
            gate.assert_engine(reference, active)
            for field in ("source_manifest_sha256", "patch_manifest_sha256", "binding_sha256"):
                changed = json.loads(json.dumps(reference))
                changed["request"]["engine"][field] = "f" * 64
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "standalone"):
                    gate.assert_engine(changed, active)
            source.write_text(json.dumps({**body, "entries": [{"changed": True}]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "standalone"):
                gate.assert_engine(reference, active)
            source.write_text(json.dumps(body), encoding="utf-8")
            changed_manifest = manifest.to_dict()
            changed_manifest["patch_metadata"]["patch_stack_sha256"] = "b" * 64
            (root / MANIFEST_FILE_NAME).write_text(json.dumps(changed_manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source manifest"):
                gate.assert_engine(reference, active)
            (root / MANIFEST_FILE_NAME).write_text(json.dumps(manifest.to_dict()), encoding="utf-8")
            source.write_text("{bad-json", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source manifest"):
                gate.assert_engine(reference, active)
            source.write_text(json.dumps(body), encoding="utf-8")
            (root / MANIFEST_FILE_NAME).write_text("{bad-json", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source manifest"):
                gate.assert_engine(reference, active)
            (root / MANIFEST_FILE_NAME).write_text(json.dumps(manifest.to_dict()), encoding="utf-8")
            binary.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "active engine"):
                gate.assert_engine(reference, active)


if __name__ == "__main__":
    unittest.main()
