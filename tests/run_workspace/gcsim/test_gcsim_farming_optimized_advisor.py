from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Event
import tempfile
import unittest

import run_workspace.gcsim as gcsim_api
from run_workspace.gcsim.farming_auto_advisor import (
    GcsimAutomaticAdvisorRequest,
    GcsimAutomaticAdvisorResult,
    GcsimAutomaticAdvisorSession,
    GcsimAutomaticAdvisorStatus,
)
from run_workspace.gcsim.farming_evaluator import GcsimFarmingSchedulerBudget
from run_workspace.gcsim.farming_finalist_optimizer import (
    GcsimFinalistOptimizerBudget,
    GcsimFinalistOptimizerRequest,
    GcsimFinalistOptimizerSession,
)
from run_workspace.gcsim.farming_optimized_advisor import (
    GcsimOptimizedAdvisorRequest,
    GcsimOptimizedAdvisorSession,
    GcsimOptimizedAdvisorStatus,
)
from run_workspace.gcsim.farming_response import ResponseProfileSelectionBudget
from run_workspace.gcsim.farming_layout_scan import (
    GcsimMainLayoutScanResult,
    GcsimMainLayoutScanStatus,
)

from tests.run_workspace.gcsim.test_gcsim_farming_controller import (
    _request as _search_request,
)
from tests.run_workspace.gcsim.test_gcsim_farming_finalist_optimizer import (
    EvidenceSessionFactory,
)
from tests.run_workspace.gcsim.test_gcsim_farming_layout_scan import (
    LayoutSchedulerFactory,
    _request as _layout_request,
)


