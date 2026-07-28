"""Versioned product contracts for GTT's three GCSIM optimizer operations.

Schema v4 makes the account minimum-stat space explicit: exact five-artifact
main/sub stats plus only engine-proved, unconditional static set contributions.
It models theoretical 4p, theoretical 2p+2p, and real-account artifact
operations without implementing UI.  The existing theoretical 4p advisor is
exposed through a compatibility projection while its richer in-process
evidence graph remains attached to the adapter.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import TypeAlias

from .optimizer_engine_context import GcsimOptimizerEngineContext


GCSIM_OPTIMIZER_PRODUCT_CONTRACT_SCHEMA_VERSION = 4
GCSIM_OPTIMIZER_SOURCE_SIMULATION_SCHEMA_VERSION = 2
GCSIM_OPTIMIZER_WORK_PLAN_SCHEMA_VERSION = 2
GCSIM_OPTIMIZER_TARGET_PACKAGE_SCHEMA_VERSION = 2
GCSIM_OPTIMIZER_PROGRESS_SCHEMA_VERSION = 2
GCSIM_OPTIMIZER_RESULT_SCHEMA_VERSION = 2
GCSIM_OPTIMIZER_UNCERTAINTY_SCHEMA_VERSION = 2
GCSIM_OPTIMIZER_DEFAULT_UNCERTAINTY_SIGMA = 2.0

GCSIM_OPTIMIZED_ADVISOR_WORK_PLAN_ID = "optimized_theoretical_4p"
GCSIM_OPTIMIZED_ADVISOR_WORK_PLAN_VERSION = 1
GCSIM_OPTIMIZED_PAIR_ADVISOR_WORK_PLAN_ID = "optimized_theoretical_2p2p"
GCSIM_OPTIMIZED_PAIR_ADVISOR_WORK_PLAN_VERSION = 1
GCSIM_THEORETICAL_ANYTIME_FOUR_PIECE_WORK_PLAN_ID = (
    "theoretical_4p_anytime_approx"
)
GCSIM_THEORETICAL_ANYTIME_FOUR_PIECE_WORK_PLAN_VERSION = 1
GCSIM_THEORETICAL_ANYTIME_TWO_PLUS_TWO_WORK_PLAN_ID = (
    "theoretical_2p2p_anytime_approx"
)
GCSIM_THEORETICAL_ANYTIME_TWO_PLUS_TWO_WORK_PLAN_VERSION = 1

GCSIM_OPTIMIZER_ARTIFACT_SLOTS = (
    "flower",
    "plume",
    "sands",
    "goblet",
    "circlet",
)

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_DOTTED_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_.]*$")
_SET_KEY_RE = re.compile(r"^[a-z][a-z0-9]*$")
_PARAMETER_KEY_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
_STAT_AXIS_RE = re.compile(r"^[a-z][a-z0-9]*%?$")

# Exact normalized axes that a real artifact build can contribute directly.
# This is deliberately narrower than arbitrary GCSIM runtime stats: unknown
# axes must fail at the versioned request boundary instead of silently making
# the candidate domain empty.
GCSIM_OPTIMIZER_ACCOUNT_STAT_AXES = frozenset(
    {
        "hp",
        "atk",
        "def",
        "hp%",
        "atk%",
        "def%",
        "em",
        "er",
        "cr",
        "cd",
        "pyro%",
        "hydro%",
        "electro%",
        "cryo%",
        "anemo%",
        "geo%",
        "dendro%",
        "phys%",
        "heal",
    }
)


class GcsimOptimizerContractError(ValueError):
    """Raised when optimizer request or evidence contracts are incoherent."""


class GcsimOptimizerOperation(str, Enum):
    THEORETICAL_FOUR_PIECE = "theoretical_4p"
    THEORETICAL_TWO_PLUS_TWO = "theoretical_2p2p"
    ACCOUNT_ARTIFACTS = "account_artifacts"


class GcsimOptimizerAccountScope(str, Enum):
    SELECTED_SET_POOLS = "selected_set_pools"
    ALL_DATABASE_SETS = "all_database_sets"


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
    REFINEMENT = "refinement"
    FINAL_VALIDATION = "final_validation"
    RERACE = "rerace"
    COMPLETED = "completed"


class GcsimOptimizerUncertaintyLabel(str, Enum):
    REFERENCE = "reference"
    WITHIN_NOISE = "within_noise"
    SEPARATED = "separated"
    UNKNOWN = "unknown"


class GcsimOptimizerIssueScope(str, Enum):
    REQUEST = "request"
    ARTIFACT = "artifact"
    PACKAGE = "package"
    CANDIDATE = "candidate"
    EVALUATION = "evaluation"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerOperationContract:
    operation: GcsimOptimizerOperation
    cache_namespace: str
    provenance_namespace: str
    requires_artifact_database: bool
    schema_version: int = GCSIM_OPTIMIZER_PRODUCT_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_enum(self.operation, GcsimOptimizerOperation, "operation")
        _require_identifier(self.cache_namespace, "cache_namespace", dotted=True)
        _require_identifier(
            self.provenance_namespace,
            "provenance_namespace",
            dotted=True,
        )
        if not isinstance(self.requires_artifact_database, bool):
            raise GcsimOptimizerContractError(
                "requires_artifact_database must be a boolean"
            )
        _require_schema(
            self.schema_version,
            GCSIM_OPTIMIZER_PRODUCT_CONTRACT_SCHEMA_VERSION,
            "optimizer product contract",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation.value,
            "cache_namespace": self.cache_namespace,
            "provenance_namespace": self.provenance_namespace,
            "requires_artifact_database": self.requires_artifact_database,
        }


_OPERATION_CONTRACT_VALUES = MappingProxyType(
    {
        GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE: (
            "gtt.gcsim.optimizer.cache.theoretical_4p.v4",
            "gtt.gcsim.optimizer.provenance.theoretical_4p.v4",
            False,
        ),
        GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO: (
            "gtt.gcsim.optimizer.cache.theoretical_2p2p.v4",
            "gtt.gcsim.optimizer.provenance.theoretical_2p2p.v4",
            False,
        ),
        GcsimOptimizerOperation.ACCOUNT_ARTIFACTS: (
            "gtt.gcsim.optimizer.cache.account_artifacts.v4",
            "gtt.gcsim.optimizer.provenance.account_artifacts.v4",
            True,
        ),
    }
)


def get_gcsim_optimizer_operation_contract(
    operation: GcsimOptimizerOperation,
) -> GcsimOptimizerOperationContract:
    _require_enum(operation, GcsimOptimizerOperation, "operation")
    cache_namespace, provenance_namespace, requires_database = (
        _OPERATION_CONTRACT_VALUES[operation]
    )
    return GcsimOptimizerOperationContract(
        operation=operation,
        cache_namespace=cache_namespace,
        provenance_namespace=provenance_namespace,
        requires_artifact_database=requires_database,
    )


GcsimOptimizerParameterScalar: TypeAlias = str | int | float | bool


@dataclass(frozen=True, slots=True)
class GcsimOptimizerWearerIdentity:
    team_slot: int
    account_character_id: int | None
    gcsim_character_key: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.team_slot, bool)
            or not isinstance(self.team_slot, int)
            or self.team_slot not in (1, 2, 3, 4)
        ):
            raise GcsimOptimizerContractError("team_slot must be one of 1, 2, 3, 4")
        if self.account_character_id is not None:
            _require_positive_int(
                self.account_character_id,
                "account_character_id",
            )
        _require_set_key_like(
            self.gcsim_character_key,
            "gcsim_character_key",
        )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "team_slot": self.team_slot,
            "account_character_id": self.account_character_id,
            "gcsim_character_key": self.gcsim_character_key,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSetReference:
    set_uid: str
    gcsim_set_key: str
    engine_binding_sha256: str
    catalog_fingerprint: str
    set_parameters: Mapping[str, GcsimOptimizerParameterScalar] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        _require_trimmed_text(self.set_uid, "set_uid")
        _require_set_key(self.gcsim_set_key)
        _require_sha256(self.engine_binding_sha256, "engine_binding_sha256")
        _require_sha256(self.catalog_fingerprint, "catalog_fingerprint")
        object.__setattr__(
            self,
            "set_parameters",
            _freeze_parameter_mapping(self.set_parameters),
        )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "set_uid": self.set_uid,
            "gcsim_set_key": self.gcsim_set_key,
            "engine_binding_sha256": self.engine_binding_sha256,
            "catalog_fingerprint": self.catalog_fingerprint,
            "set_parameters": dict(self.set_parameters),
        }


@dataclass(frozen=True, slots=True)
class GcsimFourPieceTargetPackage:
    set_ref: GcsimOptimizerSetReference
    schema_version: int = GCSIM_OPTIMIZER_TARGET_PACKAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.set_ref, GcsimOptimizerSetReference):
            raise GcsimOptimizerContractError("set_ref must be typed")
        _require_schema(
            self.schema_version,
            GCSIM_OPTIMIZER_TARGET_PACKAGE_SCHEMA_VERSION,
            "target package",
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
            "set": self.set_ref.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GcsimTwoPlusTwoTargetPackage:
    set_a: GcsimOptimizerSetReference
    set_b: GcsimOptimizerSetReference
    schema_version: int = GCSIM_OPTIMIZER_TARGET_PACKAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.set_a, GcsimOptimizerSetReference) or not isinstance(
            self.set_b,
            GcsimOptimizerSetReference,
        ):
            raise GcsimOptimizerContractError("2p+2p set references must be typed")
        if self.set_a.set_uid == self.set_b.set_uid:
            raise GcsimOptimizerContractError(
                "2p+2p requires two different concrete set_uid values"
            )
        set_a, set_b = self.set_a, self.set_b
        if set_b.identity_sha256 < set_a.identity_sha256:
            set_a, set_b = set_b, set_a
        object.__setattr__(self, "set_a", set_a)
        object.__setattr__(self, "set_b", set_b)
        _require_schema(
            self.schema_version,
            GCSIM_OPTIMIZER_TARGET_PACKAGE_SCHEMA_VERSION,
            "target package",
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
            "sets": [self.set_a.to_dict(), self.set_b.to_dict()],
        }


GcsimOptimizerTargetPackage: TypeAlias = (
    GcsimFourPieceTargetPackage | GcsimTwoPlusTwoTargetPackage
)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerWearerTarget:
    wearer: GcsimOptimizerWearerIdentity
    package: GcsimOptimizerTargetPackage

    def __post_init__(self) -> None:
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerContractError("target wearer must be typed")
        _require_target_package(self.package)

    @property
    def wearer_id(self) -> str:
        """Legacy convenience for the experimental theoretical adapter."""

        return self.wearer.gcsim_character_key

    def to_dict(self) -> dict[str, object]:
        return {
            "wearer": self.wearer.to_dict(),
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
    prepared_config_sha256: str
    rotation_sha256: str
    target_sha256: str
    simulation_options_sha256: str
    wearers: tuple[GcsimOptimizerWearerIdentity, ...]
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
            "prepared_config_sha256",
            "rotation_sha256",
            "target_sha256",
            "simulation_options_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        object.__setattr__(self, "wearers", _validated_wearers(self.wearers))
        _require_schema(
            self.schema_version,
            GCSIM_OPTIMIZER_SOURCE_SIMULATION_SCHEMA_VERSION,
            "source simulation identity",
        )

    @property
    def wearer_ids(self) -> tuple[str, ...]:
        return tuple(item.gcsim_character_key for item in self.wearers)

    @property
    def source_config_sha256(self) -> str:
        """Deprecated source name retained for the theoretical adapter."""

        return self.prepared_config_sha256

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
            "prepared_config_sha256": self.prepared_config_sha256,
            "rotation_sha256": self.rotation_sha256,
            "target_sha256": self.target_sha256,
            "simulation_options_sha256": self.simulation_options_sha256,
            "wearers": [item.to_dict() for item in self.wearers],
        }


def build_gcsim_optimizer_source_simulation_identity(
    *,
    engine_context: GcsimOptimizerEngineContext,
    prepared_config_text: str,
    wearers: Sequence[GcsimOptimizerWearerIdentity] | None = None,
    wearer_ids: Sequence[str] | None = None,
    rotation_identity_text: str | None = None,
    target_identity_text: str | None = None,
    simulation_options_identity_text: str | None = None,
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
        raise GcsimOptimizerContractError("prepared_config_text must be non-empty")
    if (wearers is None) == (wearer_ids is None):
        raise GcsimOptimizerContractError(
            "provide exactly one of typed wearers or legacy wearer_ids"
        )
    if wearers is None:
        assert wearer_ids is not None
        wearers = tuple(
            GcsimOptimizerWearerIdentity(
                team_slot=index,
                account_character_id=None,
                gcsim_character_key=wearer_id,
            )
            for index, wearer_id in enumerate(wearer_ids, start=1)
        )
    prepared_hash = _text_sha256(prepared_config_text)
    # The compatibility path lacks split semantic text.  Hashing the full config
    # is conservative: every rotation/target/options change still invalidates
    # the identity, though unrelated config changes may over-invalidate it.
    return GcsimOptimizerSourceSimulationIdentity(
        engine_id=engine_context.engine_id,
        engine_version=engine_context.engine_version,
        optimizer_contract_version=engine_context.optimizer_contract_version,
        artifact_sha256=engine_context.artifact_sha256,
        engine_tree_sha256=engine_context.engine_tree_sha256,
        engine_binding_sha256=engine_context.binding_sha256,
        catalog_fingerprint=engine_context.catalog.source_fingerprint,
        prepared_config_sha256=prepared_hash,
        rotation_sha256=_text_sha256(
            prepared_config_text
            if rotation_identity_text is None
            else rotation_identity_text
        ),
        target_sha256=_text_sha256(
            prepared_config_text if target_identity_text is None else target_identity_text
        ),
        simulation_options_sha256=_text_sha256(
            prepared_config_text
            if simulation_options_identity_text is None
            else simulation_options_identity_text
        ),
        wearers=tuple(wearers),
    )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerWorkPlan:
    operation: GcsimOptimizerOperation
    plan_id: str
    plan_version: int
    parameters: Mapping[str, object] = field(default_factory=dict)
    schema_version: int = GCSIM_OPTIMIZER_WORK_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_enum(self.operation, GcsimOptimizerOperation, "work plan operation")
        _require_identifier(self.plan_id, "plan_id")
        _require_positive_int(self.plan_version, "plan_version")
        object.__setattr__(
            self,
            "parameters",
            _freeze_json_mapping(self.parameters, field_name="parameters"),
        )
        _require_schema(
            self.schema_version,
            GCSIM_OPTIMIZER_WORK_PLAN_SCHEMA_VERSION,
            "optimizer work plan",
        )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation.value,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "parameters": _thaw_json(self.parameters),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerWearerSetPool:
    wearer: GcsimOptimizerWearerIdentity
    allowed_sets: tuple[GcsimOptimizerSetReference, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerContractError("set-pool wearer must be typed")
        values = tuple(self.allowed_sets)
        if not values or any(
            not isinstance(item, GcsimOptimizerSetReference) for item in values
        ):
            raise GcsimOptimizerContractError(
                "selected set pool must contain typed set references"
            )
        ordered = tuple(sorted(values, key=lambda item: item.identity_sha256))
        if len({item.set_uid for item in ordered}) != len(ordered):
            raise GcsimOptimizerContractError(
                "selected set pool concrete set_uid values must be unique"
            )
        object.__setattr__(self, "allowed_sets", ordered)

    def to_dict(self) -> dict[str, object]:
        return {
            "wearer": self.wearer.to_dict(),
            "allowed_sets": [item.to_dict() for item in self.allowed_sets],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerFourStarEligibilityOverride:
    wearer: GcsimOptimizerWearerIdentity
    allowed_set_uids: tuple[str, ...] = ()
    allowed_artifact_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerContractError("4-star override wearer must be typed")
        set_uids = tuple(sorted(self.allowed_set_uids))
        for value in set_uids:
            _require_trimmed_text(value, "allowed_set_uid")
        if len(set(set_uids)) != len(set_uids):
            raise GcsimOptimizerContractError(
                "4-star allowed_set_uids must be unique"
            )
        artifact_ids = _validated_artifact_ids(
            self.allowed_artifact_ids,
            "allowed_artifact_ids",
            allow_empty=True,
        )
        if not set_uids and not artifact_ids:
            raise GcsimOptimizerContractError(
                "4-star override must authorize a set or artifact ID"
            )
        object.__setattr__(self, "allowed_set_uids", set_uids)
        object.__setattr__(self, "allowed_artifact_ids", artifact_ids)

    def to_dict(self) -> dict[str, object]:
        return {
            "wearer": self.wearer.to_dict(),
            "allowed_set_uids": list(self.allowed_set_uids),
            "allowed_artifact_ids": list(self.allowed_artifact_ids),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerMinimumStatConstraint:
    """Hard lower bound over a real build's proven static stat contribution."""

    wearer: GcsimOptimizerWearerIdentity
    axis_key: str
    minimum: str

    def __post_init__(self) -> None:
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerContractError(
                "minimum-stat constraint wearer must be typed"
            )
        if (
            not isinstance(self.axis_key, str)
            or _STAT_AXIS_RE.fullmatch(self.axis_key) is None
            or self.axis_key not in GCSIM_OPTIMIZER_ACCOUNT_STAT_AXES
        ):
            raise GcsimOptimizerContractError(
                "minimum-stat axis_key must be a supported normalized "
                "artifact-build GCSIM stat key"
            )
        object.__setattr__(
            self,
            "minimum",
            _canonical_decimal_text(
                self.minimum,
                "minimum-stat minimum",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "wearer": self.wearer.to_dict(),
            "axis_key": self.axis_key,
            "minimum": self.minimum,
            "stat_space": "static_build_contribution",
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerOperationRequest:
    operation: GcsimOptimizerOperation
    source_simulation: GcsimOptimizerSourceSimulationIdentity
    work_plan: GcsimOptimizerWorkPlan
    account_scope: GcsimOptimizerAccountScope | None = None
    selected_set_pools: tuple[GcsimOptimizerWearerSetPool, ...] = ()
    include_2p2p: bool = False
    four_star_overrides: tuple[
        GcsimOptimizerFourStarEligibilityOverride, ...
    ] = ()
    minimum_stat_constraints: tuple[
        GcsimOptimizerMinimumStatConstraint, ...
    ] = ()
    artifact_database_input_sha256: str = ""
    schema_version: int = GCSIM_OPTIMIZER_PRODUCT_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_enum(self.operation, GcsimOptimizerOperation, "request operation")
        if not isinstance(
            self.source_simulation,
            GcsimOptimizerSourceSimulationIdentity,
        ):
            raise GcsimOptimizerContractError("source_simulation must be typed")
        if not isinstance(self.work_plan, GcsimOptimizerWorkPlan):
            raise GcsimOptimizerContractError("work_plan must be typed")
        if self.work_plan.operation is not self.operation:
            raise GcsimOptimizerContractError(
                "work plan belongs to another optimizer operation"
            )
        if not isinstance(self.include_2p2p, bool):
            raise GcsimOptimizerContractError("include_2p2p must be a boolean")
        pools = tuple(self.selected_set_pools)
        overrides = tuple(self.four_star_overrides)
        constraints = tuple(self.minimum_stat_constraints)
        if any(not isinstance(item, GcsimOptimizerWearerSetPool) for item in pools):
            raise GcsimOptimizerContractError(
                "selected_set_pools must contain typed wearer pools"
            )
        if any(
            not isinstance(item, GcsimOptimizerFourStarEligibilityOverride)
            for item in overrides
        ):
            raise GcsimOptimizerContractError(
                "four_star_overrides must contain typed override rows"
            )
        if any(
            not isinstance(item, GcsimOptimizerMinimumStatConstraint)
            for item in constraints
        ):
            raise GcsimOptimizerContractError(
                "minimum_stat_constraints must contain typed rows"
            )
        object.__setattr__(self, "selected_set_pools", pools)
        object.__setattr__(self, "four_star_overrides", overrides)
        object.__setattr__(
            self,
            "minimum_stat_constraints",
            tuple(
                sorted(
                    constraints,
                    key=lambda item: (
                        item.wearer.team_slot,
                        item.axis_key,
                    ),
                )
            ),
        )

        if self.operation is GcsimOptimizerOperation.ACCOUNT_ARTIFACTS:
            if len(self.source_simulation.wearers) != 4:
                raise GcsimOptimizerContractError(
                    "account optimizer request requires exactly four source wearers"
                )
            self._validate_account_request(pools, overrides, constraints)
        else:
            if (
                len(self.source_simulation.wearers) != 4
                and self.work_plan.plan_id
                not in {
                    GCSIM_OPTIMIZED_ADVISOR_WORK_PLAN_ID,
                    GCSIM_OPTIMIZED_PAIR_ADVISOR_WORK_PLAN_ID,
                }
            ):
                raise GcsimOptimizerContractError(
                    "theoretical product request requires exactly four source wearers"
                )
            if self.account_scope is not None:
                raise GcsimOptimizerContractError(
                    "theoretical operation must not carry account_scope"
                )
            if (
                pools
                or overrides
                or constraints
                or self.artifact_database_input_sha256
            ):
                raise GcsimOptimizerContractError(
                    "theoretical operation must not carry account database inputs"
                )
            if self.include_2p2p:
                raise GcsimOptimizerContractError(
                    "theoretical package shape is selected by its explicit operation"
                )
        _require_schema(
            self.schema_version,
            GCSIM_OPTIMIZER_PRODUCT_CONTRACT_SCHEMA_VERSION,
            "optimizer operation request",
        )

    def _validate_account_request(
        self,
        pools: tuple[GcsimOptimizerWearerSetPool, ...],
        overrides: tuple[GcsimOptimizerFourStarEligibilityOverride, ...],
        constraints: tuple[GcsimOptimizerMinimumStatConstraint, ...],
    ) -> None:
        _require_enum(self.account_scope, GcsimOptimizerAccountScope, "account_scope")
        _require_sha256(
            self.artifact_database_input_sha256,
            "artifact_database_input_sha256",
        )
        wearers = self.source_simulation.wearers
        if any(item.account_character_id is None for item in wearers):
            raise GcsimOptimizerContractError(
                "account operation requires stable account_character_id for every wearer"
            )
        if self.account_scope is GcsimOptimizerAccountScope.SELECTED_SET_POOLS:
            if tuple(item.wearer for item in pools) != wearers:
                raise GcsimOptimizerContractError(
                    "selected_set_pools must cover all four wearers in team order"
                )
        elif pools:
            raise GcsimOptimizerContractError(
                "all_database_sets scope cannot carry selected_set_pools"
            )
        override_wearers = tuple(item.wearer for item in overrides)
        if len(set(override_wearers)) != len(override_wearers):
            raise GcsimOptimizerContractError(
                "4-star override wearers must be unique"
            )
        if any(item not in wearers for item in override_wearers):
            raise GcsimOptimizerContractError(
                "4-star override wearer is outside the source team"
            )
        constraint_keys = tuple(
            (item.wearer, item.axis_key) for item in constraints
        )
        if len(set(constraint_keys)) != len(constraint_keys):
            raise GcsimOptimizerContractError(
                "minimum-stat wearer/axis pairs must be unique"
            )
        if any(item.wearer not in wearers for item in constraints):
            raise GcsimOptimizerContractError(
                "minimum-stat constraint wearer is outside the source team"
            )
        if self.account_scope is GcsimOptimizerAccountScope.ALL_DATABASE_SETS and any(
            item.allowed_set_uids for item in overrides
        ):
            raise GcsimOptimizerContractError(
                "all_database_sets may authorize 4-star pieces only by explicit artifact ID"
            )
        pool_by_wearer = {item.wearer: item for item in pools}
        for override in overrides:
            if override.allowed_set_uids:
                selected = {
                    item.set_uid for item in pool_by_wearer[override.wearer].allowed_sets
                }
                if not set(override.allowed_set_uids).issubset(selected):
                    raise GcsimOptimizerContractError(
                        "4-star allowed set must belong to that wearer's selected pool"
                    )
        for set_ref in _iter_request_set_refs(pools):
            _validate_set_binding(set_ref, self.source_simulation)

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
            "work_plan": self.work_plan.to_dict(),
            "account_scope": (
                None if self.account_scope is None else self.account_scope.value
            ),
            "selected_set_pools": [
                item.to_dict() for item in self.selected_set_pools
            ],
            "include_2p2p": self.include_2p2p,
            "four_star_overrides": [
                item.to_dict() for item in self.four_star_overrides
            ],
            "minimum_stat_constraints": [
                item.to_dict() for item in self.minimum_stat_constraints
            ],
            "artifact_database_input_sha256": (
                self.artifact_database_input_sha256
            ),
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
        _require_positive_int(self.iterations, "iterations")

    def to_dict(self) -> dict[str, object]:
        return {
            "dps_mean": float(self.dps_mean),
            "dps_se": None if self.dps_se is None else float(self.dps_se),
            "iterations": self.iterations,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerEvaluationIdentity:
    request_sha256: str
    source_simulation_sha256: str
    work_plan_sha256: str
    engine_binding_sha256: str
    compiled_config_sha256: str
    execution_identity_sha256: str

    def __post_init__(self) -> None:
        for field_name in (
            "request_sha256",
            "source_simulation_sha256",
            "work_plan_sha256",
            "engine_binding_sha256",
            "compiled_config_sha256",
            "execution_identity_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "request_sha256": self.request_sha256,
            "source_simulation_sha256": self.source_simulation_sha256,
            "work_plan_sha256": self.work_plan_sha256,
            "engine_binding_sha256": self.engine_binding_sha256,
            "compiled_config_sha256": self.compiled_config_sha256,
            "execution_identity_sha256": self.execution_identity_sha256,
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
    work_plan_sha256: str
    stage: GcsimOptimizerProgressStage
    sequence: int
    completed_work: int
    planned_work: int | None
    elapsed_seconds: float
    remaining_seconds: float | None
    cache_hits: int = 0
    current_best: GcsimOptimizerLeaderSnapshot | None = None
    schema_version: int = GCSIM_OPTIMIZER_PROGRESS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_sha256(self.request_sha256, "request_sha256")
        _require_sha256(self.work_plan_sha256, "work_plan_sha256")
        _require_enum(self.operation, GcsimOptimizerOperation, "progress operation")
        _require_enum(self.stage, GcsimOptimizerProgressStage, "progress stage")
        for field_name in ("sequence", "completed_work", "cache_hits"):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.planned_work is not None:
            _require_non_negative_int(self.planned_work, "planned_work")
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
        _require_schema(
            self.schema_version,
            GCSIM_OPTIMIZER_PROGRESS_SCHEMA_VERSION,
            "optimizer progress",
        )

    @property
    def event_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_sha256": self.request_sha256,
            "operation": self.operation.value,
            "work_plan_sha256": self.work_plan_sha256,
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
class GcsimOptimizerIssue:
    code: str
    scope: GcsimOptimizerIssueScope
    message: str
    wearer: GcsimOptimizerWearerIdentity | None = None
    artifact_id: int | None = None
    package_identity_sha256: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.code, "issue code")
        _require_enum(self.scope, GcsimOptimizerIssueScope, "issue scope")
        _require_trimmed_text(self.message, "issue message")
        if self.wearer is not None and not isinstance(
            self.wearer,
            GcsimOptimizerWearerIdentity,
        ):
            raise GcsimOptimizerContractError("issue wearer must be typed")
        if self.artifact_id is not None:
            _require_positive_int(self.artifact_id, "artifact_id")
        if self.package_identity_sha256 is not None:
            _require_sha256(
                self.package_identity_sha256,
                "package_identity_sha256",
            )
        if (
            self.scope is GcsimOptimizerIssueScope.ARTIFACT
            and self.artifact_id is None
        ):
            raise GcsimOptimizerContractError(
                "artifact issue requires artifact_id"
            )
        if (
            self.scope is GcsimOptimizerIssueScope.PACKAGE
            and self.package_identity_sha256 is None
        ):
            raise GcsimOptimizerContractError(
                "package issue requires package_identity_sha256"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "scope": self.scope.value,
            "message": self.message,
            "wearer": None if self.wearer is None else self.wearer.to_dict(),
            "artifact_id": self.artifact_id,
            "package_identity_sha256": self.package_identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerWearerArtifactAssignment:
    wearer: GcsimOptimizerWearerIdentity
    artifact_ids_by_slot: Mapping[str, int]

    def __post_init__(self) -> None:
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerContractError("assignment wearer must be typed")
        if not isinstance(self.artifact_ids_by_slot, Mapping):
            raise GcsimOptimizerContractError(
                "artifact_ids_by_slot must be a mapping"
            )
        if set(self.artifact_ids_by_slot) != set(GCSIM_OPTIMIZER_ARTIFACT_SLOTS):
            raise GcsimOptimizerContractError(
                "assignment requires exactly flower/plume/sands/goblet/circlet"
            )
        ordered = {
            slot: self.artifact_ids_by_slot[slot]
            for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
        }
        artifact_ids = _validated_artifact_ids(
            ordered.values(),
            "artifact_ids_by_slot",
            allow_empty=False,
        )
        if len(artifact_ids) != 5:
            raise GcsimOptimizerContractError(
                "wearer assignment requires five distinct artifact IDs"
            )
        object.__setattr__(
            self,
            "artifact_ids_by_slot",
            MappingProxyType(ordered),
        )

    @property
    def artifact_ids(self) -> tuple[int, ...]:
        return tuple(
            self.artifact_ids_by_slot[slot]
            for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "wearer": self.wearer.to_dict(),
            "artifact_ids_by_slot": dict(self.artifact_ids_by_slot),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAccountAssignmentWitness:
    request_sha256: str
    artifact_database_input_sha256: str
    wearer_assignments: tuple[GcsimOptimizerWearerArtifactAssignment, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.request_sha256, "request_sha256")
        _require_sha256(
            self.artifact_database_input_sha256,
            "artifact_database_input_sha256",
        )
        rows = tuple(self.wearer_assignments)
        if len(rows) != 4 or any(
            not isinstance(item, GcsimOptimizerWearerArtifactAssignment)
            for item in rows
        ):
            raise GcsimOptimizerContractError(
                "account assignment witness requires four typed wearer rows"
            )
        if tuple(item.wearer.team_slot for item in rows) != (1, 2, 3, 4):
            raise GcsimOptimizerContractError(
                "account assignment wearer rows must use canonical team order"
            )
        artifact_ids = tuple(
            artifact_id for row in rows for artifact_id in row.artifact_ids
        )
        if len(set(artifact_ids)) != 20:
            raise GcsimOptimizerContractError(
                "account assignment requires twenty globally distinct artifact IDs"
            )
        object.__setattr__(self, "wearer_assignments", rows)

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "request_sha256": self.request_sha256,
            "artifact_database_input_sha256": (
                self.artifact_database_input_sha256
            ),
            "wearer_assignments": [
                item.to_dict() for item in self.wearer_assignments
            ],
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
        _require_enum(self.label, GcsimOptimizerUncertaintyLabel, "uncertainty label")
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
                    "uncertainty threshold does not match its evidence"
                )
            expected_label = (
                GcsimOptimizerUncertaintyLabel.WITHIN_NOISE
                if self.absolute_delta_to_best <= self.comparison_threshold
                else GcsimOptimizerUncertaintyLabel.SEPARATED
            )
            if self.label is not expected_label:
                raise GcsimOptimizerContractError(
                    "uncertainty label does not match its evidence"
                )
        _require_schema(
            self.schema_version,
            GCSIM_OPTIMIZER_UNCERTAINTY_SCHEMA_VERSION,
            "optimizer uncertainty",
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
    request_sha256: str
    candidate_identity_sha256: str
    evaluation: GcsimOptimizerEvaluationIdentity
    estimate: GcsimOptimizerDpsEstimate
    target_packages: tuple[GcsimOptimizerWearerTarget, ...]
    evidence_sha256: Mapping[str, str]
    account_assignment: GcsimOptimizerAccountAssignmentWitness | None = None
    replacement_witnesses: tuple[
        GcsimOptimizerAccountAssignmentWitness, ...
    ] = ()
    equivalent_assignment_count: int = 1
    has_many_replacements: bool = False
    issues: tuple[GcsimOptimizerIssue, ...] = ()

    def __post_init__(self) -> None:
        _require_sha256(self.request_sha256, "request_sha256")
        _require_sha256(
            self.candidate_identity_sha256,
            "candidate_identity_sha256",
        )
        if not isinstance(self.evaluation, GcsimOptimizerEvaluationIdentity):
            raise GcsimOptimizerContractError("candidate evaluation must be typed")
        if self.evaluation.request_sha256 != self.request_sha256:
            raise GcsimOptimizerContractError(
                "candidate and evaluation request identities differ"
            )
        if not isinstance(self.estimate, GcsimOptimizerDpsEstimate):
            raise GcsimOptimizerContractError("candidate estimate must be typed")
        object.__setattr__(
            self,
            "target_packages",
            _validated_team_targets(self.target_packages),
        )
        object.__setattr__(
            self,
            "evidence_sha256",
            _freeze_sha256_mapping(self.evidence_sha256),
        )
        replacements = tuple(self.replacement_witnesses)
        if any(
            not isinstance(item, GcsimOptimizerAccountAssignmentWitness)
            for item in replacements
        ):
            raise GcsimOptimizerContractError(
                "replacement_witnesses must contain typed assignments"
            )
        if self.account_assignment is not None and not isinstance(
            self.account_assignment,
            GcsimOptimizerAccountAssignmentWitness,
        ):
            raise GcsimOptimizerContractError(
                "account_assignment must be a typed witness"
            )
        if replacements and self.account_assignment is None:
            raise GcsimOptimizerContractError(
                "replacement witnesses require a primary account assignment"
            )
        _require_positive_int(
            self.equivalent_assignment_count,
            "equivalent_assignment_count",
        )
        if self.equivalent_assignment_count < 1 + len(replacements):
            raise GcsimOptimizerContractError(
                "equivalent_assignment_count is below retained witness count"
            )
        if not isinstance(self.has_many_replacements, bool):
            raise GcsimOptimizerContractError(
                "has_many_replacements must be a boolean"
            )
        if self.has_many_replacements != (self.equivalent_assignment_count > 1):
            raise GcsimOptimizerContractError(
                "has_many_replacements must match equivalent_assignment_count"
            )
        witnesses = (
            ()
            if self.account_assignment is None
            else (self.account_assignment,) + replacements
        )
        if len({item.identity_sha256 for item in witnesses}) != len(witnesses):
            raise GcsimOptimizerContractError(
                "assignment witnesses must be unique"
            )
        for witness in witnesses:
            if witness.request_sha256 != self.request_sha256:
                raise GcsimOptimizerContractError(
                    "assignment witness belongs to another request"
                )
        issues = tuple(self.issues)
        if any(not isinstance(item, GcsimOptimizerIssue) for item in issues):
            raise GcsimOptimizerContractError(
                "candidate issues must contain typed issue rows"
            )
        object.__setattr__(self, "replacement_witnesses", replacements)
        object.__setattr__(self, "issues", issues)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerRankedResult:
    rank: int
    request_sha256: str
    candidate_identity_sha256: str
    evaluation: GcsimOptimizerEvaluationIdentity
    estimate: GcsimOptimizerDpsEstimate
    percent_of_best: float | None
    dps_delta_to_best: float
    uncertainty: GcsimOptimizerUncertainty
    target_packages: tuple[GcsimOptimizerWearerTarget, ...]
    evidence_sha256: Mapping[str, str]
    account_assignment: GcsimOptimizerAccountAssignmentWitness | None = None
    replacement_witnesses: tuple[
        GcsimOptimizerAccountAssignmentWitness, ...
    ] = ()
    equivalent_assignment_count: int = 1
    has_many_replacements: bool = False
    issues: tuple[GcsimOptimizerIssue, ...] = ()

    def __post_init__(self) -> None:
        _require_positive_int(self.rank, "rank")
        candidate = GcsimOptimizerCandidateResult(
            request_sha256=self.request_sha256,
            candidate_identity_sha256=self.candidate_identity_sha256,
            evaluation=self.evaluation,
            estimate=self.estimate,
            target_packages=self.target_packages,
            evidence_sha256=self.evidence_sha256,
            account_assignment=self.account_assignment,
            replacement_witnesses=self.replacement_witnesses,
            equivalent_assignment_count=self.equivalent_assignment_count,
            has_many_replacements=self.has_many_replacements,
            issues=self.issues,
        )
        object.__setattr__(self, "target_packages", candidate.target_packages)
        object.__setattr__(self, "evidence_sha256", candidate.evidence_sha256)
        object.__setattr__(
            self,
            "replacement_witnesses",
            candidate.replacement_witnesses,
        )
        object.__setattr__(self, "issues", candidate.issues)
        if self.percent_of_best is not None:
            _require_finite_non_negative(self.percent_of_best, "percent_of_best")
        _require_finite(self.dps_delta_to_best, "dps_delta_to_best")
        if self.dps_delta_to_best > 0:
            raise GcsimOptimizerContractError(
                "dps_delta_to_best cannot be positive"
            )
        if not isinstance(self.uncertainty, GcsimOptimizerUncertainty):
            raise GcsimOptimizerContractError("ranked uncertainty must be typed")

    def to_dict(self) -> dict[str, object]:
        return {
            "rank": self.rank,
            "request_sha256": self.request_sha256,
            "candidate_identity_sha256": self.candidate_identity_sha256,
            "evaluation": self.evaluation.to_dict(),
            "estimate": self.estimate.to_dict(),
            "percent_of_best": (
                None
                if self.percent_of_best is None
                else float(self.percent_of_best)
            ),
            "dps_delta_to_best": float(self.dps_delta_to_best),
            "uncertainty": self.uncertainty.to_dict(),
            "target_packages": [
                item.to_dict() for item in self.target_packages
            ],
            "evidence_sha256": dict(self.evidence_sha256),
            "account_assignment": (
                None
                if self.account_assignment is None
                else self.account_assignment.to_dict()
            ),
            "replacement_witnesses": [
                item.to_dict() for item in self.replacement_witnesses
            ],
            "equivalent_assignment_count": self.equivalent_assignment_count,
            "has_many_replacements": self.has_many_replacements,
            "issues": [item.to_dict() for item in self.issues],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTopN:
    operation: GcsimOptimizerOperation
    entries: tuple[GcsimOptimizerRankedResult, ...] = ()
    confidence_sigma: float = GCSIM_OPTIMIZER_DEFAULT_UNCERTAINTY_SIGMA
    schema_version: int = GCSIM_OPTIMIZER_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_enum(self.operation, GcsimOptimizerOperation, "top-N operation")
        entries = tuple(self.entries)
        object.__setattr__(self, "entries", entries)
        _require_finite_positive(self.confidence_sigma, "confidence_sigma")
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
                self.operation,
                entries,
                confidence_sigma=self.confidence_sigma,
            )
        _require_schema(
            self.schema_version,
            GCSIM_OPTIMIZER_RESULT_SCHEMA_VERSION,
            "optimizer top-N",
        )

    @property
    def best_found(self) -> GcsimOptimizerRankedResult | None:
        return self.entries[0] if self.entries else None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation.value,
            "confidence_sigma": float(self.confidence_sigma),
            "entries": [entry.to_dict() for entry in self.entries],
        }


def build_gcsim_optimizer_top_n(
    candidates: Iterable[GcsimOptimizerCandidateResult],
    *,
    operation: GcsimOptimizerOperation,
    top_n: int | None = None,
    confidence_sigma: float = GCSIM_OPTIMIZER_DEFAULT_UNCERTAINTY_SIGMA,
) -> GcsimOptimizerTopN:
    _require_enum(operation, GcsimOptimizerOperation, "operation")
    if top_n is not None:
        _require_positive_int(top_n, "top_n")
    _require_finite_positive(confidence_sigma, "confidence_sigma")
    values = tuple(candidates)
    if any(not isinstance(item, GcsimOptimizerCandidateResult) for item in values):
        raise GcsimOptimizerContractError(
            "candidates must contain typed candidate results"
        )
    if len({item.candidate_identity_sha256 for item in values}) != len(values):
        raise GcsimOptimizerContractError("candidate identities must be unique")
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
            operation=operation,
            confidence_sigma=confidence_sigma,
        )
    best = ordered[0].estimate
    entries: list[GcsimOptimizerRankedResult] = []
    for index, candidate in enumerate(ordered, start=1):
        delta = float(candidate.estimate.dps_mean) - float(best.dps_mean)
        percent = (
            None
            if operation is GcsimOptimizerOperation.ACCOUNT_ARTIFACTS
            else (
                100.0
                if best.dps_mean == 0
                else float(candidate.estimate.dps_mean)
                / float(best.dps_mean)
                * 100.0
            )
        )
        entries.append(
            GcsimOptimizerRankedResult(
                rank=index,
                request_sha256=candidate.request_sha256,
                candidate_identity_sha256=candidate.candidate_identity_sha256,
                evaluation=candidate.evaluation,
                estimate=candidate.estimate,
                percent_of_best=percent,
                dps_delta_to_best=delta,
                uncertainty=_build_uncertainty(
                    rank=index,
                    estimate=candidate.estimate,
                    best=best,
                    confidence_sigma=confidence_sigma,
                ),
                target_packages=candidate.target_packages,
                evidence_sha256=candidate.evidence_sha256,
                account_assignment=candidate.account_assignment,
                replacement_witnesses=candidate.replacement_witnesses,
                equivalent_assignment_count=(
                    candidate.equivalent_assignment_count
                ),
                has_many_replacements=candidate.has_many_replacements,
                issues=candidate.issues,
            )
        )
    return GcsimOptimizerTopN(
        operation=operation,
        entries=tuple(entries),
        confidence_sigma=confidence_sigma,
    )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerCoverageCounters:
    counters: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "counters",
            _freeze_counter_mapping(self.counters, "coverage"),
        )

    def to_dict(self) -> dict[str, object]:
        return dict(self.counters)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerCacheCounters:
    hits: int = 0
    misses: int = 0

    def __post_init__(self) -> None:
        _require_non_negative_int(self.hits, "cache hits")
        _require_non_negative_int(self.misses, "cache misses")

    def to_dict(self) -> dict[str, object]:
        return {"hits": self.hits, "misses": self.misses}


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTimingCounters:
    stage_seconds: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.stage_seconds, Mapping):
            raise GcsimOptimizerContractError("stage_seconds must be a mapping")
        result: dict[str, float] = {}
        for key, value in sorted(self.stage_seconds.items()):
            _require_identifier(key, "timing stage")
            _require_finite_non_negative(value, f"stage_seconds[{key!r}]")
            result[key] = float(value)
        object.__setattr__(
            self,
            "stage_seconds",
            MappingProxyType(result),
        )

    def to_dict(self) -> dict[str, object]:
        return dict(self.stage_seconds)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTerminalResult:
    request: GcsimOptimizerOperationRequest
    status: GcsimOptimizerTerminalStatus
    stop_reason: str
    elapsed_seconds: float
    top_n: GcsimOptimizerTopN | None = None
    evidence_sha256: Mapping[str, str] = field(default_factory=dict)
    issues: tuple[GcsimOptimizerIssue, ...] = ()
    coverage: GcsimOptimizerCoverageCounters = field(
        default_factory=GcsimOptimizerCoverageCounters
    )
    cache: GcsimOptimizerCacheCounters = field(
        default_factory=GcsimOptimizerCacheCounters
    )
    timing: GcsimOptimizerTimingCounters = field(
        default_factory=GcsimOptimizerTimingCounters
    )
    error: str = ""
    schema_version: int = GCSIM_OPTIMIZER_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.request, GcsimOptimizerOperationRequest):
            raise GcsimOptimizerContractError("terminal result request must be typed")
        _require_enum(self.status, GcsimOptimizerTerminalStatus, "terminal status")
        _require_trimmed_text(self.stop_reason, "stop_reason")
        _require_finite_non_negative(self.elapsed_seconds, "elapsed_seconds")
        top_n = self.top_n
        if top_n is None:
            top_n = GcsimOptimizerTopN(operation=self.request.operation)
            object.__setattr__(self, "top_n", top_n)
        if not isinstance(top_n, GcsimOptimizerTopN):
            raise GcsimOptimizerContractError("terminal top_n must be typed")
        if top_n.operation is not self.request.operation:
            raise GcsimOptimizerContractError(
                "terminal top_n belongs to another operation"
            )
        object.__setattr__(
            self,
            "evidence_sha256",
            _freeze_sha256_mapping(self.evidence_sha256),
        )
        issues = tuple(self.issues)
        if any(not isinstance(item, GcsimOptimizerIssue) for item in issues):
            raise GcsimOptimizerContractError(
                "terminal issues must contain typed issue rows"
            )
        object.__setattr__(self, "issues", issues)
        if not isinstance(self.coverage, GcsimOptimizerCoverageCounters):
            raise GcsimOptimizerContractError("coverage counters must be typed")
        if not isinstance(self.cache, GcsimOptimizerCacheCounters):
            raise GcsimOptimizerContractError("cache counters must be typed")
        if not isinstance(self.timing, GcsimOptimizerTimingCounters):
            raise GcsimOptimizerContractError("timing counters must be typed")
        if not isinstance(self.error, str):
            raise GcsimOptimizerContractError("terminal error must be text")
        if self.status is GcsimOptimizerTerminalStatus.BEST_FOUND:
            if top_n.best_found is None or self.error:
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
                raise GcsimOptimizerContractError("failed requires an error")
        elif top_n.entries or self.error:
            raise GcsimOptimizerContractError(
                "not_ready/no_success require no top-N evidence and no failure error"
            )
        _validate_result_entries(self.request, top_n.entries)
        _require_schema(
            self.schema_version,
            GCSIM_OPTIMIZER_RESULT_SCHEMA_VERSION,
            "optimizer result",
        )

    @property
    def best_found(self) -> GcsimOptimizerRankedResult | None:
        assert self.top_n is not None
        return self.top_n.best_found

    @property
    def result_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        assert self.top_n is not None
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
            "issues": [item.to_dict() for item in self.issues],
            "coverage": self.coverage.to_dict(),
            "cache": self.cache.to_dict(),
            "timing": self.timing.to_dict(),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerResultAdapter:
    """Serialized projection plus the untouched richer source evidence graph."""

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
    """Project the existing theoretical 4p request into current schema."""

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
    pair_mode = bool(request.automatic_request.two_plus_two_packages)
    operation = (
        GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO
        if pair_mode
        else GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE
    )
    work_plan = GcsimOptimizerWorkPlan(
        operation=operation,
        plan_id=(
            GCSIM_OPTIMIZED_PAIR_ADVISOR_WORK_PLAN_ID
            if pair_mode
            else GCSIM_OPTIMIZED_ADVISOR_WORK_PLAN_ID
        ),
        plan_version=(
            GCSIM_OPTIMIZED_PAIR_ADVISOR_WORK_PLAN_VERSION
            if pair_mode
            else GCSIM_OPTIMIZED_ADVISOR_WORK_PLAN_VERSION
        ),
        parameters=_optimized_advisor_work_plan_payload(request),
    )
    return GcsimOptimizerOperationRequest(
        operation=operation,
        source_simulation=source,
        work_plan=work_plan,
    )


