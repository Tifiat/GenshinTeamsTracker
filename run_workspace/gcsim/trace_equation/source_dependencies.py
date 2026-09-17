"""Version-bound source identities and bounded dependency-slice evidence.

This module is the additive Python contract for raw engine trace schema v4.
It deliberately wraps the frozen v3 reaction evidence instead of changing any
v1-v3 object or hash.  Source slices are diagnostic/shortlist evidence only:
they never authorize exact replay, publication, or candidate removal.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import hashlib
import json
import math
from pathlib import PurePosixPath
import re

from .codec import (
    _array,
    _boolean,
    _decode_json,
    _integer,
    _number,
    _object,
    _optional_string,
    _string,
)
from .contracts import (
    TraceContractError,
    ValueReadMode,
    canonical_json,
    canonical_sha256,
)
from .provider_evidence import ProviderIdentity
from .reaction_evidence import ReactionEvidenceTrace


SOURCE_MANIFEST_SCHEMA_VERSION = 1
SOURCE_MANIFEST_KIND = "gtt.source_manifest.body"
SOURCE_MANIFEST_BINDING_SCHEMA_VERSION = 1
SOURCE_MANIFEST_BINDING_KIND = "gtt.trace_equation.source_manifest_binding"
SOURCE_DEPENDENCY_EVIDENCE_SCHEMA_VERSION = 4
SOURCE_DEPENDENCY_EVIDENCE_KIND = "gtt.trace_equation.source_dependency_evidence"
SOURCE_HEALTH_EVIDENCE_SCHEMA_VERSION = 5
SOURCE_HEALTH_EVIDENCE_CAPABILITY = "gtt_trace_equation_v5"
SOURCE_STATE_EVIDENCE_SCHEMA_VERSION = 6
SOURCE_STATE_EVIDENCE_CAPABILITY = "gtt_trace_equation_v6"
SOURCE_COMPILER_VERSION = "gtt_source_compiler_v1"
SOURCE_IR_FORMULA_ID = "gtt_source_ir_v1"
SOURCE_IR_FORMULA_SHA256 = (
    "243f34e59a6a6df869ccafa0bcdfdcb80a986ff5ebf9a41e52059b1ee5e95208"
)
SOURCE_STATE_COMPILER_VERSION = "gtt_source_compiler_v2"
SOURCE_STATE_IR_FORMULA_ID = "gtt_source_ir_v2"
SOURCE_STATE_IR_FORMULA_SHA256 = (
    "8b8dfcb9cb97e2b06145638e47ba915a6016a11f956708d7de7ee826ae730792"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MACHINE_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_OCCURRENCE_ID_RE = re.compile(r"^source-occurrence:(0|[1-9][0-9]*)$")
_BINDING_ID_RE = re.compile(
    r"^source-binding:(0|[1-9][0-9]*):(0|[1-9][0-9]*)$"
)
_REL_TOL = 1e-9
_ABS_TOL = 1e-7


def _manifest_canonical_json(value: object) -> str:
    """Match the engine-update/source-manifest canonical byte contract."""

    try:
        output: list[str] = []
        _append_manifest_canonical_json(output, value)
        return "".join(output)
    except (TypeError, ValueError) as exc:
        raise TraceContractError("source manifest value is not canonical JSON") from exc


def _append_manifest_canonical_json(output: list[str], value: object) -> None:
    if value is None:
        output.append("null")
    elif value is True:
        output.append("true")
    elif value is False:
        output.append("false")
    elif isinstance(value, str):
        output.append(json.dumps(value, ensure_ascii=True, allow_nan=False))
    elif isinstance(value, int):
        output.append(str(value))
    elif isinstance(value, float):
        output.append(_go_json_float(value))
    elif isinstance(value, (list, tuple)):
        output.append("[")
        for index, item in enumerate(value):
            if index:
                output.append(",")
            _append_manifest_canonical_json(output, item)
        output.append("]")
    elif isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical source manifest object keys must be strings")
        output.append("{")
        for index, key in enumerate(sorted(value)):
            if index:
                output.append(",")
            output.append(json.dumps(key, ensure_ascii=True, allow_nan=False))
            output.append(":")
            _append_manifest_canonical_json(output, value[key])
        output.append("}")
    else:
        raise TypeError(f"unsupported canonical source manifest value {type(value)!r}")


def _go_json_float(value: float) -> str:
    """Mirror Go encoding/json's shortest float64 representation."""

    if not math.isfinite(value):
        raise ValueError("non-finite source manifest number")
    if value == 0.0:
        return "-0" if math.copysign(1.0, value) < 0.0 else "0"
    absolute = abs(value)
    shortest = repr(value).lower()
    if 1e-6 <= absolute < 1e21:
        rendered = format(Decimal(shortest), "f") if "e" in shortest else shortest
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return rendered
    if "e" not in shortest:
        shortest = format(Decimal(shortest).normalize(), "e")
    mantissa, exponent_text = shortest.split("e", 1)
    if "." in mantissa:
        mantissa = mantissa.rstrip("0").rstrip(".")
    exponent = int(exponent_text)
    exponent_suffix = f"+{exponent}" if exponent >= 0 else str(exponent)
    return f"{mantissa}e{exponent_suffix}"


class SourceSeam(str, Enum):
    MODIFIER_AMOUNT = "modifier_amount"
    EVENT_CALLBACK = "event_callback"
    TASK_CALLBACK = "task_callback"
    QUEUED_ATTACK = "queued_attack"
    HEALTH_INPUT = "health_input"
    STATE_OPERATION = "state_operation"


class SourceSliceStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    OPAQUE_FROZEN = "OPAQUE_FROZEN"


class SourceIROperator(str, Enum):
    CONST = "CONST"
    PARAM = "PARAM"
    ADD = "ADD"
    SUB = "SUB"
    MUL = "MUL"
    DIV = "DIV"
    MIN = "MIN"
    MAX = "MAX"
    ABS = "ABS"
    AND = "AND"
    OR = "OR"
    EQ = "EQ"
    NE = "NE"
    LT = "LT"
    LE = "LE"
    GT = "GT"
    GE = "GE"
    NOT = "NOT"
    SELECT = "SELECT"


class SourceParameterKind(str, Enum):
    CANDIDATE_STAT = "candidate_stat"
    FROZEN_SOURCE_VALUE = "frozen_source_value"
    FROZEN_RUNTIME_STATE = "frozen_runtime_state"


class SourceOutputKind(str, Enum):
    ATTACK_MOD_STAT = "attack_mod_stat"
    TERMINAL_FLAT_DMG = "terminal_flat_dmg"
    DIAGNOSTIC_SCALAR = "diagnostic_scalar"


@dataclass(frozen=True, slots=True)
class SourceLocator:
    module_path: str
    enclosing_symbol: str
    seam: SourceSeam
    ordinal: int

    def __post_init__(self) -> None:
        _module_path(self.module_path, "source locator module_path")
        _trimmed(self.enclosing_symbol, "source locator enclosing_symbol")
        _enum(self.seam, SourceSeam, "source locator seam")
        _nonnegative_int(self.ordinal, "source locator ordinal")

    @property
    def source_id(self) -> str:
        canonical = _manifest_canonical_json(
            {
                "source_id_schema": 1,
                "module_path": self.module_path,
                "enclosing_symbol": self.enclosing_symbol,
                "seam": self.seam.value,
                "ordinal": self.ordinal,
            }
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "module_path": self.module_path,
            "enclosing_symbol": self.enclosing_symbol,
            "seam": self.seam.value,
            "ordinal": self.ordinal,
        }


@dataclass(frozen=True, slots=True)
class SourceIRNode:
    node_id: int
    operator: SourceIROperator
    input_node_ids: tuple[int, ...]
    constant_value: float | None = None
    parameter_key: str | None = None

    def __post_init__(self) -> None:
        _nonnegative_int(self.node_id, "IR node_id")
        _enum(self.operator, SourceIROperator, "IR operator")
        _tuple(self.input_node_ids, "IR input_node_ids")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in self.input_node_ids
        ):
            raise TraceContractError("IR input_node_ids must contain non-negative ints")
        if self.operator is SourceIROperator.CONST:
            if self.input_node_ids or self.parameter_key is not None:
                raise TraceContractError("CONST node cannot have inputs or parameter_key")
            _finite(self.constant_value, "CONST value")
        elif self.operator is SourceIROperator.PARAM:
            if self.input_node_ids or self.constant_value is not None:
                raise TraceContractError("PARAM node cannot have inputs or constant_value")
            _trimmed(self.parameter_key, "PARAM parameter_key")
        else:
            expected_arity = 3 if self.operator is SourceIROperator.SELECT else (
                1
                if self.operator in {SourceIROperator.ABS, SourceIROperator.NOT}
                else 2
            )
            if len(self.input_node_ids) != expected_arity:
                raise TraceContractError(
                    f"{self.operator.value} node requires exactly {expected_arity} inputs"
                )
            if self.constant_value is not None or self.parameter_key is not None:
                raise TraceContractError(
                    f"{self.operator.value} node cannot carry scalar payload fields"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "operator": self.operator.value,
            "input_node_ids": list(self.input_node_ids),
            "constant_value": self.constant_value,
            "parameter_key": self.parameter_key,
        }


