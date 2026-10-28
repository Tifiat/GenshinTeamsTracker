"""Deterministic bounded full-team composer for theoretical 4p farming search.

One-wearer screening scores are only an ordering hint.  They cannot be added to
predict a team result because set ownership, non-stacking buffs, reactions, and
rotation thresholds interact.  This module therefore asks a caller-provided
batch simulator to evaluate every retained *joint* state as a complete team.

The composer is engine-agnostic and performs no filesystem or subprocess work.
The simulator adapter owns materialized configs, cache lookup, cancellation,
and GCSIM processes; this layer owns deterministic seeds, coordinate/pair
moves, recall-first beam retention, budgets, and an auditable trace.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
from itertools import combinations, product
import json
from math import isfinite
from time import monotonic
from typing import Callable, Iterable, Mapping, Protocol, Sequence

from .farming_search import (
    CandidateEvaluation,
    FourPieceSetState,
    SearchSurvivor,
    SetProfileCandidate,
    SURVIVOR_NOVEL_BRANCH,
    SURVIVOR_PROFILE_COVERAGE,
    SURVIVOR_REQUIRED_PROFILE,
    SURVIVOR_UNCERTAIN,
    SURVIVOR_WEARER_COVERAGE,
)


TEAM_SIM_PASSED = "passed"
TEAM_SIM_FAILED = "failed"
TEAM_SIM_TIMEOUT = "timeout"
TEAM_SIM_CANCELLED = "cancelled"

TEAM_SEARCH_COMPLETED = "completed"
TEAM_SEARCH_BUDGET_EXHAUSTED = "budget_exhausted"
TEAM_SEARCH_DEADLINE_REACHED = "deadline_reached"
TEAM_SEARCH_CANCELLED = "cancelled"
TEAM_SEARCH_NO_SUCCESS = "no_success"
TEAM_SEARCH_DOMAIN_EXHAUSTED = "domain_exhausted"
TEAM_SEARCH_POLICY_EXHAUSTED = "policy_exhausted"
TEAM_SEARCH_ROUND_LIMIT_REACHED = "round_limit_reached"

FULL_TEAM_COMPOSER_PROVENANCE_SCHEMA = 2

_SIM_STATUSES = {
    TEAM_SIM_PASSED,
    TEAM_SIM_FAILED,
    TEAM_SIM_TIMEOUT,
    TEAM_SIM_CANCELLED,
}
_SEARCH_RESULT_STATUSES = {
    TEAM_SEARCH_COMPLETED,
    TEAM_SEARCH_BUDGET_EXHAUSTED,
    TEAM_SEARCH_DEADLINE_REACHED,
    TEAM_SEARCH_CANCELLED,
    TEAM_SEARCH_NO_SUCCESS,
    TEAM_SEARCH_DOMAIN_EXHAUSTED,
    TEAM_SEARCH_POLICY_EXHAUSTED,
    TEAM_SEARCH_ROUND_LIMIT_REACHED,
}

ProbeKey = tuple[tuple[str, str, str, str, str], ...]
PhysicalKey = tuple[tuple[str, str, str, str], ...]


class FullTeamComposerError(ValueError):
    """Raised when the search contract or simulator response is inconsistent."""


@dataclass(frozen=True, slots=True)
class FullTeamPhysicalState:
    choices: tuple[FourPieceSetState, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "choices", tuple(self.choices))
        if not self.choices:
            raise FullTeamComposerError("a physical team state must not be empty")
        wearer_ids = tuple(choice.wearer_id for choice in self.choices)
        if len(set(wearer_ids)) != len(wearer_ids):
            raise FullTeamComposerError("physical team wearer ids must be unique")

    @property
    def key(self) -> PhysicalKey:
        return tuple(choice.key for choice in self.choices)


@dataclass(frozen=True, slots=True)
class FullTeamProbeState:
    choices: tuple[SetProfileCandidate, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "choices", tuple(self.choices))
        if not self.choices:
            raise FullTeamComposerError("a probe team state must not be empty")
        wearer_ids = tuple(choice.state.wearer_id for choice in self.choices)
        if len(set(wearer_ids)) != len(wearer_ids):
            raise FullTeamComposerError("probe team wearer ids must be unique")

    @property
    def probe_key(self) -> ProbeKey:
        return tuple(choice.key for choice in self.choices)

    @property
    def physical_state(self) -> FullTeamPhysicalState:
        return FullTeamPhysicalState(
            choices=tuple(choice.state for choice in self.choices)
        )

    @property
    def physical_key(self) -> PhysicalKey:
        return self.physical_state.key

    @property
    def wearer_ids(self) -> tuple[str, ...]:
        return tuple(choice.state.wearer_id for choice in self.choices)


@dataclass(frozen=True, slots=True)
class FullTeamCandidatePool:
    wearer_id: str
    survivors: tuple[SearchSurvivor, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "survivors", tuple(self.survivors))
        _require_identifier(self.wearer_id, field_name="wearer_id")
        if not self.survivors:
            raise FullTeamComposerError(
                f"wearer {self.wearer_id!r} has no screening survivors"
            )
        keys: set[tuple[str, str, str, str, str]] = set()
        for survivor in self.survivors:
            candidate = survivor.evaluation.candidate
            if candidate.state.wearer_id != self.wearer_id:
                raise FullTeamComposerError(
                    "candidate pool contains a survivor for another wearer"
                )
            if candidate.key in keys:
                raise FullTeamComposerError(
                    f"wearer {self.wearer_id!r} pool contains duplicate candidates"
                )
            keys.add(candidate.key)


@dataclass(frozen=True, slots=True)
class FullTeamComposerBudget:
    max_total_evaluations: int
    max_seed_evaluations: int
    max_rounds: int
    max_coordinate_evaluations_per_round: int
    max_pair_evaluations_per_round: int
    pair_frontier_per_wearer: int
    beam_width: int
    beam_top_slots: int
    beam_uncertain_slots: int
    beam_novelty_slots: int
    max_physical_finalists: int
    confidence_sigma: float
    relative_uncertainty_margin: float
    max_seconds: float
    per_evaluation_timeout_seconds: float

    def __post_init__(self) -> None:
        positive_ints = (
            "max_total_evaluations",
            "max_seed_evaluations",
            "max_rounds",
            "pair_frontier_per_wearer",
            "beam_width",
            "beam_top_slots",
            "max_physical_finalists",
        )
        nonnegative_ints = (
            "max_coordinate_evaluations_per_round",
            "max_pair_evaluations_per_round",
            "beam_uncertain_slots",
            "beam_novelty_slots",
        )
        for field_name in positive_ints:
            _require_plain_int(
                getattr(self, field_name),
                field_name=field_name,
                minimum=1,
            )
        for field_name in nonnegative_ints:
            _require_plain_int(
                getattr(self, field_name),
                field_name=field_name,
                minimum=0,
            )
        if self.max_seed_evaluations > self.max_total_evaluations:
            raise FullTeamComposerError(
                "max_seed_evaluations cannot exceed max_total_evaluations"
            )
        if (
            self.beam_top_slots
            + self.beam_uncertain_slots
            + self.beam_novelty_slots
            > self.beam_width
        ):
            raise FullTeamComposerError(
                "reserved beam slots cannot exceed beam_width"
            )
        for field_name in (
            "confidence_sigma",
            "relative_uncertainty_margin",
            "max_seconds",
            "per_evaluation_timeout_seconds",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isfinite(value) or value < 0:
                raise FullTeamComposerError(
                    f"{field_name} must be finite and non-negative"
                )
        if self.max_seconds <= 0 or self.per_evaluation_timeout_seconds <= 0:
            raise FullTeamComposerError(
                "search and per-evaluation timeouts must be positive"
            )


@dataclass(frozen=True, slots=True)
class FullTeamComposerRequest:
    evaluation_context_sha256: str
    wearer_ids: tuple[str, ...]
    candidate_pools: tuple[FullTeamCandidatePool, ...]
    budget: FullTeamComposerBudget
    explicit_seeds: tuple[FullTeamProbeState, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "wearer_ids", tuple(self.wearer_ids))
        object.__setattr__(self, "candidate_pools", tuple(self.candidate_pools))
        object.__setattr__(self, "explicit_seeds", tuple(self.explicit_seeds))
        if not _is_sha256(self.evaluation_context_sha256):
            raise FullTeamComposerError(
                "evaluation_context_sha256 must be a lowercase SHA-256 digest"
            )
        if not self.wearer_ids or len(self.wearer_ids) > 4:
            raise FullTeamComposerError("wearer_ids must contain one to four wearers")
        if len(set(self.wearer_ids)) != len(self.wearer_ids):
            raise FullTeamComposerError("wearer_ids must be unique")
        pool_ids = tuple(pool.wearer_id for pool in self.candidate_pools)
        if pool_ids != self.wearer_ids:
            raise FullTeamComposerError(
                "candidate pools must cover wearers exactly in canonical order"
            )


@dataclass(frozen=True, slots=True)
class FullTeamSimulationRequest:
    context_sha256: str
    state: FullTeamProbeState
    ordinal: int
    phase: str
    round_index: int
    parent_probe_keys: tuple[ProbeKey, ...]
    changed_wearer_ids: tuple[str, ...]
    timeout_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "parent_probe_keys", tuple(self.parent_probe_keys))
        object.__setattr__(self, "changed_wearer_ids", tuple(self.changed_wearer_ids))
        if not _is_sha256(self.context_sha256):
            raise FullTeamComposerError("simulation context_sha256 is invalid")
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 0:
            raise FullTeamComposerError("simulation ordinal must be a non-negative integer")
        _require_identifier(self.phase, field_name="simulation phase")
        if (
            isinstance(self.round_index, bool)
            or not isinstance(self.round_index, int)
            or self.round_index < 0
        ):
            raise FullTeamComposerError(
                "simulation round_index must be a non-negative integer"
            )
        if (
            isinstance(self.timeout_seconds, bool)
            or not isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise FullTeamComposerError(
                "simulation timeout_seconds must be finite and positive"
            )
        if len(set(self.changed_wearer_ids)) != len(self.changed_wearer_ids):
            raise FullTeamComposerError("changed_wearer_ids must be unique")
        for wearer_id in self.changed_wearer_ids:
            _require_identifier(wearer_id, field_name="changed wearer id")
        if len(self.parent_probe_keys) > 1:
            raise FullTeamComposerError(
                "simulation trace must use one canonical parent edge"
            )
        if bool(self.parent_probe_keys) != bool(self.changed_wearer_ids):
            raise FullTeamComposerError(
                "simulation parent edge and changed_wearer_ids must appear together"
            )
        unknown_changed_wearers = tuple(
            wearer_id
            for wearer_id in self.changed_wearer_ids
            if wearer_id not in self.state.wearer_ids
        )
        if unknown_changed_wearers:
            raise FullTeamComposerError(
                "changed_wearer_ids must belong to the simulated team state"
            )


@dataclass(frozen=True, slots=True)
class FullTeamSimulationMetrics:
    status: str
    dps_mean: float | None = None
    dps_se: float | None = None
    iterations: int | None = None
    novelty_tags: tuple[str, ...] = ()
    cache_hit: bool = False
    error: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "novelty_tags", tuple(self.novelty_tags))
        if self.status not in _SIM_STATUSES:
            raise FullTeamComposerError(f"unknown team simulation status: {self.status!r}")
        if not isinstance(self.cache_hit, bool):
            raise FullTeamComposerError("cache_hit must be a bool")
        if len(set(self.novelty_tags)) != len(self.novelty_tags):
            raise FullTeamComposerError("simulation novelty tags must be unique")
        for tag in self.novelty_tags:
            _require_identifier(tag, field_name="simulation novelty tag")
        if self.status == TEAM_SIM_PASSED:
            if (
                self.dps_mean is None
                or isinstance(self.dps_mean, bool)
                or not isfinite(self.dps_mean)
                or self.dps_mean < 0
            ):
                raise FullTeamComposerError(
                    "passed simulation requires finite non-negative DPS"
                )
            if (
                isinstance(self.iterations, bool)
                or not isinstance(self.iterations, int)
                or self.iterations <= 0
            ):
                raise FullTeamComposerError(
                    "passed simulation requires a positive iteration count"
                )
            if self.dps_se is not None and (
                isinstance(self.dps_se, bool)
                or not isfinite(self.dps_se)
                or self.dps_se < 0
            ):
                raise FullTeamComposerError(
                    "passed simulation SE must be finite and non-negative or None"
                )
        elif any(value is not None for value in (self.dps_mean, self.dps_se, self.iterations)):
            raise FullTeamComposerError(
                "failed/timeout/cancelled metrics must not carry numeric results"
            )


class FullTeamBatchSimulator(Protocol):
    def __call__(
        self,
        requests: tuple[FullTeamSimulationRequest, ...],
    ) -> Mapping[ProbeKey, FullTeamSimulationMetrics]: ...


@dataclass(frozen=True, slots=True)
class FullTeamEvaluationRecord:
    request: FullTeamSimulationRequest
    metrics: FullTeamSimulationMetrics
    structural_tags: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "structural_tags", tuple(self.structural_tags))

    @property
    def probe_key(self) -> ProbeKey:
        return self.request.state.probe_key

    @property
    def physical_key(self) -> PhysicalKey:
        return self.request.state.physical_key

    @property
    def branch_tags(self) -> tuple[str, ...]:
        return (*self.structural_tags, *self.metrics.novelty_tags)

    def lower_bound(self, confidence_sigma: float) -> float:
        if self.metrics.dps_se is None:
            return float("-inf")
        return float(self.metrics.dps_mean) - confidence_sigma * self.metrics.dps_se

    def upper_bound(self, confidence_sigma: float) -> float:
        if self.metrics.dps_se is None:
            return float("inf")
        return float(self.metrics.dps_mean) + confidence_sigma * self.metrics.dps_se


@dataclass(frozen=True, slots=True)
class FullTeamComposerResult:
    status: str
    stop_reason: str
    evaluation_context_sha256: str
    investment_signature: str
    provenance_schema_version: int
    request_sha256: str
    candidate_domain_sha256: str
    budget_sha256: str
    budget_snapshot: FullTeamComposerBudget
    elapsed_seconds: float
    requested_evaluations: int
    cache_hits: int
    rounds_completed: int
    records: tuple[FullTeamEvaluationRecord, ...]
    beam: tuple[FullTeamEvaluationRecord, ...]
    best_found: FullTeamEvaluationRecord | None
    physical_finalists: tuple[FullTeamPhysicalState, ...]

    def __post_init__(self) -> None:
        try:
            records = tuple(self.records)
            beam = tuple(self.beam)
            physical_finalists = tuple(self.physical_finalists)
        except TypeError as exc:
            raise FullTeamComposerError(
                "result records, beam, and physical_finalists must be iterable"
            ) from exc
        object.__setattr__(self, "records", records)
        object.__setattr__(self, "beam", beam)
        object.__setattr__(
            self,
            "physical_finalists",
            physical_finalists,
        )
        if (
            not isinstance(self.status, str)
            or self.status not in _SEARCH_RESULT_STATUSES
        ):
            raise FullTeamComposerError("result status is not recognized")
        if self.stop_reason != self.status:
            raise FullTeamComposerError(
                "result status and stop_reason must match exactly"
            )
        if self.provenance_schema_version != FULL_TEAM_COMPOSER_PROVENANCE_SCHEMA:
            raise FullTeamComposerError(
                "result provenance_schema_version is unsupported"
            )
        if not _is_sha256(self.evaluation_context_sha256):
            raise FullTeamComposerError(
                "result evaluation_context_sha256 must be a lowercase SHA-256 digest"
            )
        for field_name in (
            "request_sha256",
            "candidate_domain_sha256",
            "budget_sha256",
        ):
            if not _is_sha256(getattr(self, field_name)):
                raise FullTeamComposerError(
                    f"result {field_name} must be a lowercase SHA-256 digest"
                )
        if not isinstance(self.budget_snapshot, FullTeamComposerBudget):
            raise FullTeamComposerError(
                "result budget_snapshot must be a FullTeamComposerBudget"
            )
        _require_identifier(
            self.investment_signature,
            field_name="result investment_signature",
        )
        if (
            isinstance(self.elapsed_seconds, bool)
            or not isinstance(self.elapsed_seconds, (int, float))
            or not isfinite(self.elapsed_seconds)
            or self.elapsed_seconds < 0
        ):
            raise FullTeamComposerError(
                "result elapsed_seconds must be finite and non-negative"
            )
        for field_name in (
            "requested_evaluations",
            "cache_hits",
            "rounds_completed",
        ):
            _require_plain_int(
                getattr(self, field_name),
                field_name=f"result {field_name}",
                minimum=0,
            )
        if self.budget_sha256 != _canonical_sha256(
            _composer_budget_payload(self.budget_snapshot)
        ):
            raise FullTeamComposerError(
                "result budget_sha256 does not match budget_snapshot"
            )
        if self.requested_evaluations > self.budget_snapshot.max_total_evaluations:
            raise FullTeamComposerError(
                "result requested evaluations exceed the frozen budget"
            )
        if self.rounds_completed > self.budget_snapshot.max_rounds:
            raise FullTeamComposerError(
                "result rounds_completed exceed the frozen budget"
            )
        _validate_composer_result_trace(self)


def _validate_composer_result_trace(result: FullTeamComposerResult) -> None:
    """Validate only invariants reproducible from the result's own trace."""

    records = result.records
    budget = result.budget_snapshot
    if any(
        not isinstance(record, FullTeamEvaluationRecord)
        or not isinstance(record.request, FullTeamSimulationRequest)
        or not isinstance(record.request.state, FullTeamProbeState)
        or not isinstance(record.metrics, FullTeamSimulationMetrics)
        for record in records
    ):
        raise FullTeamComposerError(
            "result records carry invalid record, request, state, or metrics values"
        )
    if result.requested_evaluations != len(records):
        raise FullTeamComposerError(
            "result requested_evaluations must equal the record count"
        )
    if tuple(record.request.ordinal for record in records) != tuple(range(len(records))):
        raise FullTeamComposerError(
            "result records must have contiguous ordinal order"
        )

    records_by_key: dict[ProbeKey, FullTeamEvaluationRecord] = {}
    phase_counts: Counter[tuple[str, int]] = Counter()
    canonical_wearers: tuple[str, ...] | None = None
    for record in records:
        simulation = record.request
        if simulation.context_sha256 != result.evaluation_context_sha256:
            raise FullTeamComposerError(
                "result record context differs from the result context"
            )
        if simulation.timeout_seconds > budget.per_evaluation_timeout_seconds:
            raise FullTeamComposerError(
                "result record timeout exceeds the frozen per-evaluation budget"
            )
        if simulation.round_index > result.rounds_completed:
            raise FullTeamComposerError(
                "result record round exceeds rounds_completed"
            )
        if canonical_wearers is None:
            canonical_wearers = simulation.state.wearer_ids
        elif simulation.state.wearer_ids != canonical_wearers:
            raise FullTeamComposerError(
                "result records mix canonical wearer orders"
            )
        if record.probe_key in records_by_key:
            raise FullTeamComposerError("result records contain duplicate probe states")

        if simulation.phase == "seed":
            if (
                simulation.round_index != 0
                or simulation.parent_probe_keys
                or simulation.changed_wearer_ids
            ):
                raise FullTeamComposerError("result seed trace is inconsistent")
        elif simulation.phase in {"coordinate", "pair"}:
            expected_change_count = 1 if simulation.phase == "coordinate" else 2
            if (
                simulation.round_index == 0
                or len(simulation.parent_probe_keys) != 1
                or len(simulation.changed_wearer_ids) != expected_change_count
            ):
                raise FullTeamComposerError(
                    f"result {simulation.phase} trace is inconsistent"
                )
            parent = records_by_key.get(simulation.parent_probe_keys[0])
            if parent is None:
                raise FullTeamComposerError(
                    "result transition parent must precede its child record"
                )
            if parent.request.state.wearer_ids != simulation.state.wearer_ids:
                raise FullTeamComposerError(
                    "result transition parent uses another wearer order"
                )
            actual_changed = tuple(
                wearer_id
                for wearer_id, parent_choice, child_choice in zip(
                    simulation.state.wearer_ids,
                    parent.request.state.choices,
                    simulation.state.choices,
                    strict=True,
                )
                if parent_choice.key != child_choice.key
            )
            if actual_changed != simulation.changed_wearer_ids:
                raise FullTeamComposerError(
                    "result transition changed_wearer_ids do not match its parent edge"
                )
        else:
            raise FullTeamComposerError("result record phase is not recognized")

        phase_counts[(simulation.phase, simulation.round_index)] += 1
        records_by_key[record.probe_key] = record

    if phase_counts[("seed", 0)] > budget.max_seed_evaluations:
        raise FullTeamComposerError("result seed records exceed the frozen budget")
    for round_index in range(1, result.rounds_completed + 1):
        if (
            phase_counts[("coordinate", round_index)]
            > budget.max_coordinate_evaluations_per_round
        ):
            raise FullTeamComposerError(
                "result coordinate records exceed the frozen round budget"
            )
        if (
            phase_counts[("pair", round_index)]
            > budget.max_pair_evaluations_per_round
        ):
            raise FullTeamComposerError(
                "result pair records exceed the frozen round budget"
            )

    actual_cache_hits = sum(record.metrics.cache_hit for record in records)
    if result.cache_hits != actual_cache_hits:
        raise FullTeamComposerError(
            "result cache_hits must equal the cache-hit record count"
        )

    expected_beam = _select_beam(records, budget)
    if result.beam != expected_beam:
        raise FullTeamComposerError(
            "result beam does not match the recorded evaluations"
        )
    ranked_passed = _ranked_passed(records)
    expected_best = ranked_passed[0] if ranked_passed else None
    if result.best_found != expected_best:
        raise FullTeamComposerError(
            "result best_found does not match the recorded evaluations"
        )
    expected_finalists = _physical_finalists(
        ranked_passed,
        limit=budget.max_physical_finalists,
    )
    if result.physical_finalists != expected_finalists:
        raise FullTeamComposerError(
            "result physical_finalists do not match the recorded evaluations"
        )

    if expected_best is None and result.stop_reason not in {
        TEAM_SEARCH_CANCELLED,
        TEAM_SEARCH_DEADLINE_REACHED,
        TEAM_SEARCH_NO_SUCCESS,
    }:
        raise FullTeamComposerError(
            "result terminal status requires a successful recorded evaluation"
        )
    if expected_best is not None and result.stop_reason == TEAM_SEARCH_NO_SUCCESS:
        raise FullTeamComposerError(
            "result no_success status conflicts with best_found"
        )
    if (
        result.stop_reason == TEAM_SEARCH_BUDGET_EXHAUSTED
        and result.requested_evaluations != budget.max_total_evaluations
    ):
        raise FullTeamComposerError(
            "result budget_exhausted status requires the full evaluation budget"
        )
    if (
        result.stop_reason == TEAM_SEARCH_ROUND_LIMIT_REACHED
        and result.rounds_completed != budget.max_rounds
    ):
        raise FullTeamComposerError(
            "result round_limit_reached status requires the full round budget"
        )


