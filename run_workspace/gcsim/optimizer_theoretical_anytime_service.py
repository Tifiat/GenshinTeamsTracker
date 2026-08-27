"""Production bounded theoretical optimizer for 4p and 2p+2p standards.

The service is inventory-independent.  It measures one compact rotation
response, then measures every eligible 4p package per wearer on two crit
panels.  The 2p+2p path first measures concrete 2p effects and forms a bounded
prospective pair domain from retained components.  It screens the resulting
package/main/profile proposals at 8 and 32 iterations, runs a bounded
optimizer-backed 32-iteration physical-layout screen inside at most six
team-package signatures, validates only the one winning layout per signature
at 200 iterations, and ordinary-reraces only overlapping leaders at 1000.

Every displayed row is therefore saveable >=200 evidence.  The result claims
only the best build found under the frozen work plan, never an exhaustive
global optimum.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
import hashlib
import json
from math import isfinite
from threading import Event, Lock
from time import monotonic

from .optimizer_anytime_response import (
    GcsimOptimizerAnytimeResponsePlan,
    GcsimOptimizerAnytimeResponseResult,
    discover_gcsim_optimizer_theoretical_anytime_response,
)
from .optimizer_cache import GcsimOptimizerCacheStore
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_product_contracts import (
    GCSIM_THEORETICAL_ANYTIME_FOUR_PIECE_WORK_PLAN_ID,
    GCSIM_THEORETICAL_ANYTIME_FOUR_PIECE_WORK_PLAN_VERSION,
    GCSIM_THEORETICAL_ANYTIME_TWO_PLUS_TWO_WORK_PLAN_ID,
    GCSIM_THEORETICAL_ANYTIME_TWO_PLUS_TWO_WORK_PLAN_VERSION,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerCacheCounters,
    GcsimOptimizerCandidateResult,
    GcsimOptimizerCoverageCounters,
    GcsimOptimizerDpsEstimate,
    GcsimOptimizerEvaluationIdentity,
    GcsimOptimizerLeaderSnapshot,
    GcsimOptimizerOperation,
    GcsimOptimizerOperationRequest,
    GcsimOptimizerProgressEvent,
    GcsimOptimizerProgressLeaderQuality,
    GcsimOptimizerProgressLeaderScope,
    GcsimOptimizerProgressStage,
    GcsimOptimizerSetReference,
    GcsimOptimizerTerminalResult,
    GcsimOptimizerTerminalStatus,
    GcsimOptimizerTimingCounters,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerTarget,
    GcsimOptimizerWorkPlan,
    GcsimTwoPlusTwoTargetPackage,
    build_gcsim_optimizer_source_simulation_identity,
    build_gcsim_optimizer_top_n,
)
from .optimizer_theoretical_anytime_candidates import (
    GcsimOptimizerTheoreticalAnytimeCandidateDomain,
    GcsimOptimizerTheoreticalAnytimeCandidatePlan,
    build_gcsim_optimizer_theoretical_anytime_candidate_domain,
    derive_gcsim_optimizer_theoretical_package_keys,
    gcsim_optimizer_theoretical_team_package_signature,
)
from .optimizer_set_impact import (
    GcsimOptimizerSetImpactPlan,
    GcsimOptimizerSetImpactResult,
    GcsimOptimizerSingleTwoPieceImpactTarget,
    discover_gcsim_optimizer_set_impacts,
)
from .optimizer_theoretical_anytime_race import (
    GcsimOptimizerTheoreticalAnytimeRaceEvaluation,
    GcsimOptimizerTheoreticalAnytimeRacePlan,
    GcsimOptimizerTheoreticalAnytimeRaceResult,
    GcsimOptimizerTheoreticalAnytimeRaceSession,
    GcsimOptimizerTheoreticalAnytimeRaceStatus,
)
from .optimizer_theoretical_anytime_validation import (
    GcsimOptimizerTheoreticalValidatedEvaluation,
    GcsimOptimizerTheoreticalValidationPlan,
    GcsimOptimizerTheoreticalValidationResult,
    GcsimOptimizerTheoreticalValidationSession,
    GcsimOptimizerTheoreticalValidationStatus,
)
from .optimizer_theoretical_layout_screen import (
    GcsimOptimizerTheoreticalLayoutScreenPlan,
    GcsimOptimizerTheoreticalLayoutScreenResult,
    GcsimOptimizerTheoreticalLayoutScreenSession,
    GcsimOptimizerTheoreticalLayoutScreenStatus,
)
from .optimizer_theoretical_packages import (
    freeze_gcsim_theoretical_pair_packages,
    gcsim_theoretical_pair_domain_sha256,
    gcsim_theoretical_pair_package_key,
)
from .optimizer_theoretical_allocation import (
    build_gcsim_optimizer_theoretical_allocation_witness,
)
from .optimizer_two_piece_signatures import (
    GcsimOptimizerTheoreticalPairDomain,
)
from .optimizer_stat_response import GcsimStatResponseTarget


GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_SERVICE_SCHEMA_VERSION = 4
GCSIM_OPTIMIZER_THEORETICAL_CURRENT_IMPLEMENTATION = "current"
GCSIM_OPTIMIZER_THEORETICAL_SHARED_IMPLEMENTATION = (
    "artifact_first_shared_experimental"
)
TheoreticalAnytimeProgressCallback = Callable[
    [GcsimOptimizerProgressEvent],
    None,
]


class GcsimOptimizerTheoreticalAnytimeError(RuntimeError):
    """Fail-closed theoretical anytime service error."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalAnytimePlan:
    response: GcsimOptimizerAnytimeResponsePlan = field(
        default_factory=GcsimOptimizerAnytimeResponsePlan
    )
    set_impact: GcsimOptimizerSetImpactPlan = field(
        default_factory=GcsimOptimizerSetImpactPlan
    )
    candidates: GcsimOptimizerTheoreticalAnytimeCandidatePlan = field(
        default_factory=GcsimOptimizerTheoreticalAnytimeCandidatePlan
    )
    race: GcsimOptimizerTheoreticalAnytimeRacePlan = field(
        default_factory=GcsimOptimizerTheoreticalAnytimeRacePlan
    )
    layout_screen: GcsimOptimizerTheoreticalLayoutScreenPlan = field(
        default_factory=GcsimOptimizerTheoreticalLayoutScreenPlan
    )
    validation: GcsimOptimizerTheoreticalValidationPlan = field(
        default_factory=GcsimOptimizerTheoreticalValidationPlan
    )
    top_n: int = 6
    max_pair_core_components_per_wearer: int = 12
    max_pair_targets_per_wearer: int = 96
    overall_deadline_seconds: float = 1800.0
    implementation_id: str = GCSIM_OPTIMIZER_THEORETICAL_CURRENT_IMPLEMENTATION
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_SERVICE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if self.implementation_id not in {
            GCSIM_OPTIMIZER_THEORETICAL_CURRENT_IMPLEMENTATION,
            GCSIM_OPTIMIZER_THEORETICAL_SHARED_IMPLEMENTATION,
        }:
            raise GcsimOptimizerTheoreticalAnytimeError(
                "unsupported theoretical implementation identity"
            )
        experimental = (
            self.implementation_id
            == GCSIM_OPTIMIZER_THEORETICAL_SHARED_IMPLEMENTATION
        )
        if not isinstance(self.response, GcsimOptimizerAnytimeResponsePlan):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "response plan must be typed"
            )
        if not isinstance(self.set_impact, GcsimOptimizerSetImpactPlan):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "set_impact plan must be typed"
            )
        if experimental and (
            not self.response.enable_nonlinear_surface
            or not self.set_impact.enable_team_interaction_panel
        ):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "experimental theoretical path requires the shared nonlinear "
                "response and team set-interaction panels"
            )
        if not self.set_impact.enable_crit_headroom_panel:
            raise GcsimOptimizerTheoreticalAnytimeError(
                "theoretical set screening requires both balanced and "
                "crit-headroom panels"
            )
        if not isinstance(
            self.candidates,
            GcsimOptimizerTheoreticalAnytimeCandidatePlan,
        ):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "candidate plan must be typed"
            )
        if not isinstance(
            self.race,
            GcsimOptimizerTheoreticalAnytimeRacePlan,
        ):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "race plan must be typed"
            )
        if not isinstance(
            self.validation,
            GcsimOptimizerTheoreticalValidationPlan,
        ):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "validation plan must be typed"
            )
        if not isinstance(
            self.layout_screen,
            GcsimOptimizerTheoreticalLayoutScreenPlan,
        ):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "layout_screen plan must be typed"
            )
        if (
            isinstance(self.top_n, bool)
            or not isinstance(self.top_n, int)
            or self.top_n <= 0
            or self.top_n > self.validation.top_n
        ):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "top_n must be positive and not exceed validation top_n"
            )
        for field_name in (
            "max_pair_core_components_per_wearer",
            "max_pair_targets_per_wearer",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 2
            ):
                raise GcsimOptimizerTheoreticalAnytimeError(
                    f"{field_name} must be an integer >= 2"
                )
        if (
            self.max_pair_targets_per_wearer
            < (
                self.max_pair_core_components_per_wearer
                * (self.max_pair_core_components_per_wearer - 1)
                // 2
            )
        ):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "pair-target cap cannot preserve the core component product"
            )
        cpu_budgets = {
            self.response.total_cpu_budget,
            self.race.total_cpu_budget,
            self.layout_screen.worker_count,
            self.validation.total_cpu_budget,
        }
        if len(cpu_budgets) != 1:
            raise GcsimOptimizerTheoreticalAnytimeError(
                "response, race, layout-screen, and validation CPU budgets "
                "must match"
            )
        if self.set_impact.worker_count != min(
            self.response.total_cpu_budget,
            self.set_impact.iterations,
        ):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "set-impact workers must consume the supported shared CPU budget"
            )
        if (
            not isfinite(self.overall_deadline_seconds)
            or self.overall_deadline_seconds <= 0
        ):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "overall_deadline_seconds must be finite and positive"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "implementation_id": self.implementation_id,
            "claim": "best_found_under_frozen_budget",
            "response": self.response.to_dict(),
            "set_impact": self.set_impact.to_dict(),
            "candidates": self.candidates.to_dict(),
            "race": self.race.to_dict(),
            "layout_screen": self.layout_screen.to_dict(),
            "validation": self.validation.to_dict(),
            "top_n": self.top_n,
            "max_pair_core_components_per_wearer": (
                self.max_pair_core_components_per_wearer
            ),
            "max_pair_targets_per_wearer": (
                self.max_pair_targets_per_wearer
            ),
            "overall_deadline_seconds": self.overall_deadline_seconds,
        }


