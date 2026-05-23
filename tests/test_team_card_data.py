from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from hoyolab_export.artifact_build_snapshot import build_artifact_build_snapshot
from hoyolab_export.account_stat_sheet import (
    PROPERTY_TOTAL_ATK,
    PROPERTY_TOTAL_DEF,
    PROPERTY_TOTAL_HP,
    PROPERTY_WEAPON_BASE_ATK,
)
from hoyolab_export.artifact_db import connect_db, create_build_preset, init_db
from hoyolab_export.catalog_sanity import STATUS_SPECIAL_DEFERRED
from hoyolab_export.character_stat_snapshot import (
    WARNING_ARTIFACT_SUMMARY_MISSING,
    WARNING_FINAL_TOTALS_NOT_COMPUTED,
    WARNING_TRAVELER_SPECIAL_DEFERRED,
)
from hoyolab_export.display_stat_effects import rebuild_weapon_passive_tooltips
from hoyolab_export.team_card_data import (
    BUILD_IDENTITY_SOURCE_BUILD_ID,
    DATA_STATUS_PARTIAL,
    DATA_STATUS_READY,
    DATA_STATUS_UNSUPPORTED,
    ERROR_BUILD_PRESET_NOT_FOUND,
    WARNING_ARTIFACT_BUILD_SNAPSHOT_MISSING_FOR_SELECTED_BUILD,
    TeamCardDataError,
    build_character_details_data,
    build_character_details_data_with_build_id,
)
from hoyolab_export.weapon_stats_catalog import (
    WeaponReferenceField,
    WeaponReferenceInfo,
    WeaponStatsCatalog,
    WeaponStatsEntry,
)
from tests.test_artifact_build_snapshot import build_preset, raw_summary
from tests.test_character_stat_snapshot import character_entry, weapon_entry


