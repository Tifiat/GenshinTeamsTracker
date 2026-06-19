from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QWheelEvent
from PySide6.QtWidgets import QApplication, QLabel

from run_workspace.abyss.source_data import (
    AbyssEnemySourceRow,
    AbyssChamberSideSourceData,
    AbyssFloorSourceData,
    AbyssPeriod,
)
from ui.pvp_browser.timers import PvpTimersResultWidget


class PvpTimersResultWidgetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_cached_abyss_enemy_and_period_render_in_timer_scene(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            icon_path = Path(temp_dir) / "enemy.png"
            image = QImage(8, 8, QImage.Format.Format_ARGB32)
            image.fill(QColor("#d7b461"))
            self.assertTrue(image.save(str(icon_path)))
            source = AbyssFloorSourceData(
                floor=12,
                period=AbyssPeriod(
                    start_date="2026-06-16",
                    end_date="2026-07-16",
                    source="test",
                ),
                source_urls={},
                enemy_rows=(
                    AbyssEnemySourceRow(
                        floor=12,
                        chamber=1,
                        side=1,
                        side_name="First Half",
                        wave=1,
                        enemy_count=2,
                        display_level=100,
                        primary_display_name="Test Automaton",
                        fandom_enemy_page_url=None,
                        fandom_icon_url=None,
                        matched_nanoka_display_name=None,
                        nanoka_monster_id=None,
                        nanoka_icon_url=None,
                        nanoka_enemy_detail_url=None,
                        nanoka_hp=None,
                        hp_source="unavailable",
                        match_method="unmatched",
                        match_confidence="none",
                        cached_icon_path=str(icon_path),
                    ),
                ),
                side_summaries=(
                    AbyssChamberSideSourceData(
                        floor=12,
                        chamber=1,
                        side=1,
                        side_name="First Half",
                        waves=(),
                        solo_target_hp=1234567,
                        multi_target_hp=2345678,
                    ),
                ),
            )
            widget = PvpTimersResultWidget()
            widget.set_state(
                completed=False,
                timer_texts={"player_1": ["", "", ""], "player_2": ["", "", ""]},
                result=None,
                source_data=source,
            )

            self.assertIn("2026-06-16", widget.period_label.text())
            side = widget._side_widgets[(1, 1)]
            enemy_labels = side.findChildren(QLabel, "pvp_timer_enemy_name")
            self.assertEqual([label.text() for label in enemy_labels], ["x2 Test Automaton"])
            self.assertEqual(side.solo_value.text(), "1 234 567")
            self.assertEqual(side.multi_value.text(), "2 345 678")
            self.assertFalse(widget.finalize_button.isEnabled())

    def test_pvp_timers_reuse_common_wheel_controls_and_scoreboard(self) -> None:
        widget = PvpTimersResultWidget()
        widget.set_state(
            completed=False,
            timer_texts={"player_1": ["", "", ""], "player_2": ["", "", ""]},
            result=None,
            source_data=None,
        )
        first = widget.timer_input("player_1", 0)
        self.assertIsNotNone(first)
        first.sec_edit.wheelEvent(_wheel_event(120))
        self.assertEqual(first.seconds_left, 1)

        for index in range(3):
            self.assertTrue(widget.set_timer_seconds_for_test("player_1", index, 60))
        for index, seconds in enumerate((70, 60, 60)):
            self.assertTrue(widget.set_timer_seconds_for_test("player_2", index, seconds))

        self.assertTrue(widget.finalize_button.isEnabled())
        self.assertEqual(widget.difference_label.text(), "00:10")
        self.assertEqual(widget.left_chevron.text(), "▲")
        self.assertEqual(widget.right_chevron.text(), "▼")
        self.assertEqual(widget.left_chevron.property("outcome"), "winner")
        self.assertEqual(widget.right_chevron.property("outcome"), "loser")


def _wheel_event(delta: int) -> QWheelEvent:
    return QWheelEvent(
        QPointF(0, 0),
        QPointF(0, 0),
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )


if __name__ == "__main__":
    unittest.main()
