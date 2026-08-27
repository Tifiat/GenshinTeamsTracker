"""Typed quality evidence for the optimizer release gate.

The gate deliberately compares production-retained identities with a reduced
exhaustive oracle.  It does not claim that a bounded production search is a
global mathematical proof for an unrestricted account inventory.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Iterable

from .optimizer_oracle import (
    GcsimOptimizerOraclePruningStage,
    audit_gcsim_optimizer_oracle_winner_survival,
)


GCSIM_OPTIMIZER_RELEASE_GATE_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_PROVISIONAL_RELEASE_POLICY_SCHEMA_VERSION = 1


class GcsimOptimizerReleaseGateError(ValueError):
    """Raised when quality evidence is incomplete or internally inconsistent."""


class GcsimOptimizerRuntimeKind(str, Enum):
    SELECTED_COLD_FIRST_SAVEABLE = "selected_cold_first_saveable"
    SELECTED_COLD_TERMINAL = "selected_cold_terminal"
    SELECTED_WARM_TERMINAL = "selected_warm_terminal"
    THEORETICAL_FOUR_PIECE_COLD_TERMINAL = (
        "theoretical_four_piece_cold_terminal"
    )
    THEORETICAL_FOUR_PIECE_WARM_TERMINAL = (
        "theoretical_four_piece_warm_terminal"
    )
    THEORETICAL_TWO_PLUS_TWO_COLD_TERMINAL = (
        "theoretical_two_plus_two_cold_terminal"
    )
    THEORETICAL_TWO_PLUS_TWO_WARM_TERMINAL = (
        "theoretical_two_plus_two_warm_terminal"
    )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerProvisionalReleasePolicy:
    """User-approved first calibration point, not a permanent product SLA."""

    selected_cold_first_saveable_seconds: Decimal = Decimal("150")
    selected_cold_terminal_seconds: Decimal = Decimal("300")
    selected_warm_terminal_seconds: Decimal = Decimal("30")
    theoretical_cold_terminal_seconds: Decimal = Decimal("180")
    theoretical_warm_terminal_seconds: Decimal = Decimal("20")
    randomized_exact_top1_rate: Decimal = Decimal("0.95")
    randomized_mean_regret_ratio: Decimal = Decimal("0.005")
    randomized_maximum_regret_ratio: Decimal = Decimal("0.02")
    mandatory_cases_require_strict_top1: bool = True
    provisional: bool = True
    schema_version: int = (
        GCSIM_OPTIMIZER_PROVISIONAL_RELEASE_POLICY_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_PROVISIONAL_RELEASE_POLICY_SCHEMA_VERSION
        ):
            raise GcsimOptimizerReleaseGateError(
                "unsupported provisional release policy schema"
            )
        for field_name in (
            "selected_cold_first_saveable_seconds",
            "selected_cold_terminal_seconds",
            "selected_warm_terminal_seconds",
            "theoretical_cold_terminal_seconds",
            "theoretical_warm_terminal_seconds",
        ):
            value = Decimal(getattr(self, field_name))
            if not value.is_finite() or value <= 0:
                raise GcsimOptimizerReleaseGateError(
                    f"{field_name} must be finite and positive"
                )
            object.__setattr__(self, field_name, value)
        for field_name in (
            "randomized_exact_top1_rate",
            "randomized_mean_regret_ratio",
            "randomized_maximum_regret_ratio",
        ):
            value = Decimal(getattr(self, field_name))
            if not value.is_finite() or not 0 <= value <= 1:
                raise GcsimOptimizerReleaseGateError(
                    f"{field_name} must be in [0, 1]"
                )
            object.__setattr__(self, field_name, value)
        if (
            self.randomized_mean_regret_ratio
            > self.randomized_maximum_regret_ratio
        ):
            raise GcsimOptimizerReleaseGateError(
                "mean regret threshold cannot exceed maximum regret threshold"
            )
        if not isinstance(self.mandatory_cases_require_strict_top1, bool):
            raise GcsimOptimizerReleaseGateError(
                "mandatory strict-top1 flag must be boolean"
            )
        if not isinstance(self.provisional, bool):
            raise GcsimOptimizerReleaseGateError(
                "provisional flag must be boolean"
            )

    def runtime_limit(self, kind: GcsimOptimizerRuntimeKind) -> Decimal:
        if not isinstance(kind, GcsimOptimizerRuntimeKind):
            raise GcsimOptimizerReleaseGateError("runtime kind must be typed")
        if kind is GcsimOptimizerRuntimeKind.SELECTED_COLD_FIRST_SAVEABLE:
            return self.selected_cold_first_saveable_seconds
        if kind is GcsimOptimizerRuntimeKind.SELECTED_COLD_TERMINAL:
            return self.selected_cold_terminal_seconds
        if kind is GcsimOptimizerRuntimeKind.SELECTED_WARM_TERMINAL:
            return self.selected_warm_terminal_seconds
        if kind in {
            GcsimOptimizerRuntimeKind.THEORETICAL_FOUR_PIECE_COLD_TERMINAL,
            GcsimOptimizerRuntimeKind.THEORETICAL_TWO_PLUS_TWO_COLD_TERMINAL,
        }:
            return self.theoretical_cold_terminal_seconds
        return self.theoretical_warm_terminal_seconds

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "provisional": self.provisional,
            "selected_cold_first_saveable_seconds": str(
                self.selected_cold_first_saveable_seconds
            ),
            "selected_cold_terminal_seconds": str(
                self.selected_cold_terminal_seconds
            ),
            "selected_warm_terminal_seconds": str(
                self.selected_warm_terminal_seconds
            ),
            "theoretical_cold_terminal_seconds": str(
                self.theoretical_cold_terminal_seconds
            ),
            "theoretical_warm_terminal_seconds": str(
                self.theoretical_warm_terminal_seconds
            ),
            "randomized_exact_top1_rate": str(
                self.randomized_exact_top1_rate
            ),
            "randomized_mean_regret_ratio": str(
                self.randomized_mean_regret_ratio
            ),
            "randomized_maximum_regret_ratio": str(
                self.randomized_maximum_regret_ratio
            ),
            "mandatory_cases_require_strict_top1": (
                self.mandatory_cases_require_strict_top1
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerRuntimeEvidence:
    kind: GcsimOptimizerRuntimeKind
    elapsed_seconds: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.kind, GcsimOptimizerRuntimeKind):
            raise GcsimOptimizerReleaseGateError("runtime kind must be typed")
        elapsed = Decimal(self.elapsed_seconds)
        if not elapsed.is_finite() or elapsed < 0:
            raise GcsimOptimizerReleaseGateError(
                "runtime evidence must be finite and non-negative"
            )
        object.__setattr__(self, "elapsed_seconds", elapsed)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "elapsed_seconds": str(self.elapsed_seconds),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerQualityRank:
    candidate_identity_sha256: str
    dps: Decimal

    def __post_init__(self) -> None:
        _require_sha256(self.candidate_identity_sha256)
        value = Decimal(self.dps)
        if not value.is_finite() or value < 0:
            raise GcsimOptimizerReleaseGateError("quality DPS must be finite and non-negative")
        object.__setattr__(self, "dps", value)

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_identity_sha256": self.candidate_identity_sha256,
            "dps": str(self.dps),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerQualityCase:
    case_id: str
    oracle_ranking: tuple[GcsimOptimizerQualityRank, ...]
    production_ranking_sha256s: tuple[str, ...]
    pruning_stages: tuple[GcsimOptimizerOraclePruningStage, ...]
    top_n: int

    def __post_init__(self) -> None:
        if not self.case_id or self.case_id != self.case_id.strip():
            raise GcsimOptimizerReleaseGateError("case_id must be non-empty and trimmed")
        oracle = tuple(self.oracle_ranking)
        production = tuple(self.production_ranking_sha256s)
        stages = tuple(self.pruning_stages)
        if not oracle:
            raise GcsimOptimizerReleaseGateError("oracle ranking must be non-empty")
        if len({row.candidate_identity_sha256 for row in oracle}) != len(oracle):
            raise GcsimOptimizerReleaseGateError("oracle ranking identities must be unique")
        if tuple(sorted(oracle, key=lambda row: (-row.dps, row.candidate_identity_sha256))) != oracle:
            raise GcsimOptimizerReleaseGateError("oracle ranking must use DPS-descending canonical order")
        if len(set(production)) != len(production):
            raise GcsimOptimizerReleaseGateError("production ranking identities must be unique")
        for value in production:
            _require_sha256(value)
        if isinstance(self.top_n, bool) or not isinstance(self.top_n, int) or self.top_n <= 0:
            raise GcsimOptimizerReleaseGateError("top_n must be positive")
        object.__setattr__(self, "oracle_ranking", oracle)
        object.__setattr__(self, "production_ranking_sha256s", production)
        object.__setattr__(self, "pruning_stages", stages)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerQualityMetrics:
    case_id: str
    exact_top1: bool
    oracle_winner_survived_all_stages: bool
    oracle_winner_removed_at_stage: str
    top_n: int
    top_n_recall: Decimal
    best_dps_regret: Decimal
    best_dps_regret_ratio: Decimal
    maximum_rankwise_dps_miss: Decimal
    missing_oracle_top_n_sha256s: tuple[str, ...]
    schema_version: int = GCSIM_OPTIMIZER_RELEASE_GATE_SCHEMA_VERSION

    @property
    def strict_gate_passed(self) -> bool:
        return (
            self.exact_top1
            and self.oracle_winner_survived_all_stages
            and self.top_n_recall == Decimal(1)
            and self.best_dps_regret == Decimal(0)
            and self.maximum_rankwise_dps_miss == Decimal(0)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "strict_gate_passed": self.strict_gate_passed,
            "exact_top1": self.exact_top1,
            "oracle_winner_survived_all_stages": self.oracle_winner_survived_all_stages,
            "oracle_winner_removed_at_stage": self.oracle_winner_removed_at_stage,
            "top_n": self.top_n,
            "top_n_recall": str(self.top_n_recall),
            "best_dps_regret": str(self.best_dps_regret),
            "best_dps_regret_ratio": str(self.best_dps_regret_ratio),
            "maximum_rankwise_dps_miss": str(self.maximum_rankwise_dps_miss),
            "missing_oracle_top_n_sha256s": list(self.missing_oracle_top_n_sha256s),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerReleaseGateReport:
    cases: tuple[GcsimOptimizerQualityMetrics, ...]
    strict_gate_passed: bool
    exact_top1_rate: Decimal
    minimum_top_n_recall: Decimal
    mean_best_dps_regret_ratio: Decimal
    maximum_best_dps_regret_ratio: Decimal
    maximum_rankwise_dps_miss: Decimal
    schema_version: int = GCSIM_OPTIMIZER_RELEASE_GATE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "strict_gate_passed": self.strict_gate_passed,
            "exact_top1_rate": str(self.exact_top1_rate),
            "minimum_top_n_recall": str(self.minimum_top_n_recall),
            "mean_best_dps_regret_ratio": str(
                self.mean_best_dps_regret_ratio
            ),
            "maximum_best_dps_regret_ratio": str(self.maximum_best_dps_regret_ratio),
            "maximum_rankwise_dps_miss": str(self.maximum_rankwise_dps_miss),
            "cases": [case.to_dict() for case in self.cases],
        }


def measure_gcsim_optimizer_quality_case(
    case: GcsimOptimizerQualityCase,
) -> GcsimOptimizerQualityMetrics:
    """Calculate auditable parity/recall/regret for one reduced fixture."""

    oracle = case.oracle_ranking
    oracle_by_id = {row.candidate_identity_sha256: row.dps for row in oracle}
    winner = oracle[0]
    production = case.production_ranking_sha256s
    production_known = tuple(value for value in production if value in oracle_by_id)
    top_count = min(case.top_n, len(oracle))
    oracle_top = tuple(row.candidate_identity_sha256 for row in oracle[:top_count])
    production_top = production[:top_count]
    missing = tuple(value for value in oracle_top if value not in production_top)
    recall = Decimal(top_count - len(missing)) / Decimal(top_count)
    best_production_dps = max(
        (oracle_by_id[value] for value in production_known),
        default=Decimal(0),
    )
    regret = max(Decimal(0), winner.dps - best_production_dps)
    regret_ratio = Decimal(0) if winner.dps == 0 else regret / winner.dps
    rankwise_misses = []
    for index in range(top_count):
        oracle_dps = oracle[index].dps
        production_dps = (
            oracle_by_id.get(production_top[index], Decimal(0))
            if index < len(production_top)
            else Decimal(0)
        )
        rankwise_misses.append(max(Decimal(0), oracle_dps - production_dps))
    survival = audit_gcsim_optimizer_oracle_winner_survival(
        winner.candidate_identity_sha256,
        case.pruning_stages,
    )
    return GcsimOptimizerQualityMetrics(
        case_id=case.case_id,
        exact_top1=bool(production) and production[0] == winner.candidate_identity_sha256,
        oracle_winner_survived_all_stages=survival.survived_all,
        oracle_winner_removed_at_stage=survival.removed_at_stage,
        top_n=top_count,
        top_n_recall=recall,
        best_dps_regret=regret,
        best_dps_regret_ratio=regret_ratio,
        maximum_rankwise_dps_miss=max(rankwise_misses, default=Decimal(0)),
        missing_oracle_top_n_sha256s=missing,
    )


def build_gcsim_optimizer_release_gate_report(
    cases: Iterable[GcsimOptimizerQualityCase],
) -> GcsimOptimizerReleaseGateReport:
    metrics = tuple(measure_gcsim_optimizer_quality_case(case) for case in cases)
    if not metrics:
        raise GcsimOptimizerReleaseGateError("release gate needs at least one quality case")
    return GcsimOptimizerReleaseGateReport(
        cases=metrics,
        strict_gate_passed=all(case.strict_gate_passed for case in metrics),
        exact_top1_rate=(
            Decimal(sum(case.exact_top1 for case in metrics)) / Decimal(len(metrics))
        ),
        minimum_top_n_recall=min(case.top_n_recall for case in metrics),
        mean_best_dps_regret_ratio=(
            sum(
                (case.best_dps_regret_ratio for case in metrics),
                Decimal(0),
            )
            / Decimal(len(metrics))
        ),
        maximum_best_dps_regret_ratio=max(
            case.best_dps_regret_ratio for case in metrics
        ),
        maximum_rankwise_dps_miss=max(
            case.maximum_rankwise_dps_miss for case in metrics
        ),
    )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerReleaseAssessment:
    policy: GcsimOptimizerProvisionalReleasePolicy
    mandatory_quality: GcsimOptimizerReleaseGateReport
    randomized_quality: GcsimOptimizerReleaseGateReport
    runtime_evidence: tuple[GcsimOptimizerRuntimeEvidence, ...]
    missing_runtime_kinds: tuple[GcsimOptimizerRuntimeKind, ...]
    over_limit_runtime_kinds: tuple[GcsimOptimizerRuntimeKind, ...]

    @property
    def mandatory_quality_passed(self) -> bool:
        return (
            not self.policy.mandatory_cases_require_strict_top1
            or self.mandatory_quality.strict_gate_passed
        )

    @property
    def randomized_quality_passed(self) -> bool:
        return (
            self.randomized_quality.exact_top1_rate
            >= self.policy.randomized_exact_top1_rate
            and self.randomized_quality.mean_best_dps_regret_ratio
            <= self.policy.randomized_mean_regret_ratio
            and self.randomized_quality.maximum_best_dps_regret_ratio
            <= self.policy.randomized_maximum_regret_ratio
        )

    @property
    def runtime_passed(self) -> bool:
        return not self.missing_runtime_kinds and not self.over_limit_runtime_kinds

    @property
    def passed(self) -> bool:
        return (
            self.mandatory_quality_passed
            and self.randomized_quality_passed
            and self.runtime_passed
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "mandatory_quality_passed": self.mandatory_quality_passed,
            "randomized_quality_passed": self.randomized_quality_passed,
            "runtime_passed": self.runtime_passed,
            "policy": self.policy.to_dict(),
            "mandatory_quality": self.mandatory_quality.to_dict(),
            "randomized_quality": self.randomized_quality.to_dict(),
            "runtime_evidence": [
                item.to_dict() for item in self.runtime_evidence
            ],
            "missing_runtime_kinds": [
                item.value for item in self.missing_runtime_kinds
            ],
            "over_limit_runtime_kinds": [
                item.value for item in self.over_limit_runtime_kinds
            ],
        }


def assess_gcsim_optimizer_release(
    *,
    mandatory_cases: Iterable[GcsimOptimizerQualityCase],
    randomized_cases: Iterable[GcsimOptimizerQualityCase],
    runtime_evidence: Iterable[GcsimOptimizerRuntimeEvidence],
    policy: GcsimOptimizerProvisionalReleasePolicy | None = None,
) -> GcsimOptimizerReleaseAssessment:
    selected_policy = policy or GcsimOptimizerProvisionalReleasePolicy()
    mandatory_report = build_gcsim_optimizer_release_gate_report(
        mandatory_cases
    )
    randomized_report = build_gcsim_optimizer_release_gate_report(
        randomized_cases
    )
    evidence = tuple(runtime_evidence)
    if len({item.kind for item in evidence}) != len(evidence):
        raise GcsimOptimizerReleaseGateError(
            "runtime evidence kinds must be unique"
        )
    by_kind = {item.kind: item for item in evidence}
    missing = tuple(kind for kind in GcsimOptimizerRuntimeKind if kind not in by_kind)
    over_limit = tuple(
        kind
        for kind in GcsimOptimizerRuntimeKind
        if kind in by_kind
        and by_kind[kind].elapsed_seconds > selected_policy.runtime_limit(kind)
    )
    return GcsimOptimizerReleaseAssessment(
        policy=selected_policy,
        mandatory_quality=mandatory_report,
        randomized_quality=randomized_report,
        runtime_evidence=evidence,
        missing_runtime_kinds=missing,
        over_limit_runtime_kinds=over_limit,
    )


def _require_sha256(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GcsimOptimizerReleaseGateError("candidate identity must be lowercase SHA-256")


__all__ = [
    "GCSIM_OPTIMIZER_PROVISIONAL_RELEASE_POLICY_SCHEMA_VERSION",
    "GCSIM_OPTIMIZER_RELEASE_GATE_SCHEMA_VERSION",
    "GcsimOptimizerProvisionalReleasePolicy",
    "GcsimOptimizerQualityCase",
    "GcsimOptimizerQualityMetrics",
    "GcsimOptimizerQualityRank",
    "GcsimOptimizerReleaseGateError",
    "GcsimOptimizerReleaseGateReport",
    "GcsimOptimizerReleaseAssessment",
    "GcsimOptimizerRuntimeEvidence",
    "GcsimOptimizerRuntimeKind",
    "assess_gcsim_optimizer_release",
    "build_gcsim_optimizer_release_gate_report",
    "measure_gcsim_optimizer_quality_case",
]
