"""Top-level cheap 4p advisor: response scan followed by set/team search.

This is the first production-callable boundary that starts from a prepared
team/rotation plus explicit generic search inputs without requiring the caller
to guess per-character stat profiles.  It remains a heuristic 4p screening
stage: caller-provided bounded main-stat layouts and later expensive
``substatOptim`` finalist validation are separate contracts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
import math
from threading import Event, Lock
from time import monotonic

from .farming_controller import (
    GcsimFourPieceSearchRequest,
    GcsimFourPieceSearchResult,
    GcsimFourPieceSearchSession,
    GcsimFourPieceSearchStatus,
)
from .farming_evaluator import FarmingSessionFactory, GcsimFarmingSchedulerBudget
from .farming_pipeline import SchedulerFactory
from .farming_response_scan import (
    GcsimResponseScanRequest,
    GcsimResponseScanResult,
    GcsimResponseScanSession,
    GcsimResponseScanStatus,
)
from .farming_search import ScreeningSurvivorBudget
from .farming_team_search import FullTeamComposerBudget
from .optimizer_cache import GcsimOptimizerCacheStore


class GcsimFourPieceAdvisorError(RuntimeError):
    """Raised when combined advisor inputs are inconsistent."""


class GcsimFourPieceAdvisorStatus(str, Enum):
    BEST_FOUND = "best_found"
    CANCELLED = "cancelled"
    DEADLINE_REACHED = "deadline_reached"
    RESPONSE_FAILED = "response_failed"
    SEARCH_FAILED = "search_failed"


@dataclass(frozen=True, slots=True)
class GcsimFourPieceAdvisorRequest:
    response_scan_request: GcsimResponseScanRequest
    screening_scheduler_budget: GcsimFarmingSchedulerBudget
    team_scheduler_budget: GcsimFarmingSchedulerBudget
    survivor_budget: ScreeningSurvivorBudget
    composer_budget: FullTeamComposerBudget
    overall_deadline_seconds: float
    screening_candidate_timeout_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.response_scan_request, GcsimResponseScanRequest):
            raise GcsimFourPieceAdvisorError(
                "response_scan_request must be a GcsimResponseScanRequest"
            )
        for field_name in (
            "overall_deadline_seconds",
            "screening_candidate_timeout_seconds",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise GcsimFourPieceAdvisorError(
                    f"{field_name} must be finite and positive"
                )


@dataclass(frozen=True, slots=True)
class GcsimFourPieceAdvisorResult:
    status: GcsimFourPieceAdvisorStatus
    stop_reason: str
    elapsed_seconds: float
    response_scan: GcsimResponseScanResult
    search: GcsimFourPieceSearchResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, GcsimFourPieceAdvisorStatus):
            raise ValueError("status must be a GcsimFourPieceAdvisorStatus")
        if not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must be finite and non-negative")
        if not isinstance(self.response_scan, GcsimResponseScanResult):
            raise ValueError("response_scan must be a GcsimResponseScanResult")
        if self.status is GcsimFourPieceAdvisorStatus.BEST_FOUND:
            if (
                not self.response_scan.completed
                or self.search is None
                or self.search.best_found is None
            ):
                raise ValueError(
                    "best_found advisor result requires response and search evidence"
                )
        if self.status is GcsimFourPieceAdvisorStatus.RESPONSE_FAILED and self.search is not None:
            raise ValueError("response_failed result cannot carry a search result")

    @property
    def best_found(self):
        return None if self.search is None else self.search.best_found


class GcsimFourPieceAdvisorSession:
    """One-shot combined session with cancellation forwarded across stages."""

    def __init__(
        self,
        request: GcsimFourPieceAdvisorRequest,
        *,
        cache_store: GcsimOptimizerCacheStore | None = None,
        enable_cache: bool = True,
        session_factory: FarmingSessionFactory | None = None,
        scheduler_factory: SchedulerFactory | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isinstance(request, GcsimFourPieceAdvisorRequest):
            raise GcsimFourPieceAdvisorError(
                "request must be a GcsimFourPieceAdvisorRequest"
            )
        self.request = request
        self._cache_store = cache_store
        self._enable_cache = bool(enable_cache)
        self._session_factory = session_factory
        self._scheduler_factory = scheduler_factory
        self._clock = clock
        self._cancel_event = Event()
        self._lock = Lock()
        self._active: GcsimResponseScanSession | GcsimFourPieceSearchSession | None = None
        self._started = False

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            active = self._active
        if active is not None:
            active.cancel()

    def run(self) -> GcsimFourPieceAdvisorResult:
        with self._lock:
            if self._started:
                raise RuntimeError("GcsimFourPieceAdvisorSession instances are one-shot")
            self._started = True
        started = self._clock()
        deadline = started + self.request.overall_deadline_seconds
        remaining = deadline - self._clock()
        response_request = replace(
            self.request.response_scan_request,
            scheduler_budget=replace(
                self.request.response_scan_request.scheduler_budget,
                overall_deadline_seconds=min(
                    self.request.response_scan_request.scheduler_budget.overall_deadline_seconds,
                    max(remaining, 1e-9),
                ),
            ),
        )
        response_session = GcsimResponseScanSession(
            response_request,
            cache_store=self._cache_store,
            enable_cache=self._enable_cache,
            session_factory=self._session_factory,
            scheduler_factory=self._scheduler_factory,
            clock=self._clock,
        )
        if self._clock() >= deadline:
            response_session.cancel()
            response = GcsimResponseScanResult(
                status=GcsimResponseScanStatus.DEADLINE_REACHED,
                stop_reason="deadline_during_response_session_construction",
                elapsed_seconds=max(self._clock() - started, 0.0),
                planned_candidate_count=(
                    len(response_request.wearer_ids)
                    * len(response_request.profile_bank.profiles)
                ),
                materialized_request_count=0,
            )
            return self._result(
                started,
                GcsimFourPieceAdvisorStatus.DEADLINE_REACHED,
                "response_scan:deadline_during_session_construction",
                response,
            )
        self._set_active(response_session)
        try:
            if self._cancel_event.is_set():
                response_session.cancel()
            response = response_session.run()
        finally:
            self._clear_active(response_session)

        if not response.completed:
            if response.status is GcsimResponseScanStatus.CANCELLED:
                status = GcsimFourPieceAdvisorStatus.CANCELLED
            elif response.status is GcsimResponseScanStatus.DEADLINE_REACHED:
                status = GcsimFourPieceAdvisorStatus.DEADLINE_REACHED
            else:
                status = GcsimFourPieceAdvisorStatus.RESPONSE_FAILED
            return self._result(
                started,
                status,
                f"response_scan:{response.stop_reason}",
                response,
            )

        remaining = deadline - self._clock()
        if remaining <= 0:
            return self._result(
                started,
                GcsimFourPieceAdvisorStatus.DEADLINE_REACHED,
                "deadline_after_response_scan",
                response,
            )
        source = response_request
        search_request = GcsimFourPieceSearchRequest(
            engine_context=source.engine_context,
            prepared_config_text=source.prepared_config_text,
            wearer_ids=source.wearer_ids,
            layout_catalog=source.layout_catalog,
            profile_bank=source.profile_bank,
            wearer_profile_selections=response.selection.selections,
            baseline_states=source.baseline_states,
            fidelity=source.fidelity,
            screening_scheduler_budget=self.request.screening_scheduler_budget,
            team_scheduler_budget=self.request.team_scheduler_budget,
            survivor_budget=self.request.survivor_budget,
            composer_budget=self.request.composer_budget,
            overall_deadline_seconds=remaining,
            screening_candidate_timeout_seconds=(
                self.request.screening_candidate_timeout_seconds
            ),
            reference_weights=source.reference_weights,
            environment=source.environment,
            environment_is_frozen=True,
        )
        search_session = GcsimFourPieceSearchSession(
            search_request,
            cache_store=self._cache_store,
            enable_cache=self._enable_cache,
            session_factory=self._session_factory,
            scheduler_factory=self._scheduler_factory,
            clock=self._clock,
        )
        if self._clock() >= deadline:
            search_session.cancel()
            return self._result(
                started,
                GcsimFourPieceAdvisorStatus.DEADLINE_REACHED,
                "deadline_during_search_session_construction",
                response,
            )
        self._set_active(search_session)
        try:
            if self._cancel_event.is_set():
                search_session.cancel()
            search = search_session.run()
        finally:
            self._clear_active(search_session)
        if search.status is GcsimFourPieceSearchStatus.CANCELLED:
            status = GcsimFourPieceAdvisorStatus.CANCELLED
        elif (
            search.status is GcsimFourPieceSearchStatus.DEADLINE_REACHED
            or self._clock() >= deadline
        ):
            status = GcsimFourPieceAdvisorStatus.DEADLINE_REACHED
        elif search.status is GcsimFourPieceSearchStatus.BEST_FOUND:
            status = GcsimFourPieceAdvisorStatus.BEST_FOUND
        elif search.best_found is None:
            status = GcsimFourPieceAdvisorStatus.SEARCH_FAILED
        else:
            # Response profiles and main layouts are bounded heuristics and are
            # not set-invariant.  Even an exhausted downstream candidate domain
            # is therefore best-so-far evidence, never a global-completion claim.
            status = GcsimFourPieceAdvisorStatus.BEST_FOUND
        return self._result(
            started,
            status,
            f"set_search:{search.stop_reason}",
            response,
            search,
        )

    def _set_active(
        self,
        value: GcsimResponseScanSession | GcsimFourPieceSearchSession,
    ) -> None:
        with self._lock:
            if self._active is not None:
                raise GcsimFourPieceAdvisorError("another advisor stage is active")
            self._active = value

    def _clear_active(
        self,
        value: GcsimResponseScanSession | GcsimFourPieceSearchSession,
    ) -> None:
        with self._lock:
            if self._active is value:
                self._active = None

    def _result(
        self,
        started: float,
        status: GcsimFourPieceAdvisorStatus,
        stop_reason: str,
        response: GcsimResponseScanResult,
        search: GcsimFourPieceSearchResult | None = None,
    ) -> GcsimFourPieceAdvisorResult:
        return GcsimFourPieceAdvisorResult(
            status=status,
            stop_reason=stop_reason,
            elapsed_seconds=max(self._clock() - started, 0.0),
            response_scan=response,
            search=search,
        )


def run_gcsim_four_piece_advisor(
    request: GcsimFourPieceAdvisorRequest,
    **session_options,
) -> GcsimFourPieceAdvisorResult:
    return GcsimFourPieceAdvisorSession(request, **session_options).run()


__all__ = [
    "GcsimFourPieceAdvisorError",
    "GcsimFourPieceAdvisorRequest",
    "GcsimFourPieceAdvisorResult",
    "GcsimFourPieceAdvisorSession",
    "GcsimFourPieceAdvisorStatus",
    "run_gcsim_four_piece_advisor",
]
