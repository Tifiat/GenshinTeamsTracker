from __future__ import annotations

import unittest

from run_workspace.pvp.schedule import (
    ACTION_BAN_CHARACTER,
    ACTION_PICK_CHARACTER,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
)
from run_workspace.pvp.session import (
    REJECT_CHARACTER_GLOBALLY_BANNED,
    REJECT_CHARACTER_NOT_IN_DECK,
    REJECT_CHARACTER_UNAVAILABLE_TO_OPPONENT,
    REJECT_DUPLICATE_ACTION_ID,
    REJECT_DUPLICATE_SEQUENCE,
    REJECT_OUT_OF_TURN,
    REJECT_WRONG_ACTION_TYPE,
    DraftAction,
    DraftActionRejected,
    apply_draft_action,
    create_draft_session,
    replay_draft_actions,
)

from ._fixtures import (
    default_draft_actions,
    load_sample_decks,
    play_default_sample_draft,
    synthetic_deck,
)


class DraftSessionReducerTests(unittest.TestCase):
    def test_valid_full_default_draft_completes_and_replays(self) -> None:
        state = play_default_sample_draft()
        initial = create_draft_session(*load_sample_decks())

        replayed = replay_draft_actions(initial, state.accepted_actions)

        self.assertTrue(state.is_complete)
        self.assertEqual(len(state.accepted_actions), 22)
        self.assertEqual(len(state.player_1_picked_character_ids), 8)
        self.assertEqual(len(state.player_2_picked_character_ids), 8)
        self.assertEqual(len(state.player_1_banned_character_ids), 3)
        self.assertEqual(len(state.player_2_banned_character_ids), 3)
        self.assertEqual(replayed.to_dict(), state.to_dict())
        self.assertEqual(replayed.state_hash(), state.state_hash())

    def test_rejects_out_of_turn_and_wrong_action_type(self) -> None:
        state = create_draft_session(*load_sample_decks())

        self.assert_rejected(
            state,
            DraftAction(SEAT_PLAYER_2, ACTION_BAN_CHARACTER, "test_p1_char_01"),
            REJECT_OUT_OF_TURN,
        )
        self.assert_rejected(
            state,
            DraftAction(SEAT_PLAYER_1, ACTION_PICK_CHARACTER, "test_p1_char_01"),
            REJECT_WRONG_ACTION_TYPE,
        )

    def test_rejects_duplicate_action_id_and_sequence(self) -> None:
        state = create_draft_session(*load_sample_decks())
        state = apply_draft_action(
            state,
            DraftAction(
                SEAT_PLAYER_1,
                ACTION_BAN_CHARACTER,
                "test_p2_char_12",
                action_id="same",
                sequence=1,
            ),
        )

        self.assert_rejected(
            state,
            DraftAction(
                SEAT_PLAYER_2,
                ACTION_BAN_CHARACTER,
                "test_p1_char_12",
                action_id="same",
                sequence=2,
            ),
            REJECT_DUPLICATE_ACTION_ID,
        )
        self.assert_rejected(
            state,
            DraftAction(
                SEAT_PLAYER_2,
                ACTION_BAN_CHARACTER,
                "test_p1_char_12",
                action_id="other",
                sequence=1,
            ),
            REJECT_DUPLICATE_SEQUENCE,
        )

    def test_rejects_globally_banned_and_missing_pick(self) -> None:
        state = create_draft_session(*load_sample_decks())
        for action in default_draft_actions()[:4]:
            state = apply_draft_action(state, action)

        self.assert_rejected(
            state,
            DraftAction(SEAT_PLAYER_1, ACTION_PICK_CHARACTER, "test_p1_char_12"),
            REJECT_CHARACTER_GLOBALLY_BANNED,
        )
        self.assert_rejected(
            state,
            DraftAction(SEAT_PLAYER_1, ACTION_PICK_CHARACTER, "not_in_deck"),
            REJECT_CHARACTER_NOT_IN_DECK,
        )

    def test_global_ban_blocks_both_decks(self) -> None:
        player_1_deck = synthetic_deck("p1", shared_character_ids=("shared_char",))
        player_2_deck = synthetic_deck("p2", shared_character_ids=("shared_char",))
        state = create_draft_session(player_1_deck, player_2_deck)
        actions = (
            DraftAction(SEAT_PLAYER_1, ACTION_BAN_CHARACTER, "shared_char"),
            DraftAction(SEAT_PLAYER_2, ACTION_BAN_CHARACTER, "p1_char_12"),
            DraftAction(SEAT_PLAYER_1, ACTION_BAN_CHARACTER, "p2_char_12"),
            DraftAction(SEAT_PLAYER_2, ACTION_BAN_CHARACTER, "p1_char_11"),
            DraftAction(SEAT_PLAYER_1, ACTION_PICK_CHARACTER, "p1_char_02"),
        )
        for action in actions:
            state = apply_draft_action(state, action)

        self.assertIn("shared_char", state.banned_character_ids)
        self.assert_rejected(
            state,
            DraftAction(SEAT_PLAYER_2, ACTION_PICK_CHARACTER, "shared_char"),
            REJECT_CHARACTER_GLOBALLY_BANNED,
        )

    def test_non_immune_pick_blocks_opponent(self) -> None:
        player_1_deck = synthetic_deck("p1", shared_character_ids=("shared_char",))
        player_2_deck = synthetic_deck("p2", shared_character_ids=("shared_char",))
        state = create_draft_session(player_1_deck, player_2_deck)
        actions = (
            DraftAction(SEAT_PLAYER_1, ACTION_BAN_CHARACTER, "p2_char_12"),
            DraftAction(SEAT_PLAYER_2, ACTION_BAN_CHARACTER, "p1_char_12"),
            DraftAction(SEAT_PLAYER_1, ACTION_BAN_CHARACTER, "p2_char_11"),
            DraftAction(SEAT_PLAYER_2, ACTION_BAN_CHARACTER, "p1_char_11"),
            DraftAction(SEAT_PLAYER_1, ACTION_PICK_CHARACTER, "shared_char"),
        )
        for action in actions:
            state = apply_draft_action(state, action)

        self.assert_rejected(
            state,
            DraftAction(SEAT_PLAYER_2, ACTION_PICK_CHARACTER, "shared_char"),
            REJECT_CHARACTER_UNAVAILABLE_TO_OPPONENT,
        )

    def assert_rejected(
        self,
        state,
        action: DraftAction,
        code: str,
    ) -> None:
        with self.assertRaises(DraftActionRejected) as context:
            apply_draft_action(state, action)
        self.assertEqual(context.exception.code, code)


if __name__ == "__main__":
    unittest.main()
