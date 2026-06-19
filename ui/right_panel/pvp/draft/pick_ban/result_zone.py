from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from localization import tr
from ui.right_panel.pvp._shared import PVP_DRAFT_BAN_ACCENT
from ui.utils.pixel_icon_grid import PixelIconGrid, PixelIconGridItem, PixelIconGridMetrics
from ui.utils.pvp_colors import pvp_player_color


class PvpDraftResultZoneWidget(QFrame):
    """Compact image-backed Draft result zone using the shared painted grid."""

    def __init__(
        self,
        *,
        seat: str,
        zone: str,
        title: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.seat = seat
        self.zone = zone
        self.items_by_character_id: dict[str, PixelIconGridItem] = {}
        self.setObjectName("pvp_draft_result_zone")
        self.setProperty("seat", seat)
        self.setProperty("zone", zone)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 6, 7, 6)
        layout.setSpacing(5)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("pvp_draft_result_title")
        layout.addWidget(self.title_label)

        picked = zone == "picked"
        self.grid = PixelIconGrid(
            metrics=PixelIconGridMetrics(
                item_width=72 if picked else 42,
                item_height=72 if picked else 42,
                gap_x=4,
                gap_y=4,
            ),
            surface=f"pvp_draft_result_{zone}",
        )
        self.grid.setObjectName(
            "pvp_draft_result_pick_grid" if picked else "pvp_draft_result_ban_grid"
        )
        layout.addWidget(self.grid)

        self.empty_label = QLabel(tr("app_shell.pvp.draft.none"))
        self.empty_label.setObjectName("small_muted")
        layout.addWidget(self.empty_label)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def refresh_player_color(self) -> None:
        self.update()

    def set_items(self, items: Iterable[PixelIconGridItem]) -> None:
        values = tuple(items)
        self.items_by_character_id = {item.item_id: item for item in values}
        self.grid.set_items(values)
        self.empty_label.setVisible(not values)
        self.grid.setVisible(bool(values))

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        color = PVP_DRAFT_BAN_ACCENT if self.zone == "banned" else pvp_player_color(self.seat)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QPen(QColor(color), 1))
            painter.setBrush(QColor(0, 0, 0, 0))
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 6, 6)
        finally:
            painter.end()


__all__ = ["PvpDraftResultZoneWidget"]
