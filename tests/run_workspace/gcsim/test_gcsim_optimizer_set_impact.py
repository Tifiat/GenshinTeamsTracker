from __future__ import annotations

from dataclasses import replace
import unittest

from run_workspace.gcsim.optimizer_anytime_response import (
    GcsimOptimizerAnytimeResponseResult,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimFourPieceTargetPackage,
    GcsimOptimizerWearerTarget,
)
from run_workspace.gcsim.optimizer_set_impact import (
    GcsimOptimizerSetImpactClassification,
    GcsimOptimizerSetImpactPlan,
    GcsimOptimizerSingleTwoPieceImpactTarget,
    discover_gcsim_optimizer_set_impacts,
)
from run_workspace.gcsim.optimizer_stat_response import (
    GCSIM_SET_RESPONSE_CAPABILITY,
    GCSIM_STAT_RESPONSE_ROLL_VALUES,
    GcsimSetResponseChange,
    GcsimStatResponseObjective,
    GcsimStatResponseTarget,
    build_gcsim_stat_response_probe_request,
    parse_gcsim_stat_response_result,
)

from ._optimizer_oracle_fixtures import build_oracle_account_environment
from .test_gcsim_optimizer_anytime_selected_service import (
    _test_response_profiles,
)


class GcsimOptimizerSetImpactTests(unittest.TestCase):
    def setUp(self) -> None:
        environment = build_oracle_account_environment()
        self.wearers = environment.wearers
        self.engine = replace(
            environment.engine,
            capabilities=(
                *environment.engine.capabilities,
                GCSIM_SET_RESPONSE_CAPABILITY,
            ),
        )
        self.targets = tuple(
            GcsimOptimizerWearerTarget(
                wearer,
                GcsimFourPieceTargetPackage(set_ref),
            )
            for wearer, set_ref in zip(
                environment.wearers[:3],
                environment.set_refs[:3],
                strict=True,
            )
        )
        self.component_target = GcsimOptimizerSingleTwoPieceImpactTarget(
            wearer=environment.wearers[0],
            set_ref=environment.set_refs[0],
        )
        baseline_request = build_gcsim_stat_response_probe_request(
            context_sha256="a" * 64,
            objective=GcsimStatResponseObjective.DPS,
        )
        self.response = GcsimOptimizerAnytimeResponseResult(
            profiles=_test_response_profiles(
                environment.wearers,
                evidence_sha256="b" * 64,
            ),
            synthetic_baseline_changes=baseline_request.baseline_changes,
            synthetic_master_seed=123,
            planned_probe_count=1,
            successful_probe_count=1,
            failed_probe_count=0,
            cache_hit_count=0,
            evidence_sha256="b" * 64,
            elapsed_seconds=0.0,
        )
        self.runner = _SetImpactRunner(
            positive_set_key=environment.set_refs[0].gcsim_set_key,
            uncertain_set_key=environment.set_refs[1].gcsim_set_key,
        )

    def test_set_change_is_a_versioned_typed_union_member(self) -> None:
        change = GcsimSetResponseChange(
            character_index=3,
            set_key="noblesse",
            set_count=4,
        )
        self.assertEqual(
            change.to_dict(),
            {
                "character_index": 3,
                "stat": "",
                "mode": "",
                "value": 0,
                "set_key": "noblesse",
                "set_count": 4,
            },
        )

    def test_positive_uncertain_and_proven_negligible_are_distinct(self) -> None:
        result = discover_gcsim_optimizer_set_impacts(
            engine_context=self.engine,
            prepared_config_text=_config(),
            targets=self.targets,
            response=self.response,
            stat_response_target=GcsimStatResponseTarget(
                objective=GcsimStatResponseObjective.DPS,
                target_sha256="c" * 64,
            ),
            plan=GcsimOptimizerSetImpactPlan(
                iterations=8,
                enable_crit_headroom_panel=True,
                enable_team_interaction_panel=True,
            ),
            stat_response_runner=self.runner,
        )
        by_set = {
            row.target.package.set_ref.gcsim_set_key: row
            for row in result.rows
        }
        self.assertEqual(
            by_set[self.targets[0].package.set_ref.gcsim_set_key].classification,
            GcsimOptimizerSetImpactClassification.PERSONAL_AND_TEAM_POSITIVE,
        )
        self.assertEqual(
            by_set[self.targets[1].package.set_ref.gcsim_set_key].classification,
            GcsimOptimizerSetImpactClassification.UNCERTAIN_RETAINED,
        )
        self.assertEqual(
            by_set[self.targets[2].package.set_ref.gcsim_set_key].classification,
            GcsimOptimizerSetImpactClassification.NEGLIGIBLE,
        )
        self.assertEqual(result.batch_count, 3)
        payload = result.to_dict()
        self.assertEqual(payload["batch_count"], 3)
        self.assertEqual(len(payload["rows"]), len(result.rows))
        self.assertEqual(
            payload["response_evidence_sha256"],
            self.response.evidence_sha256,
        )
        self.assertEqual(len(self.runner.requests), 3)
        self.assertIsNotNone(result.semantic_manifest)
        self.assertEqual(len(result.runtime_observations), 6)
        self.assertEqual(len(result.interaction_observations), 3)
        self.assertTrue(
            all(
                item.classification
                in {"non_additive", "additive_within_noise", "uncertain"}
                for item in result.interaction_observations
            )
        )
        balanced_cr = _raw_cr_values(
            self.runner.requests[0].baseline_changes
        )
        headroom_cr = _raw_cr_values(
            self.runner.requests[1].baseline_changes
        )
        self.assertEqual(balanced_cr, (0.95, 0.95, 0.95, 0.95))
        self.assertEqual(headroom_cr, (0.0, 0.0, 0.0, 0.0))
        for character_index in range(4):
            self.assertAlmostEqual(
                _abstract_roll_budget(
                    self.runner.requests[0].baseline_changes,
                    character_index=character_index,
                ),
                _abstract_roll_budget(
                    self.runner.requests[1].baseline_changes,
                    character_index=character_index,
                ),
            )

    def test_single_two_piece_target_emits_exact_count_two_change(self) -> None:
        result = discover_gcsim_optimizer_set_impacts(
            engine_context=self.engine,
            prepared_config_text=_config(),
            targets=(self.component_target,),
            response=self.response,
            stat_response_target=GcsimStatResponseTarget(
                objective=GcsimStatResponseObjective.DPS,
                target_sha256="c" * 64,
            ),
            plan=GcsimOptimizerSetImpactPlan(
                iterations=8,
                enable_crit_headroom_panel=False,
            ),
            stat_response_runner=self.runner,
        )

        self.assertIs(result.rows[0].target, self.component_target)
        self.assertEqual(len(self.runner.requests), 1)
        changes = tuple(
            change
            for intervention in self.runner.requests[0].interventions
            for change in intervention.changes
            if isinstance(change, GcsimSetResponseChange)
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].set_count, 2)


