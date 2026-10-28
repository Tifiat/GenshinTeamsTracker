"""No engine: regressions for frozen gates, diversity and clock equivalence."""
import copy
from pathlib import Path
import unittest

from . import acceptance as a
from .adapter import transform


def policy(rows):
    return {"ranking": [{"family": f, "formula_dps": d, "package_key": k} for f, d, k in rows],
            "aliases_by_family": {f: [k] for f, _, k in rows}, "unavailable_by_reason": {}}


def quality_records():
    light = policy([("f1", 100, "a:4|b:4|c:4|d:4"), ("f2", 98.5, "e:4|b:4|c:4|d:4"),
                    ("f3", 97.5, "a:4|f:4|c:4|d:4")])
    records = []
    for name, seconds in (("H_light", 40), ("H_baseline", 60)):
        for suffix in ("_first_pass", ""):
            records.append({**copy.deepcopy(light), "kind": "hybrid_policy", "variant": name + suffix})
        records.append({"kind": "light_policy_result", "variant": name, "best": {"formula_dps": 100}, "seconds": seconds})
    return records


class AcceptanceTests(unittest.TestCase):
    def test_diversity_prioritizes_wearer_distance_not_alias_count(self):
        p = policy([("a", 100, "a|b|c|d"), ("b", 99.9, "e|b|c|d"), ("c", 98, "e|f|g|d")])
        p["aliases_by_family"]["a"] += ["z|b|c|d"]
        self.assertEqual([r["family"] for r in a.shortlist(p, 100, .03)], ["a", "c", "b"])
        self.assertEqual(a.band(p, 100, .03)["alias_tuple_count"], 4)
        self.assertEqual(len(a.shortlist(p, 100, .03)), 3)

    def test_unknown_lower_bound_does_not_become_exclusion(self):
        p = policy([("a", 100, "a|b|c|d"), ("b", 50, "e|b|c|d")])
        b = a.band(p, 100, .03)
        self.assertEqual(b["family_count"], 1)
        self.assertEqual(b["below_band_families_remain_unknown"], 1)

    def test_material_loss_and_runtime_are_independent_gates(self):
        records = quality_records()
        self.assertTrue(a.quality(records)["pass"])
        result = next(r for r in records if r.get("kind") == "light_policy_result")
        result["best"]["formula_dps"] = 98
        result["seconds"] = 80
        q = a.quality(records)
        self.assertIn("light_leader_deficit_over_1_percent", q["failures"])
        self.assertIn("light_runtime_regression_over_max_10s_25percent", q["failures"])

    def test_partial_audit_can_disprove_quality_without_rescuing_reference(self):
        records = quality_records()
        records.append({"kind": "light_audit_attempt", "candidate": {"formula_dps": 102}, "completed_stages": 1})
        q = a.quality(records)
        self.assertEqual(q["frozen_reference"], 100)
        self.assertFalse(q["pass"])
        self.assertFalse(q["reference_rebased_after_audit"])

    def test_meaningful_direction_missing_despite_other_diverse_choices(self):
        records = quality_records()
        for r in records:
            if r.get("kind") == "hybrid_policy" and r["variant"].startswith("H_light"):
                r["ranking"][1]["package_key"] = "x:4|b:4|c:4|d:4"
                r["aliases_by_family"]["f2"] = ["x:4|b:4|c:4|d:4"]
        q = a.quality(records)
        self.assertEqual(q["missing_directions"], [(0, "e:4")])
        self.assertFalse(q["pass"])

    def test_exact_alias_proves_direction_without_new_diversity_slot(self):
        records = quality_records()
        for r in records:
            if r.get("kind") == "hybrid_policy" and r["variant"].startswith("H_light"):
                r["ranking"][1]["package_key"] = "x:4|b:4|c:4|d:4"
                r["aliases_by_family"]["f2"] += ["x:4|b:4|c:4|d:4"]
        self.assertTrue(a.quality(records)["pass"])

    def test_process_success_does_not_mean_pair_acceptance(self):
        result = a.evaluate({"phase": "study", "status": "pass"})
        self.assertFalse(result["acceptance_complete"])
        self.assertFalse(result["next_case_allowed"])

    def test_incomplete_policy_rejected_before_audit_can_hide_it(self):
        records = [{"kind": "preparation", "packages_per_wearer": 946}]
        records += [{"kind": "light_policy_result", "variant": v, "complete": False} for v in a.VARIANTS]
        with self.assertRaisesRegex(ValueError, "incomplete"):
            a.check_policy_contract(records)

    def test_wrong_prior_prototype_or_case_cannot_release_nilou(self):
        with self.assertRaises(ValueError):
            a.validate_prerequisite({"case": "chiori_lunar_crystallize"}, "p", "s")

    def test_inverse_transform_rejects_ambiguous_anchor(self):
        transformed, proof = transform("clock=360; search=old", [("clock=360", "clock=240")])
        self.assertEqual(transformed, "clock=240; search=old")
        self.assertTrue(proof["inverse_transformation_exact"])
        with self.assertRaises(RuntimeError):
            transform("clock=360; clock=360", [("clock=360", "clock=240")])


if __name__ == "__main__":
    unittest.main()