def compose_full_team_four_piece_states(
    request: FullTeamComposerRequest,
    simulator: FullTeamBatchSimulator,
    *,
    is_cancelled: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] = monotonic,
) -> FullTeamComposerResult:
    """Run a bounded joint-state race with coordinate and exact pair moves."""

    started = clock()
    deadline = started + request.budget.max_seconds
    pools = _validated_sorted_pools(request)
    candidate_source_tags = _candidate_source_tags(pools)
    investment_signature = _common_investment_signature(pools)
    _validate_explicit_seeds(request, pools)
    (
        request_sha256,
        candidate_domain_sha256,
        budget_sha256,
    ) = _composer_provenance_digests(request, pools)
    records_by_key: dict[ProbeKey, FullTeamEvaluationRecord] = {}
    requested_count = 0
    rounds_completed = 0
    coordinate_group_cursor = 0
    pair_group_cursor = 0
    stop_reason = TEAM_SEARCH_COMPLETED

    if is_cancelled():
        stop_reason = TEAM_SEARCH_CANCELLED
    elif clock() >= deadline:
        stop_reason = TEAM_SEARCH_DEADLINE_REACHED
    else:
        seeds = _seed_states(request, pools)
        seed_limit = min(
            request.budget.max_seed_evaluations,
            request.budget.max_total_evaluations,
        )
        seeds = seeds[:seed_limit]
        requested_count += _evaluate_states(
            seeds,
            phase="seed",
            round_index=0,
            parent_keys={},
            changed_wearers={},
            request=request,
            simulator=simulator,
            records_by_key=records_by_key,
            candidate_source_tags=candidate_source_tags,
            ordinal_start=requested_count,
            deadline=deadline,
            is_cancelled=is_cancelled,
            clock=clock,
        )

    beam = _select_beam(tuple(records_by_key.values()), request.budget)
    if _contains_cancelled_result(records_by_key.values()):
        stop_reason = TEAM_SEARCH_CANCELLED
    elif is_cancelled():
        stop_reason = TEAM_SEARCH_CANCELLED
    elif clock() >= deadline:
        stop_reason = TEAM_SEARCH_DEADLINE_REACHED

    for round_index in range(1, request.budget.max_rounds + 1):
        if stop_reason != TEAM_SEARCH_COMPLETED:
            break
        if requested_count >= request.budget.max_total_evaluations:
            stop_reason = TEAM_SEARCH_BUDGET_EXHAUSTED
            break
        if not beam:
            stop_reason = TEAM_SEARCH_NO_SUCCESS
            break
        if _contains_cancelled_result(records_by_key.values()):
            stop_reason = TEAM_SEARCH_CANCELLED
            break
        elif is_cancelled():
            stop_reason = TEAM_SEARCH_CANCELLED
            break
        if clock() >= deadline:
            stop_reason = TEAM_SEARCH_DEADLINE_REACHED
            break

        remaining_total = request.budget.max_total_evaluations - requested_count
        coordinate_limit = min(
            request.budget.max_coordinate_evaluations_per_round,
            remaining_total,
        )
        coordinate_states, coordinate_parents, coordinate_changes = _coordinate_neighbors(
            beam,
            pools,
            seen_keys=set(records_by_key),
            limit=coordinate_limit,
            group_offset=coordinate_group_cursor,
        )
        coordinate_group_count = len(beam) * len(pools)
        if coordinate_group_count:
            coordinate_group_cursor = (
                coordinate_group_cursor + max(coordinate_limit, 1)
            ) % coordinate_group_count
        requested_count += _evaluate_states(
            coordinate_states,
            phase="coordinate",
            round_index=round_index,
            parent_keys=coordinate_parents,
            changed_wearers=coordinate_changes,
            request=request,
            simulator=simulator,
            records_by_key=records_by_key,
            candidate_source_tags=candidate_source_tags,
            ordinal_start=requested_count,
            deadline=deadline,
            is_cancelled=is_cancelled,
            clock=clock,
        )

        if _contains_cancelled_result(records_by_key.values()):
            stop_reason = TEAM_SEARCH_CANCELLED
        elif is_cancelled():
            stop_reason = TEAM_SEARCH_CANCELLED
        elif clock() >= deadline:
            stop_reason = TEAM_SEARCH_DEADLINE_REACHED
        elif requested_count >= request.budget.max_total_evaluations:
            stop_reason = TEAM_SEARCH_BUDGET_EXHAUSTED

        pair_states: tuple[FullTeamProbeState, ...] = ()
        if stop_reason == TEAM_SEARCH_COMPLETED:
            provisional_beam = _select_beam(tuple(records_by_key.values()), request.budget)
            remaining_total = request.budget.max_total_evaluations - requested_count
            pair_limit = min(
                request.budget.max_pair_evaluations_per_round,
                remaining_total,
            )
            pair_states, pair_parents, pair_changes = _pair_neighbors(
                provisional_beam,
                pools,
                frontier=request.budget.pair_frontier_per_wearer,
                seen_keys=set(records_by_key),
                limit=pair_limit,
                group_offset=pair_group_cursor,
            )
            pair_group_count = (
                len(provisional_beam) * len(pools) * (len(pools) - 1) // 2
            )
            if pair_group_count:
                pair_group_cursor = (
                    pair_group_cursor + max(pair_limit, 1)
                ) % pair_group_count
            requested_count += _evaluate_states(
                pair_states,
                phase="pair",
                round_index=round_index,
                parent_keys=pair_parents,
                changed_wearers=pair_changes,
                request=request,
                simulator=simulator,
                records_by_key=records_by_key,
                candidate_source_tags=candidate_source_tags,
                ordinal_start=requested_count,
                deadline=deadline,
                is_cancelled=is_cancelled,
                clock=clock,
            )
            if _contains_cancelled_result(records_by_key.values()):
                stop_reason = TEAM_SEARCH_CANCELLED
            elif is_cancelled():
                stop_reason = TEAM_SEARCH_CANCELLED
            elif clock() >= deadline:
                stop_reason = TEAM_SEARCH_DEADLINE_REACHED
            elif requested_count >= request.budget.max_total_evaluations:
                stop_reason = TEAM_SEARCH_BUDGET_EXHAUSTED

        rounds_completed = round_index
        new_beam = _select_beam(tuple(records_by_key.values()), request.budget)
        if (
            stop_reason == TEAM_SEARCH_COMPLETED
            and not coordinate_states
            and not pair_states
        ):
            stop_reason = (
                TEAM_SEARCH_POLICY_EXHAUSTED
                if _has_unseen_domain_state(pools, set(records_by_key))
                else TEAM_SEARCH_DOMAIN_EXHAUSTED
            )
            beam = new_beam
            break
        beam = new_beam

    if stop_reason == TEAM_SEARCH_COMPLETED:
        if not beam:
            stop_reason = TEAM_SEARCH_NO_SUCCESS
        elif _has_unseen_domain_state(pools, set(records_by_key)):
            stop_reason = TEAM_SEARCH_ROUND_LIMIT_REACHED
        else:
            stop_reason = TEAM_SEARCH_DOMAIN_EXHAUSTED
    ranked_passed = _ranked_passed(tuple(records_by_key.values()))
    best = ranked_passed[0] if ranked_passed else None
    if best is None and stop_reason not in {
        TEAM_SEARCH_CANCELLED,
        TEAM_SEARCH_DEADLINE_REACHED,
    }:
        stop_reason = TEAM_SEARCH_NO_SUCCESS
    physical_finalists = _physical_finalists(
        ranked_passed,
        limit=request.budget.max_physical_finalists,
    )
    status = stop_reason
    records = tuple(
        sorted(records_by_key.values(), key=lambda item: item.request.ordinal)
    )
    return FullTeamComposerResult(
        status=status,
        stop_reason=stop_reason,
        evaluation_context_sha256=request.evaluation_context_sha256,
        investment_signature=investment_signature,
        provenance_schema_version=FULL_TEAM_COMPOSER_PROVENANCE_SCHEMA,
        request_sha256=request_sha256,
        candidate_domain_sha256=candidate_domain_sha256,
        budget_sha256=budget_sha256,
        budget_snapshot=request.budget,
        elapsed_seconds=max(clock() - started, 0.0),
        requested_evaluations=requested_count,
        cache_hits=sum(1 for record in records if record.metrics.cache_hit),
        rounds_completed=rounds_completed,
        records=records,
        beam=beam,
        best_found=best,
        physical_finalists=physical_finalists,
    )