def adapt_gcsim_optimized_four_piece_result(
    source_result: object,
    *,
    finalist_override: object | None = None,
    elapsed_seconds_override: float | None = None,
) -> GcsimOptimizerResultAdapter:
    """Expose the current 4p result as a non-lossless serialized projection."""

    from .farming_optimized_advisor import (
        GcsimOptimizedAdvisorResult,
        GcsimOptimizedAdvisorStatus,
    )
    from .farming_finalist_optimizer import GcsimFinalistOptimizerResult

    if not isinstance(source_result, GcsimOptimizedAdvisorResult):
        raise GcsimOptimizerContractError(
            "source_result must be a GcsimOptimizedAdvisorResult"
        )
    request = build_gcsim_optimized_four_piece_operation_request(
        source_result.request_snapshot
    )
    wearer_by_key = {
        item.gcsim_character_key: item
        for item in request.source_simulation.wearers
    }
    candidates: list[GcsimOptimizerCandidateResult] = []
    original_finalist = source_result.finalist
    finalist = original_finalist
    if finalist_override is not None:
        if not isinstance(finalist_override, GcsimFinalistOptimizerResult):
            raise GcsimOptimizerContractError(
                "finalist_override must be typed finalist evidence"
            )
        if finalist is None:
            raise GcsimOptimizerContractError(
                "rerace evidence requires original finalist evidence"
            )
        original_request = finalist.request_snapshot
        rerace_request = finalist_override.request_snapshot
        if (
            rerace_request.engine_context != original_request.engine_context
            or rerace_request.prepared_config_text
            != original_request.prepared_config_text
            or rerace_request.wearer_ids != original_request.wearer_ids
            or rerace_request.layout_catalog != original_request.layout_catalog
            or rerace_request.optimizer_options
            != original_request.optimizer_options
            or rerace_request.two_plus_two_packages
            != original_request.two_plus_two_packages
            or not set(rerace_request.finalists).issubset(
                set(original_request.finalists)
            )
            or rerace_request.budget.validation_iterations
            <= original_request.budget.validation_iterations
        ):
            raise GcsimOptimizerContractError(
                "rerace finalist evidence does not refine the original domain"
            )
        finalist = finalist_override
    if finalist is not None:
        for outcome in finalist.outcomes:
            pair_packages = (
                source_result.request_snapshot.automatic_request.two_plus_two_packages
            )
            targets = tuple(
                GcsimOptimizerWearerTarget(
                    wearer=wearer_by_key[choice.wearer_id],
                    package=(
                        pair_packages[choice.set_key]
                        if choice.set_key in pair_packages
                        else GcsimFourPieceTargetPackage(
                            set_ref=GcsimOptimizerSetReference(
                                set_uid=choice.set_key,
                                gcsim_set_key=choice.set_key,
                                engine_binding_sha256=(
                                    request.source_simulation.engine_binding_sha256
                                ),
                                catalog_fingerprint=(
                                    request.source_simulation.catalog_fingerprint
                                ),
                            )
                        )
                    ),
                )
                for choice in outcome.state.choices
            )
            candidate_identity = _canonical_sha256(
                {
                    "operation": request.operation.value,
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
                    request_sha256=request.request_sha256,
                    candidate_identity_sha256=candidate_identity,
                    evaluation=GcsimOptimizerEvaluationIdentity(
                        request_sha256=request.request_sha256,
                        source_simulation_sha256=(
                            request.source_simulation.identity_sha256
                        ),
                        work_plan_sha256=request.work_plan.identity_sha256,
                        engine_binding_sha256=(
                            request.source_simulation.engine_binding_sha256
                        ),
                        compiled_config_sha256=(
                            outcome.optimized_config_sha256
                        ),
                        execution_identity_sha256=(
                            outcome.cache_identity_sha256
                        ),
                    ),
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
        "source_config": request.source_simulation.prepared_config_sha256,
    }
    if finalist is not None:
        result_evidence.update(
            {
                "budget": finalist.budget_sha256,
                "finalist_domain": finalist.finalist_domain_sha256,
                "finalist_request": (
                    original_finalist.request_sha256
                    if original_finalist is not None
                    else finalist.request_sha256
                ),
                "layout_catalog": finalist.layout_catalog_sha256,
                "validation_config": finalist.validation_config_sha256,
            }
        )
        if finalist_override is not None:
            result_evidence["rerace_request"] = finalist.request_sha256
    terminal_elapsed_seconds = (
        source_result.elapsed_seconds
        if elapsed_seconds_override is None
        else elapsed_seconds_override
    )
    contract = GcsimOptimizerTerminalResult(
        request=request,
        status=status,
        stop_reason=source_result.stop_reason,
        elapsed_seconds=terminal_elapsed_seconds,
        top_n=build_gcsim_optimizer_top_n(
            candidates,
            operation=request.operation,
            top_n=source_result.request_snapshot.finalist_budget.top_n,
        ),
        evidence_sha256=result_evidence,
        error=source_result.error,
    )
    return GcsimOptimizerResultAdapter(
        contract=contract,
        source_evidence=source_result,
    )


def canonical_gcsim_optimizer_json(value: object) -> str:
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        value = value.to_dict()
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def parse_gcsim_optimizer_operation_request(
    value: str | bytes | Mapping[str, object],
) -> GcsimOptimizerOperationRequest:
    payload = _parse_payload(value, "optimizer operation request")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "operation",
            "cache_namespace",
            "provenance_namespace",
            "source_simulation",
            "work_plan",
            "account_scope",
            "selected_set_pools",
            "include_2p2p",
            "four_star_overrides",
            "minimum_stat_constraints",
            "artifact_database_input_sha256",
        },
        "optimizer operation request",
    )
    _require_schema(
        payload["schema_version"],
        GCSIM_OPTIMIZER_PRODUCT_CONTRACT_SCHEMA_VERSION,
        "optimizer operation request",
    )
    operation = _parse_enum(
        GcsimOptimizerOperation,
        payload["operation"],
        "operation",
    )
    expected_contract = get_gcsim_optimizer_operation_contract(operation)
    if payload["cache_namespace"] != expected_contract.cache_namespace:
        raise GcsimOptimizerContractError("request cache_namespace is invalid")
    if payload["provenance_namespace"] != expected_contract.provenance_namespace:
        raise GcsimOptimizerContractError("request provenance_namespace is invalid")
    scope = (
        None
        if payload["account_scope"] is None
        else _parse_enum(
            GcsimOptimizerAccountScope,
            payload["account_scope"],
            "account_scope",
        )
    )
    return GcsimOptimizerOperationRequest(
        operation=operation,
        source_simulation=_parse_source_simulation(payload["source_simulation"]),
        work_plan=_parse_work_plan(payload["work_plan"]),
        account_scope=scope,
        selected_set_pools=tuple(
            _parse_wearer_set_pool(item)
            for item in _require_list(
                payload["selected_set_pools"],
                "selected_set_pools",
            )
        ),
        include_2p2p=payload["include_2p2p"],
        four_star_overrides=tuple(
            _parse_four_star_override(item)
            for item in _require_list(
                payload["four_star_overrides"],
                "four_star_overrides",
            )
        ),
        minimum_stat_constraints=tuple(
            _parse_minimum_stat_constraint(item)
            for item in _require_list(
                payload["minimum_stat_constraints"],
                "minimum_stat_constraints",
            )
        ),
        artifact_database_input_sha256=payload[
            "artifact_database_input_sha256"
        ],
        schema_version=payload["schema_version"],
    )


