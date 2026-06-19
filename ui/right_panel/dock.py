from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from run_workspace.right_panel_prototype_view_model import MODE_ABYSS
from run_workspace.history_browser_catalog import HISTORY_MODE_ABYSS
from ui.pvp_browser.placeholders import PvpRightDockPlaceholder
from ui.right_panel.constants import (
    RIGHT_DOCK_PAGE_ACCOUNT,
    RIGHT_DOCK_PAGE_HISTORY,
    RIGHT_DOCK_PAGE_PVP,
    RIGHT_DOCK_PAGE_RUN,
    RIGHT_DOCK_POLICY_HISTORY,
    RIGHT_DOCK_POLICY_PVP,
    RIGHT_DOCK_POLICY_RUN,
    RIGHT_OPERATIONS_DOCK_WIDTH,
)
from ui.right_panel.header import RightDockHeader
from ui.right_panel.history.viewer import HistoryRightPanelHost
from ui.right_panel.live_run.panel import right_panel_stylesheet
from ui.right_panel.pvp._shared import PVP_PAGE_DECKS, PVP_PAGE_DRAFT, PVP_PAGE_PLAY
from ui.right_panel.settings.account_data import AccountDataPage


class RightOperationsDock(QFrame):
    mode_requested = Signal(str)
    history_mode_requested = Signal(str)
    reset_requested = Signal()
    save_requested = Signal()

    def __init__(
        self,
        operation_widget: QWidget,
        parent: QWidget | None = None,
        *,
        history_operation_widget: QWidget | None = None,
        pvp_operation_widget: QWidget | None = None,
        active_mode: str = MODE_ABYSS,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("RightOperationsDock")
        self.operation_widget = operation_widget
        self.history_operation_widget = (
            history_operation_widget or HistoryRightPanelHost()
        )
        self.pvp_operation_widget = pvp_operation_widget or PvpRightDockPlaceholder()
        self._operation_policy = RIGHT_DOCK_POLICY_RUN
        self._pvp_page = PVP_PAGE_DECKS
        self._history_mode = HISTORY_MODE_ABYSS
        self.header = RightDockHeader(active_mode)
        self.account_page = AccountDataPage()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.operation_widget)
        self.content_stack.addWidget(self.history_operation_widget)
        self.content_stack.addWidget(self.pvp_operation_widget)
        self.content_stack.addWidget(self.account_page)
        layout.addWidget(self.content_stack, 1)

        operation_widget.setMinimumWidth(RIGHT_OPERATIONS_DOCK_WIDTH)
        self.history_operation_widget.setMinimumWidth(RIGHT_OPERATIONS_DOCK_WIDTH)
        self.pvp_operation_widget.setMinimumWidth(RIGHT_OPERATIONS_DOCK_WIDTH)
        self.setFixedWidth(RIGHT_OPERATIONS_DOCK_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(right_panel_stylesheet())

        self.header.mode_requested.connect(self._on_mode_requested)
        self.header.history_mode_requested.connect(
            self.history_mode_requested.emit
        )
        if hasattr(self.operation_widget, "reset_requested"):
            self.operation_widget.reset_requested.connect(self.reset_requested.emit)
        if hasattr(self.operation_widget, "save_requested"):
            self.operation_widget.save_requested.connect(self.save_requested.emit)
        self.header.pvp_control_requested.connect(
            lambda: self.show_pvp_page(PVP_PAGE_DECKS)
        )
        self.header.pvp_page_requested.connect(self.show_pvp_page)
        self.header.account_requested.connect(self.show_account_page)
        self.account_page.pvp_player_colors_changed.connect(
            self._on_pvp_player_colors_changed
        )
        pvp_workspace = getattr(self.pvp_operation_widget, "workspace", None)
        if pvp_workspace is not None and hasattr(pvp_workspace, "page_changed"):
            pvp_workspace.page_changed.connect(self._on_pvp_page_changed)
        self.show_run_page(active_mode)

    def current_page(self) -> str:
        if self.content_stack.currentWidget() is self.account_page:
            return RIGHT_DOCK_PAGE_ACCOUNT
        if self.content_stack.currentWidget() is self.history_operation_widget:
            return RIGHT_DOCK_PAGE_HISTORY
        if self.content_stack.currentWidget() is self.pvp_operation_widget:
            return RIGHT_DOCK_PAGE_PVP
        return RIGHT_DOCK_PAGE_RUN

    def show_run_page(self, mode: str) -> None:
        self._operation_policy = RIGHT_DOCK_POLICY_RUN
        self._clear_operation_save_status()
        self.content_stack.setCurrentWidget(self.operation_widget)
        self.header.show_run_mode(mode)

    def show_pvp_page(self, page_id: str | None = None) -> None:
        self._clear_operation_save_status()
        if page_id in (PVP_PAGE_DECKS, PVP_PAGE_PLAY, PVP_PAGE_DRAFT):
            self._pvp_page = page_id
        elif hasattr(self.pvp_operation_widget, "current_page"):
            self._pvp_page = self.pvp_operation_widget.current_page()
        self._operation_policy = RIGHT_DOCK_POLICY_PVP
        if hasattr(self.pvp_operation_widget, "set_page"):
            self.pvp_operation_widget.set_page(self._pvp_page)
        self.content_stack.setCurrentWidget(self.pvp_operation_widget)
        self.header.show_pvp_control(self._pvp_page)

    def show_history_page(self, mode: str | None = None) -> None:
        self._clear_operation_save_status()
        if mode is not None:
            self._history_mode = mode
        if hasattr(self.history_operation_widget, "set_history_mode"):
            self.history_operation_widget.set_history_mode(self._history_mode)
        self._operation_policy = RIGHT_DOCK_POLICY_HISTORY
        self.content_stack.setCurrentWidget(self.history_operation_widget)
        self.header.show_history_viewer(self._history_mode)

    def show_account_page(self) -> None:
        self._clear_operation_save_status()
        self.content_stack.setCurrentWidget(self.account_page)
        self.header.show_account(policy=self._operation_policy)

    def _on_mode_requested(self, mode: str) -> None:
        self.mode_requested.emit(mode)

    def _clear_operation_save_status(self) -> None:
        if hasattr(self.operation_widget, "clear_save_status"):
            self.operation_widget.clear_save_status()

    def _on_pvp_page_changed(self, page_id: str) -> None:
        if page_id not in (PVP_PAGE_DECKS, PVP_PAGE_PLAY, PVP_PAGE_DRAFT):
            return
        self._pvp_page = page_id
        if self.current_page() == RIGHT_DOCK_PAGE_PVP:
            self.header.show_pvp_control(self._pvp_page)

    def _on_pvp_player_colors_changed(self, _player_1: str, _player_2: str) -> None:
        refresh = getattr(self.pvp_operation_widget, "refresh_player_colors", None)
        if callable(refresh):
            refresh()

    def retranslate_ui(self) -> None:
        self.header.retranslate_ui()
        if hasattr(self.operation_widget, "retranslate_ui"):
            self.operation_widget.retranslate_ui()
        self.account_page.retranslate_ui()
        if hasattr(self.history_operation_widget, "retranslate_ui"):
            self.history_operation_widget.retranslate_ui()
        if hasattr(self.pvp_operation_widget, "retranslate_ui"):
            self.pvp_operation_widget.retranslate_ui()


__all__ = ["RightOperationsDock"]
