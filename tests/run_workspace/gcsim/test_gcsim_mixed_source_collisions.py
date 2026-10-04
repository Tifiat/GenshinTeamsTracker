"""Fixture-only collision checks; source rows and preset IDs remain intact."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hoyolab_export.artifact_db import connect_db, init_db
from run_workspace.gcsim.optimizer_artifact_database import (
    find_ambiguous_mixed_source_artifact_groups,
    load_gcsim_optimizer_artifact_database_input,
)
from run_workspace.gcsim.selected_team_config import (
    SELECTED_TEAM_CONFIG_READY,
    SelectedTeamCharacterDetail,
    build_selected_team_payload,
)
from tests.run_workspace.gcsim.test_gcsim_optimizer_artifact_database import _engine_context


class MixedSourceCollisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "artifacts.db"
        with closing(connect_db(self.db)) as conn:
            init_db(conn)
            conn.commit()

    def _artifact(self, artifact_id: int, *, set_id: int | None, source: str,
                  content_fingerprint: str | None) -> None:
        with closing(connect_db(self.db)) as conn:
            conn.execute(
                """INSERT INTO artifacts (
                    id, fingerprint, content_fingerprint, relic_id, name, set_id, set_uid,
                    pos, rarity, level, main_property_type, main_property_value,
                    first_seen_at, last_seen_at, import_source
                ) VALUES (?, ?, ?, ?, ?, ?, 'KnownSet', 1, 5, 20, 2, '4780',
                          '2026-01-01', '2026-01-01', ?)""",
                (artifact_id, f"source-{artifact_id}", content_fingerprint,
                 artifact_id if set_id else None, "Flower", set_id, source),
            )
            conn.commit()

    def _observe(self, artifact_id: int, character_id: int) -> None:
        with closing(connect_db(self.db)) as conn:
            conn.execute(
                "INSERT INTO artifact_equipment (artifact_id, character_id, character_name, pos, imported_at) "
                "VALUES (?, ?, 'Fixture', 1, '2026-01-02T00:00:00Z')",
                (artifact_id, character_id),
            )
            conn.commit()

    def test_later_mapping_does_not_admit_scanner_and_hoyolab_as_two_copies(self) -> None:
        self._artifact(1, set_id=None, source="artiscan", content_fingerprint="same-rolls")
        self._artifact(2, set_id=2150451, source="hoyolab", content_fingerprint=None)
        self._observe(2, 1001)
        with closing(connect_db(self.db)) as conn:
            # Canonical set mapping later backfills the previously unresolved row.
            conn.execute("UPDATE artifacts SET content_fingerprint = 'same-rolls' WHERE id = 2")
            conn.commit()
            self.assertEqual(find_ambiguous_mixed_source_artifact_groups(conn), ((1, 2),))

        result = load_gcsim_optimizer_artifact_database_input(
            self.db, engine_context=_engine_context(),
        )
        self.assertTrue(result.ready)
        assert result.database_input is not None
        self.assertEqual([row.artifact_id for row in result.database_input.artifacts], [1, 2])
        self.assertEqual(result.database_input.eligible_5_star_artifact_ids, ())
        self.assertTrue(all(
            any(issue.code == "artifact_mixed_source_copy_ambiguous" for issue in row.issues)
            for row in result.database_input.artifacts
        ))
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 2)

    def test_simultaneously_observed_hoyolab_twins_remain_eligible(self) -> None:
        self._artifact(1, set_id=2150451, source="hoyolab", content_fingerprint="same-rolls")
        self._artifact(2, set_id=2150451, source="hoyolab", content_fingerprint="same-rolls")
        self._observe(1, 1001)
        self._observe(2, 1002)
        result = load_gcsim_optimizer_artifact_database_input(
            self.db, engine_context=_engine_context(),
        )
        self.assertTrue(result.ready)
        assert result.database_input is not None
        self.assertEqual(result.database_input.eligible_5_star_artifact_ids, (1, 2))

    def test_mixed_source_rows_are_allowed_when_both_seen_together(self) -> None:
        self._artifact(1, set_id=None, source="artiscan", content_fingerprint="same-rolls")
        self._artifact(2, set_id=2150451, source="hoyolab", content_fingerprint="same-rolls")
        self._observe(1, 1001)
        self._observe(2, 1002)
        with closing(connect_db(self.db)) as conn:
            self.assertEqual(find_ambiguous_mixed_source_artifact_groups(conn), ())
        result = load_gcsim_optimizer_artifact_database_input(
            self.db, engine_context=_engine_context(),
        )
        assert result.database_input is not None
        self.assertEqual(result.database_input.eligible_5_star_artifact_ids, (1, 2))

    def test_selected_team_blocks_two_ambiguous_ids_but_not_single_wearer(self) -> None:
        self._artifact(1, set_id=None, source="artiscan", content_fingerprint="same-rolls")
        self._artifact(2, set_id=2150451, source="hoyolab", content_fingerprint="same-rolls")
        self._observe(2, 1002)

        def detail(_conn, slot, **_kwargs):
            artifact_id = slot["character"]["id"]
            return SelectedTeamCharacterDetail(
                slot_index=slot["slot_index"], status=SELECTED_TEAM_CONFIG_READY,
                ready=True, payload_character={
                    "artifact_build": {"artifact_ids_by_pos": {"1": artifact_id}}
                },
            )

        with patch("run_workspace.gcsim.selected_team_config._build_slot_payload", side_effect=detail):
            single = build_selected_team_payload(
                db_path=self.db, selected_team={"slots": [
                    {"slot_index": 0, "character": {"id": 1}},
                ]},
            )
            pair = build_selected_team_payload(
                db_path=self.db, selected_team={"slots": [
                    {"slot_index": 0, "character": {"id": 1}},
                    {"slot_index": 1, "character": {"id": 2}},
                ]},
            )
        self.assertTrue(single.ready)
        self.assertFalse(pair.ready)
        self.assertIn("artifact_mixed_source_copy_ambiguous", [issue.status for issue in pair.issues])


if __name__ == "__main__":
    unittest.main()
