from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import run_workspace.gcsim as gcsim_api
from run_workspace.gcsim.farming_auto_advisor import (
    GcsimAutomaticAdvisorRequest,
    GcsimAutomaticAdvisorSession,
    GcsimAutomaticAdvisorStatus,
)
from run_workspace.gcsim.farming_evaluator import GcsimFarmingSchedulerBudget
from run_workspace.gcsim.farming_response import ResponseProfileSelectionBudget

from tests.run_workspace.gcsim.test_gcsim_farming_controller import (
    _request as _search_request,
)
from tests.run_workspace.gcsim.test_gcsim_farming_layout_scan import (
    LayoutSchedulerFactory,
    _request as _layout_request,
)


class GcsimAutomaticAdvisorTest(unittest.TestCase):
    def test_public_package_facade_exports_automatic_advisor_stack(self) -> None:
        expected = {
            "GcsimAutomaticAdvisorRequest",
            "GcsimAutomaticAdvisorSession",
            "GcsimMainLayoutScanRequest",
            "GcsimResponseScanRequest",
            "GcsimFourPieceSearchRequest",
            "select_wearer_response_profiles",
        }

        self.assertTrue(expected.issubset(set(gcsim_api.__all__)))
        self.assertEqual(len(gcsim_api.__all__), len(set(gcsim_api.__all__)))
        self.assertTrue(all(hasattr(gcsim_api, name) for name in expected))

    def test_layout_response_and_set_search_run_as_one_bounded_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            search = _search_request(root)
            factory = LayoutSchedulerFactory()
            request = GcsimAutomaticAdvisorRequest(
                layout_scan_request=_layout_request(root),
                response_scheduler_budget=GcsimFarmingSchedulerBudget(2, 2, 10.0),
                response_selection_budget=ResponseProfileSelectionBudget(
                    max_profiles_per_wearer=2,
                    top_profiles_per_wearer=1,
                    confidence_sigma=0.0,
                    relative_uncertainty_margin=0.0,
                    practical_materiality_relative=0.005,
                ),
                response_candidate_timeout_seconds=2.0,
                screening_scheduler_budget=search.screening_scheduler_budget,
                team_scheduler_budget=search.team_scheduler_budget,
                survivor_budget=search.survivor_budget,
                composer_budget=search.composer_budget,
                screening_candidate_timeout_seconds=2.0,
                overall_deadline_seconds=30.0,
            )

            result = GcsimAutomaticAdvisorSession(
                request,
                enable_cache=False,
                scheduler_factory=factory,
            ).run()

            self.assertEqual(result.status, GcsimAutomaticAdvisorStatus.BEST_FOUND)
            self.assertTrue(result.layout_scan.completed)
            self.assertIsNotNone(result.advisor)
            self.assertTrue(result.advisor.response_scan.completed)
            self.assertIsNotNone(result.best_found)
            self.assertGreaterEqual(len(factory.calls), 5)
            self.assertEqual(
                result.layout_scan.selections[0].best_layout_id,
                "main/em-em-em",
            )

    def test_pre_cancel_stops_before_layout_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            search = _search_request(root)
            factory = LayoutSchedulerFactory()
            session = GcsimAutomaticAdvisorSession(
                GcsimAutomaticAdvisorRequest(
                    layout_scan_request=_layout_request(root),
                    response_scheduler_budget=GcsimFarmingSchedulerBudget(2, 2, 10.0),
                    response_selection_budget=ResponseProfileSelectionBudget(2, 1),
                    response_candidate_timeout_seconds=2.0,
                    screening_scheduler_budget=search.screening_scheduler_budget,
                    team_scheduler_budget=search.team_scheduler_budget,
                    survivor_budget=search.survivor_budget,
                    composer_budget=search.composer_budget,
                    screening_candidate_timeout_seconds=2.0,
                    overall_deadline_seconds=30.0,
                ),
                enable_cache=False,
                scheduler_factory=factory,
            )
            session.cancel()

            result = session.run()

            self.assertEqual(result.status, GcsimAutomaticAdvisorStatus.CANCELLED)
            self.assertEqual(factory.calls, [])
            self.assertIsNone(result.advisor)

    def test_best_found_result_requires_typed_successful_advisor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            search = _search_request(root)
            request = GcsimAutomaticAdvisorRequest(
                layout_scan_request=_layout_request(root),
                response_scheduler_budget=GcsimFarmingSchedulerBudget(2, 2, 10.0),
                response_selection_budget=ResponseProfileSelectionBudget(
                    max_profiles_per_wearer=2,
                    top_profiles_per_wearer=1,
                    confidence_sigma=0.0,
                    relative_uncertainty_margin=0.0,
                    practical_materiality_relative=0.005,
                ),
                response_candidate_timeout_seconds=2.0,
                screening_scheduler_budget=search.screening_scheduler_budget,
                team_scheduler_budget=search.team_scheduler_budget,
                survivor_budget=search.survivor_budget,
                composer_budget=search.composer_budget,
                screening_candidate_timeout_seconds=2.0,
                overall_deadline_seconds=30.0,
            )
            result = GcsimAutomaticAdvisorSession(
                request,
                enable_cache=False,
                scheduler_factory=LayoutSchedulerFactory(),
            ).run()

            with self.assertRaisesRegex(ValueError, "complete stage evidence"):
                replace(result, advisor=None)
            with self.assertRaisesRegex(ValueError, "advisor must"):
                replace(result, advisor=object())


if __name__ == "__main__":
    unittest.main()
