from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import run_workspace.gcsim as gcsim_api
from run_workspace.gcsim.optimizer_account_superset import (
    GcsimOptimizerAccountSupersetError,
    GcsimOptimizerAccountSupersetSession,
)
from run_workspace.gcsim.optimizer_all_set_service import (
    GCSIM_OPTIMIZER_ALL_SET_PLAN_ID,
    GCSIM_OPTIMIZER_ALL_SET_PLAN_VERSION,
    GcsimOptimizerAllSetPlan,
    GcsimOptimizerAllSetResult,
)
from run_workspace.gcsim.optimizer_anytime_selected_service import (
    GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_ID,
    GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_VERSION,
    GcsimOptimizerAnytimeSelectedPlan,
    GcsimOptimizerAnytimeSelectedResult,
)
from run_workspace.gcsim.optimizer_anytime_race import (
    GcsimOptimizerAnytimeRaceEvaluation,
    GcsimOptimizerAnytimeRaceResult,
    GcsimOptimizerAnytimeRaceStatus,
)
from run_workspace.gcsim.optimizer_joint_proposals import (
    GcsimOptimizerJointProposal,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimOptimizerAccountAssignmentWitness,
    GcsimOptimizerAccountScope,
    GcsimOptimizerCandidateResult,
    GcsimOptimizerCoverageCounters,
    GcsimOptimizerDpsEstimate,
    GcsimOptimizerEvaluationIdentity,
    GcsimOptimizerMinimumStatConstraint,
    GcsimOptimizerTerminalResult,
    GcsimOptimizerTerminalStatus,
    GcsimOptimizerWearerArtifactAssignment,
    GcsimOptimizerWorkPlan,
    build_gcsim_optimizer_top_n,
)
from run_workspace.gcsim.optimizer_run_input import (
    build_gcsim_optimizer_run_input,
)
from run_workspace.gcsim.optimizer_stat_response import (
    GcsimStatResponseObjective,
    GcsimStatResponseTarget,
)

from ._optimizer_oracle_fixtures import build_oracle_account_environment


