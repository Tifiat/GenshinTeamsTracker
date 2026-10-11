from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale(platform="linux")

from PySide6.QtWidgets import QApplication

from localization import get_language, set_language
from ui.character_browser.filter_bar import CharacterFilterBar
from ui.pvp_browser.window import PvpDraftWorkspace
from ui.utils.tooltips import CustomTooltipController
from ui.artifact_browser.window import ArtifactBrowserWindow


_APP = QApplication.instance() or QApplication([])
_LANGUAGES = ("ru", "en", "pt-br")

# These literals are the user-facing contract, kept independent of the locale
# lookup used by the widgets under test.
_SORT_EXPECTATIONS = {
    "ru": {
        "off": "Обычный порядок: редкость → уровень",
        "current": "Сейчас режим: {mode}",
        "constellation_title": "Сортировка по созвездиям",
        "constellation_modes": {
            1: "5★ → 4★; внутри каждой группы C6 → C0",
            2: "Нестандартные 5★ → стандартные 5★ → 4★; внутри каждой группы C6 → C0",
        },
        "level_title": "Сортировка по уровню",
        "level_modes": {
            1: "5★ → 4★; внутри каждой группы сначала высокий уровень",
            2: "Нестандартные 5★ → стандартные 5★ → 4★; внутри каждой группы сначала высокий уровень",
            3: "Сначала высокий уровень среди всех персонажей",
        },
        "exclusive": "Активна одна сортировка: выбор другой заменяет текущую. Фильтры сохраняются.",
    },
    "en": {
        "off": "Default order: rarity → level",
        "current": "Current mode: {mode}",
        "constellation_title": "Sort by constellations",
        "constellation_modes": {
            1: "5★ → 4★; C6 → C0 within each group",
            2: "Nonstandard 5★ → standard 5★ → 4★; C6 → C0 within each group",
        },
        "level_title": "Sort by level",
        "level_modes": {
            1: "5★ → 4★; highest level first within each group",
            2: "Nonstandard 5★ → standard 5★ → 4★; highest level first within each group",
            3: "Highest level first across all characters",
        },
        "exclusive": "Only one sort is active: choosing the other replaces it. Filters are kept.",
    },
    "pt-br": {
        "off": "Ordem padrão: raridade → nível",
        "current": "Modo atual: {mode}",
        "constellation_title": "Ordenar por constelações",
        "constellation_modes": {
            1: "5★ → 4★; C6 → C0 dentro de cada grupo",
            2: "5★ não padrão → 5★ padrão → 4★; C6 → C0 dentro de cada grupo",
        },
        "level_title": "Ordenar por nível",
        "level_modes": {
            1: "5★ → 4★; maior nível primeiro dentro de cada grupo",
            2: "5★ não padrão → 5★ padrão → 4★; maior nível primeiro dentro de cada grupo",
            3: "Maior nível primeiro entre todos os personagens",
        },
        "exclusive": "Apenas uma ordenação fica ativa: escolher a outra substitui a atual. Os filtros são mantidos.",
    },
}

_FILTER_RULE_EXPECTATIONS = {
    "ru": (
        "Внутри одной группы подходит любой отмеченный вариант.",
        "Между группами должны выполняться все условия.",
        "Несовместимые условия дают пустой список; фильтры сохраняются.",
    ),
    "en": (
        "Within one group, any selected choice matches.",
        "Between groups, all conditions must match.",
        "Conflicting conditions give an empty list; filters are kept.",
    ),
    "pt-br": (
        "Dentro de um grupo, qualquer opção marcada corresponde.",
        "Entre grupos, todas as condições devem corresponder.",
        "Condições incompatíveis deixam a lista vazia; os filtros são mantidos.",
    ),
}

_PINNED_TARGET_EXPECTATIONS = {
    "ru": (
        "выбранные персонажи и текущая цель экипировки всегда видны",
        "«Универсальный» остаётся первым.",
    ),
    "en": (
        "selected characters and the current equipment target stay visible",
        "Universal stays first.",
    ),
    "pt-br": (
        "personagens selecionados e o alvo de equipamento atual continuam visíveis",
        "Universal permanece primeiro.",
    ),
}


