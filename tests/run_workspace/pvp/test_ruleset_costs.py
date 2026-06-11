"""Tests for temporary PvP ruleset cost-preview fixtures."""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from hoyolab_export.tournament_ruleset import (
    load_tournament_ruleset_json,
    tournament_ruleset_from_mapping,
)
from run_workspace.pvp.deck import DraftCharacter
from run_workspace.pvp.ruleset_costs import (
    ISSUE_CHARACTER_CONSTELLATION_COST_MISSING,
    ISSUE_CHARACTER_MATCHED_BY_DISPLAY_NAME_FALLBACK,
    ISSUE_CHARACTER_COST_UNKNOWN,
    ISSUE_WEAPON_MATCHED_BY_DISPLAY_NAME_FALLBACK,
    ISSUE_WEAPON_COST_UNKNOWN,
    ISSUE_WEAPON_OVERRIDE_NAME_ONLY_MAPPING,
    WEAPON_COST_MODE_ASSIGNED,
    WEAPON_COST_MODE_POOL,
    calculate_draft_deck_ruleset_cost,
)

from ._fixtures import load_sample_decks


REPO_ROOT = Path(__file__).resolve().parents[3]
RULESET_SAMPLE_DIR = REPO_ROOT / "samples" / "pvp" / "rulesets"


class RulesetCostTests(unittest.TestCase):
    def test_sample_deck_costs_by_stable_ids(self) -> None:
        deck, _ = load_sample_decks()
        ruleset = load_tournament_ruleset_json(
            RULESET_SAMPLE_DIR / "minimal_gtt_ruleset.json"
        )

        report = calculate_draft_deck_ruleset_cost(deck, ruleset)

        self.assertTrue(report.ready)
        self.assertEqual(report.weapon_cost_mode, WEAPON_COST_MODE_POOL)
        self.assertEqual(report.character_total, 96)
        self.assertEqual(report.weapon_total, 50)
        self.assertEqual(report.total_cost, 146)
        self.assertEqual(report.issue_codes(), ())

    def test_level_extra_cost_is_added_for_character_preview(self) -> None:
        deck, _ = load_sample_decks()
        leveled = replace(
            deck,
            characters=(
                replace(deck.characters[0], level=95),
            )
            + deck.characters[1:],
        )
        ruleset = load_tournament_ruleset_json(
            RULESET_SAMPLE_DIR / "minimal_gtt_ruleset.json"
        )

        report = calculate_draft_deck_ruleset_cost(leveled, ruleset)

        self.assertTrue(report.ready)
        self.assertEqual(report.character_entries[0].breakdown["level_extra_cost"], 2)
        self.assertEqual(report.total_cost, 148)

    def test_character_specific_weapon_override_beats_base_cost_when_assigned(self) -> None:
        deck, _ = load_sample_decks()
        ruleset = load_tournament_ruleset_json(
            RULESET_SAMPLE_DIR / "minimal_gtt_ruleset.json"
        )

        report = calculate_draft_deck_ruleset_cost(
            deck,
            ruleset,
            weapon_assignments_by_character_id={
                "test_p1_char_01": deck.weapons[0].stack_key,
            },
        )

        self.assertEqual(report.weapon_cost_mode, WEAPON_COST_MODE_ASSIGNED)
        self.assertEqual(report.weapon_total, 9)
        self.assertEqual(report.total_cost, 105)
        self.assertIn(
            ISSUE_WEAPON_OVERRIDE_NAME_ONLY_MAPPING,
            report.issue_codes(),
        )

    def test_gentor_like_id_gap_is_reported_when_name_fallback_matches(self) -> None:
        deck, _ = load_sample_decks()
        ruleset = load_tournament_ruleset_json(
            RULESET_SAMPLE_DIR / "gentor_like_sanitized_ruleset.json"
        )

        report = calculate_draft_deck_ruleset_cost(deck, ruleset)

        self.assertFalse(report.ready)
        self.assertIn(
            ISSUE_CHARACTER_MATCHED_BY_DISPLAY_NAME_FALLBACK,
            report.issue_codes(),
        )
        self.assertIn(
            ISSUE_WEAPON_MATCHED_BY_DISPLAY_NAME_FALLBACK,
            report.issue_codes(),
        )
        self.assertIn(ISSUE_CHARACTER_COST_UNKNOWN, report.issue_codes())
        self.assertIn(ISSUE_WEAPON_COST_UNKNOWN, report.issue_codes())

    def test_missing_constellation_cost_is_a_pricing_error(self) -> None:
        deck, _ = load_sample_decks()
        tiny_deck = replace(
            deck,
            characters=(
                DraftCharacter(
                    "test_p1_char_03",
                    "P1 Polearm 03",
                    "ANEMO",
                    "POLEARM",
                    4,
                    90,
                    6,
                ),
            ),
            weapons=(),
        )
        ruleset = tournament_ruleset_from_mapping(
            {
                "name": "Missing constellation cost",
                "characters": [
                    {
                        "character_id": "test_p1_char_03",
                        "name": "P1 Polearm 03",
                        "costs_by_constellation": {"0": 4},
                    }
                ],
            }
        )

        report = calculate_draft_deck_ruleset_cost(tiny_deck, ruleset)

        self.assertFalse(report.ready)
        self.assertIn(
            ISSUE_CHARACTER_CONSTELLATION_COST_MISSING,
            report.issue_codes(),
        )


if __name__ == "__main__":
    unittest.main()
