from __future__ import annotations

import unittest

from hoyolab_export.character_trait_catalog import TRAIT_STANDARD_5_STAR
from hoyolab_export.traveler import traveler_variant_id
from ui.character_browser.sorting import (
    CHARACTER_SORT_MODE_COUNTS,
    DEFAULT_CHARACTER_SORT,
    CharacterSortState,
    character_sort_key,
    is_standard_character,
)


_MISSING = object()


def _asset(
    name: str,
    *,
    rarity: int = 5,
    level: object = _MISSING,
    constellation: object = _MISSING,
    character_id: object = _MISSING,
    canonical_name: str | None = None,
    filename: str | None = None,
    character_standard: object = _MISSING,
    metadata_standard: object = _MISSING,
    character_traits: object = _MISSING,
    metadata_traits: object = _MISSING,
    element: str | None = None,
) -> dict:
    character = {"name": name, "rarity": rarity}
    if level is not _MISSING:
        character["level"] = level
    if constellation is not _MISSING:
        character["constellation"] = constellation
    if character_id is not _MISSING:
        character["id"] = character_id
    if canonical_name is not None:
        character["canonical_name"] = canonical_name
    if character_standard is not _MISSING:
        character["is_standard_5_star"] = character_standard
    if character_traits is not _MISSING:
        character["traits"] = character_traits

    metadata = {"character": character}
    if metadata_standard is not _MISSING:
        metadata["is_standard_5_star"] = metadata_standard
    if metadata_traits is not _MISSING:
        metadata["traits"] = metadata_traits
    if element is not None:
        character["element"] = element
    return {"filename": filename or f"{name}.png", "metadata": metadata}


def _names(assets: list[dict], state: CharacterSortState) -> list[str]:
    return [
        asset["metadata"]["character"]["name"]
        for asset in sorted(assets, key=lambda item: character_sort_key(item, state))
    ]


