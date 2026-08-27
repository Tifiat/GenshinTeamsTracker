"""Strict pure real-artifact materialization for optimizer Milestone 2."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
import json
from types import MappingProxyType

from hoyolab_export.stat_normalization import (
    SOURCE_UNIT_PERCENT_POINTS,
    STAT_MAPPINGS_BY_PROPERTY_TYPE,
)

from .artifact_set_catalog import GcsimArtifactSetCapability
from .optimizer_artifact_database import (
    GcsimOptimizerArtifactRecord,
    evaluate_gcsim_optimizer_artifact_eligibility,
)
from .optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerAccountAssignmentWitness,
    GcsimOptimizerAccountScope,
    GcsimOptimizerSetReference,
    GcsimOptimizerTargetPackage,
    GcsimOptimizerWearerArtifactAssignment,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerTarget,
    GcsimTwoPlusTwoTargetPackage,
)
from .optimizer_run_input import GcsimOptimizerRunInput
from .optimizer_stat_constraints import (
    evaluate_gcsim_optimizer_minimum_stat_constraints,
)


GCSIM_OPTIMIZER_ARTIFACT_MATERIALIZER_SCHEMA_VERSION = 1

OPTIMIZER_MATERIALIZATION_READY = "ready"
OPTIMIZER_MATERIALIZATION_NOT_READY = "not_ready"
OPTIMIZER_DIAGNOSTIC_ERROR = "error"
OPTIMIZER_DIAGNOSTIC_NOTICE = "notice"

_GCSIM_STAT_ORDER = (
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
)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerMaterializationDiagnostic:
    severity: str
    code: str
    message: str
    wearer: GcsimOptimizerWearerIdentity | None = None
    artifact_id: int | None = None
    set_uid: str = ""

    def __post_init__(self) -> None:
        if self.severity not in {
            OPTIMIZER_DIAGNOSTIC_ERROR,
            OPTIMIZER_DIAGNOSTIC_NOTICE,
        }:
            raise ValueError("unsupported materialization severity")

    @property
    def blocking(self) -> bool:
        return self.severity == OPTIMIZER_DIAGNOSTIC_ERROR

    def to_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "wearer": None if self.wearer is None else self.wearer.to_dict(),
            "artifact_id": self.artifact_id,
            "set_uid": self.set_uid,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTargetSetCapabilityValidation:
    """Pure package/capability verdict shared by derivation and materialization."""

    ready: bool
    code: str = ""
    message: str = ""

    def __post_init__(self) -> None:
        if self.ready != (not self.code and not self.message):
            raise ValueError("target set capability validation is incoherent")


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSetParameterValidationIssue:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSetParameterValidation:
    """Normalized renderable parameters under one frozen set capability."""

    parameters: tuple[tuple[str, int], ...]
    defaulted_parameter_keys: tuple[str, ...]
    issues: tuple[GcsimOptimizerSetParameterValidationIssue, ...] = ()

    @property
    def ready(self) -> bool:
        return not self.issues


@dataclass(frozen=True, slots=True)
class GcsimOptimizerMaterializedStatContribution:
    artifact_id: int
    artifact_slot: str
    source_kind: str
    source_slot_index: int | None
    property_type: int
    property_name: str | None
    stored_value: object
    normalized_value: str
    gcsim_key: str

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_slot": self.artifact_slot,
            "source_kind": self.source_kind,
            "source_slot_index": self.source_slot_index,
            "property_type": self.property_type,
            "property_name": self.property_name,
            "stored_value": _json_scalar(self.stored_value),
            "normalized_value": self.normalized_value,
            "gcsim_key": self.gcsim_key,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerArtifactStatVector:
    """Strict exact GCSIM stat projection for one frozen artifact row."""

    artifact_id: int
    artifact_slot: str
    contributions: tuple[GcsimOptimizerMaterializedStatContribution, ...]
    normalized_stats: tuple[tuple[str, str], ...]
    diagnostics: tuple[GcsimOptimizerMaterializationDiagnostic, ...] = ()
    schema_version: int = GCSIM_OPTIMIZER_ARTIFACT_MATERIALIZER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_ARTIFACT_MATERIALIZER_SCHEMA_VERSION:
            raise ValueError("unsupported optimizer artifact stat-vector schema")
        if not self.artifact_slot:
            raise ValueError("artifact_slot must be non-empty")
        if any(item.blocking for item in self.diagnostics):
            raise ValueError("artifact stat vector cannot contain blocking diagnostics")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "artifact_slot": self.artifact_slot,
            "contributions": [item.to_dict() for item in self.contributions],
            "normalized_stats": [list(item) for item in self.normalized_stats],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerArtifactStatVectorResult:
    ready: bool
    stat_vector: GcsimOptimizerArtifactStatVector | None = None
    diagnostics: tuple[GcsimOptimizerMaterializationDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if self.ready != (
            self.stat_vector is not None
            and not any(item.blocking for item in self.diagnostics)
        ):
            raise ValueError("artifact stat-vector readiness is incoherent")

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "stat_vector": (
                None if self.stat_vector is None else self.stat_vector.to_dict()
            ),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerMaterializedSet:
    set_uid: str
    gcsim_set_key: str
    count: int
    set_parameters: Mapping[str, int] = field(default_factory=dict)
    defaulted_parameter_keys: tuple[str, ...] = ()
    rendered_line: str = ""

    def __post_init__(self) -> None:
        if not self.set_uid or self.set_uid != self.set_uid.strip():
            raise ValueError("set_uid must be non-empty trimmed text")
        if (
            isinstance(self.count, bool)
            or not isinstance(self.count, int)
            or self.count < 2
            or self.count > 5
        ):
            raise ValueError("materialized active set count must be 2 through 5")
        object.__setattr__(
            self,
            "set_parameters",
            MappingProxyType(dict(sorted(self.set_parameters.items()))),
        )
        object.__setattr__(
            self,
            "defaulted_parameter_keys",
            tuple(sorted(self.defaulted_parameter_keys)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "set_uid": self.set_uid,
            "gcsim_set_key": self.gcsim_set_key,
            "count": self.count,
            "set_parameters": dict(self.set_parameters),
            "defaulted_parameter_keys": list(self.defaulted_parameter_keys),
            "rendered_line": self.rendered_line,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerMaterializedBuild:
    wearer: GcsimOptimizerWearerIdentity
    assignment: GcsimOptimizerWearerArtifactAssignment
    target: GcsimOptimizerWearerTarget
    artifacts_by_slot: tuple[tuple[str, GcsimOptimizerArtifactRecord], ...]
    stat_contributions: tuple[
        GcsimOptimizerMaterializedStatContribution, ...
    ]
    normalized_stats: tuple[tuple[str, str], ...]
    set_counts: tuple[tuple[str, int], ...]
    active_sets: tuple[GcsimOptimizerMaterializedSet, ...]
    rendered_lines: tuple[str, ...]
    wearer_build_identity_sha256: str
    compiled_block_sha256: str
    diagnostics: tuple[GcsimOptimizerMaterializationDiagnostic, ...] = ()
    schema_version: int = GCSIM_OPTIMIZER_ARTIFACT_MATERIALIZER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_ARTIFACT_MATERIALIZER_SCHEMA_VERSION
        ):
            raise ValueError("unsupported artifact materializer schema")
        _require_sha256(
            self.wearer_build_identity_sha256,
            "wearer_build_identity_sha256",
        )
        _require_sha256(self.compiled_block_sha256, "compiled_block_sha256")
        if tuple(slot for slot, _artifact in self.artifacts_by_slot) != (
            GCSIM_OPTIMIZER_ARTIFACT_SLOTS
        ):
            raise ValueError("materialized artifacts must use canonical slots")
        if any(item.blocking for item in self.diagnostics):
            raise ValueError("ready materialized build cannot contain errors")
        if _sha256_text(self.block_text) != self.compiled_block_sha256:
            raise ValueError("compiled_block_sha256 differs from rendered lines")

    @property
    def block_text(self) -> str:
        return "\n".join(self.rendered_lines)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "wearer": self.wearer.to_dict(),
            "assignment": self.assignment.to_dict(),
            "target": self.target.to_dict(),
            "artifact_ids_by_slot": {
                slot: artifact.artifact_id
                for slot, artifact in self.artifacts_by_slot
            },
            "stat_contributions": [
                item.to_dict() for item in self.stat_contributions
            ],
            "normalized_stats": dict(self.normalized_stats),
            "set_counts": dict(self.set_counts),
            "active_sets": [item.to_dict() for item in self.active_sets],
            "rendered_lines": list(self.rendered_lines),
            "wearer_build_identity_sha256": (
                self.wearer_build_identity_sha256
            ),
            "compiled_block_sha256": self.compiled_block_sha256,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerMaterializedBuildResult:
    status: str
    ready: bool
    build: GcsimOptimizerMaterializedBuild | None = None
    diagnostics: tuple[GcsimOptimizerMaterializationDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        expected_status = (
            OPTIMIZER_MATERIALIZATION_READY
            if self.ready
            else OPTIMIZER_MATERIALIZATION_NOT_READY
        )
        if self.status != expected_status:
            raise ValueError("materialized build status/readiness is incoherent")
        has_errors = any(item.blocking for item in self.diagnostics)
        if self.ready != (self.build is not None and not has_errors):
            raise ValueError("materialized build readiness is incoherent")

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "ready": self.ready,
            "build": None if self.build is None else self.build.to_dict(),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerCompiledTeamCandidate:
    assignment_witness: GcsimOptimizerAccountAssignmentWitness
    targets: tuple[GcsimOptimizerWearerTarget, ...]
    builds: tuple[GcsimOptimizerMaterializedBuild, ...]
    rendered_blocks: tuple[str, ...]
    config_text: str
    compiled_config_sha256: str
    physical_assignment_sha256: str
    candidate_identity_sha256: str
    execution_identity_sha256: str
    simulation_sha256: str
    non_artifact_segments_sha256: str
    replacement_proof_sha256: str
    diagnostics: tuple[GcsimOptimizerMaterializationDiagnostic, ...] = ()
    schema_version: int = GCSIM_OPTIMIZER_ARTIFACT_MATERIALIZER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_ARTIFACT_MATERIALIZER_SCHEMA_VERSION
        ):
            raise ValueError("unsupported compiled candidate schema")
        for field_name in (
            "compiled_config_sha256",
            "physical_assignment_sha256",
            "candidate_identity_sha256",
            "execution_identity_sha256",
            "simulation_sha256",
            "non_artifact_segments_sha256",
            "replacement_proof_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if len(self.builds) != 4 or len(self.rendered_blocks) != 4:
            raise ValueError("compiled team candidate requires four builds")
        if tuple(item.wearer for item in self.targets) != tuple(
            item.wearer for item in self.builds
        ):
            raise ValueError("compiled target/build wearer order differs")
        if any(item.blocking for item in self.diagnostics):
            raise ValueError("compiled candidate cannot contain errors")
        if _sha256_text(self.config_text) != self.compiled_config_sha256:
            raise ValueError("compiled_config_sha256 differs from config_text")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "assignment_witness": self.assignment_witness.to_dict(),
            "targets": [item.to_dict() for item in self.targets],
            "builds": [item.to_dict() for item in self.builds],
            "rendered_blocks": list(self.rendered_blocks),
            "config_text": self.config_text,
            "compiled_config_sha256": self.compiled_config_sha256,
            "physical_assignment_sha256": self.physical_assignment_sha256,
            "candidate_identity_sha256": self.candidate_identity_sha256,
            "execution_identity_sha256": self.execution_identity_sha256,
            "simulation_sha256": self.simulation_sha256,
            "non_artifact_segments_sha256": (
                self.non_artifact_segments_sha256
            ),
            "replacement_proof_sha256": self.replacement_proof_sha256,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerCompiledTeamResult:
    status: str
    ready: bool
    candidate: GcsimOptimizerCompiledTeamCandidate | None = None
    diagnostics: tuple[GcsimOptimizerMaterializationDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        expected_status = (
            OPTIMIZER_MATERIALIZATION_READY
            if self.ready
            else OPTIMIZER_MATERIALIZATION_NOT_READY
        )
        if self.status != expected_status:
            raise ValueError("compiled team status/readiness is incoherent")
        has_errors = any(item.blocking for item in self.diagnostics)
        if self.ready != (self.candidate is not None and not has_errors):
            raise ValueError("compiled team readiness is incoherent")

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "ready": self.ready,
            "candidate": (
                None if self.candidate is None else self.candidate.to_dict()
            ),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSimulationWitnessBucket:
    simulation_sha256: str
    compiled_config_sha256: str
    execution_identity_sha256: str
    stored_witnesses: tuple[GcsimOptimizerAccountAssignmentWitness, ...]
    observed_assignment_count: int
    max_stored_witnesses: int
    schema_version: int = GCSIM_OPTIMIZER_ARTIFACT_MATERIALIZER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_ARTIFACT_MATERIALIZER_SCHEMA_VERSION
        ):
            raise ValueError("unsupported simulation witness schema")
        for field_name in (
            "simulation_sha256",
            "compiled_config_sha256",
            "execution_identity_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if self.max_stored_witnesses <= 0:
            raise ValueError("max_stored_witnesses must be positive")
        if len(self.stored_witnesses) > self.max_stored_witnesses:
            raise ValueError("stored witness bound exceeded")
        identities = tuple(
            item.identity_sha256 for item in self.stored_witnesses
        )
        if len(set(identities)) != len(identities):
            raise ValueError("stored witnesses must be unique")
        if self.observed_assignment_count < len(self.stored_witnesses):
            raise ValueError("observed witness count is incoherent")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "simulation_sha256": self.simulation_sha256,
            "compiled_config_sha256": self.compiled_config_sha256,
            "execution_identity_sha256": self.execution_identity_sha256,
            "stored_witnesses": [
                item.to_dict() for item in self.stored_witnesses
            ],
            "observed_assignment_count": self.observed_assignment_count,
            "max_stored_witnesses": self.max_stored_witnesses,
        }


def validate_gcsim_optimizer_target_set_capability(
    package: GcsimOptimizerTargetPackage,
    capability: GcsimArtifactSetCapability | None,
) -> GcsimOptimizerTargetSetCapabilityValidation:
    """Apply the materializer's modeled-set gate without requiring a run input."""

    if not isinstance(
        package,
        (GcsimFourPieceTargetPackage, GcsimTwoPlusTwoTargetPackage),
    ):
        raise TypeError("package must be a typed optimizer target package")
    if capability is not None and not isinstance(
        capability,
        GcsimArtifactSetCapability,
    ):
        raise TypeError("capability must be typed or None")
    if capability is None or not capability.registered:
        return GcsimOptimizerTargetSetCapabilityValidation(
            ready=False,
            code="target_set_unmapped",
            message="Target set has no registered active GCSIM mapping.",
        )
    if (
        isinstance(package, GcsimFourPieceTargetPackage)
        and not capability.complete_four_piece_modeled
    ):
        return GcsimOptimizerTargetSetCapabilityValidation(
            ready=False,
            code="target_four_piece_unmodeled",
            message="Target set does not have a complete modeled 4p effect.",
        )
    if (
        isinstance(package, GcsimTwoPlusTwoTargetPackage)
        and not capability.two_piece_modeled
    ):
        return GcsimOptimizerTargetSetCapabilityValidation(
            ready=False,
            code="target_two_piece_unmodeled",
            message="Target set does not have a modeled 2p effect.",
        )
    return GcsimOptimizerTargetSetCapabilityValidation(ready=True)


