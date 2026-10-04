from __future__ import annotations

import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hoyolab_export.artifact_db import (
    connect_db,
    create_build_preset,
    init_db,
)
from hoyolab_export.artifact_importer import import_character_details_payload
from hoyolab_export.artifact_set_catalog import UnmappedArtifactSetError


SET_ID = 2_150_451


def _relic(*, relic_id: int | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "name": "Lucky Dog's Goblet",
        "pos": 1,
        "pos_name": "Goblet of Eonothem",
        "rarity": 4,
        "level": 12,
        "set": {"id": SET_ID, "name": "Celestial Gift"},
        "main_property": {"property_type": 1, "value": "46.6%"},
        "sub_property_list": [
            {"property_type": 2, "value": "5.8%", "times": 2},
            {"property_type": 3, "value": "19", "times": 1},
        ],
    }
    if relic_id is not None:
        result["id"] = relic_id
    return result


def _payload(characters: list[tuple[int, str, dict[str, object]]]) -> dict[str, object]:
    return {
        "json": {
            "retcode": 0,
            "data": {
                "property_map": {
                    "1": {"name": "HP%"},
                    "2": {"name": "ATK%"},
                    "3": {"name": "DEF"},
                },
                "list": [
                    {
                        "base": {"id": char_id, "name": name},
                        "relics": [relic],
                    }
                    for char_id, name, relic in characters
                ],
            },
        }
    }


