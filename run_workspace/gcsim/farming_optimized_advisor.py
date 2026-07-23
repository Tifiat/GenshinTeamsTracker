"""End-to-end heuristic 4p advisor with an upstream-optimized finalist race.

The automatic screen intentionally remains recall-oriented and approximate.
This wrapper gives its bounded physical finalists to ``substatOptim`` and
returns the best fully optimized result found before one shared deadline.  It
never upgrades the heuristic finalist domain into a global-optimum claim.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
import math
from threading import Event, Lock, Timer
from time import monotonic
from types import MappingProxyType
from typing import Protocol

from .farming_auto_advisor import (
    GcsimAutomaticAdvisorRequest,
    GcsimAutomaticAdvisorResult,
    GcsimAutomaticAdvisorSession,
    GcsimAutomaticAdvisorStatus,
)
from .farming_finalist_optimizer import (
    GcsimFinalistOptimizerBudget,
    GcsimFinalistOptimizerRequest,
    GcsimFinalistOptimizerResult,
    GcsimFinalistOptimizerSession,
    GcsimFinalistOptimizerStatus,
)


class GcsimOptimizedAdvisorError(RuntimeError):
    """Raised when the combined screen/finalist contract is incoherent."""


class GcsimOptimizedAdvisorStatus(str, Enum):
    BEST_FOUND = "best_found"
    CANCELLED = "cancelled"
    DEADLINE = "deadline"
    SCREENING_FAILED = "screening_failed"
    NO_OPTIMIZED_SUCCESS = "no_optimized_success"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class GcsimOptimizedAdvisorRequest:
    automatic_request: GcsimAutomaticAdvisorRequest
    finalist_budget: GcsimFinalistOptimizerBudget
    overall_deadline_seconds: float
    optimizer_options: Mapping[str, int | float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.automatic_request, GcsimAutomaticAdvisorRequest):
            raise GcsimOptimizedAdvisorError(
                "automatic_request must be a GcsimAutomaticAdvisorRequest"
            )
        if not isinstance(self.finalist_budget, GcsimFinalistOptimizerBudget):
            raise GcsimOptimizedAdvisorError(
                "finalist_budget must be a GcsimFinalistOptimizerBudget"
            )
        if (
            isinstance(self.overall_deadline_seconds, bool)
            or not isinstance(self.overall_deadline_seconds, (int, float))
            or not math.isfinite(self.overall_deadline_seconds)
            or self.overall_deadline_seconds <= 0
        ):
            raise GcsimOptimizedAdvisorError(
                "overall_deadline_seconds must be finite and positive"
            )
        if not isinstance(self.optimizer_options, Mapping):
            raise GcsimOptimizedAdvisorError("optimizer_options must be a mapping")
        object.__setattr__(
            self,
            "optimizer_options",
            MappingProxyType(dict(self.optimizer_options)),
        )


@dataclass(frozen=True, slots=True)
class GcsimOptimizedAdvisorResult:
    status: GcsimOptimizedAdvisorStatus
    stop_reason: str
    elapsed_seconds: float
    request_snapshot: GcsimOptimizedAdvisorRequest = field(repr=False)
    automatic: GcsimAutomaticAdvisorResult | None = None
    finalist: GcsimFinalistOptimizerResult | None = None
    error: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, GcsimOptimizedAdvisorStatus):
            raise GcsimOptimizedAdvisorError("combined advisor status must be typed")
        if not isinstance(self.stop_reason, str) or not self.stop_reason:
            raise GcsimOptimizedAdvisorError("stop_reason must be non-empty")
        if (
            isinstance(self.elapsed_seconds, bool)
            or not isinstance(self.elapsed_seconds, (int, float))
            or not math.isfinite(self.elapsed_seconds)
            or self.elapsed_seconds < 0
        ):
            raise GcsimOptimizedAdvisorError(
                "elapsed_seconds must be finite and non-negative"
            )
        if not isinstance(self.request_snapshot, GcsimOptimizedAdvisorRequest):
            raise GcsimOptimizedAdvisorError("request_snapshot must be typed")
        if self.automatic is not None and not isinstance(
            self.automatic,
            GcsimAutomaticAdvisorResult,
        ):
            raise GcsimOptimizedAdvisorError("automatic evidence must be typed")
        if self.finalist is not None and not isinstance(
            self.finalist,
            GcsimFinalistOptimizerResult,
        ):
            raise GcsimOptimizedAdvisorError("finalist evidence must be typed")
        if self.automatic is not None:
            _validate_automatic_derivation(
                self.request_snapshot,
                self.automatic,
            )
        if self.finalist is not None:
            if (
                self.automatic is None
                or self.automatic.status is not GcsimAutomaticAdvisorStatus.BEST_FOUND
                or self.automatic.advisor is None
                or self.automatic.advisor.search is None
            ):
                raise GcsimOptimizedAdvisorError(
                    "finalist evidence requires a successful automatic screen"
                )
            expected_finalists = self.automatic.advisor.search.physical_finalists[
                : self.request_snapshot.finalist_budget.max_finalists
            ]
            source = self.request_snapshot.automatic_request.layout_scan_request
            finalist_request = self.finalist.request_snapshot
            configured_budget = self.request_snapshot.finalist_budget
            actual_budget = finalist_request.budget
            if (
                replace(
                    actual_budget,
                    overall_deadline_seconds=(
                        configured_budget.overall_deadline_seconds
                    ),
                )
                != configured_budget
                or actual_budget.overall_deadline_seconds
                > min(
                    configured_budget.overall_deadline_seconds,
                    self.request_snapshot.overall_deadline_seconds,
                )
            ):
                raise GcsimOptimizedAdvisorError(
                    "finalist race does not use the configured resource budget"
                )
            expected_request = GcsimFinalistOptimizerRequest(
                engine_context=source.engine_context,
                prepared_config_text=source.prepared_config_text,
                wearer_ids=source.wearer_ids,
                layout_catalog=self.automatic.layout_scan.layout_catalog,
                finalists=expected_finalists,
                budget=actual_budget,
                optimizer_options=self.request_snapshot.optimizer_options,
                environment=source.environment,
                environment_is_frozen=True,
            )
            if (
                finalist_request != expected_request
                or finalist_request.request_sha256 != expected_request.request_sha256
            ):
                raise GcsimOptimizedAdvisorError(
                    "finalist race does not derive exactly from automatic evidence"
                )

        if self.status is GcsimOptimizedAdvisorStatus.BEST_FOUND:
            if (
                self.finalist is None
                or self.finalist.status is not GcsimFinalistOptimizerStatus.BEST_FOUND
                or self.finalist.best_found is None
                or self.error
                or self.stop_reason != "finalist:finalist_race_completed"
            ):
                raise GcsimOptimizedAdvisorError(
                    "best_found requires a successful optimized finalist"
                )
        elif self.status is GcsimOptimizedAdvisorStatus.NO_OPTIMIZED_SUCCESS:
            if (
                self.finalist is None
                or self.finalist.status is not GcsimFinalistOptimizerStatus.NO_SUCCESS
                or self.finalist.best_found is not None
                or self.error
                or self.stop_reason != "finalist:no_success"
            ):
                raise GcsimOptimizedAdvisorError(
                    "no_optimized_success requires a completed unsuccessful race"
                )
        elif self.status is GcsimOptimizedAdvisorStatus.SCREENING_FAILED:
            if (
                self.automatic is None
                or self.automatic.status
                not in {
                    GcsimAutomaticAdvisorStatus.LAYOUT_FAILED,
                    GcsimAutomaticAdvisorStatus.ADVISOR_FAILED,
                }
                or self.finalist is not None
                or self.error
                or self.stop_reason != "screening_failed"
            ):
                raise GcsimOptimizedAdvisorError(
                    "screening_failed requires typed failed automatic evidence"
                )
        elif self.status is GcsimOptimizedAdvisorStatus.CANCELLED:
            active_status = (
                self.finalist.status
                if self.finalist is not None
                else None if self.automatic is None else self.automatic.status
            )
            boundary_cancel = (
                self.finalist is None
                and (
                    (
                        self.stop_reason == "cancelled_before_screening"
                        and self.automatic is None
                    )
                    or (
                        self.stop_reason == "cancelled_before_finalist_race"
                        and self.automatic is not None
                        and self.automatic.status
                        is GcsimAutomaticAdvisorStatus.BEST_FOUND
                    )
                    or (
                        self.stop_reason
                        == "cancelled_during_screening_without_evidence"
                        and self.automatic is None
                    )
                    or (
                        self.stop_reason
                        == "cancelled_during_finalist_without_evidence"
                        and self.automatic is not None
                        and self.automatic.status
                        is GcsimAutomaticAdvisorStatus.BEST_FOUND
                    )
                )
            )
            nested_cancel = (
                self.stop_reason == "screening_cancelled"
                and self.finalist is None
                and active_status is GcsimAutomaticAdvisorStatus.CANCELLED
            ) or (
                self.finalist is not None
                and self.stop_reason == "finalist:cancelled"
                and active_status is GcsimFinalistOptimizerStatus.CANCELLED
            )
            if (
                not boundary_cancel
                and not nested_cancel
                or self.error
            ):
                raise GcsimOptimizedAdvisorError(
                    "cancelled result requires cancelled nested evidence"
                )
        elif self.status is GcsimOptimizedAdvisorStatus.DEADLINE:
            allowed_deadline = False
            if self.stop_reason == "deadline_before_screening":
                allowed_deadline = self.automatic is None and self.finalist is None
            elif self.stop_reason == "deadline_during_screening_without_evidence":
                allowed_deadline = self.automatic is None and self.finalist is None
            elif self.stop_reason == "screening_deadline":
                allowed_deadline = (
                    self.automatic is not None
                    and self.finalist is None
                )
            elif self.stop_reason == "deadline_before_finalist_race":
                allowed_deadline = (
                    self.automatic is not None
                    and self.automatic.status
                    is GcsimAutomaticAdvisorStatus.BEST_FOUND
                    and self.finalist is None
                )
            elif self.stop_reason == "deadline_during_finalist_without_evidence":
                allowed_deadline = (
                    self.automatic is not None
                    and self.automatic.status
                    is GcsimAutomaticAdvisorStatus.BEST_FOUND
                    and self.finalist is None
                )
            elif self.finalist is not None:
                allowed_deadline = (
                    self.automatic is not None
                    and self.automatic.status
                    is GcsimAutomaticAdvisorStatus.BEST_FOUND
                    and self.stop_reason == f"finalist:{self.finalist.stop_reason}"
                )
            if self.error or not allowed_deadline:
                raise GcsimOptimizedAdvisorError(
                    "deadline result requires coherent boundary or nested evidence"
                )
        elif self.status is GcsimOptimizedAdvisorStatus.FAILED:
            if not self.error or self.stop_reason != "orchestration_failed":
                raise GcsimOptimizedAdvisorError("failed result requires an error")

    @property
    def best_found(self):
        return None if self.finalist is None else self.finalist.best_found


class _CombinedStage(Protocol):
    def cancel(self) -> None: ...

    def run(self): ...


AutomaticSessionFactory = Callable[[GcsimAutomaticAdvisorRequest], _CombinedStage]
FinalistSessionFactory = Callable[[GcsimFinalistOptimizerRequest], _CombinedStage]


class GcsimOptimizedAdvisorSession:
    """One-shot automatic screen followed by an optimized finalist race."""

    def __init__(
        self,
        request: GcsimOptimizedAdvisorRequest,
        *,
        automatic_session_factory: AutomaticSessionFactory | None = None,
        finalist_session_factory: FinalistSessionFactory | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isinstance(request, GcsimOptimizedAdvisorRequest):
            raise GcsimOptimizedAdvisorError(
                "request must be a GcsimOptimizedAdvisorRequest"
            )
        self.request = request
        if not callable(clock):
            raise GcsimOptimizedAdvisorError("clock must be callable")
        self._clock = clock
        self._automatic_factory = automatic_session_factory or (
            lambda value: GcsimAutomaticAdvisorSession(value, clock=self._clock)
        )
        self._finalist_factory = finalist_session_factory or (
            lambda value: GcsimFinalistOptimizerSession(value, clock=self._clock)
        )
        if not callable(self._automatic_factory) or not callable(
            self._finalist_factory
        ):
            raise GcsimOptimizedAdvisorError("session factories must be callable")
        self._cancel_event = Event()
        self._deadline_event = Event()
        self._lock = Lock()
        self._active: _CombinedStage | None = None
        self._started = False

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            active = self._active
        if active is not None:
            try:
                active.cancel()
            except Exception:
                pass

    def run(self) -> GcsimOptimizedAdvisorResult:
        with self._lock:
            if self._started:
                raise RuntimeError("GcsimOptimizedAdvisorSession instances are one-shot")
            self._started = True
        started = self._clock()
        deadline = started + self.request.overall_deadline_seconds
        automatic: GcsimAutomaticAdvisorResult | None = None
        automatic_validated = False
        finalist: GcsimFinalistOptimizerResult | None = None

        try:
            terminal = self._terminal_without_evidence(deadline)
            if terminal is not None:
                return self._result(
                    started,
                    terminal,
                    (
                        "cancelled_before_screening"
                        if terminal is GcsimOptimizedAdvisorStatus.CANCELLED
                        else "deadline_before_screening"
                    ),
                )
            remaining = deadline - self._clock()
            if remaining <= 0:
                return self._result(
                    started,
                    GcsimOptimizedAdvisorStatus.DEADLINE,
                    "deadline_before_screening",
                )
            automatic_request = replace(
                self.request.automatic_request,
                overall_deadline_seconds=min(
                    self.request.automatic_request.overall_deadline_seconds,
                    remaining,
                ),
            )
            automatic_session = self._automatic_factory(automatic_request)
            self._require_stage(automatic_session)
            terminal = self._terminal_without_evidence(deadline)
            if terminal is not None:
                automatic_session.cancel()
                return self._result(
                    started,
                    terminal,
                    (
                        "cancelled_before_screening"
                        if terminal is GcsimOptimizedAdvisorStatus.CANCELLED
                        else "deadline_before_screening"
                    ),
                )
            automatic_raw = self._run_stage(automatic_session, deadline)
            if not isinstance(automatic_raw, GcsimAutomaticAdvisorResult):
                raise GcsimOptimizedAdvisorError(
                    "automatic session returned a non-typed result"
                )
            automatic = automatic_raw
            _validate_automatic_derivation(self.request, automatic)
            automatic_validated = True

            if (
                automatic.status is GcsimAutomaticAdvisorStatus.CANCELLED
                and not self._deadline_expired(deadline)
            ):
                return self._result(
                    started,
                    GcsimOptimizedAdvisorStatus.CANCELLED,
                    "screening_cancelled",
                    automatic,
                )
            if (
                automatic.status is GcsimAutomaticAdvisorStatus.DEADLINE_REACHED
                or self._deadline_expired(deadline)
            ):
                return self._result(
                    started,
                    GcsimOptimizedAdvisorStatus.DEADLINE,
                    "screening_deadline",
                    automatic,
                )
            if automatic.status is not GcsimAutomaticAdvisorStatus.BEST_FOUND:
                return self._result(
                    started,
                    GcsimOptimizedAdvisorStatus.SCREENING_FAILED,
                    "screening_failed",
                    automatic,
                )
            if automatic.advisor is None or automatic.advisor.search is None:
                raise GcsimOptimizedAdvisorError(
                    "successful automatic result lacks physical finalists"
                )
            finalists = automatic.advisor.search.physical_finalists[
                : self.request.finalist_budget.max_finalists
            ]
            if not finalists:
                raise GcsimOptimizedAdvisorError(
                    "successful automatic result has an empty finalist domain"
                )

            remaining = deadline - self._clock()
            if remaining <= 0:
                return self._result(
                    started,
                    GcsimOptimizedAdvisorStatus.DEADLINE,
                    "deadline_before_finalist_race",
                    automatic,
                )
            source = self.request.automatic_request.layout_scan_request
            finalist_budget = replace(
                self.request.finalist_budget,
                overall_deadline_seconds=min(
                    self.request.finalist_budget.overall_deadline_seconds,
                    remaining,
                ),
            )
            finalist_request = GcsimFinalistOptimizerRequest(
                engine_context=source.engine_context,
                prepared_config_text=source.prepared_config_text,
                wearer_ids=source.wearer_ids,
                layout_catalog=automatic.layout_scan.layout_catalog,
                finalists=finalists,
                budget=finalist_budget,
                optimizer_options=self.request.optimizer_options,
                environment=source.environment,
                environment_is_frozen=True,
            )
            terminal = self._terminal_without_evidence(deadline)
            if terminal is not None:
                return self._result(
                    started,
                    terminal,
                    (
                        "cancelled_before_finalist_race"
                        if terminal is GcsimOptimizedAdvisorStatus.CANCELLED
                        else "deadline_before_finalist_race"
                    ),
                    automatic,
                )
            finalist_session = self._finalist_factory(finalist_request)
            self._require_stage(finalist_session)
            terminal = self._terminal_without_evidence(deadline)
            if terminal is not None:
                finalist_session.cancel()
                return self._result(
                    started,
                    terminal,
                    (
                        "cancelled_before_finalist_race"
                        if terminal is GcsimOptimizedAdvisorStatus.CANCELLED
                        else "deadline_before_finalist_race"
                    ),
                    automatic,
                )
            finalist_raw = self._run_stage(finalist_session, deadline)
            if not isinstance(finalist_raw, GcsimFinalistOptimizerResult):
                raise GcsimOptimizedAdvisorError(
                    "finalist session returned a non-typed result"
                )
            finalist = finalist_raw

            if (
                finalist.status is GcsimFinalistOptimizerStatus.CANCELLED
                and not self._deadline_expired(deadline)
            ):
                status = GcsimOptimizedAdvisorStatus.CANCELLED
            elif (
                finalist.status is GcsimFinalistOptimizerStatus.DEADLINE
                or self._deadline_expired(deadline)
            ):
                status = GcsimOptimizedAdvisorStatus.DEADLINE
            elif finalist.status is GcsimFinalistOptimizerStatus.BEST_FOUND:
                status = GcsimOptimizedAdvisorStatus.BEST_FOUND
            else:
                status = GcsimOptimizedAdvisorStatus.NO_OPTIMIZED_SUCCESS
            return self._result(
                started,
                status,
                f"finalist:{finalist.stop_reason}",
                automatic,
                finalist,
            )
        except Exception as exc:
            terminal = self._terminal_without_evidence(deadline)
            if terminal is not None:
                during_finalist = (
                    automatic_validated
                    and automatic is not None
                    and automatic.status is GcsimAutomaticAdvisorStatus.BEST_FOUND
                )
                return self._result(
                    started,
                    terminal,
                    (
                        (
                            "cancelled_during_finalist_without_evidence"
                            if during_finalist
                            else "cancelled_during_screening_without_evidence"
                        )
                        if terminal is GcsimOptimizedAdvisorStatus.CANCELLED
                        else (
                            "deadline_during_finalist_without_evidence"
                            if during_finalist
                            else "deadline_during_screening_without_evidence"
                        )
                    ),
                    automatic if during_finalist else None,
                )
            return self._result(
                started,
                GcsimOptimizedAdvisorStatus.FAILED,
                "orchestration_failed",
                None,
                None,
                error=str(exc).replace("\x00", "")[:2000] or type(exc).__name__,
            )

    def _terminal_without_evidence(
        self,
        deadline: float,
    ) -> GcsimOptimizedAdvisorStatus | None:
        if self._cancel_event.is_set():
            return GcsimOptimizedAdvisorStatus.CANCELLED
        if self._deadline_expired(deadline):
            return GcsimOptimizedAdvisorStatus.DEADLINE
        return None

    def _deadline_expired(self, deadline: float) -> bool:
        return self._deadline_event.is_set() or self._clock() >= deadline

    def _run_stage(self, stage: _CombinedStage, deadline: float):
        remaining = deadline - self._clock()
        if remaining <= 0:
            self._deadline_event.set()
            stage.cancel()
            raise GcsimOptimizedAdvisorError("outer deadline expired before stage run")
        timer = Timer(remaining, self._expire_stage, args=(stage,))
        timer.daemon = True
        self._set_active(stage)
        timer.start()
        try:
            if self._cancel_event.is_set():
                stage.cancel()
            return stage.run()
        finally:
            timer.cancel()
            self._clear_active(stage)

    def _expire_stage(self, stage: _CombinedStage) -> None:
        with self._lock:
            is_active = self._active is stage
        if not is_active:
            return
        self._deadline_event.set()
        try:
            stage.cancel()
        except Exception:
            pass

    @staticmethod
    def _require_stage(stage: object) -> None:
        if not callable(getattr(stage, "run", None)) or not callable(
            getattr(stage, "cancel", None)
        ):
            raise GcsimOptimizedAdvisorError("session factory returned an invalid stage")

    def _set_active(self, stage: _CombinedStage) -> None:
        with self._lock:
            if self._active is not None:
                raise GcsimOptimizedAdvisorError("another combined stage is active")
            self._active = stage

    def _clear_active(self, stage: _CombinedStage) -> None:
        with self._lock:
            if self._active is stage:
                self._active = None

    def _result(
        self,
        started: float,
        status: GcsimOptimizedAdvisorStatus,
        stop_reason: str,
        automatic: GcsimAutomaticAdvisorResult | None = None,
        finalist: GcsimFinalistOptimizerResult | None = None,
        *,
        error: str = "",
    ) -> GcsimOptimizedAdvisorResult:
        if status is GcsimOptimizedAdvisorStatus.FAILED and not error:
            error = "operation stopped before typed nested evidence was available"
        return GcsimOptimizedAdvisorResult(
            status=status,
            stop_reason=stop_reason,
            elapsed_seconds=max(self._clock() - started, 0.0),
            request_snapshot=self.request,
            automatic=automatic,
            finalist=finalist,
            error=error,
        )


def run_gcsim_optimized_four_piece_advisor(
    request: GcsimOptimizedAdvisorRequest,
    **session_options,
) -> GcsimOptimizedAdvisorResult:
    return GcsimOptimizedAdvisorSession(request, **session_options).run()


def _validate_automatic_derivation(
    combined_request: GcsimOptimizedAdvisorRequest,
    automatic: GcsimAutomaticAdvisorResult,
) -> None:
    configured = combined_request.automatic_request
    actual = automatic.request_snapshot
    if (
        replace(
            actual,
            overall_deadline_seconds=configured.overall_deadline_seconds,
        )
        != configured
        or actual.overall_deadline_seconds
        > min(
            configured.overall_deadline_seconds,
            combined_request.overall_deadline_seconds,
        )
    ):
        raise GcsimOptimizedAdvisorError(
            "automatic evidence does not derive from the configured request"
        )


__all__ = [
    "AutomaticSessionFactory",
    "FinalistSessionFactory",
    "GcsimOptimizedAdvisorError",
    "GcsimOptimizedAdvisorRequest",
    "GcsimOptimizedAdvisorResult",
    "GcsimOptimizedAdvisorSession",
    "GcsimOptimizedAdvisorStatus",
    "run_gcsim_optimized_four_piece_advisor",
]
