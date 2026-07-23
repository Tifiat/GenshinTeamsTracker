"""Production bridge from generic stat probes to bounded response profiles.

The selector in :mod:`farming_response` is intentionally pure.  This module
materializes its complete wearer-by-profile domain against one frozen physical
artifact state per wearer, executes the deduplicated whole-team configs through
the ordinary bounded evaluator, and returns proof-carrying selections for the
later 4p set screen.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
import math
from threading import Event, Lock
from time import monotonic
from types import MappingProxyType

from .farming_evaluator import (
    FarmingSessionFactory,
    GcsimFarmingBatchResult,
    GcsimFarmingBatchStatus,
    GcsimFarmingEvaluationRequest,
    GcsimFarmingEvaluationResult,
    GcsimFarmingEvaluationScheduler,
    GcsimFarmingEvaluationStatus,
    GcsimFarmingSchedulerBudget,
    freeze_gcsim_farming_environment,
    normalize_gcsim_farming_frozen_environment,
)
from .farming_pipeline import (
    GcsimFarmingMaterializedProbe,
    GcsimFarmingScreeningFidelity,
    LayoutCatalog,
    SchedulerFactory,
    materialize_gcsim_one_wearer_candidate,
)
from .farming_profile_config import GCSIM_BALANCED_REFERENCE_WEIGHTS
from .farming_response import (
    FarmingResponseSelectionError,
    ResponseProfileOutcome,
    ResponseProfileOutcomeStatus,
    ResponseProfileSelectionBudget,
    ResponseProfileSelectionResult,
    select_wearer_response_profiles,
)
from .farming_search import (
    PROFILE_BASELINE,
    CandidateEvaluation,
    SetProfileCandidate,
    StatProfileBank,
    StatWeight,
)
from .optimizer_cache import GcsimOptimizerCacheStore
from .optimizer_engine_context import GcsimOptimizerEngineContext


class GcsimResponseScanError(RuntimeError):
    """Raised when the response-scan contract is internally inconsistent."""


class GcsimResponseScanStatus(str, Enum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DEADLINE_REACHED = "deadline_reached"
    SELECTION_FAILED = "selection_failed"
    NO_RESULT = "no_result"


@dataclass(frozen=True, slots=True)
class GcsimResponseScanRequest:
    engine_context: GcsimOptimizerEngineContext
    prepared_config_text: str
    wearer_ids: tuple[str, ...]
    layout_catalog: LayoutCatalog
    profile_bank: StatProfileBank
    baseline_states: tuple[SetProfileCandidate, ...]
    fidelity: GcsimFarmingScreeningFidelity
    scheduler_budget: GcsimFarmingSchedulerBudget
    selection_budget: ResponseProfileSelectionBudget
    candidate_timeout_seconds: float
    reference_weights: tuple[StatWeight, ...] = GCSIM_BALANCED_REFERENCE_WEIGHTS
    baseline_profile_id: str = PROFILE_BASELINE
    environment: Mapping[str, str] = field(default_factory=dict, repr=False)
    environment_is_frozen: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "wearer_ids", tuple(self.wearer_ids))
        object.__setattr__(self, "baseline_states", tuple(self.baseline_states))
        object.__setattr__(self, "reference_weights", tuple(self.reference_weights))
        if not isinstance(self.layout_catalog, Mapping):
            raise GcsimResponseScanError("layout_catalog must be a mapping")
        try:
            frozen_layout_catalog = MappingProxyType(
                {
                    str(wearer): MappingProxyType(dict(entries))
                    for wearer, entries in self.layout_catalog.items()
                }
            )
        except (TypeError, ValueError) as exc:
            raise GcsimResponseScanError(
                "layout_catalog values must be mappings"
            ) from exc
        object.__setattr__(self, "layout_catalog", frozen_layout_catalog)
        if not isinstance(self.fidelity, GcsimFarmingScreeningFidelity):
            raise GcsimResponseScanError(
                "fidelity must be a GcsimFarmingScreeningFidelity"
            )
        if not isinstance(self.environment, Mapping):
            raise GcsimResponseScanError("environment must be a mapping")
        try:
            frozen_environment = (
                normalize_gcsim_farming_frozen_environment(
                    self.environment,
                    worker_count=self.fidelity.worker_count,
                )
                if self.environment_is_frozen
                else freeze_gcsim_farming_environment(
                    self.environment,
                    worker_count=self.fidelity.worker_count,
                )
            )
        except ValueError as exc:
            raise GcsimResponseScanError(str(exc)) from exc
        object.__setattr__(
            self,
            "environment",
            MappingProxyType(frozen_environment),
        )
        object.__setattr__(self, "environment_is_frozen", True)
        if (
            isinstance(self.candidate_timeout_seconds, bool)
            or not math.isfinite(self.candidate_timeout_seconds)
            or self.candidate_timeout_seconds <= 0
        ):
            raise GcsimResponseScanError(
                "candidate_timeout_seconds must be finite and positive"
            )
        if tuple(state.state.wearer_id for state in self.baseline_states) != self.wearer_ids:
            raise GcsimResponseScanError(
                "baseline_states must match wearer_ids in canonical order"
            )
        if any(
            state.profile_id != self.baseline_profile_id
            for state in self.baseline_states
        ):
            raise GcsimResponseScanError(
                "baseline_states must use baseline_profile_id"
            )
        if self.baseline_profile_id not in tuple(
            profile.profile_id for profile in self.profile_bank.profiles
        ):
            raise GcsimResponseScanError(
                "profile_bank does not contain baseline_profile_id"
            )


@dataclass(frozen=True, slots=True)
class GcsimResponseScanResult:
    status: GcsimResponseScanStatus
    stop_reason: str
    elapsed_seconds: float
    planned_candidate_count: int
    materialized_request_count: int
    comparison_context_sha256: str = ""
    outcomes: tuple[ResponseProfileOutcome, ...] = ()
    selection: ResponseProfileSelectionResult | None = None
    batch: GcsimFarmingBatchResult | None = None
    error: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, GcsimResponseScanStatus):
            raise ValueError("status must be a GcsimResponseScanStatus")
        if self.planned_candidate_count <= 0:
            raise ValueError("planned_candidate_count must be positive")
        if not 0 <= self.materialized_request_count <= self.planned_candidate_count:
            raise ValueError("materialized_request_count is out of range")
        if self.elapsed_seconds < 0 or not math.isfinite(self.elapsed_seconds):
            raise ValueError("elapsed_seconds must be finite and non-negative")
        if self.comparison_context_sha256 and (
            len(self.comparison_context_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.comparison_context_sha256
            )
        ):
            raise ValueError(
                "comparison_context_sha256 must be empty or a SHA-256 digest"
            )
        if self.status is GcsimResponseScanStatus.COMPLETED:
            if (
                self.selection is None
                or self.batch is None
                or len(self.outcomes) != self.planned_candidate_count
            ):
                raise ValueError(
                    "a completed response scan requires batch, full outcomes, and selection"
                )
        elif self.selection is not None:
            raise ValueError("only a completed response scan may carry a selection")
        if self.selection is not None and (
            self.selection.comparison_context_sha256
            != self.comparison_context_sha256
        ):
            raise ValueError("response selection context differs from scan context")
        if self.batch is not None and (
            len(self.batch.results) != self.materialized_request_count
        ):
            raise ValueError("response batch size differs from materialized requests")
        if self.batch is not None and self.batch.comparison_context_sha256 != (
            self.comparison_context_sha256
        ):
            raise ValueError("response batch context differs from scan context")
        if self.status is GcsimResponseScanStatus.COMPLETED and self.batch.status not in {
            GcsimFarmingBatchStatus.COMPLETED,
            GcsimFarmingBatchStatus.COMPLETED_WITH_ERRORS,
        }:
            raise ValueError("a completed response scan cannot carry a terminal batch")
        if self.selection is not None:
            expected_pairs = tuple(
                (selection.wearer_id, profile_id)
                for selection in self.selection.selections
                for profile_id in self.selection.profile_ids
            )
            actual_pairs = tuple(
                (outcome.candidate.state.wearer_id, outcome.candidate.profile_id)
                for outcome in self.outcomes
            )
            if actual_pairs != expected_pairs:
                raise ValueError("response outcomes are not in canonical selection order")
            if len(self.outcomes) != len(self.selection.audit_rows):
                raise ValueError("response outcomes and audit rows differ in size")
            for outcome, audit in zip(
                self.outcomes,
                self.selection.audit_rows,
                strict=True,
            ):
                evaluation = outcome.evaluation
                if (
                    outcome.candidate.key != audit.candidate_key
                    or outcome.status is not audit.status
                    or outcome.request_identity_sha256
                    != audit.request_identity_sha256
                    or outcome.comparison_context_sha256
                    != self.selection.comparison_context_sha256
                    or outcome.investment_signature
                    != self.selection.investment_signature
                    or outcome.detail != audit.detail
                    or (None if evaluation is None else evaluation.expected_dps)
                    != audit.expected_dps
                    or (None if evaluation is None else evaluation.standard_error)
                    != audit.standard_error
                ):
                    raise ValueError(
                        "response outcomes disagree with proof-carrying selection audit"
                    )

    @property
    def completed(self) -> bool:
        return (
            self.status is GcsimResponseScanStatus.COMPLETED
            and self.selection is not None
        )


class _CancellableScheduler:
    def run(self) -> GcsimFarmingBatchResult: ...

    def cancel(self) -> None: ...


class GcsimResponseScanSession:
    """One-shot, CPU-bounded and directly cancellable response scan."""

    def __init__(
        self,
        request: GcsimResponseScanRequest,
        *,
        cache_store: GcsimOptimizerCacheStore | None = None,
        enable_cache: bool = True,
        session_factory: FarmingSessionFactory | None = None,
        scheduler_factory: SchedulerFactory | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isinstance(request, GcsimResponseScanRequest):
            raise GcsimResponseScanError(
                "request must be a GcsimResponseScanRequest"
            )
        self.request = request
        self._cache_store = cache_store
        self._enable_cache = bool(enable_cache)
        self._session_factory = session_factory
        self._scheduler_factory = scheduler_factory
        self._clock = clock
        self._cancel_event = Event()
        self._lock = Lock()
        self._active_scheduler: _CancellableScheduler | None = None
        self._started = False

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            scheduler = self._active_scheduler
        if scheduler is not None:
            scheduler.cancel()

    def run(self) -> GcsimResponseScanResult:
        with self._lock:
            if self._started:
                raise RuntimeError("GcsimResponseScanSession instances are one-shot")
            self._started = True
        started = self._clock()
        deadline = started + self.request.scheduler_budget.overall_deadline_seconds
        profile_ids = tuple(
            profile.profile_id for profile in self.request.profile_bank.profiles
        )
        candidates = tuple(
            SetProfileCandidate(state=baseline.state, profile_id=profile_id)
            for baseline in self.request.baseline_states
            for profile_id in profile_ids
        )

        proof_by_probe_key: dict[tuple, GcsimFarmingMaterializedProbe] = {}
        probe_key_by_candidate_key: dict[tuple[str, str, str, str, str], tuple] = {}
        for candidate in candidates:
            if self._cancel_event.is_set():
                return self._terminal(
                    started,
                    candidates,
                    GcsimResponseScanStatus.CANCELLED,
                    "cancelled_during_materialization",
                    materialized_request_count=len(proof_by_probe_key),
                )
            if self._clock() >= deadline:
                return self._terminal(
                    started,
                    candidates,
                    GcsimResponseScanStatus.DEADLINE_REACHED,
                    "deadline_during_materialization",
                    materialized_request_count=len(proof_by_probe_key),
                )
            other_baselines = tuple(
                baseline
                for baseline in self.request.baseline_states
                if baseline.state.wearer_id != candidate.state.wearer_id
            )
            proof = materialize_gcsim_one_wearer_candidate(
                self.request.prepared_config_text,
                candidate=candidate,
                frozen_baseline_states=other_baselines,
                wearer_ids=self.request.wearer_ids,
                layout_catalog=self.request.layout_catalog,
                profile_bank=self.request.profile_bank,
                engine_context=self.request.engine_context,
                fidelity=self.request.fidelity,
                reference_weights=self.request.reference_weights,
                environment=self.request.environment,
                environment_is_frozen=True,
            )
            probe_key_by_candidate_key[candidate.key] = proof.candidate_keys
            previous = proof_by_probe_key.setdefault(proof.candidate_keys, proof)
            if (
                previous.config_text != proof.config_text
                or previous.evaluation_context_sha256
                != proof.evaluation_context_sha256
            ):
                raise GcsimResponseScanError(
                    "deduplicated response probe materialized inconsistently"
                )

        contexts = {
            proof.evaluation_context_sha256
            for proof in proof_by_probe_key.values()
        }
        if len(contexts) != 1:
            raise GcsimResponseScanError(
                "response probes do not share one comparison context"
            )
        comparison_context_sha256 = next(iter(contexts))
        evaluator_requests = tuple(
            proof.build_evaluator_request(
                engine_context=self.request.engine_context,
                timeout_seconds=self.request.candidate_timeout_seconds,
                environment=self.request.environment,
            )
            for proof in proof_by_probe_key.values()
        )
        remaining = deadline - self._clock()
        if remaining <= 0:
            return self._terminal(
                started,
                candidates,
                GcsimResponseScanStatus.DEADLINE_REACHED,
                "deadline_before_scheduler",
                materialized_request_count=len(evaluator_requests),
                comparison_context_sha256=comparison_context_sha256,
            )
        budget = replace(
            self.request.scheduler_budget,
            overall_deadline_seconds=remaining,
        )
        scheduler = self._make_scheduler(evaluator_requests, budget)
        if self._cancel_event.is_set() or self._clock() >= deadline:
            scheduler.cancel()
            return self._terminal(
                started,
                candidates,
                (
                    GcsimResponseScanStatus.CANCELLED
                    if self._cancel_event.is_set()
                    else GcsimResponseScanStatus.DEADLINE_REACHED
                ),
                (
                    "cancelled_after_scheduler_factory"
                    if self._cancel_event.is_set()
                    else "deadline_after_scheduler_factory"
                ),
                materialized_request_count=len(evaluator_requests),
                comparison_context_sha256=comparison_context_sha256,
            )
        with self._lock:
            self._active_scheduler = scheduler
        try:
            if self._cancel_event.is_set():
                scheduler.cancel()
            batch = scheduler.run()
        finally:
            with self._lock:
                if self._active_scheduler is scheduler:
                    self._active_scheduler = None
        _validate_batch(evaluator_requests, batch)
        result_by_probe_key = {
            result.candidate_keys: result
            for result in batch.results
        }
        outcomes: list[ResponseProfileOutcome] = []
        for candidate in candidates:
            result = result_by_probe_key[probe_key_by_candidate_key[candidate.key]]
            if result.success:
                evaluation = CandidateEvaluation(
                    candidate=candidate,
                    expected_dps=float(result.summary.dps_mean),
                    standard_error=result.summary.dps_se,
                    investment_signature=self._investment_signature(
                        proof_by_probe_key
                    ),
                )
                outcomes.append(
                    ResponseProfileOutcome.from_evaluation(
                        evaluation,
                        comparison_context_sha256=comparison_context_sha256,
                        request_identity_sha256=result.request_identity_sha256,
                    )
                )
            else:
                outcomes.append(
                    ResponseProfileOutcome(
                        candidate=candidate,
                        status=_outcome_status(result.status),
                        investment_signature=self._investment_signature(
                            proof_by_probe_key
                        ),
                        comparison_context_sha256=comparison_context_sha256,
                        request_identity_sha256=result.request_identity_sha256,
                        detail=result.error or result.status.value,
                    )
                )
        outcome_tuple = tuple(outcomes)
        if self._cancel_event.is_set() or batch.status is GcsimFarmingBatchStatus.CANCELLED:
            return self._terminal(
                started,
                candidates,
                GcsimResponseScanStatus.CANCELLED,
                "scheduler_cancelled",
                materialized_request_count=len(evaluator_requests),
                comparison_context_sha256=comparison_context_sha256,
                outcomes=outcome_tuple,
                batch=batch,
            )
        if (
            batch.status is GcsimFarmingBatchStatus.DEADLINE_REACHED
            or self._clock() >= deadline
        ):
            return self._terminal(
                started,
                candidates,
                GcsimResponseScanStatus.DEADLINE_REACHED,
                "scheduler_deadline_reached",
                materialized_request_count=len(evaluator_requests),
                comparison_context_sha256=comparison_context_sha256,
                outcomes=outcome_tuple,
                batch=batch,
            )
        try:
            selection = select_wearer_response_profiles(
                outcome_tuple,
                wearer_ids=self.request.wearer_ids,
                profile_bank=self.request.profile_bank,
                budget=self.request.selection_budget,
                baseline_profile_id=self.request.baseline_profile_id,
            )
        except FarmingResponseSelectionError as exc:
            return self._terminal(
                started,
                candidates,
                GcsimResponseScanStatus.SELECTION_FAILED,
                "selection_failed",
                materialized_request_count=len(evaluator_requests),
                comparison_context_sha256=comparison_context_sha256,
                outcomes=outcome_tuple,
                batch=batch,
                error=str(exc),
            )
        if self._cancel_event.is_set():
            return self._terminal(
                started,
                candidates,
                GcsimResponseScanStatus.CANCELLED,
                "cancelled_during_response_selection",
                materialized_request_count=len(evaluator_requests),
                comparison_context_sha256=comparison_context_sha256,
                outcomes=outcome_tuple,
                batch=batch,
            )
        if self._clock() >= deadline:
            return self._terminal(
                started,
                candidates,
                GcsimResponseScanStatus.DEADLINE_REACHED,
                "deadline_during_response_selection",
                materialized_request_count=len(evaluator_requests),
                comparison_context_sha256=comparison_context_sha256,
                outcomes=outcome_tuple,
                batch=batch,
            )
        return self._terminal(
            started,
            candidates,
            GcsimResponseScanStatus.COMPLETED,
            "response_profiles_selected",
            materialized_request_count=len(evaluator_requests),
            comparison_context_sha256=comparison_context_sha256,
            outcomes=outcome_tuple,
            selection=selection,
            batch=batch,
        )

    @staticmethod
    def _investment_signature(
        proof_by_probe_key: Mapping[tuple, GcsimFarmingMaterializedProbe],
    ) -> str:
        signatures = {
            proof.investment_signature for proof in proof_by_probe_key.values()
        }
        if len(signatures) != 1:
            raise GcsimResponseScanError(
                "response probes do not share one investment signature"
            )
        return next(iter(signatures))

    def _make_scheduler(
        self,
        requests: tuple[GcsimFarmingEvaluationRequest, ...],
        budget: GcsimFarmingSchedulerBudget,
    ) -> _CancellableScheduler:
        if self._scheduler_factory is not None:
            scheduler = self._scheduler_factory(requests, budget)
        else:
            scheduler = GcsimFarmingEvaluationScheduler(
                requests,
                budget,
                cache_store=self._cache_store,
                enable_cache=self._enable_cache,
                session_factory=self._session_factory,
            )
        if not hasattr(scheduler, "run") or not hasattr(scheduler, "cancel"):
            raise GcsimResponseScanError(
                "scheduler factory returned an invalid scheduler"
            )
        return scheduler

    def _terminal(
        self,
        started: float,
        candidates: tuple[SetProfileCandidate, ...],
        status: GcsimResponseScanStatus,
        stop_reason: str,
        **kwargs,
    ) -> GcsimResponseScanResult:
        return GcsimResponseScanResult(
            status=status,
            stop_reason=stop_reason,
            elapsed_seconds=max(self._clock() - started, 0.0),
            planned_candidate_count=len(candidates),
            **kwargs,
        )


def _outcome_status(
    status: GcsimFarmingEvaluationStatus,
) -> ResponseProfileOutcomeStatus:
    if status in {
        GcsimFarmingEvaluationStatus.TIMEOUT,
        GcsimFarmingEvaluationStatus.SKIPPED_DEADLINE,
    }:
        return ResponseProfileOutcomeStatus.TIMEOUT
    if status in {
        GcsimFarmingEvaluationStatus.CANCELLED,
        GcsimFarmingEvaluationStatus.SKIPPED_CANCELLED,
    }:
        return ResponseProfileOutcomeStatus.UNRESOLVED
    return ResponseProfileOutcomeStatus.FAILED


def _validate_batch(
    requests: tuple[GcsimFarmingEvaluationRequest, ...],
    batch: GcsimFarmingBatchResult,
) -> None:
    if not isinstance(batch, GcsimFarmingBatchResult):
        raise GcsimResponseScanError("scheduler returned a non-typed batch")
    if len(batch.results) != len(requests):
        raise GcsimResponseScanError(
            "scheduler did not return one result per response request"
        )
    for request, result in zip(requests, batch.results, strict=True):
        if not isinstance(result, GcsimFarmingEvaluationResult):
            raise GcsimResponseScanError(
                "scheduler returned a non-typed response result"
            )
        identity = request.identity
        if (
            result.candidate_keys != request.candidate_keys
            or result.request_identity_sha256 != identity.identity_sha256
            or result.cache_key != request.cache_identity.cache_key
            or result.comparison_context_sha256
            != request.comparison_context_sha256
            or result.expected_iterations != request.expected_iterations
            or result.engine_binding_sha256 != identity.engine_binding_sha256
            or result.source_config_sha256 != identity.source_config_sha256
            or (
                result.artifact_sha256 != identity.artifact_sha256
                and result.status
                is not GcsimFarmingEvaluationStatus.ARTIFACT_IDENTITY_MISMATCH
            )
        ):
            raise GcsimResponseScanError(
                "response result provenance/order does not match its request"
            )


def run_gcsim_response_scan(
    request: GcsimResponseScanRequest,
    **session_options,
) -> GcsimResponseScanResult:
    return GcsimResponseScanSession(request, **session_options).run()


__all__ = [
    "GcsimResponseScanError",
    "GcsimResponseScanRequest",
    "GcsimResponseScanResult",
    "GcsimResponseScanSession",
    "GcsimResponseScanStatus",
    "run_gcsim_response_scan",
]