def validate_gcsim_optimizer_set_parameters(
    set_ref: GcsimOptimizerSetReference,
    capability: GcsimArtifactSetCapability,
) -> GcsimOptimizerSetParameterValidation:
    """Apply the exact parameter/default policy used for rendered set lines."""

    if not isinstance(set_ref, GcsimOptimizerSetReference):
        raise TypeError("set_ref must be typed")
    if not isinstance(capability, GcsimArtifactSetCapability):
        raise TypeError("capability must be typed")
    issues: list[GcsimOptimizerSetParameterValidationIssue] = []
    allowed_keys = set(capability.parameter_keys)
    supplied_keys = set(set_ref.set_parameters)
    unknown_keys = supplied_keys - allowed_keys
    if unknown_keys:
        issues.append(
            GcsimOptimizerSetParameterValidationIssue(
                code="set_parameter_key_invalid",
                message=(
                    "Unsupported set parameter keys: "
                    f"{sorted(unknown_keys)}."
                ),
            )
        )
    parameters: dict[str, int] = {}
    for key, value in set_ref.set_parameters.items():
        if isinstance(value, bool) or not isinstance(value, int):
            issues.append(
                GcsimOptimizerSetParameterValidationIssue(
                    code="set_parameter_value_invalid",
                    message="Pinned GCSIM set parameters must be integers.",
                )
            )
        else:
            parameters[key] = value
    return GcsimOptimizerSetParameterValidation(
        parameters=tuple(sorted(parameters.items())),
        defaulted_parameter_keys=tuple(sorted(allowed_keys - supplied_keys)),
        issues=tuple(issues),
    )


