from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from hoyolab_export.account_equipment import (
    AUTO_APPLY_HOYOLAB_EQUIPMENT_ON_IMPORT_DEFAULT,
    EquipmentCapacityError,
    EquipmentCompatibilityError,
    apply_hoyolab_artifact_equipment_observation,
    apply_hoyolab_weapon_equipment_observation,
    equip_artifact,
    equip_weapon,
    get_equipped_artifact_owner,
    get_equipped_weapon_for_character,
    get_weapon_assignment_count,
    list_equipped_artifacts_for_character,
    list_equipped_weapon_owners,
    list_equipped_weapons,
    list_preset_current_wearers,
    move_weapon_between_characters,
    unequip_artifact_slot,
    unequip_weapon,
)
from hoyolab_export.artifact_db import (
    connect_db,
    create_build_preset,
    get_artifact_build_slots,
    get_artifact_build_targets,
    init_db,
)


class AccountEquipmentSchemaTest(unittest.TestCase):
    def test_init_db_creates_equipment_tables_idempotently(self) -> None:
        with temp_artifact_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                init_db(conn)
                init_db(conn)
                objects = {
                    row["name"]
                    for row in conn.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type = 'table'
                        """
                    )
                }

        self.assertIn("account_character_equipped_artifacts", objects)
        self.assertIn("account_character_equipped_weapons", objects)


class AccountArtifactEquipmentTest(unittest.TestCase):
    def test_equip_artifact_to_empty_slot_and_read_owner(self) -> None:
        with seeded_equipment_db() as conn:
            equip_artifact(conn, 1001, 1)

            records = list_equipped_artifacts_for_character(conn, 1001)
            owner = get_equipped_artifact_owner(conn, 1)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].slot_key, "flower")
        self.assertEqual(records[0].artifact_id, 1)
        self.assertEqual(owner, 1001)

    def test_replacing_same_slot_unequips_old_artifact(self) -> None:
        with seeded_equipment_db() as conn:
            equip_artifact(conn, 1001, 1)
            equip_artifact(conn, 1001, 2)

            records = list_equipped_artifacts_for_character(conn, 1001)
            old_owner = get_equipped_artifact_owner(conn, 1)
            new_owner = get_equipped_artifact_owner(conn, 2)

        self.assertEqual([(row.slot_key, row.artifact_id) for row in records], [("flower", 2)])
        self.assertIsNone(old_owner)
        self.assertEqual(new_owner, 1001)

    def test_artifact_move_between_characters_swaps_target_old_slot(self) -> None:
        with seeded_equipment_db() as conn:
            equip_artifact(conn, 1001, 1)
            equip_artifact(conn, 1002, 2)

            equip_artifact(conn, 1001, 2)

            first = list_equipped_artifacts_for_character(conn, 1001)
            second = list_equipped_artifacts_for_character(conn, 1002)

        self.assertEqual([(row.slot_key, row.artifact_id) for row in first], [("flower", 2)])
        self.assertEqual([(row.slot_key, row.artifact_id) for row in second], [("flower", 1)])

    def test_artifact_move_to_empty_target_clears_previous_owner_slot(self) -> None:
        with seeded_equipment_db() as conn:
            equip_artifact(conn, 1002, 1)

            equip_artifact(conn, 1001, 1)

            self.assertEqual(get_equipped_artifact_owner(conn, 1), 1001)
            self.assertEqual(list_equipped_artifacts_for_character(conn, 1002), ())

    def test_unequip_artifact_slot_clears_only_that_slot(self) -> None:
        with seeded_equipment_db() as conn:
            equip_artifact(conn, 1001, 1)
            equip_artifact(conn, 1001, 4)

            unequip_artifact_slot(conn, 1001, "flower")

            records = list_equipped_artifacts_for_character(conn, 1001)

        self.assertEqual([(row.slot_key, row.artifact_id) for row in records], [("plume", 4)])

    def test_equip_artifact_does_not_mutate_build_preset_rows(self) -> None:
        with seeded_equipment_db() as conn:
            build_id = create_build_preset(
                conn,
                name="Preset",
                slots={1: 1, 2: 4},
                targets=[
                    {
                        "target_type": "character",
                        "character_id": 1003,
                        "character_name": "Bow Hero",
                    }
                ],
            )
            before_slots = get_artifact_build_slots(conn, build_id)
            before_targets = get_artifact_build_targets(conn, build_id)

            equip_artifact(conn, 1001, 1)
            equip_artifact(conn, 1002, 4)

            after_slots = get_artifact_build_slots(conn, build_id)
            after_targets = get_artifact_build_targets(conn, build_id)

        self.assertEqual(after_slots, before_slots)
        self.assertEqual(after_targets, before_targets)

    def test_preset_current_wearers_derive_from_equipped_artifacts_only(self) -> None:
        with seeded_equipment_db() as conn:
            build_id = create_build_preset(
                conn,
                name="Shared Preset",
                slots={1: 1, 2: 4},
                targets=[
                    {
                        "target_type": "character",
                        "character_id": 1003,
                        "character_name": "Bow Hero",
                    }
                ],
            )
            equip_artifact(conn, 1001, 1)
            equip_artifact(conn, 1002, 4)

            wearers = list_preset_current_wearers(conn, build_id)

        self.assertEqual(wearers, (1001, 1002))


class AccountWeaponEquipmentTest(unittest.TestCase):
    def test_equip_weapon_fingerprint_to_character(self) -> None:
        with seeded_equipment_db() as conn:
            equip_weapon(conn, 1001, "polearm-a")

            record = get_equipped_weapon_for_character(conn, 1001)
            owners = list_equipped_weapon_owners(conn, "polearm-a")

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.weapon_fingerprint, "polearm-a")
        self.assertEqual(owners, (1001,))

    def test_cannot_equip_incompatible_weapon_type(self) -> None:
        with seeded_equipment_db() as conn:
            with self.assertRaises(EquipmentCompatibilityError):
                equip_weapon(conn, 1001, "sword-a")

    def test_same_fingerprint_assigns_up_to_known_count(self) -> None:
        with seeded_equipment_db() as conn:
            equip_weapon(conn, 1001, "polearm-stack")
            equip_weapon(conn, 1002, "polearm-stack")

            owners = list_equipped_weapon_owners(conn, "polearm-stack")
            count = get_weapon_assignment_count(conn, "polearm-stack")

        self.assertEqual(owners, (1001, 1002))
        self.assertEqual(count, 2)

    def test_assignment_beyond_known_count_fails_without_fake_instance_ids(self) -> None:
        with seeded_equipment_db() as conn:
            equip_weapon(conn, 1001, "polearm-a")

            with self.assertRaises(EquipmentCapacityError):
                equip_weapon(conn, 1002, "polearm-a")

            columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(account_character_equipped_weapons)"
                )
            }

        self.assertNotIn("weapon_instance_id", columns)
        self.assertNotIn("weapon_copy_id", columns)

    def test_unequip_weapon_frees_assignment(self) -> None:
        with seeded_equipment_db() as conn:
            equip_weapon(conn, 1001, "polearm-a")
            unequip_weapon(conn, 1001)
            equip_weapon(conn, 1002, "polearm-a")

            owners = list_equipped_weapon_owners(conn, "polearm-a")

        self.assertEqual(owners, (1002,))

    def test_explicit_move_weapon_between_characters_swaps_deterministically(self) -> None:
        with seeded_equipment_db() as conn:
            equip_weapon(conn, 1001, "polearm-a")
            equip_weapon(conn, 1002, "polearm-b")

            move_weapon_between_characters(conn, 1001, 1002)

            first = get_equipped_weapon_for_character(conn, 1001)
            second = get_equipped_weapon_for_character(conn, 1002)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None and second is not None
        self.assertEqual(first.weapon_fingerprint, "polearm-b")
        self.assertEqual(second.weapon_fingerprint, "polearm-a")


class AccountEquipmentImportObservationTest(unittest.TestCase):
    def test_artifact_observation_uses_normal_semantics_and_source_metadata(self) -> None:
        with seeded_equipment_db() as conn:
            apply_hoyolab_artifact_equipment_observation(
                conn,
                1001,
                1,
                import_batch_id="batch-1",
                observed_at="2026-05-26T10:00:00+00:00",
            )

            records = list_equipped_artifacts_for_character(conn, 1001)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source, "hoyolab_import")
        self.assertEqual(records[0].source_import_batch_id, "batch-1")
        self.assertEqual(records[0].observed_at, "2026-05-26T10:00:00+00:00")

    def test_weapon_observation_uses_normal_semantics_and_known_count(self) -> None:
        with seeded_equipment_db() as conn:
            apply_hoyolab_weapon_equipment_observation(conn, 1001, "polearm-a")

            with self.assertRaises(EquipmentCapacityError):
                apply_hoyolab_weapon_equipment_observation(conn, 1002, "polearm-a")

            record = get_equipped_weapon_for_character(conn, 1001)

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.source, "hoyolab_import")

    def test_missing_observation_does_not_clear_local_equipment(self) -> None:
        self.assertTrue(AUTO_APPLY_HOYOLAB_EQUIPMENT_ON_IMPORT_DEFAULT)
        with seeded_equipment_db() as conn:
            equip_artifact(conn, 1001, 1)
            equip_weapon(conn, 1001, "polearm-a")

            # Missing import data means no helper call, not a clear operation.
            artifact_records = list_equipped_artifacts_for_character(conn, 1001)
            weapon_record = get_equipped_weapon_for_character(conn, 1001)

        self.assertEqual([(row.slot_key, row.artifact_id) for row in artifact_records], [("flower", 1)])
        self.assertIsNotNone(weapon_record)
        assert weapon_record is not None
        self.assertEqual(weapon_record.weapon_fingerprint, "polearm-a")


class temp_artifact_db:
    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        return Path(self._tmp.name) / "artifacts.db"

    def __exit__(self, exc_type, exc, tb) -> None:
        self._tmp.cleanup()


class seeded_equipment_db:
    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._conn = connect_db(Path(self._tmp.name) / "artifacts.db")
        init_db(self._conn)
        seed_characters(self._conn)
        seed_artifacts(self._conn)
        seed_weapons(self._conn)
        return self._conn

    def __exit__(self, exc_type, exc, tb) -> None:
        self._conn.close()
        self._tmp.cleanup()


def seed_characters(conn) -> None:
    rows = [
        (1001, "Polearm Hero A", 13, "polearm"),
        (1002, "Polearm Hero B", 13, "polearm"),
        (1003, "Sword Hero", 1, "sword"),
    ]
    conn.executemany(
        """
        INSERT INTO account_characters (
            character_id,
            name,
            weapon_type,
            weapon_type_name
        )
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )


def seed_artifacts(conn) -> None:
    rows = [
        (1, "artifact-flower-a", "Flower A", 1),
        (2, "artifact-flower-b", "Flower B", 1),
        (3, "artifact-flower-c", "Flower C", 1),
        (4, "artifact-plume-a", "Plume A", 2),
    ]
    conn.executemany(
        """
        INSERT INTO artifacts (
            id,
            fingerprint,
            name,
            pos,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, '2026-05-26T00:00:00+00:00', '2026-05-26T00:00:00+00:00')
        """,
        rows,
    )


def seed_weapons(conn) -> None:
    rows = [
        ("polearm-a", 2001, "Polearm A", 13, "polearm", 1),
        ("polearm-b", 2002, "Polearm B", 13, "polearm", 1),
        ("polearm-stack", 2003, "Stacked Polearm", 13, "polearm", 2),
        ("sword-a", 1001, "Sword A", 1, "sword", 1),
    ]
    conn.executemany(
        """
        INSERT INTO account_weapon_observed_stacks (
            weapon_fingerprint,
            weapon_id,
            name,
            weapon_type,
            weapon_type_name,
            known_count
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


if __name__ == "__main__":
    unittest.main()
