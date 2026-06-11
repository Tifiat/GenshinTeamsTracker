"""Tests for temporary PvP ruleset applicability fixtures and reports."""

from __future__ import annotations

import unittest
from pathlib import Path

from hoyolab_export.tournament_ruleset import (
    load_tournament_ruleset_json,
    tournament_ruleset_from_mapping,
)
from run_workspace.pvp.ruleset_applicability import (
    ISSUE_NO_CHARACTER_COSTS,
    ISSUE_SCHEDULE_DERIVATION_REQUIRES_ADAPTER,
    ISSUE_SCHEDULE_MISSING_DRAFT_CONFIG,
    ISSUE_SCHEDULE_MISSING_EXPLICIT_FLOW,
    ISSUE_TIER_RESTRICTIONS_NOT_ENFORCED,
    ISSUE_UNSUPPORTED_IMMUNE_OR_MIRROR_RULE,
    ISSUE_UNSUPPORTED_SCRIPT_RULE,
    ISSUE_UNSUPPORTED_TRAVELER_RULESET_ENTRY,
    SCHEDULE_STATUS_MISSING_DRAFT_CONFIG,
    SCHEDULE_STATUS_MISSING_EXPLICIT_FLOW,
    SCHEDULE_STATUS_REQUIRES_SCRIPT_ADAPTER,
    build_ruleset_applicability_report,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
RULESET_SAMPLE_DIR = REPO_ROOT / "samples" / "pvp" / "rulesets"


class RulesetApplicabilityTests(unittest.TestCase):
    def test_gtt_fixture_reports_cost_preview_but_no_schedule_derivation(self) -> None:
        ruleset = load_tournament_ruleset_json(
            RULESET_SAMPLE_DIR / "minimal_gtt_ruleset.json"
        )

        report = build_ruleset_applicability_report(ruleset)

        self.assertEqual(report.parser_status, "parsed_tournament_ruleset_v1")
        self.assertEqual(report.character_cost_count, 12)
        self.assertEqual(report.weapon_cost_count, 5)
        self.assertEqual(report.weapon_override_count, 1)
        self.assertTrue(report.ready_for_cost_preview)
        self.assertFalse(report.ready_for_schedule_execution)
        self.assertEqual(
            report.schedule_derivation.status,
            SCHEDULE_STATUS_MISSING_EXPLICIT_FLOW,
        )
        self.assertIn(
            ISSUE_SCHEDULE_MISSING_EXPLICIT_FLOW,
            report.issue_codes(),
        )
        self.assertIn(
            ISSUE_SCHEDULE_DERIVATION_REQUIRES_ADAPTER,
            report.issue_codes(),
        )

    def test_gentor_like_fixture_reports_script_and_tier_limitations(self) -> None:
        ruleset = load_tournament_ruleset_json(
            RULESET_SAMPLE_DIR / "gentor_like_sanitized_ruleset.json"
        )

        report = build_ruleset_applicability_report(ruleset)

        self.assertEqual(report.source, "gentor_like_sanitized_fixture")
        self.assertTrue(report.has_unsupported_script_rules)
        self.assertTrue(report.has_tier_restrictions)
        self.assertFalse(report.ready_for_schedule_execution)
        self.assertEqual(
            report.schedule_derivation.status,
            SCHEDULE_STATUS_REQUIRES_SCRIPT_ADAPTER,
        )
        self.assertIn(ISSUE_UNSUPPORTED_SCRIPT_RULE, report.issue_codes())
        self.assertIn(
            ISSUE_TIER_RESTRICTIONS_NOT_ENFORCED,
            report.issue_codes(),
        )

    def test_empty_ruleset_reports_no_costs_and_missing_draft_config(self) -> None:
        report = build_ruleset_applicability_report(
            tournament_ruleset_from_mapping({"name": "Empty"})
        )

        self.assertFalse(report.ready_for_cost_preview)
        self.assertFalse(report.ready_for_schedule_execution)
        self.assertEqual(
            report.schedule_derivation.status,
            SCHEDULE_STATUS_MISSING_DRAFT_CONFIG,
        )
        self.assertIn(ISSUE_NO_CHARACTER_COSTS, report.issue_codes())
        self.assertIn(ISSUE_SCHEDULE_MISSING_DRAFT_CONFIG, report.issue_codes())

    def test_traveler_and_reserved_immune_mirror_terms_are_reported(self) -> None:
        ruleset = tournament_ruleset_from_mapping(
            {
                "name": "Unsupported concepts",
                "notes": "Contains mirror and immune draft notes.",
                "characters": [
                    {
                        "character_id": "10000007",
                        "name": "Traveler",
                        "costs_by_constellation": {"0": 1},
                    }
                ],
            }
        )

        report = build_ruleset_applicability_report(ruleset)

        self.assertTrue(report.has_unsupported_immune_or_mirror_rules)
        self.assertTrue(report.has_unsupported_traveler_entries)
        self.assertIn(
            ISSUE_UNSUPPORTED_IMMUNE_OR_MIRROR_RULE,
            report.issue_codes(),
        )
        self.assertIn(
            ISSUE_UNSUPPORTED_TRAVELER_RULESET_ENTRY,
            report.issue_codes(),
        )


if __name__ == "__main__":
    unittest.main()
