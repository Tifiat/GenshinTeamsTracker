from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from ui.utils.hidpi_pixmap import (
    effective_pixmap_dpr,
    load_hidpi_pixmap,
    logical_pixmap_size,
    make_hidpi_canvas,
    physical_size_for_logical,
)


class HidpiPixmapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_physical_size_uses_dpr_for_logical_size(self) -> None:
        self.assertEqual(physical_size_for_logical(QSize(48, 48), 1.0), QSize(48, 48))
        self.assertEqual(physical_size_for_logical(QSize(48, 48), 1.25), QSize(60, 60))

    def test_effective_dpr_clamps_startup_downscale(self) -> None:
        self.assertEqual(effective_pixmap_dpr(0.711), 1.0)
        self.assertEqual(physical_size_for_logical(QSize(48, 48), 0.711), QSize(48, 48))

    def test_load_hidpi_pixmap_cache_key_includes_dpr(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "icon.png"
            source = QPixmap(128, 128)
            source.fill(QColor("#ff0000"))
            self.assertTrue(source.save(str(path)))

            cache = {}
            first = load_hidpi_pixmap(
                path,
                QSize(48, 48),
                dpr=1.0,
                aspect_mode=Qt.AspectRatioMode.KeepAspectRatio,
                cache=cache,
            )
            second = load_hidpi_pixmap(
                path,
                QSize(48, 48),
                dpr=1.25,
                aspect_mode=Qt.AspectRatioMode.KeepAspectRatio,
                cache=cache,
            )
            third = load_hidpi_pixmap(
                path,
                QSize(48, 48),
                dpr=1.25,
                aspect_mode=Qt.AspectRatioMode.KeepAspectRatio,
                cache=cache,
            )

        self.assertFalse(first.cache_hit)
        self.assertFalse(second.cache_hit)
        self.assertTrue(third.cache_hit)
        self.assertEqual(first.pixmap.size(), QSize(48, 48))
        self.assertEqual(second.pixmap.size(), QSize(60, 60))
        self.assertEqual(second.pixmap.devicePixelRatio(), 1.25)
        self.assertEqual(logical_pixmap_size(second.pixmap), QSize(48, 48))

    def test_hidpi_canvas_reports_logical_size(self) -> None:
        canvas = make_hidpi_canvas(QSize(22, 26), 1.5)

        self.assertEqual(canvas.size(), QSize(33, 39))
        self.assertEqual(canvas.devicePixelRatio(), 1.5)
        self.assertEqual(logical_pixmap_size(canvas), QSize(22, 26))


if __name__ == "__main__":
    unittest.main()
