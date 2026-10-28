from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.artifact_runner import GcsimResultSummary
from run_workspace.gcsim.artifact_set_catalog import (
    GcsimArtifactSetCapability,
    GcsimArtifactSetCatalog,
)
from run_workspace.gcsim.farming_controller import (
    GcsimFourPieceSearchError,
    GcsimFourPieceSearchRequest,
    GcsimFourPieceSearchSession,
    GcsimFourPieceSearchStatus,
)
from run_workspace.gcsim.farming_evaluator import (
    GcsimFarmingBatchResult,
    GcsimFarmingBatchStatus,
    GcsimFarmingEvaluationResult,
    GcsimFarmingEvaluationStatus,
    GcsimFarmingSchedulerBudget,
)
from run_workspace.gcsim.farming_pipeline import GcsimFarmingScreeningFidelity
from run_workspace.gcsim.farming_profile_config import (
    build_default_gcsim_screening_profile_bank,
)
from run_workspace.gcsim.farming_search import (
    FourPieceSetState,
    ScreeningSurvivorBudget,
    SetProfileCandidate,
    WearerProfileSelection,
)
from run_workspace.gcsim.farming_team_search import FullTeamComposerBudget
from run_workspace.gcsim.optimizer_config import GcsimFiveStarMainStatLayout
from run_workspace.gcsim.optimizer_engine_context import GcsimOptimizerEngineContext


PREPARED_CONFIG = """furina char lvl=90/90 cons=0 talent=9,9,9;
furina add weapon="splendoroftranquilwaters" refine=1 lvl=90/90;
furina add set="gladiatorsfinale" count=4;
furina add stats hp=4780 atk=311 hp%=0.466 hydro%=0.466 cr=0.311;
bennett char lvl=90/90 cons=6 talent=9,9,10;
bennett add weapon="aquilafavonia" refine=1 lvl=90/90;
bennett add set="gladiatorsfinale" count=4;
bennett add stats hp=4780 atk=311 er=0.518 pyro%=0.466 cr=0.311;
options swap_delay=12 iteration=1000 workers=16;
target lvl=100 hp=999999999;
active furina;
"""


class GcsimFarmingControllerTest(unittest.TestCase):
    def test_complete_screen_flows_into_joint_composer_and_deduplicates_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory = SuccessfulSchedulerFactory()
            request = _request(Path(tmp))

            result = GcsimFourPieceSearchSession(
                request,
                enable_cache=False,
                scheduler_factory=factory,
            ).run()

            self.assertEqual(len(result.coverage.candidates), 4)
            # The same all-baseline team is the logical baseline row for both
            # one-wearer scans and is executed only once.
            self.assertEqual(result.materialized_request_count, 3)
            self.assertEqual(len(factory.calls[0]), 3)
            self.assertTrue(result.complete_screening_coverage)
            self.assertEqual(len(result.screening_evaluations), 4)
            self.assertEqual(
                tuple(pool.wearer_id for pool in result.candidate_pools),
                ("furina", "bennett"),
            )
            self.assertIsNotNone(result.composition)
            self.assertIsNotNone(result.best_found)
            self.assertIn(
                result.status,
                {
                    GcsimFourPieceSearchStatus.COMPLETED,
                    GcsimFourPieceSearchStatus.BEST_FOUND,
                },
            )
            self.assertGreaterEqual(len(factory.calls), 2)

    def test_incomplete_broad_screen_fails_closed_before_team_composition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory = SuccessfulSchedulerFactory(fail_first_request=True)

            result = GcsimFourPieceSearchSession(
                _request(Path(tmp)),
                enable_cache=False,
                scheduler_factory=factory,
            ).run()

            self.assertEqual(result.status, GcsimFourPieceSearchStatus.PARTIAL_SCREEN)
            self.assertFalse(result.complete_screening_coverage)
            self.assertTrue(result.screening_issues)
            self.assertIsNone(result.composition)
            self.assertEqual(len(factory.calls), 1)

    def test_pre_cancel_is_typed_and_starts_no_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory = SuccessfulSchedulerFactory()
            session = GcsimFourPieceSearchSession(
                _request(Path(tmp)),
                enable_cache=False,
                scheduler_factory=factory,
            )
            session.cancel()

            result = session.run()

            self.assertEqual(result.status, GcsimFourPieceSearchStatus.CANCELLED)
            self.assertEqual(factory.calls, [])
            self.assertIsNone(result.best_found)

    def test_survivor_budget_must_reserve_every_wearer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _request(Path(tmp))
            invalid = GcsimFourPieceSearchRequest(
                **{
                    field: getattr(request, field)
                    for field in request.__dataclass_fields__
                    if field != "survivor_budget"
                },
                survivor_budget=ScreeningSurvivorBudget(
                    max_survivors=4,
                    top_slots=1,
                    wearer_coverage_slots=1,
                    uncertain_slots=0,
                    profile_coverage_slots=0,
                    novelty_slots=0,
                    confidence_sigma=2.0,
                    relative_uncertainty_margin=0.05,
                ),
            )

            with self.assertRaisesRegex(GcsimFourPieceSearchError, "coverage slots"):
                GcsimFourPieceSearchSession(invalid).run()


class SuccessfulSchedulerFactory:
    def __init__(self, *, fail_first_request: bool = False) -> None:
        self.fail_first_request = fail_first_request
        self.calls = []

    def __call__(self, requests, budget):
        call_index = len(self.calls)
        values = tuple(requests)
        self.calls.append(values)
        return FakeScheduler(
            values,
            budget,
            fail_first=(self.fail_first_request and call_index == 0),
        )


