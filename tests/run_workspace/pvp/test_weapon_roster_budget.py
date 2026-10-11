import unittest

from run_workspace.pvp.abyss_rules import AbyssRuleset, evaluate_deck
from run_workspace.pvp.weapon_roster_budget import (
    CUP_SOURCE, CUP_WEAPON_TEXT, CUP_WEAPON_PARAGRAPH, build_weapon_roster_report, parse_weapon_budget_text,
)
from tests.run_workspace.pvp.test_abyss_rules import _source, _deck, _weapon


def cup_rules(prices=(130, 25)):
    system, agents, engines = _source()
    system.update(_id=CUP_SOURCE["system_id"], root=CUP_SOURCE["root_id"],
                  updatedAt=CUP_SOURCE["updated_at"])
    system["draft"]["minMaxCosts"]["engines"] = [0, 0]
    for row, price in zip(system["costs"]["engines"], prices):
        row.update(costs=[price] * 5 + [0], bis=[])
    return AbyssRuleset.from_source(system, agents, engines)


def report(prices, *, snapshot=None, count=None):
    return build_weapon_roster_report(snapshot or cup_rules().to_dict(),
                                     [{"base_unit_cost": price, "count": count} for price in prices])


class WeaponRosterBudgetTest(unittest.TestCase):
    def test_two_pool_boundaries_and_cheap_weapons_can_spend_general_pool(self):
        # The 25 reserve is not an independent maximum on all cheap weapons.
        for prices, expected in (((130, 14, 11), ("pass", "pass")),
                                 ((100, 14, 14, 12), ("pass", "pass")),
                                 ((131,), ("pass", "fail")),
                                 ((130, 14, 12), ("fail", "pass")),
                                 ((14,) * 12, ("fail", "pass"))):
            with self.subTest(prices=prices):
                result = report(prices)
                self.assertEqual(tuple(row["status"] for row in result["checks"]), expected)
                self.assertEqual(result["total"], sum(prices))

    def test_refinement_entry_price_is_counted_once_not_inventory_copies(self):
        self.assertEqual(report((14, 15), count=100)["total"], 29)
        self.assertEqual(report((14, 15), count=None)["total"], 29)
        self.assertEqual(report((14, 15))["expensive_total"], 15)
        self.assertEqual(report((0, 0))["total"], 0)
        self.assertEqual(report(())["total"], 0)

    def test_missing_prices_and_threshold_gap_never_claim_a_pass(self):
        result = report((None, 40))
        self.assertEqual(result["known_total"], 40)
        self.assertIsNone(result["total"])
        self.assertEqual(result["unknown_price_count"], 1)
        self.assertEqual([row["status"] for row in result["checks"]], ["unknown", "unknown"])
        gap = report((14.5,))
        self.assertEqual(gap["checks"][0]["status"], "pass")
        self.assertEqual(gap["checks"][1]["status"], "unknown")

    def test_structured_bounds_precede_prose_fallback(self):
        snapshot = cup_rules().to_dict()
        snapshot["bounds"]["engines"]["cost"] = [0, 100]
        result = report((105,), snapshot=snapshot)
        self.assertEqual(result["policy"]["source_kind"], "api")
        self.assertEqual(len(result["checks"]), 1)
        self.assertEqual(result["checks"][0]["status"], "fail")
        snapshot["bounds"]["engines"]["cost"] = [20, 0]
        self.assertEqual(report((19,), snapshot=snapshot)["checks"][0]["status"], "fail")

    def test_no_policy_other_version_still_has_a_current_counter(self):
        for key in CUP_SOURCE:
            snapshot = cup_rules().to_dict()
            snapshot["source"][key] += "changed"
            result = report((14, 15), snapshot=snapshot)
            self.assertIsNone(result["policy"])
            self.assertEqual(result["total"], 29)
            self.assertEqual(result["checks"], [])

    def test_bounded_parser_understands_only_the_supported_rule(self):
        parsed = parse_weapon_budget_text(CUP_WEAPON_TEXT)
        self.assertEqual((parsed["maximum"], parsed["general_pool"], parsed["cheap_pool"]), (155, 130, 25))
        self.assertEqual(parse_weapon_budget_text(CUP_WEAPON_TEXT.replace(" ", "\n")), parsed)
        self.assertEqual(parse_weapon_budget_text(CUP_WEAPON_TEXT.replace("≤", "<=").replace("≥", ">=")), parsed)
        self.assertEqual(parse_weapon_budget_text(CUP_WEAPON_PARAGRAPH), parsed)
        with self.assertRaises(ValueError):
            parse_weapon_budget_text(CUP_WEAPON_PARAGRAPH.replace("(130)", "(129)"))
        for text in (CUP_WEAPON_TEXT.replace("≤155", "≤154"),
                     CUP_WEAPON_TEXT.replace("эти 25", "эти 24"),
                     CUP_WEAPON_TEXT.replace("≥15", "≥16"),
                     CUP_WEAPON_TEXT + " Изменённое правило.", "x" * 5000, None):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_weapon_budget_text(text)

    def test_evaluator_uses_roster_cost_for_deck_admission(self):
        rules = cup_rules((131, 14))
        deck = _deck(weapons=(_weapon("2001", 1, 24), _weapon("2002", 1, None)))
        evaluated = evaluate_deck(deck, rules)
        self.assertEqual(evaluated.weapon_roster["total"], 145)
        self.assertIn("weapon_roster_expensive_exceeded", [issue.code for issue in evaluated.issues])
        payload = evaluated.to_dict()
        self.assertEqual(payload["weapon_roster"]["known_total"], 145)
        self.assertFalse(any(issue.code == "zero_upper_bound_unverified"
                             and issue.details.get("group") == "engines" and issue.details.get("metric") == "cost"
                             for issue in evaluated.issues))
        # Existing inventory availability is still unknown; the rule counter is known.
        self.assertIsNone(evaluated.weapon_count)
        self.assertIsNone(evaluated.weapon_total)


if __name__ == "__main__":
    unittest.main()