def parse_gcsim_optimizer_progress_event(
    value: str | bytes | Mapping[str, object],
) -> GcsimOptimizerProgressEvent:
    payload = _parse_payload(value, "optimizer progress event")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "request_sha256",
            "operation",
            "work_plan_sha256",
            "stage",
            "sequence",
            "completed_work",
            "planned_work",
            "elapsed_seconds",
            "remaining_seconds",
            "cache_hits",
            "current_best",
        },
        "optimizer progress event",
    )
    current_best_payload = payload["current_best"]
    current_best = None
    if current_best_payload is not None:
        item = _require_mapping(current_best_payload, "current_best")
        _require_exact_keys(
            item,
            {"candidate_identity_sha256", "estimate"},
            "current_best",
        )
        current_best = GcsimOptimizerLeaderSnapshot(
            candidate_identity_sha256=item["candidate_identity_sha256"],
            estimate=_parse_estimate(item["estimate"]),
        )
    return GcsimOptimizerProgressEvent(
        request_sha256=payload["request_sha256"],
        operation=_parse_enum(
            GcsimOptimizerOperation,
            payload["operation"],
            "operation",
        ),
        work_plan_sha256=payload["work_plan_sha256"],
        stage=_parse_enum(
            GcsimOptimizerProgressStage,
            payload["stage"],
            "stage",
        ),
        sequence=payload["sequence"],
        completed_work=payload["completed_work"],
        planned_work=payload["planned_work"],
        elapsed_seconds=payload["elapsed_seconds"],
        remaining_seconds=payload["remaining_seconds"],
        cache_hits=payload["cache_hits"],
        current_best=current_best,
        schema_version=payload["schema_version"],
    )


