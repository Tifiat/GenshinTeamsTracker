"""Safety controls for the source-only parametric query gate, without an engine.

The actual disposable-directory cleaner is covered by the existing managed
optimizer experiment suite. These tests pin path validation and the no-job gate.
"""
import os
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.experiments.gcsim.parametric_effects.check_stat_queries import bound_overlay_path, main, patch_paths, stage_overlay_variants, refuse_consolidated_observer
from tools.experiments.gcsim.parametric_effects.check_rules import main as rules_main, run_gate
from tools.experiments.gcsim.parametric_effects.inventory_profile import bind_saved_reference, prepare_inventory_profile, SLOTS
from tools.experiments.gcsim.parametric_effects.verify_candidates import owned_job, validate_assignments
from tools.experiments.gcsim.parametric_effects.compare_preparation import without_reuse, without_constant_binding, semantic_profile, run_comparison


class ParametricEffectGateTests(unittest.TestCase):
    def test_old_overlay_cannot_reapply_to_consolidated_active_engine(self):
        refuse_consolidated_observer({"metadata": {"gtt_capabilities": "[]"}})
        with self.assertRaisesRegex(ValueError, "already consolidated"):
            refuse_consolidated_observer({"metadata": {"gtt_capabilities": '["gtt_neutral_inputs_v1"]'}})

    def test_two_seed_profile_requires_explicit_complete_nonpaired_gate(self):
        for flags in (["--two-seeds"], ["--two-seeds", "--capture-fixture", "--inventory-profile", "--finish-passes", "--compare-effects"]):
            with self.subTest(flags=flags), patch("sys.argv", ["gate", *flags]), self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(caught.exception.code, 2)

    def test_effect_binding_control_changes_only_its_two_optimizations(self):
        key = "\tkey, constant := projectedConstantEffectKey(m.effectKeys, m.constantKeys, effects)"
        fast = "\tif bound, constant, err := p.bindConstantEffects(effects); constant {\n\t\treturn bound, err\n\t}\n"
        cache, expression = without_constant_binding("prefix\n" + key + "\nsuffix", "prefix\n" + fast + "suffix")
        self.assertIn("constantEffectKey(m.effectKeys, effects)", cache)
        self.assertEqual(expression, "prefix\nsuffix")
        with self.assertRaises(ValueError):
            without_constant_binding(key + key, fast)

    def test_preparation_control_is_narrow_and_preserves_semantic_evidence(self):
        line = "\tmodel.specializations = formula.NewSpecializationCache(neutralProgramEntries, neutralProgramNodes)"
        candidates = "prefix\n\tplan, err := r.engine.domain.PreparePackageLinear(input)\nbody\n\tids, ok, err := linear()\nsuffix"
        model, changed = without_reuse(line, candidates)
        self.assertNotIn("NewSpecializationCache", model)
        self.assertTrue(changed.startswith("prefix\n"))
        self.assertTrue(changed.endswith("\tids, ok, err := linear()\nsuffix"))
        self.assertIn("r.linear(w, excluded...)", changed)
        with self.assertRaises(ValueError):
            without_reuse(line + line, candidates)
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, "owned managed job"):
            run_comparison(Path.cwd(), {})
        row = dict(Seconds=1, ProposalSeconds=2, SeedSeconds=3, PotentialSeconds=0, JointSeconds=0, SlowFrontiers=[], WorkSHA="evidence", Finalists=[1], Model=dict(RuleSeconds=1, BindSeconds=2, ViewSeconds=3, Specialization={}, Requests=9))
        original = deepcopy(row)
        cleaned = semantic_profile(row)
        self.assertEqual(row, original)
        self.assertEqual(cleaned, dict(WorkSHA="evidence", Finalists=[1], Model=dict(Requests=9)))

    def test_only_narrow_engine_sources_are_accepted(self):
        self.assertEqual(patch_paths("diff --git a/pkg/gtttrace/query.go b/pkg/gtttrace/query.go\n"),
                         ["pkg/gtttrace/query.go"])
        self.assertEqual(patch_paths("diff --git a/internal/template/character/character.go b/internal/template/character/character.go\n"),
                         ["internal/template/character/character.go"])
        for name in ("../settings.json", "pkg/../../settings.json", "C:/outside.go", "build/engine.exe", "internal/artifacts/test/test.go"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                patch_paths(f"diff --git a/{name} b/{name}\n")
        row = "diff --git a/pkg/example.go b/pkg/example.go\n"
        with self.assertRaises(ValueError):
            patch_paths(row + row)

    def test_refuses_unmanaged_execution_before_reading_active_state(self):
        with patch.dict(os.environ, {}, clear=True), patch("sys.argv", ["gate"]), self.assertRaisesRegex(RuntimeError, "managed_optimizer"):
            main()
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, "managed_optimizer"):
            rules_main()
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, "managed_optimizer"):
            run_gate(Path.cwd())
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, "managed job"):
            prepare_inventory_profile(Path.cwd())

    def test_inventory_profile_preserves_input_and_checks_reference_vectors(self):
        request = {"wearers": [], "artifacts": [], "legality": {}, "context": {
            "rotation": {"sha256": "a" * 64}, "target": {"sha256": "b" * 64}}}
        saved = {"reference_ids": {}, "config": ""}
        for i, actor in enumerate(("alpha", "beta", "gamma", "delta")):
            request["wearers"].append({"wearer_key": actor, "selected_set_uid": "old"})
            saved["reference_ids"][actor] = {}
            saved["config"] += f'{actor} add set="sample" count=4;\n{actor} add stats hp=5;\n'
            for j, slot in enumerate(SLOTS):
                artifact_id = i * 5 + j + 1
                saved["reference_ids"][actor][slot] = artifact_id
                request["artifacts"].append(dict(artifact_id=artifact_id, slot=slot,
                    set_uid="sample" if j < 4 else "off", main_stat={"key": "hp", "value": "1"}, substats=[]))
        original = deepcopy(request)
        bound = bind_saved_reference(request, saved, {"hp": "hp"})
        self.assertEqual(request, original)
        self.assertEqual(len(bound["wearers"][0]["current_artifacts"]), 5)
        self.assertEqual(bound["wearers"][0]["selected_set_uid"], "sample")
        request["artifacts"][0]["main_stat"]["value"] = "2"
        with self.assertRaisesRegex(ValueError, "vector changed"):
            bind_saved_reference(request, saved, {"hp": "hp"})
        saved["reference_ids"]["beta"]["flower"] = 1
        with self.assertRaises(ValueError):
            bind_saved_reference(original, saved, {"hp": "hp"})

    def test_ordinary_candidates_are_bounded_legal_and_managed(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, "managed_optimizer"):
            owned_job()
        row = {"name": "expanded", "assignment": [list(range(1 + 5*i, 6 + 5*i)) for i in range(4)]}
        validate_assignments([row])
        for rows in ([], [row]*3, [{**row, "name": "../outside"}], [{**row, "assignment": [[1]*5]*4}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                validate_assignments(rows)

    def test_generated_overlay_collision_preserves_both_variants(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            engine, job = root / "engine", root / "job"
            (engine / "pkg").mkdir(parents=True)
            job.mkdir()
            original, generated = engine / "pkg/a.go", engine / "instrumented.go"
            original.write_text("original")
            generated.write_text("instrumented")
            untouched = str(engine / "pkg/untouched.go")
            overlay = {"Replace": {untouched: "preserved"}}
            variants = stage_overlay_variants(engine, job, ["pkg/a.go", "pkg/new.go"], overlay, {"pkg/a.go": generated})
            self.assertEqual((variants[0] / "pkg/a.go").read_text(), "original")
            self.assertEqual((variants[1] / "pkg/a.go").read_text(), "instrumented")
            self.assertEqual(Path(overlay["Replace"][str(original)]).read_text(), "instrumented")
            self.assertEqual(overlay["Replace"][untouched], "preserved")
            self.assertFalse((variants[0] / "pkg/new.go").exists())
            self.assertEqual(original.read_text(), "original")
            self.assertEqual(generated.read_text(), "instrumented")

    def test_overlay_relocation_cannot_select_another_installation(self):
        store = Path.cwd() / "synthetic-engine-store"
        engine = store / "engines" / "selected"
        self.assertEqual(bound_overlay_path(str(store / "staging/selected/pkg/a.go"), engine), engine / "pkg/a.go")
        self.assertEqual(bound_overlay_path(str(engine / "pkg/a.go"), engine), engine / "pkg/a.go")
        with self.assertRaises(ValueError):
            bound_overlay_path(str(store / "staging/other/pkg/a.go"), engine)


if __name__ == "__main__":
    unittest.main()
