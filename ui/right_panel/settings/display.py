from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from localization import tr
from run_workspace.display_settings import set_use_system_scaling, use_system_scaling
from ui.utils.toggle_switch import ToggleSwitch
from ui.utils.ui_palette import UI_STATE_DANGER, UI_TEXT_MUTED


class DisplaySettingsBlock(QFrame):
    def __init__(
        self, parent: QWidget | None = None, *, settings_file: str | Path | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("InfoBlock")
        self._settings_file = settings_file
        self._saved_value = use_system_scaling(settings_file=settings_file)
        self._save_failed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self.title_label = QLabel()
        self.title_label.setObjectName("SectionTitle")
        layout.addWidget(self.title_label)

        row = QHBoxLayout()
        self.system_scaling_label = QLabel()
        self.system_scaling_label.setWordWrap(True)
        self.system_scaling_switch = ToggleSwitch()
        self.system_scaling_switch.setObjectName("useSystemScaling")
        self.system_scaling_switch.setChecked(self._saved_value)
        self.system_scaling_switch.toggled.connect(self._save_system_scaling)
        row.addWidget(self.system_scaling_label, 1)
        row.addWidget(self.system_scaling_switch)
        layout.addLayout(row)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
        layout.addWidget(self.description_label)
        self.restart_label = QLabel()
        self.restart_label.setWordWrap(True)
        layout.addWidget(self.restart_label)
        self.retranslate_ui()

    def _save_system_scaling(self, enabled: bool) -> None:
        try:
            set_use_system_scaling(enabled, settings_file=self._settings_file)
        except OSError:
            self._save_failed = True
            with QSignalBlocker(self.system_scaling_switch):
                self.system_scaling_switch.setChecked(self._saved_value)
        else:
            self._save_failed = False
            self._saved_value = enabled
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("settings.display.title"))
        self.system_scaling_label.setText(tr("settings.display.system_scaling"))
        self.system_scaling_switch.setAccessibleName(
            tr("settings.display.system_scaling")
        )
        self.description_label.setText(tr("settings.display.system_scaling.description"))
        self.system_scaling_switch.setAccessibleDescription(
            tr("settings.display.system_scaling.restart")
        )
        self.restart_label.setText(tr(
            "settings.display.system_scaling.save_failed"
            if self._save_failed else "settings.display.system_scaling.restart"
        ))
        self.restart_label.setStyleSheet(
            f"color: {UI_STATE_DANGER if self._save_failed else UI_TEXT_MUTED};"
        )
