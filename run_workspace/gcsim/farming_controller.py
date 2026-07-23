"""End-to-end cheap 4p screening and joint-team composition boundary.

This controller deliberately stops before the expensive upstream substat
optimizer.  It proves and executes every requested one-wearer set/layout/profile
probe, performs recall-first survivor selection, and hands those survivors to
the whole-team coordinate/beam/pair composer.  A successful result is therefore
``best_found`` screening evidence, not a final theoretical set ranking.

The controller is synchronous and intended to run outside the UI thread.  Its
``cancel`` method is thread-safe and forwards cancellation to the currently
active evaluator scheduler or full-team simulator.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
import math
from threading import Event, Lock
from time import monotonic
from types import MappingProxyType
from typing import Protocol

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
    GcsimFarmingFullTeamBatchSimulator,
    GcsimFarmingPipelineError,
    GcsimFarmingScreeningFidelity,
    LayoutCatalog,
    SchedulerFactory,
    materialize_gcsim_one_wearer_candidate,
)
from .farming_profile_config import GCSIM_BALANCED_REFERENCE_WEIGHTS
from .farming_search import (
    CandidateEvaluation,
    FourPieceCandidateCoverage,
    ScreeningSurvivorBudget,
    SearchWearer,
    SetProfileCandidate,
    StatProfileBank,
    StatWeight,
    SurvivorSelectionResult,
    WearerProfileSelection,
    build_four_piece_candidate_coverage,
    select_screening_survivors,
)
from .farming_team_search import (
    TEAM_SEARCH_CANCELLED,
    TEAM_SEARCH_DEADLINE_REACHED,
    TEAM_SEARCH_DOMAIN_EXHAUSTED,
    FullTeamCandidatePool,
    FullTeamComposerBudget,
    FullTeamComposerRequest,
    FullTeamComposerResult,
    compose_full_team_four_piece_states,
)
from .optimizer_cache import GcsimOptimizerCacheStore
from .optimizer_engine_context import GcsimOptimizerEngineContext


class GcsimFourPieceSearchError(RuntimeError):
    """Raised when the high-level screening contract is inconsistent."""


class GcsimFourPieceSearchStatus(str, Enum):
    COMPLETED = "completed"
    BEST_FOUND = "best_found"
    PARTIAL_SCREEN = "partial_screen"
    CANCELLED = "cancelled"
    DEADLINE_REACHED = "deadline_reached"
    NO_SCREENING_RESULT = "no_screening_result"
    NO_TEAM_RESULT = "no_team_result"


@dataclass(frozen=True, slots=True)
class GcsimFourPieceScreeningIssue:
    candidate: SetProfileCandidate
    status: str
    error: str = ""


@dataclass(frozen=True, slots=True)
class GcsimFourPieceSearchRequest:
    """Frozen inputs and budgets for one cheap theoretical 4p race."""

    engine_context: GcsimOptimizerEngineContext
    prepared_config_text: str
    wearer_ids: tuple[str, ...]
    layout_catalog: LayoutCatalog
    profile_bank: StatProfileBank
    wearer_profile_selections: tuple[WearerProfileSelection, ...]
    baseline_states: tuple[SetProfileCandidate, ...]
    fidelity: GcsimFarmingScreeningFidelity
    screening_scheduler_budget: GcsimFarmingSchedulerBudget
    team_scheduler_budget: GcsimFarmingSchedulerBudget
    survivor_budget: ScreeningSurvivorBudget
    composer_budget: FullTeamComposerBudget
    overall_deadline_seconds: float
    screening_candidate_timeout_seconds: float
    reference_weights: tuple[StatWeight, ...] = GCSIM_BALANCED_REFERENCE_WEIGHTS
    environment: Mapping[str, str] = field(default_factory=dict, repr=False)
    environment_is_frozen: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "wearer_ids", tuple(self.wearer_ids))
        object.__setattr__(
            self,
            "wearer_profile_selections",
            tuple(self.wearer_profile_selections),
        )
        object.__setattr__(self, "baseline_states", tuple(self.baseline_states))
        object.__setattr__(self, "reference_weights", tuple(self.reference_weights))
        if not isinstance(self.layout_catalog, Mapping):
            raise GcsimFourPieceSearchError("layout_catalog must be a mapping")
        try:
            frozen_layout_catalog = MappingProxyType(
                {
                    str(wearer): MappingProxyType(dict(entries))
                    for wearer, entries in self.layout_catalog.items()
                }
            )
        except (TypeError, ValueError) as exc:
            raise GcsimFourPieceSearchError(
                "layout_catalog values must be mappings"
            ) from exc
        object.__setattr__(self, "layout_catalog", frozen_layout_catalog)
        if not isinstance(self.environment, Mapping):
            raise GcsimFourPieceSearchError("environment must be a mapping")
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
            raise GcsimFourPieceSearchError(str(exc)) from exc
        object.__setattr__(
            self,
            "environment",
            MappingProxyType(frozen_environment),
        )
        object.__setattr__(self, "environment_is_frozen", True)
        for field_name in (
            "overall_deadline_seconds",
            "screening_candidate_timeout_seconds",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise GcsimFourPieceSearchError(
                    f"{field_name} must be finite and positive"
                )


@dataclass(frozen=True, slots=True)
class GcsimFourPieceSearchResult:
    status: GcsimFourPieceSearchStatus
    stop_reason: str
    coverage: FourPieceCandidateCoverage
    elapsed_seconds: float
    screening_batch: GcsimFarmingBatchResult | None = None
    screening_evaluations: tuple[CandidateEvaluation, ...] = ()
    screening_issues: tuple[GcsimFourPieceScreeningIssue, ...] = ()
    survivor_selection: SurvivorSelectionResult | None = None
    candidate_pools: tuple[FullTeamCandidatePool, ...] = ()
    composition: FullTeamComposerResult | None = None
    materialized_request_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "screening_evaluations",
            tuple(self.screening_evaluations),
        )
        object.__setattr__(self, "screening_issues", tuple(self.screening_issues))
        object.__setattr__(self, "candidate_pools", tuple(self.candidate_pools))
        if not isinstance(self.status, GcsimFourPieceSearchStatus):
            raise ValueError("status must be a GcsimFourPieceSearchStatus")
        if not isinstance(self.coverage, FourPieceCandidateCoverage):
            raise ValueError("coverage must be a FourPieceCandidateCoverage")
        if not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must be finite and non-negative")
        if (
            isinstance(self.materialized_request_count, bool)
            or not isinstance(self.materialized_request_count, int)
            or self.materialized_request_count < 0
            or self.materialized_request_count > len(self.coverage.candidates)
        ):
            raise ValueError("materialized_request_count is out of range")
        if self.screening_batch is not None and len(
            self.screening_batch.results
        ) != self.materialized_request_count:
            raise ValueError("screening batch size differs from materialized requests")
        coverage_keys = {candidate.key for candidate in self.coverage.candidates}
        if any(
            evaluation.candidate.key not in coverage_keys
            for evaluation in self.screening_evaluations
        ) or any(issue.candidate.key not in coverage_keys for issue in self.screening_issues):
            raise ValueError("screening evidence contains a candidate outside coverage")
        if len(
            {
                evaluation.candidate.key
                for evaluation in self.screening_evaluations
            }
        ) != len(self.screening_evaluations):
            raise ValueError("screening evaluations contain duplicate candidates")
        if self.status in {
            GcsimFourPieceSearchStatus.COMPLETED,
            GcsimFourPieceSearchStatus.BEST_FOUND,
        } and (
            self.composition is None
            or self.best_found is None
            or not self.complete_screening_coverage
        ):
            raise ValueError(
                "successful search status requires complete screen and composition"
            )
        if self.status is GcsimFourPieceSearchStatus.PARTIAL_SCREEN and not (
            self.screening_issues
        ):
            raise ValueError("partial_screen status requires screening issues")
        if self.composition is not None and not self.candidate_pools:
            raise ValueError("composition requires candidate pools")

    @property
    def best_found(self):
        if self.composition is None:
            return None
        return self.composition.best_found

    @property
    def physical_finalists(self):
        if self.composition is None:
            return ()
        return self.composition.physical_finalists

    @property
    def complete_screening_coverage(self) -> bool:
        return (
            len(self.screening_evaluations) == len(self.coverage.candidates)
            and not self.screening_issues
        )


class _Cancellable(Protocol):
    def cancel(self) -> None: ...


class GcsimFourPieceSearchSession:
    """One-shot orchestration session for cheap 4p screening/composition."""

    def __init__(
        self,
        request: GcsimFourPieceSearchRequest,
        *,
        cache_store: GcsimOptimizerCacheStore | None = None,
        enable_cache: bool = True,
        session_factory: FarmingSessionFactory | None = None,
        scheduler_factory: SchedulerFactory | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isinstance(request, GcsimFourPieceSearchRequest):
            raise GcsimFourPieceSearchError(
                "request must be a GcsimFourPieceSearchRequest"
            )
        self.request = request
        self._cache_store = cache_store
        self._enable_cache = bool(enable_cache)
        self._session_factory = session_factory
        self._external_scheduler_factory = scheduler_factory
        self._clock = clock
        self._cancel_event = Event()
        self._lock = Lock()
        self._active: _Cancellable | None = None
        self._started = False

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            active = self._active
        if active is not None:
            active.cancel()

    def run(self) -> GcsimFourPieceSearchResult:
        with self._lock:
            if self._started:
                raise RuntimeError("GcsimFourPieceSearchSession instances are one-shot")
            self._started = True
        started = self._clock()
        deadline = started + self.request.overall_deadline_seconds
        coverage = self._build_and_validate_coverage()

        if self._cancel_event.is_set():
            return self._terminal(
                coverage,
                started,
                GcsimFourPieceSearchStatus.CANCELLED,
                "cancelled_before_materialization",
            )

        proof_by_key = {}
        logical_by_key: dict[tuple, list[SetProfileCandidate]] = {}
        probe_key_by_candidate_key: dict[tuple[str, str, str, str, str], tuple] = {}
        for candidate in coverage.candidates:
            if self._cancel_event.is_set():
                return self._terminal(
                    coverage,
                    started,
                    GcsimFourPieceSearchStatus.CANCELLED,
                    "cancelled_during_materialization",
                    materialized_request_count=len(proof_by_key),
                )
            if self._clock() >= deadline:
                return self._terminal(
                    coverage,
                    started,
                    GcsimFourPieceSearchStatus.DEADLINE_REACHED,
                    "deadline_during_materialization",
                    materialized_request_count=len(proof_by_key),
                )
            baselines = tuple(
                baseline
                for baseline in self.request.baseline_states
                if baseline.state.wearer_id != candidate.state.wearer_id
            )
            proof = materialize_gcsim_one_wearer_candidate(
                self.request.prepared_config_text,
                candidate=candidate,
                frozen_baseline_states=baselines,
                wearer_ids=self.request.wearer_ids,
                layout_catalog=self.request.layout_catalog,
                profile_bank=self.request.profile_bank,
                engine_context=self.request.engine_context,
                fidelity=self.request.fidelity,
                reference_weights=self.request.reference_weights,
                environment=self.request.environment,
                environment_is_frozen=True,
            )
            key = proof.candidate_keys
            logical_by_key.setdefault(key, []).append(candidate)
            probe_key_by_candidate_key[candidate.key] = key
            previous = proof_by_key.setdefault(key, proof)
            if (
                previous.config_text != proof.config_text
                or previous.evaluation_context_sha256
                != proof.evaluation_context_sha256
            ):
                raise GcsimFourPieceSearchError(
                    "one joint probe key materialized to inconsistent configs"
                )

        evaluator_requests = tuple(
            proof.build_evaluator_request(
                engine_context=self.request.engine_context,
                timeout_seconds=self.request.screening_candidate_timeout_seconds,
                environment=self.request.environment,
            )
            for proof in proof_by_key.values()
        )
        remaining = deadline - self._clock()
        if remaining <= 0:
            return self._terminal(
                coverage,
                started,
                GcsimFourPieceSearchStatus.DEADLINE_REACHED,
                "deadline_before_screening",
                materialized_request_count=len(evaluator_requests),
            )
        screen_budget = replace(
            self.request.screening_scheduler_budget,
            overall_deadline_seconds=min(
                self.request.screening_scheduler_budget.overall_deadline_seconds,
                remaining,
            ),
        )
        scheduler = self._make_scheduler(evaluator_requests, screen_budget)
        self._set_active(scheduler)
        try:
            if self._cancel_event.is_set():
                scheduler.cancel()
            screening_batch = scheduler.run()
        finally:
            self._clear_active(scheduler)
        self._validate_batch(evaluator_requests, screening_batch)

        result_by_key = {
            result.candidate_keys: result
            for result in screening_batch.results
        }
        evaluations: list[CandidateEvaluation] = []
        issues: list[GcsimFourPieceScreeningIssue] = []
        investment_signatures = {
            proof.investment_signature for proof in proof_by_key.values()
        }
        if len(investment_signatures) != 1:
            raise GcsimFourPieceSearchError(
                "materialized screening probes do not share one investment signature"
            )
        investment_signature = next(iter(investment_signatures))
        for candidate in coverage.candidates:
            matching_result = result_by_key[
                probe_key_by_candidate_key[candidate.key]
            ]
            if matching_result.success:
                evaluations.append(
                    CandidateEvaluation(
                        candidate=candidate,
                        expected_dps=float(matching_result.summary.dps_mean),
                        standard_error=matching_result.summary.dps_se,
                        investment_signature=investment_signature,
                    )
                )
            else:
                issues.append(
                    GcsimFourPieceScreeningIssue(
                        candidate=candidate,
                        status=matching_result.status.value,
                        error=matching_result.error,
                    )
                )

        common = dict(
            coverage=coverage,
            started=started,
            screening_batch=screening_batch,
            screening_evaluations=tuple(evaluations),
            screening_issues=tuple(issues),
            materialized_request_count=len(evaluator_requests),
        )
        if self._cancel_event.is_set() or screening_batch.status is GcsimFarmingBatchStatus.CANCELLED:
            return self._terminal(
                status=GcsimFourPieceSearchStatus.CANCELLED,
                stop_reason="screening_cancelled",
                **common,
            )
        if screening_batch.status is GcsimFarmingBatchStatus.DEADLINE_REACHED:
            return self._terminal(
                status=GcsimFourPieceSearchStatus.DEADLINE_REACHED,
                stop_reason="screening_deadline_reached",
                **common,
            )
        if issues:
            return self._terminal(
                status=(
                    GcsimFourPieceSearchStatus.PARTIAL_SCREEN
                    if evaluations
                    else GcsimFourPieceSearchStatus.NO_SCREENING_RESULT
                ),
                stop_reason="screening_incomplete",
                **common,
            )

        survivor_selection = select_screening_survivors(
            evaluations,
            self.request.survivor_budget,
            required_profile_ids_by_wearer={
                selection.wearer_id: selection.required_profile_ids
                for selection in coverage.wearer_profile_selections
                if selection.required_profile_ids
            },
        )
        survivors_by_wearer = {
            wearer: tuple(
                survivor
                for survivor in survivor_selection.survivors
                if survivor.evaluation.candidate.state.wearer_id == wearer
            )
            for wearer in self.request.wearer_ids
        }
        if any(not rows for rows in survivors_by_wearer.values()):
            return self._terminal(
                status=GcsimFourPieceSearchStatus.NO_TEAM_RESULT,
                stop_reason="survivor_pool_missing_wearer",
                survivor_selection=survivor_selection,
                **common,
            )
        candidate_pools = tuple(
            FullTeamCandidatePool(
                wearer_id=wearer,
                survivors=survivors_by_wearer[wearer],
            )
            for wearer in self.request.wearer_ids
        )

        remaining = deadline - self._clock()
        if remaining <= 0:
            return self._terminal(
                status=GcsimFourPieceSearchStatus.DEADLINE_REACHED,
                stop_reason="deadline_before_team_composition",
                survivor_selection=survivor_selection,
                candidate_pools=candidate_pools,
                **common,
            )
        team_budget = replace(
            self.request.team_scheduler_budget,
            overall_deadline_seconds=min(
                self.request.team_scheduler_budget.overall_deadline_seconds,
                remaining,
            ),
        )
        simulator = GcsimFarmingFullTeamBatchSimulator(
            engine_context=self.request.engine_context,
            prepared_config_text=self.request.prepared_config_text,
            wearer_ids=self.request.wearer_ids,
            layout_catalog=self.request.layout_catalog,
            profile_bank=self.request.profile_bank,
            reference_weights=self.request.reference_weights,
            fidelity=self.request.fidelity,
            scheduler_budget=team_budget,
            environment=self.request.environment,
            environment_is_frozen=True,
            cache_store=self._cache_store,
            enable_cache=self._enable_cache,
            session_factory=self._session_factory,
            scheduler_factory=self._external_scheduler_factory,
        )
        remaining = deadline - self._clock()
        if remaining <= 0:
            simulator.cancel()
            return self._terminal(
                status=GcsimFourPieceSearchStatus.DEADLINE_REACHED,
                stop_reason="deadline_during_team_simulator_construction",
                survivor_selection=survivor_selection,
                candidate_pools=candidate_pools,
                **common,
            )
        composer_budget = replace(
            self.request.composer_budget,
            max_seconds=min(self.request.composer_budget.max_seconds, remaining),
        )
        composer_request = FullTeamComposerRequest(
            evaluation_context_sha256=simulator.evaluation_context_sha256,
            wearer_ids=self.request.wearer_ids,
            candidate_pools=candidate_pools,
            budget=composer_budget,
        )
        self._set_active(simulator)
        try:
            if self._cancel_event.is_set():
                simulator.cancel()
            composition = compose_full_team_four_piece_states(
                composer_request,
                simulator,
                is_cancelled=self._cancel_event.is_set,
                clock=self._clock,
            )
        finally:
            self._clear_active(simulator)

        if composition.stop_reason == TEAM_SEARCH_CANCELLED:
            status = GcsimFourPieceSearchStatus.CANCELLED
        elif (
            composition.stop_reason == TEAM_SEARCH_DEADLINE_REACHED
            or self._clock() >= deadline
        ):
            status = GcsimFourPieceSearchStatus.DEADLINE_REACHED
        elif composition.best_found is None:
            status = GcsimFourPieceSearchStatus.NO_TEAM_RESULT
        elif composition.stop_reason == TEAM_SEARCH_DOMAIN_EXHAUSTED:
            status = GcsimFourPieceSearchStatus.COMPLETED
        else:
            status = GcsimFourPieceSearchStatus.BEST_FOUND
        stop_reason = f"team/{composition.stop_reason}"
        if (
            status is GcsimFourPieceSearchStatus.DEADLINE_REACHED
            and composition.stop_reason != TEAM_SEARCH_DEADLINE_REACHED
        ):
            stop_reason = "team/overall_deadline_reached"
        return self._terminal(
            status=status,
            stop_reason=stop_reason,
            survivor_selection=survivor_selection,
            candidate_pools=candidate_pools,
            composition=composition,
            **common,
        )

    def _build_and_validate_coverage(self) -> FourPieceCandidateCoverage:
        request = self.request
        if not isinstance(request.engine_context, GcsimOptimizerEngineContext):
            raise GcsimFourPieceSearchError("engine_context is invalid")
        if not request.engine_context.trusted:
            raise GcsimFourPieceSearchError(
                "4p search requires a resealed trusted engine context"
            )
        if not request.wearer_ids or len(request.wearer_ids) > 4:
            raise GcsimFourPieceSearchError(
                "wearer_ids must contain one to four values"
            )
        if tuple(item.state.wearer_id for item in request.baseline_states) != request.wearer_ids:
            raise GcsimFourPieceSearchError(
                "baseline states must cover wearers exactly in canonical order"
            )
        if request.survivor_budget.max_survivors < len(request.wearer_ids):
            raise GcsimFourPieceSearchError(
                "survivor max must allow at least one candidate per wearer"
            )
        if request.survivor_budget.wearer_coverage_slots < len(request.wearer_ids):
            raise GcsimFourPieceSearchError(
                "wearer coverage slots must reserve at least one row per wearer"
            )
        if request.fidelity.worker_count > request.screening_scheduler_budget.total_cpu_budget:
            raise GcsimFourPieceSearchError(
                "screening fidelity workers exceed screening CPU budget"
            )
        if request.fidelity.worker_count > request.team_scheduler_budget.total_cpu_budget:
            raise GcsimFourPieceSearchError(
                "screening fidelity workers exceed team CPU budget"
            )
        try:
            return build_four_piece_candidate_coverage(
                tuple(SearchWearer(wearer) for wearer in request.wearer_ids),
                request.engine_context.catalog.sets,
                request.profile_bank,
                main_stat_layout_ids_by_wearer={
                    wearer: tuple(request.layout_catalog[wearer])
                    for wearer in request.wearer_ids
                },
                wearer_profile_selections=request.wearer_profile_selections,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GcsimFourPieceSearchError(str(exc)) from exc

    def _make_scheduler(
        self,
        requests: tuple[GcsimFarmingEvaluationRequest, ...],
        budget: GcsimFarmingSchedulerBudget,
    ):
        if self._external_scheduler_factory is not None:
            return self._external_scheduler_factory(requests, budget)
        return GcsimFarmingEvaluationScheduler(
            requests,
            budget,
            cache_store=self._cache_store,
            enable_cache=self._enable_cache,
            session_factory=self._session_factory,
        )

    def _set_active(self, value: _Cancellable) -> None:
        with self._lock:
            if self._active is not None:
                raise GcsimFourPieceSearchError("another search stage is already active")
            self._active = value

    def _clear_active(self, value: _Cancellable) -> None:
        with self._lock:
            if self._active is value:
                self._active = None

    @staticmethod
    def _validate_batch(
        requests: tuple[GcsimFarmingEvaluationRequest, ...],
        batch: GcsimFarmingBatchResult,
    ) -> None:
        if not isinstance(batch, GcsimFarmingBatchResult):
            raise GcsimFourPieceSearchError("scheduler returned a non-typed batch")
        if len(batch.results) != len(requests):
            raise GcsimFourPieceSearchError(
                "scheduler did not return one result per screening request"
            )
        for request, result in zip(requests, batch.results, strict=True):
            identity = request.identity
            if (
                result.candidate_keys != request.candidate_keys
                or result.request_identity_sha256 != identity.identity_sha256
                or result.cache_key != request.cache_identity.cache_key
                or result.comparison_context_sha256
                != request.comparison_context_sha256
                or result.expected_iterations != request.expected_iterations
                or result.engine_binding_sha256 != identity.engine_binding_sha256
                or (
                    result.artifact_sha256 != identity.artifact_sha256
                    and result.status
                    is not GcsimFarmingEvaluationStatus.ARTIFACT_IDENTITY_MISMATCH
                )
                or result.source_config_sha256 != identity.source_config_sha256
            ):
                raise GcsimFourPieceSearchError(
                    "screening result provenance/order does not match its request"
                )

    def _terminal(
        self,
        coverage: FourPieceCandidateCoverage,
        started: float,
        status: GcsimFourPieceSearchStatus,
        stop_reason: str,
        **kwargs,
    ) -> GcsimFourPieceSearchResult:
        return GcsimFourPieceSearchResult(
            status=status,
            stop_reason=stop_reason,
            coverage=coverage,
            elapsed_seconds=max(self._clock() - started, 0.0),
            **kwargs,
        )


def run_gcsim_four_piece_search(
    request: GcsimFourPieceSearchRequest,
    **session_options,
) -> GcsimFourPieceSearchResult:
    """Convenience wrapper for a one-shot synchronous controller session."""

    return GcsimFourPieceSearchSession(request, **session_options).run()


__all__ = [
    "GcsimFourPieceScreeningIssue",
    "GcsimFourPieceSearchError",
    "GcsimFourPieceSearchRequest",
    "GcsimFourPieceSearchResult",
    "GcsimFourPieceSearchSession",
    "GcsimFourPieceSearchStatus",
    "run_gcsim_four_piece_search",
]
