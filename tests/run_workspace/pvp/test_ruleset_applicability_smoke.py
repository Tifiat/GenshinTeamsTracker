"""Tests for the temporary PvP ruleset applicability smoke command."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from run_workspace.pvp.ruleset_applicability_smoke import (
    main,
    run_default_ruleset_applicability_smoke,
)


class RulesetApplicabilitySmokeTests(unittest.TestCase):
    def test_smoke_report_succeeds_with_expected_statuses(self) -> None:
        report = run_default_ruleset_applicability_smoke()

        self.assertTrue(report.gtt_ruleset.ready_for_cost_preview)
        self.assertFalse(report.gtt_ruleset.ready_for_schedule_execution)
        self.assertFalse(report.gentor_like_ruleset.ready_for_schedule_execution)
        self.assertEqual(report.gtt_deck_cost.total_cost, 146)

    def test_cli_entrypoint_prints_compact_report(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = main([])

        text = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("PvP ruleset applicability smoke", text)
        self.assertIn("GTT deck cost:", text)
        self.assertIn("Schedule derivation: unsupported", text)


if __name__ == "__main__":
    unittest.main()