@dataclass(frozen=True, slots=True)
class SourceSliceTemplate:
    status: SourceSliceStatus
    nodes: tuple[SourceIRNode, ...]
    root_node_id: int | None
    parameter_keys: tuple[str, ...]
    dependencies_complete: bool
    stop_reason_code: str | None
    template_sha256: str

    def __post_init__(self) -> None:
        _enum(self.status, SourceSliceStatus, "source slice status")
        _tuple(self.nodes, "source slice nodes")
        if any(not isinstance(node, SourceIRNode) for node in self.nodes):
            raise TraceContractError("source slice contains invalid IR node")
        _sorted_unique_strings(self.parameter_keys, "source slice parameter_keys")
        _bool(self.dependencies_complete, "source slice dependencies_complete")
        _sha256(self.template_sha256, "source slice template_sha256")
        if self.status is SourceSliceStatus.SUPPORTED:
            if not self.nodes:
                raise TraceContractError("SUPPORTED slice requires IR nodes")
            expected_ids = tuple(range(len(self.nodes)))
            if tuple(node.node_id for node in self.nodes) != expected_ids:
                raise TraceContractError("source IR node IDs must be contiguous in order")
            for node in self.nodes:
                if any(input_id >= node.node_id for input_id in node.input_node_ids):
                    raise TraceContractError(
                        "source IR inputs must reference preceding nodes"
                    )
            if self.root_node_id != self.nodes[-1].node_id:
                raise TraceContractError("source slice root must be the final IR node")
            discovered = tuple(
                sorted(
                    node.parameter_key
                    for node in self.nodes
                    if node.operator is SourceIROperator.PARAM
                    and node.parameter_key is not None
                )
            )
            if discovered != self.parameter_keys or len(discovered) != len(set(discovered)):
                raise TraceContractError(
                    "source slice parameter_keys must exactly match unique PARAM nodes"
                )
            if not self.dependencies_complete:
                raise TraceContractError("SUPPORTED slice dependencies must be complete")
            if self.stop_reason_code is not None:
                raise TraceContractError("SUPPORTED slice cannot have stop_reason_code")
        else:
            if self.nodes or self.root_node_id is not None:
                raise TraceContractError("OPAQUE_FROZEN slice cannot carry executable IR")
            if self.dependencies_complete:
                raise TraceContractError(
                    "OPAQUE_FROZEN slice dependencies must remain incomplete"
                )
            _machine_code(self.stop_reason_code, "opaque stop_reason_code")
        expected = source_slice_template_sha256(
            status=self.status,
            nodes=self.nodes,
            root_node_id=self.root_node_id,
            parameter_keys=self.parameter_keys,
            dependencies_complete=self.dependencies_complete,
            stop_reason_code=self.stop_reason_code,
        )
        if self.template_sha256 != expected:
            raise TraceContractError("source slice template SHA-256 mismatch")

    @classmethod
    def build(
        cls,
        *,
        status: SourceSliceStatus,
        nodes: tuple[SourceIRNode, ...],
        root_node_id: int | None,
        parameter_keys: tuple[str, ...],
        dependencies_complete: bool,
        stop_reason_code: str | None,
    ) -> "SourceSliceTemplate":
        digest = source_slice_template_sha256(
            status=status,
            nodes=nodes,
            root_node_id=root_node_id,
            parameter_keys=parameter_keys,
            dependencies_complete=dependencies_complete,
            stop_reason_code=stop_reason_code,
        )
        return cls(
            status=status,
            nodes=nodes,
            root_node_id=root_node_id,
            parameter_keys=parameter_keys,
            dependencies_complete=dependencies_complete,
            stop_reason_code=stop_reason_code,
            template_sha256=digest,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "nodes": [node.to_dict() for node in self.nodes],
            "root_node_id": self.root_node_id,
            "parameter_keys": list(self.parameter_keys),
            "dependencies_complete": self.dependencies_complete,
            "stop_reason_code": self.stop_reason_code,
            "template_sha256": self.template_sha256,
        }


