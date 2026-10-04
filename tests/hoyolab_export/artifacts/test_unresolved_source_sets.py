"""Unmapped source sets remain visible while set-dependent work stays incomplete."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from hoyolab_export.artifact_build_snapshot import (
    WARNING_ARTIFACT_SET_CANONICAL_MAPPING_MISSING,
    build_artifact_build_snapshot,
)
from hoyolab_export.artifact_db import calculate_raw_build_summary, connect_db, init_db
from hoyolab_export.character_stat_snapshot import (
    SNAPSHOT_STATUS_PARTIAL, SNAPSHOT_STATUS_READY, build_character_stat_snapshot,
)
from run_workspace.gcsim.account_prepared_config import build_account_prepared_team_payload
from run_workspace.gcsim.selected_team_config import _artifact_payload_from_snapshot
from tests.hoyolab_export.catalog.test_character_stat_snapshot import (
    character_entry, weapon_entry,
)
from tests.run_workspace.gcsim.test_gcsim_account_prepared_config import (
    seeded_account_config_db,
)


class UnresolvedSourceSetTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db_path = Path(temporary.name) / "artifacts.db"
        with closing(connect_db(self.db_path)) as conn:
            init_db(conn)
            for artifact_id, pos in ((101, 1), (102, 2)):
                conn.execute(
                    """INSERT INTO artifacts (
                       id, fingerprint, name, set_id, set_uid, set_name, pos,
                       main_property_type, main_property_name, main_property_value,
                       first_seen_at, last_seen_at)
                       VALUES (?, ?, 'Unmapped piece', 2150451, NULL, 'Golden Troupe',
                               ?, 20, 'CRIT Rate', '3.1', '2026-01-01', '2026-01-01')""",
                    (artifact_id, f"fixture-{artifact_id}", pos),
                )
            conn.commit()

    def summary(self, slots: dict[int, int]) -> dict:
        with closing(connect_db(self.db_path)) as conn:
            return calculate_raw_build_summary(conn, slots=slots)

    def stat_snapshot(self, artifact_snapshot) -> object:
        return build_character_stat_snapshot(
            account_character={"id": 1, "name": "Amber", "level": 1},
            character_stats_entry=character_entry(),
            account_weapon={"id": 2, "name": "Favonius Warbow", "level": 1},
            weapon_stats_entry=weapon_entry(),
            artifact_summary=artifact_snapshot,
        )

    def test_two_unknown_pieces_keep_stats_but_mark_selected_build_partial(self) -> None:
        summary = self.summary({1: 101, 2: 102})
        self.assertEqual(summary["set_counts"][0]["source_set_id"], 2150451)
        self.assertFalse(summary["set_counts"][0]["canonical_set_resolved"])
        self.assertEqual(summary["unresolved_active_sets"][0]["count"], 2)
        self.assertEqual(summary["total_stats"][0]["raw_value"], 6.2)
        snapshot = build_artifact_build_snapshot(summary)
        self.assertEqual(snapshot.active_set_bonuses, ())
        self.assertFalse(snapshot.to_dict()["set_counts"][0]["canonical_set_resolved"])
        self.assertEqual(snapshot.to_dict()["set_counts"][0]["source_set_id"], 2150451)
        self.assertIn(WARNING_ARTIFACT_SET_CANONICAL_MAPPING_MISSING, snapshot.warnings)
        self.assertEqual(self.stat_snapshot(snapshot).status, SNAPSHOT_STATUS_PARTIAL)

    def test_single_unknown_piece_has_no_unknown_bonus_or_mapping_warning(self) -> None:
        summary = self.summary({1: 101})
        self.assertEqual(summary["unresolved_active_sets"], [])
        self.assertEqual(summary["total_stats"][0]["raw_value"], 3.1)
        snapshot = build_artifact_build_snapshot(summary)
        self.assertEqual(snapshot.active_set_bonuses, ())
        self.assertNotIn(WARNING_ARTIFACT_SET_CANONICAL_MAPPING_MISSING, snapshot.warnings)
        # Other readiness gates, such as missing slots, remain independent.
        self.assertEqual(self.stat_snapshot(snapshot).status, SNAPSHOT_STATUS_READY)

    def test_gcsim_cannot_infer_unknown_active_set_from_matching_name(self) -> None:
        with seeded_account_config_db() as fixture:
            with closing(sqlite3.connect(fixture.path)) as conn:
                conn.execute("ALTER TABLE artifacts ADD COLUMN set_id INTEGER")
                conn.execute(
                    "UPDATE artifacts SET set_uid = NULL, set_id = 2150451 "
                    "WHERE id IN (300, 301)"
                )
                conn.commit()
            result = build_account_prepared_team_payload(
                db_path=fixture,
                team_names=("Furina",),
                artifact_set_registry_source=fixture.artifact_set_registry_source,
            )
        self.assertFalse(result.ready)
        detail = result.characters[0]
        self.assertIn(
            "artifact_set_canonical_mapping_missing",
            {issue.status for issue in detail.issues},
        )
        unresolved = next(item for item in detail.artifact_set_counts if not item["set_uid"])
        self.assertEqual(unresolved["mapping"]["gcsim_key"], "")
        self.assertEqual(unresolved["source_set_id"], 2150451)

    def test_gcsim_single_unknown_piece_does_not_block_otherwise_ready_team(self) -> None:
        with seeded_account_config_db() as fixture:
            with closing(sqlite3.connect(fixture.path)) as conn:
                conn.execute("ALTER TABLE artifacts ADD COLUMN set_id INTEGER")
                conn.execute(
                    "UPDATE artifacts SET set_uid = NULL, set_id = 2150451 WHERE id = 300"
                )
                conn.commit()
            result = build_account_prepared_team_payload(
                db_path=fixture,
                team_names=("Furina",),
                artifact_set_registry_source=fixture.artifact_set_registry_source,
            )
        self.assertTrue(result.ready)
        self.assertNotIn(
            "artifact_set_canonical_mapping_missing",
            {issue.status for issue in result.characters[0].issues},
        )

    def test_selected_team_snapshot_cannot_resolve_unknown_set_by_name(self) -> None:
        class NameResolver:
            def resolve(self, *, set_uid: str, set_name: str) -> dict:
                return {
                    "gcsim_key": "goldentroupe", "source": "name_match",
                    "ambiguous": False, "warnings": (),
                }

        payload, report, issues, _warnings = _artifact_payload_from_snapshot(
            self.summary({1: 101, 2: 102}),
            artifact_set_resolver=NameResolver(), slot_index=0,
        )
        self.assertIn("artifact_set_canonical_mapping_missing", {issue.status for issue in issues})
        self.assertEqual(report["set_counts"][0]["mapping"]["gcsim_key"], "")
        self.assertEqual(payload["stat_totals"][0]["raw_value"], 6.2)

        _payload, _report, single_issues, _warnings = _artifact_payload_from_snapshot(
            self.summary({1: 101}), artifact_set_resolver=NameResolver(), slot_index=0,
        )
        self.assertNotIn(
            "artifact_set_canonical_mapping_missing", {issue.status for issue in single_issues}
        )


if __name__ == "__main__":
    unittest.main()
