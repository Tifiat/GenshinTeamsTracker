"""Bounded 200-iteration theoretical validation and close-leader rerace.

The expensive upstream ``substatOptim`` stage runs exactly once for at most a
small finalist set.  Its optimized configs are validated at 200 iterations.
Only statistically overlapping leaders are then repeated at 1000 iterations,
using ordinary simulation of the already optimized config.  The rerace never
invokes ``substatOptim`` again.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from math import hypot, isfinite
from threading import Event, Lock
from time import monotonic

from .farming_evaluator import (
    GcsimFarmingBatchStatus,
    GcsimFarmingEvaluationResult,
    GcsimFarmingEvaluationScheduler,
    GcsimFarmingSchedulerBudget,
    prepare_bound_gcsim_farming_joint_evaluation,
)
from .farming_finalist_optimizer import (
    GcsimFinalistAttemptStatus,
    GcsimFinalistOptimizerBudget,
    GcsimFinalistOptimizerOutcome,
    GcsimFinalistOptimizerRequest,
    GcsimFinalistOptimizerResult,
    GcsimFinalistOptimizerSession,
    GcsimFinalistOptimizerStatus,
)
from .farming_profile_config import apply_gcsim_screening_runtime_options
from .farming_team_search import FullTeamPhysicalState
from .optimizer_cache import GcsimOptimizerCacheStore
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_product_contracts import (
    GcsimOptimizerOperation,
    GcsimOptimizerOperationRequest,
)
from .optimizer_theoretical_anytime_candidates import (
    gcsim_optimizer_theoretical_team_package_signature,
)
from .optimizer_theoretical_packages import (
    freeze_gcsim_theoretical_pair_packages,
    gcsim_theoretical_pair_domain_sha256,
)
from .optimizer_stat_response import GcsimStatResponseTarget


GCSIM_OPTIMIZER_THEORETICAL_VALIDATION_SCHEMA_VERSION = 2
GCSIM_OPTIMIZER_THEORETICAL_VALIDATION_PLAN_ID = (
    "theoretical_anytime_validation"
)
GCSIM_OPTIMIZER_THEORETICAL_VALIDATION_PLAN_VERSION = 2

TheoreticalValidationProgressCallback = Callable[
    [
        str,
        int,
        int,
        int,
        "GcsimOptimizerTheoreticalValidatedEvaluation | None",
    ],
    None,
]


class GcsimOptimizerTheoreticalValidationError(RuntimeError):
    """Fail-closed theoretical validation error."""


class GcsimOptimizerTheoreticalValidationStatus(str, Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    NO_SUCCESS = "no_success"
    CANCELLED = "cancelled"
    DEADLINE = "deadline"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalValidationPlan:
    max_finalists: int = 6
    top_n: int = 6
    optimizer_worker_count: int = 1
    validation_iterations: int = 200
    rerace_iterations: int = 1000
    max_rerace_candidates: int = 3
    rerace_worker_count: int = 1
    max_parallel_reraces: int = 1
    total_cpu_budget: int = 1
    confidence_sigma: float = 2.0
    relative_rerace_margin: float = 0.0075
    optimizer_timeout_seconds: float = 300.0
    validation_timeout_seconds: float = 180.0
    rerace_timeout_seconds: float = 300.0
    overall_deadline_seconds: float = 900.0
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_VALIDATION_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in (
            "max_finalists",
            "top_n",
            "optimizer_worker_count",
            "validation_iterations",
            "rerace_iterations",
            "max_rerace_candidates",
            "rerace_worker_count",
            "max_parallel_reraces",
            "total_cpu_budget",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise GcsimOptimizerTheoreticalValidationError(
                    f"{field_name} must be a positive integer"
                )
        if self.top_n > self.max_finalists:
            raise GcsimOptimizerTheoreticalValidationError(
                "top_n cannot exceed max_finalists"
            )
        if self.max_finalists > 6:
            raise GcsimOptimizerTheoreticalValidationError(
                "max_finalists must not exceed 6"
            )
        if self.max_rerace_candidates > 3:
            raise GcsimOptimizerTheoreticalValidationError(
                "max_rerace_candidates must not exceed 3"
            )
        if self.validation_iterations != 200:
            raise GcsimOptimizerTheoreticalValidationError(
                "saveable theoretical validation must use 200 iterations"
            )
        if self.rerace_iterations != 1000:
            raise GcsimOptimizerTheoreticalValidationError(
                "close-leader theoretical rerace must use 1000 iterations"
            )
        if self.rerace_iterations <= self.validation_iterations:
            raise GcsimOptimizerTheoreticalValidationError(
                "rerace iterations must exceed validation iterations"
            )
        if (
            self.optimizer_worker_count > self.total_cpu_budget
            or self.rerace_worker_count > self.total_cpu_budget
        ):
            raise GcsimOptimizerTheoreticalValidationError(
                "per-process workers exceed total_cpu_budget"
            )
        # Reuse the scheduler's platform-aware CPU validation.
        GcsimFarmingSchedulerBudget(
            self.max_parallel_reraces,
            self.total_cpu_budget,
            self.overall_deadline_seconds,
        )
        for field_name in (
            "confidence_sigma",
            "optimizer_timeout_seconds",
            "validation_timeout_seconds",
            "rerace_timeout_seconds",
            "overall_deadline_seconds",
        ):
            value = getattr(self, field_name)
            if not isfinite(value) or value <= 0:
                raise GcsimOptimizerTheoreticalValidationError(
                    f"{field_name} must be finite and positive"
                )
        if (
            not isfinite(self.relative_rerace_margin)
            or not 0 <= self.relative_rerace_margin < 0.1
        ):
            raise GcsimOptimizerTheoreticalValidationError(
                "relative_rerace_margin must be in [0, 0.1)"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": GCSIM_OPTIMIZER_THEORETICAL_VALIDATION_PLAN_ID,
            "plan_version": (
                GCSIM_OPTIMIZER_THEORETICAL_VALIDATION_PLAN_VERSION
            ),
            "max_finalists": self.max_finalists,
            "top_n": self.top_n,
            "optimizer_worker_count": self.optimizer_worker_count,
            "validation_iterations": self.validation_iterations,
            "rerace_iterations": self.rerace_iterations,
            "max_rerace_candidates": self.max_rerace_candidates,
            "rerace_worker_count": self.rerace_worker_count,
            "max_parallel_reraces": self.max_parallel_reraces,
            "total_cpu_budget": self.total_cpu_budget,
            "confidence_sigma": self.confidence_sigma,
            "relative_rerace_margin": self.relative_rerace_margin,
            "optimizer_timeout_seconds": self.optimizer_timeout_seconds,
            "validation_timeout_seconds": self.validation_timeout_seconds,
            "rerace_timeout_seconds": self.rerace_timeout_seconds,
            "overall_deadline_seconds": self.overall_deadline_seconds,
            "rerace_policy": "ordinary_exact_optimized_config_only",
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalValidatedEvaluation:
    request_sha256: str
    finalist_outcome: GcsimFinalistOptimizerOutcome
    rerace_result: GcsimFarmingEvaluationResult | None = None
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_VALIDATION_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        _require_sha256(self.request_sha256, "request_sha256")
        if not isinstance(
            self.finalist_outcome,
            GcsimFinalistOptimizerOutcome,
        ):
            raise GcsimOptimizerTheoreticalValidationError(
                "finalist_outcome must be typed"
            )
        if self.finalist_outcome.iterations != 200:
            raise GcsimOptimizerTheoreticalValidationError(
                "validated evaluation requires 200-iteration finalist evidence"
            )
        if self.rerace_result is not None:
            if (
                not isinstance(
                    self.rerace_result,
                    GcsimFarmingEvaluationResult,
                )
                or not self.rerace_result.success
                or self.rerace_result.expected_iterations != 1000
            ):
                raise GcsimOptimizerTheoreticalValidationError(
                    "rerace_result must be successful 1000-iteration evidence"
                )

    @property
    def state(self) -> FullTeamPhysicalState:
        return self.finalist_outcome.state

    @property
    def candidate_identity_sha256(self) -> str:
        return _canonical_sha256(
            {
                "request_sha256": self.request_sha256,
                "physical_state": [
                    list(choice.key) for choice in self.state.choices
                ],
            }
        )

    @property
    def iterations(self) -> int:
        return (
            self.rerace_result.expected_iterations
            if self.rerace_result is not None
            else self.finalist_outcome.iterations
        )

    @property
    def dps_mean(self) -> float:
        if self.rerace_result is not None:
            assert self.rerace_result.summary.dps_mean is not None
            return float(self.rerace_result.summary.dps_mean)
        return float(self.finalist_outcome.dps_mean)

    @property
    def dps_se(self) -> float | None:
        if self.rerace_result is not None:
            return self.rerace_result.summary.dps_se
        return self.finalist_outcome.dps_se

    @property
    def compiled_config_sha256(self) -> str:
        return (
            self.rerace_result.source_config_sha256
            if self.rerace_result is not None
            else self.finalist_outcome.optimized_config_sha256
        )

    @property
    def execution_identity_sha256(self) -> str:
        return (
            self.rerace_result.request_identity_sha256
            if self.rerace_result is not None
            else self.finalist_outcome.cache_identity_sha256
        )

    @property
    def evidence_sha256(self) -> str:
        return _canonical_sha256(
            {
                "request_sha256": self.request_sha256,
                "candidate_identity_sha256": self.candidate_identity_sha256,
                "optimizer_input": (
                    self.finalist_outcome.optimizer_input_sha256
                ),
                "optimized_config": (
                    self.finalist_outcome.optimized_config_sha256
                ),
                "allocation": self.finalist_outcome.allocation_sha256,
                "validation_result": (
                    self.finalist_outcome.result_json_sha256
                ),
                "rerace_request": (
                    None
                    if self.rerace_result is None
                    else self.rerace_result.request_identity_sha256
                ),
                "rerace_source": (
                    None
                    if self.rerace_result is None
                    else self.rerace_result.source_config_sha256
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalValidationResult:
    status: GcsimOptimizerTheoreticalValidationStatus
    evaluations: tuple[GcsimOptimizerTheoreticalValidatedEvaluation, ...]
    finalist_result: GcsimFinalistOptimizerResult
    rerace_results: tuple[GcsimFarmingEvaluationResult, ...]
    requested_rerace_count: int
    evidence_sha256: str
    elapsed_seconds: float
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_VALIDATION_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(
            self.status,
            GcsimOptimizerTheoreticalValidationStatus,
        ):
            raise GcsimOptimizerTheoreticalValidationError(
                "validation status must be typed"
            )
        if not isinstance(
            self.finalist_result,
            GcsimFinalistOptimizerResult,
        ):
            raise GcsimOptimizerTheoreticalValidationError(
                "finalist_result must be typed"
            )
        object.__setattr__(self, "evaluations", tuple(self.evaluations))
        object.__setattr__(self, "rerace_results", tuple(self.rerace_results))
        if self.evaluations != tuple(
            sorted(self.evaluations, key=_evaluation_rank)
        ):
            raise GcsimOptimizerTheoreticalValidationError(
                "validated evaluations must use deterministic DPS order"
            )
        if any(
            not isinstance(
                item,
                GcsimOptimizerTheoreticalValidatedEvaluation,
            )
            for item in self.evaluations
        ):
            raise GcsimOptimizerTheoreticalValidationError(
                "evaluations must be typed"
            )
        if len(
            {
                gcsim_optimizer_theoretical_team_package_signature(
                    item.state
                )
                for item in self.evaluations
            }
        ) != len(self.evaluations):
            raise GcsimOptimizerTheoreticalValidationError(
                "validated Top-N rows must use distinct team package signatures"
            )
        if any(
            not isinstance(item, GcsimFarmingEvaluationResult)
            for item in self.rerace_results
        ):
            raise GcsimOptimizerTheoreticalValidationError(
                "rerace_results must be typed"
            )
        if (
            isinstance(self.requested_rerace_count, bool)
            or not isinstance(self.requested_rerace_count, int)
            or self.requested_rerace_count < 0
            or self.requested_rerace_count != len(self.rerace_results)
        ):
            raise GcsimOptimizerTheoreticalValidationError(
                "requested_rerace_count is incoherent"
            )
        if any(item.iterations < 200 for item in self.evaluations):
            raise GcsimOptimizerTheoreticalValidationError(
                "displayable evaluations require >=200 iterations"
            )
        if (
            self.status
            in {
                GcsimOptimizerTheoreticalValidationStatus.COMPLETED,
                GcsimOptimizerTheoreticalValidationStatus.COMPLETED_WITH_ERRORS,
            }
            and not self.evaluations
        ):
            raise GcsimOptimizerTheoreticalValidationError(
                "completed validation requires a successful evaluation"
            )
        _require_sha256(self.evidence_sha256, "evidence_sha256")
        if not isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise GcsimOptimizerTheoreticalValidationError(
                "elapsed_seconds must be finite and non-negative"
            )

    @property
    def best_found(
        self,
    ) -> GcsimOptimizerTheoreticalValidatedEvaluation | None:
        return self.evaluations[0] if self.evaluations else None


class GcsimOptimizerTheoreticalValidationSession:
    """One-shot owner of theoretical substat optimization and exact rerace."""

    def __init__(
        self,
        request: GcsimOptimizerOperationRequest,
        *,
        engine_context: GcsimOptimizerEngineContext,
        prepared_config_text: str,
        layout_catalog: Mapping[str, Mapping[str, object]],
        finalists: Sequence[FullTeamPhysicalState],
        two_plus_two_packages: Mapping[str, object] | None = None,
        plan: GcsimOptimizerTheoreticalValidationPlan | None = None,
        progress_callback: TheoreticalValidationProgressCallback | None = None,
        cache_store: GcsimOptimizerCacheStore | None = None,
        enable_cache: bool = True,
        finalist_session_factory: Callable[[object], object] | None = None,
        evaluation_session_factory: Callable[[object], object] | None = None,
        environment: Mapping[str, str] | None = None,
        stat_response_target: GcsimStatResponseTarget | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isinstance(request, GcsimOptimizerOperationRequest):
            raise GcsimOptimizerTheoreticalValidationError(
                "request must be typed"
            )
        if request.operation not in {
            GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
            GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO,
        }:
            raise GcsimOptimizerTheoreticalValidationError(
                "validation requires a theoretical operation"
            )
        if (
            request.source_simulation.engine_binding_sha256
            != engine_context.binding_sha256
            or request.source_simulation.catalog_fingerprint
            != engine_context.catalog.source_fingerprint
        ):
            raise GcsimOptimizerTheoreticalValidationError(
                "validation engine binding differs from request"
            )
        if (
            request.source_simulation.prepared_config_sha256
            != _text_sha256(prepared_config_text)
        ):
            raise GcsimOptimizerTheoreticalValidationError(
                "validation config differs from request"
            )
        selected_plan = plan or GcsimOptimizerTheoreticalValidationPlan()
        unique_by_package_signature = {}
        for finalist in finalists:
            if not isinstance(finalist, FullTeamPhysicalState):
                raise GcsimOptimizerTheoreticalValidationError(
                    "validation requires typed physical finalists"
                )
            unique_by_package_signature.setdefault(
                gcsim_optimizer_theoretical_team_package_signature(
                    finalist
                ),
                finalist,
            )
        rows = tuple(unique_by_package_signature.values())[
            : selected_plan.max_finalists
        ]
        if not rows or any(
            not isinstance(item, FullTeamPhysicalState) for item in rows
        ):
            raise GcsimOptimizerTheoreticalValidationError(
                "validation requires typed physical finalists"
            )
        packages = freeze_gcsim_theoretical_pair_packages(
            two_plus_two_packages
        )
        if (
            request.operation
            is GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO
        ) != bool(packages):
            raise GcsimOptimizerTheoreticalValidationError(
                "theoretical operation and pair package domain differ"
            )
        if progress_callback is not None and not callable(progress_callback):
            raise GcsimOptimizerTheoreticalValidationError(
                "progress_callback must be callable or None"
            )
        self.request = request
        self.engine_context = engine_context
        self.prepared_config_text = prepared_config_text
        self.layout_catalog = layout_catalog
        self.finalists = rows
        self.two_plus_two_packages = packages
        self.plan = selected_plan
        self.progress_callback = progress_callback
        self.enable_cache = bool(enable_cache)
        self.cache_store = (
            (cache_store or GcsimOptimizerCacheStore())
            if self.enable_cache
            else None
        )
        self.finalist_session_factory = finalist_session_factory
        self.evaluation_session_factory = evaluation_session_factory
        self.environment = dict(environment or {})
        self.stat_response_target = stat_response_target
        self.clock = clock
        self._cancel_event = Event()
        self._lock = Lock()
        self._active: object | None = None
        self._started = False

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            active = self._active
        if active is not None and callable(getattr(active, "cancel", None)):
            try:
                active.cancel()
            except Exception:
                pass

    def run(self) -> GcsimOptimizerTheoreticalValidationResult:
        with self._lock:
            if self._started:
                raise GcsimOptimizerTheoreticalValidationError(
                    "validation sessions are one-shot"
                )
            self._started = True
        started = self.clock()
        deadline = started + self.plan.overall_deadline_seconds
        budget = GcsimFinalistOptimizerBudget(
            max_finalists=len(self.finalists),
            top_n=min(self.plan.top_n, len(self.finalists)),
            worker_count=self.plan.optimizer_worker_count,
            validation_iterations=self.plan.validation_iterations,
            overall_deadline_seconds=max(deadline - self.clock(), 1e-6),
            optimizer_timeout_seconds=self.plan.optimizer_timeout_seconds,
            simulation_timeout_seconds=self.plan.validation_timeout_seconds,
        )
        finalist_request = GcsimFinalistOptimizerRequest(
            engine_context=self.engine_context,
            prepared_config_text=self.prepared_config_text,
            wearer_ids=self.request.source_simulation.wearer_ids,
            layout_catalog=self.layout_catalog,
            finalists=self.finalists,
            budget=budget,
            optimizer_options={"optimize_er": 0, "fine_tune": 0},
            two_plus_two_packages=self.two_plus_two_packages,
            environment=self.environment,
            gtt_wave_scenario_path=(
                self.stat_response_target.wave_scenario_path
                if self.stat_response_target is not None
                else None
            ),
            target_sha256=(
                self.stat_response_target.target_sha256
                if self.stat_response_target is not None
                else ""
            ),
        )
        observed: list[GcsimOptimizerTheoreticalValidatedEvaluation] = []
        finalist_cache_hits = 0

        def on_finalist(
            completed: int,
            planned: int,
            attempt,
        ) -> None:
            nonlocal finalist_cache_hits
            finalist_cache_hits += int(attempt.cache_hit)
            if attempt.outcome is not None:
                observed.append(
                    GcsimOptimizerTheoreticalValidatedEvaluation(
                        request_sha256=self.request.request_sha256,
                        finalist_outcome=attempt.outcome,
                    )
                )
            self._emit_progress(
                "validate_200",
                completed,
                planned,
                finalist_cache_hits,
                _best(observed),
            )

        if self.finalist_session_factory is None:
            finalist_session = GcsimFinalistOptimizerSession(
                finalist_request,
                cache_store=self.cache_store if self.enable_cache else None,
                completion_callback=on_finalist,
                clock=self.clock,
            )
        else:
            finalist_session = self.finalist_session_factory(
                finalist_request
            )
        self._set_active(finalist_session)
        if self._cancel_event.is_set():
            finalist_session.cancel()
        self._emit_progress(
            "validate_200",
            0,
            len(self.finalists),
            0,
            None,
        )
        try:
            finalist = finalist_session.run()
        finally:
            self._clear_active(finalist_session)
        if not isinstance(finalist, GcsimFinalistOptimizerResult):
            raise GcsimOptimizerTheoreticalValidationError(
                "finalist_session_factory returned an invalid result"
            )
        base = tuple(
            GcsimOptimizerTheoreticalValidatedEvaluation(
                request_sha256=self.request.request_sha256,
                finalist_outcome=outcome,
            )
            for outcome in finalist.all_successful_outcomes
        )
        if not observed or len(observed) != len(base):
            self._emit_progress(
                "validate_200",
                finalist.attempted_count,
                len(self.finalists),
                sum(int(attempt.cache_hit) for attempt in finalist.attempts),
                _best(base),
            )
        status = _status_from_finalist(finalist)
        rerace_results: tuple[GcsimFarmingEvaluationResult, ...] = ()
        evaluations = tuple(sorted(base, key=_evaluation_rank))
        if (
            evaluations
            and status
            not in {
                GcsimOptimizerTheoreticalValidationStatus.CANCELLED,
                GcsimOptimizerTheoreticalValidationStatus.DEADLINE,
            }
            and not self._cancel_event.is_set()
            and self.clock() < deadline
        ):
            close = _close_leaders(
                evaluations,
                limit=self.plan.max_rerace_candidates,
                confidence_sigma=self.plan.confidence_sigma,
                relative_margin=self.plan.relative_rerace_margin,
            )
            if len(close) >= 2:
                rerace_results, batch_status = self._run_rerace(
                    close,
                    finalist_request_sha256=finalist.request_sha256,
                    deadline=deadline,
                )
                replacements = {
                    result.candidate_keys: result
                    for result in rerace_results
                    if result.success
                }
                evaluations = tuple(
                    sorted(
                        (
                            GcsimOptimizerTheoreticalValidatedEvaluation(
                                request_sha256=self.request.request_sha256,
                                finalist_outcome=item.finalist_outcome,
                                rerace_result=replacements.get(
                                    _candidate_keys(item.state)
                                ),
                            )
                            for item in evaluations
                        ),
                        key=_evaluation_rank,
                    )
                )
                status = _merge_batch_status(status, batch_status)
        if (
            status is GcsimOptimizerTheoreticalValidationStatus.COMPLETED
            and any(
                attempt.status is not GcsimFinalistAttemptStatus.PASSED
                for attempt in finalist.attempts
            )
        ):
            status = (
                GcsimOptimizerTheoreticalValidationStatus.COMPLETED_WITH_ERRORS
            )
        evidence_sha256 = _canonical_sha256(
            {
                "schema_version": (
                    GCSIM_OPTIMIZER_THEORETICAL_VALIDATION_SCHEMA_VERSION
                ),
                "request_sha256": self.request.request_sha256,
                "plan_sha256": self.plan.identity_sha256,
                "finalist_request_sha256": finalist.request_sha256,
                "pair_domain_sha256": (
                    gcsim_theoretical_pair_domain_sha256(
                        self.two_plus_two_packages
                    )
                    if self.two_plus_two_packages
                    else ""
                ),
                "status": status.value,
                "evaluations": [
                    item.evidence_sha256 for item in evaluations
                ],
                "rerace_results": [
                    item.request_identity_sha256
                    for item in rerace_results
                ],
            }
        )
        return GcsimOptimizerTheoreticalValidationResult(
            status=status,
            evaluations=evaluations,
            finalist_result=finalist,
            rerace_results=rerace_results,
            requested_rerace_count=len(rerace_results),
            evidence_sha256=evidence_sha256,
            elapsed_seconds=max(self.clock() - started, 0.0),
        )

    def _run_rerace(
        self,
        candidates: tuple[
            GcsimOptimizerTheoreticalValidatedEvaluation,
            ...,
        ],
        *,
        finalist_request_sha256: str,
        deadline: float,
    ) -> tuple[
        tuple[GcsimFarmingEvaluationResult, ...],
        GcsimFarmingBatchStatus,
    ]:
        context_sha256 = _canonical_sha256(
            {
                "request_sha256": self.request.request_sha256,
                "plan_sha256": self.plan.identity_sha256,
                "finalist_request_sha256": finalist_request_sha256,
                "rerace_iterations": self.plan.rerace_iterations,
            }
        )
        requests = tuple(
            prepare_bound_gcsim_farming_joint_evaluation(
                engine_context=self.engine_context,
                candidate_keys=_candidate_keys(item.state),
                config_text=apply_gcsim_screening_runtime_options(
                    item.finalist_outcome.optimized_config_text,
                    iterations=self.plan.rerace_iterations,
                    workers=self.plan.rerace_worker_count,
                ),
                comparison_context_sha256=context_sha256,
                investment_signature=(
                    "theoretical-anytime/exact-optimized-config-v1"
                ),
                worker_count=self.plan.rerace_worker_count,
                timeout_seconds=self.plan.rerace_timeout_seconds,
                environment=self.environment,
                synthetic_set_keys=tuple(self.two_plus_two_packages),
                gtt_wave_scenario_path=(
                    self.stat_response_target.wave_scenario_path
                    if self.stat_response_target is not None
                    else None
                ),
                target_sha256=(
                    self.stat_response_target.target_sha256
                    if self.stat_response_target is not None
                    else ""
                ),
            )
            for item in candidates
        )
        completed_results: dict[int, GcsimFarmingEvaluationResult] = {}

        def on_completion(
            completed: int,
            planned: int,
            index: int,
            result: GcsimFarmingEvaluationResult,
        ) -> None:
            completed_results[index] = result
            live = tuple(
                GcsimOptimizerTheoreticalValidatedEvaluation(
                    request_sha256=self.request.request_sha256,
                    finalist_outcome=item.finalist_outcome,
                    rerace_result=(
                        completed_results.get(row_index)
                        if completed_results.get(row_index) is not None
                        and completed_results[row_index].success
                        else None
                    ),
                )
                for row_index, item in enumerate(candidates)
            )
            self._emit_progress(
                "rerace_1000",
                completed,
                planned,
                sum(
                    int(item.cache_hit)
                    for item in completed_results.values()
                ),
                _best(live),
            )

        self._emit_progress(
            "rerace_1000",
            0,
            len(requests),
            0,
            _best(candidates),
        )
        scheduler = GcsimFarmingEvaluationScheduler(
            requests,
            GcsimFarmingSchedulerBudget(
                self.plan.max_parallel_reraces,
                self.plan.total_cpu_budget,
                max(deadline - self.clock(), 1e-6),
            ),
            cache_store=self.cache_store,
            enable_cache=self.enable_cache,
            session_factory=self.evaluation_session_factory,
            completion_callback=on_completion,
        )
        self._set_active(scheduler)
        if self._cancel_event.is_set():
            scheduler.cancel()
        try:
            batch = scheduler.run()
        finally:
            self._clear_active(scheduler)
        return batch.results, batch.status

    def _emit_progress(
        self,
        stage: str,
        completed: int,
        planned: int,
        cache_hits: int,
        leader: GcsimOptimizerTheoreticalValidatedEvaluation | None,
    ) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(
                stage,
                completed,
                planned,
                cache_hits,
                leader,
            )
        except Exception:
            pass

    def _set_active(self, value: object) -> None:
        with self._lock:
            self._active = value

    def _clear_active(self, value: object) -> None:
        with self._lock:
            if self._active is value:
                self._active = None


def run_gcsim_optimizer_theoretical_anytime_validation(
    request: GcsimOptimizerOperationRequest,
    **kwargs,
) -> GcsimOptimizerTheoreticalValidationResult:
    return GcsimOptimizerTheoreticalValidationSession(
        request,
        **kwargs,
    ).run()


def _candidate_keys(
    state: FullTeamPhysicalState,
) -> tuple[tuple[str, str, str, str, str], ...]:
    return tuple(
        (
            choice.wearer_id,
            choice.set_key,
            choice.main_stat_layout_id,
            choice.offpiece_slot,
            "optimized",
        )
        for choice in state.choices
    )


def _close_leaders(
    rows: Sequence[GcsimOptimizerTheoreticalValidatedEvaluation],
    *,
    limit: int,
    confidence_sigma: float,
    relative_margin: float,
) -> tuple[GcsimOptimizerTheoreticalValidatedEvaluation, ...]:
    ranked = tuple(sorted(rows, key=_evaluation_rank))
    if len(ranked) < 2:
        return ()
    leader = ranked[0]
    retained = [leader]
    for row in ranked[1:]:
        if leader.dps_se is None or row.dps_se is None:
            retained.append(row)
        else:
            allowed = (
                confidence_sigma * hypot(leader.dps_se, row.dps_se)
                + abs(leader.dps_mean) * relative_margin
            )
            if leader.dps_mean - row.dps_mean <= allowed:
                retained.append(row)
        if len(retained) >= limit:
            break
    return tuple(retained) if len(retained) >= 2 else ()


def _best(
    rows: Sequence[GcsimOptimizerTheoreticalValidatedEvaluation],
) -> GcsimOptimizerTheoreticalValidatedEvaluation | None:
    return min(rows, key=_evaluation_rank) if rows else None


def _evaluation_rank(
    row: GcsimOptimizerTheoreticalValidatedEvaluation,
) -> tuple[float, str]:
    return -row.dps_mean, row.candidate_identity_sha256


def _status_from_finalist(
    result: GcsimFinalistOptimizerResult,
) -> GcsimOptimizerTheoreticalValidationStatus:
    return {
        GcsimFinalistOptimizerStatus.BEST_FOUND: (
            GcsimOptimizerTheoreticalValidationStatus.COMPLETED
        ),
        GcsimFinalistOptimizerStatus.NO_SUCCESS: (
            GcsimOptimizerTheoreticalValidationStatus.NO_SUCCESS
        ),
        GcsimFinalistOptimizerStatus.CANCELLED: (
            GcsimOptimizerTheoreticalValidationStatus.CANCELLED
        ),
        GcsimFinalistOptimizerStatus.DEADLINE: (
            GcsimOptimizerTheoreticalValidationStatus.DEADLINE
        ),
    }[result.status]


def _merge_batch_status(
    current: GcsimOptimizerTheoreticalValidationStatus,
    batch: GcsimFarmingBatchStatus,
) -> GcsimOptimizerTheoreticalValidationStatus:
    if batch is GcsimFarmingBatchStatus.CANCELLED:
        return GcsimOptimizerTheoreticalValidationStatus.CANCELLED
    if batch is GcsimFarmingBatchStatus.DEADLINE_REACHED:
        return GcsimOptimizerTheoreticalValidationStatus.DEADLINE
    if batch is GcsimFarmingBatchStatus.COMPLETED_WITH_ERRORS:
        return GcsimOptimizerTheoreticalValidationStatus.COMPLETED_WITH_ERRORS
    return current


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise GcsimOptimizerTheoreticalValidationError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


def _require_schema(value: int) -> None:
    if value != GCSIM_OPTIMIZER_THEORETICAL_VALIDATION_SCHEMA_VERSION:
        raise GcsimOptimizerTheoreticalValidationError(
            "unsupported theoretical validation schema"
        )


__all__ = [
    "GCSIM_OPTIMIZER_THEORETICAL_VALIDATION_PLAN_ID",
    "GCSIM_OPTIMIZER_THEORETICAL_VALIDATION_PLAN_VERSION",
    "GCSIM_OPTIMIZER_THEORETICAL_VALIDATION_SCHEMA_VERSION",
    "GcsimOptimizerTheoreticalValidatedEvaluation",
    "GcsimOptimizerTheoreticalValidationError",
    "GcsimOptimizerTheoreticalValidationPlan",
    "GcsimOptimizerTheoreticalValidationResult",
    "GcsimOptimizerTheoreticalValidationSession",
    "GcsimOptimizerTheoreticalValidationStatus",
    "TheoreticalValidationProgressCallback",
    "run_gcsim_optimizer_theoretical_anytime_validation",
]
