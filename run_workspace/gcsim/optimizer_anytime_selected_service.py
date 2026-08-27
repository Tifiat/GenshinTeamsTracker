"""Production selected-set account optimizer: ``anytime_approx_v2``.

This is intentionally a separate path from the legacy broad response scan.
It reuses the frozen request/database, strict materializer/compiler, ordinary
GCSIM runner, and product terminal contracts while replacing the expensive
search middle with:

1. one dense artifact index;
2. one shared rotation-response bootstrap;
3. multi-profile Pareto/shadow wearer pools;
4. bit-mask joint beam/local search;
5. adaptive 8 -> 32 -> 200 -> close-only 1000 evaluation.

The result is explicitly "best found under this frozen work plan", never a
claim of exhaustive optimality.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
import hashlib
import json
from math import isfinite
from threading import Event, Lock
from time import monotonic

from .optimizer_anytime_candidates import (
    GcsimOptimizerAnytimeCandidatePlan,
    GcsimOptimizerAnytimeJointCoverage,
    GcsimOptimizerAnytimeWearerPool,
    GcsimOptimizerDenseArtifactCatalog,
    build_gcsim_optimizer_anytime_joint_proposals,
    build_gcsim_optimizer_coordinate_refinement_proposals,
    build_gcsim_optimizer_soft_main_coverage_profiles,
    build_gcsim_optimizer_stat_coverage_profiles,
    build_gcsim_optimizer_dense_artifact_catalog,
    build_gcsim_optimizer_uncertainty_refinement_profiles,
    generate_gcsim_optimizer_anytime_wearer_pool,
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
from .optimizer_cache import GcsimOptimizerCacheStore
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_joint_proposals import GcsimOptimizerJointProposal
from .optimizer_package_feasibility import (
    gcsim_optimizer_account_target_is_physically_feasible,
)
from .optimizer_product_contracts import (
    GcsimFourPieceTargetPackage,
    GcsimOptimizerAccountScope,
    GcsimOptimizerCacheCounters,
    GcsimOptimizerCandidateResult,
    GcsimOptimizerCoverageCounters,
    GcsimOptimizerDpsEstimate,
    GcsimOptimizerEvaluationIdentity,
    GcsimOptimizerIssue,
    GcsimOptimizerIssueScope,
    GcsimOptimizerLeaderSnapshot,
    GcsimOptimizerOperation,
    GcsimOptimizerProgressEvent,
    GcsimOptimizerProgressLeaderQuality,
    GcsimOptimizerProgressLeaderScope,
    GcsimOptimizerProgressStage,
    GcsimOptimizerTerminalResult,
    GcsimOptimizerTerminalStatus,
    GcsimOptimizerTimingCounters,
    GcsimOptimizerWearerSetPool,
    GcsimOptimizerWearerTarget,
    GcsimTwoPlusTwoTargetPackage,
    build_gcsim_optimizer_top_n,
)
from .optimizer_run_input import GcsimOptimizerRunInput
from .optimizer_set_impact import (
    GcsimOptimizerSetImpactPlan,
    GcsimOptimizerSetImpactResult,
    discover_gcsim_optimizer_set_impacts,
)
from .optimizer_stat_response import GcsimStatResponseTarget


GCSIM_OPTIMIZER_ANYTIME_SELECTED_SCHEMA_VERSION = 2
GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_ID = "anytime_approx_v2"
GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_VERSION = 11

AnytimeSelectedProgressCallback = Callable[
    [GcsimOptimizerProgressEvent],
    None,
]


class GcsimOptimizerAnytimeSelectedError(RuntimeError):
    """Fail-closed production selected-set orchestration error."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAnytimeSelectedPlan:
    response: GcsimOptimizerAnytimeResponsePlan = field(
        default_factory=GcsimOptimizerAnytimeResponsePlan
    )
    candidates: GcsimOptimizerAnytimeCandidatePlan = field(
        default_factory=GcsimOptimizerAnytimeCandidatePlan
    )
    race: GcsimOptimizerAnytimeRacePlan = field(
        default_factory=GcsimOptimizerAnytimeRacePlan
    )
    # Four account wearers can all differ from the response-ranked seed; keep
    # one bounded revisit after a full coordinate sweep.
    coordinate_refinement_rounds: int = 5
    coordinate_seed_count: int = 3
    coordinate_max_candidates_per_wearer: int = 320
    coordinate_conflict_beam_width: int = 16
    coordinate_screen_proposal_limit: int = 256
    top_n: int = 8
    overall_deadline_seconds: float = 1200.0
    schema_version: int = GCSIM_OPTIMIZER_ANYTIME_SELECTED_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.response, GcsimOptimizerAnytimeResponsePlan):
            raise GcsimOptimizerAnytimeSelectedError(
                "response plan must be typed"
            )
        if not isinstance(self.candidates, GcsimOptimizerAnytimeCandidatePlan):
            raise GcsimOptimizerAnytimeSelectedError(
                "candidate plan must be typed"
            )
        if not isinstance(self.race, GcsimOptimizerAnytimeRacePlan):
            raise GcsimOptimizerAnytimeSelectedError(
                "race plan must be typed"
            )
        if (
            isinstance(self.top_n, bool)
            or not isinstance(self.top_n, int)
            or self.top_n <= 0
        ):
            raise GcsimOptimizerAnytimeSelectedError(
                "top_n must be a positive integer"
            )
        for field_name, allow_zero in (
            ("coordinate_refinement_rounds", True),
            ("coordinate_seed_count", False),
            ("coordinate_max_candidates_per_wearer", False),
            ("coordinate_conflict_beam_width", False),
            ("coordinate_screen_proposal_limit", False),
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < (0 if allow_zero else 1)
            ):
                raise GcsimOptimizerAnytimeSelectedError(
                    f"{field_name} has an invalid bound"
                )
        if (
            not isfinite(self.overall_deadline_seconds)
            or self.overall_deadline_seconds <= 0
        ):
            raise GcsimOptimizerAnytimeSelectedError(
                "overall_deadline_seconds must be finite and positive"
            )
        if self.response.total_cpu_budget != self.race.total_cpu_budget:
            raise GcsimOptimizerAnytimeSelectedError(
                "response and race CPU budgets must match"
            )
        top_n_capacities = (
            self.candidates.max_joint_proposals,
            *(tier.max_candidates for tier in self.race.tiers[:3]),
        )
        if any(capacity < self.top_n for capacity in top_n_capacities):
            raise GcsimOptimizerAnytimeSelectedError(
                "account search capacities must be at least top_n through "
                "joint, screening, refinement, and validation"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_ID,
            "plan_version": GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_VERSION,
            "claim": "best_found_under_frozen_budget",
            "response": self.response.to_dict(),
            "candidates": self.candidates.to_dict(),
            "race": self.race.to_dict(),
            "coordinate_refinement_rounds": (
                self.coordinate_refinement_rounds
            ),
            "coordinate_seed_count": self.coordinate_seed_count,
            "coordinate_max_candidates_per_wearer": (
                self.coordinate_max_candidates_per_wearer
            ),
            "coordinate_conflict_beam_width": (
                self.coordinate_conflict_beam_width
            ),
            "coordinate_screen_proposal_limit": (
                self.coordinate_screen_proposal_limit
            ),
            "top_n": self.top_n,
            "overall_deadline_seconds": self.overall_deadline_seconds,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAnytimeSelectedResult:
    terminal: GcsimOptimizerTerminalResult
    run_input_sha256: str
    plan: GcsimOptimizerAnytimeSelectedPlan
    progress_events: tuple[GcsimOptimizerProgressEvent, ...]
    targets_by_wearer: tuple[
        tuple[int, tuple[GcsimOptimizerWearerTarget, ...]], ...
    ]
    dense_catalog: GcsimOptimizerDenseArtifactCatalog | None
    response_result: GcsimOptimizerAnytimeResponseResult | None
    wearer_pools: tuple[GcsimOptimizerAnytimeWearerPool, ...]
    joint_coverage: GcsimOptimizerAnytimeJointCoverage | None
    race_result: GcsimOptimizerAnytimeRaceResult | None
    preliminary_race_results: tuple[
        GcsimOptimizerAnytimeRaceResult, ...
    ] = ()
    schema_version: int = GCSIM_OPTIMIZER_ANYTIME_SELECTED_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        _require_sha256(self.run_input_sha256, "run_input_sha256")
        if tuple(item.sequence for item in self.progress_events) != tuple(
            range(len(self.progress_events))
        ):
            raise GcsimOptimizerAnytimeSelectedError(
                "progress sequence must be contiguous"
            )
        if any(
            not isinstance(item, GcsimOptimizerAnytimeRaceResult)
            for item in self.preliminary_race_results
        ):
            raise GcsimOptimizerAnytimeSelectedError(
                "preliminary race results must be typed"
            )

    @property
    def best_found(self):
        return self.terminal.best_found

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "terminal": self.terminal.to_dict(),
            "run_input_sha256": self.run_input_sha256,
            "plan_sha256": self.plan.identity_sha256,
            "progress_events": [
                item.to_dict() for item in self.progress_events
            ],
            "targets_by_wearer": {
                str(slot): [item.to_dict() for item in rows]
                for slot, rows in self.targets_by_wearer
            },
            "dense_catalog_sha256": (
                None
                if self.dense_catalog is None
                else self.dense_catalog.identity_sha256
            ),
            "response_evidence_sha256": (
                None
                if self.response_result is None
                else self.response_result.evidence_sha256
            ),
            "wearer_candidate_counts": {
                str(item.wearer.team_slot): len(item.candidates)
                for item in self.wearer_pools
            },
            "joint_coverage": (
                None
                if self.joint_coverage is None
                else self.joint_coverage.to_dict()
            ),
            "race_evidence_sha256": (
                None
                if self.race_result is None
                else self.race_result.evidence_sha256
            ),
            "preliminary_race_evidence_sha256s": [
                item.evidence_sha256
                for item in self.preliminary_race_results
            ],
        }


@dataclass(frozen=True, slots=True)
class _GcsimOptimizerAllSetSignatureRefinement:
    """Restricted physical search space for one exact package signature."""

    package_signature: tuple[str, ...]
    wearer_pools: tuple[GcsimOptimizerAnytimeWearerPool, ...]
    joint_proposals: tuple[GcsimOptimizerJointProposal, ...]


