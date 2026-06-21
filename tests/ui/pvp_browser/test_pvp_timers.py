from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QWheelEvent
from PySide6.QtWidgets import QApplication, QFrame, QLabel

from run_workspace.abyss.source_data import (
    AbyssEnemySourceRow,
    AbyssChamberSideSourceData,
    AbyssFloorSourceData,
    AbyssPeriod,
)
from ui.pvp_browser.timers import (
    PVP_TIMER_HP_COLUMN_WIDTH,
    PVP_TIMER_INPUT_COLUMN_WIDTH,
    PvpTimersResultWidget,
)


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
            hp = widget._hp_widgets[(1, 1)]
            self.assertGreaterEqual(hp.width(), PVP_TIMER_HP_COLUMN_WIDTH)
            self.assertEqual(hp.solo_value.text(), "1 234 567")
            self.assertEqual(hp.multi_value.text(), "2 345 678")
            self.assertFalse(widget.finalize_button.isEnabled())
            self.assertTrue(widget.set_timer_seconds_for_test("player_1", 0, 540))
            self.assertIn("60", widget.total_labels["player_1"].text())
            self.assertEqual(
                widget.dps_value_labels[("player_1", "solo")].text(),
                "20 576",
            )
            self.assertEqual(
                widget.dps_value_labels[("player_1", "multi")].text(),
                "39 095",
            )

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
        self.assertEqual(first.seconds_left, 600)
        first.sec_edit.wheelEvent(_wheel_event(-120))
        self.assertEqual(first.seconds_left, 599)
        self.assertIn("1", widget.total_labels["player_1"].text())

        for index in range(3):
            self.assertTrue(widget.set_timer_seconds_for_test("player_1", index, 540))
        for index, seconds in enumerate((530, 540, 540)):
            self.assertTrue(widget.set_timer_seconds_for_test("player_2", index, seconds))

        self.assertTrue(widget.finalize_button.isEnabled())
        self.assertIn("10", widget.difference_label.text())
        self.assertIn("180", widget.total_labels["player_1"].text())
        self.assertIn("190", widget.total_labels["player_2"].text())
        self.assertEqual(widget.left_chevron.text(), "▲")
        self.assertEqual(widget.right_chevron.text(), "▼")
        self.assertEqual(widget.left_chevron.property("outcome"), "winner")
        self.assertEqual(widget.right_chevron.property("outcome"), "loser")

    def test_pvp_timers_use_fixed_timer_hp_and_dps_table_columns(self) -> None:
        widget = PvpTimersResultWidget()
        widget.resize(900, 700)
        widget.show()
        widget.set_state(
            completed=False,
            timer_texts={"player_1": ["", "", ""], "player_2": ["", "", ""]},
            result=None,
            source_data=None,
        )
        QApplication.processEvents()

        timer_inputs = [
            widget.timer_input(seat, index)
            for index in range(3)
            for seat in ("player_1", "player_2")
        ]
        self.assertTrue(all(timer is not None for timer in timer_inputs))
        self.assertEqual(
            {timer.width() for timer in timer_inputs if timer is not None},
            {PVP_TIMER_INPUT_COLUMN_WIDTH},
        )
        self.assertEqual(
            {timer.mapTo(widget, QPoint(0, 0)).x() for timer in timer_inputs if timer is not None},
            {next(timer for timer in timer_inputs if timer is not None).mapTo(widget, QPoint(0, 0)).x()},
        )
        hp_widths = {hp.width() for hp in widget._hp_widgets.values()}
        self.assertEqual(len(hp_widths), 1)
        self.assertGreaterEqual(next(iter(hp_widths)), PVP_TIMER_HP_COLUMN_WIDTH)
        self.assertTrue(widget.findChild(QFrame, "pvp_timer_dps_table"))
        self.assertFalse(widget.findChildren(QFrame, "pvp_timer_dps_card"))

        self.assertTrue(widget.set_timer_seconds_for_test("player_2", 1, 530))
        self.assertIn("70", widget.total_labels["player_2"].text())
        self.assertIn("70", widget.difference_label.text())

        widget.hide()


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
