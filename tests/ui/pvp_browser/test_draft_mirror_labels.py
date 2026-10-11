from __future__ import annotations

import unittest

from localization import tr
from run_workspace.pvp.schedule import ACTION_MIRROR_CHARACTER
from ui.pvp_browser.draft_order import _current_action_visual, _position_visual
from ui.right_panel.pvp._shared import _draft_action_from_unified_pool, _draft_action_label
from ui.utils.pvp_colors import pvp_player_color


class DraftMirrorLabelsTest(unittest.TestCase):
    def test_mirror_is_actor_colored_and_named_as_one_action(self) -> None:
        row = {"seat": "player_2", "action_type": ACTION_MIRROR_CHARACTER,
               "status": "active", "character_id": ""}
        slot = _position_visual(row)
        turn = _current_action_visual((row,))
        self.assertEqual(slot["overlay_color"], pvp_player_color("player_2"))
        self.assertTrue(slot["draw_action_label"])
        self.assertEqual(slot["label_key"], "app_shell.pvp.draft.slot_mirror")
        self.assertEqual(turn["action_color"], pvp_player_color("player_2"))
        self.assertEqual(turn["detail"], tr("app_shell.pvp.draft.mirror").upper())
        self.assertEqual(_draft_action_label(ACTION_MIRROR_CHARACTER),
                         tr("app_shell.pvp.draft.mirror"))

    def test_only_current_legal_mirror_payload_is_accepted(self) -> None:
        action = {"type": ACTION_MIRROR_CHARACTER, "target_type": "character",
                  "character_id": "character_1"}
        entry = {"character_id": "character_1", "is_current_legal_target": True,
                 "action": action}
        board = {"unified_pool": {"entries": [entry]}}
        self.assertEqual(_draft_action_from_unified_pool(board, action),
                         (ACTION_MIRROR_CHARACTER, "character_1"))
        self.assertIsNone(_draft_action_from_unified_pool(
            board, {**action, "character_id": "character_2"}))
        entry["is_current_legal_target"] = False
        self.assertIsNone(_draft_action_from_unified_pool(board, action))


if __name__ == "__main__":
    unittest.main()
