from __future__ import annotations

from pathlib import Path
from dataclasses import replace
import tempfile
import unittest
from unittest.mock import patch

import run_workspace.gcsim.farming_response_scan as response_scan_module
from run_workspace.gcsim.farming_evaluator import GcsimFarmingSchedulerBudget
from run_workspace.gcsim.farming_pipeline import GcsimFarmingScreeningFidelity
from run_workspace.gcsim.farming_profile_config import (
    build_default_gcsim_screening_profile_bank,
)
from run_workspace.gcsim.farming_response import ResponseProfileSelectionBudget
from run_workspace.gcsim.farming_response_scan import (
    GcsimResponseScanRequest,
    GcsimResponseScanSession,
    GcsimResponseScanStatus,
)
from run_workspace.gcsim.optimizer_config import GcsimFiveStarMainStatLayout

from tests.run_workspace.gcsim.test_gcsim_farming_controller import (
    PREPARED_CONFIG,
    SuccessfulSchedulerFactory,
    _candidate,
    _context,
)


class GcsimResponseScanTest(unittest.TestCase):
    def test_complete_scan_deduplicates_joint_baseline_and_selects_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory = SuccessfulSchedulerFactory()
            request = _request(Path(tmp), max_profiles=2)

            result = GcsimResponseScanSession(
                request,
                enable_cache=False,
                scheduler_factory=factory,
            ).run()

            profile_count = len(request.profile_bank.profiles)
            self.assertEqual(result.status, GcsimResponseScanStatus.COMPLETED)
            self.assertTrue(result.completed)
            self.assertEqual(result.planned_candidate_count, 2 * profile_count)
            self.assertEqual(result.materialized_request_count, 2 * profile_count - 1)
            self.assertEqual(len(factory.calls), 1)
            self.assertEqual(len(factory.calls[0]), 2 * profile_count - 1)
            self.assertEqual(len(result.outcomes), 2 * profile_count)
            self.assertEqual(
                result.selection.selection_for("furina").profile_ids,
                ("baseline",),
            )
            self.assertEqual(
                result.selection.selection_for("bennett").profile_ids,
                ("baseline",),
            )
            self.assertEqual(
                result.selection.comparison_context_sha256,
                result.comparison_context_sha256,
            )
            with self.assertRaisesRegex(ValueError, "batch, full outcomes"):
                replace(result, batch=None)
            with self.assertRaisesRegex(ValueError, "canonical selection order"):
                replace(result, outcomes=tuple(reversed(result.outcomes)))

    def test_missing_baseline_precision_fails_closed_when_cap_is_too_small(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory = SuccessfulSchedulerFactory(fail_first_request=True)

            result = GcsimResponseScanSession(
                _request(Path(tmp), max_profiles=2),
                enable_cache=False,
                scheduler_factory=factory,
            ).run()

            self.assertEqual(result.status, GcsimResponseScanStatus.SELECTION_FAILED)
            self.assertIsNone(result.selection)
            self.assertIn("required response profiles exceed", result.error)
            self.assertTrue(result.outcomes)

    def test_pre_cancel_is_typed_and_starts_no_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory = SuccessfulSchedulerFactory()
            session = GcsimResponseScanSession(
                _request(Path(tmp), max_profiles=2),
                enable_cache=False,
                scheduler_factory=factory,
            )
            session.cancel()

            result = session.run()

            self.assertEqual(result.status, GcsimResponseScanStatus.CANCELLED)
            self.assertEqual(factory.calls, [])
            self.assertEqual(result.materialized_request_count, 0)

    def test_cancel_during_pure_selection_is_not_reported_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory = SuccessfulSchedulerFactory()
            session = GcsimResponseScanSession(
                _request(Path(tmp), max_profiles=2),
                enable_cache=False,
                scheduler_factory=factory,
            )
            real_selector = response_scan_module.select_wearer_response_profiles

            def cancelling_selector(*args, **kwargs):
                session.cancel()
                return real_selector(*args, **kwargs)

            with patch.object(
                response_scan_module,
                "select_wearer_response_profiles",
                side_effect=cancelling_selector,
            ):
                result = session.run()

            self.assertEqual(result.status, GcsimResponseScanStatus.CANCELLED)
            self.assertIsNone(result.selection)
            self.assertEqual(result.stop_reason, "cancelled_during_response_selection")

    def test_scheduler_factory_time_counts_toward_absolute_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = MutableClock()
            base_factory = SuccessfulSchedulerFactory()

            def slow_factory(requests, budget):
                scheduler = base_factory(requests, budget)
                clock.value += 20.0
                return scheduler

            result = GcsimResponseScanSession(
                _request(Path(tmp), max_profiles=2),
                enable_cache=False,
                scheduler_factory=slow_factory,
                clock=clock,
            ).run()

            self.assertEqual(result.status, GcsimResponseScanStatus.DEADLINE_REACHED)
            self.assertEqual(result.stop_reason, "deadline_after_scheduler_factory")
            self.assertIsNone(result.batch)


class MutableClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _request(root: Path, *, max_profiles: int) -> GcsimResponseScanRequest:
    bank = build_default_gcsim_screening_profile_bank()
    return GcsimResponseScanRequest(
        engine_context=_context(root),
        prepared_config_text=PREPARED_CONFIG,
        wearer_ids=("furina", "bennett"),
        layout_catalog={
            "furina": {
                "default": GcsimFiveStarMainStatLayout(
                    sands="hp%",
                    goblet="hydro%",
                    circlet="cr",
                )
            },
            "bennett": {
                "default": GcsimFiveStarMainStatLayout(
                    sands="er",
                    goblet="pyro%",
                    circlet="cr",
                )
            },
        },
        profile_bank=bank,
        baseline_states=(
            _candidate("furina", "goldentroupe"),
            _candidate("bennett", "noblesseoblige"),
        ),
        fidelity=GcsimFarmingScreeningFidelity(iterations=10, worker_count=1),
        scheduler_budget=GcsimFarmingSchedulerBudget(2, 2, 10.0),
        selection_budget=ResponseProfileSelectionBudget(
            max_profiles_per_wearer=max_profiles,
            top_profiles_per_wearer=1,
            confidence_sigma=0.0,
            relative_uncertainty_margin=0.0,
            practical_materiality_relative=0.005,
        ),
        candidate_timeout_seconds=2.0,
    )


if __name__ == "__main__":
    unittest.main()