def materialize_gcsim_optimizer_artifact_stat_vector(
    artifact: GcsimOptimizerArtifactRecord,
    *,
    wearer: GcsimOptimizerWearerIdentity,
) -> GcsimOptimizerArtifactStatVectorResult:
    """Normalize one row through the same strict path used by full builds."""

    if not isinstance(artifact, GcsimOptimizerArtifactRecord):
        raise TypeError("artifact must be a GcsimOptimizerArtifactRecord")
    if not isinstance(wearer, GcsimOptimizerWearerIdentity):
        raise TypeError("wearer must be a GcsimOptimizerWearerIdentity")
    diagnostics: list[GcsimOptimizerMaterializationDiagnostic] = []
    contributions = _artifact_stat_contributions(
        artifact,
        artifact_slot=artifact.position_key,
        wearer=wearer,
        diagnostics=diagnostics,
    )
    if _has_errors(diagnostics):
        return GcsimOptimizerArtifactStatVectorResult(
            ready=False,
            diagnostics=tuple(diagnostics),
        )
    totals: dict[str, Decimal] = {}
    for contribution in contributions:
        value = Decimal(contribution.normalized_value)
        totals[contribution.gcsim_key] = (
            totals.get(contribution.gcsim_key, Decimal(0)) + value
        )
    if not totals:
        diagnostics.append(
            _error(
                "artifact_stats_empty",
                "Artifact produced no exact GCSIM stats.",
                wearer=wearer,
                artifact_id=artifact.artifact_id,
            )
        )
        return GcsimOptimizerArtifactStatVectorResult(
            ready=False,
            diagnostics=tuple(diagnostics),
        )
    normalized_stats = tuple(
        (key, _format_decimal(totals[key]))
        for key in _ordered_stat_keys(totals)
    )
    stat_vector = GcsimOptimizerArtifactStatVector(
        artifact_id=artifact.artifact_id,
        artifact_slot=artifact.position_key,
        contributions=contributions,
        normalized_stats=normalized_stats,
        diagnostics=tuple(diagnostics),
    )
    return GcsimOptimizerArtifactStatVectorResult(
        ready=True,
        stat_vector=stat_vector,
        diagnostics=tuple(diagnostics),
    )


