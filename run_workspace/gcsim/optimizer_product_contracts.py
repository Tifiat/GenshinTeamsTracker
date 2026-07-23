"""Versioned product contracts for the three GCSIM optimizer operations.

This module is Milestone 0 only.  It freezes operation, target-package,
source-simulation, budget, progress, terminal-result, top-N, and uncertainty
semantics without implementing theoretical 2p+2p or account-artifact search.
The legacy theoretical 4p adapter keeps the original typed result as its source
evidence; future milestones should replace that adapter with native producers.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import TypeAlias

from .optimizer_engine_context import GcsimOptimizerEngineContext


GCSIM_OPTIMIZER_PRODUCT_CONTRACT_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_SOURCE_SIMULATION_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_SEARCH_BUDGET_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_TARGET_PACKAGE_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_PROGRESS_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_RESULT_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_UNCERTAINTY_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_DEFAULT_UNCERTAINTY_SIGMA = 2.0

GCSIM_OPTIMIZED_ADVISOR_BUDGET_ID = "optimized_theoretical_4p"
GCSIM_OPTIMIZED_ADVISOR_BUDGET_VERSION = 1

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SET_KEY_RE = re.compile(r"^[a-z][a-z0-9]*$")
_PARAMETER_KEY_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")


class GcsimOptimizerContractError(ValueError):
    """Raised when product-level optimizer modes or evidence are incoherent."""


class GcsimOptimizerOperation(str, Enum):
    THEORETICAL_FOUR_PIECE = "theoretical_4p"
    THEORETICAL_TWO_PLUS_TWO = "theoretical_2p2p"
    ACCOUNT_ARTIFACTS = "account_artifacts"


class GcsimOptimizerSearchDepth(str, Enum):
    QUICK = "quick"
    BALANCED = "balanced"
    DEEP = "deep"


class GcsimOptimizerTargetPackageKind(str, Enum):
    FOUR_PIECE = "four_piece"
    TWO_PLUS_TWO = "two_plus_two"


class GcsimOptimizerTerminalStatus(str, Enum):
    BEST_FOUND = "best_found"
    CANCELLED = "cancelled"
    DEADLINE = "deadline"
    NOT_READY = "not_ready"
    NO_SUCCESS = "no_success"
    FAILED = "failed"


class GcsimOptimizerProgressStage(str, Enum):
    PREFLIGHT = "preflight"
    LAYOUT_SCAN = "layout_scan"
    RESPONSE_SCAN = "response_scan"
    CANDIDATE_GENERATION = "candidate_generation"
    JOINT_SEARCH = "joint_search"
    SCREENING = "screening"
    FINAL_VALIDATION = "final_validation"
    RERACE = "rerace"
    COMPLETED = "completed"


class GcsimOptimizerUncertaintyLabel(str, Enum):
    REFERENCE = "reference"
    WITHIN_NOISE = "within_noise"
    SEPARATED = "separated"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerOperationContract:
    operation: GcsimOptimizerOperation
    cache_namespace: str
    provenance_namespace: str
    requires_account_depth: bool
    schema_version: int = GCSIM_OPTIMIZER_PRODUCT_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.operation, GcsimOptimizerOperation):
            raise GcsimOptimizerContractError("operation must be typed")
        _require_identifier(self.cache_namespace, "cache_namespace", dotted=True)
        _require_identifier(
            self.provenance_namespace,
            "provenance_namespace",
            dotted=True,
        )
        if not isinstance(self.requires_account_depth, bool):
            raise GcsimOptimizerContractError(
                "requires_account_depth must be a boolean"
            )
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_PRODUCT_CONTRACT_SCHEMA_VERSION
        ):
            raise GcsimOptimizerContractError(
                "unsupported optimizer product contract schema"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation.value,
            "cache_namespace": self.cache_namespace,
            "provenance_namespace": self.provenance_namespace,
            "requires_account_depth": self.requires_account_depth,
        }


_OPERATION_CONTRACT_VALUES = MappingProxyType(
    {
        GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE: (
            "gtt.gcsim.optimizer.cache.theoretical_4p.v1",
            "gtt.gcsim.optimizer.provenance.theoretical_4p.v1",
            False,
        ),
        GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO: (
            "gtt.gcsim.optimizer.cache.theoretical_2p2p.v1",
            "gtt.gcsim.optimizer.provenance.theoretical_2p2p.v1",
            False,
        ),
        GcsimOptimizerOperation.ACCOUNT_ARTIFACTS: (
            "gtt.gcsim.optimizer.cache.account_artifacts.v1",
            "gtt.gcsim.optimizer.provenance.account_artifacts.v1",
            True,
        ),
    }
)


def get_gcsim_optimizer_operation_contract(
    operation: GcsimOptimizerOperation,
) -> GcsimOptimizerOperationContract:
    if not isinstance(operation, GcsimOptimizerOperation):
        raise GcsimOptimizerContractError("operation must be typed")
    cache_namespace, provenance_namespace, requires_depth = (
        _OPERATION_CONTRACT_VALUES[operation]
    )
    return GcsimOptimizerOperationContract(
        operation=operation,
        cache_namespace=cache_namespace,
        provenance_namespace=provenance_namespace,
        requires_account_depth=requires_depth,
    )


GcsimOptimizerParameterScalar: TypeAlias = str | int | float | bool


@dataclass(frozen=True, slots=True)
class GcsimFourPieceTargetPackage:
    set_key: str
    set_parameters: Mapping[str, GcsimOptimizerParameterScalar] = field(
        default_factory=dict
    )
    schema_version: int = GCSIM_OPTIMIZER_TARGET_PACKAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_set_key(self.set_key)
        object.__setattr__(
            self,
            "set_parameters",
            _freeze_parameter_mapping(self.set_parameters),
        )
        if self.schema_version != GCSIM_OPTIMIZER_TARGET_PACKAGE_SCHEMA_VERSION:
            raise GcsimOptimizerContractError(
                "unsupported target-package schema"
            )

    @property
    def kind(self) -> GcsimOptimizerTargetPackageKind:
        return GcsimOptimizerTargetPackageKind.FOUR_PIECE

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind.value,
            "set_key": self.set_key,
            "set_parameters": dict(self.set_parameters),
        }


@dataclass(frozen=True, slots=True)
class GcsimTwoPlusTwoTargetPackage:
    set_a: str
    set_b: str
    set_a_parameters: Mapping[str, GcsimOptimizerParameterScalar] = field(
        default_factory=dict
    )
    set_b_parameters: Mapping[str, GcsimOptimizerParameterScalar] = field(
        default_factory=dict
    )
    schema_version: int = GCSIM_OPTIMIZER_TARGET_PACKAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_set_key(self.set_a)
        _require_set_key(self.set_b)
        if self.set_a == self.set_b:
            raise GcsimOptimizerContractError(
                "TwoPlusTwo requires two different set keys"
            )
        params_a = _freeze_parameter_mapping(self.set_a_parameters)
        params_b = _freeze_parameter_mapping(self.set_b_parameters)
        set_a = self.set_a
        set_b = self.set_b
        if set_b < set_a:
            set_a, set_b = set_b, set_a
            params_a, params_b = params_b, params_a
        object.__setattr__(self, "set_a", set_a)
        object.__setattr__(self, "set_b", set_b)
        object.__setattr__(self, "set_a_parameters", params_a)
        object.__setattr__(self, "set_b_parameters", params_b)
        if self.schema_version != GCSIM_OPTIMIZER_TARGET_PACKAGE_SCHEMA_VERSION:
            raise GcsimOptimizerContractError(
                "unsupported target-package schema"
            )

    @property
    def kind(self) -> GcsimOptimizerTargetPackageKind:
        return GcsimOptimizerTargetPackageKind.TWO_PLUS_TWO

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind.value,
            "sets": [
                {
                    "set_key": self.set_a,
                    "set_parameters": dict(self.set_a_parameters),
                },
                {
                    "set_key": self.set_b,
                    "set_parameters": dict(self.set_b_parameters),
                },
            ],
        }


GcsimOptimizerTargetPackage: TypeAlias = (
    GcsimFourPieceTargetPackage | GcsimTwoPlusTwoTargetPackage
)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerWearerTarget:
    wearer_id: str
    package: GcsimOptimizerTargetPackage

    def __post_init__(self) -> None:
        _require_identifier(self.wearer_id, "wearer_id")
        _require_target_package(self.package)

    def to_dict(self) -> dict[str, object]:
        return {
            "wearer_id": self.wearer_id,
            "package": self.package.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSourceSimulationIdentity:
    engine_id: str
    engine_version: str
    optimizer_contract_version: str
    artifact_sha256: str
    engine_tree_sha256: str
    engine_binding_sha256: str
    catalog_fingerprint: str
    source_config_sha256: str
    wearer_ids: tuple[str, ...]
    schema_version: int = GCSIM_OPTIMIZER_SOURCE_SIMULATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "engine_id",
            "engine_version",
            "optimizer_contract_version",
        ):
            _require_trimmed_text(getattr(self, field_name), field_name)
        for field_name in (
            "artifact_sha256",
            "engine_tree_sha256",
            "engine_binding_sha256",
            "catalog_fingerprint",
            "source_config_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        wearer_ids = _validated_wearer_ids(self.wearer_ids)
        object.__setattr__(self, "wearer_ids", wearer_ids)
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_SOURCE_SIMULATION_SCHEMA_VERSION
        ):
            raise GcsimOptimizerContractError(
                "unsupported source-simulation identity schema"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "engine_id": self.engine_id,
            "engine_version": self.engine_version,
            "optimizer_contract_version": self.optimizer_contract_version,
            "artifact_sha256": self.artifact_sha256,
            "engine_tree_sha256": self.engine_tree_sha256,
            "engine_binding_sha256": self.engine_binding_sha256,
            "catalog_fingerprint": self.catalog_fingerprint,
            "source_config_sha256": self.source_config_sha256,
            "wearer_ids": list(self.wearer_ids),
        }


def build_gcsim_optimizer_source_simulation_identity(
    *,
    engine_context: GcsimOptimizerEngineContext,
    prepared_config_text: str,
    wearer_ids: Sequence[str],
) -> GcsimOptimizerSourceSimulationIdentity:
    if not isinstance(engine_context, GcsimOptimizerEngineContext):
        raise GcsimOptimizerContractError(
            "engine_context must be a GcsimOptimizerEngineContext"
        )
    if not engine_context.trusted or engine_context.issues:
        raise GcsimOptimizerContractError(
            "source simulation requires a trusted optimizer engine context"
        )
    if not isinstance(prepared_config_text, str) or not prepared_config_text.strip():
        raise GcsimOptimizerContractError(
            "prepared_config_text must be non-empty"
        )
    return GcsimOptimizerSourceSimulationIdentity(
        engine_id=engine_context.engine_id,
        engine_version=engine_context.engine_version,
        optimizer_contract_version=engine_context.optimizer_contract_version,
        artifact_sha256=engine_context.artifact_sha256,
        engine_tree_sha256=engine_context.engine_tree_sha256,
        engine_binding_sha256=engine_context.binding_sha256,
        catalog_fingerprint=engine_context.catalog.source_fingerprint,
        source_config_sha256=_text_sha256(prepared_config_text),
        wearer_ids=tuple(wearer_ids),
    )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSearchBudget:
    operation: GcsimOptimizerOperation
    budget_id: str
    budget_version: int
    parameters: Mapping[str, object] = field(default_factory=dict)
    depth: GcsimOptimizerSearchDepth | None = None
    schema_version: int = GCSIM_OPTIMIZER_SEARCH_BUDGET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.operation, GcsimOptimizerOperation):
            raise GcsimOptimizerContractError(
                "search budget operation must be typed"
            )
        _require_identifier(self.budget_id, "budget_id")
        if (
            isinstance(self.budget_version, bool)
            or not isinstance(self.budget_version, int)
            or self.budget_version <= 0
        ):
            raise GcsimOptimizerContractError(
                "budget_version must be a positive integer"
            )
        object.__setattr__(
            self,
            "parameters",
            _freeze_json_mapping(self.parameters, field_name="parameters"),
        )
        _validate_operation_depth(self.operation, self.depth)
        if self.schema_version != GCSIM_OPTIMIZER_SEARCH_BUDGET_SCHEMA_VERSION:
            raise GcsimOptimizerContractError(
                "unsupported search-budget schema"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation.value,
            "budget_id": self.budget_id,
            "budget_version": self.budget_version,
            "depth": None if self.depth is None else self.depth.value,
            "parameters": _thaw_json(self.parameters),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerOperationRequest:
    operation: GcsimOptimizerOperation
    source_simulation: GcsimOptimizerSourceSimulationIdentity
    search_budget: GcsimOptimizerSearchBudget
    target_packages: tuple[GcsimOptimizerWearerTarget, ...] = ()
    inventory_snapshot_sha256: str = ""
    schema_version: int = GCSIM_OPTIMIZER_PRODUCT_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.operation, GcsimOptimizerOperation):
            raise GcsimOptimizerContractError("request operation must be typed")
        if not isinstance(
            self.source_simulation,
            GcsimOptimizerSourceSimulationIdentity,
        ):
            raise GcsimOptimizerContractError(
                "source_simulation must be typed"
            )
        if not isinstance(self.search_budget, GcsimOptimizerSearchBudget):
            raise GcsimOptimizerContractError("search_budget must be typed")
        if self.search_budget.operation is not self.operation:
            raise GcsimOptimizerContractError(
                "search budget belongs to another optimizer operation"
            )
        targets = _validated_team_targets(self.target_packages, allow_empty=True)
        object.__setattr__(self, "target_packages", targets)
        if self.operation is GcsimOptimizerOperation.ACCOUNT_ARTIFACTS:
            if (
                len(self.source_simulation.wearer_ids) != 4
                or tuple(item.wearer_id for item in targets)
                != self.source_simulation.wearer_ids
            ):
                raise GcsimOptimizerContractError(
                    "account operation requires one target package for every "
                    "source wearer in canonical order"
                )
            _require_sha256(
                self.inventory_snapshot_sha256,
                "inventory_snapshot_sha256",
            )
        else:
            if targets:
                raise GcsimOptimizerContractError(
                    "theoretical operations search their own package domain and "
                    "must not carry selected account targets"
                )
            if self.inventory_snapshot_sha256:
                raise GcsimOptimizerContractError(
                    "theoretical operations must not carry account inventory identity"
                )
        if self.schema_version != GCSIM_OPTIMIZER_PRODUCT_CONTRACT_SCHEMA_VERSION:
            raise GcsimOptimizerContractError(
                "unsupported optimizer operation request schema"
            )

    @property
    def depth(self) -> GcsimOptimizerSearchDepth | None:
        return self.search_budget.depth

    @property
    def cache_namespace(self) -> str:
        return get_gcsim_optimizer_operation_contract(
            self.operation
        ).cache_namespace

    @property
    def provenance_namespace(self) -> str:
        return get_gcsim_optimizer_operation_contract(
            self.operation
        ).provenance_namespace

    @property
    def request_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation.value,
            "cache_namespace": self.cache_namespace,
            "provenance_namespace": self.provenance_namespace,
            "source_simulation": self.source_simulation.to_dict(),
            "search_budget": self.search_budget.to_dict(),
            "target_packages": [
                target.to_dict() for target in self.target_packages
            ],
            "inventory_snapshot_sha256": self.inventory_snapshot_sha256,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerDpsEstimate:
    dps_mean: float
    dps_se: float | None
    iterations: int

    def __post_init__(self) -> None:
        _require_finite_non_negative(self.dps_mean, "dps_mean")
        if self.dps_se is not None:
            _require_finite_non_negative(self.dps_se, "dps_se")
        if (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations <= 0
        ):
            raise GcsimOptimizerContractError(
                "iterations must be a positive integer"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "dps_mean": float(self.dps_mean),
            "dps_se": None if self.dps_se is None else float(self.dps_se),
            "iterations": self.iterations,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerLeaderSnapshot:
    candidate_identity_sha256: str
    estimate: GcsimOptimizerDpsEstimate

    def __post_init__(self) -> None:
        _require_sha256(
            self.candidate_identity_sha256,
            "candidate_identity_sha256",
        )
        if not isinstance(self.estimate, GcsimOptimizerDpsEstimate):
            raise GcsimOptimizerContractError("leader estimate must be typed")

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_identity_sha256": self.candidate_identity_sha256,
            "estimate": self.estimate.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerProgressEvent:
    request_sha256: str
    operation: GcsimOptimizerOperation
    stage: GcsimOptimizerProgressStage
    sequence: int
    completed_work: int
    planned_work: int | None
    elapsed_seconds: float
    remaining_seconds: float | None
    cache_hits: int = 0
    current_best: GcsimOptimizerLeaderSnapshot | None = None
    depth: GcsimOptimizerSearchDepth | None = None
    schema_version: int = GCSIM_OPTIMIZER_PROGRESS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_sha256(self.request_sha256, "request_sha256")
        if not isinstance(self.operation, GcsimOptimizerOperation):
            raise GcsimOptimizerContractError(
                "progress operation must be typed"
            )
        if not isinstance(self.stage, GcsimOptimizerProgressStage):
            raise GcsimOptimizerContractError("progress stage must be typed")
        for field_name in ("sequence", "completed_work", "cache_hits"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise GcsimOptimizerContractError(
                    f"{field_name} must be a non-negative integer"
                )
        if self.planned_work is not None:
            if (
                isinstance(self.planned_work, bool)
                or not isinstance(self.planned_work, int)
                or self.planned_work < 0
            ):
                raise GcsimOptimizerContractError(
                    "planned_work must be a non-negative integer or None"
                )
            if self.completed_work > self.planned_work:
                raise GcsimOptimizerContractError(
                    "completed_work cannot exceed planned_work"
                )
        _require_finite_non_negative(self.elapsed_seconds, "elapsed_seconds")
        if self.remaining_seconds is not None:
            _require_finite_non_negative(
                self.remaining_seconds,
                "remaining_seconds",
            )
        if self.current_best is not None and not isinstance(
            self.current_best,
            GcsimOptimizerLeaderSnapshot,
        ):
            raise GcsimOptimizerContractError(
                "current_best must be a typed leader snapshot or None"
            )
        _validate_operation_depth(self.operation, self.depth)
        if self.schema_version != GCSIM_OPTIMIZER_PROGRESS_SCHEMA_VERSION:
            raise GcsimOptimizerContractError(
                "unsupported optimizer progress schema"
            )

    @property
    def event_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_sha256": self.request_sha256,
            "operation": self.operation.value,
            "depth": None if self.depth is None else self.depth.value,
            "stage": self.stage.value,
            "sequence": self.sequence,
            "completed_work": self.completed_work,
            "planned_work": self.planned_work,
            "elapsed_seconds": float(self.elapsed_seconds),
            "remaining_seconds": (
                None
                if self.remaining_seconds is None
                else float(self.remaining_seconds)
            ),
            "cache_hits": self.cache_hits,
            "current_best": (
                None if self.current_best is None else self.current_best.to_dict()
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerUncertainty:
    label: GcsimOptimizerUncertaintyLabel
    confidence_sigma: float
    absolute_delta_to_best: float
    combined_standard_error: float | None
    comparison_threshold: float | None
    schema_version: int = GCSIM_OPTIMIZER_UNCERTAINTY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.label, GcsimOptimizerUncertaintyLabel):
            raise GcsimOptimizerContractError(
                "uncertainty label must be typed"
            )
        _require_finite_positive(self.confidence_sigma, "confidence_sigma")
        _require_finite_non_negative(
            self.absolute_delta_to_best,
            "absolute_delta_to_best",
        )
        if self.label is GcsimOptimizerUncertaintyLabel.REFERENCE:
            if (
                self.absolute_delta_to_best != 0
                or self.combined_standard_error is not None
                or self.comparison_threshold is not None
            ):
                raise GcsimOptimizerContractError(
                    "reference uncertainty must have zero delta and no comparison"
                )
        elif self.label is GcsimOptimizerUncertaintyLabel.UNKNOWN:
            if (
                self.combined_standard_error is not None
                or self.comparison_threshold is not None
            ):
                raise GcsimOptimizerContractError(
                    "unknown uncertainty must not invent a standard error"
                )
        else:
            if (
                self.combined_standard_error is None
                or self.comparison_threshold is None
            ):
                raise GcsimOptimizerContractError(
                    "known uncertainty requires a standard error and threshold"
                )
            _require_finite_non_negative(
                self.combined_standard_error,
                "combined_standard_error",
            )
            _require_finite_non_negative(
                self.comparison_threshold,
                "comparison_threshold",
            )
            expected_threshold = (
                self.confidence_sigma * self.combined_standard_error
            )
            if not math.isclose(
                self.comparison_threshold,
                expected_threshold,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise GcsimOptimizerContractError(
                    "uncertainty threshold does not match sigma and standard error"
                )
            within_noise = (
                self.absolute_delta_to_best <= self.comparison_threshold
            )
            expected_label = (
                GcsimOptimizerUncertaintyLabel.WITHIN_NOISE
                if within_noise
                else GcsimOptimizerUncertaintyLabel.SEPARATED
            )
            if self.label is not expected_label:
                raise GcsimOptimizerContractError(
                    "uncertainty label does not match its comparison evidence"
                )
        if self.schema_version != GCSIM_OPTIMIZER_UNCERTAINTY_SCHEMA_VERSION:
            raise GcsimOptimizerContractError(
                "unsupported optimizer uncertainty schema"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "label": self.label.value,
            "confidence_sigma": float(self.confidence_sigma),
            "absolute_delta_to_best": float(self.absolute_delta_to_best),
            "combined_standard_error": (
                None
                if self.combined_standard_error is None
                else float(self.combined_standard_error)
            ),
            "comparison_threshold": (
                None
                if self.comparison_threshold is None
                else float(self.comparison_threshold)
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerCandidateResult:
    candidate_identity_sha256: str
    estimate: GcsimOptimizerDpsEstimate
    target_packages: tuple[GcsimOptimizerWearerTarget, ...]
    evidence_sha256: Mapping[str, str]

    def __post_init__(self) -> None:
        _require_sha256(
            self.candidate_identity_sha256,
            "candidate_identity_sha256",
        )
        if not isinstance(self.estimate, GcsimOptimizerDpsEstimate):
            raise GcsimOptimizerContractError(
                "candidate estimate must be typed"
            )
        object.__setattr__(
            self,
            "target_packages",
            _validated_team_targets(self.target_packages, allow_empty=False),
        )
        object.__setattr__(
            self,
            "evidence_sha256",
            _freeze_sha256_mapping(self.evidence_sha256),
        )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerRankedResult:
    rank: int
    candidate_identity_sha256: str
    estimate: GcsimOptimizerDpsEstimate
    percent_of_best: float
    dps_delta_to_best: float
    baseline_delta: float | None
    uncertainty: GcsimOptimizerUncertainty
    target_packages: tuple[GcsimOptimizerWearerTarget, ...]
    evidence_sha256: Mapping[str, str]

    def __post_init__(self) -> None:
        if (
            isinstance(self.rank, bool)
            or not isinstance(self.rank, int)
            or self.rank <= 0
        ):
            raise GcsimOptimizerContractError("rank must be a positive integer")
        _require_sha256(
            self.candidate_identity_sha256,
            "candidate_identity_sha256",
        )
        if not isinstance(self.estimate, GcsimOptimizerDpsEstimate):
            raise GcsimOptimizerContractError("ranked estimate must be typed")
        _require_finite_non_negative(self.percent_of_best, "percent_of_best")
        _require_finite(self.dps_delta_to_best, "dps_delta_to_best")
        if self.dps_delta_to_best > 0:
            raise GcsimOptimizerContractError(
                "dps_delta_to_best cannot be positive"
            )
        if self.baseline_delta is not None:
            _require_finite(self.baseline_delta, "baseline_delta")
        if not isinstance(self.uncertainty, GcsimOptimizerUncertainty):
            raise GcsimOptimizerContractError(
                "ranked uncertainty must be typed"
            )
        object.__setattr__(
            self,
            "target_packages",
            _validated_team_targets(self.target_packages, allow_empty=False),
        )
        object.__setattr__(
            self,
            "evidence_sha256",
            _freeze_sha256_mapping(self.evidence_sha256),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "rank": self.rank,
            "candidate_identity_sha256": self.candidate_identity_sha256,
            "estimate": self.estimate.to_dict(),
            "percent_of_best": float(self.percent_of_best),
            "dps_delta_to_best": float(self.dps_delta_to_best),
            "baseline_delta": (
                None
                if self.baseline_delta is None
                else float(self.baseline_delta)
            ),
            "uncertainty": self.uncertainty.to_dict(),
            "target_packages": [
                target.to_dict() for target in self.target_packages
            ],
            "evidence_sha256": dict(self.evidence_sha256),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTopN:
    entries: tuple[GcsimOptimizerRankedResult, ...] = ()
    confidence_sigma: float = GCSIM_OPTIMIZER_DEFAULT_UNCERTAINTY_SIGMA
    baseline_dps: float | None = None
    schema_version: int = GCSIM_OPTIMIZER_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        entries = tuple(self.entries)
        object.__setattr__(self, "entries", entries)
        _require_finite_positive(self.confidence_sigma, "confidence_sigma")
        if self.baseline_dps is not None:
            _require_finite_non_negative(self.baseline_dps, "baseline_dps")
        if any(not isinstance(item, GcsimOptimizerRankedResult) for item in entries):
            raise GcsimOptimizerContractError(
                "top-N entries must be typed ranked results"
            )
        if tuple(item.rank for item in entries) != tuple(
            range(1, len(entries) + 1)
        ):
            raise GcsimOptimizerContractError(
                "top-N ranks must be a contiguous one-based sequence"
            )
        if len({item.candidate_identity_sha256 for item in entries}) != len(
            entries
        ):
            raise GcsimOptimizerContractError(
                "top-N candidate identities must be unique"
            )
        canonical_order = tuple(
            sorted(
                entries,
                key=lambda item: (
                    -float(item.estimate.dps_mean),
                    item.candidate_identity_sha256,
                ),
            )
        )
        if entries != canonical_order:
            raise GcsimOptimizerContractError(
                "top-N entries are not in canonical DPS/identity order"
            )
        if entries:
            _validate_top_n_metrics(
                entries,
                confidence_sigma=self.confidence_sigma,
                baseline_dps=self.baseline_dps,
            )
        if self.schema_version != GCSIM_OPTIMIZER_RESULT_SCHEMA_VERSION:
            raise GcsimOptimizerContractError(
                "unsupported optimizer top-N schema"
            )

    @property
    def best_found(self) -> GcsimOptimizerRankedResult | None:
        return self.entries[0] if self.entries else None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "confidence_sigma": float(self.confidence_sigma),
            "baseline_dps": (
                None if self.baseline_dps is None else float(self.baseline_dps)
            ),
            "entries": [entry.to_dict() for entry in self.entries],
        }


def build_gcsim_optimizer_top_n(
    candidates: Iterable[GcsimOptimizerCandidateResult],
    *,
    top_n: int | None = None,
    baseline_dps: float | None = None,
    confidence_sigma: float = GCSIM_OPTIMIZER_DEFAULT_UNCERTAINTY_SIGMA,
) -> GcsimOptimizerTopN:
    if top_n is not None and (
        isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0
    ):
        raise GcsimOptimizerContractError(
            "top_n must be a positive integer or None"
        )
    _require_finite_positive(confidence_sigma, "confidence_sigma")
    if baseline_dps is not None:
        _require_finite_non_negative(baseline_dps, "baseline_dps")
    values = tuple(candidates)
    if any(not isinstance(item, GcsimOptimizerCandidateResult) for item in values):
        raise GcsimOptimizerContractError(
            "candidates must contain typed candidate results"
        )
    if len({item.candidate_identity_sha256 for item in values}) != len(values):
        raise GcsimOptimizerContractError(
            "candidate identities must be unique"
        )
    ordered = tuple(
        sorted(
            values,
            key=lambda item: (
                -float(item.estimate.dps_mean),
                item.candidate_identity_sha256,
            ),
        )
    )
    if top_n is not None:
        ordered = ordered[:top_n]
    if not ordered:
        return GcsimOptimizerTopN(
            confidence_sigma=confidence_sigma,
            baseline_dps=baseline_dps,
        )

    best = ordered[0].estimate
    entries: list[GcsimOptimizerRankedResult] = []
    for index, candidate in enumerate(ordered, start=1):
        delta = float(candidate.estimate.dps_mean) - float(best.dps_mean)
        percent = (
            100.0
            if best.dps_mean == 0
            else float(candidate.estimate.dps_mean) / float(best.dps_mean) * 100.0
        )
        baseline_delta = (
            None
            if baseline_dps is None
            else float(candidate.estimate.dps_mean) - float(baseline_dps)
        )
        entries.append(
            GcsimOptimizerRankedResult(
                rank=index,
                candidate_identity_sha256=candidate.candidate_identity_sha256,
                estimate=candidate.estimate,
                percent_of_best=percent,
                dps_delta_to_best=delta,
                baseline_delta=baseline_delta,
                uncertainty=_build_uncertainty(
                    rank=index,
                    estimate=candidate.estimate,
                    best=best,
                    confidence_sigma=confidence_sigma,
                ),
                target_packages=candidate.target_packages,
                evidence_sha256=candidate.evidence_sha256,
            )
        )
    return GcsimOptimizerTopN(
        entries=tuple(entries),
        confidence_sigma=confidence_sigma,
        baseline_dps=baseline_dps,
    )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTerminalResult:
    request: GcsimOptimizerOperationRequest
    status: GcsimOptimizerTerminalStatus
    stop_reason: str
    elapsed_seconds: float
    top_n: GcsimOptimizerTopN = field(default_factory=GcsimOptimizerTopN)
    evidence_sha256: Mapping[str, str] = field(default_factory=dict)
    issues: tuple[str, ...] = ()
    error: str = ""
    schema_version: int = GCSIM_OPTIMIZER_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.request, GcsimOptimizerOperationRequest):
            raise GcsimOptimizerContractError(
                "terminal result request must be typed"
            )
        if not isinstance(self.status, GcsimOptimizerTerminalStatus):
            raise GcsimOptimizerContractError(
                "terminal result status must be typed"
            )
        _require_trimmed_text(self.stop_reason, "stop_reason")
        _require_finite_non_negative(self.elapsed_seconds, "elapsed_seconds")
        if not isinstance(self.top_n, GcsimOptimizerTopN):
            raise GcsimOptimizerContractError("terminal top_n must be typed")
        object.__setattr__(
            self,
            "evidence_sha256",
            _freeze_sha256_mapping(self.evidence_sha256),
        )
        issues = tuple(self.issues)
        if any(
            not isinstance(issue, str)
            or not issue
            or issue != issue.strip()
            for issue in issues
        ):
            raise GcsimOptimizerContractError(
                "terminal issues must be non-empty trimmed strings"
            )
        object.__setattr__(self, "issues", issues)
        if not isinstance(self.error, str):
            raise GcsimOptimizerContractError("terminal error must be text")
        if self.status is GcsimOptimizerTerminalStatus.BEST_FOUND:
            if self.top_n.best_found is None or self.error:
                raise GcsimOptimizerContractError(
                    "best_found requires a top-N result and no error"
                )
        elif self.status in {
            GcsimOptimizerTerminalStatus.CANCELLED,
            GcsimOptimizerTerminalStatus.DEADLINE,
        }:
            if self.error:
                raise GcsimOptimizerContractError(
                    "cancelled/deadline results must not claim a failure error"
                )
        elif self.status is GcsimOptimizerTerminalStatus.FAILED:
            if not self.error:
                raise GcsimOptimizerContractError(
                    "failed requires an error"
                )
        elif self.top_n.entries or self.error:
            raise GcsimOptimizerContractError(
                "not_ready/no_success require no top-N evidence and no failure error"
            )
        _validate_result_targets(self.request, self.top_n.entries)
        if self.schema_version != GCSIM_OPTIMIZER_RESULT_SCHEMA_VERSION:
            raise GcsimOptimizerContractError(
                "unsupported optimizer result schema"
            )

    @property
    def best_found(self) -> GcsimOptimizerRankedResult | None:
        return self.top_n.best_found

    @property
    def result_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "provenance_namespace": self.request.provenance_namespace,
            "request": self.request.to_dict(),
            "request_sha256": self.request.request_sha256,
            "status": self.status.value,
            "stop_reason": self.stop_reason,
            "elapsed_seconds": float(self.elapsed_seconds),
            "top_n": self.top_n.to_dict(),
            "evidence_sha256": dict(self.evidence_sha256),
            "issues": list(self.issues),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResultAdapter:
    """Common serialized contract plus the untouched source evidence graph."""

    contract: GcsimOptimizerTerminalResult
    source_evidence: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.contract, GcsimOptimizerTerminalResult):
            raise GcsimOptimizerContractError("adapter contract must be typed")
        if self.source_evidence is None:
            raise GcsimOptimizerContractError(
                "adapter must retain its source evidence"
            )

    def to_dict(self) -> dict[str, object]:
        return self.contract.to_dict()


def build_gcsim_optimized_four_piece_operation_request(
    request: object,
) -> GcsimOptimizerOperationRequest:
    """Adapt the existing 4p request into the Milestone 0 request identity."""

    from .farming_optimized_advisor import GcsimOptimizedAdvisorRequest

    if not isinstance(request, GcsimOptimizedAdvisorRequest):
        raise GcsimOptimizerContractError(
            "request must be a GcsimOptimizedAdvisorRequest"
        )
    layout_request = request.automatic_request.layout_scan_request
    source = build_gcsim_optimizer_source_simulation_identity(
        engine_context=layout_request.engine_context,
        prepared_config_text=layout_request.prepared_config_text,
        wearer_ids=layout_request.wearer_ids,
    )
    budget = GcsimOptimizerSearchBudget(
        operation=GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
        budget_id=GCSIM_OPTIMIZED_ADVISOR_BUDGET_ID,
        budget_version=GCSIM_OPTIMIZED_ADVISOR_BUDGET_VERSION,
        parameters=_optimized_advisor_budget_payload(request),
    )
    return GcsimOptimizerOperationRequest(
        operation=GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE,
        source_simulation=source,
        search_budget=budget,
    )


def adapt_gcsim_optimized_four_piece_result(
    source_result: object,
) -> GcsimOptimizerResultAdapter:
    """Expose the current 4p result through the common contract losslessly."""

    from .farming_optimized_advisor import (
        GcsimOptimizedAdvisorResult,
        GcsimOptimizedAdvisorStatus,
    )

    if not isinstance(source_result, GcsimOptimizedAdvisorResult):
        raise GcsimOptimizerContractError(
            "source_result must be a GcsimOptimizedAdvisorResult"
        )
    request = build_gcsim_optimized_four_piece_operation_request(
        source_result.request_snapshot
    )
    candidates: list[GcsimOptimizerCandidateResult] = []
    finalist = source_result.finalist
    if finalist is not None:
        for outcome in finalist.outcomes:
            targets = tuple(
                GcsimOptimizerWearerTarget(
                    wearer_id=choice.wearer_id,
                    package=GcsimFourPieceTargetPackage(
                        set_key=choice.set_key,
                    ),
                )
                for choice in outcome.state.choices
            )
            candidate_identity = _canonical_sha256(
                {
                    "operation": (
                        GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE.value
                    ),
                    "source_simulation_sha256": (
                        request.source_simulation.identity_sha256
                    ),
                    "physical_state": [
                        list(choice.key) for choice in outcome.state.choices
                    ],
                }
            )
            candidates.append(
                GcsimOptimizerCandidateResult(
                    candidate_identity_sha256=candidate_identity,
                    estimate=GcsimOptimizerDpsEstimate(
                        dps_mean=outcome.dps_mean,
                        dps_se=outcome.dps_se,
                        iterations=outcome.iterations,
                    ),
                    target_packages=targets,
                    evidence_sha256={
                        "allocation": outcome.allocation_sha256,
                        "cache_identity": outcome.cache_identity_sha256,
                        "optimized_config": outcome.optimized_config_sha256,
                        "optimizer_input": outcome.optimizer_input_sha256,
                        "result_json": outcome.result_json_sha256,
                    },
                )
            )
    status = {
        GcsimOptimizedAdvisorStatus.BEST_FOUND: (
            GcsimOptimizerTerminalStatus.BEST_FOUND
        ),
        GcsimOptimizedAdvisorStatus.CANCELLED: (
            GcsimOptimizerTerminalStatus.CANCELLED
        ),
        GcsimOptimizedAdvisorStatus.DEADLINE: (
            GcsimOptimizerTerminalStatus.DEADLINE
        ),
        GcsimOptimizedAdvisorStatus.SCREENING_FAILED: (
            GcsimOptimizerTerminalStatus.NO_SUCCESS
        ),
        GcsimOptimizedAdvisorStatus.NO_OPTIMIZED_SUCCESS: (
            GcsimOptimizerTerminalStatus.NO_SUCCESS
        ),
        GcsimOptimizedAdvisorStatus.FAILED: (
            GcsimOptimizerTerminalStatus.FAILED
        ),
    }[source_result.status]
    result_evidence: dict[str, str] = {
        "engine_binding": request.source_simulation.engine_binding_sha256,
        "source_config": request.source_simulation.source_config_sha256,
    }
    if finalist is not None:
        result_evidence.update(
            {
                "budget": finalist.budget_sha256,
                "finalist_domain": finalist.finalist_domain_sha256,
                "finalist_request": finalist.request_sha256,
                "layout_catalog": finalist.layout_catalog_sha256,
                "validation_config": finalist.validation_config_sha256,
            }
        )
    contract = GcsimOptimizerTerminalResult(
        request=request,
        status=status,
        stop_reason=source_result.stop_reason,
        elapsed_seconds=source_result.elapsed_seconds,
        top_n=build_gcsim_optimizer_top_n(candidates),
        evidence_sha256=result_evidence,
        error=source_result.error,
    )
    return GcsimOptimizerResultAdapter(
        contract=contract,
        source_evidence=source_result,
    )


def canonical_gcsim_optimizer_json(
    value: object,
) -> str:
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        value = value.to_dict()
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _optimized_advisor_budget_payload(request: object) -> dict[str, object]:
    automatic = request.automatic_request
    layout = automatic.layout_scan_request
    return {
        "layout_scan": {
            "coordinate_scheduler": _json_value(
                layout.coordinate_scheduler_budget
            ),
            "combination_scheduler": _json_value(
                layout.combination_scheduler_budget
            ),
            "fidelity": _json_value(layout.fidelity),
            "scan": _json_value(layout.scan_budget),
            "overall_deadline_seconds": layout.overall_deadline_seconds,
        },
        "automatic": {
            "response_scheduler": _json_value(
                automatic.response_scheduler_budget
            ),
            "response_selection": _json_value(
                automatic.response_selection_budget
            ),
            "response_candidate_timeout_seconds": (
                automatic.response_candidate_timeout_seconds
            ),
            "screening_scheduler": _json_value(
                automatic.screening_scheduler_budget
            ),
            "team_scheduler": _json_value(automatic.team_scheduler_budget),
            "survivors": _json_value(automatic.survivor_budget),
            "composer": _json_value(automatic.composer_budget),
            "screening_candidate_timeout_seconds": (
                automatic.screening_candidate_timeout_seconds
            ),
            "overall_deadline_seconds": automatic.overall_deadline_seconds,
        },
        "finalist": _json_value(request.finalist_budget),
        "optimizer_options": _json_value(request.optimizer_options),
        "overall_deadline_seconds": request.overall_deadline_seconds,
    }


def _build_uncertainty(
    *,
    rank: int,
    estimate: GcsimOptimizerDpsEstimate,
    best: GcsimOptimizerDpsEstimate,
    confidence_sigma: float,
) -> GcsimOptimizerUncertainty:
    delta = abs(float(best.dps_mean) - float(estimate.dps_mean))
    if rank == 1:
        return GcsimOptimizerUncertainty(
            label=GcsimOptimizerUncertaintyLabel.REFERENCE,
            confidence_sigma=confidence_sigma,
            absolute_delta_to_best=0.0,
            combined_standard_error=None,
            comparison_threshold=None,
        )
    if best.dps_se is None or estimate.dps_se is None:
        return GcsimOptimizerUncertainty(
            label=GcsimOptimizerUncertaintyLabel.UNKNOWN,
            confidence_sigma=confidence_sigma,
            absolute_delta_to_best=delta,
            combined_standard_error=None,
            comparison_threshold=None,
        )
    combined = math.hypot(float(best.dps_se), float(estimate.dps_se))
    threshold = confidence_sigma * combined
    return GcsimOptimizerUncertainty(
        label=(
            GcsimOptimizerUncertaintyLabel.WITHIN_NOISE
            if delta <= threshold
            else GcsimOptimizerUncertaintyLabel.SEPARATED
        ),
        confidence_sigma=confidence_sigma,
        absolute_delta_to_best=delta,
        combined_standard_error=combined,
        comparison_threshold=threshold,
    )


def _validate_top_n_metrics(
    entries: tuple[GcsimOptimizerRankedResult, ...],
    *,
    confidence_sigma: float,
    baseline_dps: float | None,
) -> None:
    best = entries[0].estimate
    for entry in entries:
        expected_percent = (
            100.0
            if best.dps_mean == 0
            else float(entry.estimate.dps_mean) / float(best.dps_mean) * 100.0
        )
        expected_delta = float(entry.estimate.dps_mean) - float(best.dps_mean)
        expected_baseline = (
            None
            if baseline_dps is None
            else float(entry.estimate.dps_mean) - float(baseline_dps)
        )
        expected_uncertainty = _build_uncertainty(
            rank=entry.rank,
            estimate=entry.estimate,
            best=best,
            confidence_sigma=confidence_sigma,
        )
        if not math.isclose(
            entry.percent_of_best,
            expected_percent,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise GcsimOptimizerContractError(
                "top-N percent_of_best is inconsistent"
            )
        if not math.isclose(
            entry.dps_delta_to_best,
            expected_delta,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise GcsimOptimizerContractError(
                "top-N dps_delta_to_best is inconsistent"
            )
        if expected_baseline is None:
            if entry.baseline_delta is not None:
                raise GcsimOptimizerContractError(
                    "top-N baseline delta exists without a baseline"
                )
        elif entry.baseline_delta is None or not math.isclose(
            entry.baseline_delta,
            expected_baseline,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise GcsimOptimizerContractError(
                "top-N baseline delta is inconsistent"
            )
        if entry.uncertainty != expected_uncertainty:
            raise GcsimOptimizerContractError(
                "top-N uncertainty is inconsistent"
            )


def _validate_result_targets(
    request: GcsimOptimizerOperationRequest,
    entries: tuple[GcsimOptimizerRankedResult, ...],
) -> None:
    wearer_ids = request.source_simulation.wearer_ids
    for entry in entries:
        if tuple(item.wearer_id for item in entry.target_packages) != wearer_ids:
            raise GcsimOptimizerContractError(
                "result targets do not match source wearer order"
            )
        packages = tuple(item.package for item in entry.target_packages)
        if request.operation is GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE:
            if any(
                not isinstance(package, GcsimFourPieceTargetPackage)
                for package in packages
            ):
                raise GcsimOptimizerContractError(
                    "theoretical 4p results may contain only FourPiece packages"
                )
        elif (
            request.operation
            is GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO
        ):
            if any(
                not isinstance(package, GcsimTwoPlusTwoTargetPackage)
                for package in packages
            ):
                raise GcsimOptimizerContractError(
                    "theoretical 2p+2p results may contain only TwoPlusTwo packages"
                )
        elif entry.target_packages != request.target_packages:
            raise GcsimOptimizerContractError(
                "account result targets differ from the frozen request"
            )


def _validate_operation_depth(
    operation: GcsimOptimizerOperation,
    depth: GcsimOptimizerSearchDepth | None,
) -> None:
    contract = get_gcsim_optimizer_operation_contract(operation)
    if contract.requires_account_depth:
        if not isinstance(depth, GcsimOptimizerSearchDepth):
            raise GcsimOptimizerContractError(
                "account artifact search requires Quick, Balanced, or Deep depth"
            )
    elif depth is not None:
        raise GcsimOptimizerContractError(
            "theoretical optimizer operations must not carry account search depth"
        )


def _validated_wearer_ids(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GcsimOptimizerContractError("wearer_ids must be a sequence")
    try:
        wearer_ids = tuple(values)
    except TypeError as exc:
        raise GcsimOptimizerContractError(
            "wearer_ids must be an iterable"
        ) from exc
    if not wearer_ids or len(wearer_ids) > 4:
        raise GcsimOptimizerContractError(
            "optimizer source identity requires between one and four wearers"
        )
    for wearer_id in wearer_ids:
        _require_identifier(wearer_id, "wearer_id")
    if len(set(wearer_ids)) != len(wearer_ids):
        raise GcsimOptimizerContractError("wearer_ids must be unique")
    return wearer_ids


def _validated_team_targets(
    values: Iterable[GcsimOptimizerWearerTarget],
    *,
    allow_empty: bool,
) -> tuple[GcsimOptimizerWearerTarget, ...]:
    if isinstance(values, (str, bytes)):
        raise GcsimOptimizerContractError(
            "target_packages must be a sequence"
        )
    try:
        targets = tuple(values)
    except TypeError as exc:
        raise GcsimOptimizerContractError(
            "target_packages must be an iterable"
        ) from exc
    if not targets and allow_empty:
        return ()
    if not targets or len(targets) > 4:
        raise GcsimOptimizerContractError(
            "team target packages require between one and four wearer assignments"
        )
    if any(not isinstance(item, GcsimOptimizerWearerTarget) for item in targets):
        raise GcsimOptimizerContractError(
            "target_packages must contain typed wearer targets"
        )
    wearer_ids = tuple(item.wearer_id for item in targets)
    if len(set(wearer_ids)) != len(wearer_ids):
        raise GcsimOptimizerContractError(
            "target-package wearer ids must be unique"
        )
    return targets


def _require_target_package(value: object) -> None:
    if not isinstance(
        value,
        (GcsimFourPieceTargetPackage, GcsimTwoPlusTwoTargetPackage),
    ):
        raise GcsimOptimizerContractError(
            "package must be FourPiece or TwoPlusTwo"
        )


def _freeze_parameter_mapping(
    value: Mapping[str, GcsimOptimizerParameterScalar],
) -> Mapping[str, GcsimOptimizerParameterScalar]:
    if not isinstance(value, Mapping):
        raise GcsimOptimizerContractError("set parameters must be a mapping")
    result: dict[str, GcsimOptimizerParameterScalar] = {}
    for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
        if not isinstance(key, str) or _PARAMETER_KEY_RE.fullmatch(key) is None:
            raise GcsimOptimizerContractError(
                "set parameter keys must be canonical identifiers"
            )
        if not isinstance(item, (str, int, float, bool)) or item is None:
            raise GcsimOptimizerContractError(
                "set parameter values must be JSON scalars"
            )
        if isinstance(item, float) and not math.isfinite(item):
            raise GcsimOptimizerContractError(
                "set parameter floats must be finite"
            )
        result[key] = item
    return MappingProxyType(result)


def _freeze_sha256_mapping(value: Mapping[str, str]) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise GcsimOptimizerContractError("evidence_sha256 must be a mapping")
    result: dict[str, str] = {}
    for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
        if not isinstance(key, str) or _PARAMETER_KEY_RE.fullmatch(key) is None:
            raise GcsimOptimizerContractError(
                "evidence hash keys must be canonical identifiers"
            )
        _require_sha256(item, f"evidence_sha256[{key!r}]")
        result[key] = item
    return MappingProxyType(result)


def _freeze_json_mapping(
    value: Mapping[str, object],
    *,
    field_name: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GcsimOptimizerContractError(f"{field_name} must be a mapping")
    result: dict[str, object] = {}
    for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
        if not isinstance(key, str) or not key or key != key.strip():
            raise GcsimOptimizerContractError(
                f"{field_name} keys must be non-empty trimmed strings"
            )
        result[key] = _freeze_json_value(item, field_name=f"{field_name}.{key}")
    return MappingProxyType(result)


def _freeze_json_value(value: object, *, field_name: str) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise GcsimOptimizerContractError(
                f"{field_name} contains a non-finite float"
            )
        return value
    if isinstance(value, Mapping):
        return _freeze_json_mapping(value, field_name=field_name)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(
            _freeze_json_value(item, field_name=f"{field_name}[]")
            for item in value
        )
    raise GcsimOptimizerContractError(
        f"{field_name} contains a non-JSON value"
    )


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _thaw_json(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _json_value(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise GcsimOptimizerContractError(
                "cannot serialize a non-finite float"
            )
        return value
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _json_value(getattr(value, item.name))
            for item in fields(value)
            if item.init
        }
    if isinstance(value, Mapping):
        return {
            str(key): _json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_json_value(item) for item in value]
    raise GcsimOptimizerContractError(
        f"cannot serialize budget value of type {type(value).__name__}"
    )


def _require_set_key(value: object) -> None:
    if not isinstance(value, str) or _SET_KEY_RE.fullmatch(value) is None:
        raise GcsimOptimizerContractError(
            "set_key must be a canonical lowercase GCSIM key"
        )


def _require_identifier(
    value: object,
    field_name: str,
    *,
    dotted: bool = False,
) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise GcsimOptimizerContractError(
            f"{field_name} must be a non-empty trimmed string"
        )
    pattern = (
        re.compile(r"^[a-z][a-z0-9_.]*$")
        if dotted
        else _IDENTIFIER_RE
    )
    if pattern.fullmatch(value) is None:
        raise GcsimOptimizerContractError(
            f"{field_name} must be a canonical identifier"
        )


def _require_trimmed_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise GcsimOptimizerContractError(
            f"{field_name} must be non-empty trimmed text"
        )


def _require_sha256(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GcsimOptimizerContractError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


def _require_finite(value: object, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise GcsimOptimizerContractError(f"{field_name} must be finite")


def _require_finite_non_negative(value: object, field_name: str) -> None:
    _require_finite(value, field_name)
    if value < 0:
        raise GcsimOptimizerContractError(
            f"{field_name} must be non-negative"
        )


def _require_finite_positive(value: object, field_name: str) -> None:
    _require_finite(value, field_name)
    if value <= 0:
        raise GcsimOptimizerContractError(f"{field_name} must be positive")


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        canonical_gcsim_optimizer_json(value).encode("utf-8")
    ).hexdigest()
