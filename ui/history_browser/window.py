"""AppShell History Browser for immutable run snapshots."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from localization import tr
from run_workspace.history_browser_catalog import (
    HISTORY_MODE_ABYSS,
    HISTORY_MODE_DPS_DUMMY,
    HISTORY_MODE_PVP,
    HISTORY_MODES,
    HistoryBrowserCatalog,
    HistoryEnemyVisual,
    HistoryPeriodVisual,
    HistoryRunVisual,
    HistorySideVisual,
    load_history_browser_catalog,
)
from run_workspace.history_snapshot_listing import load_history_snapshot_details_payload
from ui.right_panel.common.metrics import _fit_pixmap
from ui.right_panel.common.run_summary import CompactRunSummaryWidget
from ui.utils.ui_palette import (
    UI_BG_BUTTON_CHECKED,
    UI_BG_BUTTON_HOVER,
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
QFrame#HistoryPeriodPreview, QFrame#HistoryEnemyChamber,
QFrame#HistoryEnemySide, QFrame#CompactRunSlot,
QFrame#CompactChamberSummary {{
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 4px;
}}
QLabel#CompactRunSetLabel {{ font-size: 7px; }}
QLabel#CompactRunMetric {{ font-size: 10px; }}
QLabel#CompactRunTitle {{ font-weight: 600; }}
QLabel#HistorySideHp {{ font-size: 10px; font-weight: 600; }}
"""