def build_gcsim_optimizer_theoretical_shared_kernel_plan(
    *,
    cpu_budget: int = 1,
) -> GcsimOptimizerTheoreticalAnytimePlan:
    """Build the opt-in theoretical plan on the experimental response/set model."""

    if (
        isinstance(cpu_budget, bool)
        or not isinstance(cpu_budget, int)
        or cpu_budget <= 0
    ):
        raise GcsimOptimizerTheoreticalAnytimeError(
            "cpu_budget must be a positive integer"
        )
    base = GcsimOptimizerTheoreticalAnytimePlan()
    return replace(
        base,
        implementation_id=GCSIM_OPTIMIZER_THEORETICAL_SHARED_IMPLEMENTATION,
        response=replace(
            base.response,
            enable_nonlinear_surface=True,
            worker_count=min(cpu_budget, base.response.iterations),
            max_parallel_candidates=1,
            total_cpu_budget=cpu_budget,
        ),
        set_impact=replace(
            base.set_impact,
            enable_team_interaction_panel=True,
            worker_count=min(cpu_budget, base.set_impact.iterations),
        ),
        race=replace(
            base.race,
            worker_count=1,
            max_parallel_candidates=cpu_budget,
            total_cpu_budget=cpu_budget,
        ),
        layout_screen=replace(
            base.layout_screen,
            worker_count=cpu_budget,
        ),
        validation=replace(
            base.validation,
            optimizer_worker_count=cpu_budget,
            rerace_worker_count=1,
            max_parallel_reraces=cpu_budget,
            total_cpu_budget=cpu_budget,
        ),
    )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalAnytimeResult:
    terminal: GcsimOptimizerTerminalResult
    plan: GcsimOptimizerTheoreticalAnytimePlan
    progress_events: tuple[GcsimOptimizerProgressEvent, ...]
    pair_domain: GcsimOptimizerTheoreticalPairDomain | None
    response_result: GcsimOptimizerAnytimeResponseResult | None
    component_set_impact_result: GcsimOptimizerSetImpactResult | None
    set_impact_result: GcsimOptimizerSetImpactResult | None
    candidate_domain: GcsimOptimizerTheoreticalAnytimeCandidateDomain | None
    race_result: GcsimOptimizerTheoreticalAnytimeRaceResult | None
    layout_screen_result: GcsimOptimizerTheoreticalLayoutScreenResult | None = None
    validation_result: GcsimOptimizerTheoreticalValidationResult | None = None
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_SERVICE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.terminal, GcsimOptimizerTerminalResult):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "terminal must be typed"
            )
        if not isinstance(self.plan, GcsimOptimizerTheoreticalAnytimePlan):
            raise GcsimOptimizerTheoreticalAnytimeError("plan must be typed")
        object.__setattr__(
            self,
            "progress_events",
            tuple(self.progress_events),
        )
        if tuple(item.sequence for item in self.progress_events) != tuple(
            range(len(self.progress_events))
        ):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "progress sequence must be contiguous"
            )
        pair_mode = (
            self.terminal.request.operation
            is GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO
        )
        if self.pair_domain is not None and not pair_mode:
            raise GcsimOptimizerTheoreticalAnytimeError(
                "pair-domain presence differs from the operation"
            )
        if (
            pair_mode
            and self.pair_domain is None
            and self.terminal.status
            is not GcsimOptimizerTerminalStatus.NOT_READY
        ):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "ready pair operation must retain its pair domain"
            )
        for value in (
            self.component_set_impact_result,
            self.set_impact_result,
        ):
            if value is not None and not isinstance(
                value,
                GcsimOptimizerSetImpactResult,
            ):
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "theoretical set-impact evidence must be typed"
                )
        if self.component_set_impact_result is not None and not pair_mode:
            raise GcsimOptimizerTheoreticalAnytimeError(
                "single-2p component evidence belongs only to 2p+2p"
            )
        if (
            self.component_set_impact_result is not None
            or self.set_impact_result is not None
        ) and self.response_result is None:
            raise GcsimOptimizerTheoreticalAnytimeError(
                "set-impact evidence requires its paired response"
            )
        if self.response_result is not None and any(
            value is not None
            and value.response_evidence_sha256
            != self.response_result.evidence_sha256
            for value in (
                self.component_set_impact_result,
                self.set_impact_result,
            )
        ):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "set-impact evidence differs from the retained response"
            )
        if self.layout_screen_result is not None:
            if not isinstance(
                self.layout_screen_result,
                GcsimOptimizerTheoreticalLayoutScreenResult,
            ):
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "layout-screen evidence must be typed"
                )
            if self.race_result is None or (
                self.layout_screen_result.domain.race_evidence_sha256
                != self.race_result.evidence_sha256
            ):
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "layout-screen evidence differs from its race"
                )
        if self.validation_result is not None:
            if self.layout_screen_result is None:
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "validation evidence requires its layout screen"
                )
            if (
                self.validation_result.finalist_result.request_snapshot.finalists
                != self.layout_screen_result.selected_finalists
            ):
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "validation finalists differ from layout-screen winners"
                )

    @property
    def best_found(self):
        return self.terminal.best_found

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "terminal": self.terminal.to_dict(),
            "plan_sha256": self.plan.identity_sha256,
            "progress_events": [
                item.to_dict() for item in self.progress_events
            ],
            "pair_domain": (
                None if self.pair_domain is None else self.pair_domain.to_dict()
            ),
            "response_evidence_sha256": (
                None
                if self.response_result is None
                else self.response_result.evidence_sha256
            ),
            "component_set_impact_sha256": (
                None
                if self.component_set_impact_result is None
                else _set_impact_identity(
                    self.component_set_impact_result
                )
            ),
            "set_impact_sha256": (
                None
                if self.set_impact_result is None
                else _set_impact_identity(self.set_impact_result)
            ),
            "candidate_domain_sha256": (
                None
                if self.candidate_domain is None
                else self.candidate_domain.identity_sha256
            ),
            "race_evidence_sha256": (
                None
                if self.race_result is None
                else self.race_result.evidence_sha256
            ),
            "layout_screen_evidence_sha256": (
                None
                if self.layout_screen_result is None
                else self.layout_screen_result.evidence_sha256
            ),
            "validation_evidence_sha256": (
                None
                if self.validation_result is None
                else self.validation_result.evidence_sha256
            ),
        }


def build_gcsim_optimizer_theoretical_anytime_operation_request(
    *,
    operation: GcsimOptimizerOperation,
    engine_context: GcsimOptimizerEngineContext,
    prepared_config_text: str,
    wearers: Sequence[GcsimOptimizerWearerIdentity],
    plan: GcsimOptimizerTheoreticalAnytimePlan | None = None,
    pair_domain: GcsimOptimizerTheoreticalPairDomain | None = None,
    target_identity_text: str | None = None,
    simulation_options_identity_text: str | None = None,
) -> GcsimOptimizerOperationRequest:
    """Create the versioned product request without account/database inputs."""

    selected_plan = plan or GcsimOptimizerTheoreticalAnytimePlan()
    _validate_operation_pair_domain(
        operation,
        pair_domain,
        engine_context=engine_context,
    )
    source = build_gcsim_optimizer_source_simulation_identity(
        engine_context=engine_context,
        prepared_config_text=prepared_config_text,
        wearers=tuple(wearers),
        target_identity_text=target_identity_text,
        simulation_options_identity_text=simulation_options_identity_text,
    )
    plan_id, plan_version = _work_plan_identity(operation)
    return GcsimOptimizerOperationRequest(
        operation=operation,
        source_simulation=source,
        work_plan=GcsimOptimizerWorkPlan(
            operation=operation,
            plan_id=plan_id,
            plan_version=plan_version,
            parameters=_work_plan_parameters(
                selected_plan,
                pair_domain=pair_domain,
            ),
        ),
    )


