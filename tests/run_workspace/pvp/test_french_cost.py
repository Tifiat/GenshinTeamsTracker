from __future__ import annotations

import unittest

from hoyolab_export.traveler import traveler_variant_id

from run_workspace.pvp.abyss_rules import AbyssRulesError, AbyssRuleset
from run_workspace.pvp.french_cost import FrenchCostError, calculate_french_cost_difference
from tests.run_workspace.pvp.test_abyss_rules import _character, _deck, _source


def _rules(*, cap: int | float = 4, exempt_b: bool = True) -> AbyssRuleset:
    system, agents, engines = _source()
    system["costs"]["system"] = "FRENCH_COST"
    system["costs"]["costLimit"] = cap
    system["costs"]["agents"][1]["disableCostLimit"] = exempt_b
    return AbyssRuleset.from_source(system, agents, engines)


class FrenchCostDifferenceTests(unittest.TestCase):
    def test_union_variants_clamp_then_signed_sum(self) -> None:
        rules = _rules()
        left = _deck(
            _character("1001", "PYRO", constellation=6),
            _character("1002", "HYDRO"),
            _character("10000005", "ANEMO"),  # Lumine alias of the Anemo source row.
        )
        right = _deck(
            _character("1001", "PYRO"),
            _character(str(traveler_variant_id(10000007, "Dendro")), "DENDRO"),
        )
        report = calculate_french_cost_difference(left, right, rules)
        # A: +6→+4; exempt B: +15; Anemo: +5→+4; Dendro: -6→-4.
        self.assertEqual(report.signed_difference, 19)
        self.assertEqual(report.absolute_difference, 19)
        self.assertEqual(report.difference_cap, 4)

    def test_signed_cancellation_precedes_absolute_value(self) -> None:
        rules = _rules()
        left = _deck(_character("1001", "PYRO"))
        right = _deck(_character("1002", "HYDRO"))
        report = calculate_french_cost_difference(left, right, rules)
        self.assertEqual(report.signed_difference, -11)  # +4 capped, -15 exempt.
        self.assertEqual(report.absolute_difference, 11)

    def test_zero_cap_is_literal_and_exemption_still_applies(self) -> None:
        left = _deck(_character("1001", "PYRO"), _character("1002", "HYDRO"))
        empty = _deck()
        self.assertEqual(calculate_french_cost_difference(
            left, empty, _rules(cap=0)).signed_difference, 15)
        self.assertEqual(calculate_french_cost_difference(
            left, empty, _rules(cap=0, exempt_b=False)).absolute_difference, 0)

    def test_traveler_elements_remain_distinct_source_variants(self) -> None:
        rules = _rules()
        left = _deck(_character("10000005", "ANEMO"))
        right = _deck(_character(str(traveler_variant_id(10000007, "Dendro")), "DENDRO"))
        report = calculate_french_cost_difference(left, right, rules)
        self.assertEqual(report.signed_difference, 0)  # +4 and -4, not one shared game ID.

    def test_unknown_or_ambiguous_prices_fail_explicitly(self) -> None:
        rules = _rules()
        for character in (
            _character("1001", "PYRO", constellation=None),
            _character("9999", "PYRO"),
            _character("10000007", ""),
            _character(str(traveler_variant_id(10000005, "Pyro")), "HYDRO"),
        ):
            with self.subTest(character=character), self.assertRaises(FrenchCostError) as raised:
                calculate_french_cost_difference(_deck(character), _deck(), rules)
            self.assertEqual(raised.exception.code, "french_cost_price_unknown")

    def test_requires_french_mode_and_nonnegative_cap(self) -> None:
        default = AbyssRuleset.from_source(*_source())
        with self.assertRaises(FrenchCostError) as raised:
            calculate_french_cost_difference(_deck(), _deck(), default)
        self.assertEqual(raised.exception.code, "french_cost_mode_required")
        system, agents, engines = _source()
        system["costs"]["system"] = "FRENCH_COST"
        system["costs"].pop("costLimit")
        with self.assertRaises(AbyssRulesError):
            AbyssRuleset.from_source(system, agents, engines)
        system["costs"]["costLimit"] = -1
        with self.assertRaises(AbyssRulesError):
            AbyssRuleset.from_source(system, agents, engines)

    def test_bundle_adjustment_is_not_in_difference(self) -> None:
        rules = _rules()
        left = _deck(_character("1001", "PYRO"), _character("1002", "HYDRO", constellation=2))
        report = calculate_french_cost_difference(left, _deck(), rules)
        self.assertEqual(report.signed_difference, 19)  # +4 capped A, +15 exempt B.


if __name__ == "__main__":
    unittest.main()
