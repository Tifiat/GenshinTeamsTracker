"""Versioned measurements for the Milestone 14 optimizer benchmark matrix."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from math import ceil, isfinite
import os
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping
from uuid import uuid4

from .optimizer_anytime_selected_service import (
    GcsimOptimizerAnytimeSelectedResult,
)
from .optimizer_product_contracts import GcsimOptimizerOperationRequest
from .optimizer_run_input import GcsimOptimizerRunInput
from .optimizer_theoretical_anytime_service import (
    GcsimOptimizerTheoreticalAnytimeResult,
)


GCSIM_OPTIMIZER_BENCHMARK_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_DEBUG_TRACE_SCHEMA_VERSION = 1


class GcsimOptimizerBenchmarkError(ValueError):
    """Raised when a benchmark observation cannot be compared honestly."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerDebugTrace:
    """Self-contained replay evidence for one completed account race."""

    payload: Mapping[str, object]
    trace_identity_sha256: str
    schema_version: int = GCSIM_OPTIMIZER_DEBUG_TRACE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_DEBUG_TRACE_SCHEMA_VERSION:
            raise GcsimOptimizerBenchmarkError(
                "unsupported optimizer debug trace schema"
            )
        detached = json.loads(
            json.dumps(
                dict(self.payload),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        expected = _canonical_sha256(detached)
        if self.trace_identity_sha256 != expected:
            raise GcsimOptimizerBenchmarkError(
                "debug trace identity differs from its payload"
            )
        object.__setattr__(self, "payload", MappingProxyType(detached))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            **dict(self.payload),
            "trace_identity_sha256": self.trace_identity_sha256,
        }


def build_gcsim_optimizer_debug_trace(
    result: GcsimOptimizerAnytimeSelectedResult,
    *,
    run_input: GcsimOptimizerRunInput,
    prepared_config_text: str,
    target_payload_text: str,
    target_identity_sha256: str,
) -> GcsimOptimizerDebugTrace:
    """Capture exact candidates and every adaptive-race disposition.

    The trace deliberately stores full proposal dictionaries.  Those include
    all twenty physical artifact IDs, materialized per-wearer stat vectors,
    active set lines, main stats, and the complete compiled GCSIM config, so a
    future benchmark is not forced to reverse a candidate hash.
    """

    if not isinstance(result, GcsimOptimizerAnytimeSelectedResult):
        raise GcsimOptimizerBenchmarkError("result must be typed")
    if not isinstance(run_input, GcsimOptimizerRunInput):
        raise GcsimOptimizerBenchmarkError("run_input must be typed")
    if result.run_input_sha256 != run_input.run_input_sha256:
        raise GcsimOptimizerBenchmarkError(
            "result and frozen run input identities differ"
        )
    if result.race_result is None:
        raise GcsimOptimizerBenchmarkError(
            "debug trace requires an executed account race"
        )
    for name, value in (
        ("prepared_config_text", prepared_config_text),
        ("target_payload_text", target_payload_text),
    ):
        if not isinstance(value, str) or not value.strip():
            raise GcsimOptimizerBenchmarkError(
                f"{name} must be non-empty text"
            )
    _require_sha256(target_identity_sha256, "target_identity_sha256")

    race = result.race_result
    race_phases = (*result.preliminary_race_results, race)
    tiers = tuple(item.tier_id for item in result.plan.race.tiers)
    tier_index = {tier_id: index for index, tier_id in enumerate(tiers)}
    trace_by_proposal: dict[str, list[tuple[int, object]]] = {}
    proposal_by_id = {}
    for phase_index, phase in enumerate(race_phases):
        for evaluation in phase.trace_evaluations:
            proposal_sha256 = evaluation.proposal.proposal_sha256
            proposal_by_id[proposal_sha256] = evaluation.proposal
            trace_by_proposal.setdefault(proposal_sha256, []).append(
                (phase_index, evaluation)
            )
    confirmed_ids = {
        item.proposal.proposal_sha256
        for item in race.confirmed_evaluations
    }
    evaluated_ids_by_tier = {
        tier_id: {
            item.proposal.proposal_sha256
            for phase in race_phases
            for item in phase.trace_evaluations
            if item.tier_id == tier_id
        }
        for tier_id in tiers
    }
    successful_by_tier = {
        tier_id: tuple(
            (phase_index, item)
            for phase_index, phase in enumerate(race_phases)
            for item in phase.trace_evaluations
            if item.tier_id == tier_id and item.success
        )
        for tier_id in tiers
    }

    candidate_rows = []
    for proposal_sha256 in sorted(proposal_by_id):
        proposal = proposal_by_id[proposal_sha256]
        evaluations = tuple(
            sorted(
                trace_by_proposal[proposal_sha256],
                key=lambda item: (item[0], tier_index[item[1].tier_id]),
            )
        )
        events = []
        for evaluation_index, (phase_index, evaluation) in enumerate(
            evaluations
        ):
            next_tier_id = (
                evaluations[evaluation_index + 1][1].tier_id
                if (
                    evaluation_index + 1 < len(evaluations)
                    and evaluations[evaluation_index + 1][0] == phase_index
                )
                else None
            )
            phase = race_phases[phase_index]
            phase_confirmed_ids = {
                item.proposal.proposal_sha256
                for item in phase.confirmed_evaluations
            }
            if (
                phase_index < len(race_phases) - 1
                and next_tier_id is None
                and proposal_sha256 in phase_confirmed_ids
            ):
                disposition, reason = (
                    "phase_confirmed",
                    "fed_exact_gcsim_coordinate_refinement",
                )
            else:
                disposition, reason = _race_disposition(
                    evaluation,
                    next_tier_id=next_tier_id,
                    confirmed=(
                        phase_index == len(race_phases) - 1
                        and proposal_sha256 in confirmed_ids
                    ),
                    tier_rows=tuple(
                        item
                        for candidate_phase, item in successful_by_tier[
                            evaluation.tier_id
                        ]
                        if candidate_phase == phase_index
                    ),
                    confidence_sigma=result.plan.race.confidence_sigma,
                    relative_margin=(
                        result.plan.race.relative_elimination_margin
                    ),
                )
            farming_result = evaluation.result
            events.append(
                {
                    "phase_index": phase_index,
                    "phase_kind": (
                        "terminal"
                        if phase_index == len(race_phases) - 1
                        else "preliminary"
                    ),
                    "tier_id": evaluation.tier_id,
                    "iterations": evaluation.iterations,
                    "success": evaluation.success,
                    "status": farming_result.status.value,
                    "dps_mean": evaluation.dps_mean,
                    "dps_se": evaluation.dps_se,
                    "cache_hit": farming_result.cache_hit,
                    "cache_key": farming_result.cache_key,
                    "request_identity_sha256": (
                        farming_result.request_identity_sha256
                    ),
                    "source_config_sha256": (
                        farming_result.source_config_sha256
                    ),
                    "elapsed_seconds": farming_result.elapsed_seconds,
                    "error": farming_result.error,
                    "disposition": disposition,
                    "reason": reason,
                }
            )
        artifact_vectors = {
            str(build.wearer.team_slot): {
                "wearer": build.wearer.to_dict(),
                "artifact_ids_by_slot": dict(
                    build.assignment.artifact_ids_by_slot
                ),
                "normalized_artifact_stats": dict(build.normalized_stats),
                "active_sets": [
                    item.to_dict() for item in build.active_sets
                ],
                "rendered_lines": list(build.rendered_lines),
            }
            for build in proposal.compiled_candidate.builds
        }
        candidate_rows.append(
            {
                "proposal_sha256": proposal_sha256,
                "required_anchor": (
                    "required_external_anchor"
                    in proposal.diversity_labels
                ),
                "confirmed_terminal": proposal_sha256 in confirmed_ids,
                "artifact_stat_vectors_by_slot": artifact_vectors,
                "stage_trace": events,
                "full_proposal": proposal.to_dict(),
            }
        )

    race_seed_policy = result.plan.race.to_dict()["seed_policy"]
    requested_totals: Counter[str] = Counter()
    successful_totals: Counter[str] = Counter()
    cache_hit_totals: Counter[str] = Counter()
    for phase in race_phases:
        requested_totals.update(dict(phase.requested_by_tier))
        successful_totals.update(dict(phase.successful_by_tier))
        cache_hit_totals.update(dict(phase.cache_hits_by_tier))
    response_seed = (
        None
        if result.response_result is None
        else result.response_result.synthetic_master_seed
    )
    payload = {
        "kind": "gcsim_optimizer_account_debug_trace",
        "frozen_input": {
            "run_input": run_input.identity_payload(),
            "request": run_input.request.to_dict(),
            "prepared_config_text": prepared_config_text,
            "prepared_config_sha256": _sha256_text(prepared_config_text),
            "target_payload_text": target_payload_text,
            "target_payload_sha256": _sha256_text(target_payload_text),
            "target_identity_sha256": target_identity_sha256,
        },
        "seed_policy": {
            "response": "paired_common_seed_panel_v1",
            "response_master_seed": response_seed,
            "race": race_seed_policy,
            "race_replay_note": (
                "exact configs and cache identities are frozen; this engine "
                "runner currently samples fresh race seeds on a cold replay"
            ),
        },
        "work_plan": result.plan.to_dict(),
        "response_result": (
            None
            if result.response_result is None
            else result.response_result.to_dict()
        ),
        "wearer_pools": [
            {
                "wearer": pool.wearer.to_dict(),
                "coverage": pool.coverage.to_dict(),
                "candidates": [
                    candidate.to_dict() for candidate in pool.candidates
                ],
            }
            for pool in result.wearer_pools
        ],
        "product_result": result.to_dict(),
        "race": {
            "status": race.status.value,
            "evidence_sha256": race.evidence_sha256,
            "requested_by_tier": dict(sorted(requested_totals.items())),
            "successful_by_tier": dict(sorted(successful_totals.items())),
            "cache_hits_by_tier": dict(sorted(cache_hit_totals.items())),
            "evaluated_proposal_sha256s_by_tier": {
                tier_id: sorted(evaluated_ids_by_tier[tier_id])
                for tier_id in tiers
            },
            "phases": [
                {
                    "phase_index": phase_index,
                    "status": phase.status.value,
                    "evidence_sha256": phase.evidence_sha256,
                    "requested_by_tier": dict(phase.requested_by_tier),
                    "successful_by_tier": dict(phase.successful_by_tier),
                    "cache_hits_by_tier": dict(phase.cache_hits_by_tier),
                }
                for phase_index, phase in enumerate(race_phases)
            ],
        },
        "candidates": candidate_rows,
    }
    return GcsimOptimizerDebugTrace(
        payload=payload,
        trace_identity_sha256=_canonical_sha256(payload),
    )


def build_gcsim_optimizer_theoretical_debug_trace(
    result: GcsimOptimizerTheoreticalAnytimeResult,
    *,
    request: GcsimOptimizerOperationRequest,
    prepared_config_text: str,
    target_payload_text: str,
    target_identity_sha256: str,
) -> GcsimOptimizerDebugTrace:
    """Capture the complete equal-investment theoretical search evidence.

    Unlike the compact product DTO, this payload deliberately retains every
    response/set-impact row, candidate pool, simulated proposal, inner
    optimizer config, allocation line, and validation/rerace disposition.
    """

    if not isinstance(result, GcsimOptimizerTheoreticalAnytimeResult):
        raise GcsimOptimizerBenchmarkError(
            "theoretical result must be typed"
        )
    if not isinstance(request, GcsimOptimizerOperationRequest):
        raise GcsimOptimizerBenchmarkError(
            "theoretical request must be typed"
        )
    if result.terminal.request != request:
        raise GcsimOptimizerBenchmarkError(
            "theoretical result and frozen request differ"
        )
    for name, value in (
        ("prepared_config_text", prepared_config_text),
        ("target_payload_text", target_payload_text),
    ):
        if not isinstance(value, str) or not value.strip():
            raise GcsimOptimizerBenchmarkError(
                f"{name} must be non-empty text"
            )
    _require_sha256(target_identity_sha256, "target_identity_sha256")

    race_payload = None
    if result.race_result is not None:
        race = result.race_result
        race_payload = {
            "status": race.status.value,
            "domain_identity_sha256": race.domain_identity_sha256,
            "engine_binding_sha256": race.engine_binding_sha256,
            "source_config_sha256": race.source_config_sha256,
            "plan_identity_sha256": race.plan_identity_sha256,
            "evidence_sha256": race.evidence_sha256,
            "elapsed_seconds": race.elapsed_seconds,
            "tiers": [
                {
                    **tier.to_dict(),
                    "evaluations": [
                        {
                            **evaluation.to_dict(),
                            "full_proposal": evaluation.proposal.to_dict(),
                            "full_probe_key": [
                                list(choice)
                                for choice in evaluation.proposal.state.probe_key
                            ],
                            "physical_state": _physical_state_payload(
                                evaluation.physical_state
                            ),
                            "disposition": _theoretical_race_disposition(
                                tier.tier.tier_id,
                                evaluation,
                                selected=set(
                                    tier.selected_proposal_sha256
                                ),
                            ),
                        }
                        for evaluation in tier.evaluations
                    ],
                }
                for tier in race.tier_traces
            ],
            "finalist_evaluations": [
                {
                    **evaluation.to_dict(),
                    "full_proposal": evaluation.proposal.to_dict(),
                    "physical_state": _physical_state_payload(
                        evaluation.physical_state
                    ),
                }
                for evaluation in race.finalist_evaluations
            ],
        }

    layout_payload = None
    if result.layout_screen_result is not None:
        layout = result.layout_screen_result
        layout_payload = {
            "status": layout.status.value,
            "domain": layout.domain.to_dict(),
            "evidence_sha256": layout.evidence_sha256,
            "elapsed_seconds": layout.elapsed_seconds,
            "optimizer": _finalist_result_payload(layout.finalist_result),
            "selected_outcomes": [
                _finalist_outcome_payload(item)
                for item in layout.selected_outcomes
            ],
        }

    validation_payload = None
    if result.validation_result is not None:
        validation = result.validation_result
        validation_payload = {
            "status": validation.status.value,
            "evidence_sha256": validation.evidence_sha256,
            "elapsed_seconds": validation.elapsed_seconds,
            "requested_rerace_count": validation.requested_rerace_count,
            "optimizer": _finalist_result_payload(
                validation.finalist_result
            ),
            "evaluations": [
                {
                    "request_sha256": item.request_sha256,
                    "candidate_identity_sha256": (
                        item.candidate_identity_sha256
                    ),
                    "evidence_sha256": item.evidence_sha256,
                    "iterations": item.iterations,
                    "dps_mean": item.dps_mean,
                    "dps_se": item.dps_se,
                    "compiled_config_sha256": (
                        item.compiled_config_sha256
                    ),
                    "execution_identity_sha256": (
                        item.execution_identity_sha256
                    ),
                    "physical_state": _physical_state_payload(item.state),
                    "finalist_outcome": _finalist_outcome_payload(
                        item.finalist_outcome
                    ),
                    "rerace_result": (
                        None
                        if item.rerace_result is None
                        else _farming_result_payload(item.rerace_result)
                    ),
                }
                for item in validation.evaluations
            ],
            "rerace_results": [
                _farming_result_payload(item)
                for item in validation.rerace_results
            ],
        }

    top_n = []
    if result.validation_result is not None:
        evaluations = result.validation_result.evaluations
        top_dps = evaluations[0].dps_mean if evaluations else None
        for rank, evaluation in enumerate(evaluations, start=1):
            top_n.append(
                {
                    "rank": rank,
                    "dps_mean": evaluation.dps_mean,
                    "dps_se": evaluation.dps_se,
                    "iterations": evaluation.iterations,
                    "percent_of_top_1": (
                        None
                        if not top_dps
                        else 100.0 * evaluation.dps_mean / top_dps
                    ),
                    "physical_state": _physical_state_payload(
                        evaluation.state
                    ),
                    "allocations": _allocation_payload(
                        evaluation.finalist_outcome.allocations
                    ),
                }
            )

    payload = {
        "kind": "gcsim_optimizer_theoretical_debug_trace",
        "frozen_input": {
            "request": request.to_dict(),
            "prepared_config_text": prepared_config_text,
            "prepared_config_sha256": _sha256_text(prepared_config_text),
            "target_payload_text": target_payload_text,
            "target_payload_sha256": _sha256_text(target_payload_text),
            "target_identity_sha256": target_identity_sha256,
        },
        "seed_policy": {
            "response_and_set_impact": "paired_common_seed_panel_v1",
            "response_master_seed": (
                None
                if result.response_result is None
                else result.response_result.synthetic_master_seed
            ),
            "quick_race": "ordinary_gcsim_fresh_engine_seeds",
            "inner_optimizer": (
                "same_frozen_iterations_workers_and_substat_budget"
            ),
        },
        "work_plan": result.plan.to_dict(),
        "product_result": result.to_dict(),
        "pair_domain": (
            None
            if result.pair_domain is None
            else result.pair_domain.to_dict()
        ),
        "response_result": (
            None
            if result.response_result is None
            else result.response_result.to_dict()
        ),
        "component_set_impact_result": (
            None
            if result.component_set_impact_result is None
            else result.component_set_impact_result.to_dict()
        ),
        "set_impact_result": (
            None
            if result.set_impact_result is None
            else result.set_impact_result.to_dict()
        ),
        "candidate_domain": (
            None
            if result.candidate_domain is None
            else result.candidate_domain.to_dict()
        ),
        "race": race_payload,
        "layout_screen": layout_payload,
        "validation": validation_payload,
        "top_n": top_n,
    }
    return GcsimOptimizerDebugTrace(
        payload=payload,
        trace_identity_sha256=_canonical_sha256(payload),
    )


def write_gcsim_optimizer_debug_trace(
    trace: GcsimOptimizerDebugTrace,
    path: str | Path,
) -> Path:
    """Atomically persist a trace without leaving a partial benchmark file."""

    if not isinstance(trace, GcsimOptimizerDebugTrace):
        raise GcsimOptimizerBenchmarkError("trace must be typed")
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{uuid4().hex}.tmp"
    )
    try:
        temporary.write_text(
            json.dumps(
                trace.to_dict(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


class GcsimOptimizerBenchmarkScope(str, Enum):
    SELECTED_SET_POOLS = "selected_set_pools"
    ALL_DATABASE_SETS = "all_database_sets"


class GcsimOptimizerBenchmarkCacheState(str, Enum):
    COLD = "cold"
    WARM = "warm"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerBenchmarkCase:
    case_id: str
    scope: GcsimOptimizerBenchmarkScope
    include_2p2p: bool
    cache_state: GcsimOptimizerBenchmarkCacheState
    cpu_budget: int
    inventory_artifact_count: int
    eligible_set_count: int
    selected_pool_sizes: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.case_id or self.case_id != self.case_id.strip():
            raise GcsimOptimizerBenchmarkError("case_id must be non-empty and trimmed")
        if not isinstance(self.scope, GcsimOptimizerBenchmarkScope):
            raise GcsimOptimizerBenchmarkError("benchmark scope must be typed")
        if not isinstance(self.cache_state, GcsimOptimizerBenchmarkCacheState):
            raise GcsimOptimizerBenchmarkError("cache state must be typed")
        for name, value, minimum in (
            ("cpu_budget", self.cpu_budget, 1),
            ("inventory_artifact_count", self.inventory_artifact_count, 0),
            ("eligible_set_count", self.eligible_set_count, 0),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise GcsimOptimizerBenchmarkError(f"{name} is invalid")
        pools = tuple(self.selected_pool_sizes)
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in pools):
            raise GcsimOptimizerBenchmarkError("selected pool sizes must be non-negative integers")
        if self.scope is GcsimOptimizerBenchmarkScope.SELECTED_SET_POOLS and len(pools) != 4:
            raise GcsimOptimizerBenchmarkError("selected-set benchmark requires four pool sizes")
        if self.scope is GcsimOptimizerBenchmarkScope.ALL_DATABASE_SETS and pools:
            raise GcsimOptimizerBenchmarkError("all-set benchmark cannot claim selected pool sizes")
        object.__setattr__(self, "selected_pool_sizes", pools)

    @property
    def comparable_identity(self) -> tuple[object, ...]:
        """Identity excluding cold/warm state so both observations can be paired."""

        return (
            self.scope.value,
            self.include_2p2p,
            self.cpu_budget,
            self.inventory_artifact_count,
            self.eligible_set_count,
            self.selected_pool_sizes,
        )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerBenchmarkObservation:
    case: GcsimOptimizerBenchmarkCase
    elapsed_seconds: float
    peak_working_set_bytes: int
    generated_builds: int
    joint_proposals: int
    simulations: int
    cache_hits: int
    terminal_status: str
    stop_reason: str
    cancellation_latency_seconds: float | None = None
    ui_max_heartbeat_gap_seconds: float | None = None
    counters: Mapping[str, int] = field(default_factory=dict)
    schema_version: int = GCSIM_OPTIMIZER_BENCHMARK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.case, GcsimOptimizerBenchmarkCase):
            raise GcsimOptimizerBenchmarkError("observation case must be typed")
        if not isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise GcsimOptimizerBenchmarkError("elapsed time must be finite and non-negative")
        for name in (
            "peak_working_set_bytes",
            "generated_builds",
            "joint_proposals",
            "simulations",
            "cache_hits",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise GcsimOptimizerBenchmarkError(f"{name} must be non-negative")
        for name in ("cancellation_latency_seconds", "ui_max_heartbeat_gap_seconds"):
            value = getattr(self, name)
            if value is not None and (not isfinite(value) or value < 0):
                raise GcsimOptimizerBenchmarkError(f"{name} must be finite and non-negative")
        if not self.terminal_status:
            raise GcsimOptimizerBenchmarkError("terminal status must be recorded")
        frozen_counters = {str(key): int(value) for key, value in self.counters.items()}
        if any(value < 0 for value in frozen_counters.values()):
            raise GcsimOptimizerBenchmarkError("benchmark counters must be non-negative")
        object.__setattr__(self, "counters", MappingProxyType(dict(sorted(frozen_counters.items()))))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "case": {
                "case_id": self.case.case_id,
                "scope": self.case.scope.value,
                "include_2p2p": self.case.include_2p2p,
                "cache_state": self.case.cache_state.value,
                "cpu_budget": self.case.cpu_budget,
                "inventory_artifact_count": self.case.inventory_artifact_count,
                "eligible_set_count": self.case.eligible_set_count,
                "selected_pool_sizes": list(self.case.selected_pool_sizes),
            },
            "elapsed_seconds": self.elapsed_seconds,
            "peak_working_set_bytes": self.peak_working_set_bytes,
            "generated_builds": self.generated_builds,
            "joint_proposals": self.joint_proposals,
            "simulations": self.simulations,
            "cache_hits": self.cache_hits,
            "terminal_status": self.terminal_status,
            "stop_reason": self.stop_reason,
            "cancellation_latency_seconds": self.cancellation_latency_seconds,
            "ui_max_heartbeat_gap_seconds": self.ui_max_heartbeat_gap_seconds,
            "counters": dict(self.counters),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerBenchmarkSummary:
    observations: tuple[GcsimOptimizerBenchmarkObservation, ...]
    elapsed_p50_seconds: float
    elapsed_p95_seconds: float
    peak_working_set_bytes: int
    maximum_cancellation_latency_seconds: float | None
    maximum_ui_heartbeat_gap_seconds: float | None
    schema_version: int = GCSIM_OPTIMIZER_BENCHMARK_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "elapsed_p50_seconds": self.elapsed_p50_seconds,
            "elapsed_p95_seconds": self.elapsed_p95_seconds,
            "peak_working_set_bytes": self.peak_working_set_bytes,
            "maximum_cancellation_latency_seconds": self.maximum_cancellation_latency_seconds,
            "maximum_ui_heartbeat_gap_seconds": self.maximum_ui_heartbeat_gap_seconds,
            "observations": [item.to_dict() for item in self.observations],
        }


def summarize_gcsim_optimizer_benchmarks(
    observations: Iterable[GcsimOptimizerBenchmarkObservation],
) -> GcsimOptimizerBenchmarkSummary:
    rows = tuple(observations)
    if not rows:
        raise GcsimOptimizerBenchmarkError("benchmark summary needs observations")
    elapsed = sorted(item.elapsed_seconds for item in rows)
    cancellation = [
        item.cancellation_latency_seconds
        for item in rows
        if item.cancellation_latency_seconds is not None
    ]
    heartbeat = [
        item.ui_max_heartbeat_gap_seconds
        for item in rows
        if item.ui_max_heartbeat_gap_seconds is not None
    ]
    return GcsimOptimizerBenchmarkSummary(
        observations=rows,
        elapsed_p50_seconds=_nearest_rank(elapsed, 0.50),
        elapsed_p95_seconds=_nearest_rank(elapsed, 0.95),
        peak_working_set_bytes=max(item.peak_working_set_bytes for item in rows),
        maximum_cancellation_latency_seconds=max(cancellation) if cancellation else None,
        maximum_ui_heartbeat_gap_seconds=max(heartbeat) if heartbeat else None,
    )


def validate_gcsim_optimizer_benchmark_matrix(
    observations: Iterable[GcsimOptimizerBenchmarkObservation],
) -> tuple[str, ...]:
    """Return missing matrix cells instead of silently calling a partial run complete."""

    rows = tuple(observations)
    missing: list[str] = []
    for scope in GcsimOptimizerBenchmarkScope:
        for include_2p2p in (False, True):
            matching = [
                row for row in rows
                if row.case.scope is scope and row.case.include_2p2p == include_2p2p
            ]
            for cache_state in GcsimOptimizerBenchmarkCacheState:
                if not any(row.case.cache_state is cache_state for row in matching):
                    missing.append(f"{scope.value}:2p2p={include_2p2p}:{cache_state.value}")
    if not any(row.cancellation_latency_seconds is not None for row in rows):
        missing.append("cancellation_latency")
    if not any(row.ui_max_heartbeat_gap_seconds is not None for row in rows):
        missing.append("ui_responsiveness")
    return tuple(missing)


def _race_disposition(
    evaluation,
    *,
    next_tier_id: str | None,
    confirmed: bool,
    tier_rows: tuple[object, ...],
    confidence_sigma: float,
    relative_margin: float,
) -> tuple[str, str]:
    if not evaluation.success:
        return (
            "evaluation_failed",
            evaluation.result.error
            or f"simulator_status:{evaluation.result.status.value}",
        )
    if next_tier_id is not None:
        return "promoted", f"promoted_to:{next_tier_id}"
    if confirmed:
        if evaluation.iterations >= 1000:
            return "confirmed_terminal", "completed_long_rerace"
        return "confirmed_terminal", "retained_validated_200_evidence"
    valid_rows = tuple(
        row for row in tier_rows if row.dps_mean is not None
    )
    if not valid_rows or evaluation.dps_mean is None:
        return "eliminated", "tier_candidate_budget"
    leader = max(valid_rows, key=lambda row: row.dps_mean)
    if leader.dps_mean is None:
        return "eliminated", "tier_candidate_budget"
    leader_lower = (
        leader.dps_mean
        if leader.dps_se is None
        else leader.dps_mean - confidence_sigma * leader.dps_se
    )
    optimistic = (
        evaluation.dps_mean
        if evaluation.dps_se is None
        else evaluation.dps_mean
        + confidence_sigma * evaluation.dps_se
    )
    margin = abs(leader.dps_mean) * relative_margin
    if optimistic + margin < leader_lower:
        return "eliminated", "confidence_interval_below_leader"
    return "eliminated", "next_tier_candidate_budget_or_diversity_policy"


def _theoretical_race_disposition(
    tier_id: str,
    evaluation,
    *,
    selected: set[str],
) -> dict[str, str]:
    if not evaluation.success:
        return {
            "status": "evaluation_failed",
            "reason": "gcsim_tier_evaluation_failed",
        }
    if evaluation.proposal.proposal_sha256 in selected:
        return {
            "status": "selected",
            "reason": (
                "retained_as_distinct_package_signature"
                if not tier_id.endswith("_32")
                else "retained_by_uncertainty_aware_finalist_policy"
            ),
        }
    return {
        "status": "eliminated",
        "reason": (
            "outside_distinct_package_signature_budget"
            if not tier_id.endswith("_32")
            else "outside_uncertainty_aware_finalist_portfolio"
        ),
    }


def _physical_state_payload(state) -> dict[str, object]:
    return {
        "key": [list(choice) for choice in state.key],
        "choices": [
            {
                "wearer_id": choice.wearer_id,
                "set_key": choice.set_key,
                "main_stat_layout_id": choice.main_stat_layout_id,
                "offpiece_slot": choice.offpiece_slot,
            }
            for choice in state.choices
        ],
    }


def _allocation_payload(allocations) -> list[dict[str, object]]:
    return [
        {
            "wearer_id": item.wearer_id,
            "set_key": item.set_key,
            "main_stat_layout_id": item.main_stat_layout_id,
            "offpiece_slot": item.offpiece_slot,
            "add_stats_lines": list(item.add_stats_lines),
        }
        for item in allocations
    ]


def _finalist_outcome_payload(outcome) -> dict[str, object]:
    return {
        "ordinal": outcome.ordinal,
        "physical_state": _physical_state_payload(outcome.state),
        "dps_mean": outcome.dps_mean,
        "dps_se": outcome.dps_se,
        "iterations": outcome.iterations,
        "optimizer_input_config_text": outcome.optimizer_input_config_text,
        "optimizer_input_sha256": outcome.optimizer_input_sha256,
        "optimized_config_text": outcome.optimized_config_text,
        "optimized_config_sha256": outcome.optimized_config_sha256,
        "result_json_text": outcome.result_json_bytes.decode("utf-8"),
        "result_json_sha256": outcome.result_json_sha256,
        "allocation_sha256": outcome.allocation_sha256,
        "allocations": _allocation_payload(outcome.allocations),
        "cache_identity_sha256": outcome.cache_identity_sha256,
    }


def _finalist_result_payload(result) -> dict[str, object]:
    return {
        "status": result.status.value,
        "stop_reason": result.stop_reason,
        "request_sha256": result.request_sha256,
        "source_config_sha256": result.source_config_sha256,
        "validation_config_sha256": result.validation_config_sha256,
        "layout_catalog_sha256": result.layout_catalog_sha256,
        "finalist_domain_sha256": result.finalist_domain_sha256,
        "budget_sha256": result.budget_sha256,
        "engine_binding_sha256": result.engine_binding_sha256,
        "elapsed_seconds": result.elapsed_seconds,
        "attempted_count": result.attempted_count,
        "successful_count": result.successful_count,
        "attempts": [
            {
                "ordinal": attempt.ordinal,
                "physical_state": _physical_state_payload(attempt.state),
                "status": attempt.status.value,
                "runner_status": attempt.runner_status,
                "optimizer_input_sha256": attempt.optimizer_input_sha256,
                "cache_identity_sha256": attempt.cache_identity_sha256,
                "cache_hit": attempt.cache_hit,
                "error": attempt.error,
                "outcome": (
                    None
                    if attempt.outcome is None
                    else _finalist_outcome_payload(attempt.outcome)
                ),
            }
            for attempt in result.attempts
        ],
        "display_outcomes": [
            _finalist_outcome_payload(item) for item in result.outcomes
        ],
    }


def _farming_result_payload(result) -> dict[str, object]:
    return {
        "status": result.status.value,
        "success": result.success,
        "request_identity_sha256": result.request_identity_sha256,
        "cache_key": result.cache_key,
        "candidate_keys": [list(item) for item in result.candidate_keys],
        "comparison_context_sha256": result.comparison_context_sha256,
        "expected_iterations": result.expected_iterations,
        "summary": result.summary.to_dict(),
        "cache_hit": result.cache_hit,
        "engine_binding_sha256": result.engine_binding_sha256,
        "artifact_sha256": result.artifact_sha256,
        "source_config_sha256": result.source_config_sha256,
        "elapsed_seconds": result.elapsed_seconds,
        "error": result.error,
    }


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_sha256(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GcsimOptimizerBenchmarkError(
            f"{field_name} must be lowercase SHA-256"
        )


def _nearest_rank(values: list[float], quantile: float) -> float:
    index = max(0, ceil(quantile * len(values)) - 1)
    return float(values[index])


__all__ = [
    "GCSIM_OPTIMIZER_BENCHMARK_SCHEMA_VERSION",
    "GCSIM_OPTIMIZER_DEBUG_TRACE_SCHEMA_VERSION",
    "GcsimOptimizerBenchmarkCacheState",
    "GcsimOptimizerBenchmarkCase",
    "GcsimOptimizerBenchmarkError",
    "GcsimOptimizerBenchmarkObservation",
    "GcsimOptimizerBenchmarkScope",
    "GcsimOptimizerBenchmarkSummary",
    "GcsimOptimizerDebugTrace",
    "build_gcsim_optimizer_debug_trace",
    "build_gcsim_optimizer_theoretical_debug_trace",
    "summarize_gcsim_optimizer_benchmarks",
    "validate_gcsim_optimizer_benchmark_matrix",
    "write_gcsim_optimizer_debug_trace",
]