class GcsimOptimizerTheoreticalAnytimeSession:
    """One-shot owner of a bounded 4p or 2p+2p theoretical run."""

    def __init__(
        self,
        request: GcsimOptimizerOperationRequest,
        *,
        engine_context: GcsimOptimizerEngineContext,
        prepared_config_text: str,
        plan: GcsimOptimizerTheoreticalAnytimePlan | None = None,
        pair_domain: GcsimOptimizerTheoreticalPairDomain | None = None,
        progress_callback: TheoreticalAnytimeProgressCallback | None = None,
        cache_store: GcsimOptimizerCacheStore | None = None,
        enable_cache: bool = True,
        evaluation_session_factory: Callable[[object], object] | None = None,
        stat_response_target: GcsimStatResponseTarget | None = None,
        race_simulator_factory: Callable[..., object] | None = None,
        finalist_session_factory: Callable[[object], object] | None = None,
        response_discovery: Callable[..., object] | None = None,
        set_impact_discovery: Callable[..., object] | None = None,
        candidate_domain_builder: Callable[..., object] | None = None,
        race_session_factory: Callable[..., object] | None = None,
        layout_screen_session_factory: Callable[..., object] | None = None,
        validation_session_factory: Callable[..., object] | None = None,
        environment: Mapping[str, str] | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isinstance(request, GcsimOptimizerOperationRequest):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "request must be typed"
            )
        self.request = request
        self.engine_context = engine_context
        self.prepared_config_text = prepared_config_text
        self.plan = plan or GcsimOptimizerTheoreticalAnytimePlan()
        self.pair_domain = pair_domain
        self.progress_callback = progress_callback
        self.cache_store = cache_store
        self.enable_cache = enable_cache
        self.evaluation_session_factory = evaluation_session_factory
        self.stat_response_target = stat_response_target
        self.race_simulator_factory = race_simulator_factory
        self.finalist_session_factory = finalist_session_factory
        self.response_discovery = (
            response_discovery
            or discover_gcsim_optimizer_theoretical_anytime_response
        )
        self.set_impact_discovery = (
            set_impact_discovery
            or discover_gcsim_optimizer_set_impacts
        )
        self.candidate_domain_builder = (
            candidate_domain_builder
            or build_gcsim_optimizer_theoretical_anytime_candidate_domain
        )
        self.race_session_factory = race_session_factory
        self.layout_screen_session_factory = layout_screen_session_factory
        self.validation_session_factory = validation_session_factory
        self.environment = dict(environment or {})
        self.clock = clock
        self._cancel_event = Event()
        self._lock = Lock()
        self._active: object | None = None
        self._started = False
        self._progress: list[GcsimOptimizerProgressEvent] = []
        self._timing: dict[str, float] = {}
        self._stage_started: dict[str, float] = {}
        self._component_set_impact_result = None
        self._set_impact_result = None
        self._candidate_pair_packages = (
            freeze_gcsim_theoretical_pair_packages(None)
        )

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            active = self._active
        if active is not None and callable(getattr(active, "cancel", None)):
            try:
                active.cancel()
            except Exception:
                pass

    def run(self) -> GcsimOptimizerTheoreticalAnytimeResult:
        with self._lock:
            if self._started:
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "theoretical anytime sessions are one-shot"
                )
            self._started = True
        started = self.clock()
        deadline = started + self.plan.overall_deadline_seconds
        response = None
        component_set_impact = None
        set_impact = None
        domain = None
        race = None
        layout_screen = None
        validation = None
        packages = freeze_gcsim_theoretical_pair_packages(None)
        candidate_packages = packages
        try:
            self._emit(
                GcsimOptimizerProgressStage.PREFLIGHT,
                started=started,
                deadline=deadline,
                completed=0,
                planned=1,
            )
            not_ready = self._preflight(started)
            if not_ready is not None:
                return self._result(
                    not_ready,
                    response=response,
                    domain=domain,
                    race=race,
                    validation=validation,
                )
            self._emit(
                GcsimOptimizerProgressStage.PREFLIGHT,
                started=started,
                deadline=deadline,
                completed=1,
                planned=1,
            )
            self._raise_if_interrupted(deadline)
            packages = _pair_packages(self.pair_domain)

            _kind, package_keys = (
                derive_gcsim_optimizer_theoretical_package_keys(
                    self.engine_context,
                    two_plus_two_packages=(
                        packages if packages else None
                    ),
                )
            )
            representative_keys = (package_keys[0],) * 4
            self._start_stage("response_scan")
            response_plan = _trim_response_plan(
                self.plan.response,
                remaining=deadline - self.clock(),
            )
            response = self.response_discovery(
                self.request,
                engine_context=self.engine_context,
                prepared_config_text=self.prepared_config_text,
                package_keys=representative_keys,
                two_plus_two_packages=packages,
                plan=response_plan,
                progress_callback=lambda completed, planned, hits: (
                    self._emit(
                        GcsimOptimizerProgressStage.RESPONSE_SCAN,
                        started=started,
                        deadline=deadline,
                        completed=completed,
                        planned=planned,
                        cache_hits=hits,
                    )
                ),
                environment=self.environment,
                stat_response_target=self.stat_response_target,
                is_cancelled=self._cancel_event.is_set,
                clock=self.clock,
            )
            if not isinstance(response, GcsimOptimizerAnytimeResponseResult):
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "response discovery returned an invalid result"
                )
            self._finish_stage("response_scan")
            self._raise_if_interrupted(deadline)

            self._start_stage("set_impact_scan")
            if (
                self.request.operation
                is GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE
            ):
                impact_targets = _four_piece_impact_targets(
                    self.request.source_simulation.wearers,
                    package_keys,
                    engine_context=self.engine_context,
                )
            else:
                if self.pair_domain is None:
                    raise GcsimOptimizerTheoreticalAnytimeError(
                        "2p+2p set impact requires its pair domain"
                    )
                component_targets = _two_piece_component_targets(
                    self.request.source_simulation.wearers,
                    self.pair_domain,
                )
                component_set_impact = self.set_impact_discovery(
                    engine_context=self.engine_context,
                    prepared_config_text=self.prepared_config_text,
                    targets=component_targets,
                    response=response,
                    stat_response_target=self.stat_response_target,
                    plan=_trim_set_impact_plan(
                        self.plan.set_impact,
                        remaining=deadline - self.clock(),
                    ),
                    progress_callback=lambda completed, planned: (
                        self._emit(
                            GcsimOptimizerProgressStage.SET_IMPACT_SCAN,
                            started=started,
                            deadline=deadline,
                            completed=completed,
                            planned=planned,
                        )
                    ),
                    environment=self.environment,
                    is_cancelled=self._cancel_event.is_set,
                    clock=self.clock,
                )
                if not isinstance(
                    component_set_impact,
                    GcsimOptimizerSetImpactResult,
                ):
                    raise GcsimOptimizerTheoreticalAnytimeError(
                        "2p component impact discovery returned an invalid result"
                    )
                if (
                    component_set_impact.response_evidence_sha256
                    != response.evidence_sha256
                ):
                    raise GcsimOptimizerTheoreticalAnytimeError(
                        "2p component impact differs from its response evidence"
                    )
                self._component_set_impact_result = (
                    component_set_impact
                )
                impact_targets, candidate_packages = (
                    _prospective_two_plus_two_targets(
                        self.request.source_simulation.wearers,
                        self.pair_domain,
                        component_set_impact,
                        max_core_components_per_wearer=(
                            self.plan.max_pair_core_components_per_wearer
                        ),
                        max_targets_per_wearer=(
                            self.plan.max_pair_targets_per_wearer
                        ),
                    )
                )
                candidate_packages = (
                    freeze_gcsim_theoretical_pair_packages(
                        candidate_packages
                    )
                )
                self._candidate_pair_packages = candidate_packages
            set_impact = self.set_impact_discovery(
                engine_context=self.engine_context,
                prepared_config_text=self.prepared_config_text,
                targets=impact_targets,
                response=response,
                stat_response_target=self.stat_response_target,
                plan=_trim_set_impact_plan(
                    self.plan.set_impact,
                    remaining=deadline - self.clock(),
                ),
                progress_callback=lambda completed, planned: (
                    self._emit(
                        GcsimOptimizerProgressStage.SET_IMPACT_SCAN,
                        started=started,
                        deadline=deadline,
                        completed=completed,
                        planned=planned,
                    )
                ),
                environment=self.environment,
                is_cancelled=self._cancel_event.is_set,
                clock=self.clock,
            )
            if not isinstance(
                set_impact,
                GcsimOptimizerSetImpactResult,
            ):
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "package set-impact discovery returned an invalid result"
                )
            if (
                set_impact.response_evidence_sha256
                != response.evidence_sha256
            ):
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "package set-impact differs from its response evidence"
                )
            self._set_impact_result = set_impact
            self._finish_stage("set_impact_scan")
            self._raise_if_interrupted(deadline)

            self._start_stage("candidate_generation")
            domain = self.candidate_domain_builder(
                engine_context=self.engine_context,
                wearers=self.request.source_simulation.wearers,
                response_profiles=response.profiles,
                set_impact=set_impact,
                two_plus_two_packages=(
                    candidate_packages
                    if candidate_packages
                    else None
                ),
                plan=self.plan.candidates,
            )
            if not isinstance(
                domain,
                GcsimOptimizerTheoreticalAnytimeCandidateDomain,
            ):
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "candidate builder returned an invalid domain"
                )
            self._finish_stage("candidate_generation")
            self._emit(
                GcsimOptimizerProgressStage.CANDIDATE_GENERATION,
                started=started,
                deadline=deadline,
                completed=len(domain.proposals),
                planned=len(domain.proposals),
            )
            self._raise_if_interrupted(deadline)

            self._start_stage("screening")
            race_options = dict(
                engine_context=self.engine_context,
                domain=domain,
                two_plus_two_packages=(
                    candidate_packages
                    if candidate_packages
                    else None
                ),
                plan=_trim_race_plan(
                    self.plan.race,
                    remaining=deadline - self.clock(),
                ),
                progress_callback=lambda tier, completed, planned, hits, leader: (
                    self._emit_race_progress(
                        tier,
                        completed=completed,
                        planned=planned,
                        cache_hits=hits,
                        leader=leader,
                        started=started,
                        deadline=deadline,
                    )
                ),
                cache_store=self.cache_store,
                enable_cache=self.enable_cache,
                session_factory=self.evaluation_session_factory,
                environment=self.environment,
                simulator_factory=self.race_simulator_factory,
                stat_response_target=self.stat_response_target,
                clock=self.clock,
            )
            race_session = (
                GcsimOptimizerTheoreticalAnytimeRaceSession(
                    self.prepared_config_text,
                    **race_options,
                )
                if self.race_session_factory is None
                else self.race_session_factory(
                    self.prepared_config_text,
                    **race_options,
                )
            )
            self._set_active(race_session)
            if self._cancel_event.is_set():
                race_session.cancel()
            try:
                race = race_session.run()
            finally:
                self._clear_active(race_session)
            if not isinstance(
                race,
                GcsimOptimizerTheoreticalAnytimeRaceResult,
            ):
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "race session returned an invalid result"
                )
            self._finish_stage("screening")
            if (
                race.status
                is GcsimOptimizerTheoreticalAnytimeRaceStatus.CANCELLED
                or (
                    race.status
                    is GcsimOptimizerTheoreticalAnytimeRaceStatus.DEADLINE
                    and not race.physical_finalists
                )
            ):
                terminal = self._terminal(
                    _terminal_status_from_race(race.status),
                    f"theoretical_anytime_race_{race.status.value}",
                    started,
                    response=response,
                    domain=domain,
                    race=race,
                )
                return self._result(
                    terminal,
                    response=response,
                    domain=domain,
                    race=race,
                    validation=validation,
                )
            if not race.physical_finalists:
                terminal = self._terminal(
                    _terminal_status_from_race(race.status),
                    f"theoretical_anytime_race_{race.status.value}",
                    started,
                    response=response,
                    domain=domain,
                    race=race,
                )
                return self._result(
                    terminal,
                    response=response,
                    domain=domain,
                    race=race,
                    validation=validation,
                )
            self._raise_if_interrupted(deadline)

            self._start_stage("layout_screen")
            layout_screen_options = dict(
                engine_context=self.engine_context,
                prepared_config_text=self.prepared_config_text,
                layout_catalog=domain.layout_catalog,
                race_result=race,
                two_plus_two_packages=(
                    candidate_packages
                    if candidate_packages
                    else None
                ),
                plan=_trim_layout_screen_plan(
                    self.plan.layout_screen,
                    remaining=deadline - self.clock(),
                ),
                progress_callback=(
                    lambda completed, planned, hits, leader: (
                        self._emit_layout_screen_progress(
                            completed=completed,
                            planned=planned,
                            cache_hits=hits,
                            leader=leader,
                            started=started,
                            deadline=deadline,
                        )
                    )
                ),
                cache_store=self.cache_store,
                enable_cache=self.enable_cache,
                finalist_session_factory=self.finalist_session_factory,
                environment=self.environment,
                stat_response_target=self.stat_response_target,
                clock=self.clock,
            )
            layout_screen_session = (
                GcsimOptimizerTheoreticalLayoutScreenSession(
                    self.request,
                    **layout_screen_options,
                )
                if self.layout_screen_session_factory is None
                else self.layout_screen_session_factory(
                    self.request,
                    **layout_screen_options,
                )
            )
            self._set_active(layout_screen_session)
            if self._cancel_event.is_set():
                layout_screen_session.cancel()
            try:
                layout_screen = layout_screen_session.run()
            finally:
                self._clear_active(layout_screen_session)
            if not isinstance(
                layout_screen,
                GcsimOptimizerTheoreticalLayoutScreenResult,
            ):
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "layout-screen session returned an invalid result"
                )
            self._finish_stage("layout_screen")
            if not layout_screen.selected_finalists:
                terminal = self._terminal(
                    _terminal_status_from_layout_screen(
                        layout_screen.status
                    ),
                    (
                        "theoretical_layout_screen_"
                        f"{layout_screen.status.value}"
                    ),
                    started,
                    response=response,
                    domain=domain,
                    race=race,
                    layout_screen=layout_screen,
                )
                return self._result(
                    terminal,
                    response=response,
                    domain=domain,
                    race=race,
                    layout_screen=layout_screen,
                    validation=validation,
                )
            self._raise_if_interrupted(deadline)

            self._start_stage("final_validation")
            validation_options = dict(
                engine_context=self.engine_context,
                prepared_config_text=self.prepared_config_text,
                layout_catalog=domain.layout_catalog,
                finalists=layout_screen.selected_finalists,
                two_plus_two_packages=(
                    candidate_packages
                    if candidate_packages
                    else None
                ),
                plan=_trim_validation_plan(
                    self.plan.validation,
                    remaining=deadline - self.clock(),
                ),
                progress_callback=lambda stage, completed, planned, hits, leader: (
                    self._emit_validation_progress(
                        stage,
                        completed=completed,
                        planned=planned,
                        cache_hits=hits,
                        leader=leader,
                        started=started,
                        deadline=deadline,
                    )
                ),
                cache_store=self.cache_store,
                enable_cache=self.enable_cache,
                finalist_session_factory=self.finalist_session_factory,
                evaluation_session_factory=self.evaluation_session_factory,
                environment=self.environment,
                stat_response_target=self.stat_response_target,
                clock=self.clock,
            )
            validation_session = (
                GcsimOptimizerTheoreticalValidationSession(
                    self.request,
                    **validation_options,
                )
                if self.validation_session_factory is None
                else self.validation_session_factory(
                    self.request,
                    **validation_options,
                )
            )
            self._set_active(validation_session)
            if self._cancel_event.is_set():
                validation_session.cancel()
            try:
                validation = validation_session.run()
            finally:
                self._clear_active(validation_session)
            if not isinstance(
                validation,
                GcsimOptimizerTheoreticalValidationResult,
            ):
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "validation session returned an invalid result"
                )
            self._finish_stage("final_validation")
            terminal = self._terminal_from_validation(
                validation,
                started=started,
                response=response,
                domain=domain,
                race=race,
                layout_screen=layout_screen,
            )
            leader = (
                None
                if terminal.best_found is None
                else GcsimOptimizerLeaderSnapshot(
                    candidate_identity_sha256=(
                        terminal.best_found.candidate_identity_sha256
                    ),
                    estimate=terminal.best_found.estimate,
                    scope=GcsimOptimizerProgressLeaderScope.RUN,
                    quality=GcsimOptimizerProgressLeaderQuality.FINAL,
                )
            )
            self._emit(
                GcsimOptimizerProgressStage.COMPLETED,
                started=started,
                deadline=deadline,
                completed=len(validation.evaluations),
                planned=len(validation.evaluations),
                current_iterations=(
                    None if leader is None else leader.estimate.iterations
                ),
                leader=leader,
            )
            return self._result(
                terminal,
                response=response,
                domain=domain,
                race=race,
                layout_screen=layout_screen,
                validation=validation,
            )
        except _TheoreticalAnytimeInterrupted as exc:
            terminal = self._terminal(
                (
                    GcsimOptimizerTerminalStatus.CANCELLED
                    if exc.cancelled
                    else GcsimOptimizerTerminalStatus.DEADLINE
                ),
                exc.reason,
                started,
                response=response,
                domain=domain,
                race=race,
                layout_screen=layout_screen,
                validation=validation,
            )
            return self._result(
                terminal,
                response=response,
                domain=domain,
                race=race,
                layout_screen=layout_screen,
                validation=validation,
            )
        except Exception as exc:
            if self._cancel_event.is_set():
                terminal = self._terminal(
                    GcsimOptimizerTerminalStatus.CANCELLED,
                    "theoretical_anytime_cancelled",
                    started,
                    response=response,
                    domain=domain,
                    race=race,
                    layout_screen=layout_screen,
                    validation=validation,
                )
                return self._result(
                    terminal,
                    response=response,
                    domain=domain,
                    race=race,
                    layout_screen=layout_screen,
                    validation=validation,
                )
            terminal = self._terminal(
                GcsimOptimizerTerminalStatus.FAILED,
                "theoretical_anytime_orchestration_failed",
                started,
                response=response,
                domain=domain,
                race=race,
                layout_screen=layout_screen,
                validation=validation,
                error=f"{type(exc).__name__}: {exc}",
            )
            return self._result(
                terminal,
                response=response,
                domain=domain,
                race=race,
                layout_screen=layout_screen,
                validation=validation,
            )

    def _preflight(
        self,
        started: float,
    ) -> GcsimOptimizerTerminalResult | None:
        if self.request.operation not in {
            GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
            GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO,
        }:
            return self._terminal(
                GcsimOptimizerTerminalStatus.NOT_READY,
                "theoretical_anytime_requires_theoretical_operation",
                started,
            )
        if (
            self.request.source_simulation.engine_binding_sha256
            != self.engine_context.binding_sha256
            or self.request.source_simulation.catalog_fingerprint
            != self.engine_context.catalog.source_fingerprint
        ):
            return self._terminal(
                GcsimOptimizerTerminalStatus.NOT_READY,
                "theoretical_anytime_engine_binding_mismatch",
                started,
            )
        if (
            self.request.source_simulation.prepared_config_sha256
            != _text_sha256(self.prepared_config_text)
            or len(self.request.source_simulation.wearers) != 4
        ):
            return self._terminal(
                GcsimOptimizerTerminalStatus.NOT_READY,
                "theoretical_anytime_source_config_mismatch",
                started,
            )
        try:
            _validate_operation_pair_domain(
                self.request.operation,
                self.pair_domain,
                engine_context=self.engine_context,
            )
        except Exception:
            return self._terminal(
                GcsimOptimizerTerminalStatus.NOT_READY,
                "theoretical_anytime_pair_domain_mismatch",
                started,
            )
        plan_id, plan_version = _work_plan_identity(self.request.operation)
        expected_parameters = _work_plan_parameters(
            self.plan,
            pair_domain=self.pair_domain,
        )
        if (
            self.request.work_plan.plan_id != plan_id
            or self.request.work_plan.plan_version != plan_version
            or _canonical_sha256(
                _thaw_json(self.request.work_plan.parameters)
            )
            != _canonical_sha256(expected_parameters)
        ):
            return self._terminal(
                GcsimOptimizerTerminalStatus.NOT_READY,
                "theoretical_anytime_work_plan_mismatch",
                started,
            )
        return None

    def _terminal_from_validation(
        self,
        validation: GcsimOptimizerTheoreticalValidationResult,
        *,
        started: float,
        response,
        domain,
        race,
        layout_screen,
    ) -> GcsimOptimizerTerminalResult:
        best_by_package_signature = {}
        for item in validation.evaluations:
            best_by_package_signature.setdefault(
                gcsim_optimizer_theoretical_team_package_signature(
                    item.state
                ),
                item,
            )
        candidates = tuple(
            self._candidate_result(item, response=response, domain=domain)
            for item in best_by_package_signature.values()
        )
        top_n = build_gcsim_optimizer_top_n(
            candidates,
            operation=self.request.operation,
            top_n=self.plan.top_n,
            confidence_sigma=self.plan.validation.confidence_sigma,
        )
        status = {
            GcsimOptimizerTheoreticalValidationStatus.COMPLETED: (
                GcsimOptimizerTerminalStatus.BEST_FOUND
            ),
            GcsimOptimizerTheoreticalValidationStatus.COMPLETED_WITH_ERRORS: (
                GcsimOptimizerTerminalStatus.BEST_FOUND
            ),
            GcsimOptimizerTheoreticalValidationStatus.NO_SUCCESS: (
                GcsimOptimizerTerminalStatus.NO_SUCCESS
            ),
            GcsimOptimizerTheoreticalValidationStatus.CANCELLED: (
                GcsimOptimizerTerminalStatus.CANCELLED
            ),
            GcsimOptimizerTheoreticalValidationStatus.DEADLINE: (
                GcsimOptimizerTerminalStatus.DEADLINE
            ),
        }[validation.status]
        if (
            status is GcsimOptimizerTerminalStatus.BEST_FOUND
            and not top_n.entries
        ):
            status = GcsimOptimizerTerminalStatus.NO_SUCCESS
        return self._terminal(
            status,
            f"theoretical_anytime_validation_{validation.status.value}",
            started,
            top_n=top_n,
            response=response,
            domain=domain,
            race=race,
            layout_screen=layout_screen,
            validation=validation,
        )

    def _candidate_result(
        self,
        value: GcsimOptimizerTheoreticalValidatedEvaluation,
        *,
        response: GcsimOptimizerAnytimeResponseResult,
        domain: GcsimOptimizerTheoreticalAnytimeCandidateDomain,
    ) -> GcsimOptimizerCandidateResult:
        return GcsimOptimizerCandidateResult(
            request_sha256=self.request.request_sha256,
            candidate_identity_sha256=value.candidate_identity_sha256,
            evaluation=GcsimOptimizerEvaluationIdentity(
                request_sha256=self.request.request_sha256,
                source_simulation_sha256=(
                    self.request.source_simulation.identity_sha256
                ),
                work_plan_sha256=self.request.work_plan.identity_sha256,
                engine_binding_sha256=self.engine_context.binding_sha256,
                compiled_config_sha256=value.compiled_config_sha256,
                execution_identity_sha256=(
                    value.execution_identity_sha256
                ),
            ),
            estimate=GcsimOptimizerDpsEstimate(
                dps_mean=value.dps_mean,
                dps_se=value.dps_se,
                iterations=value.iterations,
            ),
            target_packages=_targets_for_state(
                self.request,
                value.state,
                engine_context=self.engine_context,
                pair_packages=self._candidate_pair_packages,
            ),
            evidence_sha256={
                "candidate_domain": domain.identity_sha256,
                "rotation_response": response.evidence_sha256,
                "validated_evaluation": value.evidence_sha256,
                "optimizer_input": (
                    value.finalist_outcome.optimizer_input_sha256
                ),
                "optimized_config": (
                    value.finalist_outcome.optimized_config_sha256
                ),
                "allocation": (
                    value.finalist_outcome.allocation_sha256
                ),
                "validation_result": (
                    value.finalist_outcome.result_json_sha256
                ),
            },
            theoretical_allocation=(
                build_gcsim_optimizer_theoretical_allocation_witness(
                    request_sha256=self.request.request_sha256,
                    wearers=self.request.source_simulation.wearers,
                    outcome=value.finalist_outcome,
                    layout_catalog=domain.layout_catalog,
                )
            ),
        )

    def _terminal(
        self,
        status: GcsimOptimizerTerminalStatus,
        stop_reason: str,
        started: float,
        *,
        top_n=None,
        response=None,
        domain=None,
        race=None,
        layout_screen=None,
        validation=None,
        error: str = "",
    ) -> GcsimOptimizerTerminalResult:
        coverage = _coverage(
            response=response,
            component_set_impact=self._component_set_impact_result,
            set_impact=self._set_impact_result,
            domain=domain,
            race=race,
            layout_screen=layout_screen,
            validation=validation,
        )
        hits, requested = _cache_counts(
            response=response,
            race=race,
            layout_screen=layout_screen,
            validation=validation,
        )
        evidence = {
            "service_plan": self.plan.identity_sha256,
            "source_simulation": (
                self.request.source_simulation.identity_sha256
            ),
        }
        if response is not None:
            evidence["rotation_response"] = response.evidence_sha256
        if self._component_set_impact_result is not None:
            evidence["two_piece_component_impact"] = (
                _set_impact_identity(
                    self._component_set_impact_result
                )
            )
        if self._set_impact_result is not None:
            evidence["set_impact"] = _set_impact_identity(
                self._set_impact_result
            )
        if domain is not None:
            evidence["candidate_domain"] = domain.identity_sha256
        if race is not None:
            evidence["race"] = race.evidence_sha256
        if layout_screen is not None:
            evidence["layout_screen"] = layout_screen.evidence_sha256
        if validation is not None:
            evidence["validation"] = validation.evidence_sha256
        return GcsimOptimizerTerminalResult(
            request=self.request,
            status=status,
            stop_reason=stop_reason,
            elapsed_seconds=max(self.clock() - started, 0.0),
            top_n=top_n,
            evidence_sha256=evidence,
            coverage=coverage,
            cache=GcsimOptimizerCacheCounters(
                hits=hits,
                misses=max(requested - hits, 0),
            ),
            timing=GcsimOptimizerTimingCounters(self._timing),
            error=error,
        )

    def _result(
        self,
        terminal,
        *,
        response,
        domain,
        race,
        validation,
        layout_screen=None,
    ) -> GcsimOptimizerTheoreticalAnytimeResult:
        return GcsimOptimizerTheoreticalAnytimeResult(
            terminal=terminal,
            plan=self.plan,
            progress_events=tuple(self._progress),
            pair_domain=self.pair_domain,
            response_result=response,
            component_set_impact_result=(
                self._component_set_impact_result
            ),
            set_impact_result=self._set_impact_result,
            candidate_domain=domain,
            race_result=race,
            layout_screen_result=layout_screen,
            validation_result=validation,
        )

    def _emit_race_progress(
        self,
        tier: str,
        *,
        completed: int,
        planned: int,
        cache_hits: int,
        leader: GcsimOptimizerTheoreticalAnytimeRaceEvaluation | None,
        started: float,
        deadline: float,
    ) -> None:
        stage, current_iterations = {
            "package_screen_8": (
                GcsimOptimizerProgressStage.SCREENING,
                8,
            ),
            "main_coordinate_8": (
                GcsimOptimizerProgressStage.SCREENING,
                8,
            ),
            "main_combine_8": (
                GcsimOptimizerProgressStage.SCREENING,
                8,
            ),
            "refine_32": (GcsimOptimizerProgressStage.REFINEMENT, 32),
        }[tier]
        snapshot = None
        if leader is not None and leader.dps_mean is not None:
            snapshot = GcsimOptimizerLeaderSnapshot(
                candidate_identity_sha256=leader.proposal.proposal_sha256,
                estimate=GcsimOptimizerDpsEstimate(
                    dps_mean=leader.dps_mean,
                    dps_se=leader.dps_se,
                    iterations=leader.tier_iterations,
                ),
                scope=GcsimOptimizerProgressLeaderScope.STAGE,
                quality=GcsimOptimizerProgressLeaderQuality.PROVISIONAL,
            )
        self._emit(
            stage,
            started=started,
            deadline=deadline,
            completed=completed,
            planned=planned,
            cache_hits=cache_hits,
            current_iterations=current_iterations,
            leader=snapshot,
        )

    def _emit_validation_progress(
        self,
        stage: str,
        *,
        completed: int,
        planned: int,
        cache_hits: int,
        leader: GcsimOptimizerTheoreticalValidatedEvaluation | None,
        started: float,
        deadline: float,
    ) -> None:
        current_iterations = 1000 if stage == "rerace_1000" else 200
        snapshot = None
        if leader is not None:
            snapshot = GcsimOptimizerLeaderSnapshot(
                candidate_identity_sha256=(
                    leader.candidate_identity_sha256
                ),
                estimate=GcsimOptimizerDpsEstimate(
                    dps_mean=leader.dps_mean,
                    dps_se=leader.dps_se,
                    iterations=leader.iterations,
                ),
                scope=GcsimOptimizerProgressLeaderScope.STAGE,
                quality=GcsimOptimizerProgressLeaderQuality.VERIFIED,
            )
        self._emit(
            (
                GcsimOptimizerProgressStage.RERACE
                if stage == "rerace_1000"
                else GcsimOptimizerProgressStage.FINAL_VALIDATION
            ),
            started=started,
            deadline=deadline,
            completed=completed,
            planned=planned,
            cache_hits=cache_hits,
            current_iterations=current_iterations,
            leader=snapshot,
        )

    def _emit_layout_screen_progress(
        self,
        *,
        completed: int,
        planned: int,
        cache_hits: int,
        leader,
        started: float,
        deadline: float,
    ) -> None:
        snapshot = None
        if leader is not None:
            snapshot = GcsimOptimizerLeaderSnapshot(
                candidate_identity_sha256=leader.cache_identity_sha256,
                estimate=GcsimOptimizerDpsEstimate(
                    dps_mean=leader.dps_mean,
                    dps_se=leader.dps_se,
                    iterations=leader.iterations,
                ),
                scope=GcsimOptimizerProgressLeaderScope.STAGE,
                quality=(
                    GcsimOptimizerProgressLeaderQuality.PROVISIONAL
                ),
            )
        self._emit(
            GcsimOptimizerProgressStage.REFINEMENT,
            started=started,
            deadline=deadline,
            completed=completed,
            planned=planned,
            cache_hits=cache_hits,
            current_iterations=self.plan.layout_screen.iterations,
            leader=snapshot,
        )

    def _emit(
        self,
        stage,
        *,
        started,
        deadline,
        completed,
        planned,
        cache_hits=0,
        current_iterations=None,
        leader=None,
    ) -> None:
        event = GcsimOptimizerProgressEvent(
            request_sha256=self.request.request_sha256,
            operation=self.request.operation,
            work_plan_sha256=self.request.work_plan.identity_sha256,
            stage=stage,
            sequence=len(self._progress),
            completed_work=completed,
            planned_work=planned,
            elapsed_seconds=max(self.clock() - started, 0.0),
            remaining_seconds=max(deadline - self.clock(), 0.0),
            cache_hits=cache_hits,
            current_iterations=current_iterations,
            current_best=leader,
        )
        self._progress.append(event)
        if self.progress_callback is not None:
            try:
                self.progress_callback(event)
            except Exception:
                pass

    def _raise_if_interrupted(self, deadline: float) -> None:
        if self._cancel_event.is_set():
            raise _TheoreticalAnytimeInterrupted(
                "theoretical_anytime_cancelled",
                cancelled=True,
            )
        if self.clock() >= deadline:
            raise _TheoreticalAnytimeInterrupted(
                "theoretical_anytime_deadline_reached",
                cancelled=False,
            )

    def _set_active(self, value: object) -> None:
        with self._lock:
            self._active = value

    def _clear_active(self, value: object) -> None:
        with self._lock:
            if self._active is value:
                self._active = None

    def _start_stage(self, stage: str) -> None:
        self._stage_started[stage] = self.clock()

    def _finish_stage(self, stage: str) -> None:
        stage_started = self._stage_started.pop(stage, self.clock())
        self._timing[stage] = max(self.clock() - stage_started, 0.0)