def materialize_gcsim_optimizer_wearer_build(
    run_input: GcsimOptimizerRunInput,
    *,
    assignment: GcsimOptimizerWearerArtifactAssignment,
    target: GcsimOptimizerWearerTarget,
) -> GcsimOptimizerMaterializedBuildResult:
    """Materialize one exact five-ID wearer build without external reads."""

    diagnostics: list[GcsimOptimizerMaterializationDiagnostic] = []
    if not isinstance(run_input, GcsimOptimizerRunInput):
        return _build_failed(
            _error("run_input_invalid", "run_input must be typed.")
        )
    if not isinstance(assignment, GcsimOptimizerWearerArtifactAssignment):
        return _build_failed(
            _error("assignment_invalid", "assignment must be typed.")
        )
    if not isinstance(target, GcsimOptimizerWearerTarget):
        return _build_failed(_error("target_invalid", "target must be typed."))
    if assignment.wearer != target.wearer:
        return _build_failed(
            _error(
                "assignment_target_wearer_mismatch",
                "Assignment and target wearers differ.",
                wearer=assignment.wearer,
            )
        )
    if assignment.wearer not in run_input.request.source_simulation.wearers:
        return _build_failed(
            _error(
                "wearer_outside_run",
                "Assignment wearer is outside the frozen source team.",
                wearer=assignment.wearer,
            )
        )

    target_refs = _target_set_refs(target.package)
    diagnostics.extend(
        _validate_target_for_request(run_input, target, target_refs)
    )
    package_set_uids = tuple(item.set_uid for item in target_refs)
    override = next(
        (
            item
            for item in run_input.request.four_star_overrides
            if item.wearer == assignment.wearer
        ),
        None,
    )

    artifacts_by_slot: list[tuple[str, GcsimOptimizerArtifactRecord]] = []
    contributions: list[GcsimOptimizerMaterializedStatContribution] = []
    for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
        artifact_id = assignment.artifact_ids_by_slot[slot]
        artifact = run_input.artifact_by_id(artifact_id)
        if artifact is None:
            diagnostics.append(
                _error(
                    "artifact_id_missing",
                    "Artifact ID is absent from the frozen database.",
                    wearer=assignment.wearer,
                    artifact_id=artifact_id,
                )
            )
            continue
        artifacts_by_slot.append((slot, artifact))
        if artifact.position_key != slot:
            diagnostics.append(
                _error(
                    "artifact_slot_mismatch",
                    f"Artifact metadata slot {artifact.position_key!r} "
                    f"cannot fill {slot!r}.",
                    wearer=assignment.wearer,
                    artifact_id=artifact_id,
                )
            )
        eligibility = evaluate_gcsim_optimizer_artifact_eligibility(
            artifact,
            wearer=assignment.wearer,
            four_star_override=override,
            package_set_uids=package_set_uids,
        )
        if not eligibility.eligible:
            diagnostics.append(
                _error(
                    eligibility.reason,
                    "Artifact is not eligible for this wearer/package.",
                    wearer=assignment.wearer,
                    artifact_id=artifact_id,
                )
            )
        contributions.extend(
            _artifact_stat_contributions(
                artifact,
                artifact_slot=slot,
                wearer=assignment.wearer,
                diagnostics=diagnostics,
            )
        )
    if _has_errors(diagnostics):
        return _build_failed(*diagnostics)

    set_counts = Counter(
        artifact.set_uid for _slot, artifact in artifacts_by_slot
    )
    active_sets = _materialize_active_sets(
        run_input,
        wearer=assignment.wearer,
        target=target,
        target_refs=target_refs,
        artifacts_by_slot=tuple(artifacts_by_slot),
        set_counts=set_counts,
        diagnostics=diagnostics,
    )
    if _has_errors(diagnostics):
        return _build_failed(*diagnostics)

    totals: dict[str, Decimal] = {}
    for contribution in contributions:
        value = Decimal(contribution.normalized_value)
        totals[contribution.gcsim_key] = (
            totals.get(contribution.gcsim_key, Decimal(0)) + value
        )
    for violation in evaluate_gcsim_optimizer_minimum_stat_constraints(
        run_input,
        target=target,
        artifact_stats=totals,
    ):
        diagnostics.append(
            _error(
                "minimum_stat_constraint_not_met",
                (
                    f"Static build {violation.axis_key}="
                    f"{violation.static_build_value} is below required "
                    f"{violation.minimum} (artifacts="
                    f"{violation.artifact_value}, guaranteed sets="
                    f"{violation.guaranteed_set_value})."
                ),
                wearer=assignment.wearer,
            )
        )
    if _has_errors(diagnostics):
        return _build_failed(*diagnostics)
    normalized_stats = tuple(
        (key, _format_decimal(totals[key]))
        for key in _ordered_stat_keys(totals)
    )
    if not normalized_stats:
        return _build_failed(
            *diagnostics,
            _error(
                "artifact_stats_empty",
                "Five artifacts produced no exact GCSIM stats.",
                wearer=assignment.wearer,
            ),
        )
    stats_text = " ".join(
        f"{key}={value}" for key, value in normalized_stats
    )
    rendered_lines = (
        *(item.rendered_line for item in active_sets),
        f"{assignment.wearer.gcsim_character_key} add stats {stats_text};",
    )
    target_identity = _canonical_sha256(target.to_dict())
    wearer_build_identity = _canonical_sha256(
        {
            "request_sha256": run_input.request.request_sha256,
            "artifact_database_input_sha256": (
                run_input.artifact_database.artifact_database_input_sha256
            ),
            "assignment": assignment.to_dict(),
            "target_identity_sha256": target_identity,
        }
    )
    block_text = "\n".join(rendered_lines)
    build = GcsimOptimizerMaterializedBuild(
        wearer=assignment.wearer,
        assignment=assignment,
        target=target,
        artifacts_by_slot=tuple(artifacts_by_slot),
        stat_contributions=tuple(contributions),
        normalized_stats=normalized_stats,
        set_counts=tuple(sorted(set_counts.items())),
        active_sets=active_sets,
        rendered_lines=rendered_lines,
        wearer_build_identity_sha256=wearer_build_identity,
        compiled_block_sha256=_sha256_text(block_text),
        diagnostics=tuple(diagnostics),
    )
    return GcsimOptimizerMaterializedBuildResult(
        status=OPTIMIZER_MATERIALIZATION_READY,
        ready=True,
        build=build,
        diagnostics=tuple(diagnostics),
    )


