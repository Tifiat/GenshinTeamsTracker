from __future__ import annotations

import html
import os
from pathlib import Path
import re
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QImage, QTextDocument
from PySide6.QtWidgets import QApplication

from run_workspace.right_panel_prototype_view_model import (
    FactDpsEnemyTooltipViewModel,
    FactDpsTooltipViewModel,
)
from ui.right_panel.live_run.panel import _fact_dps_tooltip_html


class FactDpsTooltipIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _tooltip(self, path: str | None) -> FactDpsTooltipViewModel:
        enemy = FactDpsEnemyTooltipViewModel(
            wave=1, primary_display_name="Enemy", enemy_count=1, display_level=100,
            matched_nanoka_display_name=None, hp_used=1000, hp_source="fixture",
            match_method="fixture", match_confidence="high", cached_icon_path=path,
        )
        return FactDpsTooltipViewModel(
            title="Abyss", formula="HP / time", total_hp=1000, total_solo_hp=1000,
            total_multi_target_hp=1000, hp_mode="solo", hp_mode_label="OFF",
            elapsed_seconds=10, calculated_dps=100, hp_source_label="fixture",
            enemies=(enemy,),
        )

    def test_qt_loads_local_tooltip_icon_with_spaces_unicode_and_url_punctuation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "monster icons" / "Иконка #1%.png"
            path.parent.mkdir()
            icon = QImage(32, 32, QImage.Format.Format_ARGB32)
            icon.fill(QColor("#dd8800"))
            self.assertTrue(icon.save(str(path), "PNG"))
            text = _fact_dps_tooltip_html(self._tooltip(str(path)))
            source = html.unescape(re.search(r"<img src='([^']+)'", text).group(1))
            url = QUrl(source)
            self.assertTrue(url.isLocalFile(), source)
            self.assertEqual(Path(url.toLocalFile()), path)
            document = QTextDocument()
            document.setHtml(text)
            resource = document.resource(QTextDocument.ResourceType.ImageResource, url)
            self.assertIsNotNone(resource)
            self.assertFalse(resource.isNull())
            self.assertEqual(resource.size(), icon.size())

    def test_missing_icon_preserves_enemy_name_and_hp_without_image_tag(self) -> None:
        text = _fact_dps_tooltip_html(self._tooltip(None))
        self.assertNotIn("<img", text)
        self.assertIn("Enemy", text)
        self.assertIn("1,000", text)


if __name__ == "__main__":
    unittest.main()
