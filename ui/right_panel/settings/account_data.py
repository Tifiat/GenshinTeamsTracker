from __future__ import annotations

import codecs
import json
import sys
import uuid
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QColorDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from hoyolab_export.auth import AuthStatus, get_auth_status, open_login_browser
from hoyolab_export.offline_profile import (
    export_offline_profile,
    has_local_hoyolab_profile,
)
from hoyolab_export.paths import (
    HOYOLAB_PROFILE_DIR,
    PROJECT_ROOT,
    ensure_hoyolab_dirs,
)
from localization import get_language, language_options, set_language, tr
from run_workspace.abyss.fact_dps_settings import (
    is_abyss_fact_dps_multi_target_enabled,
    set_abyss_fact_dps_multi_target_enabled,
)
from run_workspace.gcsim.settings import (
    optimizer_output_limits,
    effective_gcsim_optimizer_settings,
    is_gcsim_boosted_energy_enabled,
    set_gcsim_optimizer_builds_per_group,
    set_gcsim_optimizer_expanded_limits_enabled,
    set_gcsim_optimizer_fast_mode_enabled,
    set_gcsim_optimizer_set_group_limit,
    set_gcsim_boosted_energy_enabled,
)
from ui.utils.toggle_switch import ToggleSwitch
from ui.utils.tooltips import install_custom_tooltip
from ui.utils.ui_palette import UI_BORDER_DEFAULT, UI_TEXT_MUTED
from hoyolab_export.import_settings import change_equipment_on_import, set_change_equipment_on_import
from hoyolab_export.artifact_db import ARTIFACT_DB_PATH
from hoyolab_export.import_store import (
    get_import_result,
    latest_committed_import,
    list_pending_import_attempts,
)
from ui.utils.pvp_colors import (
    pvp_player_color,
    reset_pvp_player_colors,
    set_pvp_player_color as persist_pvp_player_color,
)
from ui.widgets.loader import HoYoLABLoadingDialog
from ui.widgets.overlays.login_hint import HoYoLABLoginHintOverlay
from run_workspace.app_settings import get_app_bool_setting, set_app_bool_setting
from .account_profiles import AccountProfilesWidget
from run_workspace.profile_context import PROFILE_ID
from run_workspace.account_profiles import active_profile


HOYOLAB_IMPORT_WARNING_KEYS = {
    "artifacts_not_imported": "hoyolab.import_warning.artifacts",
    "account_storage_sync_failed": "hoyolab.import_warning.account",
    "equipment_not_applied": "hoyolab.import_warning.equipment",
}
HOYOLAB_RECOVERY_ENRICHMENT_KINDS = (
    "assets", "references", "projections", "abyss", "side_icons",
)
HOYOLAB_IMPORT_STATUSES = {
    "preparing": ("loader.preparing", 0.03),
    "opening_hoyolab": ("loader.opening_hoyolab", 0.04),
    "exporting_image": ("loader.exporting_image", 0.15),
    "opening_character_list": ("loader.opening_character_list", 0.07),
    "collecting_inventory": ("loader.collecting_inventory", 0.10),
    "collecting_asset_urls": ("loader.collecting_asset_urls", 0.29),
    "downloading_assets": ("loader.downloading_assets", 0.03),
    "waiting_export_images": ("loader.waiting_export_images", 0.30),
    "opening_share_menu": ("loader.opening_share_menu", 0.34),
    "starting_image_download": ("loader.starting_image_download", 0.38),
    "waiting_image_download": ("loader.waiting_image_download", 0.42),
    "retrying_image_download_2": ("loader.retrying_image_download_2", 0.43),
    "retrying_image_download_3": ("loader.retrying_image_download_3", 0.44),
    "waiting_image_generation": ("loader.waiting_image_generation", 0.45),
    "using_image_fallback": ("loader.using_image_fallback", 0.46),
    "downloading_image": ("loader.downloading_image", 0.48),
    "image_downloaded": ("loader.image_downloaded", 0.52),
    "building_layout": ("loader.building_layout", 0.58),
    "writing_inventory": ("loader.writing_inventory", 0.35),
    "fetching_character_details": ("loader.fetching_character_details", 0.12),
    "fetching_abyss_period": ("loader.fetching_abyss_period", 0.735),
    "updating_artifact_catalog": ("loader.updating_artifact_catalog", 0.76),
    "mapping_artifact_sets": ("loader.mapping_artifact_sets", 0.80),
    "closing_browser": ("loader.closing_browser", 0.84),
    "importing_artifacts": ("loader.importing_artifacts", 0.87),
    "updating_hoyolab_data": ("loader.updating_hoyolab_data", 0.91),
    "saving_account": ("loader.saving_account", 0.18),
    "enriching_account": ("loader.enriching_account", 0.20),
    "cropping_assets": ("loader.cropping_assets", 0.72),
    "syncing_account_storage": ("loader.syncing_account_storage", 0.965),
    "account_storage_sync_warning": ("loader.account_storage_sync_warning", 0.97),
    "updating_abyss_source_data": ("loader.updating_abyss_source_data", 0.972),
    "caching_abyss_monster_icons": ("loader.caching_abyss_monster_icons", 0.976),
    "skipping_abyss_source_data_refresh": ("loader.skipping_abyss_source_data_refresh", 0.976),
    "writing_import_log": ("loader.writing_import_log", 0.98),
    "applying_equipment": ("loader.applying_equipment", 0.979),
    "done": ("loader.done", 1.0),
}