def parse_gcsim_optimizer_terminal_result(
    value: str | bytes | Mapping[str, object],
) -> GcsimOptimizerTerminalResult:
    payload = _parse_payload(value, "optimizer terminal result")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "provenance_namespace",
            "request",
            "request_sha256",
            "status",
            "stop_reason",
            "elapsed_seconds",
            "top_n",
            "evidence_sha256",
            "issues",
            "coverage",
            "cache",
            "timing",
            "error",
        },
        "optimizer terminal result",
    )
    request = parse_gcsim_optimizer_operation_request(
        _require_mapping(payload["request"], "request")
    )
    if payload["request_sha256"] != request.request_sha256:
        raise GcsimOptimizerContractError(
            "serialized terminal request_sha256 mismatch"
        )
    if payload["provenance_namespace"] != request.provenance_namespace:
        raise GcsimOptimizerContractError(
            "serialized terminal provenance_namespace mismatch"
        )
    cache_payload = _require_mapping(payload["cache"], "cache")
    _require_exact_keys(cache_payload, {"hits", "misses"}, "cache")
    return GcsimOptimizerTerminalResult(
        request=request,
        status=_parse_enum(
            GcsimOptimizerTerminalStatus,
            payload["status"],
            "status",
        ),
        stop_reason=payload["stop_reason"],
        elapsed_seconds=payload["elapsed_seconds"],
        top_n=_parse_top_n(payload["top_n"]),
        evidence_sha256=_require_mapping(
            payload["evidence_sha256"],
            "evidence_sha256",
        ),
        issues=tuple(
            _parse_issue(item)
            for item in _require_list(payload["issues"], "issues")
        ),
        coverage=GcsimOptimizerCoverageCounters(
            counters=_require_mapping(payload["coverage"], "coverage")
        ),
        cache=GcsimOptimizerCacheCounters(
            hits=cache_payload["hits"],
            misses=cache_payload["misses"],
        ),
        timing=GcsimOptimizerTimingCounters(
            stage_seconds=_require_mapping(payload["timing"], "timing")
        ),
        error=payload["error"],
        schema_version=payload["schema_version"],
    )


