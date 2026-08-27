from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from run_workspace.gcsim.optimizer_anytime_candidates import (
    build_gcsim_optimizer_dense_artifact_catalog,
)
from run_workspace.gcsim.optimizer_artifact_first_service import (
    GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_ID,
    GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_VERSION,
    GcsimOptimizerArtifactFirstPlan,
    GcsimOptimizerArtifactFirstSession,
    _PartialMatching,
    _retain_partial_matchings,
    generate_gcsim_optimizer_artifact_first_proposals,
)
from run_workspace.gcsim.optimizer_inventory_frontier import (
    build_gcsim_optimizer_inventory_frontier,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimOptimizerTerminalStatus,
    GcsimOptimizerWorkPlan,
)
from run_workspace.gcsim.optimizer_run_input import (
    build_gcsim_optimizer_run_input,
)
from run_workspace.gcsim.optimizer_set_impact import (
    GcsimOptimizerSetImpactResult,
)
from run_workspace.gcsim.optimizer_stat_response import (
    GcsimStatResponseObjective,
    GcsimStatResponseTarget,
)

from ._optimizer_oracle_fixtures import build_oracle_account_environment
from .test_gcsim_optimizer_anytime_selected_service import (
    _ImmediateSessionFactory,
    _ResponseDiscovery,
)


class GcsimOptimizerArtifactFirstServiceTests(unittest.TestCase):
    def test_partial_matching_reserves_top_two_rank_lattice(self) -> None:
        lattice = tuple(
            _PartialMatching(
                artifacts=tuple(
                    SimpleNamespace(artifact_id=100 * position + rank)
                    for position, rank in enumerate(ranks)
                ),
                mask=0,
                score=-1000.0 - mask,
                selection_score=-1000.0 - mask,
                rank_vector=ranks,
            )
            for mask in range(16)
            for ranks in (
                tuple((mask >> position) & 1 for position in range(4)),
            )
        )
        high_score_non_lattice = tuple(
            _PartialMatching(
                artifacts=(SimpleNamespace(artifact_id=1000 + index),),
                mask=0,
                score=1000.0 - index,
                selection_score=1000.0 - index,
                rank_vector=(index + 2,),
            )
            for index in range(32)
        )

        retained = _retain_partial_matchings(
            (*high_score_non_lattice, *lattice),
            limit=16,
        )

        self.assertEqual(
            {item.rank_vector for item in retained},
            {item.rank_vector for item in lattice},
        )
        self.assertIn((1, 0, 1, 0), {item.rank_vector for item in retained})

    def test_shared_kernel_builds_injective_physical_finalists(self) -> None:
        environment, plan, run_input = _artifact_first_environment()
        catalog = build_gcsim_optimizer_dense_artifact_catalog(run_input)
        frontier = build_gcsim_optimizer_inventory_frontier(
            run_input,
            catalog=catalog,
        )
        response = _ResponseDiscovery()(run_input)

        proposals, coverage = generate_gcsim_optimizer_artifact_first_proposals(
            run_input,
            catalog=catalog,
            frontier=frontier,
            response=response,
            plan=plan,
        )

        self.assertGreater(len(proposals), 0)
        self.assertLessEqual(len(proposals), plan.max_exact_finalists)
        self.assertEqual(coverage.compiled_proposal_count, len(proposals))
        self.assertEqual(
            tuple(item.artifact_id for item in frontier.retained_rows),
            tuple(item.artifact_id for item in catalog.artifacts),
        )
        self.assertGreater(coverage.slot_matching_count, 0)
        self.assertGreater(coverage.cross_slot_state_count, 0)
        for proposal in proposals:
            assignments = (
                proposal.compiled_candidate.assignment_witness.wearer_assignments
            )
            artifact_ids = tuple(
                artifact_id
                for assignment in assignments
                for artifact_id in assignment.artifact_ids_by_slot.values()
            )
            self.assertEqual(len(artifact_ids), 20)
            self.assertEqual(len(set(artifact_ids)), 20)
            self.assertTrue(
                all(
                    tuple(assignment.artifact_ids_by_slot)
                    == GCSIM_OPTIMIZER_ARTIFACT_SLOTS
                    for assignment in assignments
                )
            )

        result = GcsimOptimizerArtifactFirstSession(
            run_input,
            engine_context=environment.engine,
            prepared_config_text=environment.source_config_text,
            plan=plan,
            response_discovery=_ResponseDiscovery(),
            set_impact_discovery=_SetImpactDiscovery(),
            session_factory=_ImmediateSessionFactory(),
            enable_cache=False,
            stat_response_target=_dps_target(),
        ).run()

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.BEST_FOUND,
        )
        self.assertTrue(result.terminal.top_n.entries)
        self.assertIsNotNone(result.recall_trace)
        assert result.recall_trace is not None
        self.assertTrue(result.recall_trace.proposal_assignments)
        proposal_labels = dict(
            result.recall_trace.proposal_diversity_labels
        )
        for proposal in result.proposals:
            self.assertEqual(
                proposal_labels[proposal.proposal_sha256],
                proposal.diversity_labels,
            )
            for assignment in (
                proposal.compiled_candidate.assignment_witness.wearer_assignments
            ):
                self.assertTrue(
                    set(assignment.artifact_ids_by_slot.values()).issubset(
                        result.recall_trace.artifact_ids(
                            "proposal",
                            assignment.wearer.team_slot,
                        )
                    )
                )
        self.assertEqual(
            result.terminal.request.work_plan.plan_id,
            GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_ID,
        )
        self.assertNotEqual(
            run_input.run_input_sha256,
            environment.run_input.run_input_sha256,
        )

    def test_plan_mismatch_fails_closed_without_invoking_another_path(self) -> None:
        environment = build_oracle_account_environment()
        response_discovery = Mock()

        result = GcsimOptimizerArtifactFirstSession(
            environment.run_input,
            engine_context=environment.engine,
            prepared_config_text=environment.source_config_text,
            plan=_small_plan(),
            response_discovery=response_discovery,
            stat_response_target=_dps_target(),
        ).run()

        self.assertEqual(
            result.terminal.status,
            GcsimOptimizerTerminalStatus.NOT_READY,
        )
        self.assertEqual(
            result.terminal.stop_reason,
            "artifact_first_work_plan_mismatch",
        )
        response_discovery.assert_not_called()
        self.assertFalse(result.proposals)


