from __future__ import annotations

import unittest

from run_workspace.team_builder import (
    WARNING_DUPLICATE_SELECTED_CHARACTER,
    create_empty_team_builder_state,
)
from run_workspace.team_card_view_model import (
    EMPTY_SLOT_TITLE,
    build_team_card_view_model_from_state,
)


class FakeCharacterDetailsData:
    def to_dict(self) -> dict:
        return {
            "status": "ready",
            "account_character": {
                "id": "10000050",
                "name": "Тома",
                "level": 70,
                "element": "Pyro",
                "constellation": 6,
            },
            "account_weapon": {
                "id": "13407",
                "name": "Копьё Фавония",
                "level": 70,
                "refinement": 5,
            },
            "selected_build": {
                "build_id": 20,
                "build_name": "test111",
            },
            "stat_snapshot": {
                "artifact": {
                    "summary": {
                        "build_id": 20,
                        "build_name": "test111",
                        "active_set_bonuses": [
                            {
                                "set_name": "Серенада шёлковой луны",
                                "piece_count": 2,
                            },
                            {
                                "set_name": "Эмблема рассечённой судьбы",
                                "piece_count": 2,
                            },
                        ],
                        "crit_value": 95.6,
                        "proc_count": 12,
                        "missing_positions": [5],
                    },
                    "warnings": [
                        "artifact_build_incomplete",
                        "set_bonus_formulas_not_included",
                    ],
                },
            },
            "warnings": [
                "final_totals_not_computed",
                "artifact_build_incomplete",
            ],
        }


class TeamCardViewModelTest(unittest.TestCase):
    def test_empty_team_has_four_empty_slots(self) -> None:
        state = create_empty_team_builder_state()
        model = build_team_card_view_model_from_state(state)

        self.assertEqual(len(model.slots), 4)
        self.assertTrue(all(slot.is_empty for slot in model.slots))
        self.assertEqual(model.slots[0].character_title, EMPTY_SLOT_TITLE)

    def test_filled_slot_uses_typed_refs_without_details(self) -> None:
        state = create_empty_team_builder_state()
        state = state.set_character(
            0,
            0,
            {
                "id": "10000021",
                "name": "Amber",
                "level": 80,
                "element": "Pyro",
                "constellation": 6,
                "icon": "must-not-leak",
            },
        )
        state = state.set_weapon(
            0,
            0,
            {
                "id": "15403",
                "name": "Favonius Warbow",
                "level": 90,
                "refinement": 5,
                "icon": "must-not-leak",
            },
        )
        state = state.set_artifact_build(0, 0, {"build_id": 20, "build_name": "test111"})

        model = build_team_card_view_model_from_state(state)
        slot = model.slots[0]

        self.assertFalse(slot.is_empty)
        self.assertEqual(slot.character_title, "Amber")
        self.assertIn("Lv.80", slot.character_meta)
        self.assertIn("C6", slot.character_meta)
        self.assertEqual(slot.weapon_label, "Favonius Warbow Lv.90 R5")
        self.assertEqual(slot.build_label, "Build #20: test111")
        self.assertIsNone(slot.artifact_summary)
        self.assertFalse(_contains_forbidden_key(model.to_dict(), {"icon", "image_path"}))

    def test_character_details_data_adds_artifact_summary(self) -> None:
        state = create_empty_team_builder_state()
        state = state.set_character(0, 0, {"id": "10000050", "name": "Тома"})
        state = state.attach_character_details_data(0, 0, FakeCharacterDetailsData())

        model = build_team_card_view_model_from_state(state, title="Prototype")
        slot = model.slots[0]

        self.assertEqual(model.title, "Prototype")
        self.assertEqual(slot.character_title, "Тома")
        self.assertEqual(slot.weapon_label, "Копьё Фавония Lv.70 R5")
        self.assertEqual(slot.build_label, "Build #20: test111")
        self.assertIsNotNone(slot.artifact_summary)
        self.assertEqual(slot.artifact_summary.crit_value, 95.6)
        self.assertEqual(slot.artifact_summary.proc_count, 12)
        self.assertEqual(slot.artifact_summary.missing_positions, (5,))
        self.assertIn("2p Серенада шёлковой луны", slot.artifact_summary.active_sets)
        self.assertIn("artifact_build_incomplete", slot.warnings)

    def test_duplicate_character_warning_is_displayed_on_state_and_slots(self) -> None:
        state = create_empty_team_builder_state(team_count=2)
        state = state.set_character(0, 0, {"id": "10000021", "name": "Amber"})
        state = state.set_character(1, 0, {"id": "10000021", "name": "Amber"})

        model = build_team_card_view_model_from_state(state, team_index=0)

        self.assertIn(WARNING_DUPLICATE_SELECTED_CHARACTER, model.warnings)
        self.assertIn(WARNING_DUPLICATE_SELECTED_CHARACTER, model.slots[0].warnings)

    def test_to_dict_shape_is_serializable_friendly(self) -> None:
        state = create_empty_team_builder_state()
        state = state.set_character(0, 0, {"id": "10000021", "name": "Amber"})
        model = build_team_card_view_model_from_state(state)
        data = model.to_dict()

        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["slots"][0]["character_title"], "Amber")
        self.assertIsNone(data["slots"][0]["artifact_summary"])


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
