from __future__ import annotations

import sys
import subprocess
import unittest

from run_workspace.pvp.draft_system import (
    DRAFT_SYSTEM_FREE_DRAFT_V0,
    UnknownDraftSystemError,
    list_draft_systems,
    require_draft_system,
)
from run_workspace.pvp.schedule import (
    ACTION_BAN_CHARACTER,
    ACTION_PICK_CHARACTER,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
    build_default_free_draft_v0_schedule,
)


class DraftSystemRegistryTests(unittest.TestCase):
    def test_registry_lists_free_draft_v0(self) -> None:
        systems = list_draft_systems()

        self.assertIn(DRAFT_SYSTEM_FREE_DRAFT_V0, {item.system_id for item in systems})

    def test_free_draft_v0_definition_matches_default_schedule(self) -> None:
        system = require_draft_system(DRAFT_SYSTEM_FREE_DRAFT_V0)
        schedule = system.build_schedule()

        self.assertEqual(schedule.to_dict(), build_default_free_draft_v0_schedule().to_dict())
        self.assertEqual(system.version, "1")
        self.assertTrue(system.weapons_required)
        self.assertFalse(system.immunes_supported)
        self.assertFalse(system.mirror_supported)
        self.assertTrue(system.deterministic_smoke_planner_supported)
        self.assertIn(ACTION_BAN_CHARACTER, system.supported_action_types)
        self.assertIn(ACTION_PICK_CHARACTER, system.supported_action_types)

    def test_free_draft_v0_schedule_counts(self) -> None:
        schedule = require_draft_system(DRAFT_SYSTEM_FREE_DRAFT_V0).build_schedule()
        counts = schedule.expected_action_counts()

        self.assertEqual(counts[SEAT_PLAYER_1][ACTION_PICK_CHARACTER], 8)
        self.assertEqual(counts[SEAT_PLAYER_2][ACTION_PICK_CHARACTER], 8)
        self.assertEqual(counts[SEAT_PLAYER_1][ACTION_BAN_CHARACTER], 3)
        self.assertEqual(counts[SEAT_PLAYER_2][ACTION_BAN_CHARACTER], 3)

    def test_unknown_draft_system_fails_clearly(self) -> None:
        with self.assertRaises(UnknownDraftSystemError) as cm:
            require_draft_system("unknown_system")

        self.assertEqual(cm.exception.code, "unknown_draft_system")
        self.assertEqual(cm.exception.system_id, "unknown_system")

    def test_registry_import_does_not_pull_pyside(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "import run_workspace.pvp.draft_system; "
                    "raise SystemExit(1 if 'PySide6' in sys.modules else 0)"
                ),
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
