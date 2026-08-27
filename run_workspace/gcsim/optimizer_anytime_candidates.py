"""Compact candidate and joint-search kernel for ``anytime_approx_v2``.

The old account path derives a separate response model for every reachable
main-stat layout and rebuilds an artifact index for every model.  This module
does the opposite:

* normalize the frozen artifact database once;
* score every piece with a small rotation-specific profile family;
* retain Pareto-frontier pieces plus a bounded physical shadow pool;
* build diverse complete wearer candidates with a bounded beam;
* combine four wearer pools with integer bit masks before compiling configs.

All database access remains read-only.  Exact eligibility, set-count,
minimum-stat, materialization, and global no-reuse checks remain owned by the
existing strict typed boundaries.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
import hashlib
import json
from math import isfinite
from time import monotonic
from types import MappingProxyType

from .optimizer_artifact_database import (
    GcsimOptimizerArtifactRecord,
    evaluate_gcsim_optimizer_artifact_eligibility,
)
from .optimizer_artifact_materializer import (
    compile_gcsim_optimizer_team_candidate,
    materialize_gcsim_optimizer_artifact_stat_vector,
    materialize_gcsim_optimizer_wearer_build,
)
from .optimizer_joint_proposals import GcsimOptimizerJointProposal
from .optimizer_lazy_candidates import GcsimOptimizerLazyWearerCandidate
from .optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ACCOUNT_STAT_AXES,
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerAccountAssignmentWitness,
    GcsimOptimizerWearerArtifactAssignment,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerTarget,
    GcsimTwoPlusTwoTargetPackage,
)
from .optimizer_run_input import GcsimOptimizerRunInput
from .optimizer_stat_response import GCSIM_STAT_RESPONSE_ROLL_VALUES
from .optimizer_stat_constraints import (
    effective_gcsim_optimizer_artifact_minimums,
)


GCSIM_OPTIMIZER_ANYTIME_CANDIDATE_SCHEMA_VERSION = 4

# A fixed order makes hot-loop vectors compact and deterministic.
GCSIM_OPTIMIZER_ANYTIME_STAT_AXES = tuple(
    axis
    for axis in (
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
    if axis in GCSIM_OPTIMIZER_ACCOUNT_STAT_AXES
)
_AXIS_INDEX = MappingProxyType(
    {axis: index for index, axis in enumerate(GCSIM_OPTIMIZER_ANYTIME_STAT_AXES)}
)
_VARIABLE_SLOTS = ("sands", "goblet", "circlet")
_STRUCTURAL_SUBSTAT_AXES = (
    "hp",
    "atk",
    "def",
    "hp%",
    "atk%",
    "def%",
    "em",
    "cr",
    "cd",
)
_SOFT_MAIN_COVERAGE_AXES_BY_SLOT = MappingProxyType(
    {
        "sands": ("hp%", "atk%", "def%", "em"),
        "goblet": (
            "hp%",
            "atk%",
            "def%",
            "em",
            "pyro%",
            "hydro%",
            "electro%",
            "cryo%",
            "anemo%",
            "geo%",
            "dendro%",
            "phys%",
        ),
        "circlet": ("hp%", "atk%", "def%", "em", "cr", "cd", "heal"),
    }
)
GCSIM_OPTIMIZER_RESPONSE_CLASSIFICATIONS = (
    "dominant",
    "secondary",
    "negligible",
    "uncertain",
)


class GcsimOptimizerAnytimeCandidateError(ValueError):
    """Fail-closed compact candidate-kernel error."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAnytimeStatProfile:
    """One rotation-specific additive proposal view for a single wearer."""

    wearer: GcsimOptimizerWearerIdentity
    profile_id: str
    stat_weights: tuple[float, ...]
    main_scores: tuple[tuple[str, str, float], ...]
    evidence_sha256: str
    feature_labels: tuple[str, ...] = ()
    stat_classifications: tuple[tuple[str, str], ...] = ()
    main_classifications: tuple[tuple[str, str, str], ...] = ()
    schema_version: int = GCSIM_OPTIMIZER_ANYTIME_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerAnytimeCandidateError(
                "stat profile wearer must be typed"
            )
        if (
            not isinstance(self.profile_id, str)
            or not self.profile_id
            or self.profile_id != self.profile_id.strip()
        ):
            raise GcsimOptimizerAnytimeCandidateError(
                "stat profile_id must be non-empty trimmed text"
            )
        weights = tuple(float(value) for value in self.stat_weights)
        if len(weights) != len(GCSIM_OPTIMIZER_ANYTIME_STAT_AXES):
            raise GcsimOptimizerAnytimeCandidateError(
                "stat profile must cover the fixed anytime axis order"
            )
        if any(not isfinite(value) or value < 0 for value in weights):
            raise GcsimOptimizerAnytimeCandidateError(
                "stat profile weights must be finite and non-negative"
            )
        main_rows = tuple(
            sorted(
                (
                    str(slot),
                    str(axis),
                    float(score),
                )
                for slot, axis, score in self.main_scores
            )
        )
        if len({(slot, axis) for slot, axis, _score in main_rows}) != len(
            main_rows
        ):
            raise GcsimOptimizerAnytimeCandidateError(
                "main score rows must be unique"
            )
        for slot, axis, score in main_rows:
            if slot not in _VARIABLE_SLOTS:
                raise GcsimOptimizerAnytimeCandidateError(
                    "main score uses an unsupported slot"
                )
            if axis not in _AXIS_INDEX:
                raise GcsimOptimizerAnytimeCandidateError(
                    "main score uses an unsupported axis"
                )
            if not isfinite(score) or score < 0:
                raise GcsimOptimizerAnytimeCandidateError(
                    "main scores must be finite and non-negative"
                )
        _require_sha256(self.evidence_sha256, "evidence_sha256")
        labels = tuple(sorted(set(self.feature_labels)))
        if any(not label or label != label.strip() for label in labels):
            raise GcsimOptimizerAnytimeCandidateError(
                "feature labels must be non-empty trimmed text"
            )
        stat_classifications = tuple(
            sorted(
                (
                    (str(axis), str(classification))
                    for axis, classification in self.stat_classifications
                ),
                key=lambda item: item[0],
            )
        )
        if not stat_classifications:
            stat_classifications = tuple(
                (
                    axis,
                    "secondary" if weights[index] > 0 else "negligible",
                )
                for index, axis in enumerate(GCSIM_OPTIMIZER_ANYTIME_STAT_AXES)
            )
        if (
            len(stat_classifications) != len(GCSIM_OPTIMIZER_ANYTIME_STAT_AXES)
            or {axis for axis, _status in stat_classifications}
            != set(GCSIM_OPTIMIZER_ANYTIME_STAT_AXES)
        ):
            raise GcsimOptimizerAnytimeCandidateError(
                "stat classifications must cover the fixed anytime axes"
            )
        main_classifications = tuple(
            sorted(
                (
                    (str(slot), str(axis), str(classification))
                    for slot, axis, classification in self.main_classifications
                ),
                key=lambda item: (item[0], item[1]),
            )
        )
        if not main_classifications:
            main_classifications = tuple(
                (
                    slot,
                    axis,
                    "secondary" if score > 0 else "negligible",
                )
                for slot, axis, score in main_rows
            )
        if (
            len(main_classifications) != len(main_rows)
            or {(slot, axis) for slot, axis, _status in main_classifications}
            != {(slot, axis) for slot, axis, _score in main_rows}
        ):
            raise GcsimOptimizerAnytimeCandidateError(
                "main classifications must cover every main score row"
            )
        for axis, classification in stat_classifications:
            if classification not in GCSIM_OPTIMIZER_RESPONSE_CLASSIFICATIONS:
                raise GcsimOptimizerAnytimeCandidateError(
                    f"unsupported stat classification for {axis!r}"
                )
            weight = weights[_AXIS_INDEX[axis]]
            if classification in {"dominant", "secondary"} and weight <= 0:
                raise GcsimOptimizerAnytimeCandidateError(
                    "useful stat classifications require positive weight"
                )
            if classification in {"negligible", "uncertain"} and weight != 0:
                raise GcsimOptimizerAnytimeCandidateError(
                    "non-useful stat classifications require zero weight"
                )
        main_score_index = {
            (slot, axis): score for slot, axis, score in main_rows
        }
        for slot, axis, classification in main_classifications:
            if classification not in GCSIM_OPTIMIZER_RESPONSE_CLASSIFICATIONS:
                raise GcsimOptimizerAnytimeCandidateError(
                    f"unsupported main classification for {slot}/{axis}"
                )
            score = main_score_index[(slot, axis)]
            if classification in {"dominant", "secondary"} and score <= 0:
                raise GcsimOptimizerAnytimeCandidateError(
                    "useful main classifications require positive score"
                )
            if classification in {"negligible", "uncertain"} and score != 0:
                raise GcsimOptimizerAnytimeCandidateError(
                    "non-useful main classifications require zero score"
                )
        object.__setattr__(self, "stat_weights", weights)
        object.__setattr__(self, "main_scores", main_rows)
        object.__setattr__(self, "feature_labels", labels)
        object.__setattr__(self, "stat_classifications", stat_classifications)
        object.__setattr__(self, "main_classifications", main_classifications)

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    @property
    def main_score_index(self) -> Mapping[tuple[str, str], float]:
        return MappingProxyType(
            {(slot, axis): score for slot, axis, score in self.main_scores}
        )

    @property
    def retained_main_axes_by_slot(self) -> Mapping[str, frozenset[str]]:
        retained = {
            slot: set() for slot in _VARIABLE_SLOTS
        }
        for slot, axis, classification in self.main_classifications:
            if classification != "negligible":
                retained[slot].add(axis)
        return MappingProxyType(
            {slot: frozenset(axes) for slot, axes in retained.items()}
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "wearer": self.wearer.to_dict(),
            "profile_id": self.profile_id,
            "stat_weights": [
                {
                    "axis_key": axis,
                    "weight": self.stat_weights[index],
                }
                for index, axis in enumerate(
                    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
                )
            ],
            "main_scores": [
                {"slot": slot, "axis_key": axis, "score": score}
                for slot, axis, score in self.main_scores
            ],
            "evidence_sha256": self.evidence_sha256,
            "feature_labels": list(self.feature_labels),
            "stat_classifications": [
                {"axis_key": axis, "classification": classification}
                for axis, classification in self.stat_classifications
            ],
            "main_classifications": [
                {
                    "slot": slot,
                    "axis_key": axis,
                    "classification": classification,
                }
                for slot, axis, classification in self.main_classifications
            ],
        }


def build_gcsim_optimizer_soft_main_coverage_profiles(
    profiles: Sequence[GcsimOptimizerAnytimeStatProfile],
) -> tuple[GcsimOptimizerAnytimeStatProfile, ...]:
    """Add score-only main-stat anchors without claiming measured utility.

    A neutral all-set probe is intentionally only a shortlist/ranking signal.
    Its small sample may classify a real main stat as negligible, so the local
    physical refinement needs a bounded way to surface materially different
    layouts anyway.  These zero-substat-weight anchors do exactly that: one
    deterministic profile per legal main axis.  They never alter hard stat
    constraints and exact GCSIM remains the sole winner selector.
    """

    rows = tuple(profiles)
    if not rows or any(
        not isinstance(item, GcsimOptimizerAnytimeStatProfile)
        for item in rows
    ):
        raise GcsimOptimizerAnytimeCandidateError(
            "soft main coverage requires typed response profiles"
        )
    wearer = rows[0].wearer
    if any(item.wearer != wearer for item in rows):
        raise GcsimOptimizerAnytimeCandidateError(
            "soft main coverage profiles must use one wearer"
        )
    anchors: list[GcsimOptimizerAnytimeStatProfile] = []
    axes = tuple(
        dict.fromkeys(
            axis
            for slot in _VARIABLE_SLOTS
            for axis in _SOFT_MAIN_COVERAGE_AXES_BY_SLOT[slot]
        )
    )
    for axis in axes:
        main_scores = tuple(
            (slot, axis, 1.0)
            for slot in _VARIABLE_SLOTS
            if axis in _SOFT_MAIN_COVERAGE_AXES_BY_SLOT[slot]
        )
        profile_id = "main_anchor_" + axis.replace("%", "_pct")
        evidence_sha256 = _canonical_sha256(
            {
                "kind": "soft_main_coverage_anchor",
                "wearer": wearer.to_dict(),
                "axis": axis,
                "upstream": [item.identity_sha256 for item in rows],
            }
        )
        anchors.append(
            GcsimOptimizerAnytimeStatProfile(
                wearer=wearer,
                profile_id=profile_id,
                stat_weights=(0.0,) * len(
                    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
                ),
                main_scores=main_scores,
                evidence_sha256=evidence_sha256,
                feature_labels=(
                    "soft_main_coverage",
                    f"main_axis_anchor:{axis}",
                ),
            )
        )
    return (*rows, *anchors)


