from __future__ import annotations

import unittest

from run_workspace.pvp.match_result import (
    MATCH_STATUS_DRAW,
    MATCH_STATUS_FINISHED,
    MATCH_STATUS_TECHNICAL_LOSS,
    ChamberTimer,
    PlayerMatchTimers,
    TechnicalLoss,
    calculate_match_result,
)
from run_workspace.pvp.schedule import SEAT_PLAYER_1, SEAT_PLAYER_2


class MatchResultTests(unittest.TestCase):
    def test_player_1_wins_with_lower_total_timer(self) -> None:
        result = calculate_match_result(
            _timers(SEAT_PLAYER_1, 90, 100),
            _timers(SEAT_PLAYER_2, 110, 120),
        )

        self.assertEqual(result.status, MATCH_STATUS_FINISHED)
        self.assertEqual(result.winner_seat, SEAT_PLAYER_1)
        self.assertEqual(result.seconds_difference, 40)

    def test_player_2_wins_with_lower_total_timer(self) -> None:
        result = calculate_match_result(
            _timers(SEAT_PLAYER_1, 140, 120),
            _timers(SEAT_PLAYER_2, 100, 90),
        )

        self.assertEqual(result.status, MATCH_STATUS_FINISHED)
        self.assertEqual(result.winner_seat, SEAT_PLAYER_2)
        self.assertEqual(result.seconds_difference, 70)

    def test_equal_total_is_draw(self) -> None:
        result = calculate_match_result(
            _timers(SEAT_PLAYER_1, 100, 120),
            _timers(SEAT_PLAYER_2, 110, 110),
        )

        self.assertEqual(result.status, MATCH_STATUS_DRAW)
        self.assertIsNone(result.winner_seat)
        self.assertEqual(result.seconds_difference, 0)

    def test_technical_loss_gives_win_to_other_player(self) -> None:
        result = calculate_match_result(
            _timers(SEAT_PLAYER_1, 90, 90),
            _timers(SEAT_PLAYER_2, 300, 300),
            technical_losses=(
                TechnicalLoss(
                    seat=SEAT_PLAYER_1,
                    reason="invalid_weapon_assignment",
                    issue_codes=("weapon_assignment_missing",),
                ),
            ),
        )

        self.assertEqual(result.status, MATCH_STATUS_TECHNICAL_LOSS)
        self.assertEqual(result.winner_seat, SEAT_PLAYER_2)
        self.assertEqual(
            result.technical_losses[0].issue_codes,
            ("weapon_assignment_missing",),
        )


def _timers(seat: str, *seconds: int) -> PlayerMatchTimers:
    return PlayerMatchTimers(
        seat=seat,
        chambers=tuple(
            ChamberTimer(
                room_id="abyss-12",
                chamber_id=f"chamber-{index}",
                elapsed_seconds=value,
            )
            for index, value in enumerate(seconds, start=1)
        ),
    )


if __name__ == "__main__":
    unittest.main()
