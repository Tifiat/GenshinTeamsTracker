"""Strict, source-bound manifest body codec shared with trace consumers.

This module intentionally imports no trace package. It preserves the source
manifest body's existing canonical bytes, strict decoder, and object types.
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

from .trace_contract_error import TraceContractError


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


def encode_source_manifest_body(body: SourceManifestBody) -> str:
    if not isinstance(body, SourceManifestBody):
        raise TraceContractError("body must be SourceManifestBody")
    return _manifest_canonical_json(body.to_dict())


def decode_source_manifest_body(
    payload: str | bytes | bytearray,
) -> SourceManifestBody:
    return _decode_manifest_body(_decode_json(payload), "$")


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


def _decode_json(payload: str | bytes | bytearray) -> object:
    if isinstance(payload, (bytes, bytearray)):
        try:
            text = bytes(payload).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TraceContractError("trace payload is not UTF-8") from exc
    elif isinstance(payload, str):
        text = payload
    else:
        raise TraceContractError("trace payload must be str or UTF-8 bytes")

    def pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise TraceContractError(f"duplicate JSON object key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise TraceContractError(f"non-finite JSON number {value!r} is forbidden")

    try:
        return json.loads(
            text,
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
    except TraceContractError:
        raise
    except (TypeError, ValueError) as exc:
        raise TraceContractError(f"invalid trace JSON: {exc}") from exc


def _object(value: object, path: str, exact_keys: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TraceContractError(f"{path} must be an object")
    actual = set(value)
    if actual != exact_keys:
        missing = sorted(exact_keys - actual)
        unknown = sorted(actual - exact_keys)
        raise TraceContractError(
            f"{path} object keys mismatch; missing={missing!r}, unknown={unknown!r}"
        )
    return value


def _array(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise TraceContractError(f"{path} must be an array")
    return value


def _string_tuple(value: object, path: str) -> tuple[str, ...]:
    return tuple(
        _string(item, f"{path}[{index}]")
        for index, item in enumerate(_array(value, path))
    )


def _string(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise TraceContractError(f"{path} must be a string")
    return value


def _optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TraceContractError(f"{path} must be an integer")
    return value


def _number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceContractError(f"{path} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise TraceContractError(f"{path} must be finite")
    return result


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise TraceContractError(f"{path} must be a boolean")
    return value

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


__all__ = [
    "SOURCE_MANIFEST_SCHEMA_VERSION", "SOURCE_MANIFEST_KIND",
    "SOURCE_DEPENDENCY_EVIDENCE_SCHEMA_VERSION",
    "SOURCE_HEALTH_EVIDENCE_SCHEMA_VERSION", "SOURCE_STATE_EVIDENCE_SCHEMA_VERSION",
    "SOURCE_COMPILER_VERSION", "SOURCE_IR_FORMULA_ID", "SOURCE_IR_FORMULA_SHA256",
    "SOURCE_STATE_COMPILER_VERSION", "SOURCE_STATE_IR_FORMULA_ID",
    "SOURCE_STATE_IR_FORMULA_SHA256", "SourceSeam", "SourceSliceStatus",
    "SourceIROperator", "SourceLocator", "SourceIRNode", "SourceSliceTemplate",
    "SourceManifestEntry", "SourcePatchDigest", "SourceFormulaIdentity",
    "SourceGoToolchain", "SourceManifestBody", "source_slice_template_sha256",
    "source_manifest_body_sha256", "source_patch_stack_sha256",
    "encode_source_manifest_body", "decode_source_manifest_body",
]
