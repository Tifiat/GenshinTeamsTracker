from __future__ import annotations

import unittest
from types import SimpleNamespace

from run_workspace.models import (
    RUN_TYPE_ABYSS,
    SNAPSHOT_SOURCE_LEGACY_RIGHT_PANEL,
    WARNING_TEAM2_ELAPSED_NEGATIVE,
    AbyssTimerState,
    build_legacy_abyss_run_snapshot,
    calculate_abyss_chamber_result,
)


def legacy_slot(
    character_path: str | None = None,
    weapon_path: str | None = None,
    artifact_path: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        char=SimpleNamespace(image_path=character_path),
        weapon=SimpleNamespace(image_path=weapon_path),
        artifact=SimpleNamespace(image_path=artifact_path),
    )


def legacy_floor(team1_left: int, team2_left: int) -> SimpleNamespace:
    return SimpleNamespace(
        t1=SimpleNamespace(seconds_left=team1_left),
        t2=SimpleNamespace(seconds_left=team2_left),
    )


class RunWorkspaceModelsTest(unittest.TestCase):
    def test_calculate_abyss_chamber_result_normal_values(self) -> None:
        result = calculate_abyss_chamber_result(
            AbyssTimerState(team1_left_seconds=550, team2_left_seconds=500),
            chamber_index=2,
        )

        self.assertEqual(result.chamber_index, 2)
        self.assertEqual(result.team1_elapsed_seconds, 50)
        self.assertEqual(result.team2_elapsed_seconds, 50)
        self.assertEqual(result.total_elapsed_seconds, 100)
        self.assertEqual(result.warnings, ())

    def test_calculate_abyss_chamber_result_never_returns_negative_team2(self) -> None:
        result = calculate_abyss_chamber_result(
            AbyssTimerState(team1_left_seconds=590, team2_left_seconds=596),
        )

        self.assertEqual(result.team1_elapsed_seconds, 10)
        self.assertEqual(result.team2_elapsed_seconds, 0)
        self.assertEqual(result.total_elapsed_seconds, 10)
        self.assertIn(WARNING_TEAM2_ELAPSED_NEGATIVE, result.warnings)

    def test_build_legacy_abyss_run_snapshot_preserves_legacy_paths(self) -> None:
        snapshot = build_legacy_abyss_run_snapshot(
            teams=[
                [legacy_slot("char-a.png", "weapon-a.png", "artifact-a.png")],
                [legacy_slot("char-b.png")],
            ],
            floors=[
                legacy_floor(550, 500),
                legacy_floor(500, 480),
            ],
        )

        data = snapshot.to_dict()

        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["run_type"], RUN_TYPE_ABYSS)
        self.assertEqual(data["source"], SNAPSHOT_SOURCE_LEGACY_RIGHT_PANEL)
        self.assertEqual(data["total_elapsed_seconds"], 220)
        self.assertEqual(
            data["teams"][0]["slots"][0],
            {
                "character_path": "char-a.png",
                "weapon_path": "weapon-a.png",
                "artifact_path": "artifact-a.png",
            },
        )
        self.assertIsNone(data["teams"][1]["slots"][0]["weapon_path"])
        self.assertEqual(data["chambers"][0]["team1_elapsed_seconds"], 50)
        self.assertEqual(data["chambers"][1]["team2_elapsed_seconds"], 20)


if __name__ == "__main__":
    unittest.main()
