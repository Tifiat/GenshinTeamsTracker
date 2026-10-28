"""Tests for the temporary 2026-05-16 Abyss fixture.

These tests intentionally pin the static fixture values from
docs/handoff/ABYSS_HP_FIXTURE.md. They do not test live current-period detection
and should not be carried forward unchanged once the real HoYoLAB/Fandom/
AnimeGameData update pipeline replaces the fixture.

When the parser/cache exists, keep separate tests for:
- the static research fixture, if it still exists as sample data;
- current-period detection from HoYoLAB;
- period/page matching;
- parsed HP totals.
"""

import unittest

from run_workspace.abyss.current_fixture import (
    CURRENT_HP_KIND,
    FALLBACK_HP_KIND,
    current_floor12_fixture,
)


class AbyssCurrentFixtureTest(unittest.TestCase):
    def test_fixture_uses_current_hoyolab_period_shape(self):
        fixture = current_floor12_fixture()

        self.assertEqual(fixture.period_id, "2026-05-16")
        self.assertEqual(fixture.period_start, "2026-05-16")
        self.assertEqual(fixture.period_end, "2026-06-16")
        self.assertEqual(fixture.floor_index, 12)
        self.assertEqual(fixture.floor_id, 1129)
        self.assertEqual(fixture.hp_multiplier_current, 3.75)
        self.assertEqual(fixture.hp_multiplier_fallback, 2.5)

    def test_fixture_has_three_chambers_and_two_sides(self):
        fixture = current_floor12_fixture()

        self.assertEqual(len(fixture.chambers), 3)
        self.assertEqual(fixture.chamber(1).side(1).chamber_index, 1)
        self.assertEqual(fixture.chamber(1).side(2).side, 2)
        self.assertEqual(fixture.chamber(2).display_level, 98)
        self.assertEqual(fixture.chamber(3).display_level, 100)

    def test_chamber_side_current_hp_totals_match_confirmed_fixture(self):
        fixture = current_floor12_fixture()

        self.assertEqual(fixture.side(1, 1).total_hp_for_kind(CURRENT_HP_KIND), 3_747_864)
        self.assertEqual(fixture.side(1, 2).total_hp_for_kind(CURRENT_HP_KIND), 5_451_439)
        self.assertEqual(fixture.side(2, 1).total_hp_for_kind(CURRENT_HP_KIND), 5_375_784)
        self.assertEqual(fixture.side(2, 2).total_hp_for_kind(CURRENT_HP_KIND), 17_033_821)
        self.assertEqual(fixture.side(3, 1).total_hp_for_kind(CURRENT_HP_KIND), 13_310_405)
        self.assertEqual(fixture.side(3, 2).total_hp_for_kind(CURRENT_HP_KIND), 22_844_061)

    def test_chamber_side_fallback_hp_totals_are_available_for_cross_check(self):
        fixture = current_floor12_fixture()

        self.assertEqual(fixture.side(1, 1).total_hp_for_kind(FALLBACK_HP_KIND), 2_498_576)
        self.assertEqual(fixture.side(1, 2).total_hp_for_kind(FALLBACK_HP_KIND), 3_634_293)
        self.assertEqual(fixture.side(2, 1).total_hp_for_kind(FALLBACK_HP_KIND), 3_583_856)
        self.assertEqual(fixture.side(2, 2).total_hp_for_kind(FALLBACK_HP_KIND), 11_355_881)
        self.assertEqual(fixture.side(3, 1).total_hp_for_kind(FALLBACK_HP_KIND), 8_873_603)
        self.assertEqual(fixture.side(3, 2).total_hp_for_kind(FALLBACK_HP_KIND), 15_229_374)

    def test_enemy_identity_and_notes_are_preserved_for_future_tooltips(self):
        fixture = current_floor12_fixture()
        enemy = fixture.side(1, 1).enemies[0]

        self.assertEqual(enemy.source_name, "Super-Heavy Landrover: Mechanized Fortress")
        self.assertEqual(enemy.monster_id, "23090101")
        self.assertEqual(enemy.level, 95)
        self.assertEqual(enemy.current_3_75_hp, 3_747_864)
        self.assertTrue(enemy.notes)


if __name__ == "__main__":
    unittest.main()