def compile_gcsim_optimizer_team_candidate(
    run_input: GcsimOptimizerRunInput,
    *,
    assignment_witness: GcsimOptimizerAccountAssignmentWitness,
    targets: Sequence[GcsimOptimizerWearerTarget],
    execution_identity_sha256: str,
) -> GcsimOptimizerCompiledTeamResult:
    """Insert four strict materialized blocks into the frozen config shell."""

    if not isinstance(run_input, GcsimOptimizerRunInput):
        return _team_failed(
            _error("run_input_invalid", "run_input must be typed.")
        )
    if not isinstance(
        assignment_witness,
        GcsimOptimizerAccountAssignmentWitness,
    ):
        return _team_failed(
            _error(
                "assignment_witness_invalid",
                "assignment_witness must be typed.",
            )
        )
    try:
        _require_sha256(
            execution_identity_sha256,
            "execution_identity_sha256",
        )
    except ValueError as exc:
        return _team_failed(
            _error("execution_identity_invalid", str(exc))
        )
    target_rows = tuple(targets)
    expected_wearers = run_input.request.source_simulation.wearers
    if (
        assignment_witness.request_sha256
        != run_input.request.request_sha256
        or assignment_witness.artifact_database_input_sha256
        != run_input.artifact_database.artifact_database_input_sha256
    ):
        return _team_failed(
            _error(
                "assignment_witness_identity_mismatch",
                "Assignment witness belongs to another request/database.",
            )
        )
    if tuple(
        row.wearer for row in assignment_witness.wearer_assignments
    ) != expected_wearers:
        return _team_failed(
            _error(
                "assignment_wearers_mismatch",
                "Assignment witness must cover the frozen team in order.",
            )
        )
    if (
        len(target_rows) != 4
        or tuple(item.wearer for item in target_rows) != expected_wearers
    ):
        return _team_failed(
            _error(
                "target_wearers_mismatch",
                "Targets must cover the frozen team in order.",
            )
        )

    diagnostics: list[GcsimOptimizerMaterializationDiagnostic] = []
    builds: list[GcsimOptimizerMaterializedBuild] = []
    for assignment, target in zip(
        assignment_witness.wearer_assignments,
        target_rows,
        strict=True,
    ):
        result = materialize_gcsim_optimizer_wearer_build(
            run_input,
            assignment=assignment,
            target=target,
        )
        diagnostics.extend(result.diagnostics)
        if result.build is not None:
            builds.append(result.build)
    if _has_errors(diagnostics) or len(builds) != 4:
        return _team_failed(*diagnostics)

    compiled_config, rendered_blocks, segments = _replace_shell_markers(
        run_input,
        tuple(builds),
    )
    if compiled_config is None:
        return _team_failed(
            *diagnostics,
            _error(
                "config_shell_replacement_failed",
                "The frozen shell markers could not be replaced exactly once.",
            ),
        )
    if "gtt_optimizer_artifact_block" in compiled_config:
        return _team_failed(
            *diagnostics,
            _error(
                "config_shell_marker_survived",
                "An optimizer artifact marker survived compilation.",
            ),
        )
    compiled_hash = _sha256_text(compiled_config)
    target_identity = _canonical_sha256(
        [item.to_dict() for item in target_rows]
    )
    candidate_identity = _canonical_sha256(
        {
            "physical_assignment_sha256": (
                assignment_witness.identity_sha256
            ),
            "target_identity_sha256": target_identity,
        }
    )
    simulation_hash = _canonical_sha256(
        {
            "engine_binding_sha256": run_input.engine_binding_sha256,
            "compiled_config_sha256": compiled_hash,
            "execution_identity_sha256": execution_identity_sha256,
        }
    )
    segments_hash = _canonical_sha256(list(segments))
    replacement_proof = _canonical_sha256(
        {
            "shell_sha256": run_input.config_shell.shell_sha256,
            "non_artifact_segments_sha256": segments_hash,
            "compiled_block_sha256": [
                item.compiled_block_sha256 for item in builds
            ],
            "compiled_config_sha256": compiled_hash,
        }
    )
    candidate = GcsimOptimizerCompiledTeamCandidate(
        assignment_witness=assignment_witness,
        targets=target_rows,
        builds=tuple(builds),
        rendered_blocks=rendered_blocks,
        config_text=compiled_config,
        compiled_config_sha256=compiled_hash,
        physical_assignment_sha256=assignment_witness.identity_sha256,
        candidate_identity_sha256=candidate_identity,
        execution_identity_sha256=execution_identity_sha256,
        simulation_sha256=simulation_hash,
        non_artifact_segments_sha256=segments_hash,
        replacement_proof_sha256=replacement_proof,
        diagnostics=tuple(diagnostics),
    )
    return GcsimOptimizerCompiledTeamResult(
        status=OPTIMIZER_MATERIALIZATION_READY,
        ready=True,
        candidate=candidate,
        diagnostics=tuple(diagnostics),
    )


