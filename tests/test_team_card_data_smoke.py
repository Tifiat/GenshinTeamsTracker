from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from hoyolab_export.artifact_db import connect_db, create_build_preset, init_db
from hoyolab_export.account_storage import sync_account_storage_from_sources
from hoyolab_export.team_card_data_smoke import (
    ERROR_AMBIGUOUS_CHARACTER_NAME,
    ERROR_CHARACTER_NOT_FOUND,
    TeamCardDataSmokeError,
    build_team_card_data_smoke_report,
    build_team_card_data_smoke_report_from_paths,
    select_account_character_for_smoke,
)
from tests.test_account_storage import (
    fake_account_character,
    fake_account_details,
    fake_account_weapon,
)


class TeamCardDataSmokeTest(unittest.TestCase):
    def test_report_selects_ordinary_character_from_sqlite_by_name_and_build_id(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                build_id = seed_artifact_build(conn)
                sync_account_storage_from_sources(
                    conn,
                    account_characters=[fake_account_character(name="Amber")],
                    account_weapons=[fake_account_weapon(character_name="Amber")],
                    account_character_details=fake_account_details(character_name="Amber"),
                )
                conn.commit()

            report = build_team_card_data_smoke_report_from_paths(
                character_name="Amber",
                build_id=build_id,
                account_db_path=db_path,
                artifact_db_path=db_path,
            )

        self.assertEqual(report["selected_character"]["name"], "Amber")
        self.assertEqual(report["selected_character"]["talent_count"], 2)
        self.assertEqual(report["selected_weapon"]["refinement"], 5)
        self.assertEqual(report["selected_weapon"]["base_atk"], 100)
        self.assertEqual(report["selected_build"]["build_id"], build_id)
        self.assertTrue(report["character_details_data"]["has_stat_snapshot"])
        self.assertFalse(report["character_details_data"]["has_account_stat_sheet"])
        self.assertEqual(report["ascension_bonus"], None)
        self.assertTrue(report["artifact_contribution"]["present"])
        self.assertEqual(report["artifact_contribution"]["build_id"], build_id)
        self.assertEqual(report["source_notes"]["account_runtime_source"], "sqlite_account_storage")
        self.assertFalse(report["source_notes"]["raw_hoyolab_json_read"])

    def test_explicit_weapon_selector_does_not_use_equipped_provenance(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                build_id = seed_artifact_build(conn)
                conn.commit()

            report = build_team_card_data_smoke_report(
                account_characters=[
                    {
                        "id": 1001,
                        "name": "Amber",
                        "weapon_type": 13,
                        "base_hp": 1000,
                        "base_atk": 200,
                        "base_def": 500,
                    }
                ],
                weapon_stacks=[
                    {
                        "weapon_id": 2001,
                        "weapon_fingerprint": "provenance-choice",
                        "name": "Wrong Provenance Spear",
                        "weapon_type": 13,
                        "level": 90,
                        "refinement": 5,
                        "promote_level": 6,
                        "base_atk": 600,
                        "source_metadata": {"observed_character_ids": ["1001"]},
                    },
                    {
                        "weapon_id": 2002,
                        "weapon_fingerprint": "explicit-choice",
                        "name": "Explicit Spear",
                        "weapon_type": 13,
                        "level": 70,
                        "refinement": 1,
                        "promote_level": 4,
                        "base_atk": 400,
                        "source_metadata": {"observed_character_ids": ["9999"]},
                    },
                ],
                character_name="Amber",
                weapon_id=2002,
                weapon_level=70,
                weapon_refinement=1,
                weapon_promote_level=4,
                build_id=build_id,
                artifact_db_path=db_path,
                account_db_path=db_path,
            )

        self.assertEqual(report["selected_weapon"]["id"], "2002")
        self.assertEqual(report["selected_weapon"]["name"], "Explicit Spear")
        self.assertEqual(
            report["character_details_full"]["source_notes"]["selected_weapon_source"],
            "observed_stack_explicit_selector",
        )
        self.assertFalse(report["source_notes"]["raw_hoyolab_json_read"])

    def test_select_character_by_ambiguous_name_fails(self) -> None:
        with self.assertRaises(TeamCardDataSmokeError) as ctx:
            select_account_character_for_smoke(
                account_characters=[
                    {"id": 1, "name": "Amber"},
                    {"id": 2, "name": "Amber"},
                ],
                character_name="Amber",
            )

        self.assertEqual(ctx.exception.code, ERROR_AMBIGUOUS_CHARACTER_NAME)

    def test_select_missing_character_fails(self) -> None:
        with self.assertRaises(TeamCardDataSmokeError) as ctx:
            select_account_character_for_smoke(
                account_characters=[{"id": 1, "name": "Amber"}],
                character_name="Missing",
            )

        self.assertEqual(ctx.exception.code, ERROR_CHARACTER_NOT_FOUND)


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
        name="Smoke Build",
        slots={1: 1},
        targets=[],
    )


if __name__ == "__main__":
    unittest.main()
