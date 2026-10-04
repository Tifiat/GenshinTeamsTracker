from __future__ import annotations

import sqlite3
import unittest

from hoyolab_export.artifact_db import init_db
from ui.artifact_browser.queries import _fetch_artifacts, _load_substats, _load_tags


class InventoryBulkQueriesTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        init_db(self.conn)

    def seed(self, count):
        self.conn.executemany(
            "INSERT INTO artifacts (id, fingerprint, name, pos, rarity, level, "
            "main_property_type, main_property_value, first_seen_at, last_seen_at) "
            "VALUES (?, ?, 'Fixture', 1, 5, 20, 2000, '4780', 'fixture', 'fixture')",
            [(index, f"fixture-{index}") for index in range(1, count + 1)],
        )
        self.conn.executemany(
            "INSERT INTO artifact_substats (artifact_id, slot_index, property_type, value, times) "
            "VALUES (?, ?, 20, ?, 1)",
            [(index, slot, str(slot + 1)) for index in range(1, count + 1) for slot in (1, 0)],
        )
        self.conn.execute("INSERT INTO artifact_tags (id, name, sort_order, created_at) VALUES (1, 'Later', 2, 'fixture')")
        self.conn.execute("INSERT INTO artifact_tags (id, name, sort_order, created_at) VALUES (2, 'Earlier', 1, 'fixture')")
        self.conn.executemany("INSERT INTO artifact_tag_links VALUES (?, ?)",
                              [(index, tag) for index in range(1, count + 1) for tag in (1, 2)])

    def test_large_inventory_stays_batched_below_sqlite_variable_limit(self):
        self.seed(1217)
        self.conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 64)
        statements = []
        self.conn.set_trace_callback(statements.append)
        artifacts = _fetch_artifacts(self.conn, preferred_lang="en-us")
        self.assertEqual(len(artifacts), 1217)
        self.assertEqual({artifact.id for artifact in artifacts}, set(range(1, 1218)))
        self.assertTrue(all([stat.slot_index for stat in artifact.substats] == [0, 1] for artifact in artifacts))
        self.assertTrue(all([tag.name for tag in artifact.tags] == ["Earlier", "Later"] for artifact in artifacts))
        self.assertEqual(len(statements), 3)
        self.assertTrue(all(statement.lstrip().upper().startswith("SELECT") for statement in statements))

    def test_child_reads_keep_only_parent_ids_from_this_load(self):
        self.seed(2)
        self.assertEqual(set(_load_substats(self.conn, [1])), {1})
        self.assertEqual(set(_load_tags(self.conn, [1])), {1})
        self.assertEqual(_load_substats(self.conn, []), {})
        self.assertEqual(_load_tags(self.conn, []), {})

    def test_empty_inventory_needs_no_child_queries(self):
        statements = []
        self.conn.set_trace_callback(statements.append)
        self.assertEqual(_fetch_artifacts(self.conn), [])
        self.assertEqual(len(statements), 1)


if __name__ == "__main__":
    unittest.main()
