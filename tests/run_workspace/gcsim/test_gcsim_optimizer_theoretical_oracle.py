from __future__ import annotations

import unittest

from run_workspace.gcsim.farming_profile_config import (
    allocate_gcsim_screening_substats,
    build_default_gcsim_screening_profile_bank,
)
from run_workspace.gcsim.optimizer_config import (
    GcsimFiveStarMainStatLayout,
)
from run_workspace.gcsim.optimizer_oracle import (
    GcsimOptimizerOraclePruningStage,
    GcsimOptimizerOracleScore,
    GcsimOptimizerReducedOracleError,
    GcsimOptimizerReducedOracleLimits,
    audit_gcsim_optimizer_oracle_winner_survival,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimFourPieceTargetPackage,
    GcsimOptimizerSetReference,
    GcsimOptimizerWearerIdentity,
)
from run_workspace.gcsim.optimizer_theoretical_oracle import (
    GcsimOptimizerTheoreticalFourPieceOracleStatState,
    GcsimOptimizerTheoreticalFourPieceOracleVariant,
    GcsimOptimizerTheoreticalFourPieceOracleWearerDomain,
    run_gcsim_optimizer_theoretical_four_piece_oracle,
)


class GcsimOptimizerTheoreticalFourPieceOracleTests(unittest.TestCase):
    def test_adversarial_domain_enumerates_every_coordinated_change(self) -> None:
        domains = _domains()

        result = run_gcsim_optimizer_theoretical_four_piece_oracle(
            domains,
            evaluator=_adversarial_score,
        )

        self.assertEqual(
            result.coverage.wearer_variant_counts,
            ((1, 6), (2, 2), (3, 2), (4, 4)),
        )
        self.assertEqual(result.coverage.exhaustive_state_count, 96)
        self.assertEqual(
            result.coverage.states_by_change_count,
            ((0, 1), (1, 10), (2, 32), (3, 38), (4, 15)),
        )
        self.assertEqual(result.winner.change_count_from_baseline, 4)
        winner_tags = tuple(
            tuple(sorted(_choice_tags(choice)))
            for choice in result.winner.state.choices
        )
        self.assertEqual(
            winner_tags,
            (
                ("crit_cap", "crit_package"),
                ("rotation_threshold",),
                ("em_ownership",),
                ("healing_team_buff",),
            ),
        )
        self.assertEqual(
            result.winner.state.choices[0].variant.package.set_ref.gcsim_set_key,
            "oraclealphacrit",
        )
        evaluated_tags = {
            tag
            for row in result.evaluations
            for choice in row.state.choices
            for tag in _choice_tags(choice)
        }
        self.assertTrue(
            {
                "crit_cap",
                "rotation_threshold",
                "em_ownership",
                "hp_scaling",
                "def_scaling",
                "healing_team_buff",
                "duplicate_nonstacking_buff",
            }.issubset(evaluated_tags)
        )

    def test_oracle_winner_survival_reports_first_pruning_removal(self) -> None:
        result = run_gcsim_optimizer_theoretical_four_piece_oracle(
            _domains(),
            evaluator=_adversarial_score,
        )
        all_candidates = tuple(
            row.candidate_identity_sha256 for row in result.evaluations
        )
        without_winner = tuple(
            value
            for value in all_candidates
            if value != result.winner_candidate_sha256
        )

        audit = audit_gcsim_optimizer_oracle_winner_survival(
            result.winner_candidate_sha256,
            (
                GcsimOptimizerOraclePruningStage(
                    "legality",
                    all_candidates,
                ),
                GcsimOptimizerOraclePruningStage(
                    "surrogate_bound",
                    without_winner,
                ),
                GcsimOptimizerOraclePruningStage(
                    "finalists",
                    without_winner[:5],
                ),
            ),
        )

        self.assertFalse(audit.survived_all)
        self.assertEqual(audit.removed_at_stage, "surrogate_bound")
        self.assertEqual(
            tuple(item.winner_survived for item in audit.stages),
            (True, False, False),
        )

    def test_equal_investment_and_reduced_size_fail_closed(self) -> None:
        domains = _domains()

        with self.assertRaisesRegex(
            GcsimOptimizerReducedOracleError,
            "max_theoretical_states",
        ):
            run_gcsim_optimizer_theoretical_four_piece_oracle(
                domains,
                evaluator=_adversarial_score,
                limits=GcsimOptimizerReducedOracleLimits(
                    max_theoretical_states=95,
                ),
            )

        bank = build_default_gcsim_screening_profile_bank()
        changed_allocation = allocate_gcsim_screening_substats(
            GcsimFiveStarMainStatLayout("atk%", "pyro%", "cr"),
            bank.profile("baseline"),
            total_liquid_substats=19,
        )
        first_domain = domains[0]
        changed_stat_state = GcsimOptimizerTheoreticalFourPieceOracleStatState(
            main_stat_layout=first_domain.stat_states[0].main_stat_layout,
            allocation=changed_allocation,
        )
        mixed_domains = (
            GcsimOptimizerTheoreticalFourPieceOracleWearerDomain(
                wearer=first_domain.wearer,
                packages=first_domain.packages,
                stat_states=(
                    changed_stat_state,
                    *first_domain.stat_states[1:],
                ),
            ),
            *domains[1:],
        )
        with self.assertRaisesRegex(
            GcsimOptimizerReducedOracleError,
            "equal-investment identity",
        ):
            run_gcsim_optimizer_theoretical_four_piece_oracle(
                mixed_domains,
                evaluator=_adversarial_score,
            )

    def test_illegal_main_stat_layout_is_rejected_at_domain_boundary(self) -> None:
        bank = build_default_gcsim_screening_profile_bank()
        invalid_layout = GcsimFiveStarMainStatLayout(
            "pyro%",
            "pyro%",
            "cr",
        )
        allocation = allocate_gcsim_screening_substats(
            GcsimFiveStarMainStatLayout("atk%", "pyro%", "cr"),
            bank.profile("baseline"),
        )

        with self.assertRaisesRegex(
            GcsimOptimizerReducedOracleError,
            "illegal theoretical main-stat layout",
        ):
            GcsimOptimizerTheoreticalFourPieceOracleVariant(
                package=_package("invalid"),
                main_stat_layout=invalid_layout,
                allocation=allocation,
            )


