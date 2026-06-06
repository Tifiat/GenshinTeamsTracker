from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from run_workspace.gcsim.account_prepared_config import (
    DEFAULT_ACCOUNT_CHASCA_TEAM,
    WARNING_DEV_WEAPON_CANDIDATE_NOT_ACCOUNT_TRUTH,
    WARNING_SYNTHETIC_DEV_ARTIFACT_STATS_NOT_ACCOUNT_TRUTH,
    WARNING_TALENT_LEVEL_CAPPED_TO_GCSIM_PARSER_RANGE,
    build_account_prepared_full_config_report,
    build_account_prepared_team_payload,
)


class GcsimAccountPreparedConfigTest(unittest.TestCase):
    def test_account_character_uses_stored_gcsim_key_not_localized_name(self) -> None:
        with seeded_account_config_db() as db_path:
            result = build_account_prepared_team_payload(
                db_path=db_path,
                team_names=("Chasca",),
            )

        self.assertTrue(result.ready)
        character = result.payload["characters"][0]
        self.assertEqual(character["mapping"]["gcsim_key"], "chasca")
        self.assertEqual(character["display_name"], "Chasca")
        self.assertNotEqual(character["mapping"]["gcsim_key"], "Локализованная Chasca")
        self.assertEqual(
            result.characters[0].account_character["localized_name"],
            "Локализованная Chasca",
        )

    def test_dev_weapon_candidate_is_marked_not_account_truth(self) -> None:
        with seeded_account_config_db() as db_path:
            result = build_account_prepared_team_payload(
                db_path=db_path,
                team_names=("Chasca", "Ororon"),
            )

        self.assertTrue(result.ready)
        methods = [character.weapon_selection_method for character in result.characters]
        fingerprints = [
            character.weapon["weapon_fingerprint"]
            for character in result.characters
        ]
        self.assertEqual(methods, ["dev_observed_stack_by_weapon_type"] * 2)
        self.assertEqual(fingerprints, ["bow-a", "bow-b"])
        for character in result.characters:
            self.assertIn(
                WARNING_DEV_WEAPON_CANDIDATE_NOT_ACCOUNT_TRUTH,
                character.warnings,
            )

    def test_synthetic_artifact_stats_are_marked_not_account_truth(self) -> None:
        with seeded_account_config_db(equip_furina_artifacts=True) as db_path:
            result = build_account_prepared_team_payload(
                db_path=db_path,
                team_names=("Furina",),
            )

        self.assertTrue(result.ready)
        detail = result.characters[0]
        self.assertEqual(detail.current_equipped_artifact_count, 5)
        self.assertEqual(detail.artifact_source, "synthetic_dev_artifact_stats")
        self.assertFalse(detail.artifact_account_truth)
        self.assertIn(WARNING_SYNTHETIC_DEV_ARTIFACT_STATS_NOT_ACCOUNT_TRUTH, detail.warnings)

    def test_full_config_assembles_for_four_ready_account_characters(self) -> None:
        with seeded_account_config_db() as db_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                report = build_account_prepared_full_config_report(
                    db_path=db_path,
                    team_names=DEFAULT_ACCOUNT_CHASCA_TEAM,
                    run_dir=Path(temp_dir) / "run",
                )
                config_text = Path(report.full_config.config_path).read_text(
                    encoding="utf-8"
                )

        self.assertTrue(report.ready)
        self.assertTrue(report.full_config.wrote_config)
        self.assertEqual(
            [character.block_ready for character in report.team.characters],
            [True, True, True, True],
        )
        self.assertIn("chasca char lvl=90/90", config_text)
        self.assertIn("ororon char lvl=90/90", config_text)
        self.assertIn("furina char lvl=90/90", config_text)
        self.assertIn("bennett char lvl=90/90", config_text)
        self.assertIn("ororon char lvl=90/90 cons=6 talent=1,9,10;", config_text)
        self.assertIn("bennett char lvl=90/90 cons=6 talent=1,9,10;", config_text)
        self.assertIn("active furina;", config_text)
        self.assertIn(
            WARNING_TALENT_LEVEL_CAPPED_TO_GCSIM_PARSER_RANGE,
            report.warnings,
        )

    def test_current_weapon_is_used_when_present(self) -> None:
        with seeded_account_config_db() as db_path:
            result = build_account_prepared_team_payload(
                db_path=db_path,
                team_names=("Furina", "Bennett"),
            )

        self.assertTrue(result.ready)
        self.assertEqual(
            [character.weapon_selection_method for character in result.characters],
            ["current_equipped_weapon", "current_equipped_weapon"],
        )
        self.assertEqual(
            [character.weapon["gcsim_weapon_key"] for character in result.characters],
            ["favoniussword", "sapwoodblade"],
        )

    def test_partial_config_is_not_written_when_one_character_not_ready(self) -> None:
        with seeded_account_config_db(ororon_ready=False) as db_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                run_dir = Path(temp_dir) / "run"
                report = build_account_prepared_full_config_report(
                    db_path=db_path,
                    team_names=DEFAULT_ACCOUNT_CHASCA_TEAM,
                    run_dir=run_dir,
                )

                config_exists = (run_dir / "config.txt").exists()

        self.assertFalse(report.ready)
        self.assertFalse(report.full_config.wrote_config)
        self.assertFalse(config_exists)
        self.assertIn(
            "character_gcsim_key_not_ready",
            [issue.status for issue in report.team.issues],
        )


