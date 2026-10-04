from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from hoyolab_export.account_equipment import EquipmentError
from run_workspace.pvp.artifact_equipment import PvpArtifactEquipment


class PvpArtifactEquipmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "source.sqlite"
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("CREATE TABLE artifacts (id INTEGER PRIMARY KEY, pos INTEGER)")
            conn.executemany("INSERT INTO artifacts VALUES (?, ?)", ((7, 1), (8, 1), (9, 2)))
            conn.commit()
        self.original = self.path.read_bytes()
        self.first = PvpArtifactEquipment(self.path, frozenset({"1001", "1002"}))
        self.second = PvpArtifactEquipment(self.path, frozenset({"1001", "1002"}))

    def test_same_ids_are_independent_and_source_is_unchanged(self) -> None:
        self.first.toggle_artifact(1001, 7)
        self.second.toggle_artifact(1002, 7)
        self.assertEqual(self.first.get_equipped_artifact_owner(7), 1001)
        self.assertEqual(self.second.get_equipped_artifact_owner(7), 1002)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_move_and_replacement_refresh_both_wearers(self) -> None:
        self.first.apply_artifact_preset(1001, {1: 7, 2: 9})
        result = self.first.toggle_artifact(1002, 7)
        self.assertEqual(result.affected_character_ids, (1001, 1002))
        self.assertEqual(self.first.artifact_ids_for_character(1001), {"plume": 9})
        self.first.toggle_artifact(1002, 8)
        self.assertIsNone(self.first.get_equipped_artifact_owner(7))
        self.first.toggle_artifact(1002, 8)
        self.assertEqual(self.first.artifact_ids_for_character(1002), {})

    def test_preset_is_atomic_and_clears_unlisted_slots(self) -> None:
        self.first.apply_artifact_preset(1001, {1: 7, 2: 9})
        for invalid in ({1: 8, 2: 999}, {1: 9}, {1: True}):
            with self.subTest(invalid=invalid), self.assertRaises(EquipmentError):
                self.first.apply_artifact_preset(1001, invalid)
            self.assertEqual(self.first.artifact_ids_for_character(1001), {"flower": 7, "plume": 9})
        self.first.apply_artifact_preset(1001, {1: 8})
        self.assertEqual(self.first.artifact_ids_for_character(1001), {"flower": 8})
        self.assertFalse(self.first.apply_artifact_preset(1001, {1: 8}).changed)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_occupied_artifact_swaps_like_normal_equipment(self) -> None:
        self.first.apply_artifact_preset(1001, {1: 7})
        self.first.apply_artifact_preset(1002, {1: 8})
        result = self.first.toggle_artifact(1002, 7)
        self.assertEqual(result.affected_character_ids, (1001, 1002))
        self.assertEqual(self.first.artifact_ids_for_character(1001), {"flower": 8})
        self.assertEqual(self.first.artifact_ids_for_character(1002), {"flower": 7})
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_unknown_target_and_missing_inventory_never_create_files(self) -> None:
        with self.assertRaises(EquipmentError):
            self.first.toggle_artifact(9999, 7)
        missing = Path(self.temporary.name) / "missing.sqlite"
        state = PvpArtifactEquipment(missing, frozenset({"1001"}))
        with self.assertRaises(EquipmentError):
            state.toggle_artifact(1001, 7)
        self.assertFalse(missing.exists())
