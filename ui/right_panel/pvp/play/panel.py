from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from localization import tr
from run_workspace.pvp.deck_preset import PvpDeckPreset
from ui.right_panel.pvp._shared import (
    PVP_DECKS_RIGHT_PANEL_STYLE,
    _active_draft_summary_lines,
    _text,
)


class PvpPlayRightPanel(QWidget):
    def __init__(
        self,
        workspace: PvpWorkspace,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self.player_1_deck_id = ""
        self.player_2_deck_id = ""
        self._refreshing = False
        self.setObjectName("RightPanelPrototypeContent")
        self.setStyleSheet(PVP_DECKS_RIGHT_PANEL_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setObjectName("SectionTitle")
        root.addWidget(self.title_label)

        self.mode_label = QLabel()
        self.mode_label.setObjectName("small_muted")
        self.mode_label.setWordWrap(True)
        root.addWidget(self.mode_label)

        self.empty_label = QLabel()
        self.empty_label.setObjectName("small_muted")
        self.empty_label.setWordWrap(True)
        root.addWidget(self.empty_label)

        self.player_1_label = QLabel()
        self.player_1_label.setObjectName("pvp_deck_info_line")
        root.addWidget(self.player_1_label)
        self.player_1_combo = QComboBox()
        self.player_1_combo.currentIndexChanged.connect(
            lambda _index: self._on_selection_changed()
        )
        root.addWidget(self.player_1_combo)
        self.player_1_status_label = QLabel()
        self.player_1_status_label.setObjectName("small_muted")
        self.player_1_status_label.setWordWrap(True)
        root.addWidget(self.player_1_status_label)

        self.player_2_label = QLabel()
        self.player_2_label.setObjectName("pvp_deck_info_line")
        root.addWidget(self.player_2_label)
        self.player_2_combo = QComboBox()
        self.player_2_combo.currentIndexChanged.connect(
            lambda _index: self._on_selection_changed()
        )
        root.addWidget(self.player_2_combo)
        self.player_2_status_label = QLabel()
        self.player_2_status_label.setObjectName("small_muted")
        self.player_2_status_label.setWordWrap(True)
        root.addWidget(self.player_2_status_label)

        self.start_button = QPushButton()
        self.start_button.setObjectName("pvp_primary_button")
        self.start_button.clicked.connect(self._on_start_clicked)
        root.addWidget(self.start_button)

        self.active_frame = QFrame()
        self.active_frame.setObjectName("pvp_deck_expanded_info")
        active_layout = QVBoxLayout(self.active_frame)
        active_layout.setContentsMargins(8, 8, 8, 8)
        active_layout.setSpacing(4)
        self.active_title_label = QLabel()
        self.active_title_label.setObjectName("pvp_deck_info_line")
        active_layout.addWidget(self.active_title_label)
        self.active_summary_labels: list[QLabel] = []
        for _index in range(7):
            label = QLabel()
            label.setObjectName("pvp_deck_info_line")
            label.setWordWrap(True)
            active_layout.addWidget(label)
            self.active_summary_labels.append(label)
        self.clear_button = QPushButton()
        self.clear_button.setObjectName("pvp_secondary_button")
        self.clear_button.clicked.connect(self.workspace.clear_active_draft)
        active_layout.addWidget(self.clear_button)
        root.addWidget(self.active_frame)

        self.status_label = QLabel()
        self.status_label.setObjectName("small_muted")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        root.addStretch(1)

        self.workspace.state_changed.connect(self.refresh)
        self.workspace.active_draft_changed.connect(self.refresh)
        self.retranslate_ui()
        self.refresh()

    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        try:
            options = self.workspace.play_deck_options()
            option_ids = {preset.deck_id for preset in options}
            if self.player_1_deck_id not in option_ids:
                self.player_1_deck_id = self.workspace.default_player_1_deck_id()
            if self.player_2_deck_id not in option_ids:
                self.player_2_deck_id = self.workspace.default_player_2_deck_id(
                    self.player_1_deck_id
                )
            self.player_1_deck_id = self._sync_combo(
                self.player_1_combo,
                self.player_1_deck_id,
                options,
            )
            self.player_2_deck_id = self._sync_combo(
                self.player_2_combo,
                self.player_2_deck_id,
                options,
            )

            has_decks = bool(options)
            for widget in (
                self.player_1_label,
                self.player_1_combo,
                self.player_1_status_label,
                self.player_2_label,
                self.player_2_combo,
                self.player_2_status_label,
                self.start_button,
            ):
                widget.setVisible(True)
                widget.setEnabled(has_decks)
            self.empty_label.setVisible(not has_decks)
            if not has_decks:
                self.start_button.setEnabled(False)
                self.player_1_status_label.setText("")
                self.player_2_status_label.setText("")
            else:
                player_1_status = self.workspace.deck_start_status(
                    self.player_1_deck_id,
                    player_label="Player 1",
                )
                player_2_status = self.workspace.deck_start_status(
                    self.player_2_deck_id,
                    player_label="Player 2",
                )
                self.player_1_status_label.setText(player_1_status.text)
                self.player_2_status_label.setText(player_2_status.text)
                self.start_button.setEnabled(
                    player_1_status.ready and player_2_status.ready
                )
            self._refresh_active_summary()
            status = self.workspace.last_play_status()
            self.status_label.setText(status)
            self.status_label.setVisible(bool(status))
        finally:
            self._refreshing = False

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.pvp.play.title"))
        self.mode_label.setText(tr("app_shell.pvp.play.mode_local_hotseat"))
        self.empty_label.setText(tr("app_shell.pvp.play.no_decks"))
        self.player_1_label.setText(tr("app_shell.pvp.play.player_1_deck"))
        self.player_2_label.setText(tr("app_shell.pvp.play.player_2_deck"))
        self.start_button.setText(tr("app_shell.pvp.play.start_local_draft"))
        self.active_title_label.setText(tr("app_shell.pvp.play.active_local_draft"))
        self.clear_button.setText(tr("app_shell.pvp.play.clear_active_draft"))
        self.refresh()

    def _sync_combo(
        self,
        combo: QComboBox,
        selected_id: str,
        options: tuple[PvpDeckPreset, ...],
    ) -> str:
        combo.blockSignals(True)
        try:
            combo.clear()
            for preset in options:
                combo.addItem(preset.name, preset.deck_id)
            if not options:
                return ""
            index = combo.findData(selected_id)
            if index < 0:
                index = 0
            combo.setCurrentIndex(index)
            return _text(combo.currentData())
        finally:
            combo.blockSignals(False)

    def _on_selection_changed(self) -> None:
        if self._refreshing:
            return
        self.player_1_deck_id = _text(self.player_1_combo.currentData())
        self.player_2_deck_id = _text(self.player_2_combo.currentData())
        self.refresh()

    def _on_start_clicked(self) -> None:
        if self.workspace.start_local_draft(
            self.player_1_deck_id,
            self.player_2_deck_id,
        ):
            self.refresh()

    def _refresh_active_summary(self) -> None:
        session = self.workspace.active_draft_session
        self.active_frame.setVisible(session is not None)
        lines = _active_draft_summary_lines(session) if session is not None else []
        for index, label in enumerate(self.active_summary_labels):
            text = lines[index] if index < len(lines) else ""
            label.setText(text)
            label.setVisible(bool(text))


__all__ = ["PvpPlayRightPanel"]
