"""Iterative whole-team GCSIM feedback for optimizer Milestone 7.

Milestone 6 proposals are screening inputs, never final DPS claims.  This
module deduplicates exact compiled configs, evaluates them through the existing
ordinary-GCSIM scheduler/cache, requests typed enrichment, and gives every
displayed row common high-fidelity evidence before optional close-leader
reraces.
"""

from __future__ import annotations

from collections import Counter
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
    CandidateKey,
    GcsimFarmingBatchResult,
    GcsimFarmingBatchStatus,
    GcsimFarmingEvaluationRequest,
    GcsimFarmingEvaluationResult,
    GcsimFarmingEvaluationScheduler,
    GcsimFarmingSchedulerBudget,
    freeze_gcsim_farming_environment,
)
from .farming_profile_config import apply_gcsim_screening_runtime_options
from .optimizer_cache import GcsimOptimizerCacheStore
from .optimizer_config import (
    GcsimFiveStarMainStatLayout,
)
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_joint_proposals import (
    GcsimOptimizerJointProposal,
    GcsimOptimizerJointScoreAdjustment,
)
from .optimizer_main_response import gcsim_optimizer_main_layout_id
from .optimizer_product_contracts import (
    GcsimOptimizerUncertainty,
    GcsimOptimizerUncertaintyLabel,
)
from .optimizer_run_input import GcsimOptimizerRunInput
from .optimizer_stat_constraints import (
    evaluate_gcsim_optimizer_minimum_stat_constraints,
)


GCSIM_OPTIMIZER_FEEDBACK_SCHEMA_VERSION = 1


class GcsimOptimizerFeedbackError(RuntimeError):
    """Fail-closed M7 orchestration or provenance violation."""


class GcsimOptimizerFeedbackStage(str, Enum):
    SCREENING = "screening"
    FINALIST = "finalist"
    RERACE = "rerace"