def build_gcsim_optimizer_stat_coverage_profiles(
    profiles: Sequence[GcsimOptimizerAnytimeStatProfile],
) -> tuple[GcsimOptimizerAnytimeStatProfile, ...]:
    """Add raw-axis search directions without claiming response utility.

    A small paired response can correctly call an axis negligible around its
    synthetic working point while a coordinated physical build far away on
    that axis is strong.  If that zero becomes a hard scalar ranking decision,
    the entire physical neighborhood is unreachable by later exact GCSIM.
    One bounded profile per artifact substat axis preserves those Pareto-like
    directions.  ER remains a hard pre-simulation constraint only.
    """

    rows = tuple(profiles)
    if not rows or any(
        not isinstance(item, GcsimOptimizerAnytimeStatProfile)
        for item in rows
    ):
        raise GcsimOptimizerAnytimeCandidateError(
            "stat coverage requires typed response profiles"
        )
    wearer = rows[0].wearer
    if any(item.wearer != wearer for item in rows):
        raise GcsimOptimizerAnytimeCandidateError(
            "stat coverage profiles must use one wearer"
        )
    balanced = next(
        (item for item in rows if item.profile_id == "balanced"),
        None,
    )
    if balanced is None:
        raise GcsimOptimizerAnytimeCandidateError(
            "stat coverage requires a balanced response profile"
        )
    anchors = []
    for axis in _STRUCTURAL_SUBSTAT_AXES:
        if axis not in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES:
            continue
        weights = tuple(
            1.0 if candidate_axis == axis else 0.0
            for candidate_axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
        )
        classifications = tuple(
            (
                candidate_axis,
                "secondary"
                if candidate_axis == axis
                else "negligible",
            )
            for candidate_axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
        )
        profile_id = "structural_" + axis.replace("%", "_pct")
        evidence_sha256 = _canonical_sha256(
            {
                "kind": "structural_stat_coverage_v1",
                "wearer": wearer.to_dict(),
                "axis": axis,
                "upstream": [item.identity_sha256 for item in rows],
            }
        )
        anchors.append(
            GcsimOptimizerAnytimeStatProfile(
                wearer=wearer,
                profile_id=profile_id,
                stat_weights=weights,
                main_scores=balanced.main_scores,
                evidence_sha256=evidence_sha256,
                feature_labels=(
                    "structural_stat_coverage",
                    f"structural_stat_axis:{axis}",
                ),
                stat_classifications=classifications,
                main_classifications=balanced.main_classifications,
            )
        )
    return (*rows, *anchors)


def build_gcsim_optimizer_uncertainty_refinement_profiles(
    profiles: Sequence[GcsimOptimizerAnytimeStatProfile],
    *,
    uncertainty_floor_ratio: float = 0.25,
    focus_multiplier: float = 1.5,
    max_focus_axes: int = 2,
) -> tuple[GcsimOptimizerAnytimeStatProfile, ...]:
    """Build bounded mixed-stat/main anchors for uncertain local response.

    These profiles are deliberately kept out of the ordinary proposal beam.
    They exist only when the paired response leaves at least one nonlinear
    roll direction at zero (uncertain or locally negligible), and are consumed
    by exact-GCSIM coordinate refinement. A small per-roll utility floor
    prevents that local zero from making a distant physical build unreachable,
    while measured useful directions still determine two bounded focus views.
    """

    rows = tuple(profiles)
    if not rows or any(
        not isinstance(item, GcsimOptimizerAnytimeStatProfile)
        for item in rows
    ):
        raise GcsimOptimizerAnytimeCandidateError(
            "uncertainty refinement requires typed response profiles"
        )
    wearer = rows[0].wearer
    if any(item.wearer != wearer for item in rows):
        raise GcsimOptimizerAnytimeCandidateError(
            "uncertainty refinement profiles must use one wearer"
        )
    if (
        not isfinite(uncertainty_floor_ratio)
        or not 0 < uncertainty_floor_ratio <= 1
    ):
        raise GcsimOptimizerAnytimeCandidateError(
            "uncertainty floor ratio must be in (0, 1]"
        )
    if not isfinite(focus_multiplier) or focus_multiplier <= 1:
        raise GcsimOptimizerAnytimeCandidateError(
            "uncertainty focus multiplier must exceed one"
        )
    if (
        isinstance(max_focus_axes, bool)
        or not isinstance(max_focus_axes, int)
        or max_focus_axes <= 0
    ):
        raise GcsimOptimizerAnytimeCandidateError(
            "uncertainty max_focus_axes must be positive"
        )
    balanced = next(
        (item for item in rows if item.profile_id == "balanced"),
        None,
    )
    if balanced is None:
        raise GcsimOptimizerAnytimeCandidateError(
            "uncertainty refinement requires a balanced response profile"
        )
    stat_status = dict(balanced.stat_classifications)
    base_weights = dict(
        zip(
            GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
            balanced.stat_weights,
            strict=True,
        )
    )
    # These are the locally non-linear artifact directions for which a zero
    # derivative is especially unsafe: crit can sit at a cap and EM can turn
    # on only after a reaction/layout change. Ordinary HP/ATK/DEF uncertainty
    # remains represented by the base response/profile family and does not
    # justify multiplying the exact-simulation coordinate domain.
    nonlinear_uncertainty_axes = {"cr", "cd", "em"}
    uncertain_axes = tuple(
        axis
        for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
        if (
            axis in GCSIM_STAT_RESPONSE_ROLL_VALUES
            and axis in nonlinear_uncertainty_axes
            and stat_status.get(axis) in {"uncertain", "negligible"}
            and base_weights.get(axis, 0.0) == 0.0
        )
    )
    if not uncertain_axes:
        return ()
    measured_roll_utilities = {
        axis: base_weights.get(axis, 0.0) * roll_value
        for axis, roll_value in GCSIM_STAT_RESPONSE_ROLL_VALUES.items()
    }
    maximum_roll_utility = max(measured_roll_utilities.values(), default=0.0)
    if maximum_roll_utility <= 0:
        return ()
    focus_axes = tuple(
        axis
        for axis, utility in sorted(
            measured_roll_utilities.items(),
            key=lambda item: (-item[1], item[0]),
        )
        if utility > 0 and stat_status.get(axis) in {"dominant", "secondary"}
    )[:max_focus_axes]
    if not focus_axes:
        return ()
    main_status = {
        (slot, axis): status
        for slot, axis, status in balanced.main_classifications
    }
    damage_main_axes = {
        "pyro%", "hydro%", "electro%", "cryo%", "anemo%",
        "geo%", "dendro%", "phys%",
    }
    main_anchor_axes = tuple(
        sorted(
            {
                axis
                for (_slot, axis), status in main_status.items()
                if (
                    (status == "uncertain" and axis in uncertain_axes)
                    or (
                        axis in damage_main_axes
                        and status in {"dominant", "secondary"}
                    )
                )
            }
        )
    )
    if not main_anchor_axes:
        return ()
    anchors: list[GcsimOptimizerAnytimeStatProfile] = []
    for focus_axis in focus_axes:
        weights = dict(base_weights)
        for axis in uncertain_axes:
            weights[axis] = max(
                weights.get(axis, 0.0),
                uncertainty_floor_ratio
                * maximum_roll_utility
                / GCSIM_STAT_RESPONSE_ROLL_VALUES[axis],
            )
        weights[focus_axis] *= focus_multiplier
        classifications = tuple(
            (
                axis,
                "secondary" if weights.get(axis, 0.0) > 0 else "negligible",
            )
            for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
        )
        for main_axis in main_anchor_axes:
            main_rows = tuple(
                (
                    slot,
                    main_axis,
                    maximum_roll_utility * 1000.0,
                )
                for slot in _VARIABLE_SLOTS
                if main_axis in _SOFT_MAIN_COVERAGE_AXES_BY_SLOT[slot]
            )
            if not main_rows:
                continue
            profile_id = (
                "uncertainty_focus_"
                + focus_axis.replace("%", "_pct")
                + "_main_"
                + main_axis.replace("%", "_pct")
            )
            evidence_sha256 = _canonical_sha256(
                {
                    "kind": "uncertainty_coordinate_profile_v1",
                    "wearer": wearer.to_dict(),
                    "upstream": [item.identity_sha256 for item in rows],
                    "uncertain_axes": list(uncertain_axes),
                    "focus_axis": focus_axis,
                    "main_anchor_axis": main_axis,
                    "uncertainty_floor_ratio": uncertainty_floor_ratio,
                    "focus_multiplier": focus_multiplier,
                }
            )
            anchors.append(
                GcsimOptimizerAnytimeStatProfile(
                    wearer=wearer,
                    profile_id=profile_id,
                    stat_weights=tuple(
                        weights.get(axis, 0.0)
                        for axis in GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
                    ),
                    main_scores=main_rows,
                    evidence_sha256=evidence_sha256,
                    feature_labels=(
                        "uncertainty_coordinate_refinement",
                        f"uncertainty_focus_axis:{focus_axis}",
                        f"uncertainty_main_axis:{main_axis}",
                    ),
                    stat_classifications=classifications,
                    main_classifications=tuple(
                        (slot, axis, "secondary")
                        for slot, axis, _score in main_rows
                    ),
                )
            )
    return tuple(anchors)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerDenseArtifact:
    record: GcsimOptimizerArtifactRecord
    stats: tuple[float, ...]
    substats: tuple[float, ...]
    main_key: str
    main_value: float
    content_fingerprint: str
    bit_mask: int

    @property
    def artifact_id(self) -> int:
        return self.record.artifact_id

    @property
    def slot(self) -> str:
        return self.record.position_key


