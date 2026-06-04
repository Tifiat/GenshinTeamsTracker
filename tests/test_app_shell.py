from __future__ import annotations

from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPixmap, QWheelEvent
from PySide6.QtWidgets import QApplication, QStyleOptionButton, QWidget

from hoyolab_export.account_equipment import (
    equip_artifact,
    equip_weapon,
    get_equipped_artifact_owner,
    get_equipped_weapon_for_character,
    list_equipped_artifacts_for_character,
)
from hoyolab_export.artifact_db import (
    connect_db,
    create_build_preset,
    get_artifact_build_slots,
    init_db,
)
from ui.app_shell import (
    AppShell,
    AppShellController,
    APP_SHELL_MIN_HEIGHT,
    APP_SHELL_MIN_WIDTH,
    AssetIconLabel,
    CHARACTER_GRID_SELECTION_SAFE_TOP_MARGIN,
    CharacterWeaponWorkspace,
    LEFT_WORKSPACE_ARTIFACTS,
    LEFT_WORKSPACE_CHARACTERS_WEAPONS,
    RIGHT_OPERATIONS_DOCK_WIDTH,
    RIGHT_DOCK_PAGE_ACCOUNT,
    RIGHT_DOCK_PAGE_RUN,
    RosterSelectionMarker,
    WEAPON_PICKER_OCCUPIED_OUTLINE_COLOR,
    WEAPON_PICKER_SAFE_MARGIN,
    WEAPON_PICKER_VIEWPORT_TOP_EXTENSION,
    _SCALED_ICON_PIXMAP_CACHE,
    _selection_frame_rect,
    _scaled_icon_pixmap,
    _weapon_owner_side_icon_size,
    _weapon_owner_target_rect,
)
from ui.account_data_page import AccountDataPage
from ui.artifact_browser.card_delegate import ArtifactCardDelegate, CARD_SIZE, GRID_SIZE
from ui.artifact_browser.window import (
    ARTIFACT_GRID_FIT_PADDING,
    ARTIFACT_LIST_MIN_WIDTH,
    ArtifactGridListView,
    ArtifactBrowserWindow,
    BUILD_PANEL_WIDTH,
    BUILD_TARGET_UNIVERSAL_KEY,
    CONTENT_LAYOUT_SPACING,
    CONTENT_TARGET_BUILD_SPACING,
    EDIT_MODE_BUILD_PRESET,
    TARGET_ITEM_BUTTON_HEIGHT,
    TARGET_ITEM_ICON_SIZE,
    TARGET_PANEL_MIN_WIDTH,
    TARGET_PANEL_WIDTH,
    calculate_assignment_width_fit,
)
from run_workspace.perf import perf_enabled
from localization import get_language, set_language, tr
from ui.character_assets import STANDARD_FILTER_ONLY, load_account_weapon_stack_asset_items
from ui.utils.drag_scroll import DragScrollArea
from ui.utils.marquee_label import MarqueeButton
from ui.utils.overlay_scroll import OverlayVerticalScrollArea, OverlayVerticalScrollbar
from ui.utils.toggle_switch import FilterActionButton, SortIconButton
from run_workspace.right_panel_prototype_view_model import MODE_ABYSS, MODE_DPS_DUMMY
from run_workspace.right_panel_prototype_view_model import (
    FactDpsTooltipViewModel,
    RightPanelChamberRowViewModel,
    RightPanelGcsimStatusViewModel,
    RightPanelPrototypeViewModel,
    RightPanelSelectedDetailsViewModel,
)
from run_workspace.models import AbyssTimerState
from run_workspace.abyss.source_data import load_abyss_floor12_source_data
from tests.abyss.test_source_data import (
    composition_report,
    fandom_row,
    nanoka_report,
    nanoka_row,
)
from ui.utils.ui_palette import UI_ACCENT_TEAM_1
from ui.right_panel_prototype import (
    ABYSS_CHAMBER_BADGE_WIDTH,
    ABYSS_CHAMBER_GRID_SPACING,
    ABYSS_DPS_COLUMN_MIN_WIDTH,
    ABYSS_FACT_DPS_LEFT_BUDGET_MAX,
    ABYSS_TIMER_CELL_WIDTH,
    ABYSS_TIMER_FRAME_WIDTH,
    CompactAbyssTimerWidget,
    RightPanelPrototypeWidget,
    RunModeTabsWidget,
)


class AppShellTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_app_shell_constructs_with_character_weapon_workspace(self) -> None:
        shell = AppShell()

        self.assertIsInstance(
            shell.left_host.character_weapon_workspace,
            CharacterWeaponWorkspace,
        )
        self.assertEqual(shell.left_host.stack.currentIndex(), 0)
        self.assertEqual(shell.left_host.stack.count(), 2)
        self.assertIsNone(shell.left_host.artifact_browser_workspace)
        self.assertEqual(
            shell.active_left_workspace_id,
            LEFT_WORKSPACE_CHARACTERS_WEAPONS,
        )

    def test_left_workspace_nav_requests_route_through_app_shell(self) -> None:
        shell = AppShell()

        with patch.object(
            shell.left_host,
            "activate_workspace",
            wraps=shell.left_host.activate_workspace,
        ) as activate:
            shell.left_host.artifact_browser_button.click()

        activate.assert_called_once_with(LEFT_WORKSPACE_ARTIFACTS)
        self.assertEqual(
            shell.active_left_workspace_id,
            LEFT_WORKSPACE_ARTIFACTS,
        )
        self.assertIsNotNone(shell.left_host.artifact_browser_workspace)

    def test_left_workspace_switch_preserves_global_account_page(self) -> None:
        shell = AppShell()
        shell.right_dock.show_account_page()

        shell.left_host.artifact_browser_button.click()

        self.assertEqual(shell.right_dock.current_page(), RIGHT_DOCK_PAGE_ACCOUNT)
        self.assertEqual(
            shell.active_left_workspace_id,
            LEFT_WORKSPACE_ARTIFACTS,
        )

    def test_perf_logging_is_disabled_by_default(self) -> None:
        with patch.dict("os.environ", {"GTT_PERF_LOG": ""}):
            self.assertFalse(perf_enabled())

    def test_right_dock_uses_fixed_width(self) -> None:
        shell = AppShell()

        self.assertEqual(shell.right_dock.minimumWidth(), shell.right_dock.maximumWidth())
        self.assertEqual(shell.right_dock.minimumWidth(), RIGHT_OPERATIONS_DOCK_WIDTH)
        self.assertEqual(shell.right_dock.sizePolicy().horizontalPolicy().name, "Fixed")

    def test_right_dock_has_persistent_account_action_without_internal_tab_duplicate(self) -> None:
        shell = AppShell()

        self.assertIsNone(shell.right_panel._mode_tabs)
        self.assertEqual(len(shell.right_dock.header.run_mode_tabs.buttons()), 2)
        self.assertFalse(shell.right_dock.header.account_button.icon().isNull())
        self.assertEqual(shell.right_dock.current_page(), RIGHT_DOCK_PAGE_RUN)

    def test_account_page_keeps_left_workspace_and_run_tab_returns_to_panel(self) -> None:
        shell = AppShell()
        left_workspace_index = shell.left_host.stack.currentIndex()

        shell.right_dock.header.account_button.click()

        self.assertEqual(shell.right_dock.current_page(), RIGHT_DOCK_PAGE_ACCOUNT)
        self.assertEqual(shell.left_host.stack.currentIndex(), left_workspace_index)
        self.assertTrue(shell.right_dock.header.account_button.isChecked())
        self.assertFalse(
            any(
                button.isChecked()
                for button in shell.right_dock.header.run_mode_tabs.buttons()
            )
        )

        shell.right_dock.header.run_mode_tabs.button_for_mode(MODE_DPS_DUMMY).click()

        self.assertEqual(shell.right_dock.current_page(), RIGHT_DOCK_PAGE_RUN)
        self.assertEqual(shell.controller.mode, MODE_DPS_DUMMY)
        self.assertFalse(shell.right_dock.header.account_button.isChecked())
        self.assertTrue(
            shell.right_dock.header.run_mode_tabs.button_for_mode(
                MODE_DPS_DUMMY
            ).isChecked()
        )

    def test_account_page_blocks_roster_character_mutations_for_each_run_mode(self) -> None:
        asset = _character_asset("10000050", "Thoma")
        for mode in (MODE_ABYSS, MODE_DPS_DUMMY):
            for existing_character in (False, True):
                with self.subTest(mode=mode, existing_character=existing_character):
                    shell = AppShell()
                    if mode != MODE_ABYSS:
                        shell._on_mode_requested(mode)
                    if existing_character:
                        shell.controller.add_or_replace_character_fast(asset)
                    selected_before = (
                        shell.controller.selected_team_index,
                        shell.controller.selected_slot_index,
                    )
                    shell.right_dock.show_account_page()

                    with (
                        patch.object(
                            shell.controller,
                            "add_or_replace_character_fast",
                            side_effect=AssertionError,
                        ),
                        patch.object(
                            shell,
                            "_refresh_character_selection_markers",
                            side_effect=AssertionError,
                        ),
                        patch.object(
                            shell,
                            "schedule_persistent_equipment_hydration",
                            side_effect=AssertionError,
                        ),
                        patch.object(
                            shell,
                            "schedule_right_panel_refresh",
                            side_effect=AssertionError,
                        ),
                    ):
                        shell._on_character_clicked(asset)

                    slot = shell.controller.state.team(0).slot(0)
                    self.assertEqual(slot.is_empty, not existing_character)
                    self.assertEqual(
                        (
                            shell.controller.selected_team_index,
                            shell.controller.selected_slot_index,
                        ),
                        selected_before,
                    )

    def test_account_page_blocks_weapon_mutation(self) -> None:
        shell = AppShell()
        shell.controller.add_or_replace_character_fast(
            _character_asset("10000050", "Thoma", weapon_type=13)
        )
        shell.right_dock.show_account_page()

        with (
            patch.object(
                shell.controller,
                "assign_weapon_to_selected_slot",
                side_effect=AssertionError,
            ),
            patch.object(
                shell.left_host.character_weapon_workspace,
                "reload_weapons",
                side_effect=AssertionError,
            ),
            patch.object(
                shell,
                "schedule_right_panel_refresh",
                side_effect=AssertionError,
            ),
        ):
            shell._on_weapon_clicked(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )

        self.assertIsNone(shell.controller.state.team(0).slot(0).weapon)

    def test_account_to_run_switch_updates_model_before_showing_run_page(self) -> None:
        for initial_mode, requested_mode in (
            (MODE_ABYSS, MODE_DPS_DUMMY),
            (MODE_DPS_DUMMY, MODE_ABYSS),
        ):
            with self.subTest(initial_mode=initial_mode, requested_mode=requested_mode):
                shell = AppShell()
                if initial_mode != MODE_ABYSS:
                    shell._on_mode_requested(initial_mode)
                shell.right_dock.show_account_page()
                events: list[tuple] = []
                refresh_right_panel = shell._refresh_right_panel
                show_run_page = shell.right_dock.show_run_page

                def refresh() -> dict[str, float]:
                    events.append(("refresh", shell.controller.mode))
                    return refresh_right_panel()

                def show(mode: str) -> None:
                    events.append(
                        (
                            "show",
                            mode,
                            shell.controller.mode,
                            shell.right_panel._model.mode,
                        )
                    )
                    show_run_page(mode)

                with (
                    patch.object(shell, "_refresh_right_panel", side_effect=refresh),
                    patch.object(shell.right_dock, "show_run_page", side_effect=show),
                ):
                    shell.right_dock.header.run_mode_tabs.button_for_mode(
                        requested_mode
                    ).click()

                self.assertEqual(
                    events,
                    [
                        ("refresh", requested_mode),
                        ("show", requested_mode, requested_mode, requested_mode),
                    ],
                )

    def test_account_return_to_same_run_mode_preserves_operation_target(self) -> None:
        shell = AppShell()
        shell._on_character_clicked(_character_asset("10000050", "Thoma"))
        target_before = shell.controller.selected_operation_target()

        shell.right_dock.show_account_page()
        shell.right_dock.header.run_mode_tabs.button_for_mode(MODE_ABYSS).click()

        self.assertEqual(shell.right_dock.current_page(), RIGHT_DOCK_PAGE_RUN)
        self.assertEqual(shell.controller.selected_operation_target(), target_before)

    def test_returning_from_account_restores_normal_roster_clicks(self) -> None:
        shell = AppShell()
        asset = _character_asset("10000050", "Thoma")
        shell.right_dock.show_account_page()
        shell.right_dock.header.run_mode_tabs.button_for_mode(MODE_ABYSS).click()

        shell._on_character_clicked(asset)
        self.assertEqual(shell.controller.state.team(0).slot(0).character.id, "10000050")
        shell._on_character_clicked(asset)
        self.assertTrue(shell.controller.state.team(0).slot(0).is_empty)

    def test_app_shell_abyss_timer_defaults_show_zero_elapsed_total(self) -> None:
        shell = AppShell()

        model = shell.controller.right_panel_model()

        self.assertEqual(len(model.chamber_rows), 3)
        self.assertEqual(model.chamber_rows[0].team1_time, "10:00")
        self.assertEqual(model.chamber_rows[0].team1_seconds, 0)
        self.assertEqual(model.chamber_rows[0].team2_time, "10:00")
        self.assertEqual(model.chamber_rows[0].team2_seconds, 0)
        self.assertEqual(model.total_seconds, 0)

    def test_app_shell_abyss_timer_change_updates_right_panel_total(self) -> None:
        shell = AppShell()

        shell._on_abyss_timer_changed(0, 1, 550)
        shell._on_abyss_timer_changed(0, 2, 500)

        model = shell.right_panel._model
        self.assertEqual(model.chamber_rows[0].team1_time, "09:10")
        self.assertEqual(model.chamber_rows[0].team1_seconds, 50)
        self.assertEqual(model.chamber_rows[0].team2_time, "08:20")
        self.assertEqual(model.chamber_rows[0].team2_seconds, 50)
        self.assertEqual(model.chamber_rows[0].total_seconds, 100)
        self.assertEqual(model.total_seconds, 100)

    def test_app_shell_abyss_fact_dps_uses_cached_source_data_provider(self) -> None:
        source_data = load_abyss_floor12_source_data(
            "2026-05-16",
            "119",
            composition_report=composition_report(
                "2026-05-16",
                [
                    fandom_row(
                        "Team 1 Enemy",
                        chamber=1,
                        side=1,
                        wave=1,
                        count=2,
                        level=100,
                    ),
                    fandom_row(
                        "Team 2 Enemy",
                        chamber=1,
                        side=2,
                        wave=1,
                        count=2,
                        level=100,
                    ),
                ],
            ),
            nanoka_report=nanoka_report(
                "119",
                [
                    nanoka_row(
                        "Team 1 Enemy",
                        chamber=1,
                        side=1,
                        hp=500_000,
                        monster_id="team1",
                        level=100,
                    ),
                    nanoka_row(
                        "Team 2 Enemy",
                        chamber=1,
                        side=2,
                        hp=300_000,
                        monster_id="team2",
                        level=100,
                    ),
                ],
            ),
        )
        controller = AppShellController.empty()
        controller.set_abyss_timer_seconds(0, 1, 550)
        controller.set_abyss_timer_seconds(0, 2, 500)

        with patch(
            "ui.app_shell.load_current_cached_abyss_floor_source_data",
            return_value=source_data,
        ) as provider:
            model = controller.right_panel_model()
            controller.right_panel_model()

        self.assertEqual(model.chamber_rows[0].team1_seconds, 50)
        self.assertEqual(model.chamber_rows[0].team2_seconds, 50)
        self.assertEqual(model.chamber_rows[0].factual_team1, "10,000")
        self.assertEqual(model.chamber_rows[0].factual_team2, "6,000")
        self.assertIsNotNone(model.chamber_rows[0].factual_team1_tooltip)
        assert model.chamber_rows[0].factual_team1_tooltip is not None
        self.assertEqual(
            model.chamber_rows[0].factual_team1_tooltip.total_solo_hp,
            500_000,
        )
        self.assertEqual(
            model.chamber_rows[0].factual_team1_tooltip.calculated_dps,
            10_000,
        )
        provider.assert_called_once_with(floor=12)

    def test_app_shell_abyss_fact_dps_retries_after_initial_cache_miss(self) -> None:
        source_data = load_abyss_floor12_source_data(
            "2026-05-16",
            "119",
            composition_report=composition_report(
                "2026-05-16",
                [fandom_row("Enemy", chamber=1, side=1, wave=1, level=100)],
            ),
            nanoka_report=nanoka_report(
                "119",
                [
                    nanoka_row(
                        "Enemy",
                        chamber=1,
                        side=1,
                        hp=500_000,
                        monster_id="enemy",
                        level=100,
                    )
                ],
            ),
        )
        controller = AppShellController.empty()
        controller.set_abyss_timer_seconds(0, 1, 550)

        with patch(
            "ui.app_shell.load_current_cached_abyss_floor_source_data",
            side_effect=(None, source_data),
        ) as provider:
            first_model = controller.right_panel_model()
            second_model = controller.right_panel_model()

        self.assertEqual(first_model.chamber_rows[0].factual_team1, "-")
        self.assertEqual(second_model.chamber_rows[0].factual_team1, "10,000")
        self.assertEqual(provider.call_count, 2)

    def test_right_panel_widget_renders_fact_dps_label_from_model(self) -> None:
        previous_language = get_language()
        set_language("en")
        try:
            model = RightPanelPrototypeViewModel(
                mode=MODE_ABYSS,
                mode_tabs=("Abyss", "DPS Dummy"),
                teams=(),
                selected_details=RightPanelSelectedDetailsViewModel(has_selection=False),
                chamber_headers=(
                    "Ch.",
                    "T1",
                    "T2",
                    "Fact T1 DPS",
                    "Fact T2 DPS",
                    "Sim T1 DPS",
                    "Sim T2 DPS",
                ),
                chamber_rows=(
                    RightPanelChamberRowViewModel(
                        chamber_label="C1",
                        team1_time="09:00",
                        team1_seconds=60,
                        team2_time="09:00",
                        team2_seconds=0,
                        factual_team1="62,464",
                        factual_team2="-",
                        factual_team1_tooltip=FactDpsTooltipViewModel(
                            title="Floor 12 / C1 / Team 1",
                            formula="Fact DPS = solo target HP / elapsed time",
                            total_solo_hp=3_747_864,
                            elapsed_seconds=60,
                            calculated_dps=62_464,
                            hp_source_label="Nanoka resolved HP",
                            warnings=(
                                "Nanoka is the primary resolved HP source.",
                                "non_strict_match:variant_strip",
                            ),
                        ),
                        sim_team1="not run",
                        sim_team2="not run",
                        total_seconds=60,
                        timer_editable=True,
                    ),
                ),
                total_seconds=60,
                gcsim_status=RightPanelGcsimStatusViewModel(status="Idle"),
            )

            widget = RightPanelPrototypeWidget(model, show_mode_tabs=False)
        finally:
            set_language(previous_language)

        self.assertEqual(widget._chamber_table._row_labels[(0, 3)].text(), "62,464")
        self.assertEqual(widget._chamber_table._row_labels[(0, 4)].text(), "-")
        self.assertEqual(widget._chamber_table._row_labels[(0, 3)].toolTip(), "")
        tooltip_controller = widget._chamber_table._fact_dps_tooltips[(0, 3)]
        tooltip_text = tooltip_controller.text()
        self.assertIn(
            "Solo HP: 3,747,864",
            tooltip_text,
        )
        self.assertIn(
            "DPS: 62,464",
            tooltip_text,
        )
        self.assertNotIn(
            "Fact DPS = solo target HP / elapsed time",
            tooltip_text,
        )
        self.assertNotIn("non_strict_match", tooltip_text)
        self.assertEqual(
            widget._chamber_table._row_labels[(0, 3)].objectName(),
            "FactDpsCell",
        )

    def test_chamber_timer_cell_signal_updates_app_shell_model(self) -> None:
        shell = AppShell()
        timer_cell = shell.right_panel._chamber_table._timer_cells[(0, 1)]

        timer_cell.timer.adjust_seconds(-50)

        self.assertEqual(
            shell.controller.abyss_timer_states[0].team1_left_seconds,
            550,
        )
        self.assertEqual(shell.right_panel._model.chamber_rows[0].team1_seconds, 50)
        self.assertEqual(shell.right_panel._model.total_seconds, 50)

    def test_abyss_chamber_table_size_hint_fits_fixed_right_dock(self) -> None:
        shell = AppShell()

        self.assertLessEqual(
            shell.right_panel._chamber_table.sizeHint().width(),
            RIGHT_OPERATIONS_DOCK_WIDTH,
        )

    def test_abyss_chamber_timer_polish_preserves_fact_dps_budget(self) -> None:
        left_budget = (
            ABYSS_CHAMBER_BADGE_WIDTH
            + ABYSS_TIMER_CELL_WIDTH * 2
            + ABYSS_CHAMBER_GRID_SPACING * 3
        )

        self.assertLessEqual(left_budget, ABYSS_FACT_DPS_LEFT_BUDGET_MAX)
        self.assertEqual(left_budget, 221)
        self.assertEqual(ABYSS_TIMER_FRAME_WIDTH, 61)
        self.assertEqual(ABYSS_TIMER_CELL_WIDTH, 93)
        self.assertGreaterEqual(ABYSS_DPS_COLUMN_MIN_WIDTH, 60)

    def test_compact_abyss_timer_uses_two_digit_seconds_display(self) -> None:
        timer = CompactAbyssTimerWidget()

        timer.set_seconds(9 * 60 + 1)

        self.assertEqual(timer.min_edit.text(), "09")
        self.assertEqual(timer.sec_edit.text(), "01")

    def test_compact_abyss_timer_first_typed_digit_replaces_selected_segment(self) -> None:
        timer = CompactAbyssTimerWidget()
        timer.set_seconds(590)
        timer.sec_edit.selectAll()

        self._send_key_text(timer.sec_edit, Qt.Key.Key_5, "5")

        self.assertEqual(timer.sec_edit.text(), "5")
        self.assertEqual(timer.seconds_left, 590)

        self._send_key_text(timer.sec_edit, Qt.Key.Key_5, "5")
        self.assertEqual(timer.sec_edit.text(), "55")
        self.assertEqual(timer.seconds_left, 590)

        timer.commit_segment(timer.sec_edit)
        self.assertEqual(timer.seconds_left, 595)
        self.assertEqual(timer.sec_edit.text(), "55")

    def test_compact_abyss_timer_normalizes_one_digit_seconds_only_on_commit(self) -> None:
        timer = CompactAbyssTimerWidget()
        timer.set_seconds(540)
        timer.sec_edit.selectAll()

        self._send_key_text(timer.sec_edit, Qt.Key.Key_1, "1")

        self.assertEqual(timer.sec_edit.text(), "1")
        self.assertEqual(timer.seconds_left, 540)

        timer.commit_segment(timer.sec_edit)

        self.assertEqual(timer.sec_edit.text(), "01")
        self.assertEqual(timer.seconds_left, 541)

    def test_compact_abyss_timer_arrow_keys_step_active_segment(self) -> None:
        timer = CompactAbyssTimerWidget()
        timer.set_seconds(590)

        QApplication.sendEvent(
            timer.sec_edit,
            QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_Up,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
        self.assertEqual(timer.seconds_left, 591)

        QApplication.sendEvent(
            timer.sec_edit,
            QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_Down,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
        self.assertEqual(timer.seconds_left, 590)

        QApplication.sendEvent(
            timer.min_edit,
            QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_Down,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
        self.assertEqual(timer.seconds_left, 530)

    def test_compact_abyss_timer_wheel_steps_segment_under_cursor(self) -> None:
        timer = CompactAbyssTimerWidget()
        timer.set_seconds(590)

        timer.sec_edit.wheelEvent(self._wheel_event(120))
        self.assertEqual(timer.seconds_left, 591)

        timer.min_edit.wheelEvent(self._wheel_event(-120))
        self.assertEqual(timer.seconds_left, 531)

    def test_compact_abyss_timer_left_right_commits_and_selects_destination(self) -> None:
        timer = CompactAbyssTimerWidget()
        timer.set_seconds(540)
        timer.sec_edit.selectAll()
        self._send_key_text(timer.sec_edit, Qt.Key.Key_1, "1")

        QApplication.sendEvent(
            timer.sec_edit,
            QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_Left,
                Qt.KeyboardModifier.NoModifier,
            ),
        )

        self.assertEqual(timer.seconds_left, 541)
        self.assertEqual(timer.sec_edit.text(), "01")
        self.assertEqual(timer.min_edit.selectedText(), "09")

    def test_abyss_t2_follows_t1_until_manually_edited(self) -> None:
        shell = AppShell()

        self.assertTrue(shell.controller.set_abyss_timer_seconds(0, 1, 590))
        self.assertEqual(shell.controller.abyss_timer_states[0].team1_left_seconds, 590)
        self.assertEqual(shell.controller.abyss_timer_states[0].team2_left_seconds, 590)
        self.assertFalse(shell.controller.abyss_t2_manual_by_chamber[0])

        self.assertTrue(shell.controller.set_abyss_timer_seconds(0, 1, 595))
        self.assertEqual(shell.controller.abyss_timer_states[0].team2_left_seconds, 595)
        self.assertEqual(shell.controller.right_panel_model().chamber_rows[0].team2_seconds, 0)

    def test_abyss_manual_t2_stays_fixed_while_valid(self) -> None:
        shell = AppShell()

        shell.controller.set_abyss_timer_seconds(0, 1, 595)
        shell.controller.set_abyss_timer_seconds(0, 2, 585)
        self.assertTrue(shell.controller.abyss_t2_manual_by_chamber[0])

        shell.controller.set_abyss_timer_seconds(0, 1, 586)
        row = shell.controller.right_panel_model().chamber_rows[0]

        self.assertEqual(shell.controller.abyss_timer_states[0].team1_left_seconds, 586)
        self.assertEqual(shell.controller.abyss_timer_states[0].team2_left_seconds, 585)
        self.assertEqual(row.team2_seconds, 1)
        self.assertTrue(shell.controller.abyss_t2_manual_by_chamber[0])

    def test_abyss_t1_crossing_below_t2_clamps_and_restores_follow_mode(self) -> None:
        shell = AppShell()

        shell.controller.set_abyss_timer_seconds(0, 1, 586)
        shell.controller.set_abyss_timer_seconds(0, 2, 585)
        shell.controller.set_abyss_timer_seconds(0, 1, 580)

        row = shell.controller.right_panel_model().chamber_rows[0]
        self.assertEqual(shell.controller.abyss_timer_states[0].team2_left_seconds, 580)
        self.assertEqual(row.team2_seconds, 0)
        self.assertFalse(shell.controller.abyss_t2_manual_by_chamber[0])

        shell.controller.set_abyss_timer_seconds(0, 1, 590)
        self.assertEqual(shell.controller.abyss_timer_states[0].team2_left_seconds, 590)
        self.assertEqual(shell.controller.right_panel_model().chamber_rows[0].team2_seconds, 0)

    def test_app_shell_abyss_timer_change_is_ignored_outside_abyss_mode(self) -> None:
        shell = AppShell()
        shell._on_mode_requested(MODE_DPS_DUMMY)

        shell._on_abyss_timer_changed(0, 1, 550)

        self.assertEqual(
            shell.controller.abyss_timer_states[0],
            AbyssTimerState(team1_left_seconds=600, team2_left_seconds=600),
        )

    @staticmethod
    def _send_key_text(edit, key: Qt.Key, text: str) -> None:
        QApplication.sendEvent(
            edit,
            QKeyEvent(
                QEvent.Type.KeyPress,
                key,
                Qt.KeyboardModifier.NoModifier,
                text,
            ),
        )

    @staticmethod
    def _wheel_event(delta: int) -> QWheelEvent:
        return QWheelEvent(
            QPointF(0, 0),
            QPointF(0, 0),
            QPoint(0, 0),
            QPoint(0, delta),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )

    def test_account_page_exposes_hoyolab_profile_and_language_controls(self) -> None:
        shell = AppShell()
        page = shell.right_dock.account_page

        self.assertIsInstance(page, AccountDataPage)
        self.assertTrue(page.btn_hoyolab_export.text())
        self.assertEqual(page.btn_profile_menu.text(), tr("profile.menu_button"))
        self.assertEqual(
            [action.text() for action in page.profile_menu.actions() if not action.isSeparator()],
            [
                tr("profile.export"),
                tr("profile.import"),
                tr("profile.switch"),
            ],
        )
        self.assertGreater(page.language_combo.count(), 0)

    def test_account_data_refresh_can_reset_app_shell_runtime_team_state(self) -> None:
        shell = AppShell()
        shell.controller.add_or_replace_character_fast(
            _character_asset("10000050", "Thoma")
        )

        with patch.object(shell.left_host, "refresh_account_data") as refresh:
            shell.right_dock.account_page.account_data_changed.emit(True)

        self.assertTrue(shell.controller.state.team(0).slot(0).is_empty)
        refresh.assert_called_once_with()

    def test_hoyolab_update_refresh_preserves_app_shell_runtime_team_state(self) -> None:
        shell = AppShell()
        shell.controller.add_or_replace_character_fast(
            _character_asset("10000050", "Thoma")
        )

        with patch.object(shell.left_host, "refresh_account_data") as refresh:
            shell.right_dock.account_page.account_data_changed.emit(False)

        self.assertEqual(
            shell.controller.state.team(0).slot(0).character.id,
            "10000050",
        )
        refresh.assert_called_once_with()

    def test_run_mode_tabs_route_by_stable_id_not_localized_text(self) -> None:
        with patch(
            "ui.right_panel_prototype.tr",
            side_effect=lambda key: {
                "right_panel.mode.abyss": "First localized tab",
                "right_panel.mode.dps_dummy": "Second localized tab",
            }[key],
        ):
            tabs = RunModeTabsWidget()

        requested_modes: list[str] = []
        tabs.mode_requested.connect(requested_modes.append)
        tabs.button_for_mode(MODE_DPS_DUMMY).click()

        self.assertEqual(requested_modes, [MODE_DPS_DUMMY])

    def test_app_shell_uses_calibrated_artifact_browser_minimum_size(self) -> None:
        shell = AppShell()

        self.assertEqual(shell.minimumWidth(), APP_SHELL_MIN_WIDTH)
        self.assertEqual(shell.minimumHeight(), APP_SHELL_MIN_HEIGHT)

    def test_app_shell_minimum_height_is_independent_from_artifact_target_state(self) -> None:
        shell = AppShell()
        shell.move(0, 0)
        shell.resize(APP_SHELL_MIN_WIDTH, APP_SHELL_MIN_HEIGHT)
        shell.show()
        self._app.processEvents()
        shell.left_host.show_artifact_browser_workspace()
        self._app.processEvents()
        browser = shell.left_host.artifact_browser_workspace
        assert browser is not None

        no_target_minimum = shell.minimumHeight()

        browser.build_target_items_by_key["character:10000050"] = {
            "key": "character:10000050",
            "target_type": "character",
            "character_id": 10000050,
            "character_name": "Thoma",
        }
        browser.refresh_build_target_list()
        browser.set_right_panel_operation_target(
            {"character_id": 10000050, "character_name": "Thoma"}
        )
        self._app.processEvents()

        self.assertEqual(shell.minimumHeight(), no_target_minimum)
        shell.resize(shell.width(), 100)
        self._app.processEvents()
        self.assertGreaterEqual(shell.height(), APP_SHELL_MIN_HEIGHT)

        shell.close()
        self._app.processEvents()

    def test_assignment_width_fit_minimum_one_column(self) -> None:
        fixed_gaps = CONTENT_LAYOUT_SPACING + CONTENT_TARGET_BUILD_SPACING + 4
        content_width = (
            BUILD_PANEL_WIDTH
            + fixed_gaps
            + TARGET_PANEL_MIN_WIDTH
            + GRID_SIZE.width()
        )

        fit = calculate_assignment_width_fit(
            content_width=content_width,
            preset_panel_width=BUILD_PANEL_WIDTH,
            fixed_internal_gaps=fixed_gaps,
            assignment_min_width=TARGET_PANEL_MIN_WIDTH,
            column_step=GRID_SIZE.width(),
        )

        assert fit is not None
        self.assertEqual(fit.columns, 1)
        self.assertEqual(fit.remainder, 0)
        self.assertEqual(fit.assignment_width, TARGET_PANEL_MIN_WIDTH)
        self.assertLessEqual(fit.total_used_width, content_width)

    def test_assignment_width_fit_sends_1440_like_extra_to_assignment(self) -> None:
        fixed_gaps = CONTENT_LAYOUT_SPACING + CONTENT_TARGET_BUILD_SPACING + 4
        extra_width = 32
        content_width = (
            BUILD_PANEL_WIDTH
            + fixed_gaps
            + TARGET_PANEL_MIN_WIDTH
            + GRID_SIZE.width()
            + extra_width
        )

        fit = calculate_assignment_width_fit(
            content_width=content_width,
            preset_panel_width=BUILD_PANEL_WIDTH,
            fixed_internal_gaps=fixed_gaps,
            assignment_min_width=TARGET_PANEL_MIN_WIDTH,
            column_step=GRID_SIZE.width(),
        )

        assert fit is not None
        self.assertEqual(fit.columns, 1)
        self.assertEqual(fit.remainder, extra_width)
        self.assertEqual(fit.assignment_width, TARGET_PANEL_MIN_WIDTH + extra_width)
        self.assertLessEqual(fit.total_used_width, content_width)

    def test_assignment_width_fit_transitions_to_two_and_three_columns(self) -> None:
        fixed_gaps = CONTENT_LAYOUT_SPACING + CONTENT_TARGET_BUILD_SPACING + 4
        for columns in (2, 3):
            with self.subTest(columns=columns):
                content_width = (
                    BUILD_PANEL_WIDTH
                    + fixed_gaps
                    + TARGET_PANEL_MIN_WIDTH
                    + GRID_SIZE.width() * columns
                )

                fit = calculate_assignment_width_fit(
                    content_width=content_width,
                    preset_panel_width=BUILD_PANEL_WIDTH,
                    fixed_internal_gaps=fixed_gaps,
                    assignment_min_width=TARGET_PANEL_MIN_WIDTH,
                    column_step=GRID_SIZE.width(),
                )

                assert fit is not None
                self.assertEqual(fit.columns, columns)
                self.assertEqual(fit.remainder, 0)
                self.assertEqual(fit.assignment_width, TARGET_PANEL_MIN_WIDTH)
                self.assertLessEqual(fit.total_used_width, content_width)

    def test_assignment_width_fit_never_returns_assignment_below_min(self) -> None:
        fit = calculate_assignment_width_fit(
            content_width=BUILD_PANEL_WIDTH + TARGET_PANEL_MIN_WIDTH,
            preset_panel_width=BUILD_PANEL_WIDTH,
            fixed_internal_gaps=0,
            assignment_min_width=TARGET_PANEL_MIN_WIDTH,
            column_step=GRID_SIZE.width(),
        )

        self.assertIsNone(fit)

    def test_artifact_workspace_can_be_created_and_switched_to(self) -> None:
        shell = AppShell()

        shell.left_host.show_artifact_browser_workspace()

        self.assertIsInstance(
            shell.left_host.artifact_browser_workspace,
            ArtifactBrowserWindow,
        )
        self.assertEqual(
            shell.left_host.stack.currentWidget(),
            shell.left_host.artifact_browser_workspace,
        )
        self.assertEqual(shell.right_dock.minimumWidth(), RIGHT_OPERATIONS_DOCK_WIDTH)

    def test_artifact_workspace_minimum_width_lands_on_one_grid_cell(self) -> None:
        shell = AppShell()
        shell.move(0, 0)
        shell.resize(1535, 900)
        shell.show()
        self._app.processEvents()
        shell.left_host.show_artifact_browser_workspace()
        self._app.processEvents()
        browser = shell.left_host.artifact_browser_workspace
        assert browser is not None

        shell.resize(shell.minimumSizeHint().width(), shell.height())
        self._app.processEvents()
        browser.update_adaptive_target_panel_width()
        self._app.processEvents()

        viewport_width = browser.list_view.viewport().width()
        self.assertGreaterEqual(viewport_width, GRID_SIZE.width())
        self.assertLessEqual(viewport_width, GRID_SIZE.width() + 8)
        spacing = max(0, browser.content_layout.spacing())
        viewport_chrome_width = max(
            0,
            browser.list_view.width() - browser.list_view.viewport().width(),
        )
        fit = calculate_assignment_width_fit(
            content_width=browser.content_layout.geometry().width(),
            preset_panel_width=browser.build_panel.width(),
            fixed_internal_gaps=(
                spacing
                + CONTENT_TARGET_BUILD_SPACING
                + viewport_chrome_width
                + ARTIFACT_GRID_FIT_PADDING
            ),
            assignment_min_width=TARGET_PANEL_MIN_WIDTH,
            column_step=GRID_SIZE.width(),
        )
        self.assertGreaterEqual(
            browser.build_target_panel.width(),
            browser.build_target_panel.minimumSizeHint().width(),
        )
        if fit is not None:
            self.assertEqual(fit.columns, 1)
            self.assertEqual(browser.build_target_panel.width(), fit.assignment_width)
        else:
            self.assertEqual(browser.build_target_panel.width(), TARGET_PANEL_MIN_WIDTH)
        self.assertLess(
            browser.build_target_panel.width(),
            TARGET_PANEL_MIN_WIDTH + GRID_SIZE.width(),
        )
        self.assertEqual(browser.build_panel.width(), BUILD_PANEL_WIDTH)

        content_right = (
            browser.content_layout.geometry().x()
            + browser.content_layout.geometry().width()
        )
        for index in range(browser.content_layout.count()):
            widget = browser.content_layout.itemAt(index).widget()
            assert widget is not None
            self.assertLessEqual(widget.geometry().x() + widget.width(), content_right)

        shell.close()
        self._app.processEvents()

    def test_artifact_browser_assignment_fit_keeps_children_inside_content(self) -> None:
        shell = AppShell()
        shell.move(0, 0)
        shell.resize(1440, 900)
        shell.show()
        self._app.processEvents()
        shell.left_host.show_artifact_browser_workspace()
        self._app.processEvents()
        browser = shell.left_host.artifact_browser_workspace
        assert browser is not None

        browser.update_adaptive_target_panel_width()
        self._app.processEvents()

        self.assertEqual(browser.build_panel.width(), BUILD_PANEL_WIDTH)
        self.assertGreaterEqual(browser.build_target_panel.width(), TARGET_PANEL_MIN_WIDTH)
        self.assertLess(
            browser.build_target_panel.width(),
            TARGET_PANEL_MIN_WIDTH + GRID_SIZE.width(),
        )
        content_right = (
            browser.content_layout.geometry().x()
            + browser.content_layout.geometry().width()
        )
        for index in range(browser.content_layout.count()):
            widget = browser.content_layout.itemAt(index).widget()
            assert widget is not None
            self.assertLessEqual(widget.geometry().x() + widget.width(), content_right)

        shell.close()
        self._app.processEvents()

    def test_artifact_browser_expanded_assignment_does_not_block_shrink(self) -> None:
        shell = AppShell()
        shell.move(0, 0)
        shell.resize(1700, 900)
        shell.show()
        self._app.processEvents()
        shell.left_host.show_artifact_browser_workspace()
        self._app.processEvents()
        browser = shell.left_host.artifact_browser_workspace
        assert browser is not None

        browser.update_adaptive_target_panel_width()
        self._app.processEvents()

        expanded_width = browser.build_target_panel.width()
        expanded_shell_min = shell.minimumSizeHint().width()
        self.assertGreater(expanded_width, TARGET_PANEL_MIN_WIDTH)
        self.assertEqual(browser.build_target_panel.minimumWidth(), TARGET_PANEL_MIN_WIDTH)
        self.assertEqual(browser.build_target_panel.minimumSizeHint().width(), TARGET_PANEL_MIN_WIDTH)
        self.assertEqual(browser.build_panel.width(), BUILD_PANEL_WIDTH)

        shell.resize(expanded_shell_min, shell.height())
        self._app.processEvents()
        browser.update_adaptive_target_panel_width()
        self._app.processEvents()

        self.assertEqual(shell.minimumSizeHint().width(), expanded_shell_min)
        self.assertLessEqual(browser.build_target_panel.width(), expanded_width)
        self.assertEqual(browser.build_target_panel.minimumWidth(), TARGET_PANEL_MIN_WIDTH)
        self.assertEqual(browser.build_panel.width(), BUILD_PANEL_WIDTH)
        content_right = (
            browser.content_layout.geometry().x()
            + browser.content_layout.geometry().width()
        )
        for index in range(browser.content_layout.count()):
            widget = browser.content_layout.itemAt(index).widget()
            assert widget is not None
            self.assertLessEqual(widget.geometry().x() + widget.width(), content_right)

        shell.close()
        self._app.processEvents()

    def test_switching_artifact_workspace_preserves_team_state(self) -> None:
        shell = AppShell()
        shell.left_host.character_weapon_workspace.character_clicked.emit(
            _character_asset("10000050", "Thoma")
        )

        shell.left_host.show_artifact_browser_workspace()
        shell.left_host.stack.setCurrentIndex(0)

        self.assertEqual(shell.controller.state.team(0).slot(0).character.id, "10000050")
        self.assertEqual(shell.controller.selected_slot_index, 0)

    def test_embedded_artifact_browser_is_not_standalone_window(self) -> None:
        parent = QWidget()
        browser = ArtifactBrowserWindow(parent=parent, embedded=True)

        self.assertFalse(bool(browser.windowFlags() & Qt.Window))
        self.assertFalse(hasattr(browser, "close_button"))
        self.assertFalse(hasattr(browser, "bottom_bar_widget"))
        self.assertTrue(browser.embedded)
        browser.update_adaptive_target_panel_width()
        self.assertFalse(browser._adaptive_target_resize_timer.isActive())

    def test_embedded_artifact_browser_uses_non_shifting_scrollbars(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)

        self.assertIsInstance(browser.list_view, ArtifactGridListView)
        self.assertFalse(browser.delegate.draw_owner_icons_in_delegate)
        self.assertIsInstance(browser.build_target_scroll, OverlayVerticalScrollArea)
        self.assertIsInstance(browser.build_preset_list_scroll, OverlayVerticalScrollArea)
        self.assertIsInstance(
            browser.artifact_grid_overlay_scrollbar,
            OverlayVerticalScrollbar,
        )
        self.assertEqual(
            browser.list_view.verticalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.assertIs(
            browser.artifact_grid_overlay_scrollbar._overlay.parent(),
            browser.list_view,
        )

    def test_artifact_browser_target_filter_lane_does_not_clip_buttons(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)
        browser.resize(748, 900)
        browser.show()
        self._app.processEvents()
        try:
            filter_scroll = next(
                scroll
                for scroll in browser.findChildren(DragScrollArea)
                if not scroll._is_horizontal
            )

            self.assertEqual(filter_scroll.horizontalScrollBar().maximum(), 0)
            self.assertLessEqual(
                filter_scroll.widget().width(),
                filter_scroll.viewport().width(),
            )
        finally:
            browser.close()

    def test_artifact_browser_target_title_has_room_for_localized_text(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)

        self.assertIsInstance(browser.build_target_title_label, MarqueeButton)
        self.assertGreaterEqual(browser.build_target_title_label.minimumWidth(), 50)
        self.assertLessEqual(browser.build_target_title_label.minimumWidth(), 70)
        self.assertEqual(browser.build_target_title_label.sizeHint().width(), 0)
        self.assertEqual(
            browser.build_target_title_label.minimumSizeHint().width(),
            0,
        )
        self.assertEqual(
            browser.build_target_title_label.sizePolicy().horizontalPolicy().name,
            "Expanding",
        )

    def test_artifact_browser_sets_button_embeds_filter_toggle(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)

        self.assertIsInstance(browser.sort_button, SortIconButton)
        self.assertIsInstance(browser.sets_button, FilterActionButton)
        self.assertTrue(browser.sets_filter_enabled)
        self.assertFalse(browser.sets_button.isFilterChecked())

        browser.sets_button.setFilterChecked(True, notify=True)

        self.assertFalse(browser.sets_filter_enabled)
        self.assertTrue(browser.sets_button.isFilterChecked())

        browser.sets_button.setFilterChecked(False, notify=True)

        self.assertTrue(browser.sets_filter_enabled)
        self.assertFalse(browser.sets_button.isFilterChecked())

        browser.selected_sort_stat_types = [1, 2]
        browser.update_sort_button_text()

        self.assertEqual(browser.sort_button.count(), 2)

    def test_artifact_browser_json_buttons_use_compact_marquee_text(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)

        self.assertIsInstance(browser.import_json_button, MarqueeButton)
        self.assertIsInstance(browser.clear_json_button, MarqueeButton)
        assert browser.import_json_button is not None
        assert browser.clear_json_button is not None
        assert browser.json_action_row_widget is not None
        self.assertEqual(browser.import_json_button.sizeHint().width(), 0)
        self.assertEqual(browser.clear_json_button.sizeHint().width(), 0)
        self.assertEqual(browser.json_action_row_widget.minimumWidth(), GRID_SIZE.width())
        self.assertEqual(browser.json_action_row_widget.sizeHint().width(), GRID_SIZE.width())
        self.assertLessEqual(
            browser.import_json_button.minimumWidth(),
            GRID_SIZE.width() // 2,
        )
        self.assertLessEqual(
            browser.clear_json_button.minimumWidth(),
            GRID_SIZE.width() // 2,
        )

    def test_artifact_browser_json_buttons_expand_at_two_columns(self) -> None:
        shell = AppShell()
        shell.move(0, 0)
        shell.resize(1700, 900)
        shell.show()
        self._app.processEvents()
        shell.left_host.show_artifact_browser_workspace()
        self._app.processEvents()
        browser = shell.left_host.artifact_browser_workspace
        assert browser is not None
        assert browser.import_json_button is not None
        assert browser.clear_json_button is not None
        assert browser.json_action_row_widget is not None

        browser.update_adaptive_target_panel_width()
        self._app.processEvents()

        self.assertGreaterEqual(browser._artifact_column_count, 2)
        self.assertGreaterEqual(
            browser.json_action_row_widget.width(),
            GRID_SIZE.width() * browser._artifact_column_count,
        )
        self.assertEqual(browser.json_action_row_widget.minimumWidth(), GRID_SIZE.width())
        self.assertEqual(
            browser.json_action_row_widget.sizeHint().width(),
            GRID_SIZE.width() * browser._artifact_column_count,
        )
        self.assertGreater(browser.import_json_button.width(), GRID_SIZE.width() // 2)
        self.assertGreater(browser.clear_json_button.width(), GRID_SIZE.width() // 2)
        self.assertEqual(browser.build_panel.width(), BUILD_PANEL_WIDTH)
        self.assertGreaterEqual(browser.build_target_panel.width(), TARGET_PANEL_MIN_WIDTH)

        shell.resize(shell.minimumSizeHint().width(), shell.height())
        self._app.processEvents()
        browser.update_adaptive_target_panel_width()
        self._app.processEvents()

        self.assertEqual(browser._artifact_column_count, 1)
        self.assertEqual(
            browser.json_action_row_widget.width(),
            ARTIFACT_LIST_MIN_WIDTH,
        )
        self.assertLessEqual(browser.import_json_button.width(), GRID_SIZE.width() // 2)
        self.assertLessEqual(browser.clear_json_button.width(), GRID_SIZE.width() // 2)
        self.assertEqual(browser.build_panel.width(), BUILD_PANEL_WIDTH)
        self.assertGreaterEqual(browser.build_target_panel.width(), TARGET_PANEL_MIN_WIDTH)

        shell.close()
        self._app.processEvents()

    def test_artifact_browser_json_buttons_become_edit_actions_without_layout_jump(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)
        browser.resize(732, 852)
        browser.show()
        self._app.processEvents()
        assert browser.import_json_button is not None
        assert browser.clear_json_button is not None
        import_y = browser.import_json_button.mapTo(
            browser,
            browser.import_json_button.rect().topLeft(),
        ).y()
        clear_y = browser.clear_json_button.mapTo(
            browser,
            browser.clear_json_button.rect().topLeft(),
        ).y()

        browser.edit_selection_mode = EDIT_MODE_BUILD_PRESET
        browser.editing_build_name = "Smoke preset"
        browser.update_edit_selection_mode()
        self._app.processEvents()

        self.assertEqual(browser.import_json_button.text(), "")
        self.assertEqual(browser.clear_json_button.text(), "")
        self.assertEqual(browser.import_json_button.objectName(), "json_edit_save_button")
        self.assertEqual(browser.clear_json_button.objectName(), "json_edit_cancel_button")
        self.assertFalse(browser.import_json_button.icon().isNull())
        self.assertFalse(browser.clear_json_button.icon().isNull())
        self.assertEqual(
            browser.import_json_button.mapTo(
                browser,
                browser.import_json_button.rect().topLeft(),
            ).y(),
            import_y,
        )
        self.assertEqual(
            browser.clear_json_button.mapTo(
                browser,
                browser.clear_json_button.rect().topLeft(),
            ).y(),
            clear_y,
        )
        browser.close()

    def test_artifact_browser_target_buttons_use_marquee_without_forcing_width(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)
        long_key = "character:99999999"
        icon_path = next(
            (
                item.get("path")
                for item in browser.build_target_items_by_key.values()
                if item.get("path")
            ),
            None,
        )
        browser.build_target_items_by_key[long_key] = {
            "key": long_key,
            "target_type": "character",
            "character_id": 99999999,
            "character_name": "Очень Длинное Имя Персонажа Для Проверки Прокрутки",
            "asset": {},
            "path": icon_path,
        }

        browser.refresh_build_target_list()
        button = browser.build_target_buttons_by_key[long_key]

        self.assertIsInstance(button, MarqueeButton)
        self.assertEqual(button.sizeHint().width(), 0)
        self.assertEqual(button.minimumSizeHint().width(), 0)
        self.assertLessEqual(button.minimumWidth(), 100)
        self.assertEqual(browser.build_target_panel.width(), TARGET_PANEL_WIDTH)

        option = QStyleOptionButton()
        button.initStyleOption(option)
        text_rect = button._text_rect(option)
        icon_rect = button._icon_rect(text_rect, option.iconSize)
        text_start = icon_rect.right() + 7

        self.assertFalse(option.icon.isNull())
        self.assertEqual(button.height(), TARGET_ITEM_BUTTON_HEIGHT)
        self.assertEqual(option.iconSize.height(), TARGET_ITEM_ICON_SIZE)
        self.assertEqual(icon_rect.top(), text_rect.top())
        self.assertEqual(icon_rect.bottom(), text_rect.bottom())
        self.assertGreater(text_start, icon_rect.right())
        self.assertGreater(button._available_text_width(), 0)
        self.assertGreaterEqual(text_start, text_rect.left() + option.iconSize.width())
        self.assertLess(text_start, text_rect.right())

    def test_artifact_browser_target_filter_refresh_preserves_button_widgets(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)
        target_key = "character:99999999"
        browser.build_target_items_by_key[target_key] = {
            "key": target_key,
            "target_type": "character",
            "character_id": 99999999,
            "character_name": "Nonstandard Target",
            "asset": {
                "metadata": {
                    "character": {
                        "id": 99999999,
                        "name": "Nonstandard Target",
                        "rarity": 5,
                        "weapon_type_name": "sword",
                        "is_standard_5_star": False,
                    }
                }
            },
            "path": None,
        }
        browser.refresh_build_target_list()
        button = browser.build_target_buttons_by_key[target_key]
        existing_count = len(browser.build_target_buttons_by_key)

        browser.build_target_standard_filter = STANDARD_FILTER_ONLY
        browser.refresh_build_target_list()

        self.assertIs(browser.build_target_buttons_by_key[target_key], button)
        self.assertEqual(len(browser.build_target_buttons_by_key), existing_count)
        self.assertTrue(button.isHidden())

        browser.selected_build_target_keys = {target_key}
        browser.refresh_build_target_list()

        self.assertIs(browser.build_target_buttons_by_key[target_key], button)
        self.assertFalse(button.isHidden())
        self.assertTrue(button.isChecked())

    def test_right_panel_target_updates_artifact_browser_equip_state(self) -> None:
        with temp_app_shell_db() as db_path:
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            browser = shell.left_host.ensure_artifact_browser_workspace()
            browser.build_target_items_by_key["character:10000050"] = {
                "key": "character:10000050",
                "target_type": "character",
                "character_id": 10000050,
                "character_name": "Thoma",
            }
            browser.refresh_build_target_list()

            shell.left_host.character_weapon_workspace.character_clicked.emit(
                _character_asset("10000050", "Thoma")
            )

            self.assertEqual(browser.operation_target_character_id, 10000050)
            self.assertEqual(browser.operation_target_source, "right_panel")
            self.assertTrue(browser.equip_mode_enabled)
            self.assertEqual(browser.equipment_target_label.text(), "")
            self.assertNotIn("right panel", browser.equipment_target_label.text().casefold())
            self.assertNotIn("правой панели", browser.equipment_target_label.text().casefold())
            self.assertEqual(browser.selected_build_target_keys, {"character:10000050"})
            self.assertFalse(browser.build_preset_list_scroll.isHidden())
            self.assertTrue(
                browser.build_target_buttons_by_key["character:10000050"].isChecked()
            )

            browser.toggle_build_target("character:10000050")

            self.assertEqual(browser.selected_build_target_keys, set())
            self.assertEqual(browser.operation_target_character_id, 10000050)
            self.assertEqual(browser.operation_target_source, "right_panel")
            self.assertTrue(browser.equip_mode_enabled)
            self.assertTrue(browser.build_preset_list_scroll.isHidden())
            button = browser.build_target_buttons_by_key["character:10000050"]
            self.assertFalse(button.isChecked())
            self.assertTrue(button.property("operationTarget"))

            shell._on_slot_selected(0, 0)

            self.assertFalse(browser.equip_mode_enabled)
            self.assertFalse(
                browser.build_target_buttons_by_key["character:10000050"].isChecked()
            )
            self.assertFalse(
                browser.build_target_buttons_by_key["character:10000050"].property(
                    "operationTarget"
                )
            )

    def test_artifact_browser_can_browse_other_target_while_right_target_stays_active(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)
        browser.build_target_items_by_key["character:10000050"] = {
            "key": "character:10000050",
            "target_type": "character",
            "character_id": 10000050,
            "character_name": "Thoma",
        }
        browser.build_target_items_by_key["character:10000089"] = {
            "key": "character:10000089",
            "target_type": "character",
            "character_id": 10000089,
            "character_name": "Furina",
        }
        browser.refresh_build_target_list()

        browser.set_right_panel_operation_target(
            {"character_id": 10000050, "character_name": "Thoma"}
        )
        browser.toggle_build_target("character:10000050")
        browser.toggle_build_target("character:10000089")

        self.assertEqual(browser.selected_build_target_keys, {"character:10000089"})
        self.assertEqual(browser.operation_target_character_id, 10000050)
        self.assertEqual(browser.operation_target_source, "right_panel")
        self.assertTrue(browser.equip_mode_enabled)
        self.assertTrue(browser.build_target_buttons_by_key["character:10000089"].isChecked())
        self.assertFalse(browser.build_target_buttons_by_key["character:10000050"].isChecked())
        self.assertTrue(
            browser.build_target_buttons_by_key["character:10000050"].property(
                "operationTarget"
            )
        )

    def test_artifact_browser_target_falls_back_to_one_browser_character(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)
        browser.build_target_items_by_key["character:10000050"] = {
            "key": "character:10000050",
            "target_type": "character",
            "character_id": 10000050,
            "character_name": "Thoma",
        }
        browser.build_target_items_by_key["character:10000089"] = {
            "key": "character:10000089",
            "target_type": "character",
            "character_id": 10000089,
            "character_name": "Furina",
        }

        browser.selected_build_target_keys = {"character:10000050"}
        browser.refresh_equipment_target_state()

        self.assertEqual(browser.operation_target_character_id, 10000050)
        self.assertEqual(browser.operation_target_source, "artifact_browser")
        self.assertTrue(browser.equip_mode_enabled)

        browser.selected_build_target_keys = {"character:10000050", "character:10000089"}
        browser.refresh_equipment_target_state()

        self.assertFalse(browser.equip_mode_enabled)

    def test_assignment_only_target_updates_current_equipment_preview(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_artifact(conn, 10000050, 1)
                conn.commit()
            browser = ArtifactBrowserWindow(embedded=True, db_path=db_path)
            browser.build_target_items_by_key["character:10000050"] = {
                "key": "character:10000050",
                "target_type": "character",
                "character_id": 10000050,
                "character_name": "Thoma",
            }

            browser.selected_build_target_keys = {"character:10000050"}
            browser.update_build_panel()
            browser.update_edit_selection_mode()

            self.assertEqual(browser.operation_target_character_id, 10000050)
            self.assertEqual(browser.operation_target_source, "artifact_browser")
            self.assertEqual(browser.current_equipment_preview_slots, {1: 1})
            self.assertEqual(browser.current_build_artifact_ids(), {1})
            self.assertEqual(browser.delegate.edit_selection_artifact_ids, {1})

    def test_assignment_without_single_character_shows_placeholders(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_artifact(conn, 10000050, 1)
                equip_artifact(conn, 10000089, 2)
                conn.commit()
            browser = ArtifactBrowserWindow(embedded=True, db_path=db_path)
            browser.build_target_items_by_key["character:10000050"] = {
                "key": "character:10000050",
                "target_type": "character",
                "character_id": 10000050,
                "character_name": "Thoma",
            }
            browser.build_target_items_by_key["character:10000089"] = {
                "key": "character:10000089",
                "target_type": "character",
                "character_id": 10000089,
                "character_name": "Furina",
            }

            for selected_keys in (
                set(),
                {BUILD_TARGET_UNIVERSAL_KEY},
                {"character:10000050", "character:10000089"},
            ):
                with self.subTest(selected_keys=selected_keys):
                    browser.selected_build_target_keys = set(selected_keys)
                    browser.update_build_panel()
                    browser.update_edit_selection_mode()

                    self.assertFalse(browser.equip_mode_enabled)
                    self.assertIsNone(browser.operation_target_character_id)
                    self.assertEqual(browser.current_equipment_preview_slots, {})
                    self.assertEqual(browser.current_build_artifact_ids(), set())
                    self.assertEqual(browser.delegate.edit_selection_artifact_ids, set())

    def test_right_panel_target_overrides_assignment_for_current_equipment_preview(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_artifact(conn, 10000050, 1)
                equip_artifact(conn, 10000089, 2)
                conn.commit()
            browser = ArtifactBrowserWindow(embedded=True, db_path=db_path)
            browser.build_target_items_by_key["character:10000089"] = {
                "key": "character:10000089",
                "target_type": "character",
                "character_id": 10000089,
                "character_name": "Furina",
            }
            browser.set_right_panel_operation_target(
                {"character_id": 10000050, "character_name": "Thoma"}
            )

            for selected_keys in (
                set(),
                {"character:10000050", "character:10000089"},
            ):
                with self.subTest(selected_keys=selected_keys):
                    browser.selected_build_target_keys = set(selected_keys)
                    browser.update_build_panel()
                    browser.update_edit_selection_mode()

                    self.assertTrue(browser.equip_mode_enabled)
                    self.assertEqual(browser.operation_target_character_id, 10000050)
                    self.assertEqual(browser.operation_target_source, "right_panel")
                    self.assertEqual(browser.current_equipment_preview_slots, {1: 1})
                    self.assertEqual(browser.current_build_artifact_ids(), {1})
                    self.assertEqual(browser.delegate.edit_selection_artifact_ids, {1})

    def test_artifact_browser_current_equipment_zone_scaffold(self) -> None:
        browser = ArtifactBrowserWindow(embedded=True)

        expected_no_target = tr(
            "artifact.build.current_equipment_for_character",
            name=tr("artifact.build.character_not_selected"),
        )
        self.assertEqual(
            browser.equipment_zone_label.text(),
            expected_no_target,
        )
        browser.set_right_panel_operation_target(
            {"character_id": 10000050, "character_name": "Thoma"}
        )
        expected_thoma_target = tr(
            "artifact.build.current_equipment_for_character",
            name="Thoma",
        )
        self.assertEqual(
            browser.equipment_zone_label.text(),
            expected_thoma_target,
        )

        browser.selected_build_id = 123
        browser.update_build_panel()

        self.assertEqual(
            browser.equipment_zone_action_button.text(),
            tr("artifact.equipment.apply_preset"),
        )
        self.assertTrue(browser.equipment_zone_label.isHidden())
        self.assertFalse(browser.equipment_zone_action_button.isHidden())
        self.assertTrue(browser.equipment_zone_action_button.isEnabled())

    def test_artifact_click_without_operation_target_does_not_equip(self) -> None:
        with temp_app_shell_db() as db_path:
            browser = ArtifactBrowserWindow(embedded=True, db_path=db_path)
            index = browser.model.index(0, 0)

            browser.on_artifact_clicked(index)

            with closing(connect_db(db_path)) as conn:
                self.assertIsNone(get_equipped_artifact_owner(conn, 1))

    def test_artifact_click_with_right_panel_target_equips_and_refreshes_panel(self) -> None:
        with temp_app_shell_db() as db_path:
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_right_panel_refresh()
            browser = shell.left_host.ensure_artifact_browser_workspace()
            index = browser.model.index(0, 0)

            with patch.object(shell.right_panel, "set_model", wraps=shell.right_panel.set_model) as set_model:
                browser.on_artifact_clicked(index)

                self.assertTrue(shell._right_panel_refresh_pending)
                shell.flush_pending_right_panel_refresh()

            with closing(connect_db(db_path)) as conn:
                self.assertEqual(get_equipped_artifact_owner(conn, 1), 10000050)
            self.assertGreaterEqual(set_model.call_count, 1)
            details = shell.controller.state.team(0).slot(0).character_details_data
            self.assertEqual(
                details["current_equipped_artifact_ids_by_slot"],
                {"flower": 1},
            )
            stat_totals = {
                item["property_type"]: item["raw_value"]
                for item in details["stat_snapshot"]["artifact"]["summary"]["stat_totals"]
            }
            self.assertEqual(stat_totals[2], 4780.0)

    def test_artifact_click_does_not_mutate_presets(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                build_id = create_build_preset(
                    conn,
                    name="Preset",
                    slots={1: 1},
                    targets=[
                        {
                            "target_type": "character",
                            "character_id": 10000050,
                            "character_name": "Thoma",
                        }
                    ],
                )
                before_slots = get_artifact_build_slots(conn, build_id)
                conn.commit()
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_right_panel_refresh()
            browser = shell.left_host.ensure_artifact_browser_workspace()

            browser.on_artifact_clicked(browser.model.index(0, 0))

            with closing(connect_db(db_path)) as conn:
                self.assertEqual(get_artifact_build_slots(conn, build_id), before_slots)

    def test_artifact_click_in_preset_edit_does_not_current_equip(self) -> None:
        with temp_app_shell_db() as db_path:
            browser = ArtifactBrowserWindow(embedded=True, db_path=db_path)
            browser.set_right_panel_operation_target(
                {"character_id": 10000050, "character_name": "Thoma"}
            )
            browser.edit_selection_mode = EDIT_MODE_BUILD_PRESET
            browser.editing_build_id = 1
            browser.editing_build_name = "Preset"

            browser.on_artifact_clicked(browser.model.index(0, 0))

            self.assertEqual(browser.editing_build_slots, {1: 1})
            with closing(connect_db(db_path)) as conn:
                self.assertIsNone(get_equipped_artifact_owner(conn, 1))

    def test_artifact_click_uses_service_move_swap_semantics(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                _insert_app_shell_artifact(conn, artifact_id=3, pos=1, name="Flower B")
                equip_artifact(conn, 10000050, 1)
                equip_artifact(conn, 10000051, 3)
                conn.commit()
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_right_panel_refresh()
            browser = shell.left_host.ensure_artifact_browser_workspace()
            row = browser.model.artifact_ids.index(3)

            browser.on_artifact_clicked(browser.model.index(row, 0))

            with closing(connect_db(db_path)) as conn:
                self.assertEqual(get_equipped_artifact_owner(conn, 3), 10000050)
                self.assertEqual(get_equipped_artifact_owner(conn, 1), 10000051)
                self.assertEqual(
                    [
                        (row.slot_key, row.artifact_id)
                        for row in list_equipped_artifacts_for_character(conn, 10000051)
                    ],
                    [("flower", 1)],
                )

    def test_artifact_click_updates_preview_and_owner_markers(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                _insert_app_shell_artifact(conn, artifact_id=3, pos=1, name="Flower B")
                conn.commit()
            browser = ArtifactBrowserWindow(embedded=True, db_path=db_path)
            browser.set_right_panel_operation_target(
                {"character_id": 10000050, "character_name": "Thoma"}
            )

            browser.on_artifact_clicked(browser.model.index(0, 0))

            self.assertEqual(browser.current_equipment_preview_slots, {1: 1})
            self.assertEqual(browser.delegate.edit_selection_artifact_ids, {1})
            self.assertEqual(browser.store.artifact(1).character_name, "Thoma")

            row = browser.model.artifact_ids.index(3)
            browser.on_artifact_clicked(browser.model.index(row, 0))

            self.assertEqual(browser.current_equipment_preview_slots, {1: 3})
            self.assertEqual(browser.delegate.edit_selection_artifact_ids, {3})
            self.assertEqual(browser.store.artifact(1).character_name, "")
            self.assertEqual(browser.store.artifact(3).character_name, "Thoma")

    def test_repeated_artifact_click_unequips_current_target_artifact(self) -> None:
        with temp_app_shell_db() as db_path:
            browser = ArtifactBrowserWindow(embedded=True, db_path=db_path)
            browser.set_right_panel_operation_target(
                {"character_id": 10000050, "character_name": "Thoma"}
            )
            index = browser.model.index(0, 0)

            browser.on_artifact_clicked(index)
            browser.on_artifact_clicked(index)

            with closing(connect_db(db_path)) as conn:
                self.assertIsNone(get_equipped_artifact_owner(conn, 1))
            self.assertEqual(browser.current_equipment_preview_slots, {})
            self.assertEqual(browser.delegate.edit_selection_artifact_ids, set())
            self.assertEqual(browser.store.artifact(1).character_name, "")

    def test_preset_click_toggles_between_preset_and_current_equipment_preview(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                _insert_app_shell_artifact(conn, artifact_id=3, pos=1, name="Flower B")
                equip_artifact(conn, 10000050, 3)
                build_id = create_build_preset(
                    conn,
                    name="Preset",
                    slots={1: 1, 2: 2},
                    targets=[
                        {
                            "target_type": "character",
                            "character_id": 10000050,
                            "character_name": "Thoma",
                        }
                    ],
                )
                conn.commit()
            browser = ArtifactBrowserWindow(embedded=True, db_path=db_path)
            browser.set_right_panel_operation_target(
                {"character_id": 10000050, "character_name": "Thoma"}
            )

            browser.select_build_preset(build_id)

            self.assertEqual(browser.selected_build_id, build_id)
            self.assertEqual(browser.current_build_artifact_ids(), {1, 2})
            self.assertEqual(browser.delegate.edit_selection_artifact_ids, {1, 2})
            self.assertEqual(
                browser.equipment_zone_action_button.text(),
                tr("artifact.equipment.apply_preset"),
            )
            self.assertTrue(browser.equipment_zone_label.isHidden())
            self.assertFalse(browser.equipment_zone_action_button.isHidden())
            self.assertTrue(browser.equipment_zone_action_button.isEnabled())
            expected_thoma_current_equipment = tr(
                "artifact.build.current_equipment_for_character",
                name="Thoma",
            )

            browser.select_build_preset(build_id)

            self.assertIsNone(browser.selected_build_id)
            self.assertEqual(browser.current_equipment_preview_slots, {1: 3})
            self.assertEqual(browser.current_build_artifact_ids(), {3})
            self.assertEqual(browser.delegate.edit_selection_artifact_ids, {3})
            self.assertEqual(
                browser.equipment_zone_label.text(),
                expected_thoma_current_equipment,
            )
            self.assertFalse(browser.equipment_zone_label.isHidden())
            self.assertTrue(browser.equipment_zone_action_button.isHidden())

    def test_apply_preset_updates_current_equipment_and_clears_missing_slots(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_artifact(conn, 10000050, 1)
                equip_artifact(conn, 10000050, 2)
                build_id = create_build_preset(
                    conn,
                    name="Flower only",
                    slots={1: 1},
                    targets=[
                        {
                            "target_type": "character",
                            "character_id": 10000050,
                            "character_name": "Thoma",
                        }
                    ],
                )
                before_slots = get_artifact_build_slots(conn, build_id)
                conn.commit()
            browser = ArtifactBrowserWindow(embedded=True, db_path=db_path)
            browser.set_right_panel_operation_target(
                {"character_id": 10000050, "character_name": "Thoma"}
            )
            browser.select_build_preset(build_id)

            browser.apply_selected_build_preset_to_current_equipment()

            with closing(connect_db(db_path)) as conn:
                self.assertEqual(
                    [
                        (row.slot_key, row.artifact_id)
                        for row in list_equipped_artifacts_for_character(conn, 10000050)
                    ],
                    [("flower", 1)],
                )
                self.assertEqual(get_artifact_build_slots(conn, build_id), before_slots)
            self.assertIsNone(browser.selected_build_id)
            self.assertEqual(browser.current_equipment_preview_slots, {1: 1})
            expected_applied_preset = tr(
                "artifact.build.applied_preset_for_character",
                preset="Flower only",
                name="Thoma",
            )
            expected_thoma_current_equipment = tr(
                "artifact.build.current_equipment_for_character",
                name="Thoma",
            )
            self.assertEqual(browser.equipment_zone_label.text(), expected_applied_preset)
            self.assertEqual(browser.store.artifact(1).character_name, "Thoma")
            self.assertEqual(browser.store.artifact(2).character_name, "")

            browser.equip_clicked_artifact(2)

            self.assertEqual(
                browser.equipment_zone_label.text(),
                expected_thoma_current_equipment,
            )
            self.assertEqual(browser.current_equipment_preview_slots, {1: 1, 2: 2})

    def test_apply_preset_conflict_confirmation_blocks_or_applies(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_artifact(conn, 10000051, 2)
                build_id = create_build_preset(
                    conn,
                    name="Borrow plume",
                    slots={2: 2},
                    targets=[
                        {
                            "target_type": "character",
                            "character_id": 10000050,
                            "character_name": "Thoma",
                        }
                    ],
                )
                conn.commit()
            browser = ArtifactBrowserWindow(embedded=True, db_path=db_path)
            browser.set_right_panel_operation_target(
                {"character_id": 10000050, "character_name": "Thoma"}
            )
            browser.select_build_preset(build_id)

            with patch.object(
                browser,
                "confirm_preset_equipment_conflicts",
                return_value=False,
            ) as confirm:
                browser.apply_selected_build_preset_to_current_equipment()

            confirm.assert_called_once_with((10000051,))
            with closing(connect_db(db_path)) as conn:
                self.assertEqual(get_equipped_artifact_owner(conn, 2), 10000051)

            with patch.object(
                browser,
                "confirm_preset_equipment_conflicts",
                return_value=True,
            ) as confirm:
                browser.apply_selected_build_preset_to_current_equipment()

            confirm.assert_called_once_with((10000051,))
            with closing(connect_db(db_path)) as conn:
                self.assertEqual(get_equipped_artifact_owner(conn, 2), 10000050)
            self.assertIsNone(browser.selected_build_id)
            self.assertEqual(browser.current_equipment_preview_slots, {2: 2})

    def test_artifact_card_delegate_marks_foreign_owner_relative_to_target(self) -> None:
        delegate = ArtifactCardDelegate()

        self.assertFalse(delegate._is_foreign_owner(None))
        self.assertTrue(delegate._is_foreign_owner(10000050))

        self.assertTrue(delegate.set_current_owner_character_id(10000050))
        self.assertFalse(delegate._is_foreign_owner(None))
        self.assertFalse(delegate._is_foreign_owner(10000050))
        self.assertTrue(delegate._is_foreign_owner(10000051))
        self.assertFalse(delegate.set_current_owner_character_id(10000050))

    def test_artifact_card_delegate_owner_icon_geometry_extends_outside_item_cell(self) -> None:
        item_rect = QRect(0, 0, GRID_SIZE.width(), GRID_SIZE.height())

        card_rect = ArtifactCardDelegate.card_rect_for_item_rect(item_rect)
        owner_rect = ArtifactCardDelegate.owner_icon_rect_for_card_rect(card_rect)

        self.assertEqual(card_rect.size(), CARD_SIZE)
        self.assertLess(owner_rect.top(), item_rect.top())
        self.assertGreater(owner_rect.right(), item_rect.right())

    def test_artifact_browser_store_loads_current_owner_side_icon(self) -> None:
        with temp_app_shell_db() as db_path:
            icon_path = db_path.parent / "thoma-side.png"
            pixmap = QPixmap(8, 8)
            pixmap.fill(QColor("#00ff00"))
            self.assertTrue(pixmap.save(str(icon_path)))
            with closing(connect_db(db_path)) as conn:
                conn.execute(
                    """
                    UPDATE account_characters
                    SET side_icon_path = ?
                    WHERE character_id = 10000050
                    """,
                    (str(icon_path),),
                )
                equip_artifact(conn, 10000050, 1)
                conn.commit()

            browser = ArtifactBrowserWindow(embedded=True, db_path=db_path)

            artifact = browser.store.artifact(1)
            self.assertEqual(artifact.character_name, "Thoma")
            self.assertEqual(artifact.owner_character_id, 10000050)
            self.assertEqual(artifact.owner_icon_path, icon_path)

    def test_apply_preset_refreshes_right_panel_stats(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                build_id = create_build_preset(
                    conn,
                    name="Two piece",
                    slots={1: 1, 2: 2},
                    targets=[
                        {
                            "target_type": "character",
                            "character_id": 10000050,
                            "character_name": "Thoma",
                        }
                    ],
                )
                conn.commit()
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_right_panel_refresh()
            browser = shell.left_host.ensure_artifact_browser_workspace()
            browser.select_build_preset(build_id)

            with patch.object(shell.right_panel, "set_model", wraps=shell.right_panel.set_model) as set_model:
                browser.apply_selected_build_preset_to_current_equipment()
                self.assertTrue(shell._right_panel_refresh_pending)
                shell.flush_pending_right_panel_refresh()

            details = shell.controller.state.team(0).slot(0).character_details_data
            self.assertEqual(
                details["current_equipped_artifact_ids_by_slot"],
                {"flower": 1, "plume": 2},
            )
            self.assertGreaterEqual(set_model.call_count, 1)

    def test_artifact_click_missing_artifact_fails_cleanly(self) -> None:
        class FakeIndex:
            def data(self, role):
                class FakeArtifact:
                    id = 999999

                return FakeArtifact()

        with temp_app_shell_db() as db_path:
            browser = ArtifactBrowserWindow(embedded=True, db_path=db_path)
            browser.set_right_panel_operation_target(
                {"character_id": 10000050, "character_name": "Thoma"}
            )

            browser.on_artifact_clicked(FakeIndex())

            with closing(connect_db(db_path)) as conn:
                self.assertIsNone(get_equipped_artifact_owner(conn, 999999))

    def test_character_weapon_workspace_uses_overlay_scroll_areas(self) -> None:
        workspace = CharacterWeaponWorkspace()

        self.assertIsInstance(workspace.weapon_area, OverlayVerticalScrollArea)
        self.assertIsInstance(workspace.char_area, OverlayVerticalScrollArea)
        self.assertEqual(
            workspace.weapon_area.verticalScrollBarPolicy().name,
            "ScrollBarAlwaysOff",
        )
        self.assertEqual(
            workspace.char_area.verticalScrollBarPolicy().name,
            "ScrollBarAlwaysOff",
        )

    def test_initial_right_panel_has_no_selected_target(self) -> None:
        shell = AppShell()

        model = shell.controller.right_panel_model()
        self.assertFalse(model.selected_details.has_selection)
        self.assertEqual(shell.controller.selected_team_index, -1)
        self.assertEqual(shell.controller.selected_slot_index, -1)

    def test_controller_character_without_selection_fills_first_empty_slot(self) -> None:
        controller = AppShellController.empty()

        changed = controller.add_or_replace_character(_character_asset("10000050", "Thoma"))

        self.assertTrue(changed)
        slot = controller.state.team(0).slot(0)
        self.assertEqual(slot.character.id, "10000050")
        self.assertEqual(controller.selected_team_index, 0)
        self.assertEqual(controller.selected_slot_index, 0)
        self.assertEqual(slot.character_details_data["account_character"]["portrait_path"], "thoma.png")

    def test_controller_character_with_selection_still_fills_first_empty_slot(self) -> None:
        controller = AppShellController.empty()
        controller.toggle_slot_selection(0, 2)

        changed = controller.add_or_replace_character(_character_asset("10000089", "Furina"))

        self.assertTrue(changed)
        self.assertEqual(controller.state.team(0).slot(0).character.id, "10000089")
        self.assertIsNone(controller.state.team(0).slot(2).character)
        self.assertEqual(controller.selected_slot_index, 0)

    def test_controller_existing_character_click_removes_without_compacting(self) -> None:
        controller = AppShellController.empty()
        controller.add_or_replace_character(_character_asset("10000050", "Thoma"))
        controller.add_or_replace_character(_character_asset("10000089", "Furina"))

        changed = controller.add_or_replace_character(_character_asset("10000050", "Thoma"))

        self.assertTrue(changed)
        self.assertIsNone(controller.state.team(0).slot(0).character)
        self.assertEqual(controller.state.team(0).slot(1).character.id, "10000089")
        selected_ids = [
            slot.character.id
            for slot in controller.state.team(0).slots
            if slot.character is not None
        ]
        self.assertEqual(selected_ids, ["10000089"])

    def test_repeated_slot_click_clears_selected_target(self) -> None:
        controller = AppShellController.empty()

        controller.toggle_slot_selection(0, 1)
        controller.toggle_slot_selection(0, 1)

        self.assertEqual(controller.selected_team_index, -1)
        self.assertEqual(controller.selected_slot_index, -1)

    def test_weapon_without_selected_character_does_not_assign(self) -> None:
        controller = AppShellController.empty()

        changed = controller.assign_weapon_to_selected_slot(_weapon_asset("13407", "Favonius Lance"))

        self.assertFalse(changed)

    def test_weapon_with_selected_character_assigns_compatible_weapon(self) -> None:
        with temp_app_shell_db() as db_path:
            controller = AppShellController.empty(equipment_db_path=db_path)
            controller.add_or_replace_character(_character_asset("10000050", "Thoma", weapon_type=13))

            changed = controller.assign_weapon_to_selected_slot(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )
            with closing(connect_db(db_path)) as conn:
                persisted = get_equipped_weapon_for_character(conn, 10000050)

        self.assertTrue(changed)
        slot = controller.state.team(0).slot(0)
        self.assertEqual(slot.weapon.id, "13407")
        self.assertEqual(slot.character_details_data["account_weapon"]["icon_path"], "fav.png")
        self.assertIsNotNone(persisted)
        assert persisted is not None
        self.assertEqual(persisted.weapon_fingerprint, "fingerprint-13407")

    def test_repeated_weapon_click_unequips_selected_character_weapon(self) -> None:
        with temp_app_shell_db() as db_path:
            controller = AppShellController.empty(equipment_db_path=db_path)
            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            asset = _weapon_asset("13407", "Favonius Lance", weapon_type=13)

            controller.assign_weapon_to_selected_slot(asset)
            changed = controller.assign_weapon_to_selected_slot(asset)
            with closing(connect_db(db_path)) as conn:
                persisted = get_equipped_weapon_for_character(conn, 10000050)

        self.assertTrue(changed)
        slot = controller.state.team(0).slot(0)
        self.assertIsNone(slot.weapon)
        self.assertIsNone(persisted)
        self.assertNotIn("account_weapon", slot.character_details_data)
        self.assertNotIn("weapon_image_path", slot.character_details_data)
        self.assertEqual(slot.character_details_data["weapon_passive_reference"], {})
        self.assertEqual(slot.character_details_data["weapon_display_stat_effects"], [])
        self.assertIsNotNone(controller.last_weapon_equipment_change_result)
        assert controller.last_weapon_equipment_change_result is not None
        self.assertEqual(
            controller.last_weapon_equipment_change_result.operation,
            "unequip_weapon",
        )

    def test_incompatible_weapon_fails_soft(self) -> None:
        controller = AppShellController.empty()
        controller.add_or_replace_character(_character_asset("10000050", "Thoma", weapon_type=13))

        changed = controller.assign_weapon_to_selected_slot(
            _weapon_asset("11401", "Sword", weapon_type=1)
        )

        self.assertFalse(changed)
        self.assertIsNone(controller.state.team(0).slot(0).weapon)

    def test_weapon_type_filter_uses_stable_weapon_type_metadata(self) -> None:
        workspace = CharacterWeaponWorkspace()
        workspace._weapon_type_filters = {"polearm"}

        self.assertTrue(
            workspace._weapon_matches_filters(
                _weapon_asset(
                    "13407",
                    "Favonius Lance",
                    weapon_type=13,
                    weapon_type_name="localized polearm label",
                )
            )
        )
        self.assertFalse(
            workspace._weapon_matches_filters(
                _weapon_asset("11401", "Sword", weapon_type=1, weapon_type_name="sword")
            )
        )

    def test_weapon_rarity_and_type_filters_can_combine(self) -> None:
        workspace = CharacterWeaponWorkspace()
        workspace._weapon_type_filters = {"polearm"}
        workspace._weapon_rarity_filters = {4}

        self.assertTrue(
            workspace._weapon_matches_filters(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13, rarity=4)
            )
        )
        self.assertFalse(
            workspace._weapon_matches_filters(
                _weapon_asset("13505", "Five Star Spear", weapon_type=13, rarity=5)
            )
        )

    def test_persistent_weapon_clears_for_new_character_and_restores_old_character(self) -> None:
        with temp_app_shell_db() as db_path:
            controller = AppShellController.empty(equipment_db_path=db_path)
            controller.add_or_replace_character(_character_asset("10000050", "Thoma", weapon_type=13))
            controller.assign_weapon_to_selected_slot(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )

            controller.add_or_replace_character(_character_asset("10000050", "Thoma", weapon_type=13))
            with closing(connect_db(db_path)) as conn:
                persisted_after_remove = get_equipped_weapon_for_character(conn, 10000050)
            controller.add_or_replace_character(_character_asset("10000089", "Furina", weapon_type=1))

            furina_slot = controller.state.team(0).slot(0)
            details = controller.right_panel_model().selected_details

            controller.add_or_replace_character(_character_asset("10000089", "Furina", weapon_type=1))
            controller.add_or_replace_character(_character_asset("10000050", "Thoma", weapon_type=13))
            thoma_slot = controller.state.team(0).slot(0)

        self.assertIsNotNone(persisted_after_remove)
        self.assertEqual(furina_slot.character.id, "10000089")
        self.assertIsNone(furina_slot.weapon)
        self.assertEqual(details.weapon_name, "")
        self.assertEqual(details.weapon_icon_path, "")
        self.assertEqual(details.weapon_tooltip, "")
        self.assertEqual(thoma_slot.character.id, "10000050")
        self.assertEqual(thoma_slot.weapon.id, "13407")

    def test_adding_character_restores_persistent_weapon_from_sqlite(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_weapon(conn, 10000050, "fingerprint-13407")
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)

            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )

        slot = controller.state.team(0).slot(0)
        self.assertEqual(slot.weapon.id, "13407")
        self.assertEqual(
            slot.character_details_data["account_weapon"]["source_key"],
            "fingerprint-13407",
        )

    def test_replacing_character_restores_incoming_own_persistent_weapon(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_weapon(conn, 10000050, "fingerprint-13407")
                equip_weapon(conn, 10000089, "fingerprint-11401")
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)

            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            controller.add_or_replace_character(
                _character_asset("10000089", "Furina", weapon_type=1)
            )

        slot = controller.state.team(0).slot(0)
        self.assertEqual(slot.character.id, "10000089")
        self.assertEqual(slot.weapon.id, "11401")
        self.assertEqual(slot.character_details_data["account_weapon"]["name"], "Sword")

    def test_app_shell_assignment_moves_occupied_single_copy_weapon(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_weapon(conn, 10000051, "fingerprint-13407")
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)
            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )

            changed = controller.assign_weapon_to_selected_slot(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )
            with closing(connect_db(db_path)) as conn:
                target_weapon = get_equipped_weapon_for_character(conn, 10000050)
                previous_owner_weapon = get_equipped_weapon_for_character(conn, 10000051)

        self.assertTrue(changed)
        self.assertEqual(controller.state.team(0).slot(0).weapon.id, "13407")
        self.assertEqual(controller.last_equipment_error, "")
        self.assertIsNotNone(target_weapon)
        assert target_weapon is not None
        self.assertEqual(target_weapon.weapon_fingerprint, "fingerprint-13407")
        self.assertIsNone(previous_owner_weapon)

    def test_app_shell_assignment_refreshes_visible_previous_owner_after_weapon_swap(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_weapon(conn, 10000050, "fingerprint-13408")
                equip_weapon(conn, 10000051, "fingerprint-13407")
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)
            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            controller.add_or_replace_character(
                _character_asset("10000051", "Polearm Friend", weapon_type=13)
            )
            controller.toggle_slot_selection(0, 0)

            changed = controller.assign_weapon_to_selected_slot(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )
            with closing(connect_db(db_path)) as conn:
                thoma_weapon = get_equipped_weapon_for_character(conn, 10000050)
                friend_weapon = get_equipped_weapon_for_character(conn, 10000051)

        self.assertTrue(changed)
        self.assertEqual(controller.state.team(0).slot(0).weapon.id, "13407")
        self.assertEqual(controller.state.team(0).slot(1).weapon.id, "13408")
        self.assertIsNotNone(thoma_weapon)
        self.assertIsNotNone(friend_weapon)
        assert thoma_weapon is not None
        assert friend_weapon is not None
        self.assertEqual(thoma_weapon.weapon_fingerprint, "fingerprint-13407")
        self.assertEqual(friend_weapon.weapon_fingerprint, "fingerprint-13408")
        self.assertIsNotNone(controller.last_weapon_equipment_change_result)
        assert controller.last_weapon_equipment_change_result is not None
        self.assertEqual(
            set(controller.last_weapon_equipment_change_result.affected_character_ids),
            {10000050, 10000051},
        )

    def test_app_shell_assignment_clears_visible_previous_owner_after_weapon_move(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_weapon(conn, 10000051, "fingerprint-13407")
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)
            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            controller.add_or_replace_character(
                _character_asset("10000051", "Polearm Friend", weapon_type=13)
            )
            controller.toggle_slot_selection(0, 0)

            changed = controller.assign_weapon_to_selected_slot(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )

        self.assertTrue(changed)
        self.assertEqual(controller.state.team(0).slot(0).weapon.id, "13407")
        previous_owner_slot = controller.state.team(0).slot(1)
        self.assertIsNone(previous_owner_slot.weapon)
        self.assertNotIn("account_weapon", previous_owner_slot.character_details_data)
        self.assertNotIn("weapon_image_path", previous_owner_slot.character_details_data)

    def test_app_shell_has_no_session_weapon_memory_source_of_truth(self) -> None:
        controller = AppShellController.empty()

        self.assertFalse(hasattr(controller, "session_equipment_by_character_id"))

    def test_persistent_equipment_is_per_character_across_modes(self) -> None:
        with temp_app_shell_db() as db_path:
            controller = AppShellController.empty(equipment_db_path=db_path)
            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            controller.assign_weapon_to_selected_slot(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )

            controller.set_mode(MODE_DPS_DUMMY)
            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )

        self.assertEqual(len(controller.state.teams), 1)
        self.assertEqual(controller.state.team(0).slot(0).weapon.id, "13407")

    def test_adding_character_reads_current_equipped_artifact_ids_readonly(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_artifact(conn, 10000050, 1)
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)

            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )

        details = controller.state.team(0).slot(0).character_details_data
        self.assertEqual(
            details["current_equipped_artifact_ids_by_slot"],
            {"flower": 1},
        )
        self.assertEqual(details["selected_build"]["build_id"], None)
        self.assertEqual(
            details["selected_build"]["identity_source"],
            "current_equipment",
        )
        self.assertEqual(
            details["stat_snapshot"]["artifact"]["summary"]["artifact_ids_by_pos"],
            {"1": 1},
        )
        stat_totals = {
            item["property_type"]: item["raw_value"]
            for item in details["stat_snapshot"]["artifact"]["summary"]["stat_totals"]
        }
        self.assertEqual(stat_totals[2], 4780.0)
        self.assertTrue(details["source_notes"]["current_equipped_artifacts_readonly"])
        self.assertTrue(details["source_notes"]["current_equipment_artifact_snapshot"])

    def test_current_equipped_artifact_set_bonus_appears_in_right_panel(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_artifact(conn, 10000050, 1)
                equip_artifact(conn, 10000050, 2)
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)

            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            model = controller.right_panel_model()

        artifact_sources = [
            item
            for item in model.selected_details.bonus_sources
            if item.source_kind == "artifact_set_static"
        ]
        self.assertEqual(model.selected_details.active_sets, ("2p Current Set",))
        self.assertEqual(len(artifact_sources), 1)
        self.assertEqual(artifact_sources[0].short_effects, ("ATK +18%",))

    def test_replacing_character_clears_current_artifact_snapshot_from_slot(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_artifact(conn, 10000050, 1)
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)

            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            controller.add_or_replace_character(
                _character_asset("10000089", "Furina", weapon_type=1)
            )

        details = controller.state.team(0).slot(0).character_details_data
        self.assertEqual(details["account_character"]["id"], "10000089")
        self.assertNotIn("current_equipped_artifact_ids_by_slot", details)
        self.assertNotIn("stat_snapshot", details)
        self.assertEqual(controller.right_panel_model().selected_details.active_sets, ())

    def test_current_equipped_artifact_restore_does_not_create_build_rows(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_artifact(conn, 10000050, 1)
                before = _artifact_build_count(conn)
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)

            controller.add_or_replace_character(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            with closing(connect_db(db_path)) as conn:
                after = _artifact_build_count(conn)

        self.assertEqual(after, before)

    def test_sequential_quick_pick_fills_team_one_then_team_two(self) -> None:
        controller = AppShellController.empty()

        for index in range(5):
            controller.add_or_replace_character(
                _character_asset(f"1000005{index}", f"Character {index}")
            )

        self.assertEqual(
            [slot.character.id for slot in controller.state.team(0).slots],
            ["10000050", "10000051", "10000052", "10000053"],
        )
        self.assertEqual(controller.state.team(1).slot(0).character.id, "10000054")

    def test_sequential_quick_pick_preserves_gaps_and_blocks_when_full(self) -> None:
        controller = AppShellController.empty()
        for index in range(8):
            controller.add_or_replace_character(
                _character_asset(f"1000005{index}", f"Character {index}")
            )

        self.assertFalse(
            controller.add_or_replace_character(_character_asset("10000099", "Overflow"))
        )

        controller.add_or_replace_character(_character_asset("10000051", "Character 1"))
        self.assertIsNone(controller.state.team(0).slot(1).character)
        controller.add_or_replace_character(_character_asset("10000099", "Overflow"))

        self.assertEqual(controller.state.team(0).slot(1).character.id, "10000099")
        self.assertEqual(controller.state.team(0).slot(2).character.id, "10000052")

    def test_slot_swap_moves_full_payload_and_selects_dragged_slot(self) -> None:
        controller = AppShellController.empty()
        controller.add_or_replace_character_fast(
            _character_asset("10000050", "Thoma", weapon_type=13)
        )
        controller.add_or_replace_character_fast(
            _character_asset("10000089", "Furina", weapon_type=1)
        )
        controller.state = controller.state.set_weapon(
            0,
            0,
            {
                "id": "13407",
                "name": "Favonius Lance",
                "weapon_type": "polearm",
            },
        )
        controller.state = controller.state.attach_character_details_data(
            0,
            0,
            {
                "account_character": {"id": "10000050", "name": "Thoma"},
                "payload_marker": "source-details",
            },
        )

        changed = controller.swap_slots(0, 0, 0, 1)

        self.assertTrue(changed)
        source_after = controller.state.team(0).slot(0)
        target_after = controller.state.team(0).slot(1)
        self.assertEqual(source_after.character.id, "10000089")
        self.assertEqual(target_after.character.id, "10000050")
        self.assertEqual(target_after.weapon.id, "13407")
        self.assertEqual(target_after.character_details_data["payload_marker"], "source-details")
        self.assertEqual(controller.selected_team_index, 0)
        self.assertEqual(controller.selected_slot_index, 1)

    def test_slot_swap_to_empty_slot_behaves_like_move(self) -> None:
        controller = AppShellController.empty()
        controller.add_or_replace_character_fast(
            _character_asset("10000050", "Thoma", weapon_type=13)
        )

        changed = controller.swap_slots(0, 0, 1, 0)

        self.assertTrue(changed)
        self.assertTrue(controller.state.team(0).slot(0).is_empty)
        self.assertEqual(controller.state.team(1).slot(0).character.id, "10000050")
        self.assertEqual(controller.selected_team_index, 1)
        self.assertEqual(controller.selected_slot_index, 0)

    def test_app_shell_slot_drop_swaps_slots_and_schedules_refresh(self) -> None:
        shell = AppShell()
        shell.controller.add_or_replace_character_fast(_character_asset("10000050", "Thoma"))
        shell.controller.add_or_replace_character_fast(_character_asset("10000089", "Furina"))

        shell._on_slot_dropped(0, 0, 0, 1)

        self.assertEqual(shell.controller.state.team(0).slot(1).character.id, "10000050")
        self.assertEqual(shell.controller.selected_slot_index, 1)
        self.assertTrue(shell._right_panel_refresh_pending)

    def test_mode_states_keep_independent_quick_picks(self) -> None:
        controller = AppShellController.empty()
        controller.add_or_replace_character(_character_asset("10000050", "Thoma"))

        controller.set_mode(MODE_DPS_DUMMY)
        controller.add_or_replace_character(_character_asset("10000089", "Furina"))

        self.assertEqual(controller.state.team(0).slot(0).character.id, "10000089")
        self.assertEqual(len(controller.state.teams), 1)

        controller.set_mode(MODE_ABYSS)
        self.assertEqual(controller.state.team(0).slot(0).character.id, "10000050")
        self.assertEqual(len(controller.state.teams), 2)

    def test_roster_selection_markers_expose_team_color_and_slot_number(self) -> None:
        controller = AppShellController.empty()
        for index in range(5):
            controller.add_or_replace_character(
                _character_asset(f"1000005{index}", f"Character {index}")
            )

        markers = controller.roster_selection_markers()

        self.assertEqual(markers["10000050"].slot_number, 1)
        self.assertEqual(markers["10000050"].team_index, 0)
        self.assertEqual(markers["10000054"].slot_number, 1)
        self.assertEqual(markers["10000054"].team_index, 1)
        self.assertNotEqual(markers["10000050"].color, markers["10000054"].color)

        controller.add_or_replace_character(_character_asset("10000054", "Character 4"))
        self.assertNotIn("10000054", controller.roster_selection_markers())

    def test_marker_update_does_not_reload_character_grid(self) -> None:
        workspace = CharacterWeaponWorkspace()
        workspace._initial_grid_built = True
        card = AssetIconLabel("portrait.png", 24, asset=_character_asset("10000050", "Thoma"))
        workspace._character_cards_by_id = {"10000050": card}

        with patch.object(workspace, "reload_characters", side_effect=AssertionError):
            workspace.set_character_selection_markers(
                {
                    "10000050": RosterSelectionMarker(
                        team_index=0,
                        slot_index=0,
                        slot_number=1,
                        color="#3ed47b",
                    )
                },
                affected_character_ids={"10000050"},
            )

        self.assertIsNotNone(card.selection_marker)
        self.assertEqual(card.selection_marker.slot_number, 1)

    def test_marker_update_clears_removed_card_without_pixmap_reload(self) -> None:
        workspace = CharacterWeaponWorkspace()
        workspace._initial_grid_built = True
        card = AssetIconLabel("portrait.png", 24, asset=_character_asset("10000050", "Thoma"))
        marker = RosterSelectionMarker(
            team_index=0,
            slot_index=0,
            slot_number=1,
            color="#3ed47b",
        )
        card.set_selection_marker(marker)
        workspace._character_selection_markers = {"10000050": marker}
        workspace._character_cards_by_id = {"10000050": card}

        with (
            patch.object(workspace, "reload_characters", side_effect=AssertionError),
            patch.object(card, "_update_pixmap", side_effect=AssertionError),
        ):
            workspace.set_character_selection_markers(
                {},
                affected_character_ids={"10000050"},
            )

        self.assertIsNone(card.selection_marker)

    def test_app_shell_character_click_uses_incremental_marker_update(self) -> None:
        shell = AppShell()
        workspace = shell.left_host.character_weapon_workspace
        workspace._initial_grid_built = True
        card = AssetIconLabel("portrait.png", 24, asset=_character_asset("10000050", "Thoma"))
        workspace._character_cards_by_id = {"10000050": card}

        with patch.object(workspace, "reload_characters", side_effect=AssertionError):
            shell._on_character_clicked(_character_asset("10000050", "Thoma"))

        self.assertIsNotNone(card.selection_marker)
        self.assertEqual(card.selection_marker.slot_number, 1)
        shell.flush_pending_right_panel_refresh()

    def test_roster_click_defers_right_panel_refresh(self) -> None:
        shell = AppShell()
        workspace = shell.left_host.character_weapon_workspace
        workspace._initial_grid_built = True
        card = AssetIconLabel("portrait.png", 24, asset=_character_asset("10000050", "Thoma"))
        workspace._character_cards_by_id = {"10000050": card}

        with patch.object(shell.right_panel, "set_model", wraps=shell.right_panel.set_model) as set_model:
            shell._on_character_clicked(_character_asset("10000050", "Thoma"))

            self.assertIsNotNone(card.selection_marker)
            self.assertEqual(set_model.call_count, 0)
            self.assertFalse(shell._right_panel_refresh_pending)
            self.assertIsNotNone(shell._equipment_hydration_pending)

            shell.flush_pending_equipment_hydration()
            self.assertTrue(shell._right_panel_refresh_pending)
            shell.flush_pending_right_panel_refresh()

        self.assertEqual(set_model.call_count, 1)

    def test_roster_click_defers_persistent_equipment_hydration(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_artifact(conn, 10000050, 1)
                conn.commit()
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )

            shell._on_character_clicked(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )

            details = shell.controller.state.team(0).slot(0).character_details_data
            self.assertNotIn("current_equipped_artifact_ids_by_slot", details)
            self.assertIsNotNone(shell._equipment_hydration_pending)
            self.assertEqual(
                shell.controller.right_panel_model().selected_details.active_sets,
                (),
            )

            shell.flush_pending_equipment_hydration()

        details = shell.controller.state.team(0).slot(0).character_details_data
        self.assertEqual(
            details["current_equipped_artifact_ids_by_slot"],
            {"flower": 1},
        )
        self.assertEqual(
            shell.controller.right_panel_model().selected_details.active_sets,
            (),
        )

    def test_persistent_equipment_hydration_stale_guard_skips_changed_slot(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                equip_artifact(conn, 10000050, 1)
                conn.commit()
            controller = AppShellController.empty(equipment_db_path=db_path)

            result = controller.add_or_replace_character_fast(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            controller.add_or_replace_character_fast(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            controller.add_or_replace_character_fast(
                _character_asset("10000089", "Furina", weapon_type=1)
            )
            timings = controller.hydrate_persistent_equipment_for_slot(
                result.team_index,
                result.slot_index,
                result.character_id,
            )

        slot = controller.state.team(0).slot(0)
        self.assertEqual(slot.character.id, "10000089")
        self.assertEqual(timings["hydration_applied"], 0.0)
        self.assertNotIn(
            "current_equipped_artifact_ids_by_slot",
            slot.character_details_data,
        )

    def test_roster_click_defers_weapon_filter_reload(self) -> None:
        shell = AppShell()
        workspace = shell.left_host.character_weapon_workspace

        with patch.object(
            workspace,
            "set_auto_weapon_type_filter",
            wraps=workspace.set_auto_weapon_type_filter,
        ) as apply_filter:
            shell._on_character_clicked(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )

            self.assertEqual(apply_filter.call_count, 0)
            self.assertTrue(shell._weapon_filter_sync_pending)

            shell.flush_pending_weapon_filter_sync()

        self.assertEqual(apply_filter.call_count, 1)

    def test_right_panel_same_structure_refresh_preserves_team_and_slot_widgets(self) -> None:
        shell = AppShell()
        team_widgets_before = list(shell.right_panel._team_widgets)
        slot_widgets_before = list(shell.right_panel._slot_widgets)
        chamber_before = shell.right_panel._chamber_table

        shell.controller.add_or_replace_character_fast(
            _character_asset("10000050", "Thoma", weapon_type=13)
        )
        shell.right_panel.set_model(shell.controller.right_panel_model())

        self.assertEqual(shell.right_panel._team_widgets, team_widgets_before)
        self.assertEqual(shell.right_panel._slot_widgets, slot_widgets_before)
        self.assertIs(shell.right_panel._chamber_table, chamber_before)
        self.assertEqual(shell.right_panel._slot_widgets[0].objectName(), "SlotCardSelected")

    def test_right_panel_slot_selection_refresh_preserves_slot_widget_identity(self) -> None:
        shell = AppShell()
        shell.controller.add_or_replace_character_fast(
            _character_asset("10000050", "Thoma", weapon_type=13)
        )
        shell.right_panel.set_model(shell.controller.right_panel_model())
        slot_widget = shell.right_panel._slot_widgets[0]

        shell.controller.toggle_slot_selection(0, 0)
        shell.right_panel.set_model(shell.controller.right_panel_model())

        self.assertIs(shell.right_panel._slot_widgets[0], slot_widget)
        self.assertEqual(slot_widget.objectName(), "SlotCard")

    def test_right_panel_selected_details_refresh_preserves_skeleton_widgets(self) -> None:
        shell = AppShell()
        details_frame = shell.right_panel._details_frame

        shell.controller.add_or_replace_character_fast(
            _character_asset("10000050", "Thoma", weapon_type=13)
        )
        shell.right_panel.set_model(shell.controller.right_panel_model())
        body = details_frame._body
        stats_frame = details_frame._stats_frame
        meta_frame = details_frame._meta_frame
        bonus_strip = details_frame._bonus_strip

        shell.controller.add_or_replace_character_fast(
            _character_asset("10000089", "Furina", weapon_type=1)
        )
        shell.right_panel.set_model(shell.controller.right_panel_model())

        self.assertIs(details_frame._body, body)
        self.assertIs(details_frame._stats_frame, stats_frame)
        self.assertIs(details_frame._meta_frame, meta_frame)
        self.assertIs(details_frame._bonus_strip, bonus_strip)
        self.assertEqual(details_frame._mode, "selected")

    def test_rapid_roster_clicks_coalesce_right_panel_refresh(self) -> None:
        shell = AppShell()

        with patch.object(shell.right_panel, "set_model", wraps=shell.right_panel.set_model) as set_model:
            for index in range(4):
                shell._on_character_clicked(
                    _character_asset(f"1000005{index}", f"Character {index}")
                )

            self.assertEqual(set_model.call_count, 0)
            self.assertFalse(shell._right_panel_refresh_pending)
            self.assertIsNotNone(shell._equipment_hydration_pending)

            shell.flush_pending_equipment_hydration()
            self.assertTrue(shell._right_panel_refresh_pending)
            shell.flush_pending_right_panel_refresh()

        self.assertEqual(set_model.call_count, 1)

    def test_weapon_click_schedules_right_panel_refresh(self) -> None:
        with temp_app_shell_db() as db_path:
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_right_panel_refresh()

            with patch.object(shell.right_panel, "set_model", wraps=shell.right_panel.set_model) as set_model:
                shell._on_weapon_clicked(_weapon_asset("13407", "Favonius Lance", weapon_type=13))

                self.assertEqual(set_model.call_count, 0)
                self.assertTrue(shell._right_panel_refresh_pending)

                shell.flush_pending_right_panel_refresh()

        self.assertEqual(set_model.call_count, 1)

    def test_right_panel_uses_visible_asset_path_for_character_portrait(self) -> None:
        shell = AppShell()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "portrait.png"
            pixmap = QPixmap(8, 8)
            pixmap.fill(QColor("#00ff00"))
            self.assertTrue(pixmap.save(str(path)))
            asset = _character_asset("10000050", "Thoma")
            asset["path"] = str(path)
            asset["metadata"]["character"]["portrait_path"] = "missing-relative.png"

            shell._on_character_clicked(asset)
            shell.flush_pending_right_panel_refresh()

            model = shell.controller.right_panel_model()

        self.assertEqual(model.teams[0].slots[0].portrait_path, str(path))

    def test_right_panel_uses_visible_asset_path_for_weapon_icon(self) -> None:
        with temp_app_shell_db() as db_path:
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_right_panel_refresh()
            with tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "weapon.png"
                pixmap = QPixmap(8, 8)
                pixmap.fill(QColor("#00ff00"))
                self.assertTrue(pixmap.save(str(path)))
                asset = _weapon_asset("13407", "Favonius Lance", weapon_type=13)
                asset["path"] = str(path)
                asset["metadata"]["weapon"]["icon_path"] = "missing-relative-weapon.png"

                shell._on_weapon_clicked(asset)
                shell.flush_pending_right_panel_refresh()

                model = shell.controller.right_panel_model()

        self.assertEqual(model.teams[0].slots[0].weapon_image_path, str(path))
        self.assertEqual(model.selected_details.weapon_icon_path, str(path))

    def test_app_shell_weapon_assignment_loads_passive_tooltip_and_bonus_source(self) -> None:
        with temp_app_shell_db() as db_path:
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_right_panel_refresh()

            with (
                patch(
                "ui.app_shell.get_weapon_passive_tooltip",
                return_value={
                    "passive_name": "Windfall",
                    "passive_text": "CRIT Hits generate Elemental Particles.",
                    "language": "en-us",
                },
                ) as passive_lookup,
                patch(
                    "ui.app_shell.list_weapon_display_stat_effects",
                    return_value=[
                        {
                            "weapon_id": 13407,
                            "refinement": 5,
                            "stat_key": "ENERGY_RECHARGE",
                            "value": 12,
                            "value_type": "percent_points",
                        }
                    ],
                ) as effects_lookup,
            ):
                weapon_asset = _weapon_asset("13407", "Favonius Lance", weapon_type=13, rarity=4)
                weapon_asset["metadata"]["weapon"]["desc"] = "A polearm made from old lore."
                shell._on_weapon_clicked(
                    weapon_asset
                )
                shell.flush_pending_right_panel_refresh()

            model = shell.controller.right_panel_model()
        weapon_sources = [
            item
            for item in model.selected_details.bonus_sources
            if item.source_kind == "weapon_passive_static"
        ]

        self.assertEqual(passive_lookup.call_count, 1)
        self.assertEqual(effects_lookup.call_count, 1)
        self.assertIn("Favonius Lance R5", model.selected_details.weapon_tooltip)
        self.assertIn("Windfall", model.selected_details.weapon_tooltip)
        self.assertIn("Elemental Particles", model.selected_details.weapon_tooltip)
        self.assertNotIn("old lore", model.selected_details.weapon_tooltip)
        self.assertEqual(len(weapon_sources), 1)
        self.assertEqual(weapon_sources[0].short_effects, ("ER +12%",))
        self.assertIn("Windfall", weapon_sources[0].tooltip_body)

    def test_switching_weapon_clears_stale_static_passive_and_tooltip(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                _seed_weapon_static_effect(
                    conn,
                    weapon_id=13407,
                    stat_key="ATK_PERCENT",
                    value=15.0,
                    value_type="percent_points",
                    passive_name="Old ATK Passive",
                    passive_text="Increases ATK by 15%.",
                )
                conn.commit()
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_right_panel_refresh()

            shell._on_weapon_clicked(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )
            shell.flush_pending_right_panel_refresh()
            with_bonus = shell.controller.right_panel_model()
            shell._on_weapon_clicked(
                _weapon_asset("13408", "Kitain Cross Spear", weapon_type=13)
            )
            shell.flush_pending_right_panel_refresh()
            no_bonus = shell.controller.right_panel_model()

        self.assertTrue(
            any(
                item.source_kind == "weapon_passive_static"
                and item.short_effects == ("ATK +15%",)
                for item in with_bonus.selected_details.bonus_sources
            )
        )
        slot_details = shell.controller.state.team(0).slot(0).character_details_data
        self.assertEqual(slot_details["weapon_display_stat_effects"], [])
        self.assertEqual(slot_details["weapon_passive_reference"], {})
        self.assertFalse(
            any(
                item.source_kind == "weapon_passive_static"
                for item in no_bonus.selected_details.bonus_sources
            )
        )
        self.assertNotIn("Old ATK Passive", no_bonus.selected_details.weapon_tooltip)
        self.assertNotIn("Increases ATK", no_bonus.selected_details.weapon_tooltip)

    def test_switching_weapon_clears_stale_em_static_passive_display_stats(self) -> None:
        with temp_app_shell_db() as db_path:
            with closing(connect_db(db_path)) as conn:
                _seed_weapon_static_effect(
                    conn,
                    weapon_id=13407,
                    stat_key="ELEMENTAL_MASTERY",
                    value=100.0,
                    value_type="flat",
                    passive_name="Old EM Passive",
                    passive_text="Increases Elemental Mastery by 100.",
                )
                conn.commit()
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_right_panel_refresh()

            shell._on_weapon_clicked(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )
            shell.flush_pending_right_panel_refresh()
            with_bonus = shell.controller.right_panel_model()
            shell._on_weapon_clicked(
                _weapon_asset("13408", "Kitain Cross Spear", weapon_type=13)
            )
            shell.flush_pending_right_panel_refresh()
            no_bonus = shell.controller.right_panel_model()

        self.assertTrue(
            any(row.label == "EM" and row.value == "100" for row in with_bonus.selected_details.stat_rows)
        )
        self.assertFalse(
            any(row.label == "EM" for row in no_bonus.selected_details.stat_rows)
        )
        self.assertFalse(
            any(
                item.source_kind == "weapon_passive_static"
                for item in no_bonus.selected_details.bonus_sources
            )
        )

    def test_team_bonus_member_icons_use_visible_asset_paths(self) -> None:
        shell = AppShell()
        with tempfile.TemporaryDirectory() as temp_dir:
            first_path = Path(temp_dir) / "first.png"
            second_path = Path(temp_dir) / "second.png"
            first_pixmap = QPixmap(8, 8)
            first_pixmap.fill(QColor("#00ff00"))
            second_pixmap = QPixmap(8, 8)
            second_pixmap.fill(QColor("#0000ff"))
            self.assertTrue(first_pixmap.save(str(first_path)))
            self.assertTrue(second_pixmap.save(str(second_path)))
            first = _character_asset("10000050", "Thoma")
            second = _character_asset("10000089", "Furina", weapon_type=1)
            for asset, path in ((first, first_path), (second, second_path)):
                asset["path"] = str(path)
                character = asset["metadata"]["character"]
                character["portrait_path"] = "missing-relative-portrait.png"
                character["side_icon_path"] = "missing-relative-side.png"
                character["traits"] = ["hexerei", "moonsign"]

            shell._on_character_clicked(first)
            shell._on_character_clicked(second)
            model = shell.controller.right_panel_model()

        sources = {item.source_kind: item for item in model.selected_details.bonus_sources}
        self.assertIn("hexerei", sources)
        self.assertIn("moonsign", sources)
        self.assertEqual(sources["hexerei"].character_icons[:2], (str(first_path), str(second_path)))
        self.assertEqual(sources["moonsign"].character_icons[:2], (str(first_path), str(second_path)))

    def test_selected_character_auto_filters_weapons_by_type_and_clears_on_cancel(self) -> None:
        shell = AppShell()
        workspace = shell.left_host.character_weapon_workspace
        with patch(
            "ui.app_shell.load_account_weapon_stack_asset_items",
            return_value=[
                _weapon_asset("13407", "Favonius Lance", weapon_type=13),
                _weapon_asset("11401", "Sword", weapon_type=1, weapon_type_name="Sword"),
            ],
        ):
            shell._on_character_clicked(_character_asset("10000050", "Thoma", weapon_type=13))
            shell.flush_pending_weapon_filter_sync()

            self.assertEqual(workspace._weapon_type_filters, {"polearm"})
            self.assertTrue(workspace._weapon_type_buttons["polearm"].isChecked())
            self.assertFalse(workspace._weapon_type_buttons["sword"].isChecked())
            self.assertEqual(workspace.weapon_grid.count(), 1)

            shell._on_slot_selected(0, 0)
            shell.flush_pending_weapon_filter_sync()

            self.assertEqual(workspace._weapon_type_filters, set())
            self.assertFalse(workspace._weapon_type_buttons["polearm"].isChecked())
            self.assertFalse(workspace._weapon_type_buttons["sword"].isChecked())

            shell._on_character_clicked(_character_asset("10000089", "Furina", weapon_type=1))
            shell.flush_pending_weapon_filter_sync()

            self.assertEqual(workspace._weapon_type_filters, {"sword"})
            self.assertTrue(workspace._weapon_type_buttons["sword"].isChecked())
            self.assertFalse(workspace._weapon_type_buttons["polearm"].isChecked())

        shell.flush_pending_right_panel_refresh()

    def test_mode_switch_syncs_markers_without_grid_rebuild(self) -> None:
        shell = AppShell()
        workspace = shell.left_host.character_weapon_workspace
        workspace._initial_grid_built = True
        card = AssetIconLabel("portrait.png", 24, asset=_character_asset("10000050", "Thoma"))
        workspace._character_cards_by_id = {"10000050": card}

        with patch.object(workspace, "reload_characters", side_effect=AssertionError):
            shell._on_character_clicked(_character_asset("10000050", "Thoma"))
            self.assertIsNotNone(card.selection_marker)
            shell._on_mode_requested(MODE_DPS_DUMMY)

        self.assertIsNone(card.selection_marker)
        self.assertFalse(shell._right_panel_refresh_pending)

    def test_mode_switch_refreshes_model_before_showing_requested_run_page(self) -> None:
        shell = AppShell()
        shell._on_character_clicked(_character_asset("10000050", "Thoma"))
        shell.flush_pending_right_panel_refresh()

        with patch.object(shell.right_panel, "set_model", wraps=shell.right_panel.set_model) as set_model:
            shell._on_mode_requested(MODE_DPS_DUMMY)

        self.assertEqual(set_model.call_count, 1)
        self.assertFalse(shell._right_panel_refresh_pending)
        self.assertEqual(shell.right_panel._model.mode, MODE_DPS_DUMMY)

    def test_character_filters_use_session_cached_items(self) -> None:
        workspace = CharacterWeaponWorkspace()
        workspace._initial_grid_built = True

        with patch(
            "ui.app_shell.load_account_character_asset_items",
            return_value=[
                _character_asset("10000050", "Thoma"),
                _character_asset("10000089", "Furina", weapon_type=1),
            ],
        ) as load_items:
            workspace.reload_characters()
            workspace._character_weapon_filters = {"sword"}
            workspace.reload_characters()

        self.assertEqual(load_items.call_count, 1)
        self.assertEqual(list(workspace._character_cards_by_id), ["10000089"])

    def test_weapon_filters_use_session_cached_items(self) -> None:
        workspace = CharacterWeaponWorkspace()
        workspace._initial_grid_built = True

        with patch(
            "ui.app_shell.load_account_weapon_stack_asset_items",
            return_value=[
                _weapon_asset("13407", "Favonius Lance", weapon_type=13),
                _weapon_asset("11401", "Sword", weapon_type=1),
            ],
        ) as load_items:
            workspace.reload_weapons()
            workspace._weapon_type_filters = {"sword"}
            workspace.reload_weapons()

        self.assertEqual(load_items.call_count, 1)
        self.assertEqual(workspace.weapon_grid.count(), 1)

    def test_weapon_asset_items_include_owner_badge_metadata_for_equipped_weapon(self) -> None:
        with temp_app_shell_db() as db_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                weapon_icon = Path(temp_dir) / "weapon.png"
                side_icon = Path(temp_dir) / "side.png"
                for path, color in ((weapon_icon, "#ffcc00"), (side_icon, "#00ccff")):
                    pixmap = QPixmap(8, 8)
                    pixmap.fill(QColor(color))
                    self.assertTrue(pixmap.save(str(path)))
                with closing(connect_db(db_path)) as conn:
                    conn.execute(
                        """
                        UPDATE account_weapon_observed_stacks
                        SET icon_path = ?
                        WHERE weapon_fingerprint = 'fingerprint-13407'
                        """,
                        (str(weapon_icon),),
                    )
                    conn.execute(
                        """
                        UPDATE account_characters
                        SET side_icon_path = ?
                        WHERE character_id = 10000050
                        """,
                        (str(side_icon),),
                    )
                    equip_weapon(conn, 10000050, "fingerprint-13407")
                    conn.commit()

                assets = load_account_weapon_stack_asset_items(db_path=db_path)

        owned = next(
            asset
            for asset in assets
            if asset["metadata"]["weapon"]["source_key"] == "fingerprint-13407"
        )
        badges = owned["metadata"].get("owner_badges") or []
        self.assertEqual(len(badges), 1)
        self.assertEqual(badges[0]["character_id"], "10000050")
        self.assertEqual(badges[0]["side_icon_path"], str(side_icon))
        self.assertEqual(owned["metadata"]["extra_owner_count"], 0)

    def test_weapon_asset_items_omit_owner_badge_metadata_for_unequipped_weapon(self) -> None:
        with temp_app_shell_db() as db_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                weapon_icon = Path(temp_dir) / "weapon.png"
                pixmap = QPixmap(8, 8)
                pixmap.fill(QColor("#ffcc00"))
                self.assertTrue(pixmap.save(str(weapon_icon)))
                with closing(connect_db(db_path)) as conn:
                    conn.execute(
                        """
                        UPDATE account_weapon_observed_stacks
                        SET icon_path = ?
                        WHERE weapon_fingerprint = 'fingerprint-13407'
                        """,
                        (str(weapon_icon),),
                    )
                    conn.commit()

                assets = load_account_weapon_stack_asset_items(db_path=db_path)

        unowned = next(
            asset
            for asset in assets
            if asset["metadata"]["weapon"]["source_key"] == "fingerprint-13407"
        )
        self.assertNotIn("owner_badges", unowned["metadata"])

    def test_weapon_click_refreshes_owner_badge_asset_cache_after_swap(self) -> None:
        with temp_app_shell_db() as db_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                paths = {
                    "fav": Path(temp_dir) / "fav.png",
                    "kitain": Path(temp_dir) / "kitain.png",
                    "thoma": Path(temp_dir) / "thoma.png",
                    "friend": Path(temp_dir) / "friend.png",
                }
                for path, color in (
                    (paths["fav"], "#ffcc00"),
                    (paths["kitain"], "#00ccff"),
                    (paths["thoma"], "#ff6600"),
                    (paths["friend"], "#66ff00"),
                ):
                    pixmap = QPixmap(8, 8)
                    pixmap.fill(QColor(color))
                    self.assertTrue(pixmap.save(str(path)))
                with closing(connect_db(db_path)) as conn:
                    conn.executemany(
                        """
                        UPDATE account_weapon_observed_stacks
                        SET icon_path = ?
                        WHERE weapon_fingerprint = ?
                        """,
                        [
                            (str(paths["fav"]), "fingerprint-13407"),
                            (str(paths["kitain"]), "fingerprint-13408"),
                        ],
                    )
                    conn.executemany(
                        """
                        UPDATE account_characters
                        SET side_icon_path = ?
                        WHERE character_id = ?
                        """,
                        [
                            (str(paths["thoma"]), 10000050),
                            (str(paths["friend"]), 10000051),
                        ],
                    )
                    equip_weapon(conn, 10000050, "fingerprint-13408")
                    equip_weapon(conn, 10000051, "fingerprint-13407")
                    conn.commit()

                controller = AppShellController.empty(equipment_db_path=db_path)
                controller.add_or_replace_character(
                    _character_asset("10000050", "Thoma", weapon_type=13)
                )
                controller.add_or_replace_character(
                    _character_asset("10000051", "Polearm Friend", weapon_type=13)
                )
                controller.toggle_slot_selection(0, 0)
                shell = AppShell(controller=controller)
                workspace = shell.left_host.character_weapon_workspace
                workspace.reload_weapons()

                shell._on_weapon_clicked(
                    _weapon_asset("13407", "Favonius Lance", weapon_type=13)
                )

                assets_by_key = {
                    asset["metadata"]["weapon"]["source_key"]: asset
                    for asset in workspace._all_weapon_items or []
                }

        fav_badges = assets_by_key["fingerprint-13407"]["metadata"]["owner_badges"]
        kitain_badges = assets_by_key["fingerprint-13408"]["metadata"]["owner_badges"]
        self.assertEqual(fav_badges[0]["character_id"], "10000050")
        self.assertEqual(kitain_badges[0]["character_id"], "10000051")

    def test_asset_icon_label_accepts_owner_badge_metadata_with_selection_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            icon = Path(temp_dir) / "weapon.png"
            side_icon = Path(temp_dir) / "side.png"
            for path, color in ((icon, "#ffcc00"), (side_icon, "#00ccff")):
                pixmap = QPixmap(8, 8)
                pixmap.fill(QColor(color))
                self.assertTrue(pixmap.save(str(path)))

            marker = RosterSelectionMarker(
                team_index=0,
                slot_index=0,
                slot_number=1,
                color="#3ed47b",
            )
            label = AssetIconLabel(
                str(icon),
                48,
                asset={
                    "path": str(icon),
                    "metadata": {
                        "owner_badges": [
                            {
                                "character_id": "10000050",
                                "name": "Thoma",
                                "side_icon_path": str(side_icon),
                            }
                        ]
                    },
                },
                selection_marker=marker,
            )

        self.assertEqual(len(label.owner_badges), 1)
        self.assertIs(label.selection_marker, marker)

    def test_weapon_grid_safe_margin_does_not_change_item_spacing(self) -> None:
        workspace = CharacterWeaponWorkspace()
        with patch(
            "ui.app_shell.load_account_weapon_stack_asset_items",
            return_value=[_weapon_asset("13407", "Favonius Lance", weapon_type=13)],
        ):
            workspace.reload_weapons()

        margins = workspace.weapon_grid.contentsMargins()
        self.assertEqual(
            margins.top(),
            WEAPON_PICKER_SAFE_MARGIN + WEAPON_PICKER_VIEWPORT_TOP_EXTENSION,
        )
        self.assertEqual(margins.bottom(), WEAPON_PICKER_SAFE_MARGIN)
        self.assertEqual(workspace.weapon_grid.horizontalSpacing(), 6)
        self.assertEqual(workspace.weapon_grid.verticalSpacing(), 6)

    def test_character_grid_selection_safe_margin_does_not_change_item_spacing(self) -> None:
        workspace = CharacterWeaponWorkspace()
        with patch(
            "ui.app_shell.load_account_character_asset_items",
            return_value=[_character_asset("10000050", "Thoma")],
        ):
            workspace.reload_characters()

        margins = workspace.char_grid.contentsMargins()
        self.assertEqual(margins.top(), CHARACTER_GRID_SELECTION_SAFE_TOP_MARGIN)
        self.assertEqual(margins.bottom(), 0)
        self.assertEqual(workspace.char_grid.horizontalSpacing(), 3)
        self.assertEqual(workspace.char_grid.verticalSpacing(), 3)

    def test_selection_frame_rect_extends_one_pixel_into_grid_gap(self) -> None:
        self.assertEqual(
            _selection_frame_rect(QRect(100, 50, 48, 48)),
            QRect(99, 49, 50, 50),
        )

    def test_weapon_occupied_outline_uses_team_one_selection_color(self) -> None:
        self.assertEqual(WEAPON_PICKER_OCCUPIED_OUTLINE_COLOR, UI_ACCENT_TEAM_1)

    def test_character_selection_overlay_uses_workspace_host_above_viewport(self) -> None:
        workspace = CharacterWeaponWorkspace()

        self.assertIs(workspace._character_selection_overlay.parentWidget(), workspace)

    def test_weapon_owner_target_rect_moves_predictably_with_overhang(self) -> None:
        weapon_rect = QRect(100, 50, 48, 48)
        side_icon_size = QSize(49, 49)
        baseline = _weapon_owner_target_rect(
            weapon_rect,
            side_icon_size,
            right_overhang=0,
            top_overhang=0,
        )
        moved = _weapon_owner_target_rect(
            weapon_rect,
            side_icon_size,
            right_overhang=3,
            top_overhang=4,
        )

        self.assertEqual(moved.x(), baseline.x() + 3)
        self.assertEqual(moved.y(), baseline.y() - 4)
        self.assertEqual(moved.size(), baseline.size())

    def test_weapon_owner_geometry_scales_from_logical_weapon_rect(self) -> None:
        small_weapon_rect = QRect(100, 50, 48, 48)
        large_weapon_rect = QRect(100, 50, 96, 96)
        small_side_icon_size = _weapon_owner_side_icon_size(small_weapon_rect)
        large_side_icon_size = _weapon_owner_side_icon_size(large_weapon_rect)
        small_target = _weapon_owner_target_rect(small_weapon_rect, small_side_icon_size)
        large_target = _weapon_owner_target_rect(large_weapon_rect, large_side_icon_size)

        self.assertEqual(small_side_icon_size, QSize(45, 45))
        self.assertEqual(small_target, QRect(117, 28, 45, 45))
        self.assertEqual(large_side_icon_size, QSize(90, 90))
        self.assertEqual(large_target.width(), small_target.width() * 2)
        self.assertEqual(large_target.height(), small_target.height() * 2)

    def test_weapon_owner_overlay_uses_workspace_host_above_viewport(self) -> None:
        workspace = CharacterWeaponWorkspace()

        self.assertIs(workspace._weapon_owner_badge_overlay.parentWidget(), workspace)

    def test_weapon_owner_overlay_can_defer_startup_stack_settle(self) -> None:
        workspace = CharacterWeaponWorkspace()
        overlay = workspace._weapon_owner_badge_overlay

        overlay.schedule_settle()

        self.assertTrue(overlay._settle_timer.isActive())
        self._app.processEvents()
        self.assertFalse(overlay._settle_timer.isActive())

    def test_marker_registry_survives_filter_rebuilds(self) -> None:
        workspace = CharacterWeaponWorkspace()
        workspace._initial_grid_built = True
        marker = RosterSelectionMarker(
            team_index=0,
            slot_index=0,
            slot_number=1,
            color="#3ed47b",
        )
        workspace.set_character_selection_markers({"10000050": marker})

        with patch(
            "ui.app_shell.load_account_character_asset_items",
            return_value=[
                _character_asset("10000050", "Thoma"),
                _character_asset("10000089", "Furina", weapon_type=1),
            ],
        ):
            workspace.reload_characters()
            workspace._character_weapon_filters = {"sword"}
            workspace.reload_characters()
            workspace._character_weapon_filters = set()
            workspace.reload_characters()

        self.assertIn("10000050", workspace._character_cards_by_id)
        self.assertIsNotNone(workspace._character_cards_by_id["10000050"].selection_marker)

    def test_scaled_icon_pixmap_cache_reuses_scaled_pixmaps(self) -> None:
        _SCALED_ICON_PIXMAP_CACHE.clear()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "icon.png"
            pixmap = QPixmap(8, 8)
            pixmap.fill(QColor("#ff0000"))
            self.assertTrue(pixmap.save(str(path)))

            first = AssetIconLabel(str(path), 24)
            first_hit = first._last_pixmap_cache_hit
            second = AssetIconLabel(str(path), 24)
            second_hit = second._last_pixmap_cache_hit

        self.assertFalse(first_hit)
        self.assertTrue(second_hit)

    def test_scaled_icon_pixmap_does_not_double_downscale_global_ui_scale(self) -> None:
        _SCALED_ICON_PIXMAP_CACHE.clear()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "icon.png"
            pixmap = QPixmap(126, 125)
            pixmap.fill(QColor("#ff0000"))
            self.assertTrue(pixmap.save(str(path)))

            scaled, _cache_hit = _scaled_icon_pixmap(str(path), 48, 0.711458)

        self.assertEqual(scaled.width(), 48)
        self.assertEqual(scaled.height(), 48)
        self.assertEqual(scaled.devicePixelRatio(), 1.0)

    def test_scaled_icon_pixmap_uses_physical_pixels_for_high_dpi(self) -> None:
        _SCALED_ICON_PIXMAP_CACHE.clear()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "icon.png"
            pixmap = QPixmap(126, 126)
            pixmap.fill(QColor("#00ff00"))
            self.assertTrue(pixmap.save(str(path)))

            scaled, _cache_hit = _scaled_icon_pixmap(str(path), 48, 1.25)

        self.assertEqual(scaled.width(), 60)
        self.assertEqual(scaled.height(), 60)
        self.assertEqual(scaled.devicePixelRatio(), 1.25)

    def test_workspace_character_signal_updates_app_shell_state(self) -> None:
        shell = AppShell()

        shell.left_host.character_weapon_workspace.character_clicked.emit(
            _character_asset("10000050", "Thoma")
        )
        shell.flush_pending_right_panel_refresh()

        self.assertEqual(shell.controller.state.team(0).slot(0).character.id, "10000050")
        self.assertEqual(shell.controller.selected_slot_index, 0)

    def test_workspace_weapon_signal_updates_selected_slot(self) -> None:
        with temp_app_shell_db() as db_path:
            shell = AppShell(
                controller=AppShellController.empty(equipment_db_path=db_path)
            )
            shell.left_host.character_weapon_workspace.character_clicked.emit(
                _character_asset("10000050", "Thoma", weapon_type=13)
            )
            shell.flush_pending_right_panel_refresh()

            shell.left_host.character_weapon_workspace.weapon_clicked.emit(
                _weapon_asset("13407", "Favonius Lance", weapon_type=13)
            )
            shell.flush_pending_right_panel_refresh()

        self.assertEqual(shell.controller.state.team(0).slot(0).weapon.id, "13407")


def _character_asset(
    character_id: str,
    name: str,
    *,
    weapon_type: int = 13,
) -> dict:
    weapon_names = {
        1: "sword",
        10: "catalyst",
        11: "claymore",
        12: "bow",
        13: "polearm",
    }
    return {
        "path": "portrait.png",
        "filename": "portrait.png",
        "metadata": {
            "character": {
                "id": character_id,
                "name": name,
                "level": 90,
                "element": "Pyro",
                "rarity": 4,
                "constellation": 6,
                "weapon_type": weapon_type,
                "weapon_type_name": weapon_names.get(weapon_type, "polearm"),
                "portrait_path": f"{name.casefold()}.png",
            }
        },
    }


def _weapon_asset(
    weapon_id: str,
    name: str,
    *,
    weapon_type: int = 13,
    weapon_type_name: str = "Polearm",
    rarity: int = 4,
    weapon_fingerprint: str | None = None,
) -> dict:
    fingerprint = weapon_fingerprint or f"fingerprint-{weapon_id}"
    return {
        "path": "weapon.png",
        "filename": "weapon.png",
        "metadata": {
            "weapon": {
                "id": weapon_id,
                "name": name,
                "level": 90,
                "rarity": rarity,
                "refinement": 5,
                "weapon_type": weapon_type,
                "weapon_type_name": weapon_type_name,
                "type_name": weapon_type_name,
                "icon_path": "fav.png",
                "source_key": fingerprint,
                "weapon_fingerprint": fingerprint,
            }
        },
    }


class temp_app_shell_db:
    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "artifacts.db"
        with closing(connect_db(self.path)) as conn:
            init_db(conn)
            _seed_app_shell_characters(conn)
            _seed_app_shell_weapons(conn)
            _seed_app_shell_artifacts(conn)
            conn.commit()
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        self._tmp.cleanup()


def _seed_app_shell_characters(conn) -> None:
    conn.executemany(
        """
        INSERT INTO account_characters (
            character_id,
            name,
            weapon_type,
            weapon_type_name
        )
        VALUES (?, ?, ?, ?)
        """,
        [
            (10000050, "Thoma", 13, "polearm"),
            (10000051, "Polearm Friend", 13, "polearm"),
            (10000089, "Furina", 1, "sword"),
        ],
    )


def _seed_app_shell_weapons(conn) -> None:
    conn.executemany(
        """
        INSERT INTO account_weapon_observed_stacks (
            weapon_fingerprint,
            weapon_id,
            name,
            weapon_type,
            weapon_type_name,
            rarity,
            level,
            refinement,
            icon_path,
            known_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("fingerprint-13407", 13407, "Favonius Lance", 13, "Polearm", 4, 90, 5, "fav.png", 1),
            ("fingerprint-13408", 13408, "Kitain Cross Spear", 13, "Polearm", 4, 90, 1, "kitain.png", 1),
            ("fingerprint-11401", 11401, "Sword", 1, "Sword", 4, 90, 1, "sword.png", 1),
        ],
    )


def _seed_app_shell_artifacts(conn) -> None:
    conn.execute(
        """
        INSERT INTO artifact_sets (
            set_uid,
            hoyowiki_entry_id,
            fallback_name,
            updated_at
        )
        VALUES ('current_set', 'current-set-entry', 'Current Set', '2026-05-26T00:00:00+00:00')
        """
    )
    conn.executemany(
        """
        INSERT INTO artifacts (
            id,
            fingerprint,
            name,
            set_uid,
            set_name,
            pos,
            pos_name,
            rarity,
            level,
            main_property_type,
            main_property_name,
            main_property_value,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-05-26T00:00:00+00:00', '2026-05-26T00:00:00+00:00')
        """,
        [
            (1, "artifact-flower-a", "Flower A", "current_set", "Current Set", 1, "Flower", 5, 20, 2, "HP", "4780"),
            (2, "artifact-plume-a", "Plume A", "current_set", "Current Set", 2, "Plume", 5, 20, 5, "ATK", "311"),
        ],
    )
    conn.execute(
        """
        INSERT INTO artifact_set_display_stat_effects (
            set_uid,
            pieces_required,
            stat_key,
            value,
            value_type,
            updated_at
        )
        VALUES ('current_set', 2, 'ATK_PERCENT', 18.0, 'percent_points', '2026-05-26T00:00:00+00:00')
        """
    )


def _insert_app_shell_artifact(
    conn,
    *,
    artifact_id: int,
    pos: int,
    name: str,
) -> None:
    conn.execute(
        """
        INSERT INTO artifacts (
            id,
            fingerprint,
            name,
            set_uid,
            set_name,
            pos,
            pos_name,
            rarity,
            level,
            main_property_type,
            main_property_name,
            main_property_value,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, 'current_set', 'Current Set', ?, 'Flower', 5, 20, 2, 'HP', '4780', '2026-05-26T00:00:00+00:00', '2026-05-26T00:00:00+00:00')
        """,
        (artifact_id, f"artifact-{artifact_id}", name, pos),
    )


def _seed_weapon_static_effect(
    conn,
    *,
    weapon_id: int,
    stat_key: str,
    value: float,
    value_type: str,
    passive_name: str,
    passive_text: str,
) -> None:
    conn.execute(
        """
        INSERT INTO weapon_display_stat_effects (
            weapon_id,
            refinement,
            stat_key,
            value,
            value_type,
            updated_at
        )
        VALUES (?, 5, ?, ?, ?, '2026-05-26T00:00:00+00:00')
        """,
        (weapon_id, stat_key, value, value_type),
    )
    conn.execute(
        """
        INSERT INTO weapon_passive_tooltips (
            weapon_id,
            lang,
            passive_name,
            passive_text,
            updated_at
        )
        VALUES (?, 'en-us', ?, ?, '2026-05-26T00:00:00+00:00')
        """,
        (weapon_id, passive_name, passive_text),
    )


def _artifact_build_count(conn) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM artifact_builds").fetchone()
    return int(row["count"])
