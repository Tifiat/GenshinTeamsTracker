from __future__ import annotations

from decimal import Decimal
from itertools import product
from random import Random
import unittest

from run_workspace.gcsim.optimizer_account_oracle import (
    run_gcsim_optimizer_account_four_piece_oracle,
)
from run_workspace.gcsim.optimizer_anytime_candidates import (
    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
    GcsimOptimizerAnytimeCandidatePlan,
    GcsimOptimizerAnytimeStatProfile,
    build_gcsim_optimizer_anytime_joint_proposals,
    build_gcsim_optimizer_dense_artifact_catalog,
    generate_gcsim_optimizer_anytime_wearer_pool,
)
from run_workspace.gcsim.optimizer_oracle import (
    GcsimOptimizerOraclePruningStage,
    GcsimOptimizerOracleScore,
)
from run_workspace.gcsim.optimizer_release_gate import (
    GcsimOptimizerProvisionalReleasePolicy,
    GcsimOptimizerQualityCase,
    GcsimOptimizerQualityRank,
    build_gcsim_optimizer_release_gate_report,
)
from run_workspace.gcsim.optimizer_theoretical_anytime_candidates import (
    GcsimOptimizerTheoreticalAnytimeCandidatePlan,
    build_gcsim_optimizer_theoretical_anytime_candidate_domain,
)

from ._optimizer_oracle_fixtures import build_oracle_account_environment
from .test_gcsim_optimizer_theoretical_anytime_candidates import (
    _context,
    _profiles,
    _wearers,
)


RANDOMIZED_ACCOUNT_CORPUS_SIZE = 100
RANDOMIZED_ACCOUNT_CORPUS_SEED = 0x475454
RANDOMIZED_THEORETICAL_CORPUS_SIZE = 100
RANDOMIZED_THEORETICAL_CORPUS_SEED = 0x47545454