def add_gcsim_optimizer_simulation_witness(
    bucket: GcsimOptimizerSimulationWitnessBucket | None,
    candidate: GcsimOptimizerCompiledTeamCandidate,
    *,
    max_stored_witnesses: int = 4,
) -> GcsimOptimizerSimulationWitnessBucket:
    """Retain bounded physical witnesses for one simulator identity."""

    if not isinstance(candidate, GcsimOptimizerCompiledTeamCandidate):
        raise TypeError("candidate must be typed")
    if (
        isinstance(max_stored_witnesses, bool)
        or not isinstance(max_stored_witnesses, int)
        or max_stored_witnesses <= 0
    ):
        raise ValueError("max_stored_witnesses must be a positive integer")
    witness = candidate.assignment_witness
    if bucket is None:
        return GcsimOptimizerSimulationWitnessBucket(
            simulation_sha256=candidate.simulation_sha256,
            compiled_config_sha256=candidate.compiled_config_sha256,
            execution_identity_sha256=candidate.execution_identity_sha256,
            stored_witnesses=(witness,),
            observed_assignment_count=1,
            max_stored_witnesses=max_stored_witnesses,
        )
    if (
        bucket.simulation_sha256 != candidate.simulation_sha256
        or bucket.compiled_config_sha256 != candidate.compiled_config_sha256
        or bucket.execution_identity_sha256
        != candidate.execution_identity_sha256
    ):
        raise ValueError("candidate belongs to another simulation identity")
    if bucket.max_stored_witnesses != max_stored_witnesses:
        raise ValueError("witness bound cannot change within one bucket")
    known = {
        item.identity_sha256 for item in bucket.stored_witnesses
    }
    if witness.identity_sha256 in known:
        return GcsimOptimizerSimulationWitnessBucket(
            simulation_sha256=bucket.simulation_sha256,
            compiled_config_sha256=bucket.compiled_config_sha256,
            execution_identity_sha256=bucket.execution_identity_sha256,
            stored_witnesses=bucket.stored_witnesses,
            observed_assignment_count=bucket.observed_assignment_count + 1,
            max_stored_witnesses=max_stored_witnesses,
        )
    stored = bucket.stored_witnesses
    if len(stored) < max_stored_witnesses:
        stored = (*stored, witness)
    return GcsimOptimizerSimulationWitnessBucket(
        simulation_sha256=bucket.simulation_sha256,
        compiled_config_sha256=bucket.compiled_config_sha256,
        execution_identity_sha256=bucket.execution_identity_sha256,
        stored_witnesses=stored,
        observed_assignment_count=bucket.observed_assignment_count + 1,
        max_stored_witnesses=max_stored_witnesses,
    )


def _artifact_stat_contributions(
    artifact: GcsimOptimizerArtifactRecord,
    *,
    artifact_slot: str,
    wearer: GcsimOptimizerWearerIdentity,
    diagnostics: list[GcsimOptimizerMaterializationDiagnostic],
) -> tuple[GcsimOptimizerMaterializedStatContribution, ...]:
    result: list[GcsimOptimizerMaterializedStatContribution] = []
    main = _normalize_stored_stat(
        artifact_id=artifact.artifact_id,
        artifact_slot=artifact_slot,
        source_kind="main",
        source_slot_index=None,
        property_type=artifact.main_property_type,
        property_name=artifact.main_property_name,
        stored_value=artifact.main_property_value,
        wearer=wearer,
        diagnostics=diagnostics,
    )
    if main is not None:
        result.append(main)
    for substat in artifact.substats:
        normalized = _normalize_stored_stat(
            artifact_id=artifact.artifact_id,
            artifact_slot=artifact_slot,
            source_kind="substat",
            source_slot_index=substat.slot_index,
            property_type=substat.property_type,
            property_name=substat.property_name,
            stored_value=substat.stored_value,
            wearer=wearer,
            diagnostics=diagnostics,
        )
        if normalized is not None:
            result.append(normalized)
    return tuple(result)


def _normalize_stored_stat(
    *,
    artifact_id: int,
    artifact_slot: str,
    source_kind: str,
    source_slot_index: int | None,
    property_type: int | None,
    property_name: str | None,
    stored_value: object,
    wearer: GcsimOptimizerWearerIdentity,
    diagnostics: list[GcsimOptimizerMaterializationDiagnostic],
) -> GcsimOptimizerMaterializedStatContribution | None:
    mapping = (
        None
        if property_type is None
        else STAT_MAPPINGS_BY_PROPERTY_TYPE.get(property_type)
    )
    if mapping is None:
        diagnostics.append(
            _error(
                "artifact_stat_type_unmapped",
                f"{source_kind} stat type {property_type!r} has no GCSIM mapping.",
                wearer=wearer,
                artifact_id=artifact_id,
            )
        )
        return None
    numeric = _stored_decimal(stored_value)
    if numeric is None:
        diagnostics.append(
            _error(
                "artifact_stat_value_invalid",
                f"{source_kind} stat value must be an exact finite number.",
                wearer=wearer,
                artifact_id=artifact_id,
            )
        )
        return None
    normalized = (
        numeric / Decimal(100)
        if mapping.source_unit == SOURCE_UNIT_PERCENT_POINTS
        else numeric
    )
    return GcsimOptimizerMaterializedStatContribution(
        artifact_id=artifact_id,
        artifact_slot=artifact_slot,
        source_kind=source_kind,
        source_slot_index=source_slot_index,
        property_type=mapping.property_type,
        property_name=property_name,
        stored_value=stored_value,
        normalized_value=_format_decimal(normalized),
        gcsim_key=mapping.gcsim_key,
    )


