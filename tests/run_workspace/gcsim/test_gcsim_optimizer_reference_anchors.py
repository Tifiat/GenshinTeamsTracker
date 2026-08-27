from __future__ import annotations

import unittest

import run_workspace.gcsim as gcsim_api
from run_workspace.gcsim.farming_team_search import (
    FullTeamComposerBudget,
    FullTeamSimulationMetrics,
)
from run_workspace.gcsim.optimizer_config import (
    GcsimFiveStarMainStatLayout,
)
from run_workspace.gcsim.optimizer_main_response import (
    GcsimOptimizerFourPieceMainDomain,
    GcsimOptimizerReachableMainLayout,
)
from run_workspace.gcsim.optimizer_reference_anchors import (
    GcsimOptimizerReferenceAnchorPlan,
    build_gcsim_optimizer_reference_layout_catalog,
    discover_gcsim_optimizer_reference_anchors,
)

from ._optimizer_oracle_fixtures import build_oracle_account_environment


class GcsimOptimizerReferenceAnchorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = build_oracle_account_environment()
        self.domains = _two_layout_domains(self.environment)

    def test_public_facade_exports_m8a_boundary(self) -> None:
        expected = {
            "GCSIM_OPTIMIZER_REFERENCE_ANCHOR_SCHEMA_VERSION",
            "GcsimOptimizerReferenceAnchorPlan",
            "GcsimOptimizerReferenceAnchorResult",
            "discover_gcsim_optimizer_reference_anchors",
        }

        self.assertTrue(expected.issubset(set(gcsim_api.__all__)))
        self.assertTrue(all(hasattr(gcsim_api, name) for name in expected))
        self.assertEqual(len(gcsim_api.__all__), len(set(gcsim_api.__all__)))

    def test_small_domain_is_exhaustive_and_finds_joint_em_winner(self) -> None:
        result = discover_gcsim_optimizer_reference_anchors(
            self.environment.run_input,
            domains=self.domains,
            simulator=_JointEmSimulator("a" * 64),
            evaluation_context_sha256="a" * 64,
            plan=_plan(exact_limit=16, total=16, seeds=16),
        )

        self.assertEqual(result.status, "completed")
        self.assertTrue(result.coverage.exact_mode)
        self.assertEqual(result.coverage.raw_joint_state_count, 16)
        self.assertEqual(result.coverage.evaluated_state_count, 16)
        self.assertEqual(result.best_anchor.dps_mean, 200.0)
        self.assertTrue(
            all(
                choice.layout
                == GcsimFiveStarMainStatLayout("em", "em", "em")
                for choice in result.best_anchor.choices
            )
        )

    def test_large_mode_explicit_four_wearer_seed_preserves_em_anchor(self) -> None:
        result = discover_gcsim_optimizer_reference_anchors(
            self.environment.run_input,
            domains=self.domains,
            simulator=_JointEmSimulator("b" * 64),
            evaluation_context_sha256="b" * 64,
            plan=_plan(exact_limit=1, total=10, seeds=10),
        )

        self.assertFalse(result.coverage.exact_mode)
        self.assertLess(result.coverage.evaluated_state_count, 16)
        self.assertEqual(result.best_anchor.dps_mean, 200.0)
        self.assertIn("em", result.coverage.structural_tags_retained)

    def test_layout_catalog_unions_domains_by_wearer(self) -> None:
        catalog = build_gcsim_optimizer_reference_layout_catalog(
            self.domains
        )

        self.assertEqual(set(catalog), {"alpha", "beta", "gamma", "delta"})
        self.assertTrue(all(len(rows) == 2 for rows in catalog.values()))

    def test_cancel_before_search_returns_no_anchor(self) -> None:
        result = discover_gcsim_optimizer_reference_anchors(
            self.environment.run_input,
            domains=self.domains,
            simulator=_JointEmSimulator("c" * 64),
            evaluation_context_sha256="c" * 64,
            plan=_plan(exact_limit=16, total=16, seeds=16),
            is_cancelled=lambda: True,
        )

        self.assertEqual(result.status, "cancelled")
        self.assertFalse(result.anchors)
        self.assertEqual(result.coverage.evaluated_state_count, 0)


class _JointEmSimulator:
    def __init__(self, context_sha256: str) -> None:
        self.evaluation_context_sha256 = context_sha256

    def __call__(self, requests):
        result = {}
        for request in requests:
            em_count = sum(
                choice.state.main_stat_layout_id == "main/em-em-em"
                for choice in request.state.choices
            )
            dps = 200.0 if em_count == 4 else 100.0 + em_count
            result[request.state.probe_key] = FullTeamSimulationMetrics(
                status="passed",
                dps_mean=dps,
                dps_se=1.0,
                iterations=20,
                novelty_tags=("joint_em",) if em_count == 4 else (),
            )
        return result


def _plan(
    *,
    exact_limit: int,
    total: int,
    seeds: int,
) -> GcsimOptimizerReferenceAnchorPlan:
    return GcsimOptimizerReferenceAnchorPlan(
        exact_joint_state_limit=exact_limit,
        max_anchors=6,
        composer_budget=FullTeamComposerBudget(
            max_total_evaluations=total,
            max_seed_evaluations=seeds,
            max_rounds=2,
            max_coordinate_evaluations_per_round=2,
            max_pair_evaluations_per_round=2,
            pair_frontier_per_wearer=2,
            beam_width=6,
            beam_top_slots=2,
            beam_uncertain_slots=2,
            beam_novelty_slots=2,
            max_physical_finalists=6,
            confidence_sigma=2.0,
            relative_uncertainty_margin=0.02,
            max_seconds=10.0,
            per_evaluation_timeout_seconds=2.0,
        ),
    )


def _two_layout_domains(environment):
    layouts = (
        GcsimFiveStarMainStatLayout("atk%", "pyro%", "cr"),
        GcsimFiveStarMainStatLayout("em", "em", "em"),
    )
    evidence = tuple(
        (slot, (index,))
        for index, slot in enumerate(
            ("flower", "plume", "sands", "goblet", "circlet"),
            start=1,
        )
    )
    return tuple(
        GcsimOptimizerFourPieceMainDomain(
            run_input_sha256=environment.run_input.run_input_sha256,
            wearer=target.wearer,
            package=target.package,
            reachable_layouts=tuple(
                GcsimOptimizerReachableMainLayout(
                    layout=layout,
                    supporting_artifact_ids_by_slot=evidence,
                    maximum_target_piece_count=4,
                )
                for layout in layouts
            ),
            eligible_artifact_ids_by_slot=evidence,
            excluded_artifact_counts=(),
        )
        for target in environment.targets
    )


if __name__ == "__main__":
    unittest.main()