class GcsimOptimizerReleaseCorpusTests(unittest.TestCase):
    def test_account_kernel_passes_randomized_exhaustive_release_gate(
        self,
    ) -> None:
        environment = build_oracle_account_environment()
        catalog = build_gcsim_optimizer_dense_artifact_catalog(
            environment.run_input
        )
        plan = GcsimOptimizerAnytimeCandidatePlan(max_seconds=30.0)
        randomizer = Random(RANDOMIZED_ACCOUNT_CORPUS_SEED)
        cases = []
        oracle_universe = run_gcsim_optimizer_account_four_piece_oracle(
            environment.run_input,
            targets=environment.targets,
            execution_identity_sha256="e" * 64,
            evaluator=lambda candidate: GcsimOptimizerOracleScore(
                objective_name="randomized_account_candidate_universe",
                objective_value=0.0,
                evidence_sha256=candidate.compiled_config_sha256,
            ),
        )

        for index in range(RANDOMIZED_ACCOUNT_CORPUS_SIZE):
            coefficients = tuple(
                (
                    Decimal(randomizer.randint(500, 5000)),
                    Decimal(randomizer.randint(1, 50)) / Decimal(10),
                )
                for _wearer in environment.wearers
            )
            pools = tuple(
                generate_gcsim_optimizer_anytime_wearer_pool(
                    environment.run_input,
                    catalog=catalog,
                    wearer=wearer,
                    targets=(target,),
                    profiles=(
                        _profile(wearer, cr_weight, em_weight, index),
                    ),
                    plan=plan,
                )
                for wearer, target, (cr_weight, em_weight) in zip(
                    environment.wearers,
                    environment.targets,
                    coefficients,
                    strict=True,
                )
            )
            proposals, _coverage = (
                build_gcsim_optimizer_anytime_joint_proposals(
                    environment.run_input,
                    catalog=catalog,
                    wearer_pools=pools,
                    plan=plan,
                    execution_identity_sha256="e" * 64,
                )
            )
            oracle_ranking = tuple(
                GcsimOptimizerQualityRank(
                    evaluation.candidate_identity_sha256,
                    _candidate_score(evaluation.candidate, coefficients),
                )
                for evaluation in sorted(
                    oracle_universe.evaluations,
                    key=lambda row: (
                        -_candidate_score(row.candidate, coefficients),
                        row.candidate_identity_sha256,
                    ),
                )
            )
            production_ranking = tuple(
                proposal.compiled_candidate.simulation_sha256
                for _score, proposal in sorted(
                    (
                        (_proposal_score(proposal, coefficients), proposal)
                        for proposal in proposals
                    ),
                    key=lambda row: (
                        -row[0],
                        row[1].compiled_candidate.simulation_sha256,
                    ),
                )
            )
            cases.append(
                GcsimOptimizerQualityCase(
                    case_id=f"random_account_{index:03d}",
                    oracle_ranking=oracle_ranking,
                    production_ranking_sha256s=production_ranking,
                    pruning_stages=(
                        GcsimOptimizerOraclePruningStage(
                            "anytime_account_candidates",
                            production_ranking,
                        ),
                    ),
                    top_n=1,
                )
            )

        report = build_gcsim_optimizer_release_gate_report(cases)
        policy = GcsimOptimizerProvisionalReleasePolicy()

        self.assertGreaterEqual(
            report.exact_top1_rate,
            policy.randomized_exact_top1_rate,
        )
        self.assertLessEqual(
            report.mean_best_dps_regret_ratio,
            policy.randomized_mean_regret_ratio,
        )
        self.assertLessEqual(
            report.maximum_best_dps_regret_ratio,
            policy.randomized_maximum_regret_ratio,
        )

    @unittest.skip(
        "superseded forced-profile corpus; paired-response v2 needs real evidence"
    )
    def test_theoretical_kernel_passes_randomized_exhaustive_release_gate(
        self,
    ) -> None:
        wearers = _wearers()
        domain = build_gcsim_optimizer_theoretical_anytime_candidate_domain(
            engine_context=_context(),
            wearers=wearers,
            response_profiles=_profiles(wearers),
            plan=GcsimOptimizerTheoreticalAnytimeCandidatePlan(
                max_layouts_per_wearer=10,
                max_profiles_per_wearer=7,
                max_package_anchors_per_wearer=3,
                max_wearer_alternatives=12,
                max_joint_package_anchor_proposals=4,
                max_joint_proposals=40,
            ),
        )
        exhaustive_rows = tuple(
            (
                _alternative_state_sha256(alternatives),
                tuple(
                    Decimal(str(alternative.score))
                    for alternative in alternatives
                ),
                tuple(
                    sum(
                        tag in alternative.diversity_tags
                        for alternative in alternatives
                    )
                    for tag in THEORETICAL_ANYTIME_REQUIRED_DIVERSITY_TAGS
                ),
            )
            for alternatives in product(
                *(pool.alternatives for pool in domain.wearer_pools)
            )
        )
        proposal_rows = tuple(
            (
                _proposal_state_sha256(proposal),
                tuple(
                    Decimal(str(alternative.score))
                    for alternative in alternatives
                ),
                tuple(
                    sum(
                        tag in alternative.diversity_tags
                        for alternative in alternatives
                    )
                    for tag in THEORETICAL_ANYTIME_REQUIRED_DIVERSITY_TAGS
                ),
            )
            for proposal in domain.proposals
            for alternatives in (
                tuple(
                    pool.alternative_by_key[choice.key]
                    for pool, choice in zip(
                        domain.wearer_pools,
                        proposal.state.choices,
                        strict=True,
                    )
                ),
            )
        )
        randomizer = Random(RANDOMIZED_THEORETICAL_CORPUS_SEED)
        cases = []

        for index in range(RANDOMIZED_THEORETICAL_CORPUS_SIZE):
            wearer_weights = tuple(
                Decimal(randomizer.randint(90, 110)) / Decimal(100)
                for _wearer in wearers
            )
            protected_tag = randomizer.choice(
                THEORETICAL_ANYTIME_REQUIRED_DIVERSITY_TAGS
            )
            protected_tag_index = (
                THEORETICAL_ANYTIME_REQUIRED_DIVERSITY_TAGS.index(
                    protected_tag
                )
            )
            tag_weight = Decimal(randomizer.randint(0, 120))
            coordination_weight = Decimal(randomizer.randint(0, 600))

            def score(row):
                _identity, alternative_scores, tag_counts = row
                base = sum(
                    alternative_score * wearer_weight
                    for alternative_score, wearer_weight in zip(
                        alternative_scores,
                        wearer_weights,
                        strict=True,
                    )
                )
                tag_count = tag_counts[protected_tag_index]
                return (
                    base
                    + tag_weight * tag_count
                    + coordination_weight * (tag_count == 4)
                )

            oracle = tuple(
                sorted(
                    (
                        GcsimOptimizerQualityRank(
                            row[0],
                            score(row),
                        )
                        for row in exhaustive_rows
                    ),
                    key=lambda row: (
                        -row.dps,
                        row.candidate_identity_sha256,
                    ),
                )
            )
            production = tuple(
                identity
                for _score, identity in sorted(
                    (
                        (
                            score(row),
                            row[0],
                        )
                        for row in proposal_rows
                    ),
                    key=lambda row: (-row[0], row[1]),
                )
            )
            cases.append(
                GcsimOptimizerQualityCase(
                    case_id=f"random_theoretical_{index:03d}",
                    oracle_ranking=oracle,
                    production_ranking_sha256s=production,
                    pruning_stages=(
                        GcsimOptimizerOraclePruningStage(
                            "bounded_theoretical_proposals",
                            production,
                        ),
                    ),
                    top_n=1,
                )
            )

        report = build_gcsim_optimizer_release_gate_report(cases)
        policy = GcsimOptimizerProvisionalReleasePolicy()

        self.assertGreaterEqual(
            report.exact_top1_rate,
            policy.randomized_exact_top1_rate,
        )
        self.assertLessEqual(
            report.mean_best_dps_regret_ratio,
            policy.randomized_mean_regret_ratio,
        )
        self.assertLessEqual(
            report.maximum_best_dps_regret_ratio,
            policy.randomized_maximum_regret_ratio,
        )


def _profile(wearer, cr_weight, em_weight, index):
    return GcsimOptimizerAnytimeStatProfile(
        wearer=wearer,
        profile_id=f"random_account_{index:03d}",
        stat_weights=tuple(
            float(cr_weight)
            if axis == "cr"
            else float(em_weight)
            if axis == "em"
            else 0.0
            for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
        ),
        main_scores=(),
        evidence_sha256="f" * 64,
        feature_labels=("randomized_release_corpus",),
    )


def _candidate_score(candidate, coefficients):
    return sum(
        _build_score(build.normalized_stats, weights)
        for build, weights in zip(
            candidate.builds,
            coefficients,
            strict=True,
        )
    )


def _proposal_score(proposal, coefficients):
    return sum(
        _build_score(
            candidate.materialized_build.normalized_stats,
            weights,
        )
        for candidate, weights in zip(
            proposal.wearer_candidates,
            coefficients,
            strict=True,
        )
    )


def _build_score(normalized_stats, weights):
    stats = {key: Decimal(value) for key, value in normalized_stats}
    cr_weight, em_weight = weights
    return (
        stats.get("cr", Decimal(0)) * cr_weight
        + stats.get("em", Decimal(0)) * em_weight
    )


if __name__ == "__main__":
    unittest.main()