def _materialize_active_sets(
    run_input: GcsimOptimizerRunInput,
    *,
    wearer: GcsimOptimizerWearerIdentity,
    target: GcsimOptimizerWearerTarget,
    target_refs: tuple[GcsimOptimizerSetReference, ...],
    artifacts_by_slot: tuple[tuple[str, GcsimOptimizerArtifactRecord], ...],
    set_counts: Counter[str],
    diagnostics: list[GcsimOptimizerMaterializationDiagnostic],
) -> tuple[GcsimOptimizerMaterializedSet, ...]:
    ref_by_uid = {item.set_uid: item for item in target_refs}
    active_uids = {
        set_uid for set_uid, count in set_counts.items() if count >= 2
    }
    expected_uids = set(ref_by_uid)
    if isinstance(target.package, GcsimFourPieceTargetPackage):
        target_uid = target.package.set_ref.set_uid
        if set_counts[target_uid] < 4:
            diagnostics.append(
                _error(
                    "four_piece_target_not_satisfied",
                    "The exact assignment does not contain four target-set pieces.",
                    wearer=wearer,
                    set_uid=target_uid,
                )
            )
    elif isinstance(target.package, GcsimTwoPlusTwoTargetPackage):
        for set_uid in expected_uids:
            if set_counts[set_uid] < 2:
                diagnostics.append(
                    _error(
                        "two_piece_target_not_satisfied",
                        "The exact assignment does not contain both target 2p bonuses.",
                        wearer=wearer,
                        set_uid=set_uid,
                    )
                )
    if active_uids != expected_uids:
        diagnostics.append(
            _error(
                "active_set_package_mismatch",
                "Physical active set counts differ from the explicit target package.",
                wearer=wearer,
            )
        )

    pieces_by_uid: dict[str, list[GcsimOptimizerArtifactRecord]] = {}
    for _slot, artifact in artifacts_by_slot:
        pieces_by_uid.setdefault(artifact.set_uid, []).append(artifact)
    materialized: list[GcsimOptimizerMaterializedSet] = []
    for set_uid in sorted(active_uids):
        pieces = pieces_by_uid[set_uid]
        mapped_keys = {
            piece.gcsim_set_key
            for piece in pieces
            if piece.gcsim_set_key
        }
        if (
            any(piece.set_mapping_status != "ready" for piece in pieces)
            or len(mapped_keys) != 1
        ):
            diagnostics.append(
                _error(
                    "active_set_mapping_invalid",
                    "Every active set piece must share one validated GCSIM key.",
                    wearer=wearer,
                    set_uid=set_uid,
                )
            )
            continue
        set_ref = ref_by_uid.get(set_uid)
        if set_ref is None or set_ref.gcsim_set_key not in mapped_keys:
            diagnostics.append(
                _error(
                    "active_set_reference_mismatch",
                    "Target set reference differs from physical set mapping.",
                    wearer=wearer,
                    set_uid=set_uid,
                )
            )
            continue
        catalog_capability = _catalog_capability(run_input, set_ref)
        if catalog_capability is None:
            diagnostics.append(
                _error(
                    "active_set_catalog_unmapped",
                    "Target set is absent from the frozen active catalog.",
                    wearer=wearer,
                    set_uid=set_uid,
                )
            )
            continue
        parameter_validation = validate_gcsim_optimizer_set_parameters(
            set_ref,
            catalog_capability,
        )
        for issue in parameter_validation.issues:
            diagnostics.append(
                _error(
                    issue.code,
                    issue.message,
                    wearer=wearer,
                    set_uid=set_uid,
                )
            )
        parameters = dict(parameter_validation.parameters)
        defaulted = parameter_validation.defaulted_parameter_keys
        if defaulted:
            diagnostics.append(
                _notice(
                    "set_parameters_defaulted",
                    f"GCSIM default/automatic values retained for {list(defaulted)}.",
                    wearer=wearer,
                    set_uid=set_uid,
                )
            )
        parameter_suffix = ""
        if parameters:
            rendered = ",".join(
                f"{key}={parameters[key]}" for key in sorted(parameters)
            )
            parameter_suffix = f" +params=[{rendered}]"
        line = (
            f'{wearer.gcsim_character_key} add set="'
            f'{set_ref.gcsim_set_key}" count={set_counts[set_uid]}'
            f"{parameter_suffix};"
        )
        materialized.append(
            GcsimOptimizerMaterializedSet(
                set_uid=set_uid,
                gcsim_set_key=set_ref.gcsim_set_key,
                count=set_counts[set_uid],
                set_parameters=parameters,
                defaulted_parameter_keys=defaulted,
                rendered_line=line,
            )
        )
    return tuple(materialized)


def _validate_target_for_request(
    run_input: GcsimOptimizerRunInput,
    target: GcsimOptimizerWearerTarget,
    target_refs: tuple[GcsimOptimizerSetReference, ...],
) -> tuple[GcsimOptimizerMaterializationDiagnostic, ...]:
    diagnostics: list[GcsimOptimizerMaterializationDiagnostic] = []
    request = run_input.request
    if (
        isinstance(target.package, GcsimTwoPlusTwoTargetPackage)
        and not request.include_2p2p
    ):
        diagnostics.append(
            _error(
                "two_plus_two_not_enabled",
                "Request does not enable 2p+2p packages.",
                wearer=target.wearer,
            )
        )
    if request.account_scope is GcsimOptimizerAccountScope.SELECTED_SET_POOLS:
        pool = next(
            (
                item
                for item in request.selected_set_pools
                if item.wearer == target.wearer
            ),
            None,
        )
        allowed = (
            set()
            if pool is None
            else {item.identity_sha256 for item in pool.allowed_sets}
        )
        if any(item.identity_sha256 not in allowed for item in target_refs):
            diagnostics.append(
                _error(
                    "target_outside_selected_pool",
                    "Target package contains a set outside the wearer pool.",
                    wearer=target.wearer,
                )
            )
    for set_ref in target_refs:
        if (
            set_ref.engine_binding_sha256 != run_input.engine_binding_sha256
            or set_ref.catalog_fingerprint != run_input.catalog_fingerprint
        ):
            diagnostics.append(
                _error(
                    "target_set_binding_mismatch",
                    "Target set reference belongs to another engine/catalog.",
                    wearer=target.wearer,
                    set_uid=set_ref.set_uid,
                )
            )
        capability_validation = validate_gcsim_optimizer_target_set_capability(
            target.package,
            _catalog_capability(run_input, set_ref),
        )
        if not capability_validation.ready:
            diagnostics.append(
                _error(
                    capability_validation.code,
                    capability_validation.message,
                    wearer=target.wearer,
                    set_uid=set_ref.set_uid,
                )
            )
    return tuple(diagnostics)


