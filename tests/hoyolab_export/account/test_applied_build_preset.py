from __future__ import annotations

import unittest
from contextlib import closing

from hoyolab_export.account_equipment import (
    EquipmentError,
    apply_hoyolab_equipment_snapshot,
    equip_artifact,
    equip_weapon,
    get_applied_build_preset,
    init_account_equipment_storage,
    remember_applied_build_preset,
    get_equipped_artifact_owner,
    unequip_artifact,
    unequip_artifact_slot,
)
from hoyolab_export.artifact_db import (
    connect_db, create_build_preset, delete_build_preset,
    replace_artifact_build_slots, update_build_preset,
)
from tests.hoyolab_export.account.test_account_equipment import seeded_equipment_db


def apply_fixture(conn, character_id=1001, *, flower=1, name="Top build"):
    build_id = create_build_preset(conn, name=name, slots={1: flower, 2: 4})
    equip_artifact(conn, character_id, flower, source="preset_equip")
    equip_artifact(conn, character_id, 4, source="preset_equip")
    remember_applied_build_preset(conn, character_id, build_id)
    return build_id


class AppliedBuildPresetTest(unittest.TestCase):
    def test_standalone_artifact_services_still_initialize_missing_tables(self):
        operations = (
            lambda conn: get_equipped_artifact_owner(conn, 1),
            lambda conn: equip_artifact(conn, 1001, 1),
            lambda conn: unequip_artifact(conn, 1),
            lambda conn: unequip_artifact_slot(conn, 1001, 1),
            lambda conn: remember_applied_build_preset(conn, 1001, create_build_preset(conn, name="Empty")),
        )
        for index, operation in enumerate(operations):
            with self.subTest(operation=index), seeded_equipment_db() as conn:
                for table in ("account_character_applied_build_presets", "account_character_equipped_artifacts",
                              "account_character_equipped_weapons"):
                    conn.execute(f"DROP TABLE {table}")
                operation(conn)
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertTrue({"account_character_applied_build_presets", "account_character_equipped_artifacts",
                                 "account_character_equipped_weapons"}.issubset(tables))

    def test_existing_equipment_migrates_without_inventing_applied_preset(self):
        with seeded_equipment_db() as conn:
            equip_artifact(conn, 1001, 1)
            conn.execute("DROP TABLE account_character_applied_build_presets")
            for event in ("insert", "delete", "update"):
                conn.execute(f"DROP TRIGGER applied_build_preset_artifact_{event}")
            init_account_equipment_storage(conn)
            init_account_equipment_storage(conn)
            self.assertIsNone(get_applied_build_preset(conn, 1001))
            self.assertEqual(conn.execute(
                "SELECT artifact_id FROM account_character_equipped_artifacts WHERE character_id=1001"
            ).fetchone()[0], 1)

    def test_marker_survives_reopening_database_and_is_per_character(self):
        with seeded_equipment_db() as conn:
            build_id = apply_fixture(conn)
            conn.commit()
            path = conn.execute("PRAGMA database_list").fetchone()[2]
            with closing(connect_db(path)) as reopened:
                self.assertEqual(get_applied_build_preset(reopened, 1001),
                                 {"build_id": build_id, "name": "Top build"})
                self.assertIsNone(get_applied_build_preset(reopened, 1002))

    def test_actual_change_clears_marker_even_if_artifacts_are_restored(self):
        with seeded_equipment_db() as conn:
            apply_fixture(conn)
            equip_artifact(conn, 1001, 2)
            equip_artifact(conn, 1001, 1)
            self.assertIsNone(get_applied_build_preset(conn, 1001))

    def test_unequip_and_artifact_deletion_clear_marker(self):
        for delete in (False, True):
            with self.subTest(delete=delete), seeded_equipment_db() as conn:
                apply_fixture(conn)
                if delete:
                    conn.execute("DELETE FROM artifacts WHERE id = 1")
                else:
                    unequip_artifact_slot(conn, 1001, 1)
                self.assertIsNone(get_applied_build_preset(conn, 1001))

    def test_swap_invalidates_both_characters(self):
        with seeded_equipment_db() as conn:
            apply_fixture(conn)
            other = create_build_preset(conn, name="Other", slots={1: 2})
            equip_artifact(conn, 1002, 2)
            remember_applied_build_preset(conn, 1002, other)
            equip_artifact(conn, 1002, 1)
            self.assertIsNone(get_applied_build_preset(conn, 1001))
            self.assertIsNone(get_applied_build_preset(conn, 1002))

    def test_noop_artifact_and_weapon_changes_preserve_marker(self):
        with seeded_equipment_db() as conn:
            build_id = apply_fixture(conn)
            equip_artifact(conn, 1001, 1)
            equip_weapon(conn, 1001, "polearm-a")
            self.assertEqual(get_applied_build_preset(conn, 1001)["build_id"], build_id)

    def test_import_preserves_same_slots_but_invalidates_replacement(self):
        with seeded_equipment_db() as conn:
            build_id = apply_fixture(conn)
            apply_hoyolab_equipment_snapshot(conn, artifacts=[(1001, 1), (1001, 4)], weapons={})
            self.assertEqual(get_applied_build_preset(conn, 1001)["build_id"], build_id)
            apply_hoyolab_equipment_snapshot(conn, artifacts=[(1001, 2)], weapons={})
            self.assertIsNone(get_applied_build_preset(conn, 1001))

    def test_rename_is_live_and_preset_edit_or_delete_invalidates_marker(self):
        with seeded_equipment_db() as conn:
            build_id = apply_fixture(conn)
            update_build_preset(conn, build_id, name="Renamed")
            self.assertEqual(get_applied_build_preset(conn, 1001)["name"], "Renamed")
            replace_artifact_build_slots(conn, build_id, {1: 2})
            self.assertIsNone(get_applied_build_preset(conn, 1001))
            build_id = apply_fixture(conn)
            delete_build_preset(conn, build_id)
            self.assertIsNone(get_applied_build_preset(conn, 1001))

    def test_character_deletion_cascades_marker(self):
        with seeded_equipment_db() as conn:
            apply_fixture(conn)
            conn.execute("DELETE FROM account_characters WHERE character_id = 1001")
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM account_character_applied_build_presets"
            ).fetchone()[0], 0)

    def test_incomplete_and_empty_presets_match_exactly(self):
        with seeded_equipment_db() as conn:
            partial = create_build_preset(conn, name="Partial", slots={1: 1})
            equip_artifact(conn, 1001, 1)
            remember_applied_build_preset(conn, 1001, partial)
            self.assertEqual(get_applied_build_preset(conn, 1001)["build_id"], partial)
            empty = create_build_preset(conn, name="Empty")
            with self.assertRaises(EquipmentError):
                remember_applied_build_preset(conn, 1001, empty)
            unequip_artifact_slot(conn, 1001, 1)
            remember_applied_build_preset(conn, 1001, empty)
            self.assertEqual(get_applied_build_preset(conn, 1001)["build_id"], empty)

    def test_equipment_reads_and_batch_writes_do_not_commit_transaction(self):
        with seeded_equipment_db() as conn:
            build_id = apply_fixture(conn)
            conn.commit()
            equip_artifact(conn, 1001, 2)
            self.assertIsNone(get_applied_build_preset(conn, 1001))
            equip_artifact(conn, 1002, 4)
            conn.rollback()
            self.assertEqual(get_applied_build_preset(conn, 1001)["build_id"], build_id)


if __name__ == "__main__":
    unittest.main()
