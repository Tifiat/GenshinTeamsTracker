from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from run_workspace.pvp.full_loop_smoke import (
    main,
    run_default_full_loop_smoke,
)
from run_workspace.pvp.schedule import (
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
    build_default_free_draft_v0_schedule,
)
from run_workspace.pvp.session import create_draft_session, replay_draft_actions

from ._fixtures import load_sample_decks


class PvpFullLoopSmokeTests(unittest.TestCase):
    def test_full_loop_smoke_succeeds_with_expected_counts(self) -> None:
        report = run_default_full_loop_smoke()

        self.assertEqual(report.schedule_steps_count, 14)
        self.assertEqual(report.action_count, 22)
        self.assertEqual(report.player_1.validation_status, "ready")
        self.assertEqual(report.player_2.validation_status, "ready")
        self.assertEqual(len(report.player_1.picked_character_ids), 8)
        self.assertEqual(len(report.player_2.picked_character_ids), 8)
        self.assertEqual(len(report.player_1.banned_character_ids), 3)
        self.assertEqual(len(report.player_2.banned_character_ids), 3)

    def test_full_loop_smoke_is_deterministic(self) -> None:
        first = run_default_full_loop_smoke()
        second = run_default_full_loop_smoke()

        self.assertEqual(first.state_hash, first.replay_state_hash)
        self.assertEqual(first.state_hash, second.state_hash)
        self.assertEqual(first.match_result.to_dict(), second.match_result.to_dict())

    def test_action_log_replays_to_same_final_state_hash(self) -> None:
        report = run_default_full_loop_smoke()
        player_1_deck, player_2_deck = load_sample_decks()
        initial = create_draft_session(
            player_1_deck,
            player_2_deck,
            schedule=build_default_free_draft_v0_schedule(),
        )

        replayed = replay_draft_actions(initial, report.accepted_actions)

        self.assertEqual(replayed.state_hash(), report.state_hash)
        self.assertEqual(
            tuple(replayed.player_1_picked_character_ids),
            report.player_1.picked_character_ids,
        )
        self.assertEqual(
            tuple(replayed.player_2_picked_character_ids),
            report.player_2.picked_character_ids,
        )

    def test_team_assignments_use_only_picked_characters(self) -> None:
        report = run_default_full_loop_smoke()

        for seat_summary in (report.player_1, report.player_2):
            picked = set(seat_summary.picked_character_ids)
            assigned = {
                character_id
                for team in seat_summary.teams.teams
                for character_id in team.character_ids
            }
            self.assertEqual(assigned, picked)

    def test_weapon_assignment_consumes_stack_counts_correctly(self) -> None:
        report = run_default_full_loop_smoke()
        decks = {
            SEAT_PLAYER_1: load_sample_decks()[0],
            SEAT_PLAYER_2: load_sample_decks()[1],
        }

        for seat_summary in (report.player_1, report.player_2):
            stack_by_key = decks[seat_summary.seat].weapon_stack_by_key
            for stack_key, used_count in seat_summary.weapon_stack_usage.items():
                self.assertLessEqual(used_count, stack_by_key[stack_key].count)
            self.assertEqual(sum(seat_summary.weapon_stack_usage.values()), 8)

    def test_winner_and_seconds_difference_are_stable(self) -> None:
        report = run_default_full_loop_smoke()

        self.assertEqual(report.player_1.timer_total_seconds, 315)
        self.assertEqual(report.player_2.timer_total_seconds, 345)
        self.assertEqual(report.match_result.winner_seat, SEAT_PLAYER_1)
        self.assertEqual(report.match_result.seconds_difference, 30)

    def test_cli_entrypoint_prints_compact_report(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = main([])

        text = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("PvP full-loop smoke:", text)
        self.assertIn("Schedule/actions: 14 steps, 22 actions", text)
        self.assertIn("State hash:", text)


if __name__ == "__main__":
    unittest.main()
