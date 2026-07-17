from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from hoyolab_export.artifact_db import connect_db, init_db
from run_workspace.artifact_optimizer import (
    ArtifactOptimizationRequest,
    build_candidate_snapshot,
    connect_artifact_db_readonly,
    load_optimizer_artifacts,
    optimize_artifacts_from_db,
)


class ArtifactOptimizerRepositoryTest(unittest.TestCase):
    def test_loader_aggregates_main_substats_and_equipment(self) -> None:
        with _temporary_db() as db_path:
            _seed_db(db_path)

            with closing(connect_artifact_db_readonly(db_path)) as conn:
                artifacts = load_optimizer_artifacts(conn)

        flower = artifacts[0]
        self.assertEqual(flower.artifact_id, 1)
        self.assertEqual(flower.set_key, "set-a")
        self.assertEqual(flower.stat_value(2), 4780.0)
        self.assertEqual(flower.stat_value(20), 3.9)
        self.assertEqual(flower.equipped_character_ids, (10000001,))

    def test_db_optimization_and_snapshot_use_project_contract(self) -> None:
        with _temporary_db() as db_path:
            _seed_db(db_path)

            report = optimize_artifacts_from_db(
                ArtifactOptimizationRequest(
                    weights={20: 2.0, 22: 1.0},
                    per_slot_limit=None,
                    per_set_limit=None,
                    max_combinations=None,
                ),
                db_path=db_path,
            )
            with closing(connect_artifact_db_readonly(db_path)) as conn:
                snapshot = build_candidate_snapshot(conn, report.candidates[0])

        self.assertEqual(report.candidates[0].artifact_ids(), (1, 2, 3, 4, 5))
        self.assertEqual(snapshot.artifact_ids_by_pos, {1: 1, 2: 2, 3: 3, 4: 4, 5: 5})
        self.assertEqual(snapshot.missing_positions, ())
        self.assertEqual(snapshot.crit_value, 76.5)


class _temporary_db:
    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        return Path(self._tmp.name) / "artifacts.db"

    def __exit__(self, exc_type, exc, tb) -> None:
        self._tmp.cleanup()


def _seed_db(db_path: Path) -> None:
    now = "2026-07-17T00:00:00+00:00"
    with closing(connect_db(db_path)) as conn:
        init_db(conn)
        for pos in range(1, 6):
            artifact_id = pos
            conn.execute(
                """
                INSERT INTO artifacts (
                    id, fingerprint, name, set_uid, set_name, pos, pos_name,
                    rarity, level, main_property_type, main_property_name,
                    main_property_value, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    f"optimizer-{artifact_id}",
                    f"Artifact {artifact_id}",
                    "set-a" if pos <= 4 else "set-b",
                    "Set A" if pos <= 4 else "Set B",
                    pos,
                    f"Position {pos}",
                    5,
                    20,
                    2 if pos == 1 else 6,
                    "HP" if pos == 1 else "ATK%",
                    "4780" if pos == 1 else "46.6%",
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO artifact_substats (
                    artifact_id, slot_index, property_type, property_name,
                    value, times
                ) VALUES (?, 0, 20, 'CRIT Rate', ?, 1)
                """,
                (artifact_id, f"{2.9 + pos}%"),
            )
            conn.execute(
                """
                INSERT INTO artifact_substats (
                    artifact_id, slot_index, property_type, property_name,
                    value, times
                ) VALUES (?, 1, 22, 'CRIT DMG', '3.5%', 1)
                """,
                (artifact_id,),
            )
        conn.execute(
            """
            INSERT INTO artifact_equipment (
                artifact_id, character_id, character_name, pos, imported_at
            ) VALUES (1, 10000001, 'Amber', 1, ?)
            """,
            (now,),
        )
        conn.commit()


if __name__ == "__main__":
    unittest.main()
