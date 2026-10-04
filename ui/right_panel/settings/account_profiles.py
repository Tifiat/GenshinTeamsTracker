"""Saved-account selector. Storage changes are delegated to the app launcher."""
from __future__ import annotations

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget, QWidgetAction,
)

from localization import tr
from run_workspace.account_profiles import active_profile, list_profiles, profile_root
from ui.utils.tooltips import install_custom_tooltip


def profile_caption(profile: dict) -> str:
    metadata = profile.get("metadata") or {}
    name = metadata.get("nickname") or tr("accounts.unnamed")
    if not profile.get("imported"):
        return tr("accounts.new_draft")
    return tr("accounts.row", name=name, uid=metadata.get("uid", "—"),
              rank=metadata.get("adventure_rank", "—"),
              world=metadata.get("world_level", "—"))


def profile_icon(profile: dict) -> QIcon:
    value = (profile.get("metadata") or {}).get("avatar_path")
    if not value:
        return QIcon()
    root = profile_root(profile["id"])
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        return QIcon()
    return QIcon(str(path)) if path.is_file() else QIcon()


class AccountProfilesWidget(QWidget):
    operation_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.active_label = QLabel()
        layout.addWidget(self.active_label)
        self.selector = QPushButton()
        self.selector.setObjectName("accountProfileSelector")
        self.selector.setIconSize(QSize(46, 46))
        self.selector.setMinimumHeight(58)
        self.menu = QMenu(self.selector)
        self.menu.aboutToShow.connect(self._populate_menu)
        self.selector.setMenu(self.menu)
        layout.addWidget(self.selector)
        self.empty_hint = QLabel()
        self.empty_hint.setWordWrap(True)
        layout.addWidget(self.empty_hint)
        self.add_button = QPushButton()
        self.add_button.setObjectName("addAccountButton")
        self.add_button.clicked.connect(lambda: self.operation_requested.emit("new", ""))
        layout.addWidget(self.add_button)
        self.refresh()

    def refresh(self) -> None:
        current = active_profile()
        self.active_label.setText(tr("accounts.active") if current and current["imported"]
                                  else tr("accounts.no_active"))
        self.selector.setText(profile_caption(current) if current else tr("accounts.choose"))
        self.selector.setIcon(profile_icon(current) if current else QIcon())
        self.empty_hint.setText(tr("accounts.empty_hint"))
        self.empty_hint.setVisible(not current or not current["imported"])
        self.add_button.setText(tr("accounts.add"))

    def _populate_menu(self) -> None:
        self.menu.clear()
        current = active_profile()
        for profile in list_profiles():
            row = QWidget(self.menu)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(4, 3, 4, 3)
            select = QPushButton(profile_caption(profile), row)
            select.setIcon(profile_icon(profile))
            select.setIconSize(QSize(42, 42))
            select.setMinimumHeight(52)
            select.setObjectName(f"selectAccount_{profile['id']}")
            selected = current and current["id"] == profile["id"]
            select.setEnabled(not selected)
            select.clicked.connect(lambda _checked=False, key=profile["id"]: self._select(key))
            layout.addWidget(select, 1)
            delete = QPushButton("×", row)
            delete.setObjectName(f"deleteAccount_{profile['id']}")
            delete.setFixedWidth(30)
            delete.setStyleSheet("color: #f16b71; font-size: 22px;")
            install_custom_tooltip(delete, lambda: tr("accounts.delete"))
            delete.setAccessibleName(tr("accounts.delete_named", name=profile_caption(profile)))
            delete.clicked.connect(lambda _checked=False, key=profile["id"]: self._delete(key))
            layout.addWidget(delete)
            action = QWidgetAction(self.menu)
            action.setDefaultWidget(row)
            self.menu.addAction(action)

    def _select(self, profile_id: str) -> None:
        self.menu.close()
        self.operation_requested.emit("activate", profile_id)

    def _delete(self, profile_id: str) -> None:
        self.menu.close()
        self.operation_requested.emit("delete", profile_id)
