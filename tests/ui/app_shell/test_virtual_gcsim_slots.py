from __future__ import annotations

import unittest
from unittest.mock import patch

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()

from PySide6.QtWidgets import QApplication, QMessageBox

_APP = QApplication.instance() or QApplication([])

from ui.app_shell import AppShell, AppShellController, _selected_team_has_characters
from ui.gcsim_browser.virtual_slot_editor import (
    VirtualGcsimBuildPopup,
    VirtualGcsimCardEditor,
)
from ui.gcsim_browser.run_worker import _selected_slot_count
from ui.right_panel.live_run.panel import RunRightPanelWidget
from run_workspace.gcsim.virtual_roster import (
    GcsimCatalogCharacter,
    GcsimCatalogWeapon,
    GcsimVirtualArtifactSetChoice,
    GcsimVirtualRosterCatalog,
    GcsimVirtualSetBonus,
    GcsimVirtualSlotOverride,
)


def _account_character(character_id: str, name: str) -> dict:
    return {
        "path": "portrait.png",
        "metadata": {
            "character": {
                "id": character_id,
                "name": name,
                "level": 90,
                "weapon_type_name": "polearm",
            }
        },
    }


def _complete_virtual_override(
    *,
    slot_index: int,
    key: str,
) -> GcsimVirtualSlotOverride:
    return GcsimVirtualSlotOverride(
        team_index=0,
        slot_index=slot_index,
        character_key=key,
        character_name=key.title(),
        character_weapon_type="polearm",
        weapon_key="virtualspear",
        weapon_name="Virtual Spear",
        weapon_type="polearm",
        constellation=2,
        refinement=3,
        character_level=90,
        talent_normal=8,
        talent_skill=10,
        talent_burst=10,
        weapon_level=90,
        weapon_promote_level=6,
        artifact_build_id=42,
        artifact_build_name="Virtual build",
        artifact_set_bonuses=(
            GcsimVirtualSetBonus("virtual_set", "Virtual Set", "virtualset", 4),
        ),
    )


