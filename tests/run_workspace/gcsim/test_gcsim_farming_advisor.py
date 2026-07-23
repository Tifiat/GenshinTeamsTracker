from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from run_workspace.gcsim.farming_advisor import (
    GcsimFourPieceAdvisorRequest,
    GcsimFourPieceAdvisorSession,
    GcsimFourPieceAdvisorStatus,
)

from tests.run_workspace.gcsim.test_gcsim_farming_controller import (
    SuccessfulSchedulerFactory,
    _request as _search_request,
)
from tests.run_workspace.gcsim.test_gcsim_farming_response_scan import (
    _request as _response_request,
)


class GcsimFourPieceAdvisorTest(unittest.TestCase):
    def test_advisor_runs_response_scan_before_set_and_team_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            search_template = _search_request(root)
            factory = SuccessfulSchedulerFactory()
            request = GcsimFourPieceAdvisorRequest(
                response_scan_request=_response_request(root, max_profiles=2),
                screening_scheduler_budget=(
                    search_template.screening_scheduler_budget
                ),
                team_scheduler_budget=search_template.team_scheduler_budget,
                survivor_budget=search_template.survivor_budget,
                composer_budget=search_template.composer_budget,
                overall_deadline_seconds=20.0,
                screening_candidate_timeout_seconds=2.0,
            )

            frozen_environment = dict(request.response_scan_request.environment)
            with patch.dict(os.environ, {"LANG": "changed-after-request"}):
                result = GcsimFourPieceAdvisorSession(
                    request,
                    enable_cache=False,
                    scheduler_factory=factory,
                ).run()

            self.assertEqual(result.status, GcsimFourPieceAdvisorStatus.BEST_FOUND)
            self.assertTrue(result.response_scan.completed)
            self.assertIsNotNone(result.search)
            self.assertIsNotNone(result.best_found)
            self.assertGreaterEqual(len(factory.calls), 3)
            self.assertEqual(
                result.response_scan.selection.selection_for("bennett").profile_ids,
                ("baseline",),
            )
            self.assertTrue(
                all(
                    dict(evaluator_request.environment) == frozen_environment
                    for call in factory.calls
                    for evaluator_request in call
                )
            )

    def test_pre_cancel_stops_in_response_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            search_template = _search_request(root)
            factory = SuccessfulSchedulerFactory()
            session = GcsimFourPieceAdvisorSession(
                GcsimFourPieceAdvisorRequest(
                    response_scan_request=_response_request(root, max_profiles=2),
                    screening_scheduler_budget=(
                        search_template.screening_scheduler_budget
                    ),
                    team_scheduler_budget=search_template.team_scheduler_budget,
                    survivor_budget=search_template.survivor_budget,
                    composer_budget=search_template.composer_budget,
                    overall_deadline_seconds=20.0,
                    screening_candidate_timeout_seconds=2.0,
                ),
                enable_cache=False,
                scheduler_factory=factory,
            )
            session.cancel()

            result = session.run()

            self.assertEqual(result.status, GcsimFourPieceAdvisorStatus.CANCELLED)
            self.assertIsNone(result.search)
            self.assertEqual(factory.calls, [])


if __name__ == "__main__":
    unittest.main()
