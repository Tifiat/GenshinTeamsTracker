from __future__ import annotations

import unittest
from dataclasses import replace

from run_workspace.pvp.account_full_loop_smoke import copy_deck_for_player_2
from run_workspace.pvp.free_draft_planner import (
    ISSUE_NO_COMPATIBLE_WEAPON_STACK,
    ISSUE_NO_LEGAL_DRAFT_ACTION,
    ISSUE_TEAM_ASSIGNMENT_PICK_COUNT_INVALID,
    plan_free_draft_actions,
    plan_free_draft_team_assignment,
    plan_free_draft_weapon_assignment,
)
from run_workspace.pvp.schedule import SEAT_PLAYER_1, SEAT_PLAYER_2
from run_workspace.pvp.session import replay_draft_actions

from ._fixtures import completed_sample_state, synthetic_deck


class FreeDraftPlannerTests(unittest.TestCase):
    def test_distinct_decks_complete_default_free_draft_schedule(self) -> None:
        player_1 = synthetic_deck("planner_p1", character_count=12)
        player_2 = synthetic_deck("planner_p2", character_count=12)

        report = plan_free_draft_actions(player_1, player_2)

        self.assertTrue(report.ready)
        self.assertEqual(report.action_count, 22)
        self.assertIsNotNone(report.initial_state)
        self.assertIsNotNone(report.final_state)
        self.assertEqual(len(report.final_state.player_1_banned_character_ids), 3)
        self.assertEqual(len(report.final_state.player_2_banned_character_ids), 3)
        self.assertEqual(len(report.final_state.player_1_picked_character_ids), 8)
        self.assertEqual(len(report.final_state.player_2_picked_character_ids), 8)
        replayed = replay_draft_actions(report.initial_state, report.actions)
        self.assertEqual(replayed.state_hash(), report.final_state.state_hash())

    def test_copied_small_deck_reports_no_legal_action(self) -> None:
        player_1 = synthetic_deck("planner_copy", character_count=12)
        player_2 = copy_deck_for_player_2(player_1)

        report = plan_free_draft_actions(player_1, player_2)

        self.assertFalse(report.ready)
        self.assertIn(ISSUE_NO_LEGAL_DRAFT_ACTION, report.issue_codes())
        self.assertLess(report.action_count, 22)

    def test_team_assignment_splits_eight_picks_into_two_teams(self) -> None:
        state = completed_sample_state()

        report = plan_free_draft_team_assignment(state, SEAT_PLAYER_1)

        self.assertTrue(report.ready)
        self.assertEqual(
            [len(team.character_ids) for team in report.assignment.teams],
            [4, 4],
        )
        self.assertEqual(report.validation_report.status, "ready")

    def test_team_assignment_reports_invalid_pick_count(self) -> None:
        state = completed_sample_state(
            player_1_picks=tuple(f"test_p1_char_{index:02d}" for index in range(1, 8))
        )

        report = plan_free_draft_team_assignment(state, SEAT_PLAYER_1)

        self.assertFalse(report.ready)
        self.assertIn(ISSUE_TEAM_ASSIGNMENT_PICK_COUNT_INVALID, report.issue_codes())
        self.assertFalse(report.validation_report.ready)

    def test_weapon_assignment_uses_available_compatible_stacks(self) -> None:
        state = completed_sample_state()
        team_report = plan_free_draft_team_assignment(state, SEAT_PLAYER_2)

        report = plan_free_draft_weapon_assignment(state, team_report.assignment)

        self.assertTrue(report.ready)
        self.assertEqual(len(report.assignment.assignments), 8)
        self.assertEqual(sum(report.stack_usage.values()), 8)

    def test_weapon_assignment_reports_missing_compatible_stack(self) -> None:
        state = completed_sample_state()
        first_pick = state.player_1_picked_character_ids[0]
        missing_type = state.player_1_deck.character_by_id[first_pick].weapon_type
        player_1_deck = replace(
            state.player_1_deck,
            weapons=tuple(
                stack
                for stack in state.player_1_deck.weapons
                if stack.weapon_type.casefold() != missing_type.casefold()
            ),
        )
        state = replace(state, player_1_deck=player_1_deck)
        team_report = plan_free_draft_team_assignment(state, SEAT_PLAYER_1)

        report = plan_free_draft_weapon_assignment(state, team_report.assignment)

        self.assertFalse(report.ready)
        self.assertIn(ISSUE_NO_COMPATIBLE_WEAPON_STACK, report.issue_codes())
        self.assertFalse(report.validation_report.ready)


if __name__ == "__main__":
    unittest.main()