class TeamCardDataTest(unittest.TestCase):
    def test_character_weapon_build_snapshot_creates_details_data(self) -> None:
        artifact_snapshot = build_artifact_build_snapshot(
            raw_summary(),
            build_preset=build_preset(),
        )
        data = build_character_details_data(
            account_character={
                "id": 10000021,
                "name": "Amber",
                "level": 1,
                "constellation": 6,
            },
            character_stats_entry=character_entry(),
            account_weapon={
                "id": 15403,
                "name": "Favonius Warbow",
                "level": 1,
                "refinement": 5,
                "type_name": "Bow",
            },
            weapon_stats_entry=weapon_entry(),
            artifact_build_snapshot=artifact_snapshot,
            selected_build_id=7,
        )

        self.assertEqual(data.status, DATA_STATUS_READY)
        self.assertEqual(data.selected_build.build_id, 7)
        self.assertEqual(data.selected_build.identity_source, BUILD_IDENTITY_SOURCE_BUILD_ID)
        self.assertIsNotNone(data.stat_snapshot)
        snapshot = data.to_dict()["stat_snapshot"]
        self.assertEqual(snapshot["artifact"]["summary"]["build_id"], 7)
        self.assertEqual(snapshot["account_weapon"]["refinement"], 5)
        self.assertIn(WARNING_FINAL_TOTALS_NOT_COMPUTED, data.warnings)
        self.assertFalse(_contains_forbidden_key(data.to_dict(), {"icon", "local_path", "debug"}))

    def test_details_data_carries_explicit_weapon_passive_reference(self) -> None:
        data = build_character_details_data(
            account_character={
                "id": 10000021,
                "name": "Amber",
                "level": 1,
                "constellation": 6,
            },
            character_stats_entry=character_entry(),
            account_weapon={
                "id": 15403,
                "name": "Favonius Warbow",
                "level": 1,
                "refinement": 5,
                "type_name": "Bow",
                "description": "Flavor text, not passive.",
            },
            weapon_stats_entry=weapon_entry(with_passive=True),
            weapon_passive_reference={
                "passive_name": "Windfall",
                "passive_text": "CRIT Hits have a chance to generate Elemental Particles.",
                "language": "en-us",
            },
        )

        passive = data.to_dict()["weapon_passive_reference"]
        self.assertEqual(passive["passive_name"], "Windfall")
        self.assertIn("Particles", passive["passive_text"])

    def test_build_id_loader_reads_weapon_passive_tooltip_from_sqlite(self) -> None:
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
                                values=("Критические атаки создают элементальные частицы.",),
                            ),
                        )
                    ),
                ),
            ),
        )
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                rebuild_weapon_passive_tooltips(
                    conn,
                    weapon_catalog=catalog,
                    weapon_wiki={"13407": "https://wiki.hoyolab.com/pc/genshin/entry/2046"},
                    language="ru-ru",
                )
                conn.commit()

            data = build_character_details_data_with_build_id(
                account_character={
                    "id": 10000050,
                    "name": "Thoma",
                    "level": 70,
                    "constellation": 6,
                },
                account_weapon={
                    "id": 13407,
                    "name": "Копьё Фавония",
                    "level": 70,
                    "refinement": 5,
                    "type_name": "Древковое",
                    "description": "Лорное описание, не пассивка.",
                },
                build_id=None,
                db_path=db_path,
                source_notes={"content_language": "ru-ru"},
            )

        passive = data.to_dict()["weapon_passive_reference"]
        self.assertEqual(passive["passive_name"], "Дружественный бриз")
        self.assertIn("элементальные частицы", passive["passive_text"])
        self.assertNotIn("Лорное описание", passive["passive_text"])

    def test_details_data_carries_account_stat_sheet_and_ascension_bonus_reference(self) -> None:
        data = build_character_details_data(
            account_character={
                "id": 10000021,
                "name": "Amber",
                "level": 20,
                "constellation": 6,
            },
            character_stats_entry=character_entry(),
            account_weapon={
                "id": 15403,
                "name": "Favonius Warbow",
                "level": 20,
                "refinement": 5,
                "type_name": "Bow",
            },
            weapon_stats_entry=weapon_entry(),
            account_detail_record={
                "base": {"id": 10000021, "name": "Amber"},
                "base_properties": [
                    {"property_type": PROPERTY_TOTAL_HP, "base": "2630", "add": "1200", "final": "3830"},
                    {"property_type": PROPERTY_TOTAL_ATK, "base": "187", "add": "40", "final": "227"},
                    {"property_type": PROPERTY_TOTAL_DEF, "base": "167", "add": "12", "final": "179"},
                ],
                "extra_properties": [
                    {"property_type": 20, "base": "5.0%", "add": "", "final": "5.0%"},
                ],
                "element_properties": [],
                "selected_properties": [],
                "weapon": {
                    "id": 15403,
                    "name": "Favonius Warbow",
                    "level": 20,
                    "affix_level": 5,
                    "promote_level": 1,
                    "desc": "Reference passive text.",
                    "main_property": {
                        "property_type": PROPERTY_WEAPON_BASE_ATK,
                        "base": "",
                        "add": "",
                        "final": "125",
                    },
                    "sub_property": {
                        "property_type": 23,
                        "base": "",
                        "add": "",
                        "final": "23.6%",
                    },
                },
            },
        )

        data_dict = data.to_dict()
        stat_sheet = data_dict["account_stat_sheet"]

        self.assertEqual(stat_sheet["character_id"], "10000021")
        self.assertEqual(stat_sheet["base_properties"][0]["property_type"], PROPERTY_TOTAL_HP)
        self.assertEqual(stat_sheet["weapon"]["main_property"]["final"], "125")
        self.assertEqual(stat_sheet["weapon"]["sub_property"]["property_type"], 23)
        self.assertEqual(stat_sheet["weapon"]["desc"], "Reference passive text.")
        self.assertEqual(data_dict["ascension_bonus"]["stat_type"], "ATK")
        self.assertIn("display_stats_source", data.source_notes)
        self.assertIn("ascension_bonus_source", data.source_notes)

    def test_missing_build_id_allows_character_weapon_without_artifact(self) -> None:
        data = build_character_details_data(
            account_character={"id": 10000021, "name": "Amber", "level": 1},
            character_stats_entry=character_entry(),
            account_weapon={"id": 15403, "name": "Favonius Warbow", "level": 1},
            weapon_stats_entry=weapon_entry(),
        )

        self.assertEqual(data.status, DATA_STATUS_PARTIAL)
        self.assertIsNone(data.selected_build.build_id)
        self.assertIn(WARNING_ARTIFACT_SUMMARY_MISSING, data.warnings)

    def test_selected_build_id_without_snapshot_warns_without_silent_fallback(self) -> None:
        data = build_character_details_data(
            account_character={"id": 10000021, "name": "Amber", "level": 1},
            character_stats_entry=character_entry(),
            account_weapon={"id": 15403, "name": "Favonius Warbow", "level": 1},
            weapon_stats_entry=weapon_entry(),
            selected_build_id=99,
        )

        self.assertEqual(data.selected_build.build_id, 99)
        self.assertIn(WARNING_ARTIFACT_SUMMARY_MISSING, data.warnings)
        self.assertIn(
            WARNING_ARTIFACT_BUILD_SNAPSHOT_MISSING_FOR_SELECTED_BUILD,
            data.warnings,
        )

    def test_invalid_build_id_from_db_is_clear_error(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                conn.commit()

            with self.assertRaises(TeamCardDataError) as ctx:
                build_character_details_data_with_build_id(
                    account_character={"id": 10000021, "name": "Amber", "level": 1},
                    character_stats_entry=character_entry(),
                    account_weapon={"id": 15403, "name": "Favonius Warbow", "level": 1},
                    weapon_stats_entry=weapon_entry(),
                    build_id=404,
                    db_path=db_path,
                )

        self.assertEqual(ctx.exception.code, ERROR_BUILD_PRESET_NOT_FOUND)

    def test_build_id_loader_keeps_db_outside_character_snapshot(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                build_id = seed_artifact_build(conn)
                conn.commit()

            data = build_character_details_data_with_build_id(
                account_character={"id": 10000021, "name": "Amber", "level": 1},
                character_stats_entry=character_entry(),
                account_weapon={"id": 15403, "name": "Favonius Warbow", "level": 1},
                weapon_stats_entry=weapon_entry(),
                build_id=build_id,
                db_path=db_path,
            )

        self.assertEqual(data.selected_build.build_id, build_id)
        self.assertTrue(data.source_notes["artifact_db_readonly"])
        self.assertEqual(data.stat_snapshot.artifact.summary["build_id"], build_id)

    def test_traveler_is_special_deferred(self) -> None:
        data = build_character_details_data(
            account_character={"id": 10000007, "name": "Traveler", "level": 90},
            character_stats_entry=character_entry(),
            account_weapon={"id": 15403, "name": "Favonius Warbow", "level": 90},
            weapon_stats_entry=weapon_entry(),
            character_readiness_status=STATUS_SPECIAL_DEFERRED,
        )

        self.assertEqual(data.status, DATA_STATUS_UNSUPPORTED)
        self.assertIn(WARNING_TRAVELER_SPECIAL_DEFERRED, data.warnings)
        self.assertIsNone(data.stat_snapshot.character_base)


class temp_artifact_db:
    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        return Path(self._tmp.name) / "artifacts.db"

    def __exit__(self, exc_type, exc, tb) -> None:
        self._tmp.cleanup()


def seed_artifact_build(conn) -> int:
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        """
        INSERT INTO artifacts (
            id,
            fingerprint,
            name,
            set_uid,
            set_name,
            pos,
            pos_name,
            rarity,
            level,
            main_property_type,
            main_property_name,
            main_property_value,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            "fingerprint-1",
            "Flower",
            "gladiators_finale",
            "Gladiator",
            1,
            "Flower",
            5,
            20,
            2,
            "HP",
            "4780",
            now,
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO artifact_substats (
            artifact_id,
            slot_index,
            property_type,
            property_name,
            value,
            times
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (1, 1, 20, "CRIT Rate", "12.5%", 3),
    )
    return create_build_preset(
        conn,
        name="TeamCard Build",
        slots={1: 1},
        targets=[],
    )


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, dict):
        return any(
            key in forbidden or _contains_forbidden_key(item, forbidden)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


if __name__ == "__main__":
    unittest.main()
