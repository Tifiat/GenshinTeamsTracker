from __future__ import annotations

import unittest
from run_workspace.pvp.draft_options import DraftMatchOptions
from run_workspace.pvp.free_draft_controller import FreeDraftController
from run_workspace.pvp.session_bundle import verify_session_bundle
from tests.run_workspace.pvp._fixtures import load_sample_decks

from run_workspace.pvp.schedule import (
    ACTION_MIRROR_CHARACTER,
    DraftActionRequirement,
    DraftSchedule,
    DraftScheduleStep,
    PHASE_PICK,
    PVP_SEATS,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
    build_default_free_draft_v0_schedule,
    with_first_seat,
)


class FirstSeatScheduleTests(unittest.TestCase):
    def test_player_one_identity_and_player_two_swaps_every_actor(self) -> None:
        base = build_default_free_draft_v0_schedule()
        self.assertIs(with_first_seat(base, SEAT_PLAYER_1), base)
        switched = with_first_seat(base, SEAT_PLAYER_2)
        self.assertEqual(base.steps[0].seat, SEAT_PLAYER_1)
        self.assertEqual(switched.steps[0].seat, SEAT_PLAYER_2)
        self.assertEqual(switched.ruleset_id, base.ruleset_id)
        self.assertEqual(len(switched.steps), len(base.steps))
        for before, after in zip(base.steps, switched.steps):
            self.assertEqual(after.seat, SEAT_PLAYER_2 if before.seat == SEAT_PLAYER_1
                             else SEAT_PLAYER_1)
            self.assertEqual(after.phase, before.phase)
            self.assertIs(after.actions, before.actions)
        self.assertEqual(with_first_seat(switched, SEAT_PLAYER_2), base)

    def test_source_mirror_action_is_preserved_as_one_actor_action(self) -> None:
        base = DraftSchedule("abyss:sample", (
            DraftScheduleStep(PHASE_PICK, SEAT_PLAYER_1,
                              (DraftActionRequirement(ACTION_MIRROR_CHARACTER),)),
            DraftScheduleStep(PHASE_PICK, SEAT_PLAYER_2,
                              (DraftActionRequirement(ACTION_MIRROR_CHARACTER),)),
        ))
        switched = with_first_seat(base, SEAT_PLAYER_2)
        self.assertEqual(tuple(step.seat for step in switched.steps), PVP_SEATS[::-1])
        self.assertEqual(tuple(step.actions for step in switched.steps),
                         tuple(step.actions for step in base.steps))
        self.assertEqual(base.steps[0].seat, SEAT_PLAYER_1)

    def test_rejects_unknown_first_seat(self) -> None:
        base = build_default_free_draft_v0_schedule()
        for bad in ("", "player_3", None, True):
            with self.subTest(first=bad), self.assertRaises(ValueError):
                with_first_seat(base, bad)

    def test_swapped_free_draft_exports_and_replays_without_swapping_decks(self):
        first,second = load_sample_decks()
        controller = FreeDraftController.from_decks(first,second,
            match_options=DraftMatchOptions(first_seat=SEAT_PLAYER_2))
        self.assertEqual(controller.session_state.current_seat,SEAT_PLAYER_2)
        controller.complete_draft_with_first_legal_targets()
        controller.assign_deterministic_teams_and_weapons()
        controller.set_deterministic_timers()
        bundle = controller.build_session_bundle()
        self.assertEqual(bundle.source['first_seat'],SEAT_PLAYER_2)
        self.assertTrue(verify_session_bundle(bundle).ready)
        restored = FreeDraftController.from_session_bundle(bundle)
        self.assertEqual(restored.session_state.state_hash(),controller.session_state.state_hash())
        self.assertEqual(restored.state.player_1_deck,first)
        tampered = bundle.to_dict()
        tampered['source']['first_seat']=SEAT_PLAYER_1
        self.assertFalse(verify_session_bundle(tampered).ready)


if __name__ == "__main__":
    unittest.main()