class GcsimOptimizedAdvisorTest(unittest.TestCase):
    def test_public_package_facade_exports_optimized_advisor_stack(self) -> None:
        expected = {
            "GcsimFinalistOptimizerBudget",
            "GcsimFinalistOptimizerRequest",
            "GcsimFinalistOptimizerSession",
            "GcsimOptimizedAdvisorRequest",
            "GcsimOptimizedAdvisorSession",
            "freeze_gcsim_optimizer_environment",
            "run_gcsim_optimized_four_piece_advisor",
        }

        self.assertTrue(expected.issubset(set(gcsim_api.__all__)))
        self.assertEqual(len(gcsim_api.__all__), len(set(gcsim_api.__all__)))
        self.assertTrue(all(hasattr(gcsim_api, name) for name in expected))

    def test_automatic_screen_flows_into_real_optimizer_finalist_race(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = _request(root)
            scheduler_factory = LayoutSchedulerFactory()
            optimizer_factory = EvidenceSessionFactory(root / "optimizer-runs")

            result = GcsimOptimizedAdvisorSession(
                request,
                automatic_session_factory=lambda value: GcsimAutomaticAdvisorSession(
                    value,
                    enable_cache=False,
                    scheduler_factory=scheduler_factory,
                ),
                finalist_session_factory=lambda value: GcsimFinalistOptimizerSession(
                    value,
                    session_factory=optimizer_factory,
                ),
            ).run()

            self.assertEqual(result.status, GcsimOptimizedAdvisorStatus.BEST_FOUND)
            self.assertIsNotNone(result.automatic)
            self.assertIsNotNone(result.finalist)
            self.assertIsNotNone(result.best_found)
            self.assertEqual(result.best_found.iterations, 200)
            self.assertGreater(len(optimizer_factory.requests), 0)
            self.assertTrue(
                all(
                    "iteration=200 workers=1" in str(item.config_text)
                    for item in optimizer_factory.requests
                )
            )
            expected = result.automatic.advisor.search.physical_finalists[:2]
            self.assertEqual(result.finalist.request_snapshot.finalists, expected)

    def test_pre_cancel_is_typed_and_does_not_run_screen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stage = NeverRunStage()
            factory_calls = []

            def factory(_request):
                factory_calls.append(True)
                return stage

            session = GcsimOptimizedAdvisorSession(
                _request(Path(tmp)),
                automatic_session_factory=factory,
            )
            session.cancel()

            result = session.run()

            self.assertEqual(result.status, GcsimOptimizedAdvisorStatus.CANCELLED)
            self.assertEqual(result.stop_reason, "cancelled_before_screening")
            self.assertEqual(factory_calls, [])
            self.assertFalse(stage.cancelled)
            self.assertFalse(stage.run_called)

    def test_factory_time_counts_toward_outer_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            stage = NeverRunStage()

            def factory(_request):
                clock.value = 5
                return stage

            request = replace(_request(Path(tmp)), overall_deadline_seconds=1)
            result = GcsimOptimizedAdvisorSession(
                request,
                automatic_session_factory=factory,
                clock=clock,
            ).run()

            self.assertEqual(result.status, GcsimOptimizedAdvisorStatus.DEADLINE)
            self.assertEqual(result.stop_reason, "deadline_before_screening")
            self.assertTrue(stage.cancelled)
            self.assertFalse(stage.run_called)

    def test_best_found_wrapper_rejects_missing_finalist_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = GcsimOptimizedAdvisorSession(
                _request(root),
                automatic_session_factory=lambda value: GcsimAutomaticAdvisorSession(
                    value,
                    enable_cache=False,
                    scheduler_factory=LayoutSchedulerFactory(),
                ),
                finalist_session_factory=lambda value: GcsimFinalistOptimizerSession(
                    value,
                    session_factory=EvidenceSessionFactory(root / "runs"),
                ),
            ).run()

            with self.assertRaisesRegex(Exception, "successful optimized finalist"):
                replace(result, finalist=None)

    def test_incoherent_typed_finalist_becomes_failed_instead_of_escaping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def mismatched_factory(value: GcsimFinalistOptimizerRequest):
                mismatched = replace(value, optimizer_options={"fine_tune": 1})
                evidence = GcsimFinalistOptimizerSession(
                    mismatched,
                    session_factory=EvidenceSessionFactory(root / "mismatch-runs"),
                ).run()
                return ReturningStage(evidence)

            result = GcsimOptimizedAdvisorSession(
                _request(root),
                automatic_session_factory=lambda value: GcsimAutomaticAdvisorSession(
                    value,
                    enable_cache=False,
                    scheduler_factory=LayoutSchedulerFactory(),
                ),
                finalist_session_factory=mismatched_factory,
            ).run()

            self.assertEqual(result.status, GcsimOptimizedAdvisorStatus.FAILED)
            self.assertEqual(result.stop_reason, "orchestration_failed")
            self.assertIn("derive exactly", result.error)
            self.assertIsNone(result.automatic)
            self.assertIsNone(result.finalist)

    def test_outer_deadline_watchdog_cancels_a_blocking_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = _request(root)
            evidence = GcsimAutomaticAdvisorSession(
                request.automatic_request,
                enable_cache=False,
                scheduler_factory=LayoutSchedulerFactory(),
            ).run()
            bounded = replace(request, overall_deadline_seconds=0.1)
            evidence = replace(
                evidence,
                request_snapshot=replace(
                    evidence.request_snapshot,
                    overall_deadline_seconds=0.1,
                ),
            )
            stage = BlockingReturningStage(evidence)

            result = GcsimOptimizedAdvisorSession(
                bounded,
                automatic_session_factory=lambda _request: stage,
            ).run()

            self.assertEqual(result.status, GcsimOptimizedAdvisorStatus.DEADLINE)
            self.assertEqual(result.stop_reason, "screening_deadline")
            self.assertTrue(stage.cancelled.is_set())
            self.assertLess(result.elapsed_seconds, 1.0)

    def test_deadline_result_rejects_arbitrary_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session = GcsimOptimizedAdvisorSession(_request(Path(tmp)))
            session.cancel()
            cancelled = session.run()

            with self.assertRaisesRegex(Exception, "coherent boundary"):
                replace(
                    cancelled,
                    status=GcsimOptimizedAdvisorStatus.DEADLINE,
                    stop_reason="unrelated_reason",
                )

    def test_failed_screen_returned_at_deadline_stays_a_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            request = replace(_request(Path(tmp)), overall_deadline_seconds=1.0)
            failed_screen = GcsimAutomaticAdvisorResult(
                status=GcsimAutomaticAdvisorStatus.LAYOUT_FAILED,
                stop_reason="layout_scan:incomplete",
                elapsed_seconds=0.0,
                layout_scan=GcsimMainLayoutScanResult(
                    status=GcsimMainLayoutScanStatus.INCOMPLETE_COORDINATES,
                    stop_reason="incomplete",
                    elapsed_seconds=0.0,
                    coordinate_candidate_count=0,
                    combination_candidate_count=0,
                    coordinate_request_count=0,
                    combination_request_count=0,
                ),
                request_snapshot=replace(
                    request.automatic_request,
                    overall_deadline_seconds=1.0,
                ),
            )
            stage = ClockAdvancingReturningStage(failed_screen, clock, 2.0)

            result = GcsimOptimizedAdvisorSession(
                request,
                automatic_session_factory=lambda _request: stage,
                clock=clock,
            ).run()

            self.assertEqual(result.status, GcsimOptimizedAdvisorStatus.DEADLINE)
            self.assertEqual(result.stop_reason, "screening_deadline")

    def test_watchdog_exception_is_reported_as_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stage = RaisingOnCancelStage()
            request = replace(
                _request(Path(tmp)),
                overall_deadline_seconds=0.1,
            )

            result = GcsimOptimizedAdvisorSession(
                request,
                automatic_session_factory=lambda _request: stage,
            ).run()

            self.assertEqual(result.status, GcsimOptimizedAdvisorStatus.DEADLINE)
            self.assertEqual(
                result.stop_reason,
                "deadline_during_screening_without_evidence",
            )
            self.assertTrue(stage.cancelled.is_set())

    def test_stale_automatic_request_evidence_fails_before_finalist_factory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = _request(root)
            stale_request = replace(
                request.automatic_request,
                response_candidate_timeout_seconds=(
                    request.automatic_request.response_candidate_timeout_seconds + 1
                ),
            )
            stale = GcsimAutomaticAdvisorSession(
                stale_request,
                enable_cache=False,
                scheduler_factory=LayoutSchedulerFactory(),
            ).run()
            finalist_factory_calls = []

            result = GcsimOptimizedAdvisorSession(
                request,
                automatic_session_factory=lambda _request: ReturningStage(stale),
                finalist_session_factory=lambda value: finalist_factory_calls.append(
                    value
                ),
            ).run()

            self.assertEqual(result.status, GcsimOptimizedAdvisorStatus.FAILED)
            self.assertIn("automatic evidence", result.error)
            self.assertEqual(finalist_factory_calls, [])


class NeverRunStage:
    def __init__(self) -> None:
        self.cancelled = False
        self.run_called = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self):
        self.run_called = True
        raise AssertionError("stage must not run")


