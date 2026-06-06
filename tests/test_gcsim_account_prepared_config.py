from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from run_workspace.gcsim.account_prepared_config import (
    ARTIFACT_SOURCE_CURRENT_EQUIPPED,
    ARTIFACT_STATS_SOURCE_CURRENT_EQUIPPED_MAIN_SUB,
    DEFAULT_DEV_ENERGY_OVERRIDE_LINE,
    DEFAULT_ACCOUNT_CHASCA_TEAM,
    WARNING_DEV_WEAPON_CANDIDATE_NOT_ACCOUNT_TRUTH,
    build_account_prepared_full_config_report,
    build_account_prepared_team_payload,
    override_rotation_shell_energy_line,
)
from run_workspace.gcsim.config_talents import (
    WARNING_POST_NORMALIZATION_TALENT_LEVEL_CAPPED_TO_GCSIM_RANGE,
)


class GcsimAccountPreparedConfigTest(unittest.TestCase):
    def test_dev_energy_override_replaces_shell_energy_line(self) -> None:
        text, replaced = override_rotation_shell_energy_line(
            "options swap_delay=12;\nenergy every interval=480,720 amount=1;\nactive furina;\n"
        )

        self.assertTrue(replaced)
        self.assertIn(DEFAULT_DEV_ENERGY_OVERRIDE_LINE, text)
        self.assertNotIn("energy every interval=480,720 amount=1;", text)

    def test_dev_energy_override_is_written_to_temp_shell_only(self) -> None:
        with seeded_account_config_db() as db_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                source_shell = Path(temp_dir) / "shell.txt"
                source_shell.write_text(
                    "options swap_delay=12;\n"
                    "energy every interval=480,720 amount=1;\n"
                    "target lvl=100 resist=0.1 hp=999999999;\n"
                    "active furina;\n",
                    encoding="utf-8",
                )
                report = build_account_prepared_full_config_report(
                    db_path=db_path,
                    team_names=("Furina",),
                    rotation_shell_path=source_shell,
                    run_dir=Path(temp_dir) / "run",
                    artifact_set_registry_source=db_path.artifact_set_registry_source,
                    dev_energy_override_line=DEFAULT_DEV_ENERGY_OVERRIDE_LINE,
                )
                config_text = Path(report.full_config.config_path).read_text(
                    encoding="utf-8"
                )
                source_text = source_shell.read_text(encoding="utf-8")

        self.assertTrue(report.ready)
        self.assertIn(DEFAULT_DEV_ENERGY_OVERRIDE_LINE, config_text)
        self.assertIn("amount=1", source_text)

    def test_account_character_uses_stored_gcsim_key_not_localized_name(self) -> None:
        with seeded_account_config_db() as db_path:
            result = build_account_prepared_team_payload(
                db_path=db_path,
                team_names=("Chasca",),
                artifact_set_registry_source=db_path.artifact_set_registry_source,
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
                artifact_set_registry_source=db_path.artifact_set_registry_source,
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

    def test_current_artifact_stats_are_marked_account_truth(self) -> None:
        with seeded_account_config_db() as db_path:
            result = build_account_prepared_team_payload(
                db_path=db_path,
                team_names=("Furina",),
                artifact_set_registry_source=db_path.artifact_set_registry_source,
            )

        self.assertTrue(result.ready)
        detail = result.characters[0]
        self.assertEqual(detail.current_equipped_artifact_count, 5)
        self.assertEqual(detail.artifact_source, ARTIFACT_SOURCE_CURRENT_EQUIPPED)
        self.assertEqual(
            detail.artifact_stats_source,
            ARTIFACT_STATS_SOURCE_CURRENT_EQUIPPED_MAIN_SUB,
        )
        self.assertTrue(detail.artifact_account_truth)
        self.assertEqual(detail.artifact_set_counts[0]["count"], 5)
        self.assertEqual(
            detail.artifact_set_counts[0]["mapping"]["gcsim_key"],
            "goldentroupe",
        )

    def test_full_config_assembles_for_four_ready_account_characters(self) -> None:
        with seeded_account_config_db() as db_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                report = build_account_prepared_full_config_report(
                    db_path=db_path,
                    team_names=DEFAULT_ACCOUNT_CHASCA_TEAM,
                    run_dir=Path(temp_dir) / "run",
                    artifact_set_registry_source=db_path.artifact_set_registry_source,
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
        self.assertIn("ororon char lvl=90/90 cons=6 talent=1,9,9;", config_text)
        self.assertIn("bennett char lvl=90/90 cons=6 talent=1,9,10;", config_text)
        self.assertIn('chasca add set="obsidiancodex" count=4;', config_text)
        self.assertIn('ororon add set="deepwoodmemories" count=2;', config_text)
        self.assertIn('ororon add set="emblemofseveredfate" count=2;', config_text)
        self.assertIn('furina add set="goldentroupe" count=5;', config_text)
        self.assertIn('bennett add set="noblesseoblige" count=5;', config_text)
        self.assertIn("active furina;", config_text)
        self.assertNotIn(
            WARNING_POST_NORMALIZATION_TALENT_LEVEL_CAPPED_TO_GCSIM_RANGE,
            report.warnings,
        )
        self.assertEqual(
            report.team.characters[1].talents["talents"][2][
                "parsed_constellation_bonus"
            ],
            3,
        )

    def test_current_weapon_is_used_when_present(self) -> None:
        with seeded_account_config_db() as db_path:
            result = build_account_prepared_team_payload(
                db_path=db_path,
                team_names=("Furina", "Bennett"),
                artifact_set_registry_source=db_path.artifact_set_registry_source,
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
                    artifact_set_registry_source=db_path.artifact_set_registry_source,
                )

                config_exists = (run_dir / "config.txt").exists()

        self.assertFalse(report.ready)
        self.assertFalse(report.full_config.wrote_config)
        self.assertFalse(config_exists)
        self.assertIn(
            "character_gcsim_key_not_ready",
            [issue.status for issue in report.team.issues],
        )

    def test_missing_current_artifacts_is_not_character_missing(self) -> None:
        with seeded_account_config_db(equip_artifacts=False) as db_path:
            result = build_account_prepared_team_payload(
                db_path=db_path,
                team_names=("Furina",),
                artifact_set_registry_source=db_path.artifact_set_registry_source,
            )

        self.assertFalse(result.ready)
        self.assertTrue(result.characters[0].character_found)
        self.assertEqual(result.characters[0].artifact_source, "missing_current_equipped_artifacts")
        self.assertIn("current_artifacts_missing", [issue.status for issue in result.issues])
        self.assertNotIn("missing_account_character", [issue.status for issue in result.issues])

    def test_artifact_stats_ignore_final_or_right_panel_rows(self) -> None:
        with seeded_account_config_db() as db_path:
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO account_final_stats (
                        character_id,
                        property_type,
                        raw_value,
                        source
                    )
                    VALUES (10000089, 20, 999999, 'right_panel_total')
                    """
                )
                conn.commit()
            finally:
                conn.close()
            with tempfile.TemporaryDirectory() as temp_dir:
                report = build_account_prepared_full_config_report(
                    db_path=db_path,
                    team_names=("Furina",),
                    run_dir=Path(temp_dir) / "run",
                    artifact_set_registry_source=db_path.artifact_set_registry_source,
                )
                config_text = Path(report.full_config.config_path).read_text(
                    encoding="utf-8"
                )

        self.assertTrue(report.ready)
        add_stats_lines = [
            line for line in config_text.splitlines() if " add stats " in line
        ]
        self.assertEqual(len(add_stats_lines), 1)
        self.assertNotIn("999999", add_stats_lines[0])


class seeded_account_config_db:
    def __init__(
        self,
        *,
        ororon_ready: bool = True,
        equip_artifacts: bool = True,
    ) -> None:
        self.ororon_ready = ororon_ready
        self.equip_artifacts = equip_artifacts

    def __enter__(self) -> "seeded_account_config_db":
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "artifacts.db"
        self.artifact_set_registry_source = Path(self._tmp.name) / "artifacts.go"
        self.artifact_set_registry_source.write_text(
            "\n".join(
                [
                    "package shortcut",
                    "var artifactMap = map[string]int{",
                    '  "deepwoodmemories": 1,',
                    '  "emblemofseveredfate": 1,',
                    '  "goldentroupe": 1,',
                    '  "noblesseoblige": 1,',
                    '  "obsidiancodex": 1,',
                    "}",
                ]
            ),
            encoding="utf-8",
        )
        conn = sqlite3.connect(self.path)
        try:
            create_schema(conn)
            seed_characters(conn, ororon_ready=self.ororon_ready)
            seed_talents(conn)
            seed_constellations(conn)
            seed_weapons(conn)
            seed_current_weapons(conn)
            seed_artifacts(conn)
            if self.equip_artifacts:
                seed_current_artifacts(conn)
            conn.commit()
        finally:
            conn.close()
        return self

    def __fspath__(self) -> str:
        return str(self.path)

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

        CREATE TABLE account_character_constellations (
            character_id INTEGER NOT NULL,
            pos INTEGER NOT NULL,
            name TEXT,
            effect TEXT,
            is_actived INTEGER,
            PRIMARY KEY (character_id, pos)
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

        CREATE TABLE artifacts (
            id INTEGER PRIMARY KEY,
            pos INTEGER NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            set_uid TEXT,
            set_name TEXT,
            main_property_type INTEGER,
            main_property_name TEXT,
            main_property_value TEXT
        );

        CREATE TABLE artifact_substats (
            artifact_id INTEGER NOT NULL,
            slot_index INTEGER NOT NULL,
            property_type INTEGER,
            property_name TEXT,
            value TEXT,
            times INTEGER,
            PRIMARY KEY (artifact_id, slot_index)
        );

        CREATE TABLE account_final_stats (
            character_id INTEGER NOT NULL,
            property_type INTEGER NOT NULL,
            raw_value REAL,
            source TEXT
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


def seed_constellations(conn: sqlite3.Connection) -> None:
    rows = [
        (
            10000105,
            5,
            "Burst Boost",
            "Increases <color=#FFD780FF>Burst</color> by 3.",
            1,
        ),
        (
            10000032,
            5,
            "Burst Boost",
            "Increases <color=#FFD780FF>Burst</color> by 3.",
            1,
        ),
    ]
    conn.executemany(
        """
        INSERT INTO account_character_constellations (
            character_id,
            pos,
            name,
            effect,
            is_actived
        )
        VALUES (?, ?, ?, ?, ?)
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


def seed_artifacts(conn: sqlite3.Connection) -> None:
    artifact_rows: list[tuple[int, int, str, str, str, int, str, str]] = []
    substat_rows: list[tuple[int, int, int, str, str, int]] = []

    def add_character_artifacts(
        *,
        start_id: int,
        sets: list[tuple[str, str]],
    ) -> None:
        main_stats = (
            (2, "HP", "4780"),
            (5, "ATK", "311"),
            (23, "Energy Recharge", "51.8"),
            (20, "CRIT Rate", "31.1"),
            (22, "CRIT DMG", "62.2"),
        )
        for index, (set_uid, set_name) in enumerate(sets, start=1):
            artifact_id = start_id + index - 1
            property_type, property_name, value = main_stats[index - 1]
            artifact_rows.append(
                (
                    artifact_id,
                    index,
                    f"{set_name} Piece {index}",
                    set_uid,
                    set_name,
                    property_type,
                    property_name,
                    value,
                )
            )
            substat_rows.extend(
                [
                    (artifact_id, 0, 20, "CRIT Rate", "3.1", 1),
                    (artifact_id, 1, 22, "CRIT DMG", "6.2", 1),
                ]
            )

    add_character_artifacts(
        start_id=100,
        sets=[
            ("ObsidianCodex", "Obsidian Codex"),
            ("ObsidianCodex", "Obsidian Codex"),
            ("ObsidianCodex", "Obsidian Codex"),
            ("ObsidianCodex", "Obsidian Codex"),
            ("EmblemOfSeveredFate", "Emblem of Severed Fate"),
        ],
    )
    add_character_artifacts(
        start_id=200,
        sets=[
            ("EmblemOfSeveredFate", "Emblem of Severed Fate"),
            ("EmblemOfSeveredFate", "Emblem of Severed Fate"),
            ("DeepwoodMemories", "Deepwood Memories"),
            ("DeepwoodMemories", "Deepwood Memories"),
            ("NoblesseOblige", "Noblesse Oblige"),
        ],
    )
    add_character_artifacts(
        start_id=300,
        sets=[("GoldenTroupe", "Golden Troupe")] * 5,
    )
    add_character_artifacts(
        start_id=400,
        sets=[("NoblesseOblige", "Noblesse Oblige")] * 5,
    )

    conn.executemany(
        """
        INSERT INTO artifacts (
            id,
            pos,
            name,
            set_uid,
            set_name,
            main_property_type,
            main_property_name,
            main_property_value
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        artifact_rows,
    )
    conn.executemany(
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
        substat_rows,
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
            (10000104, "flower", 100),
            (10000104, "plume", 101),
            (10000104, "sands", 102),
            (10000104, "goblet", 103),
            (10000104, "circlet", 104),
            (10000105, "flower", 200),
            (10000105, "plume", 201),
            (10000105, "sands", 202),
            (10000105, "goblet", 203),
            (10000105, "circlet", 204),
            (10000089, "flower", 300),
            (10000089, "plume", 301),
            (10000089, "sands", 302),
            (10000089, "goblet", 303),
            (10000089, "circlet", 304),
            (10000032, "flower", 400),
            (10000032, "plume", 401),
            (10000032, "sands", 402),
            (10000032, "goblet", 403),
            (10000032, "circlet", 404),
        ),
    )


if __name__ == "__main__":
    unittest.main()
