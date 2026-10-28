"""Focused quality comparisons for the isolated All Sets hypothesis pair."""
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch

from tools.experiments.gcsim.search_hypotheses.matrix_pair import (
    EVIDENCE_ROOT, captures, compare, point_screen_diagnostics, prepare_reused_input,
    requires_exact_rows, validated_evidence_dir, validated_reuse_baseline,
)
from tools.experiments.gcsim.search_hypotheses.run import copy_variant_support
from run_workspace.gcsim.optimizer_go_selected import _write_canonical


def row(group, rank, dps):
    return {"group": group, "rank": rank, "dps": dps}


def pair(rows):
    return {
        "rows": rows,
        "leaders": [candidate for candidate in rows if candidate["rank"] == 1],
        "search_seconds": 1.0,
    }


class SearchHypothesisMatrixTests(unittest.TestCase):
    def test_capture_receipt_retains_all_three_versioned_comparisons(self):
        member = {"nodes": [{"node_id": 1, "operation": "constant", "value": "-0", "inputs": []}],
                  "channels": [{"root_node_id": 1}], "opaque_boundaries": []}
        member_bytes = json.dumps(member).encode()
        effects = {"member_content_sha256": hashlib.sha256(member_bytes).hexdigest(),
                   "neutral": {"stats": [], "reads": []}, "effect_inputs": [], "resistance_inputs": []}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "contexts/context-one/seed-1"
            directory.mkdir(parents=True)
            (directory / "member.json").write_bytes(member_bytes)
            (directory / "member.json.effects.json").write_text(json.dumps(effects), encoding="utf-8")
            row = captures(Path(temporary))["context-one/seed-1"]
        self.assertEqual(64, len(row["canonical_sha256"]))
        self.assertEqual(64, len(row["independent_status_sha256_v1"]))
        self.assertEqual(64, len(row["independent_status_constant_fold_sha256_v1"]))
        self.assertEqual(64, len(row["algebraic_capture_sha256_v1"]))

    def test_reused_json_fingerprint_matches_fresh_tuple_ids(self):
        fresh = {"rows": [{"group": "g", "rank": 1, "dps": 10.0,
                           "ids": [("actor", "flower", 7)]}],
                 "leaders": [{"group": "g", "rank": 1, "dps": 10.0}],
                 "search_seconds": 1.0}
        retained = json.loads(json.dumps(fresh))
        self.assertTrue(compare(retained, fresh)["exact_rows"])
        fresh["rows"][0]["ids"][0] = ("actor", "flower", 8)
        self.assertFalse(compare(retained, fresh)["exact_rows"])

    def test_quality_policy_distinguishes_exact_reuse_from_heuristics(self):
        for name in ("combined_exact_reuse", "wide_program_cache", "context_dispatch_memo", "player_safe_wide"):
            self.assertTrue(requires_exact_rows(name))
        for name in ("combined_narrow_reuse", "player_point32_adaptive",
                     "player_point96_adaptive", "player_point32", "player_refine_one", "amount_plan"):
            self.assertFalse(requires_exact_rows(name))
        with self.assertRaises(ValueError):
            requires_exact_rows("unknown_variant")

    def test_evidence_directory_must_remain_under_optimizer_evidence(self):
        target = EVIDENCE_ROOT / "2026-09-28-player-hypotheses" / "matrix"
        self.assertEqual(validated_evidence_dir(target), target.resolve())
        with self.assertRaises(ValueError):
            validated_evidence_dir(EVIDENCE_ROOT.parent)

    def test_shared_copy_support_covers_new_player_variants(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            native, job = root / "native", root / "job"
            for name in ("cmd/gtt-optimizer", "internal/formula", "internal/setcontext",
                         "internal/seteffects", "internal/search", "internal/allsets",
                         "internal/domain"):
                (native / name).mkdir(parents=True)
            # Source-overlay application is tested by the Go controls. Here
            # verify the common runner's complete support copy inventory.
            with patch("tools.experiments.gcsim.search_hypotheses.region_dense.apply_dense"):
                copy_variant_support(native, "player_point32_adaptive", job)
            for path in ("internal/formula/hypothesis_region_binding.go",
                         "internal/formula/hypothesis_region_binding_test.go",
                         "internal/formula/hypothesis_mixed_formula.go",
                         "internal/setcontext/hypothesis_mixed_cache.go",
                         "internal/setcontext/hypothesis_point_screen.go",
                         "internal/allsets/hypothesis_point_packages.go",
                         "internal/seteffects/hypothesis_effect_families.go",
                         "internal/seteffects/hypothesis_amount_plan.go",
                         "cmd/gtt-optimizer/hypothesis_exact_rescore_test.go"):
                self.assertTrue((native / path).is_file(), path)
            self.assertIn("const hypothesisAdaptivePoint = true",
                          (native / "internal/allsets/hypothesis_point_packages.go").read_text())
            with patch("tools.experiments.gcsim.search_hypotheses.region_dense.apply_dense"):
                copy_variant_support(native, "player_safe_wide", job)
            self.assertTrue((native / "internal/search/hypothesis_player_filter.go").is_file())
            self.assertTrue((native / "internal/seteffects/hypothesis_replay_plan_test.go").is_file())

    def test_point_screen_diagnostics_are_bounded(self):
        with tempfile.TemporaryDirectory() as raw:
            log = Path(raw) / "stdout.json"
            log.write_bytes(b"noise\n" + b"\n".join(
                b"HYPOTHESIS_POINT_SCREEN actor=%d " % i + b"x" * 1000
                for i in range(20)))
            rows = point_screen_diagnostics(log)
            self.assertEqual(len(rows), 16)
            self.assertTrue(all(row.startswith("HYPOTHESIS_POINT_SCREEN") and len(row) <= 512 for row in rows))

    def test_reused_baseline_requires_case_hashes_and_complete_installed_run(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "retained.json"
            receipt = {"case": "same", "source_sha256": "source", "installed_sha256": "installed",
                       "manifest_sha256": "manifest", "engine_sha256": "engine",
                       "request_sha256": "request", "sources_sha256": "sources",
                       "status": "quality_regression", "installed_unchanged": True,
                       "active_pointer_unchanged": True, "engine_unchanged": True,
                       "request": {"schema_version": 1},
                       "runs": [{"name": "installed", "legal_output_checked": True,
                                 "rows": [row("A", 1, 1.0)], "leaders": [row("A", 1, 1.0)],
                                 "captures": {"one": {"canonical_sha256": "capture"}}}]}
            path.write_text(json.dumps(receipt), encoding="utf-8")
            with patch("tools.experiments.gcsim.search_hypotheses.matrix_pair.EVIDENCE_ROOT", root):
                resolved, loaded, installed = validated_reuse_baseline(
                    path, case="same", source_sha="source", installed_sha="installed", manifest_sha="manifest")
                self.assertEqual(resolved, path)
                self.assertEqual(installed, receipt["runs"][0])
                self.assertEqual(loaded["request"], receipt["request"])
                receipt["status"] = "failed"  # Candidate failure does not invalidate the installed row.
                path.write_text(json.dumps(receipt), encoding="utf-8")
                validated_reuse_baseline(path, case="same", source_sha="source",
                                         installed_sha="installed", manifest_sha="manifest")
                with self.assertRaisesRegex(ValueError, "case"):
                    validated_reuse_baseline(path, case="other", source_sha="source",
                                             installed_sha="installed", manifest_sha="manifest")
                receipt["runs"] = []
                path.write_text(json.dumps(receipt), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "complete"):
                    validated_reuse_baseline(path, case="same", source_sha="source",
                                             installed_sha="installed", manifest_sha="manifest")

    def test_reused_input_regenerates_canonical_request_and_checks_sources(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            request = {"schema_version": 1, "artifacts": [{"id": 2}, {"id": 1}]}
            _write_canonical(root / "expected.json", request)
            request_sha = hashlib.sha256((root / "expected.json").read_bytes()).hexdigest()
            source = b'{"source":"active"}\n'
            source_sha = hashlib.sha256(source).hexdigest()
            class FakeSession:
                def _prepare_formula_inputs(self, *, prepared, run_dir, started):
                    self_prepared = prepared
                    assert self_prepared == {"request": request}
                    assert started > 0
                    (run_dir / "set-sources.json").write_bytes(source)
            prepare_reused_input(root, request, FakeSession(), request_sha=request_sha,
                                 sources_sha=source_sha)
            self.assertEqual((root / "request.json").read_bytes(), (root / "expected.json").read_bytes())
            with self.assertRaisesRegex(ValueError, "regenerated"):
                prepare_reused_input(root, request, FakeSession(), request_sha=request_sha,
                                     sources_sha="incorrect")

    def test_unchanged_rows_are_exact_and_clean(self):
        rows = [row("A", 1, 100.0), row("A", 2, 90.0), row("B", 1, 80.0)]

        result = compare(pair(rows), pair([dict(candidate) for candidate in rows]))

        self.assertTrue(result["exact_rows"])
        self.assertEqual(result["regressions"], [])
        self.assertEqual(result["alternative_review"], [])

    def test_stronger_replacement_is_independent_of_serialization_order(self):
        baseline = pair([row("A", 1, 100.0), row("B", 1, 80.0)])
        # Candidate emits the retained group before the replacement; scoring
        # order is by DPS, not this serialization order.
        candidate = pair([row("B", 1, 80.0), row("C", 1, 110.0)])

        result = compare(baseline, candidate)

        self.assertFalse(result["exact_rows"])
        self.assertEqual(result["leader_rank_deltas"], [10.0, 0.0])
        self.assertEqual(result["regressions"], [])
        self.assertEqual(result["replaced_groups"], ["A"])

    def test_global_rank_regression_from_replacement_is_caught(self):
        baseline = pair([row("A", 1, 100.0), row("B", 1, 90.0)])
        # B improves, but replacement C does not preserve the old top rank.
        candidate = pair([row("C", 1, 95.0), row("B", 1, 95.0)])

        result = compare(baseline, candidate)

        self.assertIn("leader_rank_1", result["regressions"])
        self.assertEqual(result["replaced_groups"], ["A"])

    def test_retained_group_leader_regression_is_caught(self):
        baseline = pair([row("A", 1, 100.0), row("B", 1, 80.0)])
        candidate = pair([row("A", 1, 99.0), row("B", 1, 80.0)])

        result = compare(baseline, candidate)

        self.assertIn("retained_group_leader", result["regressions"])

    def test_fewer_groups_is_a_regression(self):
        baseline = pair([row("A", 1, 100.0), row("B", 1, 80.0)])
        candidate = pair([row("A", 1, 101.0)])

        result = compare(baseline, candidate)

        self.assertIn("fewer_bonus_groups", result["regressions"])

    def test_lower_alternative_is_flagged_for_review(self):
        baseline = pair([row("A", 1, 100.0), row("A", 2, 90.0)])
        candidate = pair([row("A", 1, 100.0), row("A", 2, 89.0)])

        result = compare(baseline, candidate)

        self.assertIn(
            {"group": "A", "reason": "lower_alternative_rank"},
            result["alternative_review"],
        )

    def test_fewer_alternatives_is_flagged_for_review(self):
        baseline = pair([row("A", 1, 100.0), row("A", 2, 90.0)])
        candidate = pair([row("A", 1, 100.0)])

        result = compare(baseline, candidate)

        self.assertIn(
            {"group": "A", "reason": "fewer_alternatives"},
            result["alternative_review"],
        )


if __name__ == "__main__":
    unittest.main()
