from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from ui.utils.hidpi_pixmap import HidpiPixmapResult
from ui.utils.pixel_icon_grid import (
    PixelIconGrid,
    PixelIconGridBadge,
    PixelIconGridItem,
    PixelIconGridMetrics,
    PixelIconGridOutline,
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

    def test_short_rows_align_to_left_edge_of_centered_capacity_grid(self) -> None:
        metrics = PixelIconGridMetrics(item_width=50, gap_x=10)
        layout = build_pixel_icon_grid_layout(
            2,
            220,
            metrics,
            dpr=1.0,
        )

        self.assertEqual(layout.columns, 3)
        self.assertEqual(layout.margin_left, 25)
        self.assertEqual(layout.margin_right, 25)
        self.assertEqual(layout.rects[0].x(), 25)
        self.assertEqual(layout.rects[1].x(), 85)

    def test_layout_recomputes_columns_when_width_shrinks(self) -> None:
        metrics = PixelIconGridMetrics(item_width=50, gap_x=10)
        wide = build_pixel_icon_grid_layout(2, 220, metrics, dpr=1.0)
        narrow = build_pixel_icon_grid_layout(2, 50, metrics, dpr=1.0)

        self.assertEqual(wide.rects[1].y(), 0)
        self.assertGreater(narrow.rects[1].y(), 0)

    def test_widget_minimum_width_does_not_pin_previous_viewport_width(self) -> None:
        grid = PixelIconGrid(metrics=PixelIconGridMetrics(item_width=50, gap_x=10))
        grid.set_items(
            [
                PixelIconGridItem(item_id="a", icon_path=""),
                PixelIconGridItem(item_id="b", icon_path=""),
            ]
        )
        grid.resize(220, 100)

        self.assertEqual(grid.minimumSizeHint().width(), 1)

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

    def test_outline_only_update_does_not_reload_pixmaps(self) -> None:
        grid = PixelIconGrid(metrics=PixelIconGridMetrics(item_width=20, gap_x=2))
        with patch(
            "ui.utils.pixel_icon_grid.load_hidpi_pixmap",
            return_value=HidpiPixmapResult(QPixmap(), False, 1.0),
        ) as load:
            grid.set_items([PixelIconGridItem(item_id="a", icon_path="a.png")])
            self.assertEqual(load.call_count, 1)

            updated = grid.update_item(
                "a",
                outline=PixelIconGridOutline(
                    color="#35d07f",
                    right_color="#4e91ff",
                ),
            )

        self.assertTrue(updated)
        self.assertEqual(load.call_count, 1)

    def test_split_outline_paints_left_and_right_owner_colors(self) -> None:
        canvas = QPixmap(80, 80)
        canvas.fill(Qt.GlobalColor.transparent)
        grid = PixelIconGrid(metrics=PixelIconGridMetrics(item_width=72))
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        try:
            grid._draw_outline(
                painter,
                PixelIconGridOutline(
                    color="#16c7e8",
                    right_color="#d8ed35",
                    width=4,
                    radius=0,
                    alpha=255,
                ),
                QRect(4, 4, 72, 72),
            )
        finally:
            painter.end()

        image = canvas.toImage()
        left = QColor("#16c7e8")
        right = QColor("#d8ed35")
        for point in (QPoint(5, 40), QPoint(20, 5)):
            self.assertEqual(image.pixelColor(point), left, point)
        for point in (QPoint(74, 40), QPoint(60, 5)):
            self.assertEqual(image.pixelColor(point), right, point)

    def test_badge_only_update_does_not_reload_pixmaps(self) -> None:
        grid = PixelIconGrid(metrics=PixelIconGridMetrics(item_width=72, gap_x=2))
        with patch(
            "ui.utils.pixel_icon_grid.load_hidpi_pixmap",
            return_value=HidpiPixmapResult(QPixmap(), False, 1.0),
        ) as load:
            grid.set_items([PixelIconGridItem(item_id="a", icon_path="a.png")])
            self.assertEqual(load.call_count, 1)

            updated = grid.update_item(
                "a",
                badges=(
                    PixelIconGridBadge("C1", "#35d07f", "bottom_left"),
                    PixelIconGridBadge("C6", "#4e91ff", "bottom_right"),
                ),
            )

        self.assertTrue(updated)
        self.assertEqual(load.call_count, 1)

    def test_pixmap_input_update_reloads_pixmaps(self) -> None:
        grid = PixelIconGrid(metrics=PixelIconGridMetrics(item_width=20, gap_x=2))
        with patch(
            "ui.utils.pixel_icon_grid.load_hidpi_pixmap",
            return_value=HidpiPixmapResult(QPixmap(), False, 1.0),
        ) as load:
            grid.set_items([PixelIconGridItem(item_id="a", icon_path="a.png")])
            self.assertEqual(load.call_count, 1)

            updated = grid.update_item("a", icon_path="b.png")

        self.assertTrue(updated)
        self.assertEqual(load.call_count, 2)

    def test_repeated_show_event_skips_unchanged_pixmap_inputs(self) -> None:
        grid = PixelIconGrid(metrics=PixelIconGridMetrics(item_width=20, gap_x=2))
        with patch(
            "ui.utils.pixel_icon_grid.load_hidpi_pixmap",
            return_value=HidpiPixmapResult(QPixmap(), False, 1.0),
        ) as load:
            grid.set_items([PixelIconGridItem(item_id="a", icon_path="a.png")])
            self.assertEqual(load.call_count, 1)

            QApplication.sendEvent(grid, QEvent(QEvent.Type.Show))

        self.assertEqual(load.call_count, 1)


if __name__ == "__main__":
    unittest.main()
