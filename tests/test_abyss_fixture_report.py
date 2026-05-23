from __future__ import annotations

import unittest

from hoyolab_export.abyss_fixture_report import (
    build_abyss_fixture_report_from_wikitext,
)
from hoyolab_export.abyss_sources import (
    CONFIDENCE_FANDOM_FLOOR_SCALING_ESTIMATE,
    CONFIDENCE_SOURCE_LIKE_PERIOD_MULTIPLIER,
    CONFIDENCE_UNAVAILABLE,
    WARNING_ENEMY_DATA_UNAVAILABLE,
    normalize_enemy_name,
    parse_abyss_period_wikitext,
)


CURRENT_FLOOR_12_SNIPPET = """
== Floor 12 ==
{{Domain Enemies
|level1 = 95
|enemies1_1 = Super-Heavy Landrover: Mechanized Fortress
|enemies1_2 = Hydro Hilichurl Rogue // Lord of the Hidden Depths: Whisperer of Nightmares
|level2 = 98
|enemies2_1 = Fatui Electro Cicin Mage // Ruin Drake: Earthguard // Primo Geovishap (Cryo)
|enemies2_2 = Battle-Hardened Grounded Geoshroom
|level3 = 100
|enemies3_1 = Hexadecatonic Battle-Hardened Mandragora
|enemies3_2 = Ruin Guard // Battle-Scarred Rock Crab
}}
"""


class AbyssFixtureReportTest(unittest.TestCase):
    def test_parse_floor_12_chamber_sides(self) -> None:
        reports = parse_abyss_period_wikitext(CURRENT_FLOOR_12_SNIPPET, floor=12)

        self.assertEqual(len(reports), 6)
        first = reports[0]
        self.assertEqual(first.chamber_index, 1)
        self.assertEqual(first.side, "first")
        self.assertEqual(first.level, 95)
        self.assertEqual(first.enemies[0].name, "Super-Heavy Landrover: Mechanized Fortress")

    def test_report_reproduces_current_fixture_totals(self) -> None:
        report = build_abyss_fixture_report_from_wikitext(
            CURRENT_FLOOR_12_SNIPPET,
            period_url="https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors/2026-05-16",
        )

        first_side = report.chamber_sides[0]
        totals = {
            estimate.confidence: estimate.hp
            for estimate in first_side.total_hp_estimates
        }
        self.assertAlmostEqual(
            totals[CONFIDENCE_FANDOM_FLOOR_SCALING_ESTIMATE] or 0,
            2_498_576,
            delta=1,
        )
        self.assertAlmostEqual(
            totals[CONFIDENCE_SOURCE_LIKE_PERIOD_MULTIPLIER] or 0,
            3_747_864,
            delta=1,
        )

    def test_unknown_enemy_is_partial_not_crash(self) -> None:
        snippet = """
== Floor 12 ==
{{Domain Enemies
|level1 = 95
|enemies1_1 = Unknown Boss
}}
"""
        report = build_abyss_fixture_report_from_wikitext(snippet, period_url="x")

        enemy = report.chamber_sides[0].enemies[0]
        self.assertIn(WARNING_ENEMY_DATA_UNAVAILABLE, enemy.warnings)
        self.assertEqual(enemy.hp_estimates[0].confidence, CONFIDENCE_UNAVAILABLE)

    def test_enemy_normalization_keeps_variant_text(self) -> None:
        self.assertEqual(
            normalize_enemy_name("Primo Geovishap (Cryo)"),
            "primogeovishapcryo",
        )


if __name__ == "__main__":
    unittest.main()
