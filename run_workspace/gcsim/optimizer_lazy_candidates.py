"""Lazy per-wearer real 4p candidate generation for optimizer Milestone 5.

The generator reads only the immutable Milestone 2 run input.  It never reads
equipment, presets, import provenance, or SQLite.  A response branch from
Milestone 4 supplies the exact main-stat layout; an explicit/derived additive
response model supplies ordering.  Best-first branch-and-bound is exact for
that model, while every hard rejection remains auditable.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
import heapq
from itertools import product
import json
from types import MappingProxyType

from .farming_profile_config import GCSIM_SUBSTAT_ROLL_VALUES
from .optimizer_artifact_database import (
    GcsimOptimizerArtifactRecord,
    evaluate_gcsim_optimizer_artifact_eligibility,
)
from .optimizer_artifact_materializer import (
    GcsimOptimizerMaterializedBuild,
    materialize_gcsim_optimizer_artifact_stat_vector,
    materialize_gcsim_optimizer_wearer_build,
)
from .optimizer_main_response import (
    GcsimOptimizerMainResponseResult,
    GcsimOptimizerResponseBranch,
    GcsimOptimizerResponseBranchKind,
    GcsimOptimizerResponseProbeKind,
)
from .optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimFourPieceTargetPackage,
    GcsimTwoPlusTwoTargetPackage,
    GcsimOptimizerWearerArtifactAssignment,
    GcsimOptimizerWearerTarget,
)
from .optimizer_run_input import GcsimOptimizerRunInput
from .optimizer_stat_constraints import (
    effective_gcsim_optimizer_artifact_minimums,
)


GCSIM_OPTIMIZER_LAZY_CANDIDATE_SCHEMA_VERSION = 1

_ZERO = Decimal(0)
_VARIABLE_MAIN_SLOT_KEYS = ("sands", "goblet", "circlet")
_OFFPIECE_SHAPES = ("5p", *GCSIM_OPTIMIZER_ARTIFACT_SLOTS)
_TWO_PLUS_TWO_SHAPE = "2p2p"
_CANDIDATE_SHAPES = (*_OFFPIECE_SHAPES, _TWO_PLUS_TWO_SHAPE)


class GcsimOptimizerLazyCandidateError(ValueError):
    """Fail-closed M5 contract or invariant violation."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerCandidateStatWeight:
    axis_key: str
    weight: str

    def __post_init__(self) -> None:
        if not self.axis_key or self.axis_key != self.axis_key.strip():
            raise GcsimOptimizerLazyCandidateError(
                "candidate weight axis_key must be trimmed text"
            )
        object.__setattr__(
            self,
            "weight",
            _decimal_text(_finite_decimal(self.weight, "weight")),
        )

    @property
    def decimal_weight(self) -> Decimal:
        return Decimal(self.weight)

    def to_dict(self) -> dict[str, str]:
        return {"axis_key": self.axis_key, "weight": self.weight}


