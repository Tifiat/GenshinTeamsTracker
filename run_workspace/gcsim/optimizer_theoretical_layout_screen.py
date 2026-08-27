"""Optimizer-backed 32-iteration main-layout screen for theoretical search.

The cheap theoretical race intentionally uses several stat profiles to retain
recall, but those profiles are only screening surrogates.  This stage removes
profile duplicates, constructs a small physical main-stat neighborhood inside
each retained ordered team-package signature, and runs ``substatOptim`` at 32
iterations for every retained layout.  Exactly one physical layout per package
signature is then promoted to the existing 200/1000 validation layer.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import hashlib
from itertools import product
import json
from math import isfinite
from threading import Event, Lock
from time import monotonic

from .farming_finalist_optimizer import (
    GcsimFinalistAttemptStatus,
    GcsimFinalistOptimizerBudget,
    GcsimFinalistOptimizerOutcome,
    GcsimFinalistOptimizerRequest,
    GcsimFinalistOptimizerResult,
    GcsimFinalistOptimizerSession,
    GcsimFinalistOptimizerStatus,
)
from .farming_search import FourPieceSetState
from .farming_team_search import FullTeamPhysicalState
from .optimizer_cache import GcsimOptimizerCacheStore
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_product_contracts import (
    GcsimOptimizerOperation,
    GcsimOptimizerOperationRequest,
)
from .optimizer_stat_response import GcsimStatResponseTarget
from .optimizer_theoretical_anytime_candidates import (
    gcsim_optimizer_theoretical_team_package_signature,
)
from .optimizer_theoretical_anytime_race import (
    GcsimOptimizerTheoreticalAnytimeRaceEvaluation,
    GcsimOptimizerTheoreticalAnytimeRaceResult,
)
from .optimizer_theoretical_packages import (
    freeze_gcsim_theoretical_pair_packages,
    gcsim_theoretical_pair_domain_sha256,
)


GCSIM_OPTIMIZER_THEORETICAL_LAYOUT_SCREEN_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_THEORETICAL_LAYOUT_SCREEN_PLAN_ID = (
    "theoretical_layout_screen"
)
GCSIM_OPTIMIZER_THEORETICAL_LAYOUT_SCREEN_PLAN_VERSION = 1

TheoreticalLayoutScreenProgressCallback = Callable[
    [
        int,
        int,
        int,
        GcsimFinalistOptimizerOutcome | None,
    ],
    None,
]


class GcsimOptimizerTheoreticalLayoutScreenError(RuntimeError):
    """Raised when the physical-layout screen violates its frozen bounds."""


class GcsimOptimizerTheoreticalLayoutScreenStatus(str, Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    NO_SUCCESS = "no_success"
    CANCELLED = "cancelled"
    DEADLINE = "deadline"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalLayoutScreenPlan:
    iterations: int = 32
    max_package_signatures: int = 6
    max_candidates_per_signature: int = 6
    coordinate_choices_per_wearer: int = 2
    worker_count: int = 1
    optimizer_timeout_seconds: float = 300.0
    simulation_timeout_seconds: float = 300.0
    overall_deadline_seconds: float = 900.0
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_LAYOUT_SCREEN_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in (
            "iterations",
            "max_package_signatures",
            "max_candidates_per_signature",
            "coordinate_choices_per_wearer",
            "worker_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise GcsimOptimizerTheoreticalLayoutScreenError(
                    f"{field_name} must be a positive integer"
                )
        if self.iterations != 32:
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "theoretical layout screening must use 32 iterations"
            )
        if self.max_package_signatures > 6:
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout screening may retain at most six package signatures"
            )
        if self.max_candidates_per_signature > 6:
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout screening may test at most six layouts per signature"
            )
        if self.coordinate_choices_per_wearer > 2:
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "the physical coordinate beam is frozen at at most two choices"
            )
        for field_name in (
            "optimizer_timeout_seconds",
            "simulation_timeout_seconds",
            "overall_deadline_seconds",
        ):
            value = getattr(self, field_name)
            if not isfinite(value) or value <= 0:
                raise GcsimOptimizerTheoreticalLayoutScreenError(
                    f"{field_name} must be finite and positive"
                )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": GCSIM_OPTIMIZER_THEORETICAL_LAYOUT_SCREEN_PLAN_ID,
            "plan_version": (
                GCSIM_OPTIMIZER_THEORETICAL_LAYOUT_SCREEN_PLAN_VERSION
            ),
            "iterations": self.iterations,
            "max_package_signatures": self.max_package_signatures,
            "max_candidates_per_signature": (
                self.max_candidates_per_signature
            ),
            "coordinate_choices_per_wearer": (
                self.coordinate_choices_per_wearer
            ),
            "worker_count": self.worker_count,
            "optimizer_timeout_seconds": self.optimizer_timeout_seconds,
            "simulation_timeout_seconds": self.simulation_timeout_seconds,
            "overall_deadline_seconds": self.overall_deadline_seconds,
            "selection_policy": (
                "physical_coordinate_top2_then_substat_optim_32_v1"
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalLayoutSignatureDomain:
    package_signature: tuple[str, ...]
    race_finalist: FullTeamPhysicalState
    coordinate_winner: FullTeamPhysicalState
    candidates: tuple[FullTeamPhysicalState, ...]
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_LAYOUT_SCREEN_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        signature = tuple(self.package_signature)
        candidates = tuple(self.candidates)
        object.__setattr__(self, "package_signature", signature)
        object.__setattr__(self, "candidates", candidates)
        if len(signature) != 4 or any(not item for item in signature):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout signature must contain four package keys"
            )
        if not isinstance(self.race_finalist, FullTeamPhysicalState):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "race_finalist must be a physical team state"
            )
        if not isinstance(self.coordinate_winner, FullTeamPhysicalState):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "coordinate_winner must be a physical team state"
            )
        if not candidates or len(candidates) > 6:
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "a signature must retain one to six physical layouts"
            )
        if len({item.key for item in candidates}) != len(candidates):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout-screen candidates must be physically unique"
            )
        if candidates[0] != self.race_finalist:
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "the race finalist must be the first layout-screen candidate"
            )
        if self.coordinate_winner not in candidates:
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "the coordinate winner must be retained"
            )
        if any(
            gcsim_optimizer_theoretical_team_package_signature(item)
            != signature
            for item in (
                self.race_finalist,
                self.coordinate_winner,
                *candidates,
            )
        ):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "physical layouts differ from their package signature"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "package_signature": list(self.package_signature),
            "race_finalist": _state_payload(self.race_finalist),
            "coordinate_winner": _state_payload(self.coordinate_winner),
            "candidates": [_state_payload(item) for item in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalLayoutScreenDomain:
    race_evidence_sha256: str
    race_plan_identity_sha256: str
    plan: GcsimOptimizerTheoreticalLayoutScreenPlan
    signatures: tuple[
        GcsimOptimizerTheoreticalLayoutSignatureDomain, ...
    ]
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_LAYOUT_SCREEN_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        _require_sha256(self.race_evidence_sha256, "race_evidence_sha256")
        _require_sha256(
            self.race_plan_identity_sha256,
            "race_plan_identity_sha256",
        )
        if not isinstance(
            self.plan,
            GcsimOptimizerTheoreticalLayoutScreenPlan,
        ):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout-screen plan must be typed"
            )
        signatures = tuple(self.signatures)
        object.__setattr__(self, "signatures", signatures)
        if not signatures or len(signatures) > self.plan.max_package_signatures:
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout-screen signature domain is empty or exceeds its cap"
            )
        if any(
            not isinstance(
                item,
                GcsimOptimizerTheoreticalLayoutSignatureDomain,
            )
            or len(item.candidates) > self.plan.max_candidates_per_signature
            for item in signatures
        ):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout-screen signature rows violate the plan"
            )
        package_signatures = tuple(
            item.package_signature for item in signatures
        )
        if len(set(package_signatures)) != len(package_signatures):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout-screen package signatures must be unique"
            )
        if len(self.candidates) > (
            self.plan.max_package_signatures
            * self.plan.max_candidates_per_signature
        ):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout-screen physical domain exceeds its global cap"
            )

    @property
    def candidates(self) -> tuple[FullTeamPhysicalState, ...]:
        return tuple(
            state for signature in self.signatures for state in signature.candidates
        )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "race_evidence_sha256": self.race_evidence_sha256,
            "race_plan_identity_sha256": self.race_plan_identity_sha256,
            "plan_sha256": self.plan.identity_sha256,
            "signatures": [item.to_dict() for item in self.signatures],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalLayoutScreenResult:
    status: GcsimOptimizerTheoreticalLayoutScreenStatus
    domain: GcsimOptimizerTheoreticalLayoutScreenDomain
    finalist_result: GcsimFinalistOptimizerResult
    selected_outcomes: tuple[GcsimFinalistOptimizerOutcome, ...]
    selected_finalists: tuple[FullTeamPhysicalState, ...]
    evidence_sha256: str
    elapsed_seconds: float
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_LAYOUT_SCREEN_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(
            self.status,
            GcsimOptimizerTheoreticalLayoutScreenStatus,
        ):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout-screen status must be typed"
            )
        if not isinstance(
            self.domain,
            GcsimOptimizerTheoreticalLayoutScreenDomain,
        ):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout-screen domain must be typed"
            )
        if not isinstance(self.finalist_result, GcsimFinalistOptimizerResult):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout-screen finalist evidence must be typed"
            )
        outcomes = tuple(self.selected_outcomes)
        finalists = tuple(self.selected_finalists)
        object.__setattr__(self, "selected_outcomes", outcomes)
        object.__setattr__(self, "selected_finalists", finalists)
        if any(
            not isinstance(item, GcsimFinalistOptimizerOutcome)
            or item.iterations != self.domain.plan.iterations
            for item in outcomes
        ):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "selected layout outcomes require typed 32-iteration evidence"
            )
        if outcomes != tuple(sorted(outcomes, key=_outcome_rank)):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "selected layout outcomes must use deterministic DPS order"
            )
        if finalists != tuple(item.state for item in outcomes):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "selected physical finalists differ from optimizer evidence"
            )
        if len(outcomes) > self.domain.plan.max_package_signatures:
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "selected layout outcomes exceed the package-signature cap"
            )
        if len(
            {
                gcsim_optimizer_theoretical_team_package_signature(item.state)
                for item in outcomes
            }
        ) != len(outcomes):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "selected layout outcomes must use distinct package signatures"
            )
        expected_domain = self.domain.candidates
        if self.finalist_result.request_snapshot.finalists != expected_domain:
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout-screen execution domain differs from its typed domain"
            )
        if self.status in {
            GcsimOptimizerTheoreticalLayoutScreenStatus.COMPLETED,
            GcsimOptimizerTheoreticalLayoutScreenStatus.COMPLETED_WITH_ERRORS,
        } and not outcomes:
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "completed layout screening requires a selected outcome"
            )
        _require_sha256(self.evidence_sha256, "evidence_sha256")
        if not isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "elapsed_seconds must be finite and non-negative"
            )

    @property
    def best_outcome(self) -> GcsimFinalistOptimizerOutcome | None:
        return self.selected_outcomes[0] if self.selected_outcomes else None


def build_gcsim_optimizer_theoretical_layout_screen_domain(
    race: GcsimOptimizerTheoreticalAnytimeRaceResult,
    *,
    plan: GcsimOptimizerTheoreticalLayoutScreenPlan | None = None,
) -> GcsimOptimizerTheoreticalLayoutScreenDomain:
    """Build a bounded physical layout portfolio from auditable race rows."""

    if not isinstance(race, GcsimOptimizerTheoreticalAnytimeRaceResult):
        raise GcsimOptimizerTheoreticalLayoutScreenError(
            "layout screening requires a typed race result"
        )
    selected_plan = plan or GcsimOptimizerTheoreticalLayoutScreenPlan()
    finalist_rows = race.finalist_evaluations[
        : selected_plan.max_package_signatures
    ]
    if not finalist_rows:
        raise GcsimOptimizerTheoreticalLayoutScreenError(
            "layout screening requires at least one race finalist"
        )
    traces = {item.tier.tier_id: item for item in race.tier_traces}
    package_rows = tuple(
        item
        for item in traces.get("package_screen_8", ()).evaluations
        if item.success
    ) if "package_screen_8" in traces else ()
    coordinate_rows = tuple(
        item
        for item in traces.get("main_coordinate_8", ()).evaluations
        if item.success
    ) if "main_coordinate_8" in traces else ()
    all_successful_rows = tuple(
        item
        for trace in race.tier_traces
        for item in trace.evaluations
        if item.success
    )
    signature_domains = tuple(
        _build_signature_domain(
            finalist,
            package_rows=package_rows,
            coordinate_rows=coordinate_rows,
            all_successful_rows=all_successful_rows,
            plan=selected_plan,
        )
        for finalist in finalist_rows
    )
    return GcsimOptimizerTheoreticalLayoutScreenDomain(
        race_evidence_sha256=race.evidence_sha256,
        race_plan_identity_sha256=race.plan_identity_sha256,
        plan=selected_plan,
        signatures=signature_domains,
    )


class GcsimOptimizerTheoreticalLayoutScreenSession:
    """One-shot owner of the bounded optimizer-backed layout comparison."""

    def __init__(
        self,
        request: GcsimOptimizerOperationRequest,
        *,
        engine_context: GcsimOptimizerEngineContext,
        prepared_config_text: str,
        layout_catalog: Mapping[str, Mapping[str, object]],
        race_result: GcsimOptimizerTheoreticalAnytimeRaceResult,
        two_plus_two_packages: Mapping[str, object] | None = None,
        plan: GcsimOptimizerTheoreticalLayoutScreenPlan | None = None,
        progress_callback: TheoreticalLayoutScreenProgressCallback | None = None,
        cache_store: GcsimOptimizerCacheStore | None = None,
        enable_cache: bool = True,
        finalist_session_factory: Callable[[object], object] | None = None,
        environment: Mapping[str, str] | None = None,
        stat_response_target: GcsimStatResponseTarget | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isinstance(request, GcsimOptimizerOperationRequest):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout screening requires a typed operation request"
            )
        if request.operation not in {
            GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
            GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO,
        }:
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout screening requires a theoretical operation"
            )
        if (
            request.source_simulation.engine_binding_sha256
            != engine_context.binding_sha256
            or request.source_simulation.catalog_fingerprint
            != engine_context.catalog.source_fingerprint
        ):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout-screen engine binding differs from request"
            )
        if (
            request.source_simulation.prepared_config_sha256
            != _text_sha256(prepared_config_text)
            or race_result.source_config_sha256
            != _text_sha256(prepared_config_text)
            or race_result.engine_binding_sha256
            != engine_context.binding_sha256
        ):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "layout-screen source or race binding differs from request"
            )
        packages = freeze_gcsim_theoretical_pair_packages(
            two_plus_two_packages
        )
        if (
            request.operation
            is GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO
        ) != bool(packages):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "theoretical operation and pair package domain differ"
            )
        if progress_callback is not None and not callable(progress_callback):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "progress_callback must be callable or None"
            )
        selected_plan = plan or GcsimOptimizerTheoreticalLayoutScreenPlan()
        self.request = request
        self.engine_context = engine_context
        self.prepared_config_text = prepared_config_text
        self.layout_catalog = layout_catalog
        self.race_result = race_result
        self.two_plus_two_packages = packages
        self.plan = selected_plan
        self.domain = build_gcsim_optimizer_theoretical_layout_screen_domain(
            race_result,
            plan=selected_plan,
        )
        self.progress_callback = progress_callback
        self.enable_cache = bool(enable_cache)
        self.cache_store = (
            (cache_store or GcsimOptimizerCacheStore())
            if self.enable_cache
            else None
        )
        self.finalist_session_factory = finalist_session_factory
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

    def run(self) -> GcsimOptimizerTheoreticalLayoutScreenResult:
        with self._lock:
            if self._started:
                raise GcsimOptimizerTheoreticalLayoutScreenError(
                    "layout-screen sessions are one-shot"
                )
            self._started = True
        started = self.clock()
        candidates = self.domain.candidates
        budget = GcsimFinalistOptimizerBudget(
            max_finalists=len(candidates),
            top_n=len(candidates),
            worker_count=self.plan.worker_count,
            validation_iterations=self.plan.iterations,
            overall_deadline_seconds=self.plan.overall_deadline_seconds,
            optimizer_timeout_seconds=self.plan.optimizer_timeout_seconds,
            simulation_timeout_seconds=self.plan.simulation_timeout_seconds,
        )
        finalist_request = GcsimFinalistOptimizerRequest(
            engine_context=self.engine_context,
            prepared_config_text=self.prepared_config_text,
            wearer_ids=self.request.source_simulation.wearer_ids,
            layout_catalog=self.layout_catalog,
            finalists=candidates,
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
        observed: list[GcsimFinalistOptimizerOutcome] = []
        cache_hits = 0

        def on_finalist(completed: int, planned: int, attempt) -> None:
            nonlocal cache_hits
            cache_hits += int(attempt.cache_hit)
            if attempt.outcome is not None:
                observed.append(attempt.outcome)
            self._emit_progress(
                completed,
                planned,
                cache_hits,
                min(observed, key=_outcome_rank) if observed else None,
            )

        if self.finalist_session_factory is None:
            finalist_session = GcsimFinalistOptimizerSession(
                finalist_request,
                cache_store=self.cache_store if self.enable_cache else None,
                completion_callback=on_finalist,
                clock=self.clock,
            )
        else:
            finalist_session = self.finalist_session_factory(finalist_request)
        self._set_active(finalist_session)
        if self._cancel_event.is_set():
            finalist_session.cancel()
        self._emit_progress(0, len(candidates), 0, None)
        try:
            finalist = finalist_session.run()
        finally:
            self._clear_active(finalist_session)
        if not isinstance(finalist, GcsimFinalistOptimizerResult):
            raise GcsimOptimizerTheoreticalLayoutScreenError(
                "finalist_session_factory returned an invalid result"
            )
        successful = finalist.all_successful_outcomes
        if not observed or len(observed) != len(successful):
            self._emit_progress(
                finalist.attempted_count,
                len(candidates),
                sum(int(item.cache_hit) for item in finalist.attempts),
                min(successful, key=_outcome_rank) if successful else None,
            )
        best_by_signature: dict[
            tuple[str, ...], GcsimFinalistOptimizerOutcome
        ] = {}
        for outcome in sorted(successful, key=_outcome_rank):
            best_by_signature.setdefault(
                gcsim_optimizer_theoretical_team_package_signature(
                    outcome.state
                ),
                outcome,
            )
        selected = tuple(sorted(best_by_signature.values(), key=_outcome_rank))
        status = _status_from_finalist(finalist)
        if (
            status is GcsimOptimizerTheoreticalLayoutScreenStatus.COMPLETED
            and any(
                item.status is not GcsimFinalistAttemptStatus.PASSED
                for item in finalist.attempts
            )
        ):
            status = (
                GcsimOptimizerTheoreticalLayoutScreenStatus
                .COMPLETED_WITH_ERRORS
            )
        evidence_sha256 = _canonical_sha256(
            {
                "schema_version": (
                    GCSIM_OPTIMIZER_THEORETICAL_LAYOUT_SCREEN_SCHEMA_VERSION
                ),
                "request_sha256": self.request.request_sha256,
                "domain_sha256": self.domain.identity_sha256,
                "finalist_request_sha256": finalist.request_sha256,
                "pair_domain_sha256": (
                    gcsim_theoretical_pair_domain_sha256(
                        self.two_plus_two_packages
                    )
                    if self.two_plus_two_packages
                    else ""
                ),
                "status": status.value,
                "selected": [
                    {
                        "state": _state_payload(item.state),
                        "allocation_sha256": item.allocation_sha256,
                        "result_json_sha256": item.result_json_sha256,
                    }
                    for item in selected
                ],
            }
        )
        return GcsimOptimizerTheoreticalLayoutScreenResult(
            status=status,
            domain=self.domain,
            finalist_result=finalist,
            selected_outcomes=selected,
            selected_finalists=tuple(item.state for item in selected),
            evidence_sha256=evidence_sha256,
            elapsed_seconds=max(self.clock() - started, 0.0),
        )

    def _emit_progress(
        self,
        completed: int,
        planned: int,
        cache_hits: int,
        leader: GcsimFinalistOptimizerOutcome | None,
    ) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(completed, planned, cache_hits, leader)
        except Exception:
            pass

    def _set_active(self, value: object) -> None:
        with self._lock:
            self._active = value

    def _clear_active(self, value: object) -> None:
        with self._lock:
            if self._active is value:
                self._active = None


def run_gcsim_optimizer_theoretical_layout_screen(
    request: GcsimOptimizerOperationRequest,
    **kwargs,
) -> GcsimOptimizerTheoreticalLayoutScreenResult:
    return GcsimOptimizerTheoreticalLayoutScreenSession(
        request,
        **kwargs,
    ).run()


def _build_signature_domain(
    finalist: GcsimOptimizerTheoreticalAnytimeRaceEvaluation,
    *,
    package_rows: Sequence[GcsimOptimizerTheoreticalAnytimeRaceEvaluation],
    coordinate_rows: Sequence[GcsimOptimizerTheoreticalAnytimeRaceEvaluation],
    all_successful_rows: Sequence[
        GcsimOptimizerTheoreticalAnytimeRaceEvaluation
    ],
    plan: GcsimOptimizerTheoreticalLayoutScreenPlan,
) -> GcsimOptimizerTheoreticalLayoutSignatureDomain:
    signature = gcsim_optimizer_theoretical_team_package_signature(
        finalist.physical_state
    )
    matching_package = tuple(
        item
        for item in package_rows
        if gcsim_optimizer_theoretical_team_package_signature(
            item.physical_state
        ) == signature
    )
    seed = min(matching_package, key=_race_rank) if matching_package else finalist
    final_state = finalist.physical_state
    seed_state = seed.physical_state
    scores: list[
        dict[tuple[str, str, str, str], tuple[float, FourPieceSetState]]
    ] = [dict() for _item in final_state.choices]

    def retain_choice(index: int, choice: FourPieceSetState, score: float) -> None:
        previous = scores[index].get(choice.key)
        if previous is None or score > previous[0]:
            scores[index][choice.key] = (score, choice)

    seed_score = float(seed.dps_mean or 0.0)
    final_score = float(finalist.dps_mean or 0.0)
    for index, choice in enumerate(seed_state.choices):
        retain_choice(index, choice, seed_score)
    for index, choice in enumerate(final_state.choices):
        retain_choice(index, choice, final_score)

    for row in coordinate_rows:
        if gcsim_optimizer_theoretical_team_package_signature(
            row.physical_state
        ) != signature:
            continue
        differing = tuple(
            index
            for index, (left, right) in enumerate(
                zip(seed_state.choices, row.physical_state.choices, strict=True)
            )
            if left.key != right.key
        )
        if len(differing) != 1:
            continue
        index = differing[0]
        retain_choice(
            index,
            row.physical_state.choices[index],
            float(row.dps_mean or 0.0),
        )

    beams: list[tuple[FourPieceSetState, ...]] = []
    score_by_choice: list[dict[tuple[str, str, str, str], float]] = []
    for index, values in enumerate(scores):
        ordered = [
            choice
            for _score, choice in sorted(
                values.values(),
                key=lambda item: (-item[0], item[1].key),
            )
        ]
        final_choice = final_state.choices[index]
        selected = ordered[: plan.coordinate_choices_per_wearer]
        if final_choice not in selected:
            if len(selected) >= plan.coordinate_choices_per_wearer:
                selected[-1] = final_choice
            else:
                selected.append(final_choice)
        selected = list(dict.fromkeys(selected))
        beams.append(tuple(selected))
        score_by_choice.append(
            {key: score for key, (score, _choice) in values.items()}
        )

    coordinate_winner = FullTeamPhysicalState(
        tuple(values[0] for values in beams)
    )
    retained: dict[
        tuple[tuple[str, str, str, str], ...], FullTeamPhysicalState
    ] = {}

    def retain_state(state: FullTeamPhysicalState) -> None:
        if len(retained) >= plan.max_candidates_per_signature:
            return
        retained.setdefault(state.key, state)

    retain_state(final_state)
    retain_state(coordinate_winner)

    # A single-layout swap is the most important recall guard: it compares a
    # coordinate winner with the exact allies/layouts selected by the race.
    for index, choices in enumerate(beams):
        for choice in choices:
            if choice == final_state.choices[index]:
                continue
            changed = list(final_state.choices)
            changed[index] = choice
            retain_state(FullTeamPhysicalState(tuple(changed)))

    ranked_products = []
    for choices in product(*beams):
        state = FullTeamPhysicalState(tuple(choices))
        score = sum(
            score_by_choice[index].get(choice.key, 0.0)
            for index, choice in enumerate(choices)
        )
        ranked_products.append((score, state))
    ranked_products.sort(key=lambda item: (-item[0], item[1].key))
    for _score, state in ranked_products:
        retain_state(state)

    # If the coordinate beam collapses to fewer than six states, retain the
    # best already-measured physical joint layouts for the same signature.
    matching_rows = tuple(
        sorted(
            (
                item
                for item in all_successful_rows
                if gcsim_optimizer_theoretical_team_package_signature(
                    item.physical_state
                ) == signature
            ),
            key=_race_rank,
        )
    )
    for row in matching_rows:
        retain_state(row.physical_state)
    return GcsimOptimizerTheoreticalLayoutSignatureDomain(
        package_signature=signature,
        race_finalist=final_state,
        coordinate_winner=coordinate_winner,
        candidates=tuple(retained.values()),
    )


def _race_rank(
    value: GcsimOptimizerTheoreticalAnytimeRaceEvaluation,
) -> tuple[float, str]:
    return (
        -float(value.dps_mean or 0.0),
        value.proposal.proposal_sha256,
    )


def _outcome_rank(
    value: GcsimFinalistOptimizerOutcome,
) -> tuple[float, object]:
    return -float(value.dps_mean), value.state.key


def _status_from_finalist(
    value: GcsimFinalistOptimizerResult,
) -> GcsimOptimizerTheoreticalLayoutScreenStatus:
    return {
        GcsimFinalistOptimizerStatus.BEST_FOUND: (
            GcsimOptimizerTheoreticalLayoutScreenStatus.COMPLETED
        ),
        GcsimFinalistOptimizerStatus.NO_SUCCESS: (
            GcsimOptimizerTheoreticalLayoutScreenStatus.NO_SUCCESS
        ),
        GcsimFinalistOptimizerStatus.CANCELLED: (
            GcsimOptimizerTheoreticalLayoutScreenStatus.CANCELLED
        ),
        GcsimFinalistOptimizerStatus.DEADLINE: (
            GcsimOptimizerTheoreticalLayoutScreenStatus.DEADLINE
        ),
    }[value.status]


def _state_payload(value: FullTeamPhysicalState) -> list[list[str]]:
    return [list(item) for item in value.key]


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
        or any(item not in "0123456789abcdef" for item in value)
    ):
        raise GcsimOptimizerTheoreticalLayoutScreenError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


def _require_schema(value: int) -> None:
    if value != GCSIM_OPTIMIZER_THEORETICAL_LAYOUT_SCREEN_SCHEMA_VERSION:
        raise GcsimOptimizerTheoreticalLayoutScreenError(
            "unsupported theoretical layout-screen schema"
        )


__all__ = [
    "GCSIM_OPTIMIZER_THEORETICAL_LAYOUT_SCREEN_PLAN_ID",
    "GCSIM_OPTIMIZER_THEORETICAL_LAYOUT_SCREEN_PLAN_VERSION",
    "GCSIM_OPTIMIZER_THEORETICAL_LAYOUT_SCREEN_SCHEMA_VERSION",
    "GcsimOptimizerTheoreticalLayoutScreenDomain",
    "GcsimOptimizerTheoreticalLayoutScreenError",
    "GcsimOptimizerTheoreticalLayoutScreenPlan",
    "GcsimOptimizerTheoreticalLayoutScreenResult",
    "GcsimOptimizerTheoreticalLayoutScreenSession",
    "GcsimOptimizerTheoreticalLayoutScreenStatus",
    "GcsimOptimizerTheoreticalLayoutSignatureDomain",
    "TheoreticalLayoutScreenProgressCallback",
    "build_gcsim_optimizer_theoretical_layout_screen_domain",
    "run_gcsim_optimizer_theoretical_layout_screen",
]
