from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from run_workspace.abyss.source_data import (
    AbyssEnemySourceRow,
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
                side_summaries=(),
            )
            widget = PvpTimersResultWidget()
            widget.set_state(
                completed=False,
                timer_texts={"player_1": ["", "", ""], "player_2": ["", "", ""]},
                result=None,
                source_data=source,
            )

            self.assertIn("2026-06-16", widget.period_label.text())
            enemy_html = widget._enemy_labels[(1, 1)].text()
            self.assertIn("Test Automaton", enemy_html)
            self.assertIn("<img", enemy_html)
            self.assertFalse(widget.finalize_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
