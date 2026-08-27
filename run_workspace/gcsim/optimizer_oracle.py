"""Shared typed contracts for reduced exhaustive optimizer oracles.

The Milestone 3 oracles are deliberately small-domain/debug tools.  They are
not production search implementations and must fail before accidentally
enumerating a real account-sized Cartesian product.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from math import isfinite


GCSIM_OPTIMIZER_REDUCED_ORACLE_SCHEMA_VERSION = 1


class GcsimOptimizerReducedOracleError(ValueError):
    """Raised when a reduced exhaustive oracle contract cannot be satisfied."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerReducedOracleLimits:
    max_artifacts_per_slot: int = 32
    max_cartesian_builds_per_wearer: int = 100_000
    max_legal_builds_per_wearer: int = 2_000
    max_joint_cartesian_states: int = 250_000
    max_theoretical_states: int = 250_000
    max_stored_replacement_witnesses: int = 8
    schema_version: int = GCSIM_OPTIMIZER_REDUCED_ORACLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_REDUCED_ORACLE_SCHEMA_VERSION:
            raise GcsimOptimizerReducedOracleError(
                "unsupported reduced oracle schema"
            )
        for field_name in (
            "max_artifacts_per_slot",
            "max_cartesian_builds_per_wearer",
            "max_legal_builds_per_wearer",
            "max_joint_cartesian_states",
            "max_theoretical_states",
            "max_stored_replacement_witnesses",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise GcsimOptimizerReducedOracleError(
                    f"{field_name} must be a positive integer"
                )

    def to_dict(self) -> dict[str, int]:
        return {
            "schema_version": self.schema_version,
            "max_artifacts_per_slot": self.max_artifacts_per_slot,
            "max_cartesian_builds_per_wearer": (
                self.max_cartesian_builds_per_wearer
            ),
            "max_legal_builds_per_wearer": (
                self.max_legal_builds_per_wearer
            ),
            "max_joint_cartesian_states": self.max_joint_cartesian_states,
            "max_theoretical_states": self.max_theoretical_states,
            "max_stored_replacement_witnesses": (
                self.max_stored_replacement_witnesses
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerOracleScore:
    objective_name: str
    objective_value: float
    evidence_sha256: str
    standard_error: float | None = None
    iterations: int | None = None
    schema_version: int = GCSIM_OPTIMIZER_REDUCED_ORACLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_REDUCED_ORACLE_SCHEMA_VERSION:
            raise GcsimOptimizerReducedOracleError(
                "unsupported oracle score schema"
            )
        _require_identifier(self.objective_name, "objective_name")
        if (
            isinstance(self.objective_value, bool)
            or not isfinite(self.objective_value)
            or self.objective_value < 0
        ):
            raise GcsimOptimizerReducedOracleError(
                "objective_value must be finite and non-negative"
            )
        _require_sha256(self.evidence_sha256, "evidence_sha256")
        if self.standard_error is not None and (
            isinstance(self.standard_error, bool)
            or not isfinite(self.standard_error)
            or self.standard_error < 0
        ):
            raise GcsimOptimizerReducedOracleError(
                "standard_error must be finite and non-negative or None"
            )
        if self.iterations is not None and (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations <= 0
        ):
            raise GcsimOptimizerReducedOracleError(
                "iterations must be a positive integer or None"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "objective_name": self.objective_name,
            "objective_value": self.objective_value,
            "evidence_sha256": self.evidence_sha256,
            "standard_error": self.standard_error,
            "iterations": self.iterations,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerOraclePruningStage:
    stage_name: str
    retained_candidate_sha256s: tuple[str, ...]
    schema_version: int = GCSIM_OPTIMIZER_REDUCED_ORACLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_REDUCED_ORACLE_SCHEMA_VERSION:
            raise GcsimOptimizerReducedOracleError(
                "unsupported pruning-stage schema"
            )
        _require_identifier(self.stage_name, "stage_name")
        retained = tuple(sorted(self.retained_candidate_sha256s))
        for value in retained:
            _require_sha256(value, "retained_candidate_sha256")
        if len(set(retained)) != len(retained):
            raise GcsimOptimizerReducedOracleError(
                "retained candidate identities must be unique"
            )
        object.__setattr__(self, "retained_candidate_sha256s", retained)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "stage_name": self.stage_name,
            "retained_candidate_sha256s": list(
                self.retained_candidate_sha256s
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerOracleWinnerStageAudit:
    stage_name: str
    winner_survived: bool
    schema_version: int = GCSIM_OPTIMIZER_REDUCED_ORACLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_REDUCED_ORACLE_SCHEMA_VERSION:
            raise GcsimOptimizerReducedOracleError(
                "unsupported winner-stage audit schema"
            )
        _require_identifier(self.stage_name, "stage_name")
        if not isinstance(self.winner_survived, bool):
            raise GcsimOptimizerReducedOracleError(
                "winner_survived must be a boolean"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "stage_name": self.stage_name,
            "winner_survived": self.winner_survived,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerOracleWinnerSurvival:
    winner_candidate_sha256: str
    stages: tuple[GcsimOptimizerOracleWinnerStageAudit, ...]
    survived_all: bool
    removed_at_stage: str = ""
    schema_version: int = GCSIM_OPTIMIZER_REDUCED_ORACLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_REDUCED_ORACLE_SCHEMA_VERSION:
            raise GcsimOptimizerReducedOracleError(
                "unsupported winner-survival schema"
            )
        _require_sha256(
            self.winner_candidate_sha256,
            "winner_candidate_sha256",
        )
        stages = tuple(self.stages)
        if any(
            not isinstance(item, GcsimOptimizerOracleWinnerStageAudit)
            for item in stages
        ):
            raise GcsimOptimizerReducedOracleError(
                "stages must contain typed audit rows"
            )
        if len({item.stage_name for item in stages}) != len(stages):
            raise GcsimOptimizerReducedOracleError(
                "winner-survival stage names must be unique"
            )
        expected_survived = all(item.winner_survived for item in stages)
        if self.survived_all != expected_survived:
            raise GcsimOptimizerReducedOracleError(
                "winner-survival aggregate is incoherent"
            )
        expected_removed = next(
            (
                item.stage_name
                for item in stages
                if not item.winner_survived
            ),
            "",
        )
        if self.removed_at_stage != expected_removed:
            raise GcsimOptimizerReducedOracleError(
                "winner removal stage is incoherent"
            )
        object.__setattr__(self, "stages", stages)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "winner_candidate_sha256": self.winner_candidate_sha256,
            "stages": [item.to_dict() for item in self.stages],
            "survived_all": self.survived_all,
            "removed_at_stage": self.removed_at_stage,
        }


def audit_gcsim_optimizer_oracle_winner_survival(
    winner_candidate_sha256: str,
    stages: tuple[GcsimOptimizerOraclePruningStage, ...],
) -> GcsimOptimizerOracleWinnerSurvival:
    """Report the first later production stage that removed an oracle winner."""

    _require_sha256(
        winner_candidate_sha256,
        "winner_candidate_sha256",
    )
    stage_rows = tuple(stages)
    if any(
        not isinstance(item, GcsimOptimizerOraclePruningStage)
        for item in stage_rows
    ):
        raise GcsimOptimizerReducedOracleError(
            "stages must contain typed pruning stages"
        )
    if len({item.stage_name for item in stage_rows}) != len(stage_rows):
        raise GcsimOptimizerReducedOracleError(
            "pruning stage names must be unique"
        )
    survived_so_far = True
    audits: list[GcsimOptimizerOracleWinnerStageAudit] = []
    for stage in stage_rows:
        survived_so_far = (
            survived_so_far
            and winner_candidate_sha256
            in stage.retained_candidate_sha256s
        )
        audits.append(
            GcsimOptimizerOracleWinnerStageAudit(
                stage_name=stage.stage_name,
                winner_survived=survived_so_far,
            )
        )
    audit_tuple = tuple(audits)
    removed_at = next(
        (
            item.stage_name
            for item in audit_tuple
            if not item.winner_survived
        ),
        "",
    )
    return GcsimOptimizerOracleWinnerSurvival(
        winner_candidate_sha256=winner_candidate_sha256,
        stages=audit_tuple,
        survived_all=not removed_at,
        removed_at_stage=removed_at,
    )


def _require_identifier(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(not (character.isalnum() or character in "._-/") for character in value)
    ):
        raise GcsimOptimizerReducedOracleError(
            f"{field_name} must be a stable identifier"
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
    "GCSIM_OPTIMIZER_REDUCED_ORACLE_SCHEMA_VERSION",
    "GcsimOptimizerOraclePruningStage",
    "GcsimOptimizerOracleScore",
    "GcsimOptimizerOracleWinnerStageAudit",
    "GcsimOptimizerOracleWinnerSurvival",
    "GcsimOptimizerReducedOracleError",
    "GcsimOptimizerReducedOracleLimits",
    "audit_gcsim_optimizer_oracle_winner_survival",
]
