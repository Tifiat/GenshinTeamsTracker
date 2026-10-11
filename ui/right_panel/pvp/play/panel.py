from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from localization import tr
from PySide6.QtCore import Qt
from ui.utils.overlay_scroll import OverlayVerticalScrollArea
from ui.utils.tooltips import install_custom_tooltip
from run_workspace.pvp.deck_preset import PvpDeckPreset
from run_workspace.pvp.deck import FREE_DRAFT_V0_RULESET_ID
from run_workspace.pvp.draft_options import DraftMatchOptions, parse_restart_penalties
from ui.right_panel.pvp._shared import (
    PVP_DECKS_RIGHT_PANEL_STYLE,
    PVP_PAGE_DRAFT,
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
        self.draft_system_id: str | None = None
        self._settings_context = None
        self._options_error = ""
        self._refreshing = False
        self._has_refreshed = False
        self._summary_session: object | None = None
        self.setObjectName("RightPanelPrototypeContent")
        self.setStyleSheet(PVP_DECKS_RIGHT_PANEL_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.setup_scroll = OverlayVerticalScrollArea()
        self.setup_scroll.setWidgetResizable(True)
        self.setup_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.setup_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setup_content = QWidget()
        self.setup_scroll.setWidget(self.setup_content)
        outer.addWidget(self.setup_scroll)
        root = QVBoxLayout(self.setup_content)
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

        player_1_header = QHBoxLayout()
        player_1_header.setContentsMargins(0, 0, 0, 0)
        player_1_header.setSpacing(5)
        self.player_1_label = QLabel()
        self.player_1_label.setObjectName("pvp_deck_info_line")
        player_1_header.addWidget(self.player_1_label, 1)
        self.player_1_import_button = QPushButton()
        self.player_1_import_button.setObjectName("pvp_secondary_button")
        self.player_1_import_button.clicked.connect(
            lambda: self._on_import_profile("player_1")
        )
        player_1_header.addWidget(self.player_1_import_button)
        self.player_1_local_button = QPushButton()
        self.player_1_local_button.setObjectName("pvp_secondary_button")
        self.player_1_local_button.clicked.connect(
            lambda: self.workspace.use_local_profile_for_seat("player_1")
        )
        player_1_header.addWidget(self.player_1_local_button)
        root.addLayout(player_1_header)
        self.player_1_combo = QComboBox()
        self.player_1_combo.currentIndexChanged.connect(
            lambda _index: self._on_selection_changed()
        )
        root.addWidget(self.player_1_combo)
        self.player_1_status_label = QLabel()
        self.player_1_status_label.setObjectName("small_muted")
        self.player_1_status_label.setWordWrap(True)
        root.addWidget(self.player_1_status_label)

        player_2_header = QHBoxLayout()
        player_2_header.setContentsMargins(0, 0, 0, 0)
        player_2_header.setSpacing(5)
        self.player_2_label = QLabel()
        self.player_2_label.setObjectName("pvp_deck_info_line")
        player_2_header.addWidget(self.player_2_label, 1)
        self.player_2_import_button = QPushButton()
        self.player_2_import_button.setObjectName("pvp_secondary_button")
        self.player_2_import_button.clicked.connect(
            lambda: self._on_import_profile("player_2")
        )
        player_2_header.addWidget(self.player_2_import_button)
        self.player_2_local_button = QPushButton()
        self.player_2_local_button.setObjectName("pvp_secondary_button")
        self.player_2_local_button.clicked.connect(
            lambda: self.workspace.use_local_profile_for_seat("player_2")
        )
        player_2_header.addWidget(self.player_2_local_button)
        root.addLayout(player_2_header)
        self.player_2_combo = QComboBox()
        self.player_2_combo.currentIndexChanged.connect(
            lambda _index: self._on_selection_changed()
        )
        root.addWidget(self.player_2_combo)
        self.player_2_status_label = QLabel()
        self.player_2_status_label.setObjectName("small_muted")
        self.player_2_status_label.setWordWrap(True)
        root.addWidget(self.player_2_status_label)

        self.draft_system_label = QLabel()
        self.draft_system_label.setObjectName("pvp_deck_info_line")
        root.addWidget(self.draft_system_label)
        self.draft_system_combo = QComboBox()
        self.draft_system_combo.setMinimumContentsLength(12)
        self.draft_system_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.draft_system_combo.currentIndexChanged.connect(self._on_system_changed)
        root.addWidget(self.draft_system_combo)

        series_form = QFormLayout()
        self.first_seat_label = QLabel()
        self.first_seat_label.setObjectName("pvp_deck_info_line")
        self.first_seat_combo = QComboBox()
        self.first_seat_combo.addItem("", "player_1")
        self.first_seat_combo.addItem("", "player_2")
        self.first_seat_combo.currentIndexChanged.connect(self._on_options_changed)
        series_form.addRow(self.first_seat_label, self.first_seat_combo)
        self.games_count_label = QLabel()
        self.games_count_label.setObjectName("pvp_deck_info_line")
        self.games_count_spin = QSpinBox()
        self.games_count_spin.setObjectName("pvp_setup_value")
        self.games_count_spin.setRange(1, 9)
        self.games_count_spin.valueChanged.connect(self._on_options_changed)
        series_form.addRow(self.games_count_label, self.games_count_spin)
        root.addLayout(series_form)
        self.alternate_first_check = QCheckBox()
        self.alternate_first_check.setObjectName("pvp_setup_defaults")
        self.alternate_first_check.setChecked(True)
        self.alternate_first_check.toggled.connect(self._on_options_changed)
        root.addWidget(self.alternate_first_check)

        self.source_settings_check = QCheckBox()
        self.source_settings_check.setObjectName("pvp_setup_defaults")
        self.source_settings_check.setChecked(True)
        self.source_settings_check.toggled.connect(self._on_options_changed)
        root.addWidget(self.source_settings_check)
        self.timer_enabled_check = QCheckBox()
        self.timer_enabled_check.setObjectName("pvp_setup_defaults")
        self.timer_enabled_check.toggled.connect(self._on_timer_enabled_changed)
        root.addWidget(self.timer_enabled_check)
        self.auto_on_expire_check = QCheckBox()
        self.auto_on_expire_check.setObjectName("pvp_setup_defaults")
        self.auto_on_expire_check.setChecked(True)
        self.auto_on_expire_check.toggled.connect(self._on_options_changed)
        root.addWidget(self.auto_on_expire_check)
        settings_form = QFormLayout()
        self.preban_step_label = QLabel()
        self.pick_time_label = QLabel()
        self.reserve_time_label = QLabel()
        self.free_restarts_label = QLabel()
        self.paid_restarts_label = QLabel()
        self.free_restarts_spin = QSpinBox()
        self.free_restarts_spin.setRange(0, 100)
        self.free_restarts_spin.setObjectName("pvp_setup_value")
        self.paid_restarts_edit = QLineEdit()
        self.paid_restarts_edit.setPlaceholderText("5 / 5 / 10")
        self.preban_step_spin = QSpinBox()
        self.preban_step_spin.setRange(0, 10000)
        self.pick_time_spin = QSpinBox()
        self.reserve_time_spin = QSpinBox()
        for spin in (self.pick_time_spin, self.reserve_time_spin):
            spin.setRange(0, 86400)
        for label, spin in ((self.preban_step_label, self.preban_step_spin),
                            (self.pick_time_label, self.pick_time_spin),
                            (self.reserve_time_label, self.reserve_time_spin)):
            label.setWordWrap(True)
            label.setObjectName("pvp_deck_info_line")
            spin.setObjectName("pvp_setup_value")
            settings_form.addRow(label, spin)
            spin.valueChanged.connect(self._on_options_changed)
        root.addLayout(settings_form)
        for label, field in ((self.free_restarts_label, self.free_restarts_spin),
                             (self.paid_restarts_label, self.paid_restarts_edit)):
            label.setObjectName("pvp_deck_info_line")
            label.setWordWrap(True)
            settings_form.addRow(label, field)
        self.free_restarts_spin.valueChanged.connect(self._on_options_changed)
        self.paid_restarts_edit.textChanged.connect(self._on_options_changed)
        self.preban_preview_label = QLabel()
        self.preban_preview_label.setObjectName("small_muted")
        self.preban_preview_label.setWordWrap(True)
        root.addWidget(self.preban_preview_label)

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

        self.workspace.state_changed.connect(self._on_workspace_state_changed)
        self.retranslate_ui()

    def refresh(self) -> None:
        """Refresh visible Play readiness, selections, and draft summary."""
        if self._refreshing:
            return
        self._refreshing = True
        try:
            self._refresh_profile_labels()
            player_1_options = self.workspace.play_deck_options("player_1")
            player_2_options = self.workspace.play_deck_options("player_2")
            player_1_option_ids = {preset.deck_id for preset in player_1_options}
            player_2_option_ids = {preset.deck_id for preset in player_2_options}
            if self.player_1_deck_id not in player_1_option_ids:
                self.player_1_deck_id = self.workspace.default_player_1_deck_id()
            if self.player_2_deck_id not in player_2_option_ids:
                self.player_2_deck_id = self.workspace.default_player_2_deck_id(
                    self.player_1_deck_id
                )
            self.player_1_deck_id = self._sync_combo(
                self.player_1_combo,
                self.player_1_deck_id,
                player_1_options,
            )
            self.player_2_deck_id = self._sync_combo(
                self.player_2_combo,
                self.player_2_deck_id,
                player_2_options,
            )
            self._sync_draft_system_combo()
            self._sync_match_options()

            has_player_1_decks = bool(player_1_options)
            has_player_2_decks = bool(player_2_options)
            has_decks = has_player_1_decks and has_player_2_decks
            active = self.workspace.active_draft_session is not None
            self.source_settings_check.setEnabled(not active)
            self.first_seat_combo.setEnabled(not active)
            self.games_count_spin.setEnabled(not active)
            self.alternate_first_check.setEnabled(not active and self.games_count_spin.value() > 1)
            self.timer_enabled_check.setEnabled(not active)
            self.auto_on_expire_check.setEnabled(not active and self.timer_enabled_check.isChecked())
            for spin in (self.pick_time_spin, self.reserve_time_spin):
                spin.setEnabled(not active and not self.source_settings_check.isChecked()
                                and self.timer_enabled_check.isChecked())
            self.preban_step_spin.setEnabled(not active and not self.source_settings_check.isChecked()
                                             and self.draft_system_id != FREE_DRAFT_V0_RULESET_ID)
            self.preban_step_spin.setVisible(self.draft_system_id != FREE_DRAFT_V0_RULESET_ID)
            self.preban_step_label.setVisible(self.draft_system_id != FREE_DRAFT_V0_RULESET_ID)
            for widget in (self.free_restarts_label, self.free_restarts_spin,
                           self.paid_restarts_label, self.paid_restarts_edit):
                widget.setVisible(self.draft_system_id != FREE_DRAFT_V0_RULESET_ID)
                widget.setEnabled(not active and not self.source_settings_check.isChecked())
            self.player_1_combo.setEnabled(has_player_1_decks and not active)
            self.player_2_combo.setEnabled(has_player_2_decks and not active)
            self.draft_system_combo.setEnabled(has_decks and not active)
            self.player_1_import_button.setEnabled(not active)
            self.player_2_import_button.setEnabled(not active)
            self.player_1_local_button.setVisible(
                self.workspace.seat_profile_is_imported("player_1")
            )
            self.player_2_local_button.setVisible(
                self.workspace.seat_profile_is_imported("player_2")
            )
            self.player_1_local_button.setEnabled(not active)
            self.player_2_local_button.setEnabled(not active)
            self.empty_label.setVisible(not has_decks)
            if not has_decks:
                self.start_button.setEnabled(False)
                if not has_player_1_decks:
                    self.player_1_status_label.setText(
                        tr("app_shell.pvp.play.no_decks")
                    )
                if not has_player_2_decks:
                    self.player_2_status_label.setText(
                        tr("app_shell.pvp.play.no_decks")
                    )
            else:
                player_1_status = self.workspace.deck_start_status(
                    self.player_1_deck_id,
                    player_label="Player 1",
                    seat="player_1",
                    draft_system_id=self.draft_system_id,
                )
                player_2_status = self.workspace.deck_start_status(
                    self.player_2_deck_id,
                    player_label="Player 2",
                    seat="player_2",
                    draft_system_id=self.draft_system_id,
                )
                self.player_1_status_label.setText(player_1_status.text)
                self.player_2_status_label.setText(player_2_status.text)
                self.start_button.setEnabled(
                    not active and player_1_status.ready and player_2_status.ready
                    and self.workspace.period_admission().ready
                    and not self.workspace.match_rules_status(
                        self.player_1_deck_id, self.player_2_deck_id, draft_system_id=self.draft_system_id,
                        match_options=self.match_options())
                )
            self._refresh_active_summary()
            status = (self.workspace.last_play_status() or self.workspace.period_admission_text()
                      or self.workspace.match_rules_status(
                          self.player_1_deck_id, self.player_2_deck_id, draft_system_id=self.draft_system_id,
                          match_options=self.match_options()))
            self._refresh_preban_preview()
            if self._options_error:
                self.start_button.setEnabled(False)
                status = self._options_error
            self.status_label.setText(status)
            self.status_label.setVisible(bool(status))
        finally:
            self._refreshing = False
            self._has_refreshed = True
            self._summary_session = self.workspace.active_draft_session

    def _on_workspace_state_changed(self) -> None:
        if (
            self._has_refreshed
            and self.workspace.active_page_id == PVP_PAGE_DRAFT
        ):
            session = self.workspace.active_draft_session
            if session is not self._summary_session:
                self._refresh_active_summary()
                self._summary_session = session
            play_status = self.workspace.last_play_status()
            if play_status:
                self.status_label.setText(play_status)
                self.status_label.setVisible(True)
            return
        self.refresh()

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.pvp.play.title"))
        self.mode_label.setText(tr("app_shell.pvp.play.mode_local_hotseat"))
        self.empty_label.setText(tr("app_shell.pvp.play.no_decks"))
        self._refresh_profile_labels()
        self.player_1_import_button.setText(tr("app_shell.pvp.profile.import"))
        self.player_2_import_button.setText(tr("app_shell.pvp.profile.import"))
        self.player_1_local_button.setText(tr("app_shell.pvp.profile.use_local"))
        self.player_2_local_button.setText(tr("app_shell.pvp.profile.use_local"))
        self.draft_system_label.setText(tr("app_shell.pvp.decks.rules_label"))
        self.first_seat_label.setText(tr("app_shell.pvp.setup.first_seat"))
        install_custom_tooltip(self.first_seat_combo, tr("app_shell.pvp.setup.first_seat_hint"))
        self.games_count_label.setText(tr("app_shell.pvp.setup.games_count"))
        self.alternate_first_check.setText(tr("app_shell.pvp.setup.alternate_first"))
        for index, seat in enumerate(("player_1", "player_2")):
            self.first_seat_combo.setItemText(index, tr("app_shell.pvp.draft." + seat))
        self.source_settings_check.setText(tr("app_shell.pvp.setup.source_settings"))
        self.timer_enabled_check.setText(tr("app_shell.pvp.setup.timer_enabled"))
        self.auto_on_expire_check.setText(tr("app_shell.pvp.setup.auto_on_expire"))
        self.preban_step_label.setText(tr("app_shell.pvp.setup.preban_step"))
        self.pick_time_label.setText(tr("app_shell.pvp.setup.pick_time"))
        self.reserve_time_label.setText(tr("app_shell.pvp.setup.reserve_time"))
        self.free_restarts_label.setText(tr("app_shell.pvp.setup.free_restarts"))
        self.paid_restarts_label.setText(tr("app_shell.pvp.setup.paid_restarts"))
        for spin in (self.pick_time_spin, self.reserve_time_spin):
            spin.setSuffix(tr("app_shell.pvp.setup.seconds"))
        self.start_button.setText(tr("app_shell.pvp.play.start_local_draft"))
        self.active_title_label.setText(tr("app_shell.pvp.play.active_local_draft"))
        self.clear_button.setText(tr("app_shell.pvp.play.clear_active_draft"))
        self.refresh()

    def _refresh_profile_labels(self) -> None:
        self.player_1_label.setText(
            tr("app_shell.pvp.play.player_profile").format(
                seat=tr("app_shell.pvp.draft.player_1"),
                profile=self.workspace.seat_profile_label("player_1"),
            )
        )
        self.player_2_label.setText(
            tr("app_shell.pvp.play.player_profile").format(
                seat=tr("app_shell.pvp.draft.player_2"),
                profile=self.workspace.seat_profile_label("player_2"),
            )
        )

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
        options = self.match_options()
        if self._options_error:
            return
        if self.workspace.start_local_draft(
            self.player_1_deck_id,
            self.player_2_deck_id,
            draft_system_id=self.draft_system_id,
            match_options=options,
        ):
            self.refresh()

    def _sync_draft_system_combo(self) -> None:
        options = self.workspace.play_draft_system_options(self.player_1_deck_id, self.player_2_deck_id)
        available = {item[0] for item in options}
        if self.draft_system_id not in available:
            preferred = self.workspace.default_play_draft_system(self.player_1_deck_id)
            self.draft_system_id = preferred if preferred in available else options[0][0]
        self.draft_system_combo.blockSignals(True)
        try:
            self.draft_system_combo.clear()
            for system_id, label in options:
                self.draft_system_combo.addItem(label, system_id)
            self.draft_system_combo.setCurrentIndex(self.draft_system_combo.findData(self.draft_system_id))
        finally:
            self.draft_system_combo.blockSignals(False)

    def _on_system_changed(self, _index: int) -> None:
        if self._refreshing:
            return
        self.draft_system_id = _text(self.draft_system_combo.currentData())
        self.refresh()

    def match_options(self):
        self._options_error = ""
        if (self.source_settings_check.isChecked() and self.auto_on_expire_check.isChecked()
                and self.first_seat_combo.currentData() == "player_1"
                and self.games_count_spin.value() == 1 and self.alternate_first_check.isChecked()):
            return None
        try:
            penalties = parse_restart_penalties(self.paid_restarts_edit.text())
        except ValueError:
            self._options_error = tr("app_shell.pvp.setup.penalties_invalid")
            return None
        return DraftMatchOptions(
            first_seat=self.first_seat_combo.currentData(),
            games_count=self.games_count_spin.value(),
            alternate_first=self.alternate_first_check.isChecked(),
            preban_cost_step=(self.preban_step_spin.value() if self.draft_system_id != FREE_DRAFT_V0_RULESET_ID
                             and not self.source_settings_check.isChecked() else None),
            pick_time_ms=(None if self.source_settings_check.isChecked() else
                          self.pick_time_spin.value() * 1000 if self.timer_enabled_check.isChecked() else 0),
            reserve_time_ms=(None if self.source_settings_check.isChecked() else
                             self.reserve_time_spin.value() * 1000 if self.timer_enabled_check.isChecked() else 0),
            auto_on_expire=self.auto_on_expire_check.isChecked(),
            free_restarts=(self.free_restarts_spin.value() if not self.source_settings_check.isChecked()
                           and self.draft_system_id != FREE_DRAFT_V0_RULESET_ID else None),
            paid_restarts=(penalties if not self.source_settings_check.isChecked()
                           and self.draft_system_id != FREE_DRAFT_V0_RULESET_ID else None),
        )

    def _sync_match_options(self):
        try:
            defaults = self.workspace.play_match_options(self.player_1_deck_id, self.draft_system_id)
        except ValueError:
            defaults = DraftMatchOptions().resolve(None)
        context = (self.draft_system_id, defaults)
        if context != self._settings_context:
            self._settings_context = context
            self.source_settings_check.setChecked(True)
        if self.source_settings_check.isChecked():
            self.timer_enabled_check.setChecked(bool(defaults.pick_time_ms))
            for spin, value in ((self.preban_step_spin, defaults.preban_cost_step),
                                (self.pick_time_spin, (defaults.pick_time_ms or 0) // 1000),
                                (self.reserve_time_spin, (defaults.reserve_time_ms or 0) // 1000)):
                spin.blockSignals(True)
                spin.setValue(value or 0)
                spin.blockSignals(False)
            self.free_restarts_spin.blockSignals(True)
            self.free_restarts_spin.setValue(defaults.free_restarts or 0)
            self.free_restarts_spin.blockSignals(False)
            self.paid_restarts_edit.blockSignals(True)
            self.paid_restarts_edit.setText(" / ".join(str(value) for value in defaults.paid_restarts or ()))
            self.paid_restarts_edit.blockSignals(False)

    def _on_options_changed(self, *_args):
        if not self._refreshing:
            self.refresh()

    def _on_timer_enabled_changed(self, enabled):
        if self._refreshing:
            return
        self.source_settings_check.setChecked(False)
        if enabled and self.pick_time_spin.value() == 0:
            self.pick_time_spin.setValue(60)
            self.reserve_time_spin.setValue(300)
        self.refresh()

    def _refresh_preban_preview(self):
        self.preban_preview_label.setVisible(self.draft_system_id != FREE_DRAFT_V0_RULESET_ID)
        try:
            report = self.workspace.play_preban_report(
                self.player_1_deck_id, self.player_2_deck_id, draft_system_id=self.draft_system_id,
                match_options=self.match_options())
        except ValueError:
            self.preban_preview_label.setText(tr("app_shell.pvp.setup.cost_unknown"))
            return
        if report is None:
            self.preban_preview_label.setText("")
            return
        seat = tr("app_shell.pvp.draft." + report.seat) if report.seat else tr("app_shell.pvp.setup.nobody")
        text = tr("app_shell.pvp.setup.preban_preview").format(
            p1=report.total_player_1, p2=report.total_player_2, difference=report.difference,
            step=report.cost_step, count=report.count, seat=seat)
        if report.cost_method == "FRENCH_COST":
            preset = self.workspace._seat_preset_by_id("player_1", self.player_1_deck_id)
            cap = (preset.rules_snapshot or {}).get("french_difference_cap") if preset else "?"
            text += "\n" + tr("app_shell.pvp.setup.french_preban_info").format(cap=cap)
        if not self.source_settings_check.isChecked():
            text += "\n" + tr("app_shell.pvp.setup.custom_settings")
        self.preban_preview_label.setText(text)

    def _on_import_profile(self, seat: str) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            tr("app_shell.pvp.profile.import"),
            "",
            tr("app_shell.pvp.profile.file_filter"),
        )
        if path:
            self.workspace.import_profile_for_seat(seat, path)

    def _refresh_active_summary(self) -> None:
        session = self.workspace.active_draft_session
        self.active_frame.setVisible(session is not None)
        lines = (
            _active_draft_summary_lines(
                session,
                board=self.workspace.draft_board_dict(),
            )
            if session is not None
            else []
        )
        for index, label in enumerate(self.active_summary_labels):
            text = lines[index] if index < len(lines) else ""
            label.setText(text)
            label.setVisible(bool(text))


__all__ = ["PvpPlayRightPanel"]
