"""Role-agnostic nonlinear stat-response surface for optimizer proposals.

The exact GCSIM race remains authoritative.  This module only builds a
context-bound proposal surrogate from common-seed paired interventions.  It
keeps several reachable anchors for every artifact substat axis, explicit
within-wearer and cross-wearer interactions, the ordered four-character DPS
response, and conservative uncertainty / out-of-domain evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from math import isfinite, sqrt
from time import monotonic

from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_stat_response import (
    GCSIM_STAT_RESPONSE_MAIN_VALUES,
    GCSIM_STAT_RESPONSE_ROLL_VALUES,
    GcsimStatResponseChange,
    GcsimStatResponseChangeMode,
    GcsimStatResponseIntervention,
    GcsimStatResponseRequest,
    GcsimStatResponseResult,
    GcsimStatResponseTarget,
    run_gcsim_stat_response,
)


GCSIM_OPTIMIZER_RESPONSE_SURFACE_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_RESPONSE_SURFACE_PLAN_ID = "nonlinear_context_surface"
GCSIM_OPTIMIZER_RESPONSE_SURFACE_PLAN_VERSION = 1

_SUBSTAT_AXES = tuple(GCSIM_STAT_RESPONSE_ROLL_VALUES)
_SCALING_AXES = ("hp%", "atk%", "def%", "em")
_DAMAGE_BONUS_AXES = (
    "pyro%",
    "hydro%",
    "electro%",
    "cryo%",
    "anemo%",
    "geo%",
    "dendro%",
    "phys%",
)


class GcsimOptimizerResponseSurfaceError(RuntimeError):
    """Raised when nonlinear response evidence cannot preserve its contract."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResponseSurfacePlan:
    anchor_roll_span: int = 8
    interaction_roll_span: int = 1
    confidence_sigma: float = 2.0
    max_interventions_per_batch: int = 256
    schema_version: int = GCSIM_OPTIMIZER_RESPONSE_SURFACE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for name in (
            "anchor_roll_span",
            "interaction_roll_span",
            "max_interventions_per_batch",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise GcsimOptimizerResponseSurfaceError(
                    f"{name} must be a positive integer"
                )
        if self.max_interventions_per_batch > 256:
            raise GcsimOptimizerResponseSurfaceError(
                "surface batches cannot exceed the engine intervention limit"
            )
        if not isfinite(self.confidence_sigma) or self.confidence_sigma <= 0:
            raise GcsimOptimizerResponseSurfaceError(
                "confidence_sigma must be finite and positive"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    @property
    def planned_probe_count(self) -> int:
        anchor_count = 4 * (3 * len(_SUBSTAT_AXES) + 1)
        primary_interactions = (
            4 * (1 + 2 * (len(_SUBSTAT_AXES) - 2))
            + len(_SUBSTAT_AXES)
            + 6
        )
        bonus_main_effects = 4 * len(_DAMAGE_BONUS_AXES)
        bonus_interactions = 4 * len(_SCALING_AXES) * len(_DAMAGE_BONUS_AXES)
        return (
            anchor_count
            + primary_interactions
            + bonus_main_effects
            + bonus_interactions
            + 4
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": GCSIM_OPTIMIZER_RESPONSE_SURFACE_PLAN_ID,
            "plan_version": GCSIM_OPTIMIZER_RESPONSE_SURFACE_PLAN_VERSION,
            "anchor_roll_span": self.anchor_roll_span,
            "interaction_roll_span": self.interaction_roll_span,
            "confidence_sigma": self.confidence_sigma,
            "max_interventions_per_batch": self.max_interventions_per_batch,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResponseSurfacePoint:
    coordinate: float
    team_delta_mean: float
    team_delta_se: float
    character_delta_means: tuple[float, float, float, float]
    character_delta_ses: tuple[float, float, float, float]
    observation_id: str

    def __post_init__(self) -> None:
        values = (
            self.coordinate,
            self.team_delta_mean,
            self.team_delta_se,
            *self.character_delta_means,
            *self.character_delta_ses,
        )
        if any(not isfinite(float(value)) for value in values):
            raise GcsimOptimizerResponseSurfaceError(
                "surface point contains non-finite values"
            )
        if self.team_delta_se < 0 or any(
            value < 0 for value in self.character_delta_ses
        ):
            raise GcsimOptimizerResponseSurfaceError(
                "surface uncertainty must be non-negative"
            )
        if (
            len(self.character_delta_means) != 4
            or len(self.character_delta_ses) != 4
        ):
            raise GcsimOptimizerResponseSurfaceError(
                "surface point must cover four character deltas"
            )
        if not self.observation_id:
            raise GcsimOptimizerResponseSurfaceError(
                "surface point observation_id is required"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "coordinate": self.coordinate,
            "team_delta_mean": self.team_delta_mean,
            "team_delta_se": self.team_delta_se,
            "character_delta_means": list(self.character_delta_means),
            "character_delta_ses": list(self.character_delta_ses),
            "observation_id": self.observation_id,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResponseSurfaceCurve:
    team_slot: int
    stat_axis: str
    baseline_coordinate: float
    points: tuple[GcsimOptimizerResponseSurfacePoint, ...]

    def __post_init__(self) -> None:
        if self.team_slot not in range(1, 5):
            raise GcsimOptimizerResponseSurfaceError(
                "curve team_slot must be in 1..4"
            )
        if self.stat_axis not in _SUBSTAT_AXES:
            raise GcsimOptimizerResponseSurfaceError(
                f"unsupported curve stat axis: {self.stat_axis!r}"
            )
        points = tuple(sorted(self.points, key=lambda item: item.coordinate))
        if len(points) < 3 or len({item.coordinate for item in points}) != len(points):
            raise GcsimOptimizerResponseSurfaceError(
                "surface curve requires at least three unique anchors"
            )
        if not any(
            abs(item.coordinate - self.baseline_coordinate) <= 1e-12
            for item in points
        ):
            raise GcsimOptimizerResponseSurfaceError(
                "surface curve does not contain its baseline anchor"
            )
        object.__setattr__(self, "points", points)

    @property
    def lower_coordinate(self) -> float:
        return self.points[0].coordinate

    @property
    def upper_coordinate(self) -> float:
        return self.points[-1].coordinate

    def predict(self, coordinate: float) -> tuple[float, float, float]:
        """Return piecewise-linear mean, conservative SE, and OOD distance."""

        value = float(coordinate)
        if not isfinite(value) or value < 0:
            raise GcsimOptimizerResponseSurfaceError(
                "surface coordinates must be finite and non-negative"
            )
        left, right = _bracketing_points(self.points, value)
        width = right.coordinate - left.coordinate
        ratio = 0.0 if width == 0 else (value - left.coordinate) / width
        mean = left.team_delta_mean + ratio * (
            right.team_delta_mean - left.team_delta_mean
        )
        # Do not pretend interpolation removes simulation uncertainty.
        se = abs(1.0 - ratio) * left.team_delta_se + abs(ratio) * right.team_delta_se
        roll = GCSIM_STAT_RESPONSE_ROLL_VALUES[self.stat_axis]
        ood = (
            max(self.lower_coordinate - value, value - self.upper_coordinate, 0.0)
            / roll
        )
        return mean, se, ood

    def local_slope(self) -> tuple[float, float]:
        baseline = min(
            self.points,
            key=lambda item: abs(item.coordinate - self.baseline_coordinate),
        )
        candidates = tuple(
            item for item in self.points if item.coordinate > baseline.coordinate
        )
        other = candidates[0] if candidates else self.points[-1]
        width = max(other.coordinate - baseline.coordinate, 1e-12)
        return (
            (other.team_delta_mean - baseline.team_delta_mean) / width,
            sqrt(other.team_delta_se**2 + baseline.team_delta_se**2) / width,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "team_slot": self.team_slot,
            "stat_axis": self.stat_axis,
            "baseline_coordinate": self.baseline_coordinate,
            "points": [item.to_dict() for item in self.points],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResponseSurfaceFactor:
    team_slot: int
    stat_axis: str
    delta: float

    def __post_init__(self) -> None:
        if self.team_slot not in range(1, 5) or self.stat_axis not in (
            *_SUBSTAT_AXES,
            *_DAMAGE_BONUS_AXES,
        ):
            raise GcsimOptimizerResponseSurfaceError(
                "surface interaction factor is invalid"
            )
        if not isfinite(self.delta) or self.delta <= 0:
            raise GcsimOptimizerResponseSurfaceError(
                "surface interaction factor delta must be positive"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "team_slot": self.team_slot,
            "stat_axis": self.stat_axis,
            "delta": self.delta,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResponseSurfaceInteraction:
    interaction_id: str
    kind: str
    factors: tuple[GcsimOptimizerResponseSurfaceFactor, ...]
    team_residual_mean: float
    team_residual_se: float
    character_residual_means: tuple[float, float, float, float]
    character_residual_ses: tuple[float, float, float, float]
    classification: str

    def __post_init__(self) -> None:
        factors = tuple(self.factors)
        if (
            not self.interaction_id
            or self.kind not in {
                "crit_pair",
                "scaling_crit",
                "scaling_damage_bonus",
                "same_axis_all_wearers",
                "cross_wearer_pair",
            }
            or len(factors) < 2
            or len({(item.team_slot, item.stat_axis) for item in factors})
            != len(factors)
        ):
            raise GcsimOptimizerResponseSurfaceError(
                "surface interaction identity/factors are invalid"
            )
        values = (
            self.team_residual_mean,
            self.team_residual_se,
            *self.character_residual_means,
            *self.character_residual_ses,
        )
        if any(not isfinite(float(value)) for value in values) or any(
            value < 0 for value in (
                self.team_residual_se,
                *self.character_residual_ses,
            )
        ):
            raise GcsimOptimizerResponseSurfaceError(
                "surface interaction estimate is invalid"
            )
        if self.classification not in {"material", "negligible", "uncertain"}:
            raise GcsimOptimizerResponseSurfaceError(
                "surface interaction classification is invalid"
            )
        object.__setattr__(self, "factors", factors)

    @property
    def crosses_wearers(self) -> bool:
        return len({item.team_slot for item in self.factors}) > 1

    def to_dict(self) -> dict[str, object]:
        return {
            "interaction_id": self.interaction_id,
            "kind": self.kind,
            "factors": [item.to_dict() for item in self.factors],
            "team_residual_mean": self.team_residual_mean,
            "team_residual_se": self.team_residual_se,
            "character_residual_means": list(self.character_residual_means),
            "character_residual_ses": list(self.character_residual_ses),
            "classification": self.classification,
            "crosses_wearers": self.crosses_wearers,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResponseSurfaceResult:
    curves: tuple[GcsimOptimizerResponseSurfaceCurve, ...]
    interactions: tuple[GcsimOptimizerResponseSurfaceInteraction, ...]
    baseline_changes: tuple[GcsimStatResponseChange, ...]
    request_sha256s: tuple[str, ...]
    seed_panel_sha256s: tuple[str, ...]
    planned_probe_count: int
    elapsed_seconds: float
    evidence_sha256: str
    plan: GcsimOptimizerResponseSurfacePlan
    schema_version: int = GCSIM_OPTIMIZER_RESPONSE_SURFACE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        curves = tuple(self.curves)
        interactions = tuple(self.interactions)
        if (
            len(curves) != 4 * len(_SUBSTAT_AXES)
            or len({(item.team_slot, item.stat_axis) for item in curves})
            != len(curves)
        ):
            raise GcsimOptimizerResponseSurfaceError(
                "surface curves must cover every wearer/substat axis"
            )
        if not interactions or not any(item.crosses_wearers for item in interactions):
            raise GcsimOptimizerResponseSurfaceError(
                "surface must retain explicit cross-wearer interactions"
            )
        if not any(item.kind == "crit_pair" for item in interactions):
            raise GcsimOptimizerResponseSurfaceError(
                "surface must retain Crit Rate x Crit DMG interactions"
            )
        if not any(item.kind == "scaling_damage_bonus" for item in interactions):
            raise GcsimOptimizerResponseSurfaceError(
                "surface must retain scaling x damage-bonus interactions"
            )
        if self.planned_probe_count <= 0 or not isfinite(self.elapsed_seconds):
            raise GcsimOptimizerResponseSurfaceError(
                "surface runtime/probe counters are invalid"
            )
        _require_sha256(self.evidence_sha256, "evidence_sha256")
        for value in (*self.request_sha256s, *self.seed_panel_sha256s):
            _require_sha256(value, "surface request/seed identity")
        object.__setattr__(self, "curves", curves)
        object.__setattr__(self, "interactions", interactions)

    @property
    def curve_index(self) -> Mapping[tuple[int, str], GcsimOptimizerResponseSurfaceCurve]:
        return {(item.team_slot, item.stat_axis): item for item in self.curves}

    def score_team_stats(
        self,
        values_by_wearer: Sequence[Mapping[str, float]],
        *,
        uncertainty_sigma: float = 0.0,
    ) -> tuple[float, float, float]:
        """Score cheap assignment features; return mean, uncertainty and OOD."""

        rows = tuple(values_by_wearer)
        if len(rows) != 4:
            raise GcsimOptimizerResponseSurfaceError(
                "team surface scoring requires four wearer stat mappings"
            )
        mean = 0.0
        variance = 0.0
        ood = 0.0
        index = self.curve_index
        for team_slot, values in enumerate(rows, 1):
            for axis in _SUBSTAT_AXES:
                predicted, se, distance = index[(team_slot, axis)].predict(
                    max(float(values.get(axis, 0.0)), 0.0)
                )
                mean += predicted
                variance += se**2
                ood += distance
        for interaction in self.interactions:
            activation = 1.0
            for factor in interaction.factors:
                coordinate = max(
                    float(rows[factor.team_slot - 1].get(factor.stat_axis, 0.0)),
                    0.0,
                )
                baseline = (
                    index[(factor.team_slot, factor.stat_axis)].baseline_coordinate
                    if factor.stat_axis in _SUBSTAT_AXES
                    else 0.0
                )
                activation *= min(
                    max((coordinate - baseline) / factor.delta, 0.0),
                    1.0,
                )
            mean += interaction.team_residual_mean * activation
            variance += (interaction.team_residual_se * activation) ** 2
        se = sqrt(variance)
        return mean + uncertainty_sigma * se, se, ood

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan": self.plan.to_dict(),
            "curves": [item.to_dict() for item in self.curves],
            "interactions": [item.to_dict() for item in self.interactions],
            "baseline_changes": [item.to_dict() for item in self.baseline_changes],
            "request_sha256s": list(self.request_sha256s),
            "seed_panel_sha256s": list(self.seed_panel_sha256s),
            "planned_probe_count": self.planned_probe_count,
            "elapsed_seconds": self.elapsed_seconds,
            "evidence_sha256": self.evidence_sha256,
            "uncertainty_contract": {
                "kind": "paired_standard_error_plus_anchor_distance",
                "out_of_domain_unit": "average_five_star_rolls",
                "exact_probe_required_for_ood": True,
            },
        }


@dataclass(frozen=True, slots=True)
class _InteractionDefinition:
    interaction_id: str
    kind: str
    factors: tuple[GcsimOptimizerResponseSurfaceFactor, ...]


def discover_gcsim_optimizer_response_surface(
    *,
    engine_context: GcsimOptimizerEngineContext,
    prepared_config_text: str,
    target: GcsimStatResponseTarget,
    baseline_changes: Sequence[GcsimStatResponseChange],
    strongest_axes_by_wearer: Sequence[str],
    iterations: int,
    workers: int,
    master_seed: int,
    timeout_seconds: float,
    plan: GcsimOptimizerResponseSurfacePlan | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    environment: Mapping[str, str] | None = None,
    stat_response_runner: Callable[..., object] = run_gcsim_stat_response,
    is_cancelled: Callable[[], bool] | None = None,
    clock: Callable[[], float] = monotonic,
) -> GcsimOptimizerResponseSurfaceResult:
    """Run bounded multi-anchor and interaction panels through real GCSIM."""

    selected_plan = plan or GcsimOptimizerResponseSurfacePlan()
    baseline = _surface_baseline(baseline_changes)
    strongest = tuple(str(item) for item in strongest_axes_by_wearer)
    if len(strongest) != 4 or any(axis not in _SUBSTAT_AXES for axis in strongest):
        raise GcsimOptimizerResponseSurfaceError(
            "strongest_axes_by_wearer must cover four canonical substat axes"
        )
    started = clock()
    deadline = started + timeout_seconds
    anchor_interventions, anchor_coordinates = _anchor_interventions(
        baseline,
        plan=selected_plan,
    )
    interaction_definitions = _interaction_definitions(
        strongest,
        plan=selected_plan,
    )
    primary_interventions = (*anchor_interventions, *(
        _interaction_intervention(item) for item in interaction_definitions
        if item.kind != "scaling_damage_bonus"
    ))
    bonus_definitions = tuple(
        item
        for item in interaction_definitions
        if item.kind == "scaling_damage_bonus"
    )
    bonus_main_interventions = tuple(
        GcsimStatResponseIntervention(
            intervention_id=f"surface/c{character_index}/bonus/{axis}/main",
            changes=(
                GcsimStatResponseChange(
                    character_index=character_index,
                    stat=axis,
                    mode=GcsimStatResponseChangeMode.ADD,
                    value=GCSIM_STAT_RESPONSE_MAIN_VALUES[axis],
                ),
            ),
        )
        for character_index in range(4)
        for axis in _DAMAGE_BONUS_AXES
    )
    bonus_interventions = (
        *bonus_main_interventions,
        *(_interaction_intervention(item) for item in bonus_definitions),
    )
    batches = (tuple(primary_interventions), tuple(bonus_interventions))
    if any(
        not batch or len(batch) > selected_plan.max_interventions_per_batch
        for batch in batches
    ):
        raise GcsimOptimizerResponseSurfaceError(
            "surface panel does not fit the bounded engine batches"
        )
    planned = sum(len(batch) + 2 for batch in batches)
    if progress_callback is not None:
        progress_callback(0, planned)
    results: list[GcsimStatResponseResult] = []
    completed = 0
    context_root = _canonical_sha256(
        {
            "schema_version": GCSIM_OPTIMIZER_RESPONSE_SURFACE_SCHEMA_VERSION,
            "engine_binding_sha256": engine_context.binding_sha256,
            "prepared_config_sha256": hashlib.sha256(
                prepared_config_text.encode("utf-8")
            ).hexdigest(),
            "target_sha256": target.target_sha256,
            "plan_sha256": selected_plan.identity_sha256,
            "strongest_axes_by_wearer": list(strongest),
        }
    )
    for batch_index, interventions in enumerate(batches):
        remaining = deadline - clock()
        if remaining <= 0:
            raise GcsimOptimizerResponseSurfaceError(
                "nonlinear response surface exhausted its deadline"
            )
        context_sha256 = _canonical_sha256(
            {
                "context_root_sha256": context_root,
                "batch_index": batch_index,
                "intervention_ids": [item.intervention_id for item in interventions],
            }
        )
        request = GcsimStatResponseRequest(
            context_sha256=context_sha256,
            objective=target.objective,
            iterations=iterations,
            workers=workers,
            master_seed=master_seed,
            baseline_changes=baseline,
            interventions=interventions,
            ignore_burst_energy=True,
        )
        result = stat_response_runner(
            engine_context=engine_context,
            prepared_config_text=prepared_config_text,
            target=target,
            request=request,
            timeout_seconds=min(remaining, timeout_seconds),
            environment=environment,
            is_cancelled=is_cancelled,
        )
        if not isinstance(result, GcsimStatResponseResult):
            raise GcsimOptimizerResponseSurfaceError(
                "surface runner returned an invalid typed result"
            )
        results.append(result)
        completed += len(interventions) + 2
        if progress_callback is not None:
            progress_callback(completed, planned)

    observations = {
        item.observation_id: item
        for result in results
        for item in result.interventions
    }
    curves = _derive_curves(
        baseline,
        anchor_coordinates=anchor_coordinates,
        observations=observations,
    )
    interactions = _derive_interactions(
        interaction_definitions,
        observations=observations,
        confidence_sigma=selected_plan.confidence_sigma,
    )
    evidence_payload = {
        "schema_version": GCSIM_OPTIMIZER_RESPONSE_SURFACE_SCHEMA_VERSION,
        "plan_sha256": selected_plan.identity_sha256,
        "request_sha256s": [item.request_sha256 for item in results],
        "seed_panel_sha256s": [item.seed_panel_sha256 for item in results],
        "curves": [item.to_dict() for item in curves],
        "interactions": [item.to_dict() for item in interactions],
    }
    return GcsimOptimizerResponseSurfaceResult(
        curves=curves,
        interactions=interactions,
        baseline_changes=baseline,
        request_sha256s=tuple(item.request_sha256 for item in results),
        seed_panel_sha256s=tuple(item.seed_panel_sha256 for item in results),
        planned_probe_count=planned,
        elapsed_seconds=max(clock() - started, 0.0),
        evidence_sha256=_canonical_sha256(evidence_payload),
        plan=selected_plan,
    )


def _surface_baseline(
    changes: Sequence[GcsimStatResponseChange],
) -> tuple[GcsimStatResponseChange, ...]:
    rows = tuple(changes)
    expected = 4 * 19
    if len(rows) != expected or len(
        {(item.character_index, item.stat) for item in rows}
    ) != expected:
        raise GcsimOptimizerResponseSurfaceError(
            "surface baseline must cover every wearer/stat axis"
        )
    # Preserve the complete equal-investment synthetic anchor but create real
    # headroom for Crit Rate.  All surface comparisons share this same anchor.
    return tuple(
        GcsimStatResponseChange(
            character_index=item.character_index,
            stat=item.stat,
            mode=GcsimStatResponseChangeMode.SET,
            value=(0.45 if item.stat == "cr" else item.value),
        )
        for item in rows
    )


def _baseline_values(
    changes: Sequence[GcsimStatResponseChange],
) -> dict[tuple[int, str], float]:
    return {
        (item.character_index, item.stat): float(item.value)
        for item in changes
    }


def _anchor_interventions(baseline, *, plan):
    values = _baseline_values(baseline)
    interventions: list[GcsimStatResponseIntervention] = []
    coordinates: dict[tuple[int, str], list[tuple[float, str]]] = {}
    for character_index in range(4):
        for axis, roll in GCSIM_STAT_RESPONSE_ROLL_VALUES.items():
            base = values[(character_index, axis)]
            minimum = 4_780.0 if axis == "hp" else 311.0 if axis == "atk" else 0.0
            lower = max(base - plan.anchor_roll_span * roll, minimum)
            upper = base + plan.anchor_roll_span * roll
            rows = (
                ("low", lower, GcsimStatResponseChangeMode.SET, lower),
                (
                    "local",
                    base + plan.interaction_roll_span * roll,
                    GcsimStatResponseChangeMode.ADD,
                    plan.interaction_roll_span * roll,
                ),
                ("high", upper, GcsimStatResponseChangeMode.SET, upper),
            )
            if axis == "cr":
                rows = (*rows, ("cap", 1.05, GcsimStatResponseChangeMode.SET, 1.05))
            coordinates[(character_index, axis)] = [(base, "baseline")]
            for label, coordinate, mode, value in rows:
                intervention_id = f"surface/c{character_index}/{axis}/{label}"
                interventions.append(
                    GcsimStatResponseIntervention(
                        intervention_id=intervention_id,
                        changes=(
                            GcsimStatResponseChange(
                                character_index=character_index,
                                stat=axis,
                                mode=mode,
                                value=value,
                            ),
                        ),
                    )
                )
                coordinates[(character_index, axis)].append(
                    (coordinate, intervention_id)
                )
    return tuple(interventions), coordinates


def _interaction_definitions(strongest, *, plan):
    one = plan.interaction_roll_span
    definitions: list[_InteractionDefinition] = []
    for character_index in range(4):
        definitions.append(
            _definition(
                f"surface/c{character_index}/pair/cr_cd",
                "crit_pair",
                ((character_index, "cr", one), (character_index, "cd", one)),
            )
        )
        for axis in tuple(item for item in _SUBSTAT_AXES if item not in {"cr", "cd"}):
            for crit_axis in ("cr", "cd"):
                definitions.append(
                    _definition(
                        f"surface/c{character_index}/pair/{axis}_{crit_axis}",
                        "scaling_crit",
                        (
                            (character_index, axis, one),
                            (character_index, crit_axis, one),
                        ),
                    )
                )
        for scaling_axis in _SCALING_AXES:
            for bonus_axis in _DAMAGE_BONUS_AXES:
                definitions.append(
                    _InteractionDefinition(
                        interaction_id=(
                            f"surface/c{character_index}/bonus/"
                            f"{scaling_axis}_{bonus_axis}"
                        ),
                        kind="scaling_damage_bonus",
                        factors=(
                            GcsimOptimizerResponseSurfaceFactor(
                                character_index + 1,
                                scaling_axis,
                                one * GCSIM_STAT_RESPONSE_ROLL_VALUES[scaling_axis],
                            ),
                            GcsimOptimizerResponseSurfaceFactor(
                                character_index + 1,
                                bonus_axis,
                                GCSIM_STAT_RESPONSE_MAIN_VALUES[bonus_axis],
                            ),
                        ),
                    )
                )
    for axis in _SUBSTAT_AXES:
        definitions.append(
            _definition(
                f"surface/team/same/{axis}",
                "same_axis_all_wearers",
                tuple((index, axis, one) for index in range(4)),
            )
        )
    for left in range(4):
        for right in range(left + 1, 4):
            definitions.append(
                _definition(
                    f"surface/team/pair/c{left}_{strongest[left]}__c{right}_{strongest[right]}",
                    "cross_wearer_pair",
                    (
                        (left, strongest[left], one),
                        (right, strongest[right], one),
                    ),
                )
            )
    return tuple(definitions)


def _definition(interaction_id, kind, values):
    return _InteractionDefinition(
        interaction_id=interaction_id,
        kind=kind,
        factors=tuple(
            GcsimOptimizerResponseSurfaceFactor(
                character_index + 1,
                axis,
                rolls * GCSIM_STAT_RESPONSE_ROLL_VALUES[axis],
            )
            for character_index, axis, rolls in values
        ),
    )


def _interaction_intervention(definition):
    return GcsimStatResponseIntervention(
        intervention_id=definition.interaction_id,
        changes=tuple(
            GcsimStatResponseChange(
                character_index=item.team_slot - 1,
                stat=item.stat_axis,
                mode=GcsimStatResponseChangeMode.ADD,
                value=item.delta,
            )
            for item in definition.factors
        ),
    )


def _derive_curves(baseline, *, anchor_coordinates, observations):
    curves = []
    values = _baseline_values(baseline)
    for character_index in range(4):
        for axis in _SUBSTAT_AXES:
            points = []
            for coordinate, observation_id in anchor_coordinates[(character_index, axis)]:
                if observation_id == "baseline":
                    points.append(
                        GcsimOptimizerResponseSurfacePoint(
                            coordinate=coordinate,
                            team_delta_mean=0.0,
                            team_delta_se=0.0,
                            character_delta_means=(0.0, 0.0, 0.0, 0.0),
                            character_delta_ses=(0.0, 0.0, 0.0, 0.0),
                            observation_id=observation_id,
                        )
                    )
                    continue
                points.append(_point(coordinate, observation_id, observations))
            # The cap point can equal another point only on an exotic baseline;
            # keep one deterministic observation for that coordinate.
            by_coordinate = {item.coordinate: item for item in points}
            curves.append(
                GcsimOptimizerResponseSurfaceCurve(
                    team_slot=character_index + 1,
                    stat_axis=axis,
                    baseline_coordinate=values[(character_index, axis)],
                    points=tuple(by_coordinate.values()),
                )
            )
    return tuple(curves)


def _point(coordinate, observation_id, observations):
    observation = observations[observation_id]
    delta = observation.paired_delta
    if delta is None:
        raise GcsimOptimizerResponseSurfaceError(
            f"surface observation lacks paired delta: {observation_id}"
        )
    return GcsimOptimizerResponseSurfacePoint(
        coordinate=coordinate,
        team_delta_mean=delta.team_expected_dps.mean,
        team_delta_se=delta.team_expected_dps.standard_error,
        character_delta_means=tuple(
            item.mean for item in delta.character_expected_dps
        ),
        character_delta_ses=tuple(
            item.standard_error for item in delta.character_expected_dps
        ),
        observation_id=observation_id,
    )


def _derive_interactions(definitions, *, observations, confidence_sigma):
    local = {}
    for character_index in range(4):
        for axis in _SUBSTAT_AXES:
            local[(character_index + 1, axis)] = observations[
                f"surface/c{character_index}/{axis}/local"
            ].paired_delta
        for axis in _DAMAGE_BONUS_AXES:
            local[(character_index + 1, axis)] = observations[
                f"surface/c{character_index}/bonus/{axis}/main"
            ].paired_delta
    rows = []
    for definition in definitions:
        observed = observations[definition.interaction_id].paired_delta
        if observed is None or any(
            local[(item.team_slot, item.stat_axis)] is None
            for item in definition.factors
            if item.stat_axis in _SUBSTAT_AXES
        ):
            raise GcsimOptimizerResponseSurfaceError(
                f"interaction lacks paired evidence: {definition.interaction_id}"
            )
        main_team_mean = 0.0
        main_team_variance = 0.0
        main_character_means = [0.0] * 4
        main_character_variances = [0.0] * 4
        for factor in definition.factors:
            delta = local[(factor.team_slot, factor.stat_axis)]
            assert delta is not None
            main_team_mean += delta.team_expected_dps.mean
            main_team_variance += delta.team_expected_dps.standard_error**2
            for index, estimate in enumerate(delta.character_expected_dps):
                main_character_means[index] += estimate.mean
                main_character_variances[index] += estimate.standard_error**2
        team_mean = observed.team_expected_dps.mean - main_team_mean
        team_se = sqrt(
            observed.team_expected_dps.standard_error**2 + main_team_variance
        )
        character_means = tuple(
            estimate.mean - main_character_means[index]
            for index, estimate in enumerate(observed.character_expected_dps)
        )
        character_ses = tuple(
            sqrt(
                estimate.standard_error**2
                + main_character_variances[index]
            )
            for index, estimate in enumerate(observed.character_expected_dps)
        )
        lower = abs(team_mean) - confidence_sigma * team_se
        upper = abs(team_mean) + confidence_sigma * team_se
        classification = (
            "material"
            if lower > 0
            else "uncertain"
            if upper > 0
            else "negligible"
        )
        rows.append(
            GcsimOptimizerResponseSurfaceInteraction(
                interaction_id=definition.interaction_id,
                kind=definition.kind,
                factors=definition.factors,
                team_residual_mean=team_mean,
                team_residual_se=team_se,
                character_residual_means=character_means,
                character_residual_ses=character_ses,
                classification=classification,
            )
        )
    return tuple(rows)


def _bracketing_points(points, value):
    if value <= points[0].coordinate:
        return points[0], points[1]
    if value >= points[-1].coordinate:
        return points[-2], points[-1]
    for left, right in zip(points, points[1:], strict=False):
        if left.coordinate <= value <= right.coordinate:
            return left, right
    raise AssertionError("unreachable surface bracket")


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _require_schema(value: int) -> None:
    if value != GCSIM_OPTIMIZER_RESPONSE_SURFACE_SCHEMA_VERSION:
        raise GcsimOptimizerResponseSurfaceError(
            "unsupported response-surface schema version"
        )


def _require_sha256(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GcsimOptimizerResponseSurfaceError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


__all__ = [
    "GCSIM_OPTIMIZER_RESPONSE_SURFACE_PLAN_ID",
    "GCSIM_OPTIMIZER_RESPONSE_SURFACE_PLAN_VERSION",
    "GCSIM_OPTIMIZER_RESPONSE_SURFACE_SCHEMA_VERSION",
    "GcsimOptimizerResponseSurfaceCurve",
    "GcsimOptimizerResponseSurfaceError",
    "GcsimOptimizerResponseSurfaceFactor",
    "GcsimOptimizerResponseSurfaceInteraction",
    "GcsimOptimizerResponseSurfacePlan",
    "GcsimOptimizerResponseSurfacePoint",
    "GcsimOptimizerResponseSurfaceResult",
    "discover_gcsim_optimizer_response_surface",
]
