"""Deterministic, secret-free diagnostics for unsupported V6 mechanics.

This module does not widen replay or pruning authority.  It converts already
validated V6 evidence into a bounded report and a fail-open routing decision.
Product UI/export wiring and exact-run scheduling remain later composition work.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import math

from .contracts import TraceContractError, canonical_json, canonical_sha256
from .source_dependencies import SourceParameterKind, SourceSliceStatus
from .state_evidence import StateEvidenceTrace


UNKNOWN_MECHANIC_REPORT_SCHEMA_VERSION = 2
UNKNOWN_MECHANIC_REPORT_KIND = "gtt.trace_equation.unknown_mechanic_report"

_FORBIDDEN_KEY_FRAGMENTS = (
    "authorization",
    "browser_profile",
    "cookie",
    "credential",
    "password",
    "secret",
    "session",
    "token",
)


class BoundaryReachability(str, Enum):
    PROVEN_INDEPENDENT = "PROVEN_INDEPENDENT"
    PROVEN_REACHABLE = "PROVEN_REACHABLE"
    UNKNOWN = "UNKNOWN"


class BoundaryFallback(str, Enum):
    BASELINE_FROZEN = "BASELINE_FROZEN"
    KEEP_FOR_EXACT = "KEEP_FOR_EXACT"
    UNSUPPORTED_STOP = "UNSUPPORTED_STOP"


@dataclass(frozen=True, slots=True)
class UnknownMechanicBoundaryKey:
    reason_code: str
    source_id: str | None

    def __post_init__(self) -> None:
        if not self.reason_code or self.reason_code.strip() != self.reason_code:
            raise TraceContractError("unknown boundary reason_code must be trimmed")
        if self.source_id is not None and (
            not self.source_id or self.source_id.strip() != self.source_id
        ):
            raise TraceContractError("unknown boundary source_id must be trimmed")

    def to_dict(self) -> dict[str, object]:
        return {"reason_code": self.reason_code, "source_id": self.source_id}

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, UnknownMechanicBoundaryKey):
            return NotImplemented
        return (self.reason_code, self.source_id or "") < (
            other.reason_code,
            other.source_id or "",
        )


@dataclass(frozen=True, slots=True)
class ExecutedUnknownBoundaryEvidence:
    event_ids: tuple[str, ...]
    occurrence_ids: tuple[str, ...]
    binding_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, name in (
            (self.event_ids, "event_ids"),
            (self.occurrence_ids, "occurrence_ids"),
            (self.binding_ids, "binding_ids"),
        ):
            if tuple(sorted(set(value))) != value:
                raise TraceContractError(f"{name} must be sorted unique")


@dataclass(frozen=True, slots=True)
class UnknownMechanicBoundary:
    reason_code: str
    source_id: str | None
    module_path: str | None
    enclosing_symbol: str | None
    seam: str | None
    ordinal: int | None
    source_template_sha256: str | None
    event_ids: tuple[str, ...]
    affected_candidate_dimensions: tuple[str, ...]
    reachability: BoundaryReachability
    topology_may_change: bool
    direct_baseline_damage: float | None
    direct_baseline_damage_share: float | None
    fallback: BoundaryFallback
    routing_reason: str

    def __post_init__(self) -> None:
        if not self.reason_code or self.reason_code.strip() != self.reason_code:
            raise TraceContractError("unknown mechanic reason_code must be trimmed")
        if tuple(sorted(set(self.event_ids))) != self.event_ids:
            raise TraceContractError("unknown mechanic event_ids must be sorted unique")
        if (
            tuple(sorted(set(self.affected_candidate_dimensions)))
            != self.affected_candidate_dimensions
        ):
            raise TraceContractError(
                "affected candidate dimensions must be sorted unique"
            )
        if not isinstance(self.topology_may_change, bool):
            raise TraceContractError("topology_may_change must be boolean")
        for value, name in (
            (self.direct_baseline_damage, "direct_baseline_damage"),
            (self.direct_baseline_damage_share, "direct_baseline_damage_share"),
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise TraceContractError(f"{name} must be finite and non-negative")
        if (
            self.direct_baseline_damage_share is not None
            and self.direct_baseline_damage_share > 1.0
        ):
            raise TraceContractError("direct_baseline_damage_share must be in [0, 1]")
        if not self.routing_reason or self.routing_reason.strip() != self.routing_reason:
            raise TraceContractError("unknown mechanic routing_reason must be trimmed")
        if self.reachability is BoundaryReachability.PROVEN_INDEPENDENT:
            if self.topology_may_change:
                raise TraceContractError(
                    "proven-independent boundary cannot change topology"
                )
            if self.fallback is not BoundaryFallback.BASELINE_FROZEN:
                raise TraceContractError(
                    "proven-independent boundary must freeze baseline"
                )
        elif self.fallback is BoundaryFallback.BASELINE_FROZEN:
            raise TraceContractError(
                "unknown-reachability boundary cannot freeze baseline"
            )

    @property
    def boundary_id(self) -> str:
        return canonical_sha256(self.to_dict(include_id=False))

    def to_dict(self, *, include_id: bool = True) -> dict[str, object]:
        row: dict[str, object] = {
            "reason_code": self.reason_code,
            "source_id": self.source_id,
            "module_path": self.module_path,
            "enclosing_symbol": self.enclosing_symbol,
            "seam": self.seam,
            "ordinal": self.ordinal,
            "source_template_sha256": self.source_template_sha256,
            "event_ids": list(self.event_ids),
            "affected_candidate_dimensions": list(
                self.affected_candidate_dimensions
            ),
            "reachability": self.reachability.value,
            "topology_may_change": self.topology_may_change,
            "direct_baseline_damage": self.direct_baseline_damage,
            "direct_baseline_damage_share": self.direct_baseline_damage_share,
            "fallback": self.fallback.value,
            "routing_reason": self.routing_reason,
        }
        if include_id:
            row = {"boundary_id": self.boundary_id, **row}
        return row


@dataclass(frozen=True, slots=True)
class UnknownMechanicReport:
    trace_evidence_sha256: str
    raw_payload_sha256: str
    source_manifest_body_sha256: str
    source_manifest_binding_sha256: str
    compiler_version: str
    source_ir_id: str
    source_ir_sha256: str
    upstream_ref: str
    patch_stack_sha256: str
    context_sha256: str
    source_config_sha256: str
    compiled_action_sha256: str
    target_sha256: str
    boundaries: tuple[UnknownMechanicBoundary, ...]
    boundary_count_total: int
    exact_boundary_budget: int
    exact_boundary_required: int
    exact_boundary_admitted: int
    exact_boundary_overflow: bool
    routing_complete: bool
    truncated: bool
    schema_version: int = UNKNOWN_MECHANIC_REPORT_SCHEMA_VERSION
    kind: str = UNKNOWN_MECHANIC_REPORT_KIND

    def __post_init__(self) -> None:
        if self.schema_version != UNKNOWN_MECHANIC_REPORT_SCHEMA_VERSION:
            raise TraceContractError("unknown mechanic report schema mismatch")
        if self.kind != UNKNOWN_MECHANIC_REPORT_KIND:
            raise TraceContractError("unknown mechanic report kind mismatch")
        if self.boundary_count_total < len(self.boundaries):
            raise TraceContractError("boundary_count_total is smaller than payload")
        if self.truncated is not (self.boundary_count_total > len(self.boundaries)):
            raise TraceContractError("unknown mechanic truncated flag mismatch")
        for value, name in (
            (self.exact_boundary_budget, "exact_boundary_budget"),
            (self.exact_boundary_required, "exact_boundary_required"),
            (self.exact_boundary_admitted, "exact_boundary_admitted"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise TraceContractError(f"{name} must be non-negative integer")
        expected_overflow = self.exact_boundary_required > self.exact_boundary_budget
        if self.exact_boundary_overflow is not expected_overflow:
            raise TraceContractError("exact boundary overflow flag mismatch")
        expected_admitted = 0 if expected_overflow else self.exact_boundary_required
        if self.exact_boundary_admitted != expected_admitted:
            raise TraceContractError("exact boundary admitted count mismatch")
        if self.routing_complete is expected_overflow:
            raise TraceContractError("unknown mechanic routing_complete mismatch")
        expected_fallback = (
            BoundaryFallback.UNSUPPORTED_STOP
            if expected_overflow
            else BoundaryFallback.KEEP_FOR_EXACT
        )
        if any(
            row.reachability is not BoundaryReachability.PROVEN_INDEPENDENT
            and row.fallback is not expected_fallback
            for row in self.boundaries
        ):
            raise TraceContractError("unknown mechanic fallback disagrees with budget")
        ids = tuple(row.boundary_id for row in self.boundaries)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise TraceContractError("unknown mechanic boundaries must be canonical")

    @property
    def report_sha256(self) -> str:
        return canonical_sha256(self.to_dict(include_hash=False))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        row: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "trace_evidence_sha256": self.trace_evidence_sha256,
            "raw_payload_sha256": self.raw_payload_sha256,
            "source_manifest_body_sha256": self.source_manifest_body_sha256,
            "source_manifest_binding_sha256": (
                self.source_manifest_binding_sha256
            ),
            "compiler_version": self.compiler_version,
            "source_ir_id": self.source_ir_id,
            "source_ir_sha256": self.source_ir_sha256,
            "upstream_ref": self.upstream_ref,
            "patch_stack_sha256": self.patch_stack_sha256,
            "context_sha256": self.context_sha256,
            "source_config_sha256": self.source_config_sha256,
            "compiled_action_sha256": self.compiled_action_sha256,
            "target_sha256": self.target_sha256,
            "boundaries": [row.to_dict() for row in self.boundaries],
            "boundary_count_total": self.boundary_count_total,
            "exact_boundary_budget": self.exact_boundary_budget,
            "exact_boundary_required": self.exact_boundary_required,
            "exact_boundary_admitted": self.exact_boundary_admitted,
            "exact_boundary_overflow": self.exact_boundary_overflow,
            "routing_complete": self.routing_complete,
            "truncated": self.truncated,
        }
        if include_hash:
            row = {**row, "report_sha256": self.report_sha256}
        return row


def build_unknown_mechanic_report(
    trace: StateEvidenceTrace,
    *,
    exact_boundary_budget: int,
    candidate_independent_source_ids: frozenset[str],
    candidate_reachable_source_ids: frozenset[str],
    topology_changing_source_ids: frozenset[str],
    affected_dimensions_by_source: Mapping[str, tuple[str, ...]],
    max_boundaries: int,
    max_events_per_boundary: int,
    candidate_independent_boundary_keys: frozenset[
        UnknownMechanicBoundaryKey
    ] = frozenset(),
    candidate_reachable_boundary_keys: frozenset[
        UnknownMechanicBoundaryKey
    ] = frozenset(),
) -> UnknownMechanicReport:
    """Build a bounded report without granting replay/pruning authority."""

    if not isinstance(trace, StateEvidenceTrace):
        raise TraceContractError("unknown mechanic report requires V6 evidence")
    if (
        isinstance(exact_boundary_budget, bool)
        or not isinstance(exact_boundary_budget, int)
        or exact_boundary_budget < 0
    ):
        raise TraceContractError("exact_boundary_budget must be non-negative integer")
    if max_boundaries <= 0 or max_events_per_boundary <= 0:
        raise TraceContractError("diagnostic bounds must be positive")
    _validate_source_id_set(
        candidate_independent_source_ids, "candidate_independent_source_ids"
    )
    _validate_source_id_set(
        candidate_reachable_source_ids, "candidate_reachable_source_ids"
    )
    _validate_source_id_set(
        topology_changing_source_ids, "topology_changing_source_ids"
    )
    _validate_boundary_key_set(
        candidate_independent_boundary_keys,
        "candidate_independent_boundary_keys",
    )
    _validate_boundary_key_set(
        candidate_reachable_boundary_keys,
        "candidate_reachable_boundary_keys",
    )
    overlap = candidate_independent_source_ids & (
        candidate_reachable_source_ids | topology_changing_source_ids
    )
    if overlap:
        raise TraceContractError(
            "candidate-independent source IDs cannot be reachable/topology-changing"
        )
    if candidate_independent_boundary_keys & candidate_reachable_boundary_keys:
        raise TraceContractError(
            "candidate-independent boundary keys cannot be reachable"
        )

    manifest = trace.source_manifest_binding.manifest_body
    entry_by_id = {entry.source_id: entry for entry in manifest.entries}
    collected = collect_executed_unknown_boundaries(trace)
    drafts = tuple(
        (key, evidence.event_ids) for key, evidence in collected.items()
    )
    required = sum(
        key not in candidate_independent_boundary_keys
        and key.source_id not in candidate_independent_source_ids
        for key, _ in drafts
    )
    overflow = required > exact_boundary_budget
    damage_by_source, team_damage = _direct_damage_by_source(trace)

    boundaries: list[UnknownMechanicBoundary] = []
    for key, event_ids in drafts:
        reason, source_id = key.reason_code, key.source_id
        entry = entry_by_id.get(source_id) if source_id is not None else None
        independent = (
            key in candidate_independent_boundary_keys
            or (
                source_id is not None
                and source_id in candidate_independent_source_ids
            )
        )
        reachable = (
            key in candidate_reachable_boundary_keys
            or source_id in candidate_reachable_source_ids
        )
        reachability = (
            BoundaryReachability.PROVEN_INDEPENDENT
            if independent
            else BoundaryReachability.PROVEN_REACHABLE
            if reachable
            else BoundaryReachability.UNKNOWN
        )
        fallback = (
            BoundaryFallback.BASELINE_FROZEN
            if independent
            else BoundaryFallback.UNSUPPORTED_STOP
            if overflow
            else BoundaryFallback.KEEP_FOR_EXACT
        )
        topology_may_change = source_id in topology_changing_source_ids
        routing_reason = (
            "proven_candidate_independent"
            if independent
            else "exact_boundary_budget_exhausted"
            if overflow
            else "schedule_change_exact_required"
            if topology_may_change
            else "candidate_reachable_exact_required"
            if reachability is BoundaryReachability.PROVEN_REACHABLE
            else "reachability_unknown_exact_required"
        )
        dimensions = (
            affected_dimensions_by_source.get(source_id, ())
            if source_id is not None
            else ()
        )
        dimensions = tuple(sorted(set(dimensions)))
        selected_events = tuple(sorted(event_ids))[:max_events_per_boundary]
        direct_damage = damage_by_source.get(source_id) if source_id is not None else None
        direct_share = (
            None
            if direct_damage is None or team_damage <= 0.0
            else direct_damage / team_damage
        )
        boundaries.append(
            UnknownMechanicBoundary(
                reason_code=reason,
                source_id=source_id,
                module_path=entry.locator.module_path if entry else None,
                enclosing_symbol=(
                    entry.locator.enclosing_symbol if entry else None
                ),
                seam=entry.locator.seam.value if entry else None,
                ordinal=entry.locator.ordinal if entry else None,
                source_template_sha256=(
                    entry.template.template_sha256 if entry else None
                ),
                event_ids=selected_events,
                affected_candidate_dimensions=dimensions,
                reachability=reachability,
                topology_may_change=topology_may_change,
                direct_baseline_damage=direct_damage,
                direct_baseline_damage_share=direct_share,
                fallback=fallback,
                routing_reason=routing_reason,
            )
        )

    boundaries.sort(key=lambda row: row.boundary_id)
    total = len(boundaries)
    selected = tuple(boundaries[:max_boundaries])
    terminal = trace.terminal_trace
    request = terminal.request
    source_ir = next(
        row
        for row in manifest.formula_identities
        if row.id == "gtt_source_ir_v2"
    )
    report = UnknownMechanicReport(
        trace_evidence_sha256=trace.evidence_sha256,
        raw_payload_sha256=trace.raw_payload_sha256,
        source_manifest_body_sha256=manifest.body_sha256,
        source_manifest_binding_sha256=(
            trace.source_manifest_binding.binding_sha256
        ),
        compiler_version=manifest.compiler_version,
        source_ir_id=source_ir.id,
        source_ir_sha256=source_ir.sha256,
        upstream_ref=manifest.upstream_ref,
        patch_stack_sha256=manifest.patch_stack_sha256,
        context_sha256=request.context_sha256,
        source_config_sha256=request.source_config_sha256,
        compiled_action_sha256=request.compiled_action_sha256,
        target_sha256=request.target_sha256,
        boundaries=selected,
        boundary_count_total=total,
        exact_boundary_budget=exact_boundary_budget,
        exact_boundary_required=required,
        exact_boundary_admitted=0 if overflow else required,
        exact_boundary_overflow=overflow,
        routing_complete=not overflow,
        truncated=total > len(selected),
    )
    validate_secret_free_diagnostic(report.to_dict())
    return report


def collect_executed_unknown_boundaries(
    trace: StateEvidenceTrace,
) -> dict[UnknownMechanicBoundaryKey, ExecutedUnknownBoundaryEvidence]:
    """Return deterministic physical receipts for executed unknown boundaries."""

    if not isinstance(trace, StateEvidenceTrace):
        raise TraceContractError("unknown boundary collection requires V6 evidence")
    manifest = trace.source_manifest_binding.manifest_body
    entry_by_id = {entry.source_id: entry for entry in manifest.entries}
    occurrence_by_id = {row.occurrence_id: row for row in trace.occurrences}
    mutable: dict[UnknownMechanicBoundaryKey, dict[str, set[str]]] = {}

    def receipt(key: UnknownMechanicBoundaryKey) -> dict[str, set[str]]:
        return mutable.setdefault(
            key,
            {"event_ids": set(), "occurrence_ids": set(), "binding_ids": set()},
        )

    for occurrence in trace.occurrences:
        entry = entry_by_id[occurrence.source_id]
        if entry.template.status is not SourceSliceStatus.OPAQUE_FROZEN:
            continue
        assert entry.template.stop_reason_code is not None
        row = receipt(
            UnknownMechanicBoundaryKey(
                entry.template.stop_reason_code,
                entry.source_id,
            )
        )
        row["occurrence_ids"].add(occurrence.occurrence_id)
        if occurrence.terminal_event_id is not None:
            row["event_ids"].add(occurrence.terminal_event_id)
    for binding in trace.value_bindings:
        occurrence = occurrence_by_id[binding.occurrence_id]
        for parameter in binding.parameters:
            if (
                parameter.kind is SourceParameterKind.FROZEN_RUNTIME_STATE
                and not parameter.candidate_dependency_complete
            ):
                key = UnknownMechanicBoundaryKey(
                    "frozen_runtime_state_dependency_unresolved:"
                    f"{parameter.parameter_key}",
                    occurrence.source_id,
                )
                row = receipt(key)
                row["binding_ids"].add(binding.binding_id)
                row["occurrence_ids"].add(binding.occurrence_id)
                if binding.terminal_event_id is not None:
                    row["event_ids"].add(binding.terminal_event_id)
    for event in trace.state_events:
        for reason in event.uncertainty_codes:
            receipt(
                UnknownMechanicBoundaryKey(reason, event.source_id)
            )["event_ids"].add(event.event_id)

    return {
        key: ExecutedUnknownBoundaryEvidence(
            event_ids=tuple(sorted(row["event_ids"])),
            occurrence_ids=tuple(sorted(row["occurrence_ids"])),
            binding_ids=tuple(sorted(row["binding_ids"])),
        )
        for key, row in sorted(mutable.items())
    }


def _direct_damage_by_source(
    trace: StateEvidenceTrace,
) -> tuple[dict[str, float], float]:
    hit_by_id = {
        hit.event_id: hit for hit in trace.terminal_trace.hits
    }
    events_by_source: dict[str, set[str]] = {}
    for occurrence in trace.occurrences:
        if occurrence.terminal_event_id in hit_by_id:
            events_by_source.setdefault(occurrence.source_id, set()).add(
                occurrence.terminal_event_id
            )
    damage = {
        source_id: sum(hit_by_id[event_id].uncapped_rolled_damage for event_id in events)
        for source_id, events in events_by_source.items()
    }
    team_damage = sum(hit.uncapped_rolled_damage for hit in hit_by_id.values())
    return damage, team_damage


def _validate_source_id_set(value: object, field_name: str) -> None:
    if not isinstance(value, frozenset) or any(
        not isinstance(row, str) or not row or row.strip() != row for row in value
    ):
        raise TraceContractError(f"{field_name} must be a frozenset of source IDs")


def _validate_boundary_key_set(value: object, field_name: str) -> None:
    if not isinstance(value, frozenset) or any(
        not isinstance(row, UnknownMechanicBoundaryKey) for row in value
    ):
        raise TraceContractError(
            f"{field_name} must be a frozenset of boundary keys"
        )


def diagnostic_json(report: UnknownMechanicReport) -> str:
    if not isinstance(report, UnknownMechanicReport):
        raise TraceContractError("diagnostic_json requires UnknownMechanicReport")
    payload = report.to_dict()
    validate_secret_free_diagnostic(payload)
    return canonical_json(payload)


def validate_secret_free_diagnostic(value: object, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TraceContractError(f"{path} contains a non-string key")
            lowered = key.lower()
            if any(fragment in lowered for fragment in _FORBIDDEN_KEY_FRAGMENTS):
                raise TraceContractError(
                    f"{path}.{key} is forbidden in diagnostic export"
                )
            validate_secret_free_diagnostic(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            validate_secret_free_diagnostic(child, f"{path}[{index}]")


__all__ = [
    "BoundaryFallback",
    "BoundaryReachability",
    "UNKNOWN_MECHANIC_REPORT_KIND",
    "UNKNOWN_MECHANIC_REPORT_SCHEMA_VERSION",
    "UnknownMechanicBoundary",
    "UnknownMechanicBoundaryKey",
    "UnknownMechanicReport",
    "build_unknown_mechanic_report",
    "collect_executed_unknown_boundaries",
    "diagnostic_json",
    "validate_secret_free_diagnostic",
]
