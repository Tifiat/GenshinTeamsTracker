import unittest

from analyze import membership, observation, package_key, policy_band


class PracticalGroupsTests(unittest.TestCase):
    def test_fixed_reference_boundary_and_no_neighbor_chaining(self):
        self.assertEqual(membership(98, 100, .02), "demonstrated_in_band")
        self.assertEqual(membership(97.999, 100, .02), "below_band_lower_bound_only")
        # Each neighbor differs by less than 2%; the last is still outside
        # demonstrated membership against the single frozen 100 reference.
        self.assertEqual([membership(x, 100, .02) for x in (100, 98.1, 96.2)],
                         ["demonstrated_in_band", "demonstrated_in_band", "below_band_lower_bound_only"])
        self.assertEqual(membership(101, 100, .03), "demonstrated_in_band")

    def test_unknown_and_low_lower_bound_never_prove_exclusion(self):
        self.assertEqual(membership(None, 100, .03), "unknown")
        self.assertEqual(membership(0, 100, .03), "below_band_lower_bound_only")
        for reference, fraction in ((0, .02), (float("inf"), .02), (100, 0), (100, 1)):
            with self.assertRaises(ValueError):
                membership(98, reference, fraction)
        with self.assertRaises(ValueError):
            membership(float("nan"), 100, .02)

    def test_distinct_families_and_exact_aliases_count_separately(self):
        policy = {"ranking": [{"family": "f1", "formula_dps": 100, "package_key": "a:4"},
                              {"family": "f2", "formula_dps": 99, "package_key": "c:4"}],
                  "aliases_by_family": {"f1": ["a:4", "b:4"], "f2": ["c:4"]}}
        group = policy_band(policy, 100, .02)
        self.assertEqual((group["family_count"], group["exact_alias_count"]), (2, 3))
        self.assertEqual(group["alias_bearing_family_count"], 1)
        self.assertEqual(package_key([{"sets": None}]), "none")
        policy["aliases_by_family"]["f2"] = ["a:4"]
        with self.assertRaises(ValueError):
            policy_band(policy, 100, .02)

    def test_postselection_crossing_is_separate_and_does_not_rebase(self):
        policy = {"ranking": [{"family": "f", "formula_dps": 97, "package_key": "set:4"}],
                  "aliases_by_family": {"f": ["set:4"]}}
        record = {"kind": "common_h_audit_attempt", "completed_stages": 2,
                  "candidate": {"formula_family": "f", "formula_dps": 99,
                                "packages": [{"sets": [{"set_uid": "set", "count": 4}]}]}}
        point = observation(record, 8, policy, 100)
        self.assertTrue(point["bands"][0]["new_demonstrated_member"])
        self.assertFalse(point["bands"][1]["new_demonstrated_member"])
        self.assertFalse(point["credited_to_policy"])
        self.assertEqual(point["completed_stages"], 2)
        self.assertEqual(policy["ranking"][0]["formula_dps"], 97)
        record["candidate"]["formula_family"] = "previously_unseen"
        point = observation(record, 9, policy, 100)
        self.assertIsNone(point["policy_family_lower"])
        self.assertEqual(point["bands"][0]["policy_membership"], "unknown")
        self.assertTrue(point["bands"][0]["new_demonstrated_member"])
        self.assertFalse(point["package_alias_seen_in_policy"])


if __name__ == "__main__":
    unittest.main()
