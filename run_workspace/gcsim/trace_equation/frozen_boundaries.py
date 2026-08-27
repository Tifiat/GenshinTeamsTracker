"""Always-available scoring contract for partially understood trace equations.

Unknown mechanics freeze at their observed baseline value.  They reduce
coverage and pruning authority, but never make the cheap candidate scorer
unavailable.  Exact finalist observations are accepted only as an explicit
post-ranking reconciliation step; this module never starts the engine.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .candidate_dependencies import (
    CandidateDependencySlice,
    CandidateStatCoordinate,
    build_candidate_dependency_slice,
)
from .contracts import TraceContractError, TraceDocument, canonical_sha256
from .observed_snapshot import (
    ArtifactStatReplacement,
    ObservedSnapshotScore,
    score_observed_artifact_replacement,
)
from .ranking import RankingSupport
from .reaction_evidence import ReactionEvidenceTrace
from .state_evidence import StateEvidenceTrace


FROZEN_BOUNDARY_SCORE_SCHEMA_VERSION = 1
FROZEN_BOUNDARY_SCORE_KIND = "gtt.trace_equation.frozen_boundary_score"
FROZEN_COVERAGE_SCHEMA_VERSION = 1
FROZEN_COVERAGE_KIND = "gtt.trace_equation.frozen_boundary_coverage"
EXACT_FINALIST_OBSERVATION_SCHEMA_VERSION = 1
EXACT_FINALIST_OBSERVATION_KIND = "gtt.trace_equation.exact_finalist_observation"
EXACT_FINALIST_RESIDUAL_SCHEMA_VERSION = 1
EXACT_FINALIST_RESIDUAL_KIND = "gtt.trace_equation.exact_finalist_residual"

FrozenRankingDocument = TraceDocument | ReactionEvidenceTrace | StateEvidenceTrace

_REL_TOL = 1e-9
_ABS_TOL = 1e-7

_PROVENANCE_ONLY_PREFIXES = (
    "provider_identity_",
    "provider_origin_",
)

_TOPOLOGY_TOKENS = (
    "action",
    "aura",
    "callback_state",
    "count",
    "death",
    "gadget",
    "guard",
    "icd",
    "occurrence",
    "owner",
    "persistent",
    "schedule",
    "target",
    "topology",
)


@dataclass(frozen=True, slots=True)
class FrozenHitCoverage:
    event_id: str
    baseline_damage: float
    whole_contribution_frozen: bool
    frozen_input_exposed: bool
    topology_exposed: bool
    input_uncertainty_codes: tuple[str, ...]
    topology_uncertainty_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _trimmed(self.event_id, "frozen hit event_id")
        _finite_nonnegative(self.baseline_damage, "frozen hit baseline_damage")
        for value, name in (
            (self.whole_contribution_frozen, "whole_contribution_frozen"),
            (self.frozen_input_exposed, "frozen_input_exposed"),
            (self.topology_exposed, "topology_exposed"),
        ):
            if not isinstance(value, bool):
                raise TraceContractError(f"{name} must be boolean")
        _canonical_strings(
            self.input_uncertainty_codes,
            "input_uncertainty_codes",
        )
        _canonical_strings(
            self.topology_uncertainty_codes,
            "topology_uncertainty_codes",
        )
        if self.whole_contribution_frozen and self.frozen_input_exposed:
            raise TraceContractError(
                "whole-frozen hit cannot also claim partial frozen-input exposure"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "baseline_damage": self.baseline_damage,
            "whole_contribution_frozen": self.whole_contribution_frozen,
            "frozen_input_exposed": self.frozen_input_exposed,
            "topology_exposed": self.topology_exposed,
            "input_uncertainty_codes": list(self.input_uncertainty_codes),
            "topology_uncertainty_codes": list(
                self.topology_uncertainty_codes
            ),
        }


@dataclass(frozen=True, slots=True)
class FrozenBoundaryCoverage:
    reference_baseline_damage: float
    observed_rolled_damage: float
    crit_sampling_gap: float
    modeled_baseline_damage: float
    whole_frozen_damage: float
    frozen_input_exposed_damage: float
    topology_exposed_damage: float
    baseline_reconciliation_error: float
    baseline_reconciled: bool
    modeled_hit_count: int
    whole_frozen_hit_count: int
    frozen_input_exposed_hit_count: int
    topology_exposed_hit_count: int
    candidate_reachable_whole_frozen_damage: float
    candidate_reachable_frozen_input_damage: float
    candidate_reachable_topology_damage: float
    candidate_affected_hit_count: int
    candidate_reachable_boundary_count: int
    candidate_unresolved_boundary_count: int
    candidate_dependency_slice_sha256: str | None
    candidate_dependency_gap_codes: tuple[str, ...]
    hits: tuple[FrozenHitCoverage, ...]
    global_input_uncertainty_codes: tuple[str, ...]
    global_topology_uncertainty_codes: tuple[str, ...]
    uncertainty_codes: tuple[str, ...]
    schema_version: int = FROZEN_COVERAGE_SCHEMA_VERSION
    kind: str = FROZEN_COVERAGE_KIND

    def __post_init__(self) -> None:
        if self.schema_version != FROZEN_COVERAGE_SCHEMA_VERSION:
            raise TraceContractError("frozen coverage schema mismatch")
        if self.kind != FROZEN_COVERAGE_KIND:
            raise TraceContractError("frozen coverage kind mismatch")
        for value, name in (
            (self.reference_baseline_damage, "reference_baseline_damage"),
            (self.observed_rolled_damage, "observed_rolled_damage"),
            (self.modeled_baseline_damage, "modeled_baseline_damage"),
            (self.whole_frozen_damage, "whole_frozen_damage"),
            (self.frozen_input_exposed_damage, "frozen_input_exposed_damage"),
            (self.topology_exposed_damage, "topology_exposed_damage"),
            (
                self.candidate_reachable_whole_frozen_damage,
                "candidate_reachable_whole_frozen_damage",
            ),
            (
                self.candidate_reachable_frozen_input_damage,
                "candidate_reachable_frozen_input_damage",
            ),
            (
                self.candidate_reachable_topology_damage,
                "candidate_reachable_topology_damage",
            ),
        ):
            _finite_nonnegative(value, name)
        _finite(self.crit_sampling_gap, "crit_sampling_gap")
        _finite(
            self.baseline_reconciliation_error,
            "baseline_reconciliation_error",
        )
        if not isinstance(self.baseline_reconciled, bool):
            raise TraceContractError("baseline_reconciled must be boolean")
        for value, name in (
            (self.modeled_hit_count, "modeled_hit_count"),
            (self.whole_frozen_hit_count, "whole_frozen_hit_count"),
            (
                self.frozen_input_exposed_hit_count,
                "frozen_input_exposed_hit_count",
            ),
            (self.topology_exposed_hit_count, "topology_exposed_hit_count"),
            (self.candidate_affected_hit_count, "candidate_affected_hit_count"),
            (
                self.candidate_reachable_boundary_count,
                "candidate_reachable_boundary_count",
            ),
            (
                self.candidate_unresolved_boundary_count,
                "candidate_unresolved_boundary_count",
            ),
        ):
            _nonnegative_int(value, name)
        if not isinstance(self.hits, tuple) or any(
            not isinstance(row, FrozenHitCoverage) for row in self.hits
        ):
            raise TraceContractError("frozen coverage hits are invalid")
        event_ids = tuple(row.event_id for row in self.hits)
        if len(event_ids) != len(set(event_ids)):
            raise TraceContractError("frozen coverage hit IDs must be unique")
        if self.modeled_hit_count + self.whole_frozen_hit_count != len(self.hits):
            raise TraceContractError("frozen coverage hit partition mismatch")
        if self.frozen_input_exposed_hit_count != sum(
            row.frozen_input_exposed for row in self.hits
        ):
            raise TraceContractError("frozen-input hit count mismatch")
        if self.topology_exposed_hit_count != sum(
            row.topology_exposed for row in self.hits
        ):
            raise TraceContractError("topology hit count mismatch")
        if self.candidate_affected_hit_count > len(self.hits):
            raise TraceContractError("candidate affected hit count exceeds trace")
        if self.candidate_dependency_slice_sha256 is None:
            if any(
                (
                    self.candidate_affected_hit_count,
                    self.candidate_reachable_boundary_count,
                    self.candidate_unresolved_boundary_count,
                )
            ) or self.candidate_dependency_gap_codes:
                raise TraceContractError(
                    "candidate dependency data requires a slice identity"
                )
        else:
            _sha256(
                self.candidate_dependency_slice_sha256,
                "candidate_dependency_slice_sha256",
            )
        _canonical_strings(
            self.candidate_dependency_gap_codes,
            "candidate_dependency_gap_codes",
        )
        _canonical_strings(
            self.global_input_uncertainty_codes,
            "global_input_uncertainty_codes",
        )
        _canonical_strings(
            self.global_topology_uncertainty_codes,
            "global_topology_uncertainty_codes",
        )
        _canonical_strings(self.uncertainty_codes, "uncertainty_codes")
        expected_error = self.reference_baseline_damage - (
            self.modeled_baseline_damage + self.whole_frozen_damage
        )
        if not _close(expected_error, self.baseline_reconciliation_error):
            raise TraceContractError("baseline reconciliation arithmetic mismatch")
        if self.baseline_reconciled is not _close(
            self.baseline_reconciliation_error, 0.0
        ):
            raise TraceContractError("baseline_reconciled flag mismatch")
        for value, name in (
            (self.whole_frozen_damage, "whole_frozen_damage"),
            (
                self.frozen_input_exposed_damage,
                "frozen_input_exposed_damage",
            ),
            (self.topology_exposed_damage, "topology_exposed_damage"),
            (
                self.candidate_reachable_whole_frozen_damage,
                "candidate_reachable_whole_frozen_damage",
            ),
            (
                self.candidate_reachable_frozen_input_damage,
                "candidate_reachable_frozen_input_damage",
            ),
            (
                self.candidate_reachable_topology_damage,
                "candidate_reachable_topology_damage",
            ),
        ):
            if value > self.reference_baseline_damage + _ABS_TOL:
                raise TraceContractError(f"{name} exceeds reference baseline")
        for candidate_value, trace_value, name in (
            (
                self.candidate_reachable_whole_frozen_damage,
                self.whole_frozen_damage,
                "candidate reachable whole-frozen damage",
            ),
            (
                self.candidate_reachable_frozen_input_damage,
                self.frozen_input_exposed_damage,
                "candidate reachable frozen-input damage",
            ),
            (
                self.candidate_reachable_topology_damage,
                self.topology_exposed_damage,
                "candidate reachable topology damage",
            ),
        ):
            if candidate_value > trace_value + _ABS_TOL:
                raise TraceContractError(f"{name} exceeds trace-wide exposure")

    @property
    def whole_frozen_share(self) -> float:
        return _share(self.whole_frozen_damage, self.reference_baseline_damage)

    @property
    def frozen_input_exposure_share(self) -> float:
        return _share(
            self.frozen_input_exposed_damage,
            self.reference_baseline_damage,
        )

    @property
    def topology_exposure_share(self) -> float:
        return _share(
            self.topology_exposed_damage,
            self.reference_baseline_damage,
        )

    @property
    def majority_whole_frozen(self) -> bool:
        return self.whole_frozen_share > 0.5

    @property
    def candidate_reachable_whole_frozen_share(self) -> float:
        return _share(
            self.candidate_reachable_whole_frozen_damage,
            self.reference_baseline_damage,
        )

    @property
    def candidate_reachable_frozen_input_share(self) -> float:
        return _share(
            self.candidate_reachable_frozen_input_damage,
            self.reference_baseline_damage,
        )

    @property
    def candidate_reachable_topology_share(self) -> float:
        return _share(
            self.candidate_reachable_topology_damage,
            self.reference_baseline_damage,
        )

    @property
    def fully_modeled_response(self) -> bool:
        return (
            self.whole_frozen_hit_count == 0
            and self.frozen_input_exposed_hit_count == 0
            and self.topology_exposed_hit_count == 0
            and not self.global_input_uncertainty_codes
            and not self.global_topology_uncertainty_codes
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "reference_baseline_damage": self.reference_baseline_damage,
            "observed_rolled_damage": self.observed_rolled_damage,
            "crit_sampling_gap": self.crit_sampling_gap,
            "modeled_baseline_damage": self.modeled_baseline_damage,
            "whole_frozen_damage": self.whole_frozen_damage,
            "whole_frozen_share": self.whole_frozen_share,
            "frozen_input_exposed_damage": self.frozen_input_exposed_damage,
            "frozen_input_exposure_share": self.frozen_input_exposure_share,
            "topology_exposed_damage": self.topology_exposed_damage,
            "topology_exposure_share": self.topology_exposure_share,
            "baseline_reconciliation_error": self.baseline_reconciliation_error,
            "baseline_reconciled": self.baseline_reconciled,
            "modeled_hit_count": self.modeled_hit_count,
            "whole_frozen_hit_count": self.whole_frozen_hit_count,
            "frozen_input_exposed_hit_count": (
                self.frozen_input_exposed_hit_count
            ),
            "topology_exposed_hit_count": self.topology_exposed_hit_count,
            "candidate_reachable_whole_frozen_damage": (
                self.candidate_reachable_whole_frozen_damage
            ),
            "candidate_reachable_whole_frozen_share": (
                self.candidate_reachable_whole_frozen_share
            ),
            "candidate_reachable_frozen_input_damage": (
                self.candidate_reachable_frozen_input_damage
            ),
            "candidate_reachable_frozen_input_share": (
                self.candidate_reachable_frozen_input_share
            ),
            "candidate_reachable_topology_damage": (
                self.candidate_reachable_topology_damage
            ),
            "candidate_reachable_topology_share": (
                self.candidate_reachable_topology_share
            ),
            "candidate_affected_hit_count": self.candidate_affected_hit_count,
            "candidate_reachable_boundary_count": (
                self.candidate_reachable_boundary_count
            ),
            "candidate_unresolved_boundary_count": (
                self.candidate_unresolved_boundary_count
            ),
            "candidate_dependency_slice_sha256": (
                self.candidate_dependency_slice_sha256
            ),
            "candidate_dependency_gap_codes": list(
                self.candidate_dependency_gap_codes
            ),
            "majority_whole_frozen": self.majority_whole_frozen,
            "fully_modeled_response": self.fully_modeled_response,
            "hits": [row.to_dict() for row in self.hits],
            "global_input_uncertainty_codes": list(
                self.global_input_uncertainty_codes
            ),
            "global_topology_uncertainty_codes": list(
                self.global_topology_uncertainty_codes
            ),
            "uncertainty_codes": list(self.uncertainty_codes),
        }


@dataclass(frozen=True, slots=True)
class FrozenBoundaryScore:
    observed_score: ObservedSnapshotScore
    coverage: FrozenBoundaryCoverage
    baseline_estimate: float
    candidate_estimate: float
    estimated_delta: float
    engine_call_count: int = 0
    schema_version: int = FROZEN_BOUNDARY_SCORE_SCHEMA_VERSION
    kind: str = FROZEN_BOUNDARY_SCORE_KIND

    def __post_init__(self) -> None:
        if self.schema_version != FROZEN_BOUNDARY_SCORE_SCHEMA_VERSION:
            raise TraceContractError("frozen boundary score schema mismatch")
        if self.kind != FROZEN_BOUNDARY_SCORE_KIND:
            raise TraceContractError("frozen boundary score kind mismatch")
        if not isinstance(self.observed_score, ObservedSnapshotScore):
            raise TraceContractError("observed_score is invalid")
        if not isinstance(self.coverage, FrozenBoundaryCoverage):
            raise TraceContractError("coverage is invalid")
        for value, name in (
            (self.baseline_estimate, "baseline_estimate"),
            (self.candidate_estimate, "candidate_estimate"),
            (self.estimated_delta, "estimated_delta"),
        ):
            _finite(value, name)
        if not _close(
            self.estimated_delta,
            self.candidate_estimate - self.baseline_estimate,
        ):
            raise TraceContractError("frozen score delta mismatch")
        if not _close(
            self.baseline_estimate,
            self.coverage.reference_baseline_damage,
        ):
            raise TraceContractError("frozen score baseline/coverage mismatch")
        if self.engine_call_count != 0:
            raise TraceContractError("frozen boundary score cannot call engine")

    @property
    def candidate_sha256(self) -> str:
        return self.observed_score.candidate_sha256

    @property
    def orderable(self) -> bool:
        # Even a completely frozen candidate has a deterministic numeric tie.
        return True

    @property
    def publishable(self) -> bool:
        return False

    @property
    def hard_prune_allowed(self) -> bool:
        return False

    @property
    def score_sha256(self) -> str:
        return canonical_sha256(self.to_dict(include_hash=False))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        row: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "candidate_sha256": self.candidate_sha256,
            "baseline_estimate": self.baseline_estimate,
            "candidate_estimate": self.candidate_estimate,
            "estimated_delta": self.estimated_delta,
            "coverage": self.coverage.to_dict(),
            "ranking_support": self.observed_score.ranking.support.value,
            "ranking_uncertainty_codes": list(
                self.observed_score.ranking.uncertainty_codes
            ),
            "orderable": True,
            "publishable": False,
            "hard_prune_allowed": False,
            "engine_call_count": 0,
        }
        if include_hash:
            row["score_sha256"] = self.score_sha256
        return row


@dataclass(frozen=True, slots=True)
class ExactFinalistObservation:
    candidate_sha256: str
    exact_baseline_damage: float
    exact_candidate_damage: float
    fidelity_sha256: str
    seed_panel_sha256: str
    schema_version: int = EXACT_FINALIST_OBSERVATION_SCHEMA_VERSION
    kind: str = EXACT_FINALIST_OBSERVATION_KIND

    def __post_init__(self) -> None:
        if self.schema_version != EXACT_FINALIST_OBSERVATION_SCHEMA_VERSION:
            raise TraceContractError("exact finalist observation schema mismatch")
        if self.kind != EXACT_FINALIST_OBSERVATION_KIND:
            raise TraceContractError("exact finalist observation kind mismatch")
        _sha256(self.candidate_sha256, "candidate_sha256")
        _finite_nonnegative(
            self.exact_baseline_damage, "exact_baseline_damage"
        )
        _finite_nonnegative(
            self.exact_candidate_damage, "exact_candidate_damage"
        )
        _sha256(self.fidelity_sha256, "fidelity_sha256")
        _sha256(self.seed_panel_sha256, "seed_panel_sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "candidate_sha256": self.candidate_sha256,
            "exact_baseline_damage": self.exact_baseline_damage,
            "exact_candidate_damage": self.exact_candidate_damage,
            "fidelity_sha256": self.fidelity_sha256,
            "seed_panel_sha256": self.seed_panel_sha256,
        }


@dataclass(frozen=True, slots=True)
class ExactFinalistResidual:
    candidate_sha256: str
    score_sha256: str
    fidelity_sha256: str
    seed_panel_sha256: str
    offline_baseline_damage: float
    offline_candidate_damage: float
    exact_baseline_damage: float
    exact_candidate_damage: float
    baseline_missed_response: float
    candidate_missed_response: float
    change_in_missed_response: float
    engine_call_count: int = 0
    schema_version: int = EXACT_FINALIST_RESIDUAL_SCHEMA_VERSION
    kind: str = EXACT_FINALIST_RESIDUAL_KIND

    def __post_init__(self) -> None:
        if self.schema_version != EXACT_FINALIST_RESIDUAL_SCHEMA_VERSION:
            raise TraceContractError("exact finalist residual schema mismatch")
        if self.kind != EXACT_FINALIST_RESIDUAL_KIND:
            raise TraceContractError("exact finalist residual kind mismatch")
        for value, name in (
            (self.offline_baseline_damage, "offline_baseline_damage"),
            (self.offline_candidate_damage, "offline_candidate_damage"),
            (self.exact_baseline_damage, "exact_baseline_damage"),
            (self.exact_candidate_damage, "exact_candidate_damage"),
        ):
            _finite_nonnegative(value, name)
        for value, name in (
            (self.baseline_missed_response, "baseline_missed_response"),
            (self.candidate_missed_response, "candidate_missed_response"),
            (self.change_in_missed_response, "change_in_missed_response"),
        ):
            _finite(value, name)
        for value, name in (
            (self.candidate_sha256, "candidate_sha256"),
            (self.score_sha256, "score_sha256"),
            (self.fidelity_sha256, "fidelity_sha256"),
            (self.seed_panel_sha256, "seed_panel_sha256"),
        ):
            _sha256(value, name)
        if not _close(
            self.baseline_missed_response,
            self.exact_baseline_damage - self.offline_baseline_damage,
        ):
            raise TraceContractError("baseline missed-response mismatch")
        if not _close(
            self.candidate_missed_response,
            self.exact_candidate_damage - self.offline_candidate_damage,
        ):
            raise TraceContractError("candidate missed-response mismatch")
        if not _close(
            self.change_in_missed_response,
            self.candidate_missed_response - self.baseline_missed_response,
        ):
            raise TraceContractError("change in missed response mismatch")
        if self.engine_call_count != 0:
            raise TraceContractError("residual calculation cannot call engine")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "candidate_sha256": self.candidate_sha256,
            "score_sha256": self.score_sha256,
            "fidelity_sha256": self.fidelity_sha256,
            "seed_panel_sha256": self.seed_panel_sha256,
            "offline_baseline_damage": self.offline_baseline_damage,
            "offline_candidate_damage": self.offline_candidate_damage,
            "exact_baseline_damage": self.exact_baseline_damage,
            "exact_candidate_damage": self.exact_candidate_damage,
            "baseline_missed_response": self.baseline_missed_response,
            "candidate_missed_response": self.candidate_missed_response,
            "change_in_missed_response": self.change_in_missed_response,
            "engine_call_count": 0,
        }


def score_with_frozen_boundaries(
    document: FrozenRankingDocument,
    replacements: tuple[ArtifactStatReplacement, ...],
    *,
    candidate_dependency_slice: CandidateDependencySlice | None = None,
) -> FrozenBoundaryScore:
    """Return a numeric heuristic even when every observed hit is frozen."""

    observed = score_observed_artifact_replacement(document, replacements)
    baseline = observed.ranking.baseline_score
    candidate = observed.ranking.candidate_score
    if baseline is None or candidate is None:
        raise TraceContractError(
            "frozen-boundary scoring requires at least one finite damage occurrence"
        )
    expected_coordinates = _candidate_coordinates(document, replacements)
    dependency_slice = candidate_dependency_slice
    if dependency_slice is None and expected_coordinates:
        assert isinstance(document, StateEvidenceTrace)
        dependency_slice = build_candidate_dependency_slice(
            document,
            expected_coordinates,
        )
    elif dependency_slice is not None:
        if dependency_slice.coordinates != expected_coordinates:
            raise TraceContractError(
                "candidate dependency slice coordinates do not match replacements"
            )
    coverage = build_frozen_boundary_coverage(
        document,
        observed,
        candidate_dependency_slice=dependency_slice,
    )
    return FrozenBoundaryScore(
        observed_score=observed,
        coverage=coverage,
        baseline_estimate=baseline,
        candidate_estimate=candidate,
        estimated_delta=candidate - baseline,
    )


def build_frozen_boundary_coverage(
    document: FrozenRankingDocument,
    observed: ObservedSnapshotScore,
    *,
    candidate_dependency_slice: CandidateDependencySlice | None = None,
) -> FrozenBoundaryCoverage:
    """Partition whole-frozen damage and overlapping response exposures."""

    trace = _terminal_document(document)
    estimates = observed.ranking.hits
    if len(trace.hits) != len(estimates):
        raise TraceContractError("coverage trace/ranking hit count mismatch")
    if observed.ranking.baseline_score is None:
        raise TraceContractError("coverage requires a finite baseline score")

    hit_codes = {code for row in estimates for code in row.uncertainty_codes}
    global_only_codes = set(observed.ranking.uncertainty_codes) - hit_codes
    global_topology_codes = tuple(
        sorted(code for code in global_only_codes if _is_topology_code(code))
    )
    global_input_codes = tuple(
        sorted(code for code in global_only_codes if _is_input_code(code))
    )

    _validate_candidate_dependency_slice(document, candidate_dependency_slice)
    rows: list[FrozenHitCoverage] = []
    for estimate in estimates:
        topology_codes = tuple(
            sorted(
                {
                    *(
                        code
                        for code in estimate.uncertainty_codes
                        if _is_topology_code(code)
                    ),
                }
            )
        )
        input_codes = tuple(
            sorted(
                {
                    *(
                        code
                        for code in estimate.uncertainty_codes
                        if _is_input_code(code)
                    ),
                }
            )
        )
        whole = estimate.support is not RankingSupport.MODELED_EXPECTATION
        rows.append(
            FrozenHitCoverage(
                event_id=estimate.event_id,
                baseline_damage=estimate.baseline_score,
                whole_contribution_frozen=whole,
                frozen_input_exposed=bool(input_codes) and not whole,
                topology_exposed=bool(topology_codes),
                input_uncertainty_codes=() if whole else input_codes,
                topology_uncertainty_codes=topology_codes,
            )
        )

    reference = float(observed.ranking.baseline_score)
    modeled = sum(
        row.baseline_damage for row in rows if not row.whole_contribution_frozen
    )
    whole_frozen = sum(
        row.baseline_damage for row in rows if row.whole_contribution_frozen
    )
    frozen_input = sum(
        row.baseline_damage for row in rows if row.frozen_input_exposed
    )
    topology = sum(row.baseline_damage for row in rows if row.topology_exposed)
    affected_hit_ids = (
        frozenset(candidate_dependency_slice.affected_hit_event_ids)
        if candidate_dependency_slice is not None
        else frozenset()
    )
    candidate_whole_frozen = sum(
        row.baseline_damage
        for row in rows
        if row.event_id in affected_hit_ids and row.whole_contribution_frozen
    )
    candidate_frozen_input = sum(
        row.baseline_damage
        for row in rows
        if row.event_id in affected_hit_ids and row.frozen_input_exposed
    )
    candidate_topology = sum(
        row.baseline_damage
        for row in rows
        if row.event_id in affected_hit_ids and row.topology_exposed
    )
    reconciliation_error = reference - (modeled + whole_frozen)
    observed_rolled = sum(hit.uncapped_rolled_damage for hit in trace.hits)
    return FrozenBoundaryCoverage(
        reference_baseline_damage=reference,
        observed_rolled_damage=observed_rolled,
        crit_sampling_gap=observed_rolled - reference,
        modeled_baseline_damage=modeled,
        whole_frozen_damage=whole_frozen,
        frozen_input_exposed_damage=frozen_input,
        topology_exposed_damage=topology,
        baseline_reconciliation_error=reconciliation_error,
        baseline_reconciled=_close(reconciliation_error, 0.0),
        modeled_hit_count=sum(not row.whole_contribution_frozen for row in rows),
        whole_frozen_hit_count=sum(row.whole_contribution_frozen for row in rows),
        frozen_input_exposed_hit_count=sum(
            row.frozen_input_exposed for row in rows
        ),
        topology_exposed_hit_count=sum(row.topology_exposed for row in rows),
        candidate_reachable_whole_frozen_damage=candidate_whole_frozen,
        candidate_reachable_frozen_input_damage=candidate_frozen_input,
        candidate_reachable_topology_damage=candidate_topology,
        candidate_affected_hit_count=len(affected_hit_ids),
        candidate_reachable_boundary_count=(
            len(candidate_dependency_slice.reachable_boundary_keys)
            if candidate_dependency_slice is not None
            else 0
        ),
        candidate_unresolved_boundary_count=(
            len(candidate_dependency_slice.unresolved_boundary_keys)
            if candidate_dependency_slice is not None
            else 0
        ),
        candidate_dependency_slice_sha256=(
            candidate_dependency_slice.slice_sha256
            if candidate_dependency_slice is not None
            else None
        ),
        candidate_dependency_gap_codes=(
            candidate_dependency_slice.coverage_gap_codes
            if candidate_dependency_slice is not None
            else ()
        ),
        hits=tuple(rows),
        global_input_uncertainty_codes=global_input_codes,
        global_topology_uncertainty_codes=global_topology_codes,
        uncertainty_codes=observed.ranking.uncertainty_codes,
    )


def reconcile_exact_finalist(
    score: FrozenBoundaryScore,
    observation: ExactFinalistObservation,
) -> ExactFinalistResidual:
    """Measure net missed response for an already-run paired exact finalist."""

    if not isinstance(score, FrozenBoundaryScore):
        raise TraceContractError("exact reconciliation requires FrozenBoundaryScore")
    if not isinstance(observation, ExactFinalistObservation):
        raise TraceContractError(
            "exact reconciliation requires ExactFinalistObservation"
        )
    if observation.candidate_sha256 != score.candidate_sha256:
        raise TraceContractError("exact finalist candidate identity mismatch")
    baseline_residual = (
        observation.exact_baseline_damage - score.baseline_estimate
    )
    candidate_residual = (
        observation.exact_candidate_damage - score.candidate_estimate
    )
    return ExactFinalistResidual(
        candidate_sha256=score.candidate_sha256,
        score_sha256=score.score_sha256,
        fidelity_sha256=observation.fidelity_sha256,
        seed_panel_sha256=observation.seed_panel_sha256,
        offline_baseline_damage=score.baseline_estimate,
        offline_candidate_damage=score.candidate_estimate,
        exact_baseline_damage=observation.exact_baseline_damage,
        exact_candidate_damage=observation.exact_candidate_damage,
        baseline_missed_response=baseline_residual,
        candidate_missed_response=candidate_residual,
        change_in_missed_response=candidate_residual - baseline_residual,
    )


def _terminal_document(document: FrozenRankingDocument) -> TraceDocument:
    if isinstance(document, StateEvidenceTrace):
        return document.terminal_trace
    if isinstance(document, ReactionEvidenceTrace):
        return document.terminal_trace
    if isinstance(document, TraceDocument):
        return document
    raise TraceContractError("frozen boundary scorer requires a trace document")


def _candidate_coordinates(
    document: FrozenRankingDocument,
    replacements: tuple[ArtifactStatReplacement, ...],
) -> tuple[CandidateStatCoordinate, ...]:
    if not isinstance(document, StateEvidenceTrace):
        return ()
    return tuple(
        sorted(
            {
                CandidateStatCoordinate(row.actor_key, row.stat_key)
                for row in replacements
                if not _close(
                    row.baseline_artifact_value,
                    row.candidate_artifact_value,
                )
            }
        )
    )


def _validate_candidate_dependency_slice(
    document: FrozenRankingDocument,
    dependency_slice: CandidateDependencySlice | None,
) -> None:
    if dependency_slice is None:
        return
    if not isinstance(document, StateEvidenceTrace):
        raise TraceContractError(
            "candidate dependency slice requires the matching V6 state trace"
        )
    if dependency_slice.trace_evidence_sha256 != document.evidence_sha256:
        raise TraceContractError("candidate dependency slice trace identity mismatch")


def _is_topology_code(code: str) -> bool:
    lowered = code.casefold()
    return any(token in lowered for token in _TOPOLOGY_TOKENS)


def _is_input_code(code: str) -> bool:
    if _is_topology_code(code):
        return False
    return not any(code.startswith(prefix) for prefix in _PROVENANCE_ONLY_PREFIXES)


def _share(value: float, total: float) -> float:
    if total <= 0.0:
        return 0.0
    return min(1.0, max(0.0, value / total))


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)


def _trimmed(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise TraceContractError(f"{field_name} must be a trimmed string")


def _canonical_strings(value: object, field_name: str) -> None:
    if not isinstance(value, tuple) or any(
        not isinstance(row, str) or not row or row.strip() != row for row in value
    ):
        raise TraceContractError(f"{field_name} must contain trimmed strings")
    if tuple(sorted(set(value))) != value:
        raise TraceContractError(f"{field_name} must be sorted unique")


def _nonnegative_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TraceContractError(f"{field_name} must be non-negative integer")


def _finite(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceContractError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)):
        raise TraceContractError(f"{field_name} must be finite")


def _finite_nonnegative(value: object, field_name: str) -> None:
    _finite(value, field_name)
    if float(value) < 0.0:
        raise TraceContractError(f"{field_name} must be non-negative")


def _sha256(value: object, field_name: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise TraceContractError(f"{field_name} must be lowercase SHA-256")


__all__ = [
    "EXACT_FINALIST_OBSERVATION_KIND",
    "EXACT_FINALIST_OBSERVATION_SCHEMA_VERSION",
    "EXACT_FINALIST_RESIDUAL_KIND",
    "EXACT_FINALIST_RESIDUAL_SCHEMA_VERSION",
    "FROZEN_BOUNDARY_SCORE_KIND",
    "FROZEN_BOUNDARY_SCORE_SCHEMA_VERSION",
    "FROZEN_COVERAGE_KIND",
    "FROZEN_COVERAGE_SCHEMA_VERSION",
    "ExactFinalistObservation",
    "ExactFinalistResidual",
    "FrozenBoundaryCoverage",
    "FrozenBoundaryScore",
    "FrozenHitCoverage",
    "build_frozen_boundary_coverage",
    "reconcile_exact_finalist",
    "score_with_frozen_boundaries",
]
