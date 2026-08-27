"""Quality-first full-team equal-investment anchors for optimizer M8A.

M4 response probes require the other three wearers to be frozen.  This module
chooses several full-team reference states without reading equipped artifacts:
small domains are evaluated exhaustively, while larger domains reuse the
tested recall-first full-team composer with explicit structural seeds.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from itertools import product
import json
from math import isfinite, prod
from time import monotonic
from typing import Callable, Mapping, Sequence

from .farming_search import (
    CandidateEvaluation,
    FourPieceSetState,
    SearchSurvivor,
    SetProfileCandidate,
)
from .farming_team_search import (
    FullTeamBatchSimulator,
    FullTeamCandidatePool,
    FullTeamComposerBudget,
    FullTeamComposerRequest,
    FullTeamComposerResult,
    FullTeamEvaluationRecord,
    FullTeamProbeState,
    TEAM_SEARCH_CANCELLED,
    TEAM_SEARCH_DEADLINE_REACHED,
    compose_full_team_four_piece_states,
)
from .optimizer_config import GcsimFiveStarMainStatLayout
from .optimizer_main_response import (
    GcsimOptimizerFourPieceMainDomain,
    gcsim_optimizer_main_layout_id,
)
from .optimizer_product_contracts import (
    GcsimFourPieceTargetPackage,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerTarget,
)
from .optimizer_run_input import GcsimOptimizerRunInput


GCSIM_OPTIMIZER_REFERENCE_ANCHOR_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_REFERENCE_PROFILE_ID = "baseline"
GCSIM_OPTIMIZER_REFERENCE_INVESTMENT_SIGNATURE = "m8a_equal_investment"


class GcsimOptimizerReferenceAnchorError(ValueError):
    """Raised when the M8A reference domain or evidence is incoherent."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerReferenceAnchorPlan:
    exact_joint_state_limit: int = 4096
    max_anchors: int = 8
    composer_budget: FullTeamComposerBudget = FullTeamComposerBudget(
        max_total_evaluations=256,
        max_seed_evaluations=64,
        max_rounds=8,
        max_coordinate_evaluations_per_round=16,
        max_pair_evaluations_per_round=12,
        pair_frontier_per_wearer=4,
        beam_width=16,
        beam_top_slots=6,
        beam_uncertain_slots=4,
        beam_novelty_slots=6,
        max_physical_finalists=16,
        confidence_sigma=2.0,
        relative_uncertainty_margin=0.02,
        max_seconds=600.0,
        per_evaluation_timeout_seconds=120.0,
    )
    schema_version: int = GCSIM_OPTIMIZER_REFERENCE_ANCHOR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in ("exact_joint_state_limit", "max_anchors"):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise GcsimOptimizerReferenceAnchorError(
                    f"{field_name} must be a positive integer"
                )
        if not isinstance(self.composer_budget, FullTeamComposerBudget):
            raise GcsimOptimizerReferenceAnchorError(
                "composer_budget must be typed"
            )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerReferenceAnchorChoice:
    target: GcsimOptimizerWearerTarget
    layout: GcsimFiveStarMainStatLayout
    structural_tags: tuple[str, ...]
    offpiece_slot: str = ""
    schema_version: int = GCSIM_OPTIMIZER_REFERENCE_ANCHOR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.target, GcsimOptimizerWearerTarget):
            raise GcsimOptimizerReferenceAnchorError(
                "reference choice target must be typed"
            )
        if not isinstance(self.target.package, GcsimFourPieceTargetPackage):
            raise GcsimOptimizerReferenceAnchorError(
                "reference choice currently requires a 4p package"
            )
        if not isinstance(self.layout, GcsimFiveStarMainStatLayout):
            raise GcsimOptimizerReferenceAnchorError(
                "reference choice layout must be typed"
            )
        object.__setattr__(
            self,
            "structural_tags",
            tuple(sorted(set(self.structural_tags))),
        )
        if self.offpiece_slot and self.offpiece_slot not in {
            "flower",
            "plume",
            "sands",
            "goblet",
            "circlet",
        }:
            raise GcsimOptimizerReferenceAnchorError(
                "reference offpiece_slot is invalid"
            )

    @property
    def candidate(self) -> SetProfileCandidate:
        return SetProfileCandidate(
            state=FourPieceSetState(
                wearer_id=self.target.wearer.gcsim_character_key,
                set_key=self.target.package.set_ref.gcsim_set_key,
                main_stat_layout_id=gcsim_optimizer_main_layout_id(
                    self.layout
                ),
                offpiece_slot=self.offpiece_slot,
            ),
            profile_id=GCSIM_OPTIMIZER_REFERENCE_PROFILE_ID,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "target": self.target.to_dict(),
            "layout": {
                "sands": self.layout.sands,
                "goblet": self.layout.goblet,
                "circlet": self.layout.circlet,
            },
            "structural_tags": list(self.structural_tags),
            "offpiece_slot": self.offpiece_slot,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerReferenceAnchor:
    rank: int
    choices: tuple[GcsimOptimizerReferenceAnchorChoice, ...]
    dps_mean: float
    dps_standard_error: float | None
    iterations: int
    evidence_sha256: str
    structural_tags: tuple[str, ...]
    schema_version: int = GCSIM_OPTIMIZER_REFERENCE_ANCHOR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if (
            isinstance(self.rank, bool)
            or not isinstance(self.rank, int)
            or self.rank <= 0
        ):
            raise GcsimOptimizerReferenceAnchorError(
                "reference anchor rank must be positive"
            )
        if (
            len(self.choices) != 4
            or tuple(item.target.wearer.team_slot for item in self.choices)
            != (1, 2, 3, 4)
        ):
            raise GcsimOptimizerReferenceAnchorError(
                "reference anchor requires four canonical choices"
            )
        if not isfinite(self.dps_mean) or self.dps_mean < 0:
            raise GcsimOptimizerReferenceAnchorError(
                "reference anchor DPS must be finite and non-negative"
            )
        if self.dps_standard_error is not None and (
            not isfinite(self.dps_standard_error)
            or self.dps_standard_error < 0
        ):
            raise GcsimOptimizerReferenceAnchorError(
                "reference anchor standard error is invalid"
            )
        if (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations <= 0
        ):
            raise GcsimOptimizerReferenceAnchorError(
                "reference anchor iterations must be positive"
            )
        _require_sha256(self.evidence_sha256, "evidence_sha256")
        object.__setattr__(
            self,
            "structural_tags",
            tuple(sorted(set(self.structural_tags))),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "rank": self.rank,
            "choices": [item.to_dict() for item in self.choices],
            "dps_mean": self.dps_mean,
            "dps_standard_error": self.dps_standard_error,
            "iterations": self.iterations,
            "evidence_sha256": self.evidence_sha256,
            "structural_tags": list(self.structural_tags),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerReferenceAnchorCoverage:
    choice_counts_by_wearer: tuple[tuple[int, int], ...]
    raw_joint_state_count: int
    evaluated_state_count: int
    exact_mode: bool
    retained_anchor_count: int
    structural_tags_retained: tuple[str, ...]
    schema_version: int = GCSIM_OPTIMIZER_REFERENCE_ANCHOR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if tuple(slot for slot, _count in self.choice_counts_by_wearer) != (
            1,
            2,
            3,
            4,
        ):
            raise GcsimOptimizerReferenceAnchorError(
                "reference coverage must use canonical team slots"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "choice_counts_by_wearer": dict(
                self.choice_counts_by_wearer
            ),
            "raw_joint_state_count": self.raw_joint_state_count,
            "evaluated_state_count": self.evaluated_state_count,
            "exact_mode": self.exact_mode,
            "retained_anchor_count": self.retained_anchor_count,
            "structural_tags_retained": list(
                self.structural_tags_retained
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerReferenceAnchorResult:
    status: str
    run_input_sha256: str
    evaluation_context_sha256: str
    plan: GcsimOptimizerReferenceAnchorPlan
    anchors: tuple[GcsimOptimizerReferenceAnchor, ...]
    coverage: GcsimOptimizerReferenceAnchorCoverage
    composition: FullTeamComposerResult
    elapsed_seconds: float
    schema_version: int = GCSIM_OPTIMIZER_REFERENCE_ANCHOR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        _require_sha256(self.run_input_sha256, "run_input_sha256")
        _require_sha256(
            self.evaluation_context_sha256,
            "evaluation_context_sha256",
        )
        if not isinstance(self.composition, FullTeamComposerResult):
            raise GcsimOptimizerReferenceAnchorError(
                "reference composition must be typed"
            )
        if tuple(item.rank for item in self.anchors) != tuple(
            range(1, len(self.anchors) + 1)
        ):
            raise GcsimOptimizerReferenceAnchorError(
                "reference anchor ranks must be contiguous"
            )
        if self.status not in {
            "completed",
            "cancelled",
            "deadline_reached",
            "no_success",
        }:
            raise GcsimOptimizerReferenceAnchorError(
                "reference result status is unsupported"
            )

    @property
    def best_anchor(self) -> GcsimOptimizerReferenceAnchor | None:
        return self.anchors[0] if self.anchors else None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "run_input_sha256": self.run_input_sha256,
            "evaluation_context_sha256": self.evaluation_context_sha256,
            "anchors": [item.to_dict() for item in self.anchors],
            "coverage": self.coverage.to_dict(),
            "elapsed_seconds": self.elapsed_seconds,
        }


def discover_gcsim_optimizer_reference_anchors(
    run_input: GcsimOptimizerRunInput,
    *,
    domains: Sequence[GcsimOptimizerFourPieceMainDomain],
    simulator: FullTeamBatchSimulator,
    evaluation_context_sha256: str,
    plan: GcsimOptimizerReferenceAnchorPlan | None = None,
    is_cancelled: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] = monotonic,
) -> GcsimOptimizerReferenceAnchorResult:
    """Evaluate exact-small or structurally diverse large reference domains."""

    started = clock()
    request_plan = plan or GcsimOptimizerReferenceAnchorPlan()
    _require_sha256(
        evaluation_context_sha256,
        "evaluation_context_sha256",
    )
    choices_by_wearer, choice_by_candidate = _build_choice_pools(
        run_input,
        domains,
    )
    raw_count = prod(len(items) for items in choices_by_wearer)
    exact = (
        raw_count <= request_plan.exact_joint_state_limit
        and raw_count
        <= request_plan.composer_budget.max_total_evaluations
    )
    candidate_pools = _composer_candidate_pools(choices_by_wearer)
    explicit_seeds = (
        tuple(
            FullTeamProbeState(
                tuple(choice.candidate for choice in combination)
            )
            for combination in product(*choices_by_wearer)
        )
        if exact
        else _diverse_seeds(choices_by_wearer)
    )
    budget = (
        _exact_budget(
            request_plan.composer_budget,
            state_count=raw_count,
            max_anchors=request_plan.max_anchors,
        )
        if exact
        else replace(
            request_plan.composer_budget,
            max_physical_finalists=max(
                request_plan.composer_budget.max_physical_finalists,
                request_plan.max_anchors,
            ),
        )
    )
    composition = compose_full_team_four_piece_states(
        FullTeamComposerRequest(
            evaluation_context_sha256=evaluation_context_sha256,
            wearer_ids=tuple(
                item.gcsim_character_key
                for item in run_input.request.source_simulation.wearers
            ),
            candidate_pools=candidate_pools,
            budget=budget,
            explicit_seeds=explicit_seeds,
        ),
        simulator,
        is_cancelled=is_cancelled,
        clock=clock,
    )
    selected_records = _select_anchor_records(
        composition.records,
        max_anchors=request_plan.max_anchors,
    )
    required_package_keys = {
        (
            choice.target.wearer.gcsim_character_key,
            choice.target.package.set_ref.gcsim_set_key,
        )
        for values in choices_by_wearer
        for choice in values
    }
    retained_package_keys = {
        (
            choice.state.wearer_id,
            choice.state.set_key,
        )
        for record in selected_records
        for choice in record.request.state.choices
    }
    if selected_records and not required_package_keys.issubset(
        retained_package_keys
    ):
        raise GcsimOptimizerReferenceAnchorError(
            "max_anchors cannot retain every selected package context"
        )
    anchors = tuple(
        _anchor_from_record(
            rank=index,
            record=record,
            choice_by_candidate=choice_by_candidate,
            composition=composition,
        )
        for index, record in enumerate(selected_records, start=1)
    )
    status = (
        "cancelled"
        if composition.stop_reason == TEAM_SEARCH_CANCELLED
        else (
            "deadline_reached"
            if composition.stop_reason == TEAM_SEARCH_DEADLINE_REACHED
            else ("completed" if anchors else "no_success")
        )
    )
    tags = tuple(
        sorted(
            {
                tag
                for anchor in anchors
                for tag in anchor.structural_tags
            }
        )
    )
    return GcsimOptimizerReferenceAnchorResult(
        status=status,
        run_input_sha256=run_input.run_input_sha256,
        evaluation_context_sha256=evaluation_context_sha256,
        plan=request_plan,
        anchors=anchors,
        coverage=GcsimOptimizerReferenceAnchorCoverage(
            choice_counts_by_wearer=tuple(
                (
                    wearer.team_slot,
                    len(choices_by_wearer[wearer.team_slot - 1]),
                )
                for wearer in run_input.request.source_simulation.wearers
            ),
            raw_joint_state_count=raw_count,
            evaluated_state_count=len(composition.records),
            exact_mode=exact,
            retained_anchor_count=len(anchors),
            structural_tags_retained=tags,
        ),
        composition=composition,
        elapsed_seconds=max(clock() - started, 0.0),
    )


def build_gcsim_optimizer_reference_layout_catalog(
    domains: Sequence[GcsimOptimizerFourPieceMainDomain],
) -> Mapping[str, Mapping[str, GcsimFiveStarMainStatLayout]]:
    result: dict[str, dict[str, GcsimFiveStarMainStatLayout]] = {}
    for domain in domains:
        wearer = domain.wearer.gcsim_character_key
        rows = result.setdefault(wearer, {})
        for reachable in domain.reachable_layouts:
            layout_id = reachable.layout_id
            previous = rows.setdefault(layout_id, reachable.layout)
            if previous != reachable.layout:
                raise GcsimOptimizerReferenceAnchorError(
                    "layout identity collision in reference domain"
                )
    return {
        wearer: dict(sorted(rows.items()))
        for wearer, rows in sorted(result.items())
    }


def _build_choice_pools(
    run_input: GcsimOptimizerRunInput,
    domains: Sequence[GcsimOptimizerFourPieceMainDomain],
) -> tuple[
    tuple[tuple[GcsimOptimizerReferenceAnchorChoice, ...], ...],
    Mapping[
        tuple[str, str, str, str, str],
        GcsimOptimizerReferenceAnchorChoice,
    ],
]:
    by_wearer: dict[
        GcsimOptimizerWearerIdentity,
        dict[
            tuple[str, str],
            GcsimOptimizerReferenceAnchorChoice,
        ],
    ] = {
        wearer: {}
        for wearer in run_input.request.source_simulation.wearers
    }
    for domain in domains:
        if domain.run_input_sha256 != run_input.run_input_sha256:
            raise GcsimOptimizerReferenceAnchorError(
                "reference domain belongs to another run input"
            )
        if domain.wearer not in by_wearer:
            raise GcsimOptimizerReferenceAnchorError(
                "reference domain wearer is outside the frozen team"
            )
        target = GcsimOptimizerWearerTarget(
            wearer=domain.wearer,
            package=domain.package,
        )
        for reachable in domain.reachable_layouts:
            choice = GcsimOptimizerReferenceAnchorChoice(
                target=target,
                layout=reachable.layout,
                structural_tags=_layout_tags(reachable.layout),
                offpiece_slot=_reference_offpiece_slot(
                    run_input,
                    domain,
                ),
            )
            key = (
                domain.package.set_ref.gcsim_set_key,
                reachable.layout_id,
            )
            by_wearer[domain.wearer].setdefault(key, choice)
    rows = tuple(
        tuple(
            sorted(
                by_wearer[wearer].values(),
                key=lambda item: item.candidate.key,
            )
        )
        for wearer in run_input.request.source_simulation.wearers
    )
    if any(not values for values in rows):
        raise GcsimOptimizerReferenceAnchorError(
            "reference domains must provide choices for all four wearers"
        )
    choice_by_candidate = {
        choice.candidate.key: choice
        for values in rows
        for choice in values
    }
    return rows, choice_by_candidate


def _composer_candidate_pools(
    choices_by_wearer: Sequence[
        Sequence[GcsimOptimizerReferenceAnchorChoice]
    ],
) -> tuple[FullTeamCandidatePool, ...]:
    return tuple(
        FullTeamCandidatePool(
            wearer_id=choices[0].target.wearer.gcsim_character_key,
            survivors=tuple(
                SearchSurvivor(
                    evaluation=CandidateEvaluation(
                        candidate=choice.candidate,
                        expected_dps=0.0,
                        investment_signature=(
                            GCSIM_OPTIMIZER_REFERENCE_INVESTMENT_SIGNATURE
                        ),
                        standard_error=0.0,
                        novelty_score=float(len(choice.structural_tags)),
                        novelty_tags=choice.structural_tags,
                    ),
                    reasons=("required_profile",),
                )
                for choice in choices
            ),
        )
        for choices in choices_by_wearer
    )


def _diverse_seeds(
    choices_by_wearer: Sequence[
        Sequence[GcsimOptimizerReferenceAnchorChoice]
    ],
) -> tuple[FullTeamProbeState, ...]:
    result: dict[
        tuple[tuple[str, str, str, str, str], ...],
        FullTeamProbeState,
    ] = {}

    def add(
        choices: Sequence[GcsimOptimizerReferenceAnchorChoice],
    ) -> None:
        state = FullTeamProbeState(
            tuple(item.candidate for item in choices)
        )
        result.setdefault(state.probe_key, state)

    canonical = tuple(items[0] for items in choices_by_wearer)
    add(canonical)
    package_choices_by_wearer = []
    for items in choices_by_wearer:
        by_package = {}
        for choice in items:
            by_package.setdefault(
                choice.target.package.set_ref.gcsim_set_key,
                choice,
            )
        package_choices_by_wearer.append(
            tuple(by_package[key] for key in sorted(by_package))
        )
    for index in range(
        max(len(items) for items in package_choices_by_wearer)
    ):
        add(
            tuple(
                items[index % len(items)]
                for items in package_choices_by_wearer
            )
        )
    for wearer_index, items in enumerate(choices_by_wearer):
        for choice in items:
            row = list(canonical)
            row[wearer_index] = choice
            add(row)
    for tag in ("em", "support", "unusual", "damage"):
        row = []
        for items in choices_by_wearer:
            row.append(
                next(
                    (
                        choice
                        for choice in items
                        if tag in choice.structural_tags
                    ),
                    items[0],
                )
            )
        add(row)
    maximum_width = max(len(items) for items in choices_by_wearer)
    for index in range(1, maximum_width):
        add(
            tuple(
                items[index % len(items)]
                for items in choices_by_wearer
            )
        )
    return tuple(result.values())


def _exact_budget(
    source: FullTeamComposerBudget,
    *,
    state_count: int,
    max_anchors: int,
) -> FullTeamComposerBudget:
    return replace(
        source,
        max_total_evaluations=state_count,
        max_seed_evaluations=state_count,
        max_rounds=1,
        max_coordinate_evaluations_per_round=0,
        max_pair_evaluations_per_round=0,
        beam_width=max(source.beam_width, max_anchors),
        beam_top_slots=min(
            max(source.beam_top_slots, max_anchors),
            max(source.beam_width, max_anchors),
        ),
        beam_uncertain_slots=0,
        beam_novelty_slots=0,
        max_physical_finalists=max(max_anchors, 1),
    )


def _select_anchor_records(
    records: Sequence[FullTeamEvaluationRecord],
    *,
    max_anchors: int,
) -> tuple[FullTeamEvaluationRecord, ...]:
    passed = tuple(
        sorted(
            (
                item
                for item in records
                if item.metrics.status == "passed"
            ),
            key=lambda item: (
                -float(item.metrics.dps_mean),
                item.probe_key,
            ),
        )
    )
    selected: list[FullTeamEvaluationRecord] = []
    seen: set[tuple] = set()

    def add(item: FullTeamEvaluationRecord) -> None:
        if len(selected) >= max_anchors or item.probe_key in seen:
            return
        seen.add(item.probe_key)
        selected.append(item)

    if passed:
        add(passed[0])
    required_packages = {
        (
            choice.state.wearer_id,
            choice.state.set_key,
        )
        for item in passed
        for choice in item.request.state.choices
    }
    covered_packages = {
        (
            choice.state.wearer_id,
            choice.state.set_key,
        )
        for item in selected
        for choice in item.request.state.choices
    }
    while (
        required_packages.difference(covered_packages)
        and len(selected) < max_anchors
    ):
        uncovered = required_packages.difference(covered_packages)
        candidate = max(
            (
                item
                for item in passed
                if any(
                    (
                        choice.state.wearer_id,
                        choice.state.set_key,
                    )
                    in uncovered
                    for choice in item.request.state.choices
                )
            ),
            key=lambda item: (
                sum(
                    (
                        choice.state.wearer_id,
                        choice.state.set_key,
                    )
                    in uncovered
                    for choice in item.request.state.choices
                ),
                float(item.metrics.dps_mean),
                tuple(reversed(item.probe_key)),
            ),
        )
        add(candidate)
        covered_packages.update(
            (
                choice.state.wearer_id,
                choice.state.set_key,
            )
            for choice in candidate.request.state.choices
        )
    for tag in ("em", "support", "unusual"):
        candidate = next(
            (
                item
                for item in passed
                if tag in item.branch_tags
            ),
            None,
        )
        if candidate is not None:
            add(candidate)
    for item in passed:
        add(item)
    return tuple(
        sorted(
            selected,
            key=lambda item: (
                -float(item.metrics.dps_mean),
                item.probe_key,
            ),
        )
    )


def _anchor_from_record(
    *,
    rank: int,
    record: FullTeamEvaluationRecord,
    choice_by_candidate: Mapping[
        tuple[str, str, str, str, str],
        GcsimOptimizerReferenceAnchorChoice,
    ],
    composition: FullTeamComposerResult,
) -> GcsimOptimizerReferenceAnchor:
    choices = tuple(
        choice_by_candidate[item.key]
        for item in record.request.state.choices
    )
    payload = {
        "schema_version": GCSIM_OPTIMIZER_REFERENCE_ANCHOR_SCHEMA_VERSION,
        "composition_request_sha256": composition.request_sha256,
        "probe_key": record.probe_key,
        "metrics": {
            "dps_mean": record.metrics.dps_mean,
            "dps_se": record.metrics.dps_se,
            "iterations": record.metrics.iterations,
        },
    }
    assert record.metrics.dps_mean is not None
    assert record.metrics.iterations is not None
    return GcsimOptimizerReferenceAnchor(
        rank=rank,
        choices=choices,
        dps_mean=record.metrics.dps_mean,
        dps_standard_error=record.metrics.dps_se,
        iterations=record.metrics.iterations,
        evidence_sha256=_canonical_sha256(payload),
        structural_tags=tuple(
            tag
            for choice in choices
            for tag in choice.structural_tags
        ),
    )


def _layout_tags(
    layout: GcsimFiveStarMainStatLayout,
) -> tuple[str, ...]:
    values = (layout.sands, layout.goblet, layout.circlet)
    tags = {"damage"}
    if "em" in values:
        tags.add("em")
    if (
        layout.circlet == "heal"
        or values.count("hp%") >= 2
        or values.count("def%") >= 2
    ):
        tags.add("support")
    if (
        layout.sands not in {"atk%", "hp%", "def%", "er", "em"}
        or layout.goblet
        not in {
            "atk%",
            "hp%",
            "def%",
            "em",
            "phys%",
            "pyro%",
            "hydro%",
            "electro%",
            "cryo%",
            "anemo%",
            "geo%",
            "dendro%",
        }
        or layout.circlet not in {"cr", "cd", "heal", "atk%", "hp%", "def%", "em"}
    ):
        tags.add("unusual")
    return tuple(sorted(tags))


def _reference_offpiece_slot(
    run_input: GcsimOptimizerRunInput,
    domain: GcsimOptimizerFourPieceMainDomain,
) -> str:
    capability = run_input.set_capability(
        domain.package.set_ref.gcsim_set_key
    )
    if capability is None or capability.max_rarity >= 5:
        return ""
    target_uid = domain.package.set_ref.set_uid
    eligible_by_slot = dict(domain.eligible_artifact_ids_by_slot)
    for slot in ("flower", "plume", "sands", "goblet", "circlet"):
        if any(
            artifact is not None
            and artifact.rarity == 5
            and artifact.set_uid != target_uid
            for artifact in (
                run_input.artifact_by_id(artifact_id)
                for artifact_id in eligible_by_slot[slot]
            )
        ):
            return slot
    # Reference states are inventory-independent; the real M5 domain remains
    # database-bound.  A canonical theoretical offpiece is still required by
    # the existing equal-investment renderer for an explicitly allowed 4-star
    # set.
    return "flower"


def _canonical_sha256(value: object) -> str:
    text = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require_sha256(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GcsimOptimizerReferenceAnchorError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


def _require_schema(value: object) -> None:
    if value != GCSIM_OPTIMIZER_REFERENCE_ANCHOR_SCHEMA_VERSION:
        raise GcsimOptimizerReferenceAnchorError(
            "unsupported reference-anchor schema version"
        )


__all__ = [
    "GCSIM_OPTIMIZER_REFERENCE_ANCHOR_SCHEMA_VERSION",
    "GCSIM_OPTIMIZER_REFERENCE_INVESTMENT_SIGNATURE",
    "GCSIM_OPTIMIZER_REFERENCE_PROFILE_ID",
    "GcsimOptimizerReferenceAnchor",
    "GcsimOptimizerReferenceAnchorChoice",
    "GcsimOptimizerReferenceAnchorCoverage",
    "GcsimOptimizerReferenceAnchorError",
    "GcsimOptimizerReferenceAnchorPlan",
    "GcsimOptimizerReferenceAnchorResult",
    "build_gcsim_optimizer_reference_layout_catalog",
    "discover_gcsim_optimizer_reference_anchors",
]
