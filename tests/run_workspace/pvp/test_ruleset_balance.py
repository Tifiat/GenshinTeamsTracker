from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path

from hoyolab_export.tournament_ruleset import load_tournament_ruleset_json
from run_workspace.pvp.full_loop_smoke import run_default_full_loop_smoke
from run_workspace.pvp.ruleset_balance import (
    ISSUE_RULESET_BALANCE_MAPPING_FALLBACK,
    ISSUE_RULESET_BALANCE_OVERRIDE_REQUIRES_ASSIGNMENTS,
    ISSUE_RULESET_BALANCE_POINT_LIMIT_REPORT_ONLY,
    ISSUE_RULESET_BALANCE_SCHEDULE_REQUIRES_ADAPTER,
    ISSUE_RULESET_BALANCE_SCRIPT_UNSUPPORTED,
    ISSUE_RULESET_BALANCE_TIER_RESTRICTIONS_NOT_ENFORCED,
    ISSUE_RULESET_BALANCE_UNMATCHED_ENTRY,
    REPORT_STATUS_NOT_READY,
    REPORT_STATUS_PARTIAL,
    apply_ruleset_balance_to_deck,
    attach_ruleset_balance_summary_to_bundle,
)
from run_workspace.pvp.ruleset_balance_smoke import main, run_ruleset_balance_smoke
from run_workspace.pvp.ruleset_costs import (
    ISSUE_CHARACTER_COST_UNKNOWN,
    ISSUE_WEAPON_COST_UNKNOWN,
)
from run_workspace.pvp.session_bundle import (
    build_session_bundle_from_full_loop_report,
    load_session_bundle_from_json_text,
    session_bundle_to_json_text,
    verify_session_bundle,
)
from run_workspace.pvp.schedule import SEAT_PLAYER_1

from ._fixtures import load_sample_decks


REPO_ROOT = Path(__file__).resolve().parents[3]
RULESET_SAMPLE_DIR = REPO_ROOT / "samples" / "pvp" / "rulesets"