def _optimized_advisor_work_plan_payload(request: object) -> dict[str, object]:
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
            "two_plus_two_packages": {
                key: value.to_dict()
                for key, value in automatic.two_plus_two_packages.items()
            },
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
    operation: GcsimOptimizerOperation,
    entries: tuple[GcsimOptimizerRankedResult, ...],
    *,
    confidence_sigma: float,
) -> None:
    best = entries[0].estimate
    for entry in entries:
        expected_percent = (
            None
            if operation is GcsimOptimizerOperation.ACCOUNT_ARTIFACTS
            else (
                100.0
                if best.dps_mean == 0
                else float(entry.estimate.dps_mean)
                / float(best.dps_mean)
                * 100.0
            )
        )
        expected_delta = float(entry.estimate.dps_mean) - float(best.dps_mean)
        expected_uncertainty = _build_uncertainty(
            rank=entry.rank,
            estimate=entry.estimate,
            best=best,
            confidence_sigma=confidence_sigma,
        )
        if expected_percent is None:
            if entry.percent_of_best is not None:
                raise GcsimOptimizerContractError(
                    "account top-N must not carry percent_of_best"
                )
        elif entry.percent_of_best is None or not math.isclose(
            entry.percent_of_best,
            expected_percent,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise GcsimOptimizerContractError(
                "theoretical top-N percent_of_best is inconsistent"
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
        if entry.uncertainty != expected_uncertainty:
            raise GcsimOptimizerContractError(
                "top-N uncertainty is inconsistent"
            )


def _validate_result_entries(
    request: GcsimOptimizerOperationRequest,
    entries: tuple[GcsimOptimizerRankedResult, ...],
) -> None:
    wearers = request.source_simulation.wearers
    for entry in entries:
        if entry.request_sha256 != request.request_sha256:
            raise GcsimOptimizerContractError(
                "candidate belongs to another request"
            )
        evaluation = entry.evaluation
        if (
            evaluation.request_sha256 != request.request_sha256
            or evaluation.source_simulation_sha256
            != request.source_simulation.identity_sha256
            or evaluation.work_plan_sha256 != request.work_plan.identity_sha256
            or evaluation.engine_binding_sha256
            != request.source_simulation.engine_binding_sha256
        ):
            raise GcsimOptimizerContractError(
                "candidate evaluation does not match its request"
            )
        if tuple(item.wearer for item in entry.target_packages) != wearers:
            raise GcsimOptimizerContractError(
                "result targets do not match source wearer order"
            )
        for target in entry.target_packages:
            for set_ref in _package_set_refs(target.package):
                _validate_set_binding(set_ref, request.source_simulation)
        packages = tuple(item.package for item in entry.target_packages)
        if request.operation is GcsimOptimizerOperation.THEORETICAL_FOUR_PIECE:
            if any(
                not isinstance(item, GcsimFourPieceTargetPackage)
                for item in packages
            ):
                raise GcsimOptimizerContractError(
                    "theoretical 4p results may contain only 4p packages"
                )
            _require_theoretical_candidate(entry)
        elif (
            request.operation
            is GcsimOptimizerOperation.THEORETICAL_TWO_PLUS_TWO
        ):
            if any(
                not isinstance(item, GcsimTwoPlusTwoTargetPackage)
                for item in packages
            ):
                raise GcsimOptimizerContractError(
                    "theoretical 2p+2p results may contain only 2p+2p packages"
                )
            _require_theoretical_candidate(entry)
        else:
            _validate_account_candidate(request, entry)


def _require_theoretical_candidate(entry: GcsimOptimizerRankedResult) -> None:
    if (
        entry.account_assignment is not None
        or entry.replacement_witnesses
        or entry.equivalent_assignment_count != 1
        or entry.has_many_replacements
    ):
        raise GcsimOptimizerContractError(
            "theoretical result must not carry physical account assignments"
        )


def _validate_account_candidate(
    request: GcsimOptimizerOperationRequest,
    entry: GcsimOptimizerRankedResult,
) -> None:
    witness = entry.account_assignment
    if witness is None:
        raise GcsimOptimizerContractError(
            "successful account candidate requires a complete 4x5 assignment witness"
        )
    if (
        witness.request_sha256 != request.request_sha256
        or witness.artifact_database_input_sha256
        != request.artifact_database_input_sha256
        or tuple(item.wearer for item in witness.wearer_assignments)
        != request.source_simulation.wearers
    ):
        raise GcsimOptimizerContractError(
            "account assignment witness does not match its request"
        )
    for replacement in entry.replacement_witnesses:
        if (
            replacement.artifact_database_input_sha256
            != request.artifact_database_input_sha256
            or tuple(item.wearer for item in replacement.wearer_assignments)
            != request.source_simulation.wearers
        ):
            raise GcsimOptimizerContractError(
                "replacement witness does not match its request"
            )
    if request.account_scope is GcsimOptimizerAccountScope.SELECTED_SET_POOLS:
        allowed_by_wearer = {
            item.wearer: {set_ref.set_uid for set_ref in item.allowed_sets}
            for item in request.selected_set_pools
        }
        for target in entry.target_packages:
            package = target.package
            if isinstance(package, GcsimTwoPlusTwoTargetPackage):
                if not request.include_2p2p:
                    raise GcsimOptimizerContractError(
                        "account 2p+2p result requires include_2p2p"
                    )
            if any(
                item.set_uid not in allowed_by_wearer[target.wearer]
                for item in _package_set_refs(package)
            ):
                raise GcsimOptimizerContractError(
                    "account result uses a set outside its selected pool"
                )
    elif not request.include_2p2p and any(
        isinstance(item, GcsimTwoPlusTwoTargetPackage) for item in (
            target.package for target in entry.target_packages
        )
    ):
        raise GcsimOptimizerContractError(
            "account 2p+2p result requires include_2p2p"
        )


def _parse_source_simulation(value: object) -> GcsimOptimizerSourceSimulationIdentity:
    payload = _require_mapping(value, "source_simulation")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "engine_id",
            "engine_version",
            "optimizer_contract_version",
            "artifact_sha256",
            "engine_tree_sha256",
            "engine_binding_sha256",
            "catalog_fingerprint",
            "prepared_config_sha256",
            "rotation_sha256",
            "target_sha256",
            "simulation_options_sha256",
            "wearers",
        },
        "source_simulation",
    )
    return GcsimOptimizerSourceSimulationIdentity(
        engine_id=payload["engine_id"],
        engine_version=payload["engine_version"],
        optimizer_contract_version=payload["optimizer_contract_version"],
        artifact_sha256=payload["artifact_sha256"],
        engine_tree_sha256=payload["engine_tree_sha256"],
        engine_binding_sha256=payload["engine_binding_sha256"],
        catalog_fingerprint=payload["catalog_fingerprint"],
        prepared_config_sha256=payload["prepared_config_sha256"],
        rotation_sha256=payload["rotation_sha256"],
        target_sha256=payload["target_sha256"],
        simulation_options_sha256=payload["simulation_options_sha256"],
        wearers=tuple(
            _parse_wearer(item)
            for item in _require_list(payload["wearers"], "wearers")
        ),
        schema_version=payload["schema_version"],
    )


