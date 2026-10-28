from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from run_workspace.pvp.account_deck_export import (
    AccountDeckCharacterRow,
    AccountDeckExportOptions,
    AccountDeckWeaponStackRow,
    FakeAccountDeckDataProvider,
)
from run_workspace.pvp.free_draft_controller import (
    FreeDraftController,
    FreeDraftControllerActionRejected,
)
from run_workspace.pvp.free_draft_controller_smoke import (
    main,
    run_free_draft_controller_smoke,
)
from run_workspace.pvp.schedule import (
    ACTION_BAN_CHARACTER,
    ACTION_PICK_CHARACTER,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
)
from run_workspace.pvp.session import create_draft_session, replay_draft_actions
from run_workspace.pvp.session_bundle import verify_session_bundle

from ._fixtures import default_draft_actions, load_sample_decks


class FreeDraftControllerTests(unittest.TestCase):
    def test_controller_creates_from_synthetic_decks(self) -> None:
        controller = _sample_controller()
        projection = controller.to_projection().to_dict()

        self.assertTrue(projection["status"]["setup_ready"])
        self.assertEqual(projection["draft_system"]["system_id"], "free_draft_v0")
        self.assertEqual(
            projection["current_requirement"],
            {
                "phase": "preban",
                "step_index": 0,
                "action_index": 0,
                "active_seat": SEAT_PLAYER_1,
                "expected_action_type": ACTION_BAN_CHARACTER,
            },
        )

    def test_controller_creates_from_mappings(self) -> None:
        player_1, player_2 = load_sample_decks()

        controller = FreeDraftController.from_deck_mappings(
            player_1.to_dict(),
            player_2.to_dict(),
        )

        self.assertTrue(controller.state.setup_ready)
        self.assertEqual(controller.to_projection().draft_system["version"], "1")

    def test_projection_is_json_serializable_without_private_paths(self) -> None:
        projection = _sample_controller().to_projection().to_dict()

        payload = json.loads(json.dumps(projection, ensure_ascii=False))

        self.assertIn("legal_targets", payload)
        text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("data/artifacts.db", text)
        self.assertNotIn("cookies", text.casefold())
        self.assertNotIn("artifacts", payload["seats"][SEAT_PLAYER_1])

    def test_legal_targets_exist_for_first_ban(self) -> None:
        controller = _sample_controller()

        targets = controller.get_legal_targets()

        self.assertGreaterEqual(len(targets), 12)
        self.assertEqual(targets[0].status, "legal")
        self.assertEqual(targets[0].character_id, "test_p2_char_01")

    def test_apply_valid_ban_advances_requirement(self) -> None:
        controller = _sample_controller()

        action = controller.apply_ban_character("test_p2_char_12")
        projection = controller.to_projection().to_dict()

        self.assertEqual(action.sequence, 1)
        self.assertEqual(projection["progress"]["actions_accepted"], 1)
        self.assertEqual(
            projection["current_requirement"]["active_seat"],
            SEAT_PLAYER_2,
        )
        self.assertIn("test_p2_char_12", projection["draft_state"]["banned_character_ids"])

    def test_apply_valid_pick_updates_pool(self) -> None:
        controller = _sample_controller()
        for action in default_draft_actions()[:4]:
            controller.apply_manual_action(
                seat=action.seat,
                action_type=action.action_type,
                character_id=action.character_id,
            )

        controller.apply_pick_character("test_p1_char_01")
        projection = controller.to_projection().to_dict()

        self.assertIn(
            "test_p1_char_01",
            projection["draft_state"]["picked_character_ids_by_seat"][SEAT_PLAYER_1],
        )
        self.assertEqual(projection["progress"]["actions_accepted"], 5)

    def test_wrong_action_type_is_structured_rejection(self) -> None:
        controller = _sample_controller()

        with self.assertRaises(FreeDraftControllerActionRejected) as context:
            controller.apply_pick_character("test_p1_char_01")

        self.assertEqual(context.exception.code, "wrong_action_type")

    def test_unavailable_target_is_structured_rejection(self) -> None:
        controller = _sample_controller()
        target_id = controller.get_legal_targets()[0].character_id
        controller.apply_ban_character(target_id)

        with self.assertRaises(FreeDraftControllerActionRejected) as context:
            controller.apply_ban_character(target_id)

        self.assertEqual(context.exception.code, "character_already_banned")

    def test_full_manual_loop_completes_and_replays(self) -> None:
        controller = _sample_controller()

        actions = controller.complete_draft_with_first_legal_targets()
        initial = create_draft_session(*load_sample_decks())
        replayed = replay_draft_actions(initial, controller.accepted_actions)

        self.assertEqual(len(actions), 22)
        self.assertTrue(controller.session_state.is_complete)
        self.assertEqual(len(controller.session_state.player_1_banned_character_ids), 3)
        self.assertEqual(len(controller.session_state.player_2_banned_character_ids), 3)
        self.assertEqual(len(controller.session_state.player_1_picked_character_ids), 8)
        self.assertEqual(len(controller.session_state.player_2_picked_character_ids), 8)
        self.assertEqual(replayed.state_hash(), controller.session_state.state_hash())

    def test_complete_state_rejects_extra_action(self) -> None:
        controller = _sample_controller()
        controller.complete_draft_with_first_legal_targets()

        with self.assertRaises(FreeDraftControllerActionRejected) as context:
            controller.apply_current_action("test_p1_char_09")

        self.assertEqual(context.exception.code, "draft_complete")

    def test_post_draft_helpers_build_verified_bundle(self) -> None:
        controller = _completed_controller()

        controller.assign_deterministic_teams_and_weapons()
        controller.set_deterministic_timers()
        bundle = controller.build_session_bundle()
        verification = verify_session_bundle(bundle)
        projection = controller.to_projection().to_dict()

        self.assertTrue(verification.ready)
        self.assertTrue(projection["status"]["assignments_ready"])
        self.assertTrue(projection["status"]["result_ready"])
        self.assertEqual(projection["result"]["winner_seat"], SEAT_PLAYER_1)

    def test_controller_restores_from_session_bundle(self) -> None:
        source = _completed_controller()
        source.assign_deterministic_teams_and_weapons()
        source.set_deterministic_timers()
        bundle = source.build_session_bundle()

        restored = FreeDraftController.from_session_bundle(bundle)

        self.assertEqual(
            restored.session_state.state_hash(),
            source.session_state.state_hash(),
        )
        self.assertTrue(restored.to_projection().status["assignments_ready"])

    def test_fake_account_controller_path_uses_provider_only(self) -> None:
        controller = FreeDraftController.from_account_export(
            provider=_fake_account_provider(character_count=30),
            options=AccountDeckExportOptions(
                deck_name="Fake Account Controller Deck",
                nickname="fake",
                language="en",
                exported_at_utc="2026-06-12T00:00:00Z",
            ),
        )

        self.assertTrue(controller.state.setup_ready)
        self.assertEqual(controller.state.source_mode, "account")
        self.assertEqual(len(controller.state.player_1_deck.characters), 30)
        self.assertEqual(len(controller.state.player_2_deck.characters), 30)

    def test_smoke_helper_is_structured(self) -> None:
        report = run_free_draft_controller_smoke()

        self.assertTrue(report.ready)
        self.assertEqual(report.source_mode, "synthetic")
        self.assertTrue(report.bundle_verification["ready"])
        self.assertEqual(report.final_projection["progress"]["actions_accepted"], 22)

    def test_smoke_json_main_output_parses(self) -> None:
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = main(["--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["final_projection"]["draft_system"]["system_id"], "free_draft_v0")

    def test_smoke_step_demo_records_transitions(self) -> None:
        report = run_free_draft_controller_smoke(include_step_demo=True)

        self.assertTrue(report.ready)
        self.assertEqual(len(report.step_demo), 4)
        self.assertEqual(report.step_demo[0]["before"]["active_seat"], SEAT_PLAYER_1)


def _sample_controller() -> FreeDraftController:
    return FreeDraftController.from_decks(*load_sample_decks())


def _completed_controller() -> FreeDraftController:
    controller = _sample_controller()
    controller.complete_draft_with_first_legal_targets()
    return controller


def _fake_account_provider(*, character_count: int) -> FakeAccountDeckDataProvider:
    weapon_types = (1, 12, 13, 11, 10)
    elements = ("Pyro", "Hydro", "Electro", "Cryo", "Geo")
    return FakeAccountDeckDataProvider(
        characters=tuple(
            AccountDeckCharacterRow(
                character_id=f"fake_char_{index:02d}",
                display_name=f"Fake Character {index:02d}",
                element=elements[(index - 1) % len(elements)],
                weapon_type=weapon_types[(index - 1) % len(weapon_types)],
                rarity=5 if index % 2 else 4,
                level=90,
                constellation=index % 7,
            )
            for index in range(1, character_count + 1)
        ),
        weapon_stacks=(
            AccountDeckWeaponStackRow("fake_sword", "Fake Sword", 1, rarity=4, level=90, refinement=5, count=16),
            AccountDeckWeaponStackRow("fake_bow", "Fake Bow", 12, rarity=4, level=90, refinement=5, count=16),
            AccountDeckWeaponStackRow("fake_polearm", "Fake Polearm", 13, rarity=4, level=90, refinement=5, count=16),
            AccountDeckWeaponStackRow("fake_claymore", "Fake Claymore", 11, rarity=4, level=90, refinement=5, count=16),
            AccountDeckWeaponStackRow("fake_catalyst", "Fake Catalyst", 10, rarity=4, level=90, refinement=5, count=16),
        ),
        source_summary={"provider": "fake_account_controller_test"},
    )


if __name__ == "__main__":
    unittest.main()
