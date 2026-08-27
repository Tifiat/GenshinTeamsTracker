"""Paired rotation-specific stat response for the bounded optimizer.

Production has one path only: the patched GTT-GCSIM schema-v2 batch.  It uses
common seeds and expected crit damage, compares legal main stats from an equal
synthetic baseline, then performs a cheap second pass to judge crit relevance
on a complete synthetic team.  No generic-prior or unrelated-build fallback
is retained here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
import hashlib
import json
from math import isfinite
import re
from time import monotonic

from .optimizer_anytime_candidates import (
    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
    GcsimOptimizerAnytimeStatProfile,
)
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_product_contracts import (
    GcsimFourPieceTargetPackage,
    GcsimOptimizerOperation,
    GcsimOptimizerOperationRequest,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerTarget,
)
from .optimizer_run_input import GcsimOptimizerRunInput
from .optimizer_response_surface import (
    GcsimOptimizerResponseSurfacePlan,
    GcsimOptimizerResponseSurfaceResult,
    discover_gcsim_optimizer_response_surface,
)
from .optimizer_stat_response import (
    GCSIM_STAT_RESPONSE_ARTIFACT_AXES,
    GCSIM_STAT_RESPONSE_ROLL_VALUES,
    GcsimStatResponseChange,
    GcsimStatResponseTarget,
    build_gcsim_stat_response_context_sha256,
    build_gcsim_stat_response_crit_relevance_request,
    build_gcsim_stat_response_probe_request,
    derive_gcsim_optimizer_anytime_profiles_from_stat_response,
    run_gcsim_stat_response,
)


GCSIM_OPTIMIZER_ANYTIME_RESPONSE_SCHEMA_VERSION = 4
GCSIM_OPTIMIZER_ANYTIME_RESPONSE_PLAN_ID = "paired_stat_response"
GCSIM_OPTIMIZER_ANYTIME_RESPONSE_PLAN_VERSION = 4

AnytimeResponseProgressCallback = Callable[[int, int, int], None]


class GcsimOptimizerAnytimeResponseError(RuntimeError):
    """Raised when paired response evidence cannot preserve its contract."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAnytimeResponsePlan:
    surface: GcsimOptimizerResponseSurfacePlan = field(
        default_factory=GcsimOptimizerResponseSurfacePlan
    )
    iterations: int = 8
    worker_count: int = 1
    max_parallel_candidates: int = 1
    total_cpu_budget: int = 1
    enable_nonlinear_surface: bool = False
    candidate_timeout_seconds: float = 90.0
    overall_deadline_seconds: float = 300.0
    schema_version: int = GCSIM_OPTIMIZER_ANYTIME_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.surface, GcsimOptimizerResponseSurfacePlan):
            raise GcsimOptimizerAnytimeResponseError(
                "response surface plan must be typed"
            )
        if not isinstance(self.enable_nonlinear_surface, bool):
            raise GcsimOptimizerAnytimeResponseError(
                "enable_nonlinear_surface must be boolean"
            )
        for field_name in (
            "iterations",
            "worker_count",
            "max_parallel_candidates",
            "total_cpu_budget",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise GcsimOptimizerAnytimeResponseError(
                    f"{field_name} must be a positive integer"
                )
        if self.iterations > 1024:
            raise GcsimOptimizerAnytimeResponseError(
                "response iterations must not exceed 1024"
            )
        if self.worker_count > min(self.iterations, 64):
            raise GcsimOptimizerAnytimeResponseError(
                "response worker_count exceeds engine batch bounds"
            )
        if self.worker_count > self.total_cpu_budget:
            raise GcsimOptimizerAnytimeResponseError(
                "response worker_count exceeds total_cpu_budget"
            )
        # Schema v2 is exactly one engine process per pass.
        if self.max_parallel_candidates != 1:
            raise GcsimOptimizerAnytimeResponseError(
                "paired response max_parallel_candidates must be 1"
            )
        for field_name in (
            "candidate_timeout_seconds",
            "overall_deadline_seconds",
        ):
            value = getattr(self, field_name)
            if not isfinite(value) or value <= 0:
                raise GcsimOptimizerAnytimeResponseError(
                    f"{field_name} must be finite and positive"
                )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": GCSIM_OPTIMIZER_ANYTIME_RESPONSE_PLAN_ID,
            "plan_version": GCSIM_OPTIMIZER_ANYTIME_RESPONSE_PLAN_VERSION,
            "surface": self.surface.to_dict(),
            "iterations": self.iterations,
            "worker_count": self.worker_count,
            "max_parallel_candidates": self.max_parallel_candidates,
            "total_cpu_budget": self.total_cpu_budget,
            "enable_nonlinear_surface": self.enable_nonlinear_surface,
            "candidate_timeout_seconds": self.candidate_timeout_seconds,
            "overall_deadline_seconds": self.overall_deadline_seconds,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAnytimeResponseResult:
    profiles: tuple[GcsimOptimizerAnytimeStatProfile, ...]
    synthetic_baseline_changes: tuple[GcsimStatResponseChange, ...]
    synthetic_master_seed: int
    planned_probe_count: int
    successful_probe_count: int
    failed_probe_count: int
    cache_hit_count: int
    evidence_sha256: str
    elapsed_seconds: float
    surface_result: GcsimOptimizerResponseSurfaceResult | None = None
    schema_version: int = GCSIM_OPTIMIZER_ANYTIME_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        profiles = tuple(self.profiles)
        if not profiles or len({item.wearer for item in profiles}) != 4:
            raise GcsimOptimizerAnytimeResponseError(
                "response result must cover four wearers"
            )
        if any(
            not isinstance(item, GcsimOptimizerAnytimeStatProfile)
            for item in profiles
        ):
            raise GcsimOptimizerAnytimeResponseError(
                "response profiles must be typed"
            )
        profile_keys = tuple(
            (item.wearer, item.profile_id) for item in profiles
        )
        if len(set(profile_keys)) != len(profile_keys):
            raise GcsimOptimizerAnytimeResponseError(
                "response wearer/profile pairs must be unique"
            )
        if any(
            not any(
                item.wearer == wearer and item.profile_id == "balanced"
                for item in profiles
            )
            for wearer in {item.wearer for item in profiles}
        ):
            raise GcsimOptimizerAnytimeResponseError(
                "response must contain one balanced profile per wearer"
            )
        baseline = tuple(self.synthetic_baseline_changes)
        expected_baseline_size = 4 * len(GCSIM_STAT_RESPONSE_ARTIFACT_AXES)
        if (
            len(baseline) != expected_baseline_size
            or any(not isinstance(item, GcsimStatResponseChange) for item in baseline)
            or len(
                {(item.character_index, item.stat) for item in baseline}
            )
            != expected_baseline_size
        ):
            raise GcsimOptimizerAnytimeResponseError(
                "response synthetic baseline must cover every wearer/stat once"
            )
        if (
            isinstance(self.synthetic_master_seed, bool)
            or not isinstance(self.synthetic_master_seed, int)
            or not 0 < self.synthetic_master_seed <= 2**63 - 1
        ):
            raise GcsimOptimizerAnytimeResponseError(
                "response synthetic master seed is invalid"
            )
        for field_name in (
            "planned_probe_count",
            "successful_probe_count",
            "failed_probe_count",
            "cache_hit_count",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise GcsimOptimizerAnytimeResponseError(
                    f"{field_name} must be a non-negative integer"
                )
        if (
            self.successful_probe_count + self.failed_probe_count
            != self.planned_probe_count
        ):
            raise GcsimOptimizerAnytimeResponseError(
                "response counters are incoherent"
            )
        if self.cache_hit_count > self.successful_probe_count:
            raise GcsimOptimizerAnytimeResponseError(
                "response cache hits exceed successes"
            )
        _require_sha256(self.evidence_sha256, "evidence_sha256")
        if not isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise GcsimOptimizerAnytimeResponseError(
                "elapsed_seconds must be finite and non-negative"
            )
        if self.surface_result is not None and not isinstance(
            self.surface_result,
            GcsimOptimizerResponseSurfaceResult,
        ):
            raise GcsimOptimizerAnytimeResponseError(
                "surface_result must be typed when present"
            )
        object.__setattr__(self, "profiles", profiles)
        object.__setattr__(self, "synthetic_baseline_changes", baseline)

    def profiles_for(
        self,
        wearer: GcsimOptimizerWearerIdentity,
    ) -> tuple[GcsimOptimizerAnytimeStatProfile, ...]:
        return tuple(item for item in self.profiles if item.wearer == wearer)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profiles": [item.to_dict() for item in self.profiles],
            "synthetic_baseline_changes": [
                item.to_dict() for item in self.synthetic_baseline_changes
            ],
            "synthetic_master_seed": self.synthetic_master_seed,
            "planned_probe_count": self.planned_probe_count,
            "successful_probe_count": self.successful_probe_count,
            "failed_probe_count": self.failed_probe_count,
            "cache_hit_count": self.cache_hit_count,
            "evidence_sha256": self.evidence_sha256,
            "elapsed_seconds": self.elapsed_seconds,
            "surface": (
                None
                if self.surface_result is None
                else self.surface_result.to_dict()
            ),
        }


def discover_gcsim_optimizer_anytime_response(
    run_input: GcsimOptimizerRunInput,
    *,
    engine_context: GcsimOptimizerEngineContext,
    prepared_config_text: str,
    representative_targets: Sequence[GcsimOptimizerWearerTarget],
    plan: GcsimOptimizerAnytimeResponsePlan | None = None,
    progress_callback: AnytimeResponseProgressCallback | None = None,
    environment: Mapping[str, str] | None = None,
    stat_response_target: GcsimStatResponseTarget | None = None,
    stat_response_runner: Callable[..., object] = run_gcsim_stat_response,
    response_surface_discovery: Callable[..., object] = (
        discover_gcsim_optimizer_response_surface
    ),
    neutral_package_response: bool = False,
    master_seed: int | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    clock: Callable[[], float] = monotonic,
) -> GcsimOptimizerAnytimeResponseResult:
    """Measure selected-set or all-account response with one trusted target."""

    if not isinstance(run_input, GcsimOptimizerRunInput):
        raise GcsimOptimizerAnytimeResponseError("run_input must be typed")
    targets = tuple(representative_targets)
    wearers = run_input.request.source_simulation.wearers
    if len(targets) != 4 or tuple(item.wearer for item in targets) != wearers:
        raise GcsimOptimizerAnytimeResponseError(
            "representative targets must cover the frozen team"
        )
    if stat_response_target is None:
        raise GcsimOptimizerAnytimeResponseError(
            "paired response requires the selected chamber/dummy target"
        )
    response_config = (
        _without_character_set_lines(prepared_config_text)
        if neutral_package_response
        else _selected_package_response_config(prepared_config_text, targets)
    )
    return _discover_paired_response_v2(
        wearers=wearers,
        prepared_config_text=response_config,
        package_identity={
            "kind": (
                "account_all_sets_neutral_response"
                if neutral_package_response
                else "selected_packages"
            ),
            "targets": (
                []
                if neutral_package_response
                else [item.to_dict() for item in targets]
            ),
            "run_input_sha256": run_input.run_input_sha256,
        },
        engine_context=engine_context,
        target=stat_response_target,
        plan=plan or GcsimOptimizerAnytimeResponsePlan(),
        progress_callback=progress_callback,
        environment=environment,
        runner=stat_response_runner,
        surface_discovery=response_surface_discovery,
        master_seed=master_seed,
        is_cancelled=is_cancelled,
        clock=clock,
    )


def discover_gcsim_optimizer_theoretical_anytime_response(
    request: GcsimOptimizerOperationRequest,
    *,
    engine_context: GcsimOptimizerEngineContext,
    prepared_config_text: str,
    package_keys: Sequence[str],
    two_plus_two_packages: Mapping[str, object] | None = None,
    plan: GcsimOptimizerAnytimeResponsePlan | None = None,
    progress_callback: AnytimeResponseProgressCallback | None = None,
    environment: Mapping[str, str] | None = None,
    stat_response_target: GcsimStatResponseTarget | None = None,
    stat_response_runner: Callable[..., object] = run_gcsim_stat_response,
    response_surface_discovery: Callable[..., object] = (
        discover_gcsim_optimizer_response_surface
    ),
    master_seed: int | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    clock: Callable[[], float] = monotonic,
) -> GcsimOptimizerAnytimeResponseResult:
    """Measure an inventory-independent neutral-set response."""

    if not isinstance(request, GcsimOptimizerOperationRequest):
        raise GcsimOptimizerAnytimeResponseError("request must be typed")
    if request.operation not in {
        GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
        GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO,
    }:
        raise GcsimOptimizerAnytimeResponseError(
            "theoretical response requires a theoretical operation"
        )
    source = request.source_simulation
    if (
        source.engine_binding_sha256 != engine_context.binding_sha256
        or source.catalog_fingerprint
        != engine_context.catalog.source_fingerprint
    ):
        raise GcsimOptimizerAnytimeResponseError(
            "theoretical response engine binding differs from request"
        )
    if source.prepared_config_sha256 != hashlib.sha256(
        prepared_config_text.encode("utf-8")
    ).hexdigest():
        raise GcsimOptimizerAnytimeResponseError(
            "theoretical response config differs from request"
        )
    keys = tuple(str(item) for item in package_keys)
    if len(source.wearers) != 4 or len(keys) != 4 or any(not key for key in keys):
        raise GcsimOptimizerAnytimeResponseError(
            "theoretical response requires four explicit package keys"
        )
    pair_packages = dict(two_plus_two_packages or {})
    if request.operation is GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE:
        if pair_packages:
            raise GcsimOptimizerAnytimeResponseError(
                "theoretical 4p response must not carry 2p+2p packages"
            )
        for key in keys:
            capability = engine_context.catalog.get(key)
            if (
                capability is None
                or capability.max_rarity != 5
                or not capability.optimizer_four_piece_ready
            ):
                raise GcsimOptimizerAnytimeResponseError(
                    f"theoretical 4p package is not ready: {key!r}"
                )
    elif not pair_packages or any(key not in pair_packages for key in keys):
        raise GcsimOptimizerAnytimeResponseError(
            "theoretical 2p+2p response requires every synthetic package"
        )
    if stat_response_target is None:
        raise GcsimOptimizerAnytimeResponseError(
            "paired theoretical response requires an explicit target"
        )
    return _discover_paired_response_v2(
        wearers=source.wearers,
        prepared_config_text=_without_character_set_lines(
            prepared_config_text
        ),
        package_identity={
            "kind": "theoretical_neutral_set_response",
            "operation": request.operation.value,
            "request_sha256": request.request_sha256,
        },
        engine_context=engine_context,
        target=stat_response_target,
        plan=plan or GcsimOptimizerAnytimeResponsePlan(),
        progress_callback=progress_callback,
        environment=environment,
        runner=stat_response_runner,
        surface_discovery=response_surface_discovery,
        master_seed=master_seed,
        is_cancelled=is_cancelled,
        clock=clock,
    )


def _discover_paired_response_v2(
    *,
    wearers: tuple[GcsimOptimizerWearerIdentity, ...],
    prepared_config_text: str,
    package_identity: Mapping[str, object],
    engine_context: GcsimOptimizerEngineContext,
    target: GcsimStatResponseTarget,
    plan: GcsimOptimizerAnytimeResponsePlan,
    progress_callback: AnytimeResponseProgressCallback | None,
    environment: Mapping[str, str] | None,
    runner: Callable[..., object],
    surface_discovery: Callable[..., object],
    master_seed: int | None,
    is_cancelled: Callable[[], bool] | None,
    clock: Callable[[], float],
) -> GcsimOptimizerAnytimeResponseResult:
    started = clock()
    context_sha256 = build_gcsim_stat_response_context_sha256(
        engine_context=engine_context,
        prepared_config_text=prepared_config_text,
        target=target,
        package_identity_sha256=_canonical_sha256(package_identity),
    )
    request = build_gcsim_stat_response_probe_request(
        context_sha256=context_sha256,
        objective=target.objective,
        iterations=plan.iterations,
        workers=plan.worker_count,
        master_seed=master_seed,
    )
    paired_planned = len(request.interventions) + 2 + 6
    planned = paired_planned + (
        plan.surface.planned_probe_count
        if plan.enable_nonlinear_surface
        else 0
    )
    if progress_callback is not None:
        progress_callback(0, planned, 0)
    response = runner(
        engine_context=engine_context,
        prepared_config_text=prepared_config_text,
        target=target,
        request=request,
        timeout_seconds=min(
            plan.candidate_timeout_seconds * (len(request.interventions) + 2),
            plan.overall_deadline_seconds,
        ),
        environment=environment,
        is_cancelled=is_cancelled,
    )
    remaining = plan.overall_deadline_seconds - max(clock() - started, 0.0)
    if remaining <= 0:
        raise GcsimOptimizerAnytimeResponseError(
            "paired response exhausted its deadline before crit relevance"
        )
    crit_request = build_gcsim_stat_response_crit_relevance_request(
        response,
        iterations=plan.iterations,
        workers=plan.worker_count,
        master_seed=master_seed,
    )
    crit_response = runner(
        engine_context=engine_context,
        prepared_config_text=prepared_config_text,
        target=target,
        request=crit_request,
        timeout_seconds=min(plan.candidate_timeout_seconds * 6, remaining),
        environment=environment,
        is_cancelled=is_cancelled,
    )
    preliminary_profiles = tuple(
        derive_gcsim_optimizer_anytime_profiles_from_stat_response(
            response,
            wearers,
            crit_relevance_result=crit_response,
        )
    )
    if not preliminary_profiles:
        raise GcsimOptimizerAnytimeResponseError(
            "paired response produced no candidate profiles"
        )
    if not plan.enable_nonlinear_surface:
        if progress_callback is not None:
            progress_callback(paired_planned, planned, 0)
        evidence_sha256 = preliminary_profiles[0].evidence_sha256
        return GcsimOptimizerAnytimeResponseResult(
            profiles=preliminary_profiles,
            synthetic_baseline_changes=crit_request.baseline_changes,
            synthetic_master_seed=crit_request.master_seed,
            planned_probe_count=paired_planned,
            successful_probe_count=paired_planned,
            failed_probe_count=0,
            cache_hit_count=0,
            evidence_sha256=evidence_sha256,
            elapsed_seconds=max(clock() - started, 0.0),
            surface_result=None,
        )
    remaining = plan.overall_deadline_seconds - max(clock() - started, 0.0)
    if remaining <= 0:
        raise GcsimOptimizerAnytimeResponseError(
            "paired response exhausted its deadline before nonlinear surface"
        )
    surface = surface_discovery(
        engine_context=engine_context,
        prepared_config_text=prepared_config_text,
        target=target,
        baseline_changes=crit_request.baseline_changes,
        strongest_axes_by_wearer=_strongest_axes(
            wearers,
            preliminary_profiles,
        ),
        iterations=plan.iterations,
        workers=plan.worker_count,
        master_seed=crit_request.master_seed,
        timeout_seconds=remaining,
        plan=plan.surface,
        progress_callback=(
            None
            if progress_callback is None
            else lambda completed, _surface_planned: progress_callback(
                paired_planned + completed,
                planned,
                0,
            )
        ),
        environment=environment,
        stat_response_runner=runner,
        is_cancelled=is_cancelled,
        clock=clock,
    )
    if not isinstance(surface, GcsimOptimizerResponseSurfaceResult):
        raise GcsimOptimizerAnytimeResponseError(
            "nonlinear response discovery returned an invalid result"
        )
    evidence_sha256 = _canonical_sha256(
        {
            "schema_version": GCSIM_OPTIMIZER_ANYTIME_RESPONSE_SCHEMA_VERSION,
            "paired_profile_evidence_sha256": (
                preliminary_profiles[0].evidence_sha256
            ),
            "surface_evidence_sha256": surface.evidence_sha256,
        }
    )
    profiles = _profiles_with_surface(
        wearers,
        preliminary_profiles,
        surface=surface,
        evidence_sha256=evidence_sha256,
        confidence_sigma=plan.surface.confidence_sigma,
    )
    return GcsimOptimizerAnytimeResponseResult(
        profiles=profiles,
        synthetic_baseline_changes=crit_request.baseline_changes,
        synthetic_master_seed=crit_request.master_seed,
        planned_probe_count=planned,
        successful_probe_count=planned,
        failed_probe_count=0,
        cache_hit_count=0,
        evidence_sha256=evidence_sha256,
        elapsed_seconds=max(clock() - started, 0.0),
        surface_result=surface,
    )


def _strongest_axes(wearers, profiles):
    rows = []
    for wearer in wearers:
        balanced = next(
            item
            for item in profiles
            if item.wearer == wearer and item.profile_id == "balanced"
        )
        weights = dict(
            zip(
                GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
                balanced.stat_weights,
                strict=True,
            )
        )
        rows.append(
            max(
                GCSIM_STAT_RESPONSE_ROLL_VALUES,
                key=lambda axis: (
                    weights.get(axis, 0.0)
                    * GCSIM_STAT_RESPONSE_ROLL_VALUES[axis],
                    axis,
                ),
            )
        )
    return tuple(rows)


def _profiles_with_surface(
    wearers,
    profiles,
    *,
    surface,
    evidence_sha256,
    confidence_sigma,
):
    """Replace one-point weights with local surface marginals plus exploration."""

    curve_index = surface.curve_index
    result = []
    for wearer in wearers:
        wearer_profiles = tuple(item for item in profiles if item.wearer == wearer)
        balanced = next(item for item in wearer_profiles if item.profile_id == "balanced")
        old_balanced = dict(
            zip(
                GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
                balanced.stat_weights,
                strict=True,
            )
        )
        surface_weights = {}
        uncertain_weights = {}
        classifications = dict(balanced.stat_classifications)
        for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES:
            if axis not in GCSIM_STAT_RESPONSE_ROLL_VALUES:
                surface_weights[axis] = old_balanced.get(axis, 0.0)
                uncertain_weights[axis] = old_balanced.get(axis, 0.0)
                continue
            slope, slope_se = curve_index[(wearer.team_slot, axis)].local_slope()
            uncertain_weights[axis] = max(
                slope + confidence_sigma * slope_se,
                old_balanced.get(axis, 0.0),
                0.0,
            )
            if slope_se * confidence_sigma >= abs(slope):
                # The ordinary proposal lane must not turn a statistically
                # unresolved direction into deterministic utility.  Keep the
                # typed ``uncertain`` classification at zero weight and let
                # the explicit exploration lane below carry the confidence
                # upper bound with a useful classification.
                surface_weights[axis] = 0.0
                classifications[axis] = "uncertain"
            else:
                surface_weights[axis] = max(slope, 0.0)
                classifications[axis] = (
                    classifications[axis]
                    if surface_weights[axis] > 0
                    and classifications[axis] in {"dominant", "secondary"}
                    else "secondary"
                    if surface_weights[axis] > 0
                    else "negligible"
                )
        base_tuple = tuple(
            surface_weights.get(axis, old_balanced.get(axis, 0.0))
            for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
        )
        exploration_tuple = tuple(
            uncertain_weights[axis]
            for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
        )
        for profile in wearer_profiles:
            old_weights = dict(
                zip(
                    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
                    profile.stat_weights,
                    strict=True,
                )
            )
            # Balanced is the deterministic local-marginal lane.  The other
            # pre-existing profiles are bounded directional coverage lanes;
            # retaining their old shape against the confidence upper surface
            # prevents noisy slopes from collapsing every crit/structural head
            # to the same zero-weight ordering.
            profile_base = (
                base_tuple
                if profile.profile_id == "balanced"
                else exploration_tuple
            )
            scaled = tuple(
                profile_base[index]
                * (
                    old_weights.get(axis, 0.0) / old_balanced[axis]
                    if old_balanced.get(axis, 0.0) > 0
                    else 1.0
                )
                for index, axis in enumerate(GCSIM_OPTIMIZER_ANYTIME_STAT_AXES)
            )
            scaled_classifications = _compatible_stat_classifications(
                scaled,
                preferred=classifications,
            )
            result.append(
                replace(
                    profile,
                    stat_weights=scaled,
                    evidence_sha256=evidence_sha256,
                    feature_labels=tuple(
                        (
                            *profile.feature_labels,
                            "nonlinear_multi_anchor_surface",
                            "cross_wearer_pair_probes",
                            "paired_uncertainty",
                        )
                    ),
                    stat_classifications=scaled_classifications,
                )
            )
        exploration_weights = exploration_tuple
        result.append(
            replace(
                balanced,
                profile_id="uncertain_exploration",
                stat_weights=exploration_weights,
                evidence_sha256=evidence_sha256,
                feature_labels=tuple(
                    (
                        *balanced.feature_labels,
                        "nonlinear_multi_anchor_surface",
                        "uncertainty_exploration_lane",
                        "ood_exact_probe_required",
                    )
                ),
                stat_classifications=_compatible_stat_classifications(
                    exploration_weights,
                    preferred=classifications,
                ),
            )
        )
    return tuple(result)


def _compatible_stat_classifications(weights, *, preferred):
    """Return classifications that preserve the stat-profile weight contract."""

    rows = []
    for axis, weight in zip(
        GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
        weights,
        strict=True,
    ):
        classification = preferred[axis]
        if weight > 0:
            if classification not in {"dominant", "secondary"}:
                classification = "secondary"
        elif classification not in {"negligible", "uncertain"}:
            classification = "negligible"
        rows.append((axis, classification))
    return tuple(rows)


def _selected_package_response_config(
    prepared_config_text: str,
    targets: Sequence[GcsimOptimizerWearerTarget],
) -> str:
    text = _without_character_set_lines(prepared_config_text)
    insertions: dict[str, tuple[str, ...]] = {}
    for target in targets:
        wearer = target.wearer.gcsim_character_key
        package = target.package
        if isinstance(package, GcsimFourPieceTargetPackage):
            insertions[wearer] = (
                f'{wearer} add set="{package.set_ref.gcsim_set_key}" count=4;',
            )
        else:
            insertions[wearer] = (
                f'{wearer} add set="{package.set_a.gcsim_set_key}" count=2;',
                f'{wearer} add set="{package.set_b.gcsim_set_key}" count=2;',
            )
    lines: list[str] = []
    inserted: set[str] = set()
    for line in text.splitlines():
        lines.append(line)
        match = re.match(
            r"^\s*([A-Za-z][A-Za-z0-9_]*)\s+add\s+weapon\b",
            line,
            flags=re.IGNORECASE,
        )
        if match is None:
            continue
        key = match.group(1).casefold()
        if key in insertions:
            lines.extend(insertions[key])
            inserted.add(key)
    missing = set(insertions) - inserted
    if missing:
        raise GcsimOptimizerAnytimeResponseError(
            "could not place selected response sets for: "
            + ", ".join(sorted(missing))
        )
    return "\n".join(lines).rstrip() + "\n"


def _without_character_set_lines(config: str) -> str:
    if not isinstance(config, str) or not config.strip():
        raise GcsimOptimizerAnytimeResponseError(
            "prepared response config must be non-empty"
        )
    return re.sub(
        r"(?im)^\s*[A-Za-z][A-Za-z0-9_]*\s+add\s+set\s*=.*?;\s*(?:\r?\n)?",
        "",
        config,
    )


def strip_gcsim_optimizer_character_set_lines(config: str) -> str:
    """Return a response config with every character set assignment removed."""

    return _without_character_set_lines(config)


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
    if value != GCSIM_OPTIMIZER_ANYTIME_RESPONSE_SCHEMA_VERSION:
        raise GcsimOptimizerAnytimeResponseError(
            "unsupported paired response schema"
        )


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.casefold()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise GcsimOptimizerAnytimeResponseError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


__all__ = [
    "GCSIM_OPTIMIZER_ANYTIME_RESPONSE_PLAN_ID",
    "GCSIM_OPTIMIZER_ANYTIME_RESPONSE_PLAN_VERSION",
    "GCSIM_OPTIMIZER_ANYTIME_RESPONSE_SCHEMA_VERSION",
    "GcsimOptimizerAnytimeResponseError",
    "GcsimOptimizerAnytimeResponsePlan",
    "GcsimOptimizerAnytimeResponseResult",
    "discover_gcsim_optimizer_anytime_response",
    "discover_gcsim_optimizer_theoretical_anytime_response",
    "strip_gcsim_optimizer_character_set_lines",
]
