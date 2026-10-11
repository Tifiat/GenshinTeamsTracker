from __future__ import annotations

import unittest

from run_workspace.pvp.schedule import (
    ACTION_BAN_CHARACTER,
    ACTION_IMMUNE_BAN_CHARACTER,
    ACTION_IMMUNE_CHARACTER,
    ACTION_IMMUNE_PICK_CHARACTER,
    ACTION_PICK_CHARACTER,
    DraftActionRequirement,
    DraftSchedule,
    DraftScheduleStep,
    PHASE_PICK,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
)
from run_workspace.pvp.session import (
    REJECT_CHARACTER_ABSOLUTELY_IMMUNE,
    REJECT_CHARACTER_ALREADY_BANNED,
    REJECT_CHARACTER_GLOBALLY_BANNED,
    REJECT_CHARACTER_PICKED_BY_SELF,
    REJECT_CHARACTER_RESERVED_FOR_IMMUNE,
    REJECT_CHARACTER_UNAVAILABLE_TO_OPPONENT,
    REJECT_CHARACTER_NOT_IMMUNE_ELIGIBLE,
    REJECT_DUPLICATE_ACTION_ID,
    REJECT_DUPLICATE_SEQUENCE,
    DraftAction,
    DraftActionRejected,
    apply_draft_action,
    create_draft_session,
)

from ._fixtures import synthetic_deck


P1 = SEAT_PLAYER_1
P2 = SEAT_PLAYER_2
BAN = ACTION_BAN_CHARACTER
PICK = ACTION_PICK_CHARACTER
PREBAN = ACTION_IMMUNE_BAN_CHARACTER
PROTECT = ACTION_IMMUNE_PICK_CHARACTER
IMMUNE = ACTION_IMMUNE_CHARACTER


def _state(*turns: tuple[str, str], abyss: bool = True, absolute: tuple[str, ...] = ()):
    schedule = DraftSchedule(
        ruleset_id="uniqueness-regression",
        steps=tuple(
            DraftScheduleStep(PHASE_PICK, seat, (DraftActionRequirement(kind),))
            for seat, kind in turns
        ),
    )
    shared = ("shared", "other", "protected", "absolute")
    return create_draft_session(
        synthetic_deck("p1", shared_character_ids=shared),
        synthetic_deck("p2", shared_character_ids=shared),
        schedule=schedule,
        validate_decks=False,
        rules_content_hash="pinned" if abyss else "",
        immune_eligible_character_ids=shared if abyss else (),
        absolute_immune_character_ids=absolute,
    )


def _take(state, character_id: str, *, action_id: str = "", sequence: int | None = None):
    return apply_draft_action(
        state,
        DraftAction(state.current_seat, state.current_requirement.action_type,
                    character_id, action_id=action_id, sequence=sequence),
    )


