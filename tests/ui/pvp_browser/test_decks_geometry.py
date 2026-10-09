"""Real selection handlers with synthetic inventory and offscreen painted frames."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QObject, QPoint
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QStackedWidget

from run_workspace.pvp.tier_allocation import allocate_requirements
from tests.ui.pvp_browser import test_pvp_performance as _performance
from ui.right_panel.live_run.panel import right_panel_stylesheet


class _Frames(QObject):
    def __init__(self, snapshot, parent):
        super().__init__(parent)
        self.snapshot = snapshot
        self.frames = []

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Paint:
            self.frames.append(self.snapshot())
        return False


class DecksSelectionGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _performance.PvpDecksPerformanceTest.setUpClass()
        cls.app = _performance.PvpDecksPerformanceTest.app
        cls.previous_font = cls.app.font()
        cls.font_ids = []
        if not QFontDatabase.families() and os.name == "nt":
            for name in ("segoeui.ttf", "segoeuib.ttf"):
                font_id = QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / name))
                if font_id >= 0:
                    cls.font_ids.append(font_id)
        if "Segoe UI" in QFontDatabase.families():
            cls.app.setFont(QFont("Segoe UI", 9))

    @classmethod
    def tearDownClass(cls):
        cls.app.setFont(cls.previous_font)
        for font_id in cls.font_ids:
            QFontDatabase.removeApplicationFont(font_id)

    def test_selection_and_allocation_keep_every_painted_frame_and_scroll_position(self):
        for size in ((354, 480), (640, 760)):
            for saved in (False, True):
                with self.subTest(size=size, saved=saved):
                    fixture = _performance.PvpDecksPerformanceTest()
                    fixture.setUp()
                    ws, panel = fixture.workspace, fixture.panel
                    host = QStackedWidget()
                    try:
                        if saved:
                            ws.presets = [ws.active_preset()]
                            ws._editing_is_new_deck = False
                            panel.refresh()
                        host.setStyleSheet(right_panel_stylesheet())
                        host.addWidget(panel)
                        host.setFixedSize(*size)
                        host.show()
                        fixture.settle_allocation()

                        def snapshot():
                            widgets = (panel.ruleset_button, panel._expanded_info,
                                       panel._rules_line_sections["rules_costs_heading"][0],
                                       panel._requirement_section,
                                       panel._rules_line_sections["rules_issues_heading"][0],
                                       *panel.selected_info_labels.values())
                            rects = tuple((w.mapTo(panel, QPoint()).x(), w.mapTo(panel, QPoint()).y(),
                                           w.width(), w.height()) for w in widgets)
                            bar = panel.deck_list_scroll.verticalScrollBar()
                            return rects, (bar.value(), bar.maximum()), panel.deck_list_scroll.widget().height()

                        frames = _Frames(snapshot, panel)
                        panel.installEventFilter(frames)
                        bar = panel.deck_list_scroll.verticalScrollBar()
                        for position in (0, bar.maximum() // 2, bar.maximum()):
                            bar.setValue(position)
                            fixture.settle()
                            expected = snapshot()
                            for kind, asset, click in (
                                ("character", fixture.characters[0], ws._on_character_card_clicked),
                                ("weapon", fixture.weapons[0], ws._on_weapon_card_clicked),
                            ):
                                for _ in range(2):
                                    frames.frames.clear()
                                    with patch.object(ws.rules_controller, "_start_allocation"):
                                        click(asset)
                                    self.assertEqual(snapshot(), expected, (kind, "immediate"))
                                    fixture.settle()
                                    self.assertEqual(snapshot(), expected, (kind, "pending"))
                                    pending = ws.rules_controller._allocation_pending
                                    if pending is not None:
                                        generation, rows, rules = pending
                                        ws.rules_controller._allocation_pending = None
                                        ws.rules_controller._allocation_finished(
                                            generation, allocate_requirements(rows, rules),
                                        )
                                    fixture.settle()
                                    self.assertEqual(snapshot(), expected, (kind, "complete"))
                                    self.assertTrue(frames.frames)
                                    self.assertTrue(all(frame == expected for frame in frames.frames),
                                                    (kind, frames.frames))
                        self.assertFalse(panel._scroll_restore_timer.isActive())
                    finally:
                        host.close()
                        host.removeWidget(panel)
                        fixture.doCleanups()
                        host.deleteLater()
                        self.app.processEvents()

    def test_pending_replacement_groups_keep_the_table_and_wrapped_row_positions(self):
        fixture = _performance.PvpDecksPerformanceTest()
        fixture.setUp()
        ws, panel = fixture.workspace, fixture.panel
        host = QStackedWidget()
        try:
            host.setStyleSheet(right_panel_stylesheet())
            host.addWidget(panel)
            host.setFixedSize(354, 480)
            host.show()
            fixture.settle_allocation()
            for asset in fixture.characters[21:36]:
                ws._on_character_card_clicked(asset)
                fixture.settle_allocation()
            self.assertTrue(any(row.get("allocation_group") for row in panel._settled_requirement_rows))
            table = panel._requirement_table

            def positions():
                return tuple((row["label"].mapTo(panel, QPoint()).y(), row["label"].height())
                             for row in panel._requirement_rows)

            before = positions()
            with patch.object(ws.rules_controller, "_start_allocation"):
                ws._on_character_card_clicked(fixture.characters[0])
            fixture.settle()
            self.assertIs(panel._requirement_table, table)
            self.assertEqual(positions(), before)
            group_indices = [i for i, row in enumerate(panel._settled_requirement_rows)
                             if row.get("allocation_group")]
            for index in group_indices:
                self.assertEqual(panel._requirement_rows[index]["label"].text(), "")
                self.assertEqual(panel._requirement_rows[index]["marker"].property("requirementStatus"), "unknown")
            generation, rows, rules = ws.rules_controller._allocation_pending
            ws.rules_controller._allocation_pending = None
            ws.rules_controller._allocation_finished(generation, allocate_requirements(rows, rules))
            fixture.settle()
            self.assertIs(panel._requirement_table, table)
            self.assertTrue(all(panel._requirement_rows[i]["label"].text() for i in group_indices))
            self.assertEqual(ws.rules_controller._report["character_count"], 62)
        finally:
            host.close()
            host.removeWidget(panel)
            fixture.doCleanups()
            host.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
