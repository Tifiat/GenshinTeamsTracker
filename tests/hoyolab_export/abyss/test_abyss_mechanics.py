from __future__ import annotations

import unittest

from hoyolab_export.abyss_mechanics import (
    CONFIDENCE_HIGH,
    AbyssMechanicTag,
    build_abyss_mechanics_report,
    parse_fandom_enemy_mechanics_wikitext,
)


LANDROVER_SNIPPET = """
{{Enemy Stats
|ability1 = Fury
|ability2 = Ward
|hp_ratio = 22
|hp_type = 2
|res_title = State
|resglobal = 70%
|resglobal2 = 10%
|resglobal3 = -60%
|resglobal4 = 150% Base (Spiral Abyss)
|resglobal5 = 50% Overheating (Spiral Abyss)
|resglobal6 = -20% Paralyzed (Spiral Abyss)
}}
{{Elemental Shield Data|Cryo|28}}
The Landrover creates a Cryo Ward, becomes immune to damage, and can be
Paralyzed. Depleting the ward deals 30% Current HP as True Physical DMG.
"""


CRAB_SNIPPET = """
{{Enemy Stats
|resglobal2 = 210% Shielded
|resglobal3 = 80% After Almighty Bombardment
|hp_ratio = 21.2
}}
Battle-Scarred mode creates Stoneborne Seeds. Bloom, Burgeon, Hyperbloom,
or Lunar-Bloom reactions are required to deplete the Ward. Stygian mode has
additional instant-kill text that should stay mode-specific.
"""


class AbyssMechanicsTest(unittest.TestCase):
    def test_structured_fields_and_tags_are_extracted(self) -> None:
        report = parse_fandom_enemy_mechanics_wikitext(
            LANDROVER_SNIPPET,
            enemy_name="Super-Heavy Landrover",
        )

        self.assertEqual(report.parser_confidence, CONFIDENCE_HIGH)
        self.assertIn("ability1", report.structured_fields_found)
        self.assertIn("elemental_shield_data", report.structured_fields_found)
        self.assertIn(AbyssMechanicTag.WARD_OR_BARRIER.value, report.mechanic_tags)
        self.assertIn(AbyssMechanicTag.STATE_RES_OVERRIDE.value, report.mechanic_tags)
        self.assertIn(AbyssMechanicTag.TRUE_DAMAGE_HP_EVENT.value, report.mechanic_tags)

    def test_mode_specific_and_reaction_tags_are_detected(self) -> None:
        report = parse_fandom_enemy_mechanics_wikitext(
            CRAB_SNIPPET,
            enemy_name="Battle-Scarred Rock Crab",
        )

        self.assertIn(AbyssMechanicTag.REACTION_REQUIREMENT.value, report.mechanic_tags)
        self.assertIn(AbyssMechanicTag.LUNAR_REQUIREMENT.value, report.mechanic_tags)
        self.assertIn(AbyssMechanicTag.MODE_SPECIFIC_STATS.value, report.mechanic_tags)
        self.assertIn("mode-specific", report.ui_warning_recommendation)

    def test_build_report_handles_multiple_pages(self) -> None:
        reports = build_abyss_mechanics_report(
            {
                "Super-Heavy Landrover": LANDROVER_SNIPPET,
                "Battle-Scarred Rock Crab": CRAB_SNIPPET,
            }
        )

        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[0].enemy_name, "Super-Heavy Landrover")


if __name__ == "__main__":
    unittest.main()
