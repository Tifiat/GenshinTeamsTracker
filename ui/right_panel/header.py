from __future__ import annotations

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QWidget

from localization import tr
from run_workspace.history_browser_catalog import (
    HISTORY_MODE_ABYSS,
    HISTORY_MODE_DPS_DUMMY,
    HISTORY_MODE_PVP,
)
from run_workspace.right_panel_prototype_view_model import MODE_ABYSS
from ui.right_panel.pvp._shared import PVP_PAGE_DECKS, PVP_PAGE_DRAFT, PVP_PAGE_PLAY
from ui.right_panel.constants import (
    RIGHT_DOCK_ACCOUNT_ICON_SIZE,
    RIGHT_DOCK_POLICY_HISTORY,
    RIGHT_DOCK_POLICY_PVP,
    RIGHT_DOCK_POLICY_RUN,
)
from ui.right_panel.live_run.panel import RunModeTabsWidget, make_mode_tab_button
from ui.utils.icon_utils import tinted_svg_pixmap
from ui.utils.ui_palette import UI_BG_APP, UI_TEXT_SECONDARY


class RightDockHeader(QWidget):
    mode_requested = Signal(str)
    history_mode_requested = Signal(str)
    account_requested = Signal()
    pvp_control_requested = Signal()
    pvp_page_requested = Signal(str)

    def __init__(
        self,
        active_mode: str = MODE_ABYSS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("RightDockHeader")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 0)
        layout.setSpacing(6)

        self.run_mode_tabs = RunModeTabsWidget(active_mode)
        self.run_mode_tabs.mode_requested.connect(self.mode_requested.emit)
        layout.addWidget(self.run_mode_tabs, 2)

        self.history_mode_tabs = HistoryModeTabsWidget(active_mode)
        self.history_mode_tabs.mode_requested.connect(
            self.history_mode_requested.emit
        )
        layout.addWidget(self.history_mode_tabs, 3)

        self.pvp_decks_button = make_mode_tab_button(
            tr("app_shell.right_dock.pvp_decks")
        )
        self.pvp_decks_button.clicked.connect(
            lambda _checked=False: self._request_pvp_page(PVP_PAGE_DECKS)
        )
        layout.addWidget(self.pvp_decks_button, 1)

        self.pvp_play_button = make_mode_tab_button(
            tr("app_shell.right_dock.pvp_play")
        )
        self.pvp_play_button.clicked.connect(
            lambda _checked=False: self._request_pvp_page(PVP_PAGE_PLAY)
        )
        layout.addWidget(self.pvp_play_button, 1)

        self.pvp_draft_button = make_mode_tab_button(
            tr("app_shell.right_dock.pvp_draft")
        )
        self.pvp_draft_button.clicked.connect(
            lambda _checked=False: self._request_pvp_page(PVP_PAGE_DRAFT)
        )
        layout.addWidget(self.pvp_draft_button, 1)
        self.pvp_control_button = self.pvp_decks_button
        self._pvp_buttons_by_page = {
            PVP_PAGE_DECKS: self.pvp_decks_button,
            PVP_PAGE_PLAY: self.pvp_play_button,
            PVP_PAGE_DRAFT: self.pvp_draft_button,
        }

        self.account_button = make_mode_tab_button(
            tr("app_shell.right_dock.account")
        )
        self.account_button.setIcon(_account_tab_icon())
        self.account_button.setIconSize(
            QSize(RIGHT_DOCK_ACCOUNT_ICON_SIZE, RIGHT_DOCK_ACCOUNT_ICON_SIZE)
        )
        self.account_button.clicked.connect(
            lambda _checked=False: self.account_requested.emit()
        )
        layout.addWidget(self.account_button, 1)
        self.show_run_mode(active_mode)

    def show_run_mode(self, mode: str) -> None:
        self.run_mode_tabs.setVisible(True)
        self.history_mode_tabs.setVisible(False)
        self._show_pvp_buttons(False)
        self.account_button.setChecked(False)
        self.run_mode_tabs.set_active_mode(mode)

    def show_pvp_control(self, active_page: str = PVP_PAGE_DECKS) -> None:
        self.run_mode_tabs.setVisible(False)
        self.history_mode_tabs.setVisible(False)
        self.run_mode_tabs.set_active_mode(None)
        self._show_pvp_buttons(True, active_page=active_page)
        self.account_button.setChecked(False)

    def show_history_viewer(self, mode: str = HISTORY_MODE_ABYSS) -> None:
        self.run_mode_tabs.setVisible(False)
        self.run_mode_tabs.set_active_mode(None)
        self.history_mode_tabs.setVisible(True)
        self.history_mode_tabs.set_active_mode(mode)
        self._show_pvp_buttons(False)
        self.account_button.setChecked(False)

    def show_account(self, *, policy: str = RIGHT_DOCK_POLICY_RUN) -> None:
        if policy == RIGHT_DOCK_POLICY_PVP:
            self.run_mode_tabs.setVisible(False)
            self.history_mode_tabs.setVisible(False)
            self.run_mode_tabs.set_active_mode(None)
            self._show_pvp_buttons(True, active_page=None)
        elif policy == RIGHT_DOCK_POLICY_HISTORY:
            self.run_mode_tabs.setVisible(False)
            self.run_mode_tabs.set_active_mode(None)
            self.history_mode_tabs.setVisible(True)
            self.history_mode_tabs.set_active_mode(None)
            self._show_pvp_buttons(False)
        else:
            self.run_mode_tabs.setVisible(True)
            self.history_mode_tabs.setVisible(False)
            self.run_mode_tabs.set_active_mode(None)
            self._show_pvp_buttons(False)
        self.account_button.setChecked(True)

    def retranslate_ui(self) -> None:
        self.run_mode_tabs.retranslate_ui()
        self.history_mode_tabs.retranslate_ui()
        self.pvp_decks_button.setText(tr("app_shell.right_dock.pvp_decks"))
        self.pvp_play_button.setText(tr("app_shell.right_dock.pvp_play"))
        self.pvp_draft_button.setText(tr("app_shell.right_dock.pvp_draft"))
        self.account_button.setText(tr("app_shell.right_dock.account"))

    def _request_pvp_page(self, page_id: str) -> None:
        self.pvp_page_requested.emit(page_id)

    def _show_pvp_buttons(
        self,
        visible: bool,
        *,
        active_page: str | None = PVP_PAGE_DECKS,
    ) -> None:
        for page_id, button in self._pvp_buttons_by_page.items():
            button.setVisible(visible)
            button.setChecked(bool(visible and active_page == page_id))