def _parse_work_plan(value: object) -> GcsimOptimizerWorkPlan:
    payload = _require_mapping(value, "work_plan")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "operation",
            "plan_id",
            "plan_version",
            "parameters",
        },
        "work_plan",
    )
    return GcsimOptimizerWorkPlan(
        operation=_parse_enum(
            GcsimOptimizerOperation,
            payload["operation"],
            "work plan operation",
        ),
        plan_id=payload["plan_id"],
        plan_version=payload["plan_version"],
        parameters=_require_mapping(payload["parameters"], "parameters"),
        schema_version=payload["schema_version"],
    )


def _parse_wearer(value: object) -> GcsimOptimizerWearerIdentity:
    payload = _require_mapping(value, "wearer")
    _require_exact_keys(
        payload,
        {"team_slot", "account_character_id", "gcsim_character_key"},
        "wearer",
    )
    return GcsimOptimizerWearerIdentity(
        team_slot=payload["team_slot"],
        account_character_id=payload["account_character_id"],
        gcsim_character_key=payload["gcsim_character_key"],
    )


def _parse_set_ref(value: object) -> GcsimOptimizerSetReference:
    payload = _require_mapping(value, "set reference")
    _require_exact_keys(
        payload,
        {
            "set_uid",
            "gcsim_set_key",
            "engine_binding_sha256",
            "catalog_fingerprint",
            "set_parameters",
        },
        "set reference",
    )
    return GcsimOptimizerSetReference(
        set_uid=payload["set_uid"],
        gcsim_set_key=payload["gcsim_set_key"],
        engine_binding_sha256=payload["engine_binding_sha256"],
        catalog_fingerprint=payload["catalog_fingerprint"],
        set_parameters=_require_mapping(payload["set_parameters"], "set_parameters"),
    )


