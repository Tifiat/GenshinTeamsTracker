"""Paired artifact-set impact screening for broad optimizer package search.

The account-wide and theoretical package domains must not rank artifact sets
by piece substats alone.  This boundary keeps one complete synthetic stat
budget fixed, adds exactly one candidate package to one wearer, and measures
personal plus team DPS on a common seed panel.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
from itertools import combinations
from math import isfinite, sqrt
from time import monotonic

from .optimizer_anytime_response import (
    GcsimOptimizerAnytimeResponseResult,
    strip_gcsim_optimizer_character_set_lines,
)
from .optimizer_anytime_candidates import GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_product_contracts import (
    GcsimFourPieceTargetPackage,
    GcsimOptimizerSetReference,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerTarget,
    GcsimTwoPlusTwoTargetPackage,
)
from .optimizer_set_semantics import (
    GcsimOptimizerSetSemanticManifest,
    build_gcsim_optimizer_set_semantic_manifest,
)
from .optimizer_stat_response import (
    GCSIM_SET_RESPONSE_CAPABILITY,
    GCSIM_STAT_RESPONSE_ROLL_VALUES,
    GcsimSetResponseChange,
    GcsimStatResponseChange,
    GcsimStatResponseEstimate,
    GcsimStatResponseIntervention,
    GcsimStatResponseRequest,
    GcsimStatResponseSummary,
    GcsimStatResponseTarget,
    run_gcsim_stat_response,
)


GCSIM_OPTIMIZER_SET_IMPACT_SCHEMA_VERSION = 2
GCSIM_OPTIMIZER_SET_IMPACT_PLAN_ID = "paired_set_impact_v2"
GCSIM_OPTIMIZER_SET_IMPACT_PLAN_VERSION = 4


class GcsimOptimizerSetImpactError(RuntimeError):
    """Raised when set-impact evidence cannot be trusted."""


class GcsimOptimizerSetImpactClassification(str, Enum):
    PERSONAL_POSITIVE = "personal_positive"
    TEAM_POSITIVE = "team_positive"
    PERSONAL_AND_TEAM_POSITIVE = "personal_and_team_positive"
    UNCERTAIN_RETAINED = "uncertain_retained"
    NEGLIGIBLE = "negligible"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSingleTwoPieceImpactTarget:
    """One concrete 2p effect used to shortlist theoretical 2p+2p pairs."""

    wearer: GcsimOptimizerWearerIdentity
    set_ref: GcsimOptimizerSetReference
    set_count: int = 2
    schema_version: int = GCSIM_OPTIMIZER_SET_IMPACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerSetImpactError(
                "single-2p impact wearer must be typed"
            )
        if not isinstance(self.set_ref, GcsimOptimizerSetReference):
            raise GcsimOptimizerSetImpactError(
                "single-2p impact set reference must be typed"
            )
        if self.set_count != 2:
            raise GcsimOptimizerSetImpactError(
                "single-2p impact target must use set_count=2"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": "single_two_piece",
            "wearer": self.wearer.to_dict(),
            "set_ref": self.set_ref.to_dict(),
            "set_count": self.set_count,
        }


GcsimOptimizerSetImpactTarget = (
    GcsimOptimizerWearerTarget | GcsimOptimizerSingleTwoPieceImpactTarget
)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSetImpactPlan:
    iterations: int = 8
    worker_count: int = 1
    max_interventions_per_batch: int = 256
    confidence_sigma_positive: float = 0.5
    confidence_sigma_negligible: float = 2.0
    relative_materiality: float = 0.00005
    absolute_materiality_dps: float = 1.0
    enable_crit_headroom_panel: bool = True
    enable_team_interaction_panel: bool = False
    crit_headroom_raw_cr: float = 0.0
    candidate_timeout_seconds: float = 90.0
    overall_deadline_seconds: float = 600.0
    schema_version: int = GCSIM_OPTIMIZER_SET_IMPACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in (
            "iterations",
            "worker_count",
            "max_interventions_per_batch",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise GcsimOptimizerSetImpactError(
                    f"{field_name} must be a positive integer"
                )
        if self.iterations > 1024:
            raise GcsimOptimizerSetImpactError(
                "set-impact iterations must not exceed 1024"
            )
        if self.worker_count > min(self.iterations, 64):
            raise GcsimOptimizerSetImpactError(
                "set-impact worker_count exceeds engine bounds"
            )
        if self.max_interventions_per_batch > 256:
            raise GcsimOptimizerSetImpactError(
                "set-impact batch exceeds the engine intervention cap"
            )
        for field_name in (
            "confidence_sigma_positive",
            "confidence_sigma_negligible",
            "relative_materiality",
            "absolute_materiality_dps",
            "crit_headroom_raw_cr",
            "candidate_timeout_seconds",
            "overall_deadline_seconds",
        ):
            value = float(getattr(self, field_name))
            if not isfinite(value) or value < 0:
                raise GcsimOptimizerSetImpactError(
                    f"{field_name} must be finite and non-negative"
                )
        if not isinstance(self.enable_crit_headroom_panel, bool) or not isinstance(
            self.enable_team_interaction_panel,
            bool,
        ):
            raise GcsimOptimizerSetImpactError(
                "set-impact panel flags must be boolean"
            )
        if not 0 <= self.crit_headroom_raw_cr <= 0.95:
            raise GcsimOptimizerSetImpactError(
                "crit_headroom_raw_cr must be in 0..0.95"
            )
        if (
            self.confidence_sigma_negligible
            < self.confidence_sigma_positive
            or self.candidate_timeout_seconds <= 0
            or self.overall_deadline_seconds <= 0
        ):
            raise GcsimOptimizerSetImpactError(
                "set-impact confidence/deadline bounds are incoherent"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": GCSIM_OPTIMIZER_SET_IMPACT_PLAN_ID,
            "plan_version": GCSIM_OPTIMIZER_SET_IMPACT_PLAN_VERSION,
            "iterations": self.iterations,
            "worker_count": self.worker_count,
            "max_interventions_per_batch": (
                self.max_interventions_per_batch
            ),
            "confidence_sigma_positive": self.confidence_sigma_positive,
            "confidence_sigma_negligible": (
                self.confidence_sigma_negligible
            ),
            "relative_materiality": self.relative_materiality,
            "absolute_materiality_dps": self.absolute_materiality_dps,
            "enable_crit_headroom_panel": self.enable_crit_headroom_panel,
            "enable_team_interaction_panel": (
                self.enable_team_interaction_panel
            ),
            "crit_headroom_raw_cr": self.crit_headroom_raw_cr,
            "candidate_timeout_seconds": self.candidate_timeout_seconds,
            "overall_deadline_seconds": self.overall_deadline_seconds,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSetImpactRow:
    target: GcsimOptimizerSetImpactTarget
    classification: GcsimOptimizerSetImpactClassification
    team_delta: GcsimStatResponseEstimate
    personal_delta: GcsimStatResponseEstimate
    character_deltas: tuple[GcsimStatResponseEstimate, ...]
    surrogate_dps: float
    evidence_sha256: str
    schema_version: int = GCSIM_OPTIMIZER_SET_IMPACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(
            self.target,
            (
                GcsimOptimizerWearerTarget,
                GcsimOptimizerSingleTwoPieceImpactTarget,
            ),
        ):
            raise GcsimOptimizerSetImpactError(
                "set-impact target must be typed"
            )
        if not isinstance(
            self.classification,
            GcsimOptimizerSetImpactClassification,
        ):
            raise GcsimOptimizerSetImpactError(
                "set-impact classification must be typed"
            )
        if (
            not isinstance(self.team_delta, GcsimStatResponseEstimate)
            or not isinstance(self.personal_delta, GcsimStatResponseEstimate)
            or len(self.character_deltas) != 4
            or any(
                not isinstance(item, GcsimStatResponseEstimate)
                for item in self.character_deltas
            )
        ):
            raise GcsimOptimizerSetImpactError(
                "set-impact estimates are malformed"
            )
        value = float(self.surrogate_dps)
        if not isfinite(value) or value < 0:
            raise GcsimOptimizerSetImpactError(
                "set-impact surrogate DPS must be finite and non-negative"
            )
        _require_sha256(self.evidence_sha256, "evidence_sha256")
        object.__setattr__(self, "character_deltas", tuple(self.character_deltas))
        object.__setattr__(self, "surrogate_dps", value)

    @property
    def retained(self) -> bool:
        return (
            self.classification
            is not GcsimOptimizerSetImpactClassification.NEGLIGIBLE
        )

    @property
    def package_identity_sha256(self) -> str:
        if isinstance(
            self.target,
            GcsimOptimizerSingleTwoPieceImpactTarget,
        ):
            return self.target.identity_sha256
        return self.target.package.identity_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "target": self.target.to_dict(),
            "classification": self.classification.value,
            "team_delta": _estimate_payload(self.team_delta),
            "personal_delta": _estimate_payload(self.personal_delta),
            "character_deltas": [
                _estimate_payload(item) for item in self.character_deltas
            ],
            "surrogate_dps": self.surrogate_dps,
            "evidence_sha256": self.evidence_sha256,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSetRuntimeObservation:
    target_identity_sha256: str
    panel_id: str
    wearer_team_slot: int
    team_delta: GcsimStatResponseEstimate
    character_deltas: tuple[GcsimStatResponseEstimate, ...]
    request_sha256: str
    seed_panel_sha256: str
    runtime_classification: str
    observation_contract: str = "paired_dps_vector_v1"

    def __post_init__(self) -> None:
        for value in (
            self.target_identity_sha256,
            self.request_sha256,
            self.seed_panel_sha256,
        ):
            _require_sha256(value, "runtime observation identity")
        if self.panel_id not in {"balanced", "crit_headroom"}:
            raise GcsimOptimizerSetImpactError(
                "runtime observation panel is invalid"
            )
        if self.wearer_team_slot not in range(1, 5):
            raise GcsimOptimizerSetImpactError(
                "runtime observation wearer must be in slot 1..4"
            )
        if (
            not isinstance(self.team_delta, GcsimStatResponseEstimate)
            or len(self.character_deltas) != 4
            or any(
                not isinstance(item, GcsimStatResponseEstimate)
                for item in self.character_deltas
            )
        ):
            raise GcsimOptimizerSetImpactError(
                "runtime observation DPS estimates are malformed"
            )
        if self.runtime_classification not in {
            "active_observed",
            "inactive_not_proved",
            "uncertain",
        }:
            raise GcsimOptimizerSetImpactError(
                "runtime observation classification is invalid"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "target_identity_sha256": self.target_identity_sha256,
            "panel_id": self.panel_id,
            "wearer_team_slot": self.wearer_team_slot,
            "team_delta": _estimate_payload(self.team_delta),
            "character_deltas": [
                _estimate_payload(item) for item in self.character_deltas
            ],
            "request_sha256": self.request_sha256,
            "seed_panel_sha256": self.seed_panel_sha256,
            "runtime_classification": self.runtime_classification,
            "observation_contract": self.observation_contract,
            "uptime_semantics": "opaque_not_observed",
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSetInteractionObservation:
    interaction_id: str
    target_identity_sha256s: tuple[str, ...]
    wearer_team_slots: tuple[int, ...]
    observed_team_delta: GcsimStatResponseEstimate
    additive_team_mean: float
    additive_team_se: float
    residual_team_mean: float
    residual_team_se: float
    character_residual_means: tuple[float, float, float, float]
    character_residual_ses: tuple[float, float, float, float]
    classification: str
    request_sha256: str
    seed_panel_sha256: str

    def __post_init__(self) -> None:
        identities = tuple(self.target_identity_sha256s)
        slots = tuple(self.wearer_team_slots)
        if (
            not self.interaction_id
            or len(identities) not in {2, 4}
            or len(slots) != len(identities)
            or len(set(slots)) != len(slots)
            or any(slot not in range(1, 5) for slot in slots)
        ):
            raise GcsimOptimizerSetImpactError(
                "set interaction identity/slots are malformed"
            )
        for value in (*identities, self.request_sha256, self.seed_panel_sha256):
            _require_sha256(value, "set interaction identity")
        values = (
            self.additive_team_mean,
            self.additive_team_se,
            self.residual_team_mean,
            self.residual_team_se,
            *self.character_residual_means,
            *self.character_residual_ses,
        )
        if any(not isfinite(float(value)) for value in values) or any(
            value < 0
            for value in (
                self.additive_team_se,
                self.residual_team_se,
                *self.character_residual_ses,
            )
        ):
            raise GcsimOptimizerSetImpactError(
                "set interaction estimate is invalid"
            )
        if self.classification not in {
            "non_additive",
            "additive_within_noise",
            "uncertain",
        }:
            raise GcsimOptimizerSetImpactError(
                "set interaction classification is invalid"
            )
        object.__setattr__(self, "target_identity_sha256s", identities)
        object.__setattr__(self, "wearer_team_slots", slots)

    def to_dict(self) -> dict[str, object]:
        return {
            "interaction_id": self.interaction_id,
            "target_identity_sha256s": list(self.target_identity_sha256s),
            "wearer_team_slots": list(self.wearer_team_slots),
            "observed_team_delta": _estimate_payload(
                self.observed_team_delta
            ),
            "additive_team_mean": self.additive_team_mean,
            "additive_team_se": self.additive_team_se,
            "residual_team_mean": self.residual_team_mean,
            "residual_team_se": self.residual_team_se,
            "character_residual_means": list(self.character_residual_means),
            "character_residual_ses": list(self.character_residual_ses),
            "classification": self.classification,
            "request_sha256": self.request_sha256,
            "seed_panel_sha256": self.seed_panel_sha256,
            "stacking_semantics": "measured_opaque_interaction",
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSetImpactResult:
    rows: tuple[GcsimOptimizerSetImpactRow, ...]
    plan: GcsimOptimizerSetImpactPlan
    response_evidence_sha256: str
    elapsed_seconds: float
    batch_count: int
    semantic_manifest: GcsimOptimizerSetSemanticManifest | None = None
    runtime_observations: tuple[GcsimOptimizerSetRuntimeObservation, ...] = ()
    interaction_observations: tuple[
        GcsimOptimizerSetInteractionObservation,
        ...,
    ] = ()
    schema_version: int = GCSIM_OPTIMIZER_SET_IMPACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        rows = tuple(self.rows)
        if len(
            {
                (item.target.wearer, item.package_identity_sha256)
                for item in rows
            }
        ) != len(rows):
            raise GcsimOptimizerSetImpactError(
                "set-impact rows must be unique by wearer/package"
            )
        if not isinstance(self.plan, GcsimOptimizerSetImpactPlan):
            raise GcsimOptimizerSetImpactError("set-impact plan must be typed")
        _require_sha256(
            self.response_evidence_sha256,
            "response_evidence_sha256",
        )
        if (
            not isfinite(self.elapsed_seconds)
            or self.elapsed_seconds < 0
            or isinstance(self.batch_count, bool)
            or not isinstance(self.batch_count, int)
            or self.batch_count < 0
        ):
            raise GcsimOptimizerSetImpactError(
                "set-impact result timing/batch count is invalid"
            )
        object.__setattr__(self, "rows", rows)
        if self.semantic_manifest is not None and not isinstance(
            self.semantic_manifest,
            GcsimOptimizerSetSemanticManifest,
        ):
            raise GcsimOptimizerSetImpactError(
                "set semantic manifest must be typed"
            )
        runtime = tuple(self.runtime_observations)
        interactions = tuple(self.interaction_observations)
        if any(
            not isinstance(item, GcsimOptimizerSetRuntimeObservation)
            for item in runtime
        ) or any(
            not isinstance(item, GcsimOptimizerSetInteractionObservation)
            for item in interactions
        ):
            raise GcsimOptimizerSetImpactError(
                "set runtime/interaction observations must be typed"
            )
        object.__setattr__(self, "runtime_observations", runtime)
        object.__setattr__(self, "interaction_observations", interactions)

    @property
    def row_by_target_identity(
        self,
    ) -> Mapping[str, GcsimOptimizerSetImpactRow]:
        return {
            _target_identity(item.target): item
            for item in self.rows
        }

    @property
    def surrogate_dps_by_target_identity(self) -> Mapping[str, float]:
        return {
            _target_identity(item.target): item.surrogate_dps
            for item in self.rows
            if item.retained
        }

    def retained_targets_for_slot(
        self,
        team_slot: int,
    ) -> tuple[GcsimOptimizerSetImpactTarget, ...]:
        return tuple(
            item.target
            for item in self.rows
            if item.target.wearer.team_slot == team_slot and item.retained
        )

    def to_dict(self) -> dict[str, object]:
        """Return complete replay evidence, not only the derived identity.

        Set-impact results are retained by the theoretical anytime service and
        are part of the benchmark audit trail.  Keeping the full rows here
        avoids forcing diagnostics to reverse the private identity helper or
        losing an otherwise completed multi-minute run during serialization.
        """

        return {
            "schema_version": self.schema_version,
            "plan": self.plan.to_dict(),
            "response_evidence_sha256": self.response_evidence_sha256,
            "elapsed_seconds": self.elapsed_seconds,
            "batch_count": self.batch_count,
            "rows": [item.to_dict() for item in self.rows],
            "semantic_manifest": (
                None
                if self.semantic_manifest is None
                else self.semantic_manifest.to_dict()
            ),
            "runtime_observations": [
                item.to_dict() for item in self.runtime_observations
            ],
            "interaction_observations": [
                item.to_dict() for item in self.interaction_observations
            ],
        }


SetImpactProgressCallback = Callable[[int, int], None]
StatResponseRunner = Callable[..., object]


@dataclass(frozen=True, slots=True)
class _SetPanelEvidence:
    panel_id: str
    delta: GcsimStatResponseSummary
    baseline: GcsimStatResponseSummary
    request_sha256: str
    seed_panel_sha256: str


def discover_gcsim_optimizer_set_impacts(
    *,
    engine_context: GcsimOptimizerEngineContext,
    prepared_config_text: str,
    targets: Sequence[GcsimOptimizerSetImpactTarget],
    response: GcsimOptimizerAnytimeResponseResult,
    stat_response_target: GcsimStatResponseTarget,
    plan: GcsimOptimizerSetImpactPlan | None = None,
    progress_callback: SetImpactProgressCallback | None = None,
    environment: Mapping[str, str] | None = None,
    stat_response_runner: StatResponseRunner = run_gcsim_stat_response,
    is_cancelled: Callable[[], bool] | None = None,
    clock: Callable[[], float] = monotonic,
) -> GcsimOptimizerSetImpactResult:
    """Measure every concrete wearer/package against one neutral baseline."""

    selected_plan = plan or GcsimOptimizerSetImpactPlan()
    if not isinstance(engine_context, GcsimOptimizerEngineContext):
        raise GcsimOptimizerSetImpactError("engine_context must be typed")
    if (
        not engine_context.trusted
        or engine_context.issues
        or GCSIM_SET_RESPONSE_CAPABILITY
        not in set(engine_context.capabilities)
    ):
        raise GcsimOptimizerSetImpactError(
            "trusted engine with gtt_set_response_v1 is required"
        )
    if not isinstance(response, GcsimOptimizerAnytimeResponseResult):
        raise GcsimOptimizerSetImpactError("response must be typed")
    if not isinstance(stat_response_target, GcsimStatResponseTarget):
        raise GcsimOptimizerSetImpactError(
            "set-impact target must be explicit and typed"
        )
    target_rows = tuple(
        sorted(
            targets,
            key=lambda item: (
                item.wearer.team_slot,
                _target_package_identity(item),
            ),
        )
    )
    if (
        not target_rows
        or any(
            not isinstance(
                item,
                (
                    GcsimOptimizerWearerTarget,
                    GcsimOptimizerSingleTwoPieceImpactTarget,
                ),
            )
            for item in target_rows
        )
        or len(
            {
                (item.wearer, _target_package_identity(item))
                for item in target_rows
            }
        )
        != len(target_rows)
    ):
        raise GcsimOptimizerSetImpactError(
            "set-impact targets must be non-empty, typed, and unique"
        )
    neutral_config = strip_gcsim_optimizer_character_set_lines(
        prepared_config_text
    )
    semantic_manifest = build_gcsim_optimizer_set_semantic_manifest(
        engine_context
    )
    started = clock()
    deadline = started + selected_plan.overall_deadline_seconds
    completed = 0
    batches = tuple(
        target_rows[index : index + selected_plan.max_interventions_per_batch]
        for index in range(
            0,
            len(target_rows),
            selected_plan.max_interventions_per_batch,
        )
    )
    panels = [
        ("balanced", response.synthetic_baseline_changes),
    ]
    if selected_plan.enable_crit_headroom_panel:
        panels.append(
            (
                "crit_headroom",
                _baseline_with_raw_crit(
                    response.synthetic_baseline_changes,
                    response=response,
                    raw_cr=selected_plan.crit_headroom_raw_cr,
                ),
            )
        )
    evidence_by_target: dict[
        str,
        list[_SetPanelEvidence],
    ] = {
        _target_identity(target): [] for target in target_rows
    }
    interaction_probe_count = (
        _planned_team_interaction_count(target_rows)
        if selected_plan.enable_team_interaction_panel
        else 0
    )
    total_probe_count = (
        len(target_rows) * len(panels) + interaction_probe_count
    )
    if progress_callback is not None:
        progress_callback(0, total_probe_count)
    for panel_id, baseline_changes in panels:
        for batch_index, batch in enumerate(batches):
            if (
                (is_cancelled is not None and is_cancelled())
                or clock() >= deadline
            ):
                raise GcsimOptimizerSetImpactError(
                    "set-impact screening was cancelled or reached its deadline"
                )
            interventions = tuple(
                GcsimStatResponseIntervention(
                    intervention_id=f"package_{batch_index}_{index}",
                    changes=_set_changes(target),
                )
                for index, target in enumerate(batch)
            )
            context_sha256 = _canonical_sha256(
                {
                    "schema_version": (
                        GCSIM_OPTIMIZER_SET_IMPACT_SCHEMA_VERSION
                    ),
                    "engine_binding_sha256": engine_context.binding_sha256,
                    "config_sha256": hashlib.sha256(
                        neutral_config.encode("utf-8")
                    ).hexdigest(),
                    "target_sha256": stat_response_target.target_sha256,
                    "response_evidence_sha256": response.evidence_sha256,
                    "plan_sha256": selected_plan.identity_sha256,
                    "panel_id": panel_id,
                    "batch_targets": [item.to_dict() for item in batch],
                }
            )
            request = GcsimStatResponseRequest(
                context_sha256=context_sha256,
                objective=stat_response_target.objective,
                iterations=selected_plan.iterations,
                workers=selected_plan.worker_count,
                master_seed=response.synthetic_master_seed,
                baseline_changes=baseline_changes,
                interventions=interventions,
                ignore_burst_energy=True,
            )
            remaining = max(deadline - clock(), 0.001)
            result = stat_response_runner(
                engine_context=engine_context,
                prepared_config_text=neutral_config,
                target=stat_response_target,
                request=request,
                timeout_seconds=min(
                    selected_plan.candidate_timeout_seconds
                    * (len(interventions) + 2),
                    remaining,
                ),
                environment=environment,
                is_cancelled=is_cancelled,
            )
            observations = result.observation_by_id
            baseline = result.baseline.summary
            for index, target in enumerate(batch):
                observation = observations[
                    f"package_{batch_index}_{index}"
                ]
                if observation.paired_delta is None:
                    raise GcsimOptimizerSetImpactError(
                        "set-impact observation lacks paired evidence"
                    )
                evidence_by_target[_target_identity(target)].append(
                    _SetPanelEvidence(
                        panel_id=panel_id,
                        delta=observation.paired_delta,
                        baseline=baseline,
                        request_sha256=request.request_sha256,
                        seed_panel_sha256=result.seed_panel_sha256,
                    )
                )
                completed += 1
                if progress_callback is not None:
                    progress_callback(completed, total_probe_count)
    rows = tuple(
        _classify_row(
            target,
            evidence_by_target[_target_identity(target)],
            plan=selected_plan,
        )
        for target in target_rows
    )
    runtime_observations = _runtime_observations(
        target_rows,
        evidence_by_target=evidence_by_target,
        plan=selected_plan,
    )
    interaction_observations = ()
    interaction_batch_count = 0
    if interaction_probe_count:
        interaction_observations = _discover_team_set_interactions(
            engine_context=engine_context,
            neutral_config=neutral_config,
            stat_response_target=stat_response_target,
            response=response,
            rows=rows,
            evidence_by_target=evidence_by_target,
            plan=selected_plan,
            deadline=deadline,
            completed_offset=completed,
            total_probe_count=total_probe_count,
            progress_callback=progress_callback,
            environment=environment,
            stat_response_runner=stat_response_runner,
            is_cancelled=is_cancelled,
            clock=clock,
        )
        interaction_batch_count = 1
    return GcsimOptimizerSetImpactResult(
        rows=rows,
        plan=selected_plan,
        response_evidence_sha256=response.evidence_sha256,
        elapsed_seconds=max(clock() - started, 0.0),
        batch_count=len(batches) * len(panels) + interaction_batch_count,
        semantic_manifest=semantic_manifest,
        runtime_observations=runtime_observations,
        interaction_observations=interaction_observations,
    )


def _planned_team_interaction_count(targets):
    slot_count = len({item.wearer.team_slot for item in targets})
    return slot_count * (slot_count - 1) // 2 + (1 if slot_count == 4 else 0)


def _runtime_observations(targets, *, evidence_by_target, plan):
    rows = []
    for target in targets:
        identity = _target_identity(target)
        for panel in evidence_by_target[identity]:
            threshold = max(
                abs(panel.baseline.team_expected_dps.mean)
                * plan.relative_materiality,
                plan.absolute_materiality_dps,
            )
            estimate = panel.delta.team_expected_dps
            lower = abs(estimate.mean) - (
                plan.confidence_sigma_positive * estimate.standard_error
            )
            upper = abs(estimate.mean) + (
                plan.confidence_sigma_negligible * estimate.standard_error
            )
            classification = (
                "active_observed"
                if lower > threshold
                else "inactive_not_proved"
                if upper <= threshold
                else "uncertain"
            )
            rows.append(
                GcsimOptimizerSetRuntimeObservation(
                    target_identity_sha256=identity,
                    panel_id=panel.panel_id,
                    wearer_team_slot=target.wearer.team_slot,
                    team_delta=estimate,
                    character_deltas=panel.delta.character_expected_dps,
                    request_sha256=panel.request_sha256,
                    seed_panel_sha256=panel.seed_panel_sha256,
                    runtime_classification=classification,
                )
            )
    return tuple(rows)


def _discover_team_set_interactions(
    *,
    engine_context,
    neutral_config,
    stat_response_target,
    response,
    rows,
    evidence_by_target,
    plan,
    deadline,
    completed_offset,
    total_probe_count,
    progress_callback,
    environment,
    stat_response_runner,
    is_cancelled,
    clock,
):
    best_by_slot = {}
    for row in rows:
        slot = row.target.wearer.team_slot
        current = best_by_slot.get(slot)
        rank = (
            not row.retained,
            -row.surrogate_dps,
            _target_identity(row.target),
        )
        if current is None or rank < current[0]:
            best_by_slot[slot] = (rank, row.target)
    core = tuple(
        best_by_slot[slot][1] for slot in sorted(best_by_slot)
    )
    groups = [tuple(item) for item in combinations(core, 2)]
    if len(core) == 4:
        groups.append(core)
    if not groups:
        return ()
    if (is_cancelled is not None and is_cancelled()) or clock() >= deadline:
        raise GcsimOptimizerSetImpactError(
            "set interaction screening was cancelled or reached its deadline"
        )
    interventions = tuple(
        GcsimStatResponseIntervention(
            intervention_id=_set_interaction_id(group),
            changes=tuple(
                change
                for target in group
                for change in _set_changes(target)
            ),
        )
        for group in groups
    )
    context_sha256 = _canonical_sha256(
        {
            "schema_version": GCSIM_OPTIMIZER_SET_IMPACT_SCHEMA_VERSION,
            "kind": "pair_full_team_set_interactions",
            "engine_binding_sha256": engine_context.binding_sha256,
            "config_sha256": hashlib.sha256(
                neutral_config.encode("utf-8")
            ).hexdigest(),
            "target_sha256": stat_response_target.target_sha256,
            "response_evidence_sha256": response.evidence_sha256,
            "plan_sha256": plan.identity_sha256,
            "groups": [
                [_target_identity(target) for target in group]
                for group in groups
            ],
        }
    )
    request = GcsimStatResponseRequest(
        context_sha256=context_sha256,
        objective=stat_response_target.objective,
        iterations=plan.iterations,
        workers=plan.worker_count,
        master_seed=response.synthetic_master_seed,
        baseline_changes=response.synthetic_baseline_changes,
        interventions=interventions,
        ignore_burst_energy=True,
    )
    remaining = max(deadline - clock(), 0.001)
    result = stat_response_runner(
        engine_context=engine_context,
        prepared_config_text=neutral_config,
        target=stat_response_target,
        request=request,
        timeout_seconds=min(
            plan.candidate_timeout_seconds * (len(interventions) + 2),
            remaining,
        ),
        environment=environment,
        is_cancelled=is_cancelled,
    )
    observations = result.observation_by_id
    output = []
    for index, group in enumerate(groups, 1):
        observation = observations[_set_interaction_id(group)]
        observed = observation.paired_delta
        if observed is None:
            raise GcsimOptimizerSetImpactError(
                "set interaction observation lacks paired evidence"
            )
        individual = []
        for target in group:
            balanced = next(
                item
                for item in evidence_by_target[_target_identity(target)]
                if item.panel_id == "balanced"
            )
            individual.append(balanced.delta)
        additive_mean = sum(
            item.team_expected_dps.mean for item in individual
        )
        additive_variance = sum(
            item.team_expected_dps.standard_error**2
            for item in individual
        )
        residual_mean = observed.team_expected_dps.mean - additive_mean
        residual_se = sqrt(
            observed.team_expected_dps.standard_error**2
            + additive_variance
        )
        character_means = tuple(
            observed.character_expected_dps[character_index].mean
            - sum(
                item.character_expected_dps[character_index].mean
                for item in individual
            )
            for character_index in range(4)
        )
        character_ses = tuple(
            sqrt(
                observed.character_expected_dps[
                    character_index
                ].standard_error**2
                + sum(
                    item.character_expected_dps[
                        character_index
                    ].standard_error**2
                    for item in individual
                )
            )
            for character_index in range(4)
        )
        threshold = max(
            abs(result.baseline.summary.team_expected_dps.mean)
            * plan.relative_materiality,
            plan.absolute_materiality_dps,
        )
        lower = abs(residual_mean) - (
            plan.confidence_sigma_positive * residual_se
        )
        upper = abs(residual_mean) + (
            plan.confidence_sigma_negligible * residual_se
        )
        classification = (
            "non_additive"
            if lower > threshold
            else "additive_within_noise"
            if upper <= threshold
            else "uncertain"
        )
        output.append(
            GcsimOptimizerSetInteractionObservation(
                interaction_id=_set_interaction_id(group),
                target_identity_sha256s=tuple(
                    _target_identity(target) for target in group
                ),
                wearer_team_slots=tuple(
                    target.wearer.team_slot for target in group
                ),
                observed_team_delta=observed.team_expected_dps,
                additive_team_mean=additive_mean,
                additive_team_se=sqrt(additive_variance),
                residual_team_mean=residual_mean,
                residual_team_se=residual_se,
                character_residual_means=character_means,
                character_residual_ses=character_ses,
                classification=classification,
                request_sha256=request.request_sha256,
                seed_panel_sha256=result.seed_panel_sha256,
            )
        )
        if progress_callback is not None:
            progress_callback(
                completed_offset + index,
                total_probe_count,
            )
    return tuple(output)


def _set_interaction_id(targets):
    slots = "_".join(str(item.wearer.team_slot) for item in targets)
    digest = _canonical_sha256(
        [_target_identity(item) for item in targets]
    )[:12]
    return f"set_interaction/{slots}/{digest}"


def _classify_row(
    target: GcsimOptimizerSetImpactTarget,
    evidence: Sequence[_SetPanelEvidence],
    *,
    plan: GcsimOptimizerSetImpactPlan,
) -> GcsimOptimizerSetImpactRow:
    panels = tuple(evidence)
    if not panels:
        raise GcsimOptimizerSetImpactError(
            "set-impact target lacks panel evidence"
        )
    evaluated = []
    for panel in panels:
        team = panel.delta.team_expected_dps
        personal = panel.delta.character_expected_dps[
            target.wearer.team_slot - 1
        ]
        team_threshold = max(
            abs(panel.baseline.team_expected_dps.mean)
            * plan.relative_materiality,
            plan.absolute_materiality_dps,
        )
        personal_threshold = max(
            abs(
                panel.baseline.character_expected_dps[
                    target.wearer.team_slot - 1
                ].mean
            )
            * plan.relative_materiality,
            plan.absolute_materiality_dps,
        )
        team_lower = (
            team.mean
            - plan.confidence_sigma_positive * team.standard_error
        )
        personal_lower = (
            personal.mean
            - plan.confidence_sigma_positive * personal.standard_error
        )
        team_upper = (
            team.mean
            + plan.confidence_sigma_negligible * team.standard_error
        )
        personal_upper = (
            personal.mean
            + plan.confidence_sigma_negligible
            * personal.standard_error
        )
        evaluated.append(
            (
                panel,
                team_lower > team_threshold,
                personal_lower > personal_threshold,
                (
                    team_upper > team_threshold
                    or personal_upper > personal_threshold
                ),
                max(team_lower, personal_lower, 0.0),
            )
        )
    team_positive = any(item[1] for item in evaluated)
    personal_positive = any(item[2] for item in evaluated)
    if team_positive and personal_positive:
        classification = (
            GcsimOptimizerSetImpactClassification.PERSONAL_AND_TEAM_POSITIVE
        )
    elif team_positive:
        classification = GcsimOptimizerSetImpactClassification.TEAM_POSITIVE
    elif personal_positive:
        classification = (
            GcsimOptimizerSetImpactClassification.PERSONAL_POSITIVE
        )
    else:
        classification = (
            GcsimOptimizerSetImpactClassification.UNCERTAIN_RETAINED
            if any(item[3] for item in evaluated)
            else GcsimOptimizerSetImpactClassification.NEGLIGIBLE
        )
    best_panel, _team_positive, _personal_positive, _uncertain, surrogate = max(
        evaluated,
        key=lambda item: (
            item[4],
            item[0].panel_id == "balanced",
            item[0].panel_id,
        ),
    )
    team = best_panel.delta.team_expected_dps
    personal = best_panel.delta.character_expected_dps[
        target.wearer.team_slot - 1
    ]
    evidence_sha256 = _canonical_sha256(
        {
            "schema_version": GCSIM_OPTIMIZER_SET_IMPACT_SCHEMA_VERSION,
            "target": target.to_dict(),
            "classification": classification.value,
            "panels": [
                {
                    "panel_id": panel.panel_id,
                    "team_delta": _estimate_payload(
                        panel.delta.team_expected_dps
                    ),
                    "personal_delta": _estimate_payload(
                        panel.delta.character_expected_dps[
                            target.wearer.team_slot - 1
                        ]
                    ),
                    "request_sha256": panel.request_sha256,
                    "seed_panel_sha256": panel.seed_panel_sha256,
                }
                for panel in panels
            ],
            "plan_sha256": plan.identity_sha256,
        }
    )
    return GcsimOptimizerSetImpactRow(
        target=target,
        classification=classification,
        team_delta=team,
        personal_delta=personal,
        character_deltas=best_panel.delta.character_expected_dps,
        surrogate_dps=surrogate,
        evidence_sha256=evidence_sha256,
    )


def _baseline_with_raw_crit(
    changes: Sequence[GcsimStatResponseChange],
    *,
    response: GcsimOptimizerAnytimeResponseResult,
    raw_cr: float,
) -> tuple[GcsimStatResponseChange, ...]:
    """Create crit headroom without silently deleting investment.

    The balanced synthetic panel intentionally carries artificial raw Crit
    Rate.  Merely lowering that value makes a crit-granting package look good
    in a strictly weaker build and lets the best of two unequal-investment
    panels decide package order.  Convert every removed CR point to abstract
    five-star rolls and redistribute those rolls over the wearer's other
    measured response directions.  This panel remains diagnostic rather than
    a build recommendation, but both panels now carry the same numeric roll
    budget.
    """

    if not isinstance(response, GcsimOptimizerAnytimeResponseResult):
        raise GcsimOptimizerSetImpactError(
            "crit-headroom redistribution requires typed response evidence"
        )
    values = {
        (change.character_index, change.stat): float(change.value)
        for change in changes
    }
    modes = {
        (change.character_index, change.stat): change.mode
        for change in changes
    }
    for character_index in range(4):
        cr_key = (character_index, "cr")
        original_cr = values.get(cr_key)
        if original_cr is None:
            raise GcsimOptimizerSetImpactError(
                "synthetic set-impact baseline lacks raw Crit Rate"
            )
        removed_cr = max(original_cr - raw_cr, 0.0)
        values[cr_key] = raw_cr
        released_rolls = (
            removed_cr / GCSIM_STAT_RESPONSE_ROLL_VALUES["cr"]
        )
        if released_rolls <= 0:
            continue
        balanced = next(
            (
                profile
                for profile in response.profiles
                if profile.wearer.team_slot == character_index + 1
                and profile.profile_id == "balanced"
            ),
            None,
        )
        if balanced is None:
            raise GcsimOptimizerSetImpactError(
                "crit-headroom redistribution lacks balanced wearer profile"
            )
        axis_index = {
            axis: index
            for index, axis in enumerate(
                GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
            )
        }
        per_roll = tuple(
            (
                axis,
                balanced.stat_weights[axis_index[axis]] * roll_value,
            )
            for axis, roll_value in GCSIM_STAT_RESPONSE_ROLL_VALUES.items()
            if axis != "cr"
            and (character_index, axis) in values
            and balanced.stat_weights[axis_index[axis]] > 0
        )
        total_utility = sum(utility for _axis, utility in per_roll)
        if total_utility <= 0:
            # A rotation-irrelevant wearer still needs equal investment.  Use
            # a deterministic non-crit coordinate rather than deleting rolls.
            per_roll = (("cd", 1.0),)
            total_utility = 1.0
        for axis, utility in per_roll:
            values[(character_index, axis)] += (
                released_rolls
                * utility
                / total_utility
                * GCSIM_STAT_RESPONSE_ROLL_VALUES[axis]
            )
    return tuple(
        replace(
            change,
            mode=modes[(change.character_index, change.stat)],
            value=values[(change.character_index, change.stat)],
        )
        for change in changes
    )


def _set_changes(
    target: GcsimOptimizerSetImpactTarget,
) -> tuple[GcsimSetResponseChange, ...]:
    index = target.wearer.team_slot - 1
    if isinstance(
        target,
        GcsimOptimizerSingleTwoPieceImpactTarget,
    ):
        return (
            GcsimSetResponseChange(
                character_index=index,
                set_key=target.set_ref.gcsim_set_key,
                set_count=2,
            ),
        )
    package = target.package
    if isinstance(package, GcsimFourPieceTargetPackage):
        return (
            GcsimSetResponseChange(
                character_index=index,
                set_key=package.set_ref.gcsim_set_key,
                set_count=4,
            ),
        )
    if isinstance(package, GcsimTwoPlusTwoTargetPackage):
        return (
            GcsimSetResponseChange(
                character_index=index,
                set_key=package.set_a.gcsim_set_key,
                set_count=2,
            ),
            GcsimSetResponseChange(
                character_index=index,
                set_key=package.set_b.gcsim_set_key,
                set_count=2,
            ),
        )
    raise GcsimOptimizerSetImpactError("unsupported set-impact package kind")


def _target_identity(target: GcsimOptimizerSetImpactTarget) -> str:
    return _canonical_sha256(target.to_dict())


def _target_package_identity(
    target: GcsimOptimizerSetImpactTarget,
) -> str:
    if isinstance(
        target,
        GcsimOptimizerSingleTwoPieceImpactTarget,
    ):
        return target.identity_sha256
    return target.package.identity_sha256


def _estimate_payload(value: GcsimStatResponseEstimate) -> dict[str, object]:
    return {
        "count": value.count,
        "mean": value.mean,
        "sample_sd": value.sample_sd,
        "standard_error": value.standard_error,
    }


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
    if value != GCSIM_OPTIMIZER_SET_IMPACT_SCHEMA_VERSION:
        raise GcsimOptimizerSetImpactError(
            "unsupported set-impact schema version"
        )


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise GcsimOptimizerSetImpactError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


__all__ = [
    "GCSIM_OPTIMIZER_SET_IMPACT_PLAN_ID",
    "GCSIM_OPTIMIZER_SET_IMPACT_PLAN_VERSION",
    "GCSIM_OPTIMIZER_SET_IMPACT_SCHEMA_VERSION",
    "GcsimOptimizerSetImpactClassification",
    "GcsimOptimizerSetImpactError",
    "GcsimOptimizerSetImpactPlan",
    "GcsimOptimizerSetImpactResult",
    "GcsimOptimizerSetImpactRow",
    "GcsimOptimizerSetImpactTarget",
    "GcsimOptimizerSetInteractionObservation",
    "GcsimOptimizerSetRuntimeObservation",
    "GcsimOptimizerSingleTwoPieceImpactTarget",
    "discover_gcsim_optimizer_set_impacts",
]