@dataclass(frozen=True, slots=True)
class _TheoreticalAnytimeInterrupted(Exception):
    reason: str
    cancelled: bool


def run_gcsim_optimizer_theoretical_anytime(
    request: GcsimOptimizerOperationRequest,
    **kwargs,
) -> GcsimOptimizerTheoreticalAnytimeResult:
    return GcsimOptimizerTheoreticalAnytimeSession(
        request,
        **kwargs,
    ).run()


def _targets_for_state(
    request,
    state,
    *,
    engine_context,
    pair_packages,
) -> tuple[GcsimOptimizerWearerTarget, ...]:
    wearer_by_key = {
        item.gcsim_character_key: item
        for item in request.source_simulation.wearers
    }
    targets = []
    pair_mode = (
        request.operation
        is GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO
    )
    for choice in state.choices:
        if choice.wearer_id not in wearer_by_key:
            raise GcsimOptimizerTheoreticalAnytimeError(
                "validated state references an unknown wearer"
            )
        if pair_mode:
            package = pair_packages.get(choice.set_key)
            if package is None:
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "validated 2p+2p state references a package outside "
                    "the measured candidate mapping"
                )
        else:
            if choice.set_key in pair_packages:
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "validated 4p state unexpectedly references a 2p+2p "
                    "package"
                )
            package = GcsimFourPieceTargetPackage(
                GcsimOptimizerSetReference(
                    set_uid=choice.set_key,
                    gcsim_set_key=choice.set_key,
                    engine_binding_sha256=engine_context.binding_sha256,
                    catalog_fingerprint=(
                        engine_context.catalog.source_fingerprint
                    ),
                )
            )
        targets.append(
            GcsimOptimizerWearerTarget(
                wearer=wearer_by_key[choice.wearer_id],
                package=package,
            )
        )
    return tuple(targets)