@dataclass(frozen=True, slots=True)
class GcsimOptimizerDenseArtifactCatalog:
    artifacts: tuple[GcsimOptimizerDenseArtifact, ...]
    excluded_counts: tuple[tuple[str, int], ...]
    source_artifact_count: int
    identity_sha256: str
    schema_version: int = GCSIM_OPTIMIZER_ANYTIME_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        rows = tuple(self.artifacts)
        if tuple(item.artifact_id for item in rows) != tuple(
            sorted(item.artifact_id for item in rows)
        ):
            raise GcsimOptimizerAnytimeCandidateError(
                "dense artifacts must use deterministic ID order"
            )
        if len({item.artifact_id for item in rows}) != len(rows):
            raise GcsimOptimizerAnytimeCandidateError(
                "dense artifact IDs must be unique"
            )
        if self.source_artifact_count < len(rows):
            raise GcsimOptimizerAnytimeCandidateError(
                "dense source count is incoherent"
            )
        _require_sha256(self.identity_sha256, "identity_sha256")

    @property
    def bit_by_artifact_id(self) -> Mapping[int, int]:
        return MappingProxyType(
            {item.artifact_id: item.bit_mask for item in self.artifacts}
        )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAnytimeCandidatePlan:
    max_frontier_per_group: int = 24
    shadow_per_group: int = 3
    per_profile_slot_count: int = 12
    max_slot_pool: int = 64
    wearer_beam_width: int = 320
    max_builds_per_target: int = 64
    max_builds_per_wearer: int = 240
    joint_beam_width: int = 512
    max_joint_proposals: int = 64
    local_search_seed_count: int = 8
    max_marginal_coverage_targets: int = 2048
    marginal_conflict_beam_width: int = 32
    max_seconds: float = 180.0
    schema_version: int = GCSIM_OPTIMIZER_ANYTIME_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in (
            "max_frontier_per_group",
            "shadow_per_group",
            "per_profile_slot_count",
            "max_slot_pool",
            "wearer_beam_width",
            "max_builds_per_target",
            "max_builds_per_wearer",
            "joint_beam_width",
            "max_joint_proposals",
            "local_search_seed_count",
            "max_marginal_coverage_targets",
            "marginal_conflict_beam_width",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise GcsimOptimizerAnytimeCandidateError(
                    f"{field_name} must be a positive integer"
                )
        if not isfinite(self.max_seconds) or self.max_seconds <= 0:
            raise GcsimOptimizerAnytimeCandidateError(
                "max_seconds must be finite and positive"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "max_frontier_per_group": self.max_frontier_per_group,
            "shadow_per_group": self.shadow_per_group,
            "per_profile_slot_count": self.per_profile_slot_count,
            "max_slot_pool": self.max_slot_pool,
            "wearer_beam_width": self.wearer_beam_width,
            "max_builds_per_target": self.max_builds_per_target,
            "max_builds_per_wearer": self.max_builds_per_wearer,
            "joint_beam_width": self.joint_beam_width,
            "max_joint_proposals": self.max_joint_proposals,
            "local_search_seed_count": self.local_search_seed_count,
            "max_marginal_coverage_targets": (
                self.max_marginal_coverage_targets
            ),
            "marginal_conflict_beam_width": (
                self.marginal_conflict_beam_width
            ),
            "max_seconds": self.max_seconds,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAnytimeCandidateCoverage:
    indexed_artifact_count: int
    invalid_artifact_count: int
    eligible_piece_count: int
    pareto_piece_count: int
    shadow_piece_count: int
    expanded_wearer_state_count: int
    package_pruned_state_count: int
    floor_pruned_state_count: int
    complete_wearer_state_count: int
    materialized_candidate_count: int
    materialization_failure_count: int
    content_deduplicated_candidate_count: int
    schema_version: int = GCSIM_OPTIMIZER_ANYTIME_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in (
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
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise GcsimOptimizerAnytimeCandidateError(
                    f"{field_name} must be non-negative"
                )

    def to_dict(self) -> dict[str, int]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
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
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAnytimeWearerPool:
    wearer: GcsimOptimizerWearerIdentity
    candidates: tuple[GcsimOptimizerLazyWearerCandidate, ...]
    coverage: GcsimOptimizerAnytimeCandidateCoverage
    schema_version: int = GCSIM_OPTIMIZER_ANYTIME_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        rows = tuple(self.candidates)
        if any(item.target.wearer != self.wearer for item in rows):
            raise GcsimOptimizerAnytimeCandidateError(
                "wearer pool contains a candidate for another wearer"
            )
        if len({item.candidate_sha256 for item in rows}) != len(rows):
            raise GcsimOptimizerAnytimeCandidateError(
                "wearer pool candidate identities must be unique"
            )
        object.__setattr__(self, "candidates", rows)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAnytimeJointCoverage:
    candidate_counts_by_wearer: tuple[tuple[int, int], ...]
    expanded_state_count: int
    conflict_state_count: int
    retained_state_count: int
    local_search_state_count: int
    compiled_proposal_count: int
    compiled_rejection_count: int
    marginal_required_target_count: int = 0
    marginal_coverage_proposal_count: int = 0
    marginal_covered_targets: tuple[tuple[int, str], ...] = ()
    marginal_uncovered_targets: tuple[tuple[int, str], ...] = ()
    schema_version: int = GCSIM_OPTIMIZER_ANYTIME_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if tuple(slot for slot, _count in self.candidate_counts_by_wearer) != (
            1,
            2,
            3,
            4,
        ):
            raise GcsimOptimizerAnytimeCandidateError(
                "joint coverage must use canonical wearer order"
            )
        for field_name in (
            "expanded_state_count",
            "conflict_state_count",
            "retained_state_count",
            "local_search_state_count",
            "compiled_proposal_count",
            "compiled_rejection_count",
            "marginal_required_target_count",
            "marginal_coverage_proposal_count",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise GcsimOptimizerAnytimeCandidateError(
                    f"{field_name} must be non-negative"
                )
        covered = _validated_target_keys(
            self.marginal_covered_targets,
            "marginal_covered_targets",
        )
        uncovered = _validated_target_keys(
            self.marginal_uncovered_targets,
            "marginal_uncovered_targets",
        )
        if set(covered) & set(uncovered):
            raise GcsimOptimizerAnytimeCandidateError(
                "marginal covered/uncovered target sets overlap"
            )
        if len(covered) + len(uncovered) != self.marginal_required_target_count:
            raise GcsimOptimizerAnytimeCandidateError(
                "marginal target coverage count is incoherent"
            )
        if self.marginal_coverage_proposal_count > len(covered):
            raise GcsimOptimizerAnytimeCandidateError(
                "marginal proposal count exceeds strongest-fixed coverage"
            )
        object.__setattr__(self, "marginal_covered_targets", covered)
        object.__setattr__(self, "marginal_uncovered_targets", uncovered)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_counts_by_wearer": dict(
                self.candidate_counts_by_wearer
            ),
            "expanded_state_count": self.expanded_state_count,
            "conflict_state_count": self.conflict_state_count,
            "retained_state_count": self.retained_state_count,
            "local_search_state_count": self.local_search_state_count,
            "compiled_proposal_count": self.compiled_proposal_count,
            "compiled_rejection_count": self.compiled_rejection_count,
            "marginal_required_target_count": (
                self.marginal_required_target_count
            ),
            "marginal_coverage_proposal_count": (
                self.marginal_coverage_proposal_count
            ),
            "marginal_covered_target_count": len(
                self.marginal_covered_targets
            ),
            "marginal_uncovered_target_count": len(
                self.marginal_uncovered_targets
            ),
            "marginal_covered_targets": [
                [slot, package_sha256]
                for slot, package_sha256 in self.marginal_covered_targets
            ],
            "marginal_uncovered_targets": [
                [slot, package_sha256]
                for slot, package_sha256 in self.marginal_uncovered_targets
            ],
        }


@dataclass(frozen=True, slots=True)
class _ScoredPiece:
    artifact: GcsimOptimizerDenseArtifact
    profile_scores: tuple[float, ...]
    base_score: float
    package_index: int
    shadow: bool = False


@dataclass(frozen=True, slots=True)
class _WearerBeamState:
    chosen: tuple[_ScoredPiece, ...]
    stats: tuple[float, ...]
    package_counts: tuple[int, ...]
    score: float


@dataclass(frozen=True, slots=True)
class _JointState:
    candidates: tuple[GcsimOptimizerLazyWearerCandidate, ...]
    mask: int
    score: float
    indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _MarginalJointState:
    candidates: tuple[
        GcsimOptimizerLazyWearerCandidate | None,
        ...,
    ]
    mask: int
    score: float
    indices: tuple[int, ...]


@dataclass(slots=True)
class _MutableCoverage:
    eligible_piece_count: int = 0
    pareto_piece_count: int = 0
    shadow_piece_count: int = 0
    expanded_wearer_state_count: int = 0
    package_pruned_state_count: int = 0
    floor_pruned_state_count: int = 0
    complete_wearer_state_count: int = 0
    materialized_candidate_count: int = 0
    materialization_failure_count: int = 0
    content_deduplicated_candidate_count: int = 0


def build_gcsim_optimizer_dense_artifact_catalog(
    run_input: GcsimOptimizerRunInput,
) -> GcsimOptimizerDenseArtifactCatalog:
    """Normalize every calculation-valid frozen artifact exactly once."""

    if not isinstance(run_input, GcsimOptimizerRunInput):
        raise GcsimOptimizerAnytimeCandidateError(
            "run_input must be typed"
        )
    wearer = run_input.request.source_simulation.wearers[0]
    exclusions: Counter[str] = Counter()
    rows: list[GcsimOptimizerDenseArtifact] = []
    for bit_index, artifact in enumerate(run_input.artifact_database.artifacts):
        if not artifact.calculation_valid:
            exclusions["calculation_invalid"] += 1
            continue
        if artifact.position_key not in GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
            exclusions["artifact_slot_invalid"] += 1
            continue
        vector_result = materialize_gcsim_optimizer_artifact_stat_vector(
            artifact,
            wearer=wearer,
        )
        if not vector_result.ready or vector_result.stat_vector is None:
            exclusions[
                (
                    vector_result.diagnostics[0].code
                    if vector_result.diagnostics
                    else "artifact_stat_vector_invalid"
                )
            ] += 1
            continue
        vector = vector_result.stat_vector
        main = tuple(
            item for item in vector.contributions if item.source_kind == "main"
        )
        if len(main) != 1:
            exclusions["artifact_main_stat_ambiguous"] += 1
            continue
        full = [0.0] * len(GCSIM_OPTIMIZER_ANYTIME_STAT_AXES)
        sub = [0.0] * len(GCSIM_OPTIMIZER_ANYTIME_STAT_AXES)
        for contribution in vector.contributions:
            index = _AXIS_INDEX.get(contribution.gcsim_key)
            if index is None:
                continue
            value = float(contribution.normalized_value)
            full[index] += value
            if contribution.source_kind != "main":
                sub[index] += value
        main_key = main[0].gcsim_key
        main_value = float(main[0].normalized_value)
        content_fingerprint = _canonical_sha256(
            {
                "set_uid": artifact.set_uid,
                "slot": artifact.position_key,
                "main_key": main_key,
                "stats": [
                    [axis, full[index]]
                    for index, axis in enumerate(
                        GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
                    )
                    if full[index]
                ],
            }
        )
        rows.append(
            GcsimOptimizerDenseArtifact(
                record=artifact,
                stats=tuple(full),
                substats=tuple(sub),
                main_key=main_key,
                main_value=main_value,
                content_fingerprint=content_fingerprint,
                bit_mask=1 << bit_index,
            )
        )
    identity = _canonical_sha256(
        {
            "schema_version": GCSIM_OPTIMIZER_ANYTIME_CANDIDATE_SCHEMA_VERSION,
            "artifact_database_input_sha256": (
                run_input.artifact_database.artifact_database_input_sha256
            ),
            "axis_order": list(GCSIM_OPTIMIZER_ANYTIME_STAT_AXES),
            "artifacts": [
                [item.artifact_id, item.content_fingerprint] for item in rows
            ],
        }
    )
    return GcsimOptimizerDenseArtifactCatalog(
        artifacts=tuple(rows),
        excluded_counts=tuple(sorted(exclusions.items())),
        source_artifact_count=len(run_input.artifact_database.artifacts),
        identity_sha256=identity,
    )


def generate_gcsim_optimizer_anytime_wearer_pool(
    run_input: GcsimOptimizerRunInput,
    *,
    catalog: GcsimOptimizerDenseArtifactCatalog,
    wearer: GcsimOptimizerWearerIdentity,
    targets: Sequence[GcsimOptimizerWearerTarget],
    profiles: Sequence[GcsimOptimizerAnytimeStatProfile],
    package_score_by_target_identity: Mapping[str, float] | None = None,
    require_target_coverage: bool = False,
    hard_main_pruning: bool = True,
    plan: GcsimOptimizerAnytimeCandidatePlan | None = None,
    is_cancelled: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] = monotonic,
) -> GcsimOptimizerAnytimeWearerPool:
    """Build a bounded, diverse, strict five-piece pool for one wearer."""

    selected_plan = plan or GcsimOptimizerAnytimeCandidatePlan()
    target_rows = tuple(targets)
    profile_rows = tuple(profiles)
    package_scores = {
        str(key): float(value)
        for key, value in dict(
            package_score_by_target_identity or {}
        ).items()
    }
    if any(
        not isfinite(value) or value < 0
        for value in package_scores.values()
    ):
        raise GcsimOptimizerAnytimeCandidateError(
            "package scores must be finite and non-negative"
        )
    if not target_rows or any(item.wearer != wearer for item in target_rows):
        raise GcsimOptimizerAnytimeCandidateError(
            "targets must be a non-empty single-wearer domain"
        )
    if not profile_rows or any(item.wearer != wearer for item in profile_rows):
        raise GcsimOptimizerAnytimeCandidateError(
            "profiles must be a non-empty single-wearer family"
        )
    if not isinstance(require_target_coverage, bool):
        raise GcsimOptimizerAnytimeCandidateError(
            "require_target_coverage must be boolean"
        )
    if not isinstance(hard_main_pruning, bool):
        raise GcsimOptimizerAnytimeCandidateError(
            "hard_main_pruning must be boolean"
        )
    if (
        require_target_coverage
        and len(target_rows) > selected_plan.max_marginal_coverage_targets
    ):
        raise GcsimOptimizerAnytimeCandidateError(
            "retained package count exceeds marginal coverage bound"
        )
    deadline = clock() + selected_plan.max_seconds
    coverage = _MutableCoverage()
    all_candidates: list[GcsimOptimizerLazyWearerCandidate] = []
    attempted_target_ids: set[str] = set()
    for target in target_rows:
        if is_cancelled() or clock() >= deadline:
            break
        attempted_target_ids.add(_target_identity(target))
        all_candidates.extend(
            _generate_target_candidates(
                run_input,
                catalog=catalog,
                target=target,
                profiles=profile_rows,
                package_score=package_scores.get(
                    _target_identity(target),
                    0.0,
                ),
                plan=selected_plan,
                hard_main_pruning=hard_main_pruning,
                coverage=coverage,
                deadline=deadline,
                is_cancelled=is_cancelled,
                clock=clock,
            )
        )
    if (
        require_target_coverage
        and not is_cancelled()
        and len(attempted_target_ids) != len(target_rows)
    ):
        # Physically impossible targets may produce no exact build and are
        # reported later as uncovered. A deadline must not silently make
        # deterministic late targets disappear.
        raise GcsimOptimizerAnytimeCandidateError(
            "marginal wearer generation stopped before target coverage"
        )
    # Content-identical candidates are useful only up to a small physical
    # multiplicity: one primary plus bounded conflict-repair shadows.
    by_content: dict[
        tuple[str, str], list[GcsimOptimizerLazyWearerCandidate]
    ] = defaultdict(list)
    for candidate in sorted(all_candidates, key=_candidate_rank):
        by_content[
            (
                _target_identity(candidate.target),
                candidate.content_fingerprint,
            )
        ].append(candidate)
    retained: list[GcsimOptimizerLazyWearerCandidate] = []
    for rows in by_content.values():
        retained.extend(rows[: 1 + selected_plan.shadow_per_group])
        coverage.content_deduplicated_candidate_count += max(
            len(rows) - (1 + selected_plan.shadow_per_group),
            0,
        )
    retained_limit = selected_plan.max_builds_per_wearer
    if require_target_coverage:
        retained_limit = max(
            retained_limit,
            len(
                {
                    _target_identity(candidate.target)
                    for candidate in retained
                }
            ),
        )
    retained = _retain_diverse_candidates(
        retained,
        limit=retained_limit,
    )
    frozen_coverage = GcsimOptimizerAnytimeCandidateCoverage(
        indexed_artifact_count=len(catalog.artifacts),
        invalid_artifact_count=(
            catalog.source_artifact_count - len(catalog.artifacts)
        ),
        eligible_piece_count=coverage.eligible_piece_count,
        pareto_piece_count=coverage.pareto_piece_count,
        shadow_piece_count=coverage.shadow_piece_count,
        expanded_wearer_state_count=coverage.expanded_wearer_state_count,
        package_pruned_state_count=coverage.package_pruned_state_count,
        floor_pruned_state_count=coverage.floor_pruned_state_count,
        complete_wearer_state_count=coverage.complete_wearer_state_count,
        materialized_candidate_count=coverage.materialized_candidate_count,
        materialization_failure_count=coverage.materialization_failure_count,
        content_deduplicated_candidate_count=(
            coverage.content_deduplicated_candidate_count
        ),
    )
    return GcsimOptimizerAnytimeWearerPool(
        wearer=wearer,
        candidates=tuple(sorted(retained, key=_candidate_rank)),
        coverage=frozen_coverage,
    )


def build_gcsim_optimizer_anytime_joint_proposals(
    run_input: GcsimOptimizerRunInput,
    *,
    catalog: GcsimOptimizerDenseArtifactCatalog,
    wearer_pools: Sequence[GcsimOptimizerAnytimeWearerPool],
    marginal_required_targets: Sequence[
        GcsimOptimizerWearerTarget
    ] = (),
    plan: GcsimOptimizerAnytimeCandidatePlan | None = None,
    execution_identity_sha256: str,
    is_cancelled: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] = monotonic,
) -> tuple[
    tuple[GcsimOptimizerJointProposal, ...],
    GcsimOptimizerAnytimeJointCoverage,
]:
    """Combine four wearer pools with bit masks and a bounded diverse beam."""

    selected_plan = plan or GcsimOptimizerAnytimeCandidatePlan()
    _require_sha256(
        execution_identity_sha256,
        "execution_identity_sha256",
    )
    pools = tuple(wearer_pools)
    if (
        len(pools) != 4
        or tuple(item.wearer.team_slot for item in pools) != (1, 2, 3, 4)
    ):
        raise GcsimOptimizerAnytimeCandidateError(
            "joint search requires four canonical wearer pools"
        )
    required_targets = tuple(marginal_required_targets)
    if any(
        not isinstance(target, GcsimOptimizerWearerTarget)
        for target in required_targets
    ):
        raise GcsimOptimizerAnytimeCandidateError(
            "marginal coverage targets must be typed"
        )
    required_keys = _validated_target_keys(
        tuple(_account_target_key(target) for target in required_targets),
        "marginal_required_targets",
    )
    if len(required_keys) != len(required_targets):
        raise GcsimOptimizerAnytimeCandidateError(
            "marginal coverage targets must be unique"
        )
    if len(required_keys) > selected_plan.max_marginal_coverage_targets:
        raise GcsimOptimizerAnytimeCandidateError(
            "marginal coverage target count exceeds its plan bound"
        )
    pool_wearers = {item.wearer for item in pools}
    if any(target.wearer not in pool_wearers for target in required_targets):
        raise GcsimOptimizerAnytimeCandidateError(
            "marginal coverage target wearer is outside the joint pools"
        )
    if any(not item.candidates for item in pools):
        return (), GcsimOptimizerAnytimeJointCoverage(
            candidate_counts_by_wearer=tuple(
                (item.wearer.team_slot, len(item.candidates))
                for item in pools
            ),
            expanded_state_count=0,
            conflict_state_count=0,
            retained_state_count=0,
            local_search_state_count=0,
            compiled_proposal_count=0,
            compiled_rejection_count=0,
            marginal_required_target_count=len(required_keys),
            marginal_uncovered_targets=required_keys,
        )
    bit_by_id = catalog.bit_by_artifact_id
    masks: dict[str, int] = {}
    for pool in pools:
        for candidate in pool.candidates:
            mask = 0
            for artifact_id in candidate.assignment.artifact_ids:
                mask |= bit_by_id[artifact_id]
            masks[candidate.candidate_sha256] = mask
    proposals: list[GcsimOptimizerJointProposal] = []
    rejected = 0
    seen_configs: set[str] = set()
    proposal_index_by_config: dict[str, int] = {}
    covered_keys: set[tuple[int, str]] = set()
    marginal_proposal_count = 0
    marginal_expanded = 0
    marginal_conflicts = 0

    # Coverage proposals are built before the ordinary joint beam.  Their
    # domain is bounded by explicit plan fields, and this order prevents a
    # late retained package from disappearing merely because the ordinary
    # max_joint_proposals cap was filled by stronger package combinations.
    for target_key in required_keys:
        if target_key in covered_keys or is_cancelled():
            continue
        fixed_offset = 0
        while target_key not in covered_keys and not is_cancelled():
            coverage_label = (
                "marginal_package_coverage:"
                f"{target_key[0]}:{target_key[1]}"
            )
            (
                states,
                state_expanded,
                state_conflicts,
                next_fixed_offset,
            ) = _marginal_joint_states_for_target(
                pools,
                target_key=target_key,
                masks=masks,
                beam_width=selected_plan.marginal_conflict_beam_width,
                fixed_offset=fixed_offset,
                is_cancelled=is_cancelled,
            )
            marginal_expanded += state_expanded
            marginal_conflicts += state_conflicts
            for state in states:
                proposal = _compile_anytime_joint_state(
                    run_input,
                    state=state,
                    execution_identity_sha256=execution_identity_sha256,
                    extra_labels=(coverage_label,),
                )
                if proposal is None:
                    rejected += 1
                    continue
                proposal_keys = {
                    _account_target_key(candidate.target)
                    for candidate in proposal.wearer_candidates
                }
                config_sha256 = (
                    proposal.compiled_candidate.compiled_config_sha256
                )
                existing_index = proposal_index_by_config.get(config_sha256)
                if existing_index is None:
                    proposal_index_by_config[config_sha256] = len(proposals)
                    proposals.append(proposal)
                    seen_configs.add(config_sha256)
                    marginal_proposal_count += 1
                else:
                    # One byte-identical exact account config is one screen
                    # request.  If it is the strongest-fixed witness for more
                    # than one retained package, attach every obligation to
                    # that one proposal instead of emitting duplicate farming
                    # candidate scopes.
                    existing = proposals[existing_index]
                    proposals[existing_index] = replace(
                        existing,
                        diversity_labels=(
                            *existing.diversity_labels,
                            coverage_label,
                        ),
                    )
                # A package obligation is fulfilled only by the proposal
                # built with that package fixed to its strongest completable
                # physical candidate.  Merely appearing as a companion does
                # not count.
                if target_key in proposal_keys:
                    covered_keys.add(target_key)
                break
            if target_key in covered_keys or not states:
                break
            if next_fixed_offset <= fixed_offset:
                raise GcsimOptimizerAnytimeCandidateError(
                    "marginal conflict repair made no progress"
                )
            fixed_offset = next_fixed_offset

    deadline = clock() + selected_plan.max_seconds
    beam = (_JointState((), 0, 0.0, ()),)
    expanded = marginal_expanded
    conflicts = marginal_conflicts
    for pool in pools:
        next_rows: list[_JointState] = []
        for state in beam:
            for index, candidate in enumerate(pool.candidates):
                if is_cancelled() or clock() >= deadline:
                    break
                expanded += 1
                candidate_mask = masks[candidate.candidate_sha256]
                if state.mask & candidate_mask:
                    conflicts += 1
                    continue
                next_rows.append(
                    _JointState(
                        candidates=state.candidates + (candidate,),
                        mask=state.mask | candidate_mask,
                        score=state.score + float(candidate.proposal_score),
                        indices=state.indices + (index,),
                    )
                )
            if is_cancelled() or clock() >= deadline:
                break
        beam = tuple(
            _retain_diverse_joint_states(
                next_rows,
                limit=selected_plan.joint_beam_width,
            )
        )
        if not beam or is_cancelled() or clock() >= deadline:
            break
    complete = list(beam if beam and len(beam[0].candidates) == 4 else ())
    local_count = 0
    for seed in tuple(complete[: selected_plan.local_search_seed_count]):
        for wearer_index, pool in enumerate(pools):
            base_without = (
                seed.mask
                ^ masks[seed.candidates[wearer_index].candidate_sha256]
            )
            for candidate_index, candidate in enumerate(pool.candidates):
                candidate_mask = masks[candidate.candidate_sha256]
                if base_without & candidate_mask:
                    continue
                candidates = list(seed.candidates)
                candidates[wearer_index] = candidate
                indices = list(seed.indices)
                indices[wearer_index] = candidate_index
                complete.append(
                    _JointState(
                        candidates=tuple(candidates),
                        mask=base_without | candidate_mask,
                        score=(
                            seed.score
                            - float(
                                seed.candidates[
                                    wearer_index
                                ].proposal_score
                            )
                            + float(candidate.proposal_score)
                        ),
                        indices=tuple(indices),
                    )
                )
                local_count += 1
    selected_states = _retain_diverse_joint_states(
        complete,
        limit=selected_plan.max_joint_proposals,
    )
    for state in selected_states:
        if is_cancelled() or clock() >= deadline:
            break
        proposal = _compile_anytime_joint_state(
            run_input,
            execution_identity_sha256=execution_identity_sha256,
            state=state,
        )
        if proposal is None:
            rejected += 1
            continue
        candidate = proposal.compiled_candidate
        if candidate.compiled_config_sha256 in seen_configs:
            # Accepted product limitation: byte-identical artifact content is
            # one simulation, while physical alternatives stay in candidate
            # pools for conflict repair.
            continue
        seen_configs.add(candidate.compiled_config_sha256)
        proposals.append(proposal)
    proposals.sort(
        key=lambda item: (
            -float(item.surrogate_score),
            item.proposal_sha256,
        )
    )
    if len(proposals) > (
        selected_plan.max_joint_proposals
        + selected_plan.max_marginal_coverage_targets
    ):
        raise GcsimOptimizerAnytimeCandidateError(
            "joint proposal output exceeded its explicit bounded plan"
        )
    compiled_configs = tuple(
        proposal.compiled_candidate.compiled_config_sha256
        for proposal in proposals
    )
    if len(set(compiled_configs)) != len(compiled_configs):
        raise GcsimOptimizerAnytimeCandidateError(
            "joint proposals contain duplicate exact simulation configs"
        )
    coverage = GcsimOptimizerAnytimeJointCoverage(
        candidate_counts_by_wearer=tuple(
            (item.wearer.team_slot, len(item.candidates)) for item in pools
        ),
        expanded_state_count=expanded,
        conflict_state_count=conflicts,
        retained_state_count=len(selected_states),
        local_search_state_count=local_count,
        compiled_proposal_count=len(proposals),
        compiled_rejection_count=rejected,
        marginal_required_target_count=len(required_keys),
        marginal_coverage_proposal_count=marginal_proposal_count,
        marginal_covered_targets=tuple(sorted(covered_keys)),
        marginal_uncovered_targets=tuple(
            sorted(set(required_keys) - covered_keys)
        ),
    )
    return tuple(proposals), coverage


