from __future__ import annotations

import sqlite3
import unittest

from hoyolab_export.artifact_db import (
    artifact_build_targets_gcsim_character,
    create_artifact_build,
    get_artifact_build_targets,
    init_db,
    list_build_presets_for_gcsim_character,
    replace_artifact_build_targets,
)


class VirtualGcsimBuildTargetsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        init_db(self.conn)
        self.build_id = create_artifact_build(self.conn, name="Virtual build")

    def tearDown(self) -> None:
        self.conn.close()

    def test_virtual_target_round_trips_by_stable_gcsim_key(self) -> None:
        replace_artifact_build_targets(
            self.conn,
            self.build_id,
            [
                {
                    "target_type": "gcsim_character",
                    "gcsim_character_key": "futurehero",
                    "character_name": "FutureHero",
                }
            ],
        )

        self.assertEqual(
            get_artifact_build_targets(self.conn, self.build_id),
            [
                {
                    "target_type": "gcsim_character",
                    "gcsim_character_key": "futurehero",
                    "character_id": None,
                    "character_name": "FutureHero",
                }
            ],
        )
        self.assertTrue(
            artifact_build_targets_gcsim_character(
                self.conn,
                self.build_id,
                "futurehero",
            )
        )
        self.assertEqual(
            list_build_presets_for_gcsim_character(self.conn, "futurehero"),
            [
                {
                    "id": self.build_id,
                    "name": "Virtual build",
                    "slot_count": 0,
                }
            ],
        )

    def test_virtual_target_logically_merges_into_single_account_target(self) -> None:
        replace_artifact_build_targets(
            self.conn,
            self.build_id,
            [
                {
                    "target_type": "gcsim_character",
                    "gcsim_character_key": "futurehero",
                    "character_name": "FutureHero",
                }
            ],
        )
        self.conn.execute(
            """
            INSERT INTO account_characters (
                character_id, name, gcsim_character_key, gcsim_character_key_status
            ) VALUES (?, ?, ?, ?)
            """,
            (123456, "Account Future Hero", "futurehero", "ready"),
        )

        targets = get_artifact_build_targets(self.conn, self.build_id)

        self.assertEqual(
            targets,
            [
                {
                    "target_type": "character",
                    "character_id": 123456,
                    "character_name": "Account Future Hero",
                }
            ],
        )
        self.assertEqual(len(targets), 1)
        self.assertTrue(
            artifact_build_targets_gcsim_character(
                self.conn,
                self.build_id,
                "futurehero",
            )
        )
        self.assertEqual(
            list_build_presets_for_gcsim_character(self.conn, "futurehero"),
            [
                {
                    "id": self.build_id,
                    "name": "Virtual build",
                    "slot_count": 0,
                }
            ],
        )

    def test_saved_account_projection_keeps_same_logical_gcsim_target(self) -> None:
        self.conn.execute(
            """
            INSERT INTO account_characters (
                character_id, name, gcsim_character_key, gcsim_character_key_status
            ) VALUES (?, ?, ?, ?)
            """,
            (123456, "Account Future Hero", "futurehero", "ready"),
        )
        replace_artifact_build_targets(
            self.conn,
            self.build_id,
            [
                {
                    "target_type": "character",
                    "character_id": 123456,
                    "character_name": "Account Future Hero",
                }
            ],
        )

        self.assertTrue(
            artifact_build_targets_gcsim_character(
                self.conn,
                self.build_id,
                "futurehero",
            )
        )
        self.assertEqual(
            list_build_presets_for_gcsim_character(self.conn, "futurehero"),
            [
                {
                    "id": self.build_id,
                    "name": "Virtual build",
                    "slot_count": 0,
                }
            ],
        )

    def test_repeated_schema_initialization_preserves_virtual_target(self) -> None:
        replace_artifact_build_targets(
            self.conn,
            self.build_id,
            [
                {
                    "target_type": "gcsim_character",
                    "gcsim_character_key": "futurehero",
                    "character_name": "FutureHero",
                }
            ],
        )

        init_db(self.conn)

        self.assertTrue(
            artifact_build_targets_gcsim_character(
                self.conn, self.build_id, "futurehero"
            )
        )


if __name__ == "__main__":
    unittest.main()