class FakeScheduler:
    def __init__(self, requests, budget, *, fail_first=False) -> None:
        self.requests = requests
        self.budget = budget
        self.fail_first = fail_first
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self) -> GcsimFarmingBatchResult:
        results = tuple(
            _evaluation_result(
                request,
                success=not (self.fail_first and index == 0),
                dps=1000.0 + sum(
                    sum(ord(character) for character in key[1])
                    for key in request.candidate_keys
                ),
            )
            for index, request in enumerate(self.requests)
        )
        successful = tuple(item for item in results if item.success)
        best = next(
            iter(
                sorted(
                    successful,
                    key=lambda item: (
                        -float(item.summary.dps_mean),
                        item.candidate_keys,
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


def _evaluation_result(request, *, success: bool, dps: float):
    identity = request.identity
    return GcsimFarmingEvaluationResult(
        status=(
            GcsimFarmingEvaluationStatus.PASSED
            if success
            else GcsimFarmingEvaluationStatus.TIMEOUT
        ),
        success=success,
        request_identity_sha256=identity.identity_sha256,
        cache_key=request.cache_identity.cache_key,
        candidate_keys=request.candidate_keys,
        comparison_context_sha256=request.comparison_context_sha256,
        expected_iterations=request.expected_iterations,
        summary=(
            GcsimResultSummary(
                iterations=10,
                dps_mean=dps,
                dps_sd=10.0,
                dps_se=10.0 / (10**0.5),
            )
            if success
            else GcsimResultSummary()
        ),
        engine_binding_sha256=identity.engine_binding_sha256,
        artifact_sha256=identity.artifact_sha256,
        source_config_sha256=identity.source_config_sha256,
        error="synthetic timeout" if not success else "",
    )


def _request(root: Path) -> GcsimFourPieceSearchRequest:
    context = _context(root)
    bank = build_default_gcsim_screening_profile_bank()
    wearer_ids = ("furina", "bennett")
    return GcsimFourPieceSearchRequest(
        engine_context=context,
        prepared_config_text=PREPARED_CONFIG,
        wearer_ids=wearer_ids,
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
        wearer_profile_selections=tuple(
            WearerProfileSelection(wearer, ("baseline",))
            for wearer in wearer_ids
        ),
        baseline_states=(
            _candidate("furina", "goldentroupe"),
            _candidate("bennett", "noblesseoblige"),
        ),
        fidelity=GcsimFarmingScreeningFidelity(iterations=10, worker_count=1),
        screening_scheduler_budget=GcsimFarmingSchedulerBudget(2, 2, 10.0),
        team_scheduler_budget=GcsimFarmingSchedulerBudget(2, 2, 10.0),
        survivor_budget=ScreeningSurvivorBudget(
            max_survivors=4,
            top_slots=0,
            wearer_coverage_slots=2,
            uncertain_slots=0,
            profile_coverage_slots=0,
            novelty_slots=0,
            confidence_sigma=2.0,
            relative_uncertainty_margin=0.05,
        ),
        composer_budget=FullTeamComposerBudget(
            max_total_evaluations=8,
            max_seed_evaluations=2,
            max_rounds=2,
            max_coordinate_evaluations_per_round=4,
            max_pair_evaluations_per_round=2,
            pair_frontier_per_wearer=2,
            beam_width=4,
            beam_top_slots=2,
            beam_uncertain_slots=1,
            beam_novelty_slots=1,
            max_physical_finalists=3,
            confidence_sigma=2.0,
            relative_uncertainty_margin=0.05,
            max_seconds=10.0,
            per_evaluation_timeout_seconds=2.0,
        ),
        overall_deadline_seconds=20.0,
        screening_candidate_timeout_seconds=2.0,
    )


def _candidate(wearer: str, set_key: str) -> SetProfileCandidate:
    return SetProfileCandidate(
        state=FourPieceSetState(
            wearer_id=wearer,
            set_key=set_key,
            main_stat_layout_id="default",
        ),
        profile_id="baseline",
    )


def _context(root: Path) -> GcsimOptimizerEngineContext:
    root.mkdir(parents=True, exist_ok=True)
    artifact = root / "gtt-gcsim.exe"
    artifact.write_bytes(b"engine")
    capabilities = tuple(
        GcsimArtifactSetCapability(
            key=key,
            package_name=key,
            key_constant=key.title(),
            max_rarity=5,
            registered=True,
            has_two_piece_code=True,
            has_four_piece_code=True,
            two_piece_modeled=True,
            four_piece_modeled=True,
        )
        for key in ("goldentroupe", "noblesseoblige")
    )
    catalog = GcsimArtifactSetCatalog(
        source_root="fixture",
        source_fingerprint="c" * 64,
        sets=capabilities,
    )
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return GcsimOptimizerEngineContext(
        engine_id="fixture",
        engine_root=str(root),
        engine_version="v2.42.2",
        optimizer_contract_version="gcsim-v2.42.2",
        artifact_path=str(artifact),
        artifact_sha256=artifact_sha,
        engine_tree_sha256="e" * 64,
        catalog=catalog,
        manifest_artifact_sha256=artifact_sha,
        manifest_engine_tree_sha256="e" * 64,
        binding_sha256="b" * 64,
        trusted=True,
        issues=(),
    )


if __name__ == "__main__":
    unittest.main()