def _composer_provenance_digests(
    request: FullTeamComposerRequest,
    pools: Sequence[Sequence[SearchSurvivor]],
) -> tuple[str, str, str]:
    """Freeze the exact bounded search request into canonical content hashes.

    ``pools`` has already passed through ``_validated_sorted_pools``.  Hashing
    that canonical order makes equivalent survivor input order irrelevant while
    retaining every score, uncertainty, novelty, and selection reason that can
    affect traversal or its trace.  Explicit seed order remains significant
    because the seed budget can make it affect which states are evaluated.
    """

    domain_payload = {
        "schema_version": FULL_TEAM_COMPOSER_PROVENANCE_SCHEMA,
        "wearer_pools": [
            {
                "wearer_id": wearer_id,
                "survivors": [
                    _composer_survivor_payload(survivor)
                    for survivor in pool
                ],
            }
            for wearer_id, pool in zip(
                request.wearer_ids,
                pools,
                strict=True,
            )
        ],
    }
    budget_payload = _composer_budget_payload(request.budget)
    candidate_domain_sha256 = _canonical_sha256(domain_payload)
    budget_sha256 = _canonical_sha256(budget_payload)
    request_payload = {
        "schema_version": FULL_TEAM_COMPOSER_PROVENANCE_SCHEMA,
        "evaluation_context_sha256": request.evaluation_context_sha256,
        "wearer_ids": list(request.wearer_ids),
        "candidate_domain_sha256": candidate_domain_sha256,
        "budget_sha256": budget_sha256,
        "explicit_seed_probe_keys": [
            [list(candidate_key) for candidate_key in seed.probe_key]
            for seed in request.explicit_seeds
        ],
    }
    return (
        _canonical_sha256(request_payload),
        candidate_domain_sha256,
        budget_sha256,
    )