def _four_piece_impact_targets(
    wearers: Sequence[GcsimOptimizerWearerIdentity],
    package_keys: Sequence[str],
    *,
    engine_context: GcsimOptimizerEngineContext,
) -> tuple[GcsimOptimizerWearerTarget, ...]:
    return tuple(
        GcsimOptimizerWearerTarget(
            wearer=wearer,
            package=GcsimFourPieceTargetPackage(
                GcsimOptimizerSetReference(
                    set_uid=package_key,
                    gcsim_set_key=package_key,
                    engine_binding_sha256=(
                        engine_context.binding_sha256
                    ),
                    catalog_fingerprint=(
                        engine_context.catalog.source_fingerprint
                    ),
                )
            ),
        )
        for wearer in wearers
        for package_key in package_keys
    )


def _two_piece_component_targets(
    wearers: Sequence[GcsimOptimizerWearerIdentity],
    pair_domain: GcsimOptimizerTheoreticalPairDomain,
) -> tuple[GcsimOptimizerSingleTwoPieceImpactTarget, ...]:
    return tuple(
        GcsimOptimizerSingleTwoPieceImpactTarget(
            wearer=wearer,
            set_ref=GcsimOptimizerSetReference(
                set_uid=descriptor.set_key,
                gcsim_set_key=descriptor.set_key,
                engine_binding_sha256=(
                    pair_domain.engine_binding_sha256
                ),
                catalog_fingerprint=(
                    pair_domain.catalog_fingerprint
                ),
            ),
        )
        for wearer in wearers
        for descriptor in pair_domain.descriptors
    )


