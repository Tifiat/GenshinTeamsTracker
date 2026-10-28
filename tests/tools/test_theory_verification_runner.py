"""Verification accounting and payload guards; no simulator calls."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import unittest

from tools.experiments.gcsim.theory_verification import run_case as runner


class TheoryVerificationRunnerTests(unittest.TestCase):
    def test_expected_dps_uses_member_duration_and_keeps_foreign_actor(self):
        member = {"seed": 7, "duration_ms": 2000, "nodes": [], "channels": [
            {"actor_key": "flins", "baseline_damage": "800", "hit_count": 1,
             "damage_type": "electro", "attack_tag": "tag/4", "kind": "direct"},
            {"actor_key": "jahoda", "baseline_damage": "200", "hit_count": 2,
             "damage_type": "hydro", "attack_tag": "tag/4", "kind": "direct"},
        ], "opaque_boundaries": [{"reason_code": "schedule_frozen"}]}
        result = runner.summarize_member(member, 7)
        self.assertEqual(result["expected_dps"], 500)
        self.assertEqual(result["by_actor_expected_dps"], {"flins": 400, "jahoda": 100})
        self.assertEqual(result["opaque_reasons"], ["schedule_frozen"])
        with self.assertRaises(ValueError):
            runner.summarize_member(member, 8)
        for invalid in (0, -1, float("nan")):
            changed = copy.deepcopy(member)
            changed["duration_ms"] = invalid
            with self.assertRaises(ValueError):
                runner.summarize_member(changed, 7)

    def test_ordinary_se_and_iteration_guard(self):
        payload = {"statistics": {"iterations": 128, "dps": {"mean": 1000, "sd": 40},
                                  "failed_actions": [{"insufficient_energy": {"max": 0}}]}}
        result = runner.summarize_ordinary(payload, 128)
        self.assertAlmostEqual(result["standard_error"], 40 / math.sqrt(128))
        self.assertEqual(result["insufficient_energy_max"], 0)
        with self.assertRaises(ValueError):
            runner.summarize_ordinary(payload, 500)
        payload["statistics"]["dps"]["sd"] = float("inf")
        with self.assertRaises(ValueError):
            runner.summarize_ordinary(payload, 128)

    def test_optional_duration_and_reaction_counts_bind_to_declaration_order(self):
        payload = {"statistics": {
            "iterations": 500, "dps": {"mean": 1000, "sd": 40},
            "duration": {"mean": 32.5, "sd": 1.25},
            "source_reactions": [
                {"sources": {"Melt": {"mean": 3.5, "sd": 0.75}, "Vaporize": {"mean": 1}}},
                {"sources": {}},
                {},
                {"sources": {"Overloaded": {}}},
            ],
        }}
        summary = runner.summarize_ordinary(payload, 500)
        self.assertEqual(summary["duration_seconds"], {"mean": 32.5, "sd": 1.25})
        config = ("gaming char lvl=90/90;\n"
                  "citlali char lvl=90/90;\n"
                  "diona char lvl=90/90;\n"
                  "bennett char lvl=90/90;\n")
        runner.bind_ordinary_reaction_actors(summary, config)
        self.assertNotIn("source_reactions_by_declaration_index", summary)
        rows = summary["source_reactions_by_actor"]
        self.assertEqual([(row["declaration_index"], row["actor_key"]) for row in rows],
                         [(0, "gaming"), (1, "citlali"), (2, "diona"), (3, "bennett")])
        self.assertEqual(rows[0]["reactions"], {
            "Melt": {"mean": 3.5, "sd": 0.75},
            "Vaporize": {"mean": 1, "sd": 0},
        })
        self.assertEqual(rows[1]["reactions"], {})
        self.assertEqual(rows[2]["reactions"], {})
        self.assertEqual(rows[3]["reactions"], {"Overloaded": {"mean": 0, "sd": 0}})

    def test_optional_ordinary_shapes_and_actor_count_fail_closed(self):
        base = {"statistics": {"iterations": 128, "dps": {"mean": 1000, "sd": 10}}}
        bad_fields = (
            ("duration", []),
            ("duration", {"mean": -1}),
            ("duration", {"sd": float("nan")}),
            ("source_reactions", {}),
            ("source_reactions", [None]),
            ("source_reactions", [{"sources": []}]),
            ("source_reactions", [{"sources": {"Melt": {"mean": -1}}}]),
            ("source_reactions", [{"sources": {"Melt": {"sd": float("inf")}}}]),
        )
        for field, value in bad_fields:
            with self.subTest(field=field, value=value):
                payload = copy.deepcopy(base)
                payload["statistics"][field] = value
                with self.assertRaises(ValueError):
                    runner.summarize_ordinary(payload, 128)
        summary = runner.summarize_ordinary({"statistics": {
            "iterations": 128, "dps": {"mean": 1000, "sd": 10},
            "source_reactions": [{"sources": {}}],
        }}, 128)
        with self.assertRaisesRegex(ValueError, "exactly four"):
            runner.bind_ordinary_reaction_actors(summary, "a char lvl=90/90;\nb char lvl=90/90;\nc char lvl=90/90;\nd char lvl=90/90;\n")
        four = {"source_reactions_by_declaration_index": [{}, {}, {}, {}]}
        with self.assertRaisesRegex(ValueError, "exactly four"):
            runner.bind_ordinary_reaction_actors(four, "a char lvl=90/90;\na char lvl=90/90;\nc char lvl=90/90;\nd char lvl=90/90;\n")

    def test_ordinary_options_preserve_energy_and_rotation(self):
        source = "flins char lvl=90/90;\noptions swap_delay=12 iteration=100 workers=1 ignore_burst_energy=true;\ntarget lvl=100 resist=0.1;\nactive flins;\nflins skill;\n"
        result = runner.ordinary_options(source, 128)
        self.assertIn("iteration=128 workers=4", result)
        self.assertIn("ignore_burst_energy=true", result)
        self.assertEqual(result.split("\ntarget", 1)[1], source.split("\ntarget", 1)[1])
        with self.assertRaises(ValueError):
            runner.ordinary_options(source.replace("workers=1", "workers=1 workers=2"), 128)
        with self.assertRaises(ValueError):
            runner.ordinary_options(source + "options iteration=1;\n", 128)

    def test_saved_case_binds_actual_receipt_and_matrix(self):
        path = runner.ROOT / "tools/experiments/gcsim/theory_verification/cases/lunar_charged_saved_rank1.json"
        case, entry, candidate, provenance = runner.load_case(path, with_provenance=True)
        self.assertEqual(entry["team"], "lunar_charged")
        self.assertEqual(len(entry["virtual_profiles"]), 4)
        self.assertEqual(candidate["rank"], 1)
        self.assertEqual(case["seeds"], [742031889, 742031890])
        self.assertEqual(provenance["kind"], "audited_product_receipt")
        self.assertEqual(provenance["engine_identity"]["artifact_sha256"], case["engine_artifact_sha256"])
        self.assertEqual(provenance["source_input_hashes"]["rotation_sha256"], case["rotation_sha256"])
        self.assertEqual(len(runner.load_case(path)), 3)
        with self.assertRaises(ValueError):
            runner.inside_worker(runner.ROOT.parent / "outside.json")

    def test_historical_matrix_run_is_unique_and_exactly_matches_current_entry(self):
        path = runner.ROOT / "tools/experiments/gcsim/theory_verification/cases/lunar_crystallize_saved_rank1.json"
        case, entry, candidate, provenance = runner.load_case(path, with_provenance=True)
        self.assertEqual(candidate["rank"], 1)
        self.assertEqual(entry["id"], "lunar_crystallize_theory")
        self.assertEqual(provenance["kind"], "historical_matrix_run")
        self.assertEqual(provenance["run_id"], entry["id"])
        self.assertEqual(provenance["engine_identity"]["artifact_sha256"],
                         "9d107ed713a171c64509ce35348c5d8f7bc08d81bea785db0f308b46d8869d50")
        self.assertEqual(provenance["sha256"], runner.HISTORICAL_MATRIX_SHA256)
        self.assertEqual(provenance["current_manifest_sha256"], case["manifest_sha256"])
        self.assertEqual(provenance["current_rotation_sha256"], case["rotation_sha256"])
        self.assertIsNone(provenance["source_input_hashes"]["profiles_sha256"])
        self.assertIsNone(provenance["source_input_hashes"]["rotation_sha256"])
        self.assertIn("omits original profile and rotation hashes", provenance["limitations"][0])
        self.assertEqual(runner.digest(runner.HISTORICAL_MATRIX), runner.HISTORICAL_MATRIX_SHA256)

    def test_historical_source_rejects_foreign_or_ambiguous_run_and_rank(self):
        path = runner.ROOT / "tools/experiments/gcsim/theory_verification/cases/lunar_crystallize_saved_rank1.json"
        case, entry, _, _ = runner.load_case(path, with_provenance=True)
        ref = case["candidate_source"]
        source = runner.HISTORICAL_MATRIX.resolve()
        fixture = json.loads(source.read_text(encoding="utf-8"))

        def reject(change):
            document = copy.deepcopy(fixture)
            change(document)
            with self.assertRaises(ValueError):
                runner.select_candidate_source(case, entry, ref, document, source)

        reject(lambda d: d["runs"].append(copy.deepcopy(next(r for r in d["runs"] if r["id"] == entry["id"]))))
        reject(lambda d: next(r for r in d["runs"] if r["id"] == entry["id"]).update(characters=["foreign"] * 4))
        reject(lambda d: next(r for r in d["runs"] if r["id"] == entry["id"]).update(rotation_file="foreign.txt"))
        reject(lambda d: next(r for r in d["runs"] if r["id"] == entry["id"]).update(team="foreign"))
        reject(lambda d: next(r for r in d["runs"] if r["id"] == entry["id"]).update(status="failed"))
        reject(lambda d: next(r for r in d["runs"] if r["id"] == entry["id"])["product"]["candidates"].append(
            copy.deepcopy(next(r for r in d["runs"] if r["id"] == entry["id"])["product"]["candidates"][0])))
        with self.assertRaises(ValueError):
            runner.select_candidate_source(case, entry, {**ref, "run_id": "wrong_theory"}, fixture, source)
        with self.assertRaises(ValueError):
            runner.select_candidate_source(case, entry, {**ref, "rank": 99}, fixture, source)

    def test_point_comparison_distinguishes_current_historical_and_inline(self):
        audit = runner.ROOT / "tools/experiments/gcsim/theory_verification/cases/lunar_charged_saved_rank1.json"
        case, _, candidate, current = runner.load_case(audit, with_provenance=True)
        engine_id, sha = case["engine_id"], case["engine_artifact_sha256"]
        predicted = candidate["formula_dps"]
        matched = runner.compare_point_response(predicted, predicted,
            source_provenance=current, active_engine_id=engine_id, active_artifact_sha256=sha)
        self.assertEqual(matched["point_response_status"], "roundoff_match")
        self.assertEqual(matched["comparison_scope"], "same_engine_point_response")
        mismatch = runner.compare_point_response(predicted, predicted * 1.1,
            source_provenance=current, active_engine_id=engine_id, active_artifact_sha256=sha)
        self.assertEqual(mismatch["point_response_status"], "mismatch_requires_attribution")

        historical_case = runner.ROOT / "tools/experiments/gcsim/theory_verification/cases/lunar_crystallize_saved_rank1.json"
        _, _, old_candidate, historical = runner.load_case(historical_case, with_provenance=True)
        old_predicted = old_candidate["formula_dps"]
        for actual, relation in ((old_predicted, "roundoff_match"), (old_predicted * 1.1, "different")):
            result = runner.compare_point_response(old_predicted, actual,
                source_provenance=historical, active_engine_id=engine_id, active_artifact_sha256=sha)
            self.assertEqual(result["point_response_status"], "historical_cross_engine_reference")
            self.assertEqual(result["comparison_scope"], "historical_drift")
            self.assertEqual(result["numerical_relation"], relation)
        unbound = runner.compare_point_response(predicted, predicted,
            source_provenance={"kind": "inline_unbound", "engine_identity": None},
            active_engine_id=engine_id, active_artifact_sha256=sha)
        self.assertEqual(unbound["point_response_status"], "unbound_formula_reference")


if __name__ == "__main__":
    unittest.main()