@dataclass(frozen=True, slots=True)
class GcsimOptimizerCandidateStatThreshold:
    axis_key: str
    minimum: str | None = None
    maximum: str | None = None

    def __post_init__(self) -> None:
        if not self.axis_key or self.axis_key != self.axis_key.strip():
            raise GcsimOptimizerLazyCandidateError(
                "candidate threshold axis_key must be trimmed text"
            )
        minimum = (
            None
            if self.minimum is None
            else _decimal_text(_finite_decimal(self.minimum, "minimum"))
        )
        maximum = (
            None
            if self.maximum is None
            else _decimal_text(_finite_decimal(self.maximum, "maximum"))
        )
        if minimum is None and maximum is None:
            raise GcsimOptimizerLazyCandidateError(
                "candidate threshold requires minimum and/or maximum"
            )
        if (
            minimum is not None
            and maximum is not None
            and Decimal(minimum) > Decimal(maximum)
        ):
            raise GcsimOptimizerLazyCandidateError(
                "candidate threshold minimum exceeds maximum"
            )
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)

    def to_dict(self) -> dict[str, str | None]:
        return {
            "axis_key": self.axis_key,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerCandidateResponseModel:
    """Auditable additive proposal model bound to one retained M4 branch."""

    response_branch: GcsimOptimizerResponseBranch
    stat_weights: tuple[GcsimOptimizerCandidateStatWeight, ...]
    thresholds: tuple[GcsimOptimizerCandidateStatThreshold, ...] = ()
    derivation: str = "explicit"
    schema_version: int = GCSIM_OPTIMIZER_LAZY_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.response_branch, GcsimOptimizerResponseBranch):
            raise GcsimOptimizerLazyCandidateError(
                "response_model branch must be typed"
            )
        weights = tuple(sorted(self.stat_weights, key=lambda item: item.axis_key))
        thresholds = tuple(
            sorted(self.thresholds, key=lambda item: item.axis_key)
        )
        if any(
            not isinstance(item, GcsimOptimizerCandidateStatWeight)
            for item in weights
        ):
            raise GcsimOptimizerLazyCandidateError(
                "stat_weights must be typed"
            )
        if any(
            not isinstance(item, GcsimOptimizerCandidateStatThreshold)
            for item in thresholds
        ):
            raise GcsimOptimizerLazyCandidateError(
                "thresholds must be typed"
            )
        if len({item.axis_key for item in weights}) != len(weights):
            raise GcsimOptimizerLazyCandidateError(
                "candidate response weights contain duplicate axes"
            )
        if len({item.axis_key for item in thresholds}) != len(thresholds):
            raise GcsimOptimizerLazyCandidateError(
                "candidate response thresholds contain duplicate axes"
            )
        if not self.derivation or self.derivation != self.derivation.strip():
            raise GcsimOptimizerLazyCandidateError(
                "response model derivation must be trimmed text"
            )
        object.__setattr__(self, "stat_weights", weights)
        object.__setattr__(self, "thresholds", thresholds)

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    @property
    def weights_by_axis(self) -> Mapping[str, Decimal]:
        return MappingProxyType(
            {item.axis_key: item.decimal_weight for item in self.stat_weights}
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "response_branch_sha256": self.response_branch.branch_sha256,
            "stat_weights": [item.to_dict() for item in self.stat_weights],
            "thresholds": [item.to_dict() for item in self.thresholds],
            "derivation": self.derivation,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerLazyCandidateCoverage:
    raw_artifact_count: int
    eligible_artifact_count: int
    indexed_artifact_count: int
    shadow_artifact_count: int
    exclusion_counts: tuple[tuple[str, int], ...]
    partial_states_expanded: int
    set_feasibility_pruned: int
    threshold_feasibility_pruned: int
    complete_states_considered: int
    materialized_candidate_count: int
    materialization_failure_count: int
    retained_candidate_count: int
    deferred_state_count: int
    conflict_repair_request_count: int
    conflict_blocked_artifact_count: int
    schema_version: int = GCSIM_OPTIMIZER_LAZY_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in (
            "raw_artifact_count",
            "eligible_artifact_count",
            "indexed_artifact_count",
            "shadow_artifact_count",
            "partial_states_expanded",
            "set_feasibility_pruned",
            "threshold_feasibility_pruned",
            "complete_states_considered",
            "materialized_candidate_count",
            "materialization_failure_count",
            "retained_candidate_count",
            "deferred_state_count",
            "conflict_repair_request_count",
            "conflict_blocked_artifact_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise GcsimOptimizerLazyCandidateError(
                    f"{field_name} must be a non-negative integer"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "raw_artifact_count": self.raw_artifact_count,
            "eligible_artifact_count": self.eligible_artifact_count,
            "indexed_artifact_count": self.indexed_artifact_count,
            "shadow_artifact_count": self.shadow_artifact_count,
            "exclusion_counts": dict(self.exclusion_counts),
            "partial_states_expanded": self.partial_states_expanded,
            "set_feasibility_pruned": self.set_feasibility_pruned,
            "threshold_feasibility_pruned": (
                self.threshold_feasibility_pruned
            ),
            "complete_states_considered": self.complete_states_considered,
            "materialized_candidate_count": self.materialized_candidate_count,
            "materialization_failure_count": self.materialization_failure_count,
            "retained_candidate_count": self.retained_candidate_count,
            "deferred_state_count": self.deferred_state_count,
            "upper_bound_deferred_state_count": self.deferred_state_count,
            "conflict_repair_request_count": (
                self.conflict_repair_request_count
            ),
            "conflict_blocked_artifact_count": (
                self.conflict_blocked_artifact_count
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerLazyWearerCandidate:
    target: GcsimOptimizerWearerTarget
    response_model_sha256: str
    assignment: GcsimOptimizerWearerArtifactAssignment
    materialized_build: GcsimOptimizerMaterializedBuild
    proposal_score: str
    crit_value: str
    offpiece_shape: str
    feature_labels: tuple[str, ...]
    content_fingerprint: str
    candidate_sha256: str
    schema_version: int = GCSIM_OPTIMIZER_LAZY_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        _require_sha256(self.response_model_sha256, "response_model_sha256")
        _require_sha256(self.content_fingerprint, "content_fingerprint")
        _require_sha256(self.candidate_sha256, "candidate_sha256")
        if self.assignment.wearer != self.target.wearer:
            raise GcsimOptimizerLazyCandidateError(
                "candidate assignment/target wearer mismatch"
            )
        if self.materialized_build.assignment != self.assignment:
            raise GcsimOptimizerLazyCandidateError(
                "candidate materialized build differs from assignment"
            )
        if self.offpiece_shape not in _CANDIDATE_SHAPES:
            raise GcsimOptimizerLazyCandidateError(
                "candidate has unsupported offpiece shape"
            )
        _finite_decimal(self.proposal_score, "proposal_score")
        _finite_decimal(self.crit_value, "crit_value")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "target": self.target.to_dict(),
            "response_model_sha256": self.response_model_sha256,
            "assignment": self.assignment.to_dict(),
            "materialized_build": self.materialized_build.to_dict(),
            "proposal_score": self.proposal_score,
            "crit_value": self.crit_value,
            "offpiece_shape": self.offpiece_shape,
            "feature_labels": list(self.feature_labels),
            "content_fingerprint": self.content_fingerprint,
            "candidate_sha256": self.candidate_sha256,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerLazyCandidateBatch:
    candidates: tuple[GcsimOptimizerLazyWearerCandidate, ...]
    pareto_candidate_sha256s: tuple[str, ...]
    coverage: GcsimOptimizerLazyCandidateCoverage
    exhausted: bool
    next_upper_bound: str | None
    schema_version: int = GCSIM_OPTIMIZER_LAZY_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        identities = tuple(item.candidate_sha256 for item in self.candidates)
        if len(set(identities)) != len(identities):
            raise GcsimOptimizerLazyCandidateError(
                "candidate batch contains duplicate physical candidates"
            )
        if not set(self.pareto_candidate_sha256s).issubset(identities):
            raise GcsimOptimizerLazyCandidateError(
                "Pareto identities must belong to the candidate batch"
            )
        if self.next_upper_bound is not None:
            _finite_decimal(self.next_upper_bound, "next_upper_bound")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidates": [item.to_dict() for item in self.candidates],
            "pareto_candidate_sha256s": list(self.pareto_candidate_sha256s),
            "coverage": self.coverage.to_dict(),
            "exhausted": self.exhausted,
            "next_upper_bound": self.next_upper_bound,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerCandidateRetentionPolicy:
    leader_count: int
    per_offpiece_shape_count: int = 1
    useful_stat_count: int = 1
    crit_value_count: int = 1
    schema_version: int = GCSIM_OPTIMIZER_LAZY_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in (
            "leader_count",
            "per_offpiece_shape_count",
            "useful_stat_count",
            "crit_value_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise GcsimOptimizerLazyCandidateError(
                    f"{field_name} must be a non-negative integer"
                )
        if (
            self.leader_count == 0
            and self.per_offpiece_shape_count == 0
            and self.useful_stat_count == 0
            and self.crit_value_count == 0
        ):
            raise GcsimOptimizerLazyCandidateError(
                "retention policy cannot be empty"
            )


@dataclass(frozen=True, slots=True)
class _IndexedArtifact:
    record: GcsimOptimizerArtifactRecord
    stats: tuple[tuple[str, Decimal], ...]
    local_score: Decimal
    package_index: int | None
    main_key: str
    shadow: bool = False

    @property
    def artifact_id(self) -> int:
        return self.record.artifact_id

    @property
    def stats_by_axis(self) -> Mapping[str, Decimal]:
        return dict(self.stats)


@dataclass(frozen=True, slots=True)
class _CandidateIndex:
    by_slot: tuple[tuple[str, tuple[_IndexedArtifact, ...]], ...]
    exclusion_counts: tuple[tuple[str, int], ...]
    raw_artifact_count: int
    eligible_artifact_count: int
    shadow_artifact_count: int

    @property
    def slot_map(self) -> Mapping[str, tuple[_IndexedArtifact, ...]]:
        return dict(self.by_slot)


@dataclass(frozen=True, slots=True)
class _SearchState:
    depth: int
    chosen: tuple[_IndexedArtifact, ...]
    stats: tuple[tuple[str, Decimal], ...]
    score: Decimal
    package_counts: tuple[int, ...]
    upper_bound: Decimal
    threshold_regions: tuple[tuple[str, str], ...]
    minimum_completion_ids: tuple[int, ...]


@dataclass(slots=True)
class _MutableCoverage:
    raw_artifact_count: int
    eligible_artifact_count: int
    indexed_artifact_count: int
    shadow_artifact_count: int
    exclusion_counts: tuple[tuple[str, int], ...]
    partial_states_expanded: int = 0
    set_feasibility_pruned: int = 0
    threshold_feasibility_pruned: int = 0
    complete_states_considered: int = 0
    materialized_candidate_count: int = 0
    materialization_failure_count: int = 0
    retained_candidate_count: int = 0
    conflict_repair_request_count: int = 0
    conflict_blocked_artifact_count: int = 0

    def snapshot(
        self,
        deferred_state_count: int,
    ) -> GcsimOptimizerLazyCandidateCoverage:
        return GcsimOptimizerLazyCandidateCoverage(
            raw_artifact_count=self.raw_artifact_count,
            eligible_artifact_count=self.eligible_artifact_count,
            indexed_artifact_count=self.indexed_artifact_count,
            shadow_artifact_count=self.shadow_artifact_count,
            exclusion_counts=self.exclusion_counts,
            partial_states_expanded=self.partial_states_expanded,
            set_feasibility_pruned=self.set_feasibility_pruned,
            threshold_feasibility_pruned=self.threshold_feasibility_pruned,
            complete_states_considered=self.complete_states_considered,
            materialized_candidate_count=self.materialized_candidate_count,
            materialization_failure_count=self.materialization_failure_count,
            retained_candidate_count=self.retained_candidate_count,
            deferred_state_count=deferred_state_count,
            conflict_repair_request_count=self.conflict_repair_request_count,
            conflict_blocked_artifact_count=self.conflict_blocked_artifact_count,
        )


class GcsimOptimizerLazyWearerCandidateGenerator:
    """Stateful exact best-first stream for one wearer/package/layout branch."""

    def __init__(
        self,
        run_input: GcsimOptimizerRunInput,
        *,
        target: GcsimOptimizerWearerTarget,
        response_model: GcsimOptimizerCandidateResponseModel,
        artifact_rows: Sequence[GcsimOptimizerArtifactRecord] | None = None,
        blocked_artifact_ids: Sequence[int] = (),
        offpiece_shape: str | None = None,
        _conflict_request: bool = False,
    ) -> None:
        _validate_generator_inputs(run_input, target, response_model)
        if (
            offpiece_shape is not None
            and offpiece_shape not in _OFFPIECE_SHAPES
        ):
            raise GcsimOptimizerLazyCandidateError(
                "offpiece_shape must be 5p or a canonical artifact slot"
            )
        rows = (
            run_input.artifact_database.artifacts
            if artifact_rows is None
            else _validate_artifact_row_permutation(run_input, artifact_rows)
        )
        self._run_input = run_input
        self._target = target
        self._response_model = response_model
        self._package_uids, self._package_requirements = (
            _package_requirements(target)
        )
        self._thresholds = _effective_candidate_thresholds(
            run_input,
            target=target,
            response_model=response_model,
        )
        self._blocked_ids = frozenset(_positive_ids(blocked_artifact_ids))
        self._offpiece_shape = offpiece_shape
        self._index = _build_candidate_index(
            run_input,
            target=target,
            response_model=response_model,
            thresholds=self._thresholds,
            artifact_rows=rows,
        )
        self._coverage = _MutableCoverage(
            raw_artifact_count=self._index.raw_artifact_count,
            eligible_artifact_count=self._index.eligible_artifact_count,
            indexed_artifact_count=sum(
                len(items) for _slot, items in self._index.by_slot
            ),
            shadow_artifact_count=self._index.shadow_artifact_count,
            exclusion_counts=self._index.exclusion_counts,
            conflict_repair_request_count=1 if _conflict_request else 0,
            conflict_blocked_artifact_count=(
                len(self._blocked_ids) if _conflict_request else 0
            ),
        )
        self._slot_map = self._filtered_slot_map()
        self._weights = response_model.weights_by_axis
        self._remaining_score_bounds = self._build_remaining_score_bounds()
        self._remaining_stat_maxima = self._build_remaining_stat_maxima()
        self._minimum_ids_by_slot = self._build_minimum_ids()
        self._heap: list[
            tuple[Decimal, tuple[int, ...], int, _SearchState]
        ] = []
        self._serial = 0
        self._yielded_assignments: set[tuple[int, ...]] = set()
        self._exhausted = False
        self._initialize_heap()

    @property
    def target(self) -> GcsimOptimizerWearerTarget:
        return self._target

    @property
    def response_model(self) -> GcsimOptimizerCandidateResponseModel:
        return self._response_model

    @property
    def coverage(self) -> GcsimOptimizerLazyCandidateCoverage:
        return self._coverage.snapshot(len(self._heap))

    def take(self, count: int) -> GcsimOptimizerLazyCandidateBatch:
        """Return the next exact candidates without materializing lower bounds."""

        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise GcsimOptimizerLazyCandidateError(
                "candidate take count must be a positive integer"
            )
        candidates: list[GcsimOptimizerLazyWearerCandidate] = []
        while self._heap and len(candidates) < count:
            _neg_bound, _minimum_ids, _serial, state = heapq.heappop(
                self._heap
            )
            if state.depth < len(GCSIM_OPTIMIZER_ARTIFACT_SLOTS):
                self._expand(state)
                continue
            self._coverage.complete_states_considered += 1
            artifact_ids = tuple(item.artifact_id for item in state.chosen)
            if artifact_ids in self._yielded_assignments:
                continue
            if not _thresholds_satisfied(state.stats, self._thresholds):
                self._coverage.threshold_feasibility_pruned += 1
                continue
            candidate = self._materialize(state)
            if candidate is None:
                continue
            self._yielded_assignments.add(artifact_ids)
            self._coverage.retained_candidate_count += 1
            candidates.append(candidate)
        self._exhausted = not self._heap
        next_bound = None if not self._heap else -self._heap[0][0]
        candidate_tuple = tuple(candidates)
        return GcsimOptimizerLazyCandidateBatch(
            candidates=candidate_tuple,
            pareto_candidate_sha256s=_pareto_candidate_ids(
                candidate_tuple,
                self._weights,
            ),
            coverage=self._coverage.snapshot(len(self._heap)),
            exhausted=self._exhausted,
            next_upper_bound=(
                None if next_bound is None else _decimal_text(next_bound)
            ),
        )

    def take_retained(
        self,
        policy: GcsimOptimizerCandidateRetentionPolicy,
    ) -> GcsimOptimizerLazyCandidateBatch:
        """Retain global leaders plus exact leaders for every legal 4p shape."""

        if not isinstance(policy, GcsimOptimizerCandidateRetentionPolicy):
            raise GcsimOptimizerLazyCandidateError(
                "retention policy must be typed"
            )
        leaders: tuple[GcsimOptimizerLazyWearerCandidate, ...] = ()
        if policy.leader_count:
            leaders = self.take(policy.leader_count).candidates
        retained = {
            item.assignment.artifact_ids: item for item in leaders
        }
        if (
            policy.per_offpiece_shape_count
            and isinstance(
                self._target.package,
                GcsimFourPieceTargetPackage,
            )
        ):
            for shape in _OFFPIECE_SHAPES:
                shape_generator = GcsimOptimizerLazyWearerCandidateGenerator(
                    self._run_input,
                    target=self._target,
                    response_model=self._response_model,
                    blocked_artifact_ids=tuple(self._blocked_ids),
                    offpiece_shape=shape,
                )
                shape_batch = shape_generator.take(
                    policy.per_offpiece_shape_count
                )
                self._absorb_search_coverage(shape_batch.coverage)
                for candidate in shape_batch.candidates:
                    candidate = self._reproject_candidate(
                        candidate,
                        feature_label=f"quota:shape:{shape}",
                    )
                    retained.setdefault(
                        candidate.assignment.artifact_ids,
                        candidate,
                    )
        quota_models = (
            (
                "useful_stat",
                policy.useful_stat_count,
                self._useful_stat_response_model(),
            ),
            (
                "crit_value",
                policy.crit_value_count,
                self._crit_value_response_model(),
            ),
        )
        for quota_name, quota_count, quota_model in quota_models:
            if not quota_count or quota_model is None:
                continue
            quota_generator = GcsimOptimizerLazyWearerCandidateGenerator(
                self._run_input,
                target=self._target,
                response_model=quota_model,
                blocked_artifact_ids=tuple(self._blocked_ids),
            )
            quota_batch = quota_generator.take(quota_count)
            self._absorb_search_coverage(quota_batch.coverage)
            for candidate in quota_batch.candidates:
                candidate = self._reproject_candidate(
                    candidate,
                    feature_label=f"quota:{quota_name}",
                )
                retained.setdefault(
                    candidate.assignment.artifact_ids,
                    candidate,
                )
        ordered = tuple(sorted(retained.values(), key=_candidate_rank))
        self._coverage.retained_candidate_count += max(
            0,
            len(ordered) - len(leaders),
        )
        return GcsimOptimizerLazyCandidateBatch(
            candidates=ordered,
            pareto_candidate_sha256s=_pareto_candidate_ids(
                ordered,
                self._weights,
            ),
            coverage=self._coverage.snapshot(len(self._heap)),
            exhausted=self._exhausted,
            next_upper_bound=(
                None if not self._heap else _decimal_text(-self._heap[0][0])
            ),
        )

    def _absorb_search_coverage(
        self,
        coverage: GcsimOptimizerLazyCandidateCoverage,
    ) -> None:
        self._coverage.partial_states_expanded += (
            coverage.partial_states_expanded
        )
        self._coverage.set_feasibility_pruned += (
            coverage.set_feasibility_pruned
        )
        self._coverage.threshold_feasibility_pruned += (
            coverage.threshold_feasibility_pruned
        )
        self._coverage.complete_states_considered += (
            coverage.complete_states_considered
        )
        self._coverage.materialized_candidate_count += (
            coverage.materialized_candidate_count
        )
        self._coverage.materialization_failure_count += (
            coverage.materialization_failure_count
        )

    def _useful_stat_response_model(
        self,
    ) -> GcsimOptimizerCandidateResponseModel | None:
        weights = {
            item.axis_key: abs(item.decimal_weight)
            for item in self._response_model.stat_weights
            if item.decimal_weight != 0
        }
        if not weights:
            weights = {
                axis: Decimal(1)
                / Decimal(str(GCSIM_SUBSTAT_ROLL_VALUES[axis]))
                for axis in self._response_model.response_branch.focus_axes
                if axis in GCSIM_SUBSTAT_ROLL_VALUES
            }
        if not weights:
            return None
        return GcsimOptimizerCandidateResponseModel(
            response_branch=self._response_model.response_branch,
            stat_weights=tuple(
                GcsimOptimizerCandidateStatWeight(
                    axis_key=axis,
                    weight=_decimal_text(weight),
                )
                for axis, weight in weights.items()
            ),
            thresholds=self._response_model.thresholds,
            derivation="retention_useful_stat_magnitude",
        )

    def _crit_value_response_model(
        self,
    ) -> GcsimOptimizerCandidateResponseModel:
        return GcsimOptimizerCandidateResponseModel(
            response_branch=self._response_model.response_branch,
            stat_weights=(
                GcsimOptimizerCandidateStatWeight("cd", "1"),
                GcsimOptimizerCandidateStatWeight("cr", "2"),
            ),
            thresholds=self._response_model.thresholds,
            derivation="retention_raw_crit_value_feature",
        )

    def _reproject_candidate(
        self,
        candidate: GcsimOptimizerLazyWearerCandidate,
        *,
        feature_label: str,
    ) -> GcsimOptimizerLazyWearerCandidate:
        build = candidate.materialized_build
        stats = {key: Decimal(value) for key, value in build.normalized_stats}
        proposal_score = sum(
            (
                stats.get(axis, _ZERO) * weight
                for axis, weight in self._weights.items()
            ),
            _ZERO,
        )
        labels = tuple(sorted({*candidate.feature_labels, feature_label}))
        payload = {
            "schema_version": GCSIM_OPTIMIZER_LAZY_CANDIDATE_SCHEMA_VERSION,
            "target": self._target.to_dict(),
            "response_model_sha256": self._response_model.identity_sha256,
            "assignment": candidate.assignment.to_dict(),
            "wearer_build_identity_sha256": build.wearer_build_identity_sha256,
            "proposal_score": _decimal_text(proposal_score),
        }
        return GcsimOptimizerLazyWearerCandidate(
            target=self._target,
            response_model_sha256=self._response_model.identity_sha256,
            assignment=candidate.assignment,
            materialized_build=build,
            proposal_score=_decimal_text(proposal_score),
            crit_value=candidate.crit_value,
            offpiece_shape=candidate.offpiece_shape,
            feature_labels=labels,
            content_fingerprint=candidate.content_fingerprint,
            candidate_sha256=_canonical_sha256(payload),
        )

    def request_conflict_repair(
        self,
        *,
        blocked_artifact_ids: Sequence[int],
        count: int,
    ) -> GcsimOptimizerLazyCandidateBatch:
        """Generate physical shadow alternatives after a joint conflict."""

        blocked = tuple(
            sorted(set(self._blocked_ids) | set(_positive_ids(blocked_artifact_ids)))
        )
        repair = GcsimOptimizerLazyWearerCandidateGenerator(
            self._run_input,
            target=self._target,
            response_model=self._response_model,
            blocked_artifact_ids=blocked,
            offpiece_shape=self._offpiece_shape,
            _conflict_request=True,
        )
        return repair.take(count)

    def _filtered_slot_map(self) -> Mapping[str, tuple[_IndexedArtifact, ...]]:
        result: dict[str, tuple[_IndexedArtifact, ...]] = {}
        for slot, items in self._index.by_slot:
            accepted = tuple(
                item
                for item in items
                if item.artifact_id not in self._blocked_ids
                and _shape_accepts(
                    self._offpiece_shape,
                    slot,
                    item.package_index == 0,
                )
            )
            result[slot] = accepted
        return MappingProxyType(result)

    def _build_remaining_score_bounds(
        self,
    ) -> Mapping[tuple[int, tuple[int, ...]], Decimal]:
        bounds: dict[tuple[int, tuple[int, ...]], Decimal] = {}
        slot_count = len(GCSIM_OPTIMIZER_ARTIFACT_SLOTS)
        count_states = tuple(
            product(
                *(
                    range(requirement + 1)
                    for requirement in self._package_requirements
                )
            )
        )
        bounds[(slot_count, self._package_requirements)] = _ZERO
        for depth in range(slot_count - 1, -1, -1):
            slot = GCSIM_OPTIMIZER_ARTIFACT_SLOTS[depth]
            best_by_category: dict[int | None, Decimal] = {}
            for artifact in self._slot_map[slot]:
                category = artifact.package_index
                best_by_category[category] = max(
                    best_by_category.get(category, artifact.local_score),
                    artifact.local_score,
                )
            for counts in count_states:
                best = None
                for category, local_score in best_by_category.items():
                    next_counts = list(counts)
                    if category is not None:
                        next_counts[category] = min(
                            next_counts[category] + 1,
                            self._package_requirements[category],
                        )
                    remaining = bounds.get(
                        (depth + 1, tuple(next_counts))
                    )
                    if remaining is None:
                        continue
                    score = local_score + remaining
                    best = score if best is None else max(best, score)
                if best is not None:
                    bounds[(depth, counts)] = best
        return MappingProxyType(bounds)

    def _build_remaining_stat_maxima(
        self,
    ) -> tuple[Mapping[str, Decimal], ...]:
        axes = tuple(item.axis_key for item in self._thresholds)
        suffix: list[dict[str, Decimal]] = [
            {axis: _ZERO for axis in axes}
            for _unused in range(len(GCSIM_OPTIMIZER_ARTIFACT_SLOTS) + 1)
        ]
        for index in range(len(GCSIM_OPTIMIZER_ARTIFACT_SLOTS) - 1, -1, -1):
            slot = GCSIM_OPTIMIZER_ARTIFACT_SLOTS[index]
            suffix[index] = dict(suffix[index + 1])
            for axis in axes:
                suffix[index][axis] += max(
                    (
                        dict(item.stats).get(axis, _ZERO)
                        for item in self._slot_map[slot]
                    ),
                    default=_ZERO,
                )
        return tuple(MappingProxyType(item) for item in suffix)

    def _build_minimum_ids(self) -> tuple[int, ...]:
        return tuple(
            min(
                (item.artifact_id for item in self._slot_map[slot]),
                default=2**63 - 1,
            )
            for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
        )

    def _initialize_heap(self) -> None:
        if any(not self._slot_map[slot] for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS):
            self._exhausted = True
            return
        initial_counts = tuple(
            0 for _unused in self._package_requirements
        )
        initial_bound = self._remaining_score_bounds.get(
            (0, initial_counts)
        )
        if initial_bound is None:
            self._coverage.set_feasibility_pruned += 1
            self._exhausted = True
            return
        initial_stats: tuple[tuple[str, Decimal], ...] = ()
        state = _SearchState(
            depth=0,
            chosen=(),
            stats=initial_stats,
            score=_ZERO,
            package_counts=initial_counts,
            upper_bound=initial_bound,
            threshold_regions=_threshold_regions(initial_stats, self._thresholds),
            minimum_completion_ids=self._minimum_ids_by_slot,
        )
        if self._threshold_possible(state):
            self._push(state)
        else:
            self._coverage.threshold_feasibility_pruned += 1
            self._exhausted = True

    def _expand(self, state: _SearchState) -> None:
        self._coverage.partial_states_expanded += 1
        slot = GCSIM_OPTIMIZER_ARTIFACT_SLOTS[state.depth]
        next_depth = state.depth + 1
        for artifact in self._slot_map[slot]:
            package_counts = list(state.package_counts)
            if artifact.package_index is not None:
                index = artifact.package_index
                package_counts[index] = min(
                    package_counts[index] + 1,
                    self._package_requirements[index],
                )
            package_counts_tuple = tuple(package_counts)
            remaining_bound = self._remaining_score_bounds.get(
                (next_depth, package_counts_tuple)
            )
            if remaining_bound is None:
                self._coverage.set_feasibility_pruned += 1
                continue
            stats = _add_stats(state.stats, artifact.stats)
            score = state.score + artifact.local_score
            minimum_ids = (
                *(item.artifact_id for item in state.chosen),
                artifact.artifact_id,
                *self._minimum_ids_by_slot[next_depth:],
            )
            child = _SearchState(
                depth=next_depth,
                chosen=(*state.chosen, artifact),
                stats=stats,
                score=score,
                package_counts=package_counts_tuple,
                upper_bound=score + remaining_bound,
                threshold_regions=_threshold_regions(
                    stats,
                    self._thresholds,
                ),
                minimum_completion_ids=tuple(minimum_ids),
            )
            if not self._threshold_possible(child):
                self._coverage.threshold_feasibility_pruned += 1
                continue
            self._push(child)

    def _threshold_possible(self, state: _SearchState) -> bool:
        stats = dict(state.stats)
        remaining_max = self._remaining_stat_maxima[state.depth]
        for threshold in self._thresholds:
            value = stats.get(threshold.axis_key, _ZERO)
            if (
                threshold.maximum is not None
                and value > Decimal(threshold.maximum)
            ):
                return False
            if (
                threshold.minimum is not None
                and value + remaining_max[threshold.axis_key]
                < Decimal(threshold.minimum)
            ):
                return False
        return True

    def _push(self, state: _SearchState) -> None:
        self._serial += 1
        heapq.heappush(
            self._heap,
            (
                -state.upper_bound,
                state.minimum_completion_ids,
                self._serial,
                state,
            ),
        )

    def _materialize(
        self,
        state: _SearchState,
    ) -> GcsimOptimizerLazyWearerCandidate | None:
        assignment = GcsimOptimizerWearerArtifactAssignment(
            wearer=self._target.wearer,
            artifact_ids_by_slot={
                slot: artifact.artifact_id
                for slot, artifact in zip(
                    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
                    state.chosen,
                    strict=True,
                )
            },
        )
        result = materialize_gcsim_optimizer_wearer_build(
            self._run_input,
            assignment=assignment,
            target=self._target,
        )
        if not result.ready or result.build is None:
            self._coverage.materialization_failure_count += 1
            return None
        self._coverage.materialized_candidate_count += 1
        build = result.build
        stats = {key: Decimal(value) for key, value in build.normalized_stats}
        proposal_score = sum(
            (
                stats.get(axis, _ZERO) * weight
                for axis, weight in self._weights.items()
            ),
            _ZERO,
        )
        if isinstance(
            self._target.package,
            GcsimFourPieceTargetPackage,
        ):
            target_uid = self._target.package.set_ref.set_uid
            offpieces = tuple(
                slot
                for slot, artifact in build.artifacts_by_slot
                if artifact.set_uid != target_uid
            )
            offpiece_shape = "5p" if not offpieces else offpieces[0]
            package_shape_label = offpiece_shape
        else:
            offpiece_shape = _TWO_PLUS_TWO_SHAPE
            counts = Counter(
                artifact.set_uid
                for _slot, artifact in build.artifacts_by_slot
            )
            package = self._target.package
            package_shape_label = (
                f"{counts[package.set_a.set_uid]}"
                f"+{counts[package.set_b.set_uid]}"
                f"+{5 - counts[package.set_a.set_uid] - counts[package.set_b.set_uid]}"
            )
        crit_value = stats.get("cr", _ZERO) * 2 + stats.get("cd", _ZERO)
        labels = {
            f"shape:{package_shape_label}",
            f"branch:{self._response_model.response_branch.kind.value}",
        }
        labels.update(
            f"threshold:{item.axis_key}"
            for item in self._thresholds
        )
        if any(item.shadow for item in state.chosen):
            labels.add("shadow_alternative")
        if "em" in self._response_model.response_branch.focus_axes:
            labels.add("em_response")
        if (
            self._response_model.response_branch.kind
            is GcsimOptimizerResponseBranchKind.UNUSUAL_MAIN
        ):
            labels.add("unusual_main")
        payload = {
            "schema_version": GCSIM_OPTIMIZER_LAZY_CANDIDATE_SCHEMA_VERSION,
            "target": self._target.to_dict(),
            "response_model_sha256": self._response_model.identity_sha256,
            "assignment": assignment.to_dict(),
            "wearer_build_identity_sha256": build.wearer_build_identity_sha256,
            "proposal_score": _decimal_text(proposal_score),
        }
        return GcsimOptimizerLazyWearerCandidate(
            target=self._target,
            response_model_sha256=self._response_model.identity_sha256,
            assignment=assignment,
            materialized_build=build,
            proposal_score=_decimal_text(proposal_score),
            crit_value=_decimal_text(crit_value),
            offpiece_shape=offpiece_shape,
            feature_labels=tuple(sorted(labels)),
            content_fingerprint=build.compiled_block_sha256,
            candidate_sha256=_canonical_sha256(payload),
        )


def derive_gcsim_optimizer_candidate_response_model(
    response_result: GcsimOptimizerMainResponseResult,
    *,
    response_branch: GcsimOptimizerResponseBranch,
    thresholds: Sequence[GcsimOptimizerCandidateStatThreshold] = (),
) -> GcsimOptimizerCandidateResponseModel:
    """Derive an auditable additive proposal ordering from M4 probe deltas.

    This is deliberately a proposal model, not a DPS oracle.  M6/M7 still
    validate joint candidates with the frozen full-team GCSIM rotation.
    """

    if not isinstance(response_result, GcsimOptimizerMainResponseResult):
        raise GcsimOptimizerLazyCandidateError(
            "response_result must be typed"
        )
    if response_branch not in response_result.branches:
        raise GcsimOptimizerLazyCandidateError(
            "response_branch does not belong to response_result"
        )
    layout_id = response_branch.layout_id
    reference = next(
        (
            item
            for item in response_result.observations
            if item.probe.layout_id == layout_id
            and item.probe.kind is GcsimOptimizerResponseProbeKind.REFERENCE
        ),
        None,
    )
    slopes: dict[str, list[Decimal]] = {}
    if reference is not None and reference.measurement is not None:
        baseline = Decimal(
            str(reference.measurement.score.objective_value)
        )
        for observation in response_result.observations:
            probe = observation.probe
            if (
                probe.layout_id != layout_id
                or probe.kind is not GcsimOptimizerResponseProbeKind.ROLL_EXCHANGE
                or observation.measurement is None
                or probe.exchange_rolls <= 0
            ):
                continue
            if (
                response_branch.focus_axes
                and probe.focus_axes != response_branch.focus_axes
            ):
                continue
            if not response_branch.focus_axes and len(probe.focus_axes) != 1:
                continue
            delta_per_roll = (
                Decimal(str(observation.measurement.score.objective_value))
                - baseline
            ) / Decimal(probe.exchange_rolls)
            for axis in probe.focus_axes:
                roll_value = Decimal(str(GCSIM_SUBSTAT_ROLL_VALUES[axis]))
                per_unit = (
                    delta_per_roll
                    / Decimal(len(probe.focus_axes))
                    / roll_value
                )
                slopes.setdefault(axis, []).append(per_unit)
    axes = (
        response_branch.focus_axes
        if response_branch.focus_axes
        else tuple(GCSIM_SUBSTAT_ROLL_VALUES)
    )
    weights = tuple(
        GcsimOptimizerCandidateStatWeight(
            axis_key=axis,
            weight=_decimal_text(
                max(
                    slopes.get(axis, (_ZERO,)),
                    key=lambda value: (abs(value), value),
                )
            ),
        )
        for axis in axes
    )
    return GcsimOptimizerCandidateResponseModel(
        response_branch=response_branch,
        stat_weights=weights,
        thresholds=tuple(thresholds),
        derivation="m4_max_absolute_observed_slope_per_normalized_stat_unit",
    )


def build_gcsim_optimizer_lazy_wearer_candidate_generator(
    run_input: GcsimOptimizerRunInput,
    *,
    target: GcsimOptimizerWearerTarget,
    response_model: GcsimOptimizerCandidateResponseModel,
    artifact_rows: Sequence[GcsimOptimizerArtifactRecord] | None = None,
) -> GcsimOptimizerLazyWearerCandidateGenerator:
    return GcsimOptimizerLazyWearerCandidateGenerator(
        run_input,
        target=target,
        response_model=response_model,
        artifact_rows=artifact_rows,
    )


def _effective_candidate_thresholds(
    run_input: GcsimOptimizerRunInput,
    *,
    target: GcsimOptimizerWearerTarget,
    response_model: GcsimOptimizerCandidateResponseModel,
) -> tuple[GcsimOptimizerCandidateStatThreshold, ...]:
    by_axis = {
        item.axis_key: item for item in response_model.thresholds
    }
    for axis_key, requested_minimum in (
        effective_gcsim_optimizer_artifact_minimums(
            run_input,
            target=target,
        ).items()
    ):
        current = by_axis.get(axis_key)
        minimum = (
            requested_minimum
            if current is None or current.minimum is None
            else max(
                Decimal(current.minimum),
                requested_minimum,
            )
        )
        maximum = None if current is None else current.maximum
        if maximum is not None and Decimal(maximum) < minimum:
            # A user-requested hard floor outranks a response-model cap.
            maximum = None
        by_axis[axis_key] = (
            GcsimOptimizerCandidateStatThreshold(
                axis_key=axis_key,
                minimum=_decimal_text(minimum),
                maximum=maximum,
            )
        )
    return tuple(
        by_axis[axis_key] for axis_key in sorted(by_axis)
    )


def _build_candidate_index(
    run_input: GcsimOptimizerRunInput,
    *,
    target: GcsimOptimizerWearerTarget,
    response_model: GcsimOptimizerCandidateResponseModel,
    thresholds: Sequence[GcsimOptimizerCandidateStatThreshold],
    artifact_rows: Sequence[GcsimOptimizerArtifactRecord],
) -> _CandidateIndex:
    exclusions: Counter[str] = Counter()
    eligible_count = 0
    by_slot: dict[str, list[_IndexedArtifact]] = {
        slot: [] for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
    }
    override = next(
        (
            item
            for item in run_input.request.four_star_overrides
            if item.wearer == target.wearer
        ),
        None,
    )
    package_uids, _requirements = _package_requirements(target)
    package_index_by_uid = {
        set_uid: index
        for index, set_uid in enumerate(package_uids)
    }
    expected_mains = {
        "flower": "hp",
        "plume": "atk",
        **{
            slot: getattr(response_model.response_branch.layout, slot)
            for slot in _VARIABLE_MAIN_SLOT_KEYS
        },
    }
    weights = response_model.weights_by_axis
    for artifact in sorted(artifact_rows, key=lambda item: item.artifact_id):
        eligibility = evaluate_gcsim_optimizer_artifact_eligibility(
            artifact,
            wearer=target.wearer,
            four_star_override=override,
            package_set_uids=package_uids,
        )
        if not eligibility.eligible:
            exclusions[eligibility.reason] += 1
            continue
        eligible_count += 1
        if artifact.position_key not in by_slot:
            exclusions["artifact_slot_invalid"] += 1
            continue
        vector_result = materialize_gcsim_optimizer_artifact_stat_vector(
            artifact,
            wearer=target.wearer,
        )
        if not vector_result.ready or vector_result.stat_vector is None:
            code = (
                vector_result.diagnostics[0].code
                if vector_result.diagnostics
                else "artifact_stat_vector_invalid"
            )
            exclusions[code] += 1
            continue
        main_contributions = tuple(
            item
            for item in vector_result.stat_vector.contributions
            if item.source_kind == "main"
        )
        if len(main_contributions) != 1:
            exclusions["artifact_main_stat_ambiguous"] += 1
            continue
        main_key = main_contributions[0].gcsim_key
        if main_key != expected_mains[artifact.position_key]:
            exclusions["main_stat_layout_mismatch"] += 1
            continue
        stats = tuple(
            (axis, Decimal(value))
            for axis, value in vector_result.stat_vector.normalized_stats
        )
        local_score = sum(
            (
                dict(stats).get(axis, _ZERO) * weight
                for axis, weight in weights.items()
            ),
            _ZERO,
        )
        by_slot[artifact.position_key].append(
            _IndexedArtifact(
                record=artifact,
                stats=stats,
                local_score=local_score,
                package_index=package_index_by_uid.get(
                    artifact.set_uid
                ),
                main_key=main_key,
            )
        )
    shadow_count = 0
    frozen_rows: list[tuple[str, tuple[_IndexedArtifact, ...]]] = []
    relevant_axes = tuple(
        sorted(
            set(weights)
            | {item.axis_key for item in thresholds}
        )
    )
    for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
        rows = by_slot[slot]
        marked: list[_IndexedArtifact] = []
        for candidate in rows:
            shadow = any(
                other.artifact_id != candidate.artifact_id
                and other.package_index == candidate.package_index
                and _dominates_artifact(other, candidate, relevant_axes, weights)
                for other in rows
            )
            shadow_count += int(shadow)
            marked.append(
                _IndexedArtifact(
                    record=candidate.record,
                    stats=candidate.stats,
                    local_score=candidate.local_score,
                    package_index=candidate.package_index,
                    main_key=candidate.main_key,
                    shadow=shadow,
                )
            )
        frozen_rows.append(
            (
                slot,
                tuple(
                    sorted(
                        marked,
                        key=lambda item: (
                            -item.local_score,
                            item.artifact_id,
                        ),
                    )
                ),
            )
        )
    return _CandidateIndex(
        by_slot=tuple(frozen_rows),
        exclusion_counts=tuple(sorted(exclusions.items())),
        raw_artifact_count=len(artifact_rows),
        eligible_artifact_count=eligible_count,
        shadow_artifact_count=shadow_count,
    )


def _validate_generator_inputs(
    run_input: GcsimOptimizerRunInput,
    target: GcsimOptimizerWearerTarget,
    response_model: GcsimOptimizerCandidateResponseModel,
) -> None:
    if not isinstance(run_input, GcsimOptimizerRunInput):
        raise GcsimOptimizerLazyCandidateError("run_input must be typed")
    if not isinstance(target, GcsimOptimizerWearerTarget):
        raise GcsimOptimizerLazyCandidateError("target must be typed")
    if not isinstance(
        target.package,
        (GcsimFourPieceTargetPackage, GcsimTwoPlusTwoTargetPackage),
    ):
        raise GcsimOptimizerLazyCandidateError(
            "candidate generation requires a concrete 4p or 2p+2p target"
        )
    if not isinstance(response_model, GcsimOptimizerCandidateResponseModel):
        raise GcsimOptimizerLazyCandidateError(
            "response_model must be typed"
        )
    branch = response_model.response_branch
    if branch.wearer != target.wearer or branch.package != target.package:
        raise GcsimOptimizerLazyCandidateError(
            "response branch differs from wearer target"
        )
    if target.wearer not in run_input.request.source_simulation.wearers:
        raise GcsimOptimizerLazyCandidateError(
            "target wearer is outside frozen run input"
        )


def _validate_artifact_row_permutation(
    run_input: GcsimOptimizerRunInput,
    artifact_rows: Sequence[GcsimOptimizerArtifactRecord],
) -> tuple[GcsimOptimizerArtifactRecord, ...]:
    rows = tuple(artifact_rows)
    if any(not isinstance(item, GcsimOptimizerArtifactRecord) for item in rows):
        raise GcsimOptimizerLazyCandidateError(
            "artifact_rows must contain typed frozen records"
        )
    expected = {
        item.artifact_id: item
        for item in run_input.artifact_database.artifacts
    }
    actual = {item.artifact_id: item for item in rows}
    if len(actual) != len(rows) or actual != expected:
        raise GcsimOptimizerLazyCandidateError(
            "artifact_rows must be an exact permutation of frozen database rows"
        )
    return rows


def _package_requirements(target):
    package = target.package
    if isinstance(package, GcsimFourPieceTargetPackage):
        return (package.set_ref.set_uid,), (4,)
    if isinstance(package, GcsimTwoPlusTwoTargetPackage):
        return (
            package.set_a.set_uid,
            package.set_b.set_uid,
        ), (2, 2)
    raise GcsimOptimizerLazyCandidateError(
        "unsupported candidate target package"
    )


def _shape_accepts(
    shape: str | None,
    slot: str,
    target_piece: bool,
) -> bool:
    if shape is None:
        return True
    if shape == "5p":
        return target_piece
    return (not target_piece) if slot == shape else target_piece


def _threshold_regions(
    stats: Sequence[tuple[str, Decimal]],
    thresholds: Sequence[GcsimOptimizerCandidateStatThreshold],
) -> tuple[tuple[str, str], ...]:
    values = dict(stats)
    result: list[tuple[str, str]] = []
    for threshold in thresholds:
        value = values.get(threshold.axis_key, _ZERO)
        if (
            threshold.minimum is not None
            and value < Decimal(threshold.minimum)
        ):
            region = "below"
        elif (
            threshold.maximum is not None
            and value > Decimal(threshold.maximum)
        ):
            region = "above"
        else:
            region = "within"
        result.append((threshold.axis_key, region))
    return tuple(result)


def _thresholds_satisfied(
    stats: Sequence[tuple[str, Decimal]],
    thresholds: Sequence[GcsimOptimizerCandidateStatThreshold],
) -> bool:
    return all(
        region == "within"
        for _axis, region in _threshold_regions(stats, thresholds)
    )


def _add_stats(
    left: Sequence[tuple[str, Decimal]],
    right: Sequence[tuple[str, Decimal]],
) -> tuple[tuple[str, Decimal], ...]:
    values = dict(left)
    for axis, value in right:
        values[axis] = values.get(axis, _ZERO) + value
    return tuple(sorted(values.items()))


def _dominates_artifact(
    left: _IndexedArtifact,
    right: _IndexedArtifact,
    axes: Sequence[str],
    weights: Mapping[str, Decimal],
) -> bool:
    if not axes:
        return False
    left_stats = dict(left.stats)
    right_stats = dict(right.stats)
    comparisons = []
    for axis in axes:
        sign = Decimal(-1) if weights.get(axis, _ZERO) < 0 else Decimal(1)
        comparisons.append(
            sign * left_stats.get(axis, _ZERO)
            >= sign * right_stats.get(axis, _ZERO)
        )
    return all(comparisons) and (
        left.local_score > right.local_score
        or any(
            left_stats.get(axis, _ZERO) != right_stats.get(axis, _ZERO)
            for axis in axes
        )
        or (
            all(
                left_stats.get(axis, _ZERO)
                == right_stats.get(axis, _ZERO)
                for axis in axes
            )
            and left.artifact_id < right.artifact_id
        )
    )


def _pareto_candidate_ids(
    candidates: Sequence[GcsimOptimizerLazyWearerCandidate],
    weights: Mapping[str, Decimal],
) -> tuple[str, ...]:
    axes = tuple(sorted(weights))
    if not axes:
        return tuple(item.candidate_sha256 for item in candidates)
    stat_rows = [
        {
            key: Decimal(value)
            for key, value in item.materialized_build.normalized_stats
        }
        for item in candidates
    ]
    retained: list[str] = []
    for index, candidate in enumerate(candidates):
        row = stat_rows[index]
        dominated = False
        for other_index, other in enumerate(stat_rows):
            if other_index == index:
                continue
            weak = all(
                (
                    other.get(axis, _ZERO) >= row.get(axis, _ZERO)
                    if weights[axis] >= 0
                    else other.get(axis, _ZERO) <= row.get(axis, _ZERO)
                )
                for axis in axes
            )
            strict = any(
                other.get(axis, _ZERO) != row.get(axis, _ZERO)
                for axis in axes
            )
            if weak and strict:
                dominated = True
                break
        if not dominated:
            retained.append(candidate.candidate_sha256)
    return tuple(retained)


def _candidate_rank(
    candidate: GcsimOptimizerLazyWearerCandidate,
) -> tuple[Decimal, tuple[int, ...]]:
    return (-Decimal(candidate.proposal_score), candidate.assignment.artifact_ids)


def _positive_ids(values: Sequence[int]) -> tuple[int, ...]:
    result = tuple(values)
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in result
    ):
        raise GcsimOptimizerLazyCandidateError(
            "blocked artifact IDs must be positive integers"
        )
    return result


def _finite_decimal(value: object, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise GcsimOptimizerLazyCandidateError(
            f"{field_name} must be a finite decimal"
        )
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise GcsimOptimizerLazyCandidateError(
            f"{field_name} must be a finite decimal"
        ) from None
    if not result.is_finite():
        raise GcsimOptimizerLazyCandidateError(
            f"{field_name} must be a finite decimal"
        )
    return result


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_schema(value: int) -> None:
    if value != GCSIM_OPTIMIZER_LAZY_CANDIDATE_SCHEMA_VERSION:
        raise GcsimOptimizerLazyCandidateError(
            "unsupported optimizer lazy-candidate schema"
        )


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GcsimOptimizerLazyCandidateError(
            f"{field_name} must be lowercase SHA-256"
        )


__all__ = [
    "GCSIM_OPTIMIZER_LAZY_CANDIDATE_SCHEMA_VERSION",
    "GcsimOptimizerCandidateResponseModel",
    "GcsimOptimizerCandidateRetentionPolicy",
    "GcsimOptimizerCandidateStatThreshold",
    "GcsimOptimizerCandidateStatWeight",
    "GcsimOptimizerLazyCandidateBatch",
    "GcsimOptimizerLazyCandidateCoverage",
    "GcsimOptimizerLazyCandidateError",
    "GcsimOptimizerLazyWearerCandidate",
    "GcsimOptimizerLazyWearerCandidateGenerator",
    "build_gcsim_optimizer_lazy_wearer_candidate_generator",
    "derive_gcsim_optimizer_candidate_response_model",
]