def _prospective_two_plus_two_targets(
    wearers: Sequence[GcsimOptimizerWearerIdentity],
    pair_domain: GcsimOptimizerTheoreticalPairDomain,
    component_impact: GcsimOptimizerSetImpactResult,
    *,
    max_core_components_per_wearer: int,
    max_targets_per_wearer: int,
) -> tuple[
    tuple[GcsimOptimizerWearerTarget, ...],
    Mapping[str, GcsimTwoPlusTwoTargetPackage],
]:
    descriptor_keys = {
        descriptor.set_key for descriptor in pair_domain.descriptors
    }
    rows_by_wearer = {
        wearer: {} for wearer in wearers
    }
    for row in component_impact.rows:
        target = row.target
        if not isinstance(
            target,
            GcsimOptimizerSingleTwoPieceImpactTarget,
        ):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "2p component scan contains a package-level target"
            )
        if target.wearer not in rows_by_wearer:
            raise GcsimOptimizerTheoreticalAnytimeError(
                "2p component scan belongs to another wearer"
            )
        set_ref = target.set_ref
        set_key = set_ref.gcsim_set_key
        if (
            set_key not in descriptor_keys
            or set_ref.engine_binding_sha256
            != pair_domain.engine_binding_sha256
            or set_ref.catalog_fingerprint
            != pair_domain.catalog_fingerprint
        ):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "2p component scan differs from its frozen pair domain"
            )
        wearer_rows = rows_by_wearer[target.wearer]
        if set_key in wearer_rows:
            raise GcsimOptimizerTheoreticalAnytimeError(
                "2p component scan contains a duplicate wearer/set row"
            )
        wearer_rows[set_key] = row
    if any(
        set(rows_by_wearer[wearer]) != descriptor_keys
        for wearer in wearers
    ):
        raise GcsimOptimizerTheoreticalAnytimeError(
            "2p component scan does not cover every concrete set/wearer"
        )

    selected_targets = []
    selected_packages: dict[
        str,
        GcsimTwoPlusTwoTargetPackage,
    ] = {}
    for wearer in wearers:
        row_by_key = rows_by_wearer[wearer]
        retained = [
            row for row in row_by_key.values() if row.retained
        ]
        if len(retained) < 2:
            retained = sorted(
                row_by_key.values(),
                key=lambda row: (
                    -row.surrogate_dps,
                    row.target.set_ref.gcsim_set_key,
                ),
            )[:2]
        retained.sort(
            key=lambda row: (
                -row.surrogate_dps,
                row.target.set_ref.gcsim_set_key,
            )
        )
        retained_keys = {
            row.target.set_ref.gcsim_set_key for row in retained
        }
        core_keys = {
            row.target.set_ref.gcsim_set_key
            for row in retained[
                :max_core_components_per_wearer
            ]
        }
        score_by_key = {
            row.target.set_ref.gcsim_set_key: row.surrogate_dps
            for row in retained
        }
        ranked_groups = []
        for group in pair_domain.groups:
            eligible_aliases = tuple(
                package
                for package in group.concrete_aliases
                if {
                    package.set_a.gcsim_set_key,
                    package.set_b.gcsim_set_key,
                }.issubset(retained_keys)
            )
            if not eligible_aliases:
                continue
            alias_scores = tuple(
                (
                    score_by_key[package.set_a.gcsim_set_key]
                    + score_by_key[package.set_b.gcsim_set_key],
                    package,
                )
                for package in eligible_aliases
            )
            best_score, best_alias = min(
                alias_scores,
                key=lambda item: (
                    -item[0],
                    item[1].set_a.gcsim_set_key,
                    item[1].set_b.gcsim_set_key,
                ),
            )
            covered_keys = frozenset(
                key
                for package in eligible_aliases
                for key in (
                    package.set_a.gcsim_set_key,
                    package.set_b.gcsim_set_key,
                )
            )
            core = any(
                {
                    package.set_a.gcsim_set_key,
                    package.set_b.gcsim_set_key,
                }.issubset(core_keys)
                for package in eligible_aliases
            )
            ranked_groups.append(
                (
                    float(best_score),
                    group.modifier_key_relation
                    != "distinct_static_keys",
                    core,
                    covered_keys,
                    group,
                    best_alias,
                )
            )
        ranked_groups.sort(
            key=lambda item: (
                -item[0],
                -int(item[1]),
                item[5].set_a.gcsim_set_key,
                item[5].set_b.gcsim_set_key,
            )
        )
        selected = {
            item[4].pair_signature_sha256: item
            for item in ranked_groups
            if item[2]
        }
        if len(selected) > max_targets_per_wearer:
            raise GcsimOptimizerTheoreticalAnytimeError(
                "2p core product exceeds its explicit target cap"
            )
        covered = {
            key
            for item in selected.values()
            for key in item[3]
        }
        for set_key in sorted(retained_keys - covered):
            best = next(
                (
                    item
                    for item in ranked_groups
                    if set_key in item[3]
                ),
                None,
            )
            if best is None:
                raise GcsimOptimizerTheoreticalAnytimeError(
                    "retained 2p component has no legal prospective pair"
                )
            selected.setdefault(
                best[4].pair_signature_sha256,
                best,
            )
            covered.update(best[3])
        for item in ranked_groups:
            if len(selected) >= max_targets_per_wearer:
                break
            selected.setdefault(
                item[4].pair_signature_sha256,
                item,
            )
        if not retained_keys.issubset(covered):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "prospective pairs lost retained component coverage"
            )
        selected_rows = tuple(
            sorted(
                selected.values(),
                key=lambda item: (
                    -item[0],
                    -int(item[1]),
                    item[5].set_a.gcsim_set_key,
                    item[5].set_b.gcsim_set_key,
                ),
            )
        )
        if len(selected_rows) > max_targets_per_wearer:
            raise GcsimOptimizerTheoreticalAnytimeError(
                "prospective 2p+2p domain exceeds its explicit cap"
            )
        for (
            _score,
            _non_distinct,
            _core,
            _covered,
            _group,
            package,
        ) in selected_rows:
            package_key = gcsim_theoretical_pair_package_key(package)
            selected_packages[package_key] = package
            selected_targets.append(
                GcsimOptimizerWearerTarget(
                    wearer=wearer,
                    package=package,
                )
            )
    return (
        tuple(selected_targets),
        dict(sorted(selected_packages.items())),
    )