class ArtifactSourceIdentityTest(unittest.TestCase):
    def _ready_connection(self, path: Path):
        conn = connect_db(path)
        init_db(conn)
        return conn

    def test_unmapped_set_is_stored_and_strict_default_rejects(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "artifacts.db"
            with closing(self._ready_connection(db_path)) as conn:
                summary = import_character_details_payload(
                    _payload([(1001, "Amber", _relic(relic_id=701))]),
                    conn=conn,
                    initialize=False,
                    allow_unmapped_sets=True,
                )

                self.assertEqual(summary["artifacts_inserted"], 1)
                self.assertEqual(summary["relics_unresolved_set"], 1)
                self.assertEqual(summary["relics_skipped_unmapped"], 0)
                self.assertTrue(summary["equipment_updated"])
                self.assertEqual(summary["equipment_rows"], 1)
                self.assertEqual(summary["unresolved_sets"][0]["hoyolab_set_id"], SET_ID)
                self.assertEqual(summary["unresolved_sets"][0]["name"], "Celestial Gift")

                row = conn.execute(
                    """
                    SELECT relic_id, set_id, set_uid, set_name,
                        content_fingerprint, source_content_fingerprint
                    FROM artifacts
                    """
                ).fetchone()
                self.assertEqual(row["relic_id"], 701)
                self.assertEqual(row["set_id"], SET_ID)
                self.assertIsNone(row["set_uid"])
                self.assertEqual(row["set_name"], "Celestial Gift")
                self.assertIsNone(row["content_fingerprint"])
                self.assertTrue(row["source_content_fingerprint"])

                conn.execute(
                    "UPDATE artifacts SET source_content_fingerprint = NULL"
                )
                init_db(conn)
                backfilled = conn.execute(
                    "SELECT source_content_fingerprint FROM artifacts"
                ).fetchone()["source_content_fingerprint"]
                self.assertEqual(backfilled, row["source_content_fingerprint"])

                with self.assertRaises(UnmappedArtifactSetError):
                    import_character_details_payload(
                        _payload([(1001, "Amber", _relic(relic_id=701))]),
                        conn=conn,
                        initialize=False,
                    )

    def test_numeric_zero_is_retained_and_matches_string_zero(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "artifacts.db"
            relic = _relic(relic_id=701)
            relic["main_property"]["value"] = 0
            with closing(self._ready_connection(db_path)) as conn:
                first = import_character_details_payload(
                    _payload([(1001, "Amber", relic)]), conn=conn,
                    initialize=False, allow_unmapped_sets=True,
                )
                self.assertEqual(first["artifacts_inserted"], 1)
                self.assertEqual(conn.execute("SELECT main_property_value FROM artifacts").fetchone()[0], "0")
                relic["main_property"]["value"] = "0"
                repeated = import_character_details_payload(
                    _payload([(1001, "Amber", relic)]), conn=conn,
                    initialize=False, allow_unmapped_sets=True,
                )
                self.assertEqual(repeated["artifacts_inserted"], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 1)

    def test_identical_unresolved_twins_keep_ids_across_repeated_reordered_import(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "artifacts.db"
            first_snapshot = _payload(
                [
                    (1001, "Amber", _relic()),
                    (1002, "Kaeya", _relic()),
                ]
            )
            reordered_snapshot = _payload(
                [
                    (1002, "Kaeya", _relic()),
                    (1001, "Amber", _relic()),
                ]
            )

            with closing(self._ready_connection(db_path)) as conn:
                first = import_character_details_payload(
                    first_snapshot,
                    conn=conn,
                    initialize=False,
                    allow_unmapped_sets=True,
                )
                first_ids = {
                    int(row["character_id"]): int(row["artifact_id"])
                    for row in conn.execute(
                        "SELECT character_id, artifact_id FROM artifact_equipment"
                    )
                }
                self.assertEqual(first["artifacts_inserted"], 2)
                self.assertEqual(len(set(first_ids.values())), 2)

                second = import_character_details_payload(
                    reordered_snapshot,
                    conn=conn,
                    initialize=False,
                    allow_unmapped_sets=True,
                )
                second_ids = {
                    int(row["character_id"]): int(row["artifact_id"])
                    for row in conn.execute(
                        "SELECT character_id, artifact_id FROM artifact_equipment"
                    )
                }

                self.assertEqual(second["artifacts_inserted"], 0)
                self.assertEqual(second["artifacts_existing"], 2)
                self.assertEqual(second_ids, first_ids)
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0],
                    2,
                )

    def test_later_canonical_binding_preserves_artifact_and_preset_ids(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "artifacts.db"
            snapshot = _payload(
                [
                    (1001, "Amber", _relic()),
                    (1002, "Kaeya", _relic()),
                ]
            )

            with closing(self._ready_connection(db_path)) as conn:
                import_character_details_payload(
                    snapshot,
                    conn=conn,
                    initialize=False,
                    allow_unmapped_sets=True,
                )
                artifact_ids = {
                    int(row["character_id"]): int(row["artifact_id"])
                    for row in conn.execute(
                        "SELECT character_id, artifact_id FROM artifact_equipment"
                    )
                }
                preset_id = create_build_preset(
                    conn,
                    name="Amber source identity test",
                    slots={1: artifact_ids[1001]},
                )
                conn.execute(
                    """
                    INSERT INTO artifact_sets (
                        set_uid, hoyowiki_entry_id, hoyolab_set_id,
                        fallback_name, source, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("CelestialGift", "test-celestial-gift", SET_ID,
                     "Celestial Gift", "test", "now"),
                )

                bound = import_character_details_payload(
                    _payload(
                        [
                            (1002, "Kaeya", _relic()),
                            (1001, "Amber", _relic()),
                        ]
                    ),
                    conn=conn,
                    initialize=False,
                    allow_unmapped_sets=True,
                )
                bound_ids = {
                    int(row["character_id"]): int(row["artifact_id"])
                    for row in conn.execute(
                        "SELECT character_id, artifact_id FROM artifact_equipment"
                    )
                }
                rows = conn.execute(
                    "SELECT id, set_uid, content_fingerprint FROM artifacts ORDER BY id"
                ).fetchall()
                preset_artifact_id = conn.execute(
                    "SELECT artifact_id FROM artifact_build_slots WHERE build_id = ? AND pos = 1",
                    (preset_id,),
                ).fetchone()["artifact_id"]

                self.assertEqual(bound["relics_unresolved_set"], 0)
                self.assertEqual(bound_ids, artifact_ids)
                self.assertEqual(len(rows), 2)
                self.assertTrue(all(row["set_uid"] == "CelestialGift" for row in rows))
                self.assertTrue(all(row["content_fingerprint"] for row in rows))
                self.assertEqual(int(preset_artifact_id), artifact_ids[1001])

                with patch(
                    "hoyolab_export.artifact_importer.resolve_hoyolab_set_uid",
                    side_effect=UnmappedArtifactSetError(
                        hoyolab_set_id=SET_ID,
                        display_name="Celestial Gift",
                    ),
                ):
                    unavailable = import_character_details_payload(
                        snapshot,
                        conn=conn,
                        initialize=False,
                        allow_unmapped_sets=True,
                    )
                retained = conn.execute(
                    "SELECT id, set_uid FROM artifacts ORDER BY id"
                ).fetchall()
                self.assertEqual(unavailable["relics_unresolved_set"], 2)
                self.assertEqual(
                    {row["set_uid"] for row in retained},
                    {"CelestialGift"},
                )
                self.assertEqual(
                    {int(row["id"]) for row in retained},
                    set(artifact_ids.values()),
                )

    def test_caller_owned_connection_keeps_writes_rollbackable(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "artifacts.db"
            with closing(self._ready_connection(db_path)) as conn:
                conn.execute("BEGIN")
                with patch(
                    "hoyolab_export.artifact_importer.init_db",
                    side_effect=AssertionError("caller-owned connection must not initialize"),
                ), patch(
                    "hoyolab_export.artifact_importer.ensure_artifact_set_catalog",
                    side_effect=AssertionError("caller-owned connection must not initialize catalog"),
                ):
                    import_character_details_payload(
                        _payload([(1001, "Amber", _relic(relic_id=701))]),
                        conn=conn,
                        initialize=False,
                        allow_unmapped_sets=True,
                    )

                self.assertTrue(conn.in_transaction)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 1)
                conn.rollback()

            with closing(connect_db(db_path)) as reader:
                self.assertEqual(reader.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 0)
                self.assertEqual(reader.execute("SELECT COUNT(*) FROM artifact_equipment").fetchone()[0], 0)

    def test_self_owned_strict_failure_rolls_back_artifact_writes(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "artifacts.db"
            payload = _payload(
                [
                    (1001, "Amber", _relic(relic_id=701)),
                    (1002, "Kaeya", _relic(relic_id=702)),
                ]
            )
            with patch(
                "hoyolab_export.artifact_importer.resolve_hoyolab_set_uid",
                side_effect=[
                    "KnownSet",
                    UnmappedArtifactSetError(
                        hoyolab_set_id=SET_ID,
                        display_name="Celestial Gift",
                    ),
                ],
            ):
                with self.assertRaises(UnmappedArtifactSetError):
                    import_character_details_payload(payload, db_path=db_path)

            with closing(connect_db(db_path)) as reader:
                self.assertEqual(reader.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 0)
                self.assertEqual(reader.execute("SELECT COUNT(*) FROM artifact_equipment").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
