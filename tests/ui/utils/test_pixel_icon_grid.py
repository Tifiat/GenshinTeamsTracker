from __future__ import annotations

import unittest

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from ui.utils.pixel_icon_grid import (
    PixelIconGrid,
    PixelIconGridItem,
    PixelIconGridMetrics,
    build_pixel_icon_grid_layout,
)


class PixelIconGridLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_fractional_downscale_uses_integer_physical_pitch(self) -> None:
        metrics = PixelIconGridMetrics(item_width=72, gap_x=3, margin_top=4)
        layout = build_pixel_icon_grid_layout(
            24,
            620,
            metrics,
            dpr=0.711,
        )

        pitch = layout.item_width + layout.gap_x
        self.assertGreater(layout.columns, 1)
        for index, rect in enumerate(layout.rects):
            row = index // layout.columns
            col = index % layout.columns
            self.assertEqual(rect.x(), layout.margin_left + col * pitch)
            self.assertEqual(rect.y(), layout.margin_top + row * (layout.item_height + layout.gap_y))

    def test_neighbor_gaps_do_not_accumulate_drift(self) -> None:
        metrics = PixelIconGridMetrics(item_width=72, gap_x=3)
        layout = build_pixel_icon_grid_layout(
            30,
            620,
            metrics,
            dpr=0.711,
        )

        for row in range(layout.rows):
            row_rects = layout.rects[row * layout.columns : (row + 1) * layout.columns]
            for left, right in zip(row_rects, row_rects[1:]):
                self.assertEqual(right.left() - left.right() - 1, layout.gap_x)

    def test_hit_testing_uses_item_rects(self) -> None:
        grid = PixelIconGrid(metrics=PixelIconGridMetrics(item_width=20, gap_x=2))
        grid.resize(100, 100)
        grid.set_items(
            [
                PixelIconGridItem(item_id="a", icon_path=""),
                PixelIconGridItem(item_id="b", icon_path=""),
            ]
        )

        rect = grid.item_logical_rect("b").toAlignedRect()
        self.assertEqual(grid.item_at(rect.center()), "b")
        self.assertEqual(grid.item_at(QPoint(0, grid.height() - 1)), "")

    def test_click_item_for_test_emits_stable_id(self) -> None:
        grid = PixelIconGrid(metrics=PixelIconGridMetrics(item_width=20, gap_x=2))
        clicked: list[str] = []
        grid.item_clicked.connect(clicked.append)
        grid.set_items([PixelIconGridItem(item_id="10000050", icon_path="")])

        self.assertTrue(grid.click_item_for_test("10000050"))

        self.assertEqual(clicked, ["10000050"])


if __name__ == "__main__":
    unittest.main()
