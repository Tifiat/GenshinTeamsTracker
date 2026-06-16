from __future__ import annotations

import ast
from pathlib import Path
import unittest


class RightPanelOwnershipImportsTest(unittest.TestCase):
    def test_new_production_imports_work(self) -> None:
        from ui.right_panel.common.slot_parts import (
            RightPanelArtifactMiniZoneWidget,
            RightPanelPortraitMiniBox,
            RightPanelWeaponMiniBox,
        )
        from ui.right_panel.common.slot_card import RightPanelSlotCardWidget
        from ui.right_panel.common.team_card import RightPanelTeamCardWidget
        from ui.right_panel.dock import RightOperationsDock
        from ui.right_panel.header import RightDockHeader
        from ui.right_panel.history.viewer import HistoryRightPanelPlaceholder
        from ui.right_panel.live_run.panel import RunRightPanelWidget
        from ui.right_panel.pvp.draft.assignment.target_slot import (
            PvpPostDraftTargetSlotWidget,
        )
        from ui.right_panel.pvp.host import PvpRightPanelHost
        from ui.right_panel.settings.account_data import AccountDataPage

        self.assertEqual(RightPanelPortraitMiniBox.__name__, "RightPanelPortraitMiniBox")
        self.assertEqual(RightPanelWeaponMiniBox.__name__, "RightPanelWeaponMiniBox")
        self.assertEqual(
            RightPanelArtifactMiniZoneWidget.__name__,
            "RightPanelArtifactMiniZoneWidget",
        )
        self.assertEqual(RightPanelSlotCardWidget.__name__, "RightPanelSlotCardWidget")
        self.assertEqual(RightPanelTeamCardWidget.__name__, "RightPanelTeamCardWidget")
        self.assertEqual(RunRightPanelWidget.__name__, "RunRightPanelWidget")
        self.assertEqual(RightOperationsDock.__name__, "RightOperationsDock")
        self.assertEqual(RightDockHeader.__name__, "RightDockHeader")
        self.assertEqual(HistoryRightPanelPlaceholder.__name__, "HistoryRightPanelPlaceholder")
        self.assertIs(PvpPostDraftTargetSlotWidget, RightPanelSlotCardWidget)
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

    def test_pvp_constants_are_owned_by_shared_right_panel_module(self) -> None:
        from ui.pvp_browser import window as pvp_window
        from ui.right_panel.pvp import _shared as shared

        constant_names = (
            "PVP_PAGE_DECKS",
            "PVP_PAGE_PLAY",
            "PVP_PAGE_DRAFT",
            "PVP_DRAFT_STAGE_DRAFT",
            "PVP_DRAFT_STAGE_ASSIGNMENT",
            "PVP_DRAFT_STAGE_WEAPONS",
            "PVP_DRAFT_STAGE_TIMERS_RESULTS",
            "PVP_DRAFT_STAGE_COMPLETED_RESULT",
            "PVP_DRAFT_STAGE_VALUES",
            "PVP_SEATS",
            "PVP_TIMER_CHAMBERS",
        )
        for name in constant_names:
            self.assertEqual(getattr(pvp_window, name), getattr(shared, name), name)

        root = Path(__file__).resolve().parents[3]
        source = (root / "ui/pvp_browser/window.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        local_assignments: set[str] = set()
        for node in tree.body:
            targets = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    local_assignments.add(target.id)
        for name in constant_names:
            self.assertNotIn(name, local_assignments)

    def test_pvp_shared_imports_are_explicit(self) -> None:
        root = Path(__file__).resolve().parents[3]
        for relative_path in (
            "ui/pvp_browser/window.py",
            "ui/right_panel/pvp/decks/panel.py",
            "ui/right_panel/pvp/play/panel.py",
            "ui/right_panel/pvp/draft/panel.py",
        ):
            source = (root / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("from ui.right_panel.pvp._shared import *", source)

    def test_pvp_target_panel_uses_shared_team_slot_cards(self) -> None:
        root = Path(__file__).resolve().parents[3]
        target_slot_source = (
            root / "ui/right_panel/pvp/draft/assignment/target_slot.py"
        ).read_text(encoding="utf-8")
        panel_source = (root / "ui/right_panel/pvp/draft/panel.py").read_text(
            encoding="utf-8"
        )

        self.assertFalse((root / "ui/right_panel/common/compact_slot.py").exists())
        self.assertNotIn("class PvpPostDraftTargetSlotWidget", target_slot_source)
        self.assertIn("RightPanelSlotCardWidget", target_slot_source)
        self.assertIn("RightPanelTeamCardWidget", panel_source)
        self.assertIn("RightPanelSlotPrototypeViewModel", panel_source)
        self.assertIn("RightPanelTeamPrototypeViewModel", panel_source)
        self.assertNotIn("RightPanelCompactSlotWidget", panel_source)


if __name__ == "__main__":
    unittest.main()
