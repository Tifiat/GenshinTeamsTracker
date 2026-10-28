from __future__ import annotations

import unittest
from pathlib import Path

from ui import right_panel_prototype_smoke as smoke


@unittest.skipUnless(Path("data/artifacts.db").is_file(), "local account DB is not available")
class RightPanelPrototypeSmokePresetTest(unittest.TestCase):
    def test_real_smoke_uses_moonsign_team_and_aqua_yelan_when_available(self) -> None:
        state = smoke.build_real_thoma_state()
        team = state.team(1)

        self.assertEqual(
            [str(team.slot(index).character.id) for index in range(4)],
            [
                smoke.LAUMA_CHARACTER_ID,
                smoke.INEFFA_CHARACTER_ID,
                smoke.NAHIDA_CHARACTER_ID,
                smoke.YELAN_CHARACTER_ID,
            ],
        )
        self.assertEqual(str(team.slot(3).weapon.id), smoke.YELAN_SIGNATURE_WEAPON_ID)

    def test_real_smoke_first_team_contains_hexerei_slot_and_mona(self) -> None:
        state = smoke.build_real_thoma_state()
        team = state.team(0)

        self.assertEqual(str(team.slot(2).character.id), smoke.MONA_CHARACTER_ID)
        self.assertIn(
            str(team.slot(1).character.id),
            {
                smoke.SUCROSE_CHARACTER_ID,
                smoke.FISCHL_CHARACTER_ID,
                "10000123",
                "10000020",
            },
        )

    def test_moonsign_preset_has_all_moonsign_team_and_trigger_team(self) -> None:
        state = smoke.build_team_preset_state("moonsign")
        team0_traits = [
            _slot_traits(state, 0, index)
            for index in range(4)
        ]
        team1_ids = [str(state.team(1).slot(index).character.id) for index in range(4)]

        self.assertTrue(all("moonsign" in traits for traits in team0_traits))
        self.assertEqual(
            team1_ids,
            [
                smoke.LAUMA_CHARACTER_ID,
                smoke.INEFFA_CHARACTER_ID,
                smoke.NAHIDA_CHARACTER_ID,
                smoke.YELAN_CHARACTER_ID,
            ],
        )
        summary = smoke.build_preset_summary(state, preset_name="moonsign")
        self.assertIn("moonsign_count=4; non_moonsign_trigger=False", summary)
        self.assertIn("moonsign_count=2; non_moonsign_trigger=True", summary)

    def test_hexerei_preset_has_one_hexerei_team_and_two_hexerei_team(self) -> None:
        state = smoke.build_team_preset_state("hexerei")
        team0_counts = sum(
            "hexerei" in _slot_traits(state, 0, index)
            for index in range(4)
            if state.team(0).slot(index).character is not None
        )
        team1_counts = sum(
            "hexerei" in _slot_traits(state, 1, index)
            for index in range(4)
            if state.team(1).slot(index).character is not None
        )

        self.assertEqual(team0_counts, 1)
        self.assertGreaterEqual(team1_counts, 2)

    def test_resonance_sanity_preset_builds_geo_and_dendro_checks(self) -> None:
        state = smoke.build_team_preset_state("resonance-sanity")
        team0_elements = [
            state.team(0).slot(index).character.element
            for index in range(4)
            if state.team(0).slot(index).character is not None
        ]
        team1_elements = [
            state.team(1).slot(index).character.element
            for index in range(4)
            if state.team(1).slot(index).character is not None
        ]

        self.assertGreaterEqual(team0_elements.count("Geo"), 2)
        self.assertGreaterEqual(team1_elements.count("Dendro"), 2)
        self.assertIn("Electro", team1_elements)


def _slot_traits(state, team_index: int, slot_index: int) -> set[str]:
    details = state.team(team_index).slot(slot_index).character_details_data or {}
    account_character = details.get("account_character") or {}
    return set(account_character.get("traits") or ())


if __name__ == "__main__":
    unittest.main()
