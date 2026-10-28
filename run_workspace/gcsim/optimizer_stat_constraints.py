"""Hard pre-GCSIM minimum-stat legality for real artifact builds.

The constraint space is intentionally static and provable: exact normalized
main/sub stats from five selected artifacts plus unconditional two-piece stat
mods proved from the frozen engine source. Conditional combat effects never
enter this boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ACCOUNT_STAT_AXES,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerWearerTarget,
    GcsimTwoPlusTwoTargetPackage,
)
from .optimizer_run_input import GcsimOptimizerRunInput


GCSIM_OPTIMIZER_STAT_CONSTRAINT_SCHEMA_VERSION = 1

_ZERO = Decimal(0)
_GCSIM_AXIS_BY_ENGINE_ATTRIBUTE = {
    "HP": "hp",
    "ATK": "atk",
    "DEF": "def",
    "HPP": "hp%",
    "ATKP": "atk%",
    "DEFP": "def%",
    "EM": "em",
    "ER": "er",
    "CR": "cr",
    "CD": "cd",
    "PyroP": "pyro%",
    "HydroP": "hydro%",
    "ElectroP": "electro%",
    "CryoP": "cryo%",
    "AnemoP": "anemo%",
    "GeoP": "geo%",
    "DendroP": "dendro%",
    "PhyP": "phys%",
    "Heal": "heal",
}


@dataclass(frozen=True, slots=True)
class GcsimOptimizerMinimumStatViolation:
    axis_key: str
    minimum: str
    artifact_value: str
    guaranteed_set_value: str
    static_build_value: str
    schema_version: int = GCSIM_OPTIMIZER_STAT_CONSTRAINT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_STAT_CONSTRAINT_SCHEMA_VERSION:
            raise ValueError("unsupported optimizer stat-constraint schema")
        if self.axis_key not in GCSIM_OPTIMIZER_ACCOUNT_STAT_AXES:
            raise ValueError("minimum-stat violation uses an unsupported axis")
        for field_name in (
            "minimum",
            "artifact_value",
            "guaranteed_set_value",
            "static_build_value",
        ):
            _decimal(getattr(self, field_name), field_name)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "axis_key": self.axis_key,
            "minimum": self.minimum,
            "artifact_value": self.artifact_value,
            "guaranteed_set_value": self.guaranteed_set_value,
            "static_build_value": self.static_build_value,
        }


def guaranteed_gcsim_optimizer_package_stat_contribution(
    run_input: GcsimOptimizerRunInput,
    *,
    target: GcsimOptimizerWearerTarget,
) -> Mapping[str, Decimal]:
    """Return exact unconditional set stats active for one target package."""

    _validate_inputs(run_input, target)
    descriptors = {
        item.set_key: item
        for item in run_input.guaranteed_two_piece_stat_effects
    }
    package = target.package
    if isinstance(package, GcsimFourPieceTargetPackage):
        set_refs = (package.set_ref,)
    elif isinstance(package, GcsimTwoPlusTwoTargetPackage):
        set_refs = (package.set_a, package.set_b)
    else:  # pragma: no cover - target contract is a closed union.
        raise TypeError("unsupported optimizer target package")

    # The materializer renders active set rows in set_uid order. GCSIM modifier
    # keys overwrite earlier mods, so mirror that order instead of summing a
    # future same-key collision.
    active_by_modifier = {}
    for set_ref in sorted(set_refs, key=lambda item: item.set_uid):
        descriptor = descriptors.get(set_ref.gcsim_set_key)
        if descriptor is not None:
            active_by_modifier[descriptor.modifier_key] = descriptor

    totals: dict[str, Decimal] = {}
    for descriptor in active_by_modifier.values():
        for engine_axis, value in descriptor.semantic_terms:
            axis = _GCSIM_AXIS_BY_ENGINE_ATTRIBUTE.get(engine_axis)
            if axis is None:
                continue
            totals[axis] = totals.get(axis, _ZERO) + Decimal(value)
    return dict(sorted(totals.items()))


def effective_gcsim_optimizer_artifact_minimums(
    run_input: GcsimOptimizerRunInput,
    *,
    target: GcsimOptimizerWearerTarget,
) -> Mapping[str, Decimal]:
    """Translate static-build floors into package-specific artifact minima."""

    guaranteed = guaranteed_gcsim_optimizer_package_stat_contribution(
        run_input,
        target=target,
    )
    return {
        item.axis_key: max(
            _ZERO,
            Decimal(item.minimum) - guaranteed.get(item.axis_key, _ZERO),
        )
        for item in run_input.request.minimum_stat_constraints
        if item.wearer == target.wearer
    }


def evaluate_gcsim_optimizer_minimum_stat_constraints(
    run_input: GcsimOptimizerRunInput,
    *,
    target: GcsimOptimizerWearerTarget,
    artifact_stats: Mapping[str, object],
) -> tuple[GcsimOptimizerMinimumStatViolation, ...]:
    """Return every hard-floor violation for one exact five-piece build."""

    _validate_inputs(run_input, target)
    if not isinstance(artifact_stats, Mapping):
        raise TypeError("artifact_stats must be a mapping")
    normalized = {
        str(axis): _decimal(value, f"artifact_stats[{axis!r}]")
        for axis, value in artifact_stats.items()
    }
    guaranteed = guaranteed_gcsim_optimizer_package_stat_contribution(
        run_input,
        target=target,
    )
    violations = []
    for constraint in run_input.request.minimum_stat_constraints:
        if constraint.wearer != target.wearer:
            continue
        artifact_value = normalized.get(constraint.axis_key, _ZERO)
        set_value = guaranteed.get(constraint.axis_key, _ZERO)
        total = artifact_value + set_value
        minimum = Decimal(constraint.minimum)
        if total < minimum:
            violations.append(
                GcsimOptimizerMinimumStatViolation(
                    axis_key=constraint.axis_key,
                    minimum=_decimal_text(minimum),
                    artifact_value=_decimal_text(artifact_value),
                    guaranteed_set_value=_decimal_text(set_value),
                    static_build_value=_decimal_text(total),
                )
            )
    return tuple(violations)


def _validate_inputs(
    run_input: GcsimOptimizerRunInput,
    target: GcsimOptimizerWearerTarget,
) -> None:
    if not isinstance(run_input, GcsimOptimizerRunInput):
        raise TypeError("run_input must be typed")
    if not isinstance(target, GcsimOptimizerWearerTarget):
        raise TypeError("target must be typed")
    if target.wearer not in run_input.request.source_simulation.wearers:
        raise ValueError("minimum-stat target is outside the frozen team")


def _decimal(value: object, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite decimal")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite decimal") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")
    return parsed


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


__all__ = [
    "GCSIM_OPTIMIZER_STAT_CONSTRAINT_SCHEMA_VERSION",
    "GcsimOptimizerMinimumStatViolation",
    "effective_gcsim_optimizer_artifact_minimums",
    "evaluate_gcsim_optimizer_minimum_stat_constraints",
    "guaranteed_gcsim_optimizer_package_stat_contribution",
]
