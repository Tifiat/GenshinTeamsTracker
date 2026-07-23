"""Proof-carrying integration for theoretical GCSIM farming screens.

The lower-level farming evaluator deliberately accepts already-rendered text.
This module is the production boundary that makes that text trustworthy: every
set, layout, off-piece, and stat profile is resolved from an explicit search
state, rendered through the pinned candidate/profile renderers, and bound to a
trusted engine context before an evaluator request can be built.

Nothing here guesses a layout, set, or profile from a character name.  The
caller's canonical wearer order, layout catalog, profile bank, reference
weights, and equal-investment contract are all frozen into the evaluation
context digest.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from threading import Event, Lock
from time import monotonic
from types import MappingProxyType
from typing import Protocol

from .artifact_runner import GcsimResultSummary
from .config_structure import (
    GCSIM_FARMING_STATIC_TARGET_HP,
    validate_gcsim_farming_static_config,
)
from .farming_evaluator import (
    FarmingSessionFactory,
    GCSIM_FARMING_EVALUATION_CONTRACT,
    GcsimFarmingBatchResult,
    GcsimFarmingBatchStatus,
    GcsimFarmingEvaluationRequest,
    GcsimFarmingEvaluationResult,
    GcsimFarmingEvaluationScheduler,
    GcsimFarmingEvaluationStatus,
    GcsimFarmingSchedulerBudget,
    freeze_gcsim_farming_environment,
    normalize_gcsim_farming_frozen_environment,
    prepare_bound_gcsim_farming_joint_evaluation,
)
from .farming_profile_config import (
    GCSIM_BALANCED_REFERENCE_WEIGHTS,
    GCSIM_SCREENING_STAT_AXES,
    GCSIM_SUBSTAT_ROLL_VALUES,
    GcsimScreeningProfileError,
    apply_gcsim_screening_runtime_options,
    build_gcsim_screening_investment_signature,
    render_gcsim_screening_profile_config,
)
from .farming_search import SetProfileCandidate, StatProfileBank, StatWeight
from .farming_team_search import (
    TEAM_SIM_CANCELLED,
    TEAM_SIM_FAILED,
    TEAM_SIM_PASSED,
    TEAM_SIM_TIMEOUT,
    FullTeamComposerError,
    FullTeamProbeState,
    FullTeamSimulationMetrics,
    FullTeamSimulationRequest,
    ProbeKey,
)
from .optimizer_backend import PINNED_GCSIM_OPTIMIZER_CONTRACT_VERSION
from .optimizer_cache import GcsimOptimizerCacheStore
from .optimizer_candidate import prepare_gcsim_four_piece_optimizer_candidate
from .optimizer_config import (
    GcsimFiveStarMainStatLayout,
    render_five_star_main_stat_line,
)
from .optimizer_engine_context import GcsimOptimizerEngineContext


GCSIM_FARMING_PIPELINE_CONTEXT_SCHEMA = 1
_WEARER_RE = re.compile(r"^[a-z]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MATERIALIZATION_PROOF = object()


LayoutCatalog = Mapping[str, Mapping[str, GcsimFiveStarMainStatLayout]]


class GcsimFarmingPipelineError(RuntimeError):
    """Raised when a search state cannot be materialized without guessing."""


@dataclass(frozen=True, slots=True)
class GcsimFarmingScreeningFidelity:
    """Ordinary-simulation fidelity frozen into every screening config."""

    iterations: int
    worker_count: int
    contract: str = GCSIM_FARMING_EVALUATION_CONTRACT

    def __post_init__(self) -> None:
        for field_name in ("iterations", "worker_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.contract != GCSIM_FARMING_EVALUATION_CONTRACT:
            raise ValueError(
                "fidelity contract must match the ordinary farming evaluator"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "iterations": self.iterations,
            "worker_count": self.worker_count,
        }


@dataclass(frozen=True, slots=True, init=False)
class GcsimFarmingMaterializedProbe:
    """Immutable proof that one joint state produced one exact config.

    Instances can only be minted by this module's render pipeline.  This keeps
    independently supplied ``candidate_keys`` and arbitrary config text out of
    the normal evaluator path.
    """

    state: FullTeamProbeState
    candidate_keys: ProbeKey
    config_text: str
    wearer_ids: tuple[str, ...]
    set_assignments: tuple[tuple[str, str], ...]
    layout_assignments: tuple[
        tuple[str, str, GcsimFiveStarMainStatLayout], ...
    ]
    offpiece_assignments: tuple[tuple[str, str], ...]
    profile_assignments: tuple[tuple[str, str], ...]
    environment_items: tuple[tuple[str, str], ...] = field(repr=False)
    investment_signature: str
    evaluation_context_sha256: str
    engine_id: str
    engine_version: str
    artifact_sha256: str
    engine_binding_sha256: str
    catalog_fingerprint: str
    fidelity: GcsimFarmingScreeningFidelity

    def __init__(
        self,
        *,
        state: FullTeamProbeState,
        candidate_keys: ProbeKey,
        config_text: str,
        wearer_ids: tuple[str, ...],
        set_assignments: tuple[tuple[str, str], ...],
        layout_assignments: tuple[
            tuple[str, str, GcsimFiveStarMainStatLayout], ...
        ],
        offpiece_assignments: tuple[tuple[str, str], ...],
        profile_assignments: tuple[tuple[str, str], ...],
        environment_items: tuple[tuple[str, str], ...],
        investment_signature: str,
        evaluation_context_sha256: str,
        engine_id: str,
        engine_version: str,
        artifact_sha256: str,
        engine_binding_sha256: str,
        catalog_fingerprint: str,
        fidelity: GcsimFarmingScreeningFidelity,
        _proof: object | None = None,
    ) -> None:
        if _proof is not _MATERIALIZATION_PROOF:
            raise GcsimFarmingPipelineError(
                "Materialized probes must be produced by the farming render pipeline."
            )
        values = {
            "state": state,
            "candidate_keys": tuple(tuple(key) for key in candidate_keys),
            "config_text": str(config_text),
            "wearer_ids": tuple(wearer_ids),
            "set_assignments": tuple(set_assignments),
            "layout_assignments": tuple(layout_assignments),
            "offpiece_assignments": tuple(offpiece_assignments),
            "profile_assignments": tuple(profile_assignments),
            "environment_items": tuple(environment_items),
            "investment_signature": investment_signature,
            "evaluation_context_sha256": evaluation_context_sha256,
            "engine_id": engine_id,
            "engine_version": engine_version,
            "artifact_sha256": artifact_sha256,
            "engine_binding_sha256": engine_binding_sha256,
            "catalog_fingerprint": catalog_fingerprint,
            "fidelity": fidelity,
        }
        for field_name, value in values.items():
            object.__setattr__(self, field_name, value)
        self._validate_proof_shape()

    def _validate_proof_shape(self) -> None:
        if self.candidate_keys != self.state.probe_key:
            raise GcsimFarmingPipelineError(
                "materialized candidate keys do not match the proven team state"
            )
        if self.state.wearer_ids != self.wearer_ids:
            raise GcsimFarmingPipelineError(
                "materialized wearer order does not match the proven team state"
            )
        if tuple(item[0] for item in self.set_assignments) != self.wearer_ids:
            raise GcsimFarmingPipelineError("set assignment order is inconsistent")
        if tuple(item[0] for item in self.layout_assignments) != self.wearer_ids:
            raise GcsimFarmingPipelineError("layout assignment order is inconsistent")
        if tuple(item[0] for item in self.profile_assignments) != self.wearer_ids:
            raise GcsimFarmingPipelineError("profile assignment order is inconsistent")
        if tuple(sorted(self.environment_items)) != self.environment_items:
            raise GcsimFarmingPipelineError("materialized environment is not canonical")
        if len({key for key, _value in self.environment_items}) != len(
            self.environment_items
        ):
            raise GcsimFarmingPipelineError("materialized environment keys are not unique")
        if dict(self.environment_items).get("GOMAXPROCS") != str(
            self.fidelity.worker_count
        ):
            raise GcsimFarmingPipelineError(
                "materialized environment is not bound to fidelity workers"
            )
        if not self.config_text.strip() or "\x00" in self.config_text:
            raise GcsimFarmingPipelineError("materialized config is empty or contains NUL")
        _require_identifier(
            self.investment_signature,
            field_name="investment signature",
        )
        for field_name in (
            "evaluation_context_sha256",
            "artifact_sha256",
            "engine_binding_sha256",
            "catalog_fingerprint",
        ):
            if not _is_sha256(getattr(self, field_name)):
                raise GcsimFarmingPipelineError(
                    f"{field_name} must be a lowercase SHA-256 digest"
                )

    def build_evaluator_request(
        self,
        *,
        engine_context: GcsimOptimizerEngineContext,
        timeout_seconds: float,
        environment: Mapping[str, str] | None = None,
    ) -> GcsimFarmingEvaluationRequest:
        """Build the low-level request only from this proven state/config pair."""

        _require_matching_engine_context(self, engine_context)
        resolved_environment = dict(self.environment_items)
        if environment is not None:
            supplied_environment = _normalized_effective_environment(
                environment,
                worker_count=self.fidelity.worker_count,
                environment_is_frozen=True,
            )
            if tuple(supplied_environment.items()) != self.environment_items:
                raise GcsimFarmingPipelineError(
                    "evaluator environment differs from the materialized proof"
                )
            resolved_environment = supplied_environment
        return prepare_bound_gcsim_farming_joint_evaluation(
            engine_context=engine_context,
            candidate_keys=self.candidate_keys,
            config_text=self.config_text,
            comparison_context_sha256=self.evaluation_context_sha256,
            investment_signature=self.investment_signature,
            worker_count=self.fidelity.worker_count,
            timeout_seconds=timeout_seconds,
            environment=resolved_environment,
            environment_is_frozen=True,
        )


def materialize_gcsim_one_wearer_candidate(
    prepared_config_text: str,
    *,
    candidate: SetProfileCandidate,
    frozen_baseline_states: Sequence[SetProfileCandidate],
    wearer_ids: Sequence[str],
    layout_catalog: LayoutCatalog,
    profile_bank: StatProfileBank,
    engine_context: GcsimOptimizerEngineContext,
    fidelity: GcsimFarmingScreeningFidelity,
    reference_weights: Sequence[StatWeight] = GCSIM_BALANCED_REFERENCE_WEIGHTS,
    environment: Mapping[str, str] | None = None,
    environment_is_frozen: bool = False,
) -> GcsimFarmingMaterializedProbe:
    """Render one wearer probe while every other wearer stays explicitly frozen."""

    if not isinstance(candidate, SetProfileCandidate):
        raise GcsimFarmingPipelineError("candidate must be a SetProfileCandidate")
    canonical_wearers = _validated_wearer_ids(wearer_ids)
    target_wearer = candidate.state.wearer_id
    if target_wearer not in canonical_wearers:
        raise GcsimFarmingPipelineError(
            f"candidate wearer is absent from wearer_ids: {target_wearer!r}"
        )
    baselines = tuple(frozen_baseline_states)
    if any(not isinstance(item, SetProfileCandidate) for item in baselines):
        raise GcsimFarmingPipelineError(
            "frozen_baseline_states must contain SetProfileCandidate values"
        )
    expected_baseline_order = tuple(
        wearer for wearer in canonical_wearers if wearer != target_wearer
    )
    actual_baseline_order = tuple(item.state.wearer_id for item in baselines)
    if actual_baseline_order != expected_baseline_order:
        raise GcsimFarmingPipelineError(
            "frozen baseline states must cover every other wearer exactly in "
            f"canonical order; expected={expected_baseline_order!r}, "
            f"actual={actual_baseline_order!r}"
        )
    baseline_by_wearer = {item.state.wearer_id: item for item in baselines}
    state = FullTeamProbeState(
        choices=tuple(
            candidate if wearer == target_wearer else baseline_by_wearer[wearer]
            for wearer in canonical_wearers
        )
    )
    return materialize_gcsim_full_team_probe_state(
        prepared_config_text,
        state=state,
        wearer_ids=canonical_wearers,
        layout_catalog=layout_catalog,
        profile_bank=profile_bank,
        engine_context=engine_context,
        fidelity=fidelity,
        reference_weights=reference_weights,
        environment=environment,
        environment_is_frozen=environment_is_frozen,
    )


def materialize_gcsim_full_team_probe_state(
    prepared_config_text: str,
    *,
    state: FullTeamProbeState,
    wearer_ids: Sequence[str],
    layout_catalog: LayoutCatalog,
    profile_bank: StatProfileBank,
    engine_context: GcsimOptimizerEngineContext,
    fidelity: GcsimFarmingScreeningFidelity,
    reference_weights: Sequence[StatWeight] = GCSIM_BALANCED_REFERENCE_WEIGHTS,
    environment: Mapping[str, str] | None = None,
    environment_is_frozen: bool = False,
) -> GcsimFarmingMaterializedProbe:
    """Render an exact full-team state through set, main, and profile layers."""

    if not isinstance(state, FullTeamProbeState):
        raise GcsimFarmingPipelineError("state must be a FullTeamProbeState")
    canonical_wearers = _validated_wearer_ids(wearer_ids)
    if state.wearer_ids != canonical_wearers:
        raise GcsimFarmingPipelineError(
            "full-team state choices must match wearer_ids exactly in canonical order"
        )
    prepared = _validated_prepared_config(prepared_config_text, canonical_wearers)
    layouts = _normalize_layout_catalog(layout_catalog, canonical_wearers)
    _validate_profile_bank(profile_bank)
    profiles_by_id = {profile.profile_id: profile for profile in profile_bank.profiles}
    reference = _validated_reference_weights(reference_weights)
    investment_signature = build_gcsim_screening_investment_signature(
        reference_weights=reference,
    )
    _require_trusted_engine_context(engine_context)
    if not isinstance(fidelity, GcsimFarmingScreeningFidelity):
        raise GcsimFarmingPipelineError(
            "fidelity must be a GcsimFarmingScreeningFidelity"
        )
    effective_environment = _normalized_effective_environment(
        environment,
        worker_count=fidelity.worker_count,
        environment_is_frozen=environment_is_frozen,
    )

    set_assignments: list[tuple[str, str]] = []
    layout_assignments: list[
        tuple[str, str, GcsimFiveStarMainStatLayout]
    ] = []
    offpiece_assignments: list[tuple[str, str]] = []
    profile_assignments: list[tuple[str, str]] = []
    resolved_layouts: dict[str, GcsimFiveStarMainStatLayout] = {}
    resolved_profiles = {}
    offpieces: dict[str, str] = {}
    for choice in state.choices:
        wearer = choice.state.wearer_id
        layout_id = choice.state.main_stat_layout_id
        wearer_layouts = layouts[wearer]
        if layout_id not in wearer_layouts:
            raise GcsimFarmingPipelineError(
                f"missing explicit layout {layout_id!r} for wearer {wearer!r}"
            )
        if choice.profile_id not in profiles_by_id:
            raise GcsimFarmingPipelineError(
                f"missing explicit profile {choice.profile_id!r} for wearer {wearer!r}"
            )
        layout = wearer_layouts[layout_id]
        profile = profiles_by_id[choice.profile_id]
        set_assignments.append((wearer, choice.state.set_key))
        layout_assignments.append((wearer, layout_id, layout))
        profile_assignments.append((wearer, choice.profile_id))
        resolved_layouts[wearer] = layout
        resolved_profiles[wearer] = profile
        if choice.state.offpiece_slot:
            offpiece_assignments.append((wearer, choice.state.offpiece_slot))
            offpieces[wearer] = choice.state.offpiece_slot

    candidate_render = prepare_gcsim_four_piece_optimizer_candidate(
        prepared,
        set_assignments=dict(set_assignments),
        main_stat_layouts=resolved_layouts,
        set_catalog=engine_context.catalog,
        four_star_offpiece_slots=offpieces,
        require_full_team=True,
    )
    if not candidate_render.ready:
        details = tuple(
            (issue.status, issue.field, issue.message)
            for issue in candidate_render.issues
        )
        raise GcsimFarmingPipelineError(
            "candidate renderer rejected the explicit team state: "
            f"status={candidate_render.status!r}, issues={details!r}"
        )
    try:
        profile_render = render_gcsim_screening_profile_config(
            candidate_render.config_text,
            main_stat_layouts=resolved_layouts,
            profiles=resolved_profiles,
            four_star_offpiece_slots=offpieces,
            reference_weights=reference,
        )
        exact_config = apply_gcsim_screening_runtime_options(
            profile_render.config_text,
            iterations=fidelity.iterations,
            workers=fidelity.worker_count,
        )
    except (GcsimScreeningProfileError, ValueError) as exc:
        raise GcsimFarmingPipelineError(str(exc)) from exc
    if profile_render.investment_signature != investment_signature:
        raise GcsimFarmingPipelineError(
            "rendered profile investment contract does not match the requested "
            "investment signature"
        )
    context_sha256 = build_gcsim_farming_evaluation_context_sha256(
        engine_context=engine_context,
        prepared_config_text=prepared,
        wearer_ids=canonical_wearers,
        layout_catalog=layouts,
        profile_bank=profile_bank,
        reference_weights=reference,
        investment_signature=investment_signature,
        fidelity=fidelity,
        environment=effective_environment,
        environment_is_frozen=True,
    )
    return GcsimFarmingMaterializedProbe(
        state=state,
        candidate_keys=state.probe_key,
        config_text=exact_config,
        wearer_ids=canonical_wearers,
        set_assignments=tuple(set_assignments),
        layout_assignments=tuple(layout_assignments),
        offpiece_assignments=tuple(offpiece_assignments),
        profile_assignments=tuple(profile_assignments),
        environment_items=tuple(effective_environment.items()),
        investment_signature=investment_signature,
        evaluation_context_sha256=context_sha256,
        engine_id=engine_context.engine_id,
        engine_version=engine_context.engine_version,
        artifact_sha256=engine_context.artifact_sha256,
        engine_binding_sha256=engine_context.binding_sha256,
        catalog_fingerprint=engine_context.catalog.source_fingerprint,
        fidelity=fidelity,
        _proof=_MATERIALIZATION_PROOF,
    )


def build_gcsim_farming_evaluation_context_sha256(
    *,
    engine_context: GcsimOptimizerEngineContext,
    prepared_config_text: str,
    wearer_ids: Sequence[str],
    layout_catalog: LayoutCatalog,
    profile_bank: StatProfileBank,
    reference_weights: Sequence[StatWeight],
    investment_signature: str | None = None,
    fidelity: GcsimFarmingScreeningFidelity,
    environment: Mapping[str, str] | None = None,
    environment_is_frozen: bool = False,
) -> str:
    """Build the stable domain digest consumed by ``FullTeamComposerRequest``."""

    _require_trusted_engine_context(engine_context)
    canonical_wearers = _validated_wearer_ids(wearer_ids)
    prepared = _validated_prepared_config(prepared_config_text, canonical_wearers)
    layouts = _normalize_layout_catalog(layout_catalog, canonical_wearers)
    _validate_profile_bank(profile_bank)
    reference = _validated_reference_weights(reference_weights)
    expected_investment_signature = build_gcsim_screening_investment_signature(
        reference_weights=reference,
    )
    if investment_signature is None:
        investment_signature = expected_investment_signature
    _validate_investment_signature(
        investment_signature,
        expected=expected_investment_signature,
    )
    if not isinstance(fidelity, GcsimFarmingScreeningFidelity):
        raise GcsimFarmingPipelineError(
            "fidelity must be a GcsimFarmingScreeningFidelity"
        )
    effective_environment = _normalized_effective_environment(
        environment,
        worker_count=fidelity.worker_count,
        environment_is_frozen=environment_is_frozen,
    )

    payload = {
        "schema_version": GCSIM_FARMING_PIPELINE_CONTEXT_SCHEMA,
        "engine": {
            "engine_id": engine_context.engine_id,
            "engine_version": engine_context.engine_version,
            "optimizer_contract_version": engine_context.optimizer_contract_version,
            "artifact_sha256": engine_context.artifact_sha256,
            "binding_sha256": engine_context.binding_sha256,
            "catalog_fingerprint": engine_context.catalog.source_fingerprint,
        },
        "prepared_config_sha256": _sha256_text(prepared),
        "wearer_ids": list(canonical_wearers),
        "layouts": [
            {
                "wearer_id": wearer,
                "entries": [
                    {
                        "layout_id": layout_id,
                        "sands": layout.sands,
                        "goblet": layout.goblet,
                        "circlet": layout.circlet,
                    }
                    for layout_id, layout in sorted(layouts[wearer].items())
                ],
            }
            for wearer in canonical_wearers
        ],
        "profile_bank": {
            "axes": [
                {
                    "key": axis.key,
                    "probe_delta": axis.probe_delta,
                    "unit": axis.unit,
                }
                for axis in profile_bank.axes
            ],
            "profiles": [
                {
                    "profile_id": profile.profile_id,
                    "kind": profile.kind,
                    "weights": [
                        {"axis_key": item.axis_key, "weight": item.weight}
                        for item in sorted(
                            profile.weights,
                            key=lambda item: item.axis_key,
                        )
                    ],
                    "focus_axes": sorted(profile.focus_axes),
                }
                for profile in sorted(
                    profile_bank.profiles,
                    key=lambda item: item.profile_id,
                )
            ],
        },
        "reference_weights": [
            {"axis_key": item.axis_key, "weight": item.weight}
            for item in reference
        ],
        "investment_signature": investment_signature,
        "fidelity": fidelity.to_dict(),
        "environment": [list(item) for item in effective_environment.items()],
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class _Scheduler(Protocol):
    def run(self) -> GcsimFarmingBatchResult: ...

    def cancel(self) -> None: ...


SchedulerFactory = Callable[
    [tuple[GcsimFarmingEvaluationRequest, ...], GcsimFarmingSchedulerBudget],
    _Scheduler,
]


class GcsimFarmingFullTeamBatchSimulator:
    """``FullTeamBatchSimulator`` backed by one bounded evaluator scheduler."""

    def __init__(
        self,
        *,
        engine_context: GcsimOptimizerEngineContext,
        prepared_config_text: str,
        wearer_ids: Sequence[str],
        layout_catalog: LayoutCatalog,
        profile_bank: StatProfileBank,
        reference_weights: Sequence[StatWeight] = GCSIM_BALANCED_REFERENCE_WEIGHTS,
        investment_signature: str | None = None,
        fidelity: GcsimFarmingScreeningFidelity,
        scheduler_budget: GcsimFarmingSchedulerBudget,
        environment: Mapping[str, str] | None = None,
        environment_is_frozen: bool = False,
        cache_store: GcsimOptimizerCacheStore | None = None,
        enable_cache: bool = True,
        session_factory: FarmingSessionFactory | None = None,
        scheduler_factory: SchedulerFactory | None = None,
    ) -> None:
        _require_trusted_engine_context(engine_context)
        canonical_wearers = _validated_wearer_ids(wearer_ids)
        prepared = _validated_prepared_config(prepared_config_text, canonical_wearers)
        layouts = _normalize_layout_catalog(layout_catalog, canonical_wearers)
        _validate_profile_bank(profile_bank)
        reference = _validated_reference_weights(reference_weights)
        expected_investment_signature = build_gcsim_screening_investment_signature(
            reference_weights=reference,
        )
        if investment_signature is None:
            investment_signature = expected_investment_signature
        _validate_investment_signature(
            investment_signature,
            expected=expected_investment_signature,
        )
        if not isinstance(fidelity, GcsimFarmingScreeningFidelity):
            raise GcsimFarmingPipelineError(
                "fidelity must be a GcsimFarmingScreeningFidelity"
            )
        if not isinstance(scheduler_budget, GcsimFarmingSchedulerBudget):
            raise GcsimFarmingPipelineError(
                "scheduler_budget must be a GcsimFarmingSchedulerBudget"
            )
        if fidelity.worker_count > scheduler_budget.total_cpu_budget:
            raise GcsimFarmingPipelineError(
                "screening worker_count exceeds the scheduler CPU budget"
            )

        self.engine_context = engine_context
        self.prepared_config_text = prepared
        self.wearer_ids = canonical_wearers
        self.layout_catalog = MappingProxyType(
            {
                wearer: MappingProxyType(dict(entries))
                for wearer, entries in layouts.items()
            }
        )
        self.profile_bank = profile_bank
        self.reference_weights = tuple(reference)
        self.investment_signature = investment_signature
        self.fidelity = fidelity
        self.scheduler_budget = scheduler_budget
        self.environment = MappingProxyType(
            _normalized_effective_environment(
                environment,
                worker_count=fidelity.worker_count,
                environment_is_frozen=environment_is_frozen,
            )
        )
        self.evaluation_context_sha256 = (
            build_gcsim_farming_evaluation_context_sha256(
                engine_context=engine_context,
                prepared_config_text=prepared,
                wearer_ids=canonical_wearers,
                layout_catalog=self.layout_catalog,
                profile_bank=profile_bank,
                reference_weights=self.reference_weights,
                investment_signature=investment_signature,
                fidelity=fidelity,
                environment=self.environment,
                environment_is_frozen=True,
            )
        )
        if scheduler_factory is None:
            self._scheduler_factory: SchedulerFactory = lambda requests, budget: (
                GcsimFarmingEvaluationScheduler(
                    requests,
                    budget,
                    cache_store=cache_store,
                    enable_cache=enable_cache,
                    session_factory=session_factory,
                )
            )
        else:
            self._scheduler_factory = scheduler_factory
        self._cancel_event = Event()
        self._lock = Lock()
        self._active_scheduler: _Scheduler | None = None

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            scheduler = self._active_scheduler
        if scheduler is not None:
            scheduler.cancel()

    def __call__(
        self,
        requests: tuple[FullTeamSimulationRequest, ...],
    ) -> Mapping[ProbeKey, FullTeamSimulationMetrics]:
        simulation_requests = tuple(requests)
        if not simulation_requests:
            return MappingProxyType({})
        for item in simulation_requests:
            if not isinstance(item, FullTeamSimulationRequest):
                raise FullTeamComposerError(
                    "batch simulator accepts FullTeamSimulationRequest values only"
                )
            if item.context_sha256 != self.evaluation_context_sha256:
                raise FullTeamComposerError(
                    "simulation request carries a different evaluation context"
                )
            if item.state.wearer_ids != self.wearer_ids:
                raise FullTeamComposerError(
                    "simulation state wearer order differs from the frozen context"
                )
        probe_keys = tuple(item.state.probe_key for item in simulation_requests)
        if len(set(probe_keys)) != len(probe_keys):
            raise FullTeamComposerError("simulation batch contains duplicate probe states")

        started = monotonic()
        adapter_deadline = started + min(
            self.scheduler_budget.overall_deadline_seconds,
            min(item.timeout_seconds for item in simulation_requests),
        )
        materialized_rows: list[GcsimFarmingMaterializedProbe] = []
        for item in simulation_requests:
            if self._cancel_event.is_set():
                return _terminal_team_metrics(
                    simulation_requests,
                    status=TEAM_SIM_CANCELLED,
                    error="full-team batch cancelled during materialization",
                )
            if monotonic() >= adapter_deadline:
                return _terminal_team_metrics(
                    simulation_requests,
                    status=TEAM_SIM_TIMEOUT,
                    error="full-team batch deadline reached during materialization",
                )
            materialized_rows.append(
                materialize_gcsim_full_team_probe_state(
                self.prepared_config_text,
                state=item.state,
                wearer_ids=self.wearer_ids,
                layout_catalog=self.layout_catalog,
                profile_bank=self.profile_bank,
                engine_context=self.engine_context,
                fidelity=self.fidelity,
                reference_weights=self.reference_weights,
                environment=self.environment,
                environment_is_frozen=True,
            )
            )
        materialized = tuple(materialized_rows)
        if any(
            proof.evaluation_context_sha256 != self.evaluation_context_sha256
            for proof in materialized
        ):
            raise FullTeamComposerError(
                "materialized probe escaped the frozen evaluation context"
            )
        evaluator_requests = tuple(
            proof.build_evaluator_request(
                engine_context=self.engine_context,
                timeout_seconds=item.timeout_seconds,
                environment=self.environment,
            )
            for proof, item in zip(materialized, simulation_requests, strict=True)
        )
        remaining_budget = adapter_deadline - monotonic()
        if remaining_budget <= 0:
            return _terminal_team_metrics(
                simulation_requests,
                status=TEAM_SIM_TIMEOUT,
                error="full-team batch deadline reached before scheduling",
            )
        effective_budget = GcsimFarmingSchedulerBudget(
            max_parallel_candidates=self.scheduler_budget.max_parallel_candidates,
            total_cpu_budget=self.scheduler_budget.total_cpu_budget,
            overall_deadline_seconds=remaining_budget,
        )
        scheduler = self._scheduler_factory(evaluator_requests, effective_budget)
        if not hasattr(scheduler, "run") or not hasattr(scheduler, "cancel"):
            raise FullTeamComposerError("scheduler factory returned an invalid scheduler")
        with self._lock:
            if self._active_scheduler is not None:
                raise FullTeamComposerError(
                    "full-team batch simulator does not allow concurrent calls"
                )
            self._active_scheduler = scheduler
        try:
            if self._cancel_event.is_set():
                scheduler.cancel()
            batch = scheduler.run()
        finally:
            with self._lock:
                if self._active_scheduler is scheduler:
                    self._active_scheduler = None
        if not isinstance(batch, GcsimFarmingBatchResult):
            raise FullTeamComposerError("scheduler returned a non-typed batch result")
        if len(batch.results) != len(evaluator_requests):
            raise FullTeamComposerError(
                "scheduler did not return exactly one result per materialized request"
            )
        if any(
            not isinstance(result, GcsimFarmingEvaluationResult)
            for result in batch.results
        ):
            raise FullTeamComposerError(
                "scheduler returned a non-typed evaluation result"
            )
        expected_order = tuple(request.candidate_keys for request in evaluator_requests)
        actual_order = tuple(result.candidate_keys for result in batch.results)
        if actual_order != expected_order:
            raise FullTeamComposerError(
                "scheduler result order does not match the materialized request order"
            )
        if batch.status is GcsimFarmingBatchStatus.CANCELLED:
            return _terminal_team_metrics(
                simulation_requests,
                status=TEAM_SIM_CANCELLED,
                error="full-team evaluator batch was cancelled",
            )
        if batch.status is GcsimFarmingBatchStatus.DEADLINE_REACHED:
            return _terminal_team_metrics(
                simulation_requests,
                status=TEAM_SIM_TIMEOUT,
                error="full-team evaluator batch reached its deadline",
            )

        outcomes: dict[ProbeKey, FullTeamSimulationMetrics] = {}
        for simulation, evaluator_request, result in zip(
            simulation_requests,
            evaluator_requests,
            batch.results,
            strict=True,
        ):
            _validate_result_provenance(result, evaluator_request)
            outcomes[simulation.state.probe_key] = _team_metrics(result)
        if tuple(outcomes) != probe_keys:
            raise FullTeamComposerError(
                "batch adapter failed to preserve the exact probe-key order"
            )
        return MappingProxyType(outcomes)


def _team_metrics(
    result: GcsimFarmingEvaluationResult,
) -> FullTeamSimulationMetrics:
    if result.status in {
        GcsimFarmingEvaluationStatus.PASSED,
        GcsimFarmingEvaluationStatus.CACHED,
    }:
        summary = result.summary
        return FullTeamSimulationMetrics(
            status=TEAM_SIM_PASSED,
            dps_mean=summary.dps_mean,
            dps_se=summary.dps_se,
            iterations=summary.iterations,
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
        cache_hit=False,
        error=result.error or result.status.value,
    )


def _terminal_team_metrics(
    requests: Sequence[FullTeamSimulationRequest],
    *,
    status: str,
    error: str,
) -> Mapping[ProbeKey, FullTeamSimulationMetrics]:
    return MappingProxyType(
        {
            item.state.probe_key: FullTeamSimulationMetrics(
                status=status,
                cache_hit=False,
                error=error,
            )
            for item in requests
        }
    )


def _validate_result_provenance(
    result: GcsimFarmingEvaluationResult,
    request: GcsimFarmingEvaluationRequest,
) -> None:
    if not isinstance(result, GcsimFarmingEvaluationResult):
        raise FullTeamComposerError("scheduler returned a non-typed evaluation result")
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
        raise FullTeamComposerError(
            "scheduler result provenance does not match its materialized request"
        )


def _normalized_effective_environment(
    environment: Mapping[str, str] | None,
    *,
    worker_count: int,
    environment_is_frozen: bool = False,
) -> dict[str, str]:
    try:
        if environment_is_frozen:
            return normalize_gcsim_farming_frozen_environment(
                environment,
                worker_count=worker_count,
            )
        return freeze_gcsim_farming_environment(
            environment,
            worker_count=worker_count,
        )
    except ValueError as exc:
        raise GcsimFarmingPipelineError(str(exc)) from exc


def _require_matching_engine_context(
    proof: GcsimFarmingMaterializedProbe,
    engine_context: GcsimOptimizerEngineContext,
) -> None:
    _require_trusted_engine_context(engine_context)
    if (
        proof.engine_id != engine_context.engine_id
        or proof.engine_version != engine_context.engine_version
        or proof.artifact_sha256 != engine_context.artifact_sha256
        or proof.engine_binding_sha256 != engine_context.binding_sha256
        or proof.catalog_fingerprint != engine_context.catalog.source_fingerprint
    ):
        raise GcsimFarmingPipelineError(
            "materialized probe belongs to a different engine context"
        )


def _require_trusted_engine_context(
    engine_context: GcsimOptimizerEngineContext,
) -> None:
    if not isinstance(engine_context, GcsimOptimizerEngineContext):
        raise GcsimFarmingPipelineError(
            "engine_context must be a GcsimOptimizerEngineContext"
        )
    if not engine_context.trusted:
        raise GcsimFarmingPipelineError(
            "farming pipeline requires a resealed trusted engine context"
        )
    if (
        engine_context.optimizer_contract_version
        != PINNED_GCSIM_OPTIMIZER_CONTRACT_VERSION
    ):
        raise GcsimFarmingPipelineError(
            "farming profile renderer requires optimizer contract "
            f"{PINNED_GCSIM_OPTIMIZER_CONTRACT_VERSION!r}"
        )
    for field_name, value in (
        ("artifact_sha256", engine_context.artifact_sha256),
        ("binding_sha256", engine_context.binding_sha256),
        ("catalog_fingerprint", engine_context.catalog.source_fingerprint),
    ):
        if not _is_sha256(value):
            raise GcsimFarmingPipelineError(
                f"trusted engine {field_name} is not a lowercase SHA-256 digest"
            )


def _validated_wearer_ids(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GcsimFarmingPipelineError("wearer_ids must be a sequence")
    result = tuple(values)
    if not result or len(result) > 4:
        raise GcsimFarmingPipelineError("wearer_ids must contain one to four values")
    if len(set(result)) != len(result):
        raise GcsimFarmingPipelineError("wearer_ids must be unique")
    for wearer in result:
        if not isinstance(wearer, str) or not _WEARER_RE.fullmatch(wearer):
            raise GcsimFarmingPipelineError(
                "wearer ids must be lowercase ASCII GCSIM character keys"
            )
    return result


def _validated_prepared_config(
    config_text: str,
    wearer_ids: tuple[str, ...],
) -> str:
    text = str(config_text or "")
    try:
        declared = validate_gcsim_farming_static_config(text)
    except ValueError as exc:
        raise GcsimFarmingPipelineError(str(exc)) from exc
    if tuple(declared) != wearer_ids:
        raise GcsimFarmingPipelineError(
            "prepared config character declarations must match wearer_ids "
            f"exactly in canonical order; declared={tuple(declared)!r}, "
            f"expected={wearer_ids!r}"
        )
    return text


def _normalize_layout_catalog(
    layout_catalog: LayoutCatalog,
    wearer_ids: tuple[str, ...],
) -> dict[str, dict[str, GcsimFiveStarMainStatLayout]]:
    if not isinstance(layout_catalog, Mapping):
        raise GcsimFarmingPipelineError("layout_catalog must be a mapping")
    outer_keys = tuple(layout_catalog)
    if set(outer_keys) != set(wearer_ids) or len(outer_keys) != len(wearer_ids):
        raise GcsimFarmingPipelineError(
            "layout_catalog must cover exactly the canonical wearer ids"
        )
    result: dict[str, dict[str, GcsimFiveStarMainStatLayout]] = {}
    for wearer in wearer_ids:
        entries = layout_catalog[wearer]
        if not isinstance(entries, Mapping) or not entries:
            raise GcsimFarmingPipelineError(
                f"layout catalog for wearer {wearer!r} must be a non-empty mapping"
            )
        normalized: dict[str, GcsimFiveStarMainStatLayout] = {}
        for layout_id, layout in entries.items():
            _require_identifier(layout_id, field_name="main-stat layout id")
            if "\x00" in layout_id:
                raise GcsimFarmingPipelineError("layout ids must not contain NUL")
            if layout_id in normalized:
                raise GcsimFarmingPipelineError(
                    f"duplicate layout id for wearer {wearer!r}: {layout_id!r}"
                )
            if not isinstance(layout, GcsimFiveStarMainStatLayout):
                raise GcsimFarmingPipelineError(
                    "layout catalog values must be GcsimFiveStarMainStatLayout"
                )
            try:
                render_five_star_main_stat_line(wearer, layout)
            except ValueError as exc:
                raise GcsimFarmingPipelineError(str(exc)) from exc
            normalized[layout_id] = layout
        result[wearer] = normalized
    return result


def _validate_profile_bank(profile_bank: StatProfileBank) -> None:
    if not isinstance(profile_bank, StatProfileBank):
        raise GcsimFarmingPipelineError("profile_bank must be a StatProfileBank")
    actual_axes = tuple(
        (axis.key, axis.probe_delta, axis.unit)
        for axis in profile_bank.axes
    )
    expected_axes = tuple(
        (axis.key, axis.probe_delta, axis.unit)
        for axis in GCSIM_SCREENING_STAT_AXES
    )
    if actual_axes != expected_axes:
        raise GcsimFarmingPipelineError(
            "profile bank axes do not match the pinned GCSIM screening contract"
        )


def _validated_reference_weights(
    reference_weights: Sequence[StatWeight],
) -> tuple[StatWeight, ...]:
    values = tuple(reference_weights)
    if not values:
        raise GcsimFarmingPipelineError("reference_weights must not be empty")
    allowed = set(GCSIM_SUBSTAT_ROLL_VALUES)
    weights: dict[str, float] = {}
    for item in values:
        if not isinstance(item, StatWeight):
            raise GcsimFarmingPipelineError(
                "reference_weights must contain StatWeight values"
            )
        if item.axis_key not in allowed:
            raise GcsimFarmingPipelineError(
                f"reference weight uses unsupported axis: {item.axis_key!r}"
            )
        if item.axis_key in weights:
            raise GcsimFarmingPipelineError(
                f"duplicate reference weight axis: {item.axis_key!r}"
            )
        weights[item.axis_key] = item.weight
    total = sum(weights.values())
    if not math.isfinite(total) or total <= 0:
        raise GcsimFarmingPipelineError("reference weight total must be positive")
    return tuple(
        StatWeight(axis_key=axis, weight=weights[axis] / total)
        for axis in GCSIM_SUBSTAT_ROLL_VALUES
        if axis in weights
    )


def _validate_investment_signature(value: str, *, expected: str) -> None:
    _require_identifier(value, field_name="investment signature")
    if value != expected:
        raise GcsimFarmingPipelineError(
            "investment signature does not match the pinned screening renderer"
        )


def _require_identifier(value: object, *, field_name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise GcsimFarmingPipelineError(
            f"{field_name} must be a non-empty trimmed string"
        )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


__all__ = [
    "GCSIM_FARMING_STATIC_TARGET_HP",
    "GCSIM_FARMING_PIPELINE_CONTEXT_SCHEMA",
    "GcsimFarmingFullTeamBatchSimulator",
    "GcsimFarmingMaterializedProbe",
    "GcsimFarmingPipelineError",
    "GcsimFarmingScreeningFidelity",
    "LayoutCatalog",
    "build_gcsim_farming_evaluation_context_sha256",
    "materialize_gcsim_full_team_probe_state",
    "materialize_gcsim_one_wearer_candidate",
]
