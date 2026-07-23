from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.farming_evaluator import (
    GcsimFarmingBatchResult,
    GcsimFarmingBatchStatus,
    GcsimFarmingSchedulerBudget,
)
from run_workspace.gcsim.farming_layout_scan import (
    GcsimMainLayoutScanBudget,
    GcsimMainLayoutScanRequest,
    GcsimMainLayoutScanSession,
    GcsimMainLayoutScanStatus,
    GcsimWearerLayoutSelection,
)
from run_workspace.gcsim.farming_pipeline import GcsimFarmingScreeningFidelity
from run_workspace.gcsim.farming_profile_config import (
    build_default_gcsim_screening_profile_bank,
)

from tests.run_workspace.gcsim.test_gcsim_farming_controller import (
    PREPARED_CONFIG,
    _candidate,
    _context,
    _evaluation_result,
)


class GcsimMainLayoutScanTest(unittest.TestCase):
    def test_generic_coordinate_then_cartesian_scan_finds_em_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory = LayoutSchedulerFactory()

            result = GcsimMainLayoutScanSession(
                _request(Path(tmp)),
                enable_cache=False,
                scheduler_factory=factory,
            ).run()

            self.assertEqual(result.status, GcsimMainLayoutScanStatus.COMPLETED)
            self.assertEqual(result.coordinate_candidate_count, 44)
            self.assertEqual(result.coordinate_request_count, 43)
            self.assertEqual(result.combination_candidate_count, 16)
            self.assertEqual(result.combination_request_count, 15)
            self.assertEqual(len(factory.calls), 2)
            self.assertEqual(
                tuple(selection.best_layout_id for selection in result.selections),
                ("main/em-em-em", "main/em-em-em"),
            )
            self.assertEqual(
                tuple(state.state.main_stat_layout_id for state in result.best_baseline_states),
                ("main/em-em-em", "main/em-em-em"),
            )
            self.assertEqual(
                tuple(result.layout_catalog),
                ("furina", "bennett"),
            )

    def test_incomplete_coordinate_scan_fails_before_combinations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory = LayoutSchedulerFactory(fail_first=True)

            result = GcsimMainLayoutScanSession(
                _request(Path(tmp)),
                enable_cache=False,
                scheduler_factory=factory,
            ).run()

            self.assertEqual(
                result.status,
                GcsimMainLayoutScanStatus.INCOMPLETE_COORDINATES,
            )
            self.assertEqual(len(factory.calls), 1)
            self.assertFalse(result.selections)

    def test_pre_cancel_is_typed_and_starts_no_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory = LayoutSchedulerFactory()
            session = GcsimMainLayoutScanSession(
                _request(Path(tmp)),
                enable_cache=False,
                scheduler_factory=factory,
            )
            session.cancel()

            result = session.run()

            self.assertEqual(result.status, GcsimMainLayoutScanStatus.CANCELLED)
            self.assertEqual(factory.calls, [])

    def test_completed_result_requires_exact_canonical_wearer_selections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = GcsimMainLayoutScanSession(
                _request(Path(tmp)),
                enable_cache=False,
                scheduler_factory=LayoutSchedulerFactory(),
            ).run()

            with self.assertRaisesRegex(ValueError, "cover wearers exactly"):
                replace(result, selections=(result.selections[0],))
            with self.assertRaisesRegex(ValueError, "cover wearers exactly"):
                replace(result, selections=tuple(reversed(result.selections)))

    def test_completed_result_recomputes_canonical_layout_finalists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = GcsimMainLayoutScanSession(
                _request(Path(tmp)),
                enable_cache=False,
                scheduler_factory=LayoutSchedulerFactory(),
            ).run()
            selection = result.selections[0]
            wrong_best = next(
                layout_id
                for layout_id, _layout in selection.layouts
                if layout_id != selection.best_layout_id
            )

            with self.assertRaisesRegex(ValueError, "best layout|finalists"):
                replace(
                    result,
                    selections=(
                        replace(selection, best_layout_id=wrong_best),
                        *result.selections[1:],
                    ),
                )

    def test_completed_result_rejects_silently_truncated_finalists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = GcsimMainLayoutScanSession(
                _request(Path(tmp)),
                enable_cache=False,
                scheduler_factory=LayoutSchedulerFactory(),
            ).run()
            selection = result.selections[0]

            with self.assertRaisesRegex(ValueError, "frozen scan budget"):
                replace(
                    result,
                    selections=(
                        replace(selection, layouts=selection.layouts[:1]),
                        *result.selections[1:],
                    ),
                )

    def test_completed_result_projects_logical_dps_from_exact_batch_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = GcsimMainLayoutScanSession(
                _request(Path(tmp)),
                enable_cache=False,
                scheduler_factory=LayoutSchedulerFactory(),
            ).run()
            forged = replace(
                result.combination_evaluations[0],
                expected_dps=result.combination_evaluations[0].expected_dps + 100000,
            )

            with self.assertRaisesRegex(ValueError, "does not project"):
                replace(
                    result,
                    combination_evaluations=(
                        forged,
                        *result.combination_evaluations[1:],
                    ),
                )

    def test_completed_result_recomputes_selected_slot_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = GcsimMainLayoutScanSession(
                _request(Path(tmp)),
                enable_cache=False,
                scheduler_factory=LayoutSchedulerFactory(),
            ).run()
            selection = result.selections[0]
            forged_values = tuple(
                (slot, tuple(reversed(values)))
                for slot, values in selection.selected_slot_values
            )

            with self.assertRaisesRegex(ValueError, "coordinate evidence"):
                replace(
                    result,
                    selections=(
                        replace(selection, selected_slot_values=forged_values),
                        *result.selections[1:],
                    ),
                )
            with self.assertRaisesRegex(ValueError, "finalists"):
                replace(
                    result,
                    selections=(
                        replace(selection, layouts=tuple(reversed(selection.layouts))),
                        *result.selections[1:],
                    ),
                )

    def test_completed_result_rejects_terminal_phase_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = GcsimMainLayoutScanSession(
                _request(Path(tmp)),
                enable_cache=False,
                scheduler_factory=LayoutSchedulerFactory(),
            ).run()

            with self.assertRaisesRegex(ValueError, "successful batches"):
                replace(
                    result,
                    coordinate_batch=replace(
                        result.coordinate_batch,
                        status=GcsimFarmingBatchStatus.CANCELLED,
                    ),
                )

    def test_layout_selection_deep_freezes_nested_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = GcsimMainLayoutScanSession(
                _request(Path(tmp)),
                enable_cache=False,
                scheduler_factory=LayoutSchedulerFactory(),
            ).run()
            original = result.selections[0]
            mutable_layouts = list(original.layouts)
            mutable_values = [
                [slot, list(values)]
                for slot, values in original.selected_slot_values
            ]

            frozen = GcsimWearerLayoutSelection(
                wearer_id=original.wearer_id,
                best_layout_id=original.best_layout_id,
                layouts=mutable_layouts,
                selected_slot_values=mutable_values,
            )
            mutable_layouts.clear()
            mutable_values[0][1].clear()

            self.assertEqual(frozen.layouts, original.layouts)
            self.assertEqual(frozen.selected_slot_values, original.selected_slot_values)
            self.assertIsInstance(frozen.layouts, tuple)
            self.assertTrue(
                all(isinstance(values, tuple) for _slot, values in frozen.selected_slot_values)
            )


