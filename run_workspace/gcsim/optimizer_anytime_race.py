"""Adaptive 8 -> 32 -> 200 -> 1000 GCSIM race for account proposals."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from math import isfinite, sqrt
import os
from threading import Event, Lock
from time import monotonic

from .farming_evaluator import (
    GcsimFarmingBatchStatus,
    GcsimFarmingEvaluationResult,
    GcsimFarmingEvaluationScheduler,
    GcsimFarmingSchedulerBudget,
)
from .optimizer_account_evaluator import (
    prepare_gcsim_optimizer_account_evaluation,
)
from .optimizer_cache import GcsimOptimizerCacheStore
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_joint_proposals import GcsimOptimizerJointProposal
from .optimizer_product_contracts import GcsimOptimizerWearerTarget
from .optimizer_run_input import GcsimOptimizerRunInput
from .optimizer_stat_response import GcsimStatResponseTarget


GCSIM_OPTIMIZER_ANYTIME_RACE_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_ANYTIME_RACE_PLAN_ID = "multifidelity_race"
GCSIM_OPTIMIZER_ANYTIME_RACE_PLAN_VERSION = 6

AnytimeRaceProgressCallback = Callable[
    [str, int, int, "GcsimOptimizerAnytimeRaceEvaluation | None"],
    None,
]


class GcsimOptimizerAnytimeRaceError(RuntimeError):
    """Fail-closed adaptive race error."""


class GcsimOptimizerAnytimeRaceStatus(str, Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    NO_SUCCESS = "no_success"
    CANCELLED = "cancelled"
    DEADLINE = "deadline"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAnytimeRaceTier:
    tier_id: str
    iterations: int
    max_candidates: int
    min_survivors: int
    timeout_seconds: float
    schema_version: int = GCSIM_OPTIMIZER_ANYTIME_RACE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if (
            not isinstance(self.tier_id, str)
            or not self.tier_id
            or self.tier_id != self.tier_id.strip()
        ):
            raise GcsimOptimizerAnytimeRaceError(
                "tier_id must be non-empty trimmed text"
            )
        for field_name in (
            "iterations",
            "max_candidates",
            "min_survivors",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise GcsimOptimizerAnytimeRaceError(
                    f"{field_name} must be a positive integer"
                )
        if self.min_survivors > self.max_candidates:
            raise GcsimOptimizerAnytimeRaceError(
                "tier min_survivors exceeds max_candidates"
            )
        if not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise GcsimOptimizerAnytimeRaceError(
                "tier timeout_seconds must be finite and positive"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tier_id": self.tier_id,
            "iterations": self.iterations,
            "max_candidates": self.max_candidates,
            "min_survivors": self.min_survivors,
            "timeout_seconds": self.timeout_seconds,
        }


def _default_tiers() -> tuple[GcsimOptimizerAnytimeRaceTier, ...]:
    return (
        GcsimOptimizerAnytimeRaceTier("screen_8", 8, 64, 16, 90.0),
        # Eight iterations have several-thousand-DPS standard error on the
        # real account corpus.  Keep a broad n=32 bridge and validate twice
        # the product top-N capacity at n=200 so an unlucky screen seed does
        # not decide the physical build before the signal is measurable.
        GcsimOptimizerAnytimeRaceTier("refine_32", 32, 64, 16, 120.0),
        GcsimOptimizerAnytimeRaceTier("validate_200", 200, 16, 8, 180.0),
        GcsimOptimizerAnytimeRaceTier("rerace_1000", 1000, 3, 2, 300.0),
    )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAnytimeRacePlan:
    tiers: tuple[GcsimOptimizerAnytimeRaceTier, ...] = field(
        default_factory=_default_tiers
    )
    worker_count: int = 1
    max_parallel_candidates: int = 1
    total_cpu_budget: int = 1
    confidence_sigma: float = 2.0
    relative_elimination_margin: float = 0.0075
    min_saveable_iterations: int = 200
    overall_deadline_seconds: float = 900.0
    schema_version: int = GCSIM_OPTIMIZER_ANYTIME_RACE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        tiers = tuple(self.tiers)
        if any(
            not isinstance(item, GcsimOptimizerAnytimeRaceTier)
            for item in tiers
        ):
            raise GcsimOptimizerAnytimeRaceError(
                "race tiers must be typed"
            )
        if tuple(item.iterations for item in tiers) != (8, 32, 200, 1000):
            raise GcsimOptimizerAnytimeRaceError(
                "anytime_approx_v1 requires tiers 8, 32, 200, 1000"
            )
        if len({item.tier_id for item in tiers}) != len(tiers):
            raise GcsimOptimizerAnytimeRaceError(
                "race tier IDs must be unique"
            )
        for field_name in (
            "worker_count",
            "max_parallel_candidates",
            "total_cpu_budget",
            "min_saveable_iterations",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise GcsimOptimizerAnytimeRaceError(
                    f"{field_name} must be a positive integer"
                )
        if self.worker_count > self.total_cpu_budget:
            raise GcsimOptimizerAnytimeRaceError(
                "race worker_count exceeds total_cpu_budget"
            )
        logical_cpus = os.cpu_count() or 1
        if self.total_cpu_budget > logical_cpus:
            raise GcsimOptimizerAnytimeRaceError(
                "race total_cpu_budget exceeds detected logical CPUs"
            )
        if self.min_saveable_iterations != tiers[2].iterations:
            raise GcsimOptimizerAnytimeRaceError(
                "minimum saveable fidelity must be the 200-iteration tier"
            )
        if not isfinite(self.confidence_sigma) or self.confidence_sigma <= 0:
            raise GcsimOptimizerAnytimeRaceError(
                "confidence_sigma must be finite and positive"
            )
        if (
            not isfinite(self.relative_elimination_margin)
            or not 0 <= self.relative_elimination_margin < 0.1
        ):
            raise GcsimOptimizerAnytimeRaceError(
                "relative_elimination_margin must be in [0, 0.1)"
            )
        if (
            not isfinite(self.overall_deadline_seconds)
            or self.overall_deadline_seconds <= 0
        ):
            raise GcsimOptimizerAnytimeRaceError(
                "overall_deadline_seconds must be finite and positive"
            )
        object.__setattr__(self, "tiers", tiers)

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": GCSIM_OPTIMIZER_ANYTIME_RACE_PLAN_ID,
            "plan_version": GCSIM_OPTIMIZER_ANYTIME_RACE_PLAN_VERSION,
            "tiers": [item.to_dict() for item in self.tiers],
            "worker_count": self.worker_count,
            "max_parallel_candidates": self.max_parallel_candidates,
            "total_cpu_budget": self.total_cpu_budget,
            "confidence_sigma": self.confidence_sigma,
            "relative_elimination_margin": (
                self.relative_elimination_margin
            ),
            "min_saveable_iterations": self.min_saveable_iterations,
            "overall_deadline_seconds": self.overall_deadline_seconds,
            "seed_policy": "process_runner_v1_random_engine_seeds",
            "worker_allocation_policy": (
                "fill_total_cpu_budget_per_tier_v1"
            ),
            "survivor_capacity_policy": "broad_noisy_screen_v2",
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAnytimeRaceEvaluation:
    tier_id: str
    proposal: GcsimOptimizerJointProposal
    result: GcsimFarmingEvaluationResult
    schema_version: int = GCSIM_OPTIMIZER_ANYTIME_RACE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if self.result.candidate_keys == ():
            raise GcsimOptimizerAnytimeRaceError(
                "race evaluation lacks candidate identity"
            )

    @property
    def success(self) -> bool:
        return self.result.success

    @property
    def iterations(self) -> int:
        return self.result.expected_iterations

    @property
    def dps_mean(self) -> float | None:
        return self.result.summary.dps_mean

    @property
    def dps_se(self) -> float | None:
        return self.result.summary.dps_se

    @property
    def evidence_sha256(self) -> str:
        return _canonical_sha256(
            {
                "tier_id": self.tier_id,
                "proposal_sha256": self.proposal.proposal_sha256,
                "request_identity_sha256": (
                    self.result.request_identity_sha256
                ),
                "source_config_sha256": self.result.source_config_sha256,
                "cache_key": self.result.cache_key,
                "summary": self.result.summary.to_dict(),
            }
        )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAnytimeRaceResult:
    status: GcsimOptimizerAnytimeRaceStatus
    confirmed_evaluations: tuple[
        GcsimOptimizerAnytimeRaceEvaluation, ...
    ]
    trace_evaluations: tuple[GcsimOptimizerAnytimeRaceEvaluation, ...]
    requested_by_tier: tuple[tuple[str, int], ...]
    successful_by_tier: tuple[tuple[str, int], ...]
    cache_hits_by_tier: tuple[tuple[str, int], ...]
    evidence_sha256: str
    elapsed_seconds: float
    schema_version: int = GCSIM_OPTIMIZER_ANYTIME_RACE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if any(
            not item.success
            or item.iterations < 200
            for item in self.confirmed_evaluations
        ):
            raise GcsimOptimizerAnytimeRaceError(
                "confirmed race rows require successful >=200 evidence"
            )
        if tuple(self.confirmed_evaluations) != tuple(
            sorted(
                self.confirmed_evaluations,
                key=_evaluation_rank,
            )
        ):
            raise GcsimOptimizerAnytimeRaceError(
                "confirmed race rows must use deterministic DPS order"
            )
        _require_sha256(self.evidence_sha256, "evidence_sha256")
        if not isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise GcsimOptimizerAnytimeRaceError(
                "elapsed_seconds must be finite and non-negative"
            )

    @property
    def best_confirmed(
        self,
    ) -> GcsimOptimizerAnytimeRaceEvaluation | None:
        return (
            self.confirmed_evaluations[0]
            if self.confirmed_evaluations
            else None
        )


class GcsimOptimizerAnytimeRaceSession:
    """One-shot, cancellable adaptive race owner."""

    def __init__(
        self,
        run_input: GcsimOptimizerRunInput,
        *,
        engine_context: GcsimOptimizerEngineContext,
        proposals: Sequence[GcsimOptimizerJointProposal],
        required_proposal_sha256s: Sequence[str] = (),
        plan: GcsimOptimizerAnytimeRacePlan | None = None,
        progress_callback: AnytimeRaceProgressCallback | None = None,
        cache_store: GcsimOptimizerCacheStore | None = None,
        enable_cache: bool = True,
        session_factory: Callable[[object], object] | None = None,
        environment: Mapping[str, str] | None = None,
        stat_response_target: GcsimStatResponseTarget | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.run_input = run_input
        self.engine_context = engine_context
        self.proposals = tuple(proposals)
        self.required_proposal_sha256s = tuple(required_proposal_sha256s)
        self.plan = plan or GcsimOptimizerAnytimeRacePlan()
        self.progress_callback = progress_callback
        self.cache_store = cache_store
        self.enable_cache = enable_cache
        self.session_factory = session_factory
        self.environment = dict(environment or {})
        self.stat_response_target = stat_response_target
        self.clock = clock
        self._cancel_event = Event()
        self._lock = Lock()
        self._active_scheduler: GcsimFarmingEvaluationScheduler | None = None
        self._started = False
        if not self.proposals:
            raise GcsimOptimizerAnytimeRaceError(
                "race requires at least one proposal"
            )
        proposal_ids = tuple(
            proposal.proposal_sha256 for proposal in self.proposals
        )
        if len(set(proposal_ids)) != len(proposal_ids):
            raise GcsimOptimizerAnytimeRaceError(
                "race proposals must have unique identities"
            )
        for proposal_sha256 in self.required_proposal_sha256s:
            _require_sha256(
                proposal_sha256,
                "required_proposal_sha256s",
            )
        if (
            len(set(self.required_proposal_sha256s))
            != len(self.required_proposal_sha256s)
        ):
            raise GcsimOptimizerAnytimeRaceError(
                "required proposal identities must be unique"
            )
        if not set(self.required_proposal_sha256s).issubset(proposal_ids):
            raise GcsimOptimizerAnytimeRaceError(
                "required proposal identity is absent from the race"
            )
        if any(
            len(self.required_proposal_sha256s) > tier.max_candidates
            for tier in self.plan.tiers
        ):
            raise GcsimOptimizerAnytimeRaceError(
                "required proposals exceed a race tier candidate budget"
            )

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            scheduler = self._active_scheduler
        if scheduler is not None:
            scheduler.cancel()

    def run(self) -> GcsimOptimizerAnytimeRaceResult:
        with self._lock:
            if self._started:
                raise GcsimOptimizerAnytimeRaceError(
                    "race sessions are one-shot"
                )
            self._started = True
        started = self.clock()
        deadline = started + self.plan.overall_deadline_seconds
        trace: list[GcsimOptimizerAnytimeRaceEvaluation] = []
        requested: dict[str, int] = {}
        successful: dict[str, int] = {}
        cache_hits: dict[str, int] = {}
        status = GcsimOptimizerAnytimeRaceStatus.COMPLETED
        current = _retain_required_proposals(
            self.proposals,
            required_proposal_sha256s=self.required_proposal_sha256s,
            limit=self.plan.tiers[0].max_candidates,
        )
        confirmed: tuple[GcsimOptimizerAnytimeRaceEvaluation, ...] = ()
        for tier_index, tier in enumerate(self.plan.tiers[:3]):
            terminal = self._terminal_status(deadline)
            if terminal is not None:
                status = terminal
                break
            evaluations, batch_status = self._evaluate_tier(
                current,
                tier=tier,
                deadline=deadline,
            )
            trace.extend(evaluations)
            requested[tier.tier_id] = len(evaluations)
            successful[tier.tier_id] = sum(
                item.success for item in evaluations
            )
            cache_hits[tier.tier_id] = sum(
                item.result.cache_hit for item in evaluations
            )
            terminal = _batch_status(batch_status)
            if terminal is None:
                _require_successful_required_evaluations(
                    evaluations,
                    required_proposal_sha256s=(
                        self.required_proposal_sha256s
                    ),
                    tier_id=tier.tier_id,
                )
            if terminal is not None:
                status = terminal
                if tier.iterations >= self.plan.min_saveable_iterations:
                    confirmed = tuple(
                        sorted(
                            (
                                item
                                for item in evaluations
                                if item.success
                            ),
                            key=_evaluation_rank,
                        )
                    )
                break
            successful_rows = tuple(
                item for item in evaluations if item.success
            )
            if not successful_rows:
                status = GcsimOptimizerAnytimeRaceStatus.NO_SUCCESS
                break
            if tier.iterations >= self.plan.min_saveable_iterations:
                confirmed = tuple(
                    sorted(successful_rows, key=_evaluation_rank)
                )
                break
            next_tier = self.plan.tiers[tier_index + 1]
            survivors = _select_survivors(
                successful_rows,
                limit=next_tier.max_candidates,
                minimum=next_tier.min_survivors,
                confidence_sigma=self.plan.confidence_sigma,
                relative_margin=(
                    self.plan.relative_elimination_margin
                ),
            )
            current = tuple(
                item.proposal
                for item in _retain_required_evaluations(
                    survivors,
                    successful_rows,
                    required_proposal_sha256s=(
                        self.required_proposal_sha256s
                    ),
                    limit=next_tier.max_candidates,
                )
            )
        if (
            confirmed
            and status
            not in {
                GcsimOptimizerAnytimeRaceStatus.CANCELLED,
                GcsimOptimizerAnytimeRaceStatus.DEADLINE,
            }
        ):
            rerace_tier = self.plan.tiers[3]
            rerace_candidates = _close_leaders(
                confirmed,
                limit=rerace_tier.max_candidates,
                confidence_sigma=self.plan.confidence_sigma,
                relative_margin=self.plan.relative_elimination_margin,
            )
            rerace_candidates = _retain_required_evaluations(
                rerace_candidates,
                confirmed,
                required_proposal_sha256s=(
                    self.required_proposal_sha256s
                ),
                limit=rerace_tier.max_candidates,
            )
            # Always give the leading confirmed package one long validation
            # run.  Package diversity decides which *additional* leaders are
            # worth reracing; it must not suppress final validation entirely
            # when the operation intentionally has only one package layout
            # (for example selected-set account search).
            if rerace_candidates:
                evaluations, batch_status = self._evaluate_tier(
                    tuple(item.proposal for item in rerace_candidates),
                    tier=rerace_tier,
                    deadline=deadline,
                )
                trace.extend(evaluations)
                requested[rerace_tier.tier_id] = len(evaluations)
                successful[rerace_tier.tier_id] = sum(
                    item.success for item in evaluations
                )
                cache_hits[rerace_tier.tier_id] = sum(
                    item.result.cache_hit for item in evaluations
                )
                terminal = _batch_status(batch_status)
                if terminal is None:
                    _require_successful_required_evaluations(
                        evaluations,
                        required_proposal_sha256s=(
                            self.required_proposal_sha256s
                        ),
                        tier_id=rerace_tier.tier_id,
                    )
                replacements = {
                    item.proposal.proposal_sha256: item
                    for item in evaluations
                    if item.success
                }
                confirmed = tuple(
                    sorted(
                        (
                            replacements.get(
                                item.proposal.proposal_sha256,
                                item,
                            )
                            for item in confirmed
                        ),
                        key=_evaluation_rank,
                    )
                )
                if terminal is not None:
                    status = terminal
        if (
            status is GcsimOptimizerAnytimeRaceStatus.COMPLETED
            and any(not item.success for item in trace)
        ):
            status = GcsimOptimizerAnytimeRaceStatus.COMPLETED_WITH_ERRORS
        if not confirmed and status in {
            GcsimOptimizerAnytimeRaceStatus.COMPLETED,
            GcsimOptimizerAnytimeRaceStatus.COMPLETED_WITH_ERRORS,
        }:
            status = GcsimOptimizerAnytimeRaceStatus.NO_SUCCESS
        evidence_sha256 = _canonical_sha256(
            {
                "schema_version": GCSIM_OPTIMIZER_ANYTIME_RACE_SCHEMA_VERSION,
                "run_input_sha256": self.run_input.run_input_sha256,
                "engine_binding_sha256": self.engine_context.binding_sha256,
                "plan_sha256": self.plan.identity_sha256,
                "status": status.value,
                "trace": [
                    item.evidence_sha256 for item in trace
                ],
            }
        )
        return GcsimOptimizerAnytimeRaceResult(
            status=status,
            confirmed_evaluations=confirmed,
            trace_evaluations=tuple(trace),
            requested_by_tier=tuple(sorted(requested.items())),
            successful_by_tier=tuple(sorted(successful.items())),
            cache_hits_by_tier=tuple(sorted(cache_hits.items())),
            evidence_sha256=evidence_sha256,
            elapsed_seconds=max(self.clock() - started, 0.0),
        )

    def _evaluate_tier(
        self,
        proposals: tuple[GcsimOptimizerJointProposal, ...],
        *,
        tier: GcsimOptimizerAnytimeRaceTier,
        deadline: float,
    ) -> tuple[
        tuple[GcsimOptimizerAnytimeRaceEvaluation, ...],
        GcsimFarmingBatchStatus,
    ]:
        context_sha256 = _canonical_sha256(
            {
                "schema_version": GCSIM_OPTIMIZER_ANYTIME_RACE_SCHEMA_VERSION,
                "run_input_sha256": self.run_input.run_input_sha256,
                "engine_binding_sha256": self.engine_context.binding_sha256,
                "plan_sha256": self.plan.identity_sha256,
                "tier": tier.to_dict(),
            }
        )
        (
            effective_worker_count,
            effective_parallel_candidates,
        ) = _allocate_tier_resources(
            self.plan,
            proposal_count=len(proposals),
        )
        requests = tuple(
            prepare_gcsim_optimizer_account_evaluation(
                proposal,
                engine_context=self.engine_context,
                comparison_context_sha256=context_sha256,
                investment_signature=(
                    f"account-anytime/{tier.tier_id}/{tier.iterations}"
                ),
                iterations=tier.iterations,
                worker_count=effective_worker_count,
                timeout_seconds=tier.timeout_seconds,
                environment=self.environment,
                gtt_wave_scenario_path=(
                    None
                    if self.stat_response_target is None
                    else self.stat_response_target.wave_scenario_path or None
                ),
                target_sha256=(
                    ""
                    if self.stat_response_target is None
                    else self.stat_response_target.target_sha256
                ),
            )
            for proposal in proposals
        )
        if self.progress_callback is not None:
            self.progress_callback(tier.tier_id, 0, len(requests), None)
        completed_evaluations: dict[
            int, GcsimOptimizerAnytimeRaceEvaluation
        ] = {}

        def on_completion(
            completed: int,
            planned: int,
            index: int,
            result: GcsimFarmingEvaluationResult,
        ) -> None:
            evaluation = GcsimOptimizerAnytimeRaceEvaluation(
                tier_id=tier.tier_id,
                proposal=proposals[index],
                result=result,
            )
            completed_evaluations[index] = evaluation
            if self.progress_callback is None:
                return
            successful_rows = tuple(
                item
                for item in completed_evaluations.values()
                if item.success
            )
            leader = (
                min(successful_rows, key=_evaluation_rank)
                if successful_rows
                else None
            )
            self.progress_callback(
                tier.tier_id,
                completed,
                planned,
                leader,
            )

        remaining = max(deadline - self.clock(), 1e-6)
        scheduler = GcsimFarmingEvaluationScheduler(
            requests,
            GcsimFarmingSchedulerBudget(
                max_parallel_candidates=effective_parallel_candidates,
                total_cpu_budget=self.plan.total_cpu_budget,
                overall_deadline_seconds=remaining,
            ),
            cache_store=self.cache_store,
            enable_cache=self.enable_cache,
            session_factory=self.session_factory,
            completion_callback=on_completion,
        )
        with self._lock:
            self._active_scheduler = scheduler
        if self._cancel_event.is_set():
            scheduler.cancel()
        try:
            batch = scheduler.run()
        finally:
            with self._lock:
                if self._active_scheduler is scheduler:
                    self._active_scheduler = None
        evaluations = tuple(
            GcsimOptimizerAnytimeRaceEvaluation(
                tier_id=tier.tier_id,
                proposal=proposal,
                result=result,
            )
            for proposal, result in zip(
                proposals,
                batch.results,
                strict=True,
            )
        )
        return evaluations, batch.status

    def _terminal_status(
        self,
        deadline: float,
    ) -> GcsimOptimizerAnytimeRaceStatus | None:
        if self._cancel_event.is_set():
            return GcsimOptimizerAnytimeRaceStatus.CANCELLED
        if self.clock() >= deadline:
            return GcsimOptimizerAnytimeRaceStatus.DEADLINE
        return None


def _select_survivors(
    rows: Sequence[GcsimOptimizerAnytimeRaceEvaluation],
    *,
    limit: int,
    minimum: int,
    confidence_sigma: float,
    relative_margin: float,
) -> tuple[GcsimOptimizerAnytimeRaceEvaluation, ...]:
    ranked = tuple(sorted(rows, key=_evaluation_rank))
    leader = ranked[0]
    assert leader.dps_mean is not None
    leader_lower = _lower(leader, confidence_sigma)
    retained = []
    for row in ranked:
        assert row.dps_mean is not None
        # No SE means "unknown", not "bad": do not statistically eliminate it.
        if row.dps_se is None or leader.dps_se is None:
            retained.append(row)
            continue
        optimistic = _upper(row, confidence_sigma)
        margin = abs(leader.dps_mean) * relative_margin
        if optimistic + margin >= leader_lower:
            retained.append(row)
    for row in ranked:
        if len(retained) >= minimum:
            break
        if row not in retained:
            retained.append(row)
    retained = _retain_evaluation_diversity(retained, ranked, limit=limit)
    return tuple(sorted(retained, key=_evaluation_rank))


def _allocate_tier_resources(
    plan: GcsimOptimizerAnytimeRacePlan,
    *,
    proposal_count: int,
) -> tuple[int, int]:
    """Return one deterministic worker width and bounded parallel fan-out."""

    if (
        isinstance(proposal_count, bool)
        or not isinstance(proposal_count, int)
        or proposal_count <= 0
    ):
        raise GcsimOptimizerAnytimeRaceError(
            "proposal_count must be a positive integer"
        )
    parallel_slots = min(
        proposal_count,
        plan.max_parallel_candidates,
    )
    worker_count = min(
        max(
            plan.worker_count,
            plan.total_cpu_budget // parallel_slots,
        ),
        plan.total_cpu_budget,
    )
    parallel_candidates = min(
        proposal_count,
        plan.max_parallel_candidates,
        max(1, plan.total_cpu_budget // worker_count),
    )
    return worker_count, parallel_candidates


def _retain_required_evaluations(
    preferred: Sequence[GcsimOptimizerAnytimeRaceEvaluation],
    available: Sequence[GcsimOptimizerAnytimeRaceEvaluation],
    *,
    required_proposal_sha256s: Sequence[str],
    limit: int,
) -> tuple[GcsimOptimizerAnytimeRaceEvaluation, ...]:
    """Reserve exact reference candidates before filling a tier budget."""

    required_ids = tuple(required_proposal_sha256s)
    available_by_id = {
        row.proposal.proposal_sha256: row for row in available
    }
    try:
        required = tuple(
            available_by_id[proposal_sha256]
            for proposal_sha256 in required_ids
        )
    except KeyError as exc:
        raise GcsimOptimizerAnytimeRaceError(
            "required proposal disappeared before tier promotion"
        ) from exc
    selected = list(required)
    selected_ids = set(required_ids)
    if len(selected) >= limit:
        return tuple(sorted(selected[:limit], key=_evaluation_rank))
    for row in (
        *tuple(preferred),
        *tuple(sorted(available, key=_evaluation_rank)),
    ):
        proposal_sha256 = row.proposal.proposal_sha256
        if proposal_sha256 in selected_ids:
            continue
        selected.append(row)
        selected_ids.add(proposal_sha256)
        if len(selected) >= limit:
            break
    return tuple(sorted(selected[:limit], key=_evaluation_rank))


def _require_successful_required_evaluations(
    evaluations: Sequence[GcsimOptimizerAnytimeRaceEvaluation],
    *,
    required_proposal_sha256s: Sequence[str],
    tier_id: str,
) -> None:
    if not required_proposal_sha256s:
        return
    by_id = {
        row.proposal.proposal_sha256: row for row in evaluations
    }
    missing = tuple(
        proposal_sha256
        for proposal_sha256 in required_proposal_sha256s
        if proposal_sha256 not in by_id
    )
    failed = tuple(
        proposal_sha256
        for proposal_sha256 in required_proposal_sha256s
        if proposal_sha256 in by_id and not by_id[proposal_sha256].success
    )
    if missing or failed:
        raise GcsimOptimizerAnytimeRaceError(
            f"required proposal was not successfully evaluated at {tier_id}"
        )


def _close_leaders(
    rows: Sequence[GcsimOptimizerAnytimeRaceEvaluation],
    *,
    limit: int,
    confidence_sigma: float,
    relative_margin: float,
) -> tuple[GcsimOptimizerAnytimeRaceEvaluation, ...]:
    ranked = tuple(sorted(rows, key=_evaluation_rank))
    if not ranked:
        return ()
    leader = ranked[0]
    assert leader.dps_mean is not None
    close = [leader]
    for row in ranked[1:]:
        assert row.dps_mean is not None
        if leader.dps_se is None or row.dps_se is None:
            close.append(row)
        else:
            combined = sqrt(leader.dps_se**2 + row.dps_se**2)
            allowed = (
                confidence_sigma * combined
                + abs(leader.dps_mean) * relative_margin
            )
            if leader.dps_mean - row.dps_mean <= allowed:
                close.append(row)
    diverse = _retain_best_per_package_signature(close, limit=limit)
    return tuple(diverse)


def _retain_evaluation_diversity(
    retained: Sequence[GcsimOptimizerAnytimeRaceEvaluation],
    ranked: Sequence[GcsimOptimizerAnytimeRaceEvaluation],
    *,
    limit: int,
) -> list[GcsimOptimizerAnytimeRaceEvaluation]:
    retained_ordered = tuple(sorted(retained, key=_evaluation_rank))
    ranked_ordered = tuple(sorted(ranked, key=_evaluation_rank))
    selected: list[GcsimOptimizerAnytimeRaceEvaluation] = []
    selected_ids: set[str] = set()
    package_signatures: set[tuple[str, ...]] = set()

    def add(row: GcsimOptimizerAnytimeRaceEvaluation) -> bool:
        identity = row.proposal.proposal_sha256
        if identity in selected_ids:
            return False
        selected.append(row)
        selected_ids.add(identity)
        return True

    # First preserve the best statistically retained row for each ordered
    # four-wearer package combination.  Physical variants of the same package
    # combination must not consume the whole survivor budget.
    for row in retained_ordered:
        signature = _proposal_package_signature(row.proposal)
        if signature in package_signatures:
            continue
        package_signatures.add(signature)
        add(row)
        if len(selected) >= limit:
            return selected

    # If statistical retention produced fewer package families than the
    # available budget, restore the best screened row from missing families.
    # This is the account-search diversity floor; exact later tiers still rank
    # every retained family by measured team DPS.
    for row in ranked_ordered:
        signature = _proposal_package_signature(row.proposal)
        if signature in package_signatures:
            continue
        package_signatures.add(signature)
        add(row)
        if len(selected) >= limit:
            return selected

    labels = {
        label
        for row in selected
        for label in row.proposal.diversity_labels
    }
    # The former implementation pre-filled ``selected`` to ``limit`` before
    # this loop, so feature diversity could never replace a duplicate.  Run it
    # only after package coverage, while budget remains.
    for row in (*retained_ordered, *ranked_ordered):
        if len(selected) >= limit:
            break
        if row.proposal.proposal_sha256 in selected_ids:
            continue
        if any(
            label not in labels for label in row.proposal.diversity_labels
        ):
            add(row)
            labels.update(row.proposal.diversity_labels)
    for row in (*retained_ordered, *ranked_ordered):
        if len(selected) >= limit:
            break
        add(row)
    return selected


def _retain_proposal_diversity(
    rows: Sequence[GcsimOptimizerJointProposal],
    *,
    limit: int,
) -> tuple[GcsimOptimizerJointProposal, ...]:
    ordered = tuple(
        sorted(
            rows,
            key=lambda item: (
                -float(item.surrogate_score),
                item.proposal_sha256,
            ),
        )
    )
    if len(ordered) <= limit:
        return ordered
    selected: list[GcsimOptimizerJointProposal] = []
    selected_ids: set[str] = set()
    package_signatures: set[tuple[str, ...]] = set()
    labels: set[str] = set()

    for row in ordered:
        signature = _proposal_package_signature(row)
        if signature in package_signatures:
            continue
        package_signatures.add(signature)
        selected.append(row)
        selected_ids.add(row.proposal_sha256)
        labels.update(row.diversity_labels)
        if len(selected) >= limit:
            return tuple(selected)

    for row in ordered:
        if row.proposal_sha256 in selected_ids:
            continue
        if any(
            label not in labels for label in row.diversity_labels
        ):
            selected.append(row)
            selected_ids.add(row.proposal_sha256)
            labels.update(row.diversity_labels)
        if len(selected) >= limit:
            return tuple(selected)
    for row in ordered:
        if row.proposal_sha256 not in selected_ids:
            selected.append(row)
            selected_ids.add(row.proposal_sha256)
        if len(selected) >= limit:
            break
    return tuple(selected)


def _retain_required_proposals(
    rows: Sequence[GcsimOptimizerJointProposal],
    *,
    required_proposal_sha256s: Sequence[str],
    limit: int,
) -> tuple[GcsimOptimizerJointProposal, ...]:
    """Keep required anchors even when their surrogate rank is weak."""

    required_ids = tuple(required_proposal_sha256s)
    by_id = {row.proposal_sha256: row for row in rows}
    required = tuple(by_id[proposal_sha256] for proposal_sha256 in required_ids)
    required_id_set = set(required_ids)
    optional = tuple(
        row for row in rows if row.proposal_sha256 not in required_id_set
    )
    optional_limit = max(limit - len(required), 0)
    selected = (
        *required,
        *(
            _retain_proposal_diversity(optional, limit=optional_limit)
            if optional_limit
            else ()
        ),
    )
    return tuple(
        sorted(
            selected,
            key=lambda item: (
                -float(item.surrogate_score),
                item.proposal_sha256,
            ),
        )
    )


def build_gcsim_optimizer_account_package_signature(
    targets: Sequence[GcsimOptimizerWearerTarget],
) -> tuple[str, ...]:
    """Return the ordered four-wearer package identity for account ranking."""

    rows = tuple(targets)
    if (
        len(rows) != 4
        or any(
            not isinstance(item, GcsimOptimizerWearerTarget)
            for item in rows
        )
        or tuple(item.wearer.team_slot for item in rows) != (1, 2, 3, 4)
    ):
        raise GcsimOptimizerAnytimeRaceError(
            "account package signature requires canonical wearer slots 1..4"
        )
    return tuple(item.package.identity_sha256 for item in rows)


def _proposal_package_signature(
    proposal: GcsimOptimizerJointProposal,
) -> tuple[str, ...]:
    return build_gcsim_optimizer_account_package_signature(
        proposal.compiled_candidate.targets
    )


def _retain_best_per_package_signature(
    rows: Sequence[GcsimOptimizerAnytimeRaceEvaluation],
    *,
    limit: int,
) -> list[GcsimOptimizerAnytimeRaceEvaluation]:
    selected: list[GcsimOptimizerAnytimeRaceEvaluation] = []
    signatures: set[tuple[str, ...]] = set()
    for row in sorted(rows, key=_evaluation_rank):
        signature = _proposal_package_signature(row.proposal)
        if signature in signatures:
            continue
        signatures.add(signature)
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def _evaluation_rank(
    row: GcsimOptimizerAnytimeRaceEvaluation,
) -> tuple[float, str]:
    return (
        -float(row.dps_mean) if row.dps_mean is not None else float("inf"),
        row.proposal.proposal_sha256,
    )


def _lower(
    row: GcsimOptimizerAnytimeRaceEvaluation,
    sigma: float,
) -> float:
    assert row.dps_mean is not None
    return (
        row.dps_mean
        if row.dps_se is None
        else row.dps_mean - sigma * row.dps_se
    )


def _upper(
    row: GcsimOptimizerAnytimeRaceEvaluation,
    sigma: float,
) -> float:
    assert row.dps_mean is not None
    return (
        row.dps_mean
        if row.dps_se is None
        else row.dps_mean + sigma * row.dps_se
    )


def _batch_status(
    status: GcsimFarmingBatchStatus,
) -> GcsimOptimizerAnytimeRaceStatus | None:
    if status is GcsimFarmingBatchStatus.CANCELLED:
        return GcsimOptimizerAnytimeRaceStatus.CANCELLED
    if status is GcsimFarmingBatchStatus.DEADLINE_REACHED:
        return GcsimOptimizerAnytimeRaceStatus.DEADLINE
    return None


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_schema(value: int) -> None:
    if value != GCSIM_OPTIMIZER_ANYTIME_RACE_SCHEMA_VERSION:
        raise GcsimOptimizerAnytimeRaceError(
            "unsupported anytime race schema"
        )


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise GcsimOptimizerAnytimeRaceError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


__all__ = [
    "GCSIM_OPTIMIZER_ANYTIME_RACE_PLAN_ID",
    "GCSIM_OPTIMIZER_ANYTIME_RACE_PLAN_VERSION",
    "GCSIM_OPTIMIZER_ANYTIME_RACE_SCHEMA_VERSION",
    "GcsimOptimizerAnytimeRaceError",
    "GcsimOptimizerAnytimeRaceEvaluation",
    "GcsimOptimizerAnytimeRacePlan",
    "GcsimOptimizerAnytimeRaceResult",
    "GcsimOptimizerAnytimeRaceSession",
    "GcsimOptimizerAnytimeRaceStatus",
    "GcsimOptimizerAnytimeRaceTier",
    "build_gcsim_optimizer_account_package_signature",
]
