from __future__ import annotations

import unittest

from run_workspace.team_builder import (
    TEAM_BUILDER_STATUS_EMPTY,
    TEAM_BUILDER_STATUS_READY,
    WARNING_DUPLICATE_SELECTED_CHARACTER,
    WARNING_WEAPON_ALLOCATION_DEFERRED,
    SelectedArtifactBuildRef,
    SelectedCharacterRef,
    SelectedWeaponRef,
    create_empty_team,
    create_empty_team_builder_state,
)


class FakeCharacterDetailsData:
    def to_dict(self) -> dict:
        return {
            "status": "ready",
            "account_character": {"id": "10000021", "name": "Amber"},
        }


class TeamBuilderStateTest(unittest.TestCase):
    def test_create_empty_four_slot_team(self) -> None:
        team = create_empty_team()

        self.assertEqual(len(team.slots), 4)
        self.assertTrue(all(slot.is_empty for slot in team.slots))
        self.assertEqual(team.to_dict()["status"], TEAM_BUILDER_STATUS_EMPTY)

    def test_set_character_weapon_and_build_id_in_slot(self) -> None:
        state = create_empty_team_builder_state()
        state = state.set_character(
            0,
            0,
            {
                "id": 10000021,
                "name": "Amber",
                "level": 80,
                "element": "Pyro",
                "rarity": 4,
                "constellation": 6,
                "icon": "must-not-leak",
            },
        )
        state = state.set_weapon(
            0,
            0,
            {
                "id": 15403,
                "name": "Favonius Warbow",
                "level": 90,
                "refinement": 5,
                "type_name": "Bow",
                "icon": "must-not-leak",
            },
        )
        state = state.set_artifact_build(0, 0, {"build_id": 20, "build_name": "test111"})

        slot = state.team(0).slot(0)
        self.assertEqual(slot.character.id, "10000021")
        self.assertEqual(slot.weapon.variant_key, "favonius warbow|90|5|bow")
        self.assertEqual(slot.artifact_build.build_id, 20)

        data = state.to_dict()
        self.assertEqual(data["status"], TEAM_BUILDER_STATUS_READY)
        self.assertEqual(data["teams"][0]["slots"][0]["artifact_build"]["build_id"], 20)
        self.assertFalse(_contains_forbidden_key(data, {"icon", "image_path", "local_path"}))

    def test_clear_slot_removes_all_selections(self) -> None:
        state = create_empty_team_builder_state()
        state = state.set_character(0, 0, {"id": 1, "name": "Amber"})
        state = state.set_weapon(0, 0, {"id": 2, "name": "Bow"})
        state = state.set_artifact_build(0, 0, 20)

        state = state.clear_slot(0, 0)

        self.assertTrue(state.team(0).slot(0).is_empty)
        self.assertIsNone(state.team(0).slot(0).character)
        self.assertIsNone(state.team(0).slot(0).weapon)
        self.assertIsNone(state.team(0).slot(0).artifact_build)

    def test_clear_weapon_and_build_keep_character(self) -> None:
        state = create_empty_team_builder_state()
        state = state.set_character(0, 0, {"id": 1, "name": "Amber"})
        state = state.set_weapon(0, 0, {"id": 2, "name": "Bow"})
        state = state.set_artifact_build(0, 0, 20)

        state = state.clear_weapon(0, 0)
        self.assertEqual(state.team(0).slot(0).character.name, "Amber")
        self.assertIsNone(state.team(0).slot(0).weapon)
        self.assertIsNotNone(state.team(0).slot(0).artifact_build)

        state = state.clear_artifact_build(0, 0)
        self.assertEqual(state.team(0).slot(0).character.name, "Amber")
        self.assertIsNone(state.team(0).slot(0).artifact_build)

    def test_swap_slots(self) -> None:
        state = create_empty_team_builder_state()
        state = state.set_character(0, 0, {"id": "a", "name": "Amber"})
        state = state.set_character(0, 1, {"id": "b", "name": "Barbara"})

        state = state.swap_slots(0, 0, 0, 1)

        self.assertEqual(state.team(0).slot(0).character.name, "Barbara")
        self.assertEqual(state.team(0).slot(1).character.name, "Amber")
        self.assertEqual(state.team(0).slot(0).slot_index, 0)
        self.assertEqual(state.team(0).slot(1).slot_index, 1)

    def test_move_slot_clears_source(self) -> None:
        state = create_empty_team_builder_state()
        state = state.set_character(0, 0, {"id": "a", "name": "Amber"})
        state = state.set_weapon(0, 0, {"id": "w", "name": "Bow"})

        state = state.move_slot(0, 0, 0, 2)

        self.assertTrue(state.team(0).slot(0).is_empty)
        self.assertEqual(state.team(0).slot(2).character.name, "Amber")
        self.assertEqual(state.team(0).slot(2).weapon.name, "Bow")

    def test_cross_team_swap_and_move(self) -> None:
        state = create_empty_team_builder_state(team_count=2)
        state = state.set_character(0, 0, {"id": "a", "name": "Amber"})
        state = state.set_character(1, 0, {"id": "b", "name": "Barbara"})

        state = state.swap_slots(0, 0, 1, 0)

        self.assertEqual(state.team(0).slot(0).character.name, "Barbara")
        self.assertEqual(state.team(1).slot(0).character.name, "Amber")

        state = state.move_slot(0, 0, 1, 1)
        self.assertTrue(state.team(0).slot(0).is_empty)
        self.assertEqual(state.team(1).slot(1).character.name, "Barbara")

    def test_duplicate_character_detection_across_state(self) -> None:
        state = create_empty_team_builder_state(team_count=2)
        state = state.set_character(0, 0, {"id": "10000021", "name": "Amber"})
        state = state.set_character(1, 1, {"id": "10000021", "name": "Amber"})

        self.assertEqual(state.duplicate_character_ids(), ("10000021",))
        self.assertIn(WARNING_DUPLICATE_SELECTED_CHARACTER, state.validation_warnings())
        self.assertIn(WARNING_DUPLICATE_SELECTED_CHARACTER, state.to_dict()["warnings"])

    def test_can_attach_prepared_character_details_without_ui_dependency(self) -> None:
        details = FakeCharacterDetailsData()
        state = create_empty_team_builder_state()
        state = state.set_character(0, 0, {"id": "10000021", "name": "Amber"})
        state = state.attach_character_details_data(0, 0, details)

        data = state.to_dict()
        self.assertEqual(
            data["teams"][0]["slots"][0]["character_details_data"]["status"],
            "ready",
        )

    def test_ref_inputs_can_be_explicit_dataclasses(self) -> None:
        state = create_empty_team_builder_state()
        state = state.set_character(
            0,
            0,
            SelectedCharacterRef(id="10000021", name="Amber"),
        )
        state = state.set_weapon(
            0,
            0,
            SelectedWeaponRef(id="15403", name="Favonius Warbow"),
        )
        state = state.set_artifact_build(
            0,
            0,
            SelectedArtifactBuildRef(build_id=20, build_name="test111"),
        )

        slot = state.team(0).slot(0)
        self.assertEqual(slot.character.name, "Amber")
        self.assertEqual(slot.weapon.name, "Favonius Warbow")
        self.assertEqual(slot.artifact_build.build_name, "test111")
        self.assertIn(WARNING_WEAPON_ALLOCATION_DEFERRED, slot.weapon.warnings)
        self.assertNotIn(WARNING_WEAPON_ALLOCATION_DEFERRED, state.validation_warnings())


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, dict):
        return any(
            key in forbidden or _contains_forbidden_key(item, forbidden)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


if __name__ == "__main__":
    unittest.main()