def _parse_package(value: object) -> GcsimOptimizerTargetPackage:
    payload = _require_mapping(value, "target package")
    kind = _parse_enum(
        GcsimOptimizerTargetPackageKind,
        payload.get("kind"),
        "target package kind",
    )
    if kind is GcsimOptimizerTargetPackageKind.FOUR_PIECE:
        _require_exact_keys(
            payload,
            {"schema_version", "kind", "set"},
            "4p target package",
        )
        return GcsimFourPieceTargetPackage(
            set_ref=_parse_set_ref(payload["set"]),
            schema_version=payload["schema_version"],
        )
    _require_exact_keys(
        payload,
        {"schema_version", "kind", "sets"},
        "2p+2p target package",
    )
    sets = _require_list(payload["sets"], "sets")
    if len(sets) != 2:
        raise GcsimOptimizerContractError(
            "2p+2p target package requires two sets"
        )
    return GcsimTwoPlusTwoTargetPackage(
        set_a=_parse_set_ref(sets[0]),
        set_b=_parse_set_ref(sets[1]),
        schema_version=payload["schema_version"],
    )


def _parse_wearer_target(value: object) -> GcsimOptimizerWearerTarget:
    payload = _require_mapping(value, "wearer target")
    _require_exact_keys(payload, {"wearer", "package"}, "wearer target")
    return GcsimOptimizerWearerTarget(
        wearer=_parse_wearer(payload["wearer"]),
        package=_parse_package(payload["package"]),
    )


def _parse_wearer_set_pool(value: object) -> GcsimOptimizerWearerSetPool:
    payload = _require_mapping(value, "wearer set pool")
    _require_exact_keys(
        payload,
        {"wearer", "allowed_sets"},
        "wearer set pool",
    )
    return GcsimOptimizerWearerSetPool(
        wearer=_parse_wearer(payload["wearer"]),
        allowed_sets=tuple(
            _parse_set_ref(item)
            for item in _require_list(payload["allowed_sets"], "allowed_sets")
        ),
    )


def _parse_four_star_override(
    value: object,
) -> GcsimOptimizerFourStarEligibilityOverride:
    payload = _require_mapping(value, "4-star override")
    _require_exact_keys(
        payload,
        {"wearer", "allowed_set_uids", "allowed_artifact_ids"},
        "4-star override",
    )
    return GcsimOptimizerFourStarEligibilityOverride(
        wearer=_parse_wearer(payload["wearer"]),
        allowed_set_uids=tuple(
            _require_list(payload["allowed_set_uids"], "allowed_set_uids")
        ),
        allowed_artifact_ids=tuple(
            _require_list(
                payload["allowed_artifact_ids"],
                "allowed_artifact_ids",
            )
        ),
    )


def _parse_minimum_stat_constraint(
    value: object,
) -> GcsimOptimizerMinimumStatConstraint:
    payload = _require_mapping(value, "minimum-stat constraint")
    _require_exact_keys(
        payload,
        {"wearer", "axis_key", "minimum", "stat_space"},
        "minimum-stat constraint",
    )
    if payload["stat_space"] != "static_build_contribution":
        raise GcsimOptimizerContractError(
            "minimum-stat stat_space must be static_build_contribution"
        )
    return GcsimOptimizerMinimumStatConstraint(
        wearer=_parse_wearer(payload["wearer"]),
        axis_key=payload["axis_key"],
        minimum=payload["minimum"],
    )


def _parse_estimate(value: object) -> GcsimOptimizerDpsEstimate:
    payload = _require_mapping(value, "DPS estimate")
    _require_exact_keys(
        payload,
        {"dps_mean", "dps_se", "iterations"},
        "DPS estimate",
    )
    return GcsimOptimizerDpsEstimate(
        dps_mean=payload["dps_mean"],
        dps_se=payload["dps_se"],
        iterations=payload["iterations"],
    )


def _parse_evaluation(value: object) -> GcsimOptimizerEvaluationIdentity:
    payload = _require_mapping(value, "evaluation")
    keys = {
        "request_sha256",
        "source_simulation_sha256",
        "work_plan_sha256",
        "engine_binding_sha256",
        "compiled_config_sha256",
        "execution_identity_sha256",
    }
    _require_exact_keys(payload, keys, "evaluation")
    return GcsimOptimizerEvaluationIdentity(
        **{key: payload[key] for key in keys}
    )


def _parse_issue(value: object) -> GcsimOptimizerIssue:
    payload = _require_mapping(value, "issue")
    _require_exact_keys(
        payload,
        {
            "code",
            "scope",
            "message",
            "wearer",
            "artifact_id",
            "package_identity_sha256",
        },
        "issue",
    )
    return GcsimOptimizerIssue(
        code=payload["code"],
        scope=_parse_enum(
            GcsimOptimizerIssueScope,
            payload["scope"],
            "issue scope",
        ),
        message=payload["message"],
        wearer=(
            None
            if payload["wearer"] is None
            else _parse_wearer(payload["wearer"])
        ),
        artifact_id=payload["artifact_id"],
        package_identity_sha256=payload["package_identity_sha256"],
    )


def _parse_assignment(
    value: object,
) -> GcsimOptimizerAccountAssignmentWitness:
    payload = _require_mapping(value, "account assignment")
    _require_exact_keys(
        payload,
        {
            "request_sha256",
            "artifact_database_input_sha256",
            "wearer_assignments",
        },
        "account assignment",
    )
    rows: list[GcsimOptimizerWearerArtifactAssignment] = []
    for item in _require_list(
        payload["wearer_assignments"],
        "wearer_assignments",
    ):
        row = _require_mapping(item, "wearer assignment")
        _require_exact_keys(
            row,
            {"wearer", "artifact_ids_by_slot"},
            "wearer assignment",
        )
        rows.append(
            GcsimOptimizerWearerArtifactAssignment(
                wearer=_parse_wearer(row["wearer"]),
                artifact_ids_by_slot=_require_mapping(
                    row["artifact_ids_by_slot"],
                    "artifact_ids_by_slot",
                ),
            )
        )
    return GcsimOptimizerAccountAssignmentWitness(
        request_sha256=payload["request_sha256"],
        artifact_database_input_sha256=payload[
            "artifact_database_input_sha256"
        ],
        wearer_assignments=tuple(rows),
    )