class DraftSessionUniquenessTests(unittest.TestCase):
    def assert_rejected(self, state, character_id: str, code: str, **kwargs) -> None:
        before = state.state_hash()
        with self.assertRaises(DraftActionRejected) as caught:
            _take(state, character_id, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(state.state_hash(), before)

    def test_stale_action_identity_and_sequence_do_not_advance(self) -> None:
        state = _state((P1, BAN), (P2, BAN))
        state = _take(state, "shared", action_id="first", sequence=1)
        self.assert_rejected(state, "other", REJECT_DUPLICATE_ACTION_ID,
                             action_id="first", sequence=2)
        self.assert_rejected(state, "other", REJECT_DUPLICATE_SEQUENCE,
                             action_id="second", sequence=1)

    def test_ordinary_ban_and_pick_are_global_across_seats(self) -> None:
        for abyss in (False, True):
            with self.subTest(abyss=abyss):
                state = _state((P1, BAN), (P2, BAN), (P1, PICK), (P2, PICK),
                               abyss=abyss)
                state = _take(state, "shared")
                self.assert_rejected(state, "shared", REJECT_CHARACTER_ALREADY_BANNED)
                state = _take(state, "p1_char_05")
                self.assert_rejected(state, "shared", REJECT_CHARACTER_GLOBALLY_BANNED)
                state = _take(state, "other")
                self.assert_rejected(state, "other", REJECT_CHARACTER_UNAVAILABLE_TO_OPPONENT)

    def test_one_seat_cannot_pick_the_same_character_again(self) -> None:
        state = _state((P1, PICK), (P1, PICK))
        state = _take(state, "shared")
        self.assert_rejected(state, "shared", REJECT_CHARACTER_PICKED_BY_SELF)

    def test_preparation_targets_are_distinct_across_both_seats(self) -> None:
        state = _state((P1, PREBAN), (P2, PREBAN), (P1, PROTECT), (P2, PROTECT))
        state = _take(state, "shared")
        self.assert_rejected(state, "shared", REJECT_CHARACTER_RESERVED_FOR_IMMUNE)
        state = _take(state, "other")
        self.assert_rejected(state, "shared", REJECT_CHARACTER_RESERVED_FOR_IMMUNE)
        state = _take(state, "protected")
        self.assert_rejected(state, "protected", REJECT_CHARACTER_RESERVED_FOR_IMMUNE)

    def test_preparation_ban_does_not_consume_later_ordinary_ban(self) -> None:
        state = _state((P1, PREBAN), (P2, BAN))
        state = _take(state, "shared")
        state = _take(state, "shared")
        self.assertEqual(state.immune_ban_character_ids, ("shared",))
        self.assertEqual(state.banned_character_ids, ("shared",))

    def test_protected_character_can_be_claimed_once_per_seat(self) -> None:
        state = _state((P1, PROTECT), (P2, IMMUNE), (P1, IMMUNE), (P1, IMMUNE))
        state = _take(state, "protected")
        state = _take(state, "protected")
        state = _take(state, "protected")
        self.assert_rejected(state, "protected", REJECT_CHARACTER_PICKED_BY_SELF)
        self.assertEqual(state.picked_character_ids_for(P1), ("protected",))
        self.assertEqual(state.picked_character_ids_for(P2), ("protected",))

    def test_normal_pick_cannot_claim_protected_character(self) -> None:
        state = _state((P1, PROTECT), (P2, PICK), (P2, BAN))
        state = _take(state, "protected")
        self.assert_rejected(state, "protected", REJECT_CHARACTER_RESERVED_FOR_IMMUNE)
        state = _take(state, "other")
        self.assert_rejected(state, "protected", REJECT_CHARACTER_RESERVED_FOR_IMMUNE)

    def test_absolute_immunity_exception_is_explicit(self) -> None:
        # Keep the reducer's explicit absolute-immunity exception visible.
        state = _state((P1, PICK), (P2, PICK), absolute=("absolute",))
        state = _take(state, "absolute")
        state = _take(state, "absolute")
        self.assertEqual(state.picked_character_ids_for(P1), ("absolute",))
        self.assertEqual(state.picked_character_ids_for(P2), ("absolute",))
        state = _state((P1, BAN), absolute=("absolute",))
        self.assert_rejected(state, "absolute", REJECT_CHARACTER_ABSOLUTELY_IMMUNE)

    def test_free_draft_cannot_retroactively_ban_a_pick(self) -> None:
        state = _state((P1, PICK), (P2, BAN), abyss=False)
        state = _take(state, "shared")
        self.assert_rejected(state, "shared", REJECT_CHARACTER_UNAVAILABLE_TO_OPPONENT)

    def test_free_draft_rejects_immune_preparation(self) -> None:
        state = _state((P1, PREBAN), abyss=False)
        self.assert_rejected(state, "shared", REJECT_CHARACTER_NOT_IMMUNE_ELIGIBLE)


if __name__ == "__main__":
    unittest.main()