class CharacterSortingTest(unittest.TestCase):
    def test_shared_mode_counts_cover_both_sort_criteria(self) -> None:
        self.assertEqual(
            CHARACTER_SORT_MODE_COUNTS,
            {"constellation": 2, "level": 3},
        )

    def test_default_key_preserves_legacy_order_and_shape(self) -> None:
        late_five_star = _asset(
            "Zed", rarity=5, level=70, canonical_name="Alpha", character_id=1,
        )
        early_five_star = _asset(
            "Beryl", rarity=5, level=80, canonical_name="Beta", character_id=9,
        )
        four_star = _asset("Mora", rarity=4, level=90, character_id=2)

        self.assertEqual(
            character_sort_key(late_five_star),
            (-5, -70, "alpha", "Zed.png"),
        )
        self.assertEqual(
            character_sort_key(late_five_star, DEFAULT_CHARACTER_SORT),
            (-5, -70, "alpha", "Zed.png"),
        )
        self.assertEqual(
            _names([late_five_star, four_star, early_five_star], DEFAULT_CHARACTER_SORT),
            ["Beryl", "Zed", "Mora"],
        )

    def test_state_cycles_and_switches_criteria(self) -> None:
        self.assertFalse(DEFAULT_CHARACTER_SORT.active)
        constellation = DEFAULT_CHARACTER_SORT.next("constellation")
        self.assertEqual(constellation, CharacterSortState("constellation", 1))
        self.assertEqual(constellation.next("constellation").mode, 2)
        self.assertEqual(
            constellation.next("constellation").next("constellation"),
            DEFAULT_CHARACTER_SORT,
        )

        level = DEFAULT_CHARACTER_SORT.next("level")
        self.assertEqual(level, CharacterSortState("level", 1))
        self.assertEqual(level.next("level"), CharacterSortState("level", 2))
        self.assertEqual(level.next("level").next("level"), CharacterSortState("level", 3))
        self.assertEqual(
            level.next("level").next("level").next("level"),
            DEFAULT_CHARACTER_SORT,
        )
        self.assertEqual(constellation.next("level"), CharacterSortState("level", 1))

    def test_invalid_states_and_cycle_criteria_are_rejected(self) -> None:
        for criterion, mode in (
            (None, 1),
            ("unknown", 1),
            ("constellation", 0),
            ("constellation", 3),
            ("level", 0),
            ("level", 4),
            ("level", True),
            ("level", "1"),
        ):
            with self.subTest(criterion=criterion, mode=mode):
                with self.assertRaises(ValueError):
                    CharacterSortState(criterion, mode)
        with self.assertRaises(ValueError):
            DEFAULT_CHARACTER_SORT.next("unknown")

    def test_standard_classification_uses_nested_and_top_level_fallbacks(self) -> None:
        self.assertTrue(_standard_asset(character_standard=True))
        self.assertTrue(_standard_asset(metadata_standard=True))
        self.assertTrue(_standard_asset(character_traits=[TRAIT_STANDARD_5_STAR]))
        self.assertTrue(
            _standard_asset(character_traits=[], metadata_traits=[TRAIT_STANDARD_5_STAR])
        )
        self.assertFalse(_standard_asset())

    def test_all_constellation_and_level_modes_have_expected_sequences(self) -> None:
        roster = [
            _asset("A_NonstandardLow", level=10, constellation=1, character_id=100),
            _asset(
                "B_StandardHigh", level=90, constellation=6, character_id=101,
                character_traits=[TRAIT_STANDARD_5_STAR],
            ),
            _asset(
                "C_StandardC0", level=25, constellation=0, character_id=102,
                metadata_standard=True,
            ),
            _asset("D_NonstandardMissing", level=80, character_id=103),
            _asset("E_HighFour", rarity=4, level=95, constellation=1, character_id=104),
            _asset("F_FourC6", rarity=4, level=35, constellation=6, character_id=105),
            _asset(
                "H_FourMarkedStandard", rarity=4, level=70, constellation=0,
                character_id=106, character_standard=True,
            ),
            _asset("G_Three", rarity=3, level=100, constellation=2, character_id=107),
        ]

        cases = (
            (
                CharacterSortState("constellation", 1),
                ["B_StandardHigh", "A_NonstandardLow", "C_StandardC0",
                 "D_NonstandardMissing", "F_FourC6", "E_HighFour",
                 "H_FourMarkedStandard", "G_Three"],
            ),
            (
                CharacterSortState("constellation", 2),
                ["A_NonstandardLow", "D_NonstandardMissing", "B_StandardHigh",
                 "C_StandardC0", "F_FourC6", "E_HighFour",
                 "H_FourMarkedStandard", "G_Three"],
            ),
            (
                CharacterSortState("level", 1),
                ["B_StandardHigh", "D_NonstandardMissing", "C_StandardC0",
                 "A_NonstandardLow", "E_HighFour", "H_FourMarkedStandard",
                 "F_FourC6", "G_Three"],
            ),
            (
                CharacterSortState("level", 2),
                ["D_NonstandardMissing", "A_NonstandardLow", "B_StandardHigh",
                 "C_StandardC0", "E_HighFour", "H_FourMarkedStandard",
                 "F_FourC6", "G_Three"],
            ),
            (
                CharacterSortState("level", 3),
                ["G_Three", "E_HighFour", "B_StandardHigh", "D_NonstandardMissing",
                 "H_FourMarkedStandard", "F_FourC6", "C_StandardC0",
                 "A_NonstandardLow"],
            ),
        )
        for state, expected in cases:
            with self.subTest(state=state):
                self.assertEqual(_names(roster, state), expected)

    def test_invalid_constellations_and_levels_sort_after_valid_values(self) -> None:
        constellation_assets = [
            _asset("A_Missing", level=50, character_id=1),
            _asset("B_Malformed", level=50, constellation="many", character_id=2),
            _asset("C_TooHigh", level=50, constellation=7, character_id=3),
            _asset("D_Negative", level=50, constellation=-1, character_id=4),
            _asset("Z_Zero", level=50, constellation=0, character_id=5),
            _asset("M_IntegerString", level=50, constellation="3", character_id=6),
        ]
        self.assertEqual(
            _names(constellation_assets, CharacterSortState("constellation", 1)),
            ["M_IntegerString", "Z_Zero", "A_Missing", "B_Malformed", "C_TooHigh", "D_Negative"],
        )

        level_assets = [
            _asset("A_Missing", constellation=2, character_id=1),
            _asset("B_Malformed", level="high", constellation=2, character_id=2),
            _asset("C_Zero", level=0, constellation=2, character_id=3),
            _asset("D_Negative", level=-1, constellation=2, character_id=4),
            _asset("Z_Float", level=75.0, constellation=2, character_id=5),
            _asset("Y_ValidString", level="80", constellation=2, character_id=6),
            _asset("X_ValidInt", level=90, constellation=2, character_id=7),
        ]
        self.assertEqual(
            _names(level_assets, CharacterSortState("level", 1)),
            ["X_ValidInt", "Y_ValidString", "A_Missing", "B_Malformed",
             "C_Zero", "D_Negative", "Z_Float"],
        )

    def test_active_ties_keep_element_traveler_records_separate_by_character_id(self) -> None:
        variants = [
            _asset(
                "Traveler", level=90, constellation=6,
                character_id=traveler_variant_id(10000007, element),
                filename="Traveler.png", canonical_name="Traveler", element=element,
            )
            for element in ("Anemo", "Geo", "Pyro")
        ]

        ordered = sorted(
            variants,
            key=lambda asset: character_sort_key(
                asset, CharacterSortState("constellation", 1),
            ),
        )
        self.assertEqual(len(ordered), 3)
        self.assertEqual(
            [asset["metadata"]["character"]["id"] for asset in ordered],
            [-100000076, -100000072, -100000071],
        )
        self.assertEqual(
            [asset["metadata"]["character"]["element"] for asset in ordered],
            ["Pyro", "Geo", "Anemo"],
        )

    def test_active_ties_sort_string_ids_consistently_across_input_orders(self) -> None:
        records = [
            _asset(
                "Traveler", level=90, constellation=6, character_id=character_id,
                filename="Traveler.png", canonical_name="Traveler",
            )
            for character_id in ("variant-z", "10", "variant-a", "2")
        ]
        state = CharacterSortState("constellation", 1)
        expected_ids = ["2", "10", "variant-a", "variant-z"]

        for incoming in (records, list(reversed(records))):
            ordered = sorted(incoming, key=lambda asset: character_sort_key(asset, state))
            self.assertEqual(
                [asset["metadata"]["character"]["id"] for asset in ordered],
                expected_ids,
            )


def _standard_asset(**kwargs: object) -> bool:
    return is_standard_character(_asset("Standard Check", **kwargs))


if __name__ == "__main__":
    unittest.main()
