from __future__ import annotations

import unittest

from hoyolab_export.character_ascension_bonus import (
    MATCHED_BY_BASE_ATK,
    MATCHED_BY_BASE_DEF,
    MATCHED_BY_BASE_HP,
    WARNING_ASCENSION_BONUS_BASE_STAT_AMBIGUOUS,
    WARNING_ASCENSION_BONUS_BASE_STAT_NO_MATCH,
    extract_character_ascension_bonus_by_base_stats,
)
from hoyolab_export.character_stats_catalog import CharacterBaseStatsEntry


class CharacterAscensionBonusByBaseStatsTest(unittest.TestCase):
    def test_level_70_hp_match_before_selects_before_bonus(self) -> None:
        info = extract_character_ascension_bonus_by_base_stats(
            fake_entry(),
            account_level=70,
            base_hp="900",
        )

        self.assertEqual(info.selected_level_key, "Lv.70")
        self.assertEqual(info.selected_phase, "before")
        self.assertEqual(info.selected_source, MATCHED_BY_BASE_HP)
        self.assertEqual(info.stat_type, "Electro DMG Bonus")
        self.assertEqual(info.selected_value, "12%")
        self.assertNotIn(WARNING_ASCENSION_BONUS_BASE_STAT_NO_MATCH, info.warnings)

    def test_level_70_hp_match_after_selects_after_bonus(self) -> None:
        info = extract_character_ascension_bonus_by_base_stats(
            fake_entry(),
            account_level=70,
            base_hp="1000",
        )

        self.assertEqual(info.selected_phase, "after")
        self.assertEqual(info.selected_source, MATCHED_BY_BASE_HP)
        self.assertEqual(info.selected_value, "18%")

    def test_falls_back_to_def_when_hp_missing(self) -> None:
        info = extract_character_ascension_bonus_by_base_stats(
            fake_entry(),
            account_level=70,
            base_def="480",
        )

        self.assertEqual(info.selected_phase, "before")
        self.assertEqual(info.selected_source, MATCHED_BY_BASE_DEF)
        self.assertEqual(info.selected_value, "12%")

    def test_falls_back_to_derived_atk_when_hp_and_def_missing(self) -> None:
        info = extract_character_ascension_bonus_by_base_stats(
            fake_entry(),
            account_level=70,
            base_atk="200",
        )

        self.assertEqual(info.selected_phase, "after")
        self.assertEqual(info.selected_source, MATCHED_BY_BASE_ATK)
        self.assertEqual(info.selected_value, "18%")

    def test_no_match_does_not_select_bonus(self) -> None:
        info = extract_character_ascension_bonus_by_base_stats(
            fake_entry(),
            account_level=70,
            base_hp="12345",
        )

        self.assertEqual(info.selected_value, None)
        self.assertEqual(info.selected_source, "")
        self.assertIn(WARNING_ASCENSION_BONUS_BASE_STAT_NO_MATCH, info.warnings)

    def test_ambiguous_match_does_not_select_bonus(self) -> None:
        info = extract_character_ascension_bonus_by_base_stats(
            fake_entry(before_hp="1000", after_hp="1000"),
            account_level=70,
            base_hp="1000",
        )

        self.assertEqual(info.selected_value, None)
        self.assertEqual(info.selected_source, "")
        self.assertIn(WARNING_ASCENSION_BONUS_BASE_STAT_AMBIGUOUS, info.warnings)


def fake_entry(
    *,
    before_hp: str = "900",
    after_hp: str = "1000",
) -> CharacterBaseStatsEntry:
    return CharacterBaseStatsEntry.from_dict(
        {
            "entry_page_id": "9001",
            "name": "Test Beidou",
            "lang": "en-us",
            "rows": [
                {
                    "level_key": "Lv.70",
                    "base_hp": {
                        "before": before_hp,
                        "after": after_hp,
                    },
                    "base_atk": {
                        "before": "190",
                        "after": "200",
                    },
                    "base_def": {
                        "before": "480",
                        "after": "500",
                    },
                    "ascension_bonus_stat_type": "Electro DMG Bonus",
                    "ascension_bonus": {
                        "before": "12%",
                        "after": "18%",
                    },
                }
            ],
        }
    )


if __name__ == "__main__":
    unittest.main()