def _catalog_capability(
    run_input: GcsimOptimizerRunInput,
    set_ref: GcsimOptimizerSetReference,
):
    capability = run_input.set_capability(set_ref.gcsim_set_key)
    if capability is None or not capability.registered:
        return None
    return capability


def _target_set_refs(
    package: GcsimOptimizerTargetPackage,
) -> tuple[GcsimOptimizerSetReference, ...]:
    if isinstance(package, GcsimFourPieceTargetPackage):
        return (package.set_ref,)
    if isinstance(package, GcsimTwoPlusTwoTargetPackage):
        return (package.set_a, package.set_b)
    raise TypeError("unsupported target package")


def _replace_shell_markers(
    run_input: GcsimOptimizerRunInput,
    builds: tuple[GcsimOptimizerMaterializedBuild, ...],
) -> tuple[str | None, tuple[str, ...], tuple[str, ...]]:
    shell = run_input.config_shell
    build_by_wearer = {item.wearer: item for item in builds}
    cursor = 0
    segments: list[str] = []
    rendered_blocks: list[str] = []
    output: list[str] = []
    for source_block in shell.artifact_blocks:
        marker = source_block.marker
        marker_index = shell.config_text.find(marker, cursor)
        if marker_index < 0:
            return None, (), ()
        if shell.config_text.find(marker, marker_index + len(marker)) >= 0:
            return None, (), ()
        segment = shell.config_text[cursor:marker_index]
        segments.append(segment)
        output.append(segment)
        build = build_by_wearer.get(source_block.wearer)
        if build is None:
            return None, (), ()
        line_ending = _marker_line_ending(
            shell.config_text,
            marker_index + len(marker),
        )
        rendered = line_ending.join(build.rendered_lines)
        rendered_blocks.append(rendered)
        output.append(rendered)
        cursor = marker_index + len(marker)
    trailing = shell.config_text[cursor:]
    segments.append(trailing)
    output.append(trailing)
    return "".join(output), tuple(rendered_blocks), tuple(segments)


def _marker_line_ending(text: str, marker_end: int) -> str:
    if text.startswith("\r\n", marker_end):
        return "\r\n"
    return "\n"


def _stored_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, (bool, bytes)):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _ordered_stat_keys(values: Mapping[str, Decimal]) -> tuple[str, ...]:
    return tuple(
        [
            *(key for key in _GCSIM_STAT_ORDER if key in values),
            *(sorted(key for key in values if key not in _GCSIM_STAT_ORDER)),
        ]
    )


def _format_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _build_failed(
    *diagnostics: GcsimOptimizerMaterializationDiagnostic,
) -> GcsimOptimizerMaterializedBuildResult:
    return GcsimOptimizerMaterializedBuildResult(
        status=OPTIMIZER_MATERIALIZATION_NOT_READY,
        ready=False,
        diagnostics=tuple(diagnostics),
    )


def _team_failed(
    *diagnostics: GcsimOptimizerMaterializationDiagnostic,
) -> GcsimOptimizerCompiledTeamResult:
    return GcsimOptimizerCompiledTeamResult(
        status=OPTIMIZER_MATERIALIZATION_NOT_READY,
        ready=False,
        diagnostics=tuple(diagnostics),
    )


def _error(
    code: str,
    message: str,
    *,
    wearer: GcsimOptimizerWearerIdentity | None = None,
    artifact_id: int | None = None,
    set_uid: str = "",
) -> GcsimOptimizerMaterializationDiagnostic:
    return GcsimOptimizerMaterializationDiagnostic(
        severity=OPTIMIZER_DIAGNOSTIC_ERROR,
        code=code,
        message=message,
        wearer=wearer,
        artifact_id=artifact_id,
        set_uid=set_uid,
    )


def _notice(
    code: str,
    message: str,
    *,
    wearer: GcsimOptimizerWearerIdentity | None = None,
    set_uid: str = "",
) -> GcsimOptimizerMaterializationDiagnostic:
    return GcsimOptimizerMaterializationDiagnostic(
        severity=OPTIMIZER_DIAGNOSTIC_NOTICE,
        code=code,
        message=message,
        wearer=wearer,
        set_uid=set_uid,
    )


def _has_errors(
    diagnostics: Sequence[GcsimOptimizerMaterializationDiagnostic],
) -> bool:
    return any(item.blocking for item in diagnostics)


def _json_scalar(value: object) -> object:
    if isinstance(value, bytes):
        return {"sqlite_blob_hex": value.hex()}
    return value


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


__all__ = [
    "GCSIM_OPTIMIZER_ARTIFACT_MATERIALIZER_SCHEMA_VERSION",
    "GcsimOptimizerCompiledTeamCandidate",
    "GcsimOptimizerCompiledTeamResult",
    "GcsimOptimizerMaterializationDiagnostic",
    "GcsimOptimizerMaterializedBuild",
    "GcsimOptimizerMaterializedBuildResult",
    "GcsimOptimizerMaterializedSet",
    "GcsimOptimizerMaterializedStatContribution",
    "GcsimOptimizerSetParameterValidation",
    "GcsimOptimizerSetParameterValidationIssue",
    "GcsimOptimizerSimulationWitnessBucket",
    "GcsimOptimizerTargetSetCapabilityValidation",
    "OPTIMIZER_DIAGNOSTIC_ERROR",
    "OPTIMIZER_DIAGNOSTIC_NOTICE",
    "OPTIMIZER_MATERIALIZATION_NOT_READY",
    "OPTIMIZER_MATERIALIZATION_READY",
    "add_gcsim_optimizer_simulation_witness",
    "compile_gcsim_optimizer_team_candidate",
    "materialize_gcsim_optimizer_wearer_build",
    "validate_gcsim_optimizer_set_parameters",
    "validate_gcsim_optimizer_target_set_capability",
]
