"""Automatic bounded 4p advisor: main layouts -> stat response -> set search."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum
import math
from threading import Event, Lock
from time import monotonic

from .farming_advisor import (
    GcsimFourPieceAdvisorRequest,
    GcsimFourPieceAdvisorResult,
    GcsimFourPieceAdvisorSession,
    GcsimFourPieceAdvisorStatus,
)
from .farming_evaluator import FarmingSessionFactory, GcsimFarmingSchedulerBudget
from .farming_layout_scan import (
    GcsimMainLayoutScanRequest,
    GcsimMainLayoutScanResult,
    GcsimMainLayoutScanSession,
    GcsimMainLayoutScanStatus,
)
from .farming_pipeline import SchedulerFactory
from .farming_response import ResponseProfileSelectionBudget
from .farming_response_scan import GcsimResponseScanRequest
from .farming_search import ScreeningSurvivorBudget
from .farming_team_search import FullTeamComposerBudget
from .optimizer_cache import GcsimOptimizerCacheStore


class GcsimAutomaticAdvisorError(RuntimeError):
    """Raised when automatic advisor stages cannot share one contract."""


class GcsimAutomaticAdvisorStatus(str, Enum):
    BEST_FOUND = "best_found"
    CANCELLED = "cancelled"
    DEADLINE_REACHED = "deadline_reached"
    LAYOUT_FAILED = "layout_failed"
    ADVISOR_FAILED = "advisor_failed"


@dataclass(frozen=True, slots=True)
class GcsimAutomaticAdvisorRequest:
    layout_scan_request: GcsimMainLayoutScanRequest
    response_scheduler_budget: GcsimFarmingSchedulerBudget
    response_selection_budget: ResponseProfileSelectionBudget
    response_candidate_timeout_seconds: float
    screening_scheduler_budget: GcsimFarmingSchedulerBudget
    team_scheduler_budget: GcsimFarmingSchedulerBudget
    survivor_budget: ScreeningSurvivorBudget
    composer_budget: FullTeamComposerBudget
    screening_candidate_timeout_seconds: float
    overall_deadline_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.layout_scan_request, GcsimMainLayoutScanRequest):
            raise GcsimAutomaticAdvisorError(
                "layout_scan_request must be a GcsimMainLayoutScanRequest"
            )
        for field_name in (
            "response_candidate_timeout_seconds",
            "screening_candidate_timeout_seconds",
            "overall_deadline_seconds",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise GcsimAutomaticAdvisorError(
                    f"{field_name} must be finite and positive"
                )


@dataclass(frozen=True, slots=True)
class GcsimAutomaticAdvisorResult:
    status: GcsimAutomaticAdvisorStatus
    stop_reason: str
    elapsed_seconds: float
    layout_scan: GcsimMainLayoutScanResult
    request_snapshot: GcsimAutomaticAdvisorRequest = field(repr=False)
    advisor: GcsimFourPieceAdvisorResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, GcsimAutomaticAdvisorStatus):
            raise ValueError("status must be a GcsimAutomaticAdvisorStatus")
        if not isinstance(self.stop_reason, str) or not self.stop_reason:
            raise ValueError("stop_reason must be a non-empty string")
        if not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must be finite and non-negative")
        if not isinstance(self.layout_scan, GcsimMainLayoutScanResult):
            raise ValueError("layout_scan must be a GcsimMainLayoutScanResult")
        if not isinstance(self.request_snapshot, GcsimAutomaticAdvisorRequest):
            raise ValueError(
                "request_snapshot must be a GcsimAutomaticAdvisorRequest"
            )
        if self.advisor is not None and not isinstance(
            self.advisor,
            GcsimFourPieceAdvisorResult,
        ):
            raise ValueError("advisor must be a GcsimFourPieceAdvisorResult")
        if self.advisor is not None and not self.layout_scan.completed:
            raise ValueError("advisor evidence requires a completed layout scan")
        if self.status is GcsimAutomaticAdvisorStatus.BEST_FOUND:
            if (
                not self.layout_scan.completed
                or self.advisor is None
                or self.advisor.status is not GcsimFourPieceAdvisorStatus.BEST_FOUND
                or self.advisor.best_found is None
            ):
                raise ValueError(
                    "best_found automatic result requires complete stage evidence"
                )
        elif self.status is GcsimAutomaticAdvisorStatus.LAYOUT_FAILED:
            if self.layout_scan.completed or self.advisor is not None:
                raise ValueError(
                    "layout_failed result requires failed layout and no advisor"
                )
        elif self.status is GcsimAutomaticAdvisorStatus.ADVISOR_FAILED:
            if (
                not self.layout_scan.completed
                or self.advisor is None
                or self.advisor.status
                not in {
                    GcsimFourPieceAdvisorStatus.RESPONSE_FAILED,
                    GcsimFourPieceAdvisorStatus.SEARCH_FAILED,
                }
                or self.advisor.best_found is not None
            ):
                raise ValueError(
                    "advisor_failed result requires typed failed advisor evidence"
                )

    @property
    def best_found(self):
        return None if self.advisor is None else self.advisor.best_found


class GcsimAutomaticAdvisorSession:
    """One-shot three-stage heuristic with one wall-clock deadline."""

    def __init__(
        self,
        request: GcsimAutomaticAdvisorRequest,
        *,
        cache_store: GcsimOptimizerCacheStore | None = None,
        enable_cache: bool = True,
        session_factory: FarmingSessionFactory | None = None,
        scheduler_factory: SchedulerFactory | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isinstance(request, GcsimAutomaticAdvisorRequest):
            raise GcsimAutomaticAdvisorError(
                "request must be a GcsimAutomaticAdvisorRequest"
            )
        self.request = request
        self._cache_store = cache_store
        self._enable_cache = bool(enable_cache)
        self._session_factory = session_factory
        self._scheduler_factory = scheduler_factory
        self._clock = clock
        self._cancel_event = Event()
        self._lock = Lock()
        self._active = None
        self._started = False

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            active = self._active
        if active is not None:
            active.cancel()

    def run(self) -> GcsimAutomaticAdvisorResult:
        with self._lock:
            if self._started:
                raise RuntimeError("GcsimAutomaticAdvisorSession instances are one-shot")
            self._started = True
        started = self._clock()
        deadline = started + self.request.overall_deadline_seconds
        remaining = max(deadline - self._clock(), 1e-9)
        layout_request = replace(
            self.request.layout_scan_request,
            overall_deadline_seconds=min(
                self.request.layout_scan_request.overall_deadline_seconds,
                remaining,
            ),
        )
        layout_session = GcsimMainLayoutScanSession(
            layout_request,
            cache_store=self._cache_store,
            enable_cache=self._enable_cache,
            session_factory=self._session_factory,
            scheduler_factory=self._scheduler_factory,
            clock=self._clock,
        )
        if self._clock() >= deadline:
            layout_session.cancel()
            layout = GcsimMainLayoutScanResult(
                status=GcsimMainLayoutScanStatus.DEADLINE_REACHED,
                stop_reason="deadline_during_layout_session_construction",
                elapsed_seconds=max(self._clock() - started, 0.0),
                coordinate_candidate_count=0,
                combination_candidate_count=0,
                coordinate_request_count=0,
                combination_request_count=0,
            )
            return self._result(
                started,
                GcsimAutomaticAdvisorStatus.DEADLINE_REACHED,
                "layout_scan:deadline_during_session_construction",
                layout,
            )
        self._set_active(layout_session)
        try:
            if self._cancel_event.is_set():
                layout_session.cancel()
            layout = layout_session.run()
        finally:
            self._clear_active(layout_session)
        if not layout.completed:
            if layout.status is GcsimMainLayoutScanStatus.CANCELLED:
                status = GcsimAutomaticAdvisorStatus.CANCELLED
            elif layout.status is GcsimMainLayoutScanStatus.DEADLINE_REACHED:
                status = GcsimAutomaticAdvisorStatus.DEADLINE_REACHED
            else:
                status = GcsimAutomaticAdvisorStatus.LAYOUT_FAILED
            return self._result(
                started,
                status,
                f"layout_scan:{layout.stop_reason}",
                layout,
            )
        remaining = deadline - self._clock()
        if remaining <= 0:
            return self._result(
                started,
                GcsimAutomaticAdvisorStatus.DEADLINE_REACHED,
                "deadline_after_layout_scan",
                layout,
            )
        source = layout_request
        response_request = GcsimResponseScanRequest(
            engine_context=source.engine_context,
            prepared_config_text=source.prepared_config_text,
            wearer_ids=source.wearer_ids,
            layout_catalog=layout.layout_catalog,
            profile_bank=source.profile_bank,
            baseline_states=layout.best_baseline_states,
            fidelity=source.fidelity,
            scheduler_budget=replace(
                self.request.response_scheduler_budget,
                overall_deadline_seconds=min(
                    self.request.response_scheduler_budget.overall_deadline_seconds,
                    remaining,
                ),
            ),
            selection_budget=self.request.response_selection_budget,
            candidate_timeout_seconds=self.request.response_candidate_timeout_seconds,
            reference_weights=source.reference_weights,
            baseline_profile_id=source.baseline_profile_id,
            environment=source.environment,
            environment_is_frozen=True,
        )
        advisor_request = GcsimFourPieceAdvisorRequest(
            response_scan_request=response_request,
            screening_scheduler_budget=self.request.screening_scheduler_budget,
            team_scheduler_budget=self.request.team_scheduler_budget,
            survivor_budget=self.request.survivor_budget,
            composer_budget=self.request.composer_budget,
            overall_deadline_seconds=remaining,
            screening_candidate_timeout_seconds=(
                self.request.screening_candidate_timeout_seconds
            ),
        )
        advisor_session = GcsimFourPieceAdvisorSession(
            advisor_request,
            cache_store=self._cache_store,
            enable_cache=self._enable_cache,
            session_factory=self._session_factory,
            scheduler_factory=self._scheduler_factory,
            clock=self._clock,
        )
        if self._clock() >= deadline:
            advisor_session.cancel()
            return self._result(
                started,
                GcsimAutomaticAdvisorStatus.DEADLINE_REACHED,
                "deadline_during_advisor_session_construction",
                layout,
            )
        self._set_active(advisor_session)
        try:
            if self._cancel_event.is_set():
                advisor_session.cancel()
            advisor = advisor_session.run()
        finally:
            self._clear_active(advisor_session)
        if advisor.status is GcsimFourPieceAdvisorStatus.CANCELLED:
            status = GcsimAutomaticAdvisorStatus.CANCELLED
        elif (
            advisor.status is GcsimFourPieceAdvisorStatus.DEADLINE_REACHED
            or self._clock() >= deadline
        ):
            status = GcsimAutomaticAdvisorStatus.DEADLINE_REACHED
        elif advisor.status is not GcsimFourPieceAdvisorStatus.BEST_FOUND:
            status = GcsimAutomaticAdvisorStatus.ADVISOR_FAILED
        else:
            status = GcsimAutomaticAdvisorStatus.BEST_FOUND
        return self._result(
            started,
            status,
            f"advisor:{advisor.stop_reason}",
            layout,
            advisor,
        )

    def _set_active(self, value) -> None:
        with self._lock:
            if self._active is not None:
                raise GcsimAutomaticAdvisorError("another automatic stage is active")
            self._active = value

    def _clear_active(self, value) -> None:
        with self._lock:
            if self._active is value:
                self._active = None

    def _result(self, started, status, stop_reason, layout, advisor=None):
        return GcsimAutomaticAdvisorResult(
            status=status,
            stop_reason=stop_reason,
            elapsed_seconds=max(self._clock() - started, 0.0),
            layout_scan=layout,
            request_snapshot=self.request,
            advisor=advisor,
        )


def run_gcsim_automatic_four_piece_advisor(
    request: GcsimAutomaticAdvisorRequest,
    **session_options,
) -> GcsimAutomaticAdvisorResult:
    return GcsimAutomaticAdvisorSession(request, **session_options).run()


__all__ = [
    "GcsimAutomaticAdvisorError",
    "GcsimAutomaticAdvisorRequest",
    "GcsimAutomaticAdvisorResult",
    "GcsimAutomaticAdvisorSession",
    "GcsimAutomaticAdvisorStatus",
    "run_gcsim_automatic_four_piece_advisor",
]