class RulesetBalanceApplicationTests(unittest.TestCase):
    def test_report_contract_roundtrips_to_json_dict(self) -> None:
        deck, _ = load_sample_decks()
        ruleset = _minimal_ruleset()

        report = apply_ruleset_balance_to_deck(deck, ruleset, seat=SEAT_PLAYER_1)
        payload = json.loads(json.dumps(report.to_dict()))

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["ruleset_summary"]["ruleset_name"], ruleset.name)
        self.assertEqual(payload["deck_summary"]["seat"], SEAT_PLAYER_1)
        self.assertEqual(payload["cost_summary"]["total_cost"], 146)
        self.assertEqual(payload["status"], REPORT_STATUS_PARTIAL)

    def test_character_c6_and_level_extra_costs_are_applied(self) -> None:
        deck, _ = load_sample_decks()
        deck = replace(
            deck,
            characters=(
                replace(deck.characters[0], constellation=6, level=95),
            ),
            weapons=(),
        )
        ruleset = _minimal_ruleset()

        report = apply_ruleset_balance_to_deck(deck, ruleset)

        row = report.character_rows[0]
        self.assertEqual(row.base_cost, 16)
        self.assertEqual(row.level_extra_cost, 2)
        self.assertEqual(row.total_cost, 18)
        self.assertEqual(report.cost_summary.character_cost_total, 18)

    def test_unknown_character_reports_unmatched_and_cost_issue(self) -> None:
        deck, _ = load_sample_decks()
        deck = replace(
            deck,
            characters=(
                replace(
                    deck.characters[0],
                    character_id="missing_character",
                    display_name="Missing Character",
                ),
            ),
            weapons=(),
        )

        report = apply_ruleset_balance_to_deck(deck, _minimal_ruleset())

        self.assertEqual(report.status, REPORT_STATUS_NOT_READY)
        self.assertEqual(report.matching_summary.character_unmatched, 1)
        self.assertIn(ISSUE_RULESET_BALANCE_UNMATCHED_ENTRY, report.issue_codes())
        self.assertIn(ISSUE_CHARACTER_COST_UNKNOWN, report.character_rows[0].issue_codes)

    def test_display_name_fallback_is_reported_as_mapping_gap(self) -> None:
        deck, _ = load_sample_decks()
        ruleset = load_tournament_ruleset_json(
            RULESET_SAMPLE_DIR / "gentor_like_sanitized_ruleset.json"
        )

        report = apply_ruleset_balance_to_deck(deck, ruleset)

        self.assertGreater(report.matching_summary.character_fallback_name_matches, 0)
        self.assertGreater(report.matching_summary.weapon_fallback_name_matches, 0)
        self.assertIn(ISSUE_RULESET_BALANCE_MAPPING_FALLBACK, report.issue_codes())
        self.assertEqual(report.status, REPORT_STATUS_NOT_READY)

    def test_weapon_refinement_and_stack_count_total_are_applied(self) -> None:
        deck, _ = load_sample_decks()
        ruleset = _minimal_ruleset()

        report = apply_ruleset_balance_to_deck(deck, ruleset)

        row = report.weapon_rows[0]
        self.assertEqual(row.refinement, 5)
        self.assertEqual(row.count, 2)
        self.assertEqual(row.base_cost, 5)
        self.assertEqual(row.total_cost, 10)
        self.assertEqual(report.cost_summary.weapon_cost_total, 50)

    def test_character_specific_weapon_override_applies_with_assignment_context(self) -> None:
        deck, _ = load_sample_decks()
        ruleset = _minimal_ruleset()

        report = apply_ruleset_balance_to_deck(
            deck,
            ruleset,
            weapon_assignment={"test_p1_char_01": deck.weapons[0].stack_key},
        )

        self.assertEqual(report.deck_summary["weapon_cost_mode"], "assigned")
        self.assertEqual(report.cost_summary.weapon_cost_total, 9)
        self.assertEqual(report.weapon_rows[0].base_cost, 5)
        self.assertEqual(report.weapon_rows[0].override_cost, 9)
        self.assertNotIn(
            ISSUE_RULESET_BALANCE_OVERRIDE_REQUIRES_ASSIGNMENTS,
            report.issue_codes(),
        )

    def test_no_assignment_context_reports_base_only_override_gap(self) -> None:
        deck, _ = load_sample_decks()

        report = apply_ruleset_balance_to_deck(deck, _minimal_ruleset())

        self.assertIn(
            ISSUE_RULESET_BALANCE_OVERRIDE_REQUIRES_ASSIGNMENTS,
            report.issue_codes(),
        )
        self.assertIsNone(report.weapon_rows[0].override_cost)

    def test_unknown_weapon_reports_unmatched_and_cost_issue(self) -> None:
        deck, _ = load_sample_decks()
        deck = replace(
            deck,
            weapons=(
                replace(
                    deck.weapons[0],
                    weapon_id="missing_weapon",
                    display_name="Missing Weapon",
                ),
            ),
        )

        report = apply_ruleset_balance_to_deck(deck, _minimal_ruleset())

        self.assertEqual(report.status, REPORT_STATUS_NOT_READY)
        self.assertEqual(report.matching_summary.weapon_unmatched, 1)
        self.assertIn(ISSUE_WEAPON_COST_UNKNOWN, report.weapon_rows[0].issue_codes)

    def test_restrictions_report_script_tiers_and_schedule_as_not_executable(self) -> None:
        deck, _ = load_sample_decks()
        ruleset = load_tournament_ruleset_json(
            RULESET_SAMPLE_DIR / "gentor_like_sanitized_ruleset.json"
        )

        report = apply_ruleset_balance_to_deck(deck, ruleset)

        self.assertIn(
            ISSUE_RULESET_BALANCE_TIER_RESTRICTIONS_NOT_ENFORCED,
            report.issue_codes(),
        )
        self.assertIn(ISSUE_RULESET_BALANCE_SCRIPT_UNSUPPORTED, report.issue_codes())
        self.assertIn(
            ISSUE_RULESET_BALANCE_SCHEDULE_REQUIRES_ADAPTER,
            report.issue_codes(),
        )

    def test_point_limit_is_report_only_not_deck_validation(self) -> None:
        deck, _ = load_sample_decks()

        report = apply_ruleset_balance_to_deck(deck, _minimal_ruleset())

        self.assertIn(ISSUE_RULESET_BALANCE_POINT_LIMIT_REPORT_ONLY, report.issue_codes())
        self.assertTrue(report.cost_summary.costs_ready)

    def test_session_bundle_balance_summary_roundtrips_without_breaking_verifier(self) -> None:
        bundle = build_session_bundle_from_full_loop_report(run_default_full_loop_smoke())

        enriched = attach_ruleset_balance_summary_to_bundle(
            bundle,
            _minimal_ruleset(),
            seats=(SEAT_PLAYER_1,),
        )
        roundtripped = load_session_bundle_from_json_text(
            session_bundle_to_json_text(enriched)
        )

        self.assertIn("ruleset_balance", roundtripped.reports)
        self.assertTrue(verify_session_bundle(roundtripped).ready)
        self.assertEqual(
            roundtripped.reports["ruleset_balance"]["seats"][SEAT_PLAYER_1]["total_cost"],
            140,
        )

    def test_smoke_helper_is_structured(self) -> None:
        report = run_ruleset_balance_smoke()

        self.assertTrue(report.ready)
        self.assertEqual(report.source_mode, "synthetic")
        self.assertEqual(report.deck_report.cost_summary.total_cost, 146)

    def test_smoke_json_main_output_parses(self) -> None:
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = main(["--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["deck_report"]["cost_summary"]["total_cost"], 146)

    def test_smoke_main_keeps_not_ready_as_report_status(self) -> None:
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "--ruleset",
                    str(RULESET_SAMPLE_DIR / "gentor_like_sanitized_ruleset.json"),
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["deck_report"]["status"], "not_ready")


def _minimal_ruleset():
    return load_tournament_ruleset_json(
        RULESET_SAMPLE_DIR / "minimal_gtt_ruleset.json"
    )


if __name__ == "__main__":
    unittest.main()
