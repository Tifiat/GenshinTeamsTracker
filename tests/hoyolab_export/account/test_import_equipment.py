import unittest
from unittest.mock import patch

from hoyolab_export import account_equipment as equipment
from hoyolab_export.artifact_db import create_build_preset
from tests.hoyolab_export.account.test_account_equipment import seeded_equipment_db


def current(conn):
    return {
        table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY character_id")]
        for table in ("account_character_equipped_artifacts", "account_character_equipped_weapons")
    }


class ImportEquipmentSnapshotTest(unittest.TestCase):
    def test_swaps_are_order_independent_preserve_missing_slots_and_presets(self):
        with seeded_equipment_db() as conn:
            equipment.equip_artifact(conn, 1001, 1)
            equipment.equip_artifact(conn, 1002, 2)
            equipment.equip_artifact(conn, 1001, 4)
            equipment.equip_weapon(conn, 1001, "polearm-a")
            equipment.equip_weapon(conn, 1002, "polearm-b")
            create_build_preset(conn, name="Keep", slots={1: 1}, targets=[])
            conn.commit()
            tables = ("artifact_builds", "artifact_build_slots", "artifact_build_targets")
            before = {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t}")] for t in tables}
            for _ in range(2):
                result = equipment.apply_hoyolab_equipment_snapshot(
                    conn, artifacts=[(1002, 1), (1001, 2)],
                    weapons={1002: "polearm-a", 1001: "polearm-b"},
                )
                self.assertEqual(result["artifacts"], 2)
                self.assertEqual(equipment.get_equipped_artifact_owner(conn, 1), 1002)
                self.assertEqual(equipment.get_equipped_artifact_owner(conn, 4), 1001)
                self.assertEqual(equipment.get_equipped_weapon_for_character(conn, 1002).weapon_fingerprint, "polearm-a")
            self.assertEqual(before, {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t}")] for t in tables})
            self.assertEqual(conn.execute("SELECT count(*) FROM artifacts").fetchone()[0], 4)

    def test_weapon_copies_are_reused_and_only_excess_old_owners_displaced(self):
        with seeded_equipment_db() as conn:
            equipment.equip_weapon(conn, 1004, "polearm-stack")
            equipment.apply_hoyolab_equipment_snapshot(conn, artifacts=[], weapons={1001: "polearm-stack"})
            self.assertEqual(equipment.list_equipped_weapon_owners(conn, "polearm-stack"), (1001, 1004))
            equipment.apply_hoyolab_equipment_snapshot(
                conn, artifacts=[], weapons={1001: "polearm-stack", 1002: "polearm-stack"},
            )
            self.assertEqual(equipment.list_equipped_weapon_owners(conn, "polearm-stack"), (1001, 1002))
            self.assertEqual(conn.execute("SELECT known_count FROM account_weapon_observed_stacks WHERE weapon_fingerprint='polearm-stack'").fetchone()[0], 2)

    def test_invalid_weapon_capacity_does_not_apply_artifacts(self):
        with seeded_equipment_db() as conn:
            equipment.equip_artifact(conn, 1001, 1)
            before = current(conn)
            with self.assertRaises(equipment.EquipmentCapacityError):
                equipment.apply_hoyolab_equipment_snapshot(
                    conn, artifacts=[(1002, 1)], weapons={1001: "polearm-a", 1002: "polearm-a"},
                )
            self.assertEqual(current(conn), before)

    def test_partial_write_failure_rolls_back_both_equipment_tables(self):
        with seeded_equipment_db() as conn:
            equipment.equip_artifact(conn, 1001, 1)
            equipment.equip_weapon(conn, 1001, "polearm-a")
            before = current(conn)
            with patch.object(equipment, "_upsert_equipped_weapon", side_effect=RuntimeError("write fixture")):
                with self.assertRaisesRegex(RuntimeError, "write fixture"):
                    equipment.apply_hoyolab_equipment_snapshot(
                        conn, artifacts=[(1002, 1)], weapons={1002: "polearm-a"},
                    )
            self.assertEqual(current(conn), before)
