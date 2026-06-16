from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from localization import tr
from ui.right_panel.common.slot_parts import RightPanelPortraitMiniBox, slot_portrait_fallback
from ui.right_panel.pvp._shared import _refresh_qss, _text


class PvpDraftResultChipWidget(QFrame):
    def __init__(
        self,
        *,
        item: Mapping[str, Any],
        zone: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.character_id = _text(item.get("character_id"))
        self.setObjectName(
            "pvp-draft-result-pick-chip"
            if zone == "picked"
            else "pvp-draft-result-ban-chip"
        )
        self.setProperty("zone", zone)
        self.setProperty("characterId", self.character_id)
        self.setProperty("hasImage", bool(_text(item.get("portrait_path"))))

        picked = zone == "picked"
        self.setFixedSize(QSize(78, 78) if picked else QSize(42, 48))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        name = _text(item.get("name")) or self.character_id
        portrait = RightPanelPortraitMiniBox(
            box_size=QSize(44, 44) if picked else QSize(30, 30),
            object_name="pvp-draft-result-portrait",
            empty_object_name="pvp-draft-result-portrait",
        )
        loaded = portrait.set_portrait(
            image_path=_text(item.get("portrait_path")),
            fallback_text=slot_portrait_fallback(name, 0),
            empty=False,
            surface="pvp_draft_result_chip",
        )
        self.setProperty("hasPortraitPixmap", loaded)
        layout.addWidget(portrait, alignment=Qt.AlignmentFlag.AlignCenter)

        if picked:
            label = QLabel(name)
            label.setObjectName("pvp-draft-result-chip-name")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(False)
            label.setFixedHeight(18)
            layout.addWidget(label)

        _refresh_qss(self)
        _refresh_qss(portrait)


class PvpDraftResultZoneWidget(QFrame):
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
        self.chips_by_character_id: dict[str, PvpDraftResultChipWidget] = {}
        self.setObjectName("pvp_draft_result_zone")
        self.setProperty("seat", seat)
        self.setProperty("zone", zone)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(6)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("pvp_draft_result_title")
        layout.addWidget(self.title_label)

        self.grid_widget = QWidget()
        self.grid_widget.setObjectName("pvp-draft-result-chip-grid")
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setHorizontalSpacing(4)
        self.grid_layout.setVerticalSpacing(4)
        layout.addWidget(self.grid_widget)

        self.empty_label = QLabel(tr("app_shell.pvp.draft.none"))
        self.empty_label.setObjectName("small_muted")
        layout.addWidget(self.empty_label)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_items(self, items: Iterable[Mapping[str, Any]]) -> None:
        _clear_grid(self.grid_layout)
        self.chips_by_character_id.clear()
        values = [dict(item) for item in items]
        columns = 4 if self.zone == "picked" else 8
        for index, item in enumerate(values):
            chip = PvpDraftResultChipWidget(item=item, zone=self.zone)
            self.chips_by_character_id[chip.character_id] = chip
            self.grid_layout.addWidget(chip, index // columns, index % columns)
        self.empty_label.setVisible(not values)
        self.grid_widget.setVisible(bool(values))


def _clear_grid(grid: QGridLayout) -> None:
    while grid.count():
        item = grid.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


__all__ = ["PvpDraftResultChipWidget", "PvpDraftResultZoneWidget"]