class GcsimOptimizerFeedbackStopReason(str, Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    WORK_PLAN_EXHAUSTED = "work_plan_exhausted"
    NO_SUCCESS = "no_success"
    CANCELLED = "cancelled"
    DEADLINE_REACHED = "deadline_reached"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerFeedbackFidelity:
    iterations: int
    worker_count: int
    timeout_seconds: float
    schema_version: int = GCSIM_OPTIMIZER_FEEDBACK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in ("iterations", "worker_count"):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise GcsimOptimizerFeedbackError(
                    f"{field_name} must be a positive integer"
                )
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise GcsimOptimizerFeedbackError(
                "timeout_seconds must be finite and positive"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "iterations": self.iterations,
            "worker_count": self.worker_count,
            "timeout_seconds": float(self.timeout_seconds),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerFeedbackPlan:
    screening: GcsimOptimizerFeedbackFidelity = field(
        default_factory=lambda: GcsimOptimizerFeedbackFidelity(20, 1, 60.0)
    )
    finalist: GcsimOptimizerFeedbackFidelity = field(
        default_factory=lambda: GcsimOptimizerFeedbackFidelity(200, 1, 120.0)
    )
    rerace: GcsimOptimizerFeedbackFidelity = field(
        default_factory=lambda: GcsimOptimizerFeedbackFidelity(1000, 1, 180.0)
    )
    max_feedback_rounds: int = 4
    max_screening_per_round: int = 32
    max_finalists: int = 6
    max_trace_evaluations: int = 128
    confidence_sigma: float = 2.0
    max_parallel_candidates: int = 1
    total_cpu_budget: int = 1
    overall_deadline_seconds: float = 900.0
    schema_version: int = GCSIM_OPTIMIZER_FEEDBACK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in ("screening", "finalist", "rerace"):
            if not isinstance(
                getattr(self, field_name),
                GcsimOptimizerFeedbackFidelity,
            ):
                raise GcsimOptimizerFeedbackError(
                    f"{field_name} fidelity must be typed"
                )
        if self.finalist.iterations <= self.screening.iterations:
            raise GcsimOptimizerFeedbackError(
                "finalist fidelity must exceed screening iterations"
            )
        if self.rerace.iterations < self.finalist.iterations:
            raise GcsimOptimizerFeedbackError(
                "rerace fidelity cannot be below finalist iterations"
            )
        for field_name in (
            "max_feedback_rounds",
            "max_screening_per_round",
            "max_trace_evaluations",
            "max_parallel_candidates",
            "total_cpu_budget",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise GcsimOptimizerFeedbackError(
                    f"{field_name} must be a positive integer"
                )
        if (
            isinstance(self.max_finalists, bool)
            or not isinstance(self.max_finalists, int)
            or self.max_finalists < 2
        ):
            raise GcsimOptimizerFeedbackError(
                "max_finalists must be an integer of at least two"
            )
        logical_cpus = os.cpu_count() or 1
        if self.total_cpu_budget > logical_cpus:
            raise GcsimOptimizerFeedbackError(
                "total_cpu_budget exceeds detected logical CPUs"
            )
        if (
            isinstance(self.confidence_sigma, bool)
            or not isinstance(self.confidence_sigma, (int, float))
            or not isfinite(self.confidence_sigma)
            or self.confidence_sigma <= 0
        ):
            raise GcsimOptimizerFeedbackError(
                "confidence_sigma must be finite and positive"
            )
        if (
            isinstance(self.overall_deadline_seconds, bool)
            or not isinstance(self.overall_deadline_seconds, (int, float))
            or not isfinite(self.overall_deadline_seconds)
            or self.overall_deadline_seconds <= 0
        ):
            raise GcsimOptimizerFeedbackError(
                "overall_deadline_seconds must be finite and positive"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "screening": self.screening.to_dict(),
            "finalist": self.finalist.to_dict(),
            "rerace": self.rerace.to_dict(),
            "max_feedback_rounds": self.max_feedback_rounds,
            "max_screening_per_round": self.max_screening_per_round,
            "max_finalists": self.max_finalists,
            "max_trace_evaluations": self.max_trace_evaluations,
            "confidence_sigma": float(self.confidence_sigma),
            "max_parallel_candidates": self.max_parallel_candidates,
            "total_cpu_budget": self.total_cpu_budget,
            "overall_deadline_seconds": float(
                self.overall_deadline_seconds
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerFeedbackEvaluation:
    stage: GcsimOptimizerFeedbackStage
    proposal: GcsimOptimizerJointProposal
    replacement_proposal_sha256s: tuple[str, ...]
    equivalent_assignment_count: int
    request_identity_sha256: str
    simulation_sha256: str
    success: bool
    status: str
    iterations: int
    dps_mean: float | None
    dps_standard_error: float | None
    cache_hit: bool
    evidence_sha256: str
    feature_labels: tuple[str, ...]
    error: str = ""
    schema_version: int = GCSIM_OPTIMIZER_FEEDBACK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.stage, GcsimOptimizerFeedbackStage):
            raise GcsimOptimizerFeedbackError(
                "feedback evaluation stage must be typed"
            )
        if not isinstance(self.proposal, GcsimOptimizerJointProposal):
            raise GcsimOptimizerFeedbackError(
                "feedback evaluation proposal must be typed"
            )
        _require_sha256(
            self.request_identity_sha256,
            "request_identity_sha256",
        )
        _require_sha256(self.simulation_sha256, "simulation_sha256")
        _require_sha256(self.evidence_sha256, "evidence_sha256")
        replacements = tuple(
            sorted(set(self.replacement_proposal_sha256s))
        )
        for replacement_sha256 in replacements:
            _require_sha256(
                replacement_sha256,
                "replacement_proposal_sha256",
            )
        if self.proposal.proposal_sha256 in replacements:
            raise GcsimOptimizerFeedbackError(
                "primary proposal cannot also be its own replacement"
            )
        if self.equivalent_assignment_count != (
            1 + len(replacements)
        ):
            raise GcsimOptimizerFeedbackError(
                "equivalent assignment count differs from retained proposals"
            )
        if (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations <= 0
        ):
            raise GcsimOptimizerFeedbackError(
                "feedback iterations must be positive"
            )
        if self.success:
            if (
                self.dps_mean is None
                or not isfinite(self.dps_mean)
                or self.dps_mean < 0
            ):
                raise GcsimOptimizerFeedbackError(
                    "successful feedback requires finite non-negative DPS"
                )
            if self.error:
                raise GcsimOptimizerFeedbackError(
                    "successful feedback cannot carry an error"
                )
        elif self.dps_mean is not None or self.dps_standard_error is not None:
            raise GcsimOptimizerFeedbackError(
                "failed feedback cannot carry numeric evidence"
            )
        if self.dps_standard_error is not None and (
            not isfinite(self.dps_standard_error)
            or self.dps_standard_error < 0
        ):
            raise GcsimOptimizerFeedbackError(
                "feedback standard error must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "replacement_proposal_sha256s",
            replacements,
        )
        object.__setattr__(
            self,
            "feature_labels",
            tuple(sorted(set(self.feature_labels))),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "stage": self.stage.value,
            "proposal_sha256": self.proposal.proposal_sha256,
            "replacement_proposal_sha256s": list(
                self.replacement_proposal_sha256s
            ),
            "equivalent_assignment_count": self.equivalent_assignment_count,
            "request_identity_sha256": self.request_identity_sha256,
            "simulation_sha256": self.simulation_sha256,
            "success": self.success,
            "status": self.status,
            "iterations": self.iterations,
            "dps_mean": self.dps_mean,
            "dps_standard_error": self.dps_standard_error,
            "cache_hit": self.cache_hit,
            "evidence_sha256": self.evidence_sha256,
            "feature_labels": list(self.feature_labels),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerFeedbackEnrichmentRequest:
    round_index: int
    screening_evaluations: tuple[GcsimOptimizerFeedbackEvaluation, ...]
    current_leader: GcsimOptimizerFeedbackEvaluation | None
    required_branch_labels: tuple[str, ...]
    remaining_seconds: float
    schema_version: int = GCSIM_OPTIMIZER_FEEDBACK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if (
            isinstance(self.round_index, bool)
            or not isinstance(self.round_index, int)
            or self.round_index < 0
        ):
            raise GcsimOptimizerFeedbackError(
                "enrichment round_index must be non-negative"
            )
        if (
            not isfinite(self.remaining_seconds)
            or self.remaining_seconds < 0
        ):
            raise GcsimOptimizerFeedbackError(
                "remaining_seconds must be finite and non-negative"
            )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerFeedbackEnrichmentResponse:
    proposals: tuple[GcsimOptimizerJointProposal, ...] = ()
    score_adjustments: tuple[GcsimOptimizerJointScoreAdjustment, ...] = ()
    trace_notes: tuple[str, ...] = ()
    schema_version: int = GCSIM_OPTIMIZER_FEEDBACK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if any(
            not isinstance(item, GcsimOptimizerJointProposal)
            for item in self.proposals
        ):
            raise GcsimOptimizerFeedbackError(
                "enrichment proposals must be typed"
            )
        if any(
            not isinstance(item, GcsimOptimizerJointScoreAdjustment)
            for item in self.score_adjustments
        ):
            raise GcsimOptimizerFeedbackError(
                "enrichment score adjustments must be typed"
            )
        if any(
            not isinstance(item, str)
            or not item
            or item != item.strip()
            for item in self.trace_notes
        ):
            raise GcsimOptimizerFeedbackError(
                "enrichment trace notes must be trimmed text"
            )


FeedbackEnricher = Callable[
    [GcsimOptimizerFeedbackEnrichmentRequest],
    GcsimOptimizerFeedbackEnrichmentResponse,
]


@dataclass(frozen=True, slots=True)
class GcsimOptimizerFeedbackFinalist:
    rank: int
    proposal: GcsimOptimizerJointProposal
    replacement_proposal_sha256s: tuple[str, ...]
    equivalent_assignment_count: int
    screening_evaluation: GcsimOptimizerFeedbackEvaluation
    final_evaluation: GcsimOptimizerFeedbackEvaluation
    uncertainty: GcsimOptimizerUncertainty
    evidence_stage: GcsimOptimizerFeedbackStage
    feature_labels: tuple[str, ...]
    schema_version: int = GCSIM_OPTIMIZER_FEEDBACK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if (
            isinstance(self.rank, bool)
            or not isinstance(self.rank, int)
            or self.rank <= 0
        ):
            raise GcsimOptimizerFeedbackError(
                "finalist rank must be positive"
            )
        if not self.final_evaluation.success:
            raise GcsimOptimizerFeedbackError(
                "displayed finalist requires successful high-fidelity evidence"
            )
        if self.evidence_stage not in {
            GcsimOptimizerFeedbackStage.FINALIST,
            GcsimOptimizerFeedbackStage.RERACE,
        }:
            raise GcsimOptimizerFeedbackError(
                "displayed finalist cannot use screening evidence"
            )
        if self.final_evaluation.stage is not self.evidence_stage:
            raise GcsimOptimizerFeedbackError(
                "finalist evidence stage is incoherent"
            )

    @property
    def absolute_dps(self) -> float:
        assert self.final_evaluation.dps_mean is not None
        return self.final_evaluation.dps_mean

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "rank": self.rank,
            "proposal_sha256": self.proposal.proposal_sha256,
            "replacement_proposal_sha256s": list(
                self.replacement_proposal_sha256s
            ),
            "equivalent_assignment_count": self.equivalent_assignment_count,
            "absolute_dps": self.absolute_dps,
            "dps_standard_error": (
                self.final_evaluation.dps_standard_error
            ),
            "iterations": self.final_evaluation.iterations,
            "uncertainty": self.uncertainty.to_dict(),
            "evidence_stage": self.evidence_stage.value,
            "feature_labels": list(self.feature_labels),
            "account_assignment": (
                self.proposal.compiled_candidate.assignment_witness.to_dict()
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerFeedbackCoverage:
    initial_proposal_count: int
    enriched_proposal_count: int
    unique_compiled_config_count: int
    equivalent_assignment_count: int
    requested_by_stage: tuple[tuple[str, int], ...]
    successful_by_stage: tuple[tuple[str, int], ...]
    failed_by_stage: tuple[tuple[str, int], ...]
    cache_hits_by_stage: tuple[tuple[str, int], ...]
    enrichment_call_count: int
    em_safeguard_finalist_count: int
    reraced_finalist_count: int
    schema_version: int = GCSIM_OPTIMIZER_FEEDBACK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in (
            "initial_proposal_count",
            "enriched_proposal_count",
            "unique_compiled_config_count",
            "equivalent_assignment_count",
            "enrichment_call_count",
            "em_safeguard_finalist_count",
            "reraced_finalist_count",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise GcsimOptimizerFeedbackError(
                    f"{field_name} must be non-negative"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "initial_proposal_count": self.initial_proposal_count,
            "enriched_proposal_count": self.enriched_proposal_count,
            "unique_compiled_config_count": (
                self.unique_compiled_config_count
            ),
            "equivalent_assignment_count": self.equivalent_assignment_count,
            "requested_by_stage": dict(self.requested_by_stage),
            "successful_by_stage": dict(self.successful_by_stage),
            "failed_by_stage": dict(self.failed_by_stage),
            "cache_hits_by_stage": dict(self.cache_hits_by_stage),
            "enrichment_call_count": self.enrichment_call_count,
            "em_safeguard_finalist_count": (
                self.em_safeguard_finalist_count
            ),
            "reraced_finalist_count": self.reraced_finalist_count,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerFeedbackResult:
    status: GcsimOptimizerFeedbackStopReason
    stop_reason: GcsimOptimizerFeedbackStopReason
    run_input_sha256: str
    engine_binding_sha256: str
    plan: GcsimOptimizerFeedbackPlan
    finalists: tuple[GcsimOptimizerFeedbackFinalist, ...]
    trace_evaluations: tuple[GcsimOptimizerFeedbackEvaluation, ...]
    enrichment_trace_notes: tuple[str, ...]
    score_adjustments: tuple[GcsimOptimizerJointScoreAdjustment, ...]
    coverage: GcsimOptimizerFeedbackCoverage
    elapsed_seconds: float
    schema_version: int = GCSIM_OPTIMIZER_FEEDBACK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if self.status is not self.stop_reason:
            raise GcsimOptimizerFeedbackError(
                "feedback status and stop_reason must match"
            )
        _require_sha256(self.run_input_sha256, "run_input_sha256")
        _require_sha256(
            self.engine_binding_sha256,
            "engine_binding_sha256",
        )
        finalists = tuple(self.finalists)
        if tuple(item.rank for item in finalists) != tuple(
            range(1, len(finalists) + 1)
        ):
            raise GcsimOptimizerFeedbackError(
                "finalists must use contiguous rank order"
            )
        if finalists != tuple(
            sorted(
                finalists,
                key=lambda item: (
                    -item.absolute_dps,
                    item.proposal.proposal_sha256,
                ),
            )
        ):
            raise GcsimOptimizerFeedbackError(
                "finalists must use absolute-DPS order"
            )
        if self.status is GcsimOptimizerFeedbackStopReason.NO_SUCCESS:
            if finalists:
                raise GcsimOptimizerFeedbackError(
                    "no_success cannot carry finalists"
                )
        elif self.status in {
            GcsimOptimizerFeedbackStopReason.COMPLETED,
            GcsimOptimizerFeedbackStopReason.COMPLETED_WITH_ERRORS,
            GcsimOptimizerFeedbackStopReason.WORK_PLAN_EXHAUSTED,
        } and not finalists:
            raise GcsimOptimizerFeedbackError(
                "successful feedback status requires finalists"
            )
        if (
            not isfinite(self.elapsed_seconds)
            or self.elapsed_seconds < 0
        ):
            raise GcsimOptimizerFeedbackError(
                "elapsed_seconds must be finite and non-negative"
            )
        object.__setattr__(self, "finalists", finalists)

    @property
    def semantic_signature(self) -> tuple[
        tuple[str, float, float | None, int, str], ...
    ]:
        return tuple(
            (
                item.final_evaluation.simulation_sha256,
                item.absolute_dps,
                item.final_evaluation.dps_standard_error,
                item.final_evaluation.iterations,
                item.uncertainty.label.value,
            )
            for item in self.finalists
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "stop_reason": self.stop_reason.value,
            "run_input_sha256": self.run_input_sha256,
            "engine_binding_sha256": self.engine_binding_sha256,
            "plan": self.plan.to_dict(),
            "finalists": [item.to_dict() for item in self.finalists],
            "trace_evaluations": [
                item.to_dict() for item in self.trace_evaluations
            ],
            "enrichment_trace_notes": list(self.enrichment_trace_notes),
            "score_adjustments": [
                item.to_dict() for item in self.score_adjustments
            ],
            "coverage": self.coverage.to_dict(),
            "elapsed_seconds": self.elapsed_seconds,
        }


class GcsimOptimizerFeedbackSession:
    """One-shot cancellable owner of the M7 feedback loop and active batch."""

    def __init__(
        self,
        run_input: GcsimOptimizerRunInput,
        *,
        engine_context: GcsimOptimizerEngineContext,
        proposals: Sequence[GcsimOptimizerJointProposal],
        plan: GcsimOptimizerFeedbackPlan | None = None,
        enricher: FeedbackEnricher | None = None,
        cache_store: GcsimOptimizerCacheStore | None = None,
        enable_cache: bool = True,
        session_factory: Callable[[GcsimFarmingEvaluationRequest], object]
        | None = None,
        environment: Mapping[str, str] | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.run_input = run_input
        self.engine_context = engine_context
        self.proposals = tuple(proposals)
        self.plan = plan or GcsimOptimizerFeedbackPlan()
        self.enricher = enricher
        self.cache_store = cache_store
        self.enable_cache = enable_cache
        self.session_factory = session_factory
        self.environment = dict(environment or {})
        self.clock = clock
        self._cancel_event = Event()
        self._lock = Lock()
        self._active_scheduler: GcsimFarmingEvaluationScheduler | None = None
        self._started = False
        _validate_session_inputs(self)

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            scheduler = self._active_scheduler
        if scheduler is not None:
            scheduler.cancel()

    def run(self) -> GcsimOptimizerFeedbackResult:
        with self._lock:
            if self._started:
                raise GcsimOptimizerFeedbackError(
                    "feedback session is one-shot"
                )
            self._started = True
        return self._run()

    def _run(self) -> GcsimOptimizerFeedbackResult:
        started = self.clock()
        deadline = started + self.plan.overall_deadline_seconds
        seen = {
            proposal.proposal_sha256: proposal
            for proposal in self.proposals
        }
        pending = list(self.proposals)
        screened_by_simulation: dict[
            str,
            GcsimOptimizerFeedbackEvaluation,
        ] = {}
        all_evaluations: list[GcsimOptimizerFeedbackEvaluation] = []
        trace_notes: list[str] = []
        adjustments: dict[
            tuple[object, str],
            GcsimOptimizerJointScoreAdjustment,
        ] = {}
        counters = _FeedbackCounters(
            initial_proposal_count=len(self.proposals)
        )
        status = GcsimOptimizerFeedbackStopReason.COMPLETED

        for round_index in range(self.plan.max_feedback_rounds):
            terminal = self._terminal_reason(deadline)
            if terminal is not None:
                status = terminal
                break
            batch_proposals = tuple(
                pending[: self.plan.max_screening_per_round]
            )
            del pending[: len(batch_proposals)]
            if batch_proposals:
                evaluations, batch_status = self._evaluate(
                    batch_proposals,
                    stage=GcsimOptimizerFeedbackStage.SCREENING,
                    fidelity=self.plan.screening,
                    deadline=deadline,
                    counters=counters,
                )
                all_evaluations.extend(evaluations)
                for evaluation in evaluations:
                    if evaluation.success:
                        screened_by_simulation[
                            evaluation.simulation_sha256
                        ] = evaluation
                terminal = _batch_terminal_reason(batch_status)
                if terminal is not None:
                    status = terminal
                    break
            leader = _best_evaluation(
                tuple(screened_by_simulation.values())
            )
            if self.enricher is not None:
                counters.enrichment_call_count += 1
                response = self.enricher(
                    GcsimOptimizerFeedbackEnrichmentRequest(
                        round_index=round_index,
                        screening_evaluations=tuple(
                            sorted(
                                screened_by_simulation.values(),
                                key=_evaluation_rank,
                            )
                        ),
                        current_leader=leader,
                        required_branch_labels=(
                            "em_response",
                            "threshold:*",
                            "unusual_main",
                        ),
                        remaining_seconds=max(
                            deadline - self.clock(),
                            0.0,
                        ),
                    )
                )
                if not isinstance(
                    response,
                    GcsimOptimizerFeedbackEnrichmentResponse,
                ):
                    raise GcsimOptimizerFeedbackError(
                        "enricher must return a typed response"
                    )
                for proposal in response.proposals:
                    _validate_proposal_for_run(
                        self.run_input,
                        proposal,
                    )
                    if not _proposal_meets_minimum_stat_constraints(
                        self.run_input,
                        proposal,
                    ):
                        continue
                    if proposal.proposal_sha256 not in seen:
                        seen[proposal.proposal_sha256] = proposal
                        pending.append(proposal)
                        counters.enriched_proposal_count += 1
                for adjustment in response.score_adjustments:
                    adjustments[
                        (adjustment.wearer, adjustment.candidate_sha256)
                    ] = adjustment
                trace_notes.extend(response.trace_notes)
            if not pending:
                break
        else:
            if pending:
                status = (
                    GcsimOptimizerFeedbackStopReason.WORK_PLAN_EXHAUSTED
                )

        if status not in {
            GcsimOptimizerFeedbackStopReason.CANCELLED,
            GcsimOptimizerFeedbackStopReason.DEADLINE_REACHED,
        }:
            successful_screening = tuple(
                sorted(
                    screened_by_simulation.values(),
                    key=_evaluation_rank,
                )
            )
            if not successful_screening:
                status = GcsimOptimizerFeedbackStopReason.NO_SUCCESS
                return self._finish(
                    status=status,
                    started=started,
                    evaluations=all_evaluations,
                    finalists=(),
                    trace_notes=trace_notes,
                    adjustments=tuple(adjustments.values()),
                    counters=counters,
                )
            finalist_primary_proposals = _select_finalist_proposals(
                successful_screening,
                limit=self.plan.max_finalists,
            )
            finalist_proposals = _expand_replacement_proposals(
                finalist_primary_proposals,
                evaluations=successful_screening,
                known_proposals=seen,
            )
            finalist_evaluations, batch_status = self._evaluate(
                finalist_proposals,
                stage=GcsimOptimizerFeedbackStage.FINALIST,
                fidelity=self.plan.finalist,
                deadline=deadline,
                counters=counters,
            )
            all_evaluations.extend(finalist_evaluations)
            terminal = _batch_terminal_reason(batch_status)
            if terminal is not None:
                status = terminal
            successful_finalists = tuple(
                item for item in finalist_evaluations if item.success
            )
            rerace_primary_candidates = _close_rerace_proposals(
                successful_finalists,
                confidence_sigma=self.plan.confidence_sigma,
            )
            rerace_candidates = _expand_replacement_proposals(
                rerace_primary_candidates,
                evaluations=successful_finalists,
                known_proposals=seen,
            )
            rerace_by_simulation: dict[
                str,
                GcsimOptimizerFeedbackEvaluation,
            ] = {}
            if (
                len(rerace_candidates) >= 2
                and status
                not in {
                    GcsimOptimizerFeedbackStopReason.CANCELLED,
                    GcsimOptimizerFeedbackStopReason.DEADLINE_REACHED,
                }
            ):
                rerace_evaluations, rerace_status = self._evaluate(
                    rerace_candidates,
                    stage=GcsimOptimizerFeedbackStage.RERACE,
                    fidelity=self.plan.rerace,
                    deadline=deadline,
                    counters=counters,
                )
                all_evaluations.extend(rerace_evaluations)
                rerace_by_simulation = {
                    item.simulation_sha256: item
                    for item in rerace_evaluations
                    if item.success
                }
                counters.reraced_finalist_count = len(
                    rerace_by_simulation
                )
                terminal = _batch_terminal_reason(rerace_status)
                if terminal is not None:
                    status = terminal
            finalists = _build_finalists(
                successful_screening,
                successful_finalists,
                rerace_by_simulation,
                plan=self.plan,
            )
            counters.em_safeguard_finalist_count = sum(
                "em_response" in item.feature_labels
                for item in finalists
            )
            if not finalists and status not in {
                GcsimOptimizerFeedbackStopReason.CANCELLED,
                GcsimOptimizerFeedbackStopReason.DEADLINE_REACHED,
            }:
                status = GcsimOptimizerFeedbackStopReason.NO_SUCCESS
            elif (
                status is GcsimOptimizerFeedbackStopReason.COMPLETED
                and counters.failed_total
            ):
                status = (
                    GcsimOptimizerFeedbackStopReason.COMPLETED_WITH_ERRORS
                )
            return self._finish(
                status=status,
                started=started,
                evaluations=all_evaluations,
                finalists=finalists,
                trace_notes=trace_notes,
                adjustments=tuple(adjustments.values()),
                counters=counters,
            )

        return self._finish(
            status=status,
            started=started,
            evaluations=all_evaluations,
            finalists=(),
            trace_notes=trace_notes,
            adjustments=tuple(adjustments.values()),
            counters=counters,
        )

    def _evaluate(
        self,
        proposals: Sequence[GcsimOptimizerJointProposal],
        *,
        stage: GcsimOptimizerFeedbackStage,
        fidelity: GcsimOptimizerFeedbackFidelity,
        deadline: float,
        counters: "_FeedbackCounters",
    ) -> tuple[
        tuple[GcsimOptimizerFeedbackEvaluation, ...],
        GcsimFarmingBatchStatus,
    ]:
        eligible_proposals = []
        for proposal in proposals:
            _validate_proposal_for_run(self.run_input, proposal)
            if _proposal_meets_minimum_stat_constraints(
                self.run_input,
                proposal,
            ):
                eligible_proposals.append(proposal)
        if not eligible_proposals:
            return (), GcsimFarmingBatchStatus.COMPLETED
        grouped = _group_equivalent_proposals(eligible_proposals)
        prepared = tuple(
            _prepare_evaluation_request(
                self.run_input,
                engine_context=self.engine_context,
                proposals=group,
                stage=stage,
                fidelity=fidelity,
                plan=self.plan,
                environment=self.environment,
            )
            for group in grouped
        )
        remaining = max(deadline - self.clock(), 1e-6)
        scheduler = GcsimFarmingEvaluationScheduler(
            (item.request for item in prepared),
            GcsimFarmingSchedulerBudget(
                max_parallel_candidates=self.plan.max_parallel_candidates,
                total_cpu_budget=self.plan.total_cpu_budget,
                overall_deadline_seconds=remaining,
            ),
            cache_store=self.cache_store,
            enable_cache=self.enable_cache,
            session_factory=self.session_factory,
        )
        with self._lock:
            self._active_scheduler = scheduler
        if self._cancel_event.is_set():
            scheduler.cancel()
        try:
            batch = scheduler.run()
        finally:
            with self._lock:
                self._active_scheduler = None
        evaluations = tuple(
            _feedback_evaluation(item, result, stage=stage)
            for item, result in zip(prepared, batch.results, strict=True)
        )
        counters.add(stage, evaluations)
        return evaluations, batch.status

    def _terminal_reason(
        self,
        deadline: float,
    ) -> GcsimOptimizerFeedbackStopReason | None:
        if self._cancel_event.is_set():
            return GcsimOptimizerFeedbackStopReason.CANCELLED
        if self.clock() >= deadline:
            return GcsimOptimizerFeedbackStopReason.DEADLINE_REACHED
        return None

    def _finish(
        self,
        *,
        status: GcsimOptimizerFeedbackStopReason,
        started: float,
        evaluations: Sequence[GcsimOptimizerFeedbackEvaluation],
        finalists: Sequence[GcsimOptimizerFeedbackFinalist],
        trace_notes: Sequence[str],
        adjustments: Sequence[GcsimOptimizerJointScoreAdjustment],
        counters: "_FeedbackCounters",
    ) -> GcsimOptimizerFeedbackResult:
        trace = tuple(evaluations[: self.plan.max_trace_evaluations])
        return GcsimOptimizerFeedbackResult(
            status=status,
            stop_reason=status,
            run_input_sha256=self.run_input.run_input_sha256,
            engine_binding_sha256=self.engine_context.binding_sha256,
            plan=self.plan,
            finalists=tuple(finalists),
            trace_evaluations=trace,
            enrichment_trace_notes=tuple(trace_notes),
            score_adjustments=tuple(adjustments),
            coverage=counters.coverage(),
            elapsed_seconds=max(self.clock() - started, 0.0),
        )


@dataclass(frozen=True, slots=True)
class _PreparedFeedbackEvaluation:
    request: GcsimFarmingEvaluationRequest
    proposals: tuple[GcsimOptimizerJointProposal, ...]


@dataclass(slots=True)
class _FeedbackCounters:
    initial_proposal_count: int
    enriched_proposal_count: int = 0
    enrichment_call_count: int = 0
    em_safeguard_finalist_count: int = 0
    reraced_finalist_count: int = 0
    requested: Counter[str] = field(default_factory=Counter)
    successful: Counter[str] = field(default_factory=Counter)
    failed: Counter[str] = field(default_factory=Counter)
    cache_hits: Counter[str] = field(default_factory=Counter)
    unique_simulations: set[str] = field(default_factory=set)
    equivalent_assignments: set[str] = field(default_factory=set)

    @property
    def failed_total(self) -> int:
        return sum(self.failed.values())

    def add(
        self,
        stage: GcsimOptimizerFeedbackStage,
        evaluations: Sequence[GcsimOptimizerFeedbackEvaluation],
    ) -> None:
        key = stage.value
        self.requested[key] += len(evaluations)
        self.successful[key] += sum(item.success for item in evaluations)
        self.failed[key] += sum(not item.success for item in evaluations)
        self.cache_hits[key] += sum(item.cache_hit for item in evaluations)
        self.unique_simulations.update(
            item.simulation_sha256 for item in evaluations
        )
        for item in evaluations:
            self.equivalent_assignments.update(
                item.replacement_proposal_sha256s
            )

    def coverage(self) -> GcsimOptimizerFeedbackCoverage:
        stages = tuple(item.value for item in GcsimOptimizerFeedbackStage)
        return GcsimOptimizerFeedbackCoverage(
            initial_proposal_count=self.initial_proposal_count,
            enriched_proposal_count=self.enriched_proposal_count,
            unique_compiled_config_count=len(self.unique_simulations),
            equivalent_assignment_count=len(self.equivalent_assignments),
            requested_by_stage=tuple(
                (stage, self.requested[stage]) for stage in stages
            ),
            successful_by_stage=tuple(
                (stage, self.successful[stage]) for stage in stages
            ),
            failed_by_stage=tuple(
                (stage, self.failed[stage]) for stage in stages
            ),
            cache_hits_by_stage=tuple(
                (stage, self.cache_hits[stage]) for stage in stages
            ),
            enrichment_call_count=self.enrichment_call_count,
            em_safeguard_finalist_count=(
                self.em_safeguard_finalist_count
            ),
            reraced_finalist_count=self.reraced_finalist_count,
        )


def run_gcsim_optimizer_feedback_loop(
    run_input: GcsimOptimizerRunInput,
    *,
    engine_context: GcsimOptimizerEngineContext,
    proposals: Sequence[GcsimOptimizerJointProposal],
    plan: GcsimOptimizerFeedbackPlan | None = None,
    enricher: FeedbackEnricher | None = None,
    cache_store: GcsimOptimizerCacheStore | None = None,
    enable_cache: bool = True,
    session_factory: Callable[[GcsimFarmingEvaluationRequest], object]
    | None = None,
    environment: Mapping[str, str] | None = None,
) -> GcsimOptimizerFeedbackResult:
    return GcsimOptimizerFeedbackSession(
        run_input,
        engine_context=engine_context,
        proposals=proposals,
        plan=plan,
        enricher=enricher,
        cache_store=cache_store,
        enable_cache=enable_cache,
        session_factory=session_factory,
        environment=environment,
    ).run()


def build_gcsim_optimizer_feedback_candidate_keys(
    proposal: GcsimOptimizerJointProposal,
) -> tuple[CandidateKey, ...]:
    if not isinstance(proposal, GcsimOptimizerJointProposal):
        raise GcsimOptimizerFeedbackError("proposal must be typed")
    rows: list[CandidateKey] = []
    for candidate in proposal.wearer_candidates:
        build = candidate.materialized_build
        main_by_slot = {
            item.artifact_slot: item.gcsim_key
            for item in build.stat_contributions
            if item.source_kind == "main"
        }
        layout = GcsimFiveStarMainStatLayout(
            sands=main_by_slot["sands"],
            goblet=main_by_slot["goblet"],
            circlet=main_by_slot["circlet"],
        )
        package = candidate.target.package
        set_key = package.set_ref.gcsim_set_key
        rows.append(
            (
                candidate.target.wearer.gcsim_character_key,
                set_key,
                gcsim_optimizer_main_layout_id(layout),
                (
                    ""
                    if candidate.offpiece_shape == "5p"
                    else candidate.offpiece_shape
                ),
                build.compiled_block_sha256,
            )
        )
    return tuple(rows)


def _prepare_evaluation_request(
    run_input: GcsimOptimizerRunInput,
    *,
    engine_context: GcsimOptimizerEngineContext,
    proposals: tuple[GcsimOptimizerJointProposal, ...],
    stage: GcsimOptimizerFeedbackStage,
    fidelity: GcsimOptimizerFeedbackFidelity,
    plan: GcsimOptimizerFeedbackPlan,
    environment: Mapping[str, str],
) -> _PreparedFeedbackEvaluation:
    primary = min(proposals, key=lambda item: item.proposal_sha256)
    config = apply_gcsim_screening_runtime_options(
        primary.compiled_candidate.config_text,
        iterations=fidelity.iterations,
        workers=fidelity.worker_count,
    )
    comparison_context = _canonical_sha256(
        {
            "schema_version": GCSIM_OPTIMIZER_FEEDBACK_SCHEMA_VERSION,
            "run_input_sha256": run_input.run_input_sha256,
            "engine_binding_sha256": engine_context.binding_sha256,
            "stage": stage.value,
            "fidelity": fidelity.to_dict(),
            "plan_sha256": _canonical_sha256(plan.to_dict()),
        }
    )
    request = GcsimFarmingEvaluationRequest(
        candidate=None,
        config_text=config,
        comparison_context_sha256=comparison_context,
        investment_signature=(
            f"account-feedback/{stage.value}/{fidelity.iterations}"
        ),
        engine_id=engine_context.engine_id,
        engine_version=engine_context.engine_version,
        artifact_path=engine_context.artifact_path,
        artifact_sha256=engine_context.artifact_sha256,
        engine_binding_sha256=engine_context.binding_sha256,
        catalog_fingerprint=engine_context.catalog.source_fingerprint,
        worker_count=fidelity.worker_count,
        expected_iterations=fidelity.iterations,
        timeout_seconds=fidelity.timeout_seconds,
        environment=freeze_gcsim_farming_environment(
            environment,
            worker_count=fidelity.worker_count,
        ),
        novelty_score=0.0,
        novelty_tags=tuple(sorted(primary.diversity_labels)),
        joint_candidate_keys=build_gcsim_optimizer_feedback_candidate_keys(
            primary
        ),
    )
    return _PreparedFeedbackEvaluation(request=request, proposals=proposals)


def _feedback_evaluation(
    prepared: _PreparedFeedbackEvaluation,
    result: GcsimFarmingEvaluationResult,
    *,
    stage: GcsimOptimizerFeedbackStage,
) -> GcsimOptimizerFeedbackEvaluation:
    primary = min(
        prepared.proposals,
        key=lambda item: item.proposal_sha256,
    )
    replacements = tuple(
        sorted(
            item.proposal_sha256
            for item in prepared.proposals
            if item.proposal_sha256 != primary.proposal_sha256
        )
    )
    labels = {
        label
        for proposal in prepared.proposals
        for label in proposal.diversity_labels
    }
    evidence_sha256 = _canonical_sha256(
        {
            "request_identity_sha256": result.request_identity_sha256,
            "source_config_sha256": result.source_config_sha256,
            "summary": result.summary.to_dict(),
            "status": result.status.value,
        }
    )
    return GcsimOptimizerFeedbackEvaluation(
        stage=stage,
        proposal=primary,
        replacement_proposal_sha256s=replacements,
        equivalent_assignment_count=len(prepared.proposals),
        request_identity_sha256=result.request_identity_sha256,
        simulation_sha256=(
            primary.compiled_candidate.simulation_sha256
        ),
        success=result.success,
        status=result.status.value,
        iterations=result.expected_iterations,
        dps_mean=result.summary.dps_mean if result.success else None,
        dps_standard_error=(
            result.summary.dps_se if result.success else None
        ),
        cache_hit=result.cache_hit,
        evidence_sha256=evidence_sha256,
        feature_labels=tuple(labels),
        error=result.error,
    )


def _group_equivalent_proposals(
    proposals: Sequence[GcsimOptimizerJointProposal],
) -> tuple[tuple[GcsimOptimizerJointProposal, ...], ...]:
    grouped: dict[str, list[GcsimOptimizerJointProposal]] = {}
    for proposal in proposals:
        grouped.setdefault(
            proposal.compiled_candidate.compiled_config_sha256,
            [],
        ).append(proposal)
    return tuple(
        tuple(sorted(rows, key=lambda item: item.proposal_sha256))
        for _key, rows in sorted(grouped.items())
    )


def _select_finalist_proposals(
    screening: Sequence[GcsimOptimizerFeedbackEvaluation],
    *,
    limit: int,
) -> tuple[GcsimOptimizerJointProposal, ...]:
    ranked = tuple(sorted(screening, key=_evaluation_rank))
    selected: list[GcsimOptimizerFeedbackEvaluation] = []
    if ranked:
        selected.append(ranked[0])
    protected = (
        "em_response",
        "unusual_main",
    )
    for label in protected:
        match = next(
            (
                item
                for item in ranked
                if label in item.feature_labels and item not in selected
            ),
            None,
        )
        if match is not None and len(selected) < limit:
            selected.append(match)
    threshold = next(
        (
            item
            for item in ranked
            if any(
                label.startswith("threshold:")
                for label in item.feature_labels
            )
            and item not in selected
        ),
        None,
    )
    if threshold is not None and len(selected) < limit:
        selected.append(threshold)
    for item in ranked:
        if len(selected) >= limit:
            break
        if item not in selected:
            selected.append(item)
    return tuple(item.proposal for item in selected)


def _close_rerace_proposals(
    evaluations: Sequence[GcsimOptimizerFeedbackEvaluation],
    *,
    confidence_sigma: float,
) -> tuple[GcsimOptimizerJointProposal, ...]:
    ranked = tuple(sorted(evaluations, key=_evaluation_rank))
    if len(ranked) < 2:
        return ()
    best = ranked[0]
    assert best.dps_mean is not None
    close = [best]
    for item in ranked[1:]:
        assert item.dps_mean is not None
        if (
            best.dps_standard_error is None
            or item.dps_standard_error is None
        ):
            close.append(item)
            continue
        combined = sqrt(
            best.dps_standard_error**2
            + item.dps_standard_error**2
        )
        if best.dps_mean - item.dps_mean <= confidence_sigma * combined:
            close.append(item)
    return tuple(item.proposal for item in close) if len(close) >= 2 else ()


def _expand_replacement_proposals(
    primary_proposals: Sequence[GcsimOptimizerJointProposal],
    *,
    evaluations: Sequence[GcsimOptimizerFeedbackEvaluation],
    known_proposals: Mapping[str, GcsimOptimizerJointProposal],
) -> tuple[GcsimOptimizerJointProposal, ...]:
    evaluation_by_primary = {
        item.proposal.proposal_sha256: item for item in evaluations
    }
    result: dict[str, GcsimOptimizerJointProposal] = {}
    for proposal in primary_proposals:
        result[proposal.proposal_sha256] = proposal
        evaluation = evaluation_by_primary.get(proposal.proposal_sha256)
        if evaluation is None:
            continue
        for replacement_sha256 in evaluation.replacement_proposal_sha256s:
            replacement = known_proposals.get(replacement_sha256)
            if replacement is not None:
                result[replacement_sha256] = replacement
    return tuple(
        sorted(result.values(), key=lambda item: item.proposal_sha256)
    )


def _build_finalists(
    screening: Sequence[GcsimOptimizerFeedbackEvaluation],
    finalist: Sequence[GcsimOptimizerFeedbackEvaluation],
    rerace_by_simulation: Mapping[str, GcsimOptimizerFeedbackEvaluation],
    *,
    plan: GcsimOptimizerFeedbackPlan,
) -> tuple[GcsimOptimizerFeedbackFinalist, ...]:
    screening_by_simulation = {
        item.simulation_sha256: item for item in screening
    }
    final_rows = []
    for high in finalist:
        final = rerace_by_simulation.get(high.simulation_sha256, high)
        if final.iterations < plan.finalist.iterations:
            raise GcsimOptimizerFeedbackError(
                "displayed finalist lacks common minimum fidelity"
            )
        final_rows.append(final)
    ranked = tuple(sorted(final_rows, key=_evaluation_rank))
    if not ranked:
        return ()
    best = ranked[0]
    result = []
    for rank, final in enumerate(ranked, start=1):
        uncertainty = _uncertainty(
            best,
            final,
            confidence_sigma=plan.confidence_sigma,
        )
        result.append(
            GcsimOptimizerFeedbackFinalist(
                rank=rank,
                proposal=final.proposal,
                replacement_proposal_sha256s=(
                    final.replacement_proposal_sha256s
                ),
                equivalent_assignment_count=(
                    final.equivalent_assignment_count
                ),
                screening_evaluation=screening_by_simulation[
                    final.simulation_sha256
                ],
                final_evaluation=final,
                uncertainty=uncertainty,
                evidence_stage=final.stage,
                feature_labels=final.feature_labels,
            )
        )
    return tuple(result)


def _uncertainty(
    best: GcsimOptimizerFeedbackEvaluation,
    candidate: GcsimOptimizerFeedbackEvaluation,
    *,
    confidence_sigma: float,
) -> GcsimOptimizerUncertainty:
    assert best.dps_mean is not None
    assert candidate.dps_mean is not None
    delta = abs(best.dps_mean - candidate.dps_mean)
    if candidate is best:
        return GcsimOptimizerUncertainty(
            label=GcsimOptimizerUncertaintyLabel.REFERENCE,
            confidence_sigma=confidence_sigma,
            absolute_delta_to_best=0.0,
            combined_standard_error=None,
            comparison_threshold=None,
        )
    if (
        best.dps_standard_error is None
        or candidate.dps_standard_error is None
    ):
        return GcsimOptimizerUncertainty(
            label=GcsimOptimizerUncertaintyLabel.UNKNOWN,
            confidence_sigma=confidence_sigma,
            absolute_delta_to_best=delta,
            combined_standard_error=None,
            comparison_threshold=None,
        )
    combined = sqrt(
        best.dps_standard_error**2
        + candidate.dps_standard_error**2
    )
    threshold = confidence_sigma * combined
    return GcsimOptimizerUncertainty(
        label=(
            GcsimOptimizerUncertaintyLabel.WITHIN_NOISE
            if delta <= threshold
            else GcsimOptimizerUncertaintyLabel.SEPARATED
        ),
        confidence_sigma=confidence_sigma,
        absolute_delta_to_best=delta,
        combined_standard_error=combined,
        comparison_threshold=threshold,
    )


def _best_evaluation(
    evaluations: Sequence[GcsimOptimizerFeedbackEvaluation],
) -> GcsimOptimizerFeedbackEvaluation | None:
    successful = tuple(item for item in evaluations if item.success)
    return min(successful, key=_evaluation_rank) if successful else None


def _evaluation_rank(
    evaluation: GcsimOptimizerFeedbackEvaluation,
) -> tuple[float, str]:
    return (
        -float(evaluation.dps_mean or 0.0),
        evaluation.proposal.proposal_sha256,
    )


def _batch_terminal_reason(
    status: GcsimFarmingBatchStatus,
) -> GcsimOptimizerFeedbackStopReason | None:
    if status is GcsimFarmingBatchStatus.CANCELLED:
        return GcsimOptimizerFeedbackStopReason.CANCELLED
    if status is GcsimFarmingBatchStatus.DEADLINE_REACHED:
        return GcsimOptimizerFeedbackStopReason.DEADLINE_REACHED
    return None


def _validate_session_inputs(session: GcsimOptimizerFeedbackSession) -> None:
    if not isinstance(session.run_input, GcsimOptimizerRunInput):
        raise GcsimOptimizerFeedbackError("run_input must be typed")
    if not isinstance(session.engine_context, GcsimOptimizerEngineContext):
        raise GcsimOptimizerFeedbackError("engine_context must be typed")
    if (
        not session.engine_context.trusted
        or session.engine_context.binding_sha256
        != session.run_input.engine_binding_sha256
        or session.engine_context.catalog.source_fingerprint
        != session.run_input.catalog_fingerprint
    ):
        raise GcsimOptimizerFeedbackError(
            "feedback requires the trusted engine bound to run_input"
        )
    if not isinstance(session.plan, GcsimOptimizerFeedbackPlan):
        raise GcsimOptimizerFeedbackError("plan must be typed")
    if not session.proposals:
        raise GcsimOptimizerFeedbackError(
            "feedback requires initial M6 proposals"
        )
    for proposal in session.proposals:
        _validate_proposal_for_run(session.run_input, proposal)


def _validate_proposal_for_run(
    run_input: GcsimOptimizerRunInput,
    proposal: GcsimOptimizerJointProposal,
) -> None:
    if not isinstance(proposal, GcsimOptimizerJointProposal):
        raise GcsimOptimizerFeedbackError("proposal must be typed")
    witness = proposal.compiled_candidate.assignment_witness
    if (
        witness.request_sha256 != run_input.request.request_sha256
        or witness.artifact_database_input_sha256
        != run_input.artifact_database.artifact_database_input_sha256
    ):
        raise GcsimOptimizerFeedbackError(
            "proposal belongs to another request/database input"
        )


def _proposal_meets_minimum_stat_constraints(
    run_input: GcsimOptimizerRunInput,
    proposal: GcsimOptimizerJointProposal,
) -> bool:
    """Recheck every exact compiled build before any GCSIM session exists."""

    if not run_input.request.minimum_stat_constraints:
        return True
    compiled = proposal.compiled_candidate
    if (
        tuple(item.target for item in proposal.wearer_candidates)
        != compiled.targets
    ):
        return False
    try:
        for target, build in zip(
            compiled.targets,
            compiled.builds,
            strict=True,
        ):
            if build.target != target:
                return False
            artifact_stats = dict(build.normalized_stats)
            if len(artifact_stats) != len(build.normalized_stats):
                return False
            if evaluate_gcsim_optimizer_minimum_stat_constraints(
                run_input,
                target=target,
                artifact_stats=artifact_stats,
            ):
                return False
    except (TypeError, ValueError):
        return False
    return True


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_schema(value: int) -> None:
    if value != GCSIM_OPTIMIZER_FEEDBACK_SCHEMA_VERSION:
        raise GcsimOptimizerFeedbackError(
            "unsupported optimizer feedback schema"
        )


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GcsimOptimizerFeedbackError(
            f"{field_name} must be lowercase SHA-256"
        )


__all__ = [
    "GCSIM_OPTIMIZER_FEEDBACK_SCHEMA_VERSION",
    "FeedbackEnricher",
    "GcsimOptimizerFeedbackCoverage",
    "GcsimOptimizerFeedbackEnrichmentRequest",
    "GcsimOptimizerFeedbackEnrichmentResponse",
    "GcsimOptimizerFeedbackError",
    "GcsimOptimizerFeedbackEvaluation",
    "GcsimOptimizerFeedbackFidelity",
    "GcsimOptimizerFeedbackFinalist",
    "GcsimOptimizerFeedbackPlan",
    "GcsimOptimizerFeedbackResult",
    "GcsimOptimizerFeedbackSession",
    "GcsimOptimizerFeedbackStage",
    "GcsimOptimizerFeedbackStopReason",
    "build_gcsim_optimizer_feedback_candidate_keys",
    "run_gcsim_optimizer_feedback_loop",
]
