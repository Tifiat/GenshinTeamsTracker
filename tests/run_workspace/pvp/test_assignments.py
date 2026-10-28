from __future__ import annotations

import unittest

from run_workspace.pvp.schedule import SEAT_PLAYER_1, SEAT_PLAYER_2
from run_workspace.pvp.session import (
    ISSUE_DUPLICATE_TEAM_CHARACTER,
    ISSUE_PICKED_CHARACTER_NOT_ASSIGNED,
    ISSUE_TEAM_CHARACTER_NOT_PICKED,
    ISSUE_TEAM_SIZE_INVALID,
    ISSUE_WEAPON_STACK_COUNT_EXCEEDED,
    ISSUE_WEAPON_TYPE_MISMATCH,
    CharacterWeaponAssignment,
    PlayerTeamAssignment,
    PlayerWeaponAssignment,
    TeamAssignment,
    validate_team_assignment,
    validate_weapon_assignment,
)

from ._fixtures import completed_sample_state, stack_key_for, team_assignment


class PvpAssignmentTests(unittest.TestCase):
    def test_valid_two_teams_of_four(self) -> None:
        state = completed_sample_state()
        assignment = team_assignment(SEAT_PLAYER_1, state.player_1_picked_character_ids)

        report = validate_team_assignment(state, assignment)

        self.assertTrue(report.ready)

    def test_team_assignment_rejects_non_picked_character(self) -> None:
        state = completed_sample_state()
        character_ids = state.player_1_picked_character_ids[:7] + ("test_p1_char_09",)
        assignment = team_assignment(SEAT_PLAYER_1, character_ids)

        report = validate_team_assignment(state, assignment)

        self.assertFalse(report.ready)
        self.assertIn(ISSUE_TEAM_CHARACTER_NOT_PICKED, report.issue_codes())
        self.assertIn(ISSUE_PICKED_CHARACTER_NOT_ASSIGNED, report.issue_codes())

    def test_team_assignment_rejects_duplicate_character(self) -> None:
        state = completed_sample_state()
        picks = state.player_1_picked_character_ids
        assignment = team_assignment(SEAT_PLAYER_1, (picks[0],) + picks[:7])

        report = validate_team_assignment(state, assignment)

        self.assertFalse(report.ready)
        self.assertIn(ISSUE_DUPLICATE_TEAM_CHARACTER, report.issue_codes())

    def test_team_assignment_rejects_incomplete_team(self) -> None:
        state = completed_sample_state()
        assignment = PlayerTeamAssignment(
            seat=SEAT_PLAYER_1,
            teams=(
                TeamAssignment(0, state.player_1_picked_character_ids[:4]),
                TeamAssignment(1, state.player_1_picked_character_ids[4:7]),
            ),
        )

        report = validate_team_assignment(state, assignment)

        self.assertFalse(report.ready)
        self.assertIn(ISSUE_TEAM_SIZE_INVALID, report.issue_codes())

    def test_valid_weapon_assignment(self) -> None:
        state = completed_sample_state()
        teams = team_assignment(SEAT_PLAYER_1, state.player_1_picked_character_ids)
        weapons = _weapon_assignment_for(state, teams)

        report = validate_weapon_assignment(state, teams, weapons)

        self.assertTrue(report.ready)

    def test_weapon_assignment_rejects_wrong_weapon_type(self) -> None:
        state = completed_sample_state()
        teams = team_assignment(SEAT_PLAYER_1, state.player_1_picked_character_ids)
        valid = _weapon_assignment_for(state, teams)
        wrong_stack_key = stack_key_for(state.player_1_deck, "BOW")
        weapons = PlayerWeaponAssignment(
            seat=SEAT_PLAYER_1,
            assignments=(
                CharacterWeaponAssignment("test_p1_char_01", wrong_stack_key),
            )
            + valid.assignments[1:],
        )

        report = validate_weapon_assignment(state, teams, weapons)

        self.assertFalse(report.ready)
        self.assertIn(ISSUE_WEAPON_TYPE_MISMATCH, report.issue_codes())

    def test_weapon_assignment_rejects_stack_count_exceeded(self) -> None:
        picks = (
            "test_p1_char_01",
            "test_p1_char_06",
            "test_p1_char_11",
            "test_p1_char_02",
            "test_p1_char_03",
            "test_p1_char_04",
            "test_p1_char_05",
            "test_p1_char_07",
        )
        state = completed_sample_state(player_1_picks=picks)
        teams = team_assignment(SEAT_PLAYER_1, picks)
        weapons = _weapon_assignment_for(state, teams)

        report = validate_weapon_assignment(state, teams, weapons)

        self.assertFalse(report.ready)
        self.assertIn(ISSUE_WEAPON_STACK_COUNT_EXCEEDED, report.issue_codes())

    def test_weapon_pools_are_per_player(self) -> None:
        state = completed_sample_state()
        p1_teams = team_assignment(SEAT_PLAYER_1, state.player_1_picked_character_ids)
        p2_teams = team_assignment(SEAT_PLAYER_2, state.player_2_picked_character_ids)

        p1_report = validate_weapon_assignment(
            state,
            p1_teams,
            _weapon_assignment_for(state, p1_teams),
        )
        p2_report = validate_weapon_assignment(
            state,
            p2_teams,
            _weapon_assignment_for(state, p2_teams),
        )

        self.assertTrue(p1_report.ready)
        self.assertTrue(p2_report.ready)


def _weapon_assignment_for(
    state,
    teams: PlayerTeamAssignment,
) -> PlayerWeaponAssignment:
    deck = state.deck_for(teams.seat)
    character_by_id = deck.character_by_id
    assignments: list[CharacterWeaponAssignment] = []
    for team in teams.teams:
        for character_id in team.character_ids:
            weapon_type = character_by_id[character_id].weapon_type
            assignments.append(
                CharacterWeaponAssignment(
                    character_id=character_id,
                    weapon_stack_key=stack_key_for(deck, weapon_type),
                )
            )
    return PlayerWeaponAssignment(seat=teams.seat, assignments=tuple(assignments))


if __name__ == "__main__":
    unittest.main()