class HistoryModeTabsWidget(QWidget):
    mode_requested = Signal(str)

    def __init__(
        self,
        active_mode: str = HISTORY_MODE_ABYSS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.buttons = {}
        for mode in (
            HISTORY_MODE_ABYSS,
            HISTORY_MODE_DPS_DUMMY,
            HISTORY_MODE_PVP,
        ):
            button = make_mode_tab_button("")
            button.clicked.connect(
                lambda _checked=False, value=mode: self.mode_requested.emit(value)
            )
            self.buttons[mode] = button
            layout.addWidget(button, 1)
        self.retranslate_ui()
        self.set_active_mode(active_mode)

    def set_active_mode(self, mode: str | None) -> None:
        for value, button in self.buttons.items():
            button.setChecked(value == mode)

    def retranslate_ui(self) -> None:
        self.buttons[HISTORY_MODE_ABYSS].setText(
            tr("app_shell.history.mode.abyss")
        )
        self.buttons[HISTORY_MODE_DPS_DUMMY].setText(
            tr("app_shell.history.mode.dps_dummy")
        )
        self.buttons[HISTORY_MODE_PVP].setText(tr("app_shell.history.mode.pvp"))


def _account_tab_icon() -> QIcon:
    icon = QIcon()
    size = RIGHT_DOCK_ACCOUNT_ICON_SIZE
    icon.addPixmap(
        tinted_svg_pixmap("user-round-cog", size, UI_TEXT_SECONDARY),
        QIcon.Mode.Normal,
        QIcon.State.Off,
    )
    icon.addPixmap(
        tinted_svg_pixmap("user-round-cog", size, UI_BG_APP),
        QIcon.Mode.Normal,
        QIcon.State.On,
    )
    return icon


__all__ = ["HistoryModeTabsWidget", "RightDockHeader"]