class GcsimOptimizerAccountSupersetTests(unittest.TestCase):
    def setUp(self) -> None:
        environment = build_oracle_account_environment()
        self.environment = environment
        self.selected_plan = GcsimOptimizerAnytimeSelectedPlan()
        self.all_set_plan = GcsimOptimizerAllSetPlan(
            account_plan=self.selected_plan
        )
        selected_request = replace(
            environment.request,
            four_star_overrides=tuple(
                replace(item, allowed_set_uids=())
                for item in environment.request.four_star_overrides
            ),
            work_plan=GcsimOptimizerWorkPlan(
                operation=environment.request.operation,
                plan_id=GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_ID,
                plan_version=GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_VERSION,
                parameters=self.selected_plan.to_dict(),
            ),
        )
        all_request = replace(
            selected_request,
            account_scope=GcsimOptimizerAccountScope.ALL_DATABASE_SETS,
            selected_set_pools=(),
            work_plan=GcsimOptimizerWorkPlan(
                operation=environment.request.operation,
                plan_id=GCSIM_OPTIMIZER_ALL_SET_PLAN_ID,
                plan_version=GCSIM_OPTIMIZER_ALL_SET_PLAN_VERSION,
                parameters=self.all_set_plan.to_dict(),
            ),
        )
        self.selected_input = self._build_input(selected_request)
        self.all_input = self._build_input(all_request)
        self.proposal = self._proposal("a", "b")
        self.selected_result = self._selected_result(self.proposal)
        self.all_set_result = self._all_set_result(anchor_count=1)

    def test_public_facade_exports_product_superset_workflow(self) -> None:
        self.assertIs(
            gcsim_api.GcsimOptimizerAccountSupersetSession,
            GcsimOptimizerAccountSupersetSession,
        )
        self.assertTrue(
            callable(gcsim_api.run_gcsim_optimizer_account_superset)
        )

    def test_runs_selected_then_all_with_exact_confirmed_anchor(self) -> None:
        calls = []
        selected_session = _FakeSession(
            "selected",
            self.selected_result,
            calls,
        )
        all_set_session = _FakeSession(
            "all",
            self.all_set_result,
            calls,
        )
        selected_factory_calls = []
        all_factory_calls = []

        def selected_factory(run_input, **kwargs):
            selected_factory_calls.append((run_input, kwargs))
            return selected_session

        def all_factory(run_input, **kwargs):
            all_factory_calls.append((run_input, kwargs))
            return all_set_session

        session = self._workflow(
            selected_session_factory=selected_factory,
            all_set_session_factory=all_factory,
        )

        result = session.run()

        self.assertEqual(calls, ["selected", "all"])
        self.assertIs(result.selected_result, self.selected_result)
        self.assertIs(result.all_set_result, self.all_set_result)
        self.assertIs(result.terminal, self.all_set_result.terminal)
        self.assertIs(selected_factory_calls[0][0], self.selected_input)
        self.assertIs(all_factory_calls[0][0], self.all_input)
        self.assertEqual(
            all_factory_calls[0][1]["required_account_anchors"],
            (self.proposal,),
        )

    def test_anchors_selected_terminal_top_instead_of_final_race_top(self) -> None:
        preliminary_proposal = self._proposal("c", "d")
        final_proposal = self._proposal("e", "f")
        preliminary_race, preliminary_evaluation = self._race_result(
            preliminary_proposal,
            dps_mean=120.0,
            evidence_character="1",
        )
        selected_result = self._selected_result(
            final_proposal,
            final_dps_mean=110.0,
            preliminary_race_results=(preliminary_race,),
            terminal_evaluation=preliminary_evaluation,
        )
        all_factory_calls = []

        def all_factory(run_input, **kwargs):
            all_factory_calls.append((run_input, kwargs))
            return _FakeSession("all", self.all_set_result, [])

        result = self._workflow(
            selected_session_factory=lambda *_args, **_kwargs: _FakeSession(
                "selected",
                selected_result,
                [],
            ),
            all_set_session_factory=all_factory,
        ).run()

        self.assertIs(result.selected_result, selected_result)
        self.assertEqual(
            selected_result.best_found.candidate_identity_sha256,
            preliminary_proposal.compiled_candidate.candidate_identity_sha256,
        )
        self.assertIs(
            selected_result.race_result.best_confirmed.proposal,
            final_proposal,
        )
        self.assertEqual(
            all_factory_calls[0][1]["required_account_anchors"],
            (preliminary_proposal,),
        )

    def test_fails_closed_when_selected_phase_has_no_confirmed_winner(self) -> None:
        selected_without_race = replace(
            self.selected_result,
            terminal=GcsimOptimizerTerminalResult(
                request=self.selected_input.request,
                status=GcsimOptimizerTerminalStatus.NO_SUCCESS,
                stop_reason="unit_test_selected_no_success",
                elapsed_seconds=0.0,
            ),
            race_result=None,
        )
        all_factory = Mock()
        session = self._workflow(
            selected_session_factory=lambda *_args, **_kwargs: _FakeSession(
                "selected",
                selected_without_race,
                [],
            ),
            all_set_session_factory=all_factory,
        )

        with self.assertRaisesRegex(
            GcsimOptimizerAccountSupersetError,
            "no confirmed account winner",
        ):
            session.run()

        all_factory.assert_not_called()

    def test_fails_closed_when_terminal_winner_has_no_confirmed_proposal(self) -> None:
        unrelated_result = self._selected_result(self._proposal("5", "6"))
        selected_without_matching_evidence = replace(
            self.selected_result,
            race_result=unrelated_result.race_result,
        )
        all_factory = Mock()
        session = self._workflow(
            selected_session_factory=lambda *_args, **_kwargs: _FakeSession(
                "selected",
                selected_without_matching_evidence,
                [],
            ),
            all_set_session_factory=all_factory,
        )

        with self.assertRaisesRegex(
            GcsimOptimizerAccountSupersetError,
            "no matching confirmed proposal",
        ):
            session.run()

        all_factory.assert_not_called()

    def test_rejects_inputs_that_are_not_selected_and_all_scopes(self) -> None:
        with self.assertRaisesRegex(
            GcsimOptimizerAccountSupersetError,
            "all-database account scope",
        ):
            GcsimOptimizerAccountSupersetSession(
                self.selected_input,
                self.selected_input,
                engine_context=self.environment.engine,
                prepared_config_text=self.environment.source_config_text,
                selected_plan=self.selected_plan,
                all_set_plan=self.all_set_plan,
            )

    def test_rejects_different_minimum_constraints_between_scopes(self) -> None:
        mismatched_request = replace(
            self.all_input.request,
            minimum_stat_constraints=(
                GcsimOptimizerMinimumStatConstraint(
                    wearer=self.environment.wearers[0],
                    axis_key="cr",
                    minimum="0.7",
                ),
            ),
        )
        mismatched_all_input = self._build_input(mismatched_request)

        with self.assertRaisesRegex(
            GcsimOptimizerAccountSupersetError,
            "different minimum-stat constraints",
        ):
            GcsimOptimizerAccountSupersetSession(
                self.selected_input,
                mismatched_all_input,
                engine_context=self.environment.engine,
                prepared_config_text=self.environment.source_config_text,
                selected_plan=self.selected_plan,
                all_set_plan=self.all_set_plan,
            )

    def test_rejects_response_target_outside_the_frozen_source(self) -> None:
        with self.assertRaisesRegex(
            GcsimOptimizerAccountSupersetError,
            "differs from the frozen source target",
        ):
            GcsimOptimizerAccountSupersetSession(
                self.selected_input,
                self.all_input,
                engine_context=self.environment.engine,
                prepared_config_text=self.environment.source_config_text,
                selected_plan=self.selected_plan,
                all_set_plan=self.all_set_plan,
                stat_response_target=GcsimStatResponseTarget(
                    objective=GcsimStatResponseObjective.DPS,
                    target_sha256="f" * 64,
                ),
            )

    def test_cancel_targets_the_current_all_set_phase(self) -> None:
        calls = []
        selected_session = _FakeSession(
            "selected",
            self.selected_result,
            calls,
        )
        all_set_session = _FakeSession(
            "all",
            self.all_set_result,
            calls,
        )
        workflow = None

        def cancel_active_phase() -> None:
            assert workflow is not None
            workflow.cancel()

        all_set_session.on_run = cancel_active_phase
        workflow = self._workflow(
            selected_session_factory=(
                lambda *_args, **_kwargs: selected_session
            ),
            all_set_session_factory=(
                lambda *_args, **_kwargs: all_set_session
            ),
        )

        result = workflow.run()

        self.assertIs(result.all_set_result, self.all_set_result)
        self.assertEqual(calls, ["selected", "all"])
        self.assertEqual(selected_session.cancel_count, 0)
        self.assertEqual(all_set_session.cancel_count, 1)

    def test_cancel_during_selected_short_circuits_all_phase(self) -> None:
        cancelled_selected = replace(
            self.selected_result,
            terminal=GcsimOptimizerTerminalResult(
                request=self.selected_input.request,
                status=GcsimOptimizerTerminalStatus.CANCELLED,
                stop_reason="unit_test_selected_cancelled",
                elapsed_seconds=0.0,
            ),
            race_result=None,
        )
        selected_session = _FakeSession(
            "selected",
            cancelled_selected,
            [],
        )
        all_factory = Mock()
        workflow = None

        def cancel_active_phase() -> None:
            assert workflow is not None
            workflow.cancel()

        selected_session.on_run = cancel_active_phase
        workflow = self._workflow(
            selected_session_factory=(
                lambda *_args, **_kwargs: selected_session
            ),
            all_set_session_factory=all_factory,
        )

        result = workflow.run()

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.CANCELLED,
        )
        self.assertIs(result.terminal.request, self.all_input.request)
        self.assertEqual(
            result.terminal.coverage.counters.get(
                "all_set_injected_account_anchor_count",
                0,
            ),
            0,
        )
        self.assertEqual(selected_session.cancel_count, 1)
        all_factory.assert_not_called()

    def test_rejects_all_set_result_without_one_injected_anchor(self) -> None:
        session = self._workflow(
            selected_session_factory=lambda *_args, **_kwargs: _FakeSession(
                "selected",
                self.selected_result,
                [],
            ),
            all_set_session_factory=lambda *_args, **_kwargs: _FakeSession(
                "all",
                self._all_set_result(anchor_count=0),
                [],
            ),
        )

        with self.assertRaisesRegex(
            GcsimOptimizerAccountSupersetError,
            "exactly one injected account anchor",
        ):
            session.run()

    def _workflow(self, **kwargs):
        return GcsimOptimizerAccountSupersetSession(
            self.selected_input,
            self.all_input,
            engine_context=self.environment.engine,
            prepared_config_text=self.environment.source_config_text,
            selected_plan=self.selected_plan,
            all_set_plan=self.all_set_plan,
            **kwargs,
        )

    def _build_input(self, request):
        built = build_gcsim_optimizer_run_input(
            request=request,
            config_shell=self.environment.shell,
            artifact_database=self.environment.database,
            engine_context=self.environment.engine,
        )
        self.assertTrue(built.ready)
        assert built.run_input is not None
        return built.run_input

    def _proposal(self, proposal_character: str, candidate_character: str):
        proposal = Mock(spec=GcsimOptimizerJointProposal)
        proposal.proposal_sha256 = proposal_character * 64
        proposal.compiled_candidate = SimpleNamespace(
            candidate_identity_sha256=candidate_character * 64,
            assignment_witness=self._assignment_witness(),
            targets=self.environment.targets,
        )
        return proposal

    def _assignment_witness(self):
        rows = []
        next_artifact_id = 1
        for wearer in self.environment.wearers:
            rows.append(
                GcsimOptimizerWearerArtifactAssignment(
                    wearer=wearer,
                    artifact_ids_by_slot={
                        slot: next_artifact_id + index
                        for index, slot in enumerate(
                            GCSIM_OPTIMIZER_ARTIFACT_SLOTS
                        )
                    },
                )
            )
            next_artifact_id += len(GCSIM_OPTIMIZER_ARTIFACT_SLOTS)
        return GcsimOptimizerAccountAssignmentWitness(
            request_sha256=self.selected_input.request.request_sha256,
            artifact_database_input_sha256=(
                self.selected_input.request.artifact_database_input_sha256
            ),
            wearer_assignments=tuple(rows),
        )

    def _race_result(
        self,
        proposal,
        *,
        dps_mean: float,
        evidence_character: str,
    ):
        summary = SimpleNamespace(
            dps_mean=dps_mean,
            dps_se=0.5,
            to_dict=lambda: {
                "dps_mean": dps_mean,
                "dps_se": 0.5,
                "iterations": 200,
            },
        )
        evaluation = GcsimOptimizerAnytimeRaceEvaluation(
            tier_id="confirm_200",
            proposal=proposal,
            result=SimpleNamespace(
                candidate_keys=(proposal.proposal_sha256,),
                success=True,
                expected_iterations=200,
                summary=summary,
                request_identity_sha256="2" * 64,
                source_config_sha256="3" * 64,
                cache_key=f"unit-test-{evidence_character}",
            ),
        )
        race = GcsimOptimizerAnytimeRaceResult(
            status=GcsimOptimizerAnytimeRaceStatus.COMPLETED,
            confirmed_evaluations=(evaluation,),
            trace_evaluations=(evaluation,),
            requested_by_tier=(("confirm_200", 1),),
            successful_by_tier=(("confirm_200", 1),),
            cache_hits_by_tier=(("confirm_200", 0),),
            evidence_sha256=evidence_character * 64,
            elapsed_seconds=0.0,
        )
        return race, evaluation

    def _selected_result(
        self,
        proposal,
        *,
        final_dps_mean: float = 100.0,
        preliminary_race_results=(),
        terminal_evaluation=None,
    ):
        race, final_evaluation = self._race_result(
            proposal,
            dps_mean=final_dps_mean,
            evidence_character="4",
        )
        winning_evaluation = terminal_evaluation or final_evaluation
        winning_proposal = winning_evaluation.proposal
        candidate = GcsimOptimizerCandidateResult(
            request_sha256=self.selected_input.request.request_sha256,
            candidate_identity_sha256=(
                winning_proposal.compiled_candidate.candidate_identity_sha256
            ),
            evaluation=GcsimOptimizerEvaluationIdentity(
                request_sha256=self.selected_input.request.request_sha256,
                source_simulation_sha256=(
                    self.selected_input.request.source_simulation.identity_sha256
                ),
                work_plan_sha256=(
                    self.selected_input.request.work_plan.identity_sha256
                ),
                engine_binding_sha256=(
                    self.selected_input.request.source_simulation.engine_binding_sha256
                ),
                compiled_config_sha256=(
                    winning_evaluation.result.source_config_sha256
                ),
                execution_identity_sha256=(
                    winning_evaluation.result.request_identity_sha256
                ),
            ),
            estimate=GcsimOptimizerDpsEstimate(
                dps_mean=winning_evaluation.dps_mean,
                dps_se=winning_evaluation.dps_se,
                iterations=winning_evaluation.iterations,
            ),
            target_packages=winning_proposal.compiled_candidate.targets,
            evidence_sha256={
                "race_evaluation": winning_evaluation.evidence_sha256,
            },
            account_assignment=(
                winning_proposal.compiled_candidate.assignment_witness
            ),
        )
        terminal = GcsimOptimizerTerminalResult(
            request=self.selected_input.request,
            status=GcsimOptimizerTerminalStatus.BEST_FOUND,
            stop_reason="unit_test_selected",
            elapsed_seconds=0.0,
            top_n=build_gcsim_optimizer_top_n(
                (candidate,),
                operation=self.selected_input.request.operation,
            ),
        )
        return GcsimOptimizerAnytimeSelectedResult(
            terminal=terminal,
            run_input_sha256=self.selected_input.run_input_sha256,
            plan=self.selected_plan,
            progress_events=(),
            targets_by_wearer=(),
            dense_catalog=None,
            response_result=None,
            wearer_pools=(),
            joint_coverage=None,
            race_result=race,
            preliminary_race_results=tuple(preliminary_race_results),
        )

    def _all_set_result(self, *, anchor_count: int):
        terminal = GcsimOptimizerTerminalResult(
            request=self.all_input.request,
            status=GcsimOptimizerTerminalStatus.NO_SUCCESS,
            stop_reason="unit_test_all",
            elapsed_seconds=0.0,
            coverage=GcsimOptimizerCoverageCounters(
                {
                    "all_set_injected_account_anchor_count": anchor_count,
                }
            ),
        )
        return GcsimOptimizerAllSetResult(
            terminal=terminal,
            run_input_sha256=self.all_input.run_input_sha256,
            plan=self.all_set_plan,
            derived_set_refs=(),
            package_bounds=(),
            package_decisions=(),
            account_result=None,
        )


class _FakeSession:
    def __init__(self, name, result, calls) -> None:
        self.name = name
        self.result = result
        self.calls = calls
        self.cancel_count = 0
        self.on_run = None

    def run(self):
        self.calls.append(self.name)
        if self.on_run is not None:
            self.on_run()
        return self.result

    def cancel(self) -> None:
        self.cancel_count += 1


if __name__ == "__main__":
    unittest.main()
