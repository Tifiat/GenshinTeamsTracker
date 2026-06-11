from __future__ import annotations

import unittest
from dataclasses import replace

from run_workspace.pvp.deck import (
    DeckLoadError,
    DraftCharacter,
    DraftDeck,
    DraftWeaponStack,
    draft_deck_to_json_text,
    load_draft_deck_from_json_text,
)
from run_workspace.pvp.validation import (
    ISSUE_DUPLICATE_CHARACTER_ID,
    ISSUE_DUPLICATE_WEAPON_STACK_KEY,
    ISSUE_INVALID_WEAPON_COUNT,
    ISSUE_MISSING_CHARACTER_DISPLAY_NAME,
    ISSUE_MISSING_CHARACTER_ID,
    ISSUE_MISSING_WEAPON_DISPLAY_NAME,
    ISSUE_MISSING_WEAPON_ID,
    ISSUE_NOT_ENOUGH_CHARACTERS_FREE_DRAFT,
    ISSUE_UNSUPPORTED_TRAVELER_CHARACTER,
    validate_draft_deck,
)

from ._fixtures import load_sample_decks, synthetic_deck


class DraftDeckTests(unittest.TestCase):
    def test_minimal_valid_deck_loads_and_roundtrips(self) -> None:
        deck = synthetic_deck("p1")
        loaded = load_draft_deck_from_json_text(draft_deck_to_json_text(deck))

        self.assertEqual(loaded.to_dict(), deck.to_dict())
        self.assertTrue(validate_draft_deck(loaded).ready)

    def test_sample_decks_are_valid(self) -> None:
        player_1_deck, player_2_deck = load_sample_decks()

        self.assertTrue(validate_draft_deck(player_1_deck).ready)
        self.assertTrue(validate_draft_deck(player_2_deck).ready)
        self.assertTrue(player_1_deck.source.to_dict()["test_fixture"])

    def test_malformed_json_and_invalid_root_contract_are_clear_errors(self) -> None:
        with self.assertRaises(DeckLoadError):
            load_draft_deck_from_json_text("{")
        with self.assertRaises(DeckLoadError):
            load_draft_deck_from_json_text("[]")
        with self.assertRaises(DeckLoadError):
            load_draft_deck_from_json_text(
                '{"schema_version": 2, "kind": "gtt.pvp_deck"}'
            )
        with self.assertRaises(DeckLoadError):
            load_draft_deck_from_json_text(
                '{"schema_version": 1, "kind": "wrong.kind"}'
            )

    def test_validation_reports_missing_duplicate_and_bad_count_codes(self) -> None:
        base = synthetic_deck("p1")
        invalid = replace(
            base,
            characters=(
                DraftCharacter("", "", "PYRO", "SWORD", 5, 90, 0),
                DraftCharacter("duplicate", "A", "PYRO", "SWORD", 5, 90, 0),
                DraftCharacter("duplicate", "B", "PYRO", "SWORD", 5, 90, 0),
            ),
            weapons=(
                DraftWeaponStack("", "", "SWORD", 4, 90, 5, 0),
                DraftWeaponStack("weapon-a", "A", "SWORD", 4, 90, 5, 1),
                DraftWeaponStack("weapon-a", "A", "SWORD", 4, 90, 5, 1),
            ),
        )

        codes = set(validate_draft_deck(invalid).issue_codes())

        self.assertIn(ISSUE_MISSING_CHARACTER_ID, codes)
        self.assertIn(ISSUE_MISSING_CHARACTER_DISPLAY_NAME, codes)
        self.assertIn(ISSUE_DUPLICATE_CHARACTER_ID, codes)
        self.assertIn(ISSUE_MISSING_WEAPON_ID, codes)
        self.assertIn(ISSUE_MISSING_WEAPON_DISPLAY_NAME, codes)
        self.assertIn(ISSUE_INVALID_WEAPON_COUNT, codes)
        self.assertIn(ISSUE_DUPLICATE_WEAPON_STACK_KEY, codes)

    def test_free_draft_too_few_characters_fails_validation(self) -> None:
        too_small = synthetic_deck("p1", character_count=8)

        report = validate_draft_deck(too_small)

        self.assertFalse(report.ready)
        self.assertIn(ISSUE_NOT_ENOUGH_CHARACTERS_FREE_DRAFT, report.issue_codes())

    def test_unsupported_traveler_is_rejected_conservatively(self) -> None:
        deck = replace(
            synthetic_deck("p1"),
            characters=(
                DraftCharacter(
                    "10000007",
                    "Traveler",
                    "ANEMO",
                    "SWORD",
                    5,
                    90,
                    6,
                ),
            )
            + synthetic_deck("p1").characters[1:],
        )

        report = validate_draft_deck(deck)

        self.assertFalse(report.ready)
        self.assertIn(ISSUE_UNSUPPORTED_TRAVELER_CHARACTER, report.issue_codes())


if __name__ == "__main__":
    unittest.main()
