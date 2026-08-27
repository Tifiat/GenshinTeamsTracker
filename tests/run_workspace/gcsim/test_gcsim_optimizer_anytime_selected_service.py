from __future__ import annotations

from dataclasses import replace
import math
from types import SimpleNamespace
import unittest

import run_workspace.gcsim as gcsim_api
from run_workspace.gcsim.artifact_runner import GcsimResultSummary
from run_workspace.gcsim.farming_evaluator import (
    GcsimFarmingEvaluationResult,
    GcsimFarmingEvaluationStatus,
)
from run_workspace.gcsim.optimizer_anytime_candidates import (
    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
    GcsimOptimizerAnytimeCandidatePlan,
    GcsimOptimizerAnytimeStatProfile,
)
from run_workspace.gcsim.optimizer_anytime_race import (
    GcsimOptimizerAnytimeRacePlan,
    GcsimOptimizerAnytimeRaceTier,
)
from run_workspace.gcsim.optimizer_anytime_response import (
    GcsimOptimizerAnytimeResponsePlan,
    GcsimOptimizerAnytimeResponseResult,
)
from run_workspace.gcsim.optimizer_anytime_selected_service import (
    GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_ID,
    GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_VERSION,
    GcsimOptimizerAnytimeSelectedPlan,
    GcsimOptimizerAnytimeSelectedSession,
    _retain_coordinate_refinement_frontier,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimOptimizerProgressLeaderQuality,
    GcsimOptimizerProgressLeaderScope,
    GcsimOptimizerProgressStage,
    GcsimOptimizerTerminalStatus,
    GcsimOptimizerWorkPlan,
)
from run_workspace.gcsim.optimizer_run_input import (
    build_gcsim_optimizer_run_input,
)
from run_workspace.gcsim.optimizer_stat_response import (
    GcsimStatResponseObjective,
    build_gcsim_stat_response_probe_request,
)

from ._optimizer_oracle_fixtures import build_oracle_account_environment


class GcsimOptimizerAnytimeSelectedServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = build_oracle_account_environment()
        self.plan = _plan()
        request = replace(
            self.environment.request,
            work_plan=GcsimOptimizerWorkPlan(
                operation=self.environment.request.operation,
                plan_id=GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_ID,
                plan_version=(
                    GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_VERSION
                ),
                parameters=self.plan.to_dict(),
            ),
        )
        result = build_gcsim_optimizer_run_input(
            request=request,
            config_shell=self.environment.shell,
            artifact_database=self.environment.database,
            engine_context=self.environment.engine,
        )
        self.assertTrue(result.ready)
        assert result.run_input is not None
        self.run_input = result.run_input

    def test_public_facade_exports_anytime_selected_boundary(self) -> None:
        expected = {
            "GcsimOptimizerAnytimeCandidatePlan",
            "GcsimOptimizerAnytimeResponsePlan",
            "GcsimOptimizerAnytimeRacePlan",
            "GcsimOptimizerAnytimeSelectedPlan",
            "GcsimOptimizerAnytimeSelectedSession",
            "run_gcsim_optimizer_anytime_selected",
        }

        self.assertTrue(expected.issubset(set(gcsim_api.__all__)))
        self.assertTrue(all(hasattr(gcsim_api, name) for name in expected))
        self.assertEqual(len(gcsim_api.__all__), len(set(gcsim_api.__all__)))

    def test_bounded_path_returns_only_confirmed_exact_account_builds(
        self,
    ) -> None:
        progress = []
        session_factory = _ImmediateSessionFactory()
        result = GcsimOptimizerAnytimeSelectedSession(
            self.run_input,
            engine_context=self.environment.engine,
            prepared_config_text=self.environment.source_config_text,
            plan=self.plan,
            progress_callback=progress.append,
            response_discovery=_ResponseDiscovery(),
            session_factory=session_factory,
            enable_cache=False,
        ).run()

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.BEST_FOUND,
        )
        self.assertIsNotNone(result.best_found)
        assert result.best_found is not None
        self.assertGreaterEqual(result.best_found.estimate.iterations, 200)
        self.assertEqual(
            len(
                {
                    artifact_id
                    for assignment in (
                        result.best_found.account_assignment.wearer_assignments
                    )
                    for artifact_id in assignment.artifact_ids
                }
            ),
            20,
        )
        self.assertEqual(
            tuple(event.sequence for event in progress),
            tuple(range(len(progress))),
        )
        self.assertTrue(
            any(
                event.current_best is not None
                and event.current_best.estimate.iterations == 8
                and event.current_best.quality
                is GcsimOptimizerProgressLeaderQuality.PROVISIONAL
                and event.current_best.scope
                is GcsimOptimizerProgressLeaderScope.STAGE
                for event in progress
            )
        )
        for stage, iterations in (
            (GcsimOptimizerProgressStage.SCREENING, 8),
            (GcsimOptimizerProgressStage.REFINEMENT, 32),
            (GcsimOptimizerProgressStage.FINAL_VALIDATION, 200),
            (GcsimOptimizerProgressStage.RERACE, 1000),
        ):
            self.assertTrue(
                any(
                    event.stage is stage
                    and event.completed_work == 0
                    and event.current_iterations == iterations
                    and event.current_best is None
                    for event in progress
                )
            )
        self.assertTrue(
            any(
                event.stage
                is GcsimOptimizerProgressStage.FINAL_VALIDATION
                for event in progress
            )
        )
        self.assertEqual(
            {request.expected_iterations for request in session_factory.calls},
            {8, 32, 200, 1000},
        )
        terminal_progress = progress[-1]
        self.assertIs(
            terminal_progress.stage,
            GcsimOptimizerProgressStage.COMPLETED,
        )
        self.assertIsNotNone(terminal_progress.current_best)
        assert terminal_progress.current_best is not None
        self.assertIs(
            terminal_progress.current_best.scope,
            GcsimOptimizerProgressLeaderScope.RUN,
        )
        self.assertIs(
            terminal_progress.current_best.quality,
            GcsimOptimizerProgressLeaderQuality.FINAL,
        )
        self.assertEqual(
            terminal_progress.current_iterations,
            terminal_progress.current_best.estimate.iterations,
        )

    def test_work_plan_mismatch_fails_before_any_simulation(self) -> None:
        other = replace(
            self.plan,
            overall_deadline_seconds=(
                self.plan.overall_deadline_seconds + 1.0
            ),
        )
        factory = _ImmediateSessionFactory()

        result = GcsimOptimizerAnytimeSelectedSession(
            self.run_input,
            engine_context=self.environment.engine,
            prepared_config_text=self.environment.source_config_text,
            plan=other,
            response_discovery=_ResponseDiscovery(),
            session_factory=factory,
            enable_cache=False,
        ).run()

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.NOT_READY,
        )
        self.assertEqual(
            result.terminal.stop_reason,
            "anytime_selected_work_plan_mismatch",
        )
        self.assertEqual(factory.calls, [])

    def test_plan_requires_enough_validated_capacity_for_top_n(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError,
            "capacities must be at least top_n",
        ):
            replace(self.plan, top_n=5)

    def test_coordinate_frontier_keeps_low_surrogate_structural_witness(
        self,
    ) -> None:
        proposals = []
        for index in range(300):
            labels = (f"coordinate_fixed_slot:{index % 4 + 1}",)
            if index == 299:
                labels = (
                    "coordinate_fixed_slot:3",
                    "coordinate_fixed_feature:3:main_axis_anchor:electro%",
                )
            proposals.append(
                SimpleNamespace(
                    changed_wearer_count=1,
                    surrogate_score=str(1000 - index),
                    proposal_sha256=f"{index + 1:064x}",
                    diversity_labels=labels,
                )
            )

        retained = _retain_coordinate_refinement_frontier(
            proposals,
            limit=192,
        )

        self.assertEqual(len(retained), 192)
        self.assertIn(proposals[299], retained)
        self.assertEqual(
            retained,
            _retain_coordinate_refinement_frontier(
                tuple(reversed(proposals)),
                limit=192,
            ),
        )

    def test_coordinate_frontier_balances_feature_groups_across_slots(
        self,
    ) -> None:
        proposals = [
            SimpleNamespace(
                changed_wearer_count=1,
                surrogate_score=str(10_000 - index),
                proposal_sha256=f"{index + 1:064x}",
                diversity_labels=("coordinate_fixed_slot:1",),
            )
            for index in range(64)
        ]
        for slot in range(1, 5):
            for feature_index in range(50):
                index = len(proposals)
                proposals.append(
                    SimpleNamespace(
                        changed_wearer_count=1,
                        surrogate_score=str(1_000 - index),
                        proposal_sha256=f"{index + 1:064x}",
                        diversity_labels=(
                            f"coordinate_fixed_slot:{slot}",
                            "coordinate_fixed_feature:"
                            f"{slot}:main_axis_anchor:axis_{feature_index:02d}",
                        ),
                    )
                )

        retained = _retain_coordinate_refinement_frontier(
            proposals,
            limit=192,
        )

        retained_labels = {
            label
            for proposal in retained
            for label in proposal.diversity_labels
        }
        for slot in range(1, 5):
            self.assertIn(
                "coordinate_fixed_feature:"
                f"{slot}:main_axis_anchor:axis_20",
                retained_labels,
            )

    def test_coordinate_frontier_preserves_multiple_seed_basins(self) -> None:
        proposals = [
            SimpleNamespace(
                changed_wearer_count=1,
                surrogate_score=str(10_000 - index),
                proposal_sha256=f"{index + 1:064x}",
                diversity_labels=("coordinate_fixed_slot:1",),
            )
            for index in range(96)
        ]
        seed_witnesses = {}
        for seed in range(3):
            for depth in range(80):
                index = len(proposals)
                proposal = SimpleNamespace(
                    changed_wearer_count=1,
                    surrogate_score=str(1_000 - index),
                    proposal_sha256=f"{index + 1:064x}",
                    diversity_labels=(
                        f"coordinate_seed:{seed}",
                        f"coordinate_fixed_slot:{seed + 1}",
                    ),
                )
                proposals.append(proposal)
                if depth == 15:
                    seed_witnesses[seed] = proposal

        retained = _retain_coordinate_refinement_frontier(
            proposals,
            limit=256,
        )

        for witness in seed_witnesses.values():
            self.assertIn(witness, retained)

    def test_cancel_before_start_never_returns_provisional_top_n(self) -> None:
        factory = _ImmediateSessionFactory()
        session = GcsimOptimizerAnytimeSelectedSession(
            self.run_input,
            engine_context=self.environment.engine,
            prepared_config_text=self.environment.source_config_text,
            plan=self.plan,
            response_discovery=_ResponseDiscovery(),
            session_factory=factory,
            enable_cache=False,
        )
        session.cancel()

        result = session.run()

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.CANCELLED,
        )
        self.assertFalse(result.terminal.top_n.entries)
        self.assertEqual(factory.calls, [])

    def test_response_simulator_exception_fails_closed(self) -> None:
        factory = _ImmediateSessionFactory()

        result = GcsimOptimizerAnytimeSelectedSession(
            self.run_input,
            engine_context=self.environment.engine,
            prepared_config_text=self.environment.source_config_text,
            plan=self.plan,
            response_discovery=_ResponseDiscovery(explode=True),
            session_factory=factory,
            enable_cache=False,
        ).run()

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.FAILED,
        )
        self.assertEqual(
            result.terminal.stop_reason,
            "anytime_selected_orchestration_failed",
        )
        self.assertIn(
            "synthetic selected response failure",
            result.terminal.error,
        )
        self.assertIsNone(result.best_found)
        self.assertFalse(result.terminal.top_n.entries)
        self.assertIsNone(result.response_result)
        self.assertEqual(factory.calls, [])

    def test_er_is_only_a_hard_floor_not_a_response_score(self) -> None:
        profiles = _test_response_profiles(
            self.environment.wearers,
            evidence_sha256="e" * 64,
        )
        er_index = GCSIM_OPTIMIZER_ANYTIME_STAT_AXES.index("er")

        self.assertTrue(
            all(profile.stat_weights[er_index] == 0 for profile in profiles)
        )
        self.assertTrue(
            all(
                ("sands", "er")
                not in {
                    (slot, axis)
                    for slot, axis, _score in profile.main_scores
                }
                for profile in profiles
            )
        )


