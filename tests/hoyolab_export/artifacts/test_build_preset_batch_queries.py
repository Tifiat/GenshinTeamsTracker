from __future__ import annotations

import sqlite3
import unittest

from hoyolab_export.artifact_db import create_build_preset, init_db, list_build_presets


class BuildPresetBatchQueriesTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.addCleanup(self.conn.close)

    def test_query_count_stays_constant_as_preset_count_grows(self):
        for count in (1, 30, 120):
            while self.conn.execute("SELECT count(*) FROM artifact_builds").fetchone()[0] < count:
                create_build_preset(self.conn, name="Build", targets=[{
                    "target_type": "gcsim_character", "gcsim_character_key": "virtualhero",
                    "character_name": "Virtual Hero",
                }])
            statements = []
            self.conn.set_trace_callback(statements.append)
            presets = list_build_presets(self.conn)
            self.conn.set_trace_callback(None)
            with self.subTest(count=count):
                self.assertEqual(len(presets), count)
                self.assertEqual(len(statements), 4)
                self.assertTrue(all(statement.lstrip().upper().startswith("SELECT")
                                    for statement in statements))
                self.assertTrue(all(len(preset["targets"]) == 1 for preset in presets))

    def test_batch_preserves_order_projection_dedup_and_legacy_counts_per_build(self):
        self.conn.executemany(
            "INSERT INTO account_characters (character_id, name, gcsim_character_key, "
            "gcsim_character_key_status) VALUES (?, ?, ?, ?)",
            [(1001, "Live Hero", "readyhero", "ready"),
             (1002, "Pending Hero", "pendinghero", "unresolved")],
        )
        normal = {"target_type": "character", "character_id": 1001, "character_name": "Saved Hero"}
        virtual = {"target_type": "gcsim_character", "gcsim_character_key": "readyhero", "character_name": "Ready"}
        projected = create_build_preset(self.conn, name="Projection", targets=[virtual])
        deduped = create_build_preset(self.conn, name="Dedup", targets=[
            normal, virtual,
            {"target_type": "character", "character_id": 1003, "character_name": "alpha"},
            {"target_type": "universal"},
            {"target_type": "gcsim_character", "gcsim_character_key": "pendinghero", "character_name": "Zulu"},
            {"target_type": "gcsim_character", "gcsim_character_key": "absenthero", "character_name": "beta"},
        ])
        empty = create_build_preset(self.conn, name="Empty", targets=[])
        presets = {preset["id"]: preset for preset in list_build_presets(self.conn)}
        self.assertEqual(presets[projected]["targets"], [{
            "target_type": "character", "character_id": 1001, "character_name": "Live Hero",
        }])
        self.assertEqual(presets[projected]["target_count"], 0)
        targets = presets[deduped]["targets"]
        self.assertEqual([target["target_type"] for target in targets],
                         ["universal", "character", "character", "gcsim_character", "gcsim_character"])
        self.assertEqual(targets[1], {"target_type": "character", "character_id": 1003, "character_name": "alpha"})
        self.assertEqual(targets[2], normal)
        self.assertEqual([target["gcsim_character_key"] for target in targets[3:]], ["absenthero", "pendinghero"])
        self.assertEqual(presets[deduped]["target_count"], 3)
        self.assertEqual(presets[empty]["targets"], [])
        self.assertEqual(presets[empty]["slots"], [])

    def test_empty_database_does_not_issue_target_queries(self):
        statements = []
        self.conn.set_trace_callback(statements.append)
        self.assertEqual(list_build_presets(self.conn), [])
        self.conn.set_trace_callback(None)
        self.assertEqual(len(statements), 1)


if __name__ == "__main__":
    unittest.main()
