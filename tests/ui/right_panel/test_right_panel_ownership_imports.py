from __future__ import annotations

from pathlib import Path
import unittest


class RightPanelOwnershipImportsTest(unittest.TestCase):
    def test_new_production_imports_work(self) -> None:
        from ui.right_panel.common.slot_card import RightPanelSlotCardWidget
        from ui.right_panel.common.team_card import RightPanelTeamCardWidget
        from ui.right_panel.dock import RightOperationsDock
        from ui.right_panel.header import RightDockHeader
        from ui.right_panel.history.viewer import HistoryRightPanelPlaceholder
        from ui.right_panel.live_run.panel import RunRightPanelWidget
        from ui.right_panel.pvp.host import PvpRightPanelHost
        from ui.right_panel.settings.account_data import AccountDataPage

        self.assertEqual(RightPanelSlotCardWidget.__name__, "RightPanelSlotCardWidget")
        self.assertEqual(RightPanelTeamCardWidget.__name__, "RightPanelTeamCardWidget")
        self.assertEqual(RunRightPanelWidget.__name__, "RunRightPanelWidget")
        self.assertEqual(RightOperationsDock.__name__, "RightOperationsDock")
        self.assertEqual(RightDockHeader.__name__, "RightDockHeader")
        self.assertEqual(HistoryRightPanelPlaceholder.__name__, "HistoryRightPanelPlaceholder")
        self.assertEqual(PvpRightPanelHost.__name__, "PvpRightPanelHost")
        self.assertEqual(AccountDataPage.__name__, "AccountDataPage")

    def test_old_right_panel_prototype_imports_remain_compatible(self) -> None:
        from ui.right_panel_prototype import (
            RightPanelPrototypeWidget,
            RightPanelSlotPrototypeWidget,
            RightPanelTeamPrototypeWidget,
        )

        self.assertEqual(RightPanelPrototypeWidget.__name__, "RunRightPanelWidget")
        self.assertEqual(RightPanelSlotPrototypeWidget.__name__, "RightPanelSlotCardWidget")
        self.assertEqual(RightPanelTeamPrototypeWidget.__name__, "RightPanelTeamCardWidget")

    def test_old_modules_no_longer_own_moved_right_panel_class_bodies(self) -> None:
        root = Path(__file__).resolve().parents[3]
        prototype_source = (root / "ui/right_panel_prototype.py").read_text(encoding="utf-8")
        app_shell_source = (root / "ui/app_shell.py").read_text(encoding="utf-8")
        pvp_window_source = (root / "ui/pvp_browser/window.py").read_text(encoding="utf-8")

        self.assertNotIn("class RightPanelPrototypeWidget", prototype_source)
        self.assertNotIn("class RightPanelSlotPrototypeWidget", prototype_source)
        self.assertNotIn("class RightPanelTeamPrototypeWidget", prototype_source)
        self.assertNotIn("class RightDockHeader", app_shell_source)
        self.assertNotIn("class RightOperationsDock", app_shell_source)
        self.assertNotIn("class PvpRightPanelHost", pvp_window_source)
        self.assertNotIn("class PvpDecksRightPanel", pvp_window_source)
        self.assertNotIn("class PvpPlayRightPanel", pvp_window_source)
        self.assertNotIn("class PvpDraftRightPanel", pvp_window_source)
        self.assertNotIn("class PvpPostDraftTargetSlotWidget", pvp_window_source)


if __name__ == "__main__":
    unittest.main()
