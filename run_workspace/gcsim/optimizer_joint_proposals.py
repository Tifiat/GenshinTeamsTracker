"""Global all-different proposal solving for optimizer Milestone 6.

This module combines complete Milestone 5 wearer candidates.  It does not run
GCSIM and never claims that its additive proposal score is team DPS.  The
bounded Cartesian domain is traversed best-first, with exact twenty-ID
all-different validation and optional evidence-bound score adjustments for the
later feedback loop.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import heapq
import json
from math import isfinite, prod
from time import monotonic

from .optimizer_artifact_materializer import (
    GcsimOptimizerCompiledTeamCandidate,
    compile_gcsim_optimizer_team_candidate,
)
from .optimizer_lazy_candidates import (
    GcsimOptimizerLazyWearerCandidate,
    GcsimOptimizerLazyWearerCandidateGenerator,
)
from .optimizer_product_contracts import (
    GcsimOptimizerAccountAssignmentWitness,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerTarget,
)
from .optimizer_run_input import GcsimOptimizerRunInput


GCSIM_OPTIMIZER_JOINT_PROPOSAL_SCHEMA_VERSION = 1


class GcsimOptimizerJointProposalError(ValueError):
    """Fail-closed M6 request or invariant violation."""


class GcsimOptimizerJointProposalStopReason(str, Enum):
    COMPLETED = "completed"
    DOMAIN_EXHAUSTED = "domain_exhausted"
    POOL_EXHAUSTED = "pool_exhausted"
    MODEL_BOUND_PRUNED = "model_bound_pruned"
    STATE_LIMIT_REACHED = "state_limit_reached"
    CANCELLED = "cancelled"
    DEADLINE_REACHED = "deadline_reached"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerJointProposalBudget:
    max_proposals: int = 32
    max_joint_states: int = 250_000
    max_seconds: float = 30.0
    model_score_floor: str | None = None
    schema_version: int = GCSIM_OPTIMIZER_JOINT_PROPOSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in ("max_proposals", "max_joint_states"):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise GcsimOptimizerJointProposalError(
                    f"{field_name} must be a positive integer"
                )
        if (
            isinstance(self.max_seconds, bool)
            or not isinstance(self.max_seconds, (int, float))
            or not isfinite(self.max_seconds)
            or self.max_seconds <= 0
        ):
            raise GcsimOptimizerJointProposalError(
                "max_seconds must be finite and positive"
            )
        if self.model_score_floor is not None:
            object.__setattr__(
                self,
                "model_score_floor",
                _decimal_text(
                    _finite_decimal(
                        self.model_score_floor,
                        "model_score_floor",
                    )
                ),
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "max_proposals": self.max_proposals,
            "max_joint_states": self.max_joint_states,
            "max_seconds": float(self.max_seconds),
            "model_score_floor": self.model_score_floor,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerJointEnrichmentPolicy:
    initial_candidates_per_generator: int = 1
    candidates_per_round: int = 2
    max_rounds: int = 8
    schema_version: int = GCSIM_OPTIMIZER_JOINT_PROPOSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in (
            "initial_candidates_per_generator",
            "candidates_per_round",
            "max_rounds",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise GcsimOptimizerJointProposalError(
                    f"{field_name} must be a positive integer"
                )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerJointScoreAdjustment:
    wearer: GcsimOptimizerWearerIdentity
    candidate_sha256: str
    score_delta: str
    evidence_sha256: str
    reason: str
    schema_version: int = GCSIM_OPTIMIZER_JOINT_PROPOSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerJointProposalError(
                "score adjustment wearer must be typed"
            )
        _require_sha256(self.candidate_sha256, "candidate_sha256")
        _require_sha256(self.evidence_sha256, "evidence_sha256")
        if not self.reason or self.reason != self.reason.strip():
            raise GcsimOptimizerJointProposalError(
                "score adjustment reason must be trimmed text"
            )
        object.__setattr__(
            self,
            "score_delta",
            _decimal_text(
                _finite_decimal(self.score_delta, "score_delta")
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "wearer": self.wearer.to_dict(),
            "candidate_sha256": self.candidate_sha256,
            "score_delta": self.score_delta,
            "evidence_sha256": self.evidence_sha256,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerJointCandidatePool:
    wearer: GcsimOptimizerWearerIdentity
    candidates: tuple[GcsimOptimizerLazyWearerCandidate, ...]
    source_exhausted: bool
    schema_version: int = GCSIM_OPTIMIZER_JOINT_PROPOSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerJointProposalError(
                "candidate pool wearer must be typed"
            )
        if not isinstance(self.source_exhausted, bool):
            raise GcsimOptimizerJointProposalError(
                "source_exhausted must be boolean"
            )
        rows = tuple(self.candidates)
        if any(
            not isinstance(item, GcsimOptimizerLazyWearerCandidate)
            or item.target.wearer != self.wearer
            for item in rows
        ):
            raise GcsimOptimizerJointProposalError(
                "candidate pool rows must belong to its wearer"
            )
        identities = tuple(item.candidate_sha256 for item in rows)
        if len(set(identities)) != len(identities):
            raise GcsimOptimizerJointProposalError(
                "candidate pool contains duplicate candidate identities"
            )
        object.__setattr__(self, "candidates", rows)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "wearer": self.wearer.to_dict(),
            "candidate_count": len(self.candidates),
            "candidate_sha256s": [
                item.candidate_sha256 for item in self.candidates
            ],
            "source_exhausted": self.source_exhausted,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerJointProposal:
    wearer_candidates: tuple[GcsimOptimizerLazyWearerCandidate, ...]
    compiled_candidate: GcsimOptimizerCompiledTeamCandidate
    surrogate_score: str
    changed_wearer_count: int
    diversity_labels: tuple[str, ...]
    proposal_sha256: str
    schema_version: int = GCSIM_OPTIMIZER_JOINT_PROPOSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        rows = tuple(self.wearer_candidates)
        if (
            len(rows) != 4
            or tuple(item.target.wearer.team_slot for item in rows)
            != (1, 2, 3, 4)
        ):
            raise GcsimOptimizerJointProposalError(
                "joint proposal requires four canonical wearer candidates"
            )
        artifact_ids = tuple(
            artifact_id
            for item in rows
            for artifact_id in item.assignment.artifact_ids
        )
        if len(set(artifact_ids)) != 20:
            raise GcsimOptimizerJointProposalError(
                "joint proposal requires twenty distinct artifact IDs"
            )
        if tuple(
            item.assignment
            for item in rows
        ) != self.compiled_candidate.assignment_witness.wearer_assignments:
            raise GcsimOptimizerJointProposalError(
                "compiled candidate differs from proposal assignments"
            )
        _finite_decimal(self.surrogate_score, "surrogate_score")
        if (
            isinstance(self.changed_wearer_count, bool)
            or not isinstance(self.changed_wearer_count, int)
            or not 0 <= self.changed_wearer_count <= 4
        ):
            raise GcsimOptimizerJointProposalError(
                "changed_wearer_count must be zero through four"
            )
        _require_sha256(self.proposal_sha256, "proposal_sha256")
        object.__setattr__(
            self,
            "diversity_labels",
            tuple(sorted(set(self.diversity_labels))),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "wearer_candidate_sha256s": [
                item.candidate_sha256 for item in self.wearer_candidates
            ],
            "compiled_candidate": self.compiled_candidate.to_dict(),
            "surrogate_score": self.surrogate_score,
            "changed_wearer_count": self.changed_wearer_count,
            "diversity_labels": list(self.diversity_labels),
            "proposal_sha256": self.proposal_sha256,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerJointProposalCoverage:
    candidate_counts_by_wearer: tuple[tuple[int, int], ...]
    raw_joint_state_count: int
    popped_state_count: int
    expanded_state_count: int
    conflict_state_count: int
    disjoint_state_count: int
    compiled_rejection_count: int
    model_bound_pruned_state_count: int
    lazy_request_count: int
    lazy_candidate_count: int
    enrichment_round_count: int
    coordinated_change_counts: tuple[tuple[int, int], ...]
    schema_version: int = GCSIM_OPTIMIZER_JOINT_PROPOSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in (
            "raw_joint_state_count",
            "popped_state_count",
            "expanded_state_count",
            "conflict_state_count",
            "disjoint_state_count",
            "compiled_rejection_count",
            "model_bound_pruned_state_count",
            "lazy_request_count",
            "lazy_candidate_count",
            "enrichment_round_count",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise GcsimOptimizerJointProposalError(
                    f"{field_name} must be a non-negative integer"
                )
        if tuple(
            team_slot for team_slot, _count in self.candidate_counts_by_wearer
        ) != (1, 2, 3, 4):
            raise GcsimOptimizerJointProposalError(
                "candidate counts must use canonical team slots"
            )
        if tuple(
            width for width, _count in self.coordinated_change_counts
        ) != (0, 1, 2, 3, 4):
            raise GcsimOptimizerJointProposalError(
                "coordinated change counts must cover zero through four"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_counts_by_wearer": dict(
                self.candidate_counts_by_wearer
            ),
            "raw_joint_state_count": self.raw_joint_state_count,
            "popped_state_count": self.popped_state_count,
            "expanded_state_count": self.expanded_state_count,
            "conflict_state_count": self.conflict_state_count,
            "disjoint_state_count": self.disjoint_state_count,
            "compiled_rejection_count": self.compiled_rejection_count,
            "model_bound_pruned_state_count": (
                self.model_bound_pruned_state_count
            ),
            "lazy_request_count": self.lazy_request_count,
            "lazy_candidate_count": self.lazy_candidate_count,
            "enrichment_round_count": self.enrichment_round_count,
            "coordinated_change_counts": dict(
                self.coordinated_change_counts
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerJointProposalResult:
    status: GcsimOptimizerJointProposalStopReason
    stop_reason: GcsimOptimizerJointProposalStopReason
    run_input_sha256: str
    execution_identity_sha256: str
    targets: tuple[GcsimOptimizerWearerTarget, ...]
    budget: GcsimOptimizerJointProposalBudget
    score_adjustments: tuple[GcsimOptimizerJointScoreAdjustment, ...]
    proposals: tuple[GcsimOptimizerJointProposal, ...]
    coverage: GcsimOptimizerJointProposalCoverage
    elapsed_seconds: float
    schema_version: int = GCSIM_OPTIMIZER_JOINT_PROPOSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if self.status is not self.stop_reason:
            raise GcsimOptimizerJointProposalError(
                "joint proposal status and stop_reason must match"
            )
        _require_sha256(self.run_input_sha256, "run_input_sha256")
        _require_sha256(
            self.execution_identity_sha256,
            "execution_identity_sha256",
        )
        targets = tuple(self.targets)
        if (
            len(targets) != 4
            or tuple(item.wearer.team_slot for item in targets)
            != (1, 2, 3, 4)
        ):
            raise GcsimOptimizerJointProposalError(
                "joint result requires four canonical targets"
            )
        rows = tuple(self.proposals)
        if rows != tuple(sorted(rows, key=_proposal_rank)):
            raise GcsimOptimizerJointProposalError(
                "joint proposals must use deterministic score order"
            )
        if (
            isinstance(self.elapsed_seconds, bool)
            or not isinstance(self.elapsed_seconds, (int, float))
            or not isfinite(self.elapsed_seconds)
            or self.elapsed_seconds < 0
        ):
            raise GcsimOptimizerJointProposalError(
                "elapsed_seconds must be finite and non-negative"
            )
        object.__setattr__(self, "targets", targets)
        adjustments = tuple(self.score_adjustments)
        if any(
            not isinstance(item, GcsimOptimizerJointScoreAdjustment)
            for item in adjustments
        ):
            raise GcsimOptimizerJointProposalError(
                "result score_adjustments must be typed"
            )
        object.__setattr__(self, "score_adjustments", adjustments)
        object.__setattr__(self, "proposals", rows)

    @property
    def best_proposal(self) -> GcsimOptimizerJointProposal | None:
        return self.proposals[0] if self.proposals else None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "stop_reason": self.stop_reason.value,
            "run_input_sha256": self.run_input_sha256,
            "execution_identity_sha256": self.execution_identity_sha256,
            "targets": [item.to_dict() for item in self.targets],
            "budget": self.budget.to_dict(),
            "score_adjustments": [
                item.to_dict() for item in self.score_adjustments
            ],
            "proposals": [item.to_dict() for item in self.proposals],
            "coverage": self.coverage.to_dict(),
            "elapsed_seconds": self.elapsed_seconds,
        }


@dataclass(frozen=True, slots=True)
class _ScoredCandidate:
    candidate: GcsimOptimizerLazyWearerCandidate
    score: Decimal
    source_candidate_sha256s: tuple[str, ...]

    @property
    def artifact_ids(self) -> tuple[int, ...]:
        return self.candidate.assignment.artifact_ids


@dataclass(order=True, frozen=True, slots=True)
class _HeapState:
    negative_score: Decimal
    candidate_sha256s: tuple[str, ...]
    indices: tuple[int, int, int, int] = field(compare=False)


def solve_gcsim_optimizer_joint_proposals(
    run_input: GcsimOptimizerRunInput,
    *,
    targets: Sequence[GcsimOptimizerWearerTarget],
    candidate_pools: Sequence[GcsimOptimizerJointCandidatePool],
    execution_identity_sha256: str,
    budget: GcsimOptimizerJointProposalBudget | None = None,
    score_adjustments: Sequence[GcsimOptimizerJointScoreAdjustment] = (),
    is_cancelled: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] = monotonic,
) -> GcsimOptimizerJointProposalResult:
    """Exactly solve the supplied finite wearer pools in best-first order."""

    request_budget = budget or GcsimOptimizerJointProposalBudget()
    target_rows, pool_rows = _validate_inputs(
        run_input,
        targets=targets,
        candidate_pools=candidate_pools,
        execution_identity_sha256=execution_identity_sha256,
        budget=request_budget,
        score_adjustments=score_adjustments,
    )
    started = clock()
    deadline = started + request_budget.max_seconds
    scored_pools = _score_and_deduplicate_pools(
        pool_rows,
        score_adjustments=score_adjustments,
    )
    candidate_counts = tuple(
        (pool.wearer.team_slot, len(rows))
        for pool, rows in zip(pool_rows, scored_pools, strict=True)
    )
    raw_count = prod(len(rows) for rows in scored_pools)
    if is_cancelled():
        return _result(
            status=GcsimOptimizerJointProposalStopReason.CANCELLED,
            run_input=run_input,
            execution_identity_sha256=execution_identity_sha256,
            targets=target_rows,
            budget=request_budget,
            score_adjustments=tuple(score_adjustments),
            proposals=(),
            candidate_counts=candidate_counts,
            raw_joint_state_count=raw_count,
            elapsed_seconds=max(clock() - started, 0.0),
        )
    if clock() >= deadline:
        return _result(
            status=GcsimOptimizerJointProposalStopReason.DEADLINE_REACHED,
            run_input=run_input,
            execution_identity_sha256=execution_identity_sha256,
            targets=target_rows,
            budget=request_budget,
            score_adjustments=tuple(score_adjustments),
            proposals=(),
            candidate_counts=candidate_counts,
            raw_joint_state_count=raw_count,
            elapsed_seconds=max(clock() - started, 0.0),
        )
    empty_pool = any(not rows for rows in scored_pools)
    if empty_pool:
        return _result(
            status=GcsimOptimizerJointProposalStopReason.POOL_EXHAUSTED,
            run_input=run_input,
            execution_identity_sha256=execution_identity_sha256,
            targets=target_rows,
            budget=request_budget,
            score_adjustments=tuple(score_adjustments),
            proposals=(),
            candidate_counts=candidate_counts,
            raw_joint_state_count=raw_count,
            elapsed_seconds=max(clock() - started, 0.0),
        )

    root_indices = (0, 0, 0, 0)
    root_rows = tuple(
        scored_pools[index][0] for index in range(4)
    )
    root_score = sum((item.score for item in root_rows), Decimal(0))
    heap: list[_HeapState] = [
        _HeapState(
            negative_score=-root_score,
            candidate_sha256s=tuple(
                item.candidate.candidate_sha256 for item in root_rows
            ),
            indices=root_indices,
        )
    ]
    visited = {root_indices}
    proposals: list[GcsimOptimizerJointProposal] = []
    popped = 0
    expanded = 0
    conflicts = 0
    disjoint = 0
    compiled_rejections = 0
    bound_pruned = 0
    coordinated = Counter()
    status = GcsimOptimizerJointProposalStopReason.DOMAIN_EXHAUSTED
    floor = (
        None
        if request_budget.model_score_floor is None
        else Decimal(request_budget.model_score_floor)
    )

    while heap:
        if is_cancelled():
            status = GcsimOptimizerJointProposalStopReason.CANCELLED
            break
        if clock() >= deadline:
            status = GcsimOptimizerJointProposalStopReason.DEADLINE_REACHED
            break
        if popped >= request_budget.max_joint_states:
            status = GcsimOptimizerJointProposalStopReason.STATE_LIMIT_REACHED
            break
        if floor is not None and -heap[0].negative_score < floor:
            bound_pruned += len(heap)
            status = GcsimOptimizerJointProposalStopReason.MODEL_BOUND_PRUNED
            break

        state = heapq.heappop(heap)
        popped += 1
        rows = tuple(
            scored_pools[index][candidate_index]
            for index, candidate_index in enumerate(state.indices)
        )
        artifact_ids = tuple(
            artifact_id for row in rows for artifact_id in row.artifact_ids
        )
        if len(set(artifact_ids)) != 20:
            conflicts += 1
        else:
            disjoint += 1
            proposal = _compile_proposal(
                run_input,
                targets=target_rows,
                rows=rows,
                indices=state.indices,
                execution_identity_sha256=execution_identity_sha256,
            )
            if proposal is None:
                compiled_rejections += 1
            else:
                proposals.append(proposal)
                coordinated[proposal.changed_wearer_count] += 1
                proposals.sort(key=_proposal_rank)
                if len(proposals) >= request_budget.max_proposals:
                    status = GcsimOptimizerJointProposalStopReason.COMPLETED
                    break

        for wearer_index in range(4):
            next_index = state.indices[wearer_index] + 1
            if next_index >= len(scored_pools[wearer_index]):
                continue
            next_indices = list(state.indices)
            next_indices[wearer_index] = next_index
            next_key = tuple(next_indices)
            if next_key in visited:
                continue
            visited.add(next_key)
            next_rows = tuple(
                scored_pools[index][candidate_index]
                for index, candidate_index in enumerate(next_key)
            )
            next_score = sum(
                (item.score for item in next_rows),
                Decimal(0),
            )
            heapq.heappush(
                heap,
                _HeapState(
                    negative_score=-next_score,
                    candidate_sha256s=tuple(
                        item.candidate.candidate_sha256
                        for item in next_rows
                    ),
                    indices=next_key,
                ),
            )
            expanded += 1

    if (
        status is GcsimOptimizerJointProposalStopReason.DOMAIN_EXHAUSTED
        and not proposals
        and all(item.source_exhausted for item in pool_rows)
    ):
        status = GcsimOptimizerJointProposalStopReason.POOL_EXHAUSTED
    return _result(
        status=status,
        run_input=run_input,
        execution_identity_sha256=execution_identity_sha256,
        targets=target_rows,
        budget=request_budget,
        score_adjustments=tuple(score_adjustments),
        proposals=tuple(sorted(proposals, key=_proposal_rank)),
        candidate_counts=candidate_counts,
        raw_joint_state_count=raw_count,
        popped_state_count=popped,
        expanded_state_count=expanded,
        conflict_state_count=conflicts,
        disjoint_state_count=disjoint,
        compiled_rejection_count=compiled_rejections,
        model_bound_pruned_state_count=bound_pruned,
        coordinated_change_counts=tuple(
            (width, coordinated[width]) for width in range(5)
        ),
        elapsed_seconds=max(clock() - started, 0.0),
    )


def solve_gcsim_optimizer_joint_proposals_from_generators(
    run_input: GcsimOptimizerRunInput,
    *,
    targets: Sequence[GcsimOptimizerWearerTarget],
    generators: Sequence[GcsimOptimizerLazyWearerCandidateGenerator],
    execution_identity_sha256: str,
    budget: GcsimOptimizerJointProposalBudget | None = None,
    enrichment: GcsimOptimizerJointEnrichmentPolicy | None = None,
    score_adjustments: Sequence[GcsimOptimizerJointScoreAdjustment] = (),
    is_cancelled: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] = monotonic,
) -> GcsimOptimizerJointProposalResult:
    """Pull M5 streams and request blocked-ID alternatives when necessary."""

    request_budget = budget or GcsimOptimizerJointProposalBudget()
    if not isinstance(request_budget, GcsimOptimizerJointProposalBudget):
        raise GcsimOptimizerJointProposalError("budget must be typed")
    policy = enrichment or GcsimOptimizerJointEnrichmentPolicy()
    if not isinstance(policy, GcsimOptimizerJointEnrichmentPolicy):
        raise GcsimOptimizerJointProposalError(
            "enrichment policy must be typed"
        )
    started = clock()
    overall_deadline = started + request_budget.max_seconds
    target_rows = _canonical_targets(run_input, targets)
    generator_rows = tuple(
        sorted(
            generators,
            key=lambda item: (
                item.target.wearer.team_slot,
                item.response_model.identity_sha256,
            ),
        )
    )
    if not generator_rows:
        raise GcsimOptimizerJointProposalError(
            "joint generator solve requires M5 generators"
        )
    by_wearer: dict[
        GcsimOptimizerWearerIdentity,
        list[GcsimOptimizerLazyWearerCandidateGenerator],
    ] = {target.wearer: [] for target in target_rows}
    for generator in generator_rows:
        if generator.target.wearer not in by_wearer:
            raise GcsimOptimizerJointProposalError(
                "M5 generator wearer is outside joint targets"
            )
        by_wearer[generator.target.wearer].append(generator)
    if any(not by_wearer[target.wearer] for target in target_rows):
        raise GcsimOptimizerJointProposalError(
            "M5 generators must cover all four wearers"
        )

    collected: dict[
        GcsimOptimizerWearerIdentity,
        dict[str, GcsimOptimizerLazyWearerCandidate],
    ] = {target.wearer: {} for target in target_rows}
    source_exhausted: dict[
        GcsimOptimizerWearerIdentity,
        bool,
    ] = {target.wearer: False for target in target_rows}
    lazy_requests = 0
    lazy_candidates = 0
    rounds = 0
    interrupted: GcsimOptimizerJointProposalStopReason | None = None

    def add_batch(
        wearer: GcsimOptimizerWearerIdentity,
        candidates: Sequence[GcsimOptimizerLazyWearerCandidate],
    ) -> int:
        added = 0
        for candidate in candidates:
            if candidate.candidate_sha256 not in collected[wearer]:
                collected[wearer][candidate.candidate_sha256] = candidate
                added += 1
        return added

    for target in target_rows:
        exhausted_flags = []
        for generator in by_wearer[target.wearer]:
            if is_cancelled():
                interrupted = (
                    GcsimOptimizerJointProposalStopReason.CANCELLED
                )
                break
            if clock() >= overall_deadline:
                interrupted = (
                    GcsimOptimizerJointProposalStopReason.DEADLINE_REACHED
                )
                break
            batch = generator.take(policy.initial_candidates_per_generator)
            lazy_requests += 1
            lazy_candidates += add_batch(
                target.wearer,
                batch.candidates,
            )
            exhausted_flags.append(batch.exhausted)
        source_exhausted[target.wearer] = bool(exhausted_flags) and all(
            exhausted_flags
        )
        if interrupted is not None:
            break

    if interrupted is not None:
        counts = tuple(
            (
                target.wearer.team_slot,
                len(collected[target.wearer]),
            )
            for target in target_rows
        )
        return _result(
            status=interrupted,
            run_input=run_input,
            execution_identity_sha256=execution_identity_sha256,
            targets=target_rows,
            budget=request_budget,
            score_adjustments=tuple(score_adjustments),
            proposals=(),
            candidate_counts=counts,
            raw_joint_state_count=prod(count for _slot, count in counts),
            lazy_request_count=lazy_requests,
            lazy_candidate_count=lazy_candidates,
            elapsed_seconds=max(clock() - started, 0.0),
        )

    aggregate_coverage: GcsimOptimizerJointProposalCoverage | None = None
    final_result: GcsimOptimizerJointProposalResult | None = None
    for round_index in range(policy.max_rounds + 1):
        pools = tuple(
            GcsimOptimizerJointCandidatePool(
                wearer=target.wearer,
                candidates=tuple(collected[target.wearer].values()),
                source_exhausted=source_exhausted[target.wearer],
            )
            for target in target_rows
        )
        if is_cancelled():
            interrupted = GcsimOptimizerJointProposalStopReason.CANCELLED
            break
        now = clock()
        if now >= overall_deadline:
            interrupted = (
                GcsimOptimizerJointProposalStopReason.DEADLINE_REACHED
            )
            break
        round_budget = replace(
            request_budget,
            max_seconds=max(overall_deadline - now, 1e-9),
        )
        result = solve_gcsim_optimizer_joint_proposals(
            run_input,
            targets=target_rows,
            candidate_pools=pools,
            execution_identity_sha256=execution_identity_sha256,
            budget=round_budget,
            score_adjustments=score_adjustments,
            is_cancelled=is_cancelled,
            clock=clock,
        )
        aggregate_coverage = _sum_coverage(
            aggregate_coverage,
            result.coverage,
        )
        final_result = result
        if result.status in {
            GcsimOptimizerJointProposalStopReason.CANCELLED,
            GcsimOptimizerJointProposalStopReason.DEADLINE_REACHED,
            GcsimOptimizerJointProposalStopReason.MODEL_BOUND_PRUNED,
            GcsimOptimizerJointProposalStopReason.STATE_LIMIT_REACHED,
        }:
            break
        if round_index >= policy.max_rounds:
            break
        contested = _contested_top_ids(
            pools,
            score_adjustments=score_adjustments,
        )
        if not contested:
            break
        rounds += 1
        added_this_round = 0
        for target in target_rows:
            wearer = target.wearer
            wearer_blocked = tuple(
                sorted(
                    artifact_id
                    for artifact_id in contested
                    if any(
                        artifact_id in candidate.assignment.artifact_ids
                        for candidate in collected[wearer].values()
                    )
                )
            )
            exhausted_flags = []
            for generator in by_wearer[wearer]:
                if is_cancelled():
                    interrupted = (
                        GcsimOptimizerJointProposalStopReason.CANCELLED
                    )
                    break
                if clock() >= overall_deadline:
                    interrupted = (
                        GcsimOptimizerJointProposalStopReason.DEADLINE_REACHED
                    )
                    break
                continuation = generator.take(policy.candidates_per_round)
                lazy_requests += 1
                added = add_batch(wearer, continuation.candidates)
                lazy_candidates += added
                added_this_round += added
                exhausted_flags.append(continuation.exhausted)
                if wearer_blocked:
                    repair = generator.request_conflict_repair(
                        blocked_artifact_ids=wearer_blocked,
                        count=policy.candidates_per_round,
                    )
                    lazy_requests += 1
                    added = add_batch(wearer, repair.candidates)
                    lazy_candidates += added
                    added_this_round += added
            source_exhausted[wearer] = bool(exhausted_flags) and all(
                exhausted_flags
            )
            if interrupted is not None:
                break
        if interrupted is not None:
            break
        if added_this_round == 0:
            break

    if final_result is None:
        counts = tuple(
            (
                target.wearer.team_slot,
                len(collected[target.wearer]),
            )
            for target in target_rows
        )
        final_result = _result(
            status=(
                interrupted
                or GcsimOptimizerJointProposalStopReason.POOL_EXHAUSTED
            ),
            run_input=run_input,
            execution_identity_sha256=execution_identity_sha256,
            targets=target_rows,
            budget=request_budget,
            score_adjustments=tuple(score_adjustments),
            proposals=(),
            candidate_counts=counts,
            raw_joint_state_count=prod(count for _slot, count in counts),
            elapsed_seconds=max(clock() - started, 0.0),
        )
        aggregate_coverage = final_result.coverage
    assert aggregate_coverage is not None
    coverage = replace(
        aggregate_coverage,
        candidate_counts_by_wearer=tuple(
            (
                target.wearer.team_slot,
                len(collected[target.wearer]),
            )
            for target in target_rows
        ),
        lazy_request_count=lazy_requests,
        lazy_candidate_count=lazy_candidates,
        enrichment_round_count=rounds,
    )
    status = interrupted or final_result.status
    return replace(
        final_result,
        status=status,
        stop_reason=status,
        budget=request_budget,
        coverage=coverage,
        elapsed_seconds=max(clock() - started, 0.0),
    )


def _validate_inputs(
    run_input: GcsimOptimizerRunInput,
    *,
    targets: Sequence[GcsimOptimizerWearerTarget],
    candidate_pools: Sequence[GcsimOptimizerJointCandidatePool],
    execution_identity_sha256: str,
    budget: GcsimOptimizerJointProposalBudget,
    score_adjustments: Sequence[GcsimOptimizerJointScoreAdjustment],
) -> tuple[
    tuple[GcsimOptimizerWearerTarget, ...],
    tuple[GcsimOptimizerJointCandidatePool, ...],
]:
    if not isinstance(run_input, GcsimOptimizerRunInput):
        raise GcsimOptimizerJointProposalError("run_input must be typed")
    _require_sha256(
        execution_identity_sha256,
        "execution_identity_sha256",
    )
    if not isinstance(budget, GcsimOptimizerJointProposalBudget):
        raise GcsimOptimizerJointProposalError("budget must be typed")
    target_rows = _canonical_targets(run_input, targets)
    pools = tuple(
        sorted(candidate_pools, key=lambda item: item.wearer.team_slot)
    )
    if (
        len(pools) != 4
        or tuple(item.wearer for item in pools)
        != tuple(item.wearer for item in target_rows)
    ):
        raise GcsimOptimizerJointProposalError(
            "candidate pools must cover the frozen team exactly once"
        )
    adjustments = tuple(score_adjustments)
    if any(
        not isinstance(item, GcsimOptimizerJointScoreAdjustment)
        for item in adjustments
    ):
        raise GcsimOptimizerJointProposalError(
            "score_adjustments must be typed"
        )
    adjustment_keys = tuple(
        (item.wearer, item.candidate_sha256) for item in adjustments
    )
    if len(set(adjustment_keys)) != len(adjustment_keys):
        raise GcsimOptimizerJointProposalError(
            "score adjustments must be unique per wearer/candidate"
        )
    known = {
        (pool.wearer, candidate.candidate_sha256)
        for pool in pools
        for candidate in pool.candidates
    }
    if any(
        (item.wearer, item.candidate_sha256) not in known
        for item in adjustments
    ):
        raise GcsimOptimizerJointProposalError(
            "score adjustment references a candidate outside the pools"
        )
    return target_rows, pools


def _canonical_targets(
    run_input: GcsimOptimizerRunInput,
    targets: Sequence[GcsimOptimizerWearerTarget],
) -> tuple[GcsimOptimizerWearerTarget, ...]:
    rows = tuple(sorted(targets, key=lambda item: item.wearer.team_slot))
    if (
        len(rows) != 4
        or tuple(item.wearer for item in rows)
        != run_input.request.source_simulation.wearers
    ):
        raise GcsimOptimizerJointProposalError(
            "targets must cover the frozen team exactly once"
        )
    return rows


def _score_and_deduplicate_pools(
    pools: Sequence[GcsimOptimizerJointCandidatePool],
    *,
    score_adjustments: Sequence[GcsimOptimizerJointScoreAdjustment],
) -> tuple[tuple[_ScoredCandidate, ...], ...]:
    delta_by_candidate = {
        (item.wearer, item.candidate_sha256): Decimal(item.score_delta)
        for item in score_adjustments
    }
    result: list[tuple[_ScoredCandidate, ...]] = []
    for pool in pools:
        by_assignment: dict[
            tuple[int, ...],
            list[tuple[GcsimOptimizerLazyWearerCandidate, Decimal]],
        ] = {}
        for candidate in pool.candidates:
            score = Decimal(candidate.proposal_score) + delta_by_candidate.get(
                (pool.wearer, candidate.candidate_sha256),
                Decimal(0),
            )
            by_assignment.setdefault(
                candidate.assignment.artifact_ids,
                [],
            ).append((candidate, score))
        rows: list[_ScoredCandidate] = []
        for candidates in by_assignment.values():
            canonical, score = min(
                candidates,
                key=lambda item: (
                    -item[1],
                    item[0].candidate_sha256,
                ),
            )
            rows.append(
                _ScoredCandidate(
                    candidate=canonical,
                    score=score,
                    source_candidate_sha256s=tuple(
                        sorted(
                            item.candidate_sha256
                            for item, _score in candidates
                        )
                    ),
                )
            )
        rows.sort(
            key=lambda item: (
                -item.score,
                item.candidate.assignment.artifact_ids,
                item.candidate.candidate_sha256,
            )
        )
        result.append(tuple(rows))
    return tuple(result)


def _compile_proposal(
    run_input: GcsimOptimizerRunInput,
    *,
    targets: tuple[GcsimOptimizerWearerTarget, ...],
    rows: tuple[_ScoredCandidate, ...],
    indices: tuple[int, int, int, int],
    execution_identity_sha256: str,
) -> GcsimOptimizerJointProposal | None:
    wearer_candidates = tuple(item.candidate for item in rows)
    witness = GcsimOptimizerAccountAssignmentWitness(
        request_sha256=run_input.request.request_sha256,
        artifact_database_input_sha256=(
            run_input.artifact_database.artifact_database_input_sha256
        ),
        wearer_assignments=tuple(
            item.assignment for item in wearer_candidates
        ),
    )
    compiled = compile_gcsim_optimizer_team_candidate(
        run_input,
        assignment_witness=witness,
        targets=targets,
        execution_identity_sha256=execution_identity_sha256,
    )
    if not compiled.ready or compiled.candidate is None:
        return None
    score = sum((item.score for item in rows), Decimal(0))
    changed_count = sum(index > 0 for index in indices)
    labels = {
        label
        for item in wearer_candidates
        for label in item.feature_labels
    }
    payload = {
        "schema_version": GCSIM_OPTIMIZER_JOINT_PROPOSAL_SCHEMA_VERSION,
        "run_input_sha256": run_input.run_input_sha256,
        "candidate_identity_sha256": (
            compiled.candidate.candidate_identity_sha256
        ),
        "wearer_candidate_sha256s": [
            item.candidate_sha256 for item in wearer_candidates
        ],
        "surrogate_score": _decimal_text(score),
    }
    return GcsimOptimizerJointProposal(
        wearer_candidates=wearer_candidates,
        compiled_candidate=compiled.candidate,
        surrogate_score=_decimal_text(score),
        changed_wearer_count=changed_count,
        diversity_labels=tuple(labels),
        proposal_sha256=_canonical_sha256(payload),
    )


def _contested_top_ids(
    pools: Sequence[GcsimOptimizerJointCandidatePool],
    *,
    score_adjustments: Sequence[GcsimOptimizerJointScoreAdjustment],
) -> tuple[int, ...]:
    scored = _score_and_deduplicate_pools(
        pools,
        score_adjustments=score_adjustments,
    )
    if any(not rows for rows in scored):
        return ()
    counts = Counter(
        artifact_id
        for rows in scored
        for artifact_id in rows[0].artifact_ids
    )
    return tuple(
        sorted(
            artifact_id
            for artifact_id, count in counts.items()
            if count > 1
        )
    )


def _result(
    *,
    status: GcsimOptimizerJointProposalStopReason,
    run_input: GcsimOptimizerRunInput,
    execution_identity_sha256: str,
    targets: tuple[GcsimOptimizerWearerTarget, ...],
    budget: GcsimOptimizerJointProposalBudget,
    score_adjustments: tuple[GcsimOptimizerJointScoreAdjustment, ...],
    proposals: tuple[GcsimOptimizerJointProposal, ...],
    candidate_counts: tuple[tuple[int, int], ...],
    raw_joint_state_count: int,
    elapsed_seconds: float,
    popped_state_count: int = 0,
    expanded_state_count: int = 0,
    conflict_state_count: int = 0,
    disjoint_state_count: int = 0,
    compiled_rejection_count: int = 0,
    model_bound_pruned_state_count: int = 0,
    lazy_request_count: int = 0,
    lazy_candidate_count: int = 0,
    enrichment_round_count: int = 0,
    coordinated_change_counts: tuple[tuple[int, int], ...] = (
        (0, 0),
        (1, 0),
        (2, 0),
        (3, 0),
        (4, 0),
    ),
) -> GcsimOptimizerJointProposalResult:
    return GcsimOptimizerJointProposalResult(
        status=status,
        stop_reason=status,
        run_input_sha256=run_input.run_input_sha256,
        execution_identity_sha256=execution_identity_sha256,
        targets=targets,
        budget=budget,
        score_adjustments=score_adjustments,
        proposals=proposals,
        coverage=GcsimOptimizerJointProposalCoverage(
            candidate_counts_by_wearer=candidate_counts,
            raw_joint_state_count=raw_joint_state_count,
            popped_state_count=popped_state_count,
            expanded_state_count=expanded_state_count,
            conflict_state_count=conflict_state_count,
            disjoint_state_count=disjoint_state_count,
            compiled_rejection_count=compiled_rejection_count,
            model_bound_pruned_state_count=(
                model_bound_pruned_state_count
            ),
            lazy_request_count=lazy_request_count,
            lazy_candidate_count=lazy_candidate_count,
            enrichment_round_count=enrichment_round_count,
            coordinated_change_counts=coordinated_change_counts,
        ),
        elapsed_seconds=elapsed_seconds,
    )


def _sum_coverage(
    left: GcsimOptimizerJointProposalCoverage | None,
    right: GcsimOptimizerJointProposalCoverage,
) -> GcsimOptimizerJointProposalCoverage:
    if left is None:
        return right
    coordinated_left = dict(left.coordinated_change_counts)
    coordinated_right = dict(right.coordinated_change_counts)
    return GcsimOptimizerJointProposalCoverage(
        candidate_counts_by_wearer=right.candidate_counts_by_wearer,
        raw_joint_state_count=right.raw_joint_state_count,
        popped_state_count=(
            left.popped_state_count + right.popped_state_count
        ),
        expanded_state_count=(
            left.expanded_state_count + right.expanded_state_count
        ),
        conflict_state_count=(
            left.conflict_state_count + right.conflict_state_count
        ),
        disjoint_state_count=(
            left.disjoint_state_count + right.disjoint_state_count
        ),
        compiled_rejection_count=(
            left.compiled_rejection_count + right.compiled_rejection_count
        ),
        model_bound_pruned_state_count=(
            left.model_bound_pruned_state_count
            + right.model_bound_pruned_state_count
        ),
        lazy_request_count=(
            left.lazy_request_count + right.lazy_request_count
        ),
        lazy_candidate_count=(
            left.lazy_candidate_count + right.lazy_candidate_count
        ),
        enrichment_round_count=(
            left.enrichment_round_count + right.enrichment_round_count
        ),
        coordinated_change_counts=tuple(
            (
                width,
                coordinated_left[width] + coordinated_right[width],
            )
            for width in range(5)
        ),
    )


def _proposal_rank(
    proposal: GcsimOptimizerJointProposal,
) -> tuple[Decimal, tuple[str, ...]]:
    return (
        -Decimal(proposal.surrogate_score),
        tuple(
            item.candidate_sha256
            for item in proposal.wearer_candidates
        ),
    )


def _finite_decimal(value: object, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise GcsimOptimizerJointProposalError(
            f"{field_name} must be a finite decimal"
        )
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise GcsimOptimizerJointProposalError(
            f"{field_name} must be a finite decimal"
        ) from None
    if not result.is_finite():
        raise GcsimOptimizerJointProposalError(
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
    if value != GCSIM_OPTIMIZER_JOINT_PROPOSAL_SCHEMA_VERSION:
        raise GcsimOptimizerJointProposalError(
            "unsupported optimizer joint-proposal schema"
        )


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GcsimOptimizerJointProposalError(
            f"{field_name} must be lowercase SHA-256"
        )


__all__ = [
    "GCSIM_OPTIMIZER_JOINT_PROPOSAL_SCHEMA_VERSION",
    "GcsimOptimizerJointCandidatePool",
    "GcsimOptimizerJointEnrichmentPolicy",
    "GcsimOptimizerJointProposal",
    "GcsimOptimizerJointProposalBudget",
    "GcsimOptimizerJointProposalCoverage",
    "GcsimOptimizerJointProposalError",
    "GcsimOptimizerJointProposalResult",
    "GcsimOptimizerJointProposalStopReason",
    "GcsimOptimizerJointScoreAdjustment",
    "solve_gcsim_optimizer_joint_proposals",
    "solve_gcsim_optimizer_joint_proposals_from_generators",
]
