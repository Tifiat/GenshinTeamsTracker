from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from ui.app_shell import _weapon_owner_overlay_icons
from ui.utils.pixel_icon_grid import (
    PixelIconGrid,
    PixelIconGridItem,
    PixelIconGridMetrics,
    PixelIconGridOutline,
    PixelIconGridOverlayIcon,
    build_pixel_icon_grid_layout,
)


_APP = QApplication.instance() or QApplication([])
_OWNER_MARKER = QColor("#e52d9b")
_REFERENCE_WEAPON_SIDE = 48
_REFERENCE_OWNER_SIDE = 45
_REFERENCE_RIGHT_OFFSET = 14
_REFERENCE_TOP_OFFSET = 22


class WeaponOwnerGeometryTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        self.weapon_icon = folder / "weapon.png"
        self.owner_icon = folder / "owner-marker.png"
        self._save_solid_png(self.weapon_icon, QColor("#6f647d"), QSize(48, 48))
        self._save_solid_png(self.owner_icon, _OWNER_MARKER, QSize(9, 9))

    def test_widget_render_keeps_portrait_relative_to_weapon_box_across_outline_updates(self) -> None:
        asset = {
            "metadata": {
                "owner_badges": [
                    {"character_id": "synthetic-owner", "side_icon_path": str(self.owner_icon)}
                ]
            }
        }
        overlay = _weapon_owner_overlay_icons(asset)[0]
        metrics = PixelIconGridMetrics(item_width=48, margin_top=40)
        grid = PixelIconGrid(metrics=metrics, surface="weapon_owner_widget_render_test")
        self.addCleanup(grid.close)
        grid.resize(110, 100)
        grid.set_items(
            (
                PixelIconGridItem(
                    item_id="weapon",
                    icon_path=str(self.weapon_icon),
                    outline=PixelIconGridOutline(
                        color="#50e080",
                        width=2,
                        radius=4,
                        overhang=0,
                        alpha=230,
                    ),
                    overlay_icons=(overlay,),
                ),
            )
        )
        grid.show()
        _APP.processEvents()

        item_box = grid.item_physical_rect("weapon")
        self.assertEqual(item_box.size(), QSize(48, 48))
        expected_relative_bounds = QRect(17, -22, 45, 45)
        for width, overhang in ((2, 0), (4, 0), (7, 3)):
            with self.subTest(width=width, overhang=overhang):
                outline = PixelIconGridOutline(
                    color="#50e080",
                    width=width,
                    radius=4,
                    overhang=overhang,
                    alpha=230,
                )
                self.assertTrue(grid.update_item("weapon", outline=outline))
                _APP.processEvents()

                rendered = QPixmap(grid.size())
                rendered.fill(Qt.GlobalColor.transparent)
                grid.render(rendered)

                bounds = self._pixel_bounds(rendered.toImage())
                self.assertEqual(
                    QRect(
                        bounds.x() - item_box.x(),
                        bounds.y() - item_box.y(),
                        bounds.width(),
                        bounds.height(),
                    ),
                    expected_relative_bounds,
                )

    def test_rendered_owner_canvas_matches_reference_and_ignores_outline_geometry(self) -> None:
        asset = {
            "metadata": {
                "owner_badges": [
                    {"character_id": "synthetic-owner", "side_icon_path": str(self.owner_icon)}
                ]
            }
        }
        overlays = _weapon_owner_overlay_icons(asset)
        self.assertEqual(len(overlays), 1)
        overlay = overlays[0]
        self.assertEqual(overlay.icon_path, str(self.owner_icon))

        # 0.711 exercises the fractional downscaled grid path alongside normal
        # scale, 125% scale and 2x high-DPI layout.
        for dpr in (0.711, 1.0, 1.25, 2.0):
            with self.subTest(dpr=dpr):
                metrics = PixelIconGridMetrics(item_width=48, margin_top=40)
                grid = PixelIconGrid(metrics=metrics, surface="weapon_owner_geometry_test")
                self.addCleanup(grid.close)
                grid.resize(110, 100)
                item = PixelIconGridItem(
                    item_id="weapon",
                    icon_path=str(self.weapon_icon),
                    overlay_icons=overlays,
                )
                grid.set_items((item,))

                # Use the physical item-box rect produced by the grid's own
                # fractional layout. The owner target must stay tied to this
                # box even when the occupied frame expands around it.
                grid._layout = build_pixel_icon_grid_layout(
                    1,
                    110,
                    metrics,
                    dpr=dpr,
                )
                grid._prepare_item_pixmaps(item, dpr)
                item_box = grid._layout.rects[0]
                icon_rect = grid._icon_physical_rect(item, item_box)
                self.assertEqual(icon_rect, item_box)
                expected = self._reference_target(item_box)

                painted_bounds: list[QRect] = []
                for width, overhang in ((2, 0), (4, 1), (7, 3)):
                    outline = PixelIconGridOutline(
                        color="#50e080",
                        width=width,
                        radius=4,
                        overhang=overhang,
                        alpha=230,
                    )
                    painted_bounds.append(
                        self._paint_owner_bounds(
                            grid,
                            item,
                            overlay,
                            icon_rect,
                            outline,
                            dpr,
                        )
                    )

                self.assertEqual(painted_bounds, [expected, expected, expected])
                if dpr == 1.0:
                    self.assertEqual(
                        QRect(
                            expected.x() - item_box.x(),
                            expected.y() - item_box.y(),
                            expected.width(),
                            expected.height(),
                        ),
                        QRect(17, -22, 45, 45),
                    )

    @staticmethod
    def _save_solid_png(path: Path, color: QColor, size: QSize) -> None:
        image = QImage(size, QImage.Format.Format_ARGB32)
        image.fill(color)
        if not image.save(str(path)):
            raise AssertionError(f"could not save synthetic fixture: {path}")

    @staticmethod
    def _reference_target(item_box: QRect) -> QRect:
        """Scale the accepted main-checkout 45px canvas from a 48px weapon box."""
        width = max(
            1,
            int(round(item_box.width() * _REFERENCE_OWNER_SIDE / _REFERENCE_WEAPON_SIDE)),
        )
        height = max(
            1,
            int(round(item_box.height() * _REFERENCE_OWNER_SIDE / _REFERENCE_WEAPON_SIDE)),
        )
        right = int(round(width * _REFERENCE_RIGHT_OFFSET / _REFERENCE_OWNER_SIDE))
        top = int(round(height * _REFERENCE_TOP_OFFSET / _REFERENCE_OWNER_SIDE))
        return QRect(
            item_box.right() - width + 1 + right,
            item_box.top() - top,
            width,
            height,
        )

    def _paint_owner_bounds(
        self,
        grid: PixelIconGrid,
        item: PixelIconGridItem,
        overlay: PixelIconGridOverlayIcon,
        icon_rect: QRect,
        outline: PixelIconGridOutline,
        dpr: float,
    ) -> QRect:
        logical_size = QSize(110, 100)
        canvas = QPixmap(
            max(1, int(round(logical_size.width() * dpr))),
            max(1, int(round(logical_size.height() * dpr))),
        )
        canvas.setDevicePixelRatio(dpr)
        canvas.fill(Qt.GlobalColor.transparent)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        try:
            grid._draw_outline(painter, outline, icon_rect)
            grid._draw_overlay_icon(painter, item, overlay, 0, icon_rect)
        finally:
            painter.end()

        return self._pixel_bounds(canvas.toImage())

    def _pixel_bounds(self, image: QImage) -> QRect:
        points = [
            (x, y)
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y) == _OWNER_MARKER
        ]
        self.assertTrue(points, "the synthetic owner marker was not painted")
        left = min(x for x, _ in points)
        top = min(y for _, y in points)
        right = max(x for x, _ in points)
        bottom = max(y for _, y in points)
        return QRect(left, top, right - left + 1, bottom - top + 1)