def _parse_uncertainty(value: object) -> GcsimOptimizerUncertainty:
    payload = _require_mapping(value, "uncertainty")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "label",
            "confidence_sigma",
            "absolute_delta_to_best",
            "combined_standard_error",
            "comparison_threshold",
        },
        "uncertainty",
    )
    return GcsimOptimizerUncertainty(
        label=_parse_enum(
            GcsimOptimizerUncertaintyLabel,
            payload["label"],
            "uncertainty label",
        ),
        confidence_sigma=payload["confidence_sigma"],
        absolute_delta_to_best=payload["absolute_delta_to_best"],
        combined_standard_error=payload["combined_standard_error"],
        comparison_threshold=payload["comparison_threshold"],
        schema_version=payload["schema_version"],
    )


def _parse_ranked_result(value: object) -> GcsimOptimizerRankedResult:
    payload = _require_mapping(value, "ranked result")
    _require_exact_keys(
        payload,
        {
            "rank",
            "request_sha256",
            "candidate_identity_sha256",
            "evaluation",
            "estimate",
            "percent_of_best",
            "dps_delta_to_best",
            "uncertainty",
            "target_packages",
            "evidence_sha256",
            "account_assignment",
            "replacement_witnesses",
            "equivalent_assignment_count",
            "has_many_replacements",
            "issues",
        },
        "ranked result",
    )
    return GcsimOptimizerRankedResult(
        rank=payload["rank"],
        request_sha256=payload["request_sha256"],
        candidate_identity_sha256=payload["candidate_identity_sha256"],
        evaluation=_parse_evaluation(payload["evaluation"]),
        estimate=_parse_estimate(payload["estimate"]),
        percent_of_best=payload["percent_of_best"],
        dps_delta_to_best=payload["dps_delta_to_best"],
        uncertainty=_parse_uncertainty(payload["uncertainty"]),
        target_packages=tuple(
            _parse_wearer_target(item)
            for item in _require_list(
                payload["target_packages"],
                "target_packages",
            )
        ),
        evidence_sha256=_require_mapping(
            payload["evidence_sha256"],
            "evidence_sha256",
        ),
        account_assignment=(
            None
            if payload["account_assignment"] is None
            else _parse_assignment(payload["account_assignment"])
        ),
        replacement_witnesses=tuple(
            _parse_assignment(item)
            for item in _require_list(
                payload["replacement_witnesses"],
                "replacement_witnesses",
            )
        ),
        equivalent_assignment_count=payload["equivalent_assignment_count"],
        has_many_replacements=payload["has_many_replacements"],
        issues=tuple(
            _parse_issue(item)
            for item in _require_list(payload["issues"], "issues")
        ),
    )


def _parse_top_n(value: object) -> GcsimOptimizerTopN:
    payload = _require_mapping(value, "top_n")
    _require_exact_keys(
        payload,
        {"schema_version", "operation", "confidence_sigma", "entries"},
        "top_n",
    )
    return GcsimOptimizerTopN(
        operation=_parse_enum(
            GcsimOptimizerOperation,
            payload["operation"],
            "top-N operation",
        ),
        entries=tuple(
            _parse_ranked_result(item)
            for item in _require_list(payload["entries"], "entries")
        ),
        confidence_sigma=payload["confidence_sigma"],
        schema_version=payload["schema_version"],
    )


def _validated_wearers(
    values: Iterable[GcsimOptimizerWearerIdentity],
) -> tuple[GcsimOptimizerWearerIdentity, ...]:
    if isinstance(values, (str, bytes)):
        raise GcsimOptimizerContractError("wearers must be a sequence")
    try:
        wearers = tuple(values)
    except TypeError as exc:
        raise GcsimOptimizerContractError("wearers must be iterable") from exc
    if not wearers or len(wearers) > 4 or any(
        not isinstance(item, GcsimOptimizerWearerIdentity) for item in wearers
    ):
        raise GcsimOptimizerContractError(
            "source identity requires one to four typed wearers"
        )
    if tuple(item.team_slot for item in wearers) != tuple(
        range(1, len(wearers) + 1)
    ):
        raise GcsimOptimizerContractError(
            "source wearer identities must use canonical team-slot order"
        )
    if len({item.gcsim_character_key for item in wearers}) != len(wearers):
        raise GcsimOptimizerContractError(
            "source GCSIM character keys must be unique"
        )
    account_ids = tuple(
        item.account_character_id
        for item in wearers
        if item.account_character_id is not None
    )
    if len(set(account_ids)) != len(account_ids):
        raise GcsimOptimizerContractError(
            "source account character IDs must be unique"
        )
    return wearers


def _validated_team_targets(
    values: Iterable[GcsimOptimizerWearerTarget],
) -> tuple[GcsimOptimizerWearerTarget, ...]:
    if isinstance(values, (str, bytes)):
        raise GcsimOptimizerContractError("target_packages must be a sequence")
    try:
        targets = tuple(values)
    except TypeError as exc:
        raise GcsimOptimizerContractError(
            "target_packages must be iterable"
        ) from exc
    if not targets or len(targets) > 4 or any(
        not isinstance(item, GcsimOptimizerWearerTarget) for item in targets
    ):
        raise GcsimOptimizerContractError(
            "candidate target_packages require one to four typed rows"
        )
    if tuple(item.wearer.team_slot for item in targets) != tuple(
        range(1, len(targets) + 1)
    ):
        raise GcsimOptimizerContractError(
            "candidate target packages must use canonical team order"
        )
    return targets


def _validated_artifact_ids(
    values: Iterable[int],
    field_name: str,
    *,
    allow_empty: bool,
) -> tuple[int, ...]:
    try:
        result = tuple(values)
    except TypeError as exc:
        raise GcsimOptimizerContractError(
            f"{field_name} must be iterable"
        ) from exc
    if not result and not allow_empty:
        raise GcsimOptimizerContractError(f"{field_name} must not be empty")
    for value in result:
        _require_positive_int(value, field_name)
    if len(set(result)) != len(result):
        raise GcsimOptimizerContractError(f"{field_name} must be unique")
    return result


def _iter_request_set_refs(
    pools: Iterable[GcsimOptimizerWearerSetPool],
) -> Iterable[GcsimOptimizerSetReference]:
    for pool in pools:
        yield from pool.allowed_sets


def _package_set_refs(
    package: GcsimOptimizerTargetPackage,
) -> tuple[GcsimOptimizerSetReference, ...]:
    if isinstance(package, GcsimFourPieceTargetPackage):
        return (package.set_ref,)
    return (package.set_a, package.set_b)


def _validate_set_binding(
    set_ref: GcsimOptimizerSetReference,
    source: GcsimOptimizerSourceSimulationIdentity,
) -> None:
    if (
        set_ref.engine_binding_sha256 != source.engine_binding_sha256
        or set_ref.catalog_fingerprint != source.catalog_fingerprint
    ):
        raise GcsimOptimizerContractError(
            "set reference does not match the active engine/catalog binding"
        )


def _require_target_package(value: object) -> None:
    if not isinstance(
        value,
        (GcsimFourPieceTargetPackage, GcsimTwoPlusTwoTargetPackage),
    ):
        raise GcsimOptimizerContractError(
            "package must be typed 4p or 2p+2p"
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


def _freeze_counter_mapping(
    value: Mapping[str, int],
    field_name: str,
) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        raise GcsimOptimizerContractError(f"{field_name} must be a mapping")
    result: dict[str, int] = {}
    for key, item in sorted(value.items()):
        _require_identifier(key, f"{field_name} counter")
        _require_non_negative_int(item, f"{field_name}[{key!r}]")
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
        f"cannot serialize work-plan value of type {type(value).__name__}"
    )


def _parse_payload(
    value: str | bytes | Mapping[str, object],
    field_name: str,
) -> Mapping[str, object]:
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GcsimOptimizerContractError(
                f"{field_name} is not UTF-8"
            ) from exc
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise GcsimOptimizerContractError(
                f"{field_name} is not valid JSON"
            ) from exc
    return _require_mapping(value, field_name)


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GcsimOptimizerContractError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise GcsimOptimizerContractError(
            f"{field_name} object keys must be strings"
        )
    return value


def _require_list(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise GcsimOptimizerContractError(f"{field_name} must be an array")
    return value


def _require_exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    field_name: str,
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise GcsimOptimizerContractError(
            f"{field_name} fields differ; missing={missing}, unknown={unknown}"
        )


def _parse_enum(enum_type: type[Enum], value: object, field_name: str):
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise GcsimOptimizerContractError(
            f"{field_name} has an unsupported value"
        ) from exc


def _require_enum(value: object, enum_type: type[Enum], field_name: str) -> None:
    if not isinstance(value, enum_type):
        raise GcsimOptimizerContractError(f"{field_name} must be typed")


def _require_set_key(value: object) -> None:
    _require_set_key_like(value, "gcsim_set_key")


def _require_set_key_like(value: object, field_name: str) -> None:
    if not isinstance(value, str) or _SET_KEY_RE.fullmatch(value) is None:
        raise GcsimOptimizerContractError(
            f"{field_name} must be a canonical lowercase GCSIM key"
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
    pattern = _DOTTED_IDENTIFIER_RE if dotted else _IDENTIFIER_RE
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


def _require_schema(value: object, expected: int, field_name: str) -> None:
    if value != expected:
        raise GcsimOptimizerContractError(
            f"unsupported {field_name} schema; expected version {expected}"
        )


def _require_positive_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GcsimOptimizerContractError(
            f"{field_name} must be a positive integer"
        )


def _require_non_negative_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GcsimOptimizerContractError(
            f"{field_name} must be a non-negative integer"
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


def _canonical_decimal_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise GcsimOptimizerContractError(
            f"{field_name} must be a finite decimal"
        )
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise GcsimOptimizerContractError(
            f"{field_name} must be a finite decimal"
        ) from exc
    if not decimal.is_finite():
        raise GcsimOptimizerContractError(
            f"{field_name} must be a finite decimal"
        )
    if decimal < 0:
        raise GcsimOptimizerContractError(
            f"{field_name} must be non-negative"
        )
    if decimal == 0:
        return "0"
    text = format(decimal.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        canonical_gcsim_optimizer_json(value).encode("utf-8")
    ).hexdigest()