def _controller(owner) -> CustomTooltipController:
    controllers = owner.findChildren(CustomTooltipController)
    assert len(controllers) == 1, (owner, controllers)
    assert controllers[0].owner is owner
    return controllers[0]


class CharacterSortHintContracts(unittest.TestCase):
    def test_pvp_sort_hint_identifies_selected_active_and_opponent_values(self) -> None:
        original_language = get_language()
        self.addCleanup(set_language, original_language)
        workspace = PvpDraftWorkspace()
        self.addCleanup(workspace.close)
        workspace._build_unified_pool({}, draft_complete=False)
        controls = workspace.character_filter_bar.sort_controls
        controllers = {button: _controller(button) for button in controls.buttons.values()}
        expectations = {
            "ru": "В PvP используются данные выбранного игрока, а в общем пуле — игрока, который сейчас ходит. Если персонаж есть только у соперника, используются данные владельца.",
            "en": "PvP uses the selected player's values; in the combined pool, it uses the player whose turn it is. If only the opponent owns a character, that owner's values are used.",
            "pt-br": "No PvP, são usados os valores do jogador selecionado; no grupo combinado, os do jogador da vez. Se apenas o adversário possui o personagem, são usados os valores desse dono.",
        }
        controls.constellation_button.click()
        for language, expected in expectations.items():
            set_language(language)
            workspace.character_filter_bar.retranslate_ui()
            self.assertEqual(controls.state.criterion, "constellation")
            self.assertEqual(controls.state.mode, 1)
            for button, controller in controllers.items():
                self.assertIs(_controller(button), controller)
                self.assertIn(expected, controller.text())
                self.assertEqual(button.toolTip(), "")

    def test_sort_hints_describe_modes_and_exclusive_switch_in_all_languages(self) -> None:
        original_language = get_language()
        self.addCleanup(set_language, original_language)
        bar = CharacterFilterBar()
        self.addCleanup(bar.close)
        selected_filter = bar.buttons[0]
        selected_filter.click()
        bar.standard_button.click()
        selected_standard_filter = bar.standard_filter
        controls = bar.sort_controls
        constellation = controls.buttons["constellation"]
        level = controls.buttons["level"]
        constellation_controller = _controller(constellation)
        level_controller = _controller(level)

        for language in _LANGUAGES:
            with self.subTest(language=language):
                expected = _SORT_EXPECTATIONS[language]
                set_language(language)
                controls.reset(emit=False)

                self.assertEqual(level.property("sortMode"), 0)
                self.assertIn(expected["level_title"], level_controller.text())
                self.assertIn(expected["off"], level_controller.text())
                self.assertIn(expected["current"].format(mode=0), level_controller.text())
                self.assertIn(expected["exclusive"], level_controller.text())

                for mode in (1, 2, 3):
                    level.click()
                    text = level_controller.text()
                    self.assertEqual(level.property("sortMode"), mode)
                    self.assertIn(expected["level_title"], text)
                    self.assertIn(expected["current"].format(mode=mode), text)
                    self.assertIn(expected["level_modes"][mode], text)
                    self.assertEqual(level.toolTip(), "")
                    self.assertTrue(selected_filter.isChecked())
                    self.assertEqual(bar.standard_filter, selected_standard_filter)

                level.click()
                self.assertEqual(level.property("sortMode"), 0)
                self.assertIn(expected["off"], level_controller.text())
                self.assertIn(expected["current"].format(mode=0), level_controller.text())

                for mode in (1, 2):
                    constellation.click()
                    text = constellation_controller.text()
                    self.assertEqual(constellation.property("sortMode"), mode)
                    self.assertIn(expected["constellation_title"], text)
                    self.assertIn(expected["current"].format(mode=mode), text)
                    self.assertIn(expected["constellation_modes"][mode], text)
                    self.assertEqual(constellation.toolTip(), "")

                constellation.click()
                self.assertEqual(constellation.property("sortMode"), 0)
                self.assertIn(expected["off"], constellation_controller.text())
                self.assertIn(expected["current"].format(mode=0), constellation_controller.text())

                # Restart the constellation cycle, then verify selecting level replaces it.
                constellation.click()
                self.assertEqual(constellation.property("sortMode"), 1)

                # Choosing level replaces the active constellation sort.
                level.click()
                self.assertEqual(constellation.property("sortMode"), 0)
                self.assertEqual(level.property("sortMode"), 1)
                self.assertIn(expected["current"].format(mode=0), constellation_controller.text())
                self.assertIn(expected["current"].format(mode=1), level_controller.text())
                self.assertIn(expected["exclusive"], constellation_controller.text())

                # Retranslation changes the copy while preserving the active sort and controllers.
                next_language = _LANGUAGES[(_LANGUAGES.index(language) + 1) % len(_LANGUAGES)]
                set_language(next_language)
                controls.retranslate_ui()
                bar.retranslate_ui()
                next_expected = _SORT_EXPECTATIONS[next_language]
                self.assertEqual(level.property("sortMode"), 1)
                self.assertEqual(constellation.property("sortMode"), 0)
                self.assertTrue(selected_filter.isChecked())
                self.assertEqual(bar.standard_filter, selected_standard_filter)
                self.assertIn(next_expected["level_modes"][1], _controller(level).text())
                self.assertIn(next_expected["current"].format(mode=1), _controller(level).text())
                self.assertIs(_controller(constellation), constellation_controller)
                self.assertIs(_controller(level), level_controller)
                self.assertEqual(constellation.toolTip(), "")
                self.assertEqual(level.toolTip(), "")

    def test_artifact_filter_hints_explain_pinned_targets_in_all_languages(self) -> None:
        original_language = get_language()
        self.addCleanup(set_language, original_language)
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        db_path = Path(temporary_directory.name) / "unused.db"
        browser = ArtifactBrowserWindow(
            embedded=True,
            db_path=db_path,
            character_asset_items=[],
            read_only_source=True,
        )
        self.addCleanup(browser.close)
        self.assertFalse(db_path.exists())

        filter_buttons = tuple(browser._build_target_filter_tooltip_keys)
        filter_controllers = {
            button: _controller(button) for button in filter_buttons
        }
        sort_controls = browser.build_target_sort_controls
        level_button = sort_controls.buttons["level"]
        level_button.click()
        sort_controller = _controller(level_button)
        self.assertEqual(level_button.property("sortMode"), 1)

        for language in _LANGUAGES:
            with self.subTest(language=language):
                set_language(language)
                browser.retranslate_ui()
                character_phrase, universal_phrase = _PINNED_TARGET_EXPECTATIONS[language]
                self.assertEqual(level_button.property("sortMode"), 1)
                self.assertEqual(sort_controls.state.mode, 1)
                self.assertIs(_controller(level_button), sort_controller)
                self.assertEqual(level_button.toolTip(), "")
                self.assertIn(
                    _SORT_EXPECTATIONS[language]["current"].format(mode=1),
                    sort_controller.text(),
                )
                self.assertIn(_SORT_EXPECTATIONS[language]["level_modes"][1], sort_controller.text())
                for button in filter_buttons:
                    controller = filter_controllers[button]
                    self.assertIs(_controller(button), controller)
                    self.assertEqual(button.toolTip(), "")
                    self.assertIn(character_phrase, controller.text())
                    self.assertIn(universal_phrase, controller.text())
                self.assertFalse(db_path.exists())

    def test_filter_hints_explain_group_intersection_and_conflicts_in_all_languages(self) -> None:
        original_language = get_language()
        self.addCleanup(set_language, original_language)
        bar = CharacterFilterBar()
        self.addCleanup(bar.close)
        selected_filter = bar.buttons[0]
        selected_filter.click()
        bar.standard_button.click()
        self.assertTrue(selected_filter.isChecked())
        selected_standard_filter = bar.standard_filter
        controllers = [_controller(button) for button in bar.buttons]

        for language in _LANGUAGES:
            with self.subTest(language=language):
                set_language(language)
                bar.retranslate_ui()
                self.assertTrue(selected_filter.isChecked())
                self.assertEqual(bar.standard_filter, selected_standard_filter)
                self.assertEqual(len(bar.buttons), len(controllers))
                for button, controller in zip(bar.buttons, controllers):
                    self.assertIs(_controller(button), controller)
                    self.assertEqual(button.toolTip(), "")
                    for phrase in _FILTER_RULE_EXPECTATIONS[language]:
                        with self.subTest(phrase=phrase):
                            self.assertIn(phrase, controller.text())


if __name__ == "__main__":
    unittest.main()
