"""Offscreen contracts for the common tooltip surface and action/help producers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale(platform="linux")

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from hoyolab_export.auth import AuthStatus
from localization import get_language, set_language, tr, tr_for_language
from localization.i18n import LOCALES_DIR
from ui.artifact_browser.filter_popup import SetsFilterPopup
from ui.artifact_browser.models import ArtifactItem
from ui.artifact_browser.stat_types import HP_FLAT
from ui.character_assets import (
    CHARACTER_RARITY_FILTERS,
    CHARACTER_STANDARD_FILTER,
    CHARACTER_TRAIT_FILTERS,
    ELEMENT_FILTERS,
    STANDARD_FILTER_ALL,
    STANDARD_FILTER_EXCLUDE,
    STANDARD_FILTER_ONLY,
    WEAPON_TYPE_FILTERS,
)
from ui.character_browser.filter_bar import CharacterFilterBar
from ui.gcsim_browser.optimizer_result import (
    CompactOptimizerArtifactCard,
    OptimizerItemReplacement,
    OptimizerResultBuildRow,
    OptimizerResultBuildsWidget,
    OptimizerResultPage,
)
from ui.gcsim_browser.virtual_slot_editor import VirtualGcsimCardEditor
from ui.gcsim_browser.window import GcsimBrowserWorkspace
from ui.main_window import App
from ui.pvp_browser.window import PvpDecksWorkspace, PvpDraftWorkspace, PvpWorkspace
from ui.right_panel.pvp.play.panel import PvpPlayRightPanel
from ui.right_panel.common.run_summary import CompactSlotSummaryWidget
from ui.right_panel.pvp.decks.panel import PvpDecksRightPanel
from ui.right_panel.settings.account_data import AccountDataPage
from ui.right_panel.settings.account_profiles import AccountProfilesWidget
from ui.utils.pixel_icon_grid import PixelIconGrid, PixelIconGridItem, PixelIconGridMetrics
from ui.utils.tooltips import CustomTooltipController, install_custom_tooltip
from ui.widgets.drag import DraggableIcon
from run_workspace.history_browser_catalog import HistorySlotVisual


_APP = QApplication.instance() or QApplication([])
_LANGUAGES = ("ru", "en", "pt-br")
_FILTER_HINT_EXPECTATIONS = {
    "ru": {
        "filter.rarity.5": "Редкость 5★",
        "filter.rarity.4": "Редкость 4★",
        "filter.rarity.3": "Редкость 3★",
        "filter.trait.moonsign": "Персонажи Moonsign",
        "filter.trait.hexerei": "Ведьмовство",
        "filter.standard_5_star": (
            "Стандартные персонажи 5★: все → только они → исключить их."
        ),
    },
    "en": {
        "filter.rarity.5": "Rarity 5★",
        "filter.rarity.4": "Rarity 4★",
        "filter.rarity.3": "Rarity 3★",
        "filter.trait.moonsign": "Moonsign",
        "filter.trait.hexerei": "Hexerei",
        "filter.standard_5_star": (
            "Standard 5-star characters: all → only them → exclude them."
        ),
    },
    "pt-br": {
        "filter.rarity.5": "Raridade 5★",
        "filter.rarity.4": "Raridade 4★",
        "filter.rarity.3": "Raridade 3★",
        "filter.trait.moonsign": "Moonsign",
        "filter.trait.hexerei": "Hexerei",
        "filter.standard_5_star": (
            "Personagens padrão 5★: todos → somente eles → excluí-los."
        ),
    },
}
_ACTION_HELP_KEYS = (
    "gcsim.optimizer.save_tooltip",
    "gcsim.optimizer.replacement_delta_help",
    "gcsim.optimizer.artifact_missing",
    "gcsim.optimizer.character_missing",
    "settings.gcsim.optimizer.fast_mode.tooltip",
    "settings.gcsim.boosted_energy.description",
    "hoyolab.import_running_tooltip",
    "hoyolab.import_cleanup_tooltip",
    "gcsim.virtual_editor.profile",
    "accounts.delete",
    "artifact.build.targets_reset",
    "artifact.build.new",
    "artifact.build.save",
    "artifact.build.edit",
    "artifact.build.delete",
    "artifact.build.cancel",
    "common.cancel",
    "artifact.custom.create",
    "artifact.custom.edit",
    "artifact.custom.delete",
    "artifact.custom.cancel",
)


def _controller(owner: QWidget) -> CustomTooltipController:
    controllers = owner.findChildren(CustomTooltipController)
    assert len(controllers) == 1, (owner, controllers)
    assert controllers[0].owner is owner
    return controllers[0]


def _artifact(item_id: int, position: int = 1) -> ArtifactItem:
    return ArtifactItem(
        id=item_id,
        name=f"Item {item_id}",
        set_id=1,
        set_uid="test-set",
        set_name="Test Set",
        pos=position,
        pos_name="Flower",
        rarity=5,
        level=20,
        main_property_type=HP_FLAT,
        main_property_name="HP",
        main_property_value="4,780",
    )


class TooltipPresentationContracts(unittest.TestCase):
    def test_traveler_selector_hint_describes_element_choice_in_all_languages(self) -> None:
        from ui.character_browser.traveler_selector import TravelerVariantGrid
        from ui.utils.pixel_icon_grid import PixelIconGridItem

        language = get_language()
        self.addCleanup(set_language, language)
        grid = TravelerVariantGrid(surface="test_selector")
        self.addCleanup(grid.close)
        items = (PixelIconGridItem("one", ""), PixelIconGridItem("two", ""))
        grid.set_items(items[:1])
        grid.set_variant_groups({"one": items})
        button = grid._variant_buttons["one"]
        expected = {"ru": "Выбрать элемент Путешественника", "en": "Choose the Traveler's element", "pt-br": "Escolher o elemento do Viajante"}
        for language, text in expected.items():
            with self.subTest(language=language):
                set_language(language)
                grid.retranslate_ui()
                self.assertEqual(_controller(button).text(), text)
                self.assertEqual(button.accessibleName(), text)
                self.assertEqual(button.toolTip(), "")

    def test_shared_popup_renders_plain_and_rich_text_and_hides_on_owner_events(self) -> None:
        owner = QWidget()
        self.addCleanup(owner.close)
        owner.resize(80, 24)
        owner.show()
        controller = install_custom_tooltip(owner, "Plain help", delay_ms=1)

        self.assertEqual(owner.toolTip(), "")
        controller.show()
        self.assertTrue(controller._popup.isVisible())
        self.assertEqual(controller._popup.text(), "Plain help")
        self.assertEqual(controller._popup.textFormat(), Qt.TextFormat.AutoText)
        self.assertLessEqual(controller._popup.width(), 420)

        self.assertIs(install_custom_tooltip(owner, "<b>Rich help</b><br>second line"), controller)
        self.assertEqual(len(owner.findChildren(CustomTooltipController)), 1)
        self.assertTrue(controller._popup.isVisible())
        self.assertEqual(controller._popup.text(), "<b>Rich help</b><br>second line")
        QCoreApplication.sendEvent(owner, QEvent(QEvent.Type.Leave))
        self.assertFalse(controller._popup.isVisible())
        self.assertFalse(controller._timer.isActive())

        self.assertTrue(controller.eventFilter(owner, QEvent(QEvent.Type.ToolTip)))
        controller.set_text("")
        controller.show()
        self.assertFalse(controller._popup.isVisible())
        self.assertEqual(owner.toolTip(), "")

    def test_grid_hover_uses_one_anchor_and_clears_stale_text(self) -> None:
        grid = PixelIconGrid(metrics=PixelIconGridMetrics(item_width=32, gap_x=2))
        self.addCleanup(grid.close)
        grid.resize(100, 50)
        grid.set_items(
            [
                PixelIconGridItem(item_id="a", icon_path="", tooltip="First item"),
                PixelIconGridItem(item_id="b", icon_path="", tooltip=""),
            ]
        )
        grid.show()

        grid._set_hovered_item("a")
        self.assertEqual(grid._tooltip_controller.text(), "First item")
        self.assertEqual(grid._tooltip_anchor.geometry(), grid.item_logical_rect("a").toAlignedRect())
        self.assertTrue(grid._tooltip_controller._timer.isActive())
        self.assertEqual(grid._tooltip_anchor.toolTip(), "")

        grid._set_hovered_item("b")
        self.assertEqual(grid._tooltip_controller.text(), "")
        self.assertFalse(grid._tooltip_controller._timer.isActive())
        self.assertTrue(grid._tooltip_anchor.geometry().isNull())

    def test_draggable_icon_routes_updates_through_custom_controller(self) -> None:
        icon = DraggableIcon("", 24)
        self.addCleanup(icon.close)
        icon.setToolTip("First")
        self.assertEqual(_controller(icon).text(), "First")
        self.assertEqual(icon.toolTip(), "")
        icon.setToolTip("Updated")
        self.assertEqual(_controller(icon).text(), "Updated")
        icon.setToolTip("")
        self.assertEqual(_controller(icon).text(), "")

    def test_filter_buttons_attach_localized_custom_hints(self) -> None:
        original_language = get_language()
        self.addCleanup(set_language, original_language)
        set_language(_LANGUAGES[0])
        normal_bar = CharacterFilterBar()
        pvp_workspace = PvpDraftWorkspace()
        pvp_workspace._build_unified_pool({}, draft_complete=False)
        pvp_bar = pvp_workspace.character_filter_bar
        self.assertIsNotNone(pvp_bar)
        self.addCleanup(normal_bar.close)
        self.addCleanup(pvp_workspace.close)
        keys = [
            key
            for choices in (
                ELEMENT_FILTERS,
                WEAPON_TYPE_FILTERS,
                CHARACTER_RARITY_FILTERS,
                CHARACTER_TRAIT_FILTERS,
            )
            for _value, _icon, key in choices
        ] + [CHARACTER_STANDARD_FILTER[2]]

        for language in _LANGUAGES:
            with self.subTest(language=language):
                set_language(language)
                for surface, bar in (("normal", normal_bar), ("pvp", pvp_bar)):
                    with self.subTest(surface=surface):
                        previous_mode = bar.standard_filter
                        controllers_before = [_controller(button) for button in bar.buttons]
                        bar.retranslate_ui()
                        self.assertEqual(bar.standard_filter, previous_mode)
                        for button, previous_controller in zip(bar.buttons, controllers_before):
                            self.assertIs(_controller(button), previous_controller)

                        self.assertEqual(len(bar.buttons), len(keys))
                        for button, key in zip(bar.buttons, keys):
                            with self.subTest(key=key):
                                text = _controller(button).text()
                                self.assertEqual(text, f"{tr(key)}\n\n{tr('filter.character.rules')}")
                                self.assertNotIn("?", text)
                                self.assertNotIn("\\u", text)
                                if key in _FILTER_HINT_EXPECTATIONS[language]:
                                    self.assertEqual(
                                        text.split("\n\n", 1)[0],
                                        _FILTER_HINT_EXPECTATIONS[language][key],
                                    )
                                self.assertEqual(button.toolTip(), "")

                        standard_button = bar.standard_button
                        expected_hint = _FILTER_HINT_EXPECTATIONS[language][
                            CHARACTER_STANDARD_FILTER[2]
                        ] + f"\n\n{tr('filter.character.rules')}"
                        states = (
                            (STANDARD_FILTER_ALL, False, False),
                            (STANDARD_FILTER_ONLY, True, False),
                            (STANDARD_FILTER_EXCLUDE, False, True),
                        )
                        start_index = next(
                            index
                            for index, (mode, _only, _exclude) in enumerate(states)
                            if mode == bar.standard_filter
                        )
                        for offset in range(len(states)):
                            mode, only, exclude = states[
                                (start_index + offset) % len(states)
                            ]
                            for _attempt in range(len(states)):
                                if bar.standard_filter == mode:
                                    break
                                standard_button.click()
                            self.assertEqual(bar.standard_filter, mode)
                            self.assertEqual(standard_button.property("standardOnly"), only)
                            self.assertEqual(standard_button.property("standardExclude"), exclude)
                            self.assertEqual(_controller(standard_button).text(), expected_hint)

    def test_pvp_first_actor_hint_uses_custom_controller_and_retranslates(self) -> None:
        original_language = get_language()
        self.addCleanup(set_language, original_language)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = PvpWorkspace(
                db_path=root / "unused.db", deck_dir=root / "decks",
                character_assets_provider=lambda: [], weapon_assets_provider=lambda: [],
                abyss_source_data_provider=lambda: None, abyss_period_provider=lambda: None,
                abyss_cache_dir=root / "abyss",
            )
            self.addCleanup(workspace.close)
            panel = PvpPlayRightPanel(workspace)
            self.addCleanup(panel.close)
            controller = _controller(panel.first_seat_combo)
            expectations = {
                "ru": "Дополнительные пребаны по разнице коста идут до основной очереди ходов.",
                "en": "Cost compensation prebans come before the main turn order.",
                "pt-br": "Pré-bans por diferença de custo ocorrem antes da ordem principal.",
            }
            for language, phrase in expectations.items():
                set_language(language)
                panel.retranslate_ui()
                self.assertIs(_controller(panel.first_seat_combo), controller)
                self.assertEqual(controller.text(), phrase)
                self.assertEqual(panel.first_seat_combo.toolTip(), "")
            self.assertFalse((root / "unused.db").exists())

    def test_optimizer_save_status_and_replacement_help_are_distinct(self) -> None:
        widget = OptimizerResultBuildsWidget()
        self.addCleanup(widget.close)
        artifacts = tuple(_artifact(10 + pos, pos) for pos in range(1, 6))
        replacement = OptimizerItemReplacement(
            artifact=_artifact(30, 1), original_id=11,
            dps_delta=125.0, ranking_basis="formula",
        )
        rows = (
            OptimizerResultBuildRow("save", 1, "Hero", None, artifacts, (), replacements=(replacement,)),
            OptimizerResultBuildRow("missing_item", 2, "Hero", None, artifacts[:4], (), missing_artifact_ids=(15,)),
            OptimizerResultBuildRow("missing_target", None, "Unknown", None, artifacts, ()),
        )
        widget.set_pages((OptimizerResultPage(1, "", rows, ranking_basis="formula", formula_dps="1000"),))

        self.assertEqual(widget._save_tooltips["save"].text(), tr("gcsim.optimizer.save_tooltip"))
        self.assertIs(widget._save_tooltips["save"].owner, widget._save_buttons["save"])
        self.assertEqual(widget._save_buttons["save"].toolTip(), "")
        self.assertTrue(widget._save_buttons["save"].isEnabled())
        self.assertFalse(widget._save_buttons["missing_item"].isEnabled())
        self.assertEqual(widget._status_labels["missing_item"].text(), tr("gcsim.optimizer.artifact_missing"))
        self.assertFalse(widget._save_buttons["missing_target"].isEnabled())
        self.assertEqual(widget._status_labels["missing_target"].text(), tr("gcsim.optimizer.character_missing"))

        replacement_cards = [
            card for card in widget.findChildren(CompactOptimizerArtifactCard)
            if card.artifact.id == 30
        ]
        self.assertEqual(len(replacement_cards), 1)
        gain_label = replacement_cards[0].findChild(QLabel, "OptimizerReplacementDelta")
        self.assertIsNotNone(gain_label)
        self.assertTrue(gain_label.text().startswith("≈ +125 DPS"))
        self.assertEqual(_controller(gain_label).text(), tr("gcsim.optimizer.replacement_delta_help"))
        self.assertEqual(gain_label.toolTip(), "")

    def test_virtual_editor_profile_and_status_hints_follow_current_state(self) -> None:
        editor = VirtualGcsimCardEditor()
        self.addCleanup(editor.close)
        self.assertEqual(_controller(editor.profile_button).text(), tr("gcsim.virtual_editor.profile"))
        self.assertEqual(editor.profile_button.toolTip(), "")

        editor.character_combo.addItem("Hero", userData="hero")
        editor.weapon_combo.addItem("Sword", userData="sword")
        editor.character_combo.setCurrentIndex(editor.character_combo.findData("hero"))
        editor.weapon_combo.setCurrentIndex(editor.weapon_combo.findData("sword"))
        editor._character_tooltips["hero"] = "Character source details"
        editor._weapon_tooltips["sword"] = "Weapon passive details"
        self.assertEqual(_controller(editor.character_combo).text(), "Character source details")
        self.assertEqual(_controller(editor.weapon_combo).text(), "Weapon passive details")
        editor.status_label.setProperty("statusText", "Unavailable source")
        self.assertEqual(_controller(editor.status_label).text(), "Unavailable source")
        editor.status_label.setProperty("statusText", "")
        self.assertEqual(_controller(editor.status_label).text(), "")

    def test_pvp_and_artifact_actions_attach_and_reuse_custom_controllers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = PvpDecksWorkspace(
                deck_dir=directory,
                character_assets_provider=lambda: [],
                weapon_assets_provider=lambda: [],
            )
            panel = PvpDecksRightPanel(workspace)
            self.assertEqual(_controller(panel.create_button).text(), tr("artifact.build.new"))
            self.assertEqual(_controller(panel.cancel_new_deck_button).text(), tr("artifact.build.cancel"))
            self.assertEqual(panel.create_button.toolTip(), "")
            self.assertEqual(panel.cancel_new_deck_button.toolTip(), "")
            panel.close()
            workspace.close()

        button = QPushButton()
        self.addCleanup(button.close)
        PvpDecksRightPanel._install_button_tooltip(None, button, tr("artifact.build.new"))
        first = button.property("_custom_tooltip_controller")
        self.assertIs(first, _controller(button))
        self.assertEqual(first.text(), tr("artifact.build.new"))
        PvpDecksRightPanel._install_button_tooltip(None, button, tr("artifact.build.save"))
        self.assertIs(button.property("_custom_tooltip_controller"), first)
        self.assertEqual(first.text(), tr("artifact.build.save"))
        self.assertEqual(button.toolTip(), "")

        popup = SetsFilterPopup(
            game_sets=[], custom_sets=[], selected_game_set_ids=set(),
            selected_custom_set_ids=set(), on_selection_changed=lambda *_: None,
            on_custom_set_create=lambda *_: None,
            on_custom_set_edit=lambda *_: None,
            on_custom_set_delete=lambda *_: [],
        )
        self.addCleanup(popup.close)
        action_buttons = [
            child for child in popup.findChildren(QPushButton)
            if child.property("_custom_tooltip_controller") is not None
        ]
        self.assertEqual(len(action_buttons), 1)
        self.assertEqual(_controller(action_buttons[0]).text(), tr("artifact.custom.create"))
        self.assertEqual(action_buttons[0].toolTip(), "")

    def test_pvp_run_admission_hints_update_and_clear_without_changing_run_guards(self) -> None:
        browser = GcsimBrowserWorkspace()
        self.addCleanup(browser.close)
        buttons = (browser.run_selected_button, browser.run_all_button)
        reason = "The selected Abyss period is no longer available."
        browser.set_run_admission(False, message=reason)
        controllers = tuple(_controller(button) for button in buttons)
        for button, controller in zip(buttons, controllers):
            self.assertFalse(button.isEnabled())
            self.assertEqual(controller.text(), reason)
            self.assertEqual(button.toolTip(), "")

        browser.set_run_admission(False, message="The account is not ready.")
        for button, controller in zip(buttons, controllers):
            self.assertIs(_controller(button), controller)
            self.assertEqual(controller.text(), "The account is not ready.")

        browser.set_actions_busy(True)
        browser.set_run_admission(True)
        for button, controller in zip(buttons, controllers):
            self.assertIs(_controller(button), controller)
            self.assertEqual(controller.text(), "")
            self.assertFalse(button.isEnabled())
        browser.set_actions_busy(False)
        self.assertTrue(all(button.isEnabled() for button in buttons))

        preparation = GcsimBrowserWorkspace(preparation_only=True)
        self.addCleanup(preparation.close)
        preparation.set_run_admission(True)
        self.assertFalse(preparation.run_selected_button.isEnabled())
        self.assertFalse(preparation.run_all_button.isEnabled())

    def test_account_help_and_busy_hint_use_custom_controllers(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("ui.right_panel.settings.account_data.ensure_hoyolab_dirs"),
            patch("ui.right_panel.settings.account_data.get_auth_status", return_value=AuthStatus.NOT_LOGGED_IN),
            patch("ui.right_panel.settings.account_data.has_local_hoyolab_profile", return_value=False),
            patch("ui.right_panel.settings.account_data.active_profile", return_value=None),
        ):
            page = AccountDataPage(settings_file=Path(directory) / "settings.json")
            self.addCleanup(page.close)
            help_text = tr("settings.gcsim.boosted_energy.description")
            self.assertEqual(page._boosted_energy_label_tooltip.text(), help_text)
            self.assertEqual(page._boosted_energy_switch_tooltip.text(), help_text)
            self.assertIs(page._boosted_energy_label_tooltip.owner, page.gcsim_boosted_energy_label)
            self.assertIs(page._boosted_energy_switch_tooltip.owner, page.gcsim_boosted_energy_switch)
            self.assertEqual(page.gcsim_boosted_energy_label.toolTip(), "")
            self.assertEqual(page.gcsim_boosted_energy_switch.toolTip(), "")
            self.assertEqual(page.btn_hoyolab_export.toolTip(), "")
            self.assertEqual(page._hoyolab_export_tooltip.text(), "")

            page._hoyolab_export_process = object()
            page.refresh_hoyolab_auth_status()
            self.assertEqual(page._hoyolab_export_tooltip.text(), tr("hoyolab.import_running_tooltip"))
            with patch(
                "ui.right_panel.settings.account_data.tr",
                side_effect=lambda key: tr_for_language("pt-br", key),
            ):
                page.refresh_hoyolab_auth_status()
                self.assertEqual(
                    page._hoyolab_export_tooltip.text(),
                    tr_for_language("pt-br", "hoyolab.import_running_tooltip"),
                )
                self.assertEqual(
                    page._boosted_energy_label_tooltip.text(),
                    tr_for_language("pt-br", "settings.gcsim.boosted_energy.description"),
                )
            page._hoyolab_export_process = None
            page.refresh_hoyolab_auth_status()
            self.assertEqual(page._hoyolab_export_tooltip.text(), "")

    def test_profile_menu_delete_hint_uses_custom_surface(self) -> None:
        draft = {"id": "test-draft", "imported": False, "metadata": {}}
        with (
            patch("ui.right_panel.settings.account_profiles.active_profile", return_value=None),
            patch("ui.right_panel.settings.account_profiles.list_profiles", return_value=[draft]),
        ):
            selector = AccountProfilesWidget()
            self.addCleanup(selector.close)
            selector._populate_menu()
            delete = selector.menu.findChild(QPushButton, "deleteAccount_test-draft")
            self.assertIsNotNone(delete)
            self.assertEqual(_controller(delete).text(), tr("accounts.delete"))
            self.assertEqual(delete.toolTip(), "")
            with patch(
                "ui.right_panel.settings.account_profiles.tr",
                side_effect=lambda key, **kwargs: tr_for_language("pt-br", key, **kwargs),
            ):
                self.assertEqual(_controller(delete).text(), tr_for_language("pt-br", "accounts.delete"))

    def test_compact_summary_hint_includes_character_weapon_and_sets(self) -> None:
        slot = HistorySlotVisual(
            slot_index=0,
            character_name="Furina",
            character_level=90,
            constellation=2,
            weapon_name="Favonius Sword",
            weapon_refinement=5,
            build_label="Saved build",
            set_labels=("Golden Troupe 2p", "Marechaussee Hunter 2p"),
        )
        summary = CompactSlotSummaryWidget(slot)
        self.addCleanup(summary.close)
        self.assertEqual(
            _controller(summary).text().splitlines(),
            ["Furina", "Lv. 90 | C2", "Favonius Sword R5", "Saved build", "Golden Troupe 2p", "Marechaussee Hunter 2p"],
        )
        self.assertEqual(summary.toolTip(), "")

    def test_legacy_import_hint_transitions_busy_cleanup_ready(self) -> None:
        export = QPushButton()
        auth_box = QWidget()
        profile_menu = QPushButton()
        self.addCleanup(export.close)
        self.addCleanup(auth_box.close)
        self.addCleanup(profile_menu.close)
        state = SimpleNamespace(
            _hoyolab_export_process=None,
            _hoyolab_login_process=None,
            _hoyolab_import_cooldown_active=False,
            hoyolab_auth_box=auth_box,
            btn_profile_menu=profile_menu,
            action_refresh_images=QAction("Refresh"),
            btn_hoyolab_export=export,
            _hoyolab_export_tooltip=install_custom_tooltip(export),
        )
        with (
            patch("ui.main_window.get_auth_status", return_value=AuthStatus.LOGGED_IN),
            patch("ui.main_window.has_local_hoyolab_profile", return_value=True),
        ):
            App.refresh_hoyolab_auth_status(state)
            self.assertEqual(_controller(export).text(), "")
            state._hoyolab_export_process = object()
            App.refresh_hoyolab_auth_status(state)
            self.assertEqual(_controller(export).text(), tr("hoyolab.import_running_tooltip"))
            self.assertFalse(export.isEnabled())
            state._hoyolab_export_process = None
            state._hoyolab_import_cooldown_active = True
            App.refresh_hoyolab_auth_status(state)
            self.assertEqual(_controller(export).text(), tr("hoyolab.import_cleanup_tooltip"))
            state._hoyolab_import_cooldown_active = False
            App.refresh_hoyolab_auth_status(state)
            self.assertEqual(_controller(export).text(), "")
            self.assertTrue(export.isEnabled())
            self.assertEqual(export.toolTip(), "")

    def test_action_help_locales_have_explicit_meaningful_text(self) -> None:
        filter_keys = {
            key
            for choices in (
                ELEMENT_FILTERS,
                WEAPON_TYPE_FILTERS,
                CHARACTER_RARITY_FILTERS,
                CHARACTER_TRAIT_FILTERS,
            )
            for _value, _icon, key in choices
        } | {CHARACTER_STANDARD_FILTER[2]}
        for language in _LANGUAGES:
            catalog = json.loads((LOCALES_DIR / f"{language}.json").read_text(encoding="utf-8"))
            for key in (*_ACTION_HELP_KEYS, *filter_keys):
                with self.subTest(language=language, key=key):
                    self.assertIn(key, catalog)
                    self.assertTrue(catalog[key].strip())
                    self.assertNotEqual(catalog[key], key)
            for key in filter_keys:
                with self.subTest(language=language, filter_key=key):
                    self.assertNotIn("?", catalog[key])
                    self.assertNotIn("\\u", catalog[key])
            for key, expected in _FILTER_HINT_EXPECTATIONS[language].items():
                with self.subTest(language=language, semantic_filter_key=key):
                    self.assertEqual(catalog[key], expected)

        english = json.loads((LOCALES_DIR / "en.json").read_text(encoding="utf-8"))
        self.assertIn("Save this build", english["gcsim.optimizer.save_tooltip"])
        self.assertIn("Artifact Browser", english["gcsim.optimizer.save_tooltip"])
        gain = english["gcsim.optimizer.replacement_delta_help"]
        for concept in ("Team DPS", "this item only", "formula estimate", "GCSIM", "statistical variation"):
            self.assertIn(concept, gain)
        self.assertIn("account database", english["gcsim.optimizer.artifact_missing"])
        self.assertIn("Character target", english["gcsim.optimizer.character_missing"])
        fast = english["settings.gcsim.optimizer.fast_mode.tooltip"]
        for concept in ("formula", "without final GCSIM verification", "DPS may be inaccurate", "main search", "final simulations"):
            self.assertIn(concept, fast)
        self.assertIn("shared switch", english["settings.gcsim.boosted_energy.description"])
        self.assertIn("import is running", english["hoyolab.import_running_tooltip"])


if __name__ == "__main__":
    unittest.main()
