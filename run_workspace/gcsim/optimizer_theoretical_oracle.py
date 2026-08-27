"""Reduced exhaustive equal-investment theoretical package oracle."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import hashlib
from itertools import product
import json
from math import isclose, prod

from .farming_profile_config import (
    GcsimScreeningStatAllocation,
)
from .optimizer_config import (
    GcsimFiveStarMainStatLayout,
    render_five_star_main_stat_line,
)
from .optimizer_oracle import (
    GcsimOptimizerOracleScore,
    GcsimOptimizerReducedOracleError,
    GcsimOptimizerReducedOracleLimits,
)
from .optimizer_product_contracts import (
    GcsimFourPieceTargetPackage,
    GcsimOptimizerTargetPackage,
    GcsimOptimizerWearerIdentity,
    GcsimTwoPlusTwoTargetPackage,
)


GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalFourPieceOracleVariant:
    package: GcsimOptimizerTargetPackage
    main_stat_layout: GcsimFiveStarMainStatLayout
    allocation: GcsimScreeningStatAllocation
    branch_tags: tuple[str, ...] = ()
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
        ):
            raise GcsimOptimizerReducedOracleError(
                "unsupported theoretical oracle variant schema"
            )
        if not isinstance(
            self.package,
            (GcsimFourPieceTargetPackage, GcsimTwoPlusTwoTargetPackage),
        ):
            raise GcsimOptimizerReducedOracleError(
                "theoretical oracle variant requires a complete package"
            )
        _validate_layout_allocation(
            self.main_stat_layout,
            self.allocation,
        )
        tags = tuple(sorted(self.branch_tags))
        if len(set(tags)) != len(tags) or any(
            not tag or tag != tag.strip() for tag in tags
        ):
            raise GcsimOptimizerReducedOracleError(
                "branch_tags must be unique non-empty trimmed text"
            )
        object.__setattr__(self, "branch_tags", tags)

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "package": self.package.to_dict(),
            "main_stat_layout": self.main_stat_layout.to_dict(),
            "allocation": _allocation_dict(self.allocation),
            "branch_tags": list(self.branch_tags),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalFourPieceOracleStatState:
    main_stat_layout: GcsimFiveStarMainStatLayout
    allocation: GcsimScreeningStatAllocation
    branch_tags: tuple[str, ...] = ()
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
        ):
            raise GcsimOptimizerReducedOracleError(
                "unsupported theoretical stat-state schema"
            )
        _validate_layout_allocation(
            self.main_stat_layout,
            self.allocation,
        )
        tags = tuple(sorted(self.branch_tags))
        if len(set(tags)) != len(tags) or any(
            not tag or tag != tag.strip() for tag in tags
        ):
            raise GcsimOptimizerReducedOracleError(
                "branch_tags must be unique non-empty trimmed text"
            )
        object.__setattr__(self, "branch_tags", tags)

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "main_stat_layout": self.main_stat_layout.to_dict(),
            "allocation": _allocation_dict(self.allocation),
            "branch_tags": list(self.branch_tags),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalFourPieceOracleWearerDomain:
    wearer: GcsimOptimizerWearerIdentity
    packages: tuple[GcsimOptimizerTargetPackage, ...]
    stat_states: tuple[
        GcsimOptimizerTheoreticalFourPieceOracleStatState, ...
    ]
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
        ):
            raise GcsimOptimizerReducedOracleError(
                "unsupported theoretical wearer-domain schema"
            )
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerReducedOracleError("wearer must be typed")
        packages = tuple(self.packages)
        if not packages or any(
            not isinstance(
                item,
                (GcsimFourPieceTargetPackage, GcsimTwoPlusTwoTargetPackage),
            )
            for item in packages
        ):
            raise GcsimOptimizerReducedOracleError(
                "theoretical wearer domain requires complete packages"
            )
        if len({item.kind for item in packages}) != 1:
            raise GcsimOptimizerReducedOracleError(
                "one theoretical wearer domain cannot mix package shapes"
            )
        stat_states = tuple(self.stat_states)
        if not stat_states or any(
            not isinstance(
                item,
                GcsimOptimizerTheoreticalFourPieceOracleStatState,
            )
            for item in stat_states
        ):
            raise GcsimOptimizerReducedOracleError(
                "theoretical wearer domain requires typed stat states"
            )
        package_ids = tuple(item.identity_sha256 for item in packages)
        stat_state_ids = tuple(item.identity_sha256 for item in stat_states)
        if (
            len(set(package_ids)) != len(package_ids)
            or len(set(stat_state_ids)) != len(stat_state_ids)
        ):
            raise GcsimOptimizerReducedOracleError(
                "theoretical domain dimensions must be unique"
            )
        object.__setattr__(self, "packages", packages)
        object.__setattr__(self, "stat_states", stat_states)

    @property
    def variants(
        self,
    ) -> tuple[GcsimOptimizerTheoreticalFourPieceOracleVariant, ...]:
        return tuple(
            GcsimOptimizerTheoreticalFourPieceOracleVariant(
                package=package,
                main_stat_layout=stat_state.main_stat_layout,
                allocation=stat_state.allocation,
                branch_tags=stat_state.branch_tags,
            )
            for package, stat_state in product(
                self.packages,
                self.stat_states,
            )
        )

    @property
    def baseline_variant(self) -> GcsimOptimizerTheoreticalFourPieceOracleVariant:
        return self.variants[0]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "wearer": self.wearer.to_dict(),
            "packages": [item.to_dict() for item in self.packages],
            "stat_states": [item.to_dict() for item in self.stat_states],
            "cartesian_variant_count": len(self.variants),
            "baseline_variant_sha256": self.baseline_variant.identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalFourPieceOracleChoice:
    wearer: GcsimOptimizerWearerIdentity
    variant: GcsimOptimizerTheoreticalFourPieceOracleVariant
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
        ):
            raise GcsimOptimizerReducedOracleError(
                "unsupported theoretical oracle choice schema"
            )
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerReducedOracleError(
                "theoretical choice wearer must be typed"
            )
        if not isinstance(
            self.variant,
            GcsimOptimizerTheoreticalFourPieceOracleVariant,
        ):
            raise GcsimOptimizerReducedOracleError(
                "theoretical choice variant must be typed"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "wearer": self.wearer.to_dict(),
            "variant": self.variant.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalFourPieceOracleState:
    choices: tuple[GcsimOptimizerTheoreticalFourPieceOracleChoice, ...]
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
        ):
            raise GcsimOptimizerReducedOracleError(
                "unsupported theoretical oracle state schema"
            )
        choices = tuple(self.choices)
        if tuple(item.wearer.team_slot for item in choices) != (1, 2, 3, 4):
            raise GcsimOptimizerReducedOracleError(
                "theoretical oracle state requires four canonical wearers"
            )
        object.__setattr__(self, "choices", choices)

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "choices": [item.to_dict() for item in self.choices],
        }


TheoreticalOracleEvaluator = Callable[
    [GcsimOptimizerTheoreticalFourPieceOracleState],
    GcsimOptimizerOracleScore,
]


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalOracleEvaluation:
    ordinal: int
    change_count_from_baseline: int
    state: GcsimOptimizerTheoreticalFourPieceOracleState
    score: GcsimOptimizerOracleScore
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
        ):
            raise GcsimOptimizerReducedOracleError(
                "unsupported theoretical evaluation schema"
            )
        if (
            isinstance(self.ordinal, bool)
            or not isinstance(self.ordinal, int)
            or self.ordinal <= 0
        ):
            raise GcsimOptimizerReducedOracleError(
                "theoretical evaluation ordinal must be positive"
            )
        if (
            isinstance(self.change_count_from_baseline, bool)
            or not isinstance(self.change_count_from_baseline, int)
            or self.change_count_from_baseline not in (0, 1, 2, 3, 4)
        ):
            raise GcsimOptimizerReducedOracleError(
                "change_count_from_baseline must be 0 through 4"
            )

    @property
    def candidate_identity_sha256(self) -> str:
        return self.state.identity_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "ordinal": self.ordinal,
            "change_count_from_baseline": self.change_count_from_baseline,
            "state": self.state.to_dict(),
            "score": self.score.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalOracleCoverage:
    wearer_variant_counts: tuple[tuple[int, int], ...]
    exhaustive_state_count: int
    states_by_change_count: tuple[tuple[int, int], ...]
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
        ):
            raise GcsimOptimizerReducedOracleError(
                "unsupported theoretical coverage schema"
            )
        if tuple(slot for slot, _count in self.wearer_variant_counts) != (
            1,
            2,
            3,
            4,
        ):
            raise GcsimOptimizerReducedOracleError(
                "theoretical coverage requires canonical wearer slots"
            )
        for _slot, count in self.wearer_variant_counts:
            _require_positive_int(count, "wearer variant count")
        _require_positive_int(
            self.exhaustive_state_count,
            "exhaustive_state_count",
        )
        if tuple(
            change_count for change_count, _count in self.states_by_change_count
        ) != (0, 1, 2, 3, 4):
            raise GcsimOptimizerReducedOracleError(
                "change-count coverage must contain 0 through 4"
            )
        if (
            sum(count for _change_count, count in self.states_by_change_count)
            != self.exhaustive_state_count
        ):
            raise GcsimOptimizerReducedOracleError(
                "theoretical state coverage is incoherent"
            )
        if (
            prod(count for _slot, count in self.wearer_variant_counts)
            != self.exhaustive_state_count
        ):
            raise GcsimOptimizerReducedOracleError(
                "theoretical Cartesian coverage differs from wearer domains"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "wearer_variant_counts": dict(self.wearer_variant_counts),
            "exhaustive_state_count": self.exhaustive_state_count,
            "states_by_change_count": dict(self.states_by_change_count),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalFourPieceOracleResult:
    engine_binding_sha256: str
    catalog_fingerprint: str
    investment_signature: str
    limits: GcsimOptimizerReducedOracleLimits
    domains: tuple[
        GcsimOptimizerTheoreticalFourPieceOracleWearerDomain, ...
    ]
    coverage: GcsimOptimizerTheoreticalOracleCoverage
    evaluations: tuple[GcsimOptimizerTheoreticalOracleEvaluation, ...]
    winner: GcsimOptimizerTheoreticalOracleEvaluation
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION
        ):
            raise GcsimOptimizerReducedOracleError(
                "unsupported theoretical oracle result schema"
            )
        _require_sha256(self.engine_binding_sha256, "engine_binding_sha256")
        _require_sha256(self.catalog_fingerprint, "catalog_fingerprint")
        if not self.investment_signature:
            raise GcsimOptimizerReducedOracleError(
                "investment_signature must not be empty"
            )
        domains = tuple(self.domains)
        evaluations = tuple(self.evaluations)
        if tuple(item.wearer.team_slot for item in domains) != (1, 2, 3, 4):
            raise GcsimOptimizerReducedOracleError(
                "theoretical oracle result requires four canonical domains"
            )
        if len(evaluations) != self.coverage.exhaustive_state_count:
            raise GcsimOptimizerReducedOracleError(
                "theoretical evaluations differ from exhaustive coverage"
            )
        if self.winner not in evaluations:
            raise GcsimOptimizerReducedOracleError(
                "theoretical winner must belong to evaluations"
            )
        object.__setattr__(self, "domains", domains)
        object.__setattr__(self, "evaluations", evaluations)

    @property
    def winner_candidate_sha256(self) -> str:
        return self.winner.candidate_identity_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "engine_binding_sha256": self.engine_binding_sha256,
            "catalog_fingerprint": self.catalog_fingerprint,
            "investment_signature": self.investment_signature,
            "limits": self.limits.to_dict(),
            "domains": [item.to_dict() for item in self.domains],
            "coverage": self.coverage.to_dict(),
            "evaluations": [item.to_dict() for item in self.evaluations],
            "winner_candidate_sha256": self.winner_candidate_sha256,
        }


def run_gcsim_optimizer_theoretical_four_piece_oracle(
    domains: Sequence[
        GcsimOptimizerTheoreticalFourPieceOracleWearerDomain
    ],
    *,
    evaluator: TheoreticalOracleEvaluator,
    limits: GcsimOptimizerReducedOracleLimits | None = None,
) -> GcsimOptimizerTheoreticalFourPieceOracleResult:
    """Exhaustively evaluate a finite four-wearer equal-investment package domain."""

    domain_rows = tuple(domains)
    if (
        len(domain_rows) != 4
        or tuple(item.wearer.team_slot for item in domain_rows)
        != (1, 2, 3, 4)
    ):
        raise GcsimOptimizerReducedOracleError(
            "theoretical oracle requires four canonical wearer domains"
        )
    if not callable(evaluator):
        raise GcsimOptimizerReducedOracleError("evaluator must be callable")
    oracle_limits = limits or GcsimOptimizerReducedOracleLimits()
    if not isinstance(oracle_limits, GcsimOptimizerReducedOracleLimits):
        raise GcsimOptimizerReducedOracleError("limits must be typed")
    variants = tuple(
        variant
        for domain in domain_rows
        for variant in domain.variants
    )
    package_set_refs = tuple(
        set_ref
        for variant in variants
        for set_ref in (
            (variant.package.set_ref,)
            if isinstance(variant.package, GcsimFourPieceTargetPackage)
            else (variant.package.set_a, variant.package.set_b)
        )
    )
    engine_bindings = {
        set_ref.engine_binding_sha256 for set_ref in package_set_refs
    }
    catalog_fingerprints = {
        set_ref.catalog_fingerprint for set_ref in package_set_refs
    }
    investment_signatures = {
        variant.allocation.investment_signature for variant in variants
    }
    if (
        len(engine_bindings) != 1
        or len(catalog_fingerprints) != 1
        or len(investment_signatures) != 1
    ):
        raise GcsimOptimizerReducedOracleError(
            "theoretical oracle variants must share engine, catalog, and "
            "equal-investment identity"
        )
    state_count = prod(len(domain.variants) for domain in domain_rows)
    if state_count > oracle_limits.max_theoretical_states:
        raise GcsimOptimizerReducedOracleError(
            "reduced theoretical oracle domain exceeds max_theoretical_states"
        )

    evaluations: list[GcsimOptimizerTheoreticalOracleEvaluation] = []
    change_counts = Counter()
    objective_name = ""
    for ordinal, selected_variants in enumerate(
        product(*(domain.variants for domain in domain_rows)),
        start=1,
    ):
        state = GcsimOptimizerTheoreticalFourPieceOracleState(
            choices=tuple(
                GcsimOptimizerTheoreticalFourPieceOracleChoice(
                    wearer=domain.wearer,
                    variant=variant,
                )
                for domain, variant in zip(
                    domain_rows,
                    selected_variants,
                    strict=True,
                )
            )
        )
        change_count = sum(
            variant.identity_sha256
            != domain.baseline_variant.identity_sha256
            for domain, variant in zip(
                domain_rows,
                selected_variants,
                strict=True,
            )
        )
        try:
            score = evaluator(state)
        except Exception as exc:
            raise GcsimOptimizerReducedOracleError(
                "theoretical oracle evaluator failed at ordinal "
                f"{ordinal}: {exc}"
            ) from exc
        if not isinstance(score, GcsimOptimizerOracleScore):
            raise GcsimOptimizerReducedOracleError(
                "theoretical evaluator must return GcsimOptimizerOracleScore"
            )
        if objective_name and score.objective_name != objective_name:
            raise GcsimOptimizerReducedOracleError(
                "theoretical oracle evaluations must share one objective"
            )
        objective_name = score.objective_name
        change_counts[change_count] += 1
        evaluations.append(
            GcsimOptimizerTheoreticalOracleEvaluation(
                ordinal=ordinal,
                change_count_from_baseline=change_count,
                state=state,
                score=score,
            )
        )
    evaluation_rows = tuple(evaluations)
    coverage = GcsimOptimizerTheoreticalOracleCoverage(
        wearer_variant_counts=tuple(
            (domain.wearer.team_slot, len(domain.variants))
            for domain in domain_rows
        ),
        exhaustive_state_count=state_count,
        states_by_change_count=tuple(
            (change_count, change_counts[change_count])
            for change_count in range(5)
        ),
    )
    winner = min(
        evaluation_rows,
        key=lambda item: (
            -item.score.objective_value,
            item.candidate_identity_sha256,
        ),
    )
    return GcsimOptimizerTheoreticalFourPieceOracleResult(
        engine_binding_sha256=next(iter(engine_bindings)),
        catalog_fingerprint=next(iter(catalog_fingerprints)),
        investment_signature=next(iter(investment_signatures)),
        limits=oracle_limits,
        domains=domain_rows,
        coverage=coverage,
        evaluations=evaluation_rows,
        winner=winner,
    )


def _allocation_dict(
    allocation: GcsimScreeningStatAllocation,
) -> dict[str, object]:
    return {
        "profile_id": allocation.profile_id,
        "four_star_piece_count": allocation.four_star_piece_count,
        "fixed_substats_count": allocation.fixed_substats_count,
        "total_liquid_substats": allocation.total_liquid_substats,
        "rarity_modifier": allocation.rarity_modifier,
        "investment_signature": allocation.investment_signature,
        "rolls": [
            {
                "axis_key": item.axis_key,
                "fixed_rolls": item.fixed_rolls,
                "liquid_rolls": item.liquid_rolls,
                "liquid_cap": item.liquid_cap,
                "roll_value": item.roll_value,
                "rarity_modifier": item.rarity_modifier,
            }
            for item in allocation.rolls
        ],
    }


def _validate_layout_allocation(
    layout: GcsimFiveStarMainStatLayout,
    allocation: GcsimScreeningStatAllocation,
) -> None:
    if not isinstance(layout, GcsimFiveStarMainStatLayout):
        raise GcsimOptimizerReducedOracleError(
            "main_stat_layout must be typed"
        )
    try:
        render_five_star_main_stat_line("oracle", layout)
    except ValueError as exc:
        raise GcsimOptimizerReducedOracleError(
            f"illegal theoretical main-stat layout: {exc}"
        ) from exc
    if not isinstance(allocation, GcsimScreeningStatAllocation):
        raise GcsimOptimizerReducedOracleError(
            "allocation must be a typed equal-investment allocation"
        )
    if allocation.four_star_piece_count != 0 or not isclose(
        allocation.rarity_modifier,
        1.0,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise GcsimOptimizerReducedOracleError(
            "Milestone 3T uses the default five-star investment domain"
        )
    main_counts = Counter(("hp", "atk", layout.sands, layout.goblet, layout.circlet))
    inferred_individual_caps = {
        item.liquid_cap
        + allocation.fixed_substats_count * main_counts[item.axis_key]
        for item in allocation.rolls
    }
    if len(inferred_individual_caps) != 1:
        raise GcsimOptimizerReducedOracleError(
            "equal-investment allocation is not legal for its main-stat layout"
        )


def _require_positive_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GcsimOptimizerReducedOracleError(
            f"{field_name} must be a positive integer"
        )


def _require_sha256(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GcsimOptimizerReducedOracleError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "GCSIM_OPTIMIZER_THEORETICAL_FOUR_PIECE_ORACLE_SCHEMA_VERSION",
    "GcsimOptimizerTheoreticalFourPieceOracleChoice",
    "GcsimOptimizerTheoreticalFourPieceOracleResult",
    "GcsimOptimizerTheoreticalFourPieceOracleState",
    "GcsimOptimizerTheoreticalFourPieceOracleStatState",
    "GcsimOptimizerTheoreticalFourPieceOracleVariant",
    "GcsimOptimizerTheoreticalFourPieceOracleWearerDomain",
    "GcsimOptimizerTheoreticalOracleCoverage",
    "GcsimOptimizerTheoreticalOracleEvaluation",
    "TheoreticalOracleEvaluator",
    "run_gcsim_optimizer_theoretical_four_piece_oracle",
]
