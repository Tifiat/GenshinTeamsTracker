from __future__ import annotations

import unittest
from dataclasses import replace

from run_workspace.pvp.abyss_match_rules import (
    abyss_immune_context,
    build_abyss_match_definition,
)
from run_workspace.pvp.draft_completion import draft_completion
from run_workspace.pvp.draft_options import DraftMatchOptions
from run_workspace.pvp.free_draft_controller import FreeDraftController, FreeDraftControllerActionRejected
from run_workspace.pvp.schedule import (
    ACTION_BAN_CHARACTER,
    ACTION_IMMUNE_CHARACTER,
    ACTION_IMMUNE_PICK_CHARACTER,
    ACTION_MIRROR_CHARACTER,
    ACTION_PICK_CHARACTER,
    ACTION_PREBAN_CHARACTER,
    DraftActionRequirement,
    DraftSchedule,
    DraftScheduleStep,
    PHASE_PICK,
    PHASE_PREBAN,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
)
from run_workspace.pvp.session import (
    DraftAction,
    DraftActionRejected,
    apply_draft_action,
    create_draft_session,
    replay_draft_actions,
)
from tests.run_workspace.pvp.test_abyss_match_rules import _deck, _rules


def _schedule(*steps: tuple[str, str]) -> DraftSchedule:
    return DraftSchedule("synthetic", tuple(
        DraftScheduleStep(PHASE_PICK, seat, (DraftActionRequirement(kind),))
        for seat, kind in steps
    ))


def _cup_state(shared_count: int = 16):
    rules = _rules()
    full = _deck(rules)
    cheap = replace(full, characters=full.characters[:shared_count])
    eligible, absolute = abyss_immune_context(cheap, full, rules)
    state = create_draft_session(
        cheap, full, schedule=build_abyss_match_definition(rules).build_schedule(),
        validate_decks=False, rules_content_hash=rules.content_hash,
        immune_eligible_character_ids=eligible,
        absolute_immune_character_ids=absolute,
    )
    return state


