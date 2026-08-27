"""Bounded inventory-independent candidates for theoretical ``anytime_approx_v2``.

This module owns no simulation and reads no artifact database.  It turns one
small rotation-response profile family into deterministic five-star theoretical
states:

* modeled 4p package keys come from the trusted engine catalog;
* optional 2p+2p keys come from canonical engine-bound package descriptors;
* every wearer keeps response-measured stat/main alternatives only for
  package effects retained by paired set-impact evidence;
* package anchors, wearer alternatives, and full-team proposals are all capped.

The resulting :class:`FullTeamProbeState` values are cheap-screening proposals,
not claims about global optimality.  A later service package-screens them at 8,
refines main layouts inside fixed package signatures at 8, then runs the frozen
32 -> 200 -> 1000 validation policy.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
from itertools import product
import json
from math import isfinite
import re
from types import MappingProxyType

from .farming_profile_config import GCSIM_AUTOMATIC_RESPONSE_STAT_AXES
from .farming_search import (
    FourPieceSetState,
    SetProfileCandidate,
    StatProfile,
    StatProfileBank,
    StatWeight,
)
from .farming_team_search import FullTeamPhysicalState, FullTeamProbeState
from .optimizer_anytime_candidates import (
    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
    GcsimOptimizerAnytimeStatProfile,
)
from .optimizer_config import (
    LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS,
    LEGAL_FIVE_STAR_GOBLET_MAIN_STATS,
    LEGAL_FIVE_STAR_SANDS_MAIN_STATS,
    GcsimFiveStarMainStatLayout,
)
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_main_response import gcsim_optimizer_main_layout_id
from .optimizer_product_contracts import (
    GcsimFourPieceTargetPackage,
    GcsimOptimizerTargetPackageKind,
    GcsimOptimizerWearerIdentity,
    GcsimTwoPlusTwoTargetPackage,
)
from .optimizer_set_impact import (
    GcsimOptimizerSetImpactResult,
    GcsimOptimizerSetImpactRow,
    GcsimOptimizerSingleTwoPieceImpactTarget,
)
from .optimizer_stat_response import GCSIM_STAT_RESPONSE_ROLL_VALUES
from .optimizer_theoretical_packages import (
    freeze_gcsim_theoretical_pair_packages,
    gcsim_theoretical_pair_package_key,
)


GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_CANDIDATE_SCHEMA_VERSION = 4
GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_CANDIDATE_PLAN_ID = (
    "theoretical_anytime_candidates"
)
GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_CANDIDATE_PLAN_VERSION = 8

THEORETICAL_ANYTIME_REQUIRED_PROFILE_IDS = (
    "balanced",
)

_MIN_LAYOUTS = 3
_MIN_JOINT_PROPOSALS = 1
_MAX_QUICK_FOUR_PIECE_ANCHORS_PER_WEARER = 63
_MAX_QUICK_TWO_PLUS_TWO_ANCHORS_PER_WEARER = 30
_ER_AXIS_INDEX = GCSIM_OPTIMIZER_ANYTIME_STAT_AXES.index("er")
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PROFILE_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_SCALING_MAIN_AXES = frozenset(("hp%", "atk%", "def%"))
_ELEMENTAL_DAMAGE_MAIN_AXES = frozenset(
    (
        "pyro%",
        "hydro%",
        "electro%",
        "cryo%",
        "anemo%",
        "geo%",
        "dendro%",
        "phys%",
    )
)
_CRIT_MAIN_AXES = frozenset(("cr", "cd"))
_USEFUL_RESPONSE_CLASSIFICATIONS = frozenset(("dominant", "secondary"))

class GcsimOptimizerTheoreticalAnytimeCandidateError(ValueError):
    """Fail-closed theoretical candidate-domain error."""


def gcsim_optimizer_theoretical_team_package_signature(
    state: FullTeamProbeState | FullTeamPhysicalState,
) -> tuple[str, ...]:
    """Ordered four-wearer package identity used for theoretical Top-N."""

    if not isinstance(state, (FullTeamProbeState, FullTeamPhysicalState)):
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "team package signature requires a typed team state"
        )
    choices = state.choices
    if len(choices) != 4:
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "team package signature requires four wearers"
        )
    return tuple(
        (
            choice.state.set_key
            if isinstance(state, FullTeamProbeState)
            else choice.set_key
        )
        for choice in choices
    )


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalAnytimeCandidatePlan:
    """Versioned caps for one theoretical candidate domain."""

    max_layouts_per_wearer: int = 10
    max_profiles_per_wearer: int = 7
    max_package_anchors_per_wearer: int = 128
    max_quick_four_piece_anchors_per_wearer: int = (
        _MAX_QUICK_FOUR_PIECE_ANCHORS_PER_WEARER
    )
    max_quick_two_plus_two_anchors_per_wearer: int = (
        _MAX_QUICK_TWO_PLUS_TWO_ANCHORS_PER_WEARER
    )
    max_wearer_alternatives: int = 192
    max_joint_package_anchor_proposals: int = 508
    max_joint_proposals: int = 512
    max_package_coordinate_neighbors_per_wearer: int = 6
    max_package_combination_neighbors: int = 8
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_CANDIDATE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in (
            "max_layouts_per_wearer",
            "max_profiles_per_wearer",
            "max_package_anchors_per_wearer",
            "max_quick_four_piece_anchors_per_wearer",
            "max_quick_two_plus_two_anchors_per_wearer",
            "max_wearer_alternatives",
            "max_joint_package_anchor_proposals",
            "max_joint_proposals",
            "max_package_coordinate_neighbors_per_wearer",
            "max_package_combination_neighbors",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                    f"{field_name} must be a positive integer"
                )
        if self.max_layouts_per_wearer < _MIN_LAYOUTS:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                f"max_layouts_per_wearer must be at least {_MIN_LAYOUTS}"
            )
        if self.max_profiles_per_wearer < len(
            THEORETICAL_ANYTIME_REQUIRED_PROFILE_IDS
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "profile cap cannot remove a required response safeguard"
            )
        if self.max_quick_four_piece_anchors_per_wearer > (
            _MAX_QUICK_FOUR_PIECE_ANCHORS_PER_WEARER
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "4p quick-anchor cap exceeds screen-64 coverage"
            )
        if self.max_quick_two_plus_two_anchors_per_wearer > (
            _MAX_QUICK_TWO_PLUS_TWO_ANCHORS_PER_WEARER
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "2p+2p quick-anchor cap must reserve screen-64 capacity "
                "for at least one fair full-layout witness rank"
            )
        quick_anchor_capacity = min(
            self.max_package_anchors_per_wearer,
            max(
                self.max_quick_four_piece_anchors_per_wearer,
                self.max_quick_two_plus_two_anchors_per_wearer,
            ),
        )
        required_quick_witness_capacity = (
            quick_anchor_capacity * _MIN_LAYOUTS
        )
        if self.max_wearer_alternatives < required_quick_witness_capacity:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "wearer-alternative cap cannot remove required quick "
                "package/layout witnesses"
            )
        if self.max_joint_proposals < _MIN_JOINT_PROPOSALS:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "joint-proposal cap cannot remove the baseline proposal"
            )
        reserved_package_neighbors = (
            1
            + 4 * self.max_package_coordinate_neighbors_per_wearer
            + self.max_package_combination_neighbors
        )
        if reserved_package_neighbors > 64:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "package-coordinate neighbors exceed the frozen screen-64 tier"
            )
        if (
            self.max_joint_package_anchor_proposals
            > self.max_joint_proposals - _MIN_JOINT_PROPOSALS
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "joint package-anchor cap leaves no room for the baseline"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": (
                GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_CANDIDATE_PLAN_ID
            ),
            "plan_version": (
                GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_CANDIDATE_PLAN_VERSION
            ),
            "max_layouts_per_wearer": self.max_layouts_per_wearer,
            "max_profiles_per_wearer": self.max_profiles_per_wearer,
            "max_package_anchors_per_wearer": (
                self.max_package_anchors_per_wearer
            ),
            "max_quick_four_piece_anchors_per_wearer": (
                self.max_quick_four_piece_anchors_per_wearer
            ),
            "max_quick_two_plus_two_anchors_per_wearer": (
                self.max_quick_two_plus_two_anchors_per_wearer
            ),
            "max_wearer_alternatives": self.max_wearer_alternatives,
            "max_joint_package_anchor_proposals": (
                self.max_joint_package_anchor_proposals
            ),
            "max_joint_proposals": self.max_joint_proposals,
            "max_package_coordinate_neighbors_per_wearer": (
                self.max_package_coordinate_neighbors_per_wearer
            ),
            "max_package_combination_neighbors": (
                self.max_package_combination_neighbors
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalAnytimeWearerAlternative:
    """One package/main/profile alternative for one theoretical wearer."""

    wearer: GcsimOptimizerWearerIdentity
    candidate: SetProfileCandidate
    layout: GcsimFiveStarMainStatLayout
    score: float
    diversity_tags: tuple[str, ...] = ()
    package_anchor: bool = False
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_CANDIDATE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "alternative wearer must be typed"
            )
        if not isinstance(self.candidate, SetProfileCandidate):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "alternative candidate must be typed"
            )
        if not isinstance(self.layout, GcsimFiveStarMainStatLayout):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "alternative layout must be typed"
            )
        _validate_layout(self.layout)
        state = self.candidate.state
        if state.wearer_id != self.wearer.gcsim_character_key:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "alternative candidate belongs to another wearer"
            )
        if state.offpiece_slot:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "five-star theoretical candidates cannot carry an offpiece"
            )
        if state.main_stat_layout_id != gcsim_optimizer_main_layout_id(
            self.layout
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "alternative layout ID differs from its typed layout"
            )
        _reject_er_profile_id(self.candidate.profile_id)
        if (
            isinstance(self.score, bool)
            or not isinstance(self.score, (int, float))
            or not isfinite(self.score)
            or self.score < 0
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "alternative score must be finite and non-negative"
            )
        tags = _canonical_tags(self.diversity_tags)
        object.__setattr__(self, "diversity_tags", tags)
        if not isinstance(self.package_anchor, bool):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "package_anchor must be a boolean"
            )

    @property
    def package_key(self) -> str:
        return self.candidate.state.set_key

    @property
    def layout_id(self) -> str:
        return self.candidate.state.main_stat_layout_id

    @property
    def profile_id(self) -> str:
        return self.candidate.profile_id

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "wearer": self.wearer.to_dict(),
            "candidate_key": list(self.candidate.key),
            "layout": self.layout.to_dict(),
            "score": float(self.score),
            "diversity_tags": list(self.diversity_tags),
            "package_anchor": self.package_anchor,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalAnytimeWearerPool:
    """Bounded alternatives and materialization metadata for one wearer."""

    wearer: GcsimOptimizerWearerIdentity
    layouts: tuple[tuple[str, GcsimFiveStarMainStatLayout], ...]
    profile_ids: tuple[str, ...]
    retained_package_keys: tuple[str, ...]
    alternatives: tuple[
        GcsimOptimizerTheoreticalAnytimeWearerAlternative, ...
    ]
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_CANDIDATE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "wearer pool identity must be typed"
            )
        layouts = tuple(self.layouts)
        profiles = tuple(self.profile_ids)
        retained_package_keys = tuple(self.retained_package_keys)
        alternatives = tuple(self.alternatives)
        object.__setattr__(self, "layouts", layouts)
        object.__setattr__(self, "profile_ids", profiles)
        object.__setattr__(
            self,
            "retained_package_keys",
            retained_package_keys,
        )
        object.__setattr__(self, "alternatives", alternatives)
        if not layouts or len({item[0] for item in layouts}) != len(layouts):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "wearer layouts must be non-empty and uniquely identified"
            )
        for layout_id, layout in layouts:
            if (
                not isinstance(layout, GcsimFiveStarMainStatLayout)
                or layout_id != gcsim_optimizer_main_layout_id(layout)
            ):
                raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                    "wearer layout catalog is inconsistent"
                )
            _validate_layout(layout)
        if len(set(profiles)) != len(profiles):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "wearer profile IDs must be unique"
            )
        required_profiles = tuple(
            _materialized_profile_id(self.wearer, profile_id)
            for profile_id in THEORETICAL_ANYTIME_REQUIRED_PROFILE_IDS
        )
        if any(profile not in profiles for profile in required_profiles):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "wearer pool lacks a required response profile"
            )
        for profile in profiles:
            _reject_er_profile_id(profile)
        if (
            len(set(retained_package_keys)) != len(retained_package_keys)
            or any(
                not isinstance(package_key, str)
                for package_key in retained_package_keys
            )
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "retained package keys must be unique strings"
            )
        for package_key in retained_package_keys:
            _require_identifier(package_key, "retained package key")
        if not alternatives or any(
            not isinstance(
                item,
                GcsimOptimizerTheoreticalAnytimeWearerAlternative,
            )
            or item.wearer != self.wearer
            or item.layout_id not in dict(layouts)
            or item.profile_id not in profiles
            for item in alternatives
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "wearer alternatives differ from their pool metadata"
            )
        if len(
            {item.candidate.key for item in alternatives}
        ) != len(alternatives):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "wearer alternatives must be unique"
            )
        anchor_keys = set(self.anchor_package_keys)
        if retained_package_keys:
            if not anchor_keys.issubset(retained_package_keys):
                raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                    "screened anchors lie outside retained packages"
                )
        elif len(anchor_keys) != 1:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "a no-impact fallback pool requires exactly one anchor"
            )
        if any(
            item.package_key not in anchor_keys
            for item in alternatives
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "wearer alternatives lie outside screened anchors"
            )

    @property
    def anchor_package_keys(self) -> tuple[str, ...]:
        return tuple(
            item.package_key for item in self.alternatives
            if item.package_anchor
        )

    @property
    def unscreened_retained_package_keys(self) -> tuple[str, ...]:
        screened = set(self.anchor_package_keys)
        return tuple(
            package_key
            for package_key in self.retained_package_keys
            if package_key not in screened
        )

    @property
    def alternative_by_key(self) -> Mapping[
        tuple[str, str, str, str, str],
        GcsimOptimizerTheoreticalAnytimeWearerAlternative,
    ]:
        return MappingProxyType(
            {item.candidate.key: item for item in self.alternatives}
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "wearer": self.wearer.to_dict(),
            "layouts": [
                {"layout_id": layout_id, "layout": layout.to_dict()}
                for layout_id, layout in self.layouts
            ],
            "profile_ids": list(self.profile_ids),
            "retained_package_keys": list(self.retained_package_keys),
            "unscreened_retained_package_keys": list(
                self.unscreened_retained_package_keys
            ),
            "alternatives": [item.to_dict() for item in self.alternatives],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalAnytimeProposal:
    """One bounded full-team cheap-screen proposal."""

    state: FullTeamProbeState
    score: float
    diversity_tags: tuple[str, ...]
    package_anchor_count: int
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_CANDIDATE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.state, FullTeamProbeState):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "proposal state must be typed"
            )
        if len(self.state.choices) != 4:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "theoretical proposals require four wearers"
            )
        if (
            isinstance(self.score, bool)
            or not isinstance(self.score, (int, float))
            or not isfinite(self.score)
            or self.score < 0
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "proposal score must be finite and non-negative"
            )
        tags = _canonical_tags(self.diversity_tags)
        object.__setattr__(self, "diversity_tags", tags)
        if (
            isinstance(self.package_anchor_count, bool)
            or not isinstance(self.package_anchor_count, int)
            or not 0 <= self.package_anchor_count <= 4
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "proposal package_anchor_count must be in 0..4"
            )
        for choice in self.state.choices:
            _reject_er_profile_id(choice.profile_id)

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    @property
    def proposal_sha256(self) -> str:
        """Stable proposal identity used by the staged simulator."""

        return self.identity_sha256

    @property
    def surrogate_score(self) -> float:
        """Cheap deterministic ordering score; never a simulated DPS claim."""

        return float(self.score)

    @property
    def diversity_labels(self) -> tuple[str, ...]:
        return self.diversity_tags

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "probe_key": [list(item) for item in self.state.probe_key],
            "surrogate_score": self.surrogate_score,
            "diversity_labels": list(self.diversity_labels),
            "package_anchor_count": self.package_anchor_count,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalAnytimeCandidateDomain:
    """Complete typed output of the bounded theoretical candidate builder."""

    package_kind: GcsimOptimizerTargetPackageKind
    package_keys: tuple[str, ...]
    engine_binding_sha256: str
    catalog_fingerprint: str
    response_profiles_sha256: str
    set_impact_sha256: str
    plan: GcsimOptimizerTheoreticalAnytimeCandidatePlan
    wearer_pools: tuple[
        GcsimOptimizerTheoreticalAnytimeWearerPool, ...
    ]
    profile_bank: StatProfileBank
    proposals: tuple[GcsimOptimizerTheoreticalAnytimeProposal, ...]
    schema_version: int = (
        GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_CANDIDATE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(
            self.package_kind,
            GcsimOptimizerTargetPackageKind,
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "package_kind must be typed"
            )
        _require_sha256(
            self.engine_binding_sha256,
            "engine_binding_sha256",
        )
        _require_sha256(
            self.catalog_fingerprint,
            "catalog_fingerprint",
        )
        _require_sha256(
            self.response_profiles_sha256,
            "response_profiles_sha256",
        )
        _require_sha256(
            self.set_impact_sha256,
            "set_impact_sha256",
        )
        package_keys = tuple(self.package_keys)
        pools = tuple(self.wearer_pools)
        proposals = tuple(self.proposals)
        object.__setattr__(self, "package_keys", package_keys)
        object.__setattr__(self, "wearer_pools", pools)
        object.__setattr__(self, "proposals", proposals)
        if (
            not package_keys
            or package_keys != tuple(sorted(package_keys))
            or len(set(package_keys)) != len(package_keys)
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "package keys must be non-empty, unique, and canonical"
            )
        if not isinstance(
            self.plan,
            GcsimOptimizerTheoreticalAnytimeCandidatePlan,
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "candidate plan must be typed"
            )
        if not isinstance(self.profile_bank, StatProfileBank):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "candidate profile_bank must be a StatProfileBank"
            )
        if tuple(self.profile_bank.axes) != tuple(
            GCSIM_AUTOMATIC_RESPONSE_STAT_AXES
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "candidate profile bank differs from the pinned automatic "
                "response axes"
            )
        if (
            len(pools) != 4
            or tuple(item.wearer.team_slot for item in pools) != (1, 2, 3, 4)
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "wearer pools must cover canonical team slots 1..4"
            )
        quick_anchor_cap = (
            self.plan.max_quick_four_piece_anchors_per_wearer
            if self.package_kind
            is GcsimOptimizerTargetPackageKind.FOUR_PIECE
            else self.plan.max_quick_two_plus_two_anchors_per_wearer
        )
        if any(
            len(item.layouts) > self.plan.max_layouts_per_wearer
            or len(item.profile_ids) > self.plan.max_profiles_per_wearer
            or len(item.retained_package_keys)
            > self.plan.max_package_anchors_per_wearer
            or len(item.anchor_package_keys)
            > quick_anchor_cap
            or len(item.alternatives) > self.plan.max_wearer_alternatives
            or any(
                package_key not in package_keys
                for package_key in item.retained_package_keys
            )
            or any(
                alternative.package_key not in package_keys
                for alternative in item.alternatives
            )
            for item in pools
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "wearer pool exceeds its frozen cap or package domain"
            )
        expected_profile_ids = {
            profile_id
            for pool in pools
            for profile_id in pool.profile_ids
        }
        actual_profile_ids = {
            profile.profile_id for profile in self.profile_bank.profiles
        }
        if (
            expected_profile_ids != actual_profile_ids
            or len(actual_profile_ids) != len(self.profile_bank.profiles)
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "candidate profile bank does not exactly cover wearer pools"
            )
        if (
            not proposals
            or len(proposals) > self.plan.max_joint_proposals
            or len({item.state.probe_key for item in proposals})
            != len(proposals)
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "joint proposals must be non-empty, unique, and bounded"
            )
        alternative_keys = {
            item.wearer.gcsim_character_key: set(item.alternative_by_key)
            for item in pools
        }
        for proposal in proposals:
            if tuple(
                choice.state.wearer_id for choice in proposal.state.choices
            ) != tuple(
                item.wearer.gcsim_character_key for item in pools
            ):
                raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                    "proposal wearer order differs from the frozen pools"
                )
            if any(
                choice.key not in alternative_keys[choice.state.wearer_id]
                for choice in proposal.state.choices
            ):
                raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                    "proposal references an alternative outside its wearer pool"
                )
        for pool_index, pool in enumerate(pools):
            covered_candidate_keys = {
                proposal.state.choices[pool_index].key
                for proposal in proposals
            }
            required_anchor_keys = {
                alternative.candidate.key
                for alternative in pool.alternatives
                if alternative.package_anchor
            }
            if not required_anchor_keys.issubset(covered_candidate_keys):
                raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                    "joint proposals lack balanced-anchor coverage for a "
                    "retained wearer/package"
                )
        if sum(
            "package_anchor_probe" in item.diversity_tags
            for item in proposals
        ) > self.plan.max_joint_package_anchor_proposals:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "joint package-anchor proposals exceed their cap"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    @property
    def layout_catalog(self) -> Mapping[
        str,
        Mapping[str, GcsimFiveStarMainStatLayout],
    ]:
        return MappingProxyType(
            {
                pool.wearer.gcsim_character_key: MappingProxyType(
                    dict(pool.layouts)
                )
                for pool in self.wearer_pools
            }
        )

    @property
    def probe_states(self) -> tuple[FullTeamProbeState, ...]:
        return tuple(item.state for item in self.proposals)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "package_kind": self.package_kind.value,
            "package_keys": list(self.package_keys),
            "engine_binding_sha256": self.engine_binding_sha256,
            "catalog_fingerprint": self.catalog_fingerprint,
            "response_profiles_sha256": self.response_profiles_sha256,
            "set_impact_sha256": self.set_impact_sha256,
            "plan": self.plan.to_dict(),
            "wearer_pools": [item.to_dict() for item in self.wearer_pools],
            "profile_bank": _profile_bank_payload(self.profile_bank),
            "proposals": [item.to_dict() for item in self.proposals],
        }


def derive_gcsim_optimizer_theoretical_package_keys(
    engine_context: GcsimOptimizerEngineContext,
    *,
    two_plus_two_packages: Mapping[
        str,
        GcsimTwoPlusTwoTargetPackage,
    ] | None = None,
) -> tuple[GcsimOptimizerTargetPackageKind, tuple[str, ...]]:
    """Return canonical 5-star 4p keys or validated 2p+2p representative keys."""

    _require_engine_context(engine_context)
    if two_plus_two_packages is None:
        package_keys = tuple(
            sorted(
                capability.key
                for capability in engine_context.catalog.sets
                if capability.max_rarity == 5
                and capability.optimizer_four_piece_ready
            )
        )
        kind = GcsimOptimizerTargetPackageKind.FOUR_PIECE
    else:
        try:
            frozen_pairs = freeze_gcsim_theoretical_pair_packages(
                two_plus_two_packages
            )
        except ValueError as exc:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                str(exc)
            ) from exc
        for package in frozen_pairs.values():
            for set_ref in (package.set_a, package.set_b):
                if (
                    set_ref.engine_binding_sha256
                    != engine_context.binding_sha256
                    or set_ref.catalog_fingerprint
                    != engine_context.catalog.source_fingerprint
                ):
                    raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                        "2p+2p representative differs from the frozen "
                        "engine/catalog binding"
                    )
                capability = engine_context.catalog.get(
                    set_ref.gcsim_set_key
                )
                if (
                    capability is None
                    or capability.max_rarity != 5
                    or not capability.two_piece_modeled
                ):
                    raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                        "2p+2p representative references an ineligible set"
                    )
        package_keys = tuple(sorted(frozen_pairs))
        kind = GcsimOptimizerTargetPackageKind.TWO_PLUS_TWO
    if not package_keys:
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "theoretical package domain is empty"
        )
    for package_key in package_keys:
        _require_identifier(package_key, "package key")
    return kind, package_keys


def build_gcsim_optimizer_theoretical_anytime_candidate_domain(
    *,
    engine_context: GcsimOptimizerEngineContext,
    wearers: Sequence[GcsimOptimizerWearerIdentity],
    response_profiles: Sequence[GcsimOptimizerAnytimeStatProfile],
    set_impact: GcsimOptimizerSetImpactResult,
    two_plus_two_packages: Mapping[
        str,
        GcsimTwoPlusTwoTargetPackage,
    ] | None = None,
    plan: GcsimOptimizerTheoreticalAnytimeCandidatePlan | None = None,
) -> GcsimOptimizerTheoreticalAnytimeCandidateDomain:
    """Build one deterministic bounded theoretical cheap-screen domain."""

    selected_plan = (
        plan or GcsimOptimizerTheoreticalAnytimeCandidatePlan()
    )
    if not isinstance(
        selected_plan,
        GcsimOptimizerTheoreticalAnytimeCandidatePlan,
    ):
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "plan must be typed"
        )
    canonical_wearers = _canonical_wearers(wearers)
    profiles_by_wearer = _profiles_by_wearer(
        canonical_wearers,
        response_profiles,
    )
    response_profiles_sha256 = _response_profiles_sha256(
        canonical_wearers,
        profiles_by_wearer=profiles_by_wearer,
        plan=selected_plan,
    )
    package_kind, package_keys = (
        derive_gcsim_optimizer_theoretical_package_keys(
            engine_context,
            two_plus_two_packages=two_plus_two_packages,
        )
    )
    impact_rows, set_impact_sha256 = _validated_set_impact_rows(
        set_impact,
        wearers=canonical_wearers,
        package_kind=package_kind,
        package_keys=package_keys,
        engine_context=engine_context,
        two_plus_two_packages=two_plus_two_packages,
    )
    pools = tuple(
        _build_wearer_pool(
            wearer,
            wearer_index=index,
            profiles=profiles_by_wearer[wearer],
            package_keys=package_keys,
            impact_rows=impact_rows[wearer],
            quick_anchor_limit=(
                selected_plan.max_quick_four_piece_anchors_per_wearer
                if package_kind
                is GcsimOptimizerTargetPackageKind.FOUR_PIECE
                else selected_plan.max_quick_two_plus_two_anchors_per_wearer
            ),
            plan=selected_plan,
        )
        for index, wearer in enumerate(canonical_wearers)
    )
    profile_bank = _build_theoretical_profile_bank(
        canonical_wearers,
        profiles_by_wearer=profiles_by_wearer,
        plan=selected_plan,
    )
    proposals = _build_joint_proposals(pools, selected_plan)
    return GcsimOptimizerTheoreticalAnytimeCandidateDomain(
        package_kind=package_kind,
        package_keys=package_keys,
        engine_binding_sha256=engine_context.binding_sha256,
        catalog_fingerprint=engine_context.catalog.source_fingerprint,
        response_profiles_sha256=response_profiles_sha256,
        set_impact_sha256=set_impact_sha256,
        plan=selected_plan,
        wearer_pools=pools,
        profile_bank=profile_bank,
        proposals=proposals,
    )


def _select_response_profiles(
    profiles: tuple[GcsimOptimizerAnytimeStatProfile, ...],
    *,
    plan: GcsimOptimizerTheoreticalAnytimeCandidatePlan,
) -> tuple[GcsimOptimizerAnytimeStatProfile, ...]:
    profile_by_id = {item.profile_id: item for item in profiles}
    selected = tuple(
        profile_by_id[profile_id]
        for profile_id in THEORETICAL_ANYTIME_REQUIRED_PROFILE_IDS
    )
    extras = tuple(
        sorted(
            (
                item
                for item in profiles
                if item.profile_id
                not in THEORETICAL_ANYTIME_REQUIRED_PROFILE_IDS
            ),
            key=lambda item: (
                -sum(item.stat_weights),
                item.profile_id,
            ),
        )
    )
    return (
        *selected,
        *extras[: max(plan.max_profiles_per_wearer - len(selected), 0)],
    )


def _build_theoretical_profile_bank(
    wearers: tuple[GcsimOptimizerWearerIdentity, ...],
    *,
    profiles_by_wearer: Mapping[
        GcsimOptimizerWearerIdentity,
        tuple[GcsimOptimizerAnytimeStatProfile, ...],
    ],
    plan: GcsimOptimizerTheoreticalAnytimeCandidatePlan,
) -> StatProfileBank:
    """Project wearer-specific response utility onto the pinned roll axes.

    ``StatProfileBank`` is globally keyed, while response profile names repeat
    for every wearer.  Qualified IDs preserve all four distinct response
    vectors instead of silently averaging them.
    """

    axis_index = {
        axis: index
        for index, axis in enumerate(GCSIM_OPTIMIZER_ANYTIME_STAT_AXES)
    }
    if "er" in {
        axis.key for axis in GCSIM_AUTOMATIC_RESPONSE_STAT_AXES
    }:
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "automatic theoretical profile axes must exclude ER"
        )
    materialized_profiles = []
    for wearer in wearers:
        selected = _select_response_profiles(
            profiles_by_wearer[wearer],
            plan=plan,
        )
        for source in selected:
            weighted_axes = tuple(
                (
                    axis.key,
                    # ``stat_weights`` are deliberately expressed per numeric
                    # stat unit because account pieces carry arbitrary exact
                    # values.  ``StatProfile`` has a different contract: its
                    # normalized weights are target shares of whole abstract
                    # rolls.  Convert the derivative back to the utility of
                    # one comparable five-star roll before normalizing.  Using
                    # the per-unit derivative directly gives CR roughly twice
                    # the budget share of equally valuable CD because a CR
                    # roll is numerically half as large.
                    float(source.stat_weights[axis_index[axis.key]])
                    * GCSIM_STAT_RESPONSE_ROLL_VALUES[axis.key],
                )
                for axis in GCSIM_AUTOMATIC_RESPONSE_STAT_AXES
            )
            total = sum(value for _axis, value in weighted_axes)
            if not isfinite(total):
                raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                    "response profile has non-finite substat utility"
                )
            if total <= 0:
                # A rotation-irrelevant wearer still needs a syntactically
                # materializable equal-investment profile. This deterministic
                # tie-break does not claim that the axis improves damage.
                weights = (
                    StatWeight(
                        axis_key=GCSIM_AUTOMATIC_RESPONSE_STAT_AXES[0].key,
                        weight=1.0,
                    ),
                )
            else:
                weights = tuple(
                    StatWeight(axis_key=axis, weight=value / total)
                    for axis, value in weighted_axes
                    if value > 0
                )
            materialized_profiles.append(
                StatProfile(
                    profile_id=_materialized_profile_id(
                        wearer,
                        source.profile_id,
                    ),
                    kind="theoretical_response",
                    weights=weights,
                )
            )
    try:
        return StatProfileBank(
            axes=GCSIM_AUTOMATIC_RESPONSE_STAT_AXES,
            profiles=tuple(materialized_profiles),
        )
    except ValueError as exc:
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            f"could not materialize theoretical response profiles: {exc}"
        ) from exc


def _response_profiles_sha256(
    wearers: tuple[GcsimOptimizerWearerIdentity, ...],
    *,
    profiles_by_wearer: Mapping[
        GcsimOptimizerWearerIdentity,
        tuple[GcsimOptimizerAnytimeStatProfile, ...],
    ],
    plan: GcsimOptimizerTheoreticalAnytimeCandidatePlan,
) -> str:
    return _canonical_sha256(
        [
            profile.to_dict()
            for wearer in wearers
            for profile in _select_response_profiles(
                profiles_by_wearer[wearer],
                plan=plan,
            )
        ]
    )


def _materialized_profile_id(
    wearer: GcsimOptimizerWearerIdentity,
    source_profile_id: str,
) -> str:
    _require_identifier(source_profile_id, "response profile ID")
    return f"theoretical_slot{wearer.team_slot}_{source_profile_id}"


def _profile_bank_payload(
    profile_bank: StatProfileBank,
) -> dict[str, object]:
    return {
        "axes": [
            {
                "key": axis.key,
                "probe_delta": axis.probe_delta,
                "unit": axis.unit,
            }
            for axis in profile_bank.axes
        ],
        "profiles": [
            {
                "profile_id": profile.profile_id,
                "kind": profile.kind,
                "weights": [
                    {
                        "axis_key": weight.axis_key,
                        "weight": weight.weight,
                    }
                    for weight in profile.weights
                ],
                "focus_axes": list(profile.focus_axes),
            }
            for profile in profile_bank.profiles
        ],
    }


def _build_wearer_pool(
    wearer: GcsimOptimizerWearerIdentity,
    *,
    wearer_index: int,
    profiles: tuple[GcsimOptimizerAnytimeStatProfile, ...],
    package_keys: tuple[str, ...],
    impact_rows: Mapping[str, GcsimOptimizerSetImpactRow],
    quick_anchor_limit: int,
    plan: GcsimOptimizerTheoreticalAnytimeCandidatePlan,
) -> GcsimOptimizerTheoreticalAnytimeWearerPool:
    profile_by_id = {item.profile_id: item for item in profiles}
    selected_profiles = _select_response_profiles(profiles, plan=plan)
    selected_profile_ids = tuple(
        _materialized_profile_id(wearer, item.profile_id)
        for item in selected_profiles
    )

    layouts = _select_layouts(selected_profiles, plan)
    layout_by_id = dict(layouts)
    best_layout_by_profile = {
        profile.profile_id: _best_retained_layout(
            profile,
            layouts=layouts,
        )
        for profile in selected_profiles
    }
    retained_impacts = tuple(
        sorted(
            (
                (package_key, impact_rows[package_key])
                for package_key in package_keys
                if package_key in impact_rows
                and impact_rows[package_key].retained
            ),
            key=lambda item: (
                -item[1].surrogate_dps,
                item[0],
            ),
        )
    )
    retained_package_keys = tuple(
        package_key for package_key, _row in retained_impacts
    )
    eligible_impacts = retained_impacts
    if not eligible_impacts:
        eligible_impacts = (
            min(
                impact_rows.items(),
                key=lambda item: (
                    -item[1].surrogate_dps,
                    item[0],
                ),
            ),
        )
    if len(retained_impacts) > plan.max_package_anchors_per_wearer:
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            f"wearer {wearer.team_slot} retained "
            f"{len(retained_impacts)} packages, exceeding the explicit "
            "retained-package cap"
        )
    quick_impacts = _shortlist_quick_anchor_impacts(
        eligible_impacts,
        limit=quick_anchor_limit,
    )
    anchor_packages = tuple(item[0] for item in quick_impacts)
    package_score = {
        package_key: float(row.surrogate_dps)
        for package_key, row in quick_impacts
    }
    balanced = profile_by_id["balanced"]
    balanced_layout = best_layout_by_profile["balanced"]
    alternatives: dict[
        tuple[str, str, str, str, str],
        GcsimOptimizerTheoreticalAnytimeWearerAlternative,
    ] = {}

    def retain(
        package_key: str,
        profile: GcsimOptimizerAnytimeStatProfile,
        layout: GcsimFiveStarMainStatLayout,
        *,
        tags: tuple[str, ...],
        package_anchor: bool = False,
    ) -> bool:
        if len(alternatives) >= plan.max_wearer_alternatives:
            return False
        layout_id = gcsim_optimizer_main_layout_id(layout)
        if layout_id not in layout_by_id:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "required alternative layout was removed by the plan"
            )
        candidate = SetProfileCandidate(
            state=FourPieceSetState(
                wearer_id=wearer.gcsim_character_key,
                set_key=package_key,
                main_stat_layout_id=layout_id,
            ),
            profile_id=_materialized_profile_id(
                wearer,
                profile.profile_id,
            ),
        )
        key = candidate.key
        existing = alternatives.get(key)
        value = GcsimOptimizerTheoreticalAnytimeWearerAlternative(
            wearer=wearer,
            candidate=candidate,
            layout=layout,
            score=(
                package_score[package_key]
                + _layout_score(profile, layout)
            ),
            diversity_tags=(
                *tags,
                f"package_slot{wearer.team_slot}_{package_key}",
            ),
            package_anchor=package_anchor,
        )
        if existing is None or (
            package_anchor and not existing.package_anchor
        ):
            alternatives[key] = value
            return True
        return False

    for package_key in anchor_packages:
        retain(
            package_key,
            balanced,
            balanced_layout,
            tags=(
                "package_anchor",
                _package_anchor_tag(wearer, package_key),
                *_layout_archetype_tags(balanced_layout),
            ),
            package_anchor=True,
        )

    # Allocate material main/profile witnesses *across* packages before the
    # score fill.  The previous global score sort let one high-surrogate set
    # consume nearly the whole pool while another retained set kept only an
    # arbitrary focus profile.  Round-robin ranks make the bounded loss fair:
    # every package gets its balanced anchor, then every package gets witness
    # rank 1 before any package receives witness rank 2.
    witness_pairs = _ordered_package_witness_pairs(
        selected_profiles,
        layouts=layouts,
        balanced=balanced,
        balanced_layout=balanced_layout,
    )
    for witness_rank, (profile, layout) in enumerate(
        witness_pairs,
        start=1,
    ):
        for package_key in anchor_packages:
            if len(alternatives) >= plan.max_wearer_alternatives:
                break
            retain(
                package_key,
                profile,
                layout,
                tags=(
                    "package_witness",
                    f"package_witness_rank{witness_rank}",
                    _package_witness_tag(
                        wearer,
                        package_key,
                        witness_rank,
                    ),
                    f"response_profile_{profile.profile_id}",
                    *_layout_archetype_tags(layout),
                ),
            )
        if len(alternatives) >= plan.max_wearer_alternatives:
            break

    fill_rows = tuple(
        sorted(
            (
                (
                    (
                        package_score[package_key]
                        + _layout_score(profile, layout)
                    ),
                    package_key,
                    layout_id,
                    profile.profile_id,
                    profile,
                    layout,
                )
                for package_key in anchor_packages
                for layout_id, layout in layouts
                for profile in selected_profiles
            ),
            key=lambda item: (
                -item[0],
                item[1],
                item[2],
                item[3],
            ),
        )
    )
    for _score, package_key, _layout_id, _profile_id, profile, layout in fill_rows:
        if len(alternatives) >= plan.max_wearer_alternatives:
            break
        retain(
            package_key,
            profile,
            layout,
            tags=(
                "surrogate_fill",
                f"response_profile_{profile.profile_id}",
                *_layout_archetype_tags(layout),
            ),
        )
    return GcsimOptimizerTheoreticalAnytimeWearerPool(
        wearer=wearer,
        layouts=layouts,
        profile_ids=selected_profile_ids,
        retained_package_keys=retained_package_keys,
        alternatives=tuple(alternatives.values()),
    )


def _shortlist_quick_anchor_impacts(
    rows: tuple[tuple[str, GcsimOptimizerSetImpactRow], ...],
    *,
    limit: int,
) -> tuple[tuple[str, GcsimOptimizerSetImpactRow], ...]:
    """Bound retained impact evidence before the fixed screen-64 race.

    Package keys in theoretical 2p+2p mode already represent engine-proved
    effect-equivalence groups.  Within that reduced domain, preserve the best
    row of every measured impact classification, then fill strictly by paired
    surrogate DPS.  The returned subset is explicit in wearer-pool metadata;
    omitted retained rows are never reported as screened.
    """

    if len(rows) <= limit:
        return rows
    selected: set[str] = set()
    classifications = tuple(
        sorted({row.classification.value for _key, row in rows})
    )
    for classification in classifications:
        package_key, _row = next(
            item
            for item in rows
            if item[1].classification.value == classification
        )
        selected.add(package_key)
    for package_key, _row in rows:
        if len(selected) >= limit:
            break
        selected.add(package_key)
    return tuple(
        item for item in rows if item[0] in selected
    )


def _select_layouts(
    profiles: tuple[GcsimOptimizerAnytimeStatProfile, ...],
    plan: GcsimOptimizerTheoreticalAnytimeCandidatePlan,
) -> tuple[tuple[str, GcsimFiveStarMainStatLayout], ...]:
    balanced = next(
        profile for profile in profiles
        if profile.profile_id == "balanced"
    )
    crit_material = _crit_is_material(profiles)
    legal_layouts: dict[str, GcsimFiveStarMainStatLayout] = {}
    for profile in profiles:
        legal_by_slot = []
        for slot, axes in (
            ("sands", LEGAL_FIVE_STAR_SANDS_MAIN_STATS),
            ("goblet", LEGAL_FIVE_STAR_GOBLET_MAIN_STATS),
            ("circlet", LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS),
        ):
            retained = set(profile.retained_main_axes_by_slot[slot])
            if slot == "circlet" and crit_material:
                # CR and CD are one coupled build direction.  The short
                # response probe can resolve one side while noise leaves the
                # other negligible; the theoretical domain must still test
                # both balance points.
                retained.update(_CRIT_MAIN_AXES)
            positive = tuple(
                axis
                for axis in axes
                if axis != "er"
                and axis in retained
            )
            legal_by_slot.append(
                positive
                or (min(axis for axis in axes if axis != "er"),)
            )
        for sands, goblet, circlet in product(*legal_by_slot):
            layout = GcsimFiveStarMainStatLayout(
                sands,
                goblet,
                circlet,
            )
            legal_layouts.setdefault(
                gcsim_optimizer_main_layout_id(layout),
                layout,
            )
    if not legal_layouts:
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "response produced no legal theoretical main-stat layout"
        )

    result: list[tuple[str, GcsimFiveStarMainStatLayout]] = []
    seen: set[str] = set()

    def retain(layout: GcsimFiveStarMainStatLayout) -> None:
        if len(result) >= plan.max_layouts_per_wearer:
            return
        layout_id = gcsim_optimizer_main_layout_id(layout)
        if layout_id in seen:
            return
        seen.add(layout_id)
        result.append((layout_id, layout))

    # The balanced full triple is the package anchor and is never displaced
    # by a narrowly focused profile.
    retain(_best_legal_layout(balanced, tuple(legal_layouts.values())))

    if crit_material:
        # Reserve both crit-circlet directions before any score-ordered fill.
        # Where measured scaling and elemental axes coexist, make those
        # witnesses genuinely mixed (scaling / elemental / crit) instead of
        # allowing a high EM response to spend every retained slot on another
        # all-EM-like triple.
        for crit_axis in ("cr", "cd"):
            matching = tuple(
                layout
                for layout in legal_layouts.values()
                if layout.sands in _SCALING_MAIN_AXES
                and layout.goblet in _ELEMENTAL_DAMAGE_MAIN_AXES
                and layout.circlet == crit_axis
            )
            if not matching:
                matching = tuple(
                    layout
                    for layout in legal_layouts.values()
                    if layout.circlet == crit_axis
                )
            if matching:
                retain(_best_legal_layout(balanced, matching))

    # Preserve whole-layout archetypes before profile score fill.  Each row is
    # selected from retained axes (plus the paired crit safeguard); the labels
    # describe generic artifact mechanics rather than character-specific
    # knowledge.
    for archetype in (
        "direct",
        "reaction_direct",
        "scaling",
        "reaction",
        "elemental",
        "crit",
    ):
        matching = tuple(
            layout
            for layout in legal_layouts.values()
            if archetype in _layout_archetypes(layout)
        )
        if not matching:
            continue
        retain(_best_legal_layout(balanced, matching))

    # A focus profile may expose another complete triple (for example a
    # reaction/direct EM + elemental + crit layout).  Add those only after the
    # balanced/material anchors so a same-axis focus cannot consume the cap.
    for profile in profiles:
        retain(_best_legal_layout(profile, tuple(legal_layouts.values())))

    ordered = tuple(
        sorted(
            legal_layouts.values(),
            key=lambda layout: (
                -max(_layout_score(profile, layout) for profile in profiles),
                -_layout_score(balanced, layout),
                gcsim_optimizer_main_layout_id(layout),
            ),
        )
    )
    for layout in ordered:
        retain(layout)
        if len(result) >= plan.max_layouts_per_wearer:
            break
    return tuple(result)


def _ordered_package_witness_pairs(
    profiles: tuple[GcsimOptimizerAnytimeStatProfile, ...],
    *,
    layouts: tuple[tuple[str, GcsimFiveStarMainStatLayout], ...],
    balanced: GcsimOptimizerAnytimeStatProfile,
    balanced_layout: GcsimFiveStarMainStatLayout,
) -> tuple[
    tuple[
        GcsimOptimizerAnytimeStatProfile,
        GcsimFiveStarMainStatLayout,
    ],
    ...,
]:
    """Order fair per-package witnesses by full-layout materiality.

    Different balanced main triples come first.  Profile-only differences are
    useful for substat allocation, but they must not crowd out mixed main-stat
    triples such as scaling/elemental/crit.
    """

    rows: list[
        tuple[
            GcsimOptimizerAnytimeStatProfile,
            GcsimFiveStarMainStatLayout,
        ]
    ] = []
    seen: set[tuple[str, str]] = {
        (
            balanced.profile_id,
            gcsim_optimizer_main_layout_id(balanced_layout),
        )
    }

    def retain(
        profile: GcsimOptimizerAnytimeStatProfile,
        layout: GcsimFiveStarMainStatLayout,
    ) -> None:
        identity = (
            profile.profile_id,
            gcsim_optimizer_main_layout_id(layout),
        )
        if identity in seen:
            return
        seen.add(identity)
        rows.append((profile, layout))

    for _layout_id, layout in layouts:
        retain(balanced, layout)
    for profile in profiles:
        if profile.profile_id == "balanced":
            continue
        retain(
            profile,
            _best_retained_layout(profile, layouts=layouts),
        )
    for profile in profiles:
        for _layout_id, layout in sorted(
            layouts,
            key=lambda item: (
                -_layout_score(profile, item[1]),
                item[0],
            ),
        ):
            retain(profile, layout)
    return tuple(rows)


def _build_joint_proposals(
    pools: tuple[GcsimOptimizerTheoreticalAnytimeWearerPool, ...],
    plan: GcsimOptimizerTheoreticalAnytimeCandidatePlan,
) -> tuple[GcsimOptimizerTheoreticalAnytimeProposal, ...]:
    base = tuple(_base_alternative(pool) for pool in pools)
    proposals: dict[
        tuple[tuple[str, str, str, str, str], ...],
        GcsimOptimizerTheoreticalAnytimeProposal,
    ] = {}

    def retain(
        alternatives: tuple[
            GcsimOptimizerTheoreticalAnytimeWearerAlternative, ...
        ],
        *,
        tags: tuple[str, ...],
    ) -> bool:
        if len(proposals) >= plan.max_joint_proposals:
            return False
        proposal = _proposal(alternatives, tags=tags)
        if proposal.state.probe_key in proposals:
            return False
        proposals[proposal.state.probe_key] = proposal
        return True

    retain(base, tags=("baseline",))

    anchors_by_pool = tuple(
        tuple(
            sorted(
                (
                    item for item in pool.alternatives
                    if item.package_anchor
                ),
                key=lambda item: (
                    item.package_key,
                    item.candidate.key,
                ),
            )
        )
        for pool in pools
    )

    # Reserve local package-coordinate evidence around the strongest paired-
    # impact base *before* broad catalog coverage.  Without this reservation a
    # wide set domain can fill the 64-proposal quick tier with coordinated
    # audit rows, so a high-value swap such as one wearer's Golden Troupe is
    # only seen inside an unrelated four-wearer package combination.  These
    # rows deliberately retain the same balanced physical/main/profile base
    # for the other three wearers.
    coordinate_neighbors_by_pool: list[
        tuple[GcsimOptimizerTheoreticalAnytimeWearerAlternative, ...]
    ] = []
    for pool_index, anchors in enumerate(anchors_by_pool):
        neighbors = tuple(
            sorted(
                (
                    item
                    for item in anchors
                    if item.candidate.key != base[pool_index].candidate.key
                ),
                key=lambda item: (
                    -item.score,
                    item.package_key,
                    item.candidate.key,
                ),
            )[
                : plan.max_package_coordinate_neighbors_per_wearer
            ]
        )
        coordinate_neighbors_by_pool.append(neighbors)
        for alternative in neighbors:
            changed = list(base)
            changed[pool_index] = alternative
            retain(
                tuple(changed),
                tags=(
                    "package_coordinate_neighbor",
                    f"package_coordinate_slot{pool_index + 1}",
                ),
            )

    combination_rows: list[
        tuple[
            float,
            tuple[GcsimOptimizerTheoreticalAnytimeWearerAlternative, ...],
        ]
    ] = []
    combination_beams = tuple(
        (base[index], *rows[:2])
        for index, rows in enumerate(coordinate_neighbors_by_pool)
    )
    for alternatives in product(*combination_beams):
        changed_count = sum(
            item.candidate.key != base[index].candidate.key
            for index, item in enumerate(alternatives)
        )
        if changed_count < 2:
            continue
        combination_rows.append(
            (sum(item.score for item in alternatives), alternatives)
        )
    combination_rows.sort(
        key=lambda item: (
            -item[0],
            tuple(value.candidate.key for value in item[1]),
        )
    )
    for _score, alternatives in combination_rows[
        : plan.max_package_combination_neighbors
    ]:
        retain(
            alternatives,
            tags=("package_coordinate_combination",),
        )

    required_anchors = {
        (pool_index, item.candidate.key)
        for pool_index, rows in enumerate(anchors_by_pool)
        for item in rows
    }
    covered_anchors = {
        (pool_index, item.candidate.key)
        for pool_index, item in enumerate(base)
        if item.package_anchor
    }
    anchor_rows = _coordinated_alternative_rows(anchors_by_pool)
    anchor_probe_count = 0
    while covered_anchors != required_anchors:
        if anchor_probe_count >= plan.max_joint_package_anchor_proposals:
            break
        candidates = tuple(
            row for row in anchor_rows
            if any(
                (pool_index, item.candidate.key)
                not in covered_anchors
                for pool_index, item in enumerate(row)
            )
        )
        if not candidates:
            break
        selected = max(
            candidates,
            key=lambda row: (
                sum(
                    (pool_index, item.candidate.key)
                    not in covered_anchors
                    for pool_index, item in enumerate(row)
                ),
                sum(item.score for item in row),
                tuple(item.candidate.key for item in row),
            ),
        )
        selected_probe_key = _proposal(
            selected,
            tags=("coordinated", "package_anchor_probe"),
        ).state.probe_key
        if selected_probe_key in proposals:
            covered_anchors.update(
                (pool_index, item.candidate.key)
                for pool_index, item in enumerate(selected)
            )
            anchor_rows = tuple(
                row for row in anchor_rows if row != selected
            )
            continue
        if not retain(
            selected,
            tags=("coordinated", "package_anchor_probe"),
        ):
            anchor_rows = tuple(
                row for row in anchor_rows if row != selected
            )
            continue
        anchor_probe_count += 1
        covered_anchors.update(
            (pool_index, item.candidate.key)
            for pool_index, item in enumerate(selected)
        )
    if covered_anchors != required_anchors:
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "joint-proposal caps cannot preserve balanced-anchor coverage "
            "for every shortlisted wearer/package"
        )

    # Coordinate fair witness ranks next.  One proposal carries four witness
    # observations, so a 64-state quick tier can cover several full layouts
    # per package without multiplying the screen by four wearers.
    witness_rank_tags = tuple(
        sorted(
            {
                tag
                for pool in pools
                for item in pool.alternatives
                for tag in item.diversity_tags
                if tag.startswith("package_witness_rank")
            },
            key=lambda tag: int(tag.removeprefix("package_witness_rank")),
        )
    )
    for rank_tag in witness_rank_tags:
        rows_by_pool = tuple(
            tuple(
                sorted(
                    (
                        item for item in pool.alternatives
                        if rank_tag in item.diversity_tags
                    ),
                    key=lambda item: (
                        item.package_key,
                        item.candidate.key,
                    ),
                )
            )
            for pool in pools
        )
        required = {
            (pool_index, item.candidate.key)
            for pool_index, rows in enumerate(rows_by_pool)
            for item in rows
        }
        if not required:
            continue
        coordinated = _coordinated_alternative_rows(
            tuple(
                rows if rows else (base[pool_index],)
                for pool_index, rows in enumerate(rows_by_pool)
            )
        )
        covered: set[
            tuple[int, tuple[str, str, str, str, str]]
        ] = set()
        while covered != required and len(proposals) < plan.max_joint_proposals:
            candidates = tuple(
                row for row in coordinated
                if any(
                    (pool_index, item.candidate.key) in required
                    and (pool_index, item.candidate.key) not in covered
                    for pool_index, item in enumerate(row)
                )
            )
            if not candidates:
                break
            selected = max(
                candidates,
                key=lambda row: (
                    sum(
                        (pool_index, item.candidate.key) in required
                        and (pool_index, item.candidate.key) not in covered
                        for pool_index, item in enumerate(row)
                    ),
                    sum(item.score for item in row),
                    tuple(item.candidate.key for item in row),
                ),
            )
            retain(
                selected,
                tags=(
                    "coordinated",
                    "package_witness_probe",
                    rank_tag,
                ),
            )
            covered.update(
                (pool_index, item.candidate.key)
                for pool_index, item in enumerate(selected)
                if (pool_index, item.candidate.key) in required
            )

    fill_rows = []
    for pool_index, pool in enumerate(pools):
        for alternative in pool.alternatives:
            changed = list(base)
            changed[pool_index] = alternative
            fill_rows.append(tuple(changed))
    fill_rows.extend(
        _coordinated_alternative_rows(
            tuple(pool.alternatives for pool in pools)
        )
    )
    fill_rows.sort(
        key=lambda values: (
            -sum(item.score for item in values),
            tuple(item.candidate.key for item in values),
        )
    )
    for values in fill_rows:
        if len(proposals) >= plan.max_joint_proposals:
            break
        retain(values, tags=("surrogate_fill",))
    return tuple(proposals.values())


def _coordinated_alternative_rows(
    rows_by_pool: tuple[
        tuple[GcsimOptimizerTheoreticalAnytimeWearerAlternative, ...],
        ...,
    ],
) -> tuple[
    tuple[GcsimOptimizerTheoreticalAnytimeWearerAlternative, ...],
    ...,
]:
    if not rows_by_pool or any(not rows for rows in rows_by_pool):
        return ()
    row_count = max(len(rows) for rows in rows_by_pool)
    return tuple(
        tuple(
            rows[(offset + pool_index) % len(rows)]
            for pool_index, rows in enumerate(rows_by_pool)
        )
        for offset in range(row_count)
    )


def _proposal(
    alternatives: tuple[
        GcsimOptimizerTheoreticalAnytimeWearerAlternative, ...
    ],
    *,
    tags: tuple[str, ...],
) -> GcsimOptimizerTheoreticalAnytimeProposal:
    return GcsimOptimizerTheoreticalAnytimeProposal(
        state=FullTeamProbeState(
            tuple(item.candidate for item in alternatives)
        ),
        score=sum(item.score for item in alternatives),
        diversity_tags=tuple(
            {
                *tags,
                *(
                    tag
                    for item in alternatives
                    for tag in item.diversity_tags
                ),
            }
        ),
        package_anchor_count=sum(
            item.package_anchor for item in alternatives
        ),
    )


def _base_alternative(
    pool: GcsimOptimizerTheoreticalAnytimeWearerPool,
) -> GcsimOptimizerTheoreticalAnytimeWearerAlternative:
    anchors = tuple(
        item for item in pool.alternatives if item.package_anchor
    )
    if not anchors:
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "wearer pool lacks a package anchor"
        )
    return min(
        anchors,
        key=lambda item: (
            -item.score,
            item.package_key,
            item.layout_id,
            item.profile_id,
        ),
    )


def _best_legal_layout(
    profile: GcsimOptimizerAnytimeStatProfile,
    layouts: Sequence[GcsimFiveStarMainStatLayout],
) -> GcsimFiveStarMainStatLayout:
    values = tuple(layouts)
    if not values:
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "cannot choose a best layout from an empty legal domain"
        )
    return min(
        values,
        key=lambda layout: (
            -_layout_score(profile, layout),
            gcsim_optimizer_main_layout_id(layout),
        ),
    )


def _layout_archetypes(
    layout: GcsimFiveStarMainStatLayout,
) -> tuple[str, ...]:
    axes = (layout.sands, layout.goblet, layout.circlet)
    result = []
    if (
        layout.goblet in _ELEMENTAL_DAMAGE_MAIN_AXES
        and layout.circlet in _CRIT_MAIN_AXES
    ):
        result.append("direct")
        if layout.sands in _SCALING_MAIN_AXES:
            result.append("scaling_direct")
        if layout.sands == "em":
            result.append("reaction_direct")
    if sum(axis in _SCALING_MAIN_AXES for axis in axes) >= 2:
        result.append("scaling")
    if sum(axis == "em" for axis in axes) >= 2:
        result.append("reaction")
    if layout.goblet in _ELEMENTAL_DAMAGE_MAIN_AXES:
        result.append("elemental")
    if layout.circlet in _CRIT_MAIN_AXES:
        result.append("crit")
    return tuple(result)


def _crit_is_material(
    profiles: Sequence[GcsimOptimizerAnytimeStatProfile],
) -> bool:
    return any(
        axis in _CRIT_MAIN_AXES
        and classification in _USEFUL_RESPONSE_CLASSIFICATIONS
        for profile in profiles
        for axis, classification in profile.stat_classifications
    ) or any(
        slot == "circlet"
        and axis in _CRIT_MAIN_AXES
        and classification in _USEFUL_RESPONSE_CLASSIFICATIONS
        for profile in profiles
        for slot, axis, classification in profile.main_classifications
    )


def _layout_archetype_tags(
    layout: GcsimFiveStarMainStatLayout,
) -> tuple[str, ...]:
    return tuple(
        f"main_archetype_{archetype}"
        for archetype in _layout_archetypes(layout)
    )


def _package_anchor_tag(
    wearer: GcsimOptimizerWearerIdentity,
    package_key: str,
) -> str:
    return f"package_anchor_slot{wearer.team_slot}_{package_key}"


def _package_witness_tag(
    wearer: GcsimOptimizerWearerIdentity,
    package_key: str,
    witness_rank: int,
) -> str:
    return (
        f"package_witness_r{witness_rank}_slot"
        f"{wearer.team_slot}_{package_key}"
    )


def _best_retained_layout(
    profile: GcsimOptimizerAnytimeStatProfile,
    *,
    layouts: tuple[tuple[str, GcsimFiveStarMainStatLayout], ...],
) -> GcsimFiveStarMainStatLayout:
    return min(
        (layout for _layout_id, layout in layouts),
        key=lambda layout: (
            -_layout_score(profile, layout),
            gcsim_optimizer_main_layout_id(layout),
        ),
    )


def _layout_score(
    profile: GcsimOptimizerAnytimeStatProfile,
    layout: GcsimFiveStarMainStatLayout,
) -> float:
    index = profile.main_score_index
    return sum(
        float(index.get((slot, axis), 0.0))
        for slot, axis in (
            ("sands", layout.sands),
            ("goblet", layout.goblet),
            ("circlet", layout.circlet),
        )
    )


def _validated_set_impact_rows(
    set_impact: GcsimOptimizerSetImpactResult,
    *,
    wearers: tuple[GcsimOptimizerWearerIdentity, ...],
    package_kind: GcsimOptimizerTargetPackageKind,
    package_keys: tuple[str, ...],
    engine_context: GcsimOptimizerEngineContext,
    two_plus_two_packages: Mapping[
        str,
        GcsimTwoPlusTwoTargetPackage,
    ] | None,
) -> tuple[
    Mapping[
        GcsimOptimizerWearerIdentity,
        Mapping[str, GcsimOptimizerSetImpactRow],
    ],
    str,
]:
    if not isinstance(set_impact, GcsimOptimizerSetImpactResult):
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "set_impact must be typed"
        )
    pair_packages = freeze_gcsim_theoretical_pair_packages(
        two_plus_two_packages
    )
    by_wearer: dict[
        GcsimOptimizerWearerIdentity,
        dict[str, GcsimOptimizerSetImpactRow],
    ] = {wearer: {} for wearer in wearers}
    expected_wearers = set(wearers)
    for row in set_impact.rows:
        target = row.target
        if isinstance(target, GcsimOptimizerSingleTwoPieceImpactTarget):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "component-only 2p impacts cannot enter package candidates"
            )
        if target.wearer not in expected_wearers:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "set-impact row belongs to another wearer"
            )
        package = target.package
        if package_kind is GcsimOptimizerTargetPackageKind.FOUR_PIECE:
            if not isinstance(package, GcsimFourPieceTargetPackage):
                raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                    "4p candidate impact row uses another package kind"
                )
            package_key = package.set_ref.gcsim_set_key
            refs = (package.set_ref,)
        else:
            if not isinstance(package, GcsimTwoPlusTwoTargetPackage):
                raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                    "2p+2p candidate impact row uses another package kind"
                )
            package_key = gcsim_theoretical_pair_package_key(package)
            refs = (package.set_a, package.set_b)
            if (
                package_key not in pair_packages
                or pair_packages[package_key] != package
            ):
                raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                    "2p+2p set-impact row differs from its frozen package"
                )
        if package_key not in package_keys:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "set-impact row lies outside the theoretical package domain"
            )
        if any(
            ref.engine_binding_sha256 != engine_context.binding_sha256
            or ref.catalog_fingerprint
            != engine_context.catalog.source_fingerprint
            for ref in refs
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "set-impact row differs from the frozen engine/catalog"
            )
        wearer_rows = by_wearer[target.wearer]
        if package_key in wearer_rows:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "set-impact contains a duplicate wearer/package row"
            )
        wearer_rows[package_key] = row

    expected_keys = set(package_keys)
    for wearer in wearers:
        actual_keys = set(by_wearer[wearer])
        if (
            not actual_keys
            or not actual_keys.issubset(expected_keys)
            or (
                package_kind
                is GcsimOptimizerTargetPackageKind.FOUR_PIECE
                and actual_keys != expected_keys
            )
        ):
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                f"set-impact coverage is incomplete for wearer "
                f"{wearer.team_slot}"
            )
    if package_kind is GcsimOptimizerTargetPackageKind.TWO_PLUS_TWO:
        covered_keys = {
            package_key
            for rows in by_wearer.values()
            for package_key in rows
        }
        if covered_keys != expected_keys:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                "2p+2p set-impact rows do not cover their prospective domain"
            )
    frozen = MappingProxyType(
        {
            wearer: MappingProxyType(dict(sorted(rows.items())))
            for wearer, rows in by_wearer.items()
        }
    )
    identity = _canonical_sha256(
        {
            "schema_version": (
                GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_CANDIDATE_SCHEMA_VERSION
            ),
            "plan": set_impact.plan.to_dict(),
            "response_evidence_sha256": (
                set_impact.response_evidence_sha256
            ),
            "rows": [
                {
                    "target": row.target.to_dict(),
                    "classification": row.classification.value,
                    "surrogate_dps": row.surrogate_dps,
                    "evidence_sha256": row.evidence_sha256,
                }
                for row in set_impact.rows
            ],
        }
    )
    return frozen, identity


def _canonical_wearers(
    wearers: Sequence[GcsimOptimizerWearerIdentity],
) -> tuple[GcsimOptimizerWearerIdentity, ...]:
    try:
        values = tuple(wearers)
    except TypeError as exc:
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "wearers must be a sequence"
        ) from exc
    if (
        len(values) != 4
        or any(
            not isinstance(item, GcsimOptimizerWearerIdentity)
            for item in values
        )
        or tuple(item.team_slot for item in values) != (1, 2, 3, 4)
        or len({item.gcsim_character_key for item in values}) != 4
    ):
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "wearers must cover four unique canonical team slots"
        )
    return values


def _profiles_by_wearer(
    wearers: tuple[GcsimOptimizerWearerIdentity, ...],
    response_profiles: Sequence[GcsimOptimizerAnytimeStatProfile],
) -> Mapping[
    GcsimOptimizerWearerIdentity,
    tuple[GcsimOptimizerAnytimeStatProfile, ...],
]:
    try:
        profiles = tuple(response_profiles)
    except TypeError as exc:
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "response_profiles must be a sequence"
        ) from exc
    if any(
        not isinstance(item, GcsimOptimizerAnytimeStatProfile)
        for item in profiles
    ):
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "response profiles must be typed"
        )
    if len(
        {(item.wearer, item.profile_id) for item in profiles}
    ) != len(profiles):
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "response wearer/profile pairs must be unique"
        )
    expected = set(wearers)
    if {item.wearer for item in profiles} != expected:
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "response profiles must cover exactly the frozen wearers"
        )
    result = {}
    for wearer in wearers:
        rows = tuple(
            sorted(
                (
                    item for item in profiles
                    if item.wearer == wearer
                ),
                key=lambda item: item.profile_id,
            )
        )
        by_id = {item.profile_id: item for item in rows}
        missing = tuple(
            profile_id
            for profile_id in THEORETICAL_ANYTIME_REQUIRED_PROFILE_IDS
            if profile_id not in by_id
        )
        if missing:
            raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                f"wearer {wearer.team_slot} lacks required profiles: "
                f"{missing!r}"
            )
        for item in rows:
            if item.stat_weights[_ER_AXIS_INDEX] != 0:
                raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                    "theoretical response profiles cannot weight ER"
                )
            if any(
                axis == "er" and score != 0
                for _slot, axis, score in item.main_scores
            ):
                raise GcsimOptimizerTheoreticalAnytimeCandidateError(
                    "theoretical response profiles cannot score an ER main"
                )
            _reject_er_profile_id(item.profile_id)
        result[wearer] = rows
    return MappingProxyType(result)


def _require_engine_context(
    engine_context: GcsimOptimizerEngineContext,
) -> None:
    if not isinstance(engine_context, GcsimOptimizerEngineContext):
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "engine_context must be typed"
        )
    if not engine_context.trusted or engine_context.issues:
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "theoretical candidates require a trusted issue-free engine"
        )


def _validate_layout(layout: GcsimFiveStarMainStatLayout) -> None:
    if (
        layout.sands == "er"
        or layout.sands not in LEGAL_FIVE_STAR_SANDS_MAIN_STATS
        or layout.goblet not in LEGAL_FIVE_STAR_GOBLET_MAIN_STATS
        or layout.circlet not in LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS
    ):
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "theoretical candidate uses an illegal or ER main-stat layout"
        )


def _reject_er_profile_id(profile_id: str) -> None:
    tokens = tuple(
        _PROFILE_TOKEN_RE.findall(str(profile_id).strip().casefold())
    )
    if "er" in tokens:
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "theoretical candidates cannot carry an ER response profile"
        )


def _canonical_tags(values: Sequence[str]) -> tuple[str, ...]:
    try:
        tags = tuple(sorted(set(values)))
    except TypeError as exc:
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "diversity tags must be strings"
        ) from exc
    for tag in tags:
        _require_identifier(tag, "diversity tag")
    return tags


def _require_identifier(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not _IDENTIFIER_RE.fullmatch(value)
    ):
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            f"{field_name} must be a lowercase identifier"
        )


def _require_sha256(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not _SHA256_RE.fullmatch(value)
    ):
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            f"{field_name} must be a lowercase SHA-256"
        )


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _require_schema(value: int) -> None:
    if (
        value
        != GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_CANDIDATE_SCHEMA_VERSION
    ):
        raise GcsimOptimizerTheoreticalAnytimeCandidateError(
            "unsupported theoretical anytime candidate schema"
        )


__all__ = [
    "GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_CANDIDATE_PLAN_ID",
    "GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_CANDIDATE_PLAN_VERSION",
    "GCSIM_OPTIMIZER_THEORETICAL_ANYTIME_CANDIDATE_SCHEMA_VERSION",
    "GcsimOptimizerTheoreticalAnytimeCandidateDomain",
    "GcsimOptimizerTheoreticalAnytimeCandidateError",
    "GcsimOptimizerTheoreticalAnytimeCandidatePlan",
    "GcsimOptimizerTheoreticalAnytimeProposal",
    "GcsimOptimizerTheoreticalAnytimeWearerAlternative",
    "GcsimOptimizerTheoreticalAnytimeWearerPool",
    "THEORETICAL_ANYTIME_REQUIRED_PROFILE_IDS",
    "build_gcsim_optimizer_theoretical_anytime_candidate_domain",
    "derive_gcsim_optimizer_theoretical_package_keys",
    "gcsim_optimizer_theoretical_team_package_signature",
]
