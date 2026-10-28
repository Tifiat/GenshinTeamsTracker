from __future__ import annotations

from contextlib import closing
import unittest

from hoyolab_export.artifact_db import (
    connect_db,
    init_db,
    upsert_artifact_set_bonus_description,
)
from hoyolab_export.display_stat_effects import (
    detect_static_display_stat_effects,
    detect_weapon_static_display_stat_effects,
    get_weapon_passive_tooltip,
    list_weapon_display_stat_effects,
    list_artifact_set_display_stat_effects_for_active_sets,
    rebuild_artifact_set_display_stat_effects,
    rebuild_weapon_passive_tooltips,
    rebuild_weapon_display_stat_effects,
)
from hoyolab_export.weapon_stats_catalog import (
    WeaponReferenceField,
    WeaponReferenceInfo,
    WeaponStatsCatalog,
    WeaponStatsEntry,
)
from tests.hoyolab_export.account.test_account_storage import temp_artifact_db


class DisplayStatEffectsTest(unittest.TestCase):
    def test_detects_direct_artifact_display_stats(self) -> None:
        cases = {
            "ATK +18%.": ("ATK_PERCENT", 18.0, "percent_points"),
            "Max HP increased by 1000.": ("HP_FLAT", 1000.0, "flat"),
            "Increases Elemental Mastery by 80.": ("ELEMENTAL_MASTERY", 80.0, "flat"),
            "Physical DMG +25%": ("PHYSICAL_DMG_BONUS", 25.0, "percent_points"),
            "Healing Bonus +15%.": ("HEALING_BONUS", 15.0, "percent_points"),
        }

        for text, expected in cases.items():
            with self.subTest(text=text):
                effects = detect_static_display_stat_effects(text)
                self.assertEqual(len(effects), 1)
                self.assertEqual(
                    (effects[0].stat_key, effects[0].value, effects[0].value_type),
                    expected,
                )

    def test_rejects_conditional_or_unsupported_artifact_stats(self) -> None:
        self.assertEqual(
            detect_static_display_stat_effects("Increases Elemental Skill DMG by 20%."),
            (),
        )
        self.assertEqual(
            detect_static_display_stat_effects(
                "When the equipping character is off-field, Lunar Reaction DMG is increased by 20%."
            ),
            (),
        )

    def test_artifact_bonus_description_upsert_populates_effect_table(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                conn.execute(
                    """
                    INSERT INTO artifact_sets (set_uid, hoyowiki_entry_id, fallback_name, updated_at)
                    VALUES ('TestSet', '9001', 'Test Set', 'now')
                    """
                )
                upsert_artifact_set_bonus_description(
                    conn,
                    set_uid="TestSet",
                    lang="en-us",
                    piece_count=2,
                    description="ATK +18%.",
                )
                effects = list_artifact_set_display_stat_effects_for_active_sets(
                    conn,
                    [{"set_uid": "TestSet", "piece_count": 2}],
                )

        self.assertEqual(
            effects,
            [
                {
                    "set_uid": "TestSet",
                    "pieces_required": 2,
                    "stat_key": "ATK_PERCENT",
                    "value": 18.0,
                    "value_type": "percent_points",
                    "description": "ATK +18%.",
                }
            ],
        )

    def test_artifact_bonus_description_prefers_requested_language_with_english_fallback(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                conn.execute(
                    """
                    INSERT INTO artifact_sets (set_uid, hoyowiki_entry_id, fallback_name, updated_at)
                    VALUES ('TestSet', '9001', 'Test Set', 'now')
                    """
                )
                upsert_artifact_set_bonus_description(
                    conn,
                    set_uid="TestSet",
                    lang="en-us",
                    piece_count=2,
                    description="ATK +18%.",
                )
                upsert_artifact_set_bonus_description(
                    conn,
                    set_uid="TestSet",
                    lang="ru",
                    piece_count=2,
                    description="Сила атаки +18%.",
                )
                preferred = list_artifact_set_display_stat_effects_for_active_sets(
                    conn,
                    [{"set_uid": "TestSet", "piece_count": 2}],
                    preferred_lang="ru",
                )
                fallback = list_artifact_set_display_stat_effects_for_active_sets(
                    conn,
                    [{"set_uid": "TestSet", "piece_count": 2}],
                    preferred_lang="pt-br",
                )

        self.assertEqual(preferred[0]["description"], "Сила атаки +18%.")
        self.assertEqual(fallback[0]["description"], "ATK +18%.")

    def test_rebuild_skips_conditional_rows(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                conn.execute(
                    """
                    INSERT INTO artifact_sets (set_uid, hoyowiki_entry_id, fallback_name, updated_at)
                    VALUES ('ConditionalSet', '9002', 'Conditional Set', 'now')
                    """
                )
                upsert_artifact_set_bonus_description(
                    conn,
                    set_uid="ConditionalSet",
                    lang="en-us",
                    piece_count=2,
                    description="When Nightsoul points change, CRIT Rate increases by 40%.",
                )
                self.assertEqual(rebuild_artifact_set_display_stat_effects(conn), 0)

    def test_detects_weapon_refinement_values(self) -> None:
        rows = detect_weapon_static_display_stat_effects(
            "Increases ATK by 16%/20%/24%/28%/32%."
        )

        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(rows[0][1].stat_key, "ATK_PERCENT")
        self.assertEqual(rows[0][1].value, 16.0)
        self.assertEqual(rows[4][0], 5)
        self.assertEqual(rows[4][1].value, 32.0)

    def test_detects_direct_weapon_stat_with_additionally_prefix(self) -> None:
        rows = detect_weapon_static_display_stat_effects(
            "Additionally, the wielder's DEF is increased by 20%/25%/30%/35%/40%."
        )

        self.assertEqual(rows[0][1].stat_key, "DEF_PERCENT")
        self.assertEqual(rows[0][1].value, 20.0)

    def test_detects_direct_weapon_stat_before_unsupported_neighbor(self) -> None:
        rows = detect_weapon_static_display_stat_effects(
            "Increases CRIT Rate by 8%/10%/12%/14%/16% and increases Normal ATK SPD by 12%."
        )

        self.assertEqual(rows[0][1].stat_key, "CRIT_RATE")
        self.assertEqual(rows[0][1].value, 8.0)

        rows = detect_weapon_static_display_stat_effects(
            "Healing Bonus increased by 10%/12.5%/15%/17.5%/20%, "
            "Normal Attack DMG is increased by 1%/1.5%/2%/2.5%/3% of Max HP."
        )

        self.assertEqual(rows[0][1].stat_key, "HEALING_BONUS")
        self.assertEqual(rows[0][1].value, 10.0)

    def test_rejects_scoped_or_conditional_weapon_stats(self) -> None:
        cases = (
            "Increases Elemental Skill CRIT Rate by 8%/10%/12%/14%/16%.",
            "Using an Elemental Skill increases DEF by 16%/20%/24%/28%/32% for 15s.",
            "Using an Elemental Burst grants a 12% increase in ATK and Movement SPD for 15s.",
            "If a Normal or Charged Attack hits a target within 0.3s of being fired, increases DMG by 36%.",
            "Increases Elemental Burst DMG by 16% and Elemental Burst CRIT Rate by 6%.",
            "Increases Normal ATK SPD by 12%.",
        )

        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(detect_weapon_static_display_stat_effects(text), ())

    def test_weapon_rebuild_uses_entry_page_id_to_weapon_id_mapping(self) -> None:
        catalog = WeaponStatsCatalog(
            entries=(
                WeaponStatsEntry(
                    entry_page_id="1972",
                    name="Staff of Homa",
                    lang="en-us",
                    reference_info=WeaponReferenceInfo(
                        passive_fields=(
                            WeaponReferenceField(
                                key="Reckless Cinnabar",
                                values=(
                                    "HP increased by 20%/25%/30%/35%/40%. "
                                    "Additionally, provides an ATK Bonus based on Max HP.",
                                ),
                            ),
                        )
                    ),
                ),
            )
        )
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                count = rebuild_weapon_display_stat_effects(
                    conn,
                    weapon_catalog=catalog,
                    weapon_wiki={"13501": "https://wiki.hoyolab.com/pc/genshin/entry/1972"},
                )
                effects = list_weapon_display_stat_effects(
                    conn,
                    weapon_id=13501,
                    refinement=1,
                )

        self.assertEqual(count, 5)
        self.assertEqual(effects[0]["stat_key"], "HP_PERCENT")
        self.assertEqual(effects[0]["value"], 20.0)

    def test_weapon_passive_tooltips_store_localized_passive_text(self) -> None:
        catalog = WeaponStatsCatalog(
            lang="ru-ru",
            entries=(
                WeaponStatsEntry(
                    entry_page_id="2046",
                    name="Копьё Фавония",
                    lang="ru-ru",
                    reference_info=WeaponReferenceInfo(
                        passive_fields=(
                            WeaponReferenceField(
                                key="Дружественный бриз",
                                values=(
                                    "Критические атаки имеют 60% шанс создать элементальные частицы.",
                                ),
                            ),
                        )
                    ),
                ),
            ),
        )
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                count = rebuild_weapon_passive_tooltips(
                    conn,
                    weapon_catalog=catalog,
                    weapon_wiki={"13407": "https://wiki.hoyolab.com/pc/genshin/entry/2046"},
                    language="ru-ru",
                )
                passive = get_weapon_passive_tooltip(
                    conn,
                    weapon_id=13407,
                    language="ru-ru",
                )

        self.assertEqual(count, 1)
        self.assertEqual(passive["passive_name"], "Дружественный бриз")
        self.assertIn("элементальные частицы", passive["passive_text"])
        self.assertEqual(passive["language"], "ru-ru")


if __name__ == "__main__":
    unittest.main()
