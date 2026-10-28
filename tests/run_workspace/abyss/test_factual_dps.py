"""Pure tests for HP/time factual DPS math.

These tests should stay valid after the static Abyss fixture is replaced by a
real parser/cache, because they only verify calculation behavior and unavailable
states, not live period detection.
"""

import unittest

from run_workspace.abyss.current_fixture import (
    CURRENT_HP_KIND,
    FALLBACK_HP_KIND,
    current_floor12_fixture,
)
from run_workspace.abyss.factual_dps import (
    REASON_MISSING_HP,
    REASON_ZERO_OR_NEGATIVE_TIME,
    calculate_factual_dps,
    calculate_side_factual_dps,
)


class AbyssFactualDpsTest(unittest.TestCase):
    def test_calculates_factual_dps_from_hp_and_elapsed_seconds(self):
        result = calculate_factual_dps(total_hp=3_747_864, elapsed_seconds=120)

        self.assertTrue(result.is_available)
        self.assertAlmostEqual(result.dps or 0.0, 31_232.2)
        self.assertEqual(result.rounded_dps, 31_232)

    def test_missing_hp_is_unavailable(self):
        result = calculate_factual_dps(total_hp=None, elapsed_seconds=120)

        self.assertFalse(result.is_available)
        self.assertEqual(result.unavailable_reason, REASON_MISSING_HP)
        self.assertIsNone(result.rounded_dps)

    def test_zero_or_negative_elapsed_seconds_is_unavailable(self):
        zero = calculate_factual_dps(total_hp=3_747_864, elapsed_seconds=0)
        negative = calculate_factual_dps(total_hp=3_747_864, elapsed_seconds=-1)

        self.assertFalse(zero.is_available)
        self.assertEqual(zero.unavailable_reason, REASON_ZERO_OR_NEGATIVE_TIME)
        self.assertFalse(negative.is_available)
        self.assertEqual(negative.unavailable_reason, REASON_ZERO_OR_NEGATIVE_TIME)

    def test_calculates_from_current_side_fixture(self):
        fixture = current_floor12_fixture()
        side = fixture.side(1, 2)

        result = calculate_side_factual_dps(
            side,
            elapsed_seconds=180,
            hp_kind=CURRENT_HP_KIND,
        )

        self.assertTrue(result.is_available)
        self.assertAlmostEqual(result.dps or 0.0, 30_285.772222222223)

    def test_can_calculate_from_fallback_hp_for_cross_check(self):
        fixture = current_floor12_fixture()
        side = fixture.side(1, 2)

        result = calculate_side_factual_dps(
            side,
            elapsed_seconds=180,
            hp_kind=FALLBACK_HP_KIND,
        )

        self.assertTrue(result.is_available)
        self.assertAlmostEqual(result.dps or 0.0, 20_190.516666666666)


if __name__ == "__main__":
    unittest.main()