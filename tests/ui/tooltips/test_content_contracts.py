"""Independent semantic checks for non-artifact-set tooltip producers.

All Qt widgets use the offscreen platform and owned in-memory fixtures. These
checks deliberately assert user-facing facts, not values recomputed by a
second call to the producer under test.
"""

from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QLabel

from hoyolab_export.account_storage import AccountCharacterRuntimeRecord, AccountWeaponObservedStack
from run_workspace.history_browser_catalog import (
    _run_visual, HistoryBonusVisual, HistoryEnemyVisual, HistorySideVisual, HistorySlotVisual,
)
from run_workspace.right_panel_prototype_view_model import (
    FactDpsEnemyTooltipViewModel,
    FactDpsTooltipViewModel,
    GcsimTooltipViewModel,
    RightPanelBonusSourceDisplayItem,
    RightPanelChamberRowViewModel,
    RightPanelGcsimStatusViewModel,
    _TeamBonusMember,
    _elemental_resonance_tooltip,
    _hexerei_member_tooltip,
    _warning_tooltip,
    _weapon_tooltip_title_body,
)
from ui.character_assets import _character_tooltip, _weapon_tooltip as _observed_weapon_tooltip
from ui.artifact_browser.window import ArtifactBrowserWindow
from ui.right_panel.common.history_card import CardPainter, HistoryCardWidget
from ui.right_panel.live_run.panel import (
    BonusSourceChipWidget,
    BonusSourceStripWidget,
    ChamberTableBlockWidget,
    _fact_dps_tooltip_html,
    _gcsim_tooltip_html,
)
from ui.right_panel.pvp._shared import (
    _draft_unified_card_text,
    _postdraft_character_tooltip,
    _postdraft_weapon_tooltip,
)
from ui.utils.tooltips import CustomTooltipController
from tests.run_workspace.history.test_history_snapshot_right_panel import _bundle


class ContentContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_account_character_summary_identifies_level_constellation_and_element(self) -> None:
        record = AccountCharacterRuntimeRecord("1001", "Mona", element="Hydro", level=90, constellation=2)
        self.assertEqual(_character_tooltip(record), "Mona\nLv.90 | C2 | Hydro")
        self.assertEqual(_character_tooltip(replace(record, name="", level=None, constellation=None, element="")), "1001")

    def test_observed_weapon_summary_distinguishes_stack_count_and_stats(self) -> None:
        record = AccountWeaponObservedStack(
            id=1, weapon_fingerprint="owned", weapon_id="2001", name="Sample Spear",
            refinement=3, level=80, base_atk=509.5, known_count=2,
        )
        self.assertEqual(_observed_weapon_tooltip(record), "Sample Spear\nR3 | Lv.80 | ATK 509.5 | x2")
        self.assertEqual(_observed_weapon_tooltip(replace(record, name="", refinement=None, known_count=1)),
                         "2001\nLv.80 | ATK 509.5")

    def test_weapon_passive_uses_reference_title_and_body_not_flavor_copy(self) -> None:
        title, body = _weapon_tooltip_title_body({
            "account_weapon": {"name": "Favonius Lance", "refinement": 5, "level": 90,
                               "description": "A polearm made for a knight."},
            "weapon_passive_reference": {"passive_name": "Windfall", "passive_text": "CRIT Hits generate particles."},
        })
        self.assertEqual(title, "Favonius Lance R5")
        self.assertIn("Lv.90", body)
        self.assertIn("Windfall\nCRIT Hits generate particles.", body)
        self.assertNotIn("A polearm made", body)
        self.assertEqual(_weapon_tooltip_title_body({}), ("", ""))

    def test_elemental_resonance_explains_distinct_rules(self) -> None:
        geo_member = _TeamBonusMember(0, "Noelle", "geo", (), "", {})
        self.assertIn("Hydro+Pyro adds another +20", _elemental_resonance_tooltip({"element": "dendro"}, None))
        self.assertIn("Geo DMG Bonus", _elemental_resonance_tooltip({"element": "geo"}, geo_member))
        self.assertIn("Direct display-stat", _elemental_resonance_tooltip({"element": "pyro"}, None))

    def test_hexerei_member_and_warning_text_preserve_meaning_and_newlines(self) -> None:
        self.assertEqual(_hexerei_member_tooltip("Mona", "C0: First line\nC2: Second line",
                                                  source_url="unused", missing_text="Unavailable"),
                         "Mona\n\nC0: First line\nC2: Second line")
        self.assertEqual(_hexerei_member_tooltip("Mona", "", source_url="unused", missing_text="Unavailable"),
                         "Mona\n\nUnavailable")
        warnings = _warning_tooltip(("artifact_build_incomplete", "duplicate_selected_character"))
        self.assertIn("нет одного или нескольких слотов артефактов", warnings)
        self.assertIn("Персонаж выбран больше одного раза.", warnings)
        self.assertEqual(len(warnings.splitlines()), 2)

    def test_fact_dps_html_shows_enemy_calculation_and_escaped_names(self) -> None:
        enemy = FactDpsEnemyTooltipViewModel(
            wave=1, primary_display_name="Mage <elite>", enemy_count=2, display_level=100,
            matched_nanoka_display_name=None, hp_used=125_000, hp_source="Nanoka",
            match_method="strict_name", match_confidence="high", selected_for_solo=True,
        )
        tooltip = FactDpsTooltipViewModel(
            title="Floor <12>", formula="HP / seconds", total_hp=250_000,
            total_solo_hp=125_000, total_multi_target_hp=250_000,
            hp_mode="solo", hp_mode_label="solo", elapsed_seconds=50,
            calculated_dps=5_000, hp_source_label="Nanoka resolved HP", enemies=(enemy,),
        )
        result = _fact_dps_tooltip_html(tooltip)
        self.assertIn("Floor &lt;12&gt;", result)
        self.assertIn("x2 Mage &lt;elite&gt; Lv.100", result)
        self.assertIn("125,000", result)
        self.assertIn("250,000", result)
        self.assertIn("5,000", result)
        self.assertIn("Nanoka resolved HP", result)
        self.assertNotIn("Mage <elite>", result)
        self.assertEqual(_fact_dps_tooltip_html(None), "")

    def test_gcsim_html_surfaces_stale_state_and_escapes_paths(self) -> None:
        tooltip = GcsimTooltipViewModel(
            title="Floor 12 / Team 1", status="stale", dps_mean=12345,
            config_path="C:/owned/<test>.gcsim", stale_reasons=("Weapon changed",),
            warnings=("Check <rotation>",), notes=(),
        )
        result = _gcsim_tooltip_html(tooltip)
        self.assertIn("<b>Status</b>: stale", result)
        self.assertIn("Sim DPS mean", result)
        self.assertIn("12345", result)
        self.assertIn("Stale reasons", result)
        self.assertIn("Weapon changed", result)
        self.assertIn("C:/owned/&lt;test&gt;.gcsim", result)
        self.assertIn("Check &lt;rotation&gt;", result)
        self.assertNotIn("C:/owned/<test>.gcsim", result)
        self.assertNotIn("Sim clear time", result)
        self.assertEqual(_gcsim_tooltip_html(None), "")

    def test_chamber_cells_attach_and_refresh_fact_and_gcsim_tooltips(self) -> None:
        fact = FactDpsTooltipViewModel(
            title="Floor 12 / C1 / Team 1", formula="HP / seconds",
            total_hp=120_000, total_solo_hp=120_000, total_multi_target_hp=120_000,
            hp_mode="solo", hp_mode_label="off", elapsed_seconds=60,
            calculated_dps=2_000, hp_source_label="Nanoka resolved HP",
        )
        sim = GcsimTooltipViewModel(title="GCSIM / C1", status="stale",
                                    dps_mean=4_000, stale_reasons=("Weapon changed",), notes=())
        row = RightPanelChamberRowViewModel(
            chamber_label="C1", team1_time="09:00", team1_seconds=60,
            team2_time="09:00", team2_seconds=0, factual_team1="2,000",
            factual_team2="-", sim_team1="stale", sim_team2="-",
            total_seconds=60, factual_team1_tooltip=fact, sim_team1_tooltip=sim,
        )
        table = ChamberTableBlockWidget(read_only=True)
        self.addCleanup(table.deleteLater)
        headers = ("Chamber", "T1", "T2", "Fact T1", "Fact T2", "Sim T1", "Sim T2")
        status = RightPanelGcsimStatusViewModel(status="Idle")
        table.set_rows(headers, (row,), total_seconds=60, gcsim_status=status)
        fact_label, sim_label = table._row_labels[(0, 3)], table._row_labels[(0, 5)]
        fact_controller = table._fact_dps_tooltips[(0, 3)]
        sim_controller = table._gcsim_tooltips[(0, 5)]
        self.assertIs(fact_label.findChild(CustomTooltipController), fact_controller)
        self.assertIs(sim_label.findChild(CustomTooltipController), sim_controller)
        self.assertEqual((fact_label.text(), sim_label.text()), ("2,000", "stale"))
        self.assertIn("120,000", fact_controller.text())
        self.assertIn("DPS: 2,000", fact_controller.text())
        self.assertIn("Weapon changed", sim_controller.text())
        self.assertEqual((fact_label.toolTip(), sim_label.toolTip()), ("", ""))

        newer = replace(row, factual_team1="3,000", sim_team1="passed",
                        factual_team1_tooltip=replace(fact, calculated_dps=3_000),
                        sim_team1_tooltip=replace(sim, status="passed", stale_reasons=()))
        table.set_rows(headers, (newer,), total_seconds=60, gcsim_status=status)
        self.assertIs(table._fact_dps_tooltips[(0, 3)], fact_controller)
        self.assertIs(table._gcsim_tooltips[(0, 5)], sim_controller)
        self.assertIn("DPS: 3,000", fact_controller.text())
        self.assertNotIn("DPS: 2,000", fact_controller.text())
        self.assertIn("<b>Status</b>: passed", sim_controller.text())
        self.assertNotIn("Weapon changed", sim_controller.text())

        table.set_rows(headers, (replace(newer, factual_team1_tooltip=None,
                                         sim_team1_tooltip=None),), total_seconds=60,
                       gcsim_status=status)
        self.assertEqual(fact_controller.text(), "")
        self.assertEqual(sim_controller.text(), "")

    def test_bonus_source_kinds_attach_meaningful_custom_tooltips(self) -> None:
        samples = (
            ("weapon", "Favonius Lance R5", "Windfall", "ATK +20%"),
            ("artifact_set_static", "Emblem of Severed Fate 2p", "Energy Recharge +20%", "ER +20%"),
            ("elemental_resonance", "Pyro Resonance", "Direct display-stat", "ATK +25%"),
            ("moonsign", "Moonsign", "лимит: 36%", "Lunar +36%"),
            ("hexerei", "Hexerei", "Mona joins", "Hexerei +1"),
        )
        for kind, title, body, effect in samples:
            with self.subTest(kind=kind):
                item = RightPanelBonusSourceDisplayItem(
                    source_kind=kind, source_id="fixture", label="Source",
                    short_effects=(effect,), tooltip_title=title,
                    tooltip_body=body + " & More\n<unsafe>", applied=True,
                )
                chip = BonusSourceChipWidget(item)
                self.addCleanup(chip.deleteLater)
                controllers = chip.findChildren(CustomTooltipController)
                self.assertEqual(len(controllers), 1)
                content = controllers[0].text()
                self.assertIn(title, content)
                self.assertIn(body, content)
                self.assertIn(effect, content)
                self.assertIn("&amp; More", content)
                self.assertNotIn("<unsafe>", content)

    def test_bonus_source_tooltip_refreshes_when_body_changes(self) -> None:
        strip = BonusSourceStripWidget(interactive=False)
        self.addCleanup(strip.deleteLater)
        item = RightPanelBonusSourceDisplayItem(
            source_kind="weapon", source_id="owned-weapon", label="Weapon",
            tooltip_title="Windfall", tooltip_body="Old passive text",
        )
        strip.set_items((item,), external_bonuses_enabled=True)
        chip = strip._layout.itemAt(0).widget()
        self.assertIn("Old passive text", chip.findChild(CustomTooltipController).text())
        strip.set_items((replace(item, tooltip_body="New passive text"),), external_bonuses_enabled=True)
        refreshed = strip._layout.itemAt(0).widget()
        self.assertIsNot(refreshed, chip)
        current = refreshed.findChild(CustomTooltipController).text()
        self.assertIn("New passive text", current)
        self.assertNotIn("Old passive text", current)

    def test_pvp_postdraft_character_and_weapon_summaries(self) -> None:
        self.assertEqual(_postdraft_character_tooltip("Mona", assigned=False), "Mona")
        self.assertEqual(_postdraft_character_tooltip("Mona", assigned=True), "Mona\nassigned")
        stack = SimpleNamespace(display_name="Favonius Lance", refinement=5, level=90, count=2)
        deck = SimpleNamespace(weapon_stack_by_key={"stack-1": stack})
        state = SimpleNamespace(deck_for=lambda seat: deck)
        session = SimpleNamespace(controller=SimpleNamespace(session_state=state))
        self.assertEqual(_postdraft_weapon_tooltip(session, "player_1", "stack-1"),
                         "Favonius Lance\nR5 | Lv.90 | x2")
        self.assertEqual(_postdraft_weapon_tooltip(session, "player_1", "unknown"), "unknown")
        self.assertEqual(_postdraft_weapon_tooltip(session, "player_1", ""), "")

    def test_pvp_draft_card_tooltip_shows_per_seat_ownership(self) -> None:
        tooltip = _draft_unified_card_text({
            "character_id": "1001", "display_name": "Mona", "element": "Hydro",
            "weapon_type": "Catalyst", "level": 90,
            "owner_seats": ["player_1", "player_2"],
            "per_seat": {"player_1": {"constellation": 0},
                         "player_2": {"constellation": 4}},
            "status": "picked_by_self",
        })
        self.assertTrue(tooltip.startswith("Mona\nHydro Catalyst Lv.90\n"))
        self.assertIn("P1 C0 | P2 C4", tooltip)
        self.assertEqual(len(tooltip.splitlines()), 4)
        self.assertNotIn("picked_by_self", tooltip)

    def test_artifact_build_slot_tooltip_refreshes_for_populated_empty_and_missing(self) -> None:
        icon, stat = QLabel(), QLabel()
        self.addCleanup(icon.deleteLater)
        self.addCleanup(stat.deleteLater)
        artifact = SimpleNamespace(icon_path="", name="Gladiator's Nostalgia", set_name="Gladiator")

        def read_artifact(artifact_id: int):
            if artifact_id == 7:
                return artifact
            raise KeyError(artifact_id)

        owner = SimpleNamespace(
            build_slot_icon_labels={1: icon}, build_slot_stat_labels={1: stat},
            store=SimpleNamespace(artifact=read_artifact),
            _position_label=lambda pos: "Flower",
            _set_slot_placeholder_icon=lambda pos: icon.setText("+"),
            _compact_main_stat_text=lambda item: "HP 4,780",
        )
        ArtifactBrowserWindow.update_build_slot_row(owner, 1, 7)
        controller = icon.findChild(CustomTooltipController)
        self.assertIsNotNone(controller)
        self.assertEqual(controller.text(), "Flower: Gladiator's Nostalgia")
        self.assertEqual(stat.text(), "HP 4,780")
        ArtifactBrowserWindow.update_build_slot_row(owner, 1, None)
        self.assertIs(icon.findChild(CustomTooltipController), controller)
        self.assertEqual(controller.text(), "Flower")
        self.assertEqual(stat.text(), "-")
        ArtifactBrowserWindow.update_build_slot_row(owner, 1, 999)
        self.assertIs(icon.findChild(CustomTooltipController), controller)
        self.assertEqual(controller.text(), "Flower")
        self.assertEqual(icon.text(), "?")
        self.assertEqual(len(icon.findChildren(CustomTooltipController)), 1)

    def test_history_compact_slot_hover_uses_saved_identity(self) -> None:
        visual = _run_visual(_bundle(), Path("unavailable/snapshot.json"))
        card = HistoryCardWidget(visual)
        self.addCleanup(card.deleteLater)
        card.resize(960, card.height())
        card.show()
        self.app.processEvents()
        card.grab()
        slot = next(value for _, value in card._hits
                    if isinstance(value, HistorySlotVisual) and value.character_name == "Mona")
        card._hover = slot
        card._show_hover()
        self.assertIs(card._character_popup.slot, slot)
        self.assertEqual(card._character_popup.slot.weapon_name, "The Widsith")
        self.assertEqual(card._character_popup.slot.weapon_refinement, 5)
        self.assertTrue(any("Emblem of Severed Fate" in label
                            for label in card._character_popup.slot.set_labels))
        painted_text: list[str] = []
        original_text = CardPainter.text

        def record_text(painter, *args, **kwargs):
            painted_text.append(next((value for value in args if isinstance(value, str)), ""))
            return original_text(painter, *args, **kwargs)

        with patch.object(CardPainter, "text", record_text):
            card._character_popup.grab()
        for expected in ("Mona", "The Widsith", "Emblem of Severed Fate 4pc", "CR", "70%"):
            self.assertIn(expected, painted_text)
        card.close()

    def test_history_bonus_hovers_show_source_and_overflow_content(self) -> None:
        visual = _run_visual(_bundle(), Path("unavailable/snapshot.json"))
        bonuses = tuple(HistoryBonusVisual(
            identity=f"source:{index}", label=f"Bonus {index}",
            tooltip=f"Bonus {index}\nKnown effect {index}",
        ) for index in range(35))
        visual = replace(visual, teams=(replace(visual.teams[0], bonuses=bonuses), *visual.teams[1:]))
        card = HistoryCardWidget(visual)
        self.addCleanup(card.deleteLater)
        card.resize(960, card.height())
        card.set_expanded(True)
        card.show()
        self.app.processEvents()
        card.grab()
        source_hover = next(value for _, value in card._hits
                            if isinstance(value, str) and value == "Bonus 0\nKnown effect 0")
        overflow = next(value for _, value in card._hits
                        if isinstance(value, str) and "Bonus 34\nKnown effect 34" in value)
        self.assertIn("\n\n", overflow)
        self.assertNotIn("Bonus 0\n", overflow)
        card._hover = source_hover
        card._show_hover()
        self.assertEqual(card._text_popup.text(), "Bonus 0\nKnown effect 0")
        card._hover = overflow
        card._show_hover()
        self.assertIn("Bonus 34\nKnown effect 34", card._text_popup.text())
        card.close()

    def test_history_enemy_hover_uses_saved_wave_count_and_hp(self) -> None:
        visual = _run_visual(_bundle(), Path("unavailable/snapshot.json"))
        visual = replace(visual, sides=(HistorySideVisual(1, 1, enemies=(
            HistoryEnemyVisual("Abyss Mage", level=100, count=2, wave=3, hp=125_000),
        )),))
        card = HistoryCardWidget(visual)
        self.addCleanup(card.deleteLater)
        card.resize(960, card.height())
        card.set_expanded(True)
        card.grab()
        hover = next(value for _, value in card._hits
                     if isinstance(value, str) and "Abyss Mage" in value)
        self.assertIn("100 | x2", hover)
        self.assertIn("3", hover)
        self.assertIn("HP 125 000", hover)
        self.assertNotIn("None", hover)
        card.close()


if __name__ == "__main__":
    unittest.main()