def _composer_survivor_payload(survivor: SearchSurvivor) -> dict[str, object]:
    evaluation = survivor.evaluation
    return {
        "candidate_key": list(evaluation.candidate.key),
        "expected_dps": float(evaluation.expected_dps),
        "standard_error": (
            None
            if evaluation.standard_error is None
            else float(evaluation.standard_error)
        ),
        "investment_signature": evaluation.investment_signature,
        "novelty_score": float(evaluation.novelty_score),
        "novelty_tags": list(evaluation.novelty_tags),
        "survivor_reasons": list(survivor.reasons),
    }


def _composer_budget_payload(
    budget: FullTeamComposerBudget,
) -> dict[str, object]:
    return {
        "schema_version": FULL_TEAM_COMPOSER_PROVENANCE_SCHEMA,
        "max_total_evaluations": budget.max_total_evaluations,
        "max_seed_evaluations": budget.max_seed_evaluations,
        "max_rounds": budget.max_rounds,
        "max_coordinate_evaluations_per_round": (
            budget.max_coordinate_evaluations_per_round
        ),
        "max_pair_evaluations_per_round": budget.max_pair_evaluations_per_round,
        "pair_frontier_per_wearer": budget.pair_frontier_per_wearer,
        "beam_width": budget.beam_width,
        "beam_top_slots": budget.beam_top_slots,
        "beam_uncertain_slots": budget.beam_uncertain_slots,
        "beam_novelty_slots": budget.beam_novelty_slots,
        "max_physical_finalists": budget.max_physical_finalists,
        "confidence_sigma": float(budget.confidence_sigma),
        "relative_uncertainty_margin": float(
            budget.relative_uncertainty_margin
        ),
        "max_seconds": float(budget.max_seconds),
        "per_evaluation_timeout_seconds": float(
            budget.per_evaluation_timeout_seconds
        ),
    }


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _evaluate_states(
    states: Sequence[FullTeamProbeState],
    *,
    phase: str,
    round_index: int,
    parent_keys: Mapping[ProbeKey, tuple[ProbeKey, ...]],
    changed_wearers: Mapping[ProbeKey, tuple[str, ...]],
    request: FullTeamComposerRequest,
    simulator: FullTeamBatchSimulator,
    records_by_key: dict[ProbeKey, FullTeamEvaluationRecord],
    candidate_source_tags: Mapping[
        tuple[str, str, str, str, str],
        tuple[str, ...],
    ],
    ordinal_start: int,
    deadline: float,
    is_cancelled: Callable[[], bool],
    clock: Callable[[], float],
) -> int:
    unique_states: list[FullTeamProbeState] = []
    batch_seen: set[ProbeKey] = set()
    for state in states:
        if is_cancelled():
            break
        key = state.probe_key
        if key in records_by_key or key in batch_seen:
            continue
        if clock() >= deadline:
            break
        batch_seen.add(key)
        unique_states.append(state)
    if not unique_states:
        return 0
    if is_cancelled():
        return 0
    remaining = max(deadline - clock(), 0.0)
    timeout = min(request.budget.per_evaluation_timeout_seconds, remaining)
    if timeout <= 0:
        return 0
    simulation_requests = tuple(
        FullTeamSimulationRequest(
            context_sha256=request.evaluation_context_sha256,
            state=state,
            ordinal=ordinal_start + index,
            phase=phase,
            round_index=round_index,
            parent_probe_keys=parent_keys.get(state.probe_key, ()),
            changed_wearer_ids=changed_wearers.get(state.probe_key, ()),
            timeout_seconds=timeout,
        )
        for index, state in enumerate(unique_states)
    )
    outcomes = simulator(simulation_requests)
    if not isinstance(outcomes, Mapping):
        raise FullTeamComposerError("batch simulator must return a mapping")
    expected_keys = {item.state.probe_key for item in simulation_requests}
    actual_keys = set(outcomes)
    if actual_keys != expected_keys:
        raise FullTeamComposerError(
            "batch simulator returned mismatched probe keys; "
            f"missing={len(expected_keys - actual_keys)}, extra={len(actual_keys - expected_keys)}"
        )
    for item in simulation_requests:
        metrics = outcomes[item.state.probe_key]
        if not isinstance(metrics, FullTeamSimulationMetrics):
            raise FullTeamComposerError(
                "batch simulator returned a non-FullTeamSimulationMetrics value"
            )
        records_by_key[item.state.probe_key] = FullTeamEvaluationRecord(
            request=item,
            metrics=metrics,
            structural_tags=_structural_tags(
                item.state,
                candidate_source_tags=candidate_source_tags,
            ),
        )
    return len(simulation_requests)