class AccountDataPage(QWidget):
    """Compact AppShell account page reusing the current HoYoLAB/profile flow."""

    account_data_changed = Signal(bool)
    profile_operation_requested = Signal(str, str)
    language_changed = Signal()
    fact_dps_multi_target_changed = Signal(bool)
    gcsim_boosted_energy_changed = Signal(bool)
    pvp_player_colors_changed = Signal(str, str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings_file: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        ensure_hoyolab_dirs()
        self.setObjectName("RightPanelPrototypeContent")
        self._settings_file = settings_file

        self._hoyolab_login_process = None
        self._hoyolab_login_hint: HoYoLABLoginHintOverlay | None = None
        self._hoyolab_login_screen = None
        self._hoyolab_export_process: QProcess | None = None
        self._hoyolab_loader: HoYoLABLoadingDialog | None = None
        self._hoyolab_import_output_buffer = ""
        self._hoyolab_import_lines: list[str] = []
        self._hoyolab_import_warnings: list[dict] = []
        self._hoyolab_import_decoder = None
        self._hoyolab_attempt_id: str | None = None
        self._hoyolab_committed_attempt_id: str | None = None
        self._hoyolab_binding_required: dict | None = None
        self._duplicate_profile_id: str | None = None
        self._hoyolab_images_only = False
        self._hoyolab_last_progress = 0.03
        self._updating_language_combo = False
        self._suppress_optimizer_fast_mode_warning = False

        self._hoyolab_auth_timer = QTimer(self)
        self._hoyolab_auth_timer.setInterval(1000)
        self._hoyolab_auth_timer.timeout.connect(self.poll_hoyolab_login_browser)

        self._build_ui()
        self.refresh_hoyolab_auth_status()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.title_label = QLabel(tr("app_shell.account.title"))
        self.title_label.setObjectName("SectionTitle")
        root.addWidget(self.title_label)

        self.settings_scroll = QScrollArea()
        self.settings_scroll.setObjectName("accountSettingsScrollArea")
        self.settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.settings_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.settings_content = QWidget()
        self.settings_content.setObjectName("accountSettingsContent")
        content_layout = QVBoxLayout(self.settings_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        self.settings_scroll.setWidget(self.settings_content)
        root.addWidget(self.settings_scroll, 1)

        account_frame = QFrame()
        account_frame.setObjectName("InfoBlock")
        account_layout = QVBoxLayout(account_frame)
        account_layout.setContentsMargins(8, 8, 8, 8)
        account_layout.setSpacing(8)

        self.hoyolab_label = QLabel(tr("common.hoyolab"))
        self.hoyolab_label.setObjectName("SectionTitle")
        account_layout.addWidget(self.hoyolab_label)

        self.account_profiles = AccountProfilesWidget(self)
        self.account_profiles.operation_requested.connect(self._request_profile_operation)
        account_layout.addWidget(self.account_profiles)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(6)
        self.btn_hoyolab_login = QPushButton(tr("accounts.login"))
        self.btn_hoyolab_login.setObjectName("accountLoginButton")
        self.btn_hoyolab_login.clicked.connect(self.login_requested)
        action_row.addWidget(self.btn_hoyolab_login)
        self.btn_hoyolab_export = QPushButton(tr("hoyolab.import_button"))
        self.btn_hoyolab_export.setObjectName("ActionButton")
        self._hoyolab_export_tooltip = install_custom_tooltip(self.btn_hoyolab_export)
        self.btn_hoyolab_export.clicked.connect(self.run_hoyolab_export)
        action_row.addWidget(self.btn_hoyolab_export, 1)

        self.btn_profile_menu = QPushButton(tr("profile.menu_button"))
        self.btn_profile_menu.setObjectName("GhostButton")
        self.profile_menu = QMenu(self.btn_profile_menu)
        self.action_export_profile = self.profile_menu.addAction(tr("profile.export"))
        self.action_import_profile = self.profile_menu.addAction(tr("profile.import"))
        self.profile_menu.addSeparator()
        self.action_switch_profile = self.profile_menu.addAction(tr("profile.switch"))
        self.action_export_profile.triggered.connect(
            lambda _checked=False: self.export_profile()
        )
        self.action_import_profile.triggered.connect(
            lambda _checked=False: self.import_profile()
        )
        self.action_switch_profile.triggered.connect(
            lambda _checked=False: self.change_hoyolab_account()
        )
        self.btn_profile_menu.setMenu(self.profile_menu)
        action_row.addWidget(self.btn_profile_menu)
        account_layout.addLayout(action_row)
        self.btn_clear_all = QPushButton(tr("accounts.clear_all"))
        self.btn_clear_all.setObjectName("clearAllAccountsButton")
        self.btn_clear_all.setStyleSheet("color: #f16b71;")
        self.btn_clear_all.clicked.connect(lambda: self._request_profile_operation("reset", ""))
        account_layout.addWidget(self.btn_clear_all)
        self.hoyolab_recovery_status = QLabel("")
        self.hoyolab_recovery_status.setWordWrap(True)
        self.hoyolab_recovery_status.setStyleSheet(
            f"QLabel {{ color: {UI_TEXT_MUTED}; }}"
        )
        self.hoyolab_recovery_status.hide()
        account_layout.addWidget(self.hoyolab_recovery_status)
        self.btn_images_refresh = QPushButton(tr("hoyolab.refresh_images_button"))
        self.btn_images_refresh.setObjectName("GhostButton")
        self.btn_images_refresh.clicked.connect(lambda _checked=False: self.run_hoyolab_export(images_only=True))
        account_layout.addWidget(self.btn_images_refresh)
        equipment_row = QHBoxLayout()
        self.change_equipment_label = QLabel(tr("hoyolab.change_equipment"))
        self.change_equipment_switch = ToggleSwitch()
        self.change_equipment_switch.setAccessibleName(tr("hoyolab.change_equipment"))
        self.change_equipment_switch.setChecked(change_equipment_on_import(settings_file=self._settings_file))
        self.change_equipment_switch.toggled.connect(
            lambda enabled: set_change_equipment_on_import(enabled, settings_file=self._settings_file)
        )
        equipment_row.addWidget(self.change_equipment_label, 1)
        equipment_row.addWidget(self.change_equipment_switch)
        account_layout.addLayout(equipment_row)
        content_layout.addWidget(account_frame)

        language_frame = QFrame()
        language_frame.setObjectName("InfoBlock")
        language_layout = QHBoxLayout(language_frame)
        language_layout.setContentsMargins(8, 8, 8, 8)
        language_layout.setSpacing(8)

        self.language_label = QLabel(tr("language.selector"))
        self.language_combo = QComboBox()
        self.language_combo.setMinimumWidth(150)
        for code, label in language_options():
            self.language_combo.addItem(label, code)
        self._sync_language_combo()
        self.language_combo.currentIndexChanged.connect(self.on_language_changed)
        language_layout.addWidget(self.language_label)
        language_layout.addWidget(self.language_combo, 1)
        content_layout.addWidget(language_frame)

        dps_frame = QFrame()
        dps_frame.setObjectName("InfoBlock")
        dps_layout = QVBoxLayout(dps_frame)
        dps_layout.setContentsMargins(8, 8, 8, 8)
        dps_layout.setSpacing(8)

        self.dps_label = QLabel(tr("settings.dps.title"))
        self.dps_label.setObjectName("SectionTitle")
        dps_layout.addWidget(self.dps_label)

        dps_toggle_row = QHBoxLayout()
        dps_toggle_row.setContentsMargins(0, 0, 0, 0)
        dps_toggle_row.setSpacing(8)
        self.fact_dps_multi_target_label = QLabel(
            tr("settings.dps.multi_target_hp")
        )
        self.fact_dps_multi_target_switch = ToggleSwitch()
        self.fact_dps_multi_target_switch.setChecked(
            is_abyss_fact_dps_multi_target_enabled(
                settings_file=self._settings_file
            )
        )
        self.fact_dps_multi_target_switch.toggled.connect(
            self.on_fact_dps_multi_target_changed
        )
        dps_toggle_row.addWidget(self.fact_dps_multi_target_label, 1)
        dps_toggle_row.addWidget(self.fact_dps_multi_target_switch)
        dps_layout.addLayout(dps_toggle_row)
        content_layout.addWidget(dps_frame)

        gcsim_frame = QFrame()
        gcsim_frame.setObjectName("InfoBlock")
        gcsim_layout = QVBoxLayout(gcsim_frame)
        gcsim_layout.setContentsMargins(8, 8, 8, 8)
        gcsim_layout.setSpacing(8)

        self.gcsim_label = QLabel(tr("settings.gcsim.title"))
        self.gcsim_label.setObjectName("SectionTitle")
        gcsim_layout.addWidget(self.gcsim_label)

        gcsim_toggle_row = QHBoxLayout()
        gcsim_toggle_row.setContentsMargins(0, 0, 0, 0)
        gcsim_toggle_row.setSpacing(8)
        gcsim_text_col = QVBoxLayout()
        gcsim_text_col.setContentsMargins(0, 0, 0, 0)
        gcsim_text_col.setSpacing(2)
        self.gcsim_boosted_energy_label = QLabel(
            tr("settings.gcsim.boosted_energy")
        )
        self.gcsim_boosted_energy_description = QLabel(
            tr("settings.gcsim.boosted_energy.description")
        )
        self.gcsim_boosted_energy_description.setWordWrap(True)
        gcsim_text_col.addWidget(self.gcsim_boosted_energy_label)
        gcsim_text_col.addWidget(self.gcsim_boosted_energy_description)
        self.gcsim_boosted_energy_switch = ToggleSwitch()
        self.gcsim_boosted_energy_switch.setChecked(
            is_gcsim_boosted_energy_enabled(settings_file=self._settings_file)
        )
        self.gcsim_boosted_energy_switch.toggled.connect(
            self.on_gcsim_boosted_energy_changed
        )
        gcsim_toggle_row.addLayout(gcsim_text_col, 1)
        gcsim_toggle_row.addWidget(self.gcsim_boosted_energy_switch)
        gcsim_layout.addLayout(gcsim_toggle_row)
        self._boosted_energy_label_tooltip = install_custom_tooltip(
            self.gcsim_boosted_energy_label,
            lambda: tr("settings.gcsim.boosted_energy.description"),
        )
        self._boosted_energy_switch_tooltip = install_custom_tooltip(
            self.gcsim_boosted_energy_switch,
            lambda: tr("settings.gcsim.boosted_energy.description"),
        )

        optimizer_settings = effective_gcsim_optimizer_settings(
            settings_file=self._settings_file
        )
        group_max, build_max = optimizer_output_limits(optimizer_settings.fast_mode, optimizer_settings.expanded_limits)
        self._optimizer_heavy_notice = False
        self.gcsim_optimizer_limits_note = QLabel(tr("settings.gcsim.optimizer.output_limits"))
        self.gcsim_optimizer_limits_note.setWordWrap(True)
        gcsim_layout.addWidget(self.gcsim_optimizer_limits_note)
        self.gcsim_optimizer_set_group_limit_label = QLabel(
            tr("settings.gcsim.optimizer.set_group_limit")
        )
        self.gcsim_optimizer_set_group_limit_spin = QSpinBox()
        self.gcsim_optimizer_set_group_limit_spin.setObjectName(
            "gcsimOptimizerSetGroupLimit"
        )
        self.gcsim_optimizer_set_group_limit_spin.setRange(1, group_max)
        self.gcsim_optimizer_set_group_limit_spin.setValue(
            optimizer_settings.set_group_limit
        )
        self.gcsim_optimizer_set_group_limit_spin.setFixedWidth(64)
        self.gcsim_optimizer_set_group_limit_spin.valueChanged.connect(
            self.on_gcsim_optimizer_set_group_limit_changed
        )
        group_limit_row = QHBoxLayout()
        group_limit_row.setContentsMargins(0, 0, 0, 0)
        group_limit_row.setSpacing(8)
        group_limit_row.addWidget(self.gcsim_optimizer_set_group_limit_label, 1)
        group_limit_row.addWidget(self.gcsim_optimizer_set_group_limit_spin)
        gcsim_layout.addLayout(group_limit_row)

        self.gcsim_optimizer_builds_per_group_label = QLabel(
            tr("settings.gcsim.optimizer.builds_per_group")
        )
        self.gcsim_optimizer_builds_per_group_spin = QSpinBox()
        self.gcsim_optimizer_builds_per_group_spin.setObjectName(
            "gcsimOptimizerBuildsPerGroup"
        )
        self.gcsim_optimizer_builds_per_group_spin.setRange(0, build_max - 1)
        self.gcsim_optimizer_builds_per_group_spin.setValue(
            optimizer_settings.builds_per_group - 1
        )
        self.gcsim_optimizer_builds_per_group_spin.setFixedWidth(64)
        self.gcsim_optimizer_builds_per_group_spin.valueChanged.connect(
            self.on_gcsim_optimizer_builds_per_group_changed
        )
        builds_per_group_row = QHBoxLayout()
        builds_per_group_row.setContentsMargins(0, 0, 0, 0)
        builds_per_group_row.setSpacing(8)
        builds_per_group_row.addWidget(
            self.gcsim_optimizer_builds_per_group_label, 1
        )
        builds_per_group_row.addWidget(self.gcsim_optimizer_builds_per_group_spin)
        gcsim_layout.addLayout(builds_per_group_row)

        fast_mode_row = QHBoxLayout()
        fast_mode_row.setContentsMargins(0, 0, 0, 0)
        fast_mode_row.setSpacing(8)
        self.gcsim_optimizer_fast_mode_label = QLabel(
            tr("settings.gcsim.optimizer.fast_mode")
        )
        self.gcsim_optimizer_fast_mode_help = QLabel("?")
        self.gcsim_optimizer_fast_mode_help.setObjectName("gcsimOptimizerFastModeHelp")
        self.gcsim_optimizer_fast_mode_help.setFixedSize(20, 20)
        self.gcsim_optimizer_fast_mode_help.setAlignment(Qt.AlignCenter)
        self.gcsim_optimizer_fast_mode_help.setStyleSheet(
            f"QLabel {{ color: {UI_TEXT_MUTED}; border: 1px solid {UI_BORDER_DEFAULT}; "
            "border-radius: 10px; padding: 0; font-size: 12px; font-weight: 600; }"
        )
        self.gcsim_optimizer_fast_mode_help.setAccessibleName(
            tr("settings.gcsim.optimizer.fast_mode")
        )
        self.gcsim_optimizer_fast_mode_help.setAccessibleDescription(
            tr("settings.gcsim.optimizer.fast_mode.tooltip")
        )
        self.gcsim_optimizer_fast_mode_tooltip = install_custom_tooltip(
            self.gcsim_optimizer_fast_mode_help,
            lambda: tr("settings.gcsim.optimizer.fast_mode.tooltip"),
        )
        self.gcsim_optimizer_fast_mode_switch = ToggleSwitch()
        self.gcsim_optimizer_fast_mode_switch.setObjectName(
            "gcsimOptimizerFastMode"
        )
        self.gcsim_optimizer_fast_mode_switch.setChecked(
            optimizer_settings.fast_mode
        )
        self.gcsim_optimizer_fast_mode_switch.toggled.connect(
            self.on_gcsim_optimizer_fast_mode_changed
        )
        fast_mode_row.addWidget(self.gcsim_optimizer_fast_mode_label)
        fast_mode_row.addWidget(self.gcsim_optimizer_fast_mode_help)
        fast_mode_row.addStretch(1)
        fast_mode_row.addWidget(self.gcsim_optimizer_fast_mode_switch)
        gcsim_layout.addLayout(fast_mode_row)
        self.gcsim_optimizer_expanded_limits_checkbox = QCheckBox(
            tr("settings.gcsim.optimizer.expanded_limits")
        )
        self.gcsim_optimizer_expanded_limits_checkbox.setObjectName("gcsimOptimizerExpandedLimits")
        self.gcsim_optimizer_expanded_limits_checkbox.setChecked(optimizer_settings.expanded_limits)
        self.gcsim_optimizer_expanded_limits_checkbox.toggled.connect(
            self.on_gcsim_optimizer_expanded_limits_changed
        )
        gcsim_layout.addWidget(self.gcsim_optimizer_expanded_limits_checkbox)
        self.gcsim_optimizer_expanded_limits_note = QLabel(tr("settings.gcsim.optimizer.expanded_limits_note"))
        self.gcsim_optimizer_expanded_limits_note.setWordWrap(True)
        self.gcsim_optimizer_expanded_limits_note.setVisible(optimizer_settings.expanded_limits)
        gcsim_layout.addWidget(self.gcsim_optimizer_expanded_limits_note)
        content_layout.addWidget(gcsim_frame)

        pvp_frame = QFrame()
        pvp_frame.setObjectName("InfoBlock")
        pvp_layout = QVBoxLayout(pvp_frame)
        pvp_layout.setContentsMargins(8, 8, 8, 8)
        pvp_layout.setSpacing(8)
        self.pvp_settings_label = QLabel(tr("settings.pvp.title"))
        self.pvp_settings_label.setObjectName("SectionTitle")
        pvp_layout.addWidget(self.pvp_settings_label)
        self.pvp_color_labels: dict[str, QLabel] = {}
        self.pvp_color_buttons: dict[str, QPushButton] = {}
        for seat in ("player_1", "player_2"):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            label = QLabel(
                tr("settings.pvp.player_color").format(
                    player=1 if seat == "player_1" else 2
                )
            )
            button = QPushButton()
            button.setObjectName("pvp_color_swatch")
            button.setMinimumWidth(104)
            button.clicked.connect(
                lambda _checked=False, current_seat=seat: self.choose_pvp_player_color(
                    current_seat
                )
            )
            self.pvp_color_labels[seat] = label
            self.pvp_color_buttons[seat] = button
            row.addWidget(label, 1)
            row.addWidget(button)
            pvp_layout.addLayout(row)
        self.pvp_colors_reset_button = QPushButton(tr("settings.pvp.colors_reset"))
        self.pvp_colors_reset_button.setObjectName("GhostButton")
        self.pvp_colors_reset_button.clicked.connect(self.reset_pvp_colors)
        pvp_layout.addWidget(self.pvp_colors_reset_button)
        content_layout.addWidget(pvp_frame)
        self._refresh_pvp_color_controls()
        content_layout.addStretch(1)

    def _dialog_parent(self) -> QWidget:
        return self.window() or self

    def refresh_hoyolab_auth_status(self) -> None:
        self._update_hoyolab_recovery_status()
        self.account_profiles.refresh()
        status = get_auth_status(HOYOLAB_PROFILE_DIR)
        current = active_profile() if PROFILE_ID else None
        imported = bool(current and current["imported"]) if PROFILE_ID else has_local_hoyolab_profile()
        busy = self._hoyolab_export_process is not None or self._hoyolab_login_process is not None
        self.account_profiles.setEnabled(not busy)
        self.btn_clear_all.setEnabled(not busy)
        self.btn_profile_menu.setEnabled(not busy)
        self.btn_hoyolab_login.setEnabled(not busy and status != AuthStatus.PROFILE_LOCKED)
        self.btn_hoyolab_login.setText(tr("accounts.login"))
        self.btn_hoyolab_export.setText(
            tr("accounts.update_data") if imported else tr("accounts.import_data")
        )
        self.btn_hoyolab_export.setEnabled(not busy and status != AuthStatus.PROFILE_LOCKED)
        self._hoyolab_export_tooltip.set_text(
            tr("hoyolab.import_running_tooltip") if busy else ""
        )
        self.btn_images_refresh.setEnabled(not busy and imported)
        self.change_equipment_switch.setEnabled(not busy)
        if status == AuthStatus.PROFILE_LOCKED and not busy:
            QTimer.singleShot(2000, self.refresh_hoyolab_auth_status)

    def _update_hoyolab_recovery_status(self) -> None:
        label = getattr(self, "hoyolab_recovery_status", None)
        if label is None:
            return
        if self._hoyolab_export_process is not None:
            label.clear()
            label.hide()
            return
        recovery = self._find_hoyolab_recovery()
        if recovery is None:
            label.clear()
            label.hide()
            return
        _attempt, committed = recovery
        key = (
            "hoyolab.recovery.status_committed"
            if committed else "hoyolab.recovery.status_saved"
        )
        label.setText(tr(key))
        label.show()

    def ask_open_hoyolab_login(self) -> bool:
        options = {"settings_file": self._settings_file} if self._settings_file is not None else {}
        if get_app_bool_setting("hoyolab_login_hint_dismissed", **options):
            return True
        box = QMessageBox(self._dialog_parent())
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(tr("accounts.login"))
        box.setText(tr("accounts.login_hint"))
        checkbox = QCheckBox(tr("accounts.dont_show_again"), box)
        box.setCheckBox(checkbox)
        understood = box.addButton(tr("accounts.understood"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("common.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        accepted = box.clickedButton() == understood
        if accepted and checkbox.isChecked():
            set_app_bool_setting("hoyolab_login_hint_dismissed", True, **options)
        return accepted

    def login_requested(self) -> None:
        if (self._hoyolab_export_process is None and self._hoyolab_login_process is None
                and self.ask_open_hoyolab_login()):
            self.open_hoyolab_login()

    def open_hoyolab_login(self) -> None:
        if self._hoyolab_login_process is not None:
            return
        try:
            self._hoyolab_login_screen = QApplication.primaryScreen() or self.screen()
            geometry = (
                self._hoyolab_login_screen.availableGeometry()
                if self._hoyolab_login_screen is not None
                else None
            )
            self._hoyolab_login_process = open_login_browser(
                HOYOLAB_PROFILE_DIR,
                x=geometry.left() + 40 if geometry is not None else None,
                y=geometry.top() + 40 if geometry is not None else None,
            )
        except Exception as exc:
            self._hoyolab_login_screen = None
            QMessageBox.warning(
                self._dialog_parent(),
                tr("common.hoyolab"),
                tr("hoyolab.open_browser_failed", error=exc),
            )
            return

        self.refresh_hoyolab_auth_status()
        self._show_hoyolab_login_hint()
        self._hoyolab_auth_timer.start()

    def _show_hoyolab_login_hint(self) -> None:
        if self._hoyolab_login_hint is not None:
            self._hoyolab_login_hint.raise_()
            self._hoyolab_login_hint.set_target_screen(self._hoyolab_login_screen)
            self._hoyolab_login_hint.position_on_screen()
            return
        self._hoyolab_login_hint = HoYoLABLoginHintOverlay(
            self._dialog_parent(),
            target_screen=self._hoyolab_login_screen,
        )
        self._hoyolab_login_hint.show()
        self._hoyolab_login_hint.raise_()

    def _close_hoyolab_login_hint(self) -> None:
        if self._hoyolab_login_hint is None:
            return
        hint = self._hoyolab_login_hint
        self._hoyolab_login_hint = None
        hint.close()
        hint.deleteLater()

    def poll_hoyolab_login_browser(self) -> None:
        if self._hoyolab_login_process is None:
            self._hoyolab_auth_timer.stop()
            self._hoyolab_login_screen = None
            self._close_hoyolab_login_hint()
            self.refresh_hoyolab_auth_status()
            return
        if self._hoyolab_login_process.poll() is None:
            if self._hoyolab_login_hint is not None:
                self._hoyolab_login_hint.position_on_screen()
            return
        self._hoyolab_login_process = None
        self._hoyolab_login_screen = None
        self._hoyolab_auth_timer.stop()
        self._close_hoyolab_login_hint()
        self.refresh_hoyolab_auth_status()

    def change_hoyolab_account(self) -> None:
        self._request_profile_operation("new", "")

    def _confirm_profile_action(self, title: str, message: str) -> bool:
        box = QMessageBox(self._dialog_parent())
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(message)
        yes = box.addButton(tr("common.yes"), QMessageBox.ButtonRole.YesRole)
        no = box.addButton(tr("common.no"), QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(no)
        box.setEscapeButton(no)
        box.exec()
        return box.clickedButton() == yes

    def _request_profile_operation(self, operation: str, profile_id: str) -> None:
        if self._hoyolab_export_process is not None or self._hoyolab_login_process is not None:
            QMessageBox.information(self._dialog_parent(), tr("common.hoyolab"),
                                    tr("accounts.busy"))
            return
        if get_auth_status(HOYOLAB_PROFILE_DIR) == AuthStatus.PROFILE_LOCKED:
            QMessageBox.information(self._dialog_parent(), tr("common.hoyolab"),
                                    tr("hoyolab.close_browser_before_switch"))
            return
        if operation in {"delete", "reset"}:
            message = tr("accounts.reset_confirm") if operation == "reset" else tr("accounts.delete_confirm")
            if not self._confirm_profile_action(
                tr("accounts.clear_all") if operation == "reset" else tr("accounts.delete"), message,
            ):
                return
        self.profile_operation_requested.emit(operation, profile_id)

    def _find_hoyolab_recovery(self) -> tuple[dict, bool] | None:
        """Return the newest safe-to-replay source or committed unfinished receipt."""
        try:
            pending = list_pending_import_attempts(ARTIFACT_DB_PATH)
        except Exception:
            pending = []
        if pending:
            return pending[0], False
        try:
            latest = latest_committed_import(ARTIFACT_DB_PATH)
        except Exception:
            latest = None
        if not isinstance(latest, dict) or latest.get("status") != "committed":
            return None
        enrichment = latest.get("enrichment")
        enrichment = enrichment if isinstance(enrichment, dict) else {}
        if any(
            not isinstance(enrichment.get(kind), dict)
            or enrichment[kind].get("status") != "complete"
            for kind in HOYOLAB_RECOVERY_ENRICHMENT_KINDS
        ):
            return latest, True
        return None

    def _ask_hoyolab_recovery(self, attempt: dict, *, committed: bool) -> str | None:
        box = QMessageBox(self._dialog_parent())
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(tr("hoyolab.recovery.title"))
        uid = str(attempt.get("account_uid") or "")
        server = str(attempt.get("server") or "")
        text_key = (
            "hoyolab.recovery.committed_prompt"
            if committed else "hoyolab.recovery.saved_prompt"
        )
        box.setText(tr(text_key, uid=uid, server=server))
        resume_button = box.addButton(
            tr("hoyolab.recovery.resume"), QMessageBox.ButtonRole.AcceptRole
        )
        new_button = box.addButton(
            tr("hoyolab.recovery.new_import"), QMessageBox.ButtonRole.DestructiveRole
        )
        cancel_button = box.addButton(
            tr("common.cancel"), QMessageBox.ButtonRole.RejectRole
        )
        box.setEscapeButton(cancel_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked == resume_button:
            return "resume"
        if clicked == new_button:
            return "new"
        return None

    def run_hoyolab_export(self, images_only: bool = False) -> None:
        if self._hoyolab_export_process is not None or self._hoyolab_login_process is not None:
            return

        resume_attempt = None
        if not images_only:
            recovery = self._find_hoyolab_recovery()
            if recovery is not None:
                attempt, committed = recovery
                choice = self._ask_hoyolab_recovery(attempt, committed=committed)
                if choice == "resume":
                    resume_attempt = str(attempt.get("attempt_id") or "") or None
                    if resume_attempt is None:
                        return
                elif choice != "new":
                    return

        # A staged snapshot and images-only refresh both use saved source data;
        # neither needs the HoYoLAB browser profile.
        if not images_only and resume_attempt is None:
            if get_auth_status(HOYOLAB_PROFILE_DIR) != AuthStatus.LOGGED_IN:
                QMessageBox.information(self._dialog_parent(), tr("accounts.login"),
                                        tr("accounts.login_first"))
                self.refresh_hoyolab_auth_status()
                return

        self._start_hoyolab_import_process(
            images_only=images_only,
            attempt_id=str(uuid.uuid4()) if not images_only and resume_attempt is None else None,
            resume_attempt=resume_attempt,
            change_equipment=(
                not images_only and resume_attempt is None
                and self.change_equipment_switch.isChecked()
            ),
        )

    def _start_hoyolab_import_process(
        self, *, images_only: bool = False, attempt_id: str | None = None,
        resume_attempt: str | None = None, adopt_legacy: bool = False,
        change_equipment: bool = False,
    ) -> None:
        if self._hoyolab_export_process is not None or self._hoyolab_login_process is not None:
            return
        self._show_hoyolab_loader(images_only=images_only)
        process = QProcess(self)
        process.setProgram(sys.executable)
        arguments = ["-m", "hoyolab_export.run_import"]
        if images_only:
            arguments.append("--images-only")
        elif resume_attempt:
            arguments.extend(["--resume-attempt", resume_attempt])
            if adopt_legacy:
                arguments.append("--adopt-legacy")
        else:
            attempt_id = attempt_id or str(uuid.uuid4())
            arguments.extend(["--attempt-id", attempt_id])
            if change_equipment:
                arguments.append("--change-equipment")
        process.setArguments(arguments)
        process.setWorkingDirectory(str(PROJECT_ROOT))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self.read_hoyolab_import_output)
        process.finished.connect(
            lambda code, status: self._on_hoyolab_process_finished(process, code, status)
        )
        self._hoyolab_export_process = process
        self._hoyolab_attempt_id = resume_attempt or attempt_id
        self._hoyolab_committed_attempt_id = None
        self._hoyolab_binding_required = None
        self._duplicate_profile_id = None
        self._hoyolab_images_only = images_only
        self._hoyolab_import_output_buffer = ""
        self._hoyolab_import_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._hoyolab_import_lines = []
        self._hoyolab_import_warnings = []
        self._hoyolab_last_progress = 0.03
        self.hoyolab_recovery_status.hide()
        self.btn_hoyolab_export.setEnabled(False)
        self.btn_images_refresh.setEnabled(False)
        self.btn_profile_menu.setEnabled(False)
        self.account_profiles.setEnabled(False)
        self.btn_hoyolab_login.setEnabled(False)
        self.btn_clear_all.setEnabled(False)
        self.change_equipment_switch.setEnabled(False)
        self._hoyolab_export_tooltip.set_text(tr("hoyolab.import_running_tooltip"))
        process.start()
        if not process.waitForStarted(3000):
            if self._hoyolab_export_process is not process:
                return
            self._hoyolab_export_process = None
            process.deleteLater()
            self._reset_hoyolab_process_state()
            self._close_hoyolab_loader()
            self.refresh_hoyolab_auth_status()
            QMessageBox.warning(
                self._dialog_parent(),
                tr("common.hoyolab"),
                tr("hoyolab.start_import_failed"),
            )

    def _reset_hoyolab_process_state(self) -> None:
        self._hoyolab_attempt_id = None
        self._hoyolab_committed_attempt_id = None
        self._hoyolab_binding_required = None
        self._hoyolab_images_only = False
        self._hoyolab_import_decoder = None
        self._hoyolab_import_output_buffer = ""

    def _confirm_hoyolab_legacy_binding(self, binding: dict) -> bool:
        answer = QMessageBox.question(
            self._dialog_parent(),
            tr("hoyolab.legacy_binding.title"),
            tr(
                "hoyolab.legacy_binding.prompt",
                uid=binding["account_uid"],
                server=binding["server"],
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _show_hoyolab_loader(self, *, images_only=False) -> None:
        if self._hoyolab_loader is not None:
            self._hoyolab_loader.raise_()
            self._hoyolab_loader.activateWindow()
            return
        self._hoyolab_loader = HoYoLABLoadingDialog(self._dialog_parent())
        self._hoyolab_loader.set_status(tr("loader.preparing"), 0.03)
        kinds = ("assets",) if images_only else ("projections", "assets", "references", "side_icons", "abyss")
        self._hoyolab_loader.set_details("\n".join(
            tr("loader.job." + kind) + ": " + tr("loader.work.waiting") for kind in kinds
        ))
        self._hoyolab_loader.show()
        self._hoyolab_loader.raise_()
        self._hoyolab_loader.activateWindow()

    def _close_hoyolab_loader(self) -> None:
        if self._hoyolab_loader is None:
            return
        loader = self._hoyolab_loader
        self._hoyolab_loader = None
        loader.close()
        loader.deleteLater()

    def _set_hoyolab_loader_status(self, status: str) -> None:
        if self._hoyolab_loader is None:
            return
        text_key, progress = HOYOLAB_IMPORT_STATUSES.get(
            status,
            ("loader.unknown_status", None),
        )
        if progress is not None:
            self._hoyolab_last_progress = max(self._hoyolab_last_progress, progress)
        self._hoyolab_loader.set_status(
            tr(text_key, status=status), self._hoyolab_last_progress
        )

    def read_hoyolab_import_output(self, *, final: bool = False) -> None:
        process = self._hoyolab_export_process
        if process is None:
            return
        raw = bytes(process.readAllStandardOutput())
        decoder = self._hoyolab_import_decoder
        if decoder is None:
            chunk = raw.decode("utf-8", errors="replace")
        else:
            chunk = decoder.decode(raw, final=final)
            if final:
                self._hoyolab_import_decoder = None
        if not chunk:
            return
        self._hoyolab_import_output_buffer += chunk
        while "\n" in self._hoyolab_import_output_buffer:
            line, self._hoyolab_import_output_buffer = (
                self._hoyolab_import_output_buffer.split("\n", 1)
            )
            line = line.rstrip("\r")
            if line:
                self._consume_hoyolab_import_line(line)

    def _consume_hoyolab_import_line(self, line: str) -> None:
        if line.startswith("[PROFILE_DUPLICATE] "):
            try:
                value = json.loads(line[len("[PROFILE_DUPLICATE] "):]).get("existing_profile_id")
                if isinstance(value, str) and len(value) == 32 and all(c in "0123456789abcdef" for c in value):
                    self._duplicate_profile_id = value
            except (ValueError, TypeError, AttributeError):
                pass
            return
        if line.startswith("[IMPORT_PROGRESS] "):
            self._record_hoyolab_progress(line)
            return
        print(line)
        self._hoyolab_import_lines.append(line)
        self._record_hoyolab_import_warning(line)
        self._record_hoyolab_binding_required(line)
        self._record_hoyolab_commit(line)
        if line.startswith("[STATUS] "):
            self._set_hoyolab_loader_status(line.replace("[STATUS] ", "", 1).strip())

    def _record_hoyolab_progress(self, line: str) -> None:
        from math import isfinite
        from hoyolab_export.import_progress import JOB_PHASES

        if self._hoyolab_loader is None:
            return
        try:
            payload = json.loads(line[len("[IMPORT_PROGRESS] "):])
            if not isinstance(payload, dict) or payload.get("attempt_id") != self._hoyolab_attempt_id:
                return
            progress = float(payload["progress"])
            jobs = payload["jobs"]
            if not isfinite(progress) or not 0 <= progress <= 0.98 or not isinstance(jobs, dict):
                return
            lines = []
            for kind, phases in JOB_PHASES.items():
                if kind not in jobs:
                    continue
                job = jobs[kind]
                state, phase = job["state"], job["phase"]
                if state not in {"waiting", "running", "complete", "pending"} or phase not in phases:
                    return
                completed, total = job["completed"], job["total"]
                if (type(completed) is not int or type(total) is not int
                        or not 0 <= completed <= total):
                    return
                detail = tr("loader.work." + (phase if state == "running" else state))
                if state == "running" and total:
                    detail += f" · {completed}/{total}"
                steps = job.get("steps", {})
                if not isinstance(steps, dict):
                    return
                active = []
                if state == "running":
                    for step_name in phases:
                        step = steps.get(step_name, {})
                        if not isinstance(step, dict):
                            return
                        if step.get("state") != "running":
                            continue
                        count, size = step.get("completed"), step.get("total")
                        if type(count) is not int or type(size) is not int or not 0 <= count <= size:
                            return
                        text = tr("loader.work." + step_name)
                        active.append(text + (f" · {count}/{size}" if size else ""))
                if active:
                    detail = "; ".join(active)
                lines.append(tr("loader.job." + kind) + ": " + detail)
        except (ValueError, TypeError, KeyError, OverflowError):
            return
        if not lines:
            return
        self._hoyolab_last_progress = max(self._hoyolab_last_progress, progress)
        title = "loader.downloading_assets" if self._hoyolab_images_only else "loader.enriching_account"
        self._hoyolab_loader.set_status(tr(title), self._hoyolab_last_progress)
        self._hoyolab_loader.set_details("\n".join(lines))

    def _record_hoyolab_binding_required(self, line: str) -> None:
        prefix = "[IMPORT_BINDING_REQUIRED] "
        if not line.startswith(prefix):
            return
        try:
            binding = json.loads(line[len(prefix):])
        except (ValueError, TypeError):
            return
        if not isinstance(binding, dict):
            return
        attempt_id = binding.get("attempt_id")
        uid = binding.get("account_uid")
        server = binding.get("server")
        if (not isinstance(attempt_id, str) or not attempt_id
                or attempt_id != self._hoyolab_attempt_id
                or not str(uid or "").isdigit()
                or not isinstance(server, str) or not server.strip()):
            return
        self._hoyolab_binding_required = {
            "attempt_id": attempt_id,
            "account_uid": str(uid),
            "server": server.strip(),
        }

    def _record_hoyolab_commit(self, line: str) -> None:
        prefix = "[IMPORT_COMMITTED] "
        if not line.startswith(prefix):
            return
        try:
            receipt = json.loads(line[len(prefix):])
        except (ValueError, TypeError):
            return
        attempt_id = receipt.get("attempt_id") if isinstance(receipt, dict) else None
        if not isinstance(attempt_id, str) or attempt_id != self._hoyolab_attempt_id:
            return
        if self._hoyolab_committed_attempt_id == attempt_id:
            return
        self._hoyolab_committed_attempt_id = attempt_id
        self.account_profiles.refresh()
        # This receipt is written immediately after SQLite commits. Refresh the
        # account view now, then refresh once more when optional enrichment ends.
        self.account_data_changed.emit(False)

    def _record_hoyolab_import_warning(self, line: str) -> None:
        if not line.startswith("[IMPORT_WARNING] "):
            return
        try:
            warning = json.loads(line[len("[IMPORT_WARNING] "):])
        except (ValueError, TypeError):
            return
        if (isinstance(warning, dict) and isinstance(warning.get("code"), str)
                and warning["code"] in HOYOLAB_IMPORT_WARNING_KEYS
                and warning not in self._hoyolab_import_warnings):
            self._hoyolab_import_warnings.append(warning)

    def _hoyolab_import_warning_details(self) -> str:
        messages = []
        for warning in self._hoyolab_import_warnings:
            count = warning.get("count", 0)
            count = count if type(count) is int and count >= 0 else 0
            message = tr(HOYOLAB_IMPORT_WARNING_KEYS[warning["code"]], count=count)
            sets = warning.get("sets")
            sets = sets if isinstance(sets, list) else []
            names = [str(item.get("name") or item.get("hoyolab_set_id") or "")[:100]
                     for item in sets[:3] if isinstance(item, dict)]
            if names:
                message += " " + tr("hoyolab.import_warning.set_names", names=", ".join(names))
            messages.append(message)
        return "\n".join(messages)

    def _hoyolab_import_error_details(self) -> str:
        lines = [
            line
            for line in self._hoyolab_import_lines
            if line and not line.startswith("[STATUS] ")
        ]
        return "\n".join(lines[-8:])

    def _on_hoyolab_process_finished(self, process, exit_code, exit_status) -> None:
        # A delayed signal from a previous run must never finish the current run.
        if self._hoyolab_export_process is process:
            self.on_hoyolab_import_finished(exit_code, exit_status)

    def on_hoyolab_import_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        process = self._hoyolab_export_process
        if process is None:
            return
        self.read_hoyolab_import_output(final=True)
        if self._hoyolab_import_output_buffer.strip():
            line = self._hoyolab_import_output_buffer.strip()
            self._consume_hoyolab_import_line(line)
            self._hoyolab_import_output_buffer = ""
        attempt_id = self._hoyolab_attempt_id
        binding = self._hoyolab_binding_required
        duplicate_profile_id = self._duplicate_profile_id
        committed_marker = self._hoyolab_committed_attempt_id == attempt_id and attempt_id is not None
        images_only = self._hoyolab_images_only
        process.deleteLater()
        self._hoyolab_export_process = None
        if duplicate_profile_id:
            self._close_hoyolab_loader()
            self._reset_hoyolab_process_state()
            self.refresh_hoyolab_auth_status()
            if self._confirm_profile_action(tr("app_shell.account.title"), tr("accounts.duplicate")):
                self._request_profile_operation("activate", duplicate_profile_id)
            return
        receipt = None
        if attempt_id:
            try:
                receipt = get_import_result(ARTIFACT_DB_PATH, attempt_id)
            except Exception:
                receipt = None
        committed_result = (
            isinstance(receipt, dict) and receipt.get("status") == "committed"
        )
        if committed_result or committed_marker:
            if self._hoyolab_loader is not None:
                self._hoyolab_loader.finish()
            self.account_data_changed.emit(False)
            self._close_hoyolab_loader()
            self._reset_hoyolab_process_state()
            self.refresh_hoyolab_auth_status()
            if (exit_code != 0 or exit_status != QProcess.ExitStatus.NormalExit):
                QMessageBox.information(
                    self._dialog_parent(), tr("common.done"),
                    tr("hoyolab.import_committed_after_crash"),
                )
            if self._hoyolab_import_warnings:
                QMessageBox.warning(
                    self._dialog_parent(), tr("hoyolab.import_warning.title"),
                    self._hoyolab_import_warning_details(),
                )
            return

        if binding is not None and exit_code == 3:
            self._close_hoyolab_loader()
            self._reset_hoyolab_process_state()
            self.refresh_hoyolab_auth_status()
            if self._confirm_hoyolab_legacy_binding(binding):
                self._start_hoyolab_import_process(
                    resume_attempt=binding["attempt_id"], adopt_legacy=True,
                )
            else:
                QMessageBox.information(
                    self._dialog_parent(), tr("hoyolab.legacy_binding.title"),
                    tr("hoyolab.legacy_binding.deferred"),
                )
            return

        if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit and images_only:
            if self._hoyolab_loader is not None:
                self._hoyolab_loader.finish()
            self.account_data_changed.emit(False)
            self._close_hoyolab_loader()
            self._reset_hoyolab_process_state()
            self.refresh_hoyolab_auth_status()
            return

        self._close_hoyolab_loader()
        self._reset_hoyolab_process_state()
        self.refresh_hoyolab_auth_status()
        QMessageBox.warning(
            self._dialog_parent(),
            tr("common.hoyolab"),
            tr(
                "hoyolab.import_failed_with_details",
                details=self._hoyolab_import_error_details() or tr("hoyolab.import_failed"),
            ),
        )

    def export_profile(self, *, show_success: bool = True) -> bool:
        if self._hoyolab_export_process is not None or self._hoyolab_login_process is not None:
            return False
        path, _selected_filter = QFileDialog.getSaveFileName(
            self._dialog_parent(),
            tr("profile.export_dialog_title"),
            str(PROJECT_ROOT / "exports" / "hoyolab_offline_profile.zip"),
            tr("profile.zip_filter"),
        )
        if not path:
            return False
        try:
            result = export_offline_profile(path)
        except Exception as exc:
            QMessageBox.warning(
                self._dialog_parent(),
                tr("common.hoyolab"),
                tr("profile.export_failed", error=exc),
            )
            return False
        if show_success:
            QMessageBox.information(
                self._dialog_parent(),
                tr("common.done"),
                tr("profile.export_done", count=len(result.get("includedFiles") or [])),
            )
        self.refresh_hoyolab_auth_status()
        return True

    def import_profile(self) -> bool:
        if self._hoyolab_export_process is not None or self._hoyolab_login_process is not None:
            return False
        path, _selected_filter = QFileDialog.getOpenFileName(
            self._dialog_parent(),
            tr("profile.import_dialog_title"),
            str(PROJECT_ROOT / "exports"),
            tr("profile.zip_filter"),
        )
        if not path:
            return False
        try:
            from hoyolab_export.profile_restore import restore_saved_profile
            result = restore_saved_profile(path)
        except Exception as exc:
            QMessageBox.warning(
                self._dialog_parent(),
                tr("common.hoyolab"),
                tr("profile.import_failed", error=exc),
            )
            return False
        self._request_profile_operation("activate", result["profile"]["id"])
        return True

    def _sync_language_combo(self) -> None:
        self._updating_language_combo = True
        index = self.language_combo.findData(get_language())
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        self._updating_language_combo = False

    def on_language_changed(self, index: int) -> None:
        if self._updating_language_combo or index < 0:
            return
        language = self.language_combo.itemData(index)
        if not language:
            return
        set_language(str(language), persist=True)
        self.retranslate_ui()
        self.language_changed.emit()

    def on_fact_dps_multi_target_changed(self, enabled: bool) -> None:
        set_abyss_fact_dps_multi_target_enabled(
            bool(enabled),
            settings_file=self._settings_file,
        )
        self.fact_dps_multi_target_changed.emit(bool(enabled))

    def on_gcsim_boosted_energy_changed(self, enabled: bool) -> None:
        set_gcsim_boosted_energy_enabled(
            bool(enabled),
            settings_file=self._settings_file,
        )
        self.gcsim_boosted_energy_changed.emit(bool(enabled))

    def on_gcsim_optimizer_set_group_limit_changed(self, value: int) -> None:
        set_gcsim_optimizer_set_group_limit(
            value,
            settings_file=self._settings_file,
        )
        self._warn_optimizer_output_work()

    def on_gcsim_optimizer_builds_per_group_changed(self, value: int) -> None:
        set_gcsim_optimizer_builds_per_group(
            value + 1,
            settings_file=self._settings_file,
        )
        self._warn_optimizer_output_work()

    def _warn_optimizer_output_work(self) -> None:
        settings = effective_gcsim_optimizer_settings(settings_file=self._settings_file)
        heavy = not settings.fast_mode and settings.set_group_limit * settings.builds_per_group > 12
        if heavy and not self._optimizer_heavy_notice and not self._suppress_optimizer_fast_mode_warning:
            QMessageBox.warning(
                self._dialog_parent(),
                tr("settings.gcsim.optimizer.output_work.title"),
                tr("settings.gcsim.optimizer.output_work.body"),
            )
        self._optimizer_heavy_notice = heavy

    def _refresh_optimizer_output_limits(self) -> None:
        settings = effective_gcsim_optimizer_settings(settings_file=self._settings_file)
        group_max, build_max = optimizer_output_limits(settings.fast_mode, settings.expanded_limits)
        for spin, minimum, maximum, value in (
            (self.gcsim_optimizer_set_group_limit_spin, 1, group_max, settings.set_group_limit),
            (self.gcsim_optimizer_builds_per_group_spin, 0, build_max - 1, settings.builds_per_group - 1),
        ):
            previous = spin.blockSignals(True)
            spin.setRange(minimum, maximum)
            spin.setValue(value)
            spin.blockSignals(previous)
        self._warn_optimizer_output_work()

    def on_gcsim_optimizer_expanded_limits_changed(self, enabled: bool) -> None:
        set_gcsim_optimizer_expanded_limits_enabled(enabled, settings_file=self._settings_file)
        self.gcsim_optimizer_expanded_limits_note.setVisible(enabled)
        self._refresh_optimizer_output_limits()

    def on_gcsim_optimizer_fast_mode_changed(self, enabled: bool) -> None:
        set_gcsim_optimizer_fast_mode_enabled(
            enabled,
            settings_file=self._settings_file,
        )
        self._refresh_optimizer_output_limits()
        if enabled and not self._suppress_optimizer_fast_mode_warning:
            QMessageBox.warning(
                self._dialog_parent(),
                tr("settings.gcsim.optimizer.fast_mode.warning_title"),
                tr("settings.gcsim.optimizer.fast_mode.warning_body"),
            )

    def set_gcsim_optimizer_fast_mode_enabled(self, enabled: bool) -> None:
        """Restore the shared fast-mode switch without showing its warning."""

        normalized = bool(enabled)
        self._suppress_optimizer_fast_mode_warning = True
        try:
            self.gcsim_optimizer_fast_mode_switch.setChecked(normalized)
        finally:
            self._suppress_optimizer_fast_mode_warning = False
        set_gcsim_optimizer_fast_mode_enabled(
            normalized,
            settings_file=self._settings_file,
        )

    def set_gcsim_boosted_energy_enabled(self, enabled: bool) -> None:
        """Update the settings-side view of the shared energy switch."""

        normalized = bool(enabled)
        if self.gcsim_boosted_energy_switch.isChecked() != normalized:
            self.gcsim_boosted_energy_switch.setChecked(normalized)

    def choose_pvp_player_color(self, seat: str) -> None:
        current = QColor(
            pvp_player_color(seat, settings_file=self._settings_file)
        )
        selected = QColorDialog.getColor(
            current,
            self._dialog_parent(),
            tr("settings.pvp.color_dialog_title"),
        )
        if selected.isValid():
            self.set_pvp_player_color(seat, selected.name())

    def set_pvp_player_color(self, seat: str, color: str) -> None:
        persist_pvp_player_color(
            seat,
            color,
            settings_file=self._settings_file,
        )
        self._refresh_pvp_color_controls()
        self._emit_pvp_player_colors_changed()

    def reset_pvp_colors(self) -> None:
        reset_pvp_player_colors(settings_file=self._settings_file)
        self._refresh_pvp_color_controls()
        self._emit_pvp_player_colors_changed()

    def _emit_pvp_player_colors_changed(self) -> None:
        self.pvp_player_colors_changed.emit(
            pvp_player_color("player_1", settings_file=self._settings_file),
            pvp_player_color("player_2", settings_file=self._settings_file),
        )

    def _refresh_pvp_color_controls(self) -> None:
        for seat, button in self.pvp_color_buttons.items():
            color = pvp_player_color(seat, settings_file=self._settings_file)
            qcolor = QColor(color)
            foreground = "#111318" if qcolor.lightness() >= 150 else "#ffffff"
            button.setText(color.upper())
            button.setStyleSheet(
                "QPushButton#pvp_color_swatch {"
                f"background: {color}; color: {foreground};"
                "border: 1px solid #dce5f7; border-radius: 5px;"
                "font-weight: 800; padding: 4px 8px;"
                "}"
            )

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.account.title"))
        self.hoyolab_label.setText(tr("common.hoyolab"))
        self.change_equipment_label.setText(tr("hoyolab.change_equipment"))
        self.btn_images_refresh.setText(tr("hoyolab.refresh_images_button"))
        self.change_equipment_switch.setAccessibleName(tr("hoyolab.change_equipment"))
        self.btn_profile_menu.setText(tr("profile.menu_button"))
        self.btn_clear_all.setText(tr("accounts.clear_all"))
        self.action_export_profile.setText(tr("profile.export"))
        self.action_import_profile.setText(tr("profile.import"))
        self.action_switch_profile.setText(tr("profile.switch"))
        self.language_label.setText(tr("language.selector"))
        self.dps_label.setText(tr("settings.dps.title"))
        self.fact_dps_multi_target_label.setText(
            tr("settings.dps.multi_target_hp")
        )
        self.gcsim_label.setText(tr("settings.gcsim.title"))
        self.gcsim_boosted_energy_label.setText(
            tr("settings.gcsim.boosted_energy")
        )
        self.gcsim_boosted_energy_description.setText(
            tr("settings.gcsim.boosted_energy.description")
        )
        self.gcsim_optimizer_set_group_limit_label.setText(
            tr("settings.gcsim.optimizer.set_group_limit")
        )
        self.gcsim_optimizer_limits_note.setText(tr("settings.gcsim.optimizer.output_limits"))
        self.gcsim_optimizer_builds_per_group_label.setText(
            tr("settings.gcsim.optimizer.builds_per_group")
        )
        self.gcsim_optimizer_fast_mode_label.setText(
            tr("settings.gcsim.optimizer.fast_mode")
        )
        self.gcsim_optimizer_fast_mode_help.setAccessibleName(
            tr("settings.gcsim.optimizer.fast_mode")
        )
        self.gcsim_optimizer_fast_mode_help.setAccessibleDescription(
            tr("settings.gcsim.optimizer.fast_mode.tooltip")
        )
        self.gcsim_optimizer_expanded_limits_checkbox.setText(tr("settings.gcsim.optimizer.expanded_limits"))
        self.gcsim_optimizer_expanded_limits_note.setText(tr("settings.gcsim.optimizer.expanded_limits_note"))
        self.pvp_settings_label.setText(tr("settings.pvp.title"))
        self.pvp_color_labels["player_1"].setText(
            tr("settings.pvp.player_color").format(player=1)
        )
        self.pvp_color_labels["player_2"].setText(
            tr("settings.pvp.player_color").format(player=2)
        )
        self.pvp_colors_reset_button.setText(tr("settings.pvp.colors_reset"))
        self._sync_language_combo()
        if self._hoyolab_loader is not None:
            self._hoyolab_loader.retranslate_ui()
        if self._hoyolab_login_hint is not None:
            self._hoyolab_login_hint.retranslate_ui()
        self.refresh_hoyolab_auth_status()