class LayoutSchedulerFactory:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.calls = []

    def __call__(self, requests, budget):
        values = tuple(requests)
        call_index = len(self.calls)
        self.calls.append(values)
        return LayoutScheduler(
            values,
            budget,
            fail_first=self.fail_first and call_index == 0,
        )


class LayoutScheduler:
    def __init__(self, requests, budget, *, fail_first=False) -> None:
        self.requests = requests
        self.budget = budget
        self.fail_first = fail_first
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self):
        results = tuple(
            _evaluation_result(
                request,
                success=not (self.fail_first and index == 0),
                dps=1000.0 + _layout_score(request.candidate_keys),
            )
            for index, request in enumerate(self.requests)
        )
        successful = tuple(result for result in results if result.success)
        best = next(
            iter(
                sorted(
                    successful,
                    key=lambda result: (
                        -float(result.summary.dps_mean),
                        result.candidate_keys,
                    ),
                )
            ),
            None,
        )
        return GcsimFarmingBatchResult(
            status=(
                GcsimFarmingBatchStatus.COMPLETED
                if len(successful) == len(results)
                else GcsimFarmingBatchStatus.COMPLETED_WITH_ERRORS
            ),
            comparison_context_sha256=self.requests[0].comparison_context_sha256,
            results=results,
            best_result=best,
            best_evaluation=None if best is None else best.evaluation,
            requested_count=len(results),
            successful_count=len(successful),
            cache_hit_count=0,
            failed_count=len(results) - len(successful),
            skipped_count=0,
            max_parallel_candidates=self.budget.max_parallel_candidates,
            total_cpu_budget=self.budget.total_cpu_budget,
            deadline_seconds=self.budget.overall_deadline_seconds,
            elapsed_seconds=0.001,
        )


def _layout_score(candidate_keys) -> float:
    score = 0.0
    for key in candidate_keys:
        tokens = key[2].removeprefix("main/").split("-")
        score += tokens.count("em") * 100.0
        score += tokens.count("atkpct") * 5.0
        score += tokens.count("cr") * 20.0
    return score


def _request(root: Path) -> GcsimMainLayoutScanRequest:
    return GcsimMainLayoutScanRequest(
        engine_context=_context(root),
        prepared_config_text=PREPARED_CONFIG,
        wearer_ids=("furina", "bennett"),
        baseline_set_states=(
            _candidate("furina", "goldentroupe").state,
            _candidate("bennett", "noblesseoblige").state,
        ),
        profile_bank=build_default_gcsim_screening_profile_bank(),
        fidelity=GcsimFarmingScreeningFidelity(iterations=10, worker_count=1),
        coordinate_scheduler_budget=GcsimFarmingSchedulerBudget(2, 2, 10.0),
        combination_scheduler_budget=GcsimFarmingSchedulerBudget(2, 2, 10.0),
        scan_budget=GcsimMainLayoutScanBudget(
            max_values_per_slot=2,
            max_layouts_per_wearer=3,
            candidate_timeout_seconds=2.0,
        ),
        overall_deadline_seconds=20.0,
    )


if __name__ == "__main__":
    unittest.main()
