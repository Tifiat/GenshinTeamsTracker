from __future__ import annotations

import unittest

from run_workspace.pvp.schedule import (
    ACTION_BAN_CHARACTER,
    ACTION_PICK_CHARACTER,
    PHASE_PICK,
    PHASE_PREBAN,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
    build_default_free_draft_v0_schedule,
)


class FreeDraftScheduleTests(unittest.TestCase):
    def test_default_schedule_shape_is_contract_shape(self) -> None:
        schedule = build_default_free_draft_v0_schedule()

        self.assertEqual(
            [step.to_dict() for step in schedule.steps],
            [
                _step(PHASE_PREBAN, SEAT_PLAYER_1, ACTION_BAN_CHARACTER),
                _step(PHASE_PREBAN, SEAT_PLAYER_2, ACTION_BAN_CHARACTER),
                _step(PHASE_PREBAN, SEAT_PLAYER_1, ACTION_BAN_CHARACTER),
                _step(PHASE_PREBAN, SEAT_PLAYER_2, ACTION_BAN_CHARACTER),
                _step(PHASE_PICK, SEAT_PLAYER_1, ACTION_PICK_CHARACTER),
                _step(PHASE_PICK, SEAT_PLAYER_2, ACTION_PICK_CHARACTER, ACTION_PICK_CHARACTER),
                _step(PHASE_PICK, SEAT_PLAYER_1, ACTION_PICK_CHARACTER, ACTION_PICK_CHARACTER),
                _step(PHASE_PICK, SEAT_PLAYER_2, ACTION_PICK_CHARACTER, ACTION_PICK_CHARACTER),
                _step(PHASE_PICK, SEAT_PLAYER_1, ACTION_PICK_CHARACTER, ACTION_BAN_CHARACTER),
                _step(PHASE_PICK, SEAT_PLAYER_2, ACTION_PICK_CHARACTER, ACTION_BAN_CHARACTER),
                _step(PHASE_PICK, SEAT_PLAYER_1, ACTION_PICK_CHARACTER, ACTION_PICK_CHARACTER),
                _step(PHASE_PICK, SEAT_PLAYER_2, ACTION_PICK_CHARACTER, ACTION_PICK_CHARACTER),
                _step(PHASE_PICK, SEAT_PLAYER_1, ACTION_PICK_CHARACTER, ACTION_PICK_CHARACTER),
                _step(PHASE_PICK, SEAT_PLAYER_2, ACTION_PICK_CHARACTER),
            ],
        )

    def test_default_schedule_counts_picks_and_bans_by_seat(self) -> None:
        counts = build_default_free_draft_v0_schedule().expected_action_counts()

        self.assertEqual(counts[SEAT_PLAYER_1][ACTION_BAN_CHARACTER], 3)
        self.assertEqual(counts[SEAT_PLAYER_2][ACTION_BAN_CHARACTER], 3)
        self.assertEqual(counts[SEAT_PLAYER_1][ACTION_PICK_CHARACTER], 8)
        self.assertEqual(counts[SEAT_PLAYER_2][ACTION_PICK_CHARACTER], 8)


def _step(phase: str, seat: str, *actions: str) -> dict[str, object]:
    return {
        "phase": phase,
        "seat": seat,
        "actions": [{"type": action} for action in actions],
    }


if __name__ == "__main__":
    unittest.main()