def source_slice_template_sha256(
    *,
    status: SourceSliceStatus,
    nodes: tuple[SourceIRNode, ...],
    root_node_id: int | None,
    parameter_keys: tuple[str, ...],
    dependencies_complete: bool,
    stop_reason_code: str | None,
) -> str:
    canonical = _manifest_canonical_json(
        {
            "slice_template_schema": 1,
            "status": status.value,
            "nodes": [node.to_dict() for node in nodes],
            "root_node_id": root_node_id,
            "parameter_keys": list(parameter_keys),
            "dependencies_complete": dependencies_complete,
            "stop_reason_code": stop_reason_code,
        }
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceManifestEntry:
    source_id: str
    locator: SourceLocator
    source_node_sha256: str
    template: SourceSliceTemplate

    def __post_init__(self) -> None:
        _sha256(self.source_id, "manifest source_id")
        if not isinstance(self.locator, SourceLocator):
            raise TraceContractError("manifest entry locator must be SourceLocator")
        if self.source_id != self.locator.source_id:
            raise TraceContractError("manifest source_id does not match stable locator")
        _sha256(self.source_node_sha256, "manifest source_node_sha256")
        if not isinstance(self.template, SourceSliceTemplate):
            raise TraceContractError("manifest entry template is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "locator": self.locator.to_dict(),
            "source_node_sha256": self.source_node_sha256,
            "template": self.template.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SourcePatchDigest:
    path: str
    sha256: str

    def __post_init__(self) -> None:
        _relative_path(self.path, "patch path")
        _sha256(self.sha256, "patch sha256")

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class SourceFormulaIdentity:
    id: str
    sha256: str

    def __post_init__(self) -> None:
        _trimmed(self.id, "formula identity id")
        _sha256(self.sha256, "formula identity sha256")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class SourceGoToolchain:
    version: str
    os: str
    arch: str

    def __post_init__(self) -> None:
        _trimmed(self.version, "Go toolchain version")
        _trimmed(self.os, "Go toolchain os")
        _trimmed(self.arch, "Go toolchain arch")

    def to_dict(self) -> dict[str, object]:
        return {"version": self.version, "os": self.os, "arch": self.arch}


@dataclass(frozen=True, slots=True)
class SourceManifestBody:
    compiler_version: str
    upstream_repo: str
    upstream_ref: str
    pristine_source_tree_sha256: str
    patches: tuple[SourcePatchDigest, ...]
    patch_stack_sha256: str
    patched_source_tree_sha256: str
    trace_schema_version: int
    trace_capability: str
    formula_identities: tuple[SourceFormulaIdentity, ...]
    go_toolchain: SourceGoToolchain
    build_flags: tuple[str, ...]
    entries: tuple[SourceManifestEntry, ...]
    schema_version: int = SOURCE_MANIFEST_SCHEMA_VERSION
    kind: str = SOURCE_MANIFEST_KIND

    def __post_init__(self) -> None:
        _exact(self.schema_version, SOURCE_MANIFEST_SCHEMA_VERSION, "source manifest schema")
        _exact(self.kind, SOURCE_MANIFEST_KIND, "source manifest kind")
        _nonnegative_int(
            self.trace_schema_version,
            "manifest trace_schema_version",
        )
        source_contracts = {
            SOURCE_DEPENDENCY_EVIDENCE_SCHEMA_VERSION: (
                SOURCE_COMPILER_VERSION,
                SOURCE_IR_FORMULA_ID,
                SOURCE_IR_FORMULA_SHA256,
            ),
            SOURCE_HEALTH_EVIDENCE_SCHEMA_VERSION: (
                SOURCE_COMPILER_VERSION,
                SOURCE_IR_FORMULA_ID,
                SOURCE_IR_FORMULA_SHA256,
            ),
            SOURCE_STATE_EVIDENCE_SCHEMA_VERSION: (
                SOURCE_STATE_COMPILER_VERSION,
                SOURCE_STATE_IR_FORMULA_ID,
                SOURCE_STATE_IR_FORMULA_SHA256,
            ),
        }
        source_contract = source_contracts.get(self.trace_schema_version)
        if source_contract is None:
            raise TraceContractError(
                "manifest trace_schema_version has no source compiler contract"
            )
        expected_compiler, expected_ir_id, expected_ir_sha256 = source_contract
        _exact(
            self.compiler_version,
            expected_compiler,
            "manifest compiler_version",
        )
        _trimmed(self.upstream_repo, "manifest upstream_repo")
        _trimmed(self.upstream_ref, "manifest upstream_ref")
        _sha256(
            self.pristine_source_tree_sha256,
            "manifest pristine_source_tree_sha256",
        )
        _tuple(self.patches, "manifest patches")
        if any(not isinstance(row, SourcePatchDigest) for row in self.patches):
            raise TraceContractError("manifest patches contain an invalid row")
        patch_paths = tuple(row.path for row in self.patches)
        if len(patch_paths) != len(set(patch_paths)):
            raise TraceContractError("manifest patch paths must be unique")
        _sha256(self.patch_stack_sha256, "manifest patch_stack_sha256")
        if self.patch_stack_sha256 != source_patch_stack_sha256(self.patches):
            raise TraceContractError("manifest patch_stack_sha256 mismatch")
        _sha256(
            self.patched_source_tree_sha256,
            "manifest patched_source_tree_sha256",
        )
        trace_pairs = {
            SOURCE_DEPENDENCY_EVIDENCE_SCHEMA_VERSION: "gtt_trace_equation_v4",
            SOURCE_HEALTH_EVIDENCE_SCHEMA_VERSION: SOURCE_HEALTH_EVIDENCE_CAPABILITY,
            SOURCE_STATE_EVIDENCE_SCHEMA_VERSION: SOURCE_STATE_EVIDENCE_CAPABILITY,
        }
        expected_capability = trace_pairs.get(self.trace_schema_version)
        if expected_capability is None:
            raise TraceContractError(
                "manifest trace_schema_version must be one of "
                f"{tuple(sorted(trace_pairs))!r}"
            )
        _exact(
            self.trace_capability,
            expected_capability,
            "manifest trace_capability",
        )
        _tuple(self.formula_identities, "manifest formula_identities")
        if any(
            not isinstance(row, SourceFormulaIdentity)
            for row in self.formula_identities
        ):
            raise TraceContractError("manifest formula_identities contain an invalid row")
        formula_ids = tuple(row.id for row in self.formula_identities)
        if len(formula_ids) != len(set(formula_ids)):
            raise TraceContractError("manifest formula identity IDs must be unique")
        source_ir = next(
            (
                row
                for row in self.formula_identities
                if row.id == expected_ir_id
            ),
            None,
        )
        if source_ir is None or source_ir.sha256 != expected_ir_sha256:
            raise TraceContractError("manifest source IR formula identity mismatch")
        if not isinstance(self.go_toolchain, SourceGoToolchain):
            raise TraceContractError("manifest go_toolchain is invalid")
        _tuple(self.build_flags, "manifest build_flags")
        if any(
            not isinstance(flag, str) or not flag or flag.strip() != flag
            for flag in self.build_flags
        ):
            raise TraceContractError("manifest build_flags must be trimmed strings")
        if self.build_flags != ("-trimpath",):
            raise TraceContractError(
                "manifest build_flags must be exactly ('-trimpath',)"
            )
        _tuple(self.entries, "manifest entries")
        if any(not isinstance(entry, SourceManifestEntry) for entry in self.entries):
            raise TraceContractError("manifest contains invalid entry")
        ids = tuple(entry.source_id for entry in self.entries)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise TraceContractError("manifest entries must be sorted by unique source_id")

    @property
    def body_sha256(self) -> str:
        return source_manifest_body_sha256(self)

    def entry_by_id(self, source_id: str) -> SourceManifestEntry | None:
        index = bisect_left(
            self.entries,
            source_id,
            key=lambda entry: entry.source_id,
        )
        if index >= len(self.entries):
            return None
        entry = self.entries[index]
        return entry if entry.source_id == source_id else None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "compiler_version": self.compiler_version,
            "upstream_repo": self.upstream_repo,
            "upstream_ref": self.upstream_ref,
            "pristine_source_tree_sha256": self.pristine_source_tree_sha256,
            "patches": [row.to_dict() for row in self.patches],
            "patch_stack_sha256": self.patch_stack_sha256,
            "patched_source_tree_sha256": self.patched_source_tree_sha256,
            "trace_schema_version": self.trace_schema_version,
            "trace_capability": self.trace_capability,
            "formula_identities": [row.to_dict() for row in self.formula_identities],
            "go_toolchain": self.go_toolchain.to_dict(),
            "build_flags": list(self.build_flags),
            "entries": [entry.to_dict() for entry in self.entries],
        }


def source_manifest_body_sha256(body: SourceManifestBody) -> str:
    if not isinstance(body, SourceManifestBody):
        raise TraceContractError("body must be SourceManifestBody")
    canonical = _manifest_canonical_json(body.to_dict())
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def source_patch_stack_sha256(patches: tuple[SourcePatchDigest, ...]) -> str:
    _tuple(patches, "patch files")
    canonical = _manifest_canonical_json(
        {
            "schema_version": 1,
            "patches": [patch.to_dict() for patch in patches],
        }
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceManifestBinding:
    manifest_body: SourceManifestBody
    manifest_body_sha256: str
    source_tree_sha256: str
    engine_tree_sha256: str
    patch_stack_sha256: str
    patches: tuple[SourcePatchDigest, ...]
    engine_artifact_sha256: str
    engine_binding_sha256: str
    go_version: str
    binding_sha256: str
    schema_version: int = SOURCE_MANIFEST_BINDING_SCHEMA_VERSION
    kind: str = SOURCE_MANIFEST_BINDING_KIND

    def __post_init__(self) -> None:
        _exact(
            self.schema_version,
            SOURCE_MANIFEST_BINDING_SCHEMA_VERSION,
            "source manifest binding schema",
        )
        _exact(self.kind, SOURCE_MANIFEST_BINDING_KIND, "source manifest binding kind")
        if not isinstance(self.manifest_body, SourceManifestBody):
            raise TraceContractError("manifest_body must be SourceManifestBody")
        for name in (
            "manifest_body_sha256",
            "source_tree_sha256",
            "engine_tree_sha256",
            "patch_stack_sha256",
            "engine_artifact_sha256",
            "engine_binding_sha256",
            "binding_sha256",
        ):
            _sha256(getattr(self, name), name)
        if self.manifest_body_sha256 != self.manifest_body.body_sha256:
            raise TraceContractError(
                "manifest_body_sha256 does not match canonical manifest body"
            )
        if self.source_tree_sha256 != self.manifest_body.pristine_source_tree_sha256:
            raise TraceContractError(
                "source_tree_sha256 does not match pristine manifest source tree"
            )
        _tuple(self.patches, "patches")
        if any(not isinstance(row, SourcePatchDigest) for row in self.patches):
            raise TraceContractError("patches contains an invalid row")
        paths = tuple(row.path for row in self.patches)
        if len(paths) != len(set(paths)):
            raise TraceContractError("patches paths must be unique")
        expected_stack = source_patch_stack_sha256(self.patches)
        if self.patch_stack_sha256 != expected_stack:
            raise TraceContractError("patch_stack_sha256 does not match patches")
        if self.manifest_body.patch_stack_sha256 != self.patch_stack_sha256:
            raise TraceContractError(
                "manifest patch_stack_sha256 does not match semantic patch stack"
            )
        if self.manifest_body.patches != self.patches:
            raise TraceContractError(
                "manifest patches do not match semantic patch file identities"
            )
        _trimmed(self.go_version, "go_version")
        if self.go_version != self.manifest_body.go_toolchain.version:
            raise TraceContractError(
                "go_version does not match source manifest toolchain"
            )
        expected = source_manifest_binding_sha256(
            manifest_body_sha256=self.manifest_body_sha256,
            source_tree_sha256=self.source_tree_sha256,
            engine_tree_sha256=self.engine_tree_sha256,
            patch_stack_sha256=self.patch_stack_sha256,
            patches=self.patches,
            engine_artifact_sha256=self.engine_artifact_sha256,
            engine_binding_sha256=self.engine_binding_sha256,
            go_version=self.go_version,
        )
        if self.binding_sha256 != expected:
            raise TraceContractError("source manifest binding SHA-256 mismatch")

    @classmethod
    def build(
        cls,
        *,
        manifest_body: SourceManifestBody,
        source_tree_sha256: str,
        engine_tree_sha256: str,
        engine_artifact_sha256: str,
        engine_binding_sha256: str,
    ) -> "SourceManifestBinding":
        manifest_body_sha256 = manifest_body.body_sha256
        patches = manifest_body.patches
        stack_sha256 = manifest_body.patch_stack_sha256
        go_version = manifest_body.go_toolchain.version
        digest = source_manifest_binding_sha256(
            manifest_body_sha256=manifest_body_sha256,
            source_tree_sha256=source_tree_sha256,
            engine_tree_sha256=engine_tree_sha256,
            patch_stack_sha256=stack_sha256,
            patches=patches,
            engine_artifact_sha256=engine_artifact_sha256,
            engine_binding_sha256=engine_binding_sha256,
            go_version=go_version,
        )
        return cls(
            manifest_body=manifest_body,
            manifest_body_sha256=manifest_body_sha256,
            source_tree_sha256=source_tree_sha256,
            engine_tree_sha256=engine_tree_sha256,
            patch_stack_sha256=stack_sha256,
            patches=patches,
            engine_artifact_sha256=engine_artifact_sha256,
            engine_binding_sha256=engine_binding_sha256,
            go_version=go_version,
            binding_sha256=digest,
        )

    @classmethod
    def from_engine_manifest(
        cls,
        *,
        manifest_body: SourceManifestBody,
        engine_manifest: object,
        engine_binding_sha256: str,
    ) -> "SourceManifestBinding":
        """Bind a source body to stable semantic engine-manifest fields.

        Wall-clock preparation metadata and the local absolute source path are
        intentionally ignored.  The executable, source trees, ordered patch
        bytes, Go version, and generated body are all checked fail-closed.
        """

        from ..engine_store import GcsimEngineManifest

        if not isinstance(engine_manifest, GcsimEngineManifest):
            raise TraceContractError("engine_manifest must be GcsimEngineManifest")
        metadata = dict(engine_manifest.metadata)
        patch_metadata = dict(engine_manifest.patch_metadata)
        _exact_manifest_text(
            metadata,
            "source_manifest_body_sha256",
            manifest_body.body_sha256,
        )
        _exact_manifest_text(
            metadata,
            "source_manifest_compiler_version",
            manifest_body.compiler_version,
        )
        _exact_manifest_text(
            metadata,
            "source_manifest_patched_tree_sha256",
            manifest_body.patched_source_tree_sha256,
        )
        _exact_manifest_text(
            metadata,
            "go_version",
            manifest_body.go_toolchain.version,
        )
        _exact_manifest_text(
            patch_metadata,
            "patch_stack_sha256",
            manifest_body.patch_stack_sha256,
        )
        manifest_patches = _patches_from_engine_manifest(patch_metadata)
        if manifest_patches != manifest_body.patches:
            raise TraceContractError(
                "engine manifest per-file patch identities do not match source body"
            )
        artifact_sha256 = metadata.get("artifact_sha256")
        _sha256(artifact_sha256, "engine manifest artifact_sha256")
        return cls.build(
            manifest_body=manifest_body,
            source_tree_sha256=engine_manifest.source_tree_hash,
            engine_tree_sha256=engine_manifest.engine_tree_hash,
            engine_artifact_sha256=artifact_sha256,
            engine_binding_sha256=engine_binding_sha256,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "manifest_body": self.manifest_body.to_dict(),
            "manifest_body_sha256": self.manifest_body_sha256,
            "source_tree_sha256": self.source_tree_sha256,
            "engine_tree_sha256": self.engine_tree_sha256,
            "patch_stack_sha256": self.patch_stack_sha256,
            "patches": [row.to_dict() for row in self.patches],
            "engine_artifact_sha256": self.engine_artifact_sha256,
            "engine_binding_sha256": self.engine_binding_sha256,
            "go_version": self.go_version,
            "binding_sha256": self.binding_sha256,
        }


def source_manifest_binding_sha256(
    *,
    manifest_body_sha256: str,
    source_tree_sha256: str,
    engine_tree_sha256: str,
    patch_stack_sha256: str,
    patches: tuple[SourcePatchDigest, ...],
    engine_artifact_sha256: str,
    engine_binding_sha256: str,
    go_version: str,
) -> str:
    canonical = _manifest_canonical_json(
        {
            "schema_version": SOURCE_MANIFEST_BINDING_SCHEMA_VERSION,
            "kind": SOURCE_MANIFEST_BINDING_KIND,
            "manifest_body_sha256": manifest_body_sha256,
            "source_tree_sha256": source_tree_sha256,
            "engine_tree_sha256": engine_tree_sha256,
            "patch_stack_sha256": patch_stack_sha256,
            "patches": [row.to_dict() for row in patches],
            "engine_artifact_sha256": engine_artifact_sha256,
            "engine_binding_sha256": engine_binding_sha256,
            "go_version": go_version,
        }
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceOccurrence:
    sequence_index: int
    occurrence_id: str
    source_id: str
    seam: SourceSeam
    frame: int
    parent_occurrence_id: str | None
    provider: ProviderIdentity
    terminal_event_id: str | None

    def __post_init__(self) -> None:
        _nonnegative_int(self.sequence_index, "source occurrence sequence_index")
        _trimmed(self.occurrence_id, "source occurrence_id")
        if self.occurrence_id != f"source-occurrence:{self.sequence_index}":
            raise TraceContractError(
                "source occurrence_id does not match its sequence index"
            )
        _sha256(self.source_id, "source occurrence source_id")
        _enum(self.seam, SourceSeam, "source occurrence seam")
        _nonnegative_int(self.frame, "source occurrence frame")
        _optional_trimmed(self.parent_occurrence_id, "source parent_occurrence_id")
        if not isinstance(self.provider, ProviderIdentity):
            raise TraceContractError("source occurrence provider is invalid")
        _optional_trimmed(self.terminal_event_id, "source terminal_event_id")

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence_index": self.sequence_index,
            "occurrence_id": self.occurrence_id,
            "source_id": self.source_id,
            "seam": self.seam.value,
            "frame": self.frame,
            "parent_occurrence_id": self.parent_occurrence_id,
            "provider": self.provider.to_dict(),
            "terminal_event_id": self.terminal_event_id,
        }


@dataclass(frozen=True, slots=True)
class SourceParameterBinding:
    parameter_key: str
    kind: SourceParameterKind
    observed_value: float
    actor_index: int | None
    actor_key: str | None
    stat_key: str | None
    read_mode: ValueReadMode
    read_frame: int
    candidate_dependency_complete: bool

    def __post_init__(self) -> None:
        _trimmed(self.parameter_key, "source parameter_key")
        _enum(self.kind, SourceParameterKind, "source parameter kind")
        _finite(self.observed_value, "source parameter observed_value")
        _enum(self.read_mode, ValueReadMode, "source parameter read_mode")
        _nonnegative_int(self.read_frame, "source parameter read_frame")
        _bool(
            self.candidate_dependency_complete,
            "source parameter candidate_dependency_complete",
        )
        if self.kind is SourceParameterKind.CANDIDATE_STAT:
            _nonnegative_int(self.actor_index, "candidate parameter actor_index")
            _trimmed(self.actor_key, "candidate parameter actor_key")
            _trimmed(self.stat_key, "candidate parameter stat_key")
            if self.read_mode is ValueReadMode.CONSTANT:
                raise TraceContractError("candidate stat parameter cannot be constant")
            # An owned stat read may have a known artifact response while its
            # external modifier ancestry remains frozen. Keep that explicit
            # flag; a partial read is not an unbound/malformed coordinate.
        elif self.kind is SourceParameterKind.FROZEN_SOURCE_VALUE:
            if any(value is not None for value in (self.actor_index, self.actor_key, self.stat_key)):
                raise TraceContractError(
                    "frozen source value cannot carry actor/stat coordinates"
                )
            if self.read_mode is not ValueReadMode.CONSTANT:
                raise TraceContractError("frozen source value must use constant read_mode")
            if not self.candidate_dependency_complete:
                raise TraceContractError(
                    "frozen source value dependency must be complete"
                )
        else:
            if (self.actor_index is None) != (self.actor_key is None):
                raise TraceContractError(
                    "runtime state actor index/key must be both present or both absent"
                )
            if self.actor_index is not None:
                _nonnegative_int(self.actor_index, "runtime state actor_index")
                _trimmed(self.actor_key, "runtime state actor_key")
            if self.stat_key is not None:
                raise TraceContractError("runtime state cannot masquerade as a stat")
            if self.read_mode is ValueReadMode.CONSTANT:
                raise TraceContractError("runtime state cannot use constant read_mode")

    def to_dict(self) -> dict[str, object]:
        return {
            "parameter_key": self.parameter_key,
            "kind": self.kind.value,
            "observed_value": self.observed_value,
            "actor_index": self.actor_index,
            "actor_key": self.actor_key,
            "stat_key": self.stat_key,
            "read_mode": self.read_mode.value,
            "read_frame": self.read_frame,
            "candidate_dependency_complete": self.candidate_dependency_complete,
        }


@dataclass(frozen=True, slots=True)
class SourceValueBinding:
    binding_id: str
    occurrence_id: str
    template_sha256: str
    output_kind: SourceOutputKind
    terminal_event_id: str | None
    provider_sequence_index: int | None
    output_key: str
    observed_value: float
    parameters: tuple[SourceParameterBinding, ...]

    def __post_init__(self) -> None:
        _trimmed(self.binding_id, "source value binding_id")
        if _BINDING_ID_RE.fullmatch(self.binding_id) is None:
            raise TraceContractError("source value binding_id has invalid format")
        _trimmed(self.occurrence_id, "source value occurrence_id")
        if _OCCURRENCE_ID_RE.fullmatch(self.occurrence_id) is None:
            raise TraceContractError("source value occurrence_id has invalid format")
        _sha256(self.template_sha256, "source value template_sha256")
        _enum(self.output_kind, SourceOutputKind, "source output_kind")
        _optional_trimmed(self.terminal_event_id, "source output terminal_event_id")
        _optional_nonnegative_int(
            self.provider_sequence_index,
            "source output provider_sequence_index",
        )
        _trimmed(self.output_key, "source output_key")
        _finite(self.observed_value, "source output observed_value")
        _tuple(self.parameters, "source output parameters")
        if any(not isinstance(row, SourceParameterBinding) for row in self.parameters):
            raise TraceContractError("source output contains invalid parameter binding")
        keys = tuple(row.parameter_key for row in self.parameters)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise TraceContractError(
                "source output parameters must be sorted by unique parameter_key"
            )
        if self.output_kind is SourceOutputKind.ATTACK_MOD_STAT:
            _trimmed(self.terminal_event_id, "attack-mod terminal_event_id")
            _nonnegative_int(
                self.provider_sequence_index,
                "attack-mod provider_sequence_index",
            )
        elif self.output_kind is SourceOutputKind.TERMINAL_FLAT_DMG:
            _trimmed(self.terminal_event_id, "flat-dmg terminal_event_id")
            if self.provider_sequence_index is not None or self.output_key != "flat_dmg":
                raise TraceContractError(
                    "terminal FlatDmg binding requires null sequence and flat_dmg key"
                )
        else:
            if self.terminal_event_id is not None or self.provider_sequence_index is not None:
                raise TraceContractError(
                    "diagnostic scalar cannot claim a terminal output coordinate"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "binding_id": self.binding_id,
            "occurrence_id": self.occurrence_id,
            "template_sha256": self.template_sha256,
            "output_kind": self.output_kind.value,
            "terminal_event_id": self.terminal_event_id,
            "provider_sequence_index": self.provider_sequence_index,
            "output_key": self.output_key,
            "observed_value": self.observed_value,
            "parameters": [row.to_dict() for row in self.parameters],
        }


@dataclass(frozen=True, slots=True)
class SourceValueEvaluation:
    binding_id: str
    baseline_value: float
    candidate_value: float
    status: SourceSliceStatus
    uncertainty_codes: tuple[str, ...]

    @property
    def authoritative(self) -> bool:
        return False

    @property
    def hard_prune_allowed(self) -> bool:
        return False

    @property
    def publishable(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class SourceDependencyEvidenceTrace:
    reaction_evidence: ReactionEvidenceTrace
    source_manifest_binding: SourceManifestBinding
    raw_payload_sha256: str
    occurrences: tuple[SourceOccurrence, ...]
    value_bindings: tuple[SourceValueBinding, ...]
    schema_version: int = SOURCE_DEPENDENCY_EVIDENCE_SCHEMA_VERSION
    kind: str = SOURCE_DEPENDENCY_EVIDENCE_KIND

    def __post_init__(self) -> None:
        _exact(
            self.schema_version,
            SOURCE_DEPENDENCY_EVIDENCE_SCHEMA_VERSION,
            "source dependency evidence schema",
        )
        _exact(self.kind, SOURCE_DEPENDENCY_EVIDENCE_KIND, "source evidence kind")
        if not isinstance(self.source_manifest_binding, SourceManifestBinding):
            raise TraceContractError(
                "source_manifest_binding must be SourceManifestBinding"
            )
        manifest = self.source_manifest_binding.manifest_body
        if (
            manifest.trace_schema_version,
            manifest.trace_capability,
        ) != (
            SOURCE_DEPENDENCY_EVIDENCE_SCHEMA_VERSION,
            "gtt_trace_equation_v4",
        ):
            raise TraceContractError(
                "source dependency evidence v4 requires a 4/v4 source manifest"
            )
        validate_source_evidence_components(
            reaction_evidence=self.reaction_evidence,
            source_manifest_binding=self.source_manifest_binding,
            raw_payload_sha256=self.raw_payload_sha256,
            occurrences=self.occurrences,
            value_bindings=self.value_bindings,
        )

    @property
    def terminal_trace(self):
        return self.reaction_evidence.terminal_trace

    @property
    def exact_replay_eligible(self) -> bool:
        return False

    @property
    def hard_prune_allowed(self) -> bool:
        return False

    @property
    def publishable(self) -> bool:
        return False

    @property
    def uncertainty_codes(self) -> tuple[str, ...]:
        bound_occurrences = {row.occurrence_id for row in self.value_bindings}
        manifest = self.source_manifest_binding.manifest_body
        codes: set[str] = set()
        for occurrence in self.occurrences:
            entry = manifest.entry_by_id(occurrence.source_id)
            assert entry is not None
            if occurrence.occurrence_id not in bound_occurrences:
                codes.add(
                    f"source_occurrence_unbound:{occurrence.occurrence_id}"
                )
            if entry.template.status is SourceSliceStatus.OPAQUE_FROZEN:
                codes.add(
                    "source_dependency_opaque_frozen:"
                    f"{occurrence.occurrence_id}:"
                    f"{entry.template.stop_reason_code}"
                )
        return tuple(sorted(codes))

    @property
    def evidence_sha256(self) -> str:
        return canonical_sha256(
            {
                "schema_version": self.schema_version,
                "kind": self.kind,
                "reaction_evidence_sha256": self.reaction_evidence.evidence_sha256,
                "source_manifest_binding_sha256": (
                    self.source_manifest_binding.binding_sha256
                ),
                "raw_payload_sha256": self.raw_payload_sha256,
                "occurrences": [row.to_dict() for row in self.occurrences],
                "value_bindings": [row.to_dict() for row in self.value_bindings],
                "uncertainty_codes": list(self.uncertainty_codes),
                "exact_replay_eligible": False,
                "hard_prune_allowed": False,
                "publishable": False,
            }
        )

    def value_binding(self, binding_id: str) -> SourceValueBinding:
        _trimmed(binding_id, "binding_id")
        row = next(
            (row for row in self.value_bindings if row.binding_id == binding_id),
            None,
        )
        if row is None:
            raise TraceContractError(f"unknown source value binding {binding_id!r}")
        return row


def validate_source_evidence_components(
    *,
    reaction_evidence: ReactionEvidenceTrace,
    source_manifest_binding: SourceManifestBinding,
    raw_payload_sha256: str,
    occurrences: tuple[SourceOccurrence, ...],
    value_bindings: tuple[SourceValueBinding, ...],
) -> None:
    """Validate the source-slice collection shared by strict V4 and V5 wrappers."""

    if not isinstance(reaction_evidence, ReactionEvidenceTrace):
        raise TraceContractError("reaction_evidence must be ReactionEvidenceTrace")
    if not isinstance(source_manifest_binding, SourceManifestBinding):
        raise TraceContractError(
            "source_manifest_binding must be SourceManifestBinding"
        )
    _sha256(raw_payload_sha256, "source evidence raw_payload_sha256")
    request = reaction_evidence.terminal_trace.request
    binding = source_manifest_binding
    if binding.engine_artifact_sha256 != request.engine_artifact_sha256:
        raise TraceContractError("source manifest executable does not match request")
    if binding.engine_binding_sha256 != request.engine_binding_sha256:
        raise TraceContractError("source manifest engine binding does not match request")
    _tuple(occurrences, "source occurrences")
    _tuple(value_bindings, "source value_bindings")
    if any(not isinstance(row, SourceOccurrence) for row in occurrences):
        raise TraceContractError("invalid source occurrence")
    if any(not isinstance(row, SourceValueBinding) for row in value_bindings):
        raise TraceContractError("invalid source value binding")
    if tuple(row.sequence_index for row in occurrences) != tuple(
        range(len(occurrences))
    ):
        raise TraceContractError("source occurrence sequence must be contiguous")
    frames = tuple(row.frame for row in occurrences)
    if frames != tuple(sorted(frames)):
        raise TraceContractError("source occurrences must preserve frame order")
    occurrence_ids = tuple(row.occurrence_id for row in occurrences)
    if len(occurrence_ids) != len(set(occurrence_ids)):
        raise TraceContractError("source occurrence IDs must be unique")
    known_occurrences: set[str] = set()
    terminal_events = {
        hit.event_id: hit for hit in reaction_evidence.terminal_trace.hits
    }
    manifest = binding.manifest_body
    character_keys = request.character_keys
    for occurrence in occurrences:
        entry = manifest.entry_by_id(occurrence.source_id)
        if entry is None:
            raise TraceContractError("source occurrence references unknown source_id")
        if entry.locator.seam is not occurrence.seam:
            raise TraceContractError("source occurrence seam does not match manifest")
        if (
            occurrence.parent_occurrence_id is not None
            and occurrence.parent_occurrence_id not in known_occurrences
        ):
            raise TraceContractError(
                "source occurrence parent must reference an earlier occurrence"
            )
        if (
            occurrence.terminal_event_id is not None
            and occurrence.terminal_event_id not in terminal_events
        ):
            raise TraceContractError(
                "source occurrence references unknown terminal event"
            )
        _validate_provider_owner(occurrence.provider, character_keys)
        known_occurrences.add(occurrence.occurrence_id)
    binding_ids = tuple(row.binding_id for row in value_bindings)
    if len(binding_ids) != len(set(binding_ids)):
        raise TraceContractError("source value binding IDs must be unique")
    occurrence_map = {row.occurrence_id: row for row in occurrences}
    output_coordinates: set[tuple[object, ...]] = set()
    binding_ordinals: dict[str, int] = {}
    for value_binding in value_bindings:
        occurrence = occurrence_map.get(value_binding.occurrence_id)
        if occurrence is None:
            raise TraceContractError(
                "source value binding references unknown occurrence"
            )
        binding_match = _BINDING_ID_RE.fullmatch(value_binding.binding_id)
        assert binding_match is not None
        occurrence_index = int(binding_match.group(1))
        ordinal = int(binding_match.group(2))
        if occurrence_index != occurrence.sequence_index:
            raise TraceContractError(
                "source value binding_id occurrence index mismatch"
            )
        expected_ordinal = binding_ordinals.get(value_binding.occurrence_id, 0)
        if ordinal != expected_ordinal:
            raise TraceContractError(
                "source value binding ordinals must be contiguous per occurrence"
            )
        binding_ordinals[value_binding.occurrence_id] = ordinal + 1
        entry = manifest.entry_by_id(occurrence.source_id)
        assert entry is not None
        if value_binding.template_sha256 != entry.template.template_sha256:
            raise TraceContractError(
                "source value binding template does not match manifest"
            )
        keys = tuple(row.parameter_key for row in value_binding.parameters)
        if keys != entry.template.parameter_keys:
            raise TraceContractError(
                "source value parameters do not match template parameters"
            )
        for parameter in value_binding.parameters:
            _validate_parameter_actor(parameter, character_keys)
        if entry.template.status is SourceSliceStatus.SUPPORTED:
            evaluated = evaluate_source_template(
                entry.template,
                {
                    row.parameter_key: row.observed_value
                    for row in value_binding.parameters
                },
            )
            if not _close(evaluated, value_binding.observed_value):
                raise TraceContractError(
                    "source slice baseline does not match observed output"
                )
        coordinate = _validate_output_binding(
            value_binding,
            occurrence,
            reaction_evidence,
        )
        if coordinate in output_coordinates:
            raise TraceContractError("duplicate source output coordinate")
        output_coordinates.add(coordinate)


def evaluate_source_template(
    template: SourceSliceTemplate,
    parameter_values: Mapping[str, float],
) -> float:
    if not isinstance(template, SourceSliceTemplate):
        raise TraceContractError("template must be SourceSliceTemplate")
    if template.status is not SourceSliceStatus.SUPPORTED:
        raise TraceContractError("OPAQUE_FROZEN template cannot be evaluated")
    if not isinstance(parameter_values, Mapping):
        raise TraceContractError("parameter_values must be a mapping")
    if set(parameter_values) != set(template.parameter_keys):
        raise TraceContractError("parameter values do not exactly match template")
    values: list[float] = []
    for node in template.nodes:
        if node.operator is SourceIROperator.CONST:
            assert node.constant_value is not None
            value = float(node.constant_value)
        elif node.operator is SourceIROperator.PARAM:
            assert node.parameter_key is not None
            value = _finite_number(
                parameter_values[node.parameter_key],
                f"parameter {node.parameter_key}",
            )
        else:
            inputs = tuple(values[index] for index in node.input_node_ids)
            if node.operator is SourceIROperator.ADD:
                value = inputs[0] + inputs[1]
            elif node.operator is SourceIROperator.SUB:
                value = inputs[0] - inputs[1]
            elif node.operator is SourceIROperator.MUL:
                value = inputs[0] * inputs[1]
            elif node.operator is SourceIROperator.DIV:
                value = inputs[0] / inputs[1]
            elif node.operator is SourceIROperator.MIN:
                value = min(inputs)
            elif node.operator is SourceIROperator.MAX:
                value = max(inputs)
            elif node.operator is SourceIROperator.ABS:
                value = abs(inputs[0])
            elif node.operator is SourceIROperator.AND:
                value = float(bool(inputs[0]) and bool(inputs[1]))
            elif node.operator is SourceIROperator.OR:
                value = float(bool(inputs[0]) or bool(inputs[1]))
            elif node.operator is SourceIROperator.EQ:
                value = float(inputs[0] == inputs[1])
            elif node.operator is SourceIROperator.NE:
                value = float(inputs[0] != inputs[1])
            elif node.operator is SourceIROperator.LT:
                value = float(inputs[0] < inputs[1])
            elif node.operator is SourceIROperator.LE:
                value = float(inputs[0] <= inputs[1])
            elif node.operator is SourceIROperator.GT:
                value = float(inputs[0] > inputs[1])
            elif node.operator is SourceIROperator.GE:
                value = float(inputs[0] >= inputs[1])
            elif node.operator is SourceIROperator.NOT:
                value = float(not bool(inputs[0]))
            else:
                assert node.operator is SourceIROperator.SELECT
                value = inputs[1] if bool(inputs[0]) else inputs[2]
        if not math.isfinite(value):
            raise TraceContractError("source IR evaluation produced non-finite value")
        values.append(value)
    assert template.root_node_id is not None
    return values[template.root_node_id]


def evaluate_source_value_binding(
    evidence: SourceDependencyEvidenceTrace,
    binding_id: str,
    candidate_stats: Mapping[tuple[str, str], float],
) -> SourceValueEvaluation:
    if not isinstance(evidence, SourceDependencyEvidenceTrace):
        raise TraceContractError("evidence must be SourceDependencyEvidenceTrace")
    if not isinstance(candidate_stats, Mapping):
        raise TraceContractError("candidate_stats must be a mapping")
    normalized: dict[tuple[str, str], float] = {}
    for key, value in candidate_stats.items():
        if (
            not isinstance(key, tuple)
            or len(key) != 2
            or not all(isinstance(item, str) and item.strip() == item and item for item in key)
        ):
            raise TraceContractError(
                "candidate stat keys must be non-empty (actor_key, stat_key) tuples"
            )
        normalized[key] = _finite_number(value, f"candidate stat {key!r}")
    binding = evidence.value_binding(binding_id)
    occurrence = next(
        row for row in evidence.occurrences if row.occurrence_id == binding.occurrence_id
    )
    entry = evidence.source_manifest_binding.manifest_body.entry_by_id(
        occurrence.source_id
    )
    assert entry is not None
    uncertainties: set[str] = set()
    if entry.template.status is SourceSliceStatus.OPAQUE_FROZEN:
        uncertainties.add(f"opaque_frozen:{entry.template.stop_reason_code}")
        if normalized and not entry.template.dependencies_complete:
            uncertainties.add("opaque_candidate_dependencies_incomplete")
        return SourceValueEvaluation(
            binding_id=binding.binding_id,
            baseline_value=binding.observed_value,
            candidate_value=binding.observed_value,
            status=entry.template.status,
            uncertainty_codes=tuple(sorted(uncertainties)),
        )
    values: dict[str, float] = {}
    consumed: set[tuple[str, str]] = set()
    for parameter in binding.parameters:
        value = parameter.observed_value
        if parameter.kind is SourceParameterKind.CANDIDATE_STAT:
            assert parameter.actor_key is not None and parameter.stat_key is not None
            if not parameter.candidate_dependency_complete:
                uncertainties.add(
                    f"candidate_stat_external_dependencies_unresolved:{parameter.parameter_key}"
                )
            coordinate = (parameter.actor_key, parameter.stat_key)
            if coordinate in normalized:
                value = normalized[coordinate]
                consumed.add(coordinate)
        elif (
            parameter.kind is SourceParameterKind.FROZEN_RUNTIME_STATE
            and not parameter.candidate_dependency_complete
            and normalized
        ):
            uncertainties.add(
                f"frozen_runtime_state_dependency_unresolved:{parameter.parameter_key}"
            )
        values[parameter.parameter_key] = value
    uncertainties.update(
        f"candidate_stat_not_consumed:{actor}:{stat}"
        for actor, stat in sorted(set(normalized) - consumed)
    )
    candidate = evaluate_source_template(entry.template, values)
    return SourceValueEvaluation(
        binding_id=binding.binding_id,
        baseline_value=binding.observed_value,
        candidate_value=candidate,
        status=entry.template.status,
        uncertainty_codes=tuple(sorted(uncertainties)),
    )


def encode_source_manifest_binding(binding: SourceManifestBinding) -> str:
    if not isinstance(binding, SourceManifestBinding):
        raise TraceContractError("binding must be SourceManifestBinding")
    return _manifest_canonical_json(binding.to_dict())


def encode_source_manifest_body(body: SourceManifestBody) -> str:
    if not isinstance(body, SourceManifestBody):
        raise TraceContractError("body must be SourceManifestBody")
    return _manifest_canonical_json(body.to_dict())


def decode_source_manifest_body(
    payload: str | bytes | bytearray,
) -> SourceManifestBody:
    return _decode_manifest_body(_decode_json(payload), "$")


def decode_source_manifest_binding(
    payload: str | bytes | bytearray,
) -> SourceManifestBinding:
    root = _decode_json(payload)
    row = _object(
        root,
        "$",
        {
            "schema_version",
            "kind",
            "manifest_body",
            "manifest_body_sha256",
            "source_tree_sha256",
            "engine_tree_sha256",
            "patch_stack_sha256",
            "patches",
            "engine_artifact_sha256",
            "engine_binding_sha256",
            "go_version",
            "binding_sha256",
        },
    )
    return SourceManifestBinding(
        schema_version=_integer(row["schema_version"], "$.schema_version"),
        kind=_string(row["kind"], "$.kind"),
        manifest_body=_decode_manifest_body(row["manifest_body"], "$.manifest_body"),
        manifest_body_sha256=_string(
            row["manifest_body_sha256"], "$.manifest_body_sha256"
        ),
        source_tree_sha256=_string(
            row["source_tree_sha256"], "$.source_tree_sha256"
        ),
        engine_tree_sha256=_string(
            row["engine_tree_sha256"], "$.engine_tree_sha256"
        ),
        patch_stack_sha256=_string(
            row["patch_stack_sha256"], "$.patch_stack_sha256"
        ),
        patches=tuple(
            _decode_patch_digest(item, f"$.patches[{index}]")
            for index, item in enumerate(_array(row["patches"], "$.patches"))
        ),
        engine_artifact_sha256=_string(
            row["engine_artifact_sha256"], "$.engine_artifact_sha256"
        ),
        engine_binding_sha256=_string(
            row["engine_binding_sha256"], "$.engine_binding_sha256"
        ),
        go_version=_string(row["go_version"], "$.go_version"),
        binding_sha256=_string(row["binding_sha256"], "$.binding_sha256"),
    )


def decode_source_occurrences(value: object, path: str) -> tuple[SourceOccurrence, ...]:
    return tuple(
        _decode_source_occurrence(item, f"{path}[{index}]")
        for index, item in enumerate(_array(value, path))
    )


def decode_source_value_bindings(
    value: object,
    path: str,
) -> tuple[SourceValueBinding, ...]:
    return tuple(
        _decode_source_value_binding(item, f"{path}[{index}]")
        for index, item in enumerate(_array(value, path))
    )


def _decode_manifest_body(value: object, path: str) -> SourceManifestBody:
    row = _object(
        value,
        path,
        {
            "schema_version",
            "kind",
            "compiler_version",
            "upstream_repo",
            "upstream_ref",
            "pristine_source_tree_sha256",
            "patches",
            "patch_stack_sha256",
            "patched_source_tree_sha256",
            "trace_schema_version",
            "trace_capability",
            "formula_identities",
            "go_toolchain",
            "build_flags",
            "entries",
        },
    )
    return SourceManifestBody(
        schema_version=_integer(row["schema_version"], f"{path}.schema_version"),
        kind=_string(row["kind"], f"{path}.kind"),
        compiler_version=_string(
            row["compiler_version"], f"{path}.compiler_version"
        ),
        upstream_repo=_string(row["upstream_repo"], f"{path}.upstream_repo"),
        upstream_ref=_string(row["upstream_ref"], f"{path}.upstream_ref"),
        pristine_source_tree_sha256=_string(
            row["pristine_source_tree_sha256"],
            f"{path}.pristine_source_tree_sha256",
        ),
        patches=tuple(
            _decode_patch_digest(item, f"{path}.patches[{index}]")
            for index, item in enumerate(_array(row["patches"], f"{path}.patches"))
        ),
        patch_stack_sha256=_string(
            row["patch_stack_sha256"], f"{path}.patch_stack_sha256"
        ),
        patched_source_tree_sha256=_string(
            row["patched_source_tree_sha256"],
            f"{path}.patched_source_tree_sha256",
        ),
        trace_schema_version=_integer(
            row["trace_schema_version"], f"{path}.trace_schema_version"
        ),
        trace_capability=_string(
            row["trace_capability"], f"{path}.trace_capability"
        ),
        formula_identities=tuple(
            _decode_formula_identity(item, f"{path}.formula_identities[{index}]")
            for index, item in enumerate(
                _array(row["formula_identities"], f"{path}.formula_identities")
            )
        ),
        go_toolchain=_decode_go_toolchain(
            row["go_toolchain"], f"{path}.go_toolchain"
        ),
        build_flags=_string_tuple(row["build_flags"], f"{path}.build_flags"),
        entries=tuple(
            _decode_manifest_entry(item, f"{path}.entries[{index}]")
            for index, item in enumerate(_array(row["entries"], f"{path}.entries"))
        ),
    )


def _decode_manifest_entry(value: object, path: str) -> SourceManifestEntry:
    row = _object(
        value,
        path,
        {"source_id", "locator", "source_node_sha256", "template"},
    )
    return SourceManifestEntry(
        source_id=_string(row["source_id"], f"{path}.source_id"),
        locator=_decode_locator(row["locator"], f"{path}.locator"),
        source_node_sha256=_string(
            row["source_node_sha256"], f"{path}.source_node_sha256"
        ),
        template=_decode_slice_template(row["template"], f"{path}.template"),
    )


def _decode_locator(value: object, path: str) -> SourceLocator:
    row = _object(
        value,
        path,
        {"module_path", "enclosing_symbol", "seam", "ordinal"},
    )
    return SourceLocator(
        module_path=_string(row["module_path"], f"{path}.module_path"),
        enclosing_symbol=_string(
            row["enclosing_symbol"], f"{path}.enclosing_symbol"
        ),
        seam=_enum_value(SourceSeam, row["seam"], f"{path}.seam"),
        ordinal=_integer(row["ordinal"], f"{path}.ordinal"),
    )


def _decode_slice_template(value: object, path: str) -> SourceSliceTemplate:
    row = _object(
        value,
        path,
        {
            "status",
            "nodes",
            "root_node_id",
            "parameter_keys",
            "dependencies_complete",
            "stop_reason_code",
            "template_sha256",
        },
    )
    root = row["root_node_id"]
    return SourceSliceTemplate(
        status=_enum_value(SourceSliceStatus, row["status"], f"{path}.status"),
        nodes=tuple(
            _decode_ir_node(item, f"{path}.nodes[{index}]")
            for index, item in enumerate(_array(row["nodes"], f"{path}.nodes"))
        ),
        root_node_id=(
            None if root is None else _integer(root, f"{path}.root_node_id")
        ),
        parameter_keys=_string_tuple(row["parameter_keys"], f"{path}.parameter_keys"),
        dependencies_complete=_boolean(
            row["dependencies_complete"], f"{path}.dependencies_complete"
        ),
        stop_reason_code=_optional_string(
            row["stop_reason_code"], f"{path}.stop_reason_code"
        ),
        template_sha256=_string(
            row["template_sha256"], f"{path}.template_sha256"
        ),
    )


def _decode_ir_node(value: object, path: str) -> SourceIRNode:
    row = _object(
        value,
        path,
        {
            "node_id",
            "operator",
            "input_node_ids",
            "constant_value",
            "parameter_key",
        },
    )
    raw_constant = row["constant_value"]
    return SourceIRNode(
        node_id=_integer(row["node_id"], f"{path}.node_id"),
        operator=_enum_value(SourceIROperator, row["operator"], f"{path}.operator"),
        input_node_ids=tuple(
            _integer(item, f"{path}.input_node_ids[{index}]")
            for index, item in enumerate(
                _array(row["input_node_ids"], f"{path}.input_node_ids")
            )
        ),
        constant_value=(
            None
            if raw_constant is None
            else _number(raw_constant, f"{path}.constant_value")
        ),
        parameter_key=_optional_string(
            row["parameter_key"], f"{path}.parameter_key"
        ),
    )


def _decode_patch_digest(value: object, path: str) -> SourcePatchDigest:
    row = _object(value, path, {"path", "sha256"})
    return SourcePatchDigest(
        path=_string(row["path"], f"{path}.path"),
        sha256=_string(row["sha256"], f"{path}.sha256"),
    )


def _decode_formula_identity(value: object, path: str) -> SourceFormulaIdentity:
    row = _object(value, path, {"id", "sha256"})
    return SourceFormulaIdentity(
        id=_string(row["id"], f"{path}.id"),
        sha256=_string(row["sha256"], f"{path}.sha256"),
    )


def _decode_go_toolchain(value: object, path: str) -> SourceGoToolchain:
    row = _object(value, path, {"version", "os", "arch"})
    return SourceGoToolchain(
        version=_string(row["version"], f"{path}.version"),
        os=_string(row["os"], f"{path}.os"),
        arch=_string(row["arch"], f"{path}.arch"),
    )


def _decode_source_occurrence(value: object, path: str) -> SourceOccurrence:
    row = _object(
        value,
        path,
        {
            "sequence_index",
            "occurrence_id",
            "source_id",
            "seam",
            "frame",
            "parent_occurrence_id",
            "provider",
            "terminal_event_id",
        },
    )
    return SourceOccurrence(
        sequence_index=_integer(row["sequence_index"], f"{path}.sequence_index"),
        occurrence_id=_string(row["occurrence_id"], f"{path}.occurrence_id"),
        source_id=_string(row["source_id"], f"{path}.source_id"),
        seam=_enum_value(SourceSeam, row["seam"], f"{path}.seam"),
        frame=_integer(row["frame"], f"{path}.frame"),
        parent_occurrence_id=_optional_string(
            row["parent_occurrence_id"], f"{path}.parent_occurrence_id"
        ),
        provider=_decode_provider(row["provider"], f"{path}.provider"),
        terminal_event_id=_optional_string(
            row["terminal_event_id"], f"{path}.terminal_event_id"
        ),
    )


def _decode_source_value_binding(value: object, path: str) -> SourceValueBinding:
    row = _object(
        value,
        path,
        {
            "binding_id",
            "occurrence_id",
            "template_sha256",
            "output_kind",
            "terminal_event_id",
            "provider_sequence_index",
            "output_key",
            "observed_value",
            "parameters",
        },
    )
    sequence = row["provider_sequence_index"]
    return SourceValueBinding(
        binding_id=_string(row["binding_id"], f"{path}.binding_id"),
        occurrence_id=_string(row["occurrence_id"], f"{path}.occurrence_id"),
        template_sha256=_string(
            row["template_sha256"], f"{path}.template_sha256"
        ),
        output_kind=_enum_value(
            SourceOutputKind,
            row["output_kind"],
            f"{path}.output_kind",
        ),
        terminal_event_id=_optional_string(
            row["terminal_event_id"], f"{path}.terminal_event_id"
        ),
        provider_sequence_index=(
            None
            if sequence is None
            else _integer(sequence, f"{path}.provider_sequence_index")
        ),
        output_key=_string(row["output_key"], f"{path}.output_key"),
        observed_value=_number(row["observed_value"], f"{path}.observed_value"),
        parameters=decode_source_parameter_bindings(
            row["parameters"], f"{path}.parameters"
        ),
    )


def decode_source_parameter_bindings(
    value: object,
    path: str,
) -> tuple[SourceParameterBinding, ...]:
    """Decode the exact source-parameter array reused by additive schemas."""

    return tuple(
        _decode_parameter_binding(item, f"{path}[{index}]")
        for index, item in enumerate(_array(value, path))
    )


def _decode_parameter_binding(value: object, path: str) -> SourceParameterBinding:
    row = _object(
        value,
        path,
        {
            "parameter_key",
            "kind",
            "observed_value",
            "actor_index",
            "actor_key",
            "stat_key",
            "read_mode",
            "read_frame",
            "candidate_dependency_complete",
        },
    )
    actor_index = row["actor_index"]
    return SourceParameterBinding(
        parameter_key=_string(row["parameter_key"], f"{path}.parameter_key"),
        kind=_enum_value(SourceParameterKind, row["kind"], f"{path}.kind"),
        observed_value=_number(row["observed_value"], f"{path}.observed_value"),
        actor_index=(
            None
            if actor_index is None
            else _integer(actor_index, f"{path}.actor_index")
        ),
        actor_key=_optional_string(row["actor_key"], f"{path}.actor_key"),
        stat_key=_optional_string(row["stat_key"], f"{path}.stat_key"),
        read_mode=_enum_value(ValueReadMode, row["read_mode"], f"{path}.read_mode"),
        read_frame=_integer(row["read_frame"], f"{path}.read_frame"),
        candidate_dependency_complete=_boolean(
            row["candidate_dependency_complete"],
            f"{path}.candidate_dependency_complete",
        ),
    )


def _decode_provider(value: object, path: str) -> ProviderIdentity:
    row = _object(value, path, {"known", "kind", "key", "owner_index", "piece_count"})
    return ProviderIdentity(
        known=_boolean(row["known"], f"{path}.known"),
        kind=_string(row["kind"], f"{path}.kind"),
        key=_string(row["key"], f"{path}.key"),
        owner_index=_integer(row["owner_index"], f"{path}.owner_index"),
        piece_count=_integer(row["piece_count"], f"{path}.piece_count"),
    )


def _validate_output_binding(
    binding: SourceValueBinding,
    occurrence: SourceOccurrence,
    evidence: ReactionEvidenceTrace,
) -> tuple[object, ...]:
    if binding.terminal_event_id != occurrence.terminal_event_id:
        raise TraceContractError(
            "source output event does not match its occurrence event"
        )
    if binding.output_kind is SourceOutputKind.DIAGNOSTIC_SCALAR:
        return ("diagnostic", binding.binding_id)
    if binding.terminal_event_id is None:
        raise TraceContractError("terminal source output is missing event ID")
    terminal = next(
        (
            hit
            for hit in evidence.terminal_trace.hits
            if hit.event_id == binding.terminal_event_id
        ),
        None,
    )
    if terminal is None:
        raise TraceContractError("source output references unknown terminal event")
    hit_evidence = next(
        (
            hit
            for hit in evidence.provider_evidence.hit_evidence
            if hit.event_id == binding.terminal_event_id
        ),
        None,
    )
    if hit_evidence is None:
        raise TraceContractError("source output lacks provider evidence event")
    _validate_terminal_parameter_reads(binding, occurrence, terminal)
    if binding.output_kind is SourceOutputKind.TERMINAL_FLAT_DMG:
        if occurrence.seam is not SourceSeam.QUEUED_ATTACK:
            raise TraceContractError("terminal FlatDmg requires queued-attack source")
        if occurrence.provider != hit_evidence.provider:
            raise TraceContractError("queued-attack provider binding mismatch")
        if not _close(terminal.formula_inputs.flat_dmg.value, binding.observed_value):
            raise TraceContractError("source FlatDmg output does not match terminal hit")
        return (binding.output_kind.value, binding.terminal_event_id, binding.output_key)
    if occurrence.seam is not SourceSeam.MODIFIER_AMOUNT:
        raise TraceContractError("attack-mod output requires modifier source")
    assert binding.provider_sequence_index is not None
    mod = next(
        (
            row
            for row in hit_evidence.attack_mods
            if row.sequence_index == binding.provider_sequence_index
        ),
        None,
    )
    if mod is None:
        raise TraceContractError("source attack-mod sequence does not exist")
    if occurrence.provider != mod.provider:
        raise TraceContractError("source attack-mod provider binding mismatch")
    delta = next((row for row in mod.delta if row.stat_key == binding.output_key), None)
    if delta is None or not _close(delta.value, binding.observed_value):
        raise TraceContractError("source attack-mod output does not match provider row")
    return (
        binding.output_kind.value,
        binding.terminal_event_id,
        binding.provider_sequence_index,
        binding.output_key,
    )


def _validate_terminal_parameter_reads(
    binding: SourceValueBinding,
    occurrence: SourceOccurrence,
    terminal,
) -> None:
    snapshot = {
        row.stat_key: row.value for row in terminal.formula_inputs.snapshot_stats
    }
    for parameter in binding.parameters:
        if parameter.kind is not SourceParameterKind.CANDIDATE_STAT:
            continue
        if parameter.read_mode is ValueReadMode.SNAPSHOT:
            if parameter.read_frame != terminal.snapshot_frame:
                raise TraceContractError(
                    "source candidate stat read frame does not match bound read seam"
                )
        elif parameter.read_frame > occurrence.frame:
            # A live value may be captured while AttackInfo is constructed and
            # forwarded through a delayed helper before QueueAttack records the
            # source occurrence.  It cannot, however, be read after that seam.
            raise TraceContractError(
                "source candidate stat read frame is after bound read seam"
            )
        if parameter.read_mode is not ValueReadMode.SNAPSHOT:
            continue
        if parameter.actor_key != terminal.actor_key:
            continue
        observed = _derived_snapshot_stat(snapshot, parameter.stat_key)
        if observed is not None and not _close(observed, parameter.observed_value):
            raise TraceContractError(
                "source candidate stat value does not match terminal snapshot"
            )


def _derived_snapshot_stat(
    snapshot: Mapping[str, float],
    stat_key: str | None,
) -> float | None:
    if stat_key is None:
        return None
    if stat_key in snapshot:
        return snapshot[stat_key]
    components = {
        "max_hp": ("base_hp", "hp%", "hp"),
        "total_atk": ("base_atk", "atk%", "atk"),
        "total_def": ("base_def", "def%", "def"),
    }.get(stat_key)
    if components is None or any(key not in snapshot for key in components):
        return None
    base_key, percent_key, flat_key = components
    return snapshot[base_key] * (1.0 + snapshot[percent_key]) + snapshot[flat_key]


def _validate_parameter_actor(
    parameter: SourceParameterBinding,
    character_keys: tuple[str, ...],
) -> None:
    if parameter.actor_index is None:
        return
    if (
        parameter.actor_index >= len(character_keys)
        or character_keys[parameter.actor_index] != parameter.actor_key
    ):
        raise TraceContractError("source parameter actor index/key binding mismatch")


def _validate_provider_owner(
    provider: ProviderIdentity,
    character_keys: tuple[str, ...],
) -> None:
    if provider.known and provider.owner_index >= len(character_keys):
        raise TraceContractError("source provider owner_index exceeds character catalog")
    if (
        provider.known
        and provider.kind.casefold() == "character"
        and character_keys[provider.owner_index] != provider.key
    ):
        raise TraceContractError(
            "source character provider owner index/key binding mismatch"
        )


def _exact_manifest_text(
    values: Mapping[str, str],
    key: str,
    expected: str,
) -> None:
    actual = values.get(key)
    if actual != expected:
        raise TraceContractError(
            f"engine manifest {key} does not match source manifest body"
        )


def _patches_from_engine_manifest(
    patch_metadata: Mapping[str, str],
) -> tuple[SourcePatchDigest, ...]:
    try:
        raw_paths = json.loads(patch_metadata.get("patch_files", ""))
        raw_hashes = json.loads(patch_metadata.get("patch_file_sha256", ""))
    except (TypeError, json.JSONDecodeError) as exc:
        raise TraceContractError(
            "engine manifest patch identities are not valid JSON"
        ) from exc
    if not isinstance(raw_paths, list) or not isinstance(raw_hashes, dict):
        raise TraceContractError(
            "engine manifest patch identities require ordered paths and hash map"
        )
    if any(not isinstance(path, str) for path in raw_paths):
        raise TraceContractError("engine manifest patch paths must be strings")
    if set(raw_hashes) != set(raw_paths) or len(raw_paths) != len(set(raw_paths)):
        raise TraceContractError(
            "engine manifest patch path/hash catalogs do not match"
        )
    return tuple(
        SourcePatchDigest(path=path, sha256=raw_hashes[path])
        for path in raw_paths
    )


def _module_path(value: object, label: str) -> None:
    _relative_path(value, label)
    assert isinstance(value, str)
    if not value.endswith(".go"):
        raise TraceContractError(f"{label} must identify a .go module-relative file")


def _relative_path(value: object, label: str) -> None:
    _trimmed(value, label)
    assert isinstance(value, str)
    if "\\" in value or ":" in value or value.startswith("/"):
        raise TraceContractError(f"{label} must be a portable relative path")
    parts = PurePosixPath(value).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise TraceContractError(f"{label} must not contain empty/dot traversal parts")


def _machine_code(value: object, label: str) -> None:
    _trimmed(value, label)
    assert isinstance(value, str)
    if _MACHINE_CODE_RE.fullmatch(value) is None:
        raise TraceContractError(f"{label} must be lower_snake_case")


def _trimmed(value: object, label: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise TraceContractError(f"{label} must be a non-empty trimmed string")


def _optional_trimmed(value: object, label: str) -> None:
    if value is not None:
        _trimmed(value, label)


def _sha256(value: object, label: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise TraceContractError(f"{label} must be lower-case SHA-256")


def _finite(value: object, label: str) -> None:
    _finite_number(value, label)


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceContractError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise TraceContractError(f"{label} must be finite")
    return result


def _nonnegative_int(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TraceContractError(f"{label} must be a non-negative integer")


def _optional_nonnegative_int(value: object, label: str) -> None:
    if value is not None:
        _nonnegative_int(value, label)


def _bool(value: object, label: str) -> None:
    if not isinstance(value, bool):
        raise TraceContractError(f"{label} must be boolean")


def _tuple(value: object, label: str) -> None:
    if not isinstance(value, tuple):
        raise TraceContractError(f"{label} must be an immutable tuple")


def _sorted_unique_strings(value: object, label: str) -> None:
    _tuple(value, label)
    assert isinstance(value, tuple)
    if any(not isinstance(item, str) or not item or item.strip() != item for item in value):
        raise TraceContractError(f"{label} must contain non-empty trimmed strings")
    if value != tuple(sorted(set(value))):
        raise TraceContractError(f"{label} must be sorted and unique")


def _string_tuple(value: object, path: str) -> tuple[str, ...]:
    return tuple(
        _string(item, f"{path}[{index}]")
        for index, item in enumerate(_array(value, path))
    )


def _exact(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise TraceContractError(f"{label} must equal {expected!r}")


def _enum(value: object, enum_type: type[Enum], label: str) -> None:
    if not isinstance(value, enum_type):
        raise TraceContractError(f"{label} must be {enum_type.__name__}")


def _enum_value(enum_type, value: object, path: str):
    raw = _string(value, path)
    try:
        return enum_type(raw)
    except ValueError as exc:
        raise TraceContractError(f"{path} has unknown enum value {raw!r}") from exc


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)


__all__ = [
    "SOURCE_DEPENDENCY_EVIDENCE_KIND",
    "SOURCE_DEPENDENCY_EVIDENCE_SCHEMA_VERSION",
    "SOURCE_HEALTH_EVIDENCE_CAPABILITY",
    "SOURCE_HEALTH_EVIDENCE_SCHEMA_VERSION",
    "SOURCE_STATE_EVIDENCE_CAPABILITY",
    "SOURCE_STATE_EVIDENCE_SCHEMA_VERSION",
    "SOURCE_COMPILER_VERSION",
    "SOURCE_MANIFEST_BINDING_KIND",
    "SOURCE_MANIFEST_BINDING_SCHEMA_VERSION",
    "SOURCE_MANIFEST_KIND",
    "SOURCE_MANIFEST_SCHEMA_VERSION",
    "SOURCE_IR_FORMULA_ID",
    "SOURCE_IR_FORMULA_SHA256",
    "SOURCE_STATE_COMPILER_VERSION",
    "SOURCE_STATE_IR_FORMULA_ID",
    "SOURCE_STATE_IR_FORMULA_SHA256",
    "SourceDependencyEvidenceTrace",
    "SourceFormulaIdentity",
    "SourceGoToolchain",
    "SourceIROperator",
    "SourceIRNode",
    "SourceLocator",
    "SourceManifestBinding",
    "SourceManifestBody",
    "SourceManifestEntry",
    "SourceOccurrence",
    "SourceOutputKind",
    "SourceParameterBinding",
    "SourceParameterKind",
    "SourcePatchDigest",
    "SourceSeam",
    "SourceSliceStatus",
    "SourceSliceTemplate",
    "SourceValueBinding",
    "SourceValueEvaluation",
    "decode_source_manifest_binding",
    "decode_source_manifest_body",
    "decode_source_occurrences",
    "decode_source_parameter_bindings",
    "decode_source_value_bindings",
    "encode_source_manifest_binding",
    "encode_source_manifest_body",
    "evaluate_source_template",
    "evaluate_source_value_binding",
    "source_manifest_binding_sha256",
    "source_manifest_body_sha256",
    "source_patch_stack_sha256",
    "source_slice_template_sha256",
    "validate_source_evidence_components",
]
