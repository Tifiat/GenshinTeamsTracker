from __future__ import annotations

import unittest
from types import SimpleNamespace

from run_workspace.models import (
    ABYSS_CHAMBER_START_SECONDS,
    ABYSS_TIMER_EDIT_MIN_SECONDS,
    RUN_TYPE_ABYSS,
    SNAPSHOT_SOURCE_LEGACY_RIGHT_PANEL,
    WARNING_TEAM2_ELAPSED_NEGATIVE,
    AbyssTimerState,
    adjust_abyss_timer_seconds_with_second_wheel,
    build_legacy_abyss_run_snapshot,
    calculate_abyss_chamber_result,
    clamp_abyss_timer_edit_seconds,
    default_abyss_timer_states,
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
    def test_default_abyss_timer_states_start_at_legacy_full_time(self) -> None:
        states = default_abyss_timer_states()

        self.assertEqual(len(states), 3)
        self.assertTrue(
            all(
                state.team1_left_seconds == ABYSS_CHAMBER_START_SECONDS
                and state.team2_left_seconds == ABYSS_CHAMBER_START_SECONDS
                for state in states
            )
        )

    def test_edit_timer_clamp_uses_legacy_visible_range(self) -> None:
        self.assertEqual(
            clamp_abyss_timer_edit_seconds(10),
            ABYSS_TIMER_EDIT_MIN_SECONDS,
        )
        self.assertEqual(
            clamp_abyss_timer_edit_seconds(999),
            ABYSS_CHAMBER_START_SECONDS,
        )

    def test_second_wheel_wraps_across_minutes_and_clamps(self) -> None:
        self.assertEqual(
            adjust_abyss_timer_seconds_with_second_wheel(5 * 60, -1),
            5 * 60,
        )
        self.assertEqual(
            adjust_abyss_timer_seconds_with_second_wheel(5 * 60 + 59, 1),
            6 * 60,
        )
        self.assertEqual(
            adjust_abyss_timer_seconds_with_second_wheel(10 * 60, 1),
            10 * 60,
        )

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
