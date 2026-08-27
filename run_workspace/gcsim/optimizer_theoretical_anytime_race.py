"""Bounded package/main 8 -> 32 ordinary-GCSIM race for theoretical candidates.

This module deliberately stops before expensive finalist validation.  It first
screens package combinations, then compares main-stat layouts and cheap
equal-investment substat profiles *inside the same package signature*.  Only
after that like-for-like refinement does it promote at most 16 proposals to 32
iterations and return at most six distinct ordered team-package signatures for
the existing 200/1000 validation layer.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
import hashlib
from itertools import product
import json
from math import isfinite
import os
from threading import Event, Lock
from time import monotonic
from typing import Protocol

from .farming_evaluator import (
    FarmingSessionFactory,
    GcsimFarmingBatchResult,
    GcsimFarmingBatchStatus,
    GcsimFarmingEvaluationResult,
    GcsimFarmingEvaluationScheduler,
    GcsimFarmingEvaluationStatus,
    GcsimFarmingSchedulerBudget,
)
from .farming_pipeline import (
    GcsimFarmingFullTeamBatchSimulator,
    GcsimFarmingScreeningFidelity,
)
from .farming_search import FourPieceSetState, SetProfileCandidate
from .farming_team_search import (
    TEAM_SIM_CANCELLED,
    TEAM_SIM_FAILED,
    TEAM_SIM_PASSED,
    TEAM_SIM_TIMEOUT,
    FullTeamPhysicalState,
    FullTeamProbeState,
    FullTeamSimulationMetrics,
    FullTeamSimulationRequest,
    ProbeKey,
)
from .optimizer_cache import GcsimOptimizerCacheStore
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_product_contracts import (
    GcsimOptimizerTargetPackageKind,
    GcsimTwoPlusTwoTargetPackage,
)
from .optimizer_theoretical_anytime_candidates import (
    GcsimOptimizerTheoreticalAnytimeCandidateDomain,
    GcsimOptimizerTheoreticalAnytimeProposal,
    derive_gcsim_optimizer_theoretical_package_keys,
    gcsim_optimizer_theoretical_team_package_signature,
)
from .optimizer_theoretical_packages import (
    freeze_gcsim_theoretical_pair_packages,
)
from .optimizer_stat_response import GcsimStatResponseTarget


GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_RACE_SCHEMA_VERSION = 2
GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_RACE_PLAN_ID = (
    "theoretical_anytime_race"
)
GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_RACE_PLAN_VERSION = 5

TheoreticalAnytimeRaceProgressCallback = Callable[
    [
        str,
        int,
        int,
        int,
        "GcsimOptimizerTheoreticalAnytimeRaceEvaluation | None",
    ],
    None,
]


class GcsimOptimizerTheoreticalAnytimeRaceError(RuntimeError):
    """Raised when a theoretical race cannot preserve its frozen contract."""


class GcsimOptimizerTheoreticalAnytimeRaceStatus(str, Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    NO_SUCCESS = "no_success"
    CANCELLED = "cancelled"
    DEADLINE = "deadline"


class GcsimOptimizerTheoreticalAnytimeTierStatus(str, Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    NO_SUCCESS = "no_success"
    CANCELLED = "cancelled"
    DEADLINE = "deadline"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalAnytimeRaceTier:
    tier_id: str
    iterations: int
    max_candidates: int
    min_survivors: int
    timeout_seconds: float
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_RACE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if (
            not isinstance(self.tier_id, str)
            or not self.tier_id
            or self.tier_id != self.tier_id.strip()
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
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
                raise GcsimOptimizerTheoreticalAnytimeRaceError(
                    f"{field_name} must be a positive integer"
                )
        if self.min_survivors > self.max_candidates:
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "tier min_survivors exceeds max_candidates"
            )
        if not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
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


def _default_tiers(
) -> tuple[GcsimOptimizerTheoreticalAnytimeRaceTier, ...]:
    return (
        GcsimOptimizerTheoreticalAnytimeRaceTier(
            "package_screen_8",
            8,
            64,
            16,
            90.0,
        ),
        GcsimOptimizerTheoreticalAnytimeRaceTier(
            "main_coordinate_8",
            8,
            384,
            16,
            150.0,
        ),
        GcsimOptimizerTheoreticalAnytimeRaceTier(
            "main_combine_8",
            8,
            384,
            16,
            150.0,
        ),
        GcsimOptimizerTheoreticalAnytimeRaceTier(
            "refine_32",
            32,
            16,
            6,
            120.0,
        ),
    )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalAnytimeRacePlan:
    tiers: tuple[GcsimOptimizerTheoreticalAnytimeRaceTier, ...] = field(
        default_factory=_default_tiers
    )
    worker_count: int = 1
    max_parallel_candidates: int = 1
    total_cpu_budget: int = 1
    confidence_sigma: float = 2.0
    relative_elimination_margin: float = 0.0075
    max_refined_package_signatures: int = 6
    max_coordinate_candidates_per_signature: int = 64
    max_combination_candidates_per_signature: int = 64
    combination_choices_per_wearer: int = 3
    max_physical_finalists: int = 6
    overall_deadline_seconds: float = 480.0
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_RACE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        tiers = tuple(self.tiers)
        if any(
            not isinstance(
                item,
                GcsimOptimizerTheoreticalAnytimeRaceTier,
            )
            for item in tiers
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "race tiers must be typed"
            )
        if tuple(
            (
                item.tier_id,
                item.iterations,
                item.max_candidates,
                item.min_survivors,
            )
            for item in tiers
        ) != (
            ("package_screen_8", 8, 64, 16),
            ("main_coordinate_8", 8, 384, 16),
            ("main_combine_8", 8, 384, 16),
            ("refine_32", 32, 16, 6),
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "theoretical race requires frozen package-8/64 -> "
                "coordinate-8/384 -> combine-8/384 -> 32/16 tiers"
            )
        for field_name in (
            "worker_count",
            "max_parallel_candidates",
            "total_cpu_budget",
            "max_refined_package_signatures",
            "max_coordinate_candidates_per_signature",
            "max_combination_candidates_per_signature",
            "combination_choices_per_wearer",
            "max_physical_finalists",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise GcsimOptimizerTheoreticalAnytimeRaceError(
                    f"{field_name} must be a positive integer"
                )
        if (
            self.max_refined_package_signatures
            * self.max_coordinate_candidates_per_signature
            > self.tiers[1].max_candidates
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "coordinate refinement caps exceed their frozen tier"
            )
        if (
            self.max_refined_package_signatures
            * self.max_combination_candidates_per_signature
            > self.tiers[2].max_candidates
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "combination refinement caps exceed their frozen tier"
            )
        if self.combination_choices_per_wearer > 4:
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "combination_choices_per_wearer may not exceed four"
            )
        if self.worker_count > self.total_cpu_budget:
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "race worker_count exceeds total_cpu_budget"
            )
        logical_cpus = os.cpu_count() or 1
        if self.total_cpu_budget > logical_cpus:
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "race total_cpu_budget exceeds detected logical CPUs"
            )
        if self.max_physical_finalists > 6:
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "theoretical screening may return at most six physical finalists"
            )
        if not isfinite(self.confidence_sigma) or self.confidence_sigma <= 0:
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "confidence_sigma must be finite and positive"
            )
        if (
            not isfinite(self.relative_elimination_margin)
            or not 0 <= self.relative_elimination_margin < 0.1
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "relative_elimination_margin must be in [0, 0.1)"
            )
        if (
            not isfinite(self.overall_deadline_seconds)
            or self.overall_deadline_seconds <= 0
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "overall_deadline_seconds must be finite and positive"
            )
        object.__setattr__(self, "tiers", tiers)

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_RACE_PLAN_ID,
            "plan_version": (
                GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_RACE_PLAN_VERSION
            ),
            "tiers": [item.to_dict() for item in self.tiers],
            "worker_count": self.worker_count,
            "max_parallel_candidates": self.max_parallel_candidates,
            "total_cpu_budget": self.total_cpu_budget,
            "confidence_sigma": self.confidence_sigma,
            "relative_elimination_margin": (
                self.relative_elimination_margin
            ),
            "max_refined_package_signatures": (
                self.max_refined_package_signatures
            ),
            "max_coordinate_candidates_per_signature": (
                self.max_coordinate_candidates_per_signature
            ),
            "max_combination_candidates_per_signature": (
                self.max_combination_candidates_per_signature
            ),
            "combination_choices_per_wearer": (
                self.combination_choices_per_wearer
            ),
            "max_physical_finalists": self.max_physical_finalists,
            "overall_deadline_seconds": self.overall_deadline_seconds,
            "seed_policy": "ordinary_gcsim_process_seed_v1",
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalAnytimeRaceEvaluation:
    tier_id: str
    tier_iterations: int
    proposal_ordinal: int
    proposal: GcsimOptimizerTheoreticalAnytimeProposal
    evaluation_context_sha256: str
    metrics: FullTeamSimulationMetrics
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_RACE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if (
            not isinstance(self.tier_id, str)
            or not self.tier_id
            or self.tier_id != self.tier_id.strip()
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "evaluation tier_id must be non-empty trimmed text"
            )
        if (
            isinstance(self.tier_iterations, bool)
            or not isinstance(self.tier_iterations, int)
            or self.tier_iterations <= 0
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "evaluation tier_iterations must be positive"
            )
        if (
            isinstance(self.proposal_ordinal, bool)
            or not isinstance(self.proposal_ordinal, int)
            or self.proposal_ordinal < 0
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "proposal_ordinal must be non-negative"
            )
        if not isinstance(
            self.proposal,
            GcsimOptimizerTheoreticalAnytimeProposal,
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "evaluation proposal must be typed"
            )
        _require_sha256(
            self.evaluation_context_sha256,
            "evaluation_context_sha256",
        )
        if not isinstance(self.metrics, FullTeamSimulationMetrics):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "evaluation metrics must be typed"
            )
        if (
            self.metrics.status == TEAM_SIM_PASSED
            and self.metrics.iterations != self.tier_iterations
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "successful evaluation fidelity differs from its race tier"
            )

    @property
    def success(self) -> bool:
        return self.metrics.status == TEAM_SIM_PASSED

    @property
    def dps_mean(self) -> float | None:
        return self.metrics.dps_mean

    @property
    def dps_se(self) -> float | None:
        return self.metrics.dps_se

    @property
    def physical_state(self) -> FullTeamPhysicalState:
        return self.proposal.state.physical_state

    @property
    def evidence_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tier_id": self.tier_id,
            "tier_iterations": self.tier_iterations,
            "proposal_ordinal": self.proposal_ordinal,
            "proposal_sha256": self.proposal.proposal_sha256,
            "evaluation_context_sha256": self.evaluation_context_sha256,
            "metrics": _metrics_payload(self.metrics),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalAnytimeRaceTierTrace:
    tier: GcsimOptimizerTheoreticalAnytimeRaceTier
    status: GcsimOptimizerTheoreticalAnytimeTierStatus
    evaluation_context_sha256: str
    evaluations: tuple[
        GcsimOptimizerTheoreticalAnytimeRaceEvaluation, ...
    ]
    selected_proposal_sha256: tuple[str, ...]
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_RACE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(
            self.tier,
            GcsimOptimizerTheoreticalAnytimeRaceTier,
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "tier trace requires a typed tier"
            )
        if not isinstance(
            self.status,
            GcsimOptimizerTheoreticalAnytimeTierStatus,
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "tier trace status must be typed"
            )
        _require_sha256(
            self.evaluation_context_sha256,
            "evaluation_context_sha256",
        )
        evaluations = tuple(self.evaluations)
        selected = tuple(self.selected_proposal_sha256)
        object.__setattr__(self, "evaluations", evaluations)
        object.__setattr__(
            self,
            "selected_proposal_sha256",
            selected,
        )
        if any(
            not isinstance(
                item,
                GcsimOptimizerTheoreticalAnytimeRaceEvaluation,
            )
            or item.tier_id != self.tier.tier_id
            or item.tier_iterations != self.tier.iterations
            or item.evaluation_context_sha256
            != self.evaluation_context_sha256
            for item in evaluations
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "tier trace mixes incompatible evaluations"
            )
        proposal_ids = {
            item.proposal.proposal_sha256 for item in evaluations
        }
        if (
            len(selected) != len(set(selected))
            or any(item not in proposal_ids for item in selected)
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "tier trace selected proposals are invalid"
            )
        for item in selected:
            _require_sha256(item, "selected_proposal_sha256")

    @property
    def evidence_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tier": self.tier.to_dict(),
            "status": self.status.value,
            "evaluation_context_sha256": self.evaluation_context_sha256,
            "evaluations": [
                item.evidence_sha256 for item in self.evaluations
            ],
            "selected_proposal_sha256": list(
                self.selected_proposal_sha256
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalAnytimeRaceResult:
    status: GcsimOptimizerTheoreticalAnytimeRaceStatus
    domain_identity_sha256: str
    engine_binding_sha256: str
    source_config_sha256: str
    plan_identity_sha256: str
    tier_traces: tuple[
        GcsimOptimizerTheoreticalAnytimeRaceTierTrace, ...
    ]
    finalist_evaluations: tuple[
        GcsimOptimizerTheoreticalAnytimeRaceEvaluation, ...
    ]
    physical_finalists: tuple[FullTeamPhysicalState, ...]
    evidence_sha256: str
    elapsed_seconds: float
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_RACE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(
            self.status,
            GcsimOptimizerTheoreticalAnytimeRaceStatus,
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "race result status must be typed"
            )
        for field_name in (
            "domain_identity_sha256",
            "engine_binding_sha256",
            "source_config_sha256",
            "plan_identity_sha256",
            "evidence_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        traces = tuple(self.tier_traces)
        evaluations = tuple(self.finalist_evaluations)
        finalists = tuple(self.physical_finalists)
        object.__setattr__(self, "tier_traces", traces)
        object.__setattr__(
            self,
            "finalist_evaluations",
            evaluations,
        )
        object.__setattr__(
            self,
            "physical_finalists",
            finalists,
        )
        if any(
            not isinstance(
                item,
                GcsimOptimizerTheoreticalAnytimeRaceTierTrace,
            )
            for item in traces
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "race result tier traces must be typed"
            )
        if (
            len(evaluations) > 6
            or any(
                not item.success or item.tier_iterations != 32
                for item in evaluations
            )
            or evaluations
            != tuple(sorted(evaluations, key=_evaluation_rank))
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "finalist evaluations must be successful ordered 32-iteration rows"
            )
        expected_finalists = tuple(
            item.physical_state for item in evaluations
        )
        if finalists != expected_finalists:
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "physical finalists differ from finalist evidence"
            )
        if len({item.key for item in finalists}) != len(finalists):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "physical finalists must be unique"
            )
        if len(
            {
                gcsim_optimizer_theoretical_team_package_signature(
                    item
                )
                for item in finalists
            }
        ) != len(finalists):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "physical finalists must use distinct team package signatures"
            )
        if not isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "elapsed_seconds must be finite and non-negative"
            )

    @property
    def best_evaluation(
        self,
    ) -> GcsimOptimizerTheoreticalAnytimeRaceEvaluation | None:
        return (
            self.finalist_evaluations[0]
            if self.finalist_evaluations
            else None
        )


class _TierSimulator(Protocol):
    evaluation_context_sha256: str

    def __call__(
        self,
        requests: tuple[FullTeamSimulationRequest, ...],
    ) -> Mapping[ProbeKey, FullTeamSimulationMetrics]: ...

    def cancel(self) -> None: ...


TheoreticalAnytimeSimulatorFactory = Callable[..., _TierSimulator]


class _CapturingScheduler:
    def __init__(
        self,
        scheduler: GcsimFarmingEvaluationScheduler,
        holder: list[GcsimFarmingBatchResult],
    ) -> None:
        self._scheduler = scheduler
        self._holder = holder

    def cancel(self) -> None:
        self._scheduler.cancel()

    def run(self) -> GcsimFarmingBatchResult:
        result = self._scheduler.run()
        self._holder.append(result)
        return result


class GcsimOptimizerTheoreticalAnytimeRaceSession:
    """One-shot cancellable owner of theoretical 8/32 screening."""

    def __init__(
        self,
        prepared_config_text: str,
        *,
        engine_context: GcsimOptimizerEngineContext,
        domain: GcsimOptimizerTheoreticalAnytimeCandidateDomain,
        two_plus_two_packages: Mapping[
            str,
            GcsimTwoPlusTwoTargetPackage,
        ] | None = None,
        plan: GcsimOptimizerTheoreticalAnytimeRacePlan | None = None,
        progress_callback: (
            TheoreticalAnytimeRaceProgressCallback | None
        ) = None,
        cache_store: GcsimOptimizerCacheStore | None = None,
        enable_cache: bool = True,
        session_factory: FarmingSessionFactory | None = None,
        environment: Mapping[str, str] | None = None,
        clock: Callable[[], float] = monotonic,
        simulator_factory: (
            TheoreticalAnytimeSimulatorFactory | None
        ) = None,
        stat_response_target: GcsimStatResponseTarget | None = None,
    ) -> None:
        if (
            not isinstance(prepared_config_text, str)
            or not prepared_config_text.strip()
            or "\x00" in prepared_config_text
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "prepared_config_text must be non-empty and contain no NUL"
            )
        if (
            not isinstance(engine_context, GcsimOptimizerEngineContext)
            or not engine_context.trusted
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "theoretical race requires a trusted engine context"
            )
        if not isinstance(
            domain,
            GcsimOptimizerTheoreticalAnytimeCandidateDomain,
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "domain must be a typed theoretical candidate domain"
            )
        selected_plan = (
            plan or GcsimOptimizerTheoreticalAnytimeRacePlan()
        )
        if not isinstance(
            selected_plan,
            GcsimOptimizerTheoreticalAnytimeRacePlan,
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "plan must be typed"
            )
        if progress_callback is not None and not callable(
            progress_callback
        ):
            raise TypeError("progress_callback must be callable or None")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if simulator_factory is not None and not callable(
            simulator_factory
        ):
            raise TypeError("simulator_factory must be callable or None")

        pair_packages = freeze_gcsim_theoretical_pair_packages(
            two_plus_two_packages
        )
        if (
            domain.package_kind
            is GcsimOptimizerTargetPackageKind.FOUR_PIECE
            and pair_packages
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "4p candidate domain cannot carry 2p+2p packages"
            )
        if (
            domain.package_kind
            is GcsimOptimizerTargetPackageKind.TWO_PLUS_TWO
            and not pair_packages
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "2p+2p candidate domain requires its frozen package mapping"
            )
        derived_kind, derived_keys = (
            derive_gcsim_optimizer_theoretical_package_keys(
                engine_context,
                two_plus_two_packages=(
                    pair_packages
                    if domain.package_kind
                    is GcsimOptimizerTargetPackageKind.TWO_PLUS_TWO
                    else None
                ),
            )
        )
        if (
            derived_kind is not domain.package_kind
            or derived_keys != domain.package_keys
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "candidate package domain differs from the frozen 5-star engine domain"
            )
        if (
            domain.engine_binding_sha256
            != engine_context.binding_sha256
            or domain.catalog_fingerprint
            != engine_context.catalog.source_fingerprint
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "candidate domain differs from the frozen engine/catalog binding"
            )

        self.prepared_config_text = prepared_config_text
        self.engine_context = engine_context
        self.domain = domain
        self.two_plus_two_packages = pair_packages
        self.plan = selected_plan
        self.progress_callback = progress_callback
        self.cache_store = cache_store
        self.enable_cache = bool(enable_cache)
        self.session_factory = session_factory
        self.environment = dict(environment or {})
        self.clock = clock
        self.simulator_factory = (
            simulator_factory or GcsimFarmingFullTeamBatchSimulator
        )
        self.stat_response_target = stat_response_target
        self._cancel_event = Event()
        self._lock = Lock()
        self._active_simulator: _TierSimulator | None = None
        self._started = False

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            simulator = self._active_simulator
        if simulator is not None:
            try:
                simulator.cancel()
            except Exception:
                pass

    def run(self) -> GcsimOptimizerTheoreticalAnytimeRaceResult:
        with self._lock:
            if self._started:
                raise GcsimOptimizerTheoreticalAnytimeRaceError(
                    "theoretical race sessions are one-shot"
                )
            self._started = True
        started = self.clock()
        deadline = started + self.plan.overall_deadline_seconds
        traces: list[
            GcsimOptimizerTheoreticalAnytimeRaceTierTrace
        ] = []
        finalists: tuple[
            GcsimOptimizerTheoreticalAnytimeRaceEvaluation, ...
        ] = ()
        status = GcsimOptimizerTheoreticalAnytimeRaceStatus.COMPLETED

        current = _retain_proposal_diversity(
            self.domain.proposals,
            limit=self.plan.tiers[0].max_candidates,
        )
        package_tier, coordinate_tier, combine_tier, balanced = (
            self.plan.tiers
        )
        terminal = self._terminal_status(deadline)
        if terminal is not None:
            status = terminal
        else:
            package_rows, package_batch, package_context = self._evaluate_tier(
                current,
                tier=package_tier,
                deadline=deadline,
            )
            package_success = tuple(
                item for item in package_rows if item.success
            )
            terminal = self._terminal_status(
                deadline,
                batch_status=package_batch,
                rows=package_rows,
            )
            if terminal is not None:
                status = terminal
                refined_seeds = ()
            elif not package_success:
                status = (
                    GcsimOptimizerTheoreticalAnytimeRaceStatus.NO_SUCCESS
                )
                refined_seeds = ()
            else:
                refined_seeds = _best_package_signature_rows(
                    package_success,
                    limit=self.plan.max_refined_package_signatures,
                )
            traces.append(
                _tier_trace(
                    package_tier,
                    package_rows,
                    refined_seeds,
                    evaluation_context_sha256=package_context,
                    terminal=terminal,
                )
            )

            all_quick_success = list(package_success)
            coordinate_success: tuple[
                GcsimOptimizerTheoreticalAnytimeRaceEvaluation, ...
            ] = ()
            if refined_seeds and terminal is None:
                coordinate_proposals = _build_coordinate_refinement_proposals(
                    self.domain,
                    refined_seeds,
                    per_signature_limit=(
                        self.plan.max_coordinate_candidates_per_signature
                    ),
                )
                coordinate_rows, coordinate_batch, coordinate_context = (
                    self._evaluate_tier(
                        coordinate_proposals,
                        tier=coordinate_tier,
                        deadline=deadline,
                    )
                )
                coordinate_success = tuple(
                    item for item in coordinate_rows if item.success
                )
                all_quick_success.extend(coordinate_success)
                terminal = self._terminal_status(
                    deadline,
                    batch_status=coordinate_batch,
                    rows=coordinate_rows,
                )
                coordinate_selected = _best_package_signature_rows(
                    coordinate_success,
                    limit=self.plan.max_refined_package_signatures,
                )
                traces.append(
                    _tier_trace(
                        coordinate_tier,
                        coordinate_rows,
                        coordinate_selected,
                        evaluation_context_sha256=coordinate_context,
                        terminal=terminal,
                    )
                )

            if refined_seeds and terminal is None:
                combination_proposals = _build_combination_refinement_proposals(
                    refined_seeds,
                    coordinate_success,
                    choices_per_wearer=(
                        self.plan.combination_choices_per_wearer
                    ),
                    per_signature_limit=(
                        self.plan.max_combination_candidates_per_signature
                    ),
                )
                if combination_proposals:
                    combine_rows, combine_batch, combine_context = (
                        self._evaluate_tier(
                            combination_proposals,
                            tier=combine_tier,
                            deadline=deadline,
                        )
                    )
                    combine_success = tuple(
                        item for item in combine_rows if item.success
                    )
                    all_quick_success.extend(combine_success)
                    terminal = self._terminal_status(
                        deadline,
                        batch_status=combine_batch,
                        rows=combine_rows,
                    )
                    combine_selected = _best_package_signature_rows(
                        combine_success,
                        limit=self.plan.max_refined_package_signatures,
                    )
                    traces.append(
                        _tier_trace(
                            combine_tier,
                            combine_rows,
                            combine_selected,
                            evaluation_context_sha256=combine_context,
                            terminal=terminal,
                        )
                    )

            if all_quick_success and terminal is None:
                signature_representatives = _best_package_signature_rows(
                    all_quick_success,
                )
                quick_survivors = _select_survivors(
                    signature_representatives,
                    limit=min(
                        balanced.max_candidates,
                        len(signature_representatives),
                    ),
                    minimum=min(
                        package_tier.min_survivors,
                        len(signature_representatives),
                    ),
                    confidence_sigma=self.plan.confidence_sigma,
                    relative_margin=(
                        self.plan.relative_elimination_margin
                    ),
                )
            else:
                quick_survivors = ()

            if quick_survivors and terminal is None:
                balanced_rows, balanced_batch, balanced_context = (
                    self._evaluate_tier(
                        tuple(
                            item.proposal
                            for item in quick_survivors
                        ),
                        tier=balanced,
                        deadline=deadline,
                    )
                )
                balanced_success = tuple(
                    item
                    for item in balanced_rows
                    if item.success
                )
                terminal = self._terminal_status(
                    deadline,
                    batch_status=balanced_batch,
                    rows=balanced_rows,
                )
                finalists = _select_physical_finalists(
                    balanced_success,
                    limit=self.plan.max_physical_finalists,
                    minimum=balanced.min_survivors,
                    confidence_sigma=self.plan.confidence_sigma,
                    relative_margin=(
                        self.plan.relative_elimination_margin
                    ),
                )
                traces.append(
                    _tier_trace(
                        balanced,
                        balanced_rows,
                        finalists,
                        evaluation_context_sha256=balanced_context,
                        terminal=terminal,
                    )
                )
                if terminal is not None:
                    status = terminal
                elif not balanced_success:
                    status = (
                        GcsimOptimizerTheoreticalAnytimeRaceStatus.NO_SUCCESS
                    )
                elif any(
                    not item.success
                    for trace in traces
                    for item in trace.evaluations
                ):
                    status = (
                        GcsimOptimizerTheoreticalAnytimeRaceStatus
                        .COMPLETED_WITH_ERRORS
                    )

        source_config_sha256 = _sha256_text(
            self.prepared_config_text
        )
        evidence_sha256 = _canonical_sha256(
            {
                "schema_version": (
                    GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_RACE_SCHEMA_VERSION
                ),
                "domain_identity_sha256": self.domain.identity_sha256,
                "engine_binding_sha256": (
                    self.engine_context.binding_sha256
                ),
                "source_config_sha256": source_config_sha256,
                "plan_identity_sha256": self.plan.identity_sha256,
                "status": status.value,
                "tier_trace_evidence": [
                    item.evidence_sha256 for item in traces
                ],
                "physical_finalists": [
                    [list(choice) for choice in item.physical_state.key]
                    for item in finalists
                ],
            }
        )
        return GcsimOptimizerTheoreticalAnytimeRaceResult(
            status=status,
            domain_identity_sha256=self.domain.identity_sha256,
            engine_binding_sha256=self.engine_context.binding_sha256,
            source_config_sha256=source_config_sha256,
            plan_identity_sha256=self.plan.identity_sha256,
            tier_traces=tuple(traces),
            finalist_evaluations=finalists,
            physical_finalists=tuple(
                item.physical_state for item in finalists
            ),
            evidence_sha256=evidence_sha256,
            elapsed_seconds=max(self.clock() - started, 0.0),
        )

    def _evaluate_tier(
        self,
        proposals: tuple[
            GcsimOptimizerTheoreticalAnytimeProposal, ...
        ],
        *,
        tier: GcsimOptimizerTheoreticalAnytimeRaceTier,
        deadline: float,
    ) -> tuple[
        tuple[GcsimOptimizerTheoreticalAnytimeRaceEvaluation, ...],
        GcsimFarmingBatchStatus | None,
        str,
    ]:
        remaining = max(deadline - self.clock(), 1e-6)
        tier_budget = min(remaining, tier.timeout_seconds)
        fidelity = GcsimFarmingScreeningFidelity(
            iterations=tier.iterations,
            worker_count=self.plan.worker_count,
        )
        scheduler_budget = GcsimFarmingSchedulerBudget(
            max_parallel_candidates=self.plan.max_parallel_candidates,
            total_cpu_budget=self.plan.total_cpu_budget,
            overall_deadline_seconds=tier_budget,
        )
        completed_by_index: dict[
            int,
            GcsimOptimizerTheoreticalAnytimeRaceEvaluation,
        ] = {}
        captured_batches: list[GcsimFarmingBatchResult] = []
        evaluation_context_sha256 = ""

        def emit_completion(
            completed: int,
            total: int,
            index: int,
            metrics: FullTeamSimulationMetrics,
        ) -> None:
            if index in completed_by_index:
                return
            evaluation = (
                GcsimOptimizerTheoreticalAnytimeRaceEvaluation(
                    tier_id=tier.tier_id,
                    tier_iterations=tier.iterations,
                    proposal_ordinal=index,
                    proposal=proposals[index],
                    evaluation_context_sha256=(
                        evaluation_context_sha256
                    ),
                    metrics=metrics,
                )
            )
            completed_by_index[index] = evaluation
            successful = tuple(
                item
                for item in completed_by_index.values()
                if item.success
            )
            leader = (
                min(successful, key=_evaluation_rank)
                if successful
                else None
            )
            self._emit_progress(
                tier.tier_id,
                completed,
                total,
                sum(
                    int(item.metrics.cache_hit)
                    for item in completed_by_index.values()
                ),
                leader,
            )

        def on_scheduler_completion(
            completed: int,
            total: int,
            index: int,
            result: GcsimFarmingEvaluationResult,
        ) -> None:
            emit_completion(
                completed,
                total,
                index,
                _metrics_from_evaluator_result(result),
            )

        def scheduler_factory(
            requests,
            budget,
        ) -> _CapturingScheduler:
            scheduler = GcsimFarmingEvaluationScheduler(
                requests,
                budget,
                cache_store=self.cache_store,
                enable_cache=self.enable_cache,
                session_factory=self.session_factory,
                completion_callback=on_scheduler_completion,
            )
            return _CapturingScheduler(
                scheduler,
                captured_batches,
            )

        simulator = self.simulator_factory(
            engine_context=self.engine_context,
            prepared_config_text=self.prepared_config_text,
            wearer_ids=tuple(
                item.wearer.gcsim_character_key
                for item in self.domain.wearer_pools
            ),
            layout_catalog=self.domain.layout_catalog,
            profile_bank=self.domain.profile_bank,
            fidelity=fidelity,
            scheduler_budget=scheduler_budget,
            environment=self.environment,
            cache_store=self.cache_store,
            enable_cache=self.enable_cache,
            session_factory=self.session_factory,
            scheduler_factory=scheduler_factory,
            two_plus_two_packages=self.two_plus_two_packages,
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
        if (
            not hasattr(simulator, "evaluation_context_sha256")
            or not hasattr(simulator, "cancel")
            or not callable(simulator)
        ):
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "simulator factory returned an invalid simulator"
            )
        evaluation_context_sha256 = (
            simulator.evaluation_context_sha256
        )
        _require_sha256(
            evaluation_context_sha256,
            "evaluation_context_sha256",
        )
        requests = tuple(
            FullTeamSimulationRequest(
                context_sha256=evaluation_context_sha256,
                state=proposal.state,
                ordinal=index,
                phase=tier.tier_id,
                round_index=0,
                parent_probe_keys=(),
                changed_wearer_ids=(),
                timeout_seconds=tier_budget,
            )
            for index, proposal in enumerate(proposals)
        )
        self._emit_progress(tier.tier_id, 0, len(requests), 0, None)
        with self._lock:
            if self._active_simulator is not None:
                raise GcsimOptimizerTheoreticalAnytimeRaceError(
                    "theoretical race does not allow concurrent tiers"
                )
            self._active_simulator = simulator
        try:
            if self._cancel_event.is_set():
                simulator.cancel()
            outcomes = simulator(requests)
            if not isinstance(outcomes, Mapping):
                raise GcsimOptimizerTheoreticalAnytimeRaceError(
                    "simulator returned a non-mapping outcome"
                )
            for index, proposal in enumerate(proposals):
                if index in completed_by_index:
                    continue
                metrics = outcomes.get(proposal.state.probe_key)
                if not isinstance(metrics, FullTeamSimulationMetrics):
                    raise GcsimOptimizerTheoreticalAnytimeRaceError(
                        "simulator omitted a typed proposal outcome"
                    )
                emit_completion(
                    len(completed_by_index) + 1,
                    len(proposals),
                    index,
                    metrics,
                )
        finally:
            with self._lock:
                if self._active_simulator is simulator:
                    self._active_simulator = None

        evaluations = tuple(
            completed_by_index[index]
            for index in range(len(proposals))
        )
        batch_status = (
            captured_batches[-1].status
            if captured_batches
            else None
        )
        return (
            evaluations,
            batch_status,
            evaluation_context_sha256,
        )

    def _emit_progress(
        self,
        tier_id: str,
        completed: int,
        total: int,
        cache_hits: int,
        leader: (
            GcsimOptimizerTheoreticalAnytimeRaceEvaluation | None
        ),
    ) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(
                tier_id,
                completed,
                total,
                cache_hits,
                leader,
            )
        except Exception:
            # Progress observers are not part of simulation correctness.
            pass

    def _terminal_status(
        self,
        deadline: float,
        *,
        batch_status: GcsimFarmingBatchStatus | None = None,
        rows: Sequence[
            GcsimOptimizerTheoreticalAnytimeRaceEvaluation
        ] = (),
    ) -> GcsimOptimizerTheoreticalAnytimeRaceStatus | None:
        if (
            self._cancel_event.is_set()
            or batch_status is GcsimFarmingBatchStatus.CANCELLED
            or any(
                item.metrics.status == TEAM_SIM_CANCELLED
                for item in rows
            )
        ):
            return (
                GcsimOptimizerTheoreticalAnytimeRaceStatus.CANCELLED
            )
        if (
            self.clock() >= deadline
            or batch_status
            is GcsimFarmingBatchStatus.DEADLINE_REACHED
        ):
            return GcsimOptimizerTheoreticalAnytimeRaceStatus.DEADLINE
        return None


def run_gcsim_optimizer_theoretical_anytime_race(
    prepared_config_text: str,
    *,
    engine_context: GcsimOptimizerEngineContext,
    domain: GcsimOptimizerTheoreticalAnytimeCandidateDomain,
    two_plus_two_packages: Mapping[
        str,
        GcsimTwoPlusTwoTargetPackage,
    ] | None = None,
    plan: GcsimOptimizerTheoreticalAnytimeRacePlan | None = None,
    progress_callback: (
        TheoreticalAnytimeRaceProgressCallback | None
    ) = None,
    cache_store: GcsimOptimizerCacheStore | None = None,
    enable_cache: bool = True,
    session_factory: FarmingSessionFactory | None = None,
    environment: Mapping[str, str] | None = None,
) -> GcsimOptimizerTheoreticalAnytimeRaceResult:
    return GcsimOptimizerTheoreticalAnytimeRaceSession(
        prepared_config_text,
        engine_context=engine_context,
        domain=domain,
        two_plus_two_packages=two_plus_two_packages,
        plan=plan,
        progress_callback=progress_callback,
        cache_store=cache_store,
        enable_cache=enable_cache,
        session_factory=session_factory,
        environment=environment,
    ).run()


def _tier_trace(
    tier: GcsimOptimizerTheoreticalAnytimeRaceTier,
    rows: Sequence[GcsimOptimizerTheoreticalAnytimeRaceEvaluation],
    selected: Sequence[
        GcsimOptimizerTheoreticalAnytimeRaceEvaluation
    ],
    *,
    evaluation_context_sha256: str,
    terminal: GcsimOptimizerTheoreticalAnytimeRaceStatus | None,
) -> GcsimOptimizerTheoreticalAnytimeRaceTierTrace:
    successful = sum(item.success for item in rows)
    if terminal is GcsimOptimizerTheoreticalAnytimeRaceStatus.CANCELLED:
        status = GcsimOptimizerTheoreticalAnytimeTierStatus.CANCELLED
    elif terminal is GcsimOptimizerTheoreticalAnytimeRaceStatus.DEADLINE:
        status = GcsimOptimizerTheoreticalAnytimeTierStatus.DEADLINE
    elif successful == 0:
        status = GcsimOptimizerTheoreticalAnytimeTierStatus.NO_SUCCESS
    elif successful != len(rows):
        status = (
            GcsimOptimizerTheoreticalAnytimeTierStatus
            .COMPLETED_WITH_ERRORS
        )
    else:
        status = GcsimOptimizerTheoreticalAnytimeTierStatus.COMPLETED
    return GcsimOptimizerTheoreticalAnytimeRaceTierTrace(
        tier=tier,
        status=status,
        evaluation_context_sha256=evaluation_context_sha256,
        evaluations=tuple(rows),
        selected_proposal_sha256=tuple(
            item.proposal.proposal_sha256 for item in selected
        ),
    )


def _best_package_signature_rows(
    rows: Sequence[GcsimOptimizerTheoreticalAnytimeRaceEvaluation],
    *,
    limit: int | None = None,
) -> tuple[GcsimOptimizerTheoreticalAnytimeRaceEvaluation, ...]:
    """Keep the strongest measured layout for each ordered set signature."""

    best_by_signature: dict[
        tuple[str, ...],
        GcsimOptimizerTheoreticalAnytimeRaceEvaluation,
    ] = {}
    for row in sorted(rows, key=_evaluation_rank):
        best_by_signature.setdefault(
            gcsim_optimizer_theoretical_team_package_signature(
                row.proposal.state
            ),
            row,
        )
    ranked = tuple(
        sorted(best_by_signature.values(), key=_evaluation_rank)
    )
    return ranked if limit is None else ranked[:limit]


def _build_coordinate_refinement_proposals(
    domain: GcsimOptimizerTheoreticalAnytimeCandidateDomain,
    seeds: Sequence[GcsimOptimizerTheoreticalAnytimeRaceEvaluation],
    *,
    per_signature_limit: int,
) -> tuple[GcsimOptimizerTheoreticalAnytimeProposal, ...]:
    """Vary one wearer at a time while freezing all four package keys.

    Every retained main-stat layout is compared under that wearer's balanced
    response profile.  Profile-only alternatives are also sampled on the seed
    layout.  Consequently CR versus CD, scaling versus elemental goblets, and
    repeated-scaling layouts are measured against the *same* allies and sets
    instead of being accidentally compared across unrelated team signatures.
    """

    proposals: dict[
        tuple[tuple[str, str, str, str, str], ...],
        GcsimOptimizerTheoreticalAnytimeProposal,
    ] = {}
    for seed in seeds:
        seed_choices = seed.proposal.state.choices
        per_signature: dict[
            tuple[tuple[str, str, str, str, str], ...],
            GcsimOptimizerTheoreticalAnytimeProposal,
        ] = {}
        for wearer_index, pool in enumerate(domain.wearer_pools):
            current = seed_choices[wearer_index]
            balanced_profile_id = next(
                profile_id
                for profile_id in pool.profile_ids
                if profile_id.endswith("_balanced")
            )
            candidate_choices: list[SetProfileCandidate] = []
            for layout_id, _layout in pool.layouts:
                candidate_choices.append(
                    _refinement_choice(
                        current,
                        main_stat_layout_id=layout_id,
                        profile_id=balanced_profile_id,
                    )
                )
            for profile_id in pool.profile_ids:
                candidate_choices.append(
                    _refinement_choice(
                        current,
                        main_stat_layout_id=(
                            current.state.main_stat_layout_id
                        ),
                        profile_id=profile_id,
                    )
                )
            for choice in candidate_choices:
                changed = list(seed_choices)
                changed[wearer_index] = choice
                changed_tuple = tuple(changed)
                if changed_tuple == seed_choices:
                    continue
                proposal = _refinement_proposal(
                    changed_tuple,
                    score=seed.proposal.surrogate_score,
                    tags=(
                        "same_signature_main_coordinate",
                        f"coordinate_slot{wearer_index + 1}",
                    ),
                )
                per_signature.setdefault(
                    proposal.state.probe_key,
                    proposal,
                )
        for proposal in tuple(per_signature.values())[:per_signature_limit]:
            proposals.setdefault(proposal.state.probe_key, proposal)
    return tuple(proposals.values())


def _build_combination_refinement_proposals(
    seeds: Sequence[GcsimOptimizerTheoreticalAnytimeRaceEvaluation],
    coordinate_rows: Sequence[
        GcsimOptimizerTheoreticalAnytimeRaceEvaluation
    ],
    *,
    choices_per_wearer: int,
    per_signature_limit: int,
) -> tuple[GcsimOptimizerTheoreticalAnytimeProposal, ...]:
    """Combine the best like-for-like single-wearer changes into a small beam."""

    coordinate_by_signature: dict[
        tuple[str, ...],
        list[GcsimOptimizerTheoreticalAnytimeRaceEvaluation],
    ] = {}
    for row in coordinate_rows:
        coordinate_by_signature.setdefault(
            gcsim_optimizer_theoretical_team_package_signature(
                row.proposal.state
            ),
            [],
        ).append(row)

    proposals: dict[
        tuple[tuple[str, str, str, str, str], ...],
        GcsimOptimizerTheoreticalAnytimeProposal,
    ] = {}
    for seed in seeds:
        signature = gcsim_optimizer_theoretical_team_package_signature(
            seed.proposal.state
        )
        seed_choices = seed.proposal.state.choices
        seed_dps = float(seed.dps_mean or 0.0)
        scored_choices: list[
            dict[
                tuple[str, str, str, str, str],
                tuple[float, SetProfileCandidate],
            ]
        ] = [
            {choice.key: (seed_dps, choice)} for choice in seed_choices
        ]
        existing_probe_keys = {seed.proposal.state.probe_key}
        for row in coordinate_by_signature.get(signature, ()):
            existing_probe_keys.add(row.proposal.state.probe_key)
            differing = tuple(
                index
                for index, (left, right) in enumerate(
                    zip(
                        seed_choices,
                        row.proposal.state.choices,
                        strict=True,
                    )
                )
                if left.key != right.key
            )
            if len(differing) != 1:
                continue
            wearer_index = differing[0]
            choice = row.proposal.state.choices[wearer_index]
            dps = float(row.dps_mean or 0.0)
            previous = scored_choices[wearer_index].get(choice.key)
            if previous is None or dps > previous[0]:
                scored_choices[wearer_index][choice.key] = (dps, choice)

        wearer_beams = tuple(
            tuple(
                choice
                for _dps, choice in sorted(
                    values.values(),
                    key=lambda item: (-item[0], item[1].key),
                )[:choices_per_wearer]
            )
            for values in scored_choices
        )
        score_by_key = {
            key: score
            for values in scored_choices
            for key, (score, _choice) in values.items()
        }
        signature_rows: list[
            tuple[float, GcsimOptimizerTheoreticalAnytimeProposal]
        ] = []
        for choices in product(*wearer_beams):
            changed_count = sum(
                left.key != right.key
                for left, right in zip(seed_choices, choices, strict=True)
            )
            if changed_count < 2:
                continue
            proposal = _refinement_proposal(
                choices,
                score=sum(score_by_key[item.key] for item in choices),
                tags=(
                    "same_signature_main_combine",
                    f"combined_wearers{changed_count}",
                ),
            )
            if proposal.state.probe_key in existing_probe_keys:
                continue
            signature_rows.append((proposal.surrogate_score, proposal))
        signature_rows.sort(
            key=lambda item: (-item[0], item[1].proposal_sha256)
        )
        for _score, proposal in signature_rows[:per_signature_limit]:
            proposals.setdefault(proposal.state.probe_key, proposal)
    return tuple(proposals.values())


def _refinement_choice(
    source: SetProfileCandidate,
    *,
    main_stat_layout_id: str,
    profile_id: str,
) -> SetProfileCandidate:
    return SetProfileCandidate(
        state=FourPieceSetState(
            wearer_id=source.state.wearer_id,
            set_key=source.state.set_key,
            main_stat_layout_id=main_stat_layout_id,
            offpiece_slot=source.state.offpiece_slot,
        ),
        profile_id=profile_id,
    )


def _refinement_proposal(
    choices: Sequence[SetProfileCandidate],
    *,
    score: float,
    tags: tuple[str, ...],
) -> GcsimOptimizerTheoreticalAnytimeProposal:
    return GcsimOptimizerTheoreticalAnytimeProposal(
        state=FullTeamProbeState(tuple(choices)),
        score=max(float(score), 0.0),
        diversity_tags=tags,
        package_anchor_count=0,
    )


def _select_survivors(
    rows: Sequence[GcsimOptimizerTheoreticalAnytimeRaceEvaluation],
    *,
    limit: int,
    minimum: int,
    confidence_sigma: float,
    relative_margin: float,
) -> tuple[GcsimOptimizerTheoreticalAnytimeRaceEvaluation, ...]:
    ranked = tuple(sorted(rows, key=_evaluation_rank))
    if not ranked:
        return ()
    leader = ranked[0]
    assert leader.dps_mean is not None
    leader_lower = _lower_bound(leader, confidence_sigma)
    credible = []
    for row in ranked:
        assert row.dps_mean is not None
        if row.dps_se is None or leader.dps_se is None:
            credible.append(row)
            continue
        optimistic = _upper_bound(row, confidence_sigma)
        margin = abs(leader.dps_mean) * relative_margin
        if optimistic + margin >= leader_lower:
            credible.append(row)
    base = _unique_evaluations(
        (
            *credible,
            *ranked[: min(minimum, len(ranked))],
        )
    )
    return _diverse_evaluation_cap(
        ranked,
        preferred=base,
        limit=min(limit, len(ranked)),
    )


def _select_physical_finalists(
    rows: Sequence[GcsimOptimizerTheoreticalAnytimeRaceEvaluation],
    *,
    limit: int,
    minimum: int,
    confidence_sigma: float,
    relative_margin: float,
) -> tuple[GcsimOptimizerTheoreticalAnytimeRaceEvaluation, ...]:
    best_by_package_signature = {}
    for row in sorted(rows, key=_evaluation_rank):
        best_by_package_signature.setdefault(
            gcsim_optimizer_theoretical_team_package_signature(
                row.physical_state
            ),
            row,
        )
    representatives = tuple(
        sorted(
            best_by_package_signature.values(),
            key=_evaluation_rank,
        )
    )
    return _select_survivors(
        representatives,
        limit=min(limit, len(representatives)),
        minimum=min(minimum, len(representatives)),
        confidence_sigma=confidence_sigma,
        relative_margin=relative_margin,
    )


def _retain_proposal_diversity(
    rows: Sequence[GcsimOptimizerTheoreticalAnytimeProposal],
    *,
    limit: int,
) -> tuple[GcsimOptimizerTheoreticalAnytimeProposal, ...]:
    identity_by_object = {
        id(item): item.proposal_sha256 for item in rows
    }
    labels_by_object = {
        id(item): frozenset(item.diversity_labels) for item in rows
    }
    ordered = tuple(
        sorted(
            rows,
            key=lambda item: (
                -item.surrogate_score,
                identity_by_object[id(item)],
            ),
        )
    )
    if len(ordered) <= limit:
        return ordered

    baseline = next(
        (
            row for row in ordered
            if "baseline" in row.diversity_labels
        ),
        ordered[0],
    )
    selected: list[GcsimOptimizerTheoreticalAnytimeProposal] = [baseline]
    selected_objects = {id(baseline)}
    covered = set(labels_by_object[id(baseline)])

    # Package-coordinate rows are quality probes, not catalog-audit rows.
    # Preserve the bounded base-plus-one-swap and strongest combination
    # neighborhood before spending the remaining screen-64 budget on broad
    # package/layout label coverage.
    for required_tag in (
        "package_coordinate_neighbor",
        "package_coordinate_combination",
    ):
        for row in ordered:
            if len(selected) >= limit:
                break
            if (
                id(row) not in selected_objects
                and required_tag in labels_by_object[id(row)]
            ):
                selected.append(row)
                selected_objects.add(id(row))
                covered.update(labels_by_object[id(row)])

    def cover(required_labels: set[str], *, fail_closed: bool) -> bool:
        while len(selected) < limit and not required_labels.issubset(covered):
            uncovered = required_labels - covered
            candidates = tuple(
                row for row in ordered
                if id(row) not in selected_objects
            )
            if not candidates:
                break
            best = max(
                candidates,
                key=lambda row: (
                    len(labels_by_object[id(row)] & uncovered),
                    row.package_anchor_count,
                    row.surrogate_score,
                    _reverse_digest(identity_by_object[id(row)]),
                ),
            )
            if not (labels_by_object[id(best)] & uncovered):
                break
            selected.append(best)
            selected_objects.add(id(best))
            covered.update(labels_by_object[id(best)])
        complete = required_labels.issubset(covered)
        if fail_closed and not complete:
            raise GcsimOptimizerTheoreticalAnytimeRaceError(
                "quick-tier cap cannot preserve every balanced "
                "wearer/package anchor"
            )
        return complete

    # A package label used to count as covered by any focus profile.  That let
    # a high-surrogate EM/EM/EM row replace the balanced Golden Troupe anchor.
    # Anchor identities are now explicit and mandatory before any optional
    # layout/profile diversity is admitted.
    anchor_labels = {
        label
        for row in ordered
        for label in row.diversity_labels
        if label.startswith("package_anchor_slot")
    }
    # The full candidate domain still carries every anchor.  Screen-64 now
    # reports the bounded subset it actually measured instead of sacrificing
    # all local package comparisons to an impossible exhaustive audit.
    cover(anchor_labels, fail_closed=False)

    # Spend remaining capacity fairly by witness rank.  Rank 1 for every
    # package is attempted before rank 2, so one high-scoring set cannot take
    # dozens of layouts while another set receives none.
    witness_labels_by_rank: dict[int, set[str]] = {}
    for row in ordered:
        for label in row.diversity_labels:
            rank = _package_witness_rank(label)
            if rank is not None:
                witness_labels_by_rank.setdefault(rank, set()).add(label)
    for rank in sorted(witness_labels_by_rank):
        if not cover(
            witness_labels_by_rank[rank],
            fail_closed=False,
        ):
            break

    all_labels = {
        label for row in ordered for label in row.diversity_labels
    }
    while len(selected) < limit and covered != all_labels:
        candidates = tuple(
            row for row in ordered
            if id(row) not in selected_objects
        )
        best = max(
            candidates,
            key=lambda row: (
                len(labels_by_object[id(row)] - covered),
                row.surrogate_score,
                _reverse_digest(identity_by_object[id(row)]),
            ),
        )
        if not (labels_by_object[id(best)] - covered):
            break
        selected.append(best)
        selected_objects.add(id(best))
        covered.update(labels_by_object[id(best)])
    for row in ordered:
        if len(selected) >= limit:
            break
        if id(row) not in selected_objects:
            selected.append(row)
            selected_objects.add(id(row))
    return tuple(selected)


def _package_witness_rank(label: str) -> int | None:
    prefix = "package_witness_r"
    if not label.startswith(prefix):
        return None
    value = label[len(prefix):]
    token, separator, _rest = value.partition("_slot")
    if not separator or not token.isdigit():
        return None
    rank = int(token)
    return rank if rank > 0 else None


def _diverse_evaluation_cap(
    ranked: Sequence[GcsimOptimizerTheoreticalAnytimeRaceEvaluation],
    *,
    preferred: Sequence[
        GcsimOptimizerTheoreticalAnytimeRaceEvaluation
    ],
    limit: int,
) -> tuple[GcsimOptimizerTheoreticalAnytimeRaceEvaluation, ...]:
    if not ranked or limit <= 0:
        return ()
    preferred_ids = {
        item.proposal.proposal_sha256 for item in preferred
    }
    selected = [ranked[0]]
    covered = set(ranked[0].proposal.diversity_labels)
    all_labels = {
        label
        for row in ranked
        for label in row.proposal.diversity_labels
    }
    while len(selected) < limit and covered != all_labels:
        candidates = tuple(
            row for row in ranked if row not in selected
        )
        best = max(
            candidates,
            key=lambda row: (
                len(
                    set(row.proposal.diversity_labels) - covered
                ),
                int(
                    row.proposal.proposal_sha256 in preferred_ids
                ),
                -_rank_index(ranked, row),
            ),
        )
        if not (
            set(best.proposal.diversity_labels) - covered
        ):
            break
        selected.append(best)
        covered.update(best.proposal.diversity_labels)
    for source in (preferred, ranked):
        for row in source:
            if len(selected) >= limit:
                break
            if row not in selected:
                selected.append(row)
    return tuple(sorted(selected, key=_evaluation_rank))


def _unique_evaluations(
    rows: Sequence[GcsimOptimizerTheoreticalAnytimeRaceEvaluation],
) -> tuple[GcsimOptimizerTheoreticalAnytimeRaceEvaluation, ...]:
    unique = {}
    for row in rows:
        unique.setdefault(row.proposal.proposal_sha256, row)
    return tuple(unique.values())


def _evaluation_rank(
    row: GcsimOptimizerTheoreticalAnytimeRaceEvaluation,
) -> tuple[float, str]:
    return (
        (
            -float(row.dps_mean)
            if row.dps_mean is not None
            else float("inf")
        ),
        row.proposal.proposal_sha256,
    )


def _rank_index(
    ranked: Sequence[GcsimOptimizerTheoreticalAnytimeRaceEvaluation],
    row: GcsimOptimizerTheoreticalAnytimeRaceEvaluation,
) -> int:
    return next(
        index
        for index, candidate in enumerate(ranked)
        if candidate is row
    )


def _lower_bound(
    row: GcsimOptimizerTheoreticalAnytimeRaceEvaluation,
    sigma: float,
) -> float:
    assert row.dps_mean is not None
    return (
        row.dps_mean
        if row.dps_se is None
        else row.dps_mean - sigma * row.dps_se
    )


def _upper_bound(
    row: GcsimOptimizerTheoreticalAnytimeRaceEvaluation,
    sigma: float,
) -> float:
    assert row.dps_mean is not None
    return (
        row.dps_mean
        if row.dps_se is None
        else row.dps_mean + sigma * row.dps_se
    )


def _metrics_from_evaluator_result(
    result: GcsimFarmingEvaluationResult,
) -> FullTeamSimulationMetrics:
    if result.success:
        return FullTeamSimulationMetrics(
            status=TEAM_SIM_PASSED,
            dps_mean=result.summary.dps_mean,
            dps_se=result.summary.dps_se,
            iterations=result.summary.iterations,
            cache_hit=result.cache_hit,
        )
    if result.status in {
        GcsimFarmingEvaluationStatus.CANCELLED,
        GcsimFarmingEvaluationStatus.SKIPPED_CANCELLED,
    }:
        status = TEAM_SIM_CANCELLED
    elif result.status in {
        GcsimFarmingEvaluationStatus.TIMEOUT,
        GcsimFarmingEvaluationStatus.SKIPPED_DEADLINE,
    }:
        status = TEAM_SIM_TIMEOUT
    else:
        status = TEAM_SIM_FAILED
    return FullTeamSimulationMetrics(
        status=status,
        error=result.error or result.status.value,
    )


def _metrics_payload(
    metrics: FullTeamSimulationMetrics,
) -> dict[str, object]:
    return {
        "status": metrics.status,
        "dps_mean": metrics.dps_mean,
        "dps_se": metrics.dps_se,
        "iterations": metrics.iterations,
        "novelty_tags": list(metrics.novelty_tags),
        "cache_hit": metrics.cache_hit,
        "error": metrics.error,
    }


def _reverse_digest(value: str) -> tuple[int, ...]:
    return tuple(-ord(char) for char in value)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _require_schema(value: int) -> None:
    if (
        value
        != GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_RACE_SCHEMA_VERSION
    ):
        raise GcsimOptimizerTheoreticalAnytimeRaceError(
            "unsupported theoretical anytime race schema"
        )


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise GcsimOptimizerTheoreticalAnytimeRaceError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


__all__ = [
    "GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_RACE_PLAN_ID",
    "GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_RACE_PLAN_VERSION",
    "GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_RACE_SCHEMA_VERSION",
    "GcsimOptimizerTheoreticalAnytimeRaceError",
    "GcsimOptimizerTheoreticalAnytimeRaceEvaluation",
    "GcsimOptimizerTheoreticalAnytimeRacePlan",
    "GcsimOptimizerTheoreticalAnytimeRaceResult",
    "GcsimOptimizerTheoreticalAnytimeRaceSession",
    "GcsimOptimizerTheoreticalAnytimeRaceStatus",
    "GcsimOptimizerTheoreticalAnytimeRaceTier",
    "GcsimOptimizerTheoreticalAnytimeRaceTierTrace",
    "GcsimOptimizerTheoreticalAnytimeTierStatus",
    "TheoreticalAnytimeRaceProgressCallback",
    "run_gcsim_optimizer_theoretical_anytime_race",
]