def _contains_cancelled_result(
    records: Iterable[FullTeamEvaluationRecord],
) -> bool:
    """Propagate simulator-side cancellation even without an external Event.

    A batch adapter can be cancelled directly while the composer is blocked in
    ``simulator(...)``.  In that race the caller-provided ``is_cancelled``
    callback may remain false, so a typed cancelled outcome is itself terminal
    evidence and must never be reclassified as ``no_success`` or
    ``domain_exhausted``.
    """

    return any(record.metrics.status == TEAM_SIM_CANCELLED for record in records)


def _validated_sorted_pools(
    request: FullTeamComposerRequest,
) -> tuple[tuple[SearchSurvivor, ...], ...]:
    pools: list[tuple[SearchSurvivor, ...]] = []
    all_keys: set[tuple[str, str, str, str, str]] = set()
    for pool in request.candidate_pools:
        ranked = _recall_first_pool_order(pool.survivors)
        for survivor in ranked:
            key = survivor.evaluation.candidate.key
            if key in all_keys:
                raise FullTeamComposerError(
                    "candidate keys must be globally unique across wearer pools"
                )
            all_keys.add(key)
        pools.append(ranked)
    return tuple(pools)


def _common_investment_signature(
    pools: Sequence[Sequence[SearchSurvivor]],
) -> str:
    signatures = {
        survivor.evaluation.investment_signature
        for pool in pools
        for survivor in pool
    }
    if len(signatures) != 1:
        raise FullTeamComposerError(
            "all one-wearer survivors must share one investment signature"
        )
    return next(iter(signatures))