def _artifact_first_environment():
    environment = build_oracle_account_environment()
    plan = _small_plan()
    request = replace(
        environment.request,
        work_plan=GcsimOptimizerWorkPlan(
            operation=environment.request.operation,
            plan_id=GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_ID,
            plan_version=GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_VERSION,
            parameters=plan.to_dict(),
        ),
    )
    result = build_gcsim_optimizer_run_input(
        request=request,
        config_shell=environment.shell,
        artifact_database=environment.database,
        engine_context=environment.engine,
    )
    assert result.ready and result.run_input is not None
    return environment, plan, result.run_input


def _small_plan() -> GcsimOptimizerArtifactFirstPlan:
    return replace(
        GcsimOptimizerArtifactFirstPlan(),
        max_focus_signatures=8,
        response_directions_per_focus=1,
        per_wearer_slot_head=8,
        slot_matching_beam_width=16,
        max_slot_matchings=24,
        cross_slot_beam_width=64,
        max_complete_assignments=32,
        max_exact_finalists=8,
        top_n=2,
    )


class _SetImpactDiscovery:
    def __call__(self, **kwargs):
        return GcsimOptimizerSetImpactResult(
            rows=(),
            plan=kwargs["plan"],
            response_evidence_sha256=kwargs["response"].evidence_sha256,
            elapsed_seconds=0.0,
            batch_count=0,
        )


def _dps_target() -> GcsimStatResponseTarget:
    return GcsimStatResponseTarget(
        objective=GcsimStatResponseObjective.DPS,
        target_sha256="f" * 64,
    )


if __name__ == "__main__":
    unittest.main()
