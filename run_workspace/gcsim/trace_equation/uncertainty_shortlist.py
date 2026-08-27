"""Deterministic zero-engine planning for bounded exact finalists.

The planner consumes already-computed frozen-boundary scores.  It retains
ordinary numeric leaders and bounded additional representatives of reachable
or unresolved uncertainty.  It only freezes identities and reasons; it cannot
launch GCSIM and never turns omission from the exact batch into a prune proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Callable, Hashable

from .contracts import TraceContractError, canonical_sha256
from .frozen_boundaries import FrozenBoundaryScore


UNCERTAINTY_SHORTLIST_POLICY_SCHEMA_VERSION = 1
UNCERTAINTY_SHORTLIST_POLICY_KIND = (
    "gtt.trace_equation.uncertainty_shortlist_policy"
)
EXACT_FINALIST_REQUEST_SCHEMA_VERSION = 1
EXACT_FINALIST_REQUEST_KIND = "gtt.trace_equation.exact_finalist_request"
UNCERTAINTY_SHORTLIST_PLAN_SCHEMA_VERSION = 1
UNCERTAINTY_SHORTLIST_PLAN_KIND = "gtt.trace_equation.uncertainty_shortlist_plan"


class FinalistReason(str, Enum):
    NUMERIC_LEADER = "NUMERIC_LEADER"
    REACHABLE_UNCERTAINTY_REPRESENTATIVE = (
        "REACHABLE_UNCERTAINTY_REPRESENTATIVE"
    )
    UNRESOLVED_UNCERTAINTY_REPRESENTATIVE = (
        "UNRESOLVED_UNCERTAINTY_REPRESENTATIVE"
    )


@dataclass(frozen=True, slots=True)
class UncertaintyShortlistPolicy:
    finalist_limit: int
    numeric_leader_limit: int
    reachable_representative_limit: int
    unresolved_representative_limit: int
    schema_version: int = UNCERTAINTY_SHORTLIST_POLICY_SCHEMA_VERSION
    kind: str = UNCERTAINTY_SHORTLIST_POLICY_KIND

    def __post_init__(self) -> None:
        if self.schema_version != UNCERTAINTY_SHORTLIST_POLICY_SCHEMA_VERSION:
            raise TraceContractError("uncertainty shortlist policy schema mismatch")
        if self.kind != UNCERTAINTY_SHORTLIST_POLICY_KIND:
            raise TraceContractError("uncertainty shortlist policy kind mismatch")
        _positive_int(self.finalist_limit, "finalist_limit")
        _positive_int(self.numeric_leader_limit, "numeric_leader_limit")
        _nonnegative_int(
            self.reachable_representative_limit,
            "reachable_representative_limit",
        )
        _nonnegative_int(
            self.unresolved_representative_limit,
            "unresolved_representative_limit",
        )
        reserved = (
            self.numeric_leader_limit
            + self.reachable_representative_limit
            + self.unresolved_representative_limit
        )
        if reserved > self.finalist_limit:
            raise TraceContractError(
                "shortlist lane limits exceed the shared finalist limit"
            )

    @property
    def policy_sha256(self) -> str:
        return canonical_sha256(self.to_dict(include_hash=False))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        row: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "finalist_limit": self.finalist_limit,
            "numeric_leader_limit": self.numeric_leader_limit,
            "reachable_representative_limit": (
                self.reachable_representative_limit
            ),
            "unresolved_representative_limit": (
                self.unresolved_representative_limit
            ),
        }
        if include_hash:
            row["policy_sha256"] = self.policy_sha256
        return row


@dataclass(frozen=True, slots=True)
class ExactFinalistRequest:
    ordinal: int
    candidate_sha256: str
    score_sha256: str
    offline_candidate_damage: float
    estimated_delta: float
    reasons: tuple[FinalistReason, ...]
    candidate_reachable_whole_frozen_share: float
    candidate_reachable_frozen_input_share: float
    candidate_reachable_topology_share: float
    candidate_reachable_boundary_count: int
    candidate_unresolved_boundary_count: int
    fidelity_sha256: str
    seed_panel_sha256: str
    schema_version: int = EXACT_FINALIST_REQUEST_SCHEMA_VERSION
    kind: str = EXACT_FINALIST_REQUEST_KIND

    def __post_init__(self) -> None:
        if self.schema_version != EXACT_FINALIST_REQUEST_SCHEMA_VERSION:
            raise TraceContractError("exact finalist request schema mismatch")
        if self.kind != EXACT_FINALIST_REQUEST_KIND:
            raise TraceContractError("exact finalist request kind mismatch")
        _nonnegative_int(self.ordinal, "ordinal")
        for value, name in (
            (self.candidate_sha256, "candidate_sha256"),
            (self.score_sha256, "score_sha256"),
            (self.fidelity_sha256, "fidelity_sha256"),
            (self.seed_panel_sha256, "seed_panel_sha256"),
        ):
            _sha256(value, name)
        _finite(self.offline_candidate_damage, "offline_candidate_damage")
        _finite(self.estimated_delta, "estimated_delta")
        if (
            not isinstance(self.reasons, tuple)
            or not self.reasons
            or any(not isinstance(row, FinalistReason) for row in self.reasons)
            or tuple(sorted(set(self.reasons), key=lambda row: row.value))
            != self.reasons
        ):
            raise TraceContractError("finalist reasons must be canonical and non-empty")
        for value, name in (
            (
                self.candidate_reachable_whole_frozen_share,
                "candidate_reachable_whole_frozen_share",
            ),
            (
                self.candidate_reachable_frozen_input_share,
                "candidate_reachable_frozen_input_share",
            ),
            (
                self.candidate_reachable_topology_share,
                "candidate_reachable_topology_share",
            ),
        ):
            _unit_interval(value, name)
        _nonnegative_int(
            self.candidate_reachable_boundary_count,
            "candidate_reachable_boundary_count",
        )
        _nonnegative_int(
            self.candidate_unresolved_boundary_count,
            "candidate_unresolved_boundary_count",
        )

    @property
    def request_sha256(self) -> str:
        return canonical_sha256(self.to_dict(include_hash=False))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        row: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "ordinal": self.ordinal,
            "candidate_sha256": self.candidate_sha256,
            "score_sha256": self.score_sha256,
            "offline_candidate_damage": self.offline_candidate_damage,
            "estimated_delta": self.estimated_delta,
            "reasons": [item.value for item in self.reasons],
            "candidate_reachable_whole_frozen_share": (
                self.candidate_reachable_whole_frozen_share
            ),
            "candidate_reachable_frozen_input_share": (
                self.candidate_reachable_frozen_input_share
            ),
            "candidate_reachable_topology_share": (
                self.candidate_reachable_topology_share
            ),
            "candidate_reachable_boundary_count": (
                self.candidate_reachable_boundary_count
            ),
            "candidate_unresolved_boundary_count": (
                self.candidate_unresolved_boundary_count
            ),
            "fidelity_sha256": self.fidelity_sha256,
            "seed_panel_sha256": self.seed_panel_sha256,
        }
        if include_hash:
            row["request_sha256"] = self.request_sha256
        return row


@dataclass(frozen=True, slots=True)
class UncertaintyShortlistPlan:
    evidence_sha256: str
    policy: UncertaintyShortlistPolicy
    fidelity_sha256: str
    seed_panel_sha256: str
    input_candidate_count: int
    duplicate_candidate_count: int
    numeric_candidate_count: int
    reachable_uncertainty_candidate_count: int
    unresolved_uncertainty_candidate_count: int
    requests: tuple[ExactFinalistRequest, ...]
    engine_call_count: int = 0
    execution_authorized: bool = False
    hard_prune_allowed: bool = False
    schema_version: int = UNCERTAINTY_SHORTLIST_PLAN_SCHEMA_VERSION
    kind: str = UNCERTAINTY_SHORTLIST_PLAN_KIND

    def __post_init__(self) -> None:
        if self.schema_version != UNCERTAINTY_SHORTLIST_PLAN_SCHEMA_VERSION:
            raise TraceContractError("uncertainty shortlist plan schema mismatch")
        if self.kind != UNCERTAINTY_SHORTLIST_PLAN_KIND:
            raise TraceContractError("uncertainty shortlist plan kind mismatch")
        if not isinstance(self.policy, UncertaintyShortlistPolicy):
            raise TraceContractError("shortlist plan policy is invalid")
        for value, name in (
            (self.evidence_sha256, "evidence_sha256"),
            (self.fidelity_sha256, "fidelity_sha256"),
            (self.seed_panel_sha256, "seed_panel_sha256"),
        ):
            _sha256(value, name)
        for value, name in (
            (self.input_candidate_count, "input_candidate_count"),
            (self.duplicate_candidate_count, "duplicate_candidate_count"),
            (self.numeric_candidate_count, "numeric_candidate_count"),
            (
                self.reachable_uncertainty_candidate_count,
                "reachable_uncertainty_candidate_count",
            ),
            (
                self.unresolved_uncertainty_candidate_count,
                "unresolved_uncertainty_candidate_count",
            ),
        ):
            _nonnegative_int(value, name)
        if (
            self.input_candidate_count - self.duplicate_candidate_count
            != self.numeric_candidate_count
        ):
            raise TraceContractError("shortlist candidate count partition mismatch")
        if (
            self.reachable_uncertainty_candidate_count
            > self.numeric_candidate_count
            or self.unresolved_uncertainty_candidate_count
            > self.numeric_candidate_count
        ):
            raise TraceContractError("shortlist uncertainty count exceeds candidates")
        if not isinstance(self.requests, tuple) or any(
            not isinstance(row, ExactFinalistRequest) for row in self.requests
        ):
            raise TraceContractError("shortlist requests must be immutable")
        if len(self.requests) > self.policy.finalist_limit:
            raise TraceContractError("shortlist exceeds shared finalist limit")
        if tuple(row.ordinal for row in self.requests) != tuple(
            range(len(self.requests))
        ):
            raise TraceContractError("shortlist request ordinals are not contiguous")
        candidate_ids = tuple(row.candidate_sha256 for row in self.requests)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise TraceContractError("shortlist contains duplicate candidate requests")
        if any(
            row.fidelity_sha256 != self.fidelity_sha256
            or row.seed_panel_sha256 != self.seed_panel_sha256
            for row in self.requests
        ):
            raise TraceContractError("shortlist request execution identity mismatch")
        if self.engine_call_count != 0:
            raise TraceContractError("shortlist planning cannot call the engine")
        if self.execution_authorized:
            raise TraceContractError("shortlist planning cannot authorize execution")
        if self.hard_prune_allowed:
            raise TraceContractError("shortlist omission cannot authorize pruning")

    @property
    def selected_candidate_count(self) -> int:
        return len(self.requests)

    @property
    def omitted_candidate_count(self) -> int:
        return self.numeric_candidate_count - self.selected_candidate_count

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(self.to_dict(include_hash=False))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        row: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "evidence_sha256": self.evidence_sha256,
            "policy": self.policy.to_dict(),
            "fidelity_sha256": self.fidelity_sha256,
            "seed_panel_sha256": self.seed_panel_sha256,
            "input_candidate_count": self.input_candidate_count,
            "duplicate_candidate_count": self.duplicate_candidate_count,
            "numeric_candidate_count": self.numeric_candidate_count,
            "reachable_uncertainty_candidate_count": (
                self.reachable_uncertainty_candidate_count
            ),
            "unresolved_uncertainty_candidate_count": (
                self.unresolved_uncertainty_candidate_count
            ),
            "selected_candidate_count": self.selected_candidate_count,
            "omitted_candidate_count": self.omitted_candidate_count,
            "requests": [row.to_dict() for row in self.requests],
            "engine_call_count": 0,
            "execution_authorized": False,
            "hard_prune_allowed": False,
        }
        if include_hash:
            row["plan_sha256"] = self.plan_sha256
        return row


def build_uncertainty_shortlist_plan(
    scores: tuple[FrozenBoundaryScore, ...],
    *,
    policy: UncertaintyShortlistPolicy,
    fidelity_sha256: str,
    seed_panel_sha256: str,
) -> UncertaintyShortlistPlan:
    """Freeze one bounded exact-finalist request set without executing it."""

    if not isinstance(scores, tuple) or not scores:
        raise TraceContractError("shortlist planning requires candidate scores")
    if any(not isinstance(row, FrozenBoundaryScore) for row in scores):
        raise TraceContractError("shortlist inputs must be FrozenBoundaryScore")
    if not isinstance(policy, UncertaintyShortlistPolicy):
        raise TraceContractError("shortlist policy is invalid")
    _sha256(fidelity_sha256, "fidelity_sha256")
    _sha256(seed_panel_sha256, "seed_panel_sha256")

    evidence_ids = {row.observed_score.evidence_sha256 for row in scores}
    if len(evidence_ids) != 1:
        raise TraceContractError("shortlist scores must share one trace evidence")
    baselines = tuple(row.baseline_estimate for row in scores)
    if any(not _close(value, baselines[0]) for value in baselines[1:]):
        raise TraceContractError("shortlist scores must share one baseline")

    unique: dict[str, FrozenBoundaryScore] = {}
    duplicate_count = 0
    for score in scores:
        previous = unique.get(score.candidate_sha256)
        if previous is None:
            unique[score.candidate_sha256] = score
            continue
        duplicate_count += 1
        if previous.score_sha256 != score.score_sha256:
            raise TraceContractError("duplicate candidate has conflicting score")

    numeric_order = sorted(unique.values(), key=_numeric_order_key)
    numeric_ids = {
        row.candidate_sha256
        for row in numeric_order[: policy.numeric_leader_limit]
    }

    selected_order = [
        row.candidate_sha256
        for row in numeric_order[: policy.numeric_leader_limit]
    ]
    selected_ids = set(selected_order)

    reachable = [row for row in numeric_order if _has_reachable_uncertainty(row)]
    reachable_order = _representative_order(reachable, _reachable_signature)
    _append_unique(
        selected_order,
        selected_ids,
        reachable_order,
        policy.reachable_representative_limit,
    )

    unresolved = [row for row in numeric_order if _has_unresolved_uncertainty(row)]
    unresolved_order = _representative_order(unresolved, _unresolved_signature)
    _append_unique(
        selected_order,
        selected_ids,
        unresolved_order,
        policy.unresolved_representative_limit,
    )

    score_by_id = {row.candidate_sha256: row for row in numeric_order}
    requests = tuple(
        _request(
            ordinal,
            score_by_id[candidate_id],
            numeric_ids=numeric_ids,
            fidelity_sha256=fidelity_sha256,
            seed_panel_sha256=seed_panel_sha256,
        )
        for ordinal, candidate_id in enumerate(selected_order)
    )
    return UncertaintyShortlistPlan(
        evidence_sha256=next(iter(evidence_ids)),
        policy=policy,
        fidelity_sha256=fidelity_sha256,
        seed_panel_sha256=seed_panel_sha256,
        input_candidate_count=len(scores),
        duplicate_candidate_count=duplicate_count,
        numeric_candidate_count=len(numeric_order),
        reachable_uncertainty_candidate_count=len(reachable),
        unresolved_uncertainty_candidate_count=len(unresolved),
        requests=requests,
    )


def _request(
    ordinal: int,
    score: FrozenBoundaryScore,
    *,
    numeric_ids: set[str],
    fidelity_sha256: str,
    seed_panel_sha256: str,
) -> ExactFinalistRequest:
    coverage = score.coverage
    reasons: set[FinalistReason] = set()
    if score.candidate_sha256 in numeric_ids:
        reasons.add(FinalistReason.NUMERIC_LEADER)
    if _has_reachable_uncertainty(score):
        reasons.add(FinalistReason.REACHABLE_UNCERTAINTY_REPRESENTATIVE)
    if _has_unresolved_uncertainty(score):
        reasons.add(FinalistReason.UNRESOLVED_UNCERTAINTY_REPRESENTATIVE)
    return ExactFinalistRequest(
        ordinal=ordinal,
        candidate_sha256=score.candidate_sha256,
        score_sha256=score.score_sha256,
        offline_candidate_damage=score.candidate_estimate,
        estimated_delta=score.estimated_delta,
        reasons=tuple(sorted(reasons, key=lambda row: row.value)),
        candidate_reachable_whole_frozen_share=(
            coverage.candidate_reachable_whole_frozen_share
        ),
        candidate_reachable_frozen_input_share=(
            coverage.candidate_reachable_frozen_input_share
        ),
        candidate_reachable_topology_share=(
            coverage.candidate_reachable_topology_share
        ),
        candidate_reachable_boundary_count=(
            coverage.candidate_reachable_boundary_count
        ),
        candidate_unresolved_boundary_count=(
            coverage.candidate_unresolved_boundary_count
        ),
        fidelity_sha256=fidelity_sha256,
        seed_panel_sha256=seed_panel_sha256,
    )


def _append_unique(
    selected_order: list[str],
    selected_ids: set[str],
    candidates: list[FrozenBoundaryScore],
    limit: int,
) -> None:
    represented = 0
    for score in candidates:
        if represented >= limit:
            return
        if score.candidate_sha256 in selected_ids:
            represented += 1
            continue
        selected_order.append(score.candidate_sha256)
        selected_ids.add(score.candidate_sha256)
        represented += 1


def _representative_order(
    candidates: list[FrozenBoundaryScore],
    signature: Callable[[FrozenBoundaryScore], Hashable],
) -> list[FrozenBoundaryScore]:
    buckets: dict[Hashable, list[FrozenBoundaryScore]] = {}
    for score in candidates:
        buckets.setdefault(signature(score), []).append(score)
    for rows in buckets.values():
        rows.sort(key=_numeric_order_key)
    leaders = sorted(
        (rows[0] for rows in buckets.values()),
        key=_uncertainty_order_key,
    )
    repeated = sorted(
        (score for rows in buckets.values() for score in rows[1:]),
        key=_uncertainty_order_key,
    )
    return leaders + repeated


def _numeric_order_key(score: FrozenBoundaryScore) -> tuple[float, str]:
    return (-score.candidate_estimate, score.candidate_sha256)


def _uncertainty_order_key(
    score: FrozenBoundaryScore,
) -> tuple[float, float, float, int, float, str]:
    coverage = score.coverage
    return (
        -coverage.candidate_reachable_whole_frozen_share,
        -coverage.candidate_reachable_topology_share,
        -coverage.candidate_reachable_frozen_input_share,
        -coverage.candidate_reachable_boundary_count,
        -score.candidate_estimate,
        score.candidate_sha256,
    )


def _has_reachable_uncertainty(score: FrozenBoundaryScore) -> bool:
    coverage = score.coverage
    return bool(
        coverage.candidate_reachable_boundary_count
        or coverage.candidate_reachable_whole_frozen_damage
        or coverage.candidate_reachable_frozen_input_damage
        or coverage.candidate_reachable_topology_damage
    )


def _has_unresolved_uncertainty(score: FrozenBoundaryScore) -> bool:
    coverage = score.coverage
    return bool(
        coverage.candidate_unresolved_boundary_count
        or coverage.candidate_dependency_gap_codes
    )


def _reachable_signature(score: FrozenBoundaryScore) -> Hashable:
    coverage = score.coverage
    return (
        coverage.candidate_reachable_whole_frozen_damage > 0.0,
        coverage.candidate_reachable_frozen_input_damage > 0.0,
        coverage.candidate_reachable_topology_damage > 0.0,
        coverage.global_input_uncertainty_codes,
        coverage.global_topology_uncertainty_codes,
    )


def _unresolved_signature(score: FrozenBoundaryScore) -> Hashable:
    coverage = score.coverage
    return (
        coverage.candidate_dependency_gap_codes,
        coverage.global_input_uncertainty_codes,
        coverage.global_topology_uncertainty_codes,
    )


def _positive_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TraceContractError(f"{field_name} must be a positive integer")


def _nonnegative_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TraceContractError(f"{field_name} must be a non-negative integer")


def _finite(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceContractError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)):
        raise TraceContractError(f"{field_name} must be finite")


def _unit_interval(value: object, field_name: str) -> None:
    _finite(value, field_name)
    if float(value) < 0.0 or float(value) > 1.0:
        raise TraceContractError(f"{field_name} must be in [0, 1]")


def _sha256(value: object, field_name: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise TraceContractError(f"{field_name} must be lowercase SHA-256")


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-7)


__all__ = [
    "EXACT_FINALIST_REQUEST_KIND",
    "EXACT_FINALIST_REQUEST_SCHEMA_VERSION",
    "UNCERTAINTY_SHORTLIST_PLAN_KIND",
    "UNCERTAINTY_SHORTLIST_PLAN_SCHEMA_VERSION",
    "UNCERTAINTY_SHORTLIST_POLICY_KIND",
    "UNCERTAINTY_SHORTLIST_POLICY_SCHEMA_VERSION",
    "ExactFinalistRequest",
    "FinalistReason",
    "UncertaintyShortlistPlan",
    "UncertaintyShortlistPolicy",
    "build_uncertainty_shortlist_plan",
]