def _pair_packages(
    domain: GcsimOptimizerTheoreticalPairDomain | None,
):
    if domain is None:
        return freeze_gcsim_theoretical_pair_packages(None)
    return freeze_gcsim_theoretical_pair_packages(
        {
            gcsim_theoretical_pair_package_key(group.representative): (
                group.representative
            )
            for group in domain.groups
        }
    )


def _validate_operation_pair_domain(
    operation,
    domain,
    *,
    engine_context,
) -> None:
    if operation not in {
        GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
        GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO,
    }:
        raise GcsimOptimizerTheoreticalAnytimeError(
            "operation must be theoretical 4p or 2p+2p"
        )
    pair_mode = (
        operation is GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO
    )
    if pair_mode != (domain is not None):
        raise GcsimOptimizerTheoreticalAnytimeError(
            "pair domain presence differs from operation"
        )
    if domain is not None:
        if not isinstance(domain, GcsimOptimizerTheoreticalPairDomain):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "pair_domain must be typed"
            )
        if (
            domain.engine_binding_sha256 != engine_context.binding_sha256
            or domain.catalog_fingerprint
            != engine_context.catalog.source_fingerprint
            or not domain.groups
        ):
            raise GcsimOptimizerTheoreticalAnytimeError(
                "pair domain differs from the trusted engine or is empty"
            )


