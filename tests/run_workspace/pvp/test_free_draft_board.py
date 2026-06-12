from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from run_workspace.pvp.free_draft_board import (
    CARD_STATUS_BLOCKED_BY_OPPONENT_PICK,
    CARD_STATUS_GLOBALLY_BANNED,
    CARD_STATUS_LEGAL_TARGET,
    CARD_STATUS_PICKED_BY_SELF,
    TIMELINE_STATUS_ACTIVE,
    TIMELINE_STATUS_COMPLETE,
    TIMELINE_STATUS_PENDING,
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
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
)
from run_workspace.pvp.session import (
    REJECT_CHARACTER_ALREADY_BANNED,
    REJECT_CHARACTER_GLOBALLY_BANNED,
    REJECT_CHARACTER_PICKED_BY_SELF,
    REJECT_CHARACTER_UNAVAILABLE_TO_OPPONENT,
)

from ._fixtures import load_sample_decks, synthetic_deck


class FreeDraftBoardProjectionTests(unittest.TestCase):
    def test_initial_board_projection_is_json_serializable(self) -> None:
        board = _sample_controller().to_board_dict()

        payload = json.loads(json.dumps(board, ensure_ascii=False))
        text = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["variant"], "compact")
        self.assertEqual(payload["draft_system"]["system_id"], "free_draft_v0")
        self.assertNotIn("data/", text)
        self.assertNotIn("cookies", text.casefold())
        self.assertNotIn("artifacts", text.casefold())
        self.assertNotIn("source", payload["seats"][SEAT_PLAYER_1]["deck"])

    def test_initial_requirement_and_legal_markers_are_exposed(self) -> None:
        board = _sample_controller().to_board_dict()

        self.assertEqual(
            board["current_requirement"]["active_seat"],
            SEAT_PLAYER_1,
        )
        self.assertEqual(
            board["current_requirement"]["expected_action_type"],
            ACTION_BAN_CHARACTER,
        )
        self.assertEqual(board["current_requirement"]["step_actions_total"], 1)
        self.assertEqual(board["current_requirement"]["step_actions_done"], 0)
        self.assertEqual(board["progress"]["legal_target_count"], 24)

        opponent_card = _card(board, SEAT_PLAYER_2, "test_p2_char_01")
        active_seat_card = _card(board, SEAT_PLAYER_1, "test_p1_char_01")
        self.assertEqual(opponent_card["status"], CARD_STATUS_LEGAL_TARGET)
        self.assertTrue(opponent_card["is_current_legal_target"])
        self.assertFalse(opponent_card["is_active_seat_card"])
        self.assertEqual(active_seat_card["status"], CARD_STATUS_LEGAL_TARGET)
        self.assertTrue(active_seat_card["is_active_seat_card"])

    def test_ban_marks_character_globally_on_both_boards(self) -> None:
        controller = _shared_controller()

        controller.apply_ban_character("shared_char")
        board = controller.to_board_dict()

        for seat in PVP_SEATS:
            card = _card(board, seat, "shared_char")
            self.assertEqual(card["status"], CARD_STATUS_GLOBALLY_BANNED)
            self.assertEqual(card["banned_by"], SEAT_PLAYER_1)
            self.assertEqual(card["action_index"], 0)
            self.assertFalse(card["is_current_legal_target"])
            self.assertIn(
                REJECT_CHARACTER_GLOBALLY_BANNED,
                card["status_reason_codes"],
            )

    def test_rejected_action_leaves_board_unchanged(self) -> None:
        controller = _sample_controller()
        before = controller.to_board_dict()

        with self.assertRaises(FreeDraftControllerActionRejected):
            controller.apply_pick_character("test_p1_char_01")

        self.assertEqual(controller.to_board_dict(), before)

    def test_pick_blocks_same_character_on_opponent_board(self) -> None:
        controller = _shared_controller()
        _play_prebans_without_shared_character(controller)

        controller.apply_pick_character("shared_char")
        board = controller.to_board_dict()

        own_card = _card(board, SEAT_PLAYER_1, "shared_char")
        opponent_card = _card(board, SEAT_PLAYER_2, "shared_char")
        self.assertEqual(own_card["status"], CARD_STATUS_PICKED_BY_SELF)
        self.assertEqual(own_card["picked_by"], SEAT_PLAYER_1)
        self.assertIn(REJECT_CHARACTER_PICKED_BY_SELF, own_card["status_reason_codes"])
        self.assertEqual(
            opponent_card["status"],
            CARD_STATUS_BLOCKED_BY_OPPONENT_PICK,
        )
        self.assertEqual(opponent_card["picked_by"], SEAT_PLAYER_1)
        self.assertIn(
            REJECT_CHARACTER_UNAVAILABLE_TO_OPPONENT,
            opponent_card["status_reason_codes"],
        )

    def test_timeline_marks_complete_active_and_pending_steps(self) -> None:
        controller = _sample_controller()

        controller.apply_ban_character("test_p2_char_01")
        timeline = controller.to_board_dict()["timeline"]

        self.assertEqual(timeline[0]["status"], TIMELINE_STATUS_COMPLETE)
        self.assertEqual(timeline[0]["actions_done"], 1)
        self.assertEqual(timeline[1]["status"], TIMELINE_STATUS_ACTIVE)
        self.assertEqual(timeline[1]["actions_done"], 0)
        self.assertEqual(timeline[2]["status"], TIMELINE_STATUS_PENDING)

    def test_action_log_rows_update_after_actions(self) -> None:
        controller = _sample_controller()

        controller.apply_ban_character("test_p2_char_01")
        controller.apply_ban_character("test_p1_char_01")
        action_log = controller.to_board_dict()["action_log"]

        self.assertEqual(len(action_log), 2)
        self.assertEqual(action_log[0]["index"], 0)
        self.assertEqual(action_log[0]["phase"], "preban")
        self.assertEqual(action_log[0]["seat"], SEAT_PLAYER_1)
        self.assertEqual(action_log[0]["target_id"], "test_p2_char_01")
        self.assertEqual(action_log[0]["target_display_name"], "P2 Sword 01")
        self.assertTrue(action_log[0]["accepted"])
        self.assertEqual(action_log[1]["step_index"], 1)

    def test_debug_projection_adds_reducer_excluded_reason_codes(self) -> None:
        controller = _sample_controller()

        controller.apply_ban_character("test_p2_char_01")
        card = _card(
            controller.to_board_dict(debug=True),
            SEAT_PLAYER_2,
            "test_p2_char_01",
        )

        self.assertIn(REJECT_CHARACTER_ALREADY_BANNED, card["status_reason_codes"])

    def test_full_loop_finishes_with_no_legal_targets(self) -> None:
        controller = _sample_controller()

        controller.complete_draft_with_first_legal_targets()
        board = controller.to_board_dict()

        self.assertTrue(board["status"]["draft_finished"])
        self.assertEqual(board["progress"]["legal_target_count"], 0)
        self.assertTrue(
            all(
                not card["is_current_legal_target"]
                for seat in PVP_SEATS
                for card in board["seats"][seat]["cards"]
            )
        )
        self.assertTrue(
            all(step["status"] == TIMELINE_STATUS_COMPLETE for step in board["timeline"])
        )

    def test_post_draft_assignment_and_result_summary_is_compact(self) -> None:
        controller = _sample_controller()

        controller.complete_draft_with_first_legal_targets()
        controller.assign_deterministic_teams_and_weapons()
        controller.set_deterministic_timers()
        board = controller.to_board_dict()

        self.assertTrue(board["status"]["assignments_ready"])
        self.assertTrue(board["status"]["result_ready"])
        self.assertTrue(board["status"]["bundle_ready"])
        self.assertEqual(
            board["summary"]["assignments"][SEAT_PLAYER_1]["team_sizes"],
            [4, 4],
        )
        self.assertEqual(
            board["summary"]["assignments"][SEAT_PLAYER_1]["weapon_assignment_count"],
            8,
        )
        self.assertEqual(board["summary"]["result"]["winner_seat"], SEAT_PLAYER_1)
        self.assertEqual(
            set(board["summary"]["result"]["totals"]),
            {SEAT_PLAYER_1, SEAT_PLAYER_2},
        )

    def test_smoke_helper_and_json_include_board_projection(self) -> None:
        report = run_free_draft_controller_smoke()

        self.assertTrue(report.ready)
        self.assertIn("initial_board", report.to_dict())
        self.assertTrue(report.final_board["status"]["draft_finished"])
        self.assertEqual(len(report.final_board["action_log"]), 22)

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["final_board"]["status"]["bundle_ready"])
        self.assertIn("after_actions_board", payload)


PVP_SEATS = (SEAT_PLAYER_1, SEAT_PLAYER_2)


def _sample_controller() -> FreeDraftController:
    return FreeDraftController.from_decks(*load_sample_decks())


def _shared_controller() -> FreeDraftController:
    return FreeDraftController.from_decks(
        synthetic_deck("p1", shared_character_ids=("shared_char",)),
        synthetic_deck("p2", shared_character_ids=("shared_char",)),
    )


def _play_prebans_without_shared_character(controller: FreeDraftController) -> None:
    for target_id in ("p2_char_12", "p1_char_12", "p2_char_11", "p1_char_11"):
        controller.apply_ban_character(target_id)


def _card(board: dict[str, object], seat: str, character_id: str) -> dict[str, object]:
    cards = board["seats"][seat]["cards"]  # type: ignore[index]
    for card in cards:
        if card["character_id"] == character_id:
            return card
    raise AssertionError(f"{seat} card not found: {character_id}")


if __name__ == "__main__":
    unittest.main()