class DraftCompletionTests(unittest.TestCase):
    def test_controller_filters_starving_choices_and_first_legal_path_finishes(self):
        rules = _rules()
        full = _deck(rules)
        cheap = replace(full, characters=full.characters[:16])
        controller = FreeDraftController.from_abyss_decks(cheap, full, rules,
            match_options=DraftMatchOptions(preban_cost_step=0, pick_time_ms=0, reserve_time_ms=0))
        self.assertTrue(controller.state.setup_ready)
        excluded = []
        while not controller.session_state.is_complete:
            blocked = [item for item in controller.get_legal_targets(include_excluded=True)
                       if item.reason == 'draft_completion_impossible']
            if blocked:
                excluded.append(blocked[0].character_id)
                with self.assertRaises(FreeDraftControllerActionRejected) as error:
                    controller.apply_current_action(blocked[0].character_id)
                self.assertEqual(error.exception.code, 'draft_completion_impossible')
            legal = controller.get_legal_targets()
            self.assertTrue(legal)
            controller.apply_current_action(legal[0].character_id)
        self.assertTrue(excluded)
        self.assertEqual(len(controller.session_state.player_1_picked_character_ids), 8)
        self.assertEqual(len(controller.session_state.player_2_picked_character_ids), 8)

    def test_cup_overlap_has_non_greedy_completion_but_greedy_can_stall(self) -> None:
        initial = _cup_state()
        report = draft_completion(initial)
        self.assertEqual(report.status, "complete")
        self.assertEqual(len(report.witness), 26)
        replayed = replay_draft_actions(initial, report.witness)
        self.assertTrue(replayed.is_complete)
        self.assertEqual(len(replayed.picked_character_ids_for(SEAT_PLAYER_1)), 8)
        self.assertEqual(len(replayed.picked_character_ids_for(SEAT_PLAYER_2)), 8)

        state = initial
        found_impossible = False
        while not state.is_complete:
            candidates = sorted(state.player_1_deck.character_ids | state.player_2_deck.character_ids)
            for character_id in candidates:
                action = DraftAction(state.current_seat, state.current_requirement.action_type,
                                     character_id)
                try:
                    next_state = apply_draft_action(state, action)
                except DraftActionRejected:
                    continue
                break
            else:
                self.assertTrue(found_impossible)
                break
            state = next_state
            if draft_completion(state).status == "impossible":
                found_impossible = True
                break
        self.assertTrue(found_impossible)

    def test_protected_and_absolute_sharing_is_seat_specific(self) -> None:
        rules = _rules()
        deck = replace(_deck(rules), characters=_deck(rules).characters[:2])
        state = create_draft_session(
            deck, deck, validate_decks=False, rules_content_hash=rules.content_hash,
            schedule=_schedule(
                (SEAT_PLAYER_1, ACTION_IMMUNE_CHARACTER),
                (SEAT_PLAYER_2, ACTION_IMMUNE_CHARACTER),
                (SEAT_PLAYER_1, ACTION_PICK_CHARACTER),
                (SEAT_PLAYER_2, ACTION_PICK_CHARACTER),
            ),
            absolute_immune_character_ids=("1001",),
        )
        state = replace(state, player_1_immune_pick_character_ids=("1000",))
        report = draft_completion(state)
        self.assertEqual(report.status, "complete")
        replayed = replay_draft_actions(state, report.witness)
        self.assertEqual(replayed.picked_character_ids_for(SEAT_PLAYER_1), ("1000", "1001"))
        self.assertEqual(replayed.picked_character_ids_for(SEAT_PLAYER_2), ("1000", "1001"))

    def test_impossible_admission_and_optional_ban_skip(self) -> None:
        rules = _rules()
        full = _deck(rules)
        left = replace(full, characters=())
        right = replace(full, characters=full.characters[:1])
        state = create_draft_session(
            left, right, validate_decks=False, rules_content_hash=rules.content_hash,
            schedule=_schedule((SEAT_PLAYER_1, ACTION_BAN_CHARACTER),
                               (SEAT_PLAYER_2, ACTION_PICK_CHARACTER)),
        )
        self.assertEqual(draft_completion(state).status, "impossible")
        optional = draft_completion(state, require_ban_targets=False)
        self.assertEqual(optional.status, "complete")
        self.assertTrue(optional.witness[0].skip)
        self.assertTrue(replay_draft_actions(state, optional.witness).is_complete)

    def test_pending_preparation_budget_and_future_mirror(self) -> None:
        state = _cup_state()
        self.assertEqual(draft_completion(state, max_states=1).status, "unknown")
        rules = _rules()
        deck = _deck(rules)
        mirror = create_draft_session(
            deck, deck, validate_decks=False, rules_content_hash=rules.content_hash,
            schedule=_schedule((SEAT_PLAYER_1, ACTION_MIRROR_CHARACTER)),
        )
        self.assertEqual(draft_completion(mirror).status, "unknown")

    def test_optional_preban_skip_preserves_preparation_candidate(self) -> None:
        rules = _rules()
        deck = replace(_deck(rules), characters=_deck(rules).characters[:1])
        schedule = DraftSchedule("synthetic", (
            DraftScheduleStep(PHASE_PREBAN, SEAT_PLAYER_1,
                              (DraftActionRequirement(ACTION_PREBAN_CHARACTER),)),
            DraftScheduleStep(PHASE_PREBAN, SEAT_PLAYER_1,
                              (DraftActionRequirement(ACTION_IMMUNE_PICK_CHARACTER),)),
            DraftScheduleStep(PHASE_PICK, SEAT_PLAYER_2,
                              (DraftActionRequirement(ACTION_IMMUNE_CHARACTER),)),
        ))
        state = create_draft_session(
            deck, deck, schedule=schedule, validate_decks=False,
            rules_content_hash=rules.content_hash,
            immune_eligible_character_ids=("1000",),
        )
        self.assertEqual(draft_completion(state).status, "impossible")
        optional = draft_completion(state, require_ban_targets=False)
        self.assertEqual(optional.status, "complete")
        self.assertTrue(optional.witness[0].skip)
        self.assertTrue(replay_draft_actions(state, optional.witness).is_complete)


if __name__ == "__main__":
    unittest.main()
