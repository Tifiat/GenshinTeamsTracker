"""Bounded generic main-stat layout discovery for theoretical 4p search.

The legal sands/goblet/circlet domain contains 420 combinations per wearer.
This stage avoids both character hardcodes and that full Cartesian brute force:

1. start every wearer from the same neutral ATK/ATK/CR seed;
2. scan every legal value one slot at a time while the other two stay frozen;
3. keep a bounded number of best values per slot;
4. evaluate only their small Cartesian product and return bounded finalists.

It is a heuristic response surface, not a global proof.  In particular, set
bonuses may shift the best main stats, so later set-aware refinement/oracle
benchmarking remains required before claiming globally optimal sets.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from itertools import product
import math
from threading import Event, Lock
from time import monotonic
from types import MappingProxyType

from .farming_evaluator import (
    FarmingSessionFactory,
    GcsimFarmingBatchResult,
    GcsimFarmingBatchStatus,
    GcsimFarmingEvaluationRequest,
    GcsimFarmingEvaluationResult,
    GcsimFarmingEvaluationScheduler,
    GcsimFarmingEvaluationStatus,
    GcsimFarmingSchedulerBudget,
    freeze_gcsim_farming_environment,
    normalize_gcsim_farming_frozen_environment,
)
from .farming_pipeline import (
    GcsimFarmingMaterializedProbe,
    GcsimFarmingScreeningFidelity,
    SchedulerFactory,
    materialize_gcsim_one_wearer_candidate,
)
from .farming_profile_config import GCSIM_BALANCED_REFERENCE_WEIGHTS
from .farming_search import (
    PROFILE_BASELINE,
    CandidateEvaluation,
    FourPieceSetState,
    SetProfileCandidate,
    StatProfileBank,
    StatWeight,
)
from .optimizer_cache import GcsimOptimizerCacheStore
from .optimizer_config import (
    LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS,
    LEGAL_FIVE_STAR_GOBLET_MAIN_STATS,
    LEGAL_FIVE_STAR_SANDS_MAIN_STATS,
    GcsimFiveStarMainStatLayout,
)
from .optimizer_engine_context import GcsimOptimizerEngineContext


GCSIM_GENERIC_MAIN_LAYOUT_SEED = GcsimFiveStarMainStatLayout(
    sands="atk%",
    goblet="atk%",
    circlet="cr",
)


class GcsimMainLayoutScanError(RuntimeError):
    """Raised when the bounded main-layout scan cannot stay coherent."""


class GcsimMainLayoutScanStatus(str, Enum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DEADLINE_REACHED = "deadline_reached"
    INCOMPLETE_COORDINATES = "incomplete_coordinates"
    INCOMPLETE_COMBINATIONS = "incomplete_combinations"


@dataclass(frozen=True, slots=True)
class GcsimMainLayoutScanBudget:
    max_values_per_slot: int = 2
    max_layouts_per_wearer: int = 3
    candidate_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        for field_name in ("max_values_per_slot", "max_layouts_per_wearer"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.max_values_per_slot > min(
            len(LEGAL_FIVE_STAR_SANDS_MAIN_STATS),
            len(LEGAL_FIVE_STAR_GOBLET_MAIN_STATS),
            len(LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS),
        ):
            raise ValueError("max_values_per_slot exceeds a legal slot domain")
        if (
            isinstance(self.candidate_timeout_seconds, bool)
            or not math.isfinite(self.candidate_timeout_seconds)
            or self.candidate_timeout_seconds <= 0
        ):
            raise ValueError("candidate_timeout_seconds must be finite and positive")


@dataclass(frozen=True, slots=True)
class GcsimMainLayoutScanRequest:
    engine_context: GcsimOptimizerEngineContext
    prepared_config_text: str
    wearer_ids: tuple[str, ...]
    baseline_set_states: tuple[FourPieceSetState, ...]
    profile_bank: StatProfileBank
    fidelity: GcsimFarmingScreeningFidelity
    coordinate_scheduler_budget: GcsimFarmingSchedulerBudget
    combination_scheduler_budget: GcsimFarmingSchedulerBudget
    scan_budget: GcsimMainLayoutScanBudget
    overall_deadline_seconds: float
    baseline_profile_id: str = PROFILE_BASELINE
    seed_layout: GcsimFiveStarMainStatLayout = GCSIM_GENERIC_MAIN_LAYOUT_SEED
    reference_weights: tuple[StatWeight, ...] = GCSIM_BALANCED_REFERENCE_WEIGHTS
    environment: Mapping[str, str] = field(default_factory=dict, repr=False)
    environment_is_frozen: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "wearer_ids", tuple(self.wearer_ids))
        object.__setattr__(
            self,
            "baseline_set_states",
            tuple(self.baseline_set_states),
        )
        object.__setattr__(self, "reference_weights", tuple(self.reference_weights))
        if tuple(state.wearer_id for state in self.baseline_set_states) != self.wearer_ids:
            raise GcsimMainLayoutScanError(
                "baseline_set_states must match wearer_ids in canonical order"
            )
        if self.baseline_profile_id not in tuple(
            profile.profile_id for profile in self.profile_bank.profiles
        ):
            raise GcsimMainLayoutScanError(
                "profile_bank does not contain baseline_profile_id"
            )
        if (
            isinstance(self.overall_deadline_seconds, bool)
            or not math.isfinite(self.overall_deadline_seconds)
            or self.overall_deadline_seconds <= 0
        ):
            raise GcsimMainLayoutScanError(
                "overall_deadline_seconds must be finite and positive"
            )
        try:
            frozen_environment = (
                normalize_gcsim_farming_frozen_environment(
                    self.environment,
                    worker_count=self.fidelity.worker_count,
                )
                if self.environment_is_frozen
                else freeze_gcsim_farming_environment(
                    self.environment,
                    worker_count=self.fidelity.worker_count,
                )
            )
        except ValueError as exc:
            raise GcsimMainLayoutScanError(str(exc)) from exc
        object.__setattr__(
            self,
            "environment",
            MappingProxyType(frozen_environment),
        )
        object.__setattr__(self, "environment_is_frozen", True)


@dataclass(frozen=True, slots=True)
class GcsimWearerLayoutSelection:
    wearer_id: str
    best_layout_id: str
    layouts: tuple[tuple[str, GcsimFiveStarMainStatLayout], ...]
    selected_slot_values: tuple[tuple[str, tuple[str, ...]], ...]

    def __post_init__(self) -> None:
        try:
            layouts = tuple((layout_id, layout) for layout_id, layout in self.layouts)
            selected_slot_values = tuple(
                (slot, tuple(values)) for slot, values in self.selected_slot_values
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("layout selection evidence is malformed") from exc
        object.__setattr__(self, "layouts", layouts)
        object.__setattr__(self, "selected_slot_values", selected_slot_values)
        if (
            not isinstance(self.wearer_id, str)
            or not self.wearer_id
            or self.wearer_id != self.wearer_id.strip()
        ):
            raise ValueError("wearer_id must be a non-empty trimmed string")
        if (
            not isinstance(self.best_layout_id, str)
            or not self.best_layout_id
            or self.best_layout_id != self.best_layout_id.strip()
        ):
            raise ValueError("best_layout_id must be a non-empty trimmed string")
        if not layouts or self.best_layout_id not in dict(layouts):
            raise ValueError("layout selection must contain its best layout")
        if len({layout_id for layout_id, _layout in layouts}) != len(layouts):
            raise ValueError("layout selection ids must be unique")
        for layout_id, layout in layouts:
            if not isinstance(layout, GcsimFiveStarMainStatLayout):
                raise ValueError("layouts must contain typed main-stat layouts")
            if layout_id != _layout_id(layout):
                raise ValueError("layout id does not match its main-stat layout")
        if tuple(slot for slot, _values in selected_slot_values) != (
            "sands",
            "goblet",
            "circlet",
        ):
            raise ValueError("selected slot values must use canonical slot order")
        legal_values_by_slot = {
            "sands": frozenset(LEGAL_FIVE_STAR_SANDS_MAIN_STATS),
            "goblet": frozenset(LEGAL_FIVE_STAR_GOBLET_MAIN_STATS),
            "circlet": frozenset(LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS),
        }
        for slot, values in selected_slot_values:
            if not values or len(set(values)) != len(values):
                raise ValueError("selected slot values must be non-empty and unique")
            if any(
                not isinstance(value, str)
                or value not in legal_values_by_slot[slot]
                for value in values
            ):
                raise ValueError("selected slot values contain an illegal main stat")


@dataclass(frozen=True, slots=True)
class GcsimMainLayoutScanResult:
    status: GcsimMainLayoutScanStatus
    stop_reason: str
    elapsed_seconds: float
    coordinate_candidate_count: int
    combination_candidate_count: int
    coordinate_request_count: int
    combination_request_count: int
    selections: tuple[GcsimWearerLayoutSelection, ...] = ()
    coordinate_evaluations: tuple[CandidateEvaluation, ...] = ()
    combination_evaluations: tuple[CandidateEvaluation, ...] = ()
    coordinate_batch: GcsimFarmingBatchResult | None = None
    combination_batch: GcsimFarmingBatchResult | None = None
    coordinate_request_identities: tuple[str, ...] = ()
    combination_request_identities: tuple[str, ...] = ()
    scan_budget_snapshot: GcsimMainLayoutScanBudget | None = None
    seed_layout_snapshot: GcsimFiveStarMainStatLayout | None = None
    error: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "selections", tuple(self.selections))
        object.__setattr__(
            self,
            "coordinate_evaluations",
            tuple(self.coordinate_evaluations),
        )
        object.__setattr__(
            self,
            "combination_evaluations",
            tuple(self.combination_evaluations),
        )
        object.__setattr__(
            self,
            "coordinate_request_identities",
            tuple(self.coordinate_request_identities),
        )
        object.__setattr__(
            self,
            "combination_request_identities",
            tuple(self.combination_request_identities),
        )
        if not isinstance(self.status, GcsimMainLayoutScanStatus):
            raise ValueError("status must be a GcsimMainLayoutScanStatus")
        if not isinstance(self.stop_reason, str) or not self.stop_reason:
            raise ValueError("stop_reason must be a non-empty string")
        if not isinstance(self.error, str):
            raise ValueError("error must be a string")
        for field_name in (
            "coordinate_candidate_count",
            "combination_candidate_count",
            "coordinate_request_count",
            "combination_request_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must be finite and non-negative")
        if self.coordinate_request_count > self.coordinate_candidate_count:
            raise ValueError("coordinate request count exceeds logical candidates")
        if self.combination_request_count > self.combination_candidate_count:
            raise ValueError("combination request count exceeds logical candidates")
        if self.coordinate_batch is not None and len(
            self.coordinate_batch.results
        ) != self.coordinate_request_count:
            raise ValueError("coordinate batch size differs from request count")
        if self.combination_batch is not None and len(
            self.combination_batch.results
        ) != self.combination_request_count:
            raise ValueError("combination batch size differs from request count")
        _validate_layout_evaluation_projection(
            self.coordinate_evaluations,
            self.coordinate_request_identities,
            self.coordinate_batch,
            phase="coordinate",
        )
        _validate_layout_evaluation_projection(
            self.combination_evaluations,
            self.combination_request_identities,
            self.combination_batch,
            phase="combination",
        )
        if self.status is GcsimMainLayoutScanStatus.COMPLETED:
            if (
                not self.selections
                or self.coordinate_batch is None
                or self.combination_batch is None
                or len(self.coordinate_evaluations)
                != self.coordinate_candidate_count
                or len(self.combination_evaluations)
                != self.combination_candidate_count
                or not isinstance(
                    self.scan_budget_snapshot,
                    GcsimMainLayoutScanBudget,
                )
                or not isinstance(
                    self.seed_layout_snapshot,
                    GcsimFiveStarMainStatLayout,
                )
            ):
                raise ValueError(
                    "completed layout scan requires full evidence and selections"
                )
            if (
                self.coordinate_batch.status is not GcsimFarmingBatchStatus.COMPLETED
                or self.combination_batch.status
                is not GcsimFarmingBatchStatus.COMPLETED
            ):
                raise ValueError("completed layout scan requires successful batches")
            if (
                self.coordinate_batch.requested_count != self.coordinate_request_count
                or self.combination_batch.requested_count
                != self.combination_request_count
                or self.coordinate_batch.successful_count
                != self.coordinate_request_count
                or self.combination_batch.successful_count
                != self.combination_request_count
            ):
                raise ValueError("completed layout scan batch counts are inconsistent")
            investment_signatures = {
                evaluation.investment_signature
                for evaluation in (
                    *self.coordinate_evaluations,
                    *self.combination_evaluations,
                )
            }
            if len(investment_signatures) != 1:
                raise ValueError("layout scan evaluations mix investment contexts")
            coordinate_keys = tuple(
                evaluation.candidate.key
                for evaluation in self.coordinate_evaluations
            )
            combination_keys = tuple(
                evaluation.candidate.key
                for evaluation in self.combination_evaluations
            )
            if len(set(coordinate_keys)) != len(coordinate_keys):
                raise ValueError("coordinate evaluations contain duplicate candidates")
            if len(set(combination_keys)) != len(combination_keys):
                raise ValueError("combination evaluations contain duplicate candidates")
            coordinate_wearers = tuple(
                dict.fromkeys(
                    evaluation.candidate.state.wearer_id
                    for evaluation in self.coordinate_evaluations
                )
            )
            combination_wearers = tuple(
                dict.fromkeys(
                    evaluation.candidate.state.wearer_id
                    for evaluation in self.combination_evaluations
                )
            )
            selection_wearers = tuple(
                selection.wearer_id for selection in self.selections
            )
            if (
                not combination_wearers
                or coordinate_wearers != combination_wearers
                or selection_wearers != combination_wearers
            ):
                raise ValueError(
                    "layout selections must cover wearers exactly in canonical order"
                )
            expected_coordinate_layout_ids = tuple(
                _coordinate_layouts(self.seed_layout_snapshot)
            )
            selected_values_by_wearer = _select_coordinate_values(
                self.coordinate_evaluations,
                wearer_ids=combination_wearers,
                seed_layout=self.seed_layout_snapshot,
                max_values=self.scan_budget_snapshot.max_values_per_slot,
            )
            for selection in self.selections:
                actual_coordinate_layout_ids = tuple(
                    evaluation.candidate.state.main_stat_layout_id
                    for evaluation in self.coordinate_evaluations
                    if evaluation.candidate.state.wearer_id == selection.wearer_id
                )
                if actual_coordinate_layout_ids != expected_coordinate_layout_ids:
                    raise ValueError(
                        "coordinate evaluations do not cover the exact legal probe domain"
                    )
                if (
                    selection.selected_slot_values
                    != selected_values_by_wearer[selection.wearer_id]
                ):
                    raise ValueError(
                        "selected slot values do not match coordinate evidence"
                    )
                selected_value_map = dict(selection.selected_slot_values)
                expected_combination_layout_ids = {
                    _layout_id(
                        GcsimFiveStarMainStatLayout(
                            sands=sands,
                            goblet=goblet,
                            circlet=circlet,
                        )
                    )
                    for sands, goblet, circlet in product(
                        selected_value_map["sands"],
                        selected_value_map["goblet"],
                        selected_value_map["circlet"],
                    )
                }
                expected_combination_layout_ids.add(
                    _layout_id(self.seed_layout_snapshot)
                )
                ranked = tuple(
                    sorted(
                        (
                            evaluation
                            for evaluation in self.combination_evaluations
                            if evaluation.candidate.state.wearer_id
                            == selection.wearer_id
                        ),
                        key=_evaluation_rank,
                    )
                )
                actual_combination_layout_ids = {
                    evaluation.candidate.state.main_stat_layout_id
                    for evaluation in ranked
                }
                if actual_combination_layout_ids != expected_combination_layout_ids:
                    raise ValueError(
                        "combination evaluations do not match the selected layout domain"
                    )
                expected_finalist_count = min(
                    self.scan_budget_snapshot.max_layouts_per_wearer,
                    len(ranked),
                )
                if len(selection.layouts) != expected_finalist_count:
                    raise ValueError(
                        "layout finalist count does not match the frozen scan budget"
                    )
                expected_layout_ids = tuple(
                    evaluation.candidate.state.main_stat_layout_id
                    for evaluation in ranked[:expected_finalist_count]
                )
                actual_layout_ids = tuple(
                    layout_id for layout_id, _layout in selection.layouts
                )
                if not ranked or actual_layout_ids != expected_layout_ids:
                    raise ValueError(
                        "layout finalists do not match canonical combination ranking"
                    )
                if selection.best_layout_id != expected_layout_ids[0]:
                    raise ValueError(
                        "best layout does not match canonical combination ranking"
                    )
        elif self.selections:
            raise ValueError("only a completed layout scan may carry selections")

    @property
    def completed(self) -> bool:
        return self.status is GcsimMainLayoutScanStatus.COMPLETED

    @property
    def layout_catalog(self) -> Mapping[str, Mapping[str, GcsimFiveStarMainStatLayout]]:
        return MappingProxyType(
            {
                selection.wearer_id: MappingProxyType(dict(selection.layouts))
                for selection in self.selections
            }
        )

    @property
    def best_baseline_states(self) -> tuple[SetProfileCandidate, ...]:
        if not self.completed:
            return ()
        evaluation_by_pair = {
            (
                evaluation.candidate.state.wearer_id,
                evaluation.candidate.state.main_stat_layout_id,
            ): evaluation
            for evaluation in self.combination_evaluations
        }
        return tuple(
            evaluation_by_pair[(selection.wearer_id, selection.best_layout_id)].candidate
            for selection in self.selections
        )


@dataclass(frozen=True, slots=True)
class _PhaseResult:
    candidates: tuple[SetProfileCandidate, ...]
    evaluations: tuple[CandidateEvaluation, ...]
    request_count: int
    batch: GcsimFarmingBatchResult | None
    status: GcsimMainLayoutScanStatus | None = None
    stop_reason: str = ""
    request_identities: tuple[str, ...] = ()


class GcsimMainLayoutScanSession:
    """Two-phase one-shot layout scan with bounded CPU and cancellation."""

    def __init__(
        self,
        request: GcsimMainLayoutScanRequest,
        *,
        cache_store: GcsimOptimizerCacheStore | None = None,
        enable_cache: bool = True,
        session_factory: FarmingSessionFactory | None = None,
        scheduler_factory: SchedulerFactory | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isinstance(request, GcsimMainLayoutScanRequest):
            raise GcsimMainLayoutScanError(
                "request must be a GcsimMainLayoutScanRequest"
            )
        self.request = request
        self._cache_store = cache_store
        self._enable_cache = bool(enable_cache)
        self._session_factory = session_factory
        self._scheduler_factory = scheduler_factory
        self._clock = clock
        self._cancel_event = Event()
        self._lock = Lock()
        self._active_scheduler = None
        self._started = False

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            scheduler = self._active_scheduler
        if scheduler is not None:
            scheduler.cancel()

    def run(self) -> GcsimMainLayoutScanResult:
        with self._lock:
            if self._started:
                raise RuntimeError("GcsimMainLayoutScanSession instances are one-shot")
            self._started = True
        started = self._clock()
        deadline = started + self.request.overall_deadline_seconds
        seed_id = _layout_id(self.request.seed_layout)
        baseline_candidates = tuple(
            SetProfileCandidate(
                state=replace(state, main_stat_layout_id=seed_id),
                profile_id=self.request.baseline_profile_id,
            )
            for state in self.request.baseline_set_states
        )
        coordinate_layouts = _coordinate_layouts(self.request.seed_layout)
        coordinate_catalog = {
            wearer: coordinate_layouts
            for wearer in self.request.wearer_ids
        }
        coordinate_candidates = tuple(
            SetProfileCandidate(
                state=replace(
                    baseline.state,
                    main_stat_layout_id=layout_id,
                ),
                profile_id=self.request.baseline_profile_id,
            )
            for baseline in baseline_candidates
            for layout_id in coordinate_layouts
        )
        coordinate_phase = self._evaluate_phase(
            coordinate_candidates,
            baseline_candidates=baseline_candidates,
            layout_catalog=coordinate_catalog,
            scheduler_budget=self.request.coordinate_scheduler_budget,
            deadline=deadline,
            incomplete_status=GcsimMainLayoutScanStatus.INCOMPLETE_COORDINATES,
        )
        if coordinate_phase.status is not None:
            return self._terminal(
                started,
                coordinate_phase.status,
                coordinate_phase.stop_reason,
                coordinate_candidate_count=len(coordinate_candidates),
                combination_candidate_count=0,
                coordinate_request_count=coordinate_phase.request_count,
                combination_request_count=0,
                coordinate_evaluations=coordinate_phase.evaluations,
                coordinate_request_identities=coordinate_phase.request_identities,
                coordinate_batch=coordinate_phase.batch,
            )

        chosen_values = _select_coordinate_values(
            coordinate_phase.evaluations,
            wearer_ids=self.request.wearer_ids,
            seed_layout=self.request.seed_layout,
            max_values=self.request.scan_budget.max_values_per_slot,
        )
        combination_catalog: dict[
            str, dict[str, GcsimFiveStarMainStatLayout]
        ] = {}
        combination_candidates: list[SetProfileCandidate] = []
        for baseline in baseline_candidates:
            wearer = baseline.state.wearer_id
            value_map = dict(chosen_values[wearer])
            layouts = {
                _layout_id(layout): layout
                for layout in (
                    GcsimFiveStarMainStatLayout(sands=sands, goblet=goblet, circlet=circlet)
                    for sands, goblet, circlet in product(
                        value_map["sands"],
                        value_map["goblet"],
                        value_map["circlet"],
                    )
                )
            }
            layouts.setdefault(seed_id, self.request.seed_layout)
            combination_catalog[wearer] = layouts
            combination_candidates.extend(
                SetProfileCandidate(
                    state=replace(baseline.state, main_stat_layout_id=layout_id),
                    profile_id=self.request.baseline_profile_id,
                )
                for layout_id in layouts
            )
        combination_tuple = tuple(combination_candidates)
        combination_phase = self._evaluate_phase(
            combination_tuple,
            baseline_candidates=baseline_candidates,
            layout_catalog=combination_catalog,
            scheduler_budget=self.request.combination_scheduler_budget,
            deadline=deadline,
            incomplete_status=GcsimMainLayoutScanStatus.INCOMPLETE_COMBINATIONS,
        )
        if combination_phase.status is not None:
            return self._terminal(
                started,
                combination_phase.status,
                combination_phase.stop_reason,
                coordinate_candidate_count=len(coordinate_candidates),
                combination_candidate_count=len(combination_tuple),
                coordinate_request_count=coordinate_phase.request_count,
                combination_request_count=combination_phase.request_count,
                coordinate_evaluations=coordinate_phase.evaluations,
                combination_evaluations=combination_phase.evaluations,
                coordinate_request_identities=coordinate_phase.request_identities,
                combination_request_identities=combination_phase.request_identities,
                coordinate_batch=coordinate_phase.batch,
                combination_batch=combination_phase.batch,
            )

        if self._clock() >= deadline:
            return self._terminal(
                started,
                GcsimMainLayoutScanStatus.DEADLINE_REACHED,
                "deadline_before_layout_selection",
                coordinate_candidate_count=len(coordinate_candidates),
                combination_candidate_count=len(combination_tuple),
                coordinate_request_count=coordinate_phase.request_count,
                combination_request_count=combination_phase.request_count,
                coordinate_evaluations=coordinate_phase.evaluations,
                combination_evaluations=combination_phase.evaluations,
                coordinate_request_identities=coordinate_phase.request_identities,
                combination_request_identities=combination_phase.request_identities,
                coordinate_batch=coordinate_phase.batch,
                combination_batch=combination_phase.batch,
            )

        selections: list[GcsimWearerLayoutSelection] = []
        for wearer in self.request.wearer_ids:
            wearer_evaluations = tuple(
                sorted(
                    (
                        evaluation
                        for evaluation in combination_phase.evaluations
                        if evaluation.candidate.state.wearer_id == wearer
                    ),
                    key=_evaluation_rank,
                )
            )
            finalists = wearer_evaluations[
                : self.request.scan_budget.max_layouts_per_wearer
            ]
            selections.append(
                GcsimWearerLayoutSelection(
                    wearer_id=wearer,
                    best_layout_id=finalists[0].candidate.state.main_stat_layout_id,
                    layouts=tuple(
                        (
                            evaluation.candidate.state.main_stat_layout_id,
                            combination_catalog[wearer][
                                evaluation.candidate.state.main_stat_layout_id
                            ],
                        )
                        for evaluation in finalists
                    ),
                    selected_slot_values=chosen_values[wearer],
                )
            )
        if self._cancel_event.is_set() or self._clock() >= deadline:
            return self._terminal(
                started,
                (
                    GcsimMainLayoutScanStatus.CANCELLED
                    if self._cancel_event.is_set()
                    else GcsimMainLayoutScanStatus.DEADLINE_REACHED
                ),
                (
                    "cancelled_during_layout_selection"
                    if self._cancel_event.is_set()
                    else "deadline_during_layout_selection"
                ),
                coordinate_candidate_count=len(coordinate_candidates),
                combination_candidate_count=len(combination_tuple),
                coordinate_request_count=coordinate_phase.request_count,
                combination_request_count=combination_phase.request_count,
                coordinate_evaluations=coordinate_phase.evaluations,
                combination_evaluations=combination_phase.evaluations,
                coordinate_request_identities=coordinate_phase.request_identities,
                combination_request_identities=combination_phase.request_identities,
                coordinate_batch=coordinate_phase.batch,
                combination_batch=combination_phase.batch,
            )
        return self._terminal(
            started,
            GcsimMainLayoutScanStatus.COMPLETED,
            "bounded_layouts_selected",
            coordinate_candidate_count=len(coordinate_candidates),
            combination_candidate_count=len(combination_tuple),
            coordinate_request_count=coordinate_phase.request_count,
            combination_request_count=combination_phase.request_count,
            selections=tuple(selections),
            coordinate_evaluations=coordinate_phase.evaluations,
            combination_evaluations=combination_phase.evaluations,
            coordinate_request_identities=coordinate_phase.request_identities,
            combination_request_identities=combination_phase.request_identities,
            coordinate_batch=coordinate_phase.batch,
            combination_batch=combination_phase.batch,
        )

    def _evaluate_phase(
        self,
        candidates: tuple[SetProfileCandidate, ...],
        *,
        baseline_candidates: tuple[SetProfileCandidate, ...],
        layout_catalog: Mapping[str, Mapping[str, GcsimFiveStarMainStatLayout]],
        scheduler_budget: GcsimFarmingSchedulerBudget,
        deadline: float,
        incomplete_status: GcsimMainLayoutScanStatus,
    ) -> _PhaseResult:
        proof_by_key: dict[tuple, GcsimFarmingMaterializedProbe] = {}
        probe_by_candidate: dict[tuple[str, str, str, str, str], tuple] = {}
        for candidate in candidates:
            if self._cancel_event.is_set():
                return _PhaseResult(
                    candidates,
                    (),
                    len(proof_by_key),
                    None,
                    GcsimMainLayoutScanStatus.CANCELLED,
                    "cancelled_during_layout_materialization",
                )
            if self._clock() >= deadline:
                return _PhaseResult(
                    candidates,
                    (),
                    len(proof_by_key),
                    None,
                    GcsimMainLayoutScanStatus.DEADLINE_REACHED,
                    "deadline_during_layout_materialization",
                )
            other_baselines = tuple(
                baseline
                for baseline in baseline_candidates
                if baseline.state.wearer_id != candidate.state.wearer_id
            )
            proof = materialize_gcsim_one_wearer_candidate(
                self.request.prepared_config_text,
                candidate=candidate,
                frozen_baseline_states=other_baselines,
                wearer_ids=self.request.wearer_ids,
                layout_catalog=layout_catalog,
                profile_bank=self.request.profile_bank,
                engine_context=self.request.engine_context,
                fidelity=self.request.fidelity,
                reference_weights=self.request.reference_weights,
                environment=self.request.environment,
                environment_is_frozen=True,
            )
            probe_by_candidate[candidate.key] = proof.candidate_keys
            proof_by_key.setdefault(proof.candidate_keys, proof)
        requests = tuple(
            proof.build_evaluator_request(
                engine_context=self.request.engine_context,
                timeout_seconds=self.request.scan_budget.candidate_timeout_seconds,
                environment=self.request.environment,
            )
            for proof in proof_by_key.values()
        )
        remaining = deadline - self._clock()
        if remaining <= 0:
            return _PhaseResult(
                candidates,
                (),
                len(requests),
                None,
                GcsimMainLayoutScanStatus.DEADLINE_REACHED,
                "deadline_before_layout_scheduler",
            )
        effective_budget = replace(
            scheduler_budget,
            overall_deadline_seconds=min(
                scheduler_budget.overall_deadline_seconds,
                remaining,
            ),
        )
        scheduler = self._make_scheduler(requests, effective_budget)
        if self._cancel_event.is_set() or self._clock() >= deadline:
            scheduler.cancel()
            return _PhaseResult(
                candidates,
                (),
                len(requests),
                None,
                (
                    GcsimMainLayoutScanStatus.CANCELLED
                    if self._cancel_event.is_set()
                    else GcsimMainLayoutScanStatus.DEADLINE_REACHED
                ),
                (
                    "cancelled_after_layout_scheduler_factory"
                    if self._cancel_event.is_set()
                    else "deadline_after_layout_scheduler_factory"
                ),
            )
        with self._lock:
            self._active_scheduler = scheduler
        try:
            if self._cancel_event.is_set():
                scheduler.cancel()
            batch = scheduler.run()
        finally:
            with self._lock:
                if self._active_scheduler is scheduler:
                    self._active_scheduler = None
        _validate_batch(requests, batch)
        result_by_key = {result.candidate_keys: result for result in batch.results}
        signatures = {proof.investment_signature for proof in proof_by_key.values()}
        if len(signatures) != 1:
            raise GcsimMainLayoutScanError(
                "layout probes do not share one investment signature"
            )
        investment_signature = next(iter(signatures))
        evaluations = tuple(
            CandidateEvaluation(
                candidate=candidate,
                expected_dps=float(result_by_key[probe_by_candidate[candidate.key]].summary.dps_mean),
                standard_error=result_by_key[
                    probe_by_candidate[candidate.key]
                ].summary.dps_se,
                investment_signature=investment_signature,
            )
            for candidate in candidates
            if result_by_key[probe_by_candidate[candidate.key]].success
        )
        request_identities = tuple(
            result_by_key[
                probe_by_candidate[evaluation.candidate.key]
            ].request_identity_sha256
            for evaluation in evaluations
        )
        if self._cancel_event.is_set() or batch.status is GcsimFarmingBatchStatus.CANCELLED:
            status = GcsimMainLayoutScanStatus.CANCELLED
            stop_reason = "layout_scheduler_cancelled"
        elif (
            batch.status is GcsimFarmingBatchStatus.DEADLINE_REACHED
            or self._clock() >= deadline
        ):
            status = GcsimMainLayoutScanStatus.DEADLINE_REACHED
            stop_reason = "layout_scheduler_deadline"
        elif len(evaluations) != len(candidates):
            status = incomplete_status
            stop_reason = "layout_phase_incomplete"
        else:
            status = None
            stop_reason = ""
        return _PhaseResult(
            candidates,
            evaluations,
            len(requests),
            batch,
            status,
            stop_reason,
            request_identities,
        )

    def _make_scheduler(self, requests, budget):
        if self._scheduler_factory is not None:
            scheduler = self._scheduler_factory(requests, budget)
        else:
            scheduler = GcsimFarmingEvaluationScheduler(
                requests,
                budget,
                cache_store=self._cache_store,
                enable_cache=self._enable_cache,
                session_factory=self._session_factory,
            )
        if not hasattr(scheduler, "run") or not hasattr(scheduler, "cancel"):
            raise GcsimMainLayoutScanError(
                "scheduler factory returned an invalid scheduler"
            )
        return scheduler

    def _terminal(self, started, status, stop_reason, **kwargs):
        return GcsimMainLayoutScanResult(
            status=status,
            stop_reason=stop_reason,
            elapsed_seconds=max(self._clock() - started, 0.0),
            scan_budget_snapshot=self.request.scan_budget,
            seed_layout_snapshot=self.request.seed_layout,
            **kwargs,
        )


def _coordinate_layouts(
    seed: GcsimFiveStarMainStatLayout,
) -> dict[str, GcsimFiveStarMainStatLayout]:
    layouts = { _layout_id(seed): seed }
    for sands in LEGAL_FIVE_STAR_SANDS_MAIN_STATS:
        layout = replace(seed, sands=sands)
        layouts[_layout_id(layout)] = layout
    for goblet in LEGAL_FIVE_STAR_GOBLET_MAIN_STATS:
        layout = replace(seed, goblet=goblet)
        layouts[_layout_id(layout)] = layout
    for circlet in LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS:
        layout = replace(seed, circlet=circlet)
        layouts[_layout_id(layout)] = layout
    return dict(sorted(layouts.items()))


def _select_coordinate_values(
    evaluations: Sequence[CandidateEvaluation],
    *,
    wearer_ids: Sequence[str],
    seed_layout: GcsimFiveStarMainStatLayout,
    max_values: int,
) -> dict[str, tuple[tuple[str, tuple[str, ...]], ...]]:
    layout_by_id = _coordinate_layouts(seed_layout)
    legal_by_slot = {
        "sands": LEGAL_FIVE_STAR_SANDS_MAIN_STATS,
        "goblet": LEGAL_FIVE_STAR_GOBLET_MAIN_STATS,
        "circlet": LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS,
    }
    evaluation_by_pair = {
        (
            evaluation.candidate.state.wearer_id,
            evaluation.candidate.state.main_stat_layout_id,
        ): evaluation
        for evaluation in evaluations
    }
    result = {}
    for wearer in wearer_ids:
        rows = []
        for slot, legal_values in legal_by_slot.items():
            ranked = []
            for value in legal_values:
                layout = replace(seed_layout, **{slot: value})
                evaluation = evaluation_by_pair[(wearer, _layout_id(layout))]
                ranked.append((value, evaluation))
            ranked.sort(key=lambda item: (*_evaluation_rank(item[1]), item[0]))
            rows.append((slot, tuple(value for value, _evaluation in ranked[:max_values])))
        result[wearer] = tuple(rows)
    return result


def _evaluation_rank(evaluation: CandidateEvaluation):
    return (
        -evaluation.expected_dps,
        float("inf") if evaluation.standard_error is None else evaluation.standard_error,
        evaluation.candidate.state.main_stat_layout_id,
    )


def _layout_id(layout: GcsimFiveStarMainStatLayout) -> str:
    def token(value: str) -> str:
        return value.replace("%", "pct")

    return f"main/{token(layout.sands)}-{token(layout.goblet)}-{token(layout.circlet)}"


def _validate_batch(requests, batch) -> None:
    if not isinstance(batch, GcsimFarmingBatchResult):
        raise GcsimMainLayoutScanError("scheduler returned a non-typed batch")
    if len(batch.results) != len(requests):
        raise GcsimMainLayoutScanError(
            "scheduler did not return one result per layout request"
        )
    for request, result in zip(requests, batch.results, strict=True):
        if not isinstance(result, GcsimFarmingEvaluationResult):
            raise GcsimMainLayoutScanError(
                "scheduler returned a non-typed layout result"
            )
        identity = request.identity
        if (
            result.candidate_keys != request.candidate_keys
            or result.request_identity_sha256 != identity.identity_sha256
            or result.cache_key != request.cache_identity.cache_key
            or result.comparison_context_sha256 != request.comparison_context_sha256
            or result.expected_iterations != request.expected_iterations
            or result.engine_binding_sha256 != identity.engine_binding_sha256
            or result.source_config_sha256 != identity.source_config_sha256
            or (
                result.artifact_sha256 != identity.artifact_sha256
                and result.status
                is not GcsimFarmingEvaluationStatus.ARTIFACT_IDENTITY_MISMATCH
            )
        ):
            raise GcsimMainLayoutScanError(
                "layout result provenance/order does not match its request"
            )


def _validate_layout_evaluation_projection(
    evaluations: Sequence[CandidateEvaluation],
    request_identities: Sequence[str],
    batch: GcsimFarmingBatchResult | None,
    *,
    phase: str,
) -> None:
    if len(request_identities) != len(evaluations):
        raise ValueError(
            f"{phase} evaluation/request-identity projection length differs"
        )
    if any(
        not isinstance(identity, str)
        or len(identity) != 64
        or any(character not in "0123456789abcdef" for character in identity)
        for identity in request_identities
    ):
        raise ValueError(f"{phase} request identities must be SHA-256 digests")
    if not evaluations:
        return
    if batch is None:
        raise ValueError(f"{phase} evaluations require batch evidence")
    result_by_identity = {
        result.request_identity_sha256: result for result in batch.results
    }
    if len(result_by_identity) != len(batch.results):
        raise ValueError(f"{phase} batch contains duplicate request identities")
    for evaluation, request_identity in zip(
        evaluations,
        request_identities,
        strict=True,
    ):
        result = result_by_identity.get(request_identity)
        if (
            result is None
            or not result.success
            or evaluation.candidate.key not in result.candidate_keys
            or evaluation.expected_dps != result.summary.dps_mean
            or evaluation.standard_error != result.summary.dps_se
        ):
            raise ValueError(
                f"{phase} logical evaluation does not project from its batch result"
            )


def run_gcsim_main_layout_scan(
    request: GcsimMainLayoutScanRequest,
    **session_options,
) -> GcsimMainLayoutScanResult:
    return GcsimMainLayoutScanSession(request, **session_options).run()


__all__ = [
    "GCSIM_GENERIC_MAIN_LAYOUT_SEED",
    "GcsimMainLayoutScanBudget",
    "GcsimMainLayoutScanError",
    "GcsimMainLayoutScanRequest",
    "GcsimMainLayoutScanResult",
    "GcsimMainLayoutScanSession",
    "GcsimMainLayoutScanStatus",
    "GcsimWearerLayoutSelection",
    "run_gcsim_main_layout_scan",
]
