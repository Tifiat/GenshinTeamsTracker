from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()
from PySide6.QtWidgets import QApplication, QPushButton

from tests.ui.pvp_browser import test_pvp_browser as pvp_fixtures
from ui.pvp_browser.window import PvpWorkspace
from ui.right_panel.common.slot_card import RightPanelSlotCardWidget
from ui.right_panel.pvp.draft.panel import (
    PVP_POSTDRAFT_EXPANDED_MIN_HEIGHT,
    PVP_POSTDRAFT_RUN_PANEL_MIN_HEIGHT,
    PvpDraftRightPanel,
)
from ui.right_panel.pvp.play.panel import PvpPlayRightPanel


class PvpPostDraftRightPanelLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _build_assignment_panel(self) -> tuple[PvpWorkspace, PvpDraftRightPanel]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        portrait_path, weapon_path = pvp_fixtures._create_test_asset_images(temp_dir.name)
        characters = pvp_fixtures._valid_character_assets(24, image_path=portrait_path)
        weapons = [
            pvp_fixtures._weapon_asset(
                "11401",
                "Sword",
                weapon_type=1,
                weapon_type_name="Sword",
                known_count=24,
                image_path=weapon_path,
            )
        ]
        db_path = Path(temp_dir.name) / "right-panel-postdraft.sqlite"
        pvp_fixtures._seed_pvp_build_db(db_path, characters=characters, weapons=weapons)

        workspace = PvpWorkspace(db_path=db_path, deck_dir=temp_dir.name)
        self.assertTrue(workspace.decks_workspace.create_deck("Mirror"))
        self.assertTrue(workspace.decks_workspace.save_edit(name="Mirror"))
        play_panel = PvpPlayRightPanel(workspace)
        play_panel.start_button.click()
        QApplication.processEvents()
        pvp_fixtures.PvpBrowserTest()._complete_draft(workspace)
        self.assertTrue(workspace.continue_to_assignment())

        draft_panel = PvpDraftRightPanel(workspace)
        draft_panel.resize(420, 680)
        draft_panel.show()
        QApplication.processEvents()
        self.addCleanup(draft_panel.close)
        return workspace, draft_panel

    def test_expanded_and_collapsed_postdraft_seat_geometry(self) -> None:
        workspace, draft_panel = self._build_assignment_panel()

        p1_zone = draft_panel.target_zone_frames_by_seat["player_1"]
        p2_zone = draft_panel.target_zone_frames_by_seat["player_2"]
        p1_panel = draft_panel.postdraft_run_panels_by_seat["player_1"]
        p1_ready = draft_panel.postdraft_ready_buttons_by_seat["player_1"]
        p1_toggle = draft_panel.postdraft_toggle_buttons_by_seat["player_1"]
        p2_toggle = draft_panel.postdraft_toggle_buttons_by_seat["player_2"]

        self.assertFalse(p1_zone.isHidden())
        self.assertEqual(len(p1_zone.findChildren(RightPanelSlotCardWidget)), 8)
        self.assertGreaterEqual(p1_panel.minimumHeight(), PVP_POSTDRAFT_RUN_PANEL_MIN_HEIGHT)
        self.assertGreaterEqual(p1_zone.minimumHeight(), PVP_POSTDRAFT_EXPANDED_MIN_HEIGHT)
        self.assertIs(p1_ready.parentWidget(), p1_zone)
        self.assertFalse(p1_zone.findChildren(QPushButton, "pvp_postdraft_player_toggle"))
        self.assertEqual(p1_toggle.parentWidget().objectName(), "pvp_postdraft_target_toggle_row")

        self.assertTrue(p2_zone.isHidden())
        self.assertEqual(p2_zone.maximumHeight(), 0)
        self.assertEqual(p2_toggle.parentWidget().objectName(), "pvp_postdraft_target_toggle_row")

        workspace.toggle_build_seat_collapsed("player_2")
        QApplication.processEvents()
        self.assertFalse(p2_zone.isHidden())
        self.assertEqual(len(p2_zone.findChildren(RightPanelSlotCardWidget)), 8)
        self.assertGreaterEqual(p2_zone.minimumHeight(), PVP_POSTDRAFT_EXPANDED_MIN_HEIGHT)

        workspace.toggle_build_seat_collapsed("player_2")
        QApplication.processEvents()
        self.assertTrue(p2_zone.isHidden())
        self.assertEqual(p2_zone.maximumHeight(), 0)


if __name__ == "__main__":
    unittest.main()
