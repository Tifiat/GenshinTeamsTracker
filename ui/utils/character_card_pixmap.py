"""Prepare a styled portrait in memory from explicit character layer paths.

Live slots and new frozen History use the same recipe as the browser. No layer
is looked up from the live account here, and no composed image is saved to disk.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap

from run_workspace.profile_context import account_asset_path
from ui.utils.character_card_layers import with_character_card_layers
from ui.utils.hidpi_pixmap import load_hidpi_pixmap, logical_pixmap_size, make_hidpi_canvas
from ui.utils.pixel_icon_grid import PixelIconGridItem


def character_card_pixmap(
    portrait_path: str, size: QSize | int, *, dpr: float = 1.,
    rarity: int | None = None, element: str = "", constellation: int | None = None,
    background_path: str = "", element_icon_path: str = "",
) -> QPixmap | None:
    dimensions = QSize(size, size) if isinstance(size, int) else QSize(size)
    raw = load_hidpi_pixmap(account_asset_path(portrait_path), dimensions, dpr=dpr,
                           surface="character_card_portrait").pixmap if portrait_path else QPixmap()
    if raw.isNull():
        return None
    item = with_character_card_layers(
        PixelIconGridItem("portrait", portrait_path),
        {"rarity": rarity, "element": element, "constellation": constellation},
        background_path=background_path, element_icon_path=element_icon_path,
    )
    canvas = make_hidpi_canvas(dimensions, dpr=dpr)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    try:
        frame = QRectF(0, 0, dimensions.width(), dimensions.height())
        if item.background is not None and item.background.icon_path:
            background = load_hidpi_pixmap(account_asset_path(item.background.icon_path), dimensions, dpr=dpr,
                                           aspect_mode=Qt.AspectRatioMode.IgnoreAspectRatio,
                                           surface="character_card_background").pixmap
            if not background.isNull():
                painter.drawPixmap(frame, background, QRectF(background.rect()))
        raw_size = logical_pixmap_size(raw)
        portrait_rect = QRectF((dimensions.width()-raw_size.width())/2, (dimensions.height()-raw_size.height())/2,
                              raw_size.width(), raw_size.height())
        painter.drawPixmap(portrait_rect, raw, QRectF(raw.rect()))
        for overlay in item.overlay_icons:
            icon_size = max(1, round(min(dimensions.width(), dimensions.height()) * overlay.size_ratio))
            icon = load_hidpi_pixmap(account_asset_path(overlay.icon_path), icon_size, dpr=dpr,
                                    surface="character_card_element").pixmap
            if icon.isNull():
                continue
            left = -icon_size * overlay.right_overhang_ratio
            top = -icon_size * overlay.top_overhang_ratio
            painter.drawPixmap(QRectF(left, top, icon_size, icon_size), icon, QRectF(icon.rect()))
        for badge in item.badges:
            scale = min(dimensions.width(), dimensions.height()) / 96
            width, height, margin = badge.width*scale, badge.height*scale, badge.margin*scale
            left = frame.right() - width - margin
            top = frame.top() + margin
            badge_rect = QRectF(left, top, width, height)
            fill = QColor(badge.color)
            fill.setAlpha(badge.fill_alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(badge_rect, 5*scale, 5*scale)
            painter.setPen(QColor(badge.text_color))
            font = painter.font()
            font.setPointSizeF(badge.font_size*scale)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge.text)
    finally:
        painter.end()
    return canvas
