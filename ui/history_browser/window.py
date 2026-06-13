"""History Browser left-workspace placeholder.

This module owns the inert AppShell History placeholder until typed immutable
run snapshots exist. The future product and architecture contract lives in
`docs/handoff/HISTORY_BROWSER.md`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from localization import tr


class HistoryBrowserWorkspace(QFrame):
    """Temporary left-workspace placeholder until immutable snapshots exist."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HistoryBrowserWorkspace")
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

        self.legacy_note_label = QLabel()
        self.legacy_note_label.setWordWrap(True)
        self.legacy_note_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.legacy_note_label)
        root.addStretch(2)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.history.placeholder.title"))
        self.subtitle_label.setText(tr("app_shell.history.placeholder.subtitle"))
        self.note_label.setText(tr("app_shell.history.placeholder.note"))
        self.legacy_note_label.setText(tr("app_shell.history.placeholder.legacy_note"))
