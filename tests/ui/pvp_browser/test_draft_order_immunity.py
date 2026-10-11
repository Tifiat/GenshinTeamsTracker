from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from localization import tr
from run_workspace.pvp.schedule import (
    ACTION_BAN_CHARACTER,
    ACTION_IMMUNE_BAN_CHARACTER,
    ACTION_IMMUNE_CHARACTER,
    ACTION_IMMUNE_PICK_CHARACTER,
    ACTION_PICK_CHARACTER,
)
from ui.pvp_browser.draft_order import PvpDraftOrderStrip
from ui.right_panel.pvp._shared import PVP_DRAFT_BAN_ACCENT, PVP_DRAFT_IMMUNE_ACCENT


_ACTIONS = [
    ("player_1", ACTION_IMMUNE_BAN_CHARACTER),
    ("player_2", ACTION_IMMUNE_BAN_CHARACTER),
    ("player_1", ACTION_IMMUNE_PICK_CHARACTER),
    ("player_2", ACTION_IMMUNE_PICK_CHARACTER),
    *(("player_1" if i % 2 == 0 else "player_2",
       ACTION_IMMUNE_CHARACTER if i in (9, 10) else
       ACTION_BAN_CHARACTER if i % 5 == 0 else ACTION_PICK_CHARACTER)
      for i in range(22)),
]


def _board(accepted: int) -> dict:
    targets = ["ban_then_ban", "ban_other", "shared_one", "shared_two"] + [
        "shared_one" if i in (9, 10) else "ban_then_ban" if i == 0 else f"character_{i}"
        for i in range(22)
    ]
    return {
        "timeline": [
            {"seat": seat, "required_actions": [action_type]}
            for seat, action_type in _ACTIONS
        ],
        "action_log": [
            {"seat": seat, "action_type": action_type, "target_id": targets[i]}
            for i, (seat, action_type) in enumerate(_ACTIONS[:accepted])
        ],
        "current_requirement": {"expected_action_type": _ACTIONS[accepted][1]}
        if accepted < len(_ACTIONS) else None,
    }


class DraftOrderImmunityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_preparation_and_claims_have_distinct_visuals_and_indices(self) -> None:
        strip = PvpDraftOrderStrip()
        strip.set_board(_board(4), portrait_paths={})
        self.assertEqual(strip.position_count(), 26)
        self.assertEqual(strip.active_position(), 5)
        self.assertEqual(strip._protected_ids, ("shared_one", "shared_two"))
        self.assertEqual(strip.position_visual(1)["overlay_color"], PVP_DRAFT_IMMUNE_ACCENT)
        self.assertEqual(strip.position_visual(3)["overlay_color"], PVP_DRAFT_IMMUNE_ACCENT)
        self.assertEqual(strip.position_visual(5)["overlay_color"], PVP_DRAFT_BAN_ACCENT)
        self.assertEqual(strip.position_visual(1)["label_key"], "app_shell.pvp.draft.slot_immune_ban")
        self.assertEqual(strip.position_visual(3)["label_key"], "app_shell.pvp.draft.slot_immune_pick")
        self.assertEqual(strip.current_action_visual()["detail"], tr("app_shell.pvp.draft.turn_ban").upper())
        strip.set_board(_board(5), portrait_paths={})
        self.assertEqual(strip._positions[0]["character_id"],
                         strip._positions[4]["character_id"])
        strip.set_board(_board(1), portrait_paths={})
        self.assertEqual(strip.active_position(), 2)
        self.assertEqual(strip.current_action_visual()["detail"], tr("app_shell.pvp.draft.immune_ban").upper())
        strip.set_board(_board(2), portrait_paths={})
        self.assertEqual(strip.current_action_visual()["detail"], tr("app_shell.pvp.draft.immune_pick").upper())
        strip.set_board(_board(13), portrait_paths={})
        self.assertEqual(strip.position_visual(14)["label_key"], "app_shell.pvp.draft.slot_immune")
        self.assertEqual(strip.current_action_visual()["detail"], tr("app_shell.pvp.draft.immune").upper())
        strip.set_board(_board(26), portrait_paths={})
        self.assertEqual(strip.active_position(), 0)
        self.assertEqual(strip._protected_ids, ("shared_one", "shared_two"))
        self.assertEqual(strip.position_visual(15)["label_key"], "app_shell.pvp.draft.slot_immune")

    def test_protected_portraits_are_central_and_narrow_layout_is_contained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = QImage(32, 32, QImage.Format.Format_ARGB32)
            image.fill(QColor("#f0c040"))
            portrait = Path(directory) / "portrait.png"
            self.assertTrue(image.save(str(portrait)))
            strip = PvpDraftOrderStrip()
            strip.set_board(_board(4), portrait_paths={
                "shared_one": str(portrait), "shared_two": str(portrait),
            })
            for width in (200, 270, 370, 520, 620, 860):
                layout = strip.layout_visual(width)
                self.assertFalse(layout["has_overlap"], width)
                self.assertEqual(len(layout["protection_slot_rects"]), 2)
                canvas = QRect(0, 0, width, layout["height"])
                for rect in (*layout["position_rects"], layout["turn_rect"],
                             layout["protection_rect"], *layout["protection_slot_rects"]):
                    self.assertTrue(canvas.contains(rect), (width, rect, canvas))
                strip.resize(width, layout["height"])
                rendered = strip.grab().toImage()
                self.assertFalse(rendered.isNull())
                self.assertGreaterEqual(rendered.height(), layout["height"])
                self.assertNotEqual(rendered.pixelColor(layout["protection_slot_rects"][0].center()),
                                    QColor("#000000"))
            self.assertIn(("protected", "shared_one"), strip._prepared)
            self.assertIn(("protected", "shared_two"), strip._prepared)
            self.assertNotIn(2, strip._prepared)
            self.assertNotIn(3, strip._prepared)


if __name__ == "__main__":
    unittest.main()
