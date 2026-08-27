"""Experimental shared artifact-first account optimizer.

The current selected/package-first services remain the production baseline.
This module is an independent shadow path: it starts from the frozen physical
inventory, builds injective four-wearer matchings per artifact slot, joins the
matchings across slots, derives packages only from complete assignments, and
uses the common exact multifidelity race as its oracle.

The bounded matching/beam scores are proposal evidence only.  They are never
reported as DPS and never authorize a hard artifact prune.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
import hashlib
import json
from math import isfinite
from threading import Event, Lock
from time import monotonic

from .optimizer_anytime_candidates import (
    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
    GcsimOptimizerAnytimeStatProfile,
    GcsimOptimizerDenseArtifact,
    GcsimOptimizerDenseArtifactCatalog,
    build_gcsim_optimizer_dense_artifact_catalog,
)
from .optimizer_anytime_race import (
    GcsimOptimizerAnytimeRaceEvaluation,
    GcsimOptimizerAnytimeRacePlan,
    GcsimOptimizerAnytimeRaceResult,
    GcsimOptimizerAnytimeRaceSession,
    GcsimOptimizerAnytimeRaceStatus,
    build_gcsim_optimizer_account_package_signature,
)
from .optimizer_anytime_response import (
    GcsimOptimizerAnytimeResponsePlan,
    GcsimOptimizerAnytimeResponseResult,
    discover_gcsim_optimizer_anytime_response,
)
from .optimizer_artifact_materializer import (
    compile_gcsim_optimizer_team_candidate,
    materialize_gcsim_optimizer_wearer_build,
)
from .optimizer_cache import GcsimOptimizerCacheStore
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_inventory_frontier import (
    GcsimOptimizerInventoryFrontierResult,
    build_gcsim_optimizer_inventory_frontier,
)
from .optimizer_joint_proposals import GcsimOptimizerJointProposal
from .optimizer_lazy_candidates import GcsimOptimizerLazyWearerCandidate
from .optimizer_physical_package import (
    derive_gcsim_optimizer_target_from_physical_artifacts,
)
from .optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerAccountAssignmentWitness,
    GcsimOptimizerAccountScope,
    GcsimOptimizerCacheCounters,
    GcsimOptimizerCandidateResult,
    GcsimOptimizerCoverageCounters,
    GcsimOptimizerDpsEstimate,
    GcsimOptimizerEvaluationIdentity,
    GcsimOptimizerOperation,
    GcsimOptimizerProgressEvent,
    GcsimOptimizerProgressStage,
    GcsimOptimizerSetReference,
    GcsimOptimizerTerminalResult,
    GcsimOptimizerTerminalStatus,
    GcsimOptimizerTimingCounters,
    GcsimOptimizerWearerArtifactAssignment,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerTarget,
    GcsimTwoPlusTwoTargetPackage,
    build_gcsim_optimizer_top_n,
)
from .optimizer_run_input import GcsimOptimizerRunInput
from .optimizer_set_impact import (
    GcsimOptimizerSetImpactPlan,
    GcsimOptimizerSetImpactResult,
    GcsimOptimizerSingleTwoPieceImpactTarget,
    discover_gcsim_optimizer_set_impacts,
)
from .optimizer_stat_response import (
    GCSIM_SET_RESPONSE_CAPABILITY,
    GcsimStatResponseTarget,
)


GCSIM_OPTIMIZER_ARTIFACT_FIRST_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_ID = "artifact_first_shared_v1"
GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_VERSION = 4


class GcsimOptimizerArtifactFirstError(RuntimeError):
    """Fail-closed experimental-kernel error."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerArtifactFirstPlan:
    response: GcsimOptimizerAnytimeResponsePlan = field(
        default_factory=lambda: GcsimOptimizerAnytimeResponsePlan(
            enable_nonlinear_surface=True
        )
    )
    set_impact: GcsimOptimizerSetImpactPlan = field(
        default_factory=lambda: GcsimOptimizerSetImpactPlan(
            enable_team_interaction_panel=True
        )
    )
    race: GcsimOptimizerAnytimeRacePlan = field(
        default_factory=GcsimOptimizerAnytimeRacePlan
    )
    max_focus_signatures: int = 64
    response_directions_per_focus: int = 6
    per_wearer_slot_head: int = 12
    slot_matching_beam_width: int = 64
    max_slot_matchings: int = 192
    cross_slot_beam_width: int = 512
    max_complete_assignments: int = 256
    cap_aware_local_neighbors_per_direction: int = 2
    max_exact_finalists: int = 64
    top_n: int = 8
    overall_deadline_seconds: float = 1200.0
    schema_version: int = GCSIM_OPTIMIZER_ARTIFACT_FIRST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_ARTIFACT_FIRST_SCHEMA_VERSION:
            raise GcsimOptimizerArtifactFirstError(
                "unsupported artifact-first plan schema"
            )
        if not isinstance(self.response, GcsimOptimizerAnytimeResponsePlan):
            raise GcsimOptimizerArtifactFirstError("response plan must be typed")
        if not isinstance(self.set_impact, GcsimOptimizerSetImpactPlan):
            raise GcsimOptimizerArtifactFirstError(
                "set-impact plan must be typed"
            )
        if not isinstance(self.race, GcsimOptimizerAnytimeRacePlan):
            raise GcsimOptimizerArtifactFirstError("race plan must be typed")
        for field_name in (
            "max_focus_signatures",
            "response_directions_per_focus",
            "per_wearer_slot_head",
            "slot_matching_beam_width",
            "max_slot_matchings",
            "cross_slot_beam_width",
            "max_complete_assignments",
            "cap_aware_local_neighbors_per_direction",
            "max_exact_finalists",
            "top_n",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise GcsimOptimizerArtifactFirstError(
                    f"{field_name} must be a positive integer"
                )
        if not isfinite(self.overall_deadline_seconds) or self.overall_deadline_seconds <= 0:
            raise GcsimOptimizerArtifactFirstError(
                "overall_deadline_seconds must be finite and positive"
            )
        if self.max_exact_finalists > self.max_complete_assignments:
            raise GcsimOptimizerArtifactFirstError(
                "exact-finalist bound exceeds complete-assignment bound"
            )
        if self.max_exact_finalists > self.race.tiers[0].max_candidates:
            raise GcsimOptimizerArtifactFirstError(
                "exact-finalist bound exceeds the common race screen"
            )
        if self.top_n > min(
            self.max_exact_finalists,
            self.race.tiers[2].max_candidates,
        ):
            raise GcsimOptimizerArtifactFirstError(
                "top_n exceeds exact validation capacity"
            )
        if self.response.total_cpu_budget != self.race.total_cpu_budget:
            raise GcsimOptimizerArtifactFirstError(
                "response and race CPU budgets must match"
            )
        if self.set_impact.worker_count != min(
            self.response.total_cpu_budget,
            self.set_impact.iterations,
        ):
            raise GcsimOptimizerArtifactFirstError(
                "set-impact workers must consume the supported shared CPU budget"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_ID,
            "plan_version": GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_VERSION,
            "claim": "best_found_under_frozen_budget",
            "hard_artifact_pruning": False,
            "response": self.response.to_dict(),
            "set_impact": self.set_impact.to_dict(),
            "race": self.race.to_dict(),
            "max_focus_signatures": self.max_focus_signatures,
            "response_directions_per_focus": self.response_directions_per_focus,
            "per_wearer_slot_head": self.per_wearer_slot_head,
            "slot_matching_beam_width": self.slot_matching_beam_width,
            "max_slot_matchings": self.max_slot_matchings,
            "cross_slot_beam_width": self.cross_slot_beam_width,
            "max_complete_assignments": self.max_complete_assignments,
            "cap_aware_local_neighbors_per_direction": (
                self.cap_aware_local_neighbors_per_direction
            ),
            "max_exact_finalists": self.max_exact_finalists,
            "top_n": self.top_n,
            "overall_deadline_seconds": self.overall_deadline_seconds,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerArtifactFirstSlotMatching:
    artifact_slot: str
    artifact_ids_by_wearer: tuple[int, int, int, int]
    artifact_mask: int
    set_uids_by_wearer: tuple[str, str, str, str]
    score: float
    lane_id: str
    direction_id: str
    rank_vector: tuple[int, int, int, int]

    def __post_init__(self) -> None:
        if self.artifact_slot not in GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
            raise GcsimOptimizerArtifactFirstError("unsupported matching slot")
        if len(set(self.artifact_ids_by_wearer)) != 4:
            raise GcsimOptimizerArtifactFirstError(
                "slot matching must be injective across four wearers"
            )
        if len(self.set_uids_by_wearer) != 4:
            raise GcsimOptimizerArtifactFirstError(
                "slot matching must retain four concrete set identities"
            )
        if not isfinite(self.score):
            raise GcsimOptimizerArtifactFirstError("matching score must be finite")
        if not self.lane_id:
            raise GcsimOptimizerArtifactFirstError("matching lane is required")
        if (
            not self.direction_id
            or len(self.rank_vector) != 4
            or any(rank < 0 for rank in self.rank_vector)
        ):
            raise GcsimOptimizerArtifactFirstError(
                "matching direction/rank vector is invalid"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(
            {
                "slot": self.artifact_slot,
                "artifact_ids_by_wearer": list(self.artifact_ids_by_wearer),
                "lane_id": self.lane_id,
                "direction_id": self.direction_id,
                "rank_vector": list(self.rank_vector),
            }
        )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerArtifactFirstAssignment:
    artifact_ids_by_wearer: tuple[
        tuple[int, int, int, int, int],
        tuple[int, int, int, int, int],
        tuple[int, int, int, int, int],
        tuple[int, int, int, int, int],
    ]
    artifact_mask: int
    set_counts_by_wearer: tuple[tuple[tuple[str, int], ...], ...]
    score: float
    lane_trace: tuple[str, ...]

    def __post_init__(self) -> None:
        flat = tuple(value for row in self.artifact_ids_by_wearer for value in row)
        if len(flat) != 20 or len(set(flat)) != 20:
            raise GcsimOptimizerArtifactFirstError(
                "complete artifact-first assignment must contain 20 distinct IDs"
            )
        if len(self.set_counts_by_wearer) != 4:
            raise GcsimOptimizerArtifactFirstError(
                "complete assignment must retain four set-count rows"
            )
        if not isfinite(self.score):
            raise GcsimOptimizerArtifactFirstError(
                "assignment score must be finite"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(
            {
                "artifact_ids_by_wearer": [
                    list(row) for row in self.artifact_ids_by_wearer
                ],
                "lane_trace": list(self.lane_trace),
            }
        )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerArtifactFirstCoverage:
    focus_signature_count: int
    slot_matching_count: int
    cross_slot_state_count: int
    complete_assignment_count: int
    package_rejection_count: int
    materialization_rejection_count: int
    compiled_proposal_count: int
    incumbent_anchor_count: int = 0
    retained_incumbent_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            name: int(getattr(self, name))
            for name in (
                "focus_signature_count",
                "slot_matching_count",
                "cross_slot_state_count",
                "complete_assignment_count",
                "package_rejection_count",
                "materialization_rejection_count",
                "compiled_proposal_count",
                "incumbent_anchor_count",
                "retained_incumbent_count",
            )
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerArtifactFirstRecallTrace:
    """Bounded physical-ID evidence for every lossy proposal stage."""

    stage_artifact_ids_by_wearer: tuple[
        tuple[str, tuple[tuple[int, tuple[int, ...]], ...]], ...
    ] = ()
    stage_assignments: tuple[
        tuple[str, tuple[tuple[tuple[int, ...], ...], ...]], ...
    ] = ()
    proposal_assignments: tuple[
        tuple[str, tuple[tuple[int, tuple[int, ...]], ...]], ...
    ] = ()
    proposal_diversity_labels: tuple[
        tuple[str, tuple[str, ...]], ...
    ] = ()
    package_rejections: tuple[
        tuple[str, int, tuple[tuple[int, tuple[int, ...]], ...]], ...
    ] = ()

    def artifact_ids(self, stage: str, team_slot: int) -> tuple[int, ...]:
        for stage_id, wearer_rows in self.stage_artifact_ids_by_wearer:
            if stage_id != stage:
                continue
            return next(
                (artifact_ids for slot, artifact_ids in wearer_rows if slot == team_slot),
                (),
            )
        return ()

    def to_dict(self) -> dict[str, object]:
        proposal_labels = dict(self.proposal_diversity_labels)
        return {
            "stage_artifact_ids_by_wearer": [
                {
                    "stage": stage,
                    "wearers": [
                        {
                            "team_slot": team_slot,
                            "artifact_ids": list(artifact_ids),
                        }
                        for team_slot, artifact_ids in wearer_rows
                    ],
                }
                for stage, wearer_rows in self.stage_artifact_ids_by_wearer
            ],
            "stage_assignments": [
                {
                    "stage": stage,
                    "assignments": [
                        [list(artifact_ids) for artifact_ids in wearer_rows]
                        for wearer_rows in assignments
                    ],
                }
                for stage, assignments in self.stage_assignments
            ],
            "proposal_assignments": [
                {
                    "proposal_sha256": proposal_sha256,
                    "diversity_labels": list(
                        proposal_labels.get(proposal_sha256, ())
                    ),
                    "wearers": [
                        {
                            "team_slot": team_slot,
                            "artifact_ids": list(artifact_ids),
                        }
                        for team_slot, artifact_ids in wearer_rows
                    ],
                }
                for proposal_sha256, wearer_rows in self.proposal_assignments
            ],
            "package_rejections": [
                {
                    "reason": reason,
                    "wearer_team_slot": wearer_team_slot,
                    "wearers": [
                        {
                            "team_slot": team_slot,
                            "artifact_ids": list(artifact_ids),
                        }
                        for team_slot, artifact_ids in wearer_rows
                    ],
                }
                for reason, wearer_team_slot, wearer_rows in self.package_rejections
            ],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerArtifactFirstResult:
    terminal: GcsimOptimizerTerminalResult
    run_input_sha256: str
    plan: GcsimOptimizerArtifactFirstPlan
    progress_events: tuple[GcsimOptimizerProgressEvent, ...]
    dense_catalog: GcsimOptimizerDenseArtifactCatalog | None
    inventory_frontier: GcsimOptimizerInventoryFrontierResult | None
    response_result: GcsimOptimizerAnytimeResponseResult | None
    set_impact_result: GcsimOptimizerSetImpactResult | None
    proposals: tuple[GcsimOptimizerJointProposal, ...]
    race_result: GcsimOptimizerAnytimeRaceResult | None
    coverage: GcsimOptimizerArtifactFirstCoverage
    recall_trace: GcsimOptimizerArtifactFirstRecallTrace | None = None
    schema_version: int = GCSIM_OPTIMIZER_ARTIFACT_FIRST_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "terminal": self.terminal.to_dict(),
            "run_input_sha256": self.run_input_sha256,
            "plan_sha256": self.plan.identity_sha256,
            "progress_events": [item.to_dict() for item in self.progress_events],
            "dense_catalog_sha256": (
                None if self.dense_catalog is None else self.dense_catalog.identity_sha256
            ),
            "inventory_frontier_sha256": (
                None
                if self.inventory_frontier is None
                else self.inventory_frontier.identity_sha256
            ),
            "response_evidence_sha256": (
                None if self.response_result is None else self.response_result.evidence_sha256
            ),
            "set_impact_evidence_sha256": (
                None
                if self.set_impact_result is None
                else _canonical_sha256(self.set_impact_result.to_dict())
            ),
            "proposal_sha256s": [item.proposal_sha256 for item in self.proposals],
            "race_evidence_sha256": (
                None if self.race_result is None else self.race_result.evidence_sha256
            ),
            "coverage": self.coverage.to_dict(),
            "recall_trace": (
                None if self.recall_trace is None else self.recall_trace.to_dict()
            ),
        }


@dataclass(frozen=True, slots=True)
class _FocusLane:
    lane_id: str
    focus_set_uids: tuple[str | None, str | None, str | None, str | None]
    offpiece_slot_by_wearer: tuple[str | None, str | None, str | None, str | None]
    direction_id: str


@dataclass(frozen=True, slots=True)
class _PartialMatching:
    artifacts: tuple[GcsimOptimizerDenseArtifact, ...]
    mask: int
    score: float
    selection_score: float
    rank_vector: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _CrossSlotState:
    ids_by_wearer: tuple[tuple[int, ...], ...]
    mask: int
    set_counts_by_wearer: tuple[tuple[tuple[str, int], ...], ...]
    score: float
    lane_trace: tuple[str, ...]


class _ArtifactFirstRecallTraceBuilder:
    def __init__(self) -> None:
        self._stage_ids: dict[str, dict[int, set[int]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self._stage_assignments: dict[
            str,
            set[tuple[tuple[int, ...], ...]],
        ] = defaultdict(set)
        self._proposal_assignments: list[
            tuple[str, tuple[tuple[int, tuple[int, ...]], ...]]
        ] = []
        self._proposal_diversity_labels: list[
            tuple[str, tuple[str, ...]]
        ] = []
        self._package_rejections: list[
            tuple[str, int, tuple[tuple[int, tuple[int, ...]], ...]]
        ] = []

    def add_ids(
        self,
        stage: str,
        team_slot: int,
        artifact_ids: Sequence[int],
    ) -> None:
        self._stage_ids[str(stage)][int(team_slot)].update(
            int(value) for value in artifact_ids
        )

    def add_assignment(self, stage: str, assignment) -> None:
        assignment_rows = tuple(
            tuple(int(value) for value in artifact_ids)
            for artifact_ids in assignment.artifact_ids_by_wearer
        )
        self._stage_assignments[str(stage)].add(assignment_rows)
        for wearer_index, artifact_ids in enumerate(
            assignment_rows
        ):
            self.add_ids(stage, wearer_index + 1, artifact_ids)

    def add_slot_matching(
        self,
        stage: str,
        matching: GcsimOptimizerArtifactFirstSlotMatching,
    ) -> None:
        assignment_rows = tuple(
            (int(artifact_id),)
            for artifact_id in matching.artifact_ids_by_wearer
        )
        self._stage_assignments[str(stage)].add(assignment_rows)
        for wearer_index, artifact_ids in enumerate(assignment_rows):
            self.add_ids(stage, wearer_index + 1, artifact_ids)

    def add_cross_states(self, stage: str, states) -> None:
        for state in states:
            assignment_rows = tuple(
                tuple(int(value) for value in artifact_ids)
                for artifact_ids in state.ids_by_wearer
            )
            self._stage_assignments[str(stage)].add(assignment_rows)
            for wearer_index, artifact_ids in enumerate(assignment_rows):
                self.add_ids(stage, wearer_index + 1, artifact_ids)

    def add_package_rejection(
        self,
        assignment,
        *,
        reason: str,
        wearer_team_slot: int,
    ) -> None:
        self._package_rejections.append(
            (
                str(reason),
                int(wearer_team_slot),
                _assignment_trace_rows(assignment.artifact_ids_by_wearer),
            )
        )

    def set_proposals(self, proposals) -> None:
        self._proposal_assignments = []
        self._proposal_diversity_labels = []
        for proposal in proposals:
            witness = proposal.compiled_candidate.assignment_witness
            wearer_rows = tuple(
                (
                    assignment.wearer.team_slot,
                    tuple(
                        int(assignment.artifact_ids_by_slot[slot])
                        for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
                    ),
                )
                for assignment in witness.wearer_assignments
            )
            self._proposal_assignments.append(
                (proposal.proposal_sha256, wearer_rows)
            )
            self._proposal_diversity_labels.append(
                (
                    proposal.proposal_sha256,
                    tuple(str(value) for value in proposal.diversity_labels),
                )
            )
            for team_slot, artifact_ids in wearer_rows:
                self.add_ids("proposal", team_slot, artifact_ids)

    def snapshot(self) -> GcsimOptimizerArtifactFirstRecallTrace:
        return GcsimOptimizerArtifactFirstRecallTrace(
            stage_artifact_ids_by_wearer=tuple(
                (
                    stage,
                    tuple(
                        (team_slot, tuple(sorted(artifact_ids)))
                        for team_slot, artifact_ids in sorted(wearers.items())
                    ),
                )
                for stage, wearers in sorted(self._stage_ids.items())
            ),
            stage_assignments=tuple(
                (stage, tuple(sorted(assignments)))
                for stage, assignments in sorted(self._stage_assignments.items())
            ),
            proposal_assignments=tuple(self._proposal_assignments),
            proposal_diversity_labels=tuple(
                self._proposal_diversity_labels
            ),
            package_rejections=tuple(self._package_rejections),
        )


def _assignment_trace_rows(artifact_ids_by_wearer):
    return tuple(
        (wearer_index + 1, tuple(int(value) for value in artifact_ids))
        for wearer_index, artifact_ids in enumerate(artifact_ids_by_wearer)
    )


ProgressCallback = Callable[[GcsimOptimizerProgressEvent], None]


class GcsimOptimizerArtifactFirstSession:
    """One-shot experimental session with no baseline fallback."""

    def __init__(
        self,
        run_input: GcsimOptimizerRunInput,
        *,
        engine_context: GcsimOptimizerEngineContext,
        prepared_config_text: str,
        plan: GcsimOptimizerArtifactFirstPlan | None = None,
        progress_callback: ProgressCallback | None = None,
        cache_store: GcsimOptimizerCacheStore | None = None,
        enable_cache: bool = True,
        session_factory: Callable[[object], object] | None = None,
        response_discovery: Callable[..., object] | None = None,
        set_impact_discovery: Callable[..., object] | None = None,
        stat_response_target: GcsimStatResponseTarget | None = None,
        response_master_seed: int | None = None,
        required_artifact_assignments: Sequence[Sequence[Sequence[int]]] = (),
        environment: Mapping[str, str] | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isinstance(run_input, GcsimOptimizerRunInput):
            raise GcsimOptimizerArtifactFirstError("run_input must be typed")
        if not isinstance(engine_context, GcsimOptimizerEngineContext):
            raise GcsimOptimizerArtifactFirstError("engine_context must be typed")
        self.run_input = run_input
        self.engine_context = engine_context
        self.prepared_config_text = prepared_config_text
        self.plan = plan or GcsimOptimizerArtifactFirstPlan()
        self.progress_callback = progress_callback
        self.cache_store = cache_store
        self.enable_cache = bool(enable_cache)
        self.session_factory = session_factory
        self.response_discovery = (
            response_discovery or discover_gcsim_optimizer_anytime_response
        )
        self._uses_default_set_impact_discovery = set_impact_discovery is None
        self.set_impact_discovery = (
            set_impact_discovery or discover_gcsim_optimizer_set_impacts
        )
        self.stat_response_target = stat_response_target
        self.response_master_seed = response_master_seed
        self.required_artifact_assignments = _normalize_required_artifact_assignments(
            required_artifact_assignments
        )
        self.environment = dict(environment or {})
        self.clock = clock
        self._cancel_event = Event()
        self._lock = Lock()
        self._active: object | None = None
        self._started = False
        self._progress: list[GcsimOptimizerProgressEvent] = []
        self._timing: dict[str, float] = {}
        self._recall_trace: GcsimOptimizerArtifactFirstRecallTrace | None = None
        self._set_impact_result: GcsimOptimizerSetImpactResult | None = None

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            active = self._active
        if active is not None and hasattr(active, "cancel"):
            active.cancel()

    def run(self) -> GcsimOptimizerArtifactFirstResult:
        with self._lock:
            if self._started:
                raise GcsimOptimizerArtifactFirstError(
                    "artifact-first sessions are one-shot"
                )
            self._started = True
        started = self.clock()
        stage = started
        deadline = started + self.plan.overall_deadline_seconds
        catalog = None
        frontier = None
        response = None
        set_impact = None
        proposals: tuple[GcsimOptimizerJointProposal, ...] = ()
        race = None
        coverage = GcsimOptimizerArtifactFirstCoverage(0, 0, 0, 0, 0, 0, 0)
        trace_builder = _ArtifactFirstRecallTraceBuilder()
        try:
            not_ready = self._preflight(started)
            if not_ready is not None:
                return self._result(
                    not_ready, catalog, frontier, response, proposals, race, coverage
                )
            self._emit(GcsimOptimizerProgressStage.PREFLIGHT, started, deadline, 1, 1)
            self._raise_if_interrupted(deadline)

            stage = self.clock()
            catalog = build_gcsim_optimizer_dense_artifact_catalog(self.run_input)
            frontier = build_gcsim_optimizer_inventory_frontier(
                self.run_input,
                catalog=catalog,
            )
            self._timing["layout_scan"] = max(self.clock() - stage, 0.0)
            self._emit(
                GcsimOptimizerProgressStage.LAYOUT_SCAN,
                started,
                deadline,
                len(frontier.retained_rows),
                len(catalog.artifacts),
            )
            self._raise_if_interrupted(deadline)

            stage = self.clock()
            representative_targets = _representative_targets(self.run_input)
            response_plan = replace(
                self.plan.response,
                overall_deadline_seconds=min(
                    self.plan.response.overall_deadline_seconds,
                    max(deadline - self.clock(), 0.001),
                ),
            )
            response = self.response_discovery(
                self.run_input,
                engine_context=self.engine_context,
                prepared_config_text=self.prepared_config_text,
                representative_targets=representative_targets,
                plan=response_plan,
                progress_callback=lambda completed, planned, hits: self._emit(
                    GcsimOptimizerProgressStage.RESPONSE_SCAN,
                    started,
                    deadline,
                    completed,
                    planned,
                    cache_hits=hits,
                ),
                environment=self.environment,
                stat_response_target=self.stat_response_target,
                neutral_package_response=(
                    self.run_input.request.account_scope
                    is GcsimOptimizerAccountScope.ALL_DATABASE_SETS
                ),
                master_seed=self.response_master_seed,
                is_cancelled=self._cancel_event.is_set,
                clock=self.clock,
            )
            self._timing["response_scan"] = max(self.clock() - stage, 0.0)
            self._raise_if_interrupted(deadline)

            stage = self.clock()
            set_impact_plan = replace(
                self.plan.set_impact,
                overall_deadline_seconds=min(
                    self.plan.set_impact.overall_deadline_seconds,
                    max(deadline - self.clock(), 0.001),
                ),
            )
            set_impact = self.set_impact_discovery(
                engine_context=self.engine_context,
                prepared_config_text=self.prepared_config_text,
                targets=_set_impact_targets(self.run_input),
                response=response,
                stat_response_target=self.stat_response_target,
                plan=set_impact_plan,
                progress_callback=lambda completed, planned: self._emit(
                    GcsimOptimizerProgressStage.SET_IMPACT_SCAN,
                    started,
                    deadline,
                    completed,
                    planned,
                ),
                environment=self.environment,
                is_cancelled=self._cancel_event.is_set,
                clock=self.clock,
            )
            if not isinstance(set_impact, GcsimOptimizerSetImpactResult):
                raise GcsimOptimizerArtifactFirstError(
                    "set-impact discovery returned an invalid result"
                )
            if set_impact.response_evidence_sha256 != response.evidence_sha256:
                raise GcsimOptimizerArtifactFirstError(
                    "set-impact result differs from response evidence"
                )
            self._set_impact_result = set_impact
            self._timing["set_impact_scan"] = max(self.clock() - stage, 0.0)
            self._raise_if_interrupted(deadline)

            stage = self.clock()
            proposals, coverage = generate_gcsim_optimizer_artifact_first_proposals(
                self.run_input,
                catalog=catalog,
                frontier=frontier,
                response=response,
                set_impact=set_impact,
                plan=self.plan,
                is_cancelled=self._cancel_event.is_set,
                deadline=deadline,
                clock=self.clock,
                trace_collector=trace_builder,
                required_artifact_assignments=(
                    self.required_artifact_assignments
                ),
            )
            self._recall_trace = trace_builder.snapshot()
            self._timing["artifact_first_search"] = max(self.clock() - stage, 0.0)
            self._emit(
                GcsimOptimizerProgressStage.JOINT_SEARCH,
                started,
                deadline,
                len(proposals),
                self.plan.max_exact_finalists,
            )
            self._raise_if_interrupted(deadline)
            if not proposals:
                terminal = self._terminal(
                    GcsimOptimizerTerminalStatus.NO_SUCCESS,
                    "artifact_first_no_legal_complete_assignment",
                    started,
                    catalog=catalog,
                    frontier=frontier,
                    response=response,
                    coverage=coverage,
                )
                return self._result(
                    terminal, catalog, frontier, response, proposals, race, coverage
                )

            race_plan = replace(
                self.plan.race,
                overall_deadline_seconds=min(
                    self.plan.race.overall_deadline_seconds,
                    max(deadline - self.clock(), 0.001),
                ),
            )
            race_session = GcsimOptimizerAnytimeRaceSession(
                self.run_input,
                engine_context=self.engine_context,
                proposals=proposals,
                plan=race_plan,
                progress_callback=lambda tier, completed, planned, leader: self._emit(
                    _race_progress_stage(tier),
                    started,
                    deadline,
                    completed,
                    planned,
                    current_iterations=_race_iterations(tier),
                    leader=leader,
                ),
                cache_store=self.cache_store,
                enable_cache=self.enable_cache,
                session_factory=self.session_factory,
                environment=self.environment,
                stat_response_target=self.stat_response_target,
                clock=self.clock,
            )
            with self._lock:
                self._active = race_session
            if self._cancel_event.is_set():
                race_session.cancel()
            try:
                race = race_session.run()
            finally:
                with self._lock:
                    if self._active is race_session:
                        self._active = None
            terminal = self._terminal_from_race(
                race,
                started=started,
                catalog=catalog,
                frontier=frontier,
                response=response,
                coverage=coverage,
            )
            self._emit(
                GcsimOptimizerProgressStage.COMPLETED,
                started,
                deadline,
                1,
                1,
            )
            return self._result(
                terminal, catalog, frontier, response, proposals, race, coverage
            )
        except _ArtifactFirstInterrupted as exc:
            self._recall_trace = trace_builder.snapshot()
            self._timing.setdefault(
                "artifact_first_search",
                max(self.clock() - stage, 0.0),
            )
            terminal = self._terminal(
                (
                    GcsimOptimizerTerminalStatus.CANCELLED
                    if exc.cancelled
                    else GcsimOptimizerTerminalStatus.DEADLINE
                ),
                str(exc),
                started,
                catalog=catalog,
                frontier=frontier,
                response=response,
                race=race,
                coverage=coverage,
            )
            return self._result(
                terminal, catalog, frontier, response, proposals, race, coverage
            )
        except Exception as exc:  # noqa: BLE001 - product boundary is fail-closed.
            self._recall_trace = trace_builder.snapshot()
            terminal = self._terminal(
                GcsimOptimizerTerminalStatus.FAILED,
                "artifact_first_unexpected_failure",
                started,
                catalog=catalog,
                frontier=frontier,
                response=response,
                race=race,
                coverage=coverage,
                error=f"{type(exc).__name__}: {exc}",
            )
            return self._result(
                terminal, catalog, frontier, response, proposals, race, coverage
            )

    def _preflight(self, started: float) -> GcsimOptimizerTerminalResult | None:
        self._emit(GcsimOptimizerProgressStage.PREFLIGHT, started, started + self.plan.overall_deadline_seconds, 0, 1)
        request = self.run_input.request
        if (
            request.operation is not GcsimOptimizerOperation.ACCOUNT_ARTIFACTS
            or request.account_scope
            not in {
                GcsimOptimizerAccountScope.SELECTED_SET_POOLS,
                GcsimOptimizerAccountScope.ALL_DATABASE_SETS,
            }
        ):
            return self._terminal(
                GcsimOptimizerTerminalStatus.NOT_READY,
                "artifact_first_account_scope_required",
                started,
            )
        work_plan = request.work_plan
        if (
            work_plan.plan_id != GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_ID
            or work_plan.plan_version != GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_VERSION
            or _canonical_sha256(_thaw_identity_value(work_plan.parameters))
            != _canonical_sha256(self.plan.to_dict())
        ):
            return self._terminal(
                GcsimOptimizerTerminalStatus.NOT_READY,
                "artifact_first_work_plan_mismatch",
                started,
            )
        if self.stat_response_target is None:
            return self._terminal(
                GcsimOptimizerTerminalStatus.NOT_READY,
                "artifact_first_explicit_target_required",
                started,
            )
        if (
            self._uses_default_set_impact_discovery
            and GCSIM_SET_RESPONSE_CAPABILITY
            not in set(self.engine_context.capabilities)
        ):
            return self._terminal(
                GcsimOptimizerTerminalStatus.NOT_READY,
                "artifact_first_set_response_capability_required",
                started,
            )
        return None

    def _terminal_from_race(
        self,
        race: GcsimOptimizerAnytimeRaceResult,
        *,
        started: float,
        catalog,
        frontier,
        response,
        coverage,
    ) -> GcsimOptimizerTerminalResult:
        best_by_signature: dict[tuple[str, ...], GcsimOptimizerAnytimeRaceEvaluation] = {}
        for evaluation in race.confirmed_evaluations:
            signature = build_gcsim_optimizer_account_package_signature(
                evaluation.proposal.compiled_candidate.targets
            )
            current = best_by_signature.get(signature)
            if current is None or _evaluation_rank(evaluation) < _evaluation_rank(current):
                best_by_signature[signature] = evaluation
        candidates = tuple(
            self._candidate_result(
                item,
                response=response,
                frontier=frontier,
            )
            for item in sorted(best_by_signature.values(), key=_evaluation_rank)
        )
        top_n = build_gcsim_optimizer_top_n(
            candidates,
            operation=GcsimOptimizerOperation.ACCOUNT_ARTIFACTS,
            top_n=self.plan.top_n,
            confidence_sigma=self.plan.race.confidence_sigma,
        )
        status = {
            GcsimOptimizerAnytimeRaceStatus.COMPLETED: GcsimOptimizerTerminalStatus.BEST_FOUND,
            GcsimOptimizerAnytimeRaceStatus.COMPLETED_WITH_ERRORS: GcsimOptimizerTerminalStatus.BEST_FOUND,
            GcsimOptimizerAnytimeRaceStatus.NO_SUCCESS: GcsimOptimizerTerminalStatus.NO_SUCCESS,
            GcsimOptimizerAnytimeRaceStatus.CANCELLED: GcsimOptimizerTerminalStatus.CANCELLED,
            GcsimOptimizerAnytimeRaceStatus.DEADLINE: GcsimOptimizerTerminalStatus.DEADLINE,
        }[race.status]
        if status is GcsimOptimizerTerminalStatus.BEST_FOUND and not top_n.entries:
            status = GcsimOptimizerTerminalStatus.NO_SUCCESS
        if status is GcsimOptimizerTerminalStatus.NO_SUCCESS and top_n.entries:
            status = GcsimOptimizerTerminalStatus.BEST_FOUND
        return self._terminal(
            status,
            f"artifact_first_race_{race.status.value}",
            started,
            top_n=top_n,
            catalog=catalog,
            frontier=frontier,
            response=response,
            race=race,
            coverage=coverage,
        )

    def _candidate_result(self, evaluation, *, response, frontier):
        compiled = evaluation.proposal.compiled_candidate
        assert evaluation.dps_mean is not None
        return GcsimOptimizerCandidateResult(
            request_sha256=self.run_input.request.request_sha256,
            candidate_identity_sha256=compiled.candidate_identity_sha256,
            evaluation=GcsimOptimizerEvaluationIdentity(
                request_sha256=self.run_input.request.request_sha256,
                source_simulation_sha256=(
                    self.run_input.request.source_simulation.identity_sha256
                ),
                work_plan_sha256=self.run_input.request.work_plan.identity_sha256,
                engine_binding_sha256=self.engine_context.binding_sha256,
                compiled_config_sha256=evaluation.result.source_config_sha256,
                execution_identity_sha256=evaluation.result.request_identity_sha256,
            ),
            estimate=GcsimOptimizerDpsEstimate(
                evaluation.dps_mean,
                evaluation.dps_se,
                evaluation.iterations,
            ),
            target_packages=compiled.targets,
            evidence_sha256={
                "artifact_first_frontier": frontier.identity_sha256,
                "rotation_response": response.evidence_sha256,
                **(
                    {}
                    if self._set_impact_result is None
                    else {
                        "set_impact": _canonical_sha256(
                            self._set_impact_result.to_dict()
                        )
                    }
                ),
                "race_evaluation": evaluation.evidence_sha256,
                "runner_cache_identity": evaluation.result.cache_key,
            },
            account_assignment=compiled.assignment_witness,
        )

    def _terminal(
        self,
        status,
        stop_reason,
        started,
        *,
        top_n=None,
        catalog=None,
        frontier=None,
        response=None,
        race=None,
        coverage=None,
        error="",
    ):
        coverage = coverage or GcsimOptimizerArtifactFirstCoverage(0, 0, 0, 0, 0, 0, 0)
        race_hits = 0 if race is None else sum(value for _tier, value in race.cache_hits_by_tier)
        race_requested = 0 if race is None else sum(value for _tier, value in race.requested_by_tier)
        response_hits = 0 if response is None else response.cache_hit_count
        response_requested = 0 if response is None else response.planned_probe_count
        set_impact_requested = (
            0
            if self._set_impact_result is None
            else len(self._set_impact_result.runtime_observations)
            + len(self._set_impact_result.interaction_observations)
        )
        return GcsimOptimizerTerminalResult(
            request=self.run_input.request,
            status=status,
            stop_reason=stop_reason,
            elapsed_seconds=max(self.clock() - started, 0.0),
            top_n=top_n,
            evidence_sha256={
                "run_input": self.run_input.run_input_sha256,
                "service_plan": self.plan.identity_sha256,
                **({} if catalog is None else {"dense_catalog": catalog.identity_sha256}),
                **({} if frontier is None else {"inventory_frontier": frontier.identity_sha256}),
                **({} if response is None else {"rotation_response": response.evidence_sha256}),
                **(
                    {}
                    if self._set_impact_result is None
                    else {
                        "set_impact": _canonical_sha256(
                            self._set_impact_result.to_dict()
                        )
                    }
                ),
                **({} if race is None else {"race": race.evidence_sha256}),
            },
            coverage=GcsimOptimizerCoverageCounters(coverage.to_dict()),
            cache=GcsimOptimizerCacheCounters(
                hits=response_hits + race_hits,
                misses=max(
                    response_requested
                    + set_impact_requested
                    + race_requested
                    - response_hits
                    - race_hits,
                    0,
                ),
            ),
            timing=GcsimOptimizerTimingCounters(self._timing),
            error=error,
        )

    def _result(self, terminal, catalog, frontier, response, proposals, race, coverage):
        return GcsimOptimizerArtifactFirstResult(
            terminal=terminal,
            run_input_sha256=self.run_input.run_input_sha256,
            plan=self.plan,
            progress_events=tuple(self._progress),
            dense_catalog=catalog,
            inventory_frontier=frontier,
            response_result=response,
            set_impact_result=self._set_impact_result,
            proposals=tuple(proposals),
            race_result=race,
            coverage=coverage,
            recall_trace=self._recall_trace,
        )

    def _emit(
        self,
        stage,
        started,
        deadline,
        completed,
        planned,
        *,
        cache_hits=0,
        current_iterations=None,
        leader=None,
    ) -> None:
        leader_snapshot = None
        if leader is not None and leader.dps_mean is not None:
            from .optimizer_product_contracts import (
                GcsimOptimizerLeaderSnapshot,
                GcsimOptimizerProgressLeaderQuality,
                GcsimOptimizerProgressLeaderScope,
            )

            leader_snapshot = GcsimOptimizerLeaderSnapshot(
                candidate_identity_sha256=(
                    leader.proposal.compiled_candidate.candidate_identity_sha256
                ),
                estimate=GcsimOptimizerDpsEstimate(
                    leader.dps_mean,
                    leader.dps_se,
                    leader.iterations,
                ),
                scope=GcsimOptimizerProgressLeaderScope.STAGE,
                quality=(
                    GcsimOptimizerProgressLeaderQuality.VERIFIED
                    if leader.iterations >= 200
                    else GcsimOptimizerProgressLeaderQuality.PROVISIONAL
                ),
            )
        event = GcsimOptimizerProgressEvent(
            request_sha256=self.run_input.request.request_sha256,
            operation=self.run_input.request.operation,
            work_plan_sha256=self.run_input.request.work_plan.identity_sha256,
            stage=stage,
            sequence=len(self._progress),
            completed_work=max(0, int(completed)),
            planned_work=(None if planned is None else max(int(completed), int(planned))),
            elapsed_seconds=max(self.clock() - started, 0.0),
            remaining_seconds=max(deadline - self.clock(), 0.0),
            cache_hits=max(0, int(cache_hits)),
            current_iterations=current_iterations,
            current_best=leader_snapshot,
        )
        self._progress.append(event)
        if self.progress_callback is not None:
            self.progress_callback(event)

    def _raise_if_interrupted(self, deadline: float) -> None:
        if self._cancel_event.is_set():
            raise _ArtifactFirstInterrupted("artifact_first_cancelled", cancelled=True)
        if self.clock() >= deadline:
            raise _ArtifactFirstInterrupted("artifact_first_deadline", cancelled=False)


def generate_gcsim_optimizer_artifact_first_proposals(
    run_input: GcsimOptimizerRunInput,
    *,
    catalog: GcsimOptimizerDenseArtifactCatalog,
    frontier: GcsimOptimizerInventoryFrontierResult,
    response: GcsimOptimizerAnytimeResponseResult,
    set_impact: GcsimOptimizerSetImpactResult | None = None,
    plan: GcsimOptimizerArtifactFirstPlan,
    is_cancelled: Callable[[], bool] | None = None,
    deadline: float | None = None,
    clock: Callable[[], float] = monotonic,
    trace_collector: _ArtifactFirstRecallTraceBuilder | None = None,
    required_artifact_assignments: Sequence[Sequence[Sequence[int]]] = (),
) -> tuple[tuple[GcsimOptimizerJointProposal, ...], GcsimOptimizerArtifactFirstCoverage]:
    """Build bounded exact finalists without removing any eligible frontier row."""

    if frontier.run_input_sha256 != run_input.run_input_sha256:
        raise GcsimOptimizerArtifactFirstError("frontier belongs to another run input")
    if frontier.dense_catalog_sha256 != catalog.identity_sha256:
        raise GcsimOptimizerArtifactFirstError("frontier/catalog identities differ")
    if is_cancelled is None:
        is_cancelled = lambda: False
    rows = tuple(frontier.retained_rows)
    artifact_by_id = {item.artifact_id: item.artifact for item in rows}
    profiles_by_wearer = {
        wearer: response.profiles_for(wearer)
        for wearer in run_input.request.source_simulation.wearers
    }
    lanes = _build_focus_lanes(run_input, profiles_by_wearer, plan)
    incumbent_anchors = _build_required_artifact_first_assignments(
        required_artifact_assignments,
        artifact_by_id=artifact_by_id,
        profiles_by_wearer=profiles_by_wearer,
    )
    if trace_collector is not None:
        for assignment in incumbent_anchors:
            trace_collector.add_assignment("incumbent_anchor/input", assignment)
    slot_matchings: dict[str, tuple[GcsimOptimizerArtifactFirstSlotMatching, ...]] = {}
    matching_by_lane_slot: dict[tuple[str, str], GcsimOptimizerArtifactFirstSlotMatching] = {}
    for artifact_slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
        available = tuple(item for item in rows if item.artifact.slot == artifact_slot)
        matchings: list[GcsimOptimizerArtifactFirstSlotMatching] = []
        for lane in lanes:
            _raise_generation_interrupted(is_cancelled, deadline, clock)
            lane_matchings = _best_slot_matchings(
                artifact_slot,
                available,
                lane=lane,
                profiles_by_wearer=profiles_by_wearer,
                plan=plan,
                trace_collector=trace_collector,
            )
            if not lane_matchings:
                continue
            matchings.extend(lane_matchings)
            matching_by_lane_slot[(lane.lane_id, artifact_slot)] = (
                lane_matchings[0]
            )
        slot_matchings[artifact_slot] = _retain_slot_matchings(
            matchings,
            limit=plan.max_slot_matchings,
        )
        if trace_collector is not None:
            for matching in slot_matchings[artifact_slot]:
                trace_collector.add_slot_matching(
                    f"slot_matching/{artifact_slot}",
                    matching,
                )

    direct: list[GcsimOptimizerArtifactFirstAssignment] = []
    for lane in lanes:
        lane_rows = tuple(
            matching_by_lane_slot.get((lane.lane_id, slot))
            for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
        )
        if any(item is None for item in lane_rows):
            continue
        state = _join_matching_sequence(tuple(item for item in lane_rows if item is not None))
        if state is not None:
            direct.append(_complete_assignment(state))

    states = (
        _CrossSlotState(
            ids_by_wearer=((), (), (), ()),
            mask=0,
            set_counts_by_wearer=((), (), (), ()),
            score=0.0,
            lane_trace=(),
        ),
    )
    expanded_state_count = 0
    for artifact_slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
        next_states: list[_CrossSlotState] = []
        for state in states:
            for matching in slot_matchings[artifact_slot]:
                _raise_generation_interrupted(is_cancelled, deadline, clock)
                if state.mask & matching.artifact_mask:
                    continue
                next_states.append(_join_state(state, matching))
        expanded_state_count += len(next_states)
        states = _retain_cross_slot_states(
            _rescore_cross_slot_states(
                next_states,
                artifact_by_id=artifact_by_id,
                response=response,
            ),
            limit=plan.cross_slot_beam_width,
        )
        if trace_collector is not None:
            trace_collector.add_cross_states(
                f"cross_slot/{artifact_slot}",
                states,
            )
        if not states:
            break
    beam_complete = [
        _complete_assignment(state)
        for state in states
        if all(len(row) == len(GCSIM_OPTIMIZER_ARTIFACT_SLOTS) for row in state.ids_by_wearer)
    ]
    cap_aware_local = _build_cap_aware_package_local_assignments(
        incumbent_anchors + tuple(direct),
        slot_matchings=slot_matchings,
        artifact_by_id=artifact_by_id,
        profiles_by_wearer=profiles_by_wearer,
        neighbors_per_direction=plan.cap_aware_local_neighbors_per_direction,
    )
    if trace_collector is not None:
        for assignment in cap_aware_local:
            trace_collector.add_assignment(
                "cap_aware_local/generation",
                assignment,
            )
    complete_candidates = _rescore_complete_assignments(
        list(incumbent_anchors) + direct + list(cap_aware_local) + beam_complete,
        artifact_by_id=artifact_by_id,
        response=response,
    )
    complete = _retain_complete_assignments(
        complete_candidates,
        limit=plan.max_complete_assignments,
        required=incumbent_anchors + tuple(direct),
        coverage_required=cap_aware_local,
    )
    if trace_collector is not None:
        for assignment in complete:
            trace_collector.add_assignment("complete_assignment", assignment)
            if _assignment_origin_labels(assignment):
                trace_collector.add_assignment(
                    "cap_aware_local/retained",
                    assignment,
                )
            if "exact_incumbent_anchor" in assignment.lane_trace:
                trace_collector.add_assignment(
                    "incumbent_anchor/retained",
                    assignment,
                )

    set_refs_by_wearer = _set_refs_by_wearer(run_input)
    override_by_wearer = {
        item.wearer: item for item in run_input.request.four_star_overrides
    }
    proposals: list[GcsimOptimizerJointProposal] = []
    package_rejections = 0
    materialization_rejections = 0
    seen_configs: set[str] = set()
    for assignment in complete:
        _raise_generation_interrupted(is_cancelled, deadline, clock)
        assignment_origin_labels = _assignment_origin_labels(assignment)
        wearer_candidates: list[GcsimOptimizerLazyWearerCandidate] = []
        targets: list[GcsimOptimizerWearerTarget] = []
        wearer_assignments: list[GcsimOptimizerWearerArtifactAssignment] = []
        failed = False
        for wearer_index, wearer in enumerate(
            run_input.request.source_simulation.wearers
        ):
            artifact_ids = assignment.artifact_ids_by_wearer[wearer_index]
            physical = tuple(artifact_by_id[value].record for value in artifact_ids)
            derived = derive_gcsim_optimizer_target_from_physical_artifacts(
                wearer=wearer,
                artifacts=physical,
                set_refs=set_refs_by_wearer[wearer],
                set_capabilities=run_input.set_capabilities,
                include_2p2p=run_input.request.include_2p2p,
                four_star_override=override_by_wearer.get(wearer),
            )
            if not derived.ready or derived.target is None:
                package_rejections += 1
                if trace_collector is not None:
                    trace_collector.add_package_rejection(
                        assignment,
                        reason="target_derivation",
                        wearer_team_slot=wearer.team_slot,
                    )
                failed = True
                break
            target = derived.target
            wearer_set_score = _set_impact_target_score(
                target,
                set_impact,
            )
            offpiece_shape = _offpiece_shape(physical, target)
            if isinstance(target.package, GcsimFourPieceTargetPackage):
                capability = run_input.set_capability(
                    target.package.set_ref.gcsim_set_key
                )
                if (
                    capability is not None
                    and capability.max_rarity == 4
                    and offpiece_shape not in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
                ):
                    package_rejections += 1
                    if trace_collector is not None:
                        trace_collector.add_package_rejection(
                            assignment,
                            reason="four_star_offpiece_shape",
                            wearer_team_slot=wearer.team_slot,
                        )
                    failed = True
                    break
            wearer_assignment = GcsimOptimizerWearerArtifactAssignment(
                wearer=wearer,
                artifact_ids_by_slot=dict(
                    zip(GCSIM_OPTIMIZER_ARTIFACT_SLOTS, artifact_ids, strict=True)
                ),
            )
            materialized = materialize_gcsim_optimizer_wearer_build(
                run_input,
                assignment=wearer_assignment,
                target=target,
            )
            if not materialized.ready or materialized.build is None:
                materialization_rejections += 1
                if trace_collector is not None:
                    trace_collector.add_package_rejection(
                        assignment,
                        reason="wearer_materialization",
                        wearer_team_slot=wearer.team_slot,
                    )
                failed = True
                break
            artifact_rows = tuple(artifact_by_id[value] for value in artifact_ids)
            candidate_payload = {
                "plan_id": GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_ID,
                "run_input_sha256": run_input.run_input_sha256,
                "wearer": wearer.to_dict(),
                "target": target.to_dict(),
                "artifact_ids": list(artifact_ids),
                "lane_trace": list(assignment.lane_trace),
            }
            wearer_candidates.append(
                GcsimOptimizerLazyWearerCandidate(
                    target=target,
                    response_model_sha256=_canonical_sha256(
                        {
                            "response": response.evidence_sha256,
                            "set_impact": (
                                None
                                if set_impact is None
                                else _canonical_sha256(set_impact.to_dict())
                            ),
                            "wearer": wearer.identity_sha256,
                            "lanes": list(assignment.lane_trace),
                        }
                    ),
                    assignment=wearer_assignment,
                    materialized_build=materialized.build,
                    proposal_score=_decimal_text(
                        assignment.score / 4.0 + wearer_set_score
                    ),
                    crit_value=_decimal_text(
                        sum(
                            2.0 * row.stats[GCSIM_OPTIMIZER_ANYTIME_STAT_AXES.index("cr")]
                            + row.stats[GCSIM_OPTIMIZER_ANYTIME_STAT_AXES.index("cd")]
                            for row in artifact_rows
                        )
                    ),
                    offpiece_shape=offpiece_shape,
                    feature_labels=(
                        "artifact_first",
                        "injective_slot_matching",
                        "package_after_assignment",
                        *(
                            (
                                "typed_set_semantics",
                                "paired_set_runtime_observation",
                            )
                            if set_impact is not None
                            else ()
                        ),
                        *assignment_origin_labels,
                    ),
                    content_fingerprint=_canonical_sha256(
                        [row.content_fingerprint for row in artifact_rows]
                    ),
                    candidate_sha256=_canonical_sha256(candidate_payload),
                )
            )
            targets.append(target)
            wearer_assignments.append(wearer_assignment)
        if failed:
            continue
        witness = GcsimOptimizerAccountAssignmentWitness(
            request_sha256=run_input.request.request_sha256,
            artifact_database_input_sha256=(
                run_input.artifact_database.artifact_database_input_sha256
            ),
            wearer_assignments=tuple(wearer_assignments),
        )
        compiled_result = compile_gcsim_optimizer_team_candidate(
            run_input,
            assignment_witness=witness,
            targets=tuple(targets),
            execution_identity_sha256=_canonical_sha256(
                {
                    "plan_id": GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_ID,
                    "plan_version": GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_VERSION,
                    "run_input_sha256": run_input.run_input_sha256,
                    "assignment_sha256": witness.identity_sha256,
                }
            ),
        )
        if not compiled_result.ready or compiled_result.candidate is None:
            materialization_rejections += 1
            if trace_collector is not None:
                trace_collector.add_package_rejection(
                    assignment,
                    reason="team_compilation",
                    wearer_team_slot=0,
                )
            continue
        compiled = compiled_result.candidate
        if trace_collector is not None:
            trace_collector.add_assignment("package_derivation", assignment)
        if compiled.compiled_config_sha256 in seen_configs:
            continue
        seen_configs.add(compiled.compiled_config_sha256)
        proposal_payload = {
            "plan_id": GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_ID,
            "run_input_sha256": run_input.run_input_sha256,
            "assignment_sha256": witness.identity_sha256,
            "compiled_config_sha256": compiled.compiled_config_sha256,
            "wearer_candidate_sha256s": [
                item.candidate_sha256 for item in wearer_candidates
            ],
        }
        proposals.append(
            GcsimOptimizerJointProposal(
                wearer_candidates=tuple(wearer_candidates),
                compiled_candidate=compiled,
                surrogate_score=_decimal_text(assignment.score),
                changed_wearer_count=4,
                diversity_labels=(
                    "artifact_first",
                    "package_signature:" + ":".join(
                        build_gcsim_optimizer_account_package_signature(targets)
                    ),
                    *assignment_origin_labels,
                ),
                proposal_sha256=_canonical_sha256(proposal_payload),
            )
        )
    proposals = _retain_proposal_signatures(
        proposals,
        limit=plan.max_exact_finalists,
    )
    if trace_collector is not None:
        trace_collector.set_proposals(proposals)
    coverage = GcsimOptimizerArtifactFirstCoverage(
        focus_signature_count=len(lanes),
        slot_matching_count=sum(len(value) for value in slot_matchings.values()),
        cross_slot_state_count=expanded_state_count,
        complete_assignment_count=len(complete),
        package_rejection_count=package_rejections,
        materialization_rejection_count=materialization_rejections,
        compiled_proposal_count=len(proposals),
        incumbent_anchor_count=len(incumbent_anchors),
        retained_incumbent_count=sum(
            "exact_incumbent_anchor" in item.lane_trace for item in complete
        ),
    )
    return tuple(proposals), coverage


def _build_focus_lanes(run_input, profiles_by_wearer, plan):
    wearers = run_input.request.source_simulation.wearers
    refs_by_wearer = _set_refs_by_wearer(run_input)
    uid_rows = tuple(
        tuple(item.set_uid for item in refs_by_wearer[wearer])
        for wearer in wearers
    )
    focus_signatures: list[tuple[str | None, ...]] = []
    if run_input.request.account_scope is GcsimOptimizerAccountScope.SELECTED_SET_POOLS:
        states: list[tuple[str, ...]] = [()]
        for values in uid_rows:
            states = [prefix + (value,) for prefix in states for value in values]
            if len(states) > plan.max_focus_signatures * 4:
                states = states[: plan.max_focus_signatures * 4]
        focus_signatures.extend(states)
    else:
        all_uids = tuple(sorted({value for row in uid_rows for value in row}))
        for offset in range(min(4, max(1, len(all_uids)))):
            for index in range(len(all_uids)):
                focus_signatures.append(
                    tuple(
                        all_uids[(index + offset * wearer_index) % len(all_uids)]
                        for wearer_index in range(4)
                    )
                )
        source_uids = _source_set_uid_focus(run_input)
        if source_uids is not None:
            focus_signatures.insert(0, source_uids)
    focus_signatures = list(dict.fromkeys(focus_signatures))[: plan.max_focus_signatures]
    direction_ids = _direction_ids(profiles_by_wearer, plan)
    offpiece_shapes = (None, *GCSIM_OPTIMIZER_ARTIFACT_SLOTS)
    lane_payloads = []
    variants = tuple(
        (direction_id, offpiece_slot)
        for offpiece_slot in offpiece_shapes
        for direction_id in direction_ids
    )
    for focus_index, focus in enumerate(focus_signatures):
        direction_id, offpiece_slot = variants[focus_index % len(variants)]
        lane_payloads.append((focus, direction_id, offpiece_slot))
    variant_index = 0
    while len(lane_payloads) < plan.max_focus_signatures and focus_signatures:
        direction_id, offpiece_slot = variants[variant_index % len(variants)]
        focus = focus_signatures[variant_index % len(focus_signatures)]
        value = (focus, direction_id, offpiece_slot)
        if value not in lane_payloads:
            lane_payloads.append(value)
        variant_index += 1
        if variant_index >= len(variants) * len(focus_signatures):
            break
    lanes: list[_FocusLane] = []
    for focus, direction_id, offpiece_slot in lane_payloads[
        : plan.max_focus_signatures
    ]:
        lane_payload = {
            "focus": list(focus),
            "direction": direction_id,
            "offpiece_slot": offpiece_slot,
        }
        lanes.append(
            _FocusLane(
                lane_id="artifact_first_lane/" + _canonical_sha256(lane_payload)[:20],
                focus_set_uids=tuple(focus),
                offpiece_slot_by_wearer=(offpiece_slot,) * 4,
                direction_id=direction_id,
            )
        )
    return tuple(lanes)


def _best_slot_matchings(
    artifact_slot,
    rows,
    *,
    lane,
    profiles_by_wearer,
    plan,
    trace_collector=None,
):
    pools: list[tuple[tuple[GcsimOptimizerDenseArtifact, float], ...]] = []
    for wearer_index, wearer in enumerate(sorted(profiles_by_wearer, key=lambda item: item.team_slot)):
        eligibility_index = wearer.team_slot - 1
        profile = _profile_for_direction(
            profiles_by_wearer[wearer], lane.direction_id
        )
        scored = []
        for frontier_row in rows:
            if not frontier_row.eligibility.entries[eligibility_index].eligible:
                continue
            artifact = frontier_row.artifact
            score = _piece_score(artifact, profile)
            focus = lane.focus_set_uids[wearer_index]
            offpiece_slot = lane.offpiece_slot_by_wearer[wearer_index]
            focused_here = focus is not None and artifact_slot != offpiece_slot
            selection_score = score + (
                1_000_000_000.0
                if focused_here and artifact.record.set_uid == focus
                else 0.0
            )
            scored.append((artifact, score, selection_score))
        if trace_collector is not None:
            trace_collector.add_ids(
                f"eligible_frontier/{artifact_slot}",
                wearer.team_slot,
                tuple(item[0].artifact_id for item in scored),
            )
        scored.sort(key=lambda item: (-item[2], -item[1], item[0].artifact_id))
        retained = list(scored[: plan.per_wearer_slot_head])
        best_by_set: dict[str, tuple[GcsimOptimizerDenseArtifact, float, float]] = {}
        for item in scored:
            best_by_set.setdefault(item[0].record.set_uid, item)
        retained.extend(best_by_set.values())
        deduplicated = {
            item[0].artifact_id: (item[0], item[1], item[2])
            for item in retained
        }
        if trace_collector is not None:
            trace_collector.add_ids(
                f"piece_head/{artifact_slot}",
                wearer.team_slot,
                tuple(deduplicated),
            )
        pools.append(
            tuple(
                sorted(
                    deduplicated.values(),
                    key=lambda item: (-item[2], -item[1], item[0].artifact_id),
                )
            )
        )
    if any(not pool for pool in pools):
        return None
    states = (_PartialMatching((), 0, 0.0, 0.0, ()),)
    for pool in pools:
        next_states = []
        for state in states:
            for candidate_rank, (artifact, score, selection_score) in enumerate(pool):
                if state.mask & artifact.bit_mask:
                    continue
                next_states.append(
                    _PartialMatching(
                        artifacts=state.artifacts + (artifact,),
                        mask=state.mask | artifact.bit_mask,
                        score=state.score + score,
                        selection_score=(
                            state.selection_score + selection_score
                        ),
                        rank_vector=state.rank_vector + (candidate_rank,),
                    )
                )
        next_states.sort(
            key=lambda item: (
                -item.selection_score,
                -item.score,
                tuple(row.artifact_id for row in item.artifacts),
            )
        )
        states = _retain_partial_matchings(
            next_states,
            limit=plan.slot_matching_beam_width,
        )
        if not states:
            return ()
    return tuple(
        GcsimOptimizerArtifactFirstSlotMatching(
            artifact_slot=artifact_slot,
            artifact_ids_by_wearer=tuple(
                item.artifact_id for item in state.artifacts
            ),
            artifact_mask=state.mask,
            set_uids_by_wearer=tuple(
                item.record.set_uid for item in state.artifacts
            ),
            score=state.score,
            lane_id=lane.lane_id,
            direction_id=lane.direction_id,
            rank_vector=state.rank_vector,
        )
        for state in states
    )


def _retain_partial_matchings(rows, *, limit):
    ordered = sorted(
        rows,
        key=lambda item: (
            -item.selection_score,
            -item.score,
            tuple(row.artifact_id for row in item.artifacts),
        ),
    )
    if not ordered:
        return ()
    # Reserve the tiny top-two Cartesian lattice before score/marginal
    # compression.  A four-wearer slot has at most 2**4 = 16 such states, so
    # this keeps low-order role interactions reachable without increasing the
    # beam or enumerating the full head product.  The first canonical recall
    # counterexample is rank vector (1, 0, 1, 0).
    lattice = tuple(
        sorted(
            (item for item in ordered if all(rank <= 1 for rank in item.rank_vector)),
            key=lambda item: (
                sum(item.rank_vector),
                item.rank_vector,
                -item.selection_score,
                tuple(row.artifact_id for row in item.artifacts),
            ),
        )
    )
    selected: list[_PartialMatching] = list(lattice[:limit])
    if not selected:
        selected.append(ordered[0])
    selected_keys: set[tuple[int, ...]] = {
        tuple(row.artifact_id for row in item.artifacts) for item in selected
    }
    covered_piece_positions: set[tuple[int, int]] = {
        (wearer_index, artifact.artifact_id)
        for item in selected
        for wearer_index, artifact in enumerate(item.artifacts)
    }
    if len(selected) >= limit:
        return tuple(selected[:limit])
    while len(selected) < limit:
        best = None
        best_uncovered: tuple[tuple[int, int], ...] = ()
        for item in ordered:
            key = tuple(row.artifact_id for row in item.artifacts)
            if key in selected_keys:
                continue
            uncovered = tuple(
                (wearer_index, artifact.artifact_id)
                for wearer_index, artifact in enumerate(item.artifacts)
                if (
                    wearer_index,
                    artifact.artifact_id,
                ) not in covered_piece_positions
            )
            if len(uncovered) > len(best_uncovered):
                best = item
                best_uncovered = uncovered
        if best is None or not best_uncovered:
            break
        selected.append(best)
        selected_keys.add(tuple(row.artifact_id for row in best.artifacts))
        covered_piece_positions.update(best_uncovered)
    for item in ordered:
        key = tuple(row.artifact_id for row in item.artifacts)
        if key in selected_keys:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return tuple(selected)


def _retain_slot_matchings(rows, *, limit):
    unique = {}
    for item in rows:
        previous = unique.get(item.artifact_ids_by_wearer)
        if previous is None or _slot_matching_origin_key(item) < _slot_matching_origin_key(
            previous
        ):
            unique[item.artifact_ids_by_wearer] = item
    ordered = sorted(
        unique.values(),
        key=lambda item: (-item.score, item.artifact_ids_by_wearer, item.lane_id),
    )
    balanced_lattice = sorted(
        (
            item
            for item in unique.values()
            if item.direction_id == "balanced"
            and all(rank <= 1 for rank in item.rank_vector)
        ),
        key=lambda item: (
            sum(item.rank_vector),
            item.rank_vector,
            -item.score,
            item.artifact_ids_by_wearer,
            item.lane_id,
        ),
    )
    selected: list[GcsimOptimizerArtifactFirstSlotMatching] = list(
        balanced_lattice[:limit]
    )
    selected_ids = {item.artifact_ids_by_wearer for item in selected}
    seen_sets: set[tuple[str, ...]] = {
        item.set_uids_by_wearer for item in selected
    }
    if len(selected) >= limit:
        return tuple(selected[:limit])
    for item in ordered:
        if item.artifact_ids_by_wearer in selected_ids:
            continue
        if item.set_uids_by_wearer in seen_sets:
            continue
        seen_sets.add(item.set_uids_by_wearer)
        selected.append(item)
        selected_ids.add(item.artifact_ids_by_wearer)
        if len(selected) >= limit:
            return tuple(selected)
    covered_piece_positions = {
        (wearer_index, artifact_id)
        for item in selected
        for wearer_index, artifact_id in enumerate(item.artifact_ids_by_wearer)
    }
    while len(selected) < limit:
        best = None
        best_uncovered: tuple[tuple[int, int], ...] = ()
        for item in ordered:
            if item in selected:
                continue
            uncovered = tuple(
                (wearer_index, artifact_id)
                for wearer_index, artifact_id in enumerate(
                    item.artifact_ids_by_wearer
                )
                if (wearer_index, artifact_id) not in covered_piece_positions
            )
            if len(uncovered) > len(best_uncovered):
                best = item
                best_uncovered = uncovered
        if best is None or not best_uncovered:
            break
        selected.append(best)
        selected_ids.add(best.artifact_ids_by_wearer)
        covered_piece_positions.update(best_uncovered)
    if len(selected) >= limit:
        return tuple(selected[:limit])
    for item in ordered:
        if item.artifact_ids_by_wearer in selected_ids:
            continue
        selected.append(item)
        selected_ids.add(item.artifact_ids_by_wearer)
        if len(selected) >= limit:
            break
    return tuple(selected)


def _slot_matching_origin_key(item):
    return (
        item.direction_id != "balanced",
        max(item.rank_vector),
        sum(item.rank_vector),
        item.rank_vector,
        -item.score,
        item.lane_id,
    )


def _join_matching_sequence(matchings):
    state = _CrossSlotState(((), (), (), ()), 0, ((), (), (), ()), 0.0, ())
    for matching in matchings:
        if state.mask & matching.artifact_mask:
            return None
        state = _join_state(state, matching)
    return state


def _join_state(state, matching):
    ids = tuple(
        state.ids_by_wearer[index] + (matching.artifact_ids_by_wearer[index],)
        for index in range(4)
    )
    counts = []
    for index in range(4):
        row = Counter(dict(state.set_counts_by_wearer[index]))
        row[matching.set_uids_by_wearer[index]] += 1
        counts.append(tuple(sorted(row.items())))
    return _CrossSlotState(
        ids_by_wearer=ids,
        mask=state.mask | matching.artifact_mask,
        set_counts_by_wearer=tuple(counts),
        score=state.score + matching.score,
        lane_trace=state.lane_trace + (matching.lane_id,),
    )


def _rescore_cross_slot_states(rows, *, artifact_by_id, response):
    surface = getattr(response, "surface_result", None)
    if surface is None:
        return tuple(rows)
    rescored = []
    for state in rows:
        values = _assignment_stat_values(
            state.ids_by_wearer,
            artifact_by_id=artifact_by_id,
        )
        score, _uncertainty, _ood = surface.score_team_stats(values)
        rescored.append(replace(state, score=score))
    return tuple(rescored)


def _rescore_complete_assignments(rows, *, artifact_by_id, response):
    surface = getattr(response, "surface_result", None)
    if surface is None:
        return tuple(rows)
    rescored = []
    for assignment in rows:
        values = _assignment_stat_values(
            assignment.artifact_ids_by_wearer,
            artifact_by_id=artifact_by_id,
        )
        score, uncertainty, ood = surface.score_team_stats(values)
        trace = assignment.lane_trace + (
            (
                "nonlinear_surface:"
                f"uncertainty={_decimal_text(uncertainty)}:"
                f"ood_rolls={_decimal_text(ood)}"
            ),
        )
        rescored.append(
            replace(
                assignment,
                score=score,
                lane_trace=trace,
            )
        )
    return tuple(rescored)


def _assignment_stat_values(ids_by_wearer, *, artifact_by_id):
    rows = []
    for artifact_ids in ids_by_wearer:
        values = {
            axis: 0.0 for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
        }
        for artifact_id in artifact_ids:
            artifact = artifact_by_id[artifact_id]
            for axis, value in zip(
                GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
                artifact.stats,
                strict=True,
            ):
                values[axis] += value
        rows.append(values)
    return tuple(rows)


def _retain_cross_slot_states(rows, *, limit):
    unique = {item.ids_by_wearer: item for item in rows}
    ordered = sorted(unique.values(), key=_cross_state_rank)
    if not ordered:
        return ()
    selected: list[_CrossSlotState] = [ordered[0]]
    selected_ids: set[tuple[tuple[int, ...], ...]] = {
        ordered[0].ids_by_wearer
    }
    covered_piece_positions = {
        key
        for item in selected
        for key in _cross_state_piece_keys(item)
    }
    best_by_piece_position: dict[
        tuple[int, int, int], _CrossSlotState
    ] = {}
    for item in ordered:
        for key in _cross_state_piece_keys(item):
            best_by_piece_position.setdefault(key, item)
    coverage_candidates = tuple(
        {
            item.ids_by_wearer: item
            for item in best_by_piece_position.values()
        }.values()
    )
    while len(selected) < limit:
        best = None
        best_uncovered: tuple[tuple[int, int, int], ...] = ()
        for item in coverage_candidates:
            if item.ids_by_wearer in selected_ids:
                continue
            uncovered = tuple(
                key
                for key in _cross_state_piece_keys(item)
                if key not in covered_piece_positions
            )
            if len(uncovered) > len(best_uncovered):
                best = item
                best_uncovered = uncovered
        if best is None or not best_uncovered:
            break
        selected.append(best)
        selected_ids.add(best.ids_by_wearer)
        covered_piece_positions.update(best_uncovered)
    if len(selected) >= limit:
        return tuple(sorted(selected, key=_cross_state_rank))
    progress_seen: set[tuple[tuple[tuple[str, int], ...], ...]] = {
        item.set_counts_by_wearer for item in selected
    }
    for item in ordered:
        if item.ids_by_wearer in selected_ids:
            continue
        signature = item.set_counts_by_wearer
        if signature in progress_seen:
            continue
        progress_seen.add(signature)
        selected.append(item)
        selected_ids.add(item.ids_by_wearer)
        if len(selected) >= limit:
            return tuple(sorted(selected, key=_cross_state_rank))
    for item in ordered:
        if item.ids_by_wearer in selected_ids:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return tuple(sorted(selected, key=_cross_state_rank))


def _cross_state_piece_keys(item):
    return tuple(
        (wearer_index, slot_index, artifact_id)
        for wearer_index, artifact_ids in enumerate(item.ids_by_wearer)
        for slot_index, artifact_id in enumerate(artifact_ids)
    )


def _cross_state_rank(item):
    return (-item.score, item.ids_by_wearer, item.lane_trace)


def _complete_assignment(state):
    return GcsimOptimizerArtifactFirstAssignment(
        artifact_ids_by_wearer=state.ids_by_wearer,
        artifact_mask=state.mask,
        set_counts_by_wearer=state.set_counts_by_wearer,
        score=state.score,
        lane_trace=state.lane_trace,
    )


def _normalize_required_artifact_assignments(values):
    normalized = []
    seen = set()
    for value in values:
        rows = tuple(tuple(int(artifact_id) for artifact_id in row) for row in value)
        if len(rows) != 4 or any(
            len(row) != len(GCSIM_OPTIMIZER_ARTIFACT_SLOTS) for row in rows
        ):
            raise GcsimOptimizerArtifactFirstError(
                "required incumbent must contain four five-slot assignments"
            )
        flat = tuple(artifact_id for row in rows for artifact_id in row)
        if len(set(flat)) != len(flat):
            raise GcsimOptimizerArtifactFirstError(
                "required incumbent artifact IDs must be globally injective"
            )
        if rows not in seen:
            normalized.append(rows)
            seen.add(rows)
    return tuple(normalized)


def _build_required_artifact_first_assignments(
    values,
    *,
    artifact_by_id,
    profiles_by_wearer,
):
    normalized = _normalize_required_artifact_assignments(values)
    wearers = tuple(sorted(profiles_by_wearer, key=lambda item: item.team_slot))
    built = []
    for rows in normalized:
        if any(artifact_id not in artifact_by_id for row in rows for artifact_id in row):
            continue
        artifacts_by_wearer = tuple(
            tuple(artifact_by_id[artifact_id] for artifact_id in row)
            for row in rows
        )
        if any(
            artifact.slot != GCSIM_OPTIMIZER_ARTIFACT_SLOTS[slot_index]
            for artifacts in artifacts_by_wearer
            for slot_index, artifact in enumerate(artifacts)
        ):
            continue
        set_counts = tuple(
            tuple(sorted(Counter(item.record.set_uid for item in artifacts).items()))
            for artifacts in artifacts_by_wearer
        )
        score = 0.0
        mask = 0
        for wearer, artifacts in zip(wearers, artifacts_by_wearer, strict=True):
            profile = _profile_for_direction(
                profiles_by_wearer[wearer],
                "balanced",
            )
            for artifact in artifacts:
                score += _piece_score(artifact, profile)
                mask |= artifact.bit_mask
        built.append(
            GcsimOptimizerArtifactFirstAssignment(
                artifact_ids_by_wearer=rows,
                artifact_mask=mask,
                set_counts_by_wearer=set_counts,
                score=score,
                lane_trace=("exact_incumbent_anchor",),
            )
        )
    return tuple(built)


def _build_cap_aware_package_local_assignments(
    bases,
    *,
    slot_matchings,
    artifact_by_id,
    profiles_by_wearer,
    neighbors_per_direction,
):
    """Build bounded same-package one-piece neighborhoods around legal lanes.

    A same-slot, same-set replacement keeps the derived package shape stable.
    Crit tradeoffs are retained explicitly so a linear response direction cannot
    hide a lower-CR/higher-CD alternative near the 100% Crit Rate saturation.
    The exact race remains the only authority on whether the swap is better.
    """

    wearers = tuple(sorted(profiles_by_wearer, key=lambda item: item.team_slot))
    pools: dict[tuple[int, int], dict[int, GcsimOptimizerDenseArtifact]] = {}
    for slot_index, artifact_slot in enumerate(GCSIM_OPTIMIZER_ARTIFACT_SLOTS):
        for wearer_index in range(4):
            values: dict[int, GcsimOptimizerDenseArtifact] = {}
            for matching in slot_matchings.get(artifact_slot, ()):
                artifact_id = matching.artifact_ids_by_wearer[wearer_index]
                values[artifact_id] = artifact_by_id[artifact_id]
            pools[(wearer_index, slot_index)] = values

    generated: dict[
        tuple[tuple[int, ...], ...], GcsimOptimizerArtifactFirstAssignment
    ] = {}
    for base in bases:
        used_ids = {
            artifact_id
            for artifact_ids in base.artifact_ids_by_wearer
            for artifact_id in artifact_ids
        }
        for wearer_index, wearer in enumerate(wearers):
            profiles = profiles_by_wearer[wearer]
            balanced = _profile_for_direction(profiles, "balanced")
            for slot_index, artifact_slot in enumerate(
                GCSIM_OPTIMIZER_ARTIFACT_SLOTS
            ):
                old_id = base.artifact_ids_by_wearer[wearer_index][slot_index]
                old = artifact_by_id[old_id]
                candidates = tuple(
                    item
                    for item in pools[(wearer_index, slot_index)].values()
                    if (
                        item.artifact_id != old_id
                        and item.artifact_id not in used_ids
                        and item.record.set_uid == old.record.set_uid
                    )
                )
                for candidate, reason in _cap_aware_piece_neighbors(
                    old,
                    candidates,
                    profiles=profiles,
                    limit=neighbors_per_direction,
                ):
                    artifact_ids_by_wearer = [
                        list(row) for row in base.artifact_ids_by_wearer
                    ]
                    artifact_ids_by_wearer[wearer_index][slot_index] = (
                        candidate.artifact_id
                    )
                    assignment_ids = tuple(
                        tuple(row) for row in artifact_ids_by_wearer
                    )
                    assignment = GcsimOptimizerArtifactFirstAssignment(
                        artifact_ids_by_wearer=assignment_ids,
                        artifact_mask=(
                            (base.artifact_mask & ~old.bit_mask)
                            | candidate.bit_mask
                        ),
                        set_counts_by_wearer=base.set_counts_by_wearer,
                        score=(
                            base.score
                            - _piece_score(old, balanced)
                            + _piece_score(candidate, balanced)
                        ),
                        lane_trace=base.lane_trace
                        + (
                            "cap_aware_local:"
                            f"{reason}:team_slot_{wearer.team_slot}:"
                            f"{artifact_slot}:{old_id}->{candidate.artifact_id}",
                        ),
                    )
                    previous = generated.get(assignment_ids)
                    if previous is None or assignment.score > previous.score:
                        generated[assignment_ids] = assignment
    return tuple(
        sorted(
            generated.values(),
            key=lambda item: (-item.score, item.artifact_ids_by_wearer),
        )
    )


def _cap_aware_piece_neighbors(base, candidates, *, profiles, limit):
    if not candidates:
        return ()
    cr_index = GCSIM_OPTIMIZER_ANYTIME_STAT_AXES.index("cr")
    cd_index = GCSIM_OPTIMIZER_ANYTIME_STAT_AXES.index("cd")
    base_cr = base.substats[cr_index]
    base_cd = base.substats[cd_index]
    selected: dict[int, tuple[GcsimOptimizerDenseArtifact, str]] = {}

    lower_cr_higher_cd = sorted(
        (
            item
            for item in candidates
            if item.substats[cr_index] < base_cr
            and item.substats[cd_index] > base_cd
        ),
        key=lambda item: (
            -item.substats[cd_index],
            item.substats[cr_index],
            item.artifact_id,
        ),
    )
    for item in lower_cr_higher_cd[:limit]:
        selected.setdefault(
            item.artifact_id,
            (item, "crit_lower_cr_higher_cd"),
        )

    higher_cr_lower_cd = sorted(
        (
            item
            for item in candidates
            if item.substats[cr_index] > base_cr
            and item.substats[cd_index] < base_cd
        ),
        key=lambda item: (
            -item.substats[cr_index],
            item.substats[cd_index],
            item.artifact_id,
        ),
    )
    for item in higher_cr_lower_cd[:limit]:
        selected.setdefault(
            item.artifact_id,
            (item, "crit_higher_cr_lower_cd"),
        )

    for profile in profiles:
        ordered = sorted(
            candidates,
            key=lambda item: (
                -_piece_score(item, profile),
                item.artifact_id,
            ),
        )
        for item in ordered[:limit]:
            selected.setdefault(
                item.artifact_id,
                (item, f"response_{profile.profile_id}"),
            )
    return tuple(selected.values())


def _assignment_origin_labels(assignment):
    labels = {
                value.split(":team_slot_", 1)[0]
                for value in assignment.lane_trace
                if value.startswith("cap_aware_local:")
    }
    if "exact_incumbent_anchor" in assignment.lane_trace:
        labels.add("exact_incumbent_anchor")
    return tuple(sorted(labels))


def _retain_complete_assignments(
    rows,
    *,
    limit,
    required=(),
    coverage_required=(),
):
    unique = {item.artifact_ids_by_wearer: item for item in rows}
    ordered = sorted(
        unique.values(),
        key=lambda item: (-item.score, item.artifact_ids_by_wearer),
    )
    selected = []
    selected_ids = set()
    signatures = set()
    for item in sorted(
        (
            unique.get(value.artifact_ids_by_wearer, value)
            for value in required
        ),
        key=lambda value: (-value.score, value.artifact_ids_by_wearer),
    ):
        if item.artifact_ids_by_wearer in selected_ids:
            continue
        selected.append(item)
        selected_ids.add(item.artifact_ids_by_wearer)
        signatures.add(item.set_counts_by_wearer)
        if len(selected) >= limit:
            return tuple(selected)
    covered_piece_positions = {
        key
        for item in selected
        for key in _assignment_piece_keys(item)
    }
    for coverage_rows in (coverage_required, ordered):
        coverage_ordered = sorted(
            {
                item.artifact_ids_by_wearer: unique.get(
                    item.artifact_ids_by_wearer,
                    item,
                )
                for item in coverage_rows
            }.values(),
            key=lambda item: (-item.score, item.artifact_ids_by_wearer),
        )
        best_by_piece_position = {}
        for item in coverage_ordered:
            for key in _assignment_piece_keys(item):
                best_by_piece_position.setdefault(key, item)
        coverage_candidates = tuple(
            {
                item.artifact_ids_by_wearer: item
                for item in best_by_piece_position.values()
            }.values()
        )
        while len(selected) < limit:
            best = None
            best_uncovered: tuple[tuple[int, int, int], ...] = ()
            for item in coverage_candidates:
                if item.artifact_ids_by_wearer in selected_ids:
                    continue
                uncovered = tuple(
                    key
                    for key in _assignment_piece_keys(item)
                    if key not in covered_piece_positions
                )
                if len(uncovered) > len(best_uncovered):
                    best = item
                    best_uncovered = uncovered
            if best is None or not best_uncovered:
                break
            selected.append(best)
            selected_ids.add(best.artifact_ids_by_wearer)
            signatures.add(best.set_counts_by_wearer)
            covered_piece_positions.update(best_uncovered)
        if len(selected) >= limit:
            return tuple(selected)
    for item in ordered:
        if item.artifact_ids_by_wearer in selected_ids:
            continue
        signature = item.set_counts_by_wearer
        if signature in signatures:
            continue
        signatures.add(signature)
        selected.append(item)
        selected_ids.add(item.artifact_ids_by_wearer)
        if len(selected) >= limit:
            return tuple(selected)
    for item in ordered:
        if item.artifact_ids_by_wearer in selected_ids:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return tuple(selected)


def _assignment_piece_keys(item):
    return tuple(
        (wearer_index, slot_index, artifact_id)
        for wearer_index, artifact_ids in enumerate(
            item.artifact_ids_by_wearer
        )
        for slot_index, artifact_id in enumerate(artifact_ids)
    )


def _retain_proposal_signatures(rows, *, limit):
    ordered = sorted(
        rows,
        key=lambda item: (-Decimal(item.surrogate_score), item.proposal_sha256),
    )
    selected = []
    selected_ids = set()
    signatures = set()
    for item in ordered:
        if "exact_incumbent_anchor" not in item.diversity_labels:
            continue
        selected.append(item)
        selected_ids.add(item.proposal_sha256)
        signatures.add(
            build_gcsim_optimizer_account_package_signature(
                item.compiled_candidate.targets
            )
        )
        if len(selected) >= limit:
            return tuple(selected)
    for item in ordered:
        if item.proposal_sha256 in selected_ids:
            continue
        signature = build_gcsim_optimizer_account_package_signature(
            item.compiled_candidate.targets
        )
        if signature in signatures:
            continue
        signatures.add(signature)
        selected.append(item)
        selected_ids.add(item.proposal_sha256)
        if len(selected) >= limit:
            return tuple(selected)
    cap_aware = tuple(
        item
        for item in ordered
        if any(
            label.startswith("cap_aware_local:")
            for label in item.diversity_labels
        )
    )
    covered_piece_positions = {
        key for item in selected for key in _proposal_piece_keys(item)
    }
    while len(selected) < limit:
        best = None
        best_uncovered: tuple[tuple[int, str, int], ...] = ()
        for item in cap_aware:
            if item.proposal_sha256 in selected_ids:
                continue
            uncovered = tuple(
                key
                for key in _proposal_piece_keys(item)
                if key not in covered_piece_positions
            )
            if len(uncovered) > len(best_uncovered):
                best = item
                best_uncovered = uncovered
        if best is None or not best_uncovered:
            break
        selected.append(best)
        selected_ids.add(best.proposal_sha256)
        covered_piece_positions.update(best_uncovered)
    if len(selected) >= limit:
        return tuple(selected)
    for item in ordered:
        if item.proposal_sha256 in selected_ids:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return tuple(selected)


def _proposal_piece_keys(item):
    return tuple(
        (
            assignment.wearer.team_slot,
            artifact_slot,
            int(assignment.artifact_ids_by_slot[artifact_slot]),
        )
        for assignment in (
            item.compiled_candidate.assignment_witness.wearer_assignments
        )
        for artifact_slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
    )


def _representative_targets(run_input):
    targets = []
    refs_by_wearer = _set_refs_by_wearer(run_input)
    for wearer in run_input.request.source_simulation.wearers:
        refs = refs_by_wearer[wearer]
        four_piece = next(
            (
                item
                for item in refs
                if (
                    run_input.set_capability(item.gcsim_set_key) is not None
                    and run_input.set_capability(item.gcsim_set_key).optimizer_four_piece_ready
                )
            ),
            None,
        )
        if four_piece is not None:
            targets.append(
                GcsimOptimizerWearerTarget(
                    wearer,
                    GcsimFourPieceTargetPackage(four_piece),
                )
            )
            continue
        pair_refs = tuple(
            item
            for item in refs
            if (
                run_input.set_capability(item.gcsim_set_key) is not None
                and run_input.set_capability(item.gcsim_set_key).two_piece_modeled
            )
        )
        pair = next(
            (
                (left, right)
                for index, left in enumerate(pair_refs)
                for right in pair_refs[index + 1 :]
                if left.gcsim_set_key != right.gcsim_set_key
            ),
            None,
        )
        if pair is None or not run_input.request.include_2p2p:
            raise GcsimOptimizerArtifactFirstError(
                f"wearer {wearer.team_slot} has no representative modeled package"
            )
        targets.append(
            GcsimOptimizerWearerTarget(
                wearer,
                GcsimTwoPlusTwoTargetPackage(*pair),
            )
        )
    return tuple(targets)


def _set_impact_targets(run_input):
    targets = []
    refs_by_wearer = _set_refs_by_wearer(run_input)
    for wearer in run_input.request.source_simulation.wearers:
        for set_ref in refs_by_wearer[wearer]:
            capability = run_input.set_capability(set_ref.gcsim_set_key)
            if capability is None:
                continue
            if capability.optimizer_four_piece_ready:
                targets.append(
                    GcsimOptimizerWearerTarget(
                        wearer,
                        GcsimFourPieceTargetPackage(set_ref),
                    )
                )
            if (
                run_input.request.include_2p2p
                and capability.two_piece_modeled
            ):
                targets.append(
                    GcsimOptimizerSingleTwoPieceImpactTarget(
                        wearer=wearer,
                        set_ref=set_ref,
                    )
                )
    if not targets:
        raise GcsimOptimizerArtifactFirstError(
            "artifact-first set model has no measurable package targets"
        )
    return tuple(targets)


def _set_impact_target_score(target, set_impact):
    if set_impact is None:
        return 0.0
    exact = set_impact.row_by_target_identity.get(
        _canonical_sha256(target.to_dict())
    )
    if exact is not None:
        return exact.surrogate_dps
    if not isinstance(target.package, GcsimTwoPlusTwoTargetPackage):
        return 0.0
    keys = {
        target.package.set_a.gcsim_set_key,
        target.package.set_b.gcsim_set_key,
    }
    score = 0.0
    matched = set()
    for row in set_impact.rows:
        component = row.target
        if (
            isinstance(component, GcsimOptimizerSingleTwoPieceImpactTarget)
            and component.wearer == target.wearer
            and component.set_ref.gcsim_set_key in keys
            and row.retained
        ):
            score += row.surrogate_dps
            matched.add(component.set_ref.gcsim_set_key)
    return score if matched == keys else 0.0


def _set_refs_by_wearer(run_input):
    request = run_input.request
    if request.account_scope is GcsimOptimizerAccountScope.SELECTED_SET_POOLS:
        return {
            pool.wearer: tuple(pool.allowed_sets)
            for pool in request.selected_set_pools
        }
    refs = _all_modeled_set_refs(run_input)
    return {wearer: refs for wearer in request.source_simulation.wearers}


def _all_modeled_set_refs(run_input):
    mapped: dict[str, str] = {}
    slots_by_uid: dict[str, set[str]] = defaultdict(set)
    for artifact in run_input.artifact_database.artifacts:
        if not artifact.default_eligible or artifact.set_mapping_status != "ready":
            continue
        capability = run_input.set_capability(artifact.gcsim_set_key)
        if capability is None or capability.max_rarity != 5:
            continue
        mapped.setdefault(artifact.set_uid, artifact.gcsim_set_key)
        if mapped[artifact.set_uid] != artifact.gcsim_set_key:
            raise GcsimOptimizerArtifactFirstError(
                "one concrete set UID maps to multiple GCSIM keys"
            )
        slots_by_uid[artifact.set_uid].add(artifact.position_key)
    refs = []
    for set_uid in sorted(mapped):
        key = mapped[set_uid]
        capability = run_input.set_capability(key)
        assert capability is not None
        slot_count = len(slots_by_uid[set_uid])
        if not (
            (capability.optimizer_four_piece_ready and slot_count >= 4)
            or (
                run_input.request.include_2p2p
                and capability.two_piece_modeled
                and slot_count >= 2
            )
        ):
            continue
        refs.append(
            GcsimOptimizerSetReference(
                set_uid=set_uid,
                gcsim_set_key=key,
                engine_binding_sha256=run_input.engine_binding_sha256,
                catalog_fingerprint=run_input.catalog_fingerprint,
                set_parameters={},
            )
        )
    if not refs:
        raise GcsimOptimizerArtifactFirstError(
            "all-database artifact-first domain has no modeled physical set"
        )
    return tuple(refs)


def _source_set_uid_focus(run_input):
    uids_by_key: dict[str, str] = {}
    for artifact in run_input.artifact_database.artifacts:
        if artifact.set_mapping_status == "ready":
            uids_by_key.setdefault(artifact.gcsim_set_key, artifact.set_uid)
    rows = []
    suggestions_by_slot: dict[int, list[str]] = defaultdict(list)
    for item in run_input.config_shell.source_set_suggestions:
        if item.mapping_status == "ready":
            suggestions_by_slot[item.wearer.team_slot].append(item.gcsim_set_key)
    for slot in range(1, 5):
        key = next(
            (value for value in suggestions_by_slot[slot] if value in uids_by_key),
            None,
        )
        if key is None:
            return None
        rows.append(uids_by_key[key])
    return tuple(rows)


def _direction_ids(profiles_by_wearer, plan):
    common = None
    for profiles in profiles_by_wearer.values():
        ids = {item.profile_id for item in profiles}
        common = ids if common is None else common & ids
    available = common or set()
    ordered = ["balanced"]
    ordered.extend(
        item
        for item in (
            "uncertain_exploration",
            "crit_chance",
            "crit_damage",
        )
        if item in available
    )
    ordered.extend(
        sorted(
            available
            - {
                "balanced",
                "uncertain_exploration",
                "crit_chance",
                "crit_damage",
            }
        )
    )
    return tuple(ordered[: plan.response_directions_per_focus])


def _profile_for_direction(profiles, direction_id):
    return next(
        (item for item in profiles if item.profile_id == direction_id),
        next(item for item in profiles if item.profile_id == "balanced"),
    )


def _piece_score(artifact, profile):
    return sum(
        value * weight
        for value, weight in zip(artifact.substats, profile.stat_weights, strict=True)
    ) + profile.main_score_index.get((artifact.slot, artifact.main_key), 0.0)


def _offpiece_shape(artifacts, target):
    counts = Counter(item.set_uid for item in artifacts)
    if isinstance(target.package, GcsimTwoPlusTwoTargetPackage):
        return "2p2p"
    target_uid = target.package.set_ref.set_uid
    if counts[target_uid] == 5:
        return "5p"
    return next(item.position_key for item in artifacts if item.set_uid != target_uid)


def _race_progress_stage(tier_id):
    return {
        "screen_8": GcsimOptimizerProgressStage.SCREENING,
        "refine_32": GcsimOptimizerProgressStage.REFINEMENT,
        "validate_200": GcsimOptimizerProgressStage.FINAL_VALIDATION,
        "rerace_1000": GcsimOptimizerProgressStage.RERACE,
    }.get(tier_id, GcsimOptimizerProgressStage.SCREENING)


def _race_iterations(tier_id):
    return {"screen_8": 8, "refine_32": 32, "validate_200": 200, "rerace_1000": 1000}.get(tier_id)


def _evaluation_rank(item):
    return (-float(item.dps_mean or 0.0), float(item.dps_se or float("inf")), item.proposal.proposal_sha256)


def _decimal_text(value):
    return format(Decimal(str(value)), "f")


def _canonical_sha256(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _thaw_identity_value(value):
    if isinstance(value, Mapping):
        return {
            str(key): _thaw_identity_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_thaw_identity_value(item) for item in value]
    return value


def _raise_generation_interrupted(is_cancelled, deadline, clock):
    if is_cancelled():
        raise _ArtifactFirstInterrupted("artifact_first_cancelled", cancelled=True)
    if deadline is not None and clock() >= deadline:
        raise _ArtifactFirstInterrupted("artifact_first_deadline", cancelled=False)


class _ArtifactFirstInterrupted(RuntimeError):
    def __init__(self, message: str, *, cancelled: bool) -> None:
        super().__init__(message)
        self.cancelled = cancelled


__all__ = [
    "GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_ID",
    "GCSIM_OPTIMIZER_ARTIFACT_FIRST_PLAN_VERSION",
    "GCSIM_OPTIMIZER_ARTIFACT_FIRST_SCHEMA_VERSION",
    "GcsimOptimizerArtifactFirstAssignment",
    "GcsimOptimizerArtifactFirstCoverage",
    "GcsimOptimizerArtifactFirstError",
    "GcsimOptimizerArtifactFirstPlan",
    "GcsimOptimizerArtifactFirstRecallTrace",
    "GcsimOptimizerArtifactFirstResult",
    "GcsimOptimizerArtifactFirstSession",
    "GcsimOptimizerArtifactFirstSlotMatching",
    "generate_gcsim_optimizer_artifact_first_proposals",
]
