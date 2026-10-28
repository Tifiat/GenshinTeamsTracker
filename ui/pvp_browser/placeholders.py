from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from localization import tr


class PvpWorkspacePlaceholder(QFrame):
    """Temporary left-workspace placeholder for the first PvP AppShell step."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PvpWorkspacePlaceholder")
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(8)
        root.addStretch(1)

        self.title_label = QLabel()
        self.title_label.setObjectName("SectionTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.title_label)

        self.subtitle_label = QLabel()
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.subtitle_label)

        self.note_label = QLabel()
        self.note_label.setWordWrap(True)
        self.note_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.note_label)

        self.sample_label = QLabel()
        self.sample_label.setWordWrap(True)
        self.sample_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.sample_label)
        root.addStretch(2)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.pvp.placeholder.title"))
        self.subtitle_label.setText(tr("app_shell.pvp.placeholder.subtitle"))
        self.note_label.setText(tr("app_shell.pvp.placeholder.note"))
        self.sample_label.setText(tr("app_shell.pvp.placeholder.sample"))


class PvpRightDockPlaceholder(QWidget):
    """Temporary right-dock control page for PvP before the draft UI is wired."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RightPanelPrototypeContent")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        frame = QFrame()
        frame.setObjectName("InfoBlock")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setObjectName("SectionTitle")
        frame_layout.addWidget(self.title_label)

        self.body_label = QLabel()
        self.body_label.setWordWrap(True)
        frame_layout.addWidget(self.body_label)

        self.sample_label = QLabel()
        self.sample_label.setWordWrap(True)
        frame_layout.addWidget(self.sample_label)

        root.addWidget(frame)
        root.addStretch(1)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.right_dock.pvp_decks"))
        self.body_label.setText(tr("app_shell.pvp.control.placeholder"))
        self.sample_label.setText(tr("app_shell.pvp.placeholder.sample"))


__all__ = ["PvpRightDockPlaceholder", "PvpWorkspacePlaceholder"]