def _validate_explicit_seeds(
    request: FullTeamComposerRequest,
    pools: Sequence[Sequence[SearchSurvivor]],
) -> None:
    allowed = {
        survivor.evaluation.candidate.key
        for pool in pools
        for survivor in pool
    }
    seen: set[ProbeKey] = set()
    for seed in request.explicit_seeds:
        if seed.wearer_ids != request.wearer_ids:
            raise FullTeamComposerError(
                "explicit seed choices must follow canonical wearer order"
            )
        if any(choice.key not in allowed for choice in seed.choices):
            raise FullTeamComposerError(
                "explicit seed contains a choice outside the candidate pools"
            )
        if seed.probe_key in seen:
            raise FullTeamComposerError("explicit seeds must be unique")
        seen.add(seed.probe_key)


def _seed_states(
    request: FullTeamComposerRequest,
    pools: Sequence[Sequence[SearchSurvivor]],
) -> tuple[FullTeamProbeState, ...]:
    result: list[FullTeamProbeState] = []
    seen: set[ProbeKey] = set()

    def append(state: FullTeamProbeState) -> None:
        if state.probe_key not in seen:
            seen.add(state.probe_key)
            result.append(state)

    for seed in request.explicit_seeds:
        append(seed)
    append(
        FullTeamProbeState(
            choices=tuple(pool[0].evaluation.candidate for pool in pools)
        )
    )
    depth = 1
    while len(result) < request.budget.max_seed_evaluations:
        produced = False
        for rotation in range(len(pools)):
            choices = tuple(
                pool[min(depth + ((index + rotation) % len(pools)), len(pool) - 1)]
                .evaluation.candidate
                for index, pool in enumerate(pools)
            )
            before = len(result)
            append(FullTeamProbeState(choices=choices))
            produced = produced or len(result) > before
            if len(result) >= request.budget.max_seed_evaluations:
                break
        if not produced:
            break
        depth += 1
    return tuple(result)


