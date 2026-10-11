"""Explicit no-target BAN/PREBAN actions keep the draft log replayable."""

from __future__ import annotations

import unittest
from dataclasses import replace

from run_workspace.pvp.abyss_match_rules import (
    abyss_immune_context,
    build_abyss_match_definition,
    calculate_abyss_prebans,
)
from run_workspace.pvp.schedule import (
    ACTION_BAN_CHARACTER,
    ACTION_IMMUNE_BAN_CHARACTER,
    ACTION_PICK_CHARACTER,
    ACTION_PREBAN_CHARACTER,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
)
from run_workspace.pvp.session import (
    DraftAction,
    DraftActionRejected,
    REJECT_DUPLICATE_ACTION_ID,
    REJECT_DUPLICATE_SEQUENCE,
    REJECT_MISSING_CHARACTER_ID,
    REJECT_SKIP_ACTION_UNSUPPORTED,
    REJECT_SKIP_INVALID,
    REJECT_SKIP_TARGET_PRESENT,
    REJECT_WRONG_ACTION_TYPE,
    apply_draft_action,
    create_draft_session,
    replay_draft_actions,
)
from tests.run_workspace.pvp.test_abyss_dynamic_preban import _priced_pair


def _session():
    rules, cheap, expensive = _priced_pair(120)
    prebans = calculate_abyss_prebans(cheap, expensive, rules)
    eligible, absolute = abyss_immune_context(cheap, expensive, rules)
    schedule = build_abyss_match_definition(rules, preban_report=prebans).build_schedule()
    return create_draft_session(
        cheap, expensive, schedule=schedule, validate_decks=False,
        rules_content_hash=rules.content_hash,
        immune_eligible_character_ids=eligible,
        absolute_immune_character_ids=absolute,
    )


class DraftBanSkipTests(unittest.TestCase):
    def test_skip_prebans_and_bans_replay_to_eight_picks(self) -> None:
        initial = _session()
        state = initial
        while not state.is_complete:
            seat = state.current_seat
            kind = state.current_requirement.action_type
            sequence = len(state.accepted_actions) + 1
            if kind in (ACTION_PREBAN_CHARACTER, ACTION_BAN_CHARACTER):
                action = DraftAction(seat, kind, action_id=f"skip-{sequence}",
                                     sequence=sequence, skip=True)
                self.assertEqual(action.to_dict()["skip"], True)
                self.assertEqual(DraftAction.from_dict(action.to_dict()), action)
                next_state = apply_draft_action(state, action)
                self.assertEqual(next_state.banned_character_ids, state.banned_character_ids)
            else:
                for character_id in sorted(
                    state.deck_for(seat).character_ids
                    | set(state.immune_eligible_character_ids)
                ):
                    action = DraftAction(seat, kind, character_id,
                                         action_id=f"target-{sequence}", sequence=sequence)
                    try:
                        next_state = apply_draft_action(state, action)
                    except DraftActionRejected:
                        continue
                    break
                else:
                    self.fail(f"No legal target at {sequence}: {kind} for {seat}")
            state = next_state
        self.assertEqual(len(state.accepted_actions), 28)
        self.assertEqual(len(state.banned_character_ids), 0)
        self.assertEqual(len(state.picked_character_ids_for(SEAT_PLAYER_1)), 8)
        self.assertEqual(len(state.picked_character_ids_for(SEAT_PLAYER_2)), 8)
        parsed = tuple(DraftAction.from_dict(item.to_dict()) for item in state.accepted_actions)
        replayed = replay_draft_actions(initial, parsed)
        self.assertEqual(replayed.state_hash(), state.state_hash())
        self.assertEqual(replayed.to_dict(), state.to_dict())

    def test_default_shape_and_invalid_skip_forms(self) -> None:
        state = _session()
        normal = DraftAction(SEAT_PLAYER_1, ACTION_PREBAN_CHARACTER, "1000")
        self.assertNotIn("skip", normal.to_dict())
        self.assertEqual(DraftAction.from_dict(normal.to_dict()), normal)
        for bad in (None, 0, 1, "true"):
            with self.subTest(bad=bad):
                action = DraftAction(SEAT_PLAYER_1, ACTION_PREBAN_CHARACTER, skip=bad)
                with self.assertRaises(DraftActionRejected) as raised:
                    apply_draft_action(state, action)
                self.assertEqual(raised.exception.code, REJECT_SKIP_INVALID)
                with self.assertRaises(ValueError):
                    DraftAction.from_dict({**normal.to_dict(), "skip": bad})

        cases = (
            (DraftAction(SEAT_PLAYER_1, ACTION_PREBAN_CHARACTER, "1000", skip=True),
             REJECT_SKIP_TARGET_PRESENT),
            (DraftAction(SEAT_PLAYER_1, ACTION_PREBAN_CHARACTER, " ", skip=True),
             REJECT_SKIP_TARGET_PRESENT),
            (DraftAction(SEAT_PLAYER_1, ACTION_PREBAN_CHARACTER),
             REJECT_MISSING_CHARACTER_ID),
            (DraftAction(SEAT_PLAYER_1, ACTION_BAN_CHARACTER, skip=True),
             REJECT_WRONG_ACTION_TYPE),
            (DraftAction(SEAT_PLAYER_1, ACTION_IMMUNE_BAN_CHARACTER, skip=True),
             REJECT_WRONG_ACTION_TYPE),
        )
        for action, expected in cases:
            with self.subTest(action=action), self.assertRaises(DraftActionRejected) as raised:
                apply_draft_action(state, action)
            self.assertEqual(raised.exception.code, expected)
        pick_state = replace(state, step_index=10)
        with self.assertRaises(DraftActionRejected) as raised:
            apply_draft_action(pick_state, DraftAction(
                pick_state.current_seat, ACTION_PICK_CHARACTER, skip=True))
        self.assertEqual(raised.exception.code, REJECT_SKIP_ACTION_UNSUPPORTED)
        immune_state = replace(state, step_index=2)
        with self.assertRaises(DraftActionRejected) as raised:
            apply_draft_action(immune_state, DraftAction(
                immune_state.current_seat, ACTION_IMMUNE_BAN_CHARACTER, skip=True))
        self.assertEqual(raised.exception.code, REJECT_SKIP_ACTION_UNSUPPORTED)

    def test_skip_obeys_identity_sequence_and_turn(self) -> None:
        state = _session()
        first = DraftAction(SEAT_PLAYER_1, ACTION_PREBAN_CHARACTER,
                            action_id="same", sequence=1, skip=True)
        state = apply_draft_action(state, first)
        for action, expected in (
            (DraftAction(SEAT_PLAYER_1, ACTION_PREBAN_CHARACTER,
                         action_id="same", sequence=2, skip=True), REJECT_DUPLICATE_ACTION_ID),
            (DraftAction(SEAT_PLAYER_1, ACTION_PREBAN_CHARACTER,
                         action_id="fresh", sequence=1, skip=True), REJECT_DUPLICATE_SEQUENCE),
        ):
            with self.assertRaises(DraftActionRejected) as raised:
                apply_draft_action(state, action)
            self.assertEqual(raised.exception.code, expected)


if __name__ == "__main__":
    unittest.main()
