from __future__ import annotations

import unittest

from run_workspace.display_stats import (
    ATK_FLAT,
    ATK_PERCENT,
    CRIT_DAMAGE,
    CRIT_RATE,
    DEF_FLAT,
    DEF_PERCENT,
    DISPLAY_TOTALS_EXCLUDE_PASSIVES,
    DISPLAY_TOTALS_EXCLUDE_RESONANCE,
    DISPLAY_TOTALS_EXCLUDE_SET_FORMULAS,
    DISPLAY_TOTALS_SOURCE_TEAM_BUILDER_VIRTUAL_BUILD,
    ELEMENTAL_MASTERY,
    ENERGY_RECHARGE,
    ELECTRO_DAMAGE,
    HEALING_BONUS,
    HP_FLAT,
    HP_PERCENT,
    HYDRO_DAMAGE,
    PYRO_DAMAGE,
    TOTAL_ATK,
    TOTAL_DEF,
    TOTAL_HP,
    WEAPON_BASE_ATK,
    build_character_display_stats,
)


class CharacterDisplayStatsTest(unittest.TestCase):
    def test_display_totals_use_safe_bases_percent_bonuses_and_flat_bonuses(self) -> None:
        result = build_character_display_stats(
            {
                "stat_snapshot": {
                    "character_base": {
                        "base_hp": {"selected": "1000"},
                        "base_atk": {"selected": "100"},
                        "base_def": {"selected": "500"},
                        "ascension_bonus_stat_type": "ATK",
                        "ascension_bonus": {"selected": "20%"},
                    },
                    "weapon": {
                        "base_atk": {"selected": "400"},
                        "secondary_stat_type": "Energy Recharge",
                        "secondary_stat_value": "15%",
                        "passive_bonus": {"atk_percent": 999},
                    },
                    "artifact": {
                        "summary": {
                            "active_set_bonuses": [
                                {"piece_count": 2, "set_name": "Fake ATK 999%"},
                            ],
                            "stat_totals": [
                                {"property_type": HP_PERCENT, "raw_value": 10},
                                {"property_type": HP_FLAT, "raw_value": 300},
                                {"property_type": ATK_PERCENT, "raw_value": 30},
                                {"property_type": ATK_FLAT, "raw_value": 50},
                                {"property_type": DEF_PERCENT, "raw_value": 10},
                                {"property_type": DEF_FLAT, "raw_value": 55},
                                {"property_type": CRIT_RATE, "raw_value": 31.1},
                                {"property_type": CRIT_DAMAGE, "raw_value": 33.4},
                                {"property_type": ENERGY_RECHARGE, "raw_value": 10.2},
                                {"property_type": ELEMENTAL_MASTERY, "raw_value": 187},
                                {"property_type": HYDRO_DAMAGE, "raw_value": 0},
                                {"property_type": PYRO_DAMAGE, "raw_value": 46.6},
                                {"property_type": HEALING_BONUS, "raw_value": 15},
                            ],
                        }
                    },
                    "resonance_bonuses": {"atk_percent": 999},
                }
            }
        )

        rows = {row.label: row.value for row in result.rows}

        self.assertEqual(rows["HP"], "1400")
        self.assertEqual(rows["ATK"], "800")
        self.assertEqual(rows["DEF"], "605")
        self.assertEqual(rows["EM"], "187")
        self.assertEqual(rows["Crit Rate"], "36.1%")
        self.assertEqual(rows["Crit DMG"], "83.4%")
        self.assertEqual(rows["ER"], "125.2%")
        self.assertEqual(rows["Pyro DMG"], "46.6%")
        self.assertEqual(rows["Healing Bonus"], "15%")
        self.assertNotIn("Hydro DMG", rows)
        self.assertIn(DISPLAY_TOTALS_EXCLUDE_PASSIVES, result.notes)
        self.assertIn(DISPLAY_TOTALS_EXCLUDE_SET_FORMULAS, result.notes)
        self.assertIn(DISPLAY_TOTALS_EXCLUDE_RESONANCE, result.notes)

    def test_virtual_build_uses_hoyolab_bases_not_current_final_sheet_values(self) -> None:
        result = build_character_display_stats(
            {
                "account_stat_sheet": {
                    "base_properties": [
                        {"property_type": TOTAL_HP, "base": "1000", "add": "9000", "final": "10000"},
                        {"property_type": TOTAL_ATK, "base": "500", "add": "9000", "final": "9500"},
                        {"property_type": TOTAL_DEF, "base": "500", "add": "9000", "final": "9500"},
                    ],
                    "extra_properties": [
                        {"property_type": ELEMENTAL_MASTERY, "base": "999", "add": "", "final": "999"},
                        {"property_type": CRIT_RATE, "base": "99.9%", "add": "", "final": "99.9%"},
                        {"property_type": CRIT_DAMAGE, "base": "199.9%", "add": "", "final": "199.9%"},
                        {"property_type": ENERGY_RECHARGE, "base": "199.9%", "add": "", "final": "199.9%"},
                        {"property_type": HEALING_BONUS, "base": "0.0%", "add": "", "final": "0.0%"},
                    ],
                    "element_properties": [
                        {"property_type": PYRO_DAMAGE, "base": "99.9%", "add": "", "final": "99.9%"},
                        {"property_type": HYDRO_DAMAGE, "base": "0.0%", "add": "", "final": "0.0%"},
                    ],
                    "weapon": {
                        "main_property": {"property_type": WEAPON_BASE_ATK, "base": "", "add": "", "final": "400"},
                        "sub_property": {"property_type": ENERGY_RECHARGE, "base": "", "add": "", "final": "15%"},
                    },
                },
                "stat_snapshot": {
                    "character_base": {
                        "ascension_bonus_stat_type": "ATK",
                        "ascension_bonus": {"selected": "20%"},
                    },
                    "weapon": {
                        "base_atk": {"selected": "400"},
                        "secondary_stat_type": "Energy Recharge",
                        "secondary_stat_value": "15%",
                    },
                    "artifact": {
                        "summary": {
                            "active_set_bonuses": [{"piece_count": 4, "set_name": "Ignored Set"}],
                            "stat_totals": [
                                {"property_type": HP_PERCENT, "raw_value": 10},
                                {"property_type": HP_FLAT, "raw_value": 300},
                                {"property_type": ATK_PERCENT, "raw_value": 30},
                                {"property_type": ATK_FLAT, "raw_value": 50},
                                {"property_type": DEF_PERCENT, "raw_value": 10},
                                {"property_type": DEF_FLAT, "raw_value": 55},
                                {"property_type": CRIT_RATE, "raw_value": 31.1},
                                {"property_type": CRIT_DAMAGE, "raw_value": 33.4},
                                {"property_type": ENERGY_RECHARGE, "raw_value": 10.2},
                                {"property_type": ELEMENTAL_MASTERY, "raw_value": 187},
                                {"property_type": PYRO_DAMAGE, "raw_value": 46.6},
                                {"property_type": HEALING_BONUS, "raw_value": 15},
                            ],
                        }
                    },
                },
            }
        )

        self.assertEqual(
            [row.to_dict() for row in result.rows],
            [
                {"key": "hp", "label": "HP", "value": "1400", "icon_label": "HP"},
                {"key": "atk", "label": "ATK", "value": "800", "icon_label": "ATK"},
                {"key": "def", "label": "DEF", "value": "605", "icon_label": "DEF"},
                {"key": "em", "label": "EM", "value": "187", "icon_label": "EM"},
                {"key": "crit_rate", "label": "Crit Rate", "value": "36.1%", "icon_label": "CR"},
                {"key": "crit_damage", "label": "Crit DMG", "value": "83.4%", "icon_label": "CD"},
                {"key": "energy_recharge", "label": "ER", "value": "125.2%", "icon_label": "ER"},
                {"key": "pyro_dmg", "label": "Pyro DMG", "value": "46.6%", "icon_label": "PYRO"},
                {"key": "healing_bonus", "label": "Healing Bonus", "value": "15%", "icon_label": "HEAL"},
            ],
        )
        self.assertIn(DISPLAY_TOTALS_SOURCE_TEAM_BUILDER_VIRTUAL_BUILD, result.notes)
        self.assertIn(DISPLAY_TOTALS_EXCLUDE_SET_FORMULAS, result.notes)

    def test_no_preset_uses_base_and_weapon_only_not_hoyolab_equipped_finals(self) -> None:
        result = build_character_display_stats(
            {
                "account_stat_sheet": {
                    "base_properties": [
                        {"property_type": TOTAL_HP, "base": "1000", "add": "9000", "final": "10000"},
                        {"property_type": TOTAL_ATK, "base": "500", "add": "9000", "final": "9500"},
                        {"property_type": TOTAL_DEF, "base": "500", "add": "9000", "final": "9500"},
                    ],
                    "extra_properties": [
                        {"property_type": CRIT_RATE, "base": "99.9%", "add": "", "final": "99.9%"},
                        {"property_type": CRIT_DAMAGE, "base": "199.9%", "add": "", "final": "199.9%"},
                    ],
                    "weapon": {
                        "main_property": {"property_type": WEAPON_BASE_ATK, "base": "", "add": "", "final": "400"},
                        "sub_property": {"property_type": ENERGY_RECHARGE, "base": "", "add": "", "final": "15%"},
                    },
                }
            }
        )

        self.assertEqual(
            [row.to_dict() for row in result.rows],
            [
                {"key": "hp", "label": "HP", "value": "1000", "icon_label": "HP"},
                {"key": "atk", "label": "ATK", "value": "500", "icon_label": "ATK"},
                {"key": "def", "label": "DEF", "value": "500", "icon_label": "DEF"},
                {"key": "crit_rate", "label": "Crit Rate", "value": "5%", "icon_label": "CR"},
                {"key": "crit_damage", "label": "Crit DMG", "value": "50%", "icon_label": "CD"},
                {"key": "energy_recharge", "label": "ER", "value": "115%", "icon_label": "ER"},
            ],
        )

    def test_baseline_percent_stats_are_shown_when_no_bonus_exists(self) -> None:
        result = build_character_display_stats(
            {
                "stat_snapshot": {
                    "character_base": {
                        "base_hp": {"selected": "0"},
                        "base_atk": {"selected": "0"},
                        "base_def": {"selected": "0"},
                    }
                }
            }
        )

        self.assertEqual(
            [row.to_dict() for row in result.rows],
            [
                {"key": "crit_rate", "label": "Crit Rate", "value": "5%", "icon_label": "CR"},
                {"key": "crit_damage", "label": "Crit DMG", "value": "50%", "icon_label": "CD"},
                {"key": "energy_recharge", "label": "ER", "value": "100%", "icon_label": "ER"},
            ],
        )

    def test_uses_sqlite_account_character_and_weapon_fields_without_stat_sheet(self) -> None:
        result = build_character_display_stats(
            {
                "account_character": {
                    "base_hp": 1000,
                    "base_atk": 200,
                    "base_def": 500,
                    "ascension_bonus_stat_type": "ATK%",
                    "ascension_bonus_value": 10,
                },
                "account_weapon": {
                    "base_atk": 100,
                    "secondary_property_type": ENERGY_RECHARGE,
                    "secondary_stat_value": 25.2,
                },
                "stat_snapshot": {
                    "artifact": {
                        "summary": {
                            "stat_totals": [
                                {"property_type": HP_PERCENT, "raw_value": 20},
                                {"property_type": ATK_FLAT, "raw_value": 50},
                            ],
                        },
                    },
                },
            }
        )

        self.assertEqual(
            [row.to_dict() for row in result.rows],
            [
                {"key": "hp", "label": "HP", "value": "1200", "icon_label": "HP"},
                {"key": "atk", "label": "ATK", "value": "380", "icon_label": "ATK"},
                {"key": "def", "label": "DEF", "value": "500", "icon_label": "DEF"},
                {"key": "crit_rate", "label": "Crit Rate", "value": "5%", "icon_label": "CR"},
                {"key": "crit_damage", "label": "Crit DMG", "value": "50%", "icon_label": "CD"},
                {"key": "energy_recharge", "label": "ER", "value": "125.2%", "icon_label": "ER"},
            ],
        )

    def test_uses_only_matched_account_ascension_bonus_value(self) -> None:
        result = build_character_display_stats(
            {
                "account_character": {
                    "base_hp": 900,
                    "base_atk": 190,
                    "base_def": 480,
                    "ascension_bonus_stat_type": "Electro DMG Bonus",
                    "ascension_bonus_value": 12,
                },
                "account_weapon": {"base_atk": 100},
                "stat_snapshot": {
                    "artifact": {
                        "summary": {
                            "stat_totals": [
                                {"property_type": ELECTRO_DAMAGE, "raw_value": 0},
                            ],
                        }
                    }
                },
            }
        )

        rows = {row.label: row.value for row in result.rows}

        self.assertEqual(rows["Electro DMG"], "12%")
        self.assertNotEqual(rows["Electro DMG"], "18%")

    def test_unmatched_account_ascension_bonus_is_not_applied_when_storage_left_it_empty(self) -> None:
        result = build_character_display_stats(
            {
                "account_character": {
                    "base_hp": 900,
                    "base_atk": 190,
                    "base_def": 480,
                    "ascension_bonus_stat_type": "Electro DMG Bonus",
                    "ascension_bonus_value": None,
                },
                "account_weapon": {"base_atk": 100},
            }
        )

        rows = {row.label: row.value for row in result.rows}

        self.assertNotIn("Electro DMG", rows)

    def test_sqlite_account_base_ascension_atk_label_is_percent_bonus(self) -> None:
        result = build_character_display_stats(
            {
                "account_character": {
                    "base_hp": 1000,
                    "base_atk": 200,
                    "base_def": 500,
                    "ascension_bonus_stat_type": "ATK",
                    "ascension_bonus_value": 10,
                },
                "account_weapon": {"base_atk": 100},
            }
        )

        rows = {row.label: row.value for row in result.rows}

        self.assertEqual(rows["ATK"], "330")

    def test_sqlite_account_ascension_summary_atk_label_is_percent_bonus(self) -> None:
        result = build_character_display_stats(
            {
                "account_character": {
                    "base_hp": 1000,
                    "base_atk": 200,
                    "base_def": 500,
                },
                "account_weapon": {"base_atk": 100},
                "ascension_bonus": {
                    "stat_type": "ATK",
                    "selected_value": 10,
                    "source": "account_sqlite_character_reference",
                },
            }
        )

        rows = {row.label: row.value for row in result.rows}

        self.assertEqual(rows["ATK"], "330")

    def test_applies_static_artifact_and_weapon_effect_rows(self) -> None:
        result = build_character_display_stats(
            {
                "account_character": {
                    "base_hp": 1000,
                    "base_atk": 200,
                    "base_def": 500,
                },
                "account_weapon": {"base_atk": 100},
                "artifact_set_display_stat_effects": [
                    {
                        "stat_key": "ATK_PERCENT",
                        "value": 18,
                        "value_type": "percent_points",
                    },
                    {
                        "stat_key": "ALL_ELEMENTAL_DMG_BONUS",
                        "value": 12,
                        "value_type": "percent_points",
                    },
                ],
                "weapon_display_stat_effects": [
                    {
                        "stat_key": "HP_PERCENT",
                        "value": 20,
                        "value_type": "percent_points",
                    },
                    {
                        "formula_key": "ATK_FLAT_FROM_MAX_HP",
                        "value": 999,
                        "apply_enabled": 0,
                    },
                ],
            }
        )

        rows = {row.label: row.value for row in result.rows}

        self.assertEqual(rows["HP"], "1200")
        self.assertEqual(rows["ATK"], "354")
        self.assertEqual(rows["Pyro DMG"], "12%")
        self.assertEqual(rows["Dendro DMG"], "12%")
        self.assertNotIn("Physical DMG", rows)

    def test_external_bonus_toggle_excludes_only_static_effect_sources(self) -> None:
        result = build_character_display_stats(
            {
                "external_bonuses_enabled": False,
                "account_character": {
                    "base_hp": 1000,
                    "base_atk": 200,
                    "base_def": 500,
                },
                "account_weapon": {
                    "base_atk": 100,
                    "secondary_property_type": ENERGY_RECHARGE,
                    "secondary_stat_value": 25,
                },
                "stat_snapshot": {
                    "artifact": {
                        "summary": {
                            "stat_totals": [
                                {"property_type": HP_PERCENT, "raw_value": 10},
                                {"property_type": ATK_FLAT, "raw_value": 50},
                            ]
                        }
                    }
                },
                "artifact_set_display_stat_effects": [
                    {
                        "stat_key": "ATK_PERCENT",
                        "value": 18,
                        "value_type": "percent_points",
                    }
                ],
                "weapon_display_stat_effects": [
                    {
                        "stat_key": "HP_PERCENT",
                        "value": 20,
                        "value_type": "percent_points",
                    }
                ],
            }
        )

        rows = {row.label: row.value for row in result.rows}

        self.assertEqual(rows["HP"], "1100")
        self.assertEqual(rows["ATK"], "350")
        self.assertEqual(rows["ER"], "125%")

    def test_ignores_unsupported_static_effect_rows(self) -> None:
        result = build_character_display_stats(
            {
                "account_character": {"base_hp": 1000},
                "weapon_display_stat_effects": [
                    {
                        "stat_key": "ELEMENTAL_SKILL_DMG_BONUS",
                        "value": 20,
                        "value_type": "percent_points",
                    }
                ],
            }
        )

        rows = {row.label: row.value for row in result.rows}

        self.assertNotIn("Elemental Skill DMG", rows)


if __name__ == "__main__":
    unittest.main()
