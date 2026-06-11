from __future__ import annotations

import unittest

from hoyolab_export.artifact_build_snapshot import (
    WARNING_ARTIFACT_BUILD_INCOMPLETE,
    WARNING_ARTIFACT_SUMMARY_MISSING,
    WARNING_CONDITIONAL_SET_BONUSES_NOT_INCLUDED,
    WARNING_SET_BONUS_FORMULAS_NOT_INCLUDED,
    ArtifactBuildSnapshot,
    build_artifact_build_snapshot,
)
from hoyolab_export.character_stat_snapshot import build_character_stat_snapshot
from tests.hoyolab_export.catalog.test_character_stat_snapshot import character_entry, weapon_entry


def raw_summary() -> dict:
    return {
        "artifact_ids_by_pos": {1: 101, 2: 102, 3: 103, 4: 104},
        "missing_positions": [5],
        "set_counts": [
            {"set_uid": "gladiators_finale", "set_name": "Gladiator", "count": 4},
        ],
        "total_stats": [
            {"property_type": 20, "property_name": "CRIT Rate", "raw_value": 31.1},
            {"property_type": 22, "property_name": "CRIT DMG", "raw_value": 62.2},
        ],
        "crit_value": 124.4,
        "proc_count": 9,
    }


def build_preset() -> dict:
    return {
        "id": 7,
        "name": "Noelle DEF",
        "slots": [
            {
                "pos": 1,
                "artifact_id": 101,
                "name": "Flower",
                "set_uid": "gladiators_finale",
                "set_name": "Gladiator",
                "rarity": 5,
                "level": 20,
                "main_property_type": 2,
                "main_property_name": "HP",
                "main_property_value": "4780",
            },
        ],
    }


class ArtifactBuildSnapshotTest(unittest.TestCase):
    def test_missing_artifact_summary_snapshot_warns(self) -> None:
        snapshot = build_artifact_build_snapshot()

        self.assertIsInstance(snapshot, ArtifactBuildSnapshot)
        self.assertIn(WARNING_ARTIFACT_SUMMARY_MISSING, snapshot.warnings)

    def test_raw_summary_is_converted_to_build_snapshot(self) -> None:
        snapshot = build_artifact_build_snapshot(raw_summary(), build_preset=build_preset())

        self.assertEqual(snapshot.build_id, 7)
        self.assertEqual(snapshot.build_name, "Noelle DEF")
        self.assertEqual(snapshot.artifact_ids_by_pos[1], 101)
        self.assertEqual(snapshot.missing_positions, (5,))
        self.assertEqual(snapshot.stat_totals[0].property_type, 20)
        self.assertEqual(snapshot.crit_value, 124.4)
        self.assertEqual(snapshot.proc_count, 9)
        self.assertIn(WARNING_ARTIFACT_BUILD_INCOMPLETE, snapshot.warnings)

    def test_set_counts_create_reference_active_set_bonus_and_formula_warnings(self) -> None:
        snapshot = build_artifact_build_snapshot(raw_summary())

        self.assertEqual(len(snapshot.set_counts), 1)
        self.assertEqual(snapshot.active_set_bonuses[0].piece_count, 4)
        self.assertIn(WARNING_SET_BONUS_FORMULAS_NOT_INCLUDED, snapshot.warnings)
        self.assertIn(WARNING_CONDITIONAL_SET_BONUSES_NOT_INCLUDED, snapshot.warnings)

    def test_character_stat_snapshot_carries_artifact_build_snapshot(self) -> None:
        artifact_snapshot = build_artifact_build_snapshot(
            raw_summary(),
            build_preset=build_preset(),
        )
        snapshot = build_character_stat_snapshot(
            account_character={"id": 1, "name": "Amber", "level": 1},
            character_stats_entry=character_entry(),
            account_weapon={"id": 2, "name": "Favonius Warbow", "level": 1},
            weapon_stats_entry=weapon_entry(),
            artifact_summary=artifact_snapshot,
        )

        self.assertEqual(snapshot.artifact.summary["build_id"], 7)
        self.assertEqual(snapshot.artifact.summary["stat_totals"][0]["property_type"], 20)
        self.assertIn(WARNING_SET_BONUS_FORMULAS_NOT_INCLUDED, snapshot.artifact.warnings)

    def test_character_stat_snapshot_keeps_missing_artifact_summary_warning(self) -> None:
        snapshot = build_character_stat_snapshot(
            account_character={"id": 1, "name": "Amber", "level": 1},
            character_stats_entry=character_entry(),
            account_weapon={"id": 2, "name": "Favonius Warbow", "level": 1},
            weapon_stats_entry=weapon_entry(),
        )

        self.assertIn(WARNING_ARTIFACT_SUMMARY_MISSING, snapshot.artifact.warnings)


if __name__ == "__main__":
    unittest.main()