def _domains() -> tuple[
    GcsimOptimizerTheoreticalFourPieceOracleWearerDomain, ...
]:
    bank = build_default_gcsim_screening_profile_bank()
    wearers = tuple(
        GcsimOptimizerWearerIdentity(
            team_slot=index,
            account_character_id=None,
            gcsim_character_key=key,
        )
        for index, key in enumerate(
            ("alpha", "beta", "gamma", "delta"),
            start=1,
        )
    )

    def stat_state(
        layout: GcsimFiveStarMainStatLayout,
        profile_id: str,
        *tags: str,
    ) -> GcsimOptimizerTheoreticalFourPieceOracleStatState:
        return GcsimOptimizerTheoreticalFourPieceOracleStatState(
            main_stat_layout=layout,
            allocation=allocate_gcsim_screening_substats(
                layout,
                bank.profile(profile_id),
            ),
            branch_tags=tags,
        )

    return (
        GcsimOptimizerTheoreticalFourPieceOracleWearerDomain(
            wearer=wearers[0],
            packages=(
                _package("alpha_base"),
                _package("alpha_crit"),
                _package("alpha_duplicate"),
            ),
            stat_states=(
                stat_state(
                    GcsimFiveStarMainStatLayout("atk%", "pyro%", "cr"),
                    "baseline",
                ),
                stat_state(
                    GcsimFiveStarMainStatLayout("atk%", "pyro%", "cd"),
                    "focus/cr",
                    "crit_cap",
                ),
            ),
        ),
        GcsimOptimizerTheoreticalFourPieceOracleWearerDomain(
            wearer=wearers[1],
            packages=(_package("beta_base"),),
            stat_states=(
                stat_state(
                    GcsimFiveStarMainStatLayout("atk%", "electro%", "cr"),
                    "baseline",
                ),
                stat_state(
                    GcsimFiveStarMainStatLayout("atk%", "electro%", "cd"),
                    "focus/atk%",
                    "rotation_threshold",
                ),
            ),
        ),
        GcsimOptimizerTheoreticalFourPieceOracleWearerDomain(
            wearer=wearers[2],
            packages=(_package("gamma_base"),),
            stat_states=(
                stat_state(
                    GcsimFiveStarMainStatLayout("atk%", "dendro%", "cr"),
                    "baseline",
                ),
                stat_state(
                    GcsimFiveStarMainStatLayout("em", "em", "em"),
                    "focus/em",
                    "em_ownership",
                ),
            ),
        ),
        GcsimOptimizerTheoreticalFourPieceOracleWearerDomain(
            wearer=wearers[3],
            packages=(_package("delta_base"),),
            stat_states=(
                stat_state(
                    GcsimFiveStarMainStatLayout("atk%", "hydro%", "cr"),
                    "baseline",
                ),
                stat_state(
                    GcsimFiveStarMainStatLayout("hp%", "hp%", "hp%"),
                    "focus/hp%",
                    "hp_scaling",
                ),
                stat_state(
                    GcsimFiveStarMainStatLayout("def%", "def%", "def%"),
                    "focus/def%",
                    "def_scaling",
                ),
                stat_state(
                    GcsimFiveStarMainStatLayout("hp%", "hp%", "heal"),
                    "focus/hp%",
                    "healing_team_buff",
                ),
            ),
        ),
    )


def _adversarial_score(state) -> GcsimOptimizerOracleScore:
    tags = {
        tag
        for choice in state.choices
        for tag in _choice_tags(choice)
    }
    value = 1000.0
    value += 50.0 if "crit_cap" in tags else 0.0
    value += 5.0 if "crit_package" in tags else 0.0
    value += 20.0 if "duplicate_nonstacking_buff" in tags else 0.0
    value += 100.0 if "rotation_threshold" in tags else 0.0
    value += 20.0 if "em_ownership" in tags else 0.0
    value += 50.0 if "hp_scaling" in tags else 0.0
    value += 60.0 if "def_scaling" in tags else 0.0
    value += 90.0 if "healing_team_buff" in tags else 0.0
    if {"rotation_threshold", "em_ownership"}.issubset(tags):
        value += 150.0
    if {
        "duplicate_nonstacking_buff",
        "healing_team_buff",
    }.issubset(tags):
        value -= 80.0
    return GcsimOptimizerOracleScore(
        objective_name="synthetic_team_dps",
        objective_value=value,
        evidence_sha256=state.identity_sha256,
    )


def _choice_tags(choice) -> set[str]:
    tags = set(choice.variant.branch_tags)
    package_key = choice.variant.package.set_ref.gcsim_set_key
    if package_key == "oraclealphacrit":
        tags.add("crit_package")
    if package_key == "oraclealphaduplicate":
        tags.add("duplicate_nonstacking_buff")
    return tags


def _package(key: str) -> GcsimFourPieceTargetPackage:
    normalized = key.replace("_", "")
    return GcsimFourPieceTargetPackage(
        GcsimOptimizerSetReference(
            set_uid=f"Oracle{key.title()}",
            gcsim_set_key=f"oracle{normalized}",
            engine_binding_sha256="3" * 64,
            catalog_fingerprint="4" * 64,
        )
    )


if __name__ == "__main__":
    unittest.main()