class _SetImpactRunner:
    def __init__(
        self,
        *,
        positive_set_key: str,
        uncertain_set_key: str,
    ) -> None:
        self.positive_set_key = positive_set_key
        self.uncertain_set_key = uncertain_set_key
        self.requests = []

    def __call__(self, *, request, **_kwargs):
        self.requests.append(request)
        interventions = []
        for intervention in request.interventions:
            set_change = next(
                item
                for item in intervention.changes
                if isinstance(item, GcsimSetResponseChange)
            )
            if set_change.set_key == self.positive_set_key:
                team_mean, personal_mean, standard_error = 100.0, 80.0, 0.0
            elif set_change.set_key == self.uncertain_set_key:
                team_mean, personal_mean, standard_error = 0.0, 0.0, 10.0
            else:
                team_mean, personal_mean, standard_error = 0.0, 0.0, 0.0
            character_means = [0.0, 0.0, 0.0, 0.0]
            character_means[set_change.character_index] = personal_mean
            interventions.append(
                _observation(
                    intervention.intervention_id,
                    paired=True,
                    team_mean=team_mean,
                    character_means=character_means,
                    standard_error=standard_error,
                )
            )
        return parse_gcsim_stat_response_result(
            {
                "schema_version": 2,
                "context_sha256": request.context_sha256,
                "request_sha256": request.request_sha256,
                "objective": request.objective.value,
                "ignore_burst_energy": True,
                "character_keys": [
                    "alpha",
                    "beta",
                    "gamma",
                    "delta",
                ],
                "seed_panel_sha256": "d" * 64,
                "source": _observation("source", paired=False),
                "baseline": _observation("baseline", paired=True),
                "interventions": interventions,
            }
        )


def _observation(
    observation_id: str,
    *,
    paired: bool,
    team_mean: float = 100_000.0,
    character_means=(40_000.0, 30_000.0, 20_000.0, 10_000.0),
    standard_error: float = 0.0,
):
    payload = {
        "id": observation_id,
        "samples": [
            {
                "seed": "11",
                "duration_frames": 600,
                "duration_seconds": 10.0,
                "team_expected_damage": 1_000_000.0,
                "team_expected_dps": 100_000.0,
                "character_expected_damage": [
                    400_000.0,
                    300_000.0,
                    200_000.0,
                    100_000.0,
                ],
                "character_expected_dps": [
                    40_000.0,
                    30_000.0,
                    20_000.0,
                    10_000.0,
                ],
            }
        ],
        "summary": _summary(
            100_000.0,
            (40_000.0, 30_000.0, 20_000.0, 10_000.0),
        ),
    }
    if paired:
        payload["paired_delta"] = _summary(
            team_mean,
            character_means,
            standard_error=standard_error,
        )
    return payload


def _summary(
    team_mean,
    character_means,
    *,
    standard_error: float = 0.0,
):
    return {
        "duration_seconds": _estimate(10.0),
        "team_expected_damage": _estimate(1_000_000.0),
        "team_expected_dps": _estimate(
            team_mean,
            standard_error=standard_error,
        ),
        "character_expected_dps": [
            _estimate(value, standard_error=standard_error)
            for value in character_means
        ],
    }


def _estimate(mean, *, standard_error: float = 0.0):
    return {
        "count": 1,
        "mean": mean,
        "sample_sd": 0.0,
        "standard_error": standard_error,
    }


def _raw_cr_values(changes):
    return tuple(
        item.value for item in changes if item.stat == "cr"
    )


def _abstract_roll_budget(changes, *, character_index: int) -> float:
    return sum(
        item.value / GCSIM_STAT_RESPONSE_ROLL_VALUES[item.stat]
        for item in changes
        if item.character_index == character_index
        and item.stat in GCSIM_STAT_RESPONSE_ROLL_VALUES
    )


def _config() -> str:
    return """\
alpha char lvl=90/90 cons=0 talent=1,1,1;
alpha add weapon="dullblade" refine=1 lvl=1/20;
alpha add set="oraclesetalpha" count=4;
beta char lvl=90/90 cons=0 talent=1,1,1;
beta add weapon="dullblade" refine=1 lvl=1/20;
gamma char lvl=90/90 cons=0 talent=1,1,1;
gamma add weapon="dullblade" refine=1 lvl=1/20;
delta char lvl=90/90 cons=0 talent=1,1,1;
delta add weapon="dullblade" refine=1 lvl=1/20;
"""


if __name__ == "__main__":
    unittest.main()
