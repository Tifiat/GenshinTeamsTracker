from __future__ import annotations

import unittest
from types import SimpleNamespace

from run_workspace.models import RUN_TYPE_ABYSS, SNAPSHOT_SOURCE_LEGACY_RIGHT_PANEL
from ui.main_window import App


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


class MainWindowRunSnapshotAdapterTest(unittest.TestCase):
    def test_build_current_run_snapshot_uses_legacy_state_without_qapp(self) -> None:
        legacy_app = SimpleNamespace(
            teams=[
                [legacy_slot("char-a.png", "weapon-a.png", "artifact-a.png")],
                [legacy_slot("char-b.png")],
            ],
            floors=[
                legacy_floor(590, 580),
                legacy_floor(550, 500),
            ],
        )

        snapshot = App.build_current_run_snapshot(legacy_app)
        data = snapshot.to_dict()

        self.assertEqual(data["run_type"], RUN_TYPE_ABYSS)
        self.assertEqual(data["source"], SNAPSHOT_SOURCE_LEGACY_RIGHT_PANEL)
        self.assertEqual(data["total_elapsed_seconds"], 120)
        self.assertEqual(
            data["teams"][0]["slots"][0],
            {
                "character_path": "char-a.png",
                "weapon_path": "weapon-a.png",
                "artifact_path": "artifact-a.png",
            },
        )


if __name__ == "__main__":
    unittest.main()
