import hashlib
import json
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from run_workspace.gcsim import optimizer_go_all_sources as sources
from run_workspace.gcsim import optimizer_go_selected as selected
from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsRequest, GcsimOptimizerGoAllSetsSession
from run_workspace.gcsim.source_manifest_build import canonical_json, compute_patched_source_tree_sha256


def check_effect_sources(case, tmp_path):
    binary = tmp_path / "build/gtt-gcsim.exe"
    binary.parent.mkdir()
    binary.write_bytes(b"test binary, never executed")
    files = ("pkg/core/attributes/stats.go", "pkg/core/attributes/element.go", "pkg/core/attacks/attack.go", "pkg/enemy/damage.go", "internal/artifacts/test/test.go")
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"package test\r\n")
    manifest = {"patched_source_tree_sha256": compute_patched_source_tree_sha256(tmp_path)}
    (tmp_path / "build/gtt-source-manifest-body.json").write_text(json.dumps(manifest))
    # The normal updater adds installation metadata after the source build.
    (tmp_path / "gtt_engine_manifest.json").write_text('{"installed": true}')
    binding = {"binary_path": str(binary), "artifact_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
               "source_manifest_sha256": hashlib.sha256(canonical_json(manifest).encode()).hexdigest(),
               "capabilities": ["gtt_effect_inputs_v1"]}
    catalog = SimpleNamespace(source_fingerprint="a" * 64, sets=[SimpleNamespace(
        max_rarity=5, key="test", two_piece_modeled=True, four_piece_modeled=True, source_files=[files[-1]])])
    with patch.object(sources, "load_gcsim_artifact_set_catalog", return_value=catalog):
        result = sources.prepare_all_set_effect_sources(tmp_path, binding)
    assert result["items"][0]["key"] == "test"
    assert result["stat_source"]["text"].endswith("\r\n")
    # Only exact store metadata is excluded: an added source-side file must fail.
    extra = tmp_path / "pkg/source-input.json"
    extra.write_text('{}')
    with case.assertRaisesRegex(ValueError, "sources differ"):
        sources.prepare_all_set_effect_sources(tmp_path, binding)
    extra.unlink()
    with case.assertRaisesRegex(ValueError, "capability"):
        sources.prepare_all_set_effect_sources(tmp_path, {**binding, "capabilities": []})
    with case.assertRaisesRegex(ValueError, "binary changed"):
        sources.prepare_all_set_effect_sources(tmp_path, {**binding, "artifact_sha256": "c" * 64})
    (tmp_path / files[-1]).write_text("package changed")
    with case.assertRaisesRegex(ValueError, "sources differ"):
        sources.prepare_all_set_effect_sources(tmp_path, binding)


class AllSetSourceBindingTests(unittest.TestCase):
    def test_sources_bind_binary_manifest_and_complete_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            check_effect_sources(self, Path(folder))

    def test_real_request_preparation_connects_to_all_sets_source_validation(self):
        # Synthetic engine/account scaffolding only. Exercise both production
        # adapters together; never construct the request's manifest hash by hand.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "engine"
            binary = root / "build/gtt-gcsim.exe"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"test binary, never executed")
            source_files = (
                "pkg/core/attributes/stats.go", "pkg/core/attributes/element.go",
                "pkg/core/attacks/attack.go", "pkg/enemy/damage.go",
                "internal/artifacts/test/test.go",
            )
            for name in source_files:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"package test\r\n")
            manifest = {"patched_source_tree_sha256": compute_patched_source_tree_sha256(root)}
            manifest_path = root / "build/gtt-source-manifest-body.json"
            canonical = canonical_json(manifest).encode("utf-8")
            expected_sha = hashlib.sha256(canonical).hexdigest()
            catalog = SimpleNamespace(source_fingerprint="a" * 64, sets=[SimpleNamespace(
                max_rarity=5, key="test", two_piece_modeled=True, four_piece_modeled=True,
                source_files=[source_files[-1]],
            )])
            engine = SimpleNamespace(
                engine_root=str(root), artifact_path=str(binary),
                artifact_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                capabilities=selected.REQUIRED_ENGINE_CAPABILITIES | {"gtt_effect_inputs_v1"},
            )
            config = "\n".join(f"{key} char lvl=90;" for key in ("alpha", "beta", "gamma", "delta"))
            config += "\ntarget lvl=100 resist=0.1;\n"
            report = SimpleNamespace(ready=True, issues=[], team=SimpleNamespace(payload={}),
                                     full_config=SimpleNamespace(assembly=SimpleNamespace(config_text=config)))
            database = SimpleNamespace(artifact_database_input_sha256="a" * 64)
            snapshot = SimpleNamespace(equipment_rows_sha256="b" * 64, snapshot_sha256="c" * 64)
            scaffolding = {
                "load_active_gcsim_optimizer_engine_context": Mock(return_value=engine),
                "build_selected_team_full_config_report": Mock(return_value=report),
                "load_gcsim_optimizer_artifact_database_input": Mock(return_value=SimpleNamespace(ready=True, database_input=database)),
                "load_selected_equipped_team_snapshot": Mock(return_value=snapshot),
                "bind_selected_report_config_and_snapshot": Mock(return_value=(SimpleNamespace(actor_key="alpha"),)),
                "load_engine_manifest": Mock(return_value=SimpleNamespace(patch_metadata={"patch_stack_sha256": "d" * 64})),
                "_request_wearers": Mock(return_value=[]),
                "_request_artifacts": Mock(return_value=[]),
            }
            request = GcsimOptimizerGoAllSetsRequest("unused.db", {}, 0, config)
            session = GcsimOptimizerGoAllSetsSession(request)
            serializations = (canonical, canonical + b"\n", canonical + b"\r\n",
                              json.dumps(manifest, indent=2).encode("utf-8"))
            with patch.multiple(selected, **scaffolding), patch.object(sources, "load_gcsim_artifact_set_catalog", return_value=catalog):
                for i, raw in enumerate(serializations):
                    with self.subTest(serialization=i):
                        manifest_path.write_bytes(raw)
                        run = Path(folder) / f"run-{i}"
                        run.mkdir()
                        prepared = selected._prepare_inputs(request, run)
                        budgets = prepared["request"]["budgets"]
                        self.assertEqual(budgets["product_timeout_ms"], 600_000)
                        self.assertGreaterEqual(budgets["development_timeout_ms"], budgets["product_timeout_ms"])
                        binding = prepared["request"]["engine"]
                        self.assertEqual(binding["source_manifest_sha256"], expected_sha)
                        session._prepare_formula_inputs(prepared=prepared, run_dir=run, started=0)
                        envelope = json.loads((run / "set-sources.json").read_bytes())
                        self.assertEqual(envelope["source_manifest_sha256"], expected_sha)
                        self.assertEqual(envelope["items"][0]["key"], "test")
                # Actual content changes after request preparation must still fail.
                manifest_path.write_text(json.dumps({**manifest, "changed": True}), encoding="utf-8")
                with self.assertRaisesRegex(selected.GcsimOptimizerGoSelectedError, "bound source manifest changed"):
                    session._prepare_formula_inputs(prepared=prepared, run_dir=run, started=0)
                manifest_path.write_bytes(b"{")
                with self.assertRaises(selected.GcsimOptimizerGoSelectedError) as invalid:
                    selected._prepare_inputs(request, run)
                self.assertEqual(invalid.exception.code, "source_manifest_invalid")