class seeded_account_config_db:
    def __init__(
        self,
        *,
        ororon_ready: bool = True,
        equip_furina_artifacts: bool = False,
    ) -> None:
        self.ororon_ready = ororon_ready
        self.equip_furina_artifacts = equip_furina_artifacts

    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "artifacts.db"
        conn = sqlite3.connect(self.path)
        try:
            create_schema(conn)
            seed_characters(conn, ororon_ready=self.ororon_ready)
            seed_talents(conn)
            seed_weapons(conn)
            seed_current_weapons(conn)
            if self.equip_furina_artifacts:
                seed_current_artifacts(conn)
            conn.commit()
        finally:
            conn.close()
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        self._tmp.cleanup()


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE account_characters (
            character_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            catalog_english_name TEXT NOT NULL DEFAULT '',
            level INTEGER,
            constellation INTEGER,
            weapon_type INTEGER,
            weapon_type_name TEXT,
            gcsim_character_key TEXT NOT NULL DEFAULT '',
            gcsim_character_key_status TEXT NOT NULL DEFAULT '',
            gcsim_character_key_method TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE account_character_talents (
            character_id INTEGER NOT NULL,
            skill_id INTEGER NOT NULL,
            skill_type INTEGER,
            name TEXT,
            level INTEGER,
            is_unlock INTEGER
        );

        CREATE TABLE account_weapon_observed_stacks (
            weapon_fingerprint TEXT PRIMARY KEY,
            weapon_id INTEGER,
            name TEXT NOT NULL,
            catalog_english_name TEXT NOT NULL DEFAULT '',
            level INTEGER,
            promote_level INTEGER,
            refinement INTEGER,
            weapon_type INTEGER,
            weapon_type_name TEXT,
            rarity INTEGER,
            known_count INTEGER NOT NULL DEFAULT 1,
            gcsim_weapon_key TEXT NOT NULL DEFAULT '',
            gcsim_weapon_key_status TEXT NOT NULL DEFAULT '',
            gcsim_weapon_key_method TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE account_character_equipped_weapons (
            character_id INTEGER PRIMARY KEY,
            weapon_fingerprint TEXT NOT NULL,
            source TEXT,
            updated_at TEXT
        );

        CREATE TABLE account_character_equipped_artifacts (
            character_id INTEGER NOT NULL,
            slot_key TEXT NOT NULL,
            artifact_id INTEGER NOT NULL,
            source TEXT,
            updated_at TEXT
        );
        """
    )


def seed_characters(conn: sqlite3.Connection, *, ororon_ready: bool) -> None:
    rows = [
        (10000104, "Локализованная Chasca", "Chasca", 90, 1, 12, "bow", "chasca", "ready"),
        (
            10000105,
            "Локализованная Ororon",
            "Ororon",
            90,
            6,
            12,
            "bow",
            "ororon" if ororon_ready else "",
            "ready" if ororon_ready else "missing",
        ),
        (10000089, "Локализованная Furina", "Furina", 90, 2, 1, "sword", "furina", "ready"),
        (10000032, "Локализованная Bennett", "Bennett", 90, 6, 1, "sword", "bennett", "ready"),
    ]
    conn.executemany(
        """
        INSERT INTO account_characters (
            character_id,
            name,
            catalog_english_name,
            level,
            constellation,
            weapon_type,
            weapon_type_name,
            gcsim_character_key,
            gcsim_character_key_status,
            gcsim_character_key_method
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'test')
        """,
        rows,
    )


def seed_talents(conn: sqlite3.Connection) -> None:
    rows = []
    for character_id, base, burst_level in (
        (10000104, 11040, 10),
        (10000105, 30500, 12),
        (10000089, 10890, 10),
        (10000032, 10320, 13),
    ):
        rows.extend(
            [
                (character_id, base + 1, 1, "Normal", 1, 1),
                (character_id, base + 2, 1, "Skill", 9, 1),
                (character_id, base + 5, 1, "Burst", burst_level, 1),
            ]
        )
    conn.executemany(
        """
        INSERT INTO account_character_talents (
            character_id,
            skill_id,
            skill_type,
            name,
            level,
            is_unlock
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def seed_weapons(conn: sqlite3.Connection) -> None:
    rows = [
        ("bow-a", 15508, "Лок Bow A", "Aqua Simulacra", 90, 6, 1, 12, "bow", 5, 1, "aquasimulacra"),
        (
            "bow-b",
            15514,
            "Лок Bow B",
            "Astral Vulture's Crimson Plumage",
            90,
            6,
            1,
            12,
            "bow",
            5,
            1,
            "astralvulturescrimsonplumage",
        ),
        ("sword-a", 11401, "Лок Sword A", "Favonius Sword", 90, 6, 2, 1, "sword", 4, 1, "favoniussword"),
        ("sword-b", 11417, "Лок Sword B", "Sapwood Blade", 90, 6, 5, 1, "sword", 4, 1, "sapwoodblade"),
    ]
    conn.executemany(
        """
        INSERT INTO account_weapon_observed_stacks (
            weapon_fingerprint,
            weapon_id,
            name,
            catalog_english_name,
            level,
            promote_level,
            refinement,
            weapon_type,
            weapon_type_name,
            rarity,
            known_count,
            gcsim_weapon_key,
            gcsim_weapon_key_status,
            gcsim_weapon_key_method
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', 'test')
        """,
        rows,
    )


def seed_current_weapons(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT INTO account_character_equipped_weapons (
            character_id,
            weapon_fingerprint,
            source,
            updated_at
        )
        VALUES (?, ?, 'manual', '2026-06-06T00:00:00+00:00')
        """,
        (
            (10000089, "sword-a"),
            (10000032, "sword-b"),
        ),
    )


def seed_current_artifacts(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT INTO account_character_equipped_artifacts (
            character_id,
            slot_key,
            artifact_id,
            source,
            updated_at
        )
        VALUES (?, ?, ?, 'preset_equip', '2026-06-06T00:00:00+00:00')
        """,
        (
            (10000089, "flower", 1),
            (10000089, "plume", 2),
            (10000089, "sands", 3),
            (10000089, "goblet", 4),
            (10000089, "circlet", 5),
        ),
    )


if __name__ == "__main__":
    unittest.main()