def _plan() -> GcsimOptimizerAnytimeSelectedPlan:
    return GcsimOptimizerAnytimeSelectedPlan(
        response=GcsimOptimizerAnytimeResponsePlan(
            iterations=8,
            worker_count=1,
            max_parallel_candidates=1,
            total_cpu_budget=1,
            candidate_timeout_seconds=2.0,
            overall_deadline_seconds=20.0,
        ),
        candidates=GcsimOptimizerAnytimeCandidatePlan(
            max_frontier_per_group=8,
            shadow_per_group=2,
            per_profile_slot_count=4,
            max_slot_pool=16,
            wearer_beam_width=32,
            max_builds_per_target=8,
            max_builds_per_wearer=8,
            joint_beam_width=32,
            max_joint_proposals=6,
            local_search_seed_count=2,
            max_seconds=10.0,
        ),
        race=GcsimOptimizerAnytimeRacePlan(
            tiers=(
                GcsimOptimizerAnytimeRaceTier(
                    "screen_8", 8, 6, 2, 2.0
                ),
                GcsimOptimizerAnytimeRaceTier(
                    "refine_32", 32, 4, 2, 2.0
                ),
                GcsimOptimizerAnytimeRaceTier(
                    "validate_200", 200, 4, 1, 2.0
                ),
                GcsimOptimizerAnytimeRaceTier(
                    "rerace_1000", 1000, 2, 1, 2.0
                ),
            ),
            worker_count=1,
            max_parallel_candidates=1,
            total_cpu_budget=1,
            overall_deadline_seconds=30.0,
        ),
        top_n=4,
        overall_deadline_seconds=60.0,
    )


