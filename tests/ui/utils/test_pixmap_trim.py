from __future__ import annotations

import unittest

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication

from ui.utils.pixmap_utils import trim_transparent_pixmap


class PixmapTrimTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def assert_matches_alpha_reference(self, source, threshold):
        image = source.toImage()
        limit = max(0, min(255, int(threshold)))
        points = [
            (x, y)
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > limit
        ]
        expected = source
        if points:
            xs, ys = zip(*points)
            expected = source.copy(QRect(
                min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1,
            ))
        actual = trim_transparent_pixmap(source, alpha_threshold=threshold)
        self.assertEqual(actual.toImage(), expected.toImage())
        self.assertEqual(actual.devicePixelRatio(), source.devicePixelRatio())
        self.assertEqual(source.toImage(), image)

    def test_threshold_crop_matches_pixel_reference_for_formats_and_dpr(self):
        image = QImage(7, 9, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        for x, y, alpha in ((0, 1, 1), (6, 2, 8), (1, 0, 16), (5, 8, 128),
                            (2, 3, 254), (3, 4, 255)):
            image.setPixelColor(x, y, QColor(90, 130, 200, alpha))
        for image_format in (QImage.Format.Format_ARGB32,
                             QImage.Format.Format_ARGB32_Premultiplied,
                             QImage.Format.Format_RGBA8888,
                             QImage.Format.Format_RGBA64,
                             QImage.Format.Format_RGB888):
            for dpr in (1.0, 1.25, 2.0):
                pixmap = QPixmap.fromImage(image.convertToFormat(image_format))
                pixmap.setDevicePixelRatio(dpr)
                for threshold in (-1, 0, 1, 8, 16, 128, 254, 255, 300):
                    with self.subTest(format=image_format, dpr=dpr, threshold=threshold):
                        self.assert_matches_alpha_reference(pixmap, threshold)

    def test_empty_and_fully_transparent_pixmaps_keep_original_extent(self):
        empty = QPixmap()
        self.assertTrue(trim_transparent_pixmap(empty).isNull())
        transparent = QPixmap(7, 9)
        transparent.fill(Qt.GlobalColor.transparent)
        for threshold in (0, 16, 255):
            self.assert_matches_alpha_reference(transparent, threshold)


if __name__ == "__main__":
    unittest.main()
