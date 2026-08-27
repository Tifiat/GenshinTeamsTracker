"""Set-aware main-stat and response discovery for optimizer Milestone 4.

This module replaces the legacy one-seed coordinate scan as the authority for
new account-optimizer work.  It has two deliberately separate responsibilities:

* prove every database-reachable five-star main-stat layout for one wearer and
  one concrete 4p or 2p+2p package without enumerating complete builds;
* plan and reduce full-rotation equal-investment response probes while keeping
  explicit layout/threshold/support/coupled-EM branches.

The evaluator remains injected.  A production adapter must run each probe
against the frozen full-team rotation; synthetic tests may use a deterministic
typed evaluator.  No artifact candidate generation or pruning is performed
here -- those belong to Milestone 5.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
from math import isfinite, sqrt
import re

from hoyolab_export.stat_normalization import STAT_MAPPINGS_BY_PROPERTY_TYPE

from .farming_profile_config import (
    GCSIM_AUTOMATIC_RESPONSE_STAT_AXES,
    GCSIM_BALANCED_REFERENCE_WEIGHTS,
    GCSIM_SUBSTAT_ROLL_VALUES,
    GcsimScreeningStatAllocation,
    allocate_gcsim_screening_substats,
    build_default_gcsim_screening_profile_bank,
)
from .farming_pipeline import (
    GcsimFarmingMaterializedProbe,
    GcsimFarmingScreeningFidelity,
    LayoutCatalog,
    materialize_gcsim_one_wearer_candidate,
)
from .farming_evaluator import (
    GcsimFarmingEvaluationRequest,
    prepare_bound_gcsim_farming_joint_evaluation,
)
from .farming_search import (
    FourPieceSetState,
    SetProfileCandidate,
    StatProfile,
    StatProfileBank,
    StatWeight,
)
from .optimizer_artifact_database import (
    GcsimOptimizerArtifactRecord,
    evaluate_gcsim_optimizer_artifact_eligibility,
)
from .optimizer_config import (
    GcsimFiveStarMainStatLayout,
    render_five_star_main_stat_line,
)
from .optimizer_oracle import (
    GcsimOptimizerOracleScore,
    GcsimOptimizerReducedOracleError,
)
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerOperation,
    GcsimOptimizerTargetPackage,
    GcsimTwoPlusTwoTargetPackage,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerTarget,
)
from .optimizer_run_input import GcsimOptimizerRunInput


GCSIM_OPTIMIZER_MAIN_RESPONSE_SCHEMA_VERSION = 1

_VARIABLE_MAIN_SLOTS = ("sands", "goblet", "circlet")
_DEFAULT_EXCHANGE_SCALES = (1, 4, 8)
_DEFAULT_INTERACTION_AXES = (
    ("em", "atk%"),
    ("em", "cr"),
    ("em", "cd"),
)


class GcsimOptimizerResponseProbeKind(str, Enum):
    REFERENCE = "reference"
    ROLL_EXCHANGE = "roll_exchange"
    UPSTREAM_OPTIMIZED_SEED = "upstream_optimized_seed"


class GcsimOptimizerResponseBranchKind(str, Enum):
    SET_ONLY = "set_only"
    DAMAGE = "damage"
    THRESHOLD = "threshold"
    SUPPORT = "support"
    MIXED = "mixed"
    COUPLED_EM = "coupled_em"
    UNUSUAL_MAIN = "unusual_main"
    UNCERTAIN = "uncertain"
    UPSTREAM_SEED = "upstream_seed"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResponsePlanningLimits:
    max_reachable_layouts: int = 420
    max_planned_probes: int = 50_000
    schema_version: int = GCSIM_OPTIMIZER_MAIN_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in (
            "max_reachable_layouts",
            "max_planned_probes",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise GcsimOptimizerReducedOracleError(
                    f"{field_name} must be a positive integer"
                )

    def to_dict(self) -> dict[str, int]:
        return {
            "schema_version": self.schema_version,
            "max_reachable_layouts": self.max_reachable_layouts,
            "max_planned_probes": self.max_planned_probes,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerReachableMainLayout:
    layout: GcsimFiveStarMainStatLayout
    supporting_artifact_ids_by_slot: tuple[tuple[str, tuple[int, ...]], ...]
    maximum_target_piece_count: int
    schema_version: int = GCSIM_OPTIMIZER_MAIN_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        _validate_layout(self.layout)
        rows = tuple(
            (slot, tuple(artifact_ids))
            for slot, artifact_ids in self.supporting_artifact_ids_by_slot
        )
        if tuple(slot for slot, _ids in rows) != GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
            raise GcsimOptimizerReducedOracleError(
                "reachable layout evidence must use canonical slot order"
            )
        for _slot, artifact_ids in rows:
            if not artifact_ids or artifact_ids != tuple(sorted(artifact_ids)):
                raise GcsimOptimizerReducedOracleError(
                    "reachable layout evidence requires sorted artifact IDs"
                )
            if len(set(artifact_ids)) != len(artifact_ids):
                raise GcsimOptimizerReducedOracleError(
                    "reachable layout evidence contains duplicate artifact IDs"
                )
        if (
            isinstance(self.maximum_target_piece_count, bool)
            or not isinstance(self.maximum_target_piece_count, int)
            or self.maximum_target_piece_count < 4
            or self.maximum_target_piece_count > 5
        ):
            raise GcsimOptimizerReducedOracleError(
                "reachable 4p layout must prove four or five target pieces"
            )
        object.__setattr__(self, "supporting_artifact_ids_by_slot", rows)

    @property
    def layout_id(self) -> str:
        return gcsim_optimizer_main_layout_id(self.layout)

    @property
    def em_main_count(self) -> int:
        return sum(
            value == "em"
            for value in (
                self.layout.sands,
                self.layout.goblet,
                self.layout.circlet,
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "layout_id": self.layout_id,
            "layout": self.layout.to_dict(),
            "supporting_artifact_ids_by_slot": {
                slot: list(artifact_ids)
                for slot, artifact_ids in self.supporting_artifact_ids_by_slot
            },
            "maximum_target_piece_count": self.maximum_target_piece_count,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerFourPieceMainDomain:
    run_input_sha256: str
    wearer: GcsimOptimizerWearerIdentity
    package: GcsimOptimizerTargetPackage
    reachable_layouts: tuple[GcsimOptimizerReachableMainLayout, ...]
    eligible_artifact_ids_by_slot: tuple[tuple[str, tuple[int, ...]], ...]
    excluded_artifact_counts: tuple[tuple[str, int], ...]
    schema_version: int = GCSIM_OPTIMIZER_MAIN_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        _require_sha256(self.run_input_sha256, "run_input_sha256")
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerReducedOracleError("domain wearer must be typed")
        if not isinstance(
            self.package,
            (GcsimFourPieceTargetPackage, GcsimTwoPlusTwoTargetPackage),
        ):
            raise GcsimOptimizerReducedOracleError(
                "main-layout domain requires a concrete complete package"
            )
        layouts = tuple(self.reachable_layouts)
        if not layouts:
            raise GcsimOptimizerReducedOracleError(
                "main-layout domain requires at least one reachable layout"
            )
        layout_ids = tuple(item.layout_id for item in layouts)
        if layout_ids != tuple(sorted(layout_ids)) or len(set(layout_ids)) != len(
            layout_ids
        ):
            raise GcsimOptimizerReducedOracleError(
                "reachable layouts must be unique and canonically ordered"
            )
        slot_rows = tuple(
            (slot, tuple(artifact_ids))
            for slot, artifact_ids in self.eligible_artifact_ids_by_slot
        )
        if tuple(slot for slot, _ids in slot_rows) != GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
            raise GcsimOptimizerReducedOracleError(
                "eligible layout pools must use canonical slot order"
            )
        for _slot, artifact_ids in slot_rows:
            if artifact_ids != tuple(sorted(artifact_ids)):
                raise GcsimOptimizerReducedOracleError(
                    "eligible layout pool IDs must be sorted"
                )
        excluded = tuple(self.excluded_artifact_counts)
        if excluded != tuple(sorted(excluded)):
            raise GcsimOptimizerReducedOracleError(
                "excluded artifact counts must be canonically ordered"
            )
        object.__setattr__(self, "reachable_layouts", layouts)
        object.__setattr__(self, "eligible_artifact_ids_by_slot", slot_rows)
        object.__setattr__(self, "excluded_artifact_counts", excluded)

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_input_sha256": self.run_input_sha256,
            "wearer": self.wearer.to_dict(),
            "package": self.package.to_dict(),
            "reachable_layouts": [
                item.to_dict() for item in self.reachable_layouts
            ],
            "eligible_artifact_ids_by_slot": {
                slot: list(artifact_ids)
                for slot, artifact_ids in self.eligible_artifact_ids_by_slot
            },
            "excluded_artifact_counts": dict(self.excluded_artifact_counts),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResponseProbe:
    domain_sha256: str
    frozen_team_context_sha256: str
    wearer: GcsimOptimizerWearerIdentity
    package: GcsimOptimizerTargetPackage
    layout: GcsimFiveStarMainStatLayout
    allocation: GcsimScreeningStatAllocation
    kind: GcsimOptimizerResponseProbeKind
    focus_axes: tuple[str, ...] = ()
    exchange_rolls: int = 0
    schema_version: int = GCSIM_OPTIMIZER_MAIN_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        _require_sha256(self.domain_sha256, "domain_sha256")
        _require_sha256(
            self.frozen_team_context_sha256,
            "frozen_team_context_sha256",
        )
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerReducedOracleError("probe wearer must be typed")
        if not isinstance(
            self.package,
            (GcsimFourPieceTargetPackage, GcsimTwoPlusTwoTargetPackage),
        ):
            raise GcsimOptimizerReducedOracleError("probe package must be typed")
        _validate_layout(self.layout)
        if not isinstance(self.allocation, GcsimScreeningStatAllocation):
            raise GcsimOptimizerReducedOracleError(
                "probe allocation must be typed"
            )
        if not isinstance(self.kind, GcsimOptimizerResponseProbeKind):
            raise GcsimOptimizerReducedOracleError("probe kind must be typed")
        axes = tuple(self.focus_axes)
        axis_order = tuple(GCSIM_SUBSTAT_ROLL_VALUES)
        if (
            len(set(axes)) != len(axes)
            or any(axis not in GCSIM_SUBSTAT_ROLL_VALUES for axis in axes)
            or axes != tuple(sorted(axes, key=axis_order.index))
        ):
            raise GcsimOptimizerReducedOracleError(
                "probe focus axes must be unique and canonically ordered"
            )
        if (
            isinstance(self.exchange_rolls, bool)
            or not isinstance(self.exchange_rolls, int)
            or self.exchange_rolls < 0
        ):
            raise GcsimOptimizerReducedOracleError(
                "exchange_rolls must be a non-negative integer"
            )
        if self.kind is GcsimOptimizerResponseProbeKind.REFERENCE and (
            axes or self.exchange_rolls
        ):
            raise GcsimOptimizerReducedOracleError(
                "reference probes cannot carry an exchange"
            )
        if self.kind is GcsimOptimizerResponseProbeKind.ROLL_EXCHANGE and (
            not axes or self.exchange_rolls <= 0
        ):
            raise GcsimOptimizerReducedOracleError(
                "roll-exchange probes require focus axes and exchanged rolls"
            )
        object.__setattr__(self, "focus_axes", axes)

    @property
    def layout_id(self) -> str:
        return gcsim_optimizer_main_layout_id(self.layout)

    @property
    def probe_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "domain_sha256": self.domain_sha256,
            "frozen_team_context_sha256": self.frozen_team_context_sha256,
            "wearer": self.wearer.to_dict(),
            "package": self.package.to_dict(),
            "layout_id": self.layout_id,
            "layout": self.layout.to_dict(),
            "allocation": _allocation_dict(self.allocation),
            "kind": self.kind.value,
            "focus_axes": list(self.focus_axes),
            "exchange_rolls": self.exchange_rolls,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResponseProbePlan:
    domain: GcsimOptimizerFourPieceMainDomain
    frozen_team_context_sha256: str
    limits: GcsimOptimizerResponsePlanningLimits
    exchange_scales: tuple[int, ...]
    interaction_axes: tuple[tuple[str, ...], ...]
    probes: tuple[GcsimOptimizerResponseProbe, ...]
    schema_version: int = GCSIM_OPTIMIZER_MAIN_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.domain, GcsimOptimizerFourPieceMainDomain):
            raise GcsimOptimizerReducedOracleError("plan domain must be typed")
        if not isinstance(self.limits, GcsimOptimizerResponsePlanningLimits):
            raise GcsimOptimizerReducedOracleError("plan limits must be typed")
        if len(self.domain.reachable_layouts) > self.limits.max_reachable_layouts:
            raise GcsimOptimizerReducedOracleError(
                "response domain exceeds max_reachable_layouts"
            )
        _require_sha256(
            self.frozen_team_context_sha256,
            "frozen_team_context_sha256",
        )
        scales = tuple(self.exchange_scales)
        if (
            not scales
            or scales != tuple(sorted(scales))
            or len(set(scales)) != len(scales)
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
                for value in scales
            )
        ):
            raise GcsimOptimizerReducedOracleError(
                "exchange scales must be unique sorted positive integers"
            )
        interactions = tuple(tuple(item) for item in self.interaction_axes)
        probes = tuple(self.probes)
        if not probes:
            raise GcsimOptimizerReducedOracleError("response plan is empty")
        if len(probes) > self.limits.max_planned_probes:
            raise GcsimOptimizerReducedOracleError(
                "response plan exceeds max_planned_probes"
            )
        probe_ids = tuple(item.probe_sha256 for item in probes)
        if len(set(probe_ids)) != len(probe_ids):
            raise GcsimOptimizerReducedOracleError(
                "response plan contains duplicate probes"
            )
        if any(
            item.domain_sha256 != self.domain.identity_sha256
            or item.frozen_team_context_sha256
            != self.frozen_team_context_sha256
            or item.wearer != self.domain.wearer
            or item.package != self.domain.package
            for item in probes
        ):
            raise GcsimOptimizerReducedOracleError(
                "response probes do not belong to their frozen plan"
            )
        reference_layout_ids = {
            item.layout_id
            for item in probes
            if item.kind is GcsimOptimizerResponseProbeKind.REFERENCE
        }
        if reference_layout_ids != {
            item.layout_id for item in self.domain.reachable_layouts
        }:
            raise GcsimOptimizerReducedOracleError(
                "every reachable layout requires one reference probe"
            )
        signatures = {item.allocation.investment_signature for item in probes}
        if len(signatures) != 1:
            raise GcsimOptimizerReducedOracleError(
                "response plan mixes equal-investment envelopes"
            )
        object.__setattr__(self, "exchange_scales", scales)
        object.__setattr__(self, "interaction_axes", interactions)
        object.__setattr__(self, "probes", probes)

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "domain": self.domain.to_dict(),
            "frozen_team_context_sha256": self.frozen_team_context_sha256,
            "limits": self.limits.to_dict(),
            "exchange_scales": list(self.exchange_scales),
            "interaction_axes": [list(item) for item in self.interaction_axes],
            "probes": [item.to_dict() for item in self.probes],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResponseMeasurement:
    score: GcsimOptimizerOracleScore
    reaction_signature: str = ""
    schema_version: int = GCSIM_OPTIMIZER_MAIN_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.score, GcsimOptimizerOracleScore):
            raise GcsimOptimizerReducedOracleError(
                "response measurement score must be typed"
            )
        if (
            not isinstance(self.reaction_signature, str)
            or self.reaction_signature != self.reaction_signature.strip()
        ):
            raise GcsimOptimizerReducedOracleError(
                "reaction_signature must be trimmed text"
            )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResponseObservation:
    probe: GcsimOptimizerResponseProbe
    measurement: GcsimOptimizerResponseMeasurement | None
    failure_reason: str = ""
    schema_version: int = GCSIM_OPTIMIZER_MAIN_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.probe, GcsimOptimizerResponseProbe):
            raise GcsimOptimizerReducedOracleError(
                "response observation probe must be typed"
            )
        if self.measurement is None:
            if not self.failure_reason:
                raise GcsimOptimizerReducedOracleError(
                    "failed response observation requires a reason"
                )
        elif not isinstance(
            self.measurement,
            GcsimOptimizerResponseMeasurement,
        ):
            raise GcsimOptimizerReducedOracleError(
                "response observation measurement must be typed"
            )
        elif self.failure_reason:
            raise GcsimOptimizerReducedOracleError(
                "successful response observation cannot carry a failure"
            )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResponseSelectionPolicy:
    confidence_sigma: float = 2.0
    practical_materiality_relative: float = 0.005
    nonlinear_slope_relative: float = 0.02
    schema_version: int = GCSIM_OPTIMIZER_MAIN_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in (
            "confidence_sigma",
            "practical_materiality_relative",
            "nonlinear_slope_relative",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isfinite(value)
                or value < 0
            ):
                raise GcsimOptimizerReducedOracleError(
                    f"{field_name} must be finite and non-negative"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "confidence_sigma": self.confidence_sigma,
            "practical_materiality_relative": (
                self.practical_materiality_relative
            ),
            "nonlinear_slope_relative": self.nonlinear_slope_relative,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResponseBranch:
    wearer: GcsimOptimizerWearerIdentity
    package: GcsimOptimizerTargetPackage
    layout: GcsimFiveStarMainStatLayout
    kind: GcsimOptimizerResponseBranchKind
    focus_axes: tuple[str, ...]
    reasons: tuple[str, ...]
    evidence_probe_sha256s: tuple[str, ...]
    schema_version: int = GCSIM_OPTIMIZER_MAIN_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerReducedOracleError("branch wearer must be typed")
        if not isinstance(
            self.package,
            (GcsimFourPieceTargetPackage, GcsimTwoPlusTwoTargetPackage),
        ):
            raise GcsimOptimizerReducedOracleError("branch package must be typed")
        _validate_layout(self.layout)
        if not isinstance(self.kind, GcsimOptimizerResponseBranchKind):
            raise GcsimOptimizerReducedOracleError("branch kind must be typed")
        axes = tuple(self.focus_axes)
        reasons = tuple(sorted(set(self.reasons)))
        evidence = tuple(sorted(set(self.evidence_probe_sha256s)))
        if not reasons or any(not item for item in reasons):
            raise GcsimOptimizerReducedOracleError(
                "retained response branch requires reasons"
            )
        if not evidence:
            raise GcsimOptimizerReducedOracleError(
                "retained response branch requires probe evidence"
            )
        for value in evidence:
            _require_sha256(value, "evidence_probe_sha256")
        object.__setattr__(self, "focus_axes", axes)
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "evidence_probe_sha256s", evidence)

    @property
    def layout_id(self) -> str:
        return gcsim_optimizer_main_layout_id(self.layout)

    @property
    def branch_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    @property
    def decision_key(self) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
        """Character-name-independent semantic decision projection."""

        return (
            self.layout_id,
            self.kind.value,
            self.focus_axes,
            self.reasons,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "wearer": self.wearer.to_dict(),
            "package": self.package.to_dict(),
            "layout_id": self.layout_id,
            "layout": self.layout.to_dict(),
            "kind": self.kind.value,
            "focus_axes": list(self.focus_axes),
            "reasons": list(self.reasons),
            "evidence_probe_sha256s": list(self.evidence_probe_sha256s),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResponseTraceRow:
    branch_sha256: str
    decision_key: tuple[str, str, tuple[str, ...], tuple[str, ...]]
    evidence_probe_sha256s: tuple[str, ...]
    schema_version: int = GCSIM_OPTIMIZER_MAIN_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        _require_sha256(self.branch_sha256, "branch_sha256")
        if not self.evidence_probe_sha256s:
            raise GcsimOptimizerReducedOracleError(
                "response trace row requires evidence"
            )
        for value in self.evidence_probe_sha256s:
            _require_sha256(value, "evidence_probe_sha256")


@dataclass(frozen=True, slots=True)
class GcsimOptimizerMainResponseResult:
    plan: GcsimOptimizerResponseProbePlan
    policy: GcsimOptimizerResponseSelectionPolicy
    observations: tuple[GcsimOptimizerResponseObservation, ...]
    branches: tuple[GcsimOptimizerResponseBranch, ...]
    trace_rows: tuple[GcsimOptimizerResponseTraceRow, ...]
    schema_version: int = GCSIM_OPTIMIZER_MAIN_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.plan, GcsimOptimizerResponseProbePlan):
            raise GcsimOptimizerReducedOracleError("result plan must be typed")
        if not isinstance(self.policy, GcsimOptimizerResponseSelectionPolicy):
            raise GcsimOptimizerReducedOracleError("result policy must be typed")
        observations = tuple(self.observations)
        branches = tuple(self.branches)
        traces = tuple(self.trace_rows)
        if tuple(item.probe.probe_sha256 for item in observations) != tuple(
            item.probe_sha256 for item in self.plan.probes
        ):
            raise GcsimOptimizerReducedOracleError(
                "response result observations do not cover the plan in order"
            )
        if not branches:
            raise GcsimOptimizerReducedOracleError(
                "response result requires retained branches"
            )
        if tuple(item.branch_sha256 for item in branches) != tuple(
            item.branch_sha256 for item in traces
        ):
            raise GcsimOptimizerReducedOracleError(
                "every retained response branch requires one trace row"
            )
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "branches", branches)
        object.__setattr__(self, "trace_rows", traces)

    @property
    def decision_signature(self) -> tuple[
        tuple[str, str, tuple[str, ...], tuple[str, ...]], ...
    ]:
        return tuple(item.decision_key for item in self.branches)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_sha256": self.plan.identity_sha256,
            "policy": self.policy.to_dict(),
            "observation_count": len(self.observations),
            "branches": [item.to_dict() for item in self.branches],
            "trace_rows": [
                {
                    "schema_version": item.schema_version,
                    "branch_sha256": item.branch_sha256,
                    "decision_key": list(item.decision_key),
                    "evidence_probe_sha256s": list(
                        item.evidence_probe_sha256s
                    ),
                }
                for item in self.trace_rows
            ],
        }


ResponseProbeEvaluator = Callable[
    [GcsimOptimizerResponseProbe],
    GcsimOptimizerResponseMeasurement,
]


def enumerate_gcsim_optimizer_reachable_four_piece_main_domain(
    run_input: GcsimOptimizerRunInput,
    *,
    target: GcsimOptimizerWearerTarget,
) -> GcsimOptimizerFourPieceMainDomain:
    """Prove every main layout reachable by one legal complete package."""

    if not isinstance(run_input, GcsimOptimizerRunInput):
        raise GcsimOptimizerReducedOracleError("run_input must be typed")
    if run_input.request.operation is not GcsimOptimizerOperation.ACCOUNT_ARTIFACTS:
        raise GcsimOptimizerReducedOracleError(
            "database reachability requires an account-artifacts request"
        )
    if not isinstance(target, GcsimOptimizerWearerTarget):
        raise GcsimOptimizerReducedOracleError("target must be typed")
    if target.wearer not in run_input.request.source_simulation.wearers:
        raise GcsimOptimizerReducedOracleError(
            "target wearer is absent from the frozen team"
        )
    if not isinstance(
        target.package,
        (GcsimFourPieceTargetPackage, GcsimTwoPlusTwoTargetPackage),
    ):
        raise GcsimOptimizerReducedOracleError(
            "reachability requires a concrete 4p or 2p+2p package"
        )
    package = target.package
    package_refs = _package_set_refs(package)
    package_uids = tuple(item.set_uid for item in package_refs)
    override = next(
        (
            item
            for item in run_input.request.four_star_overrides
            if item.wearer == target.wearer
        ),
        None,
    )
    eligible_by_slot: dict[str, list[GcsimOptimizerArtifactRecord]] = {
        slot: [] for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
    }
    excluded = Counter()
    for artifact in run_input.artifact_database.artifacts:
        eligibility = evaluate_gcsim_optimizer_artifact_eligibility(
            artifact,
            wearer=target.wearer,
            four_star_override=override,
            package_set_uids=package_uids,
        )
        if not eligibility.eligible:
            excluded[eligibility.reason] += 1
            continue
        if artifact.position_key not in eligible_by_slot:
            excluded["artifact_slot_invalid"] += 1
            continue
        eligible_by_slot[artifact.position_key].append(artifact)
    for rows in eligible_by_slot.values():
        rows.sort(key=lambda item: item.artifact_id)
    if any(not eligible_by_slot[slot] for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS):
        raise GcsimOptimizerReducedOracleError(
            "target package has an empty eligible artifact slot"
        )

    main_keys_by_slot: dict[str, tuple[str, ...]] = {}
    for slot in _VARIABLE_MAIN_SLOTS:
        keys = tuple(
            sorted(
                {
                    _artifact_main_key(artifact)
                    for artifact in eligible_by_slot[slot]
                }
            )
        )
        main_keys_by_slot[slot] = keys
    reachable: list[GcsimOptimizerReachableMainLayout] = []
    for sands in main_keys_by_slot["sands"]:
        for goblet in main_keys_by_slot["goblet"]:
            for circlet in main_keys_by_slot["circlet"]:
                layout = GcsimFiveStarMainStatLayout(
                    sands=sands,
                    goblet=goblet,
                    circlet=circlet,
                )
                try:
                    _validate_layout(layout)
                except GcsimOptimizerReducedOracleError:
                    continue
                desired = {
                    "sands": sands,
                    "goblet": goblet,
                    "circlet": circlet,
                }
                supporting: list[tuple[str, tuple[int, ...]]] = []
                maximum_target_count = 0
                feasible = True
                layout_rows: list[
                    tuple[str, tuple[GcsimOptimizerArtifactRecord, ...]]
                ] = []
                for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
                    rows = tuple(
                        artifact
                        for artifact in eligible_by_slot[slot]
                        if slot not in desired
                        or _artifact_main_key(artifact) == desired[slot]
                    )
                    if not rows:
                        feasible = False
                        break
                    supporting.append(
                        (
                            slot,
                            tuple(item.artifact_id for item in rows),
                        )
                    )
                    layout_rows.append((slot, rows))
                    if any(
                        item.set_uid in package_uids for item in rows
                    ):
                        maximum_target_count += 1
                if feasible and _layout_supports_package(
                    layout_rows,
                    package=package,
                ):
                    reachable.append(
                        GcsimOptimizerReachableMainLayout(
                            layout=layout,
                            supporting_artifact_ids_by_slot=tuple(supporting),
                            maximum_target_piece_count=maximum_target_count,
                        )
                    )
    reachable.sort(key=lambda item: item.layout_id)
    if not reachable:
        raise GcsimOptimizerReducedOracleError(
            (
                "target package has no reachable legal 4p main-stat layout"
                if isinstance(package, GcsimFourPieceTargetPackage)
                else (
                    "target package has no reachable legal "
                    "2p+2p main-stat layout"
                )
            )
        )
    return GcsimOptimizerFourPieceMainDomain(
        run_input_sha256=run_input.run_input_sha256,
        wearer=target.wearer,
        package=package,
        reachable_layouts=tuple(reachable),
        eligible_artifact_ids_by_slot=tuple(
            (
                slot,
                tuple(item.artifact_id for item in eligible_by_slot[slot]),
            )
            for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
        ),
        excluded_artifact_counts=tuple(sorted(excluded.items())),
    )


def build_gcsim_optimizer_response_probe_plan(
    domain: GcsimOptimizerFourPieceMainDomain,
    *,
    frozen_team_context_sha256: str,
    exchange_scales: Sequence[int] = _DEFAULT_EXCHANGE_SCALES,
    interaction_axes: Sequence[Sequence[str]] = _DEFAULT_INTERACTION_AXES,
    limits: GcsimOptimizerResponsePlanningLimits | None = None,
    upstream_seed_allocations: Mapping[
        str, GcsimScreeningStatAllocation
    ] | None = None,
) -> GcsimOptimizerResponseProbePlan:
    """Build exact equal-budget reference, exchange, and optional seed probes."""

    if not isinstance(domain, GcsimOptimizerFourPieceMainDomain):
        raise GcsimOptimizerReducedOracleError("domain must be typed")
    planning_limits = limits or GcsimOptimizerResponsePlanningLimits()
    if not isinstance(planning_limits, GcsimOptimizerResponsePlanningLimits):
        raise GcsimOptimizerReducedOracleError("limits must be typed")
    if len(domain.reachable_layouts) > planning_limits.max_reachable_layouts:
        raise GcsimOptimizerReducedOracleError(
            "response domain exceeds max_reachable_layouts"
        )
    _require_sha256(
        frozen_team_context_sha256,
        "frozen_team_context_sha256",
    )
    scales = tuple(sorted(set(exchange_scales)))
    if (
        not scales
        or any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            for value in scales
        )
    ):
        raise GcsimOptimizerReducedOracleError(
            "exchange_scales must contain positive integers"
        )
    axis_order = tuple(axis.key for axis in GCSIM_AUTOMATIC_RESPONSE_STAT_AXES)
    raw_interactions = tuple(tuple(values) for values in interaction_axes)
    if any(
        len(set(values)) < 2
        or any(axis not in axis_order for axis in values)
        for values in raw_interactions
    ):
        raise GcsimOptimizerReducedOracleError(
            "interaction axes require at least two known axes"
        )
    interactions = tuple(
        tuple(sorted(set(values), key=axis_order.index))
        for values in raw_interactions
    )
    interactions = tuple(dict.fromkeys(interactions))
    profile_bank = build_default_gcsim_screening_profile_bank()
    baseline_profile = profile_bank.profile("baseline")
    probes: list[GcsimOptimizerResponseProbe] = []
    domain_sha256 = domain.identity_sha256
    upstream = dict(upstream_seed_allocations or {})
    known_layout_ids = {item.layout_id for item in domain.reachable_layouts}
    unknown_seed_layouts = set(upstream).difference(known_layout_ids)
    if unknown_seed_layouts:
        raise GcsimOptimizerReducedOracleError(
            "upstream seed allocations contain unreachable layouts"
        )
    for reachable in domain.reachable_layouts:
        baseline = allocate_gcsim_screening_substats(
            reachable.layout,
            baseline_profile,
        )
        probes.append(
            GcsimOptimizerResponseProbe(
                domain_sha256=domain_sha256,
                frozen_team_context_sha256=frozen_team_context_sha256,
                wearer=domain.wearer,
                package=domain.package,
                layout=reachable.layout,
                allocation=baseline,
                kind=GcsimOptimizerResponseProbeKind.REFERENCE,
            )
        )
        focus_groups = tuple((axis,) for axis in axis_order) + interactions
        seen_allocations = {_allocation_roll_key(baseline)}
        for focus_axes in focus_groups:
            for scale in scales:
                allocation, actual_exchange = _exchange_allocation(
                    baseline,
                    focus_axes=focus_axes,
                    requested_exchange=scale,
                )
                allocation_key = _allocation_roll_key(allocation)
                if actual_exchange <= 0 or allocation_key in seen_allocations:
                    continue
                seen_allocations.add(allocation_key)
                probes.append(
                    GcsimOptimizerResponseProbe(
                        domain_sha256=domain_sha256,
                        frozen_team_context_sha256=(
                            frozen_team_context_sha256
                        ),
                        wearer=domain.wearer,
                        package=domain.package,
                        layout=reachable.layout,
                        allocation=allocation,
                        kind=GcsimOptimizerResponseProbeKind.ROLL_EXCHANGE,
                        focus_axes=focus_axes,
                        exchange_rolls=actual_exchange,
                    )
                )
        seed = upstream.get(reachable.layout_id)
        if seed is not None:
            if dict(seed.liquid_rolls_by_axis).get("er", 0) != 0:
                raise GcsimOptimizerReducedOracleError(
                    "upstream seed cannot automatically allocate liquid ER rolls"
                )
            if seed.investment_signature != baseline.investment_signature:
                raise GcsimOptimizerReducedOracleError(
                    "upstream seed changed the equal-investment envelope"
                )
            probes.append(
                GcsimOptimizerResponseProbe(
                    domain_sha256=domain_sha256,
                    frozen_team_context_sha256=frozen_team_context_sha256,
                    wearer=domain.wearer,
                    package=domain.package,
                    layout=reachable.layout,
                    allocation=seed,
                    kind=(
                        GcsimOptimizerResponseProbeKind.UPSTREAM_OPTIMIZED_SEED
                    ),
                )
            )
    return GcsimOptimizerResponseProbePlan(
        domain=domain,
        frozen_team_context_sha256=frozen_team_context_sha256,
        limits=planning_limits,
        exchange_scales=scales,
        interaction_axes=interactions,
        probes=tuple(probes),
    )


def build_gcsim_optimizer_reference_probes(
    domain: GcsimOptimizerFourPieceMainDomain,
    *,
    frozen_team_context_sha256: str,
    limits: GcsimOptimizerResponsePlanningLimits | None = None,
) -> tuple[GcsimOptimizerResponseProbe, ...]:
    """Build only the equal-investment reference row for every layout.

    Account response screening needs complete reference coverage before it can
    choose the smaller layout set that receives roll-exchange probes.  Building
    the complete exchange plan merely to discard those probes makes that
    screening step needlessly quadratic in serialization and hashing work.
    """

    if not isinstance(domain, GcsimOptimizerFourPieceMainDomain):
        raise GcsimOptimizerReducedOracleError("domain must be typed")
    planning_limits = limits or GcsimOptimizerResponsePlanningLimits()
    if not isinstance(planning_limits, GcsimOptimizerResponsePlanningLimits):
        raise GcsimOptimizerReducedOracleError("limits must be typed")
    if len(domain.reachable_layouts) > planning_limits.max_reachable_layouts:
        raise GcsimOptimizerReducedOracleError(
            "response domain exceeds max_reachable_layouts"
        )
    _require_sha256(
        frozen_team_context_sha256,
        "frozen_team_context_sha256",
    )
    baseline_profile = build_default_gcsim_screening_profile_bank().profile(
        "baseline"
    )
    domain_sha256 = domain.identity_sha256
    return tuple(
        GcsimOptimizerResponseProbe(
            domain_sha256=domain_sha256,
            frozen_team_context_sha256=frozen_team_context_sha256,
            wearer=domain.wearer,
            package=domain.package,
            layout=reachable.layout,
            allocation=allocate_gcsim_screening_substats(
                reachable.layout,
                baseline_profile,
            ),
            kind=GcsimOptimizerResponseProbeKind.REFERENCE,
        )
        for reachable in domain.reachable_layouts
    )


def run_gcsim_optimizer_main_response_discovery(
    plan: GcsimOptimizerResponseProbePlan,
    *,
    evaluator: ResponseProbeEvaluator,
    policy: GcsimOptimizerResponseSelectionPolicy | None = None,
) -> GcsimOptimizerMainResponseResult:
    """Evaluate the complete plan and retain auditable piecewise branches."""

    if not isinstance(plan, GcsimOptimizerResponseProbePlan):
        raise GcsimOptimizerReducedOracleError("plan must be typed")
    if not callable(evaluator):
        raise GcsimOptimizerReducedOracleError("evaluator must be callable")
    selection_policy = policy or GcsimOptimizerResponseSelectionPolicy()
    if not isinstance(
        selection_policy,
        GcsimOptimizerResponseSelectionPolicy,
    ):
        raise GcsimOptimizerReducedOracleError("policy must be typed")
    batch_evaluator = getattr(evaluator, "evaluate_many", None)
    if callable(batch_evaluator):
        observations = list(batch_evaluator(plan.probes))
        if len(observations) != len(plan.probes) or any(
            not isinstance(item, GcsimOptimizerResponseObservation)
            for item in observations
        ):
            raise GcsimOptimizerReducedOracleError(
                "batch response evaluator must return one typed observation per probe"
            )
        return analyze_gcsim_optimizer_response_observations(
            plan,
            observations,
            policy=selection_policy,
        )

    observations: list[GcsimOptimizerResponseObservation] = []
    objective_name = ""
    for probe in plan.probes:
        try:
            measurement = evaluator(probe)
            if not isinstance(measurement, GcsimOptimizerResponseMeasurement):
                raise TypeError("evaluator returned a non-typed measurement")
            if objective_name and measurement.score.objective_name != objective_name:
                raise GcsimOptimizerReducedOracleError(
                    "response measurements must share one objective"
                )
            objective_name = measurement.score.objective_name
            observations.append(
                GcsimOptimizerResponseObservation(
                    probe=probe,
                    measurement=measurement,
                )
            )
        except GcsimOptimizerReducedOracleError:
            raise
        except Exception as exc:
            observations.append(
                GcsimOptimizerResponseObservation(
                    probe=probe,
                    measurement=None,
                    failure_reason=f"{type(exc).__name__}: {exc}",
                )
            )
    return analyze_gcsim_optimizer_response_observations(
        plan,
        observations,
        policy=selection_policy,
    )


def analyze_gcsim_optimizer_response_observations(
    plan: GcsimOptimizerResponseProbePlan,
    observations: Sequence[GcsimOptimizerResponseObservation],
    *,
    policy: GcsimOptimizerResponseSelectionPolicy | None = None,
) -> GcsimOptimizerMainResponseResult:
    if not isinstance(plan, GcsimOptimizerResponseProbePlan):
        raise GcsimOptimizerReducedOracleError("plan must be typed")
    selection_policy = policy or GcsimOptimizerResponseSelectionPolicy()
    rows = tuple(observations)
    if tuple(item.probe.probe_sha256 for item in rows) != tuple(
        item.probe_sha256 for item in plan.probes
    ):
        raise GcsimOptimizerReducedOracleError(
            "observations must cover the response plan exactly in order"
        )
    observation_by_probe = {
        item.probe.probe_sha256: item for item in rows
    }
    references = {
        item.probe.layout_id: item
        for item in rows
        if item.probe.kind is GcsimOptimizerResponseProbeKind.REFERENCE
    }
    reachable_by_id = {
        item.layout_id: item for item in plan.domain.reachable_layouts
    }
    branches: dict[
        tuple[str, GcsimOptimizerResponseBranchKind, tuple[str, ...]],
        tuple[set[str], set[str]],
    ] = {}

    def retain(
        layout_id: str,
        kind: GcsimOptimizerResponseBranchKind,
        *,
        focus_axes: tuple[str, ...] = (),
        reason: str,
        evidence: Sequence[str],
    ) -> None:
        key = (layout_id, kind, focus_axes)
        reasons, probe_ids = branches.setdefault(key, (set(), set()))
        reasons.add(reason)
        probe_ids.update(evidence)

    passed_references = tuple(
        item
        for item in references.values()
        if item.measurement is not None
    )
    if passed_references:
        best_reference = min(passed_references, key=_observation_rank)
        retain(
            best_reference.probe.layout_id,
            GcsimOptimizerResponseBranchKind.SET_ONLY,
            reason="package_reference_leader",
            evidence=(best_reference.probe.probe_sha256,),
        )
    for layout_id, reference in references.items():
        if reference.measurement is None:
            retain(
                layout_id,
                GcsimOptimizerResponseBranchKind.UNCERTAIN,
                reason="reference_probe_failed",
                evidence=(reference.probe.probe_sha256,),
            )

    region_rows: dict[str, list[GcsimOptimizerResponseObservation]] = {}
    for reference in passed_references:
        for region in _layout_regions(reference.probe.layout):
            region_rows.setdefault(region, []).append(reference)
    region_kind = {
        "ordinary": GcsimOptimizerResponseBranchKind.DAMAGE,
        "crit": GcsimOptimizerResponseBranchKind.THRESHOLD,
        "hp": GcsimOptimizerResponseBranchKind.SUPPORT,
        "heal": GcsimOptimizerResponseBranchKind.SUPPORT,
        "def": GcsimOptimizerResponseBranchKind.SUPPORT,
        "em": GcsimOptimizerResponseBranchKind.COUPLED_EM,
        "unusual": GcsimOptimizerResponseBranchKind.UNUSUAL_MAIN,
    }
    for region, region_observations in sorted(region_rows.items()):
        best = min(region_observations, key=_observation_rank)
        retain(
            best.probe.layout_id,
            region_kind[region],
            reason=f"best_reachable_{region}_main_region",
            evidence=(best.probe.probe_sha256,),
        )

    em_trigger_evidence: set[str] = set()
    for layout_id, reference in references.items():
        exchange_rows = tuple(
            item
            for item in rows
            if item.probe.layout_id == layout_id
            and item.probe.kind
            is GcsimOptimizerResponseProbeKind.ROLL_EXCHANGE
        )
        by_axes: dict[
            tuple[str, ...], list[GcsimOptimizerResponseObservation]
        ] = {}
        for item in exchange_rows:
            by_axes.setdefault(item.probe.focus_axes, []).append(item)
        for axes, axis_rows in by_axes.items():
            passed = tuple(
                item for item in axis_rows if item.measurement is not None
            )
            failed = tuple(
                item for item in axis_rows if item.measurement is None
            )
            evidence = tuple(
                item.probe.probe_sha256 for item in (reference, *axis_rows)
            )
            if failed or reference.measurement is None:
                retain(
                    layout_id,
                    GcsimOptimizerResponseBranchKind.UNCERTAIN,
                    focus_axes=axes,
                    reason="response_probe_unresolved",
                    evidence=evidence,
                )
                if "em" in axes:
                    em_trigger_evidence.update(evidence)
                continue
            uncertainty_unknown = (
                reference.measurement.score.standard_error is None
                or any(
                    item.measurement.score.standard_error is None
                    for item in passed
                )
            )
            if uncertainty_unknown:
                retain(
                    layout_id,
                    GcsimOptimizerResponseBranchKind.UNCERTAIN,
                    focus_axes=axes,
                    reason="response_uncertainty_unknown",
                    evidence=evidence,
                )
                if "em" in axes:
                    em_trigger_evidence.update(evidence)
            material = any(
                _material_change(reference, item, selection_policy)
                for item in passed
            )
            reaction_changed = any(
                item.measurement.reaction_signature
                != reference.measurement.reaction_signature
                for item in passed
            )
            reaction_unknown = (
                not reference.measurement.reaction_signature
                or any(
                    not item.measurement.reaction_signature
                    for item in passed
                )
            )
            if reaction_unknown and "em" in axes:
                retain(
                    layout_id,
                    GcsimOptimizerResponseBranchKind.UNCERTAIN,
                    focus_axes=axes,
                    reason="reaction_ownership_unavailable",
                    evidence=evidence,
                )
                em_trigger_evidence.update(evidence)
            nonlinear = _nonlinear_response(
                reference,
                passed,
                selection_policy,
            )
            if not (material or reaction_changed or nonlinear):
                continue
            kind = _response_kind_for_axes(axes)
            reasons = []
            if material:
                reasons.append("material_roll_exchange")
            if reaction_changed:
                reasons.append("reaction_ownership_changed")
            if nonlinear:
                reasons.append("nonlinear_roll_response")
            for reason in reasons:
                retain(
                    layout_id,
                    kind,
                    focus_axes=axes,
                    reason=reason,
                    evidence=evidence,
                )
            if "em" in axes:
                em_trigger_evidence.update(evidence)

    em_sensitive_layouts = tuple(
        item
        for item in plan.domain.reachable_layouts
        if item.em_main_count >= 1
    )
    em_heavy = tuple(
        item
        for item in em_sensitive_layouts
        if item.em_main_count >= 2
    )
    isolated_em = tuple(
        reference
        for reference in passed_references
        if reachable_by_id[reference.probe.layout_id].em_main_count == 1
    )
    passed_em_heavy = tuple(
        references[item.layout_id]
        for item in em_heavy
        if references[item.layout_id].measurement is not None
    )
    if passed_em_heavy and isolated_em:
        best_heavy = min(passed_em_heavy, key=_observation_rank)
        best_isolated = min(isolated_em, key=_observation_rank)
        if _positive_material_change(
            best_isolated,
            best_heavy,
            selection_policy,
        ):
            evidence = (
                best_isolated.probe.probe_sha256,
                best_heavy.probe.probe_sha256,
            )
            em_trigger_evidence.update(evidence)
            retain(
                best_heavy.probe.layout_id,
                GcsimOptimizerResponseBranchKind.COUPLED_EM,
                focus_axes=("em",),
                reason="joint_em_beats_isolated_em",
                evidence=evidence,
            )
    if em_trigger_evidence:
        for reachable in em_sensitive_layouts:
            reference = references[reachable.layout_id]
            retain(
                reachable.layout_id,
                GcsimOptimizerResponseBranchKind.COUPLED_EM,
                focus_axes=("em",),
                reason="em_safeguard_forced_reachable_mixed_or_joint_layout",
                evidence=(
                    reference.probe.probe_sha256,
                    *sorted(em_trigger_evidence),
                ),
            )

    for item in rows:
        if (
            item.probe.kind
            is GcsimOptimizerResponseProbeKind.UPSTREAM_OPTIMIZED_SEED
        ):
            retain(
                item.probe.layout_id,
                (
                    GcsimOptimizerResponseBranchKind.UPSTREAM_SEED
                    if item.measurement is not None
                    else GcsimOptimizerResponseBranchKind.UNCERTAIN
                ),
                reason=(
                    "upstream_seed_observed"
                    if item.measurement is not None
                    else "upstream_seed_unresolved"
                ),
                evidence=(item.probe.probe_sha256,),
            )

    retained: list[GcsimOptimizerResponseBranch] = []
    for (layout_id, kind, focus_axes), (reasons, evidence) in sorted(
        branches.items(),
        key=lambda item: (
            item[0][0],
            item[0][1].value,
            item[0][2],
        ),
    ):
        retained.append(
            GcsimOptimizerResponseBranch(
                wearer=plan.domain.wearer,
                package=plan.domain.package,
                layout=reachable_by_id[layout_id].layout,
                kind=kind,
                focus_axes=focus_axes,
                reasons=tuple(reasons),
                evidence_probe_sha256s=tuple(evidence),
            )
        )
    retained_tuple = tuple(retained)
    traces = tuple(
        GcsimOptimizerResponseTraceRow(
            branch_sha256=item.branch_sha256,
            decision_key=item.decision_key,
            evidence_probe_sha256s=item.evidence_probe_sha256s,
        )
        for item in retained_tuple
    )
    return GcsimOptimizerMainResponseResult(
        plan=plan,
        policy=selection_policy,
        observations=rows,
        branches=retained_tuple,
        trace_rows=traces,
    )


def gcsim_optimizer_main_layout_id(
    layout: GcsimFiveStarMainStatLayout,
) -> str:
    _validate_layout(layout)

    def token(value: str) -> str:
        return value.replace("%", "pct")

    return (
        f"main/{token(layout.sands)}-"
        f"{token(layout.goblet)}-{token(layout.circlet)}"
    )


def build_gcsim_optimizer_response_probe_stat_profile(
    probe: GcsimOptimizerResponseProbe,
) -> StatProfile:
    """Project an exact M4 allocation into the existing trusted renderer.

    The renderer accepts normalized profile weights.  Using the exact integer
    liquid-roll shares reproduces the probe allocation byte-for-byte under the
    same frozen envelope; the explicit round-trip check fails closed if that
    invariant ever changes.
    """

    if not isinstance(probe, GcsimOptimizerResponseProbe):
        raise GcsimOptimizerReducedOracleError("probe must be typed")
    total = probe.allocation.total_liquid_substats
    if total <= 0:
        raise GcsimOptimizerReducedOracleError(
            "response probe requires a positive liquid-roll budget"
        )
    profile = StatProfile(
        profile_id=f"m4/exact/{probe.probe_sha256[:24]}",
        kind="m4_exact_allocation",
        weights=tuple(
            StatWeight(
                axis_key=item.axis_key,
                weight=item.liquid_rolls / total,
            )
            for item in probe.allocation.rolls
            if item.liquid_rolls > 0
        ),
        focus_axes=probe.focus_axes,
    )
    reproduced = allocate_gcsim_screening_substats(
        probe.layout,
        profile,
        four_star_piece_count=probe.allocation.four_star_piece_count,
        total_liquid_substats=probe.allocation.total_liquid_substats,
        fixed_substats_count=probe.allocation.fixed_substats_count,
    )
    if _allocation_roll_key(reproduced) != _allocation_roll_key(
        probe.allocation
    ):
        raise GcsimOptimizerReducedOracleError(
            "existing screening renderer cannot reproduce the exact M4 probe"
        )
    return profile


def materialize_gcsim_optimizer_response_probe(
    prepared_config_text: str,
    *,
    probe: GcsimOptimizerResponseProbe,
    frozen_baseline_states: Sequence[SetProfileCandidate],
    wearer_ids: Sequence[str],
    layout_catalog: LayoutCatalog,
    profile_bank: StatProfileBank,
    engine_context: GcsimOptimizerEngineContext,
    fidelity: GcsimFarmingScreeningFidelity,
    reference_weights: Sequence[StatWeight] = (
        GCSIM_BALANCED_REFERENCE_WEIGHTS
    ),
    environment: Mapping[str, str] | None = None,
    environment_is_frozen: bool = False,
) -> GcsimFarmingMaterializedProbe:
    """Materialize one exact M4 probe into a frozen full-team GCSIM config."""

    if not isinstance(probe, GcsimOptimizerResponseProbe):
        raise GcsimOptimizerReducedOracleError("probe must be typed")
    if not isinstance(profile_bank, StatProfileBank):
        raise GcsimOptimizerReducedOracleError("profile_bank must be typed")
    exact_profile = build_gcsim_optimizer_response_probe_stat_profile(probe)
    if any(
        item.profile_id == exact_profile.profile_id
        for item in profile_bank.profiles
    ):
        raise GcsimOptimizerReducedOracleError(
            "M4 exact profile identity collides with the supplied profile bank"
        )
    combined_bank = StatProfileBank(
        axes=profile_bank.axes,
        profiles=(*profile_bank.profiles, exact_profile),
    )
    canonical_wearers = tuple(wearer_ids)
    target_key = probe.wearer.gcsim_character_key
    if target_key not in canonical_wearers:
        raise GcsimOptimizerReducedOracleError(
            "probe wearer is absent from the frozen team"
        )
    layouts = {
        wearer: dict(wearer_layouts)
        for wearer, wearer_layouts in layout_catalog.items()
    }
    target_layouts = layouts.setdefault(target_key, {})
    layout_id = probe.layout_id
    existing_layout = target_layouts.get(layout_id)
    if existing_layout is not None and existing_layout != probe.layout:
        raise GcsimOptimizerReducedOracleError(
            "probe layout identity collides with another layout"
        )
    target_layouts[layout_id] = probe.layout
    candidate = SetProfileCandidate(
        state=FourPieceSetState(
            wearer_id=target_key,
            set_key=probe.package.set_ref.gcsim_set_key,
            main_stat_layout_id=layout_id,
        ),
        profile_id=exact_profile.profile_id,
    )
    return materialize_gcsim_one_wearer_candidate(
        prepared_config_text,
        candidate=candidate,
        frozen_baseline_states=frozen_baseline_states,
        wearer_ids=canonical_wearers,
        layout_catalog=layouts,
        profile_bank=combined_bank,
        engine_context=engine_context,
        fidelity=fidelity,
        reference_weights=reference_weights,
        environment=environment,
        environment_is_frozen=environment_is_frozen,
    )


def build_gcsim_optimizer_response_probe_evaluator_request(
    prepared_config_text: str,
    *,
    probe: GcsimOptimizerResponseProbe,
    frozen_baseline_states: Sequence[SetProfileCandidate],
    wearer_ids: Sequence[str],
    layout_catalog: LayoutCatalog,
    profile_bank: StatProfileBank,
    engine_context: GcsimOptimizerEngineContext,
    fidelity: GcsimFarmingScreeningFidelity,
    timeout_seconds: float,
    reference_weights: Sequence[StatWeight] = (
        GCSIM_BALANCED_REFERENCE_WEIGHTS
    ),
    environment: Mapping[str, str] | None = None,
) -> GcsimFarmingEvaluationRequest:
    """Build a bound ordinary request for either complete package shape."""

    if isinstance(probe.package, GcsimFourPieceTargetPackage):
        materialized = materialize_gcsim_optimizer_response_probe(
            prepared_config_text,
            probe=probe,
            frozen_baseline_states=frozen_baseline_states,
            wearer_ids=wearer_ids,
            layout_catalog=layout_catalog,
            profile_bank=profile_bank,
            engine_context=engine_context,
            fidelity=fidelity,
            reference_weights=reference_weights,
            environment=environment,
        )
        return materialized.build_evaluator_request(
            engine_context=engine_context,
            timeout_seconds=timeout_seconds,
            environment=dict(materialized.environment_items),
        )
    package = probe.package
    base_capability = next(
        (
            capability
            for capability in engine_context.catalog.sets
            if capability.optimizer_four_piece_ready
            and capability.max_rarity == 5
        ),
        None,
    )
    if base_capability is None:
        raise GcsimOptimizerReducedOracleError(
            "2p+2p response rendering requires one modeled five-star 4p "
            "carrier set in the pinned engine"
        )
    base_ref = replace(
        package.set_a,
        gcsim_set_key=base_capability.key,
        set_parameters={},
    )
    base_probe = replace(
        probe,
        package=GcsimFourPieceTargetPackage(base_ref),
    )
    materialized = materialize_gcsim_optimizer_response_probe(
        prepared_config_text,
        probe=base_probe,
        frozen_baseline_states=frozen_baseline_states,
        wearer_ids=wearer_ids,
        layout_catalog=layout_catalog,
        profile_bank=profile_bank,
        engine_context=engine_context,
        fidelity=fidelity,
        reference_weights=reference_weights,
        environment=environment,
    )
    pair_config = _replace_theoretical_four_piece_with_two_plus_two(
        materialized.config_text,
        wearer=probe.wearer.gcsim_character_key,
        base_set_key=base_capability.key,
        package=package,
    )
    context_sha256 = _canonical_sha256(
        {
            "base_evaluation_context_sha256": (
                materialized.evaluation_context_sha256
            ),
            "target_package": package.to_dict(),
            "probe_sha256": probe.probe_sha256,
        }
    )
    return prepare_bound_gcsim_farming_joint_evaluation(
        engine_context=engine_context,
        candidate_keys=materialized.candidate_keys,
        config_text=pair_config,
        comparison_context_sha256=context_sha256,
        investment_signature=materialized.investment_signature,
        worker_count=fidelity.worker_count,
        timeout_seconds=timeout_seconds,
        environment=dict(materialized.environment_items),
        environment_is_frozen=True,
    )


def _replace_theoretical_four_piece_with_two_plus_two(
    config_text,
    *,
    wearer,
    base_set_key,
    package,
):
    pattern = re.compile(
        rf'(?m)^[ \t]*{re.escape(wearer)}[ \t]+add[ \t]+set="'
        rf'{re.escape(base_set_key)}"[ \t]+count=4'
        rf'(?:[ \t]+\+params=\[[^\]\r\n]*\])?;[ \t]*(?P<ending>\r?)$'
    )
    matches = tuple(pattern.finditer(config_text))
    if len(matches) != 1:
        raise GcsimOptimizerReducedOracleError(
            "2p+2p response base config lacks one canonical 4p set row"
        )
    ending = matches[0].group("ending")
    lines = []
    for set_ref in (package.set_a, package.set_b):
        parameters = ""
        if set_ref.set_parameters:
            rendered = ",".join(
                f"{key}={set_ref.set_parameters[key]}"
                for key in sorted(set_ref.set_parameters)
            )
            parameters = f" +params=[{rendered}]"
        lines.append(
            f'{wearer} add set="{set_ref.gcsim_set_key}" '
            f"count=2{parameters};"
        )
    replacement = f"{lines[0]}{ending}\n{lines[1]}{ending}"
    return pattern.sub(replacement, config_text, count=1)


def _artifact_main_key(artifact: GcsimOptimizerArtifactRecord) -> str:
    mapping = (
        None
        if artifact.main_property_type is None
        else STAT_MAPPINGS_BY_PROPERTY_TYPE.get(artifact.main_property_type)
    )
    if mapping is None or not mapping.gcsim_key:
        raise GcsimOptimizerReducedOracleError(
            f"eligible artifact {artifact.artifact_id} has no main-stat mapping"
        )
    return mapping.gcsim_key


def _package_set_refs(package):
    if isinstance(package, GcsimFourPieceTargetPackage):
        return (package.set_ref,)
    if isinstance(package, GcsimTwoPlusTwoTargetPackage):
        return (package.set_a, package.set_b)
    raise GcsimOptimizerReducedOracleError(
        "unsupported account target package"
    )


def _layout_supports_package(rows_by_slot, *, package):
    refs = _package_set_refs(package)
    requirements = (
        (4,)
        if isinstance(package, GcsimFourPieceTargetPackage)
        else (2, 2)
    )
    index_by_uid = {
        item.set_uid: index for index, item in enumerate(refs)
    }
    states = {tuple(0 for _unused in requirements)}
    for _slot, rows in rows_by_slot:
        categories = {
            index_by_uid.get(artifact.set_uid)
            for artifact in rows
        }
        next_states = set()
        for state in states:
            for category in categories:
                counts = list(state)
                if category is not None:
                    counts[category] = min(
                        counts[category] + 1,
                        requirements[category],
                    )
                next_states.add(tuple(counts))
        states = next_states
    return requirements in states


def _exchange_allocation(
    baseline: GcsimScreeningStatAllocation,
    *,
    focus_axes: Sequence[str],
    requested_exchange: int,
) -> tuple[GcsimScreeningStatAllocation, int]:
    axes = tuple(focus_axes)
    axis_order = tuple(axis.key for axis in GCSIM_AUTOMATIC_RESPONSE_STAT_AXES)
    if (
        not axes
        or len(set(axes)) != len(axes)
        or any(axis not in axis_order for axis in axes)
    ):
        raise GcsimOptimizerReducedOracleError(
            "roll exchange requires known unique focus axes"
        )
    if (
        isinstance(requested_exchange, bool)
        or not isinstance(requested_exchange, int)
        or requested_exchange <= 0
    ):
        raise GcsimOptimizerReducedOracleError(
            "requested exchange must be a positive integer"
        )
    counts = {
        item.axis_key: item.liquid_rolls for item in baseline.rolls
    }
    caps = {item.axis_key: item.liquid_cap for item in baseline.rolls}
    exchanged = 0
    additions = {axis: 0 for axis in axes}
    for _ in range(requested_exchange):
        receivers = tuple(axis for axis in axes if counts[axis] < caps[axis])
        donors = tuple(
            axis
            for axis in axis_order
            if axis not in axes and counts[axis] > 0
        )
        if not receivers or not donors:
            break
        receiver = min(
            receivers,
            key=lambda axis: (additions[axis], axis_order.index(axis)),
        )
        donor = min(
            donors,
            key=lambda axis: (-counts[axis], axis_order.index(axis)),
        )
        counts[donor] -= 1
        counts[receiver] += 1
        additions[receiver] += 1
        exchanged += 1
    rolls = tuple(
        replace(item, liquid_rolls=counts[item.axis_key])
        for item in baseline.rolls
    )
    focus_token = "-".join(axis.replace("%", "pct") for axis in axes)
    return (
        GcsimScreeningStatAllocation(
            profile_id=f"m4/exchange/{focus_token}/{exchanged}",
            four_star_piece_count=baseline.four_star_piece_count,
            fixed_substats_count=baseline.fixed_substats_count,
            total_liquid_substats=baseline.total_liquid_substats,
            rarity_modifier=baseline.rarity_modifier,
            rolls=rolls,
            investment_signature=baseline.investment_signature,
        ),
        exchanged,
    )


def _layout_regions(
    layout: GcsimFiveStarMainStatLayout,
) -> tuple[str, ...]:
    values = (layout.sands, layout.goblet, layout.circlet)
    regions: set[str] = set()
    if layout.circlet in {"cr", "cd"}:
        regions.add("crit")
    if values.count("hp%") >= 2:
        regions.add("hp")
    if layout.circlet == "heal":
        regions.add("heal")
    if values.count("def%") >= 2:
        regions.add("def")
    if values.count("em") >= 2:
        regions.add("em")
    if not regions.intersection({"hp", "heal", "def", "em"}):
        regions.add("ordinary")
    if (
        layout.sands not in {"atk%", "er"}
        or layout.goblet
        not in {
            "atk%",
            "phys%",
            "pyro%",
            "hydro%",
            "electro%",
            "cryo%",
            "anemo%",
            "geo%",
            "dendro%",
        }
        or layout.circlet not in {"cr", "cd"}
    ):
        regions.add("unusual")
    return tuple(sorted(regions))


def _response_kind_for_axes(
    axes: tuple[str, ...],
) -> GcsimOptimizerResponseBranchKind:
    if "em" in axes:
        return GcsimOptimizerResponseBranchKind.COUPLED_EM
    if set(axes).intersection({"hp%", "hp", "def%", "def"}):
        return GcsimOptimizerResponseBranchKind.SUPPORT
    if len(axes) > 1:
        return GcsimOptimizerResponseBranchKind.MIXED
    return GcsimOptimizerResponseBranchKind.DAMAGE


def _material_change(
    baseline: GcsimOptimizerResponseObservation,
    candidate: GcsimOptimizerResponseObservation,
    policy: GcsimOptimizerResponseSelectionPolicy,
) -> bool:
    return _change_exceeds_margin(
        baseline,
        candidate,
        policy,
        positive_only=False,
    )


def _positive_material_change(
    baseline: GcsimOptimizerResponseObservation,
    candidate: GcsimOptimizerResponseObservation,
    policy: GcsimOptimizerResponseSelectionPolicy,
) -> bool:
    return _change_exceeds_margin(
        baseline,
        candidate,
        policy,
        positive_only=True,
    )


def _change_exceeds_margin(
    baseline: GcsimOptimizerResponseObservation,
    candidate: GcsimOptimizerResponseObservation,
    policy: GcsimOptimizerResponseSelectionPolicy,
    *,
    positive_only: bool,
) -> bool:
    if baseline.measurement is None or candidate.measurement is None:
        return False
    before = baseline.measurement.score
    after = candidate.measurement.score
    delta = after.objective_value - before.objective_value
    if positive_only and delta <= 0:
        return False
    combined_error = (
        None
        if before.standard_error is None or after.standard_error is None
        else sqrt(before.standard_error**2 + after.standard_error**2)
    )
    uncertainty = (
        float("inf")
        if combined_error is None
        else policy.confidence_sigma * combined_error
    )
    practical = (
        abs(before.objective_value)
        * policy.practical_materiality_relative
    )
    threshold = max(uncertainty, practical)
    return (delta if positive_only else abs(delta)) > threshold


def _nonlinear_response(
    baseline: GcsimOptimizerResponseObservation,
    candidates: Sequence[GcsimOptimizerResponseObservation],
    policy: GcsimOptimizerResponseSelectionPolicy,
) -> bool:
    if baseline.measurement is None:
        return False
    slopes = tuple(
        (
            item.measurement.score.objective_value
            - baseline.measurement.score.objective_value
        )
        / item.probe.exchange_rolls
        for item in candidates
        if item.measurement is not None and item.probe.exchange_rolls > 0
    )
    if len(slopes) < 2:
        return False
    spread = max(slopes) - min(slopes)
    scale = max(
        abs(baseline.measurement.score.objective_value),
        1.0,
    )
    return spread > scale * policy.nonlinear_slope_relative


def _observation_rank(
    observation: GcsimOptimizerResponseObservation,
) -> tuple[float, float, str]:
    if observation.measurement is None:
        return (float("inf"), float("inf"), observation.probe.layout_id)
    score = observation.measurement.score
    return (
        -score.objective_value,
        (
            float("inf")
            if score.standard_error is None
            else score.standard_error
        ),
        observation.probe.layout_id,
    )


def _validate_layout(layout: GcsimFiveStarMainStatLayout) -> None:
    if not isinstance(layout, GcsimFiveStarMainStatLayout):
        raise GcsimOptimizerReducedOracleError(
            "main-stat layout must be typed"
        )
    try:
        render_five_star_main_stat_line("oracle", layout)
    except ValueError as exc:
        raise GcsimOptimizerReducedOracleError(
            f"illegal main-stat layout: {exc}"
        ) from exc


def _allocation_roll_key(
    allocation: GcsimScreeningStatAllocation,
) -> tuple[int, ...]:
    return tuple(item.liquid_rolls for item in allocation.rolls)


def _allocation_dict(
    allocation: GcsimScreeningStatAllocation,
) -> dict[str, object]:
    return {
        "profile_id": allocation.profile_id,
        "four_star_piece_count": allocation.four_star_piece_count,
        "fixed_substats_count": allocation.fixed_substats_count,
        "total_liquid_substats": allocation.total_liquid_substats,
        "rarity_modifier": allocation.rarity_modifier,
        "investment_signature": allocation.investment_signature,
        "rolls": [
            {
                "axis_key": item.axis_key,
                "fixed_rolls": item.fixed_rolls,
                "liquid_rolls": item.liquid_rolls,
                "liquid_cap": item.liquid_cap,
                "roll_value": item.roll_value,
                "rarity_modifier": item.rarity_modifier,
            }
            for item in allocation.rolls
        ],
    }


def _require_schema(value: object) -> None:
    if value != GCSIM_OPTIMIZER_MAIN_RESPONSE_SCHEMA_VERSION:
        raise GcsimOptimizerReducedOracleError(
            "unsupported optimizer main-response schema"
        )


def _require_sha256(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GcsimOptimizerReducedOracleError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "GCSIM_OPTIMIZER_MAIN_RESPONSE_SCHEMA_VERSION",
    "GcsimOptimizerFourPieceMainDomain",
    "GcsimOptimizerMainResponseResult",
    "GcsimOptimizerReachableMainLayout",
    "GcsimOptimizerResponseBranch",
    "GcsimOptimizerResponseBranchKind",
    "GcsimOptimizerResponseMeasurement",
    "GcsimOptimizerResponseObservation",
    "GcsimOptimizerResponseProbe",
    "GcsimOptimizerResponseProbeKind",
    "GcsimOptimizerResponseProbePlan",
    "GcsimOptimizerResponsePlanningLimits",
    "GcsimOptimizerResponseSelectionPolicy",
    "GcsimOptimizerResponseTraceRow",
    "ResponseProbeEvaluator",
    "analyze_gcsim_optimizer_response_observations",
    "build_gcsim_optimizer_response_probe_evaluator_request",
    "build_gcsim_optimizer_response_probe_stat_profile",
    "build_gcsim_optimizer_response_probe_plan",
    "enumerate_gcsim_optimizer_reachable_four_piece_main_domain",
    "gcsim_optimizer_main_layout_id",
    "materialize_gcsim_optimizer_response_probe",
    "run_gcsim_optimizer_main_response_discovery",
]