def _coordinate_neighbors(
    beam: Sequence[FullTeamEvaluationRecord],
    pools: Sequence[Sequence[SearchSurvivor]],
    *,
    seen_keys: set[ProbeKey],
    limit: int,
    group_offset: int = 0,
) -> tuple[
    tuple[FullTeamProbeState, ...],
    dict[ProbeKey, tuple[ProbeKey, ...]],
    dict[ProbeKey, tuple[str, ...]],
]:
    groups: list[list[tuple[FullTeamProbeState, ProbeKey, tuple[str, ...]]]] = []
    for parent in beam:
        for wearer_index, pool in enumerate(pools):
            group: list[tuple[FullTeamProbeState, ProbeKey, tuple[str, ...]]] = []
            for survivor in pool:
                choice = survivor.evaluation.candidate
                if choice.key == parent.request.state.choices[wearer_index].key:
                    continue
                choices = list(parent.request.state.choices)
                choices[wearer_index] = choice
                state = FullTeamProbeState(choices=tuple(choices))
                group.append(
                    (
                        state,
                        parent.probe_key,
                        (choice.state.wearer_id,),
                    )
                )
            groups.append(group)
    if groups:
        offset = group_offset % len(groups)
        groups = [*groups[offset:], *groups[:offset]]
    return _bounded_round_robin_neighbors(groups, seen_keys=seen_keys, limit=limit)


def _pair_neighbors(
    beam: Sequence[FullTeamEvaluationRecord],
    pools: Sequence[Sequence[SearchSurvivor]],
    *,
    frontier: int,
    seen_keys: set[ProbeKey],
    limit: int,
    group_offset: int = 0,
) -> tuple[
    tuple[FullTeamProbeState, ...],
    dict[ProbeKey, tuple[ProbeKey, ...]],
    dict[ProbeKey, tuple[str, ...]],
]:
    groups: list[list[tuple[FullTeamProbeState, ProbeKey, tuple[str, ...]]]] = []
    wearer_pairs = tuple(combinations(range(len(pools)), 2))
    for parent in beam:
        for left_index, right_index in wearer_pairs:
            left_choices = tuple(
                survivor.evaluation.candidate
                for survivor in pools[left_index]
                if survivor.evaluation.candidate.key
                != parent.request.state.choices[left_index].key
            )[:frontier]
            right_choices = tuple(
                survivor.evaluation.candidate
                for survivor in pools[right_index]
                if survivor.evaluation.candidate.key
                != parent.request.state.choices[right_index].key
            )[:frontier]
            group: list[tuple[FullTeamProbeState, ProbeKey, tuple[str, ...]]] = []
            for left, right in product(left_choices, right_choices):
                choices = list(parent.request.state.choices)
                choices[left_index] = left
                choices[right_index] = right
                state = FullTeamProbeState(choices=tuple(choices))
                group.append(
                    (
                        state,
                        parent.probe_key,
                        (left.state.wearer_id, right.state.wearer_id),
                    )
                )
            group.sort(
                key=lambda item: (
                    -_duplicate_set_change_score(parent.request.state, item[0]),
                    item[0].probe_key,
                )
            )
            groups.append(group)
    if groups:
        offset = group_offset % len(groups)
        groups = [*groups[offset:], *groups[:offset]]
    return _bounded_round_robin_neighbors(groups, seen_keys=seen_keys, limit=limit)


def _bounded_round_robin_neighbors(
    groups: Sequence[Sequence[tuple[FullTeamProbeState, ProbeKey, tuple[str, ...]]]],
    *,
    seen_keys: set[ProbeKey],
    limit: int,
) -> tuple[
    tuple[FullTeamProbeState, ...],
    dict[ProbeKey, tuple[ProbeKey, ...]],
    dict[ProbeKey, tuple[str, ...]],
]:
    selected: list[FullTeamProbeState] = []
    parent_map: dict[ProbeKey, list[ProbeKey]] = {}
    change_map: dict[ProbeKey, tuple[str, ...]] = {}
    indices = [0] * len(groups)
    while len(selected) < limit:
        progressed = False
        for group_index, group in enumerate(groups):
            while indices[group_index] < len(group):
                state, parent_key, changed = group[indices[group_index]]
                indices[group_index] += 1
                key = state.probe_key
                if key in parent_map:
                    # A child can be reachable from multiple beam parents with
                    # different changed-wearer sets.  Keep the first edge in
                    # deterministic group order so the request never pairs one
                    # edge's changed_wearer_ids with another edge's parent.
                    continue
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                selected.append(state)
                parent_map[key] = [parent_key]
                change_map[key] = changed
                progressed = True
                break
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return (
        tuple(selected),
        {key: tuple(values) for key, values in parent_map.items()},
        change_map,
    )


def _has_unseen_domain_state(
    pools: Sequence[Sequence[SearchSurvivor]],
    seen_keys: set[ProbeKey],
) -> bool:
    """Return whether any state in the exact Cartesian candidate domain is unseen.

    Looking only one coordinate away from a passed beam can incorrectly call the
    domain exhausted when failed/timeout intermediates surround an unseen pair or
    higher-order state.  Candidate keys are unique within validated pools, so the
    product cardinality is an exact, enumeration-free exhaustion check.
    """

    domain_size = 1
    for pool in pools:
        domain_size *= len(pool)
    return len(seen_keys) < domain_size


def _select_beam(
    records: Sequence[FullTeamEvaluationRecord],
    budget: FullTeamComposerBudget,
) -> tuple[FullTeamEvaluationRecord, ...]:
    ranked = list(_ranked_passed(records))
    if not ranked:
        return ()
    selected: list[FullTeamEvaluationRecord] = []
    selected_keys: set[ProbeKey] = set()

    def add(record: FullTeamEvaluationRecord) -> None:
        if len(selected) >= budget.beam_width or record.probe_key in selected_keys:
            return
        selected_keys.add(record.probe_key)
        selected.append(record)

    for record in ranked[: budget.beam_top_slots]:
        add(record)

    leader = ranked[0]
    margin = budget.relative_uncertainty_margin * max(
        float(leader.metrics.dps_mean),
        1.0,
    )
    uncertain = [
        record
        for record in ranked
        if record.metrics.dps_se is None
        or record.upper_bound(budget.confidence_sigma)
        >= leader.lower_bound(budget.confidence_sigma) - margin
    ]
    before = len(selected)
    for record in uncertain:
        if len(selected) - before >= budget.beam_uncertain_slots:
            break
        add(record)

    before = len(selected)
    seen_tags = {
        tag
        for record in selected
        for tag in record.branch_tags
    }
    for record in ranked:
        if len(selected) - before >= budget.beam_novelty_slots:
            break
        if record.probe_key in selected_keys:
            continue
        new_tags = set(record.branch_tags).difference(seen_tags)
        if not new_tags:
            continue
        add(record)
        seen_tags.update(record.branch_tags)

    for record in ranked:
        add(record)
    return tuple(selected)


def _ranked_passed(
    records: Sequence[FullTeamEvaluationRecord],
) -> tuple[FullTeamEvaluationRecord, ...]:
    return tuple(
        sorted(
            (
                record
                for record in records
                if record.metrics.status == TEAM_SIM_PASSED
            ),
            key=_team_record_rank,
        )
    )


