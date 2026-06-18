"""History Browser workspace for immutable snapshot rows.

This module owns the first AppShell History left workspace reader/list. It does
not query live account/session/cache data while browsing saved snapshots; future
product rules live in `docs/handoff/HISTORY_BROWSER.md`.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from localization import tr
from run_workspace.history_snapshot import (
    HISTORY_RUN_TYPE_ABYSS,
    HISTORY_RUN_TYPE_DPS_DUMMY,
    HISTORY_UNKNOWN_ABYSS_PERIOD,
)
from run_workspace.history_snapshot_listing import (
    HistoryRunGroupSummary,
    HistoryRunSummary,
    HistorySnapshotSummaryListing,
    load_history_snapshot_details_payload,
    load_history_snapshot_summary_listing,
)
from ui.utils.ui_palette import (
    UI_BG_BUTTON_HOVER,
    UI_BG_BUTTON_CHECKED,
    UI_BORDER_DEFAULT,
    UI_BORDER_SELECTED,
)


HISTORY_BROWSER_STYLESHEET = f"""
QFrame#HistoryRunRow {{
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 6px;
}}
QFrame#HistoryRunRow:hover {{
    background: {UI_BG_BUTTON_HOVER};
}}
QFrame#HistoryRunRow[selected="true"] {{
    border-color: {UI_BORDER_SELECTED};
    background: {UI_BG_BUTTON_CHECKED};
}}
"""


class HistoryBrowserWorkspace(QFrame):
    """Minimal left-workspace reader for immutable History snapshots."""

    snapshot_selected = Signal(object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        snapshot_root: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("HistoryBrowserWorkspace")
        self.setStyleSheet(HISTORY_BROWSER_STYLESHEET)
        self.snapshot_root = Path(snapshot_root) if snapshot_root is not None else None
        self._listing = HistorySnapshotSummaryListing()
        self._selected_bundle_id = ""
        self._summaries_by_bundle_id: dict[str, HistoryRunSummary] = {}
        self._row_widgets_by_bundle_id: dict[str, "HistoryRunRowWidget"] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self.title_label = QLabel()
        self.title_label.setObjectName("SectionTitle")
        header.addWidget(self.title_label, 1)

        self.refresh_button = QPushButton()
        self.refresh_button.setObjectName("ActionButton")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button, 0)
        root.addLayout(header)

        self.empty_label = QLabel()
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty_label)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setObjectName("WarningLabel")
        root.addWidget(self.error_label)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)
        self.scroll_area.setWidget(self.content_widget)
        root.addWidget(self.scroll_area, 1)
        self.retranslate_ui()
        self.refresh()

    def set_snapshot_root(self, snapshot_root: str | Path) -> None:
        self.snapshot_root = Path(snapshot_root)

    def refresh(self) -> None:
        if self.snapshot_root is None:
            self._listing = HistorySnapshotSummaryListing()
        else:
            self._listing = load_history_snapshot_summary_listing(self.snapshot_root)
        available_ids = {
            summary.bundle_id
            for group in self._listing.groups
            for summary in group.runs
        }
        if self._selected_bundle_id not in available_ids:
            self._selected_bundle_id = ""
        self._render_listing()
        if self._selected_bundle_id:
            self._emit_selected_payload(self._selected_bundle_id)
        else:
            self.snapshot_selected.emit(None)

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.history.title"))
        self.refresh_button.setText(tr("app_shell.history.refresh"))
        self.empty_label.setText(tr("app_shell.history.empty"))
        self._render_listing()

    def selected_bundle_id(self) -> str:
        return self._selected_bundle_id

    def row_widget(self, bundle_id: str) -> "HistoryRunRowWidget | None":
        return self._row_widgets_by_bundle_id.get(bundle_id)

    def _render_listing(self) -> None:
        if not hasattr(self, "content_layout"):
            return
        _clear_layout(self.content_layout)
        self._summaries_by_bundle_id = {}
        self._row_widgets_by_bundle_id = {}
        has_runs = self._listing.run_count > 0
        self.empty_label.setVisible(not has_runs)
        self.scroll_area.setVisible(has_runs)
        if self._listing.errors:
            self.error_label.setVisible(True)
            self.error_label.setText(
                tr("app_shell.history.errors").format(
                    count=len(self._listing.errors)
                )
            )
        else:
            self.error_label.setVisible(False)
            self.error_label.clear()
        for group in self._listing.groups:
            self.content_layout.addWidget(self._group_widget(group))
        self.content_layout.addStretch(1)

    def _group_widget(self, group: HistoryRunGroupSummary) -> QWidget:
        frame = QFrame()
        frame.setObjectName("InfoBlock")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel(_group_title(group))
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        period_summary = group.abyss_period_summary
        if period_summary is not None:
            summary_label = QLabel(
                tr("app_shell.history.period.summary").format(
                    count=period_summary.saved_run_count
                )
            )
            summary_label.setWordWrap(True)
            summary_label.setObjectName("MutedLabel")
            layout.addWidget(summary_label)
            if period_summary.chamber_labels:
                chamber_label = QLabel(
                    tr("app_shell.history.period.chambers").format(
                        chambers=", ".join(period_summary.chamber_labels)
                    )
                )
                chamber_label.setWordWrap(True)
                chamber_label.setObjectName("MutedLabel")
                layout.addWidget(chamber_label)
            if period_summary.chamber_enemy_hp_summaries:
                enemy_label = QLabel(
                    tr("app_shell.history.period.enemy_hp").format(
                        summary=" | ".join(
                            period_summary.chamber_enemy_hp_summaries
                        )
                    )
                )
                enemy_label.setWordWrap(True)
                enemy_label.setObjectName("MutedLabel")
                layout.addWidget(enemy_label)

        for summary in group.runs:
            layout.addWidget(self._row_widget(summary))
        return frame

    def _row_widget(self, summary: HistoryRunSummary) -> QWidget:
        self._summaries_by_bundle_id[summary.bundle_id] = summary
        frame = HistoryRunRowWidget(
            summary,
            selected=summary.bundle_id == self._selected_bundle_id,
        )
        frame.clicked.connect(self._on_row_clicked)
        self._row_widgets_by_bundle_id[summary.bundle_id] = frame
        layout = frame.layout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        meta_label = QLabel(
            " | ".join(
                item
                for item in (
                    summary.created_at,
                    _run_type_label(summary.run_type),
                    summary.bundle_id,
                )
                if item
            )
        )
        meta_label.setObjectName("MutedLabel")
        meta_label.setWordWrap(True)
        layout.addWidget(meta_label)

        team_label = QLabel(summary.team_summary or "-")
        team_label.setWordWrap(True)
        layout.addWidget(team_label)

        chamber_text = " | ".join(summary.chamber_summaries)
        if chamber_text:
            chamber_label = QLabel(chamber_text)
            chamber_label.setWordWrap(True)
            layout.addWidget(chamber_label)

        if summary.warnings_count:
            warnings_label = QLabel(
                tr("app_shell.history.row.warnings").format(
                    count=summary.warnings_count
                )
            )
            warnings_label.setObjectName("WarningLabel")
            layout.addWidget(warnings_label)
        return frame

    def _on_row_clicked(self, bundle_id: str) -> None:
        if bundle_id not in self._summaries_by_bundle_id:
            return
        self._selected_bundle_id = bundle_id
        self._render_listing()
        self._emit_selected_payload(bundle_id)

    def _emit_selected_payload(self, bundle_id: str) -> None:
        if self.snapshot_root is None:
            self.snapshot_selected.emit(None)
            return
        summary = self._summaries_by_bundle_id.get(bundle_id)
        payload = load_history_snapshot_details_payload(
            self.snapshot_root,
            bundle_id,
            bundle_path=None if summary is None else summary.bundle_path,
        )
        self.snapshot_selected.emit(payload)


class HistoryRunRowWidget(QFrame):
    clicked = Signal(str)

    def __init__(
        self,
        summary: HistoryRunSummary,
        parent: QWidget | None = None,
        *,
        selected: bool = False,
    ) -> None:
        super().__init__(parent)
        self.summary = summary
        self.setObjectName("HistoryRunRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", bool(selected))
        self._layout = QVBoxLayout(self)

    def layout(self) -> QVBoxLayout:
        return self._layout

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", bool(selected))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def click(self) -> None:
        self.clicked.emit(self.summary.bundle_id)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.click()
            event.accept()
            return
        super().mousePressEvent(event)


def _group_title(group: HistoryRunGroupSummary) -> str:
    if group.run_type == HISTORY_RUN_TYPE_ABYSS:
        section = tr("app_shell.history.section.abyss")
        label = group.group_label
        if group.group_key == HISTORY_UNKNOWN_ABYSS_PERIOD:
            label = tr("app_shell.history.period.unknown")
        return f"{section} | {label}"
    return tr("app_shell.history.section.dps_dummy")


def _run_type_label(run_type: str) -> str:
    if run_type == HISTORY_RUN_TYPE_ABYSS:
        return tr("app_shell.history.run_type.abyss")
    if run_type == HISTORY_RUN_TYPE_DPS_DUMMY:
        return tr("app_shell.history.run_type.dps_dummy")
    return run_type


def _clear_layout(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