class VirtualGcsimSlotControllerTest(unittest.TestCase):
    def test_override_clears_only_account_slot_and_reaches_gcsim_payload(self) -> None:
        controller = AppShellController.empty()
        controller.add_or_replace_character_fast(_account_character("1", "Account Hero"))
        override = GcsimVirtualSlotOverride(
            team_index=0,
            slot_index=0,
            character_key="virtualhero",
            character_name="VirtualHero",
            character_weapon_type="polearm",
            weapon_key="virtualspear",
            weapon_name="VirtualSpear",
            weapon_type="polearm",
            constellation=2,
            refinement=4,
        )

        self.assertTrue(controller.set_virtual_gcsim_override(override))
        self.assertTrue(controller.state.team(0).slot(0).is_empty)
        self.assertEqual(controller.virtual_gcsim_override(0, 0), override)

        model_slot = controller.right_panel_model().teams[0].slots[0]
        self.assertFalse(model_slot.is_empty)
        self.assertEqual(model_slot.character_title, "VirtualHero")
        self.assertEqual(model_slot.stat_badge, "R4")
        snapshot_slot = controller.right_panel_model(
            include_virtual_gcsim_overrides=False
        ).teams[0].slots[0]
        self.assertTrue(snapshot_slot.is_empty)

        payload_slot = controller.gcsim_browser_selected_team(0)["slots"][0]
        self.assertEqual(
            payload_slot["gcsim_virtual_override"]["character"]["gcsim_key"],
            "virtualhero",
        )
        self.assertFalse(payload_slot["is_empty"])
        selected_team = controller.gcsim_browser_selected_team(0)
        self.assertTrue(_selected_team_has_characters(selected_team))
        self.assertEqual(_selected_slot_count(selected_team), 1)

    def test_account_slot_order_still_sees_virtual_slot_as_empty(self) -> None:
        controller = AppShellController.empty()
        controller.set_virtual_gcsim_override(
            GcsimVirtualSlotOverride(
                team_index=0,
                slot_index=0,
                character_key="virtualhero",
                character_name="VirtualHero",
                character_weapon_type="polearm",
            )
        )

        self.assertEqual(controller.first_empty_account_slot(), (0, 0))
        self.assertTrue(controller.clear_virtual_gcsim_override(0, 0))
        result = controller.add_or_replace_character_fast(
            _account_character("1", "Account Hero")
        )
        self.assertEqual((result.team_index, result.slot_index), (0, 0))

    def test_compact_card_filters_weapons_and_emits_profile_changes(self) -> None:
        controls = VirtualGcsimCardEditor()
        catalog = GcsimVirtualRosterCatalog(
            engine_id="test",
            characters=(
                GcsimCatalogCharacter("hero", "Hero", "polearm"),
            ),
            weapons=(
                GcsimCatalogWeapon("spear", "Spear", "polearm"),
                GcsimCatalogWeapon("bow", "Bow", "bow"),
            ),
        )
        override = GcsimVirtualSlotOverride(
            team_index=0,
            slot_index=0,
            character_key="hero",
            character_name="Hero",
            character_weapon_type="polearm",
            weapon_key="spear",
            weapon_name="Spear",
            weapon_type="polearm",
            constellation=4,
            refinement=2,
        )
        constellation_values: list[int] = []
        refinement_values: list[int] = []
        profile_values: list[dict] = []
        controls.constellation_requested.connect(constellation_values.append)
        controls.refinement_requested.connect(refinement_values.append)
        controls.profile_requested.connect(profile_values.append)

        controls.set_catalogs(catalog, ())
        controls.set_context(
            override=override,
            artifact_builds=(
                {"id": 42, "name": "Virtual build", "slot_count": 5},
            ),
        )
        controls.constellation_button.click()
        controls.refinement_button.click()
        controls.character_level_spin.setValue(90)
        controls.profile_popup.talent_normal_spin.setValue(8)
        controls.profile_popup.talent_skill_spin.setValue(10)
        controls.profile_popup.talent_burst_spin.setValue(9)
        controls.weapon_level_spin.setValue(90)
        controls.profile_popup.weapon_ascension_combo.setCurrentIndex(
            controls.profile_popup.weapon_ascension_combo.findData(6)
        )
        controls.build_popup.saved_build_combo.setCurrentIndex(
            controls.build_popup.saved_build_combo.findData(42)
        )

        self.assertEqual(controls.weapon_combo.count(), 2)  # empty + compatible spear
        self.assertEqual(constellation_values, [5])
        self.assertEqual(refinement_values, [3])
        self.assertEqual(profile_values[0]["character_level"], 90)
        self.assertTrue(any(value.get("talent_skill") == 10 for value in profile_values))
        self.assertTrue(any(value.get("weapon_promote_level") == 6 for value in profile_values))
        self.assertEqual(profile_values[-1]["artifact_build_id"], 42)

    def test_set_selector_allows_only_one_4p_or_two_distinct_2p(self) -> None:
        popup = VirtualGcsimBuildPopup()
        choices = tuple(
            GcsimVirtualArtifactSetChoice(key, key.title(), key)
            for key in ("alpha", "beta", "gamma")
        )
        emitted: list[list[dict]] = []
        popup.set_bonuses_requested.connect(emitted.append)
        popup.set_context(override=None, artifact_builds=(), set_choices=choices)

        popup._cycle_set("alpha")
        popup._cycle_set("alpha")
        popup._cycle_set("beta")  # blocked while alpha is 4p
        self.assertEqual(
            [(row["set_uid"], row["count"]) for row in emitted[-1]],
            [("alpha", 4)],
        )

        popup._cycle_set("alpha")  # remove 4p
        popup._cycle_set("alpha")
        popup._cycle_set("beta")
        popup._cycle_set("gamma")  # blocked while alpha+beta is 2p+2p
        self.assertEqual(
            [(row["set_uid"], row["count"]) for row in emitted[-1]],
            [("alpha", 2), ("beta", 2)],
        )

    def test_swap_account_and_virtual_moves_both_without_account_equipment_leak(self) -> None:
        controller = AppShellController.empty()
        controller.add_or_replace_character_fast(_account_character("1", "Account Hero"))
        virtual = _complete_virtual_override(slot_index=1, key="virtualhero")
        controller.set_virtual_gcsim_override(virtual)

        self.assertTrue(controller.swap_slots(0, 0, 0, 1))

        self.assertEqual(controller.state.team(0).slot(1).character.id, "1")
        self.assertTrue(controller.state.team(0).slot(0).is_empty)
        moved = controller.virtual_gcsim_override(0, 0)
        self.assertIsNotNone(moved)
        self.assertEqual(moved.to_dict()["character"], virtual.to_dict()["character"])
        self.assertEqual(moved.artifact_build_id, 42)

    def test_swap_empty_and_virtual_moves_complete_profile(self) -> None:
        controller = AppShellController.empty()
        virtual = _complete_virtual_override(slot_index=1, key="virtualhero")
        controller.set_virtual_gcsim_override(virtual)

        self.assertTrue(controller.swap_slots(0, 1, 0, 3))

        self.assertIsNone(controller.virtual_gcsim_override(0, 1))
        moved = controller.virtual_gcsim_override(0, 3)
        self.assertIsNotNone(moved)
        self.assertEqual(moved.weapon_key, "virtualspear")
        self.assertEqual(moved.talent_burst, 10)

    def test_swap_two_virtual_profiles_preserves_each_identity(self) -> None:
        controller = AppShellController.empty()
        left = _complete_virtual_override(slot_index=0, key="left")
        right = _complete_virtual_override(slot_index=2, key="right")
        controller.set_virtual_gcsim_override(left)
        controller.set_virtual_gcsim_override(right)

        self.assertTrue(controller.swap_slots(0, 0, 0, 2))

        self.assertEqual(controller.virtual_gcsim_override(0, 0).character_key, "right")
        self.assertEqual(controller.virtual_gcsim_override(0, 2).character_key, "left")

    def test_right_panel_treats_virtual_slot_as_draggable_and_forwards_drop(self) -> None:
        controller = AppShellController.empty()
        controller.set_virtual_gcsim_override(
            _complete_virtual_override(slot_index=1, key="virtualhero")
        )
        panel = RunRightPanelWidget(controller.right_panel_model())
        source = next(
            widget
            for widget in panel._slot_widgets
            if widget.slot_position() == (0, 1)
        )
        drops: list[tuple[int, int, int, int]] = []
        panel.slot_dropped.connect(
            lambda *positions: drops.append(tuple(int(value) for value in positions))
        )

        self.assertFalse(source._model.is_empty)
        source.dropped.emit(0, 1, 0, 3)

        self.assertEqual(drops, [(0, 1, 0, 3)])

    def test_account_character_requires_confirmation_before_replacing_virtual(self) -> None:
        controller = AppShellController.empty()
        controller.set_virtual_gcsim_override(
            GcsimVirtualSlotOverride(
                team_index=0,
                slot_index=0,
                character_key="virtualhero",
                character_name="VirtualHero",
                character_weapon_type="polearm",
            )
        )
        shell = AppShell(controller=controller)

        with patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.No,
        ):
            shell._on_character_clicked(_account_character("1", "Account Hero"))
        self.assertIsNotNone(controller.virtual_gcsim_override(0, 0))
        self.assertTrue(controller.state.team(0).slot(0).is_empty)

        with patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            shell._on_character_clicked(_account_character("1", "Account Hero"))
        self.assertIsNone(controller.virtual_gcsim_override(0, 0))
        self.assertEqual(controller.state.team(0).slot(0).character.id, "1")

    def test_account_weapon_click_is_blocked_for_virtual_slot(self) -> None:
        controller = AppShellController.empty()
        override = GcsimVirtualSlotOverride(
            team_index=0,
            slot_index=0,
            character_key="virtualhero",
            character_name="VirtualHero",
            character_weapon_type="polearm",
        )
        controller.set_virtual_gcsim_override(override)
        shell = AppShell(controller=controller)

        with patch.object(QMessageBox, "information") as notice:
            shell._on_weapon_clicked(
                {
                    "path": "weapon.png",
                    "metadata": {
                        "weapon": {
                            "id": "1",
                            "name": "Account Spear",
                            "weapon_type_name": "polearm",
                        }
                    },
                }
            )

        notice.assert_called_once()
        self.assertEqual(controller.virtual_gcsim_override(0, 0), override)
        self.assertTrue(controller.state.team(0).slot(0).is_empty)


if __name__ == "__main__":
    unittest.main()