def _physical_finalists(
    ranked: Sequence[FullTeamEvaluationRecord],
    *,
    limit: int,
) -> tuple[FullTeamPhysicalState, ...]:
    result: list[FullTeamPhysicalState] = []
    seen: set[PhysicalKey] = set()
    for record in ranked:
        physical = record.request.state.physical_state
        if physical.key in seen:
            continue
        seen.add(physical.key)
        result.append(physical)
        if len(result) >= limit:
            break
    return tuple(result)


def _candidate_evaluation_rank(
    evaluation: CandidateEvaluation,
) -> tuple[float, float, tuple[str, str, str, str, str]]:
    return (
        -evaluation.expected_dps,
        float("inf") if evaluation.standard_error is None else evaluation.standard_error,
        evaluation.candidate.key,
    )


def _recall_first_pool_order(
    survivors: Sequence[SearchSurvivor],
) -> tuple[SearchSurvivor, ...]:
    """Keep selector-preserved branches early in every bounded traversal.

    Raw one-wearer DPS still supplies the leader, but it must not erase the
    explicit uncertainty/profile/novelty reasons that caused a branch to
    survive the preceding response scan.
    """

    ranked = tuple(
        sorted(
            survivors,
            key=lambda item: _candidate_evaluation_rank(item.evaluation),
        )
    )
    result: list[SearchSurvivor] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    def add(item: SearchSurvivor) -> None:
        key = item.evaluation.candidate.key
        if key not in seen:
            seen.add(key)
            result.append(item)

    add(ranked[0])
    reason_order = (
        SURVIVOR_REQUIRED_PROFILE,
        SURVIVOR_NOVEL_BRANCH,
        SURVIVOR_PROFILE_COVERAGE,
        SURVIVOR_UNCERTAIN,
        SURVIVOR_WEARER_COVERAGE,
    )
    reason_rows = {
        reason: tuple(
            survivor for survivor in ranked if reason in survivor.reasons
        )
        for reason in reason_order
    }
    # First expose one representative of every selector-reserved category.
    # Otherwise a long noisy uncertainty tail can consume the whole bounded
    # coordinate frontier before a nonlinear/profile branch is ever visited.
    for reason in reason_order:
        if reason_rows[reason]:
            add(reason_rows[reason][0])
    # Then interleave remaining representatives instead of exhausting one
    # category wholesale.
    reason_index = 1
    while True:
        added = False
        for reason in reason_order:
            rows = reason_rows[reason]
            if reason_index < len(rows):
                before = len(result)
                add(rows[reason_index])
                added = added or len(result) != before
        if not any(reason_index < len(rows) for rows in reason_rows.values()):
            break
        reason_index += 1
    for survivor in sorted(
        ranked,
        key=lambda item: (
            -item.evaluation.novelty_score,
            _candidate_evaluation_rank(item.evaluation),
        ),
    ):
        if survivor.evaluation.novelty_tags or survivor.evaluation.novelty_score > 0:
            add(survivor)
    for survivor in ranked:
        add(survivor)
    return tuple(result)


def _team_record_rank(
    record: FullTeamEvaluationRecord,
) -> tuple[float, float, ProbeKey]:
    return (
        -float(record.metrics.dps_mean),
        float("inf") if record.metrics.dps_se is None else record.metrics.dps_se,
        record.probe_key,
    )


def _candidate_source_tags(
    pools: Sequence[Sequence[SearchSurvivor]],
) -> dict[tuple[str, str, str, str, str], tuple[str, ...]]:
    result: dict[tuple[str, str, str, str, str], tuple[str, ...]] = {}
    for pool in pools:
        for survivor in pool:
            candidate = survivor.evaluation.candidate
            wearer = candidate.state.wearer_id
            result[candidate.key] = tuple(
                (
                    *(f"source-reason/{wearer}/{reason}" for reason in survivor.reasons),
                    *(
                        f"source-novelty/{wearer}/{tag}"
                        for tag in survivor.evaluation.novelty_tags
                    ),
                )
            )
    return result


def _structural_tags(
    state: FullTeamProbeState,
    *,
    candidate_source_tags: Mapping[
        tuple[str, str, str, str, str],
        tuple[str, ...],
    ],
) -> tuple[str, ...]:
    tags: list[str] = []
    set_counts = Counter(choice.state.set_key for choice in state.choices)
    for choice in state.choices:
        wearer = choice.state.wearer_id
        tags.extend(
            (
                f"wearer/{wearer}/set/{choice.state.set_key}",
                f"wearer/{wearer}/layout/{choice.state.main_stat_layout_id}",
                f"wearer/{wearer}/profile/{choice.profile_id}",
            )
        )
        if choice.state.offpiece_slot:
            tags.append(
                f"wearer/{wearer}/offpiece/{choice.state.offpiece_slot}"
            )
        tags.extend(candidate_source_tags.get(choice.key, ()))
    tags.extend(
        f"duplicate-set/{set_key}/{count}"
        for set_key, count in sorted(set_counts.items())
        if count > 1
    )
    return tuple(tags)


def _duplicate_set_change_score(
    parent: FullTeamProbeState,
    candidate: FullTeamProbeState,
) -> int:
    before = Counter(choice.state.set_key for choice in parent.choices)
    after = Counter(choice.state.set_key for choice in candidate.choices)
    keys = set(before).union(after)
    return sum(
        1
        for key in keys
        if (before[key] > 1) != (after[key] > 1)
        or before[key] != after[key]
    )


def _is_sha256(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.casefold()
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_identifier(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FullTeamComposerError(
            f"{field_name} must be a non-empty trimmed string"
        )


def _require_plain_int(value: int, *, field_name: str, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise FullTeamComposerError(
            f"{field_name} must be an integer >= {minimum}"
        )


__all__ = [
    "FULL_TEAM_COMPOSER_PROVENANCE_SCHEMA",
    "FullTeamBatchSimulator",
    "FullTeamCandidatePool",
    "FullTeamComposerBudget",
    "FullTeamComposerError",
    "FullTeamComposerRequest",
    "FullTeamComposerResult",
    "FullTeamEvaluationRecord",
    "FullTeamPhysicalState",
    "FullTeamProbeState",
    "FullTeamSimulationMetrics",
    "FullTeamSimulationRequest",
    "PhysicalKey",
    "ProbeKey",
    "TEAM_SEARCH_BUDGET_EXHAUSTED",
    "TEAM_SEARCH_CANCELLED",
    "TEAM_SEARCH_COMPLETED",
    "TEAM_SEARCH_DEADLINE_REACHED",
    "TEAM_SEARCH_DOMAIN_EXHAUSTED",
    "TEAM_SEARCH_NO_SUCCESS",
    "TEAM_SEARCH_POLICY_EXHAUSTED",
    "TEAM_SEARCH_ROUND_LIMIT_REACHED",
    "TEAM_SIM_CANCELLED",
    "TEAM_SIM_FAILED",
    "TEAM_SIM_PASSED",
    "TEAM_SIM_TIMEOUT",
    "compose_full_team_four_piece_states",
]