class GcsimOptimizerAnytimeSelectedSession:
    """One-shot owner of the complete production selected-set path."""

    def __init__(
        self,
        run_input: GcsimOptimizerRunInput,
        *,
        engine_context: GcsimOptimizerEngineContext,
        prepared_config_text: str,
        plan: GcsimOptimizerAnytimeSelectedPlan | None = None,
        progress_callback: AnytimeSelectedProgressCallback | None = None,
        cache_store: GcsimOptimizerCacheStore | None = None,
        enable_cache: bool = True,
        session_factory: Callable[[object], object] | None = None,
        response_discovery: Callable[..., object] | None = None,
        response_master_seed: int | None = None,
        stat_response_target: GcsimStatResponseTarget | None = None,
        environment: Mapping[str, str] | None = None,
        clock: Callable[[], float] = monotonic,
        target_pools: Sequence[GcsimOptimizerWearerSetPool] | None = None,
        allow_all_database_scope: bool = False,
        boundary_plan_id: str = GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_ID,
        boundary_plan_version: int = (
            GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_VERSION
        ),
        boundary_plan_parameters: Mapping[str, object] | None = None,
        neutral_package_response: bool = False,
        enable_set_impact_screening: bool = False,
        set_impact_plan: GcsimOptimizerSetImpactPlan | None = None,
        set_impact_discovery: Callable[..., object] | None = None,
        soft_main_pruning: bool = False,
        local_refinement_signature_limit: int = 0,
        local_refinement_proposals_per_signature: int = 8,
        required_anchor_targets: Sequence[
            GcsimOptimizerWearerTarget
        ] = (),
        required_joint_proposals: Sequence[
            GcsimOptimizerJointProposal
        ] = (),
    ) -> None:
        self.run_input = run_input
        self.engine_context = engine_context
        self.prepared_config_text = prepared_config_text
        self.plan = plan or GcsimOptimizerAnytimeSelectedPlan()
        self.progress_callback = progress_callback
        self.cache_store = cache_store
        self.enable_cache = enable_cache
        self.session_factory = session_factory
        self.response_discovery = (
            response_discovery
            or discover_gcsim_optimizer_anytime_response
        )
        self.response_master_seed = response_master_seed
        self.stat_response_target = stat_response_target
        self.environment = dict(environment or {})
        self.clock = clock
        self.target_pools = tuple(
            target_pools or run_input.request.selected_set_pools
        )
        if tuple(pool.wearer.team_slot for pool in self.target_pools) != (
            1,
            2,
            3,
            4,
        ):
            raise GcsimOptimizerAnytimeSelectedError(
                "target pools must cover canonical wearer slots 1..4"
            )
        if not isinstance(allow_all_database_scope, bool):
            raise GcsimOptimizerAnytimeSelectedError(
                "allow_all_database_scope must be boolean"
            )
        self.allow_all_database_scope = allow_all_database_scope
        self.boundary_plan_id = str(boundary_plan_id)
        self.boundary_plan_version = int(boundary_plan_version)
        self.boundary_plan_parameters = (
            dict(boundary_plan_parameters)
            if boundary_plan_parameters is not None
            else self.plan.to_dict()
        )
        self.neutral_package_response = bool(neutral_package_response)
        self.enable_set_impact_screening = bool(
            enable_set_impact_screening
        )
        if self.enable_set_impact_screening and not allow_all_database_scope:
            raise GcsimOptimizerAnytimeSelectedError(
                "set-impact screening is reserved for broad package search"
            )
        self.set_impact_plan = (
            set_impact_plan or GcsimOptimizerSetImpactPlan()
        )
        if not isinstance(
            self.set_impact_plan,
            GcsimOptimizerSetImpactPlan,
        ):
            raise GcsimOptimizerAnytimeSelectedError(
                "set_impact_plan must be typed"
            )
        self.set_impact_discovery = (
            set_impact_discovery
            or discover_gcsim_optimizer_set_impacts
        )
        if not isinstance(soft_main_pruning, bool):
            raise GcsimOptimizerAnytimeSelectedError(
                "soft_main_pruning must be boolean"
            )
        for field_name, value, allow_zero in (
            (
                "local_refinement_signature_limit",
                local_refinement_signature_limit,
                True,
            ),
            (
                "local_refinement_proposals_per_signature",
                local_refinement_proposals_per_signature,
                False,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < (0 if allow_zero else 1)
            ):
                raise GcsimOptimizerAnytimeSelectedError(
                    f"{field_name} has an invalid bound"
                )
        anchors = tuple(required_anchor_targets)
        if anchors and (
            len(anchors) != 4
            or tuple(item.wearer.team_slot for item in anchors)
            != (1, 2, 3, 4)
        ):
            raise GcsimOptimizerAnytimeSelectedError(
                "required anchor targets must cover canonical slots 1..4"
            )
        joint_anchors = tuple(required_joint_proposals)
        if any(
            not isinstance(item, GcsimOptimizerJointProposal)
            for item in joint_anchors
        ):
            raise GcsimOptimizerAnytimeSelectedError(
                "required joint proposals must be typed"
            )
        if len(
            {item.proposal_sha256 for item in joint_anchors}
        ) != len(joint_anchors):
            raise GcsimOptimizerAnytimeSelectedError(
                "required joint proposal identities must be unique"
            )
        if len(
            {
                item.compiled_candidate.compiled_config_sha256
                for item in joint_anchors
            }
        ) != len(joint_anchors):
            raise GcsimOptimizerAnytimeSelectedError(
                "required joint proposals must have distinct exact configs"
            )
        for proposal in joint_anchors:
            compiled = proposal.compiled_candidate
            if (
                compiled.assignment_witness.request_sha256
                != run_input.request.request_sha256
                or compiled.assignment_witness.artifact_database_input_sha256
                != run_input.artifact_database.artifact_database_input_sha256
                or tuple(item.wearer for item in compiled.targets)
                != run_input.request.source_simulation.wearers
            ):
                raise GcsimOptimizerAnytimeSelectedError(
                    "required joint proposal is not rebound to this run input"
                )
        if (
            (
                soft_main_pruning
                or local_refinement_signature_limit
                or anchors
                or joint_anchors
            )
            and not allow_all_database_scope
        ):
            raise GcsimOptimizerAnytimeSelectedError(
                "soft/local package refinement is reserved for broad search"
            )
        self.soft_main_pruning = soft_main_pruning
        self.local_refinement_signature_limit = (
            local_refinement_signature_limit
        )
        if (
            self.allow_all_database_scope
            and self.local_refinement_signature_limit
            and self.local_refinement_signature_limit < self.plan.top_n
        ):
            raise GcsimOptimizerAnytimeSelectedError(
                "all-database local refinement must cover every displayable "
                "package signature"
            )
        self.local_refinement_proposals_per_signature = (
            local_refinement_proposals_per_signature
        )
        self.required_anchor_targets = anchors
        self.required_joint_proposals = joint_anchors
        self.local_refinement_signature_count = 0
        self.local_refinement_candidate_count = 0
        self.local_refinement_proposal_count = 0
        self.preliminary_race_results: list[
            GcsimOptimizerAnytimeRaceResult
        ] = []
        self.set_impact_result: GcsimOptimizerSetImpactResult | None = None
        self._cancel_event = Event()
        self._lock = Lock()
        self._active_cancellable: object | None = None
        self._started = False
        self._progress: list[GcsimOptimizerProgressEvent] = []
        self._timing: dict[str, float] = {}
        self._stage_started: dict[str, float] = {}

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            active = self._active_cancellable
        if active is not None and hasattr(active, "cancel"):
            active.cancel()

    def run(self) -> GcsimOptimizerAnytimeSelectedResult:
        with self._lock:
            if self._started:
                raise GcsimOptimizerAnytimeSelectedError(
                    "anytime selected sessions are one-shot"
                )
            self._started = True
        started = self.clock()
        deadline = started + self.plan.overall_deadline_seconds
        targets_by_wearer: tuple[
            tuple[int, tuple[GcsimOptimizerWearerTarget, ...]], ...
        ] = ()
        catalog = None
        response = None
        wearer_pools: tuple[GcsimOptimizerAnytimeWearerPool, ...] = ()
        base_wearer_pools: tuple[
            GcsimOptimizerAnytimeWearerPool, ...
        ] = ()
        joint_coverage = None
        race = None
        issues: list[GcsimOptimizerIssue] = []
        try:
            self._emit(
                GcsimOptimizerProgressStage.PREFLIGHT,
                started=started,
                deadline=deadline,
                completed=0,
                planned=1,
            )
            not_ready = self._preflight(started)
            if not_ready is not None:
                return self._result(
                    not_ready,
                    targets_by_wearer=targets_by_wearer,
                    catalog=catalog,
                    response=response,
                    wearer_pools=wearer_pools,
                    joint_coverage=joint_coverage,
                    race=race,
                )
            self._emit(
                GcsimOptimizerProgressStage.PREFLIGHT,
                started=started,
                deadline=deadline,
                completed=1,
                planned=1,
            )
            self._raise_if_interrupted(deadline)

            self._start_stage("layout_scan")
            targets_by_wearer, target_issues = self._build_targets()
            issues.extend(target_issues)
            catalog = build_gcsim_optimizer_dense_artifact_catalog(
                self.run_input
            )
            self._finish_stage("layout_scan")
            self._emit(
                GcsimOptimizerProgressStage.LAYOUT_SCAN,
                started=started,
                deadline=deadline,
                completed=len(catalog.artifacts),
                planned=len(self.run_input.artifact_database.artifacts),
            )
            self._raise_if_interrupted(deadline)
            if any(not rows for _slot, rows in targets_by_wearer):
                terminal = self._terminal(
                    GcsimOptimizerTerminalStatus.NO_SUCCESS,
                    "anytime_selected_has_no_feasible_target_for_a_wearer",
                    started,
                    issues=issues,
                    catalog=catalog,
                )
                return self._result(
                    terminal,
                    targets_by_wearer=targets_by_wearer,
                    catalog=catalog,
                    response=response,
                    wearer_pools=wearer_pools,
                    joint_coverage=joint_coverage,
                    race=race,
                )
            self._raise_if_interrupted(deadline)

            representative_targets = tuple(rows[0] for _slot, rows in targets_by_wearer)
            self._start_stage("response_scan")
            response_plan = self.plan.response
            response_remaining = max(deadline - self.clock(), 0.001)
            if response_remaining < response_plan.overall_deadline_seconds:
                response_plan = replace(
                    response_plan,
                    overall_deadline_seconds=response_remaining,
                )

            try:
                response = self.response_discovery(
                    self.run_input,
                    engine_context=self.engine_context,
                    prepared_config_text=self.prepared_config_text,
                    representative_targets=representative_targets,
                    plan=response_plan,
                    progress_callback=lambda completed, planned, hits: (
                        self._emit(
                            GcsimOptimizerProgressStage.RESPONSE_SCAN,
                            started=started,
                            deadline=deadline,
                            completed=completed,
                            planned=planned,
                            cache_hits=hits,
                        )
                    ),
                    environment=self.environment,
                    stat_response_target=self.stat_response_target,
                    neutral_package_response=self.neutral_package_response,
                    master_seed=self.response_master_seed,
                    is_cancelled=self._cancel_event.is_set,
                    clock=self.clock,
                )
            finally:
                self._finish_stage("response_scan")
            self._raise_if_interrupted(deadline)

            package_scores: Mapping[str, float] = {}
            if self.enable_set_impact_screening:
                self._start_stage("set_impact_scan")
                set_impact_plan = self.set_impact_plan
                set_impact_remaining = max(
                    deadline - self.clock(),
                    0.001,
                )
                if (
                    set_impact_remaining
                    < set_impact_plan.overall_deadline_seconds
                ):
                    set_impact_plan = replace(
                        set_impact_plan,
                        overall_deadline_seconds=set_impact_remaining,
                    )
                all_targets = tuple(
                    target
                    for _slot, rows in targets_by_wearer
                    for target in rows
                )
                try:
                    self.set_impact_result = self.set_impact_discovery(
                        engine_context=self.engine_context,
                        prepared_config_text=self.prepared_config_text,
                        targets=all_targets,
                        response=response,
                        stat_response_target=self.stat_response_target,
                        plan=set_impact_plan,
                        progress_callback=lambda completed, planned: (
                            self._emit(
                                GcsimOptimizerProgressStage.SET_IMPACT_SCAN,
                                started=started,
                                deadline=deadline,
                                completed=completed,
                                planned=planned,
                            )
                        ),
                        environment=self.environment,
                        is_cancelled=self._cancel_event.is_set,
                        clock=self.clock,
                    )
                finally:
                    self._finish_stage("set_impact_scan")
                impact_rows = (
                    self.set_impact_result.row_by_target_identity
                )
                targets_by_wearer = tuple(
                    (
                        slot,
                        tuple(
                            target
                            for target in rows
                            if (
                                impact_rows[
                                    _target_identity(target)
                                ].retained
                                or _target_identity(target)
                                in {
                                    _target_identity(anchor)
                                    for anchor in self.required_anchor_targets
                                }
                            )
                        ),
                    )
                    for slot, rows in targets_by_wearer
                )
                package_scores = (
                    self.set_impact_result
                    .surrogate_dps_by_target_identity
                )
                self._raise_if_interrupted(deadline)
                if any(not rows for _slot, rows in targets_by_wearer):
                    terminal = self._terminal(
                        GcsimOptimizerTerminalStatus.NO_SUCCESS,
                        "all_set_impact_removed_every_package_for_a_wearer",
                        started,
                        issues=issues,
                        catalog=catalog,
                        response=response,
                    )
                    return self._result(
                        terminal,
                        targets_by_wearer=targets_by_wearer,
                        catalog=catalog,
                        response=response,
                        wearer_pools=wearer_pools,
                        joint_coverage=joint_coverage,
                        race=race,
                    )

            self._start_stage("candidate_generation")
            pool_rows = []
            base_pool_rows = []
            for completed, (slot, targets) in enumerate(
                targets_by_wearer,
                start=1,
            ):
                wearer = self.run_input.request.source_simulation.wearers[
                    slot - 1
                ]
                base_pool = generate_gcsim_optimizer_anytime_wearer_pool(
                    self.run_input,
                    catalog=catalog,
                    wearer=wearer,
                    targets=targets,
                    profiles=response.profiles_for(wearer),
                    package_score_by_target_identity=package_scores,
                    require_target_coverage=(
                        self.enable_set_impact_screening
                    ),
                    hard_main_pruning=not self.soft_main_pruning,
                    plan=self.plan.candidates,
                    is_cancelled=lambda: (
                        self._cancel_event.is_set()
                        or self.clock() >= deadline
                    ),
                    clock=self.clock,
                )
                base_pool_rows.append(base_pool)
                refinement_pools = []
                if (
                    self.plan.coordinate_refinement_rounds
                    and not self.allow_all_database_scope
                ):
                    source_profiles = response.profiles_for(wearer)
                    source_profile_ids = {
                        item.identity_sha256 for item in source_profiles
                    }
                    # Candidate recall must not depend on whether a noisy,
                    # low-iteration response happened to classify CR/CD/EM as
                    # locally uncertain.  Preserve one deterministic search
                    # direction for every structural substat and legal main
                    # axis on every selected-set run.  The response-driven
                    # profiles remain the exploitation head; exact GCSIM is
                    # still the only selector of a coordinate winner.
                    coverage_profiles = tuple(
                        {
                            item.identity_sha256: item
                            for item in (
                                *source_profiles,
                                *build_gcsim_optimizer_stat_coverage_profiles(
                                    source_profiles
                                ),
                                *build_gcsim_optimizer_soft_main_coverage_profiles(
                                    source_profiles
                                ),
                                *build_gcsim_optimizer_uncertainty_refinement_profiles(
                                    source_profiles
                                ),
                            )
                        }.values()
                    )
                    if any(
                        item.identity_sha256 not in source_profile_ids
                        for item in coverage_profiles
                    ):
                        # Generate the coverage family in one pass.  Besides
                        # being materially faster than rebuilding the same
                        # target once per axis, the hybrid retention policy can
                        # now allocate its bound fairly across all profiles.
                        coverage_limit = min(
                            self.plan.coordinate_max_candidates_per_wearer,
                            max(
                                self.plan.candidates.max_builds_per_target,
                                128,
                            ),
                        )
                        coverage_plan = replace(
                            self.plan.candidates,
                            max_builds_per_target=coverage_limit,
                            max_builds_per_wearer=coverage_limit,
                        )
                        refinement_pools.append(
                            generate_gcsim_optimizer_anytime_wearer_pool(
                                self.run_input,
                                catalog=catalog,
                                wearer=wearer,
                                targets=targets,
                                profiles=coverage_profiles,
                                package_score_by_target_identity=package_scores,
                                require_target_coverage=False,
                                hard_main_pruning=False,
                                plan=coverage_plan,
                                is_cancelled=lambda: (
                                    self._cancel_event.is_set()
                                    or self.clock() >= deadline
                                ),
                                clock=self.clock,
                            )
                        )
                pool_rows.append(
                    _merge_anytime_wearer_pools(
                        base_pool,
                        refinement_pools,
                        limit=(
                            self.plan
                            .coordinate_max_candidates_per_wearer
                        ),
                    )
                )
                self._emit(
                    GcsimOptimizerProgressStage.CANDIDATE_GENERATION,
                    started=started,
                    deadline=deadline,
                    completed=completed,
                    planned=4,
                )
                self._raise_if_interrupted(deadline)
            wearer_pools = tuple(pool_rows)
            base_wearer_pools = tuple(base_pool_rows)
            self._finish_stage("candidate_generation")
            if any(not item.candidates for item in wearer_pools):
                terminal = self._terminal(
                    GcsimOptimizerTerminalStatus.NO_SUCCESS,
                    "anytime_selected_no_complete_wearer_build",
                    started,
                    issues=issues,
                    catalog=catalog,
                    response=response,
                    wearer_pools=wearer_pools,
                )
                return self._result(
                    terminal,
                    targets_by_wearer=targets_by_wearer,
                    catalog=catalog,
                    response=response,
                    wearer_pools=wearer_pools,
                    joint_coverage=joint_coverage,
                    race=race,
                )

            self._start_stage("joint_search")
            execution_identity = _canonical_sha256(
                {
                    "run_input_sha256": self.run_input.run_input_sha256,
                    "plan_sha256": self.plan.identity_sha256,
                    "catalog_sha256": catalog.identity_sha256,
                    "response_sha256": response.evidence_sha256,
                }
            )
            proposals, joint_coverage = (
                build_gcsim_optimizer_anytime_joint_proposals(
                    self.run_input,
                    catalog=catalog,
                    wearer_pools=base_wearer_pools,
                    marginal_required_targets=(
                        tuple(
                            target
                            for _slot, targets in targets_by_wearer
                            for target in targets
                        )
                        if self.enable_set_impact_screening
                        else ()
                    ),
                    plan=self.plan.candidates,
                    execution_identity_sha256=execution_identity,
                    is_cancelled=lambda: (
                        self._cancel_event.is_set()
                        or self.clock() >= deadline
                    ),
                    clock=self.clock,
                )
            )
            source_anchor_proposals = self._build_source_anchor_proposals(
                catalog=catalog,
                response=response,
                package_scores=package_scores,
                execution_identity_sha256=execution_identity,
                deadline=deadline,
            )
            proposals = _merge_distinct_proposals(
                source_anchor_proposals,
                proposals,
            )
            proposals = _merge_distinct_proposals(
                self.required_joint_proposals,
                proposals,
            )
            self._finish_stage("joint_search")
            self._emit(
                GcsimOptimizerProgressStage.JOINT_SEARCH,
                started=started,
                deadline=deadline,
                completed=len(proposals),
                planned=len(proposals),
            )
            self._raise_if_interrupted(deadline)
            if not proposals:
                terminal = self._terminal(
                    GcsimOptimizerTerminalStatus.NO_SUCCESS,
                    "anytime_selected_no_disjoint_team_proposal",
                    started,
                    issues=issues,
                    catalog=catalog,
                    response=response,
                    wearer_pools=wearer_pools,
                    joint_coverage=joint_coverage,
                )
                return self._result(
                    terminal,
                    targets_by_wearer=targets_by_wearer,
                    catalog=catalog,
                    response=response,
                    wearer_pools=wearer_pools,
                    joint_coverage=joint_coverage,
                    race=race,
                )
            race = self._run_race_phase(
                proposals=proposals,
                required_proposal_sha256s=tuple(
                    proposal.proposal_sha256
                    for proposal in self.required_joint_proposals
                ),
                started=started,
                deadline=deadline,
                timing_stage="race",
            )
            if (
                self.local_refinement_signature_limit
                and self.allow_all_database_scope
                and race.best_confirmed is not None
            ):
                signature_seeds = _select_refinement_signature_seeds(
                    race,
                    required_proposals=self.required_joint_proposals,
                    limit=self.local_refinement_signature_limit,
                )
                self._start_stage("local_refinement")
                try:
                    signature_families = (
                        self._build_local_refinement_families(
                        seed_proposals=signature_seeds,
                        catalog=catalog,
                        response=response,
                        package_scores=package_scores,
                        execution_identity_sha256=execution_identity,
                        deadline=deadline,
                        )
                    )
                finally:
                    self._finish_stage("local_refinement")
                self._raise_if_interrupted(deadline)
                if signature_families:
                    family_signatures = tuple(
                        item.package_signature
                        for item in signature_families
                    )
                    local_proposals = tuple(
                        proposal
                        for family in signature_families
                        for proposal in family.joint_proposals
                    )
                else:
                    family_signatures = ()
                    local_proposals = ()
                if local_proposals:
                    confirmed_proposals = tuple(
                        item.proposal for item in race.confirmed_evaluations
                    )
                    signature_leaders = (
                        _best_confirmed_proposals_by_signature(
                            race.confirmed_evaluations,
                            signatures=family_signatures,
                        )
                    )
                    mandatory_challengers = (
                        _select_required_signature_challengers(
                            local_proposals,
                            incumbents=signature_leaders,
                            signatures=family_signatures,
                        )
                    )
                    active_local_signatures = tuple(
                        build_gcsim_optimizer_account_package_signature(
                            item.compiled_candidate.targets
                        )
                        for item in mandatory_challengers
                    )
                    signature_required = _merge_distinct_proposals(
                        signature_leaders,
                        mandatory_challengers,
                    )
                    required_proposals = _merge_distinct_proposals(
                        self.required_joint_proposals,
                        signature_required,
                    )
                    required_proposal_sha256s = tuple(
                        item.proposal_sha256
                        for item in required_proposals
                    )
                    optional_proposals = _merge_distinct_proposals(
                        confirmed_proposals,
                        local_proposals,
                    )
                    round_proposals = _merge_distinct_proposals(
                        required_proposals,
                        optional_proposals,
                    )
                    self.preliminary_race_results.append(race)
                    race = self._run_race_phase(
                        proposals=round_proposals,
                        required_proposal_sha256s=required_proposal_sha256s,
                        started=started,
                        deadline=deadline,
                        timing_stage="local_refinement_race",
                        challenger_signature_count=len(
                            active_local_signatures
                        ),
                    )
                    _require_refinement_proposals_confirmed(
                        race,
                        required_proposal_sha256s,
                        phase="post-race local refinement",
                    )
                    race = self._run_signature_consolidation_phase(
                        exploration_race=race,
                        incumbents=signature_leaders,
                        signatures=active_local_signatures,
                        started=started,
                        deadline=deadline,
                        timing_stage="local_refinement_consolidation_race",
                    )
                if (
                    signature_families
                    and race.status
                    not in {
                        GcsimOptimizerAnytimeRaceStatus.CANCELLED,
                        GcsimOptimizerAnytimeRaceStatus.DEADLINE,
                    }
                ):
                    for round_index in range(
                        self.plan.coordinate_refinement_rounds
                    ):
                        self._raise_if_interrupted(deadline)
                        signature_leaders = (
                            _best_confirmed_proposals_by_signature(
                                race.confirmed_evaluations,
                                signatures=family_signatures,
                            )
                        )
                        if len(signature_leaders) != len(
                            family_signatures
                        ):
                            raise GcsimOptimizerAnytimeSelectedError(
                                "all-set refinement lost a confirmed package "
                                "signature before coordinate search"
                            )
                        coordinate_seeds_by_signature = {
                            signature: tuple(
                                evaluation.proposal
                                for evaluation in race.confirmed_evaluations
                                if build_gcsim_optimizer_account_package_signature(
                                    evaluation.proposal.compiled_candidate.targets
                                )
                                == signature
                            )[: self.plan.coordinate_seed_count]
                            for signature in family_signatures
                        }
                        if any(
                            not rows
                            for rows in coordinate_seeds_by_signature.values()
                        ):
                            raise GcsimOptimizerAnytimeSelectedError(
                                "all-set coordinate search lacks a confirmed "
                                "seed for a package signature"
                            )
                        coordinate_rows = []
                        for family in signature_families:
                            self._raise_if_interrupted(deadline)
                            coordinate_seeds = (
                                coordinate_seeds_by_signature[
                                    family.package_signature
                                ]
                            )
                            coordinate_identity = _canonical_sha256(
                                {
                                    "kind": (
                                        "all_set_signature_coordinate_"
                                        "refinement"
                                    ),
                                    "round_index": round_index,
                                    "execution_identity_sha256": (
                                        execution_identity
                                    ),
                                    "package_signature": list(
                                        family.package_signature
                                    ),
                                    "seed_proposal_sha256s": [
                                        item.proposal_sha256
                                        for item in coordinate_seeds
                                    ],
                                }
                            )
                            rows = (
                                build_gcsim_optimizer_coordinate_refinement_proposals(
                                    self.run_input,
                                    catalog=catalog,
                                    seed_proposals=coordinate_seeds,
                                    wearer_pools=family.wearer_pools,
                                    execution_identity_sha256=(
                                        coordinate_identity
                                    ),
                                    max_candidates_per_wearer=(
                                        self.plan
                                        .coordinate_max_candidates_per_wearer
                                    ),
                                    conflict_beam_width=(
                                        self.plan
                                        .coordinate_conflict_beam_width
                                    ),
                                    is_cancelled=lambda: (
                                        self._cancel_event.is_set()
                                        or self.clock() >= deadline
                                    ),
                                )
                            )
                            coordinate_rows.append(
                                (family.package_signature, rows)
                            )
                        self._raise_if_interrupted(deadline)
                        coordinate_proposals = (
                            _retain_signature_coordinate_frontiers(
                                coordinate_rows,
                                limit=(
                                    self.plan
                                    .coordinate_screen_proposal_limit
                                ),
                            )
                        )
                        if not coordinate_proposals:
                            break
                        mandatory_challengers = (
                            _select_required_signature_challengers(
                                coordinate_proposals,
                                incumbents=signature_leaders,
                                signatures=family_signatures,
                            )
                        )
                        active_coordinate_signatures = tuple(
                            build_gcsim_optimizer_account_package_signature(
                                item.compiled_candidate.targets
                            )
                            for item in mandatory_challengers
                        )
                        signature_required = _merge_distinct_proposals(
                            signature_leaders,
                            mandatory_challengers,
                        )
                        required_proposals = _merge_distinct_proposals(
                            self.required_joint_proposals,
                            signature_required,
                        )
                        required_proposal_sha256s = tuple(
                            item.proposal_sha256
                            for item in required_proposals
                        )
                        confirmed_proposals = tuple(
                            item.proposal
                            for item in race.confirmed_evaluations
                        )
                        optional_proposals = _merge_distinct_proposals(
                            confirmed_proposals,
                            coordinate_proposals,
                        )
                        round_proposals = _merge_distinct_proposals(
                            required_proposals,
                            optional_proposals,
                        )
                        self.preliminary_race_results.append(race)
                        race = self._run_race_phase(
                            proposals=round_proposals,
                            required_proposal_sha256s=(
                                required_proposal_sha256s
                            ),
                            started=started,
                            deadline=deadline,
                            timing_stage=(
                                "all_set_coordinate_race_"
                                f"{round_index + 1}"
                            ),
                            challenger_signature_count=(
                                len(active_coordinate_signatures)
                            ),
                        )
                        _require_refinement_proposals_confirmed(
                            race,
                            required_proposal_sha256s,
                            phase=(
                                "all-set coordinate refinement round "
                                f"{round_index + 1}"
                            ),
                        )
                        race = self._run_signature_consolidation_phase(
                            exploration_race=race,
                            incumbents=signature_leaders,
                            signatures=active_coordinate_signatures,
                            started=started,
                            deadline=deadline,
                            timing_stage=(
                                "all_set_coordinate_consolidation_race_"
                                f"{round_index + 1}"
                            ),
                        )
                        if race.status in {
                            GcsimOptimizerAnytimeRaceStatus.CANCELLED,
                            GcsimOptimizerAnytimeRaceStatus.DEADLINE,
                        }:
                            break
            if (
                self.plan.coordinate_refinement_rounds
                and not self.allow_all_database_scope
                and race.best_confirmed is not None
                and any(
                    len(pool.candidates) > len(base_pool.candidates)
                    for pool, base_pool in zip(
                        wearer_pools,
                        base_wearer_pools,
                        strict=True,
                    )
                )
            ):
                for round_index in range(
                    self.plan.coordinate_refinement_rounds
                ):
                    self._raise_if_interrupted(deadline)
                    seeds = tuple(
                        item.proposal
                        for item in race.confirmed_evaluations[
                            :self.plan.coordinate_seed_count
                        ]
                    )
                    if not seeds:
                        break
                    coordinate_identity = _canonical_sha256(
                        {
                            "kind": "exact_gcsim_coordinate_refinement",
                            "round_index": round_index,
                            "execution_identity_sha256": execution_identity,
                            "seed_proposal_sha256s": [
                                item.proposal_sha256 for item in seeds
                            ],
                        }
                    )
                    coordinate_proposals = (
                        build_gcsim_optimizer_coordinate_refinement_proposals(
                            self.run_input,
                            catalog=catalog,
                            seed_proposals=seeds,
                            wearer_pools=wearer_pools,
                            execution_identity_sha256=coordinate_identity,
                            max_candidates_per_wearer=(
                                self.plan
                                .coordinate_max_candidates_per_wearer
                            ),
                            conflict_beam_width=(
                                self.plan.coordinate_conflict_beam_width
                            ),
                            is_cancelled=lambda: (
                                self._cancel_event.is_set()
                                or self.clock() >= deadline
                            ),
                        )
                    )
                    if not coordinate_proposals:
                        break
                    coordinate_proposals = (
                        _retain_coordinate_refinement_frontier(
                            coordinate_proposals,
                            limit=(
                                self.plan.coordinate_screen_proposal_limit
                            ),
                        )
                    )
                    anchor = race.best_confirmed.proposal
                    round_proposals = _merge_distinct_proposals(
                        (anchor,),
                        coordinate_proposals,
                    )
                    self.preliminary_race_results.append(race)
                    race = self._run_race_phase(
                        proposals=round_proposals,
                        required_proposal_sha256s=(
                            anchor.proposal_sha256,
                        ),
                        started=started,
                        deadline=deadline,
                        timing_stage=(
                            f"coordinate_race_{round_index + 1}"
                        ),
                    )
                    if race.best_confirmed is None:
                        if race.status in {
                            GcsimOptimizerAnytimeRaceStatus.CANCELLED,
                            GcsimOptimizerAnytimeRaceStatus.DEADLINE,
                        }:
                            break
                        raise GcsimOptimizerAnytimeSelectedError(
                            "coordinate refinement lost its required leader"
                        )
            interrupted_race_status = (
                race.status
                if race.status in {
                    GcsimOptimizerAnytimeRaceStatus.CANCELLED,
                    GcsimOptimizerAnytimeRaceStatus.DEADLINE,
                }
                else None
            )
            if interrupted_race_status is not None:
                race = self._preserve_last_confirmed_race(race)
            terminal = self._terminal_from_race(
                race,
                started=started,
                issues=issues,
                catalog=catalog,
                response=response,
                wearer_pools=wearer_pools,
                joint_coverage=joint_coverage,
            )
            if interrupted_race_status is not None:
                terminal = replace(
                    terminal,
                    status=(
                        GcsimOptimizerTerminalStatus.CANCELLED
                        if interrupted_race_status
                        is GcsimOptimizerAnytimeRaceStatus.CANCELLED
                        else GcsimOptimizerTerminalStatus.DEADLINE
                    ),
                    stop_reason=(
                        f"anytime_race_{interrupted_race_status.value}"
                    ),
                )
            leader = (
                None
                if terminal.best_found is None
                else GcsimOptimizerLeaderSnapshot(
                    candidate_identity_sha256=(
                        terminal.best_found.candidate_identity_sha256
                    ),
                    estimate=terminal.best_found.estimate,
                    scope=GcsimOptimizerProgressLeaderScope.RUN,
                    quality=GcsimOptimizerProgressLeaderQuality.FINAL,
                )
            )
            self._emit(
                GcsimOptimizerProgressStage.COMPLETED,
                started=started,
                deadline=deadline,
                completed=len(race.confirmed_evaluations),
                planned=len(race.confirmed_evaluations),
                cache_hits=sum(count for _tier, count in race.cache_hits_by_tier),
                current_iterations=(
                    None if leader is None else leader.estimate.iterations
                ),
                leader=leader,
            )
            return self._result(
                terminal,
                targets_by_wearer=targets_by_wearer,
                catalog=catalog,
                response=response,
                wearer_pools=wearer_pools,
                joint_coverage=joint_coverage,
                race=race,
            )
        except _AnytimeSelectedInterrupted as exc:
            race = self._preserve_last_confirmed_race(race)
            terminal = self._terminal_after_interruption(
                (
                    GcsimOptimizerTerminalStatus.CANCELLED
                    if exc.cancelled
                    else GcsimOptimizerTerminalStatus.DEADLINE
                ),
                exc.reason,
                started,
                issues=issues,
                catalog=catalog,
                response=response,
                wearer_pools=wearer_pools,
                joint_coverage=joint_coverage,
                race=race,
            )
            return self._result(
                terminal,
                targets_by_wearer=targets_by_wearer,
                catalog=catalog,
                response=response,
                wearer_pools=wearer_pools,
                joint_coverage=joint_coverage,
                race=race,
            )

        except Exception as exc:
            if self._cancel_event.is_set():
                race = self._preserve_last_confirmed_race(race)
                terminal = self._terminal_after_interruption(
                    GcsimOptimizerTerminalStatus.CANCELLED,
                    "anytime_selected_cancelled",
                    started,
                    issues=issues,
                    catalog=catalog,
                    response=response,
                    wearer_pools=wearer_pools,
                    joint_coverage=joint_coverage,
                    race=race,
                )
                return self._result(
                    terminal,
                    targets_by_wearer=targets_by_wearer,
                    catalog=catalog,
                    response=response,
                    wearer_pools=wearer_pools,
                    joint_coverage=joint_coverage,
                    race=race,
                )
            terminal = self._terminal(
                GcsimOptimizerTerminalStatus.FAILED,
                "anytime_selected_orchestration_failed",
                started,
                issues=issues,
                catalog=catalog,
                response=response,
                wearer_pools=wearer_pools,
                joint_coverage=joint_coverage,
                race=race,
                error=f"{type(exc).__name__}: {exc}",
            )
            return self._result(
                terminal,
                targets_by_wearer=targets_by_wearer,
                catalog=catalog,
                response=response,
                wearer_pools=wearer_pools,
                joint_coverage=joint_coverage,
                race=race,
            )

    def _run_race_phase(
        self,
        *,
        proposals: Sequence[GcsimOptimizerJointProposal],
        required_proposal_sha256s: Sequence[str],
        started: float,
        deadline: float,
        timing_stage: str,
        challenger_signature_count: int = 0,
    ) -> GcsimOptimizerAnytimeRaceResult:
        race_plan = self.plan.race
        if (
            isinstance(challenger_signature_count, bool)
            or not isinstance(challenger_signature_count, int)
            or challenger_signature_count < 0
        ):
            raise GcsimOptimizerAnytimeSelectedError(
                "challenger signature count must be a non-negative integer"
            )
        refinement_capacity_floor = (
            len(tuple(required_proposal_sha256s))
            + challenger_signature_count
        )
        tier_rows = []
        for tier_index, tier in enumerate(race_plan.tiers):
            capacity = max(
                tier.max_candidates,
                refinement_capacity_floor,
                len(proposals) if tier_index == 0 else 0,
            )
            tier_rows.append(
                tier
                if capacity == tier.max_candidates
                else replace(tier, max_candidates=capacity)
            )
        if tuple(tier_rows) != race_plan.tiers:
            race_plan = replace(
                race_plan,
                tiers=tuple(tier_rows),
            )
        remaining = max(deadline - self.clock(), 0.001)
        if remaining < race_plan.overall_deadline_seconds:
            race_plan = replace(
                race_plan,
                overall_deadline_seconds=remaining,
            )
        race_session = GcsimOptimizerAnytimeRaceSession(
            self.run_input,
            engine_context=self.engine_context,
            proposals=proposals,
            required_proposal_sha256s=required_proposal_sha256s,
            plan=race_plan,
            progress_callback=lambda tier, completed, planned, leader: (
                self._emit_race_progress(
                    tier,
                    completed=completed,
                    planned=planned,
                    leader=leader,
                    started=started,
                    deadline=deadline,
                )
            ),
            cache_store=self.cache_store,
            enable_cache=self.enable_cache,
            session_factory=self.session_factory,
            environment=self.environment,
            stat_response_target=self.stat_response_target,
            clock=self.clock,
        )
        self._set_active(race_session)
        self._start_stage(timing_stage)
        try:
            return race_session.run()
        finally:
            self._clear_active(race_session)
            self._finish_stage(timing_stage)

    def _run_signature_consolidation_phase(
        self,
        *,
        exploration_race: GcsimOptimizerAnytimeRaceResult,
        incumbents: Sequence[GcsimOptimizerJointProposal],
        signatures: Sequence[tuple[str, ...]],
        started: float,
        deadline: float,
        timing_stage: str,
    ) -> GcsimOptimizerAnytimeRaceResult:
        """Rerace incumbent and exact n=200 challenger per signature at n=1000."""

        signature_rows = tuple(signatures)
        if not signature_rows or exploration_race.status in {
            GcsimOptimizerAnytimeRaceStatus.CANCELLED,
            GcsimOptimizerAnytimeRaceStatus.DEADLINE,
        }:
            return exploration_race
        incumbent_signatures = tuple(
            build_gcsim_optimizer_account_package_signature(
                item.compiled_candidate.targets
            )
            for item in incumbents
        )
        current_incumbents = _best_confirmed_proposals_by_signature(
            exploration_race.confirmed_evaluations,
            signatures=incumbent_signatures,
        )
        if len(current_incumbents) != len(incumbent_signatures):
            raise GcsimOptimizerAnytimeSelectedError(
                "refinement exploration lost a confirmed signature leader"
            )
        challengers = _best_validated_challengers_by_signature(
            exploration_race,
            incumbents=current_incumbents,
            signatures=signature_rows,
        )
        challenger_signatures = {
            build_gcsim_optimizer_account_package_signature(
                item.compiled_candidate.targets
            )
            for item in challengers
        }
        if challenger_signatures != set(signature_rows):
            raise GcsimOptimizerAnytimeSelectedError(
                "refinement race did not validate one physical challenger "
                "per package signature"
            )
        signature_required = _merge_distinct_proposals(
            current_incumbents,
            challengers,
        )
        required_proposals = _merge_distinct_proposals(
            self.required_joint_proposals,
            signature_required,
        )
        required_proposal_sha256s = tuple(
            item.proposal_sha256 for item in required_proposals
        )
        optional_proposals = tuple(
            item.proposal
            for item in exploration_race.confirmed_evaluations
        )
        round_proposals = _merge_distinct_proposals(
            required_proposals,
            optional_proposals,
        )
        self.preliminary_race_results.append(exploration_race)
        consolidated = self._run_race_phase(
            proposals=round_proposals,
            required_proposal_sha256s=required_proposal_sha256s,
            started=started,
            deadline=deadline,
            timing_stage=timing_stage,
            # Every incumbent/challenger pair is already required here.  The
            # exploration race reserved the extra per-signature slot; this
            # consolidation only needs to carry those exact pairs to n=1000.
            challenger_signature_count=0,
        )
        _require_refinement_proposals_confirmed(
            consolidated,
            required_proposal_sha256s,
            phase=timing_stage,
        )
        return consolidated

    def _build_local_refinement_families(
        self,
        *,
        seed_proposals: Sequence[GcsimOptimizerJointProposal],
        catalog: GcsimOptimizerDenseArtifactCatalog,
        response: GcsimOptimizerAnytimeResponseResult,
        package_scores: Mapping[str, float],
        execution_identity_sha256: str,
        deadline: float,
    ) -> tuple[_GcsimOptimizerAllSetSignatureRefinement, ...]:
        """Build a selected-mode-like physical pool per package signature."""

        target_families: list[tuple[GcsimOptimizerWearerTarget, ...]] = []
        seen_signatures: set[tuple[str, ...]] = set()

        def retain(targets: Sequence[GcsimOptimizerWearerTarget]) -> None:
            rows = tuple(targets)
            if len(rows) != 4:
                return
            signature = build_gcsim_optimizer_account_package_signature(rows)
            if signature in seen_signatures:
                return
            seen_signatures.add(signature)
            target_families.append(rows)

        # The caller supplies exact confirmed evaluations in deterministic DPS
        # order.  Do not re-rank them by the pre-race surrogate: that was the
        # failure mode this post-race refinement is intended to remove.
        for proposal in seed_proposals:
            retain(proposal.compiled_candidate.targets)
        if not target_families:
            return ()

        coverage_limit = min(
            self.plan.coordinate_max_candidates_per_wearer,
            max(
                self.plan.candidates.max_builds_per_target,
                128,
            ),
        )
        coverage_plan = replace(
            self.plan.candidates,
            max_builds_per_target=coverage_limit,
            max_builds_per_wearer=coverage_limit,
        )
        local_plan = replace(
            self.plan.candidates,
            max_builds_per_target=(
                self.plan.coordinate_max_candidates_per_wearer
            ),
            max_builds_per_wearer=(
                self.plan.coordinate_max_candidates_per_wearer
            ),
            max_joint_proposals=min(
                self.local_refinement_proposals_per_signature,
                self.plan.candidates.max_joint_proposals,
            ),
            local_search_seed_count=min(
                self.plan.candidates.local_search_seed_count,
                self.local_refinement_proposals_per_signature,
            ),
        )
        pool_cache: dict[
            tuple[int, str], GcsimOptimizerAnytimeWearerPool
        ] = {}
        families: list[_GcsimOptimizerAllSetSignatureRefinement] = []
        completed_signatures = 0
        for targets in target_families:
            if self._cancel_event.is_set() or self.clock() >= deadline:
                break
            pools = []
            for target in targets:
                key = (target.wearer.team_slot, target.package.identity_sha256)
                pool = pool_cache.get(key)
                if pool is None:
                    source_profiles = response.profiles_for(target.wearer)
                    base_pool = generate_gcsim_optimizer_anytime_wearer_pool(
                        self.run_input,
                        catalog=catalog,
                        wearer=target.wearer,
                        targets=(target,),
                        profiles=source_profiles,
                        package_score_by_target_identity=package_scores,
                        require_target_coverage=False,
                        hard_main_pruning=not self.soft_main_pruning,
                        plan=self.plan.candidates,
                        is_cancelled=lambda: (
                            self._cancel_event.is_set()
                            or self.clock() >= deadline
                        ),
                        clock=self.clock,
                    )
                    coverage_profiles = tuple(
                        {
                            item.identity_sha256: item
                            for item in (
                                *source_profiles,
                                *build_gcsim_optimizer_stat_coverage_profiles(
                                    source_profiles
                                ),
                                *build_gcsim_optimizer_soft_main_coverage_profiles(
                                    source_profiles
                                ),
                                *build_gcsim_optimizer_uncertainty_refinement_profiles(
                                    source_profiles
                                ),
                            )
                        }.values()
                    )
                    coverage_pool = (
                        generate_gcsim_optimizer_anytime_wearer_pool(
                            self.run_input,
                            catalog=catalog,
                            wearer=target.wearer,
                            targets=(target,),
                            profiles=coverage_profiles,
                            package_score_by_target_identity=package_scores,
                            require_target_coverage=False,
                            hard_main_pruning=False,
                            plan=coverage_plan,
                            is_cancelled=lambda: (
                                self._cancel_event.is_set()
                                or self.clock() >= deadline
                            ),
                            clock=self.clock,
                        )
                    )
                    pool = _merge_anytime_wearer_pools(
                        base_pool,
                        (coverage_pool,),
                        limit=(
                            self.plan.coordinate_max_candidates_per_wearer
                        ),
                    )
                    pool_cache[key] = pool
                    self.local_refinement_candidate_count += len(
                        pool.candidates
                    )
                pools.append(pool)
            if any(not pool.candidates for pool in pools):
                continue
            signature = build_gcsim_optimizer_account_package_signature(
                targets
            )
            local_identity = _canonical_sha256(
                {
                    "kind": "all_set_local_physical_refinement",
                    "execution_identity_sha256": execution_identity_sha256,
                    "package_signature": list(signature),
                }
            )
            local_rows, _coverage = (
                build_gcsim_optimizer_anytime_joint_proposals(
                    self.run_input,
                    catalog=catalog,
                    wearer_pools=tuple(pools),
                    plan=local_plan,
                    execution_identity_sha256=local_identity,
                    is_cancelled=lambda: (
                        self._cancel_event.is_set()
                        or self.clock() >= deadline
                    ),
                    clock=self.clock,
                )
            )
            families.append(
                _GcsimOptimizerAllSetSignatureRefinement(
                    package_signature=signature,
                    wearer_pools=tuple(pools),
                    joint_proposals=tuple(local_rows),
                )
            )
            completed_signatures += 1
        self.local_refinement_signature_count = completed_signatures
        self.local_refinement_proposal_count = sum(
            len(item.joint_proposals) for item in families
        )
        return tuple(families)

    def _build_source_anchor_proposals(
        self,
        *,
        catalog: GcsimOptimizerDenseArtifactCatalog,
        response: GcsimOptimizerAnytimeResponseResult,
        package_scores: Mapping[str, float],
        execution_identity_sha256: str,
        deadline: float,
    ) -> tuple[GcsimOptimizerJointProposal, ...]:
        """Build one ordinary-profile control for the source package family."""

        if not self.required_anchor_targets:
            return ()
        anchor_plan = replace(
            self.plan.candidates,
            max_builds_per_wearer=max(
                self.plan.candidates.max_builds_per_wearer,
                self.plan.candidates.max_builds_per_target,
            ),
            max_joint_proposals=1,
            local_search_seed_count=1,
        )
        pools = []
        for target in self.required_anchor_targets:
            if self._cancel_event.is_set() or self.clock() >= deadline:
                return ()
            pools.append(
                generate_gcsim_optimizer_anytime_wearer_pool(
                    self.run_input,
                    catalog=catalog,
                    wearer=target.wearer,
                    targets=(target,),
                    profiles=response.profiles_for(target.wearer),
                    package_score_by_target_identity=package_scores,
                    require_target_coverage=False,
                    hard_main_pruning=not self.soft_main_pruning,
                    plan=anchor_plan,
                    is_cancelled=lambda: (
                        self._cancel_event.is_set()
                        or self.clock() >= deadline
                    ),
                    clock=self.clock,
                )
            )
        if any(not pool.candidates for pool in pools):
            return ()
        anchor_identity = _canonical_sha256(
            {
                "kind": "required_source_package_control",
                "execution_identity_sha256": execution_identity_sha256,
                "package_signature": list(
                    build_gcsim_optimizer_account_package_signature(
                        self.required_anchor_targets
                    )
                ),
            }
        )
        proposals, _coverage = build_gcsim_optimizer_anytime_joint_proposals(
            self.run_input,
            catalog=catalog,
            wearer_pools=tuple(pools),
            plan=anchor_plan,
            execution_identity_sha256=anchor_identity,
            is_cancelled=lambda: (
                self._cancel_event.is_set() or self.clock() >= deadline
            ),
            clock=self.clock,
        )
        return tuple(proposals[:1])

    def _preflight(
        self,
        started: float,
    ) -> GcsimOptimizerTerminalResult | None:
        request = self.run_input.request
        if (
            self.run_input.engine_binding_sha256
            != self.engine_context.binding_sha256
            or self.run_input.catalog_fingerprint
            != self.engine_context.catalog.source_fingerprint
        ):
            return self._terminal(
                GcsimOptimizerTerminalStatus.NOT_READY,
                "anytime_selected_engine_binding_mismatch",
                started,
            )
        if request.operation is not GcsimOptimizerOperation.ACCOUNT_ARTIFACTS:
            return self._terminal(
                GcsimOptimizerTerminalStatus.NOT_READY,
                "anytime_selected_requires_account_operation",
                started,
            )
        allowed_scopes = {GcsimOptimizerAccountScope.SELECTED_SET_POOLS}
        if self.allow_all_database_scope:
            allowed_scopes.add(GcsimOptimizerAccountScope.ALL_DATABASE_SETS)
        if request.account_scope not in allowed_scopes:
            return self._terminal(
                GcsimOptimizerTerminalStatus.NOT_READY,
                "anytime_selected_requires_selected_set_scope",
                started,
            )
        if (
            request.work_plan.plan_id != self.boundary_plan_id
            or request.work_plan.plan_version != self.boundary_plan_version
            or _canonical_sha256(
                _thaw_json(request.work_plan.parameters)
            )
            != _canonical_sha256(self.boundary_plan_parameters)
        ):
            return self._terminal(
                GcsimOptimizerTerminalStatus.NOT_READY,
                "anytime_selected_work_plan_mismatch",
                started,
            )
        return None

    def _build_targets(
        self,
    ) -> tuple[
        tuple[tuple[int, tuple[GcsimOptimizerWearerTarget, ...]], ...],
        tuple[GcsimOptimizerIssue, ...],
    ]:
        result = []
        issues = []
        for pool in self.target_pools:
            targets = []
            for set_ref in pool.allowed_sets:
                capability = self.run_input.set_capability(
                    set_ref.gcsim_set_key
                )
                if (
                    capability is not None
                    and capability.optimizer_four_piece_ready
                ):
                    target = GcsimOptimizerWearerTarget(
                        pool.wearer,
                        GcsimFourPieceTargetPackage(set_ref),
                    )
                    if (
                        not self.allow_all_database_scope
                        or gcsim_optimizer_account_target_is_physically_feasible(
                            self.run_input,
                            target,
                        )
                    ):
                        targets.append(target)
            if self.run_input.request.include_2p2p:
                refs = pool.allowed_sets
                for left_index, left in enumerate(refs):
                    left_capability = self.run_input.set_capability(
                        left.gcsim_set_key
                    )
                    if (
                        left_capability is None
                        or not left_capability.two_piece_modeled
                    ):
                        continue
                    for right in refs[left_index + 1 :]:
                        right_capability = self.run_input.set_capability(
                            right.gcsim_set_key
                        )
                        if (
                            right_capability is None
                            or not right_capability.two_piece_modeled
                        ):
                            continue
                        pair_package = GcsimTwoPlusTwoTargetPackage(
                            left,
                            right,
                        )
                        if (
                            left.gcsim_set_key.casefold()
                            == right.gcsim_set_key.casefold()
                        ):
                            issues.append(
                                GcsimOptimizerIssue(
                                    code="duplicate_pair_set_key",
                                    scope=GcsimOptimizerIssueScope.PACKAGE,
                                    message=(
                                        "Two concrete set UIDs map to the "
                                        "same GCSIM set key and cannot form "
                                        "a meaningful 2p+2p package."
                                    ),
                                    wearer=pool.wearer,
                                    package_identity_sha256=(
                                        pair_package.identity_sha256
                                    ),
                                )
                            )
                            continue
                        target = GcsimOptimizerWearerTarget(
                            pool.wearer,
                            pair_package,
                        )
                        if (
                            not self.allow_all_database_scope
                            or gcsim_optimizer_account_target_is_physically_feasible(
                                self.run_input,
                                target,
                            )
                        ):
                            targets.append(target)
            targets = tuple(
                sorted(
                    targets,
                    key=lambda item: _canonical_sha256(item.to_dict()),
                )
            )
            result.append((pool.wearer.team_slot, targets))
        return tuple(result), tuple(issues)

    def _emit_race_progress(
        self,
        tier: str,
        *,
        completed: int,
        planned: int,
        leader: GcsimOptimizerAnytimeRaceEvaluation | None,
        started: float,
        deadline: float,
    ) -> None:
        stage, current_iterations = {
            "screen_8": (GcsimOptimizerProgressStage.SCREENING, 8),
            "refine_32": (GcsimOptimizerProgressStage.REFINEMENT, 32),
            "validate_200": (
                GcsimOptimizerProgressStage.FINAL_VALIDATION,
                200,
            ),
            "rerace_1000": (GcsimOptimizerProgressStage.RERACE, 1000),
        }[tier]
        snapshot = None
        if (
            leader is not None
            and leader.dps_mean is not None
        ):
            snapshot = GcsimOptimizerLeaderSnapshot(
                candidate_identity_sha256=(
                    leader.proposal.compiled_candidate.candidate_identity_sha256
                ),
                estimate=GcsimOptimizerDpsEstimate(
                    dps_mean=leader.dps_mean,
                    dps_se=leader.dps_se,
                    iterations=leader.iterations,
                ),
                scope=GcsimOptimizerProgressLeaderScope.STAGE,
                quality=(
                    GcsimOptimizerProgressLeaderQuality.VERIFIED
                    if leader.iterations >= 200
                    else GcsimOptimizerProgressLeaderQuality.PROVISIONAL
                ),
            )
        self._emit(
            stage,
            started=started,
            deadline=deadline,
            completed=completed,
            planned=planned,
            cache_hits=(
                int(leader.result.cache_hit)
                if leader is not None
                else 0
            ),
            current_iterations=current_iterations,
            leader=snapshot,
        )

    def _preserve_last_confirmed_race(
        self,
        current: GcsimOptimizerAnytimeRaceResult | None,
    ) -> GcsimOptimizerAnytimeRaceResult | None:
        """Keep an empty interrupted race as trace, not as the final result."""

        if current is None or current.confirmed_evaluations:
            return current
        confirmed = _last_confirmed_race(
            self.preliminary_race_results,
            current=current,
        )
        if confirmed is None:
            return current
        if all(
            item.evidence_sha256 != current.evidence_sha256
            for item in self.preliminary_race_results
        ):
            self.preliminary_race_results.append(current)
        return confirmed

    def _terminal_after_interruption(
        self,
        status: GcsimOptimizerTerminalStatus,
        stop_reason: str,
        started: float,
        *,
        issues: Sequence[GcsimOptimizerIssue],
        catalog,
        response,
        wearer_pools,
        joint_coverage,
        race,
    ) -> GcsimOptimizerTerminalResult:
        """Retain already-confirmed exact evidence on cancel/deadline."""

        if (
            response is not None
            and race is not None
            and any(
                phase.confirmed_evaluations
                for phase in (
                    *tuple(self.preliminary_race_results),
                    race,
                )
            )
        ):
            preserved = self._terminal_from_race(
                race,
                started=started,
                issues=issues,
                catalog=catalog,
                response=response,
                wearer_pools=wearer_pools,
                joint_coverage=joint_coverage,
            )
            return replace(
                preserved,
                status=status,
                stop_reason=stop_reason,
            )
        return self._terminal(
            status,
            stop_reason,
            started,
            issues=issues,
            catalog=catalog,
            response=response,
            wearer_pools=wearer_pools,
            joint_coverage=joint_coverage,
            race=race,
        )

    def _terminal_from_race(
        self,
        race: GcsimOptimizerAnytimeRaceResult,
        *,
        started: float,
        issues: Sequence[GcsimOptimizerIssue],
        catalog,
        response,
        wearer_pools,
        joint_coverage,
    ) -> GcsimOptimizerTerminalResult:
        confirmed = _retain_best_confirmed_evaluations_by_signature(
            tuple(
                evaluation
                for phase in (
                    *tuple(self.preliminary_race_results),
                    race,
                )
                for evaluation in phase.confirmed_evaluations
            )
        )
        candidates = tuple(
            self._candidate_result(item, response=response)
            for item in confirmed
        )
        candidates = _retain_best_account_package_candidates(candidates)
        top_n = build_gcsim_optimizer_top_n(
            candidates,
            operation=GcsimOptimizerOperation.ACCOUNT_ARTIFACTS,
            top_n=self.plan.top_n,
            confidence_sigma=self.plan.race.confidence_sigma,
        )
        status = {
            GcsimOptimizerAnytimeRaceStatus.COMPLETED: (
                GcsimOptimizerTerminalStatus.BEST_FOUND
            ),
            GcsimOptimizerAnytimeRaceStatus.COMPLETED_WITH_ERRORS: (
                GcsimOptimizerTerminalStatus.BEST_FOUND
            ),
            GcsimOptimizerAnytimeRaceStatus.NO_SUCCESS: (
                GcsimOptimizerTerminalStatus.NO_SUCCESS
            ),
            GcsimOptimizerAnytimeRaceStatus.CANCELLED: (
                GcsimOptimizerTerminalStatus.CANCELLED
            ),
            GcsimOptimizerAnytimeRaceStatus.DEADLINE: (
                GcsimOptimizerTerminalStatus.DEADLINE
            ),
        }[race.status]
        if (
            status is GcsimOptimizerTerminalStatus.BEST_FOUND
            and not top_n.entries
        ):
            status = GcsimOptimizerTerminalStatus.NO_SUCCESS
        elif (
            status is GcsimOptimizerTerminalStatus.NO_SUCCESS
            and top_n.entries
        ):
            # A bounded refinement race may fail after an earlier phase was
            # already confirmed.  That phase remains valid exact evidence and
            # must not disappear from the product result.
            status = GcsimOptimizerTerminalStatus.BEST_FOUND
        return self._terminal(
            status,
            f"anytime_race_{race.status.value}",
            started,
            top_n=top_n,
            issues=issues,
            catalog=catalog,
            response=response,
            wearer_pools=wearer_pools,
            joint_coverage=joint_coverage,
            race=race,
        )

    def _candidate_result(
        self,
        evaluation: GcsimOptimizerAnytimeRaceEvaluation,
        *,
        response: GcsimOptimizerAnytimeResponseResult,
    ) -> GcsimOptimizerCandidateResult:
        proposal = evaluation.proposal
        compiled = proposal.compiled_candidate
        assert evaluation.dps_mean is not None
        return GcsimOptimizerCandidateResult(
            request_sha256=self.run_input.request.request_sha256,
            candidate_identity_sha256=compiled.candidate_identity_sha256,
            evaluation=GcsimOptimizerEvaluationIdentity(
                request_sha256=self.run_input.request.request_sha256,
                source_simulation_sha256=(
                    self.run_input.request.source_simulation.identity_sha256
                ),
                work_plan_sha256=(
                    self.run_input.request.work_plan.identity_sha256
                ),
                engine_binding_sha256=self.engine_context.binding_sha256,
                # Exact actually evaluated config after iteration/worker
                # replacement, not the pre-tier compiled shell.
                compiled_config_sha256=(
                    evaluation.result.source_config_sha256
                ),
                execution_identity_sha256=(
                    evaluation.result.request_identity_sha256
                ),
            ),
            estimate=GcsimOptimizerDpsEstimate(
                dps_mean=evaluation.dps_mean,
                dps_se=evaluation.dps_se,
                iterations=evaluation.iterations,
            ),
            target_packages=compiled.targets,
            evidence_sha256={
                "rotation_response": response.evidence_sha256,
                **(
                    {}
                    if self.set_impact_result is None
                    else {
                        "set_impact": _canonical_sha256(
                            [
                                item.evidence_sha256
                                for item in self.set_impact_result.rows
                            ]
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
        status: GcsimOptimizerTerminalStatus,
        stop_reason: str,
        started: float,
        *,
        top_n=None,
        issues: Sequence[GcsimOptimizerIssue] = (),
        catalog=None,
        response=None,
        wearer_pools: Sequence[GcsimOptimizerAnytimeWearerPool] = (),
        joint_coverage=None,
        race=None,
        error: str = "",
    ) -> GcsimOptimizerTerminalResult:
        race_results = tuple(
            {
                item.evidence_sha256: item
                for item in (
                    *tuple(self.preliminary_race_results),
                    *((race,) if race is not None else ()),
                )
            }.values()
        )
        coverage = _coverage(
            catalog=catalog,
            response=response,
            set_impact=self.set_impact_result,
            wearer_pools=wearer_pools,
            joint_coverage=joint_coverage,
            races=race_results,
        )
        cache_hits = (
            (response.cache_hit_count if response is not None else 0)
            + (
                sum(
                    count
                    for race_result in race_results
                    for _tier, count in race_result.cache_hits_by_tier
                )
            )
        )
        requested = (
            (response.planned_probe_count if response is not None else 0)
            + (
                sum(
                    count
                    for race_result in race_results
                    for _tier, count in race_result.requested_by_tier
                )
            )
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
                **(
                    {}
                    if catalog is None
                    else {"dense_catalog": catalog.identity_sha256}
                ),
                **(
                    {}
                    if response is None
                    else {
                        "rotation_response": response.evidence_sha256
                    }
                ),
                **(
                    {}
                    if self.set_impact_result is None
                    else {
                        "set_impact": _canonical_sha256(
                            [
                                item.evidence_sha256
                                for item in self.set_impact_result.rows
                            ]
                        )
                    }
                ),
                **(
                    {}
                    if race is None
                    else {"race": race.evidence_sha256}
                ),
            },
            issues=tuple(issues),
            coverage=coverage,
            cache=GcsimOptimizerCacheCounters(
                hits=cache_hits,
                misses=max(requested - cache_hits, 0),
            ),
            timing=GcsimOptimizerTimingCounters(self._timing),
            error=error,
        )

    def _result(
        self,
        terminal,
        *,
        targets_by_wearer,
        catalog,
        response,
        wearer_pools,
        joint_coverage,
        race,
    ) -> GcsimOptimizerAnytimeSelectedResult:
        return GcsimOptimizerAnytimeSelectedResult(
            terminal=terminal,
            run_input_sha256=self.run_input.run_input_sha256,
            plan=self.plan,
            progress_events=tuple(self._progress),
            targets_by_wearer=tuple(targets_by_wearer),
            dense_catalog=catalog,
            response_result=response,
            wearer_pools=tuple(wearer_pools),
            joint_coverage=joint_coverage,
            race_result=race,
            preliminary_race_results=tuple(
                self.preliminary_race_results
            ),
        )

    def _emit(
        self,
        stage,
        *,
        started,
        deadline,
        completed,
        planned,
        cache_hits=0,
        current_iterations=None,
        leader=None,
    ) -> None:
        event = GcsimOptimizerProgressEvent(
            request_sha256=self.run_input.request.request_sha256,
            operation=self.run_input.request.operation,
            work_plan_sha256=(
                self.run_input.request.work_plan.identity_sha256
            ),
            stage=stage,
            sequence=len(self._progress),
            completed_work=completed,
            planned_work=planned,
            elapsed_seconds=max(self.clock() - started, 0.0),
            remaining_seconds=max(deadline - self.clock(), 0.0),
            cache_hits=cache_hits,
            current_iterations=current_iterations,
            current_best=leader,
        )
        self._progress.append(event)
        if self.progress_callback is not None:
            self.progress_callback(event)

    def _raise_if_interrupted(self, deadline: float) -> None:
        if self._cancel_event.is_set():
            raise _AnytimeSelectedInterrupted(
                "anytime_selected_cancelled",
                cancelled=True,
            )
        if self.clock() >= deadline:
            raise _AnytimeSelectedInterrupted(
                "anytime_selected_deadline_reached",
                cancelled=False,
            )

    def _set_active(self, value: object) -> None:
        with self._lock:
            self._active_cancellable = value

    def _clear_active(self, value: object) -> None:
        with self._lock:
            if self._active_cancellable is value:
                self._active_cancellable = None

    def _start_stage(self, stage: str) -> None:
        self._stage_started[stage] = self.clock()

    def _finish_stage(self, stage: str) -> None:
        started = self._stage_started.pop(stage, self.clock())
        self._timing[stage] = max(self.clock() - started, 0.0)


@dataclass(frozen=True, slots=True)
class _AnytimeSelectedInterrupted(Exception):
    reason: str
    cancelled: bool


def run_gcsim_optimizer_anytime_selected(
    run_input: GcsimOptimizerRunInput,
    **kwargs,
) -> GcsimOptimizerAnytimeSelectedResult:
    return GcsimOptimizerAnytimeSelectedSession(
        run_input,
        **kwargs,
    ).run()


def _retain_best_account_package_candidates(
    candidates: Sequence[GcsimOptimizerCandidateResult],
) -> tuple[GcsimOptimizerCandidateResult, ...]:
    """Keep the strongest confirmed physical build per team package layout."""

    ordered = tuple(
        sorted(
            candidates,
            key=lambda item: (
                -float(item.estimate.dps_mean),
                item.candidate_identity_sha256,
            ),
        )
    )
    retained: list[GcsimOptimizerCandidateResult] = []
    signatures: set[tuple[str, ...]] = set()
    for candidate in ordered:
        signature = build_gcsim_optimizer_account_package_signature(
            candidate.target_packages
        )
        if signature in signatures:
            continue
        signatures.add(signature)
        retained.append(candidate)
    return tuple(retained)


def _last_confirmed_race(
    preliminary: Sequence[GcsimOptimizerAnytimeRaceResult],
    *,
    current: GcsimOptimizerAnytimeRaceResult | None,
) -> GcsimOptimizerAnytimeRaceResult | None:
    """Find the latest race that still owns saveable exact evidence."""

    phases = (
        *tuple(preliminary),
        *((current,) if current is not None else ()),
    )
    return next(
        (
            phase
            for phase in reversed(phases)
            if phase.confirmed_evaluations
        ),
        None,
    )


def _best_confirmed_proposals_by_signature(
    evaluations: Sequence[GcsimOptimizerAnytimeRaceEvaluation],
    *,
    signatures: Sequence[tuple[str, ...]] | None = None,
) -> tuple[GcsimOptimizerJointProposal, ...]:
    """Return the exact-DPS leader for each requested package signature."""

    by_signature: dict[tuple[str, ...], GcsimOptimizerJointProposal] = {}
    for evaluation in evaluations:
        signature = build_gcsim_optimizer_account_package_signature(
            evaluation.proposal.compiled_candidate.targets
        )
        by_signature.setdefault(signature, evaluation.proposal)
    if signatures is None:
        return tuple(by_signature.values())
    return tuple(
        by_signature[signature]
        for signature in signatures
        if signature in by_signature
    )


def _select_refinement_signature_seeds(
    race: GcsimOptimizerAnytimeRaceResult,
    *,
    required_proposals: Sequence[GcsimOptimizerJointProposal],
    limit: int,
) -> tuple[GcsimOptimizerJointProposal, ...]:
    """Select bounded confirmed package leaders plus external anchors."""

    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise GcsimOptimizerAnytimeSelectedError(
            "refinement signature seed limit must be positive"
        )
    selected: list[GcsimOptimizerJointProposal] = []
    seen: set[tuple[str, ...]] = set()
    for evaluation in race.confirmed_evaluations:
        signature = build_gcsim_optimizer_account_package_signature(
            evaluation.proposal.compiled_candidate.targets
        )
        if signature in seen:
            continue
        selected.append(evaluation.proposal)
        seen.add(signature)
        if len(selected) >= limit:
            break
    for required in required_proposals:
        signature = build_gcsim_optimizer_account_package_signature(
            required.compiled_candidate.targets
        )
        if signature in seen:
            continue
        selected.append(required)
        seen.add(signature)
    return tuple(selected)


def _select_required_signature_challengers(
    proposals: Sequence[GcsimOptimizerJointProposal],
    *,
    incumbents: Sequence[GcsimOptimizerJointProposal],
    signatures: Sequence[tuple[str, ...]],
) -> tuple[GcsimOptimizerJointProposal, ...]:
    """Reserve one deterministic physical challenger for each family."""

    incumbent_proposals = {
        build_gcsim_optimizer_account_package_signature(
            item.compiled_candidate.targets
        ): item.proposal_sha256
        for item in incumbents
    }
    rows_by_signature: dict[
        tuple[str, ...], list[GcsimOptimizerJointProposal]
    ] = {signature: [] for signature in signatures}
    for proposal in proposals:
        signature = build_gcsim_optimizer_account_package_signature(
            proposal.compiled_candidate.targets
        )
        if signature in rows_by_signature:
            rows_by_signature[signature].append(proposal)
    selected = []
    for signature in signatures:
        incumbent_proposal = incumbent_proposals.get(signature)
        challenger = next(
            (
                item
                for item in sorted(
                    rows_by_signature[signature],
                    key=lambda proposal: (
                        -float(proposal.surrogate_score),
                        proposal.proposal_sha256,
                    ),
                )
                if item.proposal_sha256 != incumbent_proposal
            ),
            None,
        )
        if challenger is not None:
            selected.append(challenger)
    return tuple(selected)


def _best_validated_challengers_by_signature(
    race: GcsimOptimizerAnytimeRaceResult,
    *,
    incumbents: Sequence[GcsimOptimizerJointProposal],
    signatures: Sequence[tuple[str, ...]],
) -> tuple[GcsimOptimizerJointProposal, ...]:
    """Promote the best exact n=200 non-incumbent physical config."""

    incumbent_proposals = {
        build_gcsim_optimizer_account_package_signature(
            item.compiled_candidate.targets
        ): item.proposal_sha256
        for item in incumbents
    }
    rows_by_signature: dict[
        tuple[str, ...], list[GcsimOptimizerAnytimeRaceEvaluation]
    ] = {signature: [] for signature in signatures}
    for evaluation in race.trace_evaluations:
        if evaluation.tier_id != "validate_200" or not evaluation.success:
            continue
        signature = build_gcsim_optimizer_account_package_signature(
            evaluation.proposal.compiled_candidate.targets
        )
        if (
            signature not in rows_by_signature
            or evaluation.proposal.proposal_sha256
            == incumbent_proposals.get(signature)
        ):
            continue
        rows_by_signature[signature].append(evaluation)
    selected = []
    for signature in signatures:
        rows = rows_by_signature[signature]
        if not rows:
            continue
        selected.append(
            min(
                rows,
                key=lambda item: (
                    -float(item.dps_mean),
                    item.proposal.proposal_sha256,
                ),
            ).proposal
        )
    return tuple(selected)


def _require_refinement_proposals_confirmed(
    race: GcsimOptimizerAnytimeRaceResult,
    required_proposal_sha256s: Sequence[str],
    *,
    phase: str,
) -> None:
    """Fail closed if a completed refinement race discarded an anchor."""

    if race.status in {
        GcsimOptimizerAnytimeRaceStatus.CANCELLED,
        GcsimOptimizerAnytimeRaceStatus.DEADLINE,
    }:
        return
    confirmed_ids = {
        item.proposal.proposal_sha256
        for item in race.confirmed_evaluations
    }
    if not set(required_proposal_sha256s).issubset(confirmed_ids):
        raise GcsimOptimizerAnytimeSelectedError(
            f"{phase} lost a required confirmed proposal"
        )


def _retain_signature_coordinate_frontiers(
    rows_by_signature: Sequence[
        tuple[
            tuple[str, ...],
            Sequence[GcsimOptimizerJointProposal],
        ]
    ],
    *,
    limit: int,
) -> tuple[GcsimOptimizerJointProposal, ...]:
    """Apply the selected-mode coordinate bound to every package family."""

    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise GcsimOptimizerAnytimeSelectedError(
            "signature coordinate frontier limit must be positive"
        )
    rows = tuple(
        (tuple(signature), tuple(proposals))
        for signature, proposals in rows_by_signature
        if proposals
    )
    if not rows:
        return ()
    if len({signature for signature, _proposals in rows}) != len(rows):
        raise GcsimOptimizerAnytimeSelectedError(
            "signature coordinate frontiers must be unique"
        )
    retained = []
    for _signature, proposals in rows:
        retained.extend(
            _retain_coordinate_refinement_frontier(
                proposals,
                limit=limit,
            )
        )
    return _merge_distinct_proposals((), retained)


def _retain_best_confirmed_evaluations_by_signature(
    evaluations: Sequence[GcsimOptimizerAnytimeRaceEvaluation],
) -> tuple[GcsimOptimizerAnytimeRaceEvaluation, ...]:
    """Keep the highest-fidelity non-regressing exact row per signature."""

    best: dict[
        tuple[str, ...], GcsimOptimizerAnytimeRaceEvaluation
    ] = {}
    for evaluation in evaluations:
        signature = build_gcsim_optimizer_account_package_signature(
            evaluation.proposal.compiled_candidate.targets
        )
        current = best.get(signature)
        if current is None or (
            -evaluation.iterations,
            -float(evaluation.dps_mean),
            evaluation.proposal.proposal_sha256,
        ) < (
            -current.iterations,
            -float(current.dps_mean),
            current.proposal.proposal_sha256,
        ):
            best[signature] = evaluation
    return tuple(
        sorted(
            best.values(),
            key=lambda item: (
                -float(item.dps_mean),
                item.proposal.proposal_sha256,
            ),
        )
    )


def _merge_distinct_proposals(
    primary: Sequence[GcsimOptimizerJointProposal],
    local: Sequence[GcsimOptimizerJointProposal],
) -> tuple[GcsimOptimizerJointProposal, ...]:
    """Merge exact configs while retaining every attached coverage witness."""

    by_config: dict[str, GcsimOptimizerJointProposal] = {}
    for proposal in (*tuple(primary), *tuple(local)):
        config_sha256 = (
            proposal.compiled_candidate.compiled_config_sha256
        )
        retained = by_config.get(config_sha256)
        if retained is None:
            by_config[config_sha256] = proposal
            continue
        labels = tuple(
            sorted(
                {
                    *retained.diversity_labels,
                    *proposal.diversity_labels,
                }
            )
        )
        if labels != retained.diversity_labels:
            # Physical/evaluation identity remains the primary proposal's;
            # diversity labels are provenance attached to that exact config.
            by_config[config_sha256] = replace(
                retained,
                diversity_labels=labels,
            )
    return tuple(
        sorted(
            by_config.values(),
            key=lambda item: (
                -float(item.surrogate_score),
                item.proposal_sha256,
            ),
        )
    )


def _merge_anytime_wearer_pools(
    primary: GcsimOptimizerAnytimeWearerPool,
    refinements: Sequence[GcsimOptimizerAnytimeWearerPool],
    *,
    limit: int,
) -> GcsimOptimizerAnytimeWearerPool:
    """Preserve the ordinary pool, then append distinct exploration builds."""

    rows = (primary, *tuple(refinements))
    if any(item.wearer != primary.wearer for item in rows):
        raise GcsimOptimizerAnytimeSelectedError(
            "merged wearer pools must use one wearer"
        )
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise GcsimOptimizerAnytimeSelectedError(
            "merged wearer pool limit must be positive"
        )
    candidates = []
    seen_assignments: set[tuple[int, ...]] = set()

    def append(candidate) -> None:
        assignment = candidate.assignment.artifact_ids
        if assignment in seen_assignments or len(candidates) >= limit:
            return
        seen_assignments.add(assignment)
        candidates.append(candidate)

    # Never weaken the ordinary response-ranked pool.
    for candidate in primary.candidates:
        append(candidate)
        if len(candidates) >= limit:
            break

    # Spend the bounded exploration remainder fairly across structural/main
    # directions.  The former sequential append let the first profile consume
    # all remaining capacity, making later axes unreachable by exact-GCSIM
    # coordinate refinement.
    depth = 0
    refinement_rows = tuple(refinements)
    while len(candidates) < limit:
        progressed = False
        for pool in refinement_rows:
            if depth >= len(pool.candidates):
                continue
            progressed = True
            append(pool.candidates[depth])
            if len(candidates) >= limit:
                break
        if not progressed:
            break
        depth += 1
    coverage_fields = (
        "indexed_artifact_count",
        "invalid_artifact_count",
        "eligible_piece_count",
        "pareto_piece_count",
        "shadow_piece_count",
        "expanded_wearer_state_count",
        "package_pruned_state_count",
        "floor_pruned_state_count",
        "complete_wearer_state_count",
        "materialized_candidate_count",
        "materialization_failure_count",
        "content_deduplicated_candidate_count",
    )
    coverage_values = {}
    for field_name in coverage_fields:
        if field_name in {"indexed_artifact_count", "invalid_artifact_count"}:
            coverage_values[field_name] = getattr(
                primary.coverage,
                field_name,
            )
        else:
            coverage_values[field_name] = sum(
                getattr(pool.coverage, field_name) for pool in rows
            )
    return GcsimOptimizerAnytimeWearerPool(
        wearer=primary.wearer,
        candidates=tuple(candidates),
        coverage=type(primary.coverage)(**coverage_values),
    )


def _retain_coordinate_refinement_frontier(
    proposals: Sequence[GcsimOptimizerJointProposal],
    *,
    limit: int,
) -> tuple[GcsimOptimizerJointProposal, ...]:
    """Bound exact screening while preserving coordinate search directions.

    A coordinate pool can contain hundreds of one-wearer moves.  Simulating
    every one at n=8 made three useful coordinate rounds dominate product
    runtime.  A scalar-score head alone is unsafe (the real winner can be weak
    under the local surrogate), so the bounded frontier also retains a fair
    depth for every fixed wearer slot and every fixed-candidate structural/main
    feature emitted by the proposal builder.
    """

    rows = tuple(proposals)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise GcsimOptimizerAnytimeSelectedError(
            "coordinate screen proposal limit must be positive"
        )
    if len(rows) <= limit:
        return rows
    ordered = tuple(
        sorted(
            rows,
            key=lambda item: (
                item.changed_wearer_count,
                -float(item.surrogate_score),
                item.proposal_sha256,
            ),
        )
    )
    retained: list[GcsimOptimizerJointProposal] = []
    retained_ids: set[str] = set()

    def add(item: GcsimOptimizerJointProposal) -> None:
        if item.proposal_sha256 in retained_ids or len(retained) >= limit:
            return
        retained.append(item)
        retained_ids.add(item.proposal_sha256)

    # Ordinary exploitation head.
    for item in ordered[: max(1, limit // 3)]:
        add(item)

    def retain_group_depth(
        prefix: str,
        depth_limit: int,
        *,
        balance_feature_slots: bool = False,
    ) -> None:
        groups: dict[str, list[GcsimOptimizerJointProposal]] = {}
        for item in ordered:
            for label in item.diversity_labels:
                if label.startswith(prefix):
                    groups.setdefault(label, []).append(item)
        if balance_feature_slots:
            labels_by_slot: dict[int, list[tuple[int, str, str]]] = {}
            for label in groups:
                suffix = label[len(prefix) :]
                slot_text, separator, feature = suffix.partition(":")
                if not separator or not slot_text.isdigit():
                    continue
                slot = int(slot_text)
                feature_priority = (
                    0
                    if feature.startswith("main_axis_anchor:")
                    else 1
                    if feature.startswith("structural_stat_axis:")
                    else 2
                    if feature.startswith("uncertainty_")
                    else 3
                )
                labels_by_slot.setdefault(slot, []).append(
                    (feature_priority, feature, label)
                )
            ordered_by_slot = {
                slot: [row[2] for row in sorted(rows)]
                for slot, rows in labels_by_slot.items()
            }
            slots = tuple(sorted(ordered_by_slot))
            max_group_count = max(
                (len(labels) for labels in ordered_by_slot.values()),
                default=0,
            )
            for depth in range(depth_limit):
                for group_index in range(max_group_count):
                    for slot in slots:
                        labels = ordered_by_slot[slot]
                        if group_index >= len(labels):
                            continue
                        group = groups[labels[group_index]]
                        if depth < len(group):
                            add(group[depth])
                        if len(retained) >= limit:
                            return
            return
        for depth in range(depth_limit):
            for label in sorted(groups):
                group = groups[label]
                if depth < len(group):
                    add(group[depth])
                if len(retained) >= limit:
                    return

    # Coordinate descent must not collapse onto one noisy n=1000 seed.  Keep
    # several directions from each confirmed basin before allocating the
    # wearer/feature quotas below.
    retain_group_depth("coordinate_seed:", 16)
    # A balanced candidate ranked 10-15 inside its wearer slot produced the
    # large Chasca/Furina improvements in the frozen real-account regression.
    retain_group_depth("coordinate_fixed_slot:", 16)
    # Structural/main anchors are more specific; one fair depth per emitted
    # fixed feature is normally sufficient, with four levels retained for
    # conflict-repair alternatives.
    retain_group_depth(
        "coordinate_fixed_feature:",
        4,
        balance_feature_slots=True,
    )
    for item in ordered:
        add(item)
        if len(retained) >= limit:
            break
    return tuple(retained)


def _coverage(
    *,
    catalog,
    response,
    set_impact,
    wearer_pools,
    joint_coverage,
    races,
) -> GcsimOptimizerCoverageCounters:
    counters: Counter[str] = Counter()
    if catalog is not None:
        counters["dense_indexed_artifact_count"] = len(catalog.artifacts)
        counters["dense_invalid_artifact_count"] = (
            catalog.source_artifact_count - len(catalog.artifacts)
        )
    if response is not None:
        counters["response_probe_count"] = response.planned_probe_count
        counters["response_success_count"] = response.successful_probe_count
        counters["response_failure_count"] = response.failed_probe_count
    if set_impact is not None:
        counters["set_impact_probe_count"] = len(set_impact.rows)
        counters["set_impact_retained_count"] = sum(
            item.retained for item in set_impact.rows
        )
        counters["set_impact_negligible_count"] = sum(
            not item.retained for item in set_impact.rows
        )
        counters["set_impact_batch_count"] = set_impact.batch_count
    for pool in wearer_pools:
        slot = pool.wearer.team_slot
        counters[f"wearer_{slot}_candidate_count"] = len(pool.candidates)
        for key, value in pool.coverage.to_dict().items():
            if key == "schema_version":
                continue
            counters[f"wearer_{slot}_{key}"] = value
    if joint_coverage is not None:
        for key, value in joint_coverage.to_dict().items():
            if key != "schema_version" and isinstance(value, int):
                counters[f"joint_{key}"] = value
    for race in races:
        for tier, count in race.requested_by_tier:
            counters[f"race_{tier}_requested"] += count
        for tier, count in race.successful_by_tier:
            counters[f"race_{tier}_successful"] += count
    return GcsimOptimizerCoverageCounters(counters)


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _thaw_json(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_thaw_json(item) for item in value]
    return value


def _target_identity(target: GcsimOptimizerWearerTarget) -> str:
    return _canonical_sha256(target.to_dict())


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_schema(value: int) -> None:
    if value != GCSIM_OPTIMIZER_ANYTIME_SELECTED_SCHEMA_VERSION:
        raise GcsimOptimizerAnytimeSelectedError(
            "unsupported anytime selected schema"
        )


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise GcsimOptimizerAnytimeSelectedError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


__all__ = [
    "GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_ID",
    "GCSIM_OPTIMIZER_ANYTIME_SELECTED_PLAN_VERSION",
    "GCSIM_OPTIMIZER_ANYTIME_SELECTED_SCHEMA_VERSION",
    "GcsimOptimizerAnytimeSelectedError",
    "GcsimOptimizerAnytimeSelectedPlan",
    "GcsimOptimizerAnytimeSelectedResult",
    "GcsimOptimizerAnytimeSelectedSession",
    "run_gcsim_optimizer_anytime_selected",
]
