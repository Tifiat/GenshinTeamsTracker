from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from hoyolab_export.artifact_db import create_build_preset, init_db
from ui.artifact_browser import queries
from ui.artifact_browser.store import ArtifactBrowserStore


class ReadOnlyArtifactQueriesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db_path = Path(self.directory.name) / "profile.db"

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            init_db(conn)
            conn.execute(
                """
                INSERT INTO artifacts (
                    id, fingerprint, name, set_uid, set_name, pos, pos_name,
                    rarity, level, main_property_type, main_property_name,
                    main_property_value, first_seen_at, last_seen_at,
                    import_source, json_imported
                ) VALUES (
                    7, 'fixture-7', 'Test Flower', 'test-set', 'Test Set',
                    1, 'Flower', 5, 20, 20, 'CRIT Rate', '31.1%',
                    '2026-01-01', '2026-01-01', 'artiscan', 1
                )
                """
            )
            self.build_id = create_build_preset(
                conn,
                name="Test Build",
                slots={1: 7},
                targets=[{
                    "target_type": "gcsim_character",
                    "gcsim_character_key": "testcharacter",
                    "character_name": "Test Character",
                }],
            )
            conn.commit()
        finally:
            conn.close()

    def test_readonly_store_build_and_summary_preserve_database(self) -> None:
        original_bytes = self.db_path.read_bytes()
        with closing(sqlite3.connect(self.db_path)) as conn:
            original_schema = conn.execute(
                "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
            ).fetchall()

        with (
            patch.object(queries, "init_db", side_effect=AssertionError("init_db called")),
            patch.object(
                queries,
                "connect_db",
                side_effect=AssertionError("writable connection opened"),
            ),
            patch.object(
                queries,
                "current_hoyolab_content_language",
                side_effect=AssertionError("global language read"),
            ),
        ):
            store = ArtifactBrowserStore.load_from_db(
                self.db_path, preferred_lang="ru-ru", read_only=True,
            )
            self.assertEqual(store.content_language, "ru-ru")
            self.assertEqual(store.artifact(7).name, "Test Flower")
            self.assertEqual(
                [item.id for item in queries.list_all_artifacts(
                    db_path=self.db_path, read_only=True,
                )],
                [7],
            )
            self.assertEqual(len(queries.list_build_presets(
                db_path=self.db_path, read_only=True,
            )), 1)
            self.assertEqual(
                queries.list_build_presets_for_gcsim_character(
                    "testcharacter", db_path=self.db_path, read_only=True,
                )[0]["id"],
                self.build_id,
            )
            self.assertEqual(
                queries.get_build_preset(
                    self.build_id, db_path=self.db_path, read_only=True,
                )["slots"][0]["artifact_id"],
                7,
            )
            self.assertEqual(
                queries.calculate_build_summary(
                    build_id=self.build_id, db_path=self.db_path, read_only=True,
                )["artifact_ids_by_pos"],
                {1: 7},
            )
            self.assertEqual(queries.count_json_imported_artifacts(
                db_path=self.db_path, read_only=True,
            ), 1)
            self.assertEqual(queries.list_custom_sets(
                db_path=self.db_path, read_only=True,
            ), [])
            self.assertEqual(queries.get_custom_set_artifact_ids(
                1, db_path=self.db_path, read_only=True,
            ), set())
            self.assertEqual(queries.list_set_bonus_description_map(
                db_path=self.db_path, read_only=True,
            ), {})

        self.assertEqual(self.db_path.read_bytes(), original_bytes)
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute(
                "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
            ).fetchall(), original_schema)

    def test_missing_database_is_not_created(self) -> None:
        missing = Path(self.directory.name) / "missing" / "profile.db"
        self.assertFalse(ArtifactBrowserStore.load_from_db(
            missing, read_only=True,
        ).database_exists)
        self.assertIsNone(queries.calculate_build_summary(
            build_id=1, db_path=missing, read_only=True,
        ))
        self.assertEqual(queries.list_build_presets(
            db_path=missing, read_only=True,
        ), [])
        self.assertFalse(missing.parent.exists())

    def test_readonly_connection_rejects_writes(self) -> None:
        conn = queries._open_query_connection(self.db_path, read_only=True)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("INSERT INTO artifact_tags (name) VALUES ('blocked')")
        finally:
            conn.close()

    def test_preset_read_flags_preserve_initialized_store_and_readonly_source(self) -> None:
        original_bytes = self.db_path.read_bytes()
        with closing(sqlite3.connect(self.db_path)) as conn:
            original_contents = list(conn.iterdump())
        with patch.object(queries, "init_db", side_effect=AssertionError("redundant init")):
            for read_only in (True, False):
                for initialize in ((False, True) if read_only else (False,)):
                    with self.subTest(read_only=read_only, initialize=initialize):
                        options = dict(db_path=self.db_path, read_only=read_only,
                                       initialize=initialize)
                        self.assertEqual(queries.list_build_presets(**options)[0]["id"], self.build_id)
                        self.assertEqual(queries.get_build_preset(self.build_id, **options)["id"], self.build_id)
                        self.assertEqual(queries.calculate_build_summary(
                            build_id=self.build_id, **options,
                        )["artifact_ids_by_pos"], {1: 7})
                        if read_only:
                            self.assertEqual(self.db_path.read_bytes(), original_bytes)
        # Normal account connections enable WAL; only read-only sources promise
        # byte identity. Both routes must preserve schema and application data.
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(list(conn.iterdump()), original_contents)


if __name__ == "__main__":
    unittest.main()
