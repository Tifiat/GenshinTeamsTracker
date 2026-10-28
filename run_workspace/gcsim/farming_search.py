"""Pure orchestration primitives for inventory-independent artifact-set search.

This module deliberately does not call GCSIM, choose artifact main stats, inspect
the account inventory, or claim to solve the final team optimization problem.
It defines the immutable inputs/results used by the future evaluator and the
deterministic, recall-first survivor policy used between cheap screening and
expensive GCSIM optimization.

The evaluator remains responsible for producing profile scores, uncertainty,
and mechanic-derived novelty tags.  Keeping those values outside this module
prevents provisional character or artifact-set knowledge from becoming hidden
hardcoded policy.
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from itertools import combinations
from math import isclose, isfinite
from typing import Callable, Iterable, Mapping, Protocol, Sequence, TypeVar

from .optimizer_config import ARTIFACT_MAIN_STAT_SLOTS


PROFILE_BASELINE = "baseline"
PROFILE_BALANCED = "balanced"
PROFILE_SINGLE_AXIS = "single_axis"
PROFILE_AXIS_PAIR = "axis_pair"

SURVIVOR_TOP_SCORE = "top_score"
SURVIVOR_WEARER_COVERAGE = "wearer_coverage"
SURVIVOR_UNCERTAIN = "uncertain"
SURVIVOR_PROFILE_COVERAGE = "profile_coverage"
SURVIVOR_NOVEL_BRANCH = "novel_branch"
SURVIVOR_BUDGET_FILL = "budget_fill"
SURVIVOR_REQUIRED_PROFILE = "required_profile"


_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class StatAxis:
    """One evaluator-controlled stat direction and its comparable probe step."""

    key: str
    probe_delta: float
    unit: str = ""

    def __post_init__(self) -> None:
        _require_identifier(self.key, field_name="stat axis key")
        if not isfinite(self.probe_delta) or self.probe_delta <= 0:
            raise ValueError("stat axis probe_delta must be finite and positive")


@dataclass(frozen=True, slots=True)
class StatWeight:
    axis_key: str
    weight: float

    def __post_init__(self) -> None:
        _require_identifier(self.axis_key, field_name="stat weight axis_key")
        if not isfinite(self.weight) or self.weight <= 0:
            raise ValueError("stat weight must be finite and positive")


@dataclass(frozen=True, slots=True)
class StatDelta:
    axis_key: str
    value: float

    def __post_init__(self) -> None:
        _require_identifier(self.axis_key, field_name="stat delta axis_key")
        if not isfinite(self.value):
            raise ValueError("stat delta value must be finite")


@dataclass(frozen=True, slots=True)
class StatProfile:
    """A normalized investment direction, independent of any character name."""

    profile_id: str
    kind: str
    weights: tuple[StatWeight, ...] = ()
    focus_axes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        weights = _frozen_tuple(self.weights, field_name="stat profile weights")
        focus_axes = _frozen_tuple(
            self.focus_axes,
            field_name="stat profile focus axes",
        )
        object.__setattr__(self, "weights", weights)
        object.__setattr__(self, "focus_axes", focus_axes)
        _require_identifier(self.profile_id, field_name="profile_id")
        _require_identifier(self.kind, field_name="profile kind")
        _require_instances(
            weights,
            StatWeight,
            field_name="stat profile weights",
        )
        _require_unique(
            (weight.axis_key for weight in weights),
            field_name="stat profile weight axes",
        )
        _require_unique(focus_axes, field_name="stat profile focus axes")
        for axis_key in focus_axes:
            _require_identifier(axis_key, field_name="stat profile focus axis")
        if weights:
            total = sum(weight.weight for weight in weights)
            if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError("non-baseline stat profile weights must sum to 1")
        elif self.kind != PROFILE_BASELINE:
            raise ValueError("only a baseline profile may have no stat weights")

    def weight_for(self, axis_key: str) -> float:
        return next(
            (
                weight.weight
                for weight in self.weights
                if weight.axis_key == axis_key
            ),
            0.0,
        )

    def materialize(
        self,
        axes: Sequence[StatAxis],
        *,
        reference_weights: Sequence[StatWeight],
        exchange_rolls: float = 1.0,
    ) -> tuple[StatDelta, ...]:
        """Materialize a roll-budget-conserving exchange around a reference.

        Profile weights are target roll shares, not free positive stats.  The
        explicit reference is subtracted before stat values are emitted, so
        every non-baseline probe adds and removes the same number of abstract
        rolls.  The baseline profile materializes to no delta by definition.
        """

        if not isfinite(exchange_rolls) or exchange_rolls < 0:
            raise ValueError("exchange_rolls must be finite and non-negative")
        axis_by_key = _axis_index(axes)
        reference = _normalized_weight_index(
            reference_weights,
            axis_by_key=axis_by_key,
            field_name="reference weights",
        )
        target = (
            reference
            if self.kind == PROFILE_BASELINE
            else _normalized_weight_index(
                self.weights,
                axis_by_key=axis_by_key,
                field_name=f"profile {self.profile_id!r} weights",
            )
        )
        deltas = tuple(
            StatDelta(
                axis_key=axis.key,
                value=(
                    axis.probe_delta
                    * (target.get(axis.key, 0.0) - reference.get(axis.key, 0.0))
                    * exchange_rolls
                ),
            )
            for axis in axes
            if not isclose(
                target.get(axis.key, 0.0),
                reference.get(axis.key, 0.0),
                rel_tol=0.0,
                abs_tol=1e-15,
            )
        )
        exchanged_share = sum(
            delta.value / axis_by_key[delta.axis_key].probe_delta
            for delta in deltas
        )
        if not isclose(exchanged_share, 0.0, rel_tol=0.0, abs_tol=1e-12):
            raise AssertionError("profile materialization changed the roll budget")
        return deltas


@dataclass(frozen=True, slots=True)
class StatProfileBank:
    axes: tuple[StatAxis, ...]
    profiles: tuple[StatProfile, ...]

    def __post_init__(self) -> None:
        axes = _frozen_tuple(self.axes, field_name="stat profile bank axes")
        profiles = _frozen_tuple(
            self.profiles,
            field_name="stat profile bank profiles",
        )
        object.__setattr__(self, "axes", axes)
        object.__setattr__(self, "profiles", profiles)
        _require_instances(axes, StatAxis, field_name="stat profile bank axes")
        _require_instances(
            profiles,
            StatProfile,
            field_name="stat profile bank profiles",
        )
        axis_by_key = _axis_index(axes)
        _require_unique(
            (profile.profile_id for profile in profiles),
            field_name="profile ids",
        )
        if not profiles:
            raise ValueError("stat profile bank must contain at least one profile")
        for profile in profiles:
            referenced = {
                *(weight.axis_key for weight in profile.weights),
                *profile.focus_axes,
            }
            unknown = tuple(sorted(referenced.difference(axis_by_key)))
            if unknown:
                raise ValueError(
                    f"profile {profile.profile_id!r} references unknown axes: "
                    f"{unknown!r}"
                )

    def profile(self, profile_id: str) -> StatProfile:
        for profile in self.profiles:
            if profile.profile_id == profile_id:
                return profile
        raise KeyError(profile_id)


def generate_stat_profile_bank(
    axes: Iterable[StatAxis],
    *,
    include_baseline: bool = True,
    include_balanced: bool = True,
    include_single_axis: bool = True,
    include_axis_pairs: bool = False,
    axis_pair_limit: int | None = None,
) -> StatProfileBank:
    """Build a deterministic generic profile bank from caller-supplied axes.

    Pair profiles are opt-in because their count grows quadratically.  A caller
    can keep pair coverage bounded without changing which early pairs are
    selected: combinations follow the supplied axis order.
    """

    axis_tuple = tuple(axes)
    _axis_index(axis_tuple)
    if axis_pair_limit is not None and axis_pair_limit < 0:
        raise ValueError("axis_pair_limit must be non-negative or None")
    if axis_pair_limit is not None and not include_axis_pairs:
        raise ValueError("axis_pair_limit requires include_axis_pairs=True")

    profiles: list[StatProfile] = []
    if include_baseline:
        profiles.append(
            StatProfile(
                profile_id=PROFILE_BASELINE,
                kind=PROFILE_BASELINE,
            )
        )
    if include_balanced:
        if not axis_tuple:
            raise ValueError("a balanced profile requires at least one stat axis")
        balanced_weight = 1.0 / len(axis_tuple)
        profiles.append(
            StatProfile(
                profile_id=PROFILE_BALANCED,
                kind=PROFILE_BALANCED,
                weights=tuple(
                    StatWeight(axis_key=axis.key, weight=balanced_weight)
                    for axis in axis_tuple
                ),
            )
        )
    if include_single_axis:
        profiles.extend(
            StatProfile(
                profile_id=f"focus/{axis.key}",
                kind=PROFILE_SINGLE_AXIS,
                weights=(StatWeight(axis_key=axis.key, weight=1.0),),
                focus_axes=(axis.key,),
            )
            for axis in axis_tuple
        )
    if include_axis_pairs:
        pair_iter = combinations(axis_tuple, 2)
        for pair_index, (left, right) in enumerate(pair_iter):
            if axis_pair_limit is not None and pair_index >= axis_pair_limit:
                break
            profiles.append(
                StatProfile(
                    profile_id=f"pair/{left.key}+{right.key}",
                    kind=PROFILE_AXIS_PAIR,
                    weights=(
                        StatWeight(axis_key=left.key, weight=0.5),
                        StatWeight(axis_key=right.key, weight=0.5),
                    ),
                    focus_axes=(left.key, right.key),
                )
            )

    return StatProfileBank(axes=axis_tuple, profiles=tuple(profiles))


@dataclass(frozen=True, slots=True)
class SearchWearer:
    wearer_id: str

    def __post_init__(self) -> None:
        _require_identifier(self.wearer_id, field_name="wearer_id")


@dataclass(frozen=True, slots=True)
class WearerProfileSelection:
    """Small profile subset carried into set screening for one wearer.

    ``required_profile_ids`` is the fail-closed handoff from the preceding
    response scan: directions marked large or uncertain upstream must also be
    present in ``profile_ids``.
    """

    wearer_id: str
    profile_ids: tuple[str, ...]
    required_profile_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        profile_ids = _frozen_tuple(
            self.profile_ids,
            field_name="carried profile ids",
        )
        required_profile_ids = _frozen_tuple(
            self.required_profile_ids,
            field_name="required carried profile ids",
        )
        object.__setattr__(self, "profile_ids", profile_ids)
        object.__setattr__(self, "required_profile_ids", required_profile_ids)
        _require_identifier(self.wearer_id, field_name="wearer_id")
        _require_unique(profile_ids, field_name="carried profile ids")
        _require_unique(
            required_profile_ids,
            field_name="required carried profile ids",
        )
        if not profile_ids:
            raise ValueError("each wearer must carry at least one stat profile")
        for profile_id in (*profile_ids, *required_profile_ids):
            _require_identifier(profile_id, field_name="profile_id")
        missing_required = tuple(
            profile_id
            for profile_id in required_profile_ids
            if profile_id not in profile_ids
        )
        if missing_required:
            raise ValueError(
                "required large/uncertain profiles were not carried: "
                f"{missing_required!r}"
            )


class FourPieceSetCapability(Protocol):
    """Structural boundary implemented by the engine-scoped set catalog."""

    @property
    def key(self) -> str: ...

    @property
    def optimizer_four_piece_ready(self) -> bool: ...

    @property
    def max_rarity(self) -> int: ...


@dataclass(frozen=True, slots=True)
class FourPieceSetState:
    wearer_id: str
    set_key: str
    main_stat_layout_id: str
    offpiece_slot: str = ""

    def __post_init__(self) -> None:
        _require_identifier(self.wearer_id, field_name="wearer_id")
        _require_identifier(self.set_key, field_name="artifact set key")
        _require_identifier(
            self.main_stat_layout_id,
            field_name="main stat layout id",
        )
        if self.offpiece_slot and self.offpiece_slot not in ARTIFACT_MAIN_STAT_SLOTS:
            raise ValueError(f"invalid off-piece slot: {self.offpiece_slot!r}")

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (
            self.wearer_id,
            self.set_key,
            self.main_stat_layout_id,
            self.offpiece_slot,
        )


@dataclass(frozen=True, slots=True)
class SetProfileCandidate:
    state: FourPieceSetState
    profile_id: str

    def __post_init__(self) -> None:
        _require_identifier(self.profile_id, field_name="profile_id")

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return (*self.state.key, self.profile_id)


@dataclass(frozen=True, slots=True)
class FourPieceCandidateCoverage:
    wearer_ids: tuple[str, ...]
    optimizer_ready_set_keys: tuple[str, ...]
    optimizer_ready_set_rarities: tuple[tuple[str, int], ...]
    excluded_set_keys: tuple[str, ...]
    available_profile_ids: tuple[str, ...]
    main_stat_layout_ids_by_wearer: tuple[tuple[str, tuple[str, ...]], ...]
    wearer_profile_selections: tuple[WearerProfileSelection, ...]
    states: tuple[FourPieceSetState, ...]
    candidates: tuple[SetProfileCandidate, ...]

    def __post_init__(self) -> None:
        wearer_ids = _frozen_tuple(self.wearer_ids, field_name="coverage wearer ids")
        optimizer_ready_set_keys = _frozen_tuple(
            self.optimizer_ready_set_keys,
            field_name="optimizer-ready set keys",
        )
        optimizer_ready_set_rarities = _frozen_pair_tuple(
            self.optimizer_ready_set_rarities,
            field_name="optimizer-ready set rarities",
        )
        excluded_set_keys = _frozen_tuple(
            self.excluded_set_keys,
            field_name="excluded set keys",
        )
        available_profile_ids = _frozen_tuple(
            self.available_profile_ids,
            field_name="available profile ids",
        )
        raw_layouts = _frozen_pair_tuple(
            self.main_stat_layout_ids_by_wearer,
            field_name="main-stat layouts by wearer",
        )
        main_stat_layout_ids_by_wearer = tuple(
            (
                wearer_id,
                _frozen_tuple(
                    layout_ids,
                    field_name=f"{wearer_id!r} main-stat layout ids",
                ),
            )
            for wearer_id, layout_ids in raw_layouts
        )
        wearer_profile_selections = _frozen_tuple(
            self.wearer_profile_selections,
            field_name="wearer profile selections",
        )
        states = _frozen_tuple(self.states, field_name="four-piece states")
        candidates = _frozen_tuple(
            self.candidates,
            field_name="set/profile candidates",
        )

        object.__setattr__(self, "wearer_ids", wearer_ids)
        object.__setattr__(
            self,
            "optimizer_ready_set_keys",
            optimizer_ready_set_keys,
        )
        object.__setattr__(
            self,
            "optimizer_ready_set_rarities",
            optimizer_ready_set_rarities,
        )
        object.__setattr__(self, "excluded_set_keys", excluded_set_keys)
        object.__setattr__(self, "available_profile_ids", available_profile_ids)
        object.__setattr__(
            self,
            "main_stat_layout_ids_by_wearer",
            main_stat_layout_ids_by_wearer,
        )
        object.__setattr__(
            self,
            "wearer_profile_selections",
            wearer_profile_selections,
        )
        object.__setattr__(self, "states", states)
        object.__setattr__(self, "candidates", candidates)

        identifier_groups = (
            (wearer_ids, "coverage wearer ids"),
            (optimizer_ready_set_keys, "optimizer-ready set keys"),
            (excluded_set_keys, "excluded set keys"),
            (available_profile_ids, "available profile ids"),
        )
        for values, field_name in identifier_groups:
            _require_unique(values, field_name=field_name)
            for value in values:
                _require_identifier(value, field_name=field_name)
        for set_key, rarity in optimizer_ready_set_rarities:
            _require_identifier(set_key, field_name="optimizer-ready set key")
            if isinstance(rarity, bool) or rarity not in (4, 5):
                raise ValueError("optimizer-ready set rarity must be 4 or 5")
        _require_unique(
            (set_key for set_key, _rarity in optimizer_ready_set_rarities),
            field_name="optimizer-ready set rarity keys",
        )
        for wearer_id, layout_ids in main_stat_layout_ids_by_wearer:
            _require_identifier(wearer_id, field_name="main-stat layout wearer id")
            _require_unique(
                layout_ids,
                field_name=f"{wearer_id} main-stat layout ids",
            )
            for layout_id in layout_ids:
                _require_identifier(layout_id, field_name="main stat layout id")
        _require_unique(
            (
                wearer_id
                for wearer_id, _layout_ids in main_stat_layout_ids_by_wearer
            ),
            field_name="main-stat layout wearer ids",
        )
        _require_instances(
            wearer_profile_selections,
            WearerProfileSelection,
            field_name="wearer profile selections",
        )
        _require_instances(states, FourPieceSetState, field_name="four-piece states")
        _require_instances(
            candidates,
            SetProfileCandidate,
            field_name="set/profile candidates",
        )

    @property
    def expected_state_count(self) -> int:
        layout_count = sum(
            len(layout_ids)
            for _wearer_id, layout_ids in self.main_stat_layout_ids_by_wearer
        )
        set_variant_count = sum(
            len(ARTIFACT_MAIN_STAT_SLOTS) if rarity == 4 else 1
            for _set_key, rarity in self.optimizer_ready_set_rarities
        )
        return layout_count * set_variant_count

    @property
    def expected_candidate_count(self) -> int:
        profiles_by_wearer = {
            selection.wearer_id: len(selection.profile_ids)
            for selection in self.wearer_profile_selections
        }
        layouts_by_wearer = dict(self.main_stat_layout_ids_by_wearer)
        set_variant_count = sum(
            len(ARTIFACT_MAIN_STAT_SLOTS) if rarity == 4 else 1
            for _set_key, rarity in self.optimizer_ready_set_rarities
        )
        return sum(
            len(layouts_by_wearer[wearer_id])
            * set_variant_count
            * profiles_by_wearer[wearer_id]
            for wearer_id in self.wearer_ids
        )

    @property
    def candidate_counts_by_wearer(self) -> tuple[tuple[str, int], ...]:
        return tuple(
            (
                selection.wearer_id,
                sum(
                    1
                    for candidate in self.candidates
                    if candidate.state.wearer_id == selection.wearer_id
                ),
            )
            for selection in self.wearer_profile_selections
        )

    @property
    def uses_full_profile_bank(self) -> bool:
        return all(
            selection.profile_ids == self.available_profile_ids
            for selection in self.wearer_profile_selections
        )


def build_four_piece_candidate_coverage(
    wearers: Iterable[SearchWearer],
    set_capabilities: Iterable[FourPieceSetCapability],
    profile_bank: StatProfileBank,
    *,
    main_stat_layout_ids_by_wearer: Mapping[str, Sequence[str]],
    wearer_profile_selections: Iterable[WearerProfileSelection] | None = None,
) -> FourPieceCandidateCoverage:
    """Build modeled set x wearer coverage with full or adaptive profiles."""

    wearer_tuple = tuple(wearers)
    capability_tuple = tuple(set_capabilities)
    _require_unique(
        (wearer.wearer_id for wearer in wearer_tuple),
        field_name="wearer ids",
    )
    _require_unique(
        (capability.key for capability in capability_tuple),
        field_name="artifact set capability keys",
    )
    if not wearer_tuple:
        raise ValueError("4p candidate coverage requires at least one wearer")
    for capability in capability_tuple:
        _require_identifier(capability.key, field_name="artifact set key")
        if not isinstance(capability.optimizer_four_piece_ready, bool):
            raise ValueError("optimizer_four_piece_ready must be a bool")
        if capability.max_rarity not in (4, 5):
            raise ValueError("artifact set max_rarity must be 4 or 5")

    wearer_ids = tuple(wearer.wearer_id for wearer in wearer_tuple)
    layout_wearers = set(main_stat_layout_ids_by_wearer)
    if layout_wearers != set(wearer_ids):
        raise ValueError(
            "main-stat layouts must cover exactly the search wearers"
        )
    normalized_layouts: dict[str, tuple[str, ...]] = {}
    for wearer_id in wearer_ids:
        layout_ids = tuple(main_stat_layout_ids_by_wearer[wearer_id])
        if not layout_ids:
            raise ValueError("each wearer requires at least one main-stat layout")
        _require_unique(layout_ids, field_name=f"{wearer_id} main-stat layout ids")
        for layout_id in layout_ids:
            _require_identifier(layout_id, field_name="main stat layout id")
        normalized_layouts[wearer_id] = layout_ids

    optimizer_ready_set_keys = tuple(
        capability.key
        for capability in capability_tuple
        if capability.optimizer_four_piece_ready
    )
    excluded_set_keys = tuple(
        capability.key
        for capability in capability_tuple
        if not capability.optimizer_four_piece_ready
    )
    modeled_capabilities = tuple(
        capability
        for capability in capability_tuple
        if capability.optimizer_four_piece_ready
    )
    states = tuple(
        FourPieceSetState(
            wearer_id=wearer.wearer_id,
            set_key=capability.key,
            main_stat_layout_id=layout_id,
            offpiece_slot=offpiece_slot,
        )
        for wearer in wearer_tuple
        for capability in modeled_capabilities
        for layout_id in normalized_layouts[wearer.wearer_id]
        for offpiece_slot in (
            ARTIFACT_MAIN_STAT_SLOTS
            if capability.max_rarity == 4
            else ("",)
        )
    )
    available_profile_ids = tuple(
        profile.profile_id
        for profile in profile_bank.profiles
    )
    resolved_selections = _resolve_wearer_profile_selections(
        wearer_tuple,
        available_profile_ids,
        wearer_profile_selections,
    )
    profiles_by_wearer = {
        selection.wearer_id: selection.profile_ids
        for selection in resolved_selections
    }
    candidates = tuple(
        SetProfileCandidate(
            state=state,
            profile_id=profile_id,
        )
        for state in states
        for profile_id in profiles_by_wearer[state.wearer_id]
    )
    result = FourPieceCandidateCoverage(
        wearer_ids=wearer_ids,
        optimizer_ready_set_keys=optimizer_ready_set_keys,
        optimizer_ready_set_rarities=tuple(
            (capability.key, capability.max_rarity)
            for capability in modeled_capabilities
        ),
        excluded_set_keys=excluded_set_keys,
        available_profile_ids=available_profile_ids,
        main_stat_layout_ids_by_wearer=tuple(
            (wearer_id, normalized_layouts[wearer_id])
            for wearer_id in wearer_ids
        ),
        wearer_profile_selections=resolved_selections,
        states=states,
        candidates=candidates,
    )
    if len(result.states) != result.expected_state_count:
        raise AssertionError("incomplete modeled 4p set/wearer coverage")
    if len(result.candidates) != result.expected_candidate_count:
        raise AssertionError("incomplete modeled 4p candidate/profile coverage")
    return result


def _resolve_wearer_profile_selections(
    wearers: Sequence[SearchWearer],
    available_profile_ids: tuple[str, ...],
    selections: Iterable[WearerProfileSelection] | None,
) -> tuple[WearerProfileSelection, ...]:
    if selections is None:
        return tuple(
            WearerProfileSelection(
                wearer_id=wearer.wearer_id,
                profile_ids=available_profile_ids,
            )
            for wearer in wearers
        )

    selection_tuple = tuple(selections)
    _require_unique(
        (selection.wearer_id for selection in selection_tuple),
        field_name="wearer profile selection ids",
    )
    selection_by_wearer = {
        selection.wearer_id: selection
        for selection in selection_tuple
    }
    expected_wearers = {wearer.wearer_id for wearer in wearers}
    actual_wearers = set(selection_by_wearer)
    if actual_wearers != expected_wearers:
        raise ValueError(
            "adaptive profile selections must cover exactly the search wearers; "
            f"missing={tuple(sorted(expected_wearers - actual_wearers))!r}, "
            f"extra={tuple(sorted(actual_wearers - expected_wearers))!r}"
        )

    available_set = set(available_profile_ids)
    resolved: list[WearerProfileSelection] = []
    for wearer in wearers:
        selection = selection_by_wearer[wearer.wearer_id]
        unknown = tuple(
            profile_id
            for profile_id in selection.profile_ids
            if profile_id not in available_set
        )
        if unknown:
            raise ValueError(
                f"wearer {wearer.wearer_id!r} carries unknown profiles: "
                f"{unknown!r}"
            )
        carried_set = set(selection.profile_ids)
        canonical_profile_ids = tuple(
            profile_id
            for profile_id in available_profile_ids
            if profile_id in carried_set
        )
        resolved.append(
            WearerProfileSelection(
                wearer_id=selection.wearer_id,
                profile_ids=canonical_profile_ids,
                required_profile_ids=selection.required_profile_ids,
            )
        )
    return tuple(resolved)


@dataclass(frozen=True, slots=True)
class ScreeningSurvivorBudget:
    """Explicit limits for survivor selection, not scheduler/time limits."""

    max_survivors: int
    top_slots: int
    wearer_coverage_slots: int
    uncertain_slots: int
    profile_coverage_slots: int
    novelty_slots: int
    confidence_sigma: float
    relative_uncertainty_margin: float

    def __post_init__(self) -> None:
        integer_fields = {
            "max_survivors": self.max_survivors,
            "top_slots": self.top_slots,
            "wearer_coverage_slots": self.wearer_coverage_slots,
            "uncertain_slots": self.uncertain_slots,
            "profile_coverage_slots": self.profile_coverage_slots,
            "novelty_slots": self.novelty_slots,
        }
        for field_name, value in integer_fields.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field_name} must be an integer")
        if self.max_survivors <= 0:
            raise ValueError("max_survivors must be positive")
        slot_values = (
            self.top_slots,
            self.wearer_coverage_slots,
            self.uncertain_slots,
            self.profile_coverage_slots,
            self.novelty_slots,
        )
        if any(value < 0 for value in slot_values):
            raise ValueError("survivor slot budgets must be non-negative")
        if sum(slot_values) > self.max_survivors:
            raise ValueError(
                "reserved survivor slots cannot exceed max_survivors"
            )
        if not isfinite(self.confidence_sigma) or self.confidence_sigma < 0:
            raise ValueError("confidence_sigma must be finite and non-negative")
        if (
            not isfinite(self.relative_uncertainty_margin)
            or self.relative_uncertainty_margin < 0
        ):
            raise ValueError(
                "relative_uncertainty_margin must be finite and non-negative"
            )


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    candidate: SetProfileCandidate
    expected_dps: float
    investment_signature: str
    standard_error: float | None = None
    novelty_score: float = 0.0
    novelty_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        novelty_tags = _frozen_tuple(
            self.novelty_tags,
            field_name="novelty tags",
        )
        object.__setattr__(self, "novelty_tags", novelty_tags)
        _require_identifier(
            self.investment_signature,
            field_name="investment signature",
        )
        if not isfinite(self.expected_dps) or self.expected_dps < 0:
            raise ValueError("expected_dps must be finite and non-negative")
        if self.standard_error is not None and (
            not isfinite(self.standard_error) or self.standard_error < 0
        ):
            raise ValueError(
                "standard_error must be finite and non-negative or None"
            )
        if not isfinite(self.novelty_score):
            raise ValueError("novelty_score must be finite")
        _require_unique(novelty_tags, field_name="novelty tags")
        for tag in novelty_tags:
            _require_identifier(tag, field_name="novelty tag")

    def lower_bound(self, confidence_sigma: float) -> float:
        if self.standard_error is None:
            return float("-inf")
        return self.expected_dps - confidence_sigma * self.standard_error

    def upper_bound(self, confidence_sigma: float) -> float:
        if self.standard_error is None:
            return float("inf")
        return self.expected_dps + confidence_sigma * self.standard_error

    @property
    def branch_tags(self) -> tuple[str, ...]:
        return (
            f"set/{self.candidate.state.set_key}",
            f"layout/{self.candidate.state.main_stat_layout_id}",
            *(
                (f"offpiece/{self.candidate.state.offpiece_slot}",)
                if self.candidate.state.offpiece_slot
                else ()
            ),
            *self.novelty_tags,
        )


@dataclass(frozen=True, slots=True)
class SearchSurvivor:
    evaluation: CandidateEvaluation
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        reasons = _frozen_tuple(self.reasons, field_name="survivor reasons")
        object.__setattr__(self, "reasons", reasons)
        _require_unique(reasons, field_name="survivor reasons")
        for reason in reasons:
            _require_identifier(reason, field_name="survivor reason")


@dataclass(frozen=True, slots=True)
class SurvivorSelectionResult:
    budget: ScreeningSurvivorBudget
    evaluated_count: int
    survivors: tuple[SearchSurvivor, ...]
    dropped_count: int
    required_profile_groups: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        survivors = _frozen_tuple(self.survivors, field_name="search survivors")
        required_profile_groups = _frozen_pair_tuple(
            self.required_profile_groups,
            field_name="required profile groups",
        )
        object.__setattr__(self, "survivors", survivors)
        object.__setattr__(
            self,
            "required_profile_groups",
            required_profile_groups,
        )
        _require_instances(
            survivors,
            SearchSurvivor,
            field_name="search survivors",
        )
        _require_unique(
            required_profile_groups,
            field_name="required profile groups",
        )
        for wearer_id, profile_id in required_profile_groups:
            _require_identifier(wearer_id, field_name="required profile wearer_id")
            _require_identifier(profile_id, field_name="required profile_id")

    @property
    def survivor_candidates(self) -> tuple[SetProfileCandidate, ...]:
        return tuple(survivor.evaluation.candidate for survivor in self.survivors)


def select_screening_survivors(
    evaluations: Iterable[CandidateEvaluation],
    budget: ScreeningSurvivorBudget,
    *,
    required_profile_ids_by_wearer: Mapping[str, Sequence[str]] | None = None,
) -> SurvivorSelectionResult:
    """Select a bounded recall-first pool for expensive optimization.

    Slots are reserved for complementary evidence instead of relying on one DPS
    ordering: raw leaders, wearer coverage, statistical near-ties,
    wearer/profile winners, and branches not represented by the earlier
    phases.  Remaining capacity is filled by score.  Input order never affects
    the result.
    """

    evaluation_tuple = tuple(evaluations)
    _require_unique(
        (evaluation.candidate.key for evaluation in evaluation_tuple),
        field_name="candidate evaluation keys",
    )
    investment_signatures = {
        evaluation.investment_signature
        for evaluation in evaluation_tuple
    }
    if len(investment_signatures) > 1:
        raise ValueError(
            "candidate evaluations must share one equal-investment signature"
        )
    ranked = tuple(sorted(evaluation_tuple, key=_evaluation_rank_key))
    required_groups = _normalized_required_profile_groups(
        required_profile_ids_by_wearer
    )
    selected: dict[
        tuple[str, str, str, str, str],
        tuple[CandidateEvaluation, list[str]],
    ] = {}

    def retain(
        evaluation: CandidateEvaluation,
        reason: str,
        *,
        mandatory: bool = False,
    ) -> bool:
        key = evaluation.candidate.key
        existing = selected.get(key)
        if existing is None:
            if len(selected) >= budget.max_survivors:
                if mandatory:
                    raise ValueError(
                        "required wearer/profile survivor groups exceed "
                        "max_survivors"
                    )
                return False
            selected[key] = (evaluation, [reason])
            return True
        elif reason not in existing[1]:
            existing[1].append(reason)
        return False

    for wearer_id, profile_id in required_groups:
        match = next(
            (
                evaluation
                for evaluation in ranked
                if evaluation.candidate.state.wearer_id == wearer_id
                and evaluation.candidate.profile_id == profile_id
            ),
            None,
        )
        if match is None:
            raise ValueError(
                "required wearer/profile group has no successful evaluation: "
                f"{(wearer_id, profile_id)!r}"
            )
        retain(match, SURVIVOR_REQUIRED_PROFILE, mandatory=True)

    for evaluation in ranked[: budget.top_slots]:
        retain(evaluation, SURVIVOR_TOP_SCORE)

    _retain_round_robin(
        ranked,
        group_key=lambda item: item.candidate.state.wearer_id,
        slots=budget.wearer_coverage_slots,
        reason=SURVIVOR_WEARER_COVERAGE,
        retain=retain,
    )

    uncertain_by_wearer = _uncertain_candidates_by_wearer(ranked, budget)
    _retain_grouped_round_robin(
        uncertain_by_wearer,
        slots=budget.uncertain_slots,
        reason=SURVIVOR_UNCERTAIN,
        retain=retain,
    )

    _retain_round_robin(
        ranked,
        group_key=lambda item: (
            item.candidate.state.wearer_id,
            item.candidate.profile_id,
        ),
        slots=budget.profile_coverage_slots,
        reason=SURVIVOR_PROFILE_COVERAGE,
        retain=retain,
    )

    seen_branch_tags = {
        tag
        for evaluation, _reasons in selected.values()
        for tag in evaluation.branch_tags
    }
    novelty_ranked = sorted(
        ranked,
        key=lambda item: (-item.novelty_score, *_evaluation_rank_key(item)),
    )
    novelty_added = 0
    for evaluation in novelty_ranked:
        if novelty_added >= budget.novelty_slots:
            break
        if evaluation.candidate.key in selected:
            continue
        unseen_tags = set(evaluation.branch_tags).difference(seen_branch_tags)
        if not unseen_tags:
            continue
        retain(evaluation, SURVIVOR_NOVEL_BRANCH)
        seen_branch_tags.update(evaluation.branch_tags)
        novelty_added += 1

    for evaluation in ranked:
        if len(selected) >= budget.max_survivors:
            break
        if evaluation.candidate.key not in selected:
            retain(evaluation, SURVIVOR_BUDGET_FILL)

    survivor_rows = tuple(
        SearchSurvivor(evaluation=evaluation, reasons=tuple(reasons))
        for evaluation, reasons in sorted(
            selected.values(),
            key=lambda item: _evaluation_rank_key(item[0]),
        )
    )
    return SurvivorSelectionResult(
        budget=budget,
        evaluated_count=len(evaluation_tuple),
        survivors=survivor_rows,
        dropped_count=len(evaluation_tuple) - len(survivor_rows),
        required_profile_groups=required_groups,
    )


def _normalized_required_profile_groups(
    values: Mapping[str, Sequence[str]] | None,
) -> tuple[tuple[str, str], ...]:
    if values is None:
        return ()
    if not isinstance(values, Mapping):
        raise ValueError("required_profile_ids_by_wearer must be a mapping")
    groups: list[tuple[str, str]] = []
    for wearer_id, profile_ids in values.items():
        _require_identifier(wearer_id, field_name="required profile wearer_id")
        if isinstance(profile_ids, (str, bytes)):
            raise ValueError("required profile ids must be a sequence")
        profile_tuple = tuple(profile_ids)
        _require_unique(
            profile_tuple,
            field_name=f"required profile ids for {wearer_id}",
        )
        for profile_id in profile_tuple:
            _require_identifier(profile_id, field_name="required profile_id")
            groups.append((wearer_id, profile_id))
    return tuple(sorted(groups, key=lambda item: (item[0], item[1])))


def _uncertain_candidates_by_wearer(
    ranked: Sequence[CandidateEvaluation],
    budget: ScreeningSurvivorBudget,
) -> dict[str, tuple[CandidateEvaluation, ...]]:
    grouped = _group_ranked(
        ranked,
        key=lambda item: item.candidate.state.wearer_id,
    )
    uncertain: dict[str, tuple[CandidateEvaluation, ...]] = {}
    for wearer_id, wearer_evaluations in grouped.items():
        best = wearer_evaluations[0]
        best_lower = best.lower_bound(budget.confidence_sigma)
        absolute_margin = (
            best.expected_dps * budget.relative_uncertainty_margin
        )
        candidates = tuple(
            evaluation
            for evaluation in wearer_evaluations[1:]
            if evaluation.upper_bound(budget.confidence_sigma) + absolute_margin
            >= best_lower
        )
        if candidates:
            uncertain[wearer_id] = candidates
    return uncertain


def _retain_round_robin(
    ranked: Sequence[CandidateEvaluation],
    *,
    group_key: Callable[[CandidateEvaluation], Hashable],
    slots: int,
    reason: str,
    retain: Callable[[CandidateEvaluation, str], bool],
) -> None:
    _retain_grouped_round_robin(
        _group_ranked(ranked, key=group_key),
        slots=slots,
        reason=reason,
        retain=retain,
    )


def _retain_grouped_round_robin(
    grouped: dict[Hashable, tuple[CandidateEvaluation, ...]],
    *,
    slots: int,
    reason: str,
    retain: Callable[[CandidateEvaluation, str], bool],
) -> None:
    retained = 0
    round_index = 0
    group_keys = tuple(sorted(grouped, key=_stable_group_sort_key))
    while retained < slots:
        made_progress = False
        for group in group_keys:
            candidates = grouped[group]
            if round_index >= len(candidates):
                continue
            if retain(candidates[round_index], reason):
                retained += 1
            made_progress = True
            if retained >= slots:
                break
        if not made_progress:
            break
        round_index += 1


def _group_ranked(
    ranked: Sequence[CandidateEvaluation],
    *,
    key: Callable[[CandidateEvaluation], Hashable],
) -> dict[Hashable, tuple[CandidateEvaluation, ...]]:
    grouped_lists: dict[Hashable, list[CandidateEvaluation]] = {}
    for evaluation in ranked:
        grouped_lists.setdefault(key(evaluation), []).append(evaluation)
    return {
        group: tuple(items)
        for group, items in grouped_lists.items()
    }


def _evaluation_rank_key(
    evaluation: CandidateEvaluation,
) -> tuple[float, float, str, str, str, str, str]:
    return (
        -evaluation.expected_dps,
        (
            float("inf")
            if evaluation.standard_error is None
            else evaluation.standard_error
        ),
        evaluation.candidate.state.wearer_id,
        evaluation.candidate.state.set_key,
        evaluation.candidate.state.main_stat_layout_id,
        evaluation.candidate.state.offpiece_slot,
        evaluation.candidate.profile_id,
    )


def _stable_group_sort_key(value: Hashable) -> tuple[str, str]:
    return type(value).__name__, repr(value)


def _axis_index(axes: Sequence[StatAxis]) -> dict[str, StatAxis]:
    _require_unique((axis.key for axis in axes), field_name="stat axis keys")
    return {axis.key: axis for axis in axes}


def _normalized_weight_index(
    weights: Sequence[StatWeight],
    *,
    axis_by_key: dict[str, StatAxis],
    field_name: str,
) -> dict[str, float]:
    _require_unique(
        (weight.axis_key for weight in weights),
        field_name=f"{field_name} axes",
    )
    unknown = tuple(
        weight.axis_key
        for weight in weights
        if weight.axis_key not in axis_by_key
    )
    if unknown:
        raise ValueError(f"{field_name} reference unknown axes: {unknown!r}")
    total = sum(weight.weight for weight in weights)
    if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"{field_name} must sum to 1")
    return {weight.axis_key: weight.weight for weight in weights}


def _require_identifier(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty trimmed string")


def _frozen_tuple(
    values: Iterable[_T],
    *,
    field_name: str,
) -> tuple[_T, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{field_name} must be an iterable of values")
    try:
        return tuple(values)
    except TypeError as exc:
        raise ValueError(f"{field_name} must be an iterable of values") from exc


def _frozen_pair_tuple(
    values: Iterable[Iterable[_T]],
    *,
    field_name: str,
) -> tuple[tuple[_T, _T], ...]:
    rows = _frozen_tuple(values, field_name=field_name)
    normalized: list[tuple[_T, _T]] = []
    for row in rows:
        pair = _frozen_tuple(row, field_name=f"{field_name} row")
        if len(pair) != 2:
            raise ValueError(f"{field_name} rows must contain exactly two values")
        normalized.append((pair[0], pair[1]))
    return tuple(normalized)


def _require_instances(
    values: Iterable[object],
    expected_type: type[object],
    *,
    field_name: str,
) -> None:
    if any(not isinstance(value, expected_type) for value in values):
        raise ValueError(
            f"{field_name} must contain only {expected_type.__name__} values"
        )


def _require_unique(values: Iterable[object], *, field_name: str) -> None:
    seen: set[object] = set()
    duplicates: list[object] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise ValueError(f"{field_name} must be unique; duplicates={duplicates!r}")