class _ResponseDiscovery:
    def __init__(self, *, explode: bool = False) -> None:
        self.explode = explode

    def __call__(self, run_input, **_kwargs):
        if self.explode:
            raise RuntimeError("synthetic selected response failure")
        return GcsimOptimizerAnytimeResponseResult(
            profiles=_test_response_profiles(
                run_input.request.source_simulation.wearers,
                evidence_sha256="a" * 64,
            ),
            synthetic_baseline_changes=(
                build_gcsim_stat_response_probe_request(
                    context_sha256="b" * 64,
                    objective=GcsimStatResponseObjective.DPS,
                ).baseline_changes
            ),
            synthetic_master_seed=123,
            planned_probe_count=108,
            successful_probe_count=108,
            failed_probe_count=0,
            cache_hit_count=0,
            evidence_sha256="a" * 64,
            elapsed_seconds=0.01,
        )


def _test_response_profiles(wearers, *, evidence_sha256):
    legal_mains = {
        "sands": ("hp%", "atk%", "def%", "em"),
        "goblet": (
            "hp%", "atk%", "def%", "em", "pyro%", "hydro%",
            "electro%", "cryo%", "anemo%", "geo%", "dendro%", "phys%",
        ),
        "circlet": ("hp%", "atk%", "def%", "em", "cr", "cd", "heal"),
    }
    return tuple(
        GcsimOptimizerAnytimeStatProfile(
            wearer=wearer,
            profile_id="balanced",
            stat_weights=tuple(
                0.0 if axis == "er" else 1.0
                for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
            ),
            main_scores=tuple(
                (slot, axis, 1.0)
                for slot, axes in legal_mains.items()
                for axis in axes
            ),
            evidence_sha256=evidence_sha256,
            feature_labels=("test_response",),
        )
        for wearer in wearers
    )


class _ImmediateSessionFactory:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, request):
        self.calls.append(request)
        return _ImmediateSession(request)


class _ImmediateSession:
    def __init__(self, request) -> None:
        self.request = request

    def cancel(self) -> None:
        pass

    def run(self):
        token = int(self.request.identity.identity_sha256[:8], 16)
        dps = 100.0 + (token % 1000) / 1000.0
        iterations = self.request.expected_iterations
        sd = 2.0
        return GcsimFarmingEvaluationResult(
            status=GcsimFarmingEvaluationStatus.PASSED,
            success=True,
            request_identity_sha256=(
                self.request.identity.identity_sha256
            ),
            cache_key=self.request.cache_identity.cache_key,
            candidate_keys=self.request.candidate_keys,
            comparison_context_sha256=(
                self.request.comparison_context_sha256
            ),
            expected_iterations=iterations,
            summary=GcsimResultSummary(
                schema_version="1",
                sim_version="fixture",
                iterations=iterations,
                dps_mean=dps,
                dps_sd=sd,
                dps_se=sd / math.sqrt(iterations),
            ),
            engine_binding_sha256=self.request.engine_binding_sha256,
            artifact_sha256=self.request.artifact_sha256,
            source_config_sha256=(
                self.request.identity.source_config_sha256
            ),
        )


if __name__ == "__main__":
    unittest.main()
