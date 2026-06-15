from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QVBoxLayout, QWidget

from run_workspace.right_panel_prototype_view_model import RightPanelTeamPrototypeViewModel
from ui.right_panel.common.metrics import SLOT_CARD_FIXED_HEIGHT, _clear_layout
from ui.right_panel.common.slot_card import RightPanelSlotCardWidget

class RightPanelTeamCardWidget(QFrame):
    slot_selected = Signal(int, int)
    slot_dropped = Signal(int, int, int, int)

    def __init__(
        self,
        model: RightPanelTeamPrototypeViewModel,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("TeamSlotRow")
        self._model = model
        self._slot_widgets: list[RightPanelSlotCardWidget] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(4)
        self._grid.setVerticalSpacing(6)
        layout.addWidget(self._grid_container)
        self._rebuild_slot_widgets(model)
        self._sync_fixed_height()

    def set_model(self, model: RightPanelTeamPrototypeViewModel) -> None:
        self._model = model
        if len(model.slots) != len(self._slot_widgets):
            self._rebuild_slot_widgets(model)
            self._sync_fixed_height()
            return
        for slot_widget, slot in zip(self._slot_widgets, model.slots):
            slot_widget.set_model(slot)

    def slot_count(self) -> int:
        return len(self._slot_widgets)

    def slot_widgets(self) -> list["RightPanelSlotCardWidget"]:
        return list(self._slot_widgets)

    def _rebuild_slot_widgets(self, model: RightPanelTeamPrototypeViewModel) -> None:
        _clear_layout(self._grid)
        self._slot_widgets.clear()
        for index, slot in enumerate(model.slots):
            widget = RightPanelSlotCardWidget(slot)
            widget.clicked.connect(self.slot_selected.emit)
            widget.dropped.connect(self.slot_dropped.emit)
            self._slot_widgets.append(widget)
            self._grid.addWidget(widget, index // 4, index % 4)

    def _sync_fixed_height(self) -> None:
        slot_count = max(1, len(self._slot_widgets))
        rows = max(1, (slot_count + 3) // 4)
        vertical_spacing = max(0, self._grid.verticalSpacing())
        grid_height = rows * SLOT_CARD_FIXED_HEIGHT + max(0, rows - 1) * vertical_spacing
        frame_height = grid_height + 8
        self._grid_container.setFixedHeight(grid_height)
        self.setFixedHeight(frame_height)


# Deprecated compatibility name for old imports/tests.
RightPanelTeamPrototypeWidget = RightPanelTeamCardWidget

__all__ = [name for name in globals() if not name.startswith("__")]