def _work_plan_identity(operation):
    if operation is GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE:
        return (
            GCSIM_THEORETICAL_ANYTIME_FOUR_PIECE_WORK_PLAN_ID,
            GCSIM_THEORETICAL_ANYTIME_FOUR_PIECE_WORK_PLAN_VERSION,
        )
    if operation is GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO:
        return (
            GCSIM_THEORETICAL_ANYTIME_TWO_PLUS_TWO_WORK_PLAN_ID,
            GCSIM_THEORETICAL_ANYTIME_TWO_PLUS_TWO_WORK_PLAN_VERSION,
        )
    raise GcsimOptimizerTheoreticalAnytimeError(
        "unsupported theoretical operation"
    )


def _work_plan_parameters(plan, *, pair_domain):
    packages = _pair_packages(pair_domain)
    return {
        "claim": "best_found_under_frozen_budget",
        "service": plan.to_dict(),
        "pair_domain_sha256": (
            ""
            if pair_domain is None
            else _canonical_sha256(pair_domain.to_dict())
        ),
        "pair_package_domain_sha256": (
            ""
            if not packages
            else gcsim_theoretical_pair_domain_sha256(packages)
        ),
    }


def _trim_response_plan(plan, *, remaining):
    return replace(
        plan,
        overall_deadline_seconds=min(
            plan.overall_deadline_seconds,
            max(remaining, 1e-6),
        ),
    )


def _trim_set_impact_plan(plan, *, remaining):
    return replace(
        plan,
        overall_deadline_seconds=min(
            plan.overall_deadline_seconds,
            max(remaining, 1e-6),
        ),
    )


def _trim_race_plan(plan, *, remaining):
    return replace(
        plan,
        overall_deadline_seconds=min(
            plan.overall_deadline_seconds,
            max(remaining, 1e-6),
        ),
    )


def _trim_layout_screen_plan(plan, *, remaining):
    return replace(
        plan,
        overall_deadline_seconds=min(
            plan.overall_deadline_seconds,
            max(remaining, 1e-6),
        ),
    )


def _trim_validation_plan(plan, *, remaining):
    return replace(
        plan,
        overall_deadline_seconds=min(
            plan.overall_deadline_seconds,
            max(remaining, 1e-6),
        ),
    )


def _terminal_status_from_race(status):
    return {
        GcsimOptimizerTheoreticalAnytimeRaceStatus.COMPLETED: (
            GcsimOptimizerTerminalStatus.NO_SUCCESS
        ),
        GcsimOptimizerTheoreticalAnytimeRaceStatus.COMPLETED_WITH_ERRORS: (
            GcsimOptimizerTerminalStatus.NO_SUCCESS
        ),
        GcsimOptimizerTheoreticalAnytimeRaceStatus.NO_SUCCESS: (
            GcsimOptimizerTerminalStatus.NO_SUCCESS
        ),
        GcsimOptimizerTheoreticalAnytimeRaceStatus.CANCELLED: (
            GcsimOptimizerTerminalStatus.CANCELLED
        ),
        GcsimOptimizerTheoreticalAnytimeRaceStatus.DEADLINE: (
            GcsimOptimizerTerminalStatus.DEADLINE
        ),
    }[status]


def _terminal_status_from_layout_screen(status):
    return {
        GcsimOptimizerTheoreticalLayoutScreenStatus.COMPLETED: (
            GcsimOptimizerTerminalStatus.NO_SUCCESS
        ),
        GcsimOptimizerTheoreticalLayoutScreenStatus.COMPLETED_WITH_ERRORS: (
            GcsimOptimizerTerminalStatus.NO_SUCCESS
        ),
        GcsimOptimizerTheoreticalLayoutScreenStatus.NO_SUCCESS: (
            GcsimOptimizerTerminalStatus.NO_SUCCESS
        ),
        GcsimOptimizerTheoreticalLayoutScreenStatus.CANCELLED: (
            GcsimOptimizerTerminalStatus.CANCELLED
        ),
        GcsimOptimizerTheoreticalLayoutScreenStatus.DEADLINE: (
            GcsimOptimizerTerminalStatus.DEADLINE
        ),
    }[status]


def _coverage(
    *,
    response,
    component_set_impact,
    set_impact,
    domain,
    race,
    validation,
    layout_screen=None,
):
    counters: Counter[str] = Counter()
    if response is not None:
        counters["response_probe_count"] = response.planned_probe_count
        counters["response_success_count"] = response.successful_probe_count
        counters["response_failure_count"] = response.failed_probe_count
    if component_set_impact is not None:
        counters["two_piece_component_probe_count"] = len(
            component_set_impact.rows
        )
        counters["two_piece_component_retained_count"] = sum(
            item.retained for item in component_set_impact.rows
        )
    if set_impact is not None:
        counters["set_impact_probe_count"] = len(set_impact.rows)
        counters["set_impact_retained_count"] = sum(
            item.retained for item in set_impact.rows
        )
    if domain is not None:
        counters["theoretical_package_count"] = len(domain.package_keys)
        counters["candidate_proposal_count"] = len(domain.proposals)
        for pool in domain.wearer_pools:
            slot = pool.wearer.team_slot
            counters[
                f"wearer_{slot}_alternative_count"
            ] = len(pool.alternatives)
            counters[
                f"wearer_{slot}_retained_package_count"
            ] = len(pool.retained_package_keys)
            counters[
                f"wearer_{slot}_screened_anchor_count"
            ] = len(pool.anchor_package_keys)
            counters[
                f"wearer_{slot}_retained_unscreened_count"
            ] = len(pool.unscreened_retained_package_keys)
            counters["retained_package_count"] += len(
                pool.retained_package_keys
            )
            counters["screened_anchor_count"] += len(
                pool.anchor_package_keys
            )
            counters["retained_unscreened_count"] += len(
                pool.unscreened_retained_package_keys
            )
    if race is not None:
        counters["race_finalist_count"] = len(race.physical_finalists)
        counters["race_tier_count"] = len(race.tier_traces)
    if layout_screen is not None:
        counters["layout_screen_signature_count"] = len(
            layout_screen.domain.signatures
        )
        counters["layout_screen_candidate_count"] = len(
            layout_screen.domain.candidates
        )
        counters["layout_screen_attempt_count"] = (
            layout_screen.finalist_result.attempted_count
        )
        counters["layout_screen_success_count"] = (
            layout_screen.finalist_result.successful_count
        )
        counters["layout_screen_selected_count"] = len(
            layout_screen.selected_finalists
        )
    if validation is not None:
        counters["validation_attempt_count"] = (
            validation.finalist_result.attempted_count
        )
        counters["validation_success_count"] = len(validation.evaluations)
        counters["rerace_request_count"] = (
            validation.requested_rerace_count
        )
    return GcsimOptimizerCoverageCounters(counters)


def _cache_counts(*, response, race, validation, layout_screen=None):
    hits = response.cache_hit_count if response is not None else 0
    requested = response.planned_probe_count if response is not None else 0
    if race is not None:
        for trace in race.tier_traces:
            rows = tuple(trace.evaluations)
            requested += len(rows)
            hits += sum(int(item.metrics.cache_hit) for item in rows)
    if layout_screen is not None:
        requested += layout_screen.finalist_result.attempted_count
        hits += sum(
            int(item.cache_hit)
            for item in layout_screen.finalist_result.attempts
        )
    if validation is not None:
        requested += validation.finalist_result.attempted_count
        hits += sum(
            int(attempt.cache_hit)
            for attempt in validation.finalist_result.attempts
        )
        requested += len(validation.rerace_results)
        hits += sum(
            int(item.cache_hit) for item in validation.rerace_results
        )
    return hits, requested


def _thaw_json(value):
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw_json(item) for item in value]
    return value


def _set_impact_identity(
    value: GcsimOptimizerSetImpactResult,
) -> str:
    return _canonical_sha256(
        {
            "plan": value.plan.to_dict(),
            "response_evidence_sha256": (
                value.response_evidence_sha256
            ),
            "rows": [
                {
                    "target": row.target.to_dict(),
                    "classification": row.classification.value,
                    "surrogate_dps": row.surrogate_dps,
                    "evidence_sha256": row.evidence_sha256,
                }
                for row in value.rows
            ],
        }
    )


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


def _require_schema(value: int) -> None:
    if value != GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_SERVICE_SCHEMA_VERSION:
        raise GcsimOptimizerTheoreticalAnytimeError(
            "unsupported theoretical anytime service schema"
        )


__all__ = [
    "GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_SERVICE_SCHEMA_VERSION",
    "GCSIM_OPTIMIZER_THEORETICAL_CURRENT_IMPLEMENTATION",
    "GCSIM_OPTIMIZER_THEORETICAL_SHARED_IMPLEMENTATION",
    "GcsimOptimizerTheoreticalAnytimeError",
    "GcsimOptimizerTheoreticalAnytimePlan",
    "GcsimOptimizerTheoreticalAnytimeResult",
    "GcsimOptimizerTheoreticalAnytimeSession",
    "TheoreticalAnytimeProgressCallback",
    "build_gcsim_optimizer_theoretical_anytime_operation_request",
    "build_gcsim_optimizer_theoretical_shared_kernel_plan",
    "run_gcsim_optimizer_theoretical_anytime",
]
