from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from hoyolab_export.artifact_build_snapshot_smoke import (
    ERROR_AMBIGUOUS_BUILD_NAME,
    ERROR_BUILD_PRESET_NOT_FOUND,
    ArtifactBuildSnapshotSmokeError,
    build_artifact_build_snapshot_smoke_report_from_db,
    select_build_preset_for_smoke,
)
from hoyolab_export.artifact_db import (
    connect_db,
    create_build_preset,
    init_db,
)


class ArtifactBuildSnapshotSmokeTest(unittest.TestCase):
    def test_build_name_lookup_returns_unique_preset(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                build_id = seed_artifact_build(conn, name="test111")
                conn.commit()
            with closing(connect_db(db_path)) as conn:
                preset = select_build_preset_for_smoke(conn, build_name="test111")

        self.assertEqual(preset["id"], build_id)
        self.assertEqual(preset["name"], "test111")

    def test_duplicate_build_name_is_ambiguous(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                seed_artifact_build(conn, name="same")
                seed_artifact_build(conn, name="same", first_artifact_id=100)
                conn.commit()
            with closing(connect_db(db_path)) as conn:
                with self.assertRaises(ArtifactBuildSnapshotSmokeError) as ctx:
                    select_build_preset_for_smoke(conn, build_name="same")

        self.assertEqual(ctx.exception.code, ERROR_AMBIGUOUS_BUILD_NAME)

    def test_missing_build_name_is_reported(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                seed_artifact_build(conn, name="present")
                conn.commit()
            with closing(connect_db(db_path)) as conn:
                with self.assertRaises(ArtifactBuildSnapshotSmokeError) as ctx:
                    select_build_preset_for_smoke(conn, build_name="missing")

        self.assertEqual(ctx.exception.code, ERROR_BUILD_PRESET_NOT_FOUND)

    def test_smoke_report_uses_readonly_db_and_sanitized_shape(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                build_id = seed_artifact_build(conn, name="test111")
                conn.commit()

            report = build_artifact_build_snapshot_smoke_report_from_db(
                build_name="test111",
                db_path=db_path,
                include_character_snapshot=False,
            )

        self.assertEqual(report["selected_build"]["id"], build_id)
        snapshot = report["artifact_build_snapshot"]
        self.assertEqual(snapshot["build_id"], build_id)
        self.assertEqual(snapshot["build_name"], "test111")
        self.assertEqual(snapshot["artifact_ids_by_pos"]["1"], 1)
        self.assertEqual(snapshot["crit_value"], 25.0)
        self.assertEqual(snapshot["proc_count"], 3)
        self.assertTrue(report["source_notes"]["readonly_db_connection"])
        self.assertFalse(_contains_forbidden_key(report, {"icon", "local_path", "debug"}))


class temp_artifact_db:
    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        return Path(self._tmp.name) / "artifacts.db"

    def __exit__(self, exc_type, exc, tb) -> None:
        self._tmp.cleanup()


def seed_artifact_build(conn, *, name: str, first_artifact_id: int = 1) -> int:
    now = "2026-01-01T00:00:00+00:00"
    artifact_id = first_artifact_id
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
            artifact_id,
            f"fingerprint-{artifact_id}",
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
        (artifact_id, 1, 20, "CRIT Rate", "12.5%", 3),
    )
    return create_build_preset(
        conn,
        name=name,
        slots={1: artifact_id},
        targets=[],
    )


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, dict):
        return any(
            key in forbidden or _contains_forbidden_key(item, forbidden)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


if __name__ == "__main__":
    unittest.main()