class HistoryBrowserWorkspace(QFrame):
    """Left History workspace with local modes and automatic reload."""

    snapshot_selected = Signal(object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        snapshot_root: str | Path | None = None,
        abyss_cache_dir: str | Path | None = None,
        current_period_path: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("HistoryBrowserWorkspace")
        self.setStyleSheet(HISTORY_BROWSER_STYLESHEET)
        self.snapshot_root = Path(snapshot_root) if snapshot_root is not None else None
        self.abyss_cache_dir = (
            Path(abyss_cache_dir) if abyss_cache_dir is not None else None
        )
        self.current_period_path = (
            Path(current_period_path) if current_period_path is not None else None
        )
        self._mode = HISTORY_MODE_ABYSS
        self._catalog = HistoryBrowserCatalog()
        self._selected_period_start = ""
        self._selected_bundle_id = ""
        self._runs_by_bundle_id: dict[str, HistoryRunVisual] = {}
        self._row_widgets_by_bundle_id: dict[str, HistoryRunRowWidget] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        self.error_label = QLabel()
        self.error_label.setObjectName("WarningLabel")
        self.error_label.setWordWrap(True)
        root.addWidget(self.error_label)

        self.empty_label = QLabel()
        self.empty_label.setObjectName("MutedLabel")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty_label, 1)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)
        self.scroll_area.setWidget(self.content_widget)
        root.addWidget(self.scroll_area, 1)
        self.reload_data()

    @property
    def mode(self) -> str:
        return self._mode

    def set_snapshot_root(self, snapshot_root: str | Path) -> None:
        self.snapshot_root = Path(snapshot_root)

    def set_mode(self, mode: str) -> None:
        normalized = mode if mode in HISTORY_MODES else HISTORY_MODE_ABYSS
        if normalized == self._mode:
            return
        self._mode = normalized
        self._clear_selection()
        self._render()

    def reload_data(self) -> None:
        if self.snapshot_root is None:
            self._catalog = HistoryBrowserCatalog()
        else:
            self._catalog = load_history_browser_catalog(
                self.snapshot_root,
                abyss_cache_dir=self.abyss_cache_dir,
                current_period_path=self.current_period_path,
            )
        available_periods = {
            period.period_start for period in self._catalog.periods
        }
        if self._selected_period_start not in available_periods:
            preferred = self._catalog.current_period_start
            self._selected_period_start = (
                preferred
                if preferred in available_periods
                else (
                    self._catalog.periods[0].period_start
                    if self._catalog.periods
                    else ""
                )
            )
        available_ids = {
            run.bundle_id
            for period in self._catalog.periods
            for run in period.runs
        } | {run.bundle_id for run in self._catalog.dps_dummy_runs}
        if self._selected_bundle_id not in available_ids:
            self._selected_bundle_id = ""
        self._render()
        if not self._selected_bundle_id:
            self.snapshot_selected.emit(None)

    def retranslate_ui(self) -> None:
        self._render()

    def selected_bundle_id(self) -> str:
        return self._selected_bundle_id

    def selected_period_start(self) -> str:
        return self._selected_period_start

    def row_widget(self, bundle_id: str) -> "HistoryRunRowWidget | None":
        return self._row_widgets_by_bundle_id.get(bundle_id)

    def _render(self) -> None:
        if not hasattr(self, "content_layout"):
            return
        _clear_layout(self.content_layout)
        self._runs_by_bundle_id = {}
        self._row_widgets_by_bundle_id = {}
        if self._catalog.errors:
            self.error_label.setText(
                tr("app_shell.history.errors").format(count=len(self._catalog.errors))
            )
            self.error_label.show()
        else:
            self.error_label.clear()
            self.error_label.hide()

        if self._mode == HISTORY_MODE_PVP:
            self.scroll_area.hide()
            self.empty_label.setText(tr("app_shell.history.pvp.placeholder"))
            self.empty_label.show()
            return
        self.scroll_area.show()
        self.empty_label.hide()
        if self._mode == HISTORY_MODE_ABYSS:
            self._render_abyss()
        else:
            self._render_runs(self._catalog.dps_dummy_runs)
            if not self._catalog.dps_dummy_runs:
                self.scroll_area.hide()
                self.empty_label.setText(tr("app_shell.history.empty.dps_dummy"))
                self.empty_label.show()
        self.content_layout.addStretch(1)

    def _render_abyss(self) -> None:
        period = self._selected_period()
        if period is None:
            self.scroll_area.hide()
            self.empty_label.setText(tr("app_shell.history.empty.abyss"))
            self.empty_label.show()
            return
        self.content_layout.addWidget(AbyssPeriodPreviewWidget(period))
        selector = QToolButton()
        selector.setObjectName("ActionButton")
        selector.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        selector.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        selector.setArrowType(Qt.ArrowType.DownArrow)
        selector.setText(_period_label(period))
        selector.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        menu = QMenu(selector)
        for option in self._catalog.periods:
            action = menu.addAction(_period_label(option))
            action.setCheckable(True)
            action.setChecked(option.period_start == period.period_start)
            action.triggered.connect(
                lambda _checked=False, value=option.period_start: self._select_period(
                    value
                )
            )
        selector.setMenu(menu)
        self.content_layout.addWidget(selector)
        self._render_runs(period.runs)
        if not period.runs:
            empty = QLabel(tr("app_shell.history.period.no_runs"))
            empty.setObjectName("MutedLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setContentsMargins(0, 16, 0, 16)
            self.content_layout.addWidget(empty)

    def _render_runs(self, runs: tuple[HistoryRunVisual, ...]) -> None:
        for run in runs:
            self._runs_by_bundle_id[run.bundle_id] = run
            row = HistoryRunRowWidget(
                run,
                selected=run.bundle_id == self._selected_bundle_id,
            )
            row.clicked.connect(self._on_row_clicked)
            self._row_widgets_by_bundle_id[run.bundle_id] = row
            self.content_layout.addWidget(row)

    def _selected_period(self) -> HistoryPeriodVisual | None:
        return next(
            (
                period
                for period in self._catalog.periods
                if period.period_start == self._selected_period_start
            ),
            None,
        )

    def _select_period(self, period_start: str) -> None:
        if period_start == self._selected_period_start:
            return
        self._selected_period_start = period_start
        self._clear_selection()
        self._render()

    def _clear_selection(self) -> None:
        self._selected_bundle_id = ""
        self.snapshot_selected.emit(None)

    def _on_row_clicked(self, bundle_id: str) -> None:
        run = self._runs_by_bundle_id.get(bundle_id)
        if run is None or self.snapshot_root is None:
            return
        self._selected_bundle_id = bundle_id
        for row_id, row in self._row_widgets_by_bundle_id.items():
            row.set_selected(row_id == bundle_id)
        payload = load_history_snapshot_details_payload(
            self.snapshot_root,
            bundle_id,
            bundle_path=run.bundle_path,
        )
        self.snapshot_selected.emit(payload)


class AbyssPeriodPreviewWidget(QFrame):
    def __init__(
        self,
        period: HistoryPeriodVisual,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("HistoryPeriodPreview")
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        sides = {(item.chamber, item.side): item for item in period.sides}
        for chamber in (1, 2, 3):
            frame = QFrame()
            frame.setObjectName("HistoryEnemyChamber")
            column = QVBoxLayout(frame)
            column.setContentsMargins(4, 3, 4, 3)
            column.setSpacing(3)
            title = QLabel(f"C{chamber}")
            title.setObjectName("CompactRunTitle")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            column.addWidget(title)
            for side in (1, 2):
                column.addWidget(
                    EnemySidePreviewWidget(
                        sides.get(
                            (chamber, side),
                            HistorySideVisual(chamber=chamber, side=side),
                        )
                    )
                )
            root.addWidget(frame, 1)


class EnemySidePreviewWidget(QFrame):
    def __init__(
        self,
        side: HistorySideVisual,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("HistoryEnemySide")
        root = QHBoxLayout(self)
        root.setContentsMargins(3, 2, 3, 2)
        root.setSpacing(2)
        side_label = QLabel(f"S{side.side}")
        side_label.setObjectName("MutedLabel")
        side_label.setFixedWidth(15)
        root.addWidget(side_label)
        for enemy in side.enemies[:4]:
            root.addWidget(_enemy_icon(enemy))
        if len(side.enemies) > 4:
            extra = QLabel(f"+{len(side.enemies) - 4}")
            extra.setObjectName("MutedLabel")
            root.addWidget(extra)
        root.addStretch(1)
        hp = QLabel(_compact_hp(side.total_hp))
        hp.setObjectName("HistorySideHp")
        hp.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(hp)


class HistoryRunRowWidget(QFrame):
    clicked = Signal(str)

    def __init__(
        self,
        run: HistoryRunVisual,
        parent: QWidget | None = None,
        *,
        selected: bool = False,
    ) -> None:
        super().__init__(parent)
        self.run = run
        self.setObjectName("HistoryRunRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", bool(selected))
        self.setMinimumHeight(130 if run.run_type == HISTORY_MODE_ABYSS else 76)
        self.setMaximumHeight(150 if run.run_type == HISTORY_MODE_ABYSS else 96)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(CompactRunSummaryWidget(run))

    @property
    def summary(self) -> HistoryRunVisual:
        return self.run

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", bool(selected))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def click(self) -> None:
        self.clicked.emit(self.run.bundle_id)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.click()
            event.accept()
            return
        super().mousePressEvent(event)


def _enemy_icon(enemy: HistoryEnemyVisual) -> QLabel:
    size = 28
    label = QLabel()
    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pixmap = _fit_pixmap(enemy.icon_path, QSize(size, size))
    if pixmap is not None:
        label.setPixmap(pixmap)
    else:
        label.setText((enemy.name or "?")[:1].upper())
    hp = "-" if enemy.hp is None else _compact_hp(enemy.hp)
    level = "-" if enemy.level is None else str(enemy.level)
    label.setToolTip(
        tr("app_shell.history.enemy.tooltip").format(
            name=enemy.name or "-",
            level=level,
            count=enemy.count,
            wave=enemy.wave,
            hp=hp,
        )
    )
    return label


def _period_label(period: HistoryPeriodVisual) -> str:
    start = (
        tr("app_shell.history.period.unknown")
        if period.period_start == "unknown_period"
        else period.period_start
    )
    end = _valid_period_end(period.period_start, period.period_end)
    dates = start if not end else f"{start} - {end}"
    floor = "-" if period.floor is None else f"F{period.floor}"
    return tr("app_shell.history.period.option").format(
        dates=dates,
        floor=floor,
        count=len(period.runs),
    )


def _valid_period_end(start: str, end: str) -> str:
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except ValueError:
        return ""
    return end if (end_date - start_date).days >= 7 else ""


def _compact_hp(value: int | None) -> str:
    if value is None:
        return "-"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}m".replace(".0m", "m")
    if value >= 1_000:
        return f"{value / 1_000:.0f}k"
    return str(value)


def _clear_layout(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        child = item.layout()
        if child is not None:
            _clear_layout(child)


__all__ = ["HistoryBrowserWorkspace", "HistoryRunRowWidget"]