def build_gcsim_optimizer_coordinate_refinement_proposals(
    run_input: GcsimOptimizerRunInput,
    *,
    catalog: GcsimOptimizerDenseArtifactCatalog,
    seed_proposals: Sequence[GcsimOptimizerJointProposal],
    wearer_pools: Sequence[GcsimOptimizerAnytimeWearerPool],
    execution_identity_sha256: str,
    max_candidates_per_wearer: int = 320,
    conflict_beam_width: int = 16,
    is_cancelled: Callable[[], bool] = lambda: False,
) -> tuple[GcsimOptimizerJointProposal, ...]:
    """Build exact-GCSIM coordinate moves around confirmed team leaders.

    Every retained wearer candidate gets one bounded attempt per seed.  The
    current seed assignments are preferred; when a fixed candidate consumes
    one of their artifacts, a small beam repairs only the conflicting
    companions.  The output is bounded by
    ``seed_count * 4 * max_candidates_per_wearer`` and contains no duplicate
    exact configs.
    """

    if not isinstance(run_input, GcsimOptimizerRunInput):
        raise GcsimOptimizerAnytimeCandidateError(
            "coordinate refinement requires a typed run input"
        )
    seeds = tuple(seed_proposals)
    pools = tuple(wearer_pools)
    if any(not isinstance(item, GcsimOptimizerJointProposal) for item in seeds):
        raise GcsimOptimizerAnytimeCandidateError(
            "coordinate seeds must be typed joint proposals"
        )
    if len({item.proposal_sha256 for item in seeds}) != len(seeds):
        raise GcsimOptimizerAnytimeCandidateError(
            "coordinate seed identities must be unique"
        )
    if (
        len(pools) != 4
        or tuple(item.wearer.team_slot for item in pools) != (1, 2, 3, 4)
    ):
        raise GcsimOptimizerAnytimeCandidateError(
            "coordinate refinement requires four canonical wearer pools"
        )
    for field_name, value in (
        ("max_candidates_per_wearer", max_candidates_per_wearer),
        ("conflict_beam_width", conflict_beam_width),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise GcsimOptimizerAnytimeCandidateError(
                f"{field_name} must be a positive integer"
            )
    _require_sha256(execution_identity_sha256, "execution_identity_sha256")
    if not seeds:
        return ()
    bit_by_id = catalog.bit_by_artifact_id
    masks: dict[str, int] = {}
    for pool in pools:
        for candidate in pool.candidates:
            mask = 0
            for artifact_id in candidate.assignment.artifact_ids:
                mask |= bit_by_id[artifact_id]
            masks[candidate.candidate_sha256] = mask
    for seed in seeds:
        for candidate in seed.wearer_candidates:
            if candidate.candidate_sha256 not in masks:
                mask = 0
                for artifact_id in candidate.assignment.artifact_ids:
                    mask |= bit_by_id[artifact_id]
                masks[candidate.candidate_sha256] = mask

    proposals: list[GcsimOptimizerJointProposal] = []
    seen_configs = {
        seed.compiled_candidate.compiled_config_sha256 for seed in seeds
    }
    for seed_index, seed in enumerate(seeds):
        if is_cancelled():
            break
        seed_by_slot = {
            item.target.wearer.team_slot: item
            for item in seed.wearer_candidates
        }
        if tuple(sorted(seed_by_slot)) != (1, 2, 3, 4):
            raise GcsimOptimizerAnytimeCandidateError(
                "coordinate seed does not cover canonical slots"
            )
        for wearer_index, pool in enumerate(pools):
            if is_cancelled():
                break
            slot = wearer_index + 1
            for fixed in pool.candidates[:max_candidates_per_wearer]:
                if is_cancelled():
                    break
                if (
                    fixed.assignment.artifact_ids
                    == seed_by_slot[slot].assignment.artifact_ids
                ):
                    continue
                candidates: list[
                    GcsimOptimizerLazyWearerCandidate | None
                ] = [None, None, None, None]
                candidates[wearer_index] = fixed
                indices = [-1, -1, -1, -1]
                indices[wearer_index] = 0
                mask = masks[fixed.candidate_sha256]
                score = float(fixed.proposal_score)
                for companion_index, companion_pool in enumerate(pools):
                    if companion_index == wearer_index:
                        continue
                    companion_slot = companion_index + 1
                    seed_companion = seed_by_slot[companion_slot]
                    options = (
                        seed_companion,
                        *tuple(
                            candidate
                            for candidate in companion_pool.candidates[
                                :max_candidates_per_wearer
                            ]
                            if candidate.assignment.artifact_ids
                            != seed_companion.assignment.artifact_ids
                        ),
                    )
                    selected = next(
                        (
                            (candidate_index, candidate)
                            for candidate_index, candidate in enumerate(
                                options[: 1 + conflict_beam_width]
                            )
                            if not (
                                mask & masks[candidate.candidate_sha256]
                            )
                        ),
                        None,
                    )
                    if selected is None:
                        break
                    candidate_index, candidate = selected
                    candidates[companion_index] = candidate
                    indices[companion_index] = candidate_index
                    mask |= masks[candidate.candidate_sha256]
                    score += float(candidate.proposal_score)
                if not all(item is not None for item in candidates):
                    continue
                complete = _JointState(
                    candidates=tuple(
                        item for item in candidates if item is not None
                    ),
                    mask=mask,
                    score=score,
                    indices=tuple(indices),
                )
                proposal = _compile_anytime_joint_state(
                    run_input,
                    state=complete,
                    execution_identity_sha256=execution_identity_sha256,
                    extra_labels=(
                        "exact_gcsim_coordinate_refinement",
                        f"coordinate_seed:{seed_index}",
                        f"coordinate_fixed_slot:{slot}",
                        f"coordinate_fixed_candidate:{fixed.candidate_sha256}",
                        *tuple(
                            f"coordinate_fixed_feature:{slot}:{label}"
                            for label in fixed.feature_labels
                            if label.startswith(
                                (
                                    "structural_stat_axis:",
                                    "main_axis_anchor:",
                                    "uncertainty_",
                                )
                            )
                        ),
                    ),
                )
                if proposal is None:
                    continue
                config_sha256 = (
                    proposal.compiled_candidate.compiled_config_sha256
                )
                if config_sha256 in seen_configs:
                    continue
                seen_configs.add(config_sha256)
                changed = sum(
                    candidate.assignment.artifact_ids
                    != seed_by_slot[candidate.target.wearer.team_slot]
                    .assignment.artifact_ids
                    for candidate in complete.candidates
                )
                proposals.append(
                    replace(proposal, changed_wearer_count=changed)
                )
    maximum = len(seeds) * 4 * max_candidates_per_wearer
    if len(proposals) > maximum:
        raise GcsimOptimizerAnytimeCandidateError(
            "coordinate proposal output exceeded its explicit bound"
        )
    return tuple(
        sorted(
            proposals,
            key=lambda item: (
                item.changed_wearer_count,
                -float(item.surrogate_score),
                item.proposal_sha256,
            ),
        )
    )


def _marginal_joint_states_for_target(
    pools: tuple[GcsimOptimizerAnytimeWearerPool, ...],
    *,
    target_key: tuple[int, str],
    masks: Mapping[str, int],
    beam_width: int,
    fixed_offset: int,
    is_cancelled: Callable[[], bool],
) -> tuple[tuple[_JointState, ...], int, int, int]:
    """Find the strongest completable physical build for one package.

    The fixed package candidate is tried in score order.  Companions use a
    small bounded beam solely for artifact-conflict repair; this is not a
    Cartesian package search.
    """

    wearer_index = target_key[0] - 1
    fixed_rows = tuple(
        (candidate_index, candidate)
        for candidate_index, candidate in enumerate(
            pools[wearer_index].candidates
        )
        if _account_target_key(candidate.target) == target_key
    )
    if (
        isinstance(fixed_offset, bool)
        or not isinstance(fixed_offset, int)
        or not 0 <= fixed_offset <= len(fixed_rows)
    ):
        raise GcsimOptimizerAnytimeCandidateError(
            "marginal fixed candidate offset is invalid"
        )
    expanded = 0
    conflicts = 0
    for fixed_position in range(fixed_offset, len(fixed_rows)):
        fixed_index, fixed = fixed_rows[fixed_position]
        if is_cancelled():
            break
        candidates: list[
            GcsimOptimizerLazyWearerCandidate | None
        ] = [None, None, None, None]
        candidates[wearer_index] = fixed
        indices = [-1, -1, -1, -1]
        indices[wearer_index] = fixed_index
        states = (
            _MarginalJointState(
                candidates=tuple(candidates),
                mask=masks[fixed.candidate_sha256],
                score=float(fixed.proposal_score),
                indices=tuple(indices),
            ),
        )
        for companion_index, pool in enumerate(pools):
            if companion_index == wearer_index:
                continue
            next_rows: list[_MarginalJointState] = []
            for state in states:
                for candidate_index, candidate in enumerate(pool.candidates):
                    if is_cancelled():
                        break
                    expanded += 1
                    candidate_mask = masks[candidate.candidate_sha256]
                    if state.mask & candidate_mask:
                        conflicts += 1
                        continue
                    next_candidates = list(state.candidates)
                    next_candidates[companion_index] = candidate
                    next_indices = list(state.indices)
                    next_indices[companion_index] = candidate_index
                    next_rows.append(
                        _MarginalJointState(
                            candidates=tuple(next_candidates),
                            mask=state.mask | candidate_mask,
                            score=(
                                state.score
                                + float(candidate.proposal_score)
                            ),
                            indices=tuple(next_indices),
                        )
                    )
                if is_cancelled():
                    break
            states = tuple(
                _retain_marginal_joint_states(
                    next_rows,
                    limit=beam_width,
                )
            )
            if not states or is_cancelled():
                break
        complete = tuple(
            _JointState(
                candidates=tuple(
                    candidate
                    for candidate in state.candidates
                    if candidate is not None
                ),
                mask=state.mask,
                score=state.score,
                indices=state.indices,
            )
            for state in states
            if all(candidate is not None for candidate in state.candidates)
        )
        if complete:
            return complete, expanded, conflicts, fixed_position + 1
    return (), expanded, conflicts, len(fixed_rows)


def _retain_marginal_joint_states(
    rows: Sequence[_MarginalJointState],
    *,
    limit: int,
) -> list[_MarginalJointState]:
    deduplicated: dict[tuple[str, ...], _MarginalJointState] = {}
    for row in rows:
        key = tuple(
            "" if candidate is None else candidate.candidate_sha256
            for candidate in row.candidates
        )
        current = deduplicated.get(key)
        if current is None or row.score > current.score:
            deduplicated[key] = row
    return sorted(
        deduplicated.values(),
        key=lambda item: (
            -item.score,
            tuple(
                ""
                if candidate is None
                else candidate.candidate_sha256
                for candidate in item.candidates
            ),
        ),
    )[:limit]


def _compile_anytime_joint_state(
    run_input: GcsimOptimizerRunInput,
    *,
    state: _JointState,
    execution_identity_sha256: str,
    extra_labels: Sequence[str] = (),
) -> GcsimOptimizerJointProposal | None:
    witness = GcsimOptimizerAccountAssignmentWitness(
        request_sha256=run_input.request.request_sha256,
        artifact_database_input_sha256=(
            run_input.artifact_database.artifact_database_input_sha256
        ),
        wearer_assignments=tuple(
            item.assignment for item in state.candidates
        ),
    )
    targets = tuple(item.target for item in state.candidates)
    compiled = compile_gcsim_optimizer_team_candidate(
        run_input,
        assignment_witness=witness,
        targets=targets,
        execution_identity_sha256=execution_identity_sha256,
    )
    if not compiled.ready or compiled.candidate is None:
        return None
    candidate = compiled.candidate
    labels = tuple(
        sorted(
            {
                *extra_labels,
                *(
                    label
                    for row in state.candidates
                    for label in row.feature_labels
                ),
            }
        )
    )
    payload = {
        "schema_version": GCSIM_OPTIMIZER_ANYTIME_CANDIDATE_SCHEMA_VERSION,
        "run_input_sha256": run_input.run_input_sha256,
        "candidate_identity_sha256": candidate.candidate_identity_sha256,
        "wearer_candidate_sha256s": [
            item.candidate_sha256 for item in state.candidates
        ],
        "surrogate_score": _float_text(state.score),
    }
    return GcsimOptimizerJointProposal(
        wearer_candidates=state.candidates,
        compiled_candidate=candidate,
        surrogate_score=_float_text(state.score),
        changed_wearer_count=sum(index > 0 for index in state.indices),
        diversity_labels=labels,
        proposal_sha256=_canonical_sha256(payload),
    )


def _generate_target_candidates(
    run_input: GcsimOptimizerRunInput,
    *,
    catalog: GcsimOptimizerDenseArtifactCatalog,
    target: GcsimOptimizerWearerTarget,
    profiles: tuple[GcsimOptimizerAnytimeStatProfile, ...],
    package_score: float,
    plan: GcsimOptimizerAnytimeCandidatePlan,
    hard_main_pruning: bool,
    coverage: _MutableCoverage,
    deadline: float,
    is_cancelled: Callable[[], bool],
    clock: Callable[[], float],
) -> tuple[GcsimOptimizerLazyWearerCandidate, ...]:
    package_uids, requirements = _package_requirements(target)
    package_index = {
        set_uid: index for index, set_uid in enumerate(package_uids)
    }
    override = next(
        (
            item
            for item in run_input.request.four_star_overrides
            if item.wearer == target.wearer
        ),
        None,
    )
    effective_minimums = effective_gcsim_optimizer_artifact_minimums(
        run_input,
        target=target,
    )
    useful_main_axes_by_slot = {
        slot: {
            axis
            for profile in profiles
            for axis in profile.retained_main_axes_by_slot[slot]
        }
        for slot in _VARIABLE_SLOTS
    }
    for axis in effective_minimums:
        if axis in {"hp%", "atk%", "def%", "em", "er"}:
            useful_main_axes_by_slot["sands"].add(axis)
        if axis in {
            "hp%", "atk%", "def%", "em", "pyro%", "hydro%",
            "electro%", "cryo%", "anemo%", "geo%", "dendro%", "phys%",
        }:
            useful_main_axes_by_slot["goblet"].add(axis)
        if axis in {"hp%", "atk%", "def%", "em", "cr", "cd", "heal"}:
            useful_main_axes_by_slot["circlet"].add(axis)
    by_slot: dict[str, list[_ScoredPiece]] = {
        slot: [] for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
    }
    for artifact in catalog.artifacts:
        eligibility = evaluate_gcsim_optimizer_artifact_eligibility(
            artifact.record,
            wearer=target.wearer,
            four_star_override=override,
            package_set_uids=package_uids,
        )
        if not eligibility.eligible:
            continue
        useful_mains = useful_main_axes_by_slot.get(artifact.slot, set())
        if (
            hard_main_pruning
            and useful_mains
            and artifact.main_key not in useful_mains
        ):
            # V2 response measured this main against the same synthetic state
            # and found another legal direction useful while this one was not.
            # Do not spend beam width or GCSIM evaluations on the known-zero
            # main merely because its substats happen to look attractive.
            continue
        coverage.eligible_piece_count += 1
        scores = tuple(
            _piece_score(artifact, profile) for profile in profiles
        )
        by_slot[artifact.slot].append(
            _ScoredPiece(
                artifact=artifact,
                profile_scores=scores,
                base_score=scores[0],
                package_index=package_index.get(
                    artifact.record.set_uid,
                    -1,
                ),
            )
        )
    retained_by_slot: dict[str, tuple[_ScoredPiece, ...]] = {}
    for slot, rows in by_slot.items():
        grouped: dict[
            tuple[int, str, int | None], list[_ScoredPiece]
        ] = defaultdict(list)
        for row in rows:
            grouped[
                (
                    row.package_index,
                    row.artifact.main_key,
                    row.artifact.record.rarity,
                )
            ].append(row)
        retained_rows: list[_ScoredPiece] = []
        for group_rows in grouped.values():
            shadow_limit = plan.shadow_per_group
            if group_rows[0].package_index < 0:
                # Every wearer competes for the same off-set pieces.  A
                # strictly weaker local score can therefore be the strongest
                # conflict-free team choice after a better piece is consumed
                # elsewhere.  Keep a bounded physical repair reservoir rather
                # than treating all off-pieces as one three-item shadow.
                shadow_limit = max(
                    shadow_limit,
                    plan.per_profile_slot_count,
                )
            frontier, shadow = _pareto_and_shadow(
                group_rows,
                frontier_limit=plan.max_frontier_per_group,
                shadow_limit=shadow_limit,
            )
            coverage.pareto_piece_count += len(frontier)
            coverage.shadow_piece_count += len(shadow)
            retained_rows.extend(frontier)
            retained_rows.extend(
                _ScoredPiece(
                    artifact=item.artifact,
                    profile_scores=item.profile_scores,
                    base_score=item.base_score,
                    package_index=item.package_index,
                    shadow=True,
                )
                for item in shadow
            )
        retained_by_slot[slot] = tuple(
            _retain_slot_profile_diversity(
                retained_rows,
                profile_count=len(profiles),
                per_profile=plan.per_profile_slot_count,
                limit=plan.max_slot_pool,
            )
        )
    if any(not retained_by_slot[slot] for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS):
        return ()
    minima = {
        _AXIS_INDEX[axis]: float(value)
        for axis, value in effective_minimums.items()
        if axis in _AXIS_INDEX
    }
    remaining_stat_max = _remaining_stat_maxima(retained_by_slot)
    all_complete: list[tuple[_WearerBeamState, int]] = []
    for profile_index, profile in enumerate(profiles):
        beam = (
            _WearerBeamState(
                chosen=(),
                stats=(0.0,) * len(GCSIM_OPTIMIZER_ANYTIME_STAT_AXES),
                package_counts=(0,) * len(package_uids),
                score=0.0,
            ),
        )
        for slot_index, slot in enumerate(GCSIM_OPTIMIZER_ARTIFACT_SLOTS):
            next_rows: list[_WearerBeamState] = []
            remaining_slots = len(GCSIM_OPTIMIZER_ARTIFACT_SLOTS) - slot_index - 1
            for state in beam:
                for piece in retained_by_slot[slot]:
                    coverage.expanded_wearer_state_count += 1
                    counts = list(state.package_counts)
                    if piece.package_index >= 0:
                        counts[piece.package_index] += 1
                    if any(
                        counts[index] + remaining_slots < required
                        for index, required in enumerate(requirements)
                    ):
                        coverage.package_pruned_state_count += 1
                        continue
                    stats = tuple(
                        left + right
                        for left, right in zip(
                            state.stats,
                            piece.artifact.stats,
                            strict=True,
                        )
                    )
                    if any(
                        stats[index]
                        + remaining_stat_max[slot_index + 1][index]
                        + 1e-12
                        < minimum
                        for index, minimum in minima.items()
                    ):
                        coverage.floor_pruned_state_count += 1
                        continue
                    next_rows.append(
                        _WearerBeamState(
                            chosen=state.chosen + (piece,),
                            stats=stats,
                            package_counts=tuple(counts),
                            score=(
                                state.score
                                + piece.profile_scores[profile_index]
                            ),
                        )
                    )
            beam = tuple(
                _retain_hybrid_wearer_beam_states(
                    next_rows,
                    limit=plan.wearer_beam_width,
                )
            )
            if not beam or is_cancelled() or clock() >= deadline:
                break
        for state in beam:
            if len(state.chosen) != len(GCSIM_OPTIMIZER_ARTIFACT_SLOTS):
                continue
            if any(
                state.package_counts[index] < required
                for index, required in enumerate(requirements)
            ):
                continue
            if any(
                state.stats[index] + 1e-12 < minimum
                for index, minimum in minima.items()
            ):
                continue
            coverage.complete_wearer_state_count += 1
            all_complete.append((state, profile_index))
    all_complete.sort(
        key=lambda item: (
            -item[0].score,
            tuple(
                row.artifact.artifact_id for row in item[0].chosen
            ),
            item[1],
        )
    )
    # Scores are comparable inside one response profile, not across profiles:
    # crit-chance, crit-damage, and focused views intentionally use different
    # scales.  Keep a normalized global head plus bounded profile/layout and
    # physical-conflict witnesses before exact GCSIM becomes the judge.
    all_complete = _retain_hybrid_complete_states(
        all_complete,
        limit=plan.max_builds_per_target,
    )
    candidates: list[GcsimOptimizerLazyWearerCandidate] = []
    seen_assignments: set[tuple[int, ...]] = set()
    for state, profile_index in all_complete:
        ids = tuple(
            item.artifact.artifact_id for item in state.chosen
        )
        if ids in seen_assignments:
            continue
        seen_assignments.add(ids)
        assignment = GcsimOptimizerWearerArtifactAssignment(
            wearer=target.wearer,
            artifact_ids_by_slot=dict(
                zip(GCSIM_OPTIMIZER_ARTIFACT_SLOTS, ids, strict=True)
            ),
        )
        materialized = materialize_gcsim_optimizer_wearer_build(
            run_input,
            assignment=assignment,
            target=target,
        )
        if not materialized.ready or materialized.build is None:
            coverage.materialization_failure_count += 1
            continue
        coverage.materialized_candidate_count += 1
        build = materialized.build
        profile = profiles[profile_index]
        # Every candidate is ranked on the same balanced, team-DPS-response
        # scale.  The originating focused profile remains a separate feature
        # label used by wearer/joint diversity; its intentionally rescaled raw
        # score must never be summed with another profile or wearer.
        base_score = package_score + sum(
            _piece_score(item.artifact, profiles[0])
            for item in state.chosen
        )
        labels = {
            f"profile:{profile.profile_id}",
            *profile.feature_labels,
        }
        if package_score > 0:
            labels.add("measured_package_impact")
        if any(item.shadow for item in state.chosen):
            labels.add("shadow_alternative")
        if any(axis == "em" for _slot, axis, _score in profile.main_scores):
            if "em" in profile.profile_id:
                labels.add("em_response")
        variable_mains = tuple(
            item.artifact.main_key for item in state.chosen[2:]
        )
        labels.add("main_shape:" + "/".join(variable_mains))
        if variable_mains not in {
            ("atk%", "atk%", "cr"),
            ("atk%", "atk%", "cd"),
        }:
            labels.add("unusual_main")
        labels.update(f"minimum:{axis}" for axis in sorted(
            axis
            for axis in effective_gcsim_optimizer_artifact_minimums(
                run_input,
                target=target,
            )
        ))
        offpiece_shape = _offpiece_shape(build, target)
        if isinstance(target.package, GcsimFourPieceTargetPackage):
            capability = run_input.set_capability(
                target.package.set_ref.gcsim_set_key
            )
            if (
                capability is not None
                and capability.max_rarity == 4
                and offpiece_shape == "5p"
            ):
                # A four-star package is authorized only with one explicit
                # five-star off-piece.  Do not allow an exploratory profile
                # to surface a syntactically complete but evaluator-invalid
                # five-piece four-star build.
                continue
        crit_value = (
            state.stats[_AXIS_INDEX["cr"]] * 2
            + state.stats[_AXIS_INDEX["cd"]]
        )
        payload = {
            "schema_version": GCSIM_OPTIMIZER_ANYTIME_CANDIDATE_SCHEMA_VERSION,
            "target": target.to_dict(),
            "response_profile_sha256": profile.identity_sha256,
            "assignment": assignment.to_dict(),
            "wearer_build_identity_sha256": (
                build.wearer_build_identity_sha256
            ),
            "proposal_score": _float_text(base_score),
        }
        candidates.append(
            GcsimOptimizerLazyWearerCandidate(
                target=target,
                response_model_sha256=profile.identity_sha256,
                assignment=assignment,
                materialized_build=build,
                proposal_score=_float_text(base_score),
                crit_value=_float_text(crit_value),
                offpiece_shape=offpiece_shape,
                feature_labels=tuple(sorted(labels)),
                content_fingerprint=build.compiled_block_sha256,
                candidate_sha256=_canonical_sha256(payload),
            )
        )
    return tuple(candidates)


def _retain_hybrid_wearer_beam_states(
    rows: Sequence[_WearerBeamState],
    *,
    limit: int,
) -> list[_WearerBeamState]:
    """Mix the score head with bounded partial-layout/conflict witnesses."""

    ordered = sorted(
        rows,
        key=lambda item: (
            -item.score,
            tuple(row.artifact.artifact_id for row in item.chosen),
        ),
    )
    if len(ordered) <= limit:
        return ordered
    selected: list[_WearerBeamState] = []
    selected_assignments: set[tuple[int, ...]] = set()

    def assignment(row: _WearerBeamState) -> tuple[int, ...]:
        return tuple(item.artifact.artifact_id for item in row.chosen)

    def layout(row: _WearerBeamState) -> tuple[str, ...]:
        return tuple(
            item.artifact.main_key
            for item in row.chosen
            if item.artifact.slot in _VARIABLE_SLOTS
        )

    def conflict_shape(row: _WearerBeamState) -> tuple[int, ...]:
        return tuple(
            index
            for index, item in enumerate(row.chosen)
            if item.package_index < 0
        )

    def add(row: _WearerBeamState) -> bool:
        key = assignment(row)
        if key in selected_assignments:
            return False
        selected.append(row)
        selected_assignments.add(key)
        return True

    # Half of the beam remains an ordinary best-score beam.  This preserves
    # exploitation while leaving an explicit, bounded exploration budget.
    score_head = max(1, limit // 2)
    for row in ordered:
        add(row)
        if len(selected) >= score_head:
            break

    # Preserve the strongest prefix for every reachable variable-main layout.
    # This is the key guard against a useful elemental/utility main being
    # ranked behind hundreds of same-shape crit-heavy prefixes.
    seen_layouts: set[tuple[str, ...]] = set()
    for row in ordered:
        signature = layout(row)
        if signature in seen_layouts:
            continue
        seen_layouts.add(signature)
        add(row)
        if len(selected) >= limit:
            return selected

    # Then round-robin physical off-piece positions inside each layout.  A
    # locally dominated piece may be necessary only because another wearer
    # consumes the locally stronger one.
    groups: dict[
        tuple[tuple[str, ...], tuple[int, ...]],
        list[_WearerBeamState],
    ] = defaultdict(list)
    for row in ordered:
        groups[(layout(row), conflict_shape(row))].append(row)
    group_keys = sorted(
        groups,
        key=lambda key: (
            -groups[key][0].score,
            key,
        ),
    )
    depth = 0
    while len(selected) < limit:
        progressed = False
        for key in group_keys:
            group = groups[key]
            if depth >= len(group):
                continue
            progressed = True
            add(group[depth])
            if len(selected) >= limit:
                return selected
        if not progressed:
            break
        depth += 1
    for row in ordered:
        add(row)
        if len(selected) >= limit:
            break
    return selected


def _retain_hybrid_complete_states(
    rows: Sequence[tuple[_WearerBeamState, int]],
    *,
    limit: int,
) -> list[tuple[_WearerBeamState, int]]:
    """Retain normalized score leaders and profile/layout witnesses."""

    source = list(rows)
    if len(source) <= limit:
        return source
    by_profile: dict[int, list[tuple[_WearerBeamState, int]]] = defaultdict(
        list
    )
    for row in source:
        by_profile[row[1]].append(row)
    normalized_rows: list[
        tuple[
            float,
            float,
            tuple[int, ...],
            int,
            tuple[_WearerBeamState, int],
        ]
    ] = []
    for profile_index, profile_rows in by_profile.items():
        ordered_profile = sorted(
            profile_rows,
            key=lambda item: (
                -item[0].score,
                tuple(
                    piece.artifact.artifact_id
                    for piece in item[0].chosen
                ),
            ),
        )
        best_score = ordered_profile[0][0].score
        denominator = max(len(ordered_profile) - 1, 1)
        score_scale = max(abs(best_score), 1.0)
        for rank, row in enumerate(ordered_profile):
            ids = tuple(
                piece.artifact.artifact_id for piece in row[0].chosen
            )
            normalized_rows.append(
                (
                    rank / denominator,
                    max(best_score - row[0].score, 0.0) / score_scale,
                    ids,
                    profile_index,
                    row,
                )
            )
    normalized_rows.sort(key=lambda item: item[:4])
    selected: list[tuple[_WearerBeamState, int]] = []
    selected_assignments: set[tuple[int, ...]] = set()

    def add(row: tuple[_WearerBeamState, int]) -> bool:
        assignment = tuple(
            item.artifact.artifact_id for item in row[0].chosen
        )
        if assignment in selected_assignments:
            return False
        selected.append(row)
        selected_assignments.add(assignment)
        return True

    normalized_head = max(1, limit // 2)
    for _rank, _loss, _ids, _profile_index, row in normalized_rows:
        add(row)
        if len(selected) >= normalized_head:
            break

    # Every response view gets at least one witness even when its numeric
    # scale is much smaller than another view's raw scale.
    retained_profiles: set[int] = set()
    for _rank, _loss, _ids, profile_index, row in normalized_rows:
        if profile_index not in retained_profiles:
            retained_profiles.add(profile_index)
            add(row)
        if len(selected) >= limit:
            return selected

    retained_profile_layouts: set[
        tuple[int, tuple[str, ...], tuple[int, ...]]
    ] = set()
    for _rank, _loss, _ids, profile_index, row in normalized_rows:
        layout = tuple(
            item.artifact.main_key for item in row[0].chosen[2:]
        )
        conflict_shape = tuple(
            index
            for index, item in enumerate(row[0].chosen)
            if item.package_index < 0
        )
        signature = (profile_index, layout, conflict_shape)
        if signature in retained_profile_layouts:
            continue
        retained_profile_layouts.add(signature)
        add(row)
        if len(selected) >= limit:
            return selected

    for _rank, _loss, _ids, _profile_index, row in normalized_rows:
        add(row)
        if len(selected) >= limit:
            break
    return selected


def _retain_diverse_complete_states(
    rows: Sequence[tuple[_WearerBeamState, int]],
    *,
    limit: int,
) -> list[tuple[_WearerBeamState, int]]:
    """Compatibility name for the normalized hybrid retention policy."""

    return _retain_hybrid_complete_states(rows, limit=limit)


def _piece_score(
    artifact: GcsimOptimizerDenseArtifact,
    profile: GcsimOptimizerAnytimeStatProfile,
) -> float:
    substat_score = sum(
        value * weight
        for value, weight in zip(
            artifact.substats,
            profile.stat_weights,
            strict=True,
        )
    )
    main_score = profile.main_score_index.get(
        (artifact.slot, artifact.main_key),
        0.0,
    )
    return substat_score + main_score


def _pareto_and_shadow(
    rows: Sequence[_ScoredPiece],
    *,
    frontier_limit: int,
    shadow_limit: int,
) -> tuple[tuple[_ScoredPiece, ...], tuple[_ScoredPiece, ...]]:
    # profile_scores[0] is the balanced/base score.  Lexicographic descending
    # order guarantees that a later row cannot dominate an earlier row:
    # at the first differing profile it is necessarily smaller.  Therefore we
    # only compare each row with the current nondominated frontier instead of
    # performing the former quadratic all-pairs scan.
    ordered = tuple(
        sorted(
            rows,
            key=lambda item: (
                tuple(-score for score in item.profile_scores),
                item.artifact.artifact_id,
            ),
        )
    )
    frontier: list[_ScoredPiece] = []
    dominated: list[_ScoredPiece] = []
    for row in ordered:
        is_dominated = any(
            _piece_dominates(other, row)
            for other in frontier
        )
        (dominated if is_dominated else frontier).append(row)
    frontier = _retain_piece_profile_diversity(
        frontier,
        limit=frontier_limit,
    )
    shadow = _retain_piece_profile_diversity(
        dominated,
        limit=shadow_limit,
    )
    return tuple(frontier), tuple(shadow)


def _piece_dominates(
    left: _ScoredPiece,
    right: _ScoredPiece,
) -> bool:
    no_worse = all(
        left_score + 1e-12 >= right_score
        for left_score, right_score in zip(
            left.profile_scores,
            right.profile_scores,
            strict=True,
        )
    )
    if not no_worse:
        return False
    return (
        any(
            left_score > right_score + 1e-12
            for left_score, right_score in zip(
                left.profile_scores,
                right.profile_scores,
                strict=True,
            )
        )
        or left.artifact.artifact_id < right.artifact.artifact_id
    )


def _retain_piece_profile_diversity(
    rows: Sequence[_ScoredPiece],
    *,
    limit: int,
) -> list[_ScoredPiece]:
    if len(rows) <= limit:
        return list(
            sorted(
                rows,
                key=lambda item: (
                    -item.base_score,
                    item.artifact.artifact_id,
                ),
            )
        )
    selected: list[_ScoredPiece] = []
    selected_ids: set[int] = set()
    profile_count = len(rows[0].profile_scores) if rows else 0
    for profile_index in range(profile_count):
        row = min(
            rows,
            key=lambda item: (
                -item.profile_scores[profile_index],
                item.artifact.artifact_id,
            ),
        )
        if row.artifact.artifact_id not in selected_ids:
            selected.append(row)
            selected_ids.add(row.artifact.artifact_id)
        if len(selected) >= limit:
            return selected
    for row in sorted(
        rows,
        key=lambda item: (
            -item.base_score,
            item.artifact.artifact_id,
        ),
    ):
        if row.artifact.artifact_id not in selected_ids:
            selected.append(row)
            selected_ids.add(row.artifact.artifact_id)
        if len(selected) >= limit:
            break
    return selected


def _retain_slot_profile_diversity(
    rows: Sequence[_ScoredPiece],
    *,
    profile_count: int,
    per_profile: int,
    limit: int,
) -> list[_ScoredPiece]:
    selected: list[_ScoredPiece] = []
    selected_ids: set[int] = set()
    # Preserve one strong representative of every package/main/rarity
    # category before score-based truncation.  In particular, ER has zero
    # response weight by policy but ER sands must remain reachable when a
    # request defines a hard minimum.
    categories: dict[tuple[int, str, int | None], list[_ScoredPiece]] = (
        defaultdict(list)
    )
    for row in rows:
        categories[
            (
                row.package_index,
                row.artifact.main_key,
                row.artifact.record.rarity,
            )
        ].append(row)
    for key in sorted(categories, key=repr):
        row = min(
            categories[key],
            key=lambda item: (
                -item.base_score,
                item.artifact.artifact_id,
            ),
        )
        selected.append(row)
        selected_ids.add(row.artifact.artifact_id)
        if len(selected) >= limit:
            return selected
    # Keep a bounded cross-profile reservoir of dominated off-pieces before
    # the ordinary per-profile head.  These are conflict-repair candidates,
    # not claims that their local surrogate is stronger.
    offpiece_shadows = tuple(
        row for row in rows if row.package_index < 0 and row.shadow
    )
    for row in _retain_piece_profile_diversity(
        offpiece_shadows,
        limit=min(per_profile, len(offpiece_shadows)),
    ):
        if row.artifact.artifact_id not in selected_ids:
            selected.append(row)
            selected_ids.add(row.artifact.artifact_id)
        if len(selected) >= limit:
            return selected
    for profile_index in range(profile_count):
        ranked = sorted(
            rows,
            key=lambda item: (
                -item.profile_scores[profile_index],
                item.artifact.artifact_id,
            ),
        )
        for row in ranked[:per_profile]:
            if row.artifact.artifact_id not in selected_ids:
                selected.append(row)
                selected_ids.add(row.artifact.artifact_id)
            if len(selected) >= limit:
                return selected
    for row in sorted(
        rows,
        key=lambda item: (
            -item.base_score,
            item.artifact.artifact_id,
        ),
    ):
        if row.artifact.artifact_id not in selected_ids:
            selected.append(row)
            selected_ids.add(row.artifact.artifact_id)
        if len(selected) >= limit:
            break
    return selected


def _remaining_stat_maxima(
    by_slot: Mapping[str, tuple[_ScoredPiece, ...]],
) -> tuple[tuple[float, ...], ...]:
    result: list[tuple[float, ...]] = [
        (0.0,) * len(GCSIM_OPTIMIZER_ANYTIME_STAT_AXES)
        for _ in range(len(GCSIM_OPTIMIZER_ARTIFACT_SLOTS) + 1)
    ]
    running = [0.0] * len(GCSIM_OPTIMIZER_ANYTIME_STAT_AXES)
    for slot_index in range(
        len(GCSIM_OPTIMIZER_ARTIFACT_SLOTS) - 1,
        -1,
        -1,
    ):
        slot = GCSIM_OPTIMIZER_ARTIFACT_SLOTS[slot_index]
        for axis_index in range(len(running)):
            running[axis_index] += max(
                (
                    row.artifact.stats[axis_index]
                    for row in by_slot[slot]
                ),
                default=0.0,
            )
        result[slot_index] = tuple(running)
    return tuple(result)


def _retain_diverse_candidates(
    rows: Sequence[GcsimOptimizerLazyWearerCandidate],
    *,
    limit: int,
) -> list[GcsimOptimizerLazyWearerCandidate]:
    ordered = sorted(rows, key=_candidate_rank)
    if len(ordered) <= limit:
        return ordered
    selected: list[GcsimOptimizerLazyWearerCandidate] = []
    target_ids = {
        _target_identity(row.target) for row in ordered
    }
    if len(target_ids) > limit:
        raise GcsimOptimizerAnytimeCandidateError(
            "wearer candidate cap cannot preserve one representative per "
            "retained package"
        )
    selected_ids: set[str] = set()
    retained_targets: set[str] = set()
    for row in ordered:
        target_id = _target_identity(row.target)
        if target_id in retained_targets:
            continue
        retained_targets.add(target_id)
        selected.append(row)
        selected_ids.add(row.candidate_sha256)
        if len(selected) >= limit:
            return selected
    signatures: set[tuple[str, str]] = set()
    for row in ordered:
        profile = next(
            (
                label for label in row.feature_labels
                if label.startswith("profile:")
            ),
            "",
        )
        signature = (_target_identity(row.target), profile)
        if signature not in signatures:
            signatures.add(signature)
            if row.candidate_sha256 not in selected_ids:
                selected.append(row)
                selected_ids.add(row.candidate_sha256)
        if len(selected) >= limit:
            return selected
    for row in ordered:
        if row.candidate_sha256 not in selected_ids:
            selected.append(row)
            selected_ids.add(row.candidate_sha256)
        if len(selected) >= limit:
            break
    return selected


def _retain_diverse_joint_states(
    rows: Sequence[_JointState],
    *,
    limit: int,
) -> list[_JointState]:
    deduplicated: dict[tuple[str, ...], _JointState] = {}
    for row in rows:
        key = tuple(
            item.candidate_sha256 for item in row.candidates
        )
        current = deduplicated.get(key)
        if current is None or row.score > current.score:
            deduplicated[key] = row
    ordered = sorted(
        deduplicated.values(),
        key=lambda item: (
            -item.score,
            tuple(
                row.candidate_sha256 for row in item.candidates
            ),
        ),
    )
    if len(ordered) <= limit:
        return ordered
    selected: list[_JointState] = []
    signatures: set[tuple[str, ...]] = set()
    for row in ordered:
        signature = tuple(
            (
                _target_identity(item.target)
                + ":"
                + next(
                    (
                        label.removeprefix("profile:")
                        for label in item.feature_labels
                        if label.startswith("profile:")
                    ),
                    "",
                )
            )
            for item in row.candidates
        )
        if signature not in signatures:
            signatures.add(signature)
            selected.append(row)
        if len(selected) >= limit:
            return selected
    for row in ordered:
        if row not in selected:
            selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def _package_requirements(
    target: GcsimOptimizerWearerTarget,
) -> tuple[tuple[str, ...], tuple[int, ...]]:
    package = target.package
    if isinstance(package, GcsimFourPieceTargetPackage):
        return (package.set_ref.set_uid,), (4,)
    if isinstance(package, GcsimTwoPlusTwoTargetPackage):
        return (
            package.set_a.set_uid,
            package.set_b.set_uid,
        ), (2, 2)
    raise GcsimOptimizerAnytimeCandidateError(
        "unsupported target package"
    )


def _offpiece_shape(build, target: GcsimOptimizerWearerTarget) -> str:
    package = target.package
    if isinstance(package, GcsimTwoPlusTwoTargetPackage):
        return "2p2p"
    target_uid = package.set_ref.set_uid
    offpieces = tuple(
        slot
        for slot, artifact in build.artifacts_by_slot
        if artifact.set_uid != target_uid
    )
    return "5p" if not offpieces else offpieces[0]


def _target_identity(target: GcsimOptimizerWearerTarget) -> str:
    return _canonical_sha256(target.to_dict())


def _account_target_key(
    target: GcsimOptimizerWearerTarget,
) -> tuple[int, str]:
    return target.wearer.team_slot, target.package.identity_sha256


def _validated_target_keys(
    values: Sequence[tuple[int, str]],
    field_name: str,
) -> tuple[tuple[int, str], ...]:
    rows = tuple(values)
    normalized: list[tuple[int, str]] = []
    for row in rows:
        if (
            not isinstance(row, tuple)
            or len(row) != 2
            or isinstance(row[0], bool)
            or not isinstance(row[0], int)
            or row[0] not in {1, 2, 3, 4}
            or not isinstance(row[1], str)
        ):
            raise GcsimOptimizerAnytimeCandidateError(
                f"{field_name} must contain (team_slot, package_sha256) rows"
            )
        _require_sha256(row[1], f"{field_name}.package_sha256")
        normalized.append((row[0], row[1]))
    if len(set(normalized)) != len(normalized):
        raise GcsimOptimizerAnytimeCandidateError(
            f"{field_name} must contain unique target keys"
        )
    return tuple(sorted(normalized))


def _candidate_rank(
    candidate: GcsimOptimizerLazyWearerCandidate,
) -> tuple[float, tuple[int, ...], str]:
    return (
        -float(candidate.proposal_score),
        candidate.assignment.artifact_ids,
        candidate.candidate_sha256,
    )


def _float_text(value: float) -> str:
    if not isfinite(value):
        raise GcsimOptimizerAnytimeCandidateError(
            "candidate score must be finite"
        )
    decimal = Decimal(str(value))
    if decimal == 0:
        return "0"
    text = format(decimal.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_schema(value: int) -> None:
    if value != GCSIM_OPTIMIZER_ANYTIME_CANDIDATE_SCHEMA_VERSION:
        raise GcsimOptimizerAnytimeCandidateError(
            "unsupported anytime candidate schema"
        )


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise GcsimOptimizerAnytimeCandidateError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


__all__ = [
    "GCSIM_OPTIMIZER_ANYTIME_CANDIDATE_SCHEMA_VERSION",
    "GCSIM_OPTIMIZER_RESPONSE_CLASSIFICATIONS",
    "GCSIM_OPTIMIZER_ANYTIME_STAT_AXES",
    "GcsimOptimizerAnytimeCandidateCoverage",
    "GcsimOptimizerAnytimeCandidateError",
    "GcsimOptimizerAnytimeCandidatePlan",
    "GcsimOptimizerAnytimeJointCoverage",
    "GcsimOptimizerAnytimeStatProfile",
    "GcsimOptimizerAnytimeWearerPool",
    "GcsimOptimizerDenseArtifact",
    "GcsimOptimizerDenseArtifactCatalog",
    "build_gcsim_optimizer_anytime_joint_proposals",
    "build_gcsim_optimizer_coordinate_refinement_proposals",
    "build_gcsim_optimizer_soft_main_coverage_profiles",
    "build_gcsim_optimizer_stat_coverage_profiles",
    "build_gcsim_optimizer_uncertainty_refinement_profiles",
    "build_gcsim_optimizer_dense_artifact_catalog",
    "generate_gcsim_optimizer_anytime_wearer_pool",
]