class ReturningStage:
    def __init__(self, result) -> None:
        self.result = result
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self):
        return self.result


class BlockingReturningStage:
    def __init__(self, result) -> None:
        self.result = result
        self.cancelled = Event()

    def cancel(self) -> None:
        self.cancelled.set()

    def run(self):
        if not self.cancelled.wait(timeout=2):
            raise AssertionError("outer deadline watchdog did not cancel the stage")
        return self.result


class ClockAdvancingReturningStage(ReturningStage):
    def __init__(self, result, clock, final_time: float) -> None:
        super().__init__(result)
        self.clock = clock
        self.final_time = final_time

    def run(self):
        self.clock.value = self.final_time
        return self.result


class RaisingOnCancelStage:
    def __init__(self) -> None:
        self.cancelled = Event()

    def cancel(self) -> None:
        self.cancelled.set()

    def run(self):
        if not self.cancelled.wait(timeout=2):
            raise AssertionError("outer deadline watchdog did not cancel the stage")
        raise RuntimeError("stage interrupted by watchdog")


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _request(root: Path) -> GcsimOptimizedAdvisorRequest:
    search = _search_request(root)
    automatic = GcsimAutomaticAdvisorRequest(
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
    finalist = GcsimFinalistOptimizerBudget(
        max_finalists=2,
        top_n=1,
        worker_count=1,
        validation_iterations=200,
        overall_deadline_seconds=30.0,
        optimizer_timeout_seconds=10.0,
        simulation_timeout_seconds=10.0,
    )
    return GcsimOptimizedAdvisorRequest(
        automatic_request=automatic,
        finalist_budget=finalist,
        overall_deadline_seconds=60.0,
        optimizer_options={"fine_tune": 0},
    )


if __name__ == "__main__":
    unittest.main()
