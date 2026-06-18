from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from localization import tr
from run_workspace.history_snapshot import (
    HistorySnapshotBundle,
    HistorySnapshotBundleError,
    history_snapshot_bundle_from_json_text,
)
from run_workspace.history_snapshot_listing import HistorySnapshotDetailsPayload
from run_workspace.history_snapshot_right_panel import (
    build_history_snapshot_right_panel_view_model,
    first_occupied_history_slot,
)
from ui.right_panel.live_run.panel import RunRightPanelWidget


class HistoryRightPanelHost(QWidget):
    """Hosts an isolated read-only instance of the shared Run panel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.empty_label = QLabel()
        self.empty_label.setObjectName("SubtleText")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setContentsMargins(16, 16, 16, 16)
        root.addWidget(self.empty_label, 1)

        self.run_panel: RunRightPanelWidget | None = None
        self._bundle: HistorySnapshotBundle | None = None
        self._bundle_dir: Path | None = None
        self._selected: tuple[int, int] | None = None
        self.retranslate_ui()

    def set_snapshot_details(
        self,
        payload: HistorySnapshotDetailsPayload | None,
    ) -> None:
        if payload is None or payload.bundle_path is None:
            self._clear_snapshot()
            return
        path = Path(payload.bundle_path)
        try:
            bundle = history_snapshot_bundle_from_json_text(
                path.read_text(encoding="utf-8")
            )
        except (OSError, HistorySnapshotBundleError):
            self._clear_snapshot()
            return
        self._bundle = bundle
        self._bundle_dir = path.parent
        self._selected = first_occupied_history_slot(bundle)
        self._render_snapshot()

    def retranslate_ui(self) -> None:
        self.empty_label.setText(tr("app_shell.history.viewer.empty"))
        if self.run_panel is not None:
            self.run_panel.retranslate_ui()

    def _render_snapshot(self) -> None:
        if self._bundle is None or self._bundle_dir is None:
            self._clear_snapshot()
            return
        selected_team = None if self._selected is None else self._selected[0]
        selected_slot = None if self._selected is None else self._selected[1]
        model = build_history_snapshot_right_panel_view_model(
            self._bundle,
            bundle_dir=self._bundle_dir,
            selected_team_index=selected_team,
            selected_slot_index=selected_slot,
        )
        if self.run_panel is None:
            self.run_panel = RunRightPanelWidget(
                model,
                show_mode_tabs=False,
                show_run_actions=False,
                read_only=True,
            )
            self.run_panel.slot_selected.connect(self._on_slot_selected)
            self.layout().addWidget(self.run_panel, 1)
        else:
            self.run_panel.set_model(model)
        self.empty_label.setVisible(False)
        self.run_panel.setVisible(True)

    def _on_slot_selected(self, team_index: int, slot_index: int) -> None:
        if self._bundle is None:
            return
        selected = (int(team_index), int(slot_index))
        model = build_history_snapshot_right_panel_view_model(
            self._bundle,
            bundle_dir=self._bundle_dir or Path(),
            selected_team_index=selected[0],
            selected_slot_index=selected[1],
        )
        actual = (
            model.selected_details.team_index,
            model.selected_details.slot_index,
        )
        if actual[0] is None or actual[1] is None:
            return
        self._selected = int(actual[0]), int(actual[1])
        if self.run_panel is not None:
            self.run_panel.set_model(model)

    def _clear_snapshot(self) -> None:
        self._bundle = None
        self._bundle_dir = None
        self._selected = None
        self.empty_label.setVisible(True)
        if self.run_panel is not None:
            self.run_panel.setVisible(False)


__all__ = ["HistoryRightPanelHost"]
