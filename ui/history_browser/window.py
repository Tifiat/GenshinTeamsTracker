"""AppShell History Browser for immutable run snapshots."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt, Signal
from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import (
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QToolButton,
    QPushButton,
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
from run_workspace.history_artwork import HistoryArtworkStore
from ui.right_panel.common.history_card import HistoryCardWidget, render_history_card_png
from ui.utils.overlay_scroll import OverlayVerticalScrollArea
from ui.utils.tooltips import install_custom_tooltip
from ui.utils.ui_palette import (
    UI_BG_BUTTON_CHECKED,
    UI_BG_BUTTON_HOVER,
    UI_BORDER_DEFAULT,
    UI_BORDER_SELECTED,
    UI_HISTORY_BG_TOP,
    UI_HISTORY_BG_BOTTOM,
    UI_HISTORY_BORDER,
    UI_HISTORY_TEXT,
    UI_HISTORY_MUTED,
    UI_HISTORY_TEAM_1,
)


HISTORY_BROWSER_STYLESHEET = f"""
QFrame#HistoryRunRow {{
    border: none;
    border-radius: 10px;
    background: {UI_HISTORY_BG_BOTTOM};
}}
QFrame#HistoryRunRow:hover {{
    background: {UI_HISTORY_BG_BOTTOM};
}}
QFrame#HistoryRunRow[selected="true"] {{
    background: {UI_HISTORY_BG_BOTTOM};
}}
QFrame#HistoryPeriodPreview {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {UI_HISTORY_BG_TOP}, stop:1 {UI_HISTORY_BG_BOTTOM});
    border: 1px solid {UI_HISTORY_BORDER};
    border-radius: 8px;
}}
QFrame#HistoryEnemyChamber, QFrame#HistoryEnemySide {{ border: none; background: transparent; }}
QLabel#CompactRunTitle {{ font-weight: 600; color: {UI_HISTORY_TEXT}; }}
QLabel#HistorySideHp {{ font-size: 12px; font-weight: 600; color: {UI_HISTORY_MUTED}; }}
QPushButton#HistoryExportButton {{
    background: {UI_HISTORY_BG_TOP}; color: {UI_HISTORY_TEXT};
    border: 1px solid {UI_HISTORY_BORDER}; border-radius: 5px;
    padding: 5px 14px; font-size: 12px; font-weight: 600;
}}
QPushButton#HistoryExportButton:hover {{ border-color: {UI_HISTORY_TEAM_1}; }}
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
        self._expanded_bundle_id = ""
        self._character_view = "profile"
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

        self.scroll_area = OverlayVerticalScrollArea()
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
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._hide_card_tooltips)
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
        previous_catalog = self._catalog
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
            self._expanded_bundle_id = ""
        if self._catalog == previous_catalog and self.content_layout.count():
            return
        self._render()
        if not self._selected_bundle_id:
            self.snapshot_selected.emit(None)

    def retranslate_ui(self) -> None:
        self._render()

    def selected_bundle_id(self) -> str:
        return self._selected_bundle_id

    def _hide_card_tooltips(self, _value: int = 0) -> None:
        for row in self._row_widgets_by_bundle_id.values():
            row.card.dismiss_tooltip()

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
        for index, run in enumerate(runs):
            self._runs_by_bundle_id[run.bundle_id] = run
            row = HistoryRunRowWidget(
                run,
                selected=run.bundle_id == self._selected_bundle_id,
                character_view=self._character_view,
                alternate=bool(index % 2),
            )
            row.set_expanded(run.bundle_id == self._expanded_bundle_id)
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
        self._expanded_bundle_id = ""
        self.snapshot_selected.emit(None)

    def _on_row_clicked(self, bundle_id: str) -> None:
        run = self._runs_by_bundle_id.get(bundle_id)
        if run is None or self.snapshot_root is None:
            return
        self._selected_bundle_id = bundle_id
        self._expanded_bundle_id = "" if self._expanded_bundle_id == bundle_id else bundle_id
        for row_id, row in self._row_widgets_by_bundle_id.items():
            row.set_selected(row_id == bundle_id)
            row.set_expanded(row_id == self._expanded_bundle_id)
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
        character_view: str = "profile",
        alternate: bool = False,
    ) -> None:
        super().__init__(parent)
        self.run = run
        self.setObjectName("HistoryRunRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", bool(selected))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.artwork_store = HistoryArtworkStore()
        self.card = HistoryCardWidget(run, self, character_view=character_view, alternate=alternate,
                                      artwork_paths=self.artwork_store.paths(run))
        self.card.clicked.connect(self.click)
        self.card.artwork_requested.connect(self._choose_artwork)
        self.card.artwork_reset_requested.connect(self._reset_artwork)
        layout.addWidget(self.card)
        self.export_bar = QWidget(self)
        bar = QHBoxLayout(self.export_bar)
        bar.setContentsMargins(12, 4, 12, 8)
        self.export_status = QLabel()
        self.export_status.setWordWrap(True)
        bar.addWidget(self.export_status, 1)
        # Keyboard-accessible counterpart of the artwork hover actions.
        self.artwork_button = QToolButton(self)
        self.artwork_button.setText(tr("history.card.artwork.menu"))
        self.artwork_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.artwork_button)
        for team in run.teams:
            submenu = menu.addMenu(tr("history.card.team").format(value=team.team_index+1))
            submenu.addAction(tr("history.card.artwork.change"),
                              lambda checked=False, i=team.team_index: self._choose_artwork(i))
            submenu.addAction(tr("history.card.artwork.reset"),
                              lambda checked=False, i=team.team_index: self._reset_artwork(i))
        self.artwork_button.setMenu(menu)
        bar.addWidget(self.artwork_button)
        self.export_button = QPushButton(tr("history.card.export"))
        self.export_button.setObjectName("HistoryExportButton")
        self.export_button.clicked.connect(self._export_png)
        bar.addWidget(self.export_button)
        layout.addWidget(self.export_bar)
        self.export_bar.hide()

    def set_expanded(self, expanded: bool) -> None:
        self.card.set_expanded(expanded)
        self.export_bar.setVisible(expanded)

    def _export_png(self) -> None:
        self.card.dismiss_tooltip()
        filename, _ = QFileDialog.getSaveFileName(self, tr("history.card.export"),
            f"{self.run.bundle_id}.png", tr("history.card.png_filter"))
        if not filename:
            return
        if not filename.lower().endswith(".png"):
            filename += ".png"
        try:
            render_history_card_png(self.run, filename, character_view=self.card.character_view,
                                    artwork_paths=self.card.artwork_paths)
        except OSError as exc:
            self.export_status.setText(tr("history.card.export_error").format(error=exc))
        else:
            self.export_status.setText(tr("history.card.export_saved").format(path=filename))

    def _choose_artwork(self, team_index: int) -> None:
        self.card.dismiss_tooltip()
        filename, _ = QFileDialog.getOpenFileName(self, tr("history.card.artwork.change"), "",
                                                  tr("history.card.artwork.filter"))
        if not filename:
            return
        try:
            if Path(filename).stat().st_size > 32*1024*1024:
                raise ValueError("Image too large")
            reader = QImageReader(filename)
            reader.setAutoTransform(True)
            size = reader.size()
            if not size.isValid() or size.width()*size.height() > 24_000_000:
                raise ValueError("Invalid image dimensions")
            if max(size.width(), size.height()) > 1600:
                reader.setScaledSize(size.scaled(1600, 1600, Qt.AspectRatioMode.KeepAspectRatio))
            image = reader.read()
            if image.isNull():
                raise ValueError("Unreadable image")
            data = QByteArray()
            buffer = QBuffer(data)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            if not image.save(buffer, "PNG"):
                raise ValueError("Image conversion failed")
            buffer.close()
            self.artwork_store.save(self.run, team_index, bytes(data))
        except (OSError, ValueError):
            self.export_status.setText(tr("history.card.artwork.error"))
            return
        self.card.set_artwork_paths(self.artwork_store.paths(self.run))
        self.export_status.clear()

    def _reset_artwork(self, team_index: int) -> None:
        try:
            self.artwork_store.reset(self.run, team_index)
        except OSError:
            self.export_status.setText(tr("history.card.artwork.error"))
            return
        self.card.set_artwork_paths(self.artwork_store.paths(self.run))
        self.export_status.clear()

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
    install_custom_tooltip(label,
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
