"""Conservative inventory catalog with advisory skyline diagnostics.

This module is intentionally isolated from the account optimizer services.  It
does not score artifacts with a character-specific scalar and it does not
truncate the physical inventory silently.  Instead it:

* freezes one eligibility profile for every physical dense artifact;
* compares pieces only inside an exact set/slot/rarity/eligibility group;
* measures strict componentwise dominance over every normalized artifact axis;
* marks the first ``k`` Pareto layers for diagnostics only;
* retains every eligible physical row and shadows only unusable rows.

Componentwise artifact stats are not a universal monotonicity certificate for
an exact GCSIM objective.  More ER, for example, can change an ``energy < max``
condition and therefore alter conditional weapon or action behaviour.  Skyline
depth must not hard-prune a row until a future caller supplies and validates a
scenario-specific monotonicity proof.  Exact-stat physical copies never
dominate one another and retain their real multiplicity within a layer.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from math import isfinite
from types import MappingProxyType

from .optimizer_anytime_candidates import (
    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES,
    GcsimOptimizerDenseArtifact,
    GcsimOptimizerDenseArtifactCatalog,
)
from .optimizer_artifact_database import (
    evaluate_gcsim_optimizer_artifact_eligibility,
)
from .optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ACCOUNT_STAT_AXES,
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimOptimizerWearerIdentity,
)
from .optimizer_run_input import GcsimOptimizerRunInput


GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SCHEMA_VERSION = 2
GCSIM_OPTIMIZER_INVENTORY_FRONTIER_PLAN_ID = (
    "inventory_advisory_componentwise_skyline"
)
GCSIM_OPTIMIZER_INVENTORY_FRONTIER_PLAN_VERSION = 2

GCSIM_OPTIMIZER_INVENTORY_FRONTIER_RETAINED = "retained_no_hard_prune"
GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SHADOW_INELIGIBLE = (
    "shadow_no_eligible_wearer"
)
GCSIM_OPTIMIZER_INVENTORY_ADMISSION_UNCONDITIONAL = "unconditional"
GCSIM_OPTIMIZER_INVENTORY_ADMISSION_REQUIRES_ACTIVE_SET = (
    "requires_active_set"
)
GCSIM_OPTIMIZER_INVENTORY_ADMISSION_INELIGIBLE = "ineligible"

# Dense artifacts are versioned against this order.  The equality assertion is
# deliberate: the advisory diagnostic must describe the complete normalized
# artifact space, not a convenient scoring subset.
GCSIM_OPTIMIZER_INVENTORY_STAT_AXES = tuple(
    GCSIM_OPTIMIZER_ANYTIME_STAT_AXES
)
if (
    frozenset(GCSIM_OPTIMIZER_INVENTORY_STAT_AXES)
    != GCSIM_OPTIMIZER_ACCOUNT_STAT_AXES
):
    raise RuntimeError(
        "dense artifact axes no longer cover the full normalized account "
        "artifact stat space"
    )

_SLOT_ORDER = MappingProxyType(
    {
        slot: index
        for index, slot in enumerate(GCSIM_OPTIMIZER_ARTIFACT_SLOTS)
    }
)
_VALID_DISPOSITIONS = frozenset(
    {
        GCSIM_OPTIMIZER_INVENTORY_FRONTIER_RETAINED,
        GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SHADOW_INELIGIBLE,
    }
)
_VALID_ADMISSION_KINDS = frozenset(
    {
        GCSIM_OPTIMIZER_INVENTORY_ADMISSION_UNCONDITIONAL,
        GCSIM_OPTIMIZER_INVENTORY_ADMISSION_REQUIRES_ACTIVE_SET,
        GCSIM_OPTIMIZER_INVENTORY_ADMISSION_INELIGIBLE,
    }
)


class GcsimOptimizerInventoryFrontierError(ValueError):
    """Fail-closed inventory-frontier contract error."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerInventoryEligibilityEntry:
    """Eligibility evidence for one physical artifact and one wearer."""

    wearer: GcsimOptimizerWearerIdentity
    eligible: bool
    reason_code: str
    admission_kind: str
    required_active_set_uid: str = ""
    schema_version: int = GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerInventoryFrontierError(
                "eligibility wearer must be typed"
            )
        if not isinstance(self.eligible, bool):
            raise GcsimOptimizerInventoryFrontierError(
                "eligibility flag must be boolean"
            )
        _require_trimmed_text(self.reason_code, "eligibility reason_code")
        if self.admission_kind not in _VALID_ADMISSION_KINDS:
            raise GcsimOptimizerInventoryFrontierError(
                "eligibility admission_kind is unsupported"
            )
        if self.required_active_set_uid != self.required_active_set_uid.strip():
            raise GcsimOptimizerInventoryFrontierError(
                "required_active_set_uid must be trimmed"
            )
        if self.eligible:
            if self.admission_kind == GCSIM_OPTIMIZER_INVENTORY_ADMISSION_INELIGIBLE:
                raise GcsimOptimizerInventoryFrontierError(
                    "eligible row cannot use ineligible admission"
                )
            if (
                self.admission_kind
                == GCSIM_OPTIMIZER_INVENTORY_ADMISSION_REQUIRES_ACTIVE_SET
            ) != bool(self.required_active_set_uid):
                raise GcsimOptimizerInventoryFrontierError(
                    "conditional admission requires exactly one active set UID"
                )
        elif (
            self.admission_kind != GCSIM_OPTIMIZER_INVENTORY_ADMISSION_INELIGIBLE
            or self.required_active_set_uid
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "ineligible row must use ineligible admission without a set UID"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.identity_payload())

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "wearer": self.wearer.to_dict(),
            "eligible": self.eligible,
            "reason_code": self.reason_code,
            "admission_kind": self.admission_kind,
            "required_active_set_uid": self.required_active_set_uid,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.identity_payload(),
            "identity_sha256": self.identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerInventoryEligibilityMask:
    """Four-wearer eligibility mask plus its exact admission semantics."""

    entries: tuple[GcsimOptimizerInventoryEligibilityEntry, ...]
    schema_version: int = GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        entries = tuple(self.entries)
        if len(entries) != 4 or any(
            not isinstance(item, GcsimOptimizerInventoryEligibilityEntry)
            for item in entries
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "eligibility mask must contain exactly four typed entries"
            )
        slots = tuple(item.wearer.team_slot for item in entries)
        if slots != (1, 2, 3, 4):
            raise GcsimOptimizerInventoryFrontierError(
                "eligibility entries must use deterministic team-slot order"
            )
        if len({item.wearer for item in entries}) != len(entries):
            raise GcsimOptimizerInventoryFrontierError(
                "eligibility mask wearer identities must be unique"
            )
        object.__setattr__(self, "entries", entries)

    @property
    def bit_mask(self) -> int:
        return sum(
            1 << (item.wearer.team_slot - 1)
            for item in self.entries
            if item.eligible
        )

    @property
    def eligible_wearer_slots(self) -> tuple[int, ...]:
        return tuple(
            item.wearer.team_slot for item in self.entries if item.eligible
        )

    @property
    def eligible_count(self) -> int:
        return len(self.eligible_wearer_slots)

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.identity_payload())

    @property
    def comparison_signature(
        self,
    ) -> tuple[tuple[str, bool, str, str, str], ...]:
        """Exact semantics used to prevent unsafe cross-context dominance."""

        return tuple(
            (
                item.wearer.identity_sha256,
                item.eligible,
                item.reason_code,
                item.admission_kind,
                item.required_active_set_uid,
            )
            for item in self.entries
        )

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "bit_mask": self.bit_mask,
            "entries": [item.to_dict() for item in self.entries],
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.identity_payload(),
            "eligible_wearer_slots": list(self.eligible_wearer_slots),
            "identity_sha256": self.identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerInventoryFrontierGroupKey:
    """Exact domain inside which raw vectors are diagnostically comparable."""

    concrete_set_uid: str
    slot: str
    rarity: int | None
    eligibility: GcsimOptimizerInventoryEligibilityMask
    schema_version: int = GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        _require_trimmed_text(self.concrete_set_uid, "concrete_set_uid")
        if self.slot not in _SLOT_ORDER:
            raise GcsimOptimizerInventoryFrontierError(
                "frontier group slot is unsupported"
            )
        if self.rarity is not None and (
            isinstance(self.rarity, bool)
            or not isinstance(self.rarity, int)
            or self.rarity <= 0
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "frontier group rarity must be a positive integer or null"
            )
        if not isinstance(
            self.eligibility,
            GcsimOptimizerInventoryEligibilityMask,
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "frontier group eligibility must be typed"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.identity_payload())

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "concrete_set_uid": self.concrete_set_uid,
            "slot": self.slot,
            "rarity": self.rarity,
            "eligibility": self.eligibility.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.identity_payload(),
            "identity_sha256": self.identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerInventoryFrontierRow:
    """One retained or shadowed physical artifact with proof metadata."""

    artifact: GcsimOptimizerDenseArtifact
    group: GcsimOptimizerInventoryFrontierGroupKey
    skyline_depth: int | None
    disposition: str
    dominance_chain_artifact_ids: tuple[int, ...] = ()
    schema_version: int = GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.artifact, GcsimOptimizerDenseArtifact):
            raise GcsimOptimizerInventoryFrontierError(
                "frontier row artifact must be typed"
            )
        if not isinstance(
            self.group,
            GcsimOptimizerInventoryFrontierGroupKey,
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "frontier row group must be typed"
            )
        if (
            self.artifact.record.set_uid != self.group.concrete_set_uid
            or self.artifact.slot != self.group.slot
            or self.artifact.record.rarity != self.group.rarity
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "frontier row artifact differs from its comparison group"
            )
        if self.disposition not in _VALID_DISPOSITIONS:
            raise GcsimOptimizerInventoryFrontierError(
                "frontier row disposition is unsupported"
            )
        chain = tuple(self.dominance_chain_artifact_ids)
        if self.group.eligibility.eligible_count == 0:
            if (
                self.disposition
                != GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SHADOW_INELIGIBLE
                or self.skyline_depth is not None
                or chain
            ):
                raise GcsimOptimizerInventoryFrontierError(
                    "ineligible row must remain an unranked shadow row"
                )
        else:
            if (
                isinstance(self.skyline_depth, bool)
                or not isinstance(self.skyline_depth, int)
                or self.skyline_depth <= 0
            ):
                raise GcsimOptimizerInventoryFrontierError(
                    "eligible row must have a positive skyline depth"
                )
            if (
                len(chain) != self.skyline_depth
                or not chain
                or chain[-1] != self.artifact_id
                or len(set(chain)) != len(chain)
            ):
                raise GcsimOptimizerInventoryFrontierError(
                    "dominance chain must contain one physical row per depth"
                )
            if self.disposition == (
                GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SHADOW_INELIGIBLE
            ):
                raise GcsimOptimizerInventoryFrontierError(
                    "eligible row cannot use the ineligible disposition"
                )
        object.__setattr__(self, "dominance_chain_artifact_ids", chain)

    @property
    def artifact_id(self) -> int:
        return self.artifact.artifact_id

    @property
    def normalized_stat_vector(self) -> tuple[float, ...]:
        return self.artifact.stats

    @property
    def eligibility(self) -> GcsimOptimizerInventoryEligibilityMask:
        return self.group.eligibility

    @property
    def direct_dominator_artifact_id(self) -> int | None:
        if len(self.dominance_chain_artifact_ids) < 2:
            return None
        return self.dominance_chain_artifact_ids[-2]

    @property
    def retained(self) -> bool:
        return (
            self.disposition
            == GCSIM_OPTIMIZER_INVENTORY_FRONTIER_RETAINED
        )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.identity_payload())

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "artifact_bit_mask": self.artifact.bit_mask,
            "content_fingerprint": self.artifact.content_fingerprint,
            "group_identity_sha256": self.group.identity_sha256,
            "main_stat": {
                "key": self.artifact.main_key,
                "value": self.artifact.main_value,
            },
            "normalized_stat_vector": [
                [axis, value]
                for axis, value in zip(
                    GCSIM_OPTIMIZER_INVENTORY_STAT_AXES,
                    self.normalized_stat_vector,
                    strict=True,
                )
            ],
            "skyline_depth": self.skyline_depth,
            "disposition": self.disposition,
            "dominance_chain_artifact_ids": list(
                self.dominance_chain_artifact_ids
            ),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.identity_payload(),
            "group": self.group.to_dict(),
            "direct_dominator_artifact_id": (
                self.direct_dominator_artifact_id
            ),
            "identity_sha256": self.identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerInventoryFrontierGroupDiagnostic:
    """Deterministic layer membership for one comparison group."""

    group: GcsimOptimizerInventoryFrontierGroupKey
    physical_artifact_ids: tuple[int, ...]
    skyline_layers: tuple[tuple[int, tuple[int, ...]], ...]
    retained_artifact_ids: tuple[int, ...]
    shadow_artifact_ids: tuple[int, ...]
    schema_version: int = GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(
            self.group,
            GcsimOptimizerInventoryFrontierGroupKey,
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "group diagnostic key must be typed"
            )
        physical = _sorted_unique_ids(
            self.physical_artifact_ids,
            "physical_artifact_ids",
        )
        retained = _sorted_unique_ids(
            self.retained_artifact_ids,
            "retained_artifact_ids",
        )
        shadow = _sorted_unique_ids(
            self.shadow_artifact_ids,
            "shadow_artifact_ids",
        )
        if set(retained) & set(shadow) or set(retained) | set(shadow) != set(
            physical
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "group retained/shadow IDs must partition physical IDs"
            )
        layers = tuple(self.skyline_layers)
        expected_depths = tuple(range(1, len(layers) + 1))
        if tuple(depth for depth, _ids in layers) != expected_depths:
            raise GcsimOptimizerInventoryFrontierError(
                "group skyline layers must use contiguous depth order"
            )
        layer_ids: list[int] = []
        normalized_layers: list[tuple[int, tuple[int, ...]]] = []
        for depth, ids in layers:
            normalized = _sorted_unique_ids(ids, "skyline layer IDs")
            if not normalized:
                raise GcsimOptimizerInventoryFrontierError(
                    "skyline layer cannot be empty"
                )
            normalized_layers.append((depth, normalized))
            layer_ids.extend(normalized)
        if len(set(layer_ids)) != len(layer_ids):
            raise GcsimOptimizerInventoryFrontierError(
                "physical artifact cannot occur in multiple skyline layers"
            )
        if self.group.eligibility.eligible_count:
            if set(layer_ids) != set(physical):
                raise GcsimOptimizerInventoryFrontierError(
                    "eligible group layers must cover every physical row"
                )
        elif layers or retained:
            raise GcsimOptimizerInventoryFrontierError(
                "ineligible group cannot expose skyline layers or retained IDs"
            )
        object.__setattr__(self, "physical_artifact_ids", physical)
        object.__setattr__(self, "retained_artifact_ids", retained)
        object.__setattr__(self, "shadow_artifact_ids", shadow)
        object.__setattr__(self, "skyline_layers", tuple(normalized_layers))

    @property
    def max_skyline_depth(self) -> int:
        return self.skyline_layers[-1][0] if self.skyline_layers else 0

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.identity_payload())

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "group_identity_sha256": self.group.identity_sha256,
            "physical_artifact_ids": list(self.physical_artifact_ids),
            "skyline_layers": [
                {"depth": depth, "artifact_ids": list(ids)}
                for depth, ids in self.skyline_layers
            ],
            "retained_artifact_ids": list(self.retained_artifact_ids),
            "shadow_artifact_ids": list(self.shadow_artifact_ids),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.identity_payload(),
            "group": self.group.to_dict(),
            "max_skyline_depth": self.max_skyline_depth,
            "identity_sha256": self.identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerInventoryFrontierCounters:
    source_artifact_count: int
    dense_artifact_count: int
    dense_excluded_artifact_count: int
    eligible_artifact_count: int
    ineligible_artifact_count: int
    comparison_group_count: int
    retained_artifact_count: int
    shadow_artifact_count: int
    depth_exceeded_artifact_count: int
    identical_vector_class_count: int
    identical_vector_extra_copy_count: int
    max_observed_skyline_depth: int
    schema_version: int = GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        for field_name in (
            "source_artifact_count",
            "dense_artifact_count",
            "dense_excluded_artifact_count",
            "eligible_artifact_count",
            "ineligible_artifact_count",
            "comparison_group_count",
            "retained_artifact_count",
            "shadow_artifact_count",
            "depth_exceeded_artifact_count",
            "identical_vector_class_count",
            "identical_vector_extra_copy_count",
            "max_observed_skyline_depth",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise GcsimOptimizerInventoryFrontierError(
                    f"{field_name} must be a non-negative integer"
                )
        if (
            self.source_artifact_count
            != self.dense_artifact_count
            + self.dense_excluded_artifact_count
            or self.dense_artifact_count
            != self.eligible_artifact_count + self.ineligible_artifact_count
            or self.dense_artifact_count
            != self.retained_artifact_count + self.shadow_artifact_count
            or self.shadow_artifact_count != self.ineligible_artifact_count
            or self.depth_exceeded_artifact_count
            > self.eligible_artifact_count
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "inventory frontier counters are incoherent"
            )

    def to_dict(self) -> dict[str, int]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "source_artifact_count",
                "dense_artifact_count",
                "dense_excluded_artifact_count",
                "eligible_artifact_count",
                "ineligible_artifact_count",
                "comparison_group_count",
                "retained_artifact_count",
                "shadow_artifact_count",
                "depth_exceeded_artifact_count",
                "identical_vector_class_count",
                "identical_vector_extra_copy_count",
                "max_observed_skyline_depth",
            )
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerInventoryFrontierResult:
    """Complete eligible-retained/ineligible-shadow catalog partition."""

    run_input_sha256: str
    dense_catalog_sha256: str
    wearers: tuple[GcsimOptimizerWearerIdentity, ...]
    k_skyline_depth: int
    retained_rows: tuple[GcsimOptimizerInventoryFrontierRow, ...]
    shadow_reservoir: tuple[GcsimOptimizerInventoryFrontierRow, ...]
    group_diagnostics: tuple[
        GcsimOptimizerInventoryFrontierGroupDiagnostic, ...
    ]
    counters: GcsimOptimizerInventoryFrontierCounters
    schema_version: int = GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        _require_sha256(self.run_input_sha256, "run_input_sha256")
        _require_sha256(self.dense_catalog_sha256, "dense_catalog_sha256")
        wearers = _validate_wearers(self.wearers)
        if (
            isinstance(self.k_skyline_depth, bool)
            or not isinstance(self.k_skyline_depth, int)
            or self.k_skyline_depth <= 0
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "k_skyline_depth must be a positive integer"
            )
        retained = tuple(self.retained_rows)
        shadow = tuple(self.shadow_reservoir)
        diagnostics = tuple(self.group_diagnostics)
        if any(
            not isinstance(item, GcsimOptimizerInventoryFrontierRow)
            for item in retained + shadow
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "frontier result rows must be typed"
            )
        if tuple(item.artifact_id for item in retained) != tuple(
            sorted(item.artifact_id for item in retained)
        ) or tuple(item.artifact_id for item in shadow) != tuple(
            sorted(item.artifact_id for item in shadow)
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "frontier rows must use deterministic artifact-ID order"
            )
        retained_ids = {item.artifact_id for item in retained}
        shadow_ids = {item.artifact_id for item in shadow}
        if (
            len(retained_ids) != len(retained)
            or len(shadow_ids) != len(shadow)
            or retained_ids & shadow_ids
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "retained and shadow physical artifact IDs must be unique"
            )
        if any(not item.retained for item in retained) or any(
            item.retained for item in shadow
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "frontier row disposition differs from its result partition"
            )
        if any(
            not isinstance(
                item,
                GcsimOptimizerInventoryFrontierGroupDiagnostic,
            )
            for item in diagnostics
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "group diagnostics must be typed"
            )
        diagnostic_id_sequence = tuple(
            artifact_id
            for item in diagnostics
            for artifact_id in item.physical_artifact_ids
        )
        diagnostic_ids = set(diagnostic_id_sequence)
        if (
            len({item.group.identity_sha256 for item in diagnostics})
            != len(diagnostics)
            or len(diagnostic_id_sequence) != len(diagnostic_ids)
            or diagnostic_ids != retained_ids | shadow_ids
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "group diagnostics must uniquely cover every physical row"
            )
        row_by_id = {
            item.artifact_id: item for item in retained + shadow
        }
        for diagnostic in diagnostics:
            group_rows = tuple(
                row_by_id[artifact_id]
                for artifact_id in diagnostic.physical_artifact_ids
            )
            if (
                any(item.group != diagnostic.group for item in group_rows)
                or diagnostic.retained_artifact_ids
                != tuple(item.artifact_id for item in group_rows if item.retained)
                or diagnostic.shadow_artifact_ids
                != tuple(item.artifact_id for item in group_rows if not item.retained)
            ):
                raise GcsimOptimizerInventoryFrontierError(
                    "group diagnostic differs from its physical result rows"
                )
        if not isinstance(
            self.counters,
            GcsimOptimizerInventoryFrontierCounters,
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "frontier counters must be typed"
            )
        if (
            self.counters.dense_artifact_count != len(retained) + len(shadow)
            or self.counters.retained_artifact_count != len(retained)
            or self.counters.shadow_artifact_count != len(shadow)
            or self.counters.comparison_group_count != len(diagnostics)
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "frontier counters differ from result rows"
            )
        object.__setattr__(self, "wearers", wearers)
        object.__setattr__(self, "retained_rows", retained)
        object.__setattr__(self, "shadow_reservoir", shadow)
        object.__setattr__(self, "group_diagnostics", diagnostics)

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.identity_payload())

    @property
    def row_by_artifact_id(
        self,
    ) -> Mapping[int, GcsimOptimizerInventoryFrontierRow]:
        return MappingProxyType(
            {
                item.artifact_id: item
                for item in self.retained_rows + self.shadow_reservoir
            }
        )

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": GCSIM_OPTIMIZER_INVENTORY_FRONTIER_PLAN_ID,
            "plan_version": GCSIM_OPTIMIZER_INVENTORY_FRONTIER_PLAN_VERSION,
            "run_input_sha256": self.run_input_sha256,
            "dense_catalog_sha256": self.dense_catalog_sha256,
            "wearers": [item.to_dict() for item in self.wearers],
            "axis_order": list(GCSIM_OPTIMIZER_INVENTORY_STAT_AXES),
            "k_skyline_depth": self.k_skyline_depth,
            "retained_rows": [item.to_dict() for item in self.retained_rows],
            "shadow_reservoir": [
                item.to_dict() for item in self.shadow_reservoir
            ],
            "group_diagnostics": [
                item.to_dict() for item in self.group_diagnostics
            ],
            "counters": self.counters.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.identity_payload(),
            "identity_sha256": self.identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class _PreparedArtifact:
    artifact: GcsimOptimizerDenseArtifact
    group: GcsimOptimizerInventoryFrontierGroupKey


@dataclass(frozen=True, slots=True)
class _RankedArtifact:
    prepared: _PreparedArtifact
    skyline_depth: int
    dominance_chain_artifact_ids: tuple[int, ...]


def build_gcsim_optimizer_inventory_frontier(
    run_input: GcsimOptimizerRunInput,
    *,
    catalog: GcsimOptimizerDenseArtifactCatalog,
    wearers: Sequence[GcsimOptimizerWearerIdentity] | None = None,
    k_skyline_depth: int | None = None,
) -> GcsimOptimizerInventoryFrontierResult:
    """Build a no-prune catalog plus advisory physical ``k``-skyline ranks."""

    if not isinstance(run_input, GcsimOptimizerRunInput):
        raise GcsimOptimizerInventoryFrontierError(
            "run_input must be typed"
        )
    if not isinstance(catalog, GcsimOptimizerDenseArtifactCatalog):
        raise GcsimOptimizerInventoryFrontierError(
            "catalog must be a typed dense artifact catalog"
        )
    source_wearers = run_input.request.source_simulation.wearers
    selected_wearers = _validate_wearers(
        source_wearers if wearers is None else wearers
    )
    if selected_wearers != source_wearers:
        raise GcsimOptimizerInventoryFrontierError(
            "frontier wearers must exactly match the run-input source team"
        )
    selected_depth = (
        len(selected_wearers)
        if k_skyline_depth is None
        else k_skyline_depth
    )
    if (
        isinstance(selected_depth, bool)
        or not isinstance(selected_depth, int)
        or selected_depth <= 0
    ):
        raise GcsimOptimizerInventoryFrontierError(
            "k_skyline_depth must be a positive integer"
        )
    _validate_dense_catalog(run_input, catalog)

    override_by_wearer = {
        item.wearer: item for item in run_input.request.four_star_overrides
    }
    prepared_by_group: dict[
        GcsimOptimizerInventoryFrontierGroupKey,
        list[_PreparedArtifact],
    ] = defaultdict(list)
    for artifact in catalog.artifacts:
        entries: list[GcsimOptimizerInventoryEligibilityEntry] = []
        for wearer in selected_wearers:
            eligibility = evaluate_gcsim_optimizer_artifact_eligibility(
                artifact.record,
                wearer=wearer,
                four_star_override=override_by_wearer.get(wearer),
                # Set-authorized 4-star pieces are conditional on a package
                # containing this concrete set.  The returned reason code is
                # retained in the comparison signature, so that conditional
                # admission cannot collapse into artifact-ID admission.
                package_set_uids=(artifact.record.set_uid,),
            )
            if not eligibility.eligible:
                admission_kind = GCSIM_OPTIMIZER_INVENTORY_ADMISSION_INELIGIBLE
                required_active_set_uid = ""
            elif eligibility.reason == "explicit_four_star_selected_set":
                admission_kind = (
                    GCSIM_OPTIMIZER_INVENTORY_ADMISSION_REQUIRES_ACTIVE_SET
                )
                required_active_set_uid = artifact.record.set_uid
            else:
                admission_kind = (
                    GCSIM_OPTIMIZER_INVENTORY_ADMISSION_UNCONDITIONAL
                )
                required_active_set_uid = ""
            entries.append(
                GcsimOptimizerInventoryEligibilityEntry(
                    wearer=wearer,
                    eligible=eligibility.eligible,
                    reason_code=eligibility.reason,
                    admission_kind=admission_kind,
                    required_active_set_uid=required_active_set_uid,
                )
            )
        mask = GcsimOptimizerInventoryEligibilityMask(tuple(entries))
        group = GcsimOptimizerInventoryFrontierGroupKey(
            concrete_set_uid=artifact.record.set_uid,
            slot=artifact.slot,
            rarity=artifact.record.rarity,
            eligibility=mask,
        )
        prepared_by_group[group].append(_PreparedArtifact(artifact, group))

    retained_rows: list[GcsimOptimizerInventoryFrontierRow] = []
    shadow_rows: list[GcsimOptimizerInventoryFrontierRow] = []
    diagnostics: list[GcsimOptimizerInventoryFrontierGroupDiagnostic] = []
    for group in sorted(prepared_by_group, key=_group_sort_key):
        prepared = tuple(
            sorted(
                prepared_by_group[group],
                key=lambda item: item.artifact.artifact_id,
            )
        )
        group_rows: list[GcsimOptimizerInventoryFrontierRow] = []
        if group.eligibility.eligible_count == 0:
            for item in prepared:
                group_rows.append(
                    GcsimOptimizerInventoryFrontierRow(
                        artifact=item.artifact,
                        group=group,
                        skyline_depth=None,
                        disposition=(
                            GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SHADOW_INELIGIBLE
                        ),
                    )
                )
        else:
            for ranked in _rank_componentwise_skyline(prepared):
                group_rows.append(
                    GcsimOptimizerInventoryFrontierRow(
                        artifact=ranked.prepared.artifact,
                        group=group,
                        skyline_depth=ranked.skyline_depth,
                        disposition=GCSIM_OPTIMIZER_INVENTORY_FRONTIER_RETAINED,
                        dominance_chain_artifact_ids=(
                            ranked.dominance_chain_artifact_ids
                        ),
                    )
                )
        group_rows.sort(key=lambda item: item.artifact_id)
        retained_rows.extend(item for item in group_rows if item.retained)
        shadow_rows.extend(item for item in group_rows if not item.retained)
        layer_ids: dict[int, list[int]] = defaultdict(list)
        for item in group_rows:
            if item.skyline_depth is not None:
                layer_ids[item.skyline_depth].append(item.artifact_id)
        diagnostics.append(
            GcsimOptimizerInventoryFrontierGroupDiagnostic(
                group=group,
                physical_artifact_ids=tuple(
                    item.artifact_id for item in group_rows
                ),
                skyline_layers=tuple(
                    (depth, tuple(sorted(ids)))
                    for depth, ids in sorted(layer_ids.items())
                ),
                retained_artifact_ids=tuple(
                    item.artifact_id for item in group_rows if item.retained
                ),
                shadow_artifact_ids=tuple(
                    item.artifact_id
                    for item in group_rows
                    if not item.retained
                ),
            )
        )

    retained_rows.sort(key=lambda item: item.artifact_id)
    shadow_rows.sort(key=lambda item: item.artifact_id)
    duplicate_counts = Counter(
        (item.group.identity_sha256, item.normalized_stat_vector)
        for item in retained_rows + shadow_rows
        if item.eligibility.eligible_count
    )
    counters = GcsimOptimizerInventoryFrontierCounters(
        source_artifact_count=catalog.source_artifact_count,
        dense_artifact_count=len(catalog.artifacts),
        dense_excluded_artifact_count=(
            catalog.source_artifact_count - len(catalog.artifacts)
        ),
        eligible_artifact_count=sum(
            item.eligibility.eligible_count > 0
            for item in retained_rows + shadow_rows
        ),
        ineligible_artifact_count=sum(
            item.eligibility.eligible_count == 0
            for item in retained_rows + shadow_rows
        ),
        comparison_group_count=len(diagnostics),
        retained_artifact_count=len(retained_rows),
        shadow_artifact_count=len(shadow_rows),
        depth_exceeded_artifact_count=sum(
            item.skyline_depth is not None
            and item.skyline_depth > selected_depth
            for item in retained_rows
        ),
        identical_vector_class_count=sum(
            count > 1 for count in duplicate_counts.values()
        ),
        identical_vector_extra_copy_count=sum(
            count - 1 for count in duplicate_counts.values() if count > 1
        ),
        max_observed_skyline_depth=max(
            (
                item.skyline_depth or 0
                for item in retained_rows + shadow_rows
            ),
            default=0,
        ),
    )
    return GcsimOptimizerInventoryFrontierResult(
        run_input_sha256=run_input.run_input_sha256,
        dense_catalog_sha256=catalog.identity_sha256,
        wearers=selected_wearers,
        k_skyline_depth=selected_depth,
        retained_rows=tuple(retained_rows),
        shadow_reservoir=tuple(shadow_rows),
        group_diagnostics=tuple(diagnostics),
        counters=counters,
    )


def _rank_componentwise_skyline(
    rows: Sequence[_PreparedArtifact],
) -> tuple[_RankedArtifact, ...]:
    """Assign exact Pareto-peeling depth without scalarization."""

    # If left strictly dominates right, descending lexicographic vector order
    # necessarily places left first.  Dynamic programming over that order gives
    # the same depth as repeated nondominated-front peeling in O(n^2 * axes).
    ordered = tuple(
        sorted(
            rows,
            key=lambda item: (
                tuple(-value for value in item.artifact.stats),
                item.artifact.artifact_id,
            ),
        )
    )
    ranked: list[_RankedArtifact] = []
    for item in ordered:
        dominators = tuple(
            other
            for other in ranked
            if _componentwise_strictly_dominates(
                other.prepared.artifact.stats,
                item.artifact.stats,
            )
        )
        if not dominators:
            ranked.append(
                _RankedArtifact(
                    prepared=item,
                    skyline_depth=1,
                    dominance_chain_artifact_ids=(item.artifact.artifact_id,),
                )
            )
            continue
        predecessor = min(
            dominators,
            key=lambda other: (
                -other.skyline_depth,
                other.prepared.artifact.artifact_id,
            ),
        )
        ranked.append(
            _RankedArtifact(
                prepared=item,
                skyline_depth=predecessor.skyline_depth + 1,
                dominance_chain_artifact_ids=(
                    predecessor.dominance_chain_artifact_ids
                    + (item.artifact.artifact_id,)
                ),
            )
        )
    return tuple(
        sorted(ranked, key=lambda item: item.prepared.artifact.artifact_id)
    )


def _componentwise_strictly_dominates(
    left: Sequence[float],
    right: Sequence[float],
) -> bool:
    """Return strict full-vector dominance; exact copies never dominate."""

    if len(left) != len(GCSIM_OPTIMIZER_INVENTORY_STAT_AXES) or len(
        right
    ) != len(GCSIM_OPTIMIZER_INVENTORY_STAT_AXES):
        raise GcsimOptimizerInventoryFrontierError(
            "dominance vectors must cover the full normalized axis order"
        )
    no_worse = True
    strictly_better = False
    for left_value, right_value in zip(left, right, strict=True):
        if left_value < right_value:
            no_worse = False
            break
        if left_value > right_value:
            strictly_better = True
    return no_worse and strictly_better


def _validate_dense_catalog(
    run_input: GcsimOptimizerRunInput,
    catalog: GcsimOptimizerDenseArtifactCatalog,
) -> None:
    if catalog.source_artifact_count != len(
        run_input.artifact_database.artifacts
    ):
        raise GcsimOptimizerInventoryFrontierError(
            "dense catalog source count differs from run input"
        )
    excluded_count = 0
    for reason, count in catalog.excluded_counts:
        _require_trimmed_text(reason, "dense exclusion reason")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise GcsimOptimizerInventoryFrontierError(
                "dense exclusion counts must be non-negative integers"
            )
        excluded_count += count
    if excluded_count != catalog.source_artifact_count - len(catalog.artifacts):
        raise GcsimOptimizerInventoryFrontierError(
            "dense exclusion counts do not cover omitted source artifacts"
        )
    seen_bit_masks: set[int] = set()
    for artifact in catalog.artifacts:
        source_record = run_input.artifact_by_id(artifact.artifact_id)
        if source_record is None or source_record != artifact.record:
            raise GcsimOptimizerInventoryFrontierError(
                "dense artifact record differs from the run-input database"
            )
        if (
            artifact.bit_mask <= 0
            or artifact.bit_mask & (artifact.bit_mask - 1)
            or artifact.bit_mask in seen_bit_masks
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "dense physical artifact bit masks must be unique powers of two"
            )
        seen_bit_masks.add(artifact.bit_mask)
        _validate_dense_vector(artifact.stats, "stats")
        _validate_dense_vector(artifact.substats, "substats")
        if artifact.main_key not in GCSIM_OPTIMIZER_INVENTORY_STAT_AXES:
            raise GcsimOptimizerInventoryFrontierError(
                "dense main key is outside the full normalized stat space"
            )
        if (
            not isfinite(artifact.main_value)
            or artifact.main_value < 0
        ):
            raise GcsimOptimizerInventoryFrontierError(
                "dense main value must be finite and non-negative"
            )
        _require_sha256(
            artifact.content_fingerprint,
            "dense content_fingerprint",
        )


def _validate_dense_vector(values: Sequence[float], field_name: str) -> None:
    if len(values) != len(GCSIM_OPTIMIZER_INVENTORY_STAT_AXES):
        raise GcsimOptimizerInventoryFrontierError(
            f"dense {field_name} must cover the full normalized stat space"
        )
    if any(not isfinite(value) or value < 0 for value in values):
        raise GcsimOptimizerInventoryFrontierError(
            f"dense {field_name} values must be finite and non-negative"
        )


def _validate_wearers(
    values: Sequence[GcsimOptimizerWearerIdentity],
) -> tuple[GcsimOptimizerWearerIdentity, ...]:
    wearers = tuple(values)
    if len(wearers) != 4 or any(
        not isinstance(item, GcsimOptimizerWearerIdentity) for item in wearers
    ):
        raise GcsimOptimizerInventoryFrontierError(
            "inventory frontier requires exactly four typed wearers"
        )
    if tuple(item.team_slot for item in wearers) != (1, 2, 3, 4):
        raise GcsimOptimizerInventoryFrontierError(
            "inventory frontier wearers must use deterministic team-slot order"
        )
    if len(set(wearers)) != len(wearers):
        raise GcsimOptimizerInventoryFrontierError(
            "inventory frontier wearer identities must be unique"
        )
    return wearers


def _group_sort_key(
    group: GcsimOptimizerInventoryFrontierGroupKey,
) -> tuple[object, ...]:
    return (
        group.concrete_set_uid,
        _SLOT_ORDER[group.slot],
        -1 if group.rarity is None else group.rarity,
        group.eligibility.bit_mask,
        group.eligibility.comparison_signature,
    )


def _sorted_unique_ids(
    values: Sequence[int],
    field_name: str,
) -> tuple[int, ...]:
    rows = tuple(values)
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in rows
    ):
        raise GcsimOptimizerInventoryFrontierError(
            f"{field_name} must contain positive integer IDs"
        )
    ordered = tuple(sorted(rows))
    if len(set(ordered)) != len(ordered):
        raise GcsimOptimizerInventoryFrontierError(
            f"{field_name} must contain unique IDs"
        )
    return ordered


def _require_schema(value: int) -> None:
    if value != GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SCHEMA_VERSION:
        raise GcsimOptimizerInventoryFrontierError(
            "unsupported inventory frontier schema"
        )


def _require_trimmed_text(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
    ):
        raise GcsimOptimizerInventoryFrontierError(
            f"{field_name} must be non-empty trimmed text"
        )


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GcsimOptimizerInventoryFrontierError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "GCSIM_OPTIMIZER_INVENTORY_ADMISSION_INELIGIBLE",
    "GCSIM_OPTIMIZER_INVENTORY_ADMISSION_REQUIRES_ACTIVE_SET",
    "GCSIM_OPTIMIZER_INVENTORY_ADMISSION_UNCONDITIONAL",
    "GCSIM_OPTIMIZER_INVENTORY_FRONTIER_PLAN_ID",
    "GCSIM_OPTIMIZER_INVENTORY_FRONTIER_PLAN_VERSION",
    "GCSIM_OPTIMIZER_INVENTORY_FRONTIER_RETAINED",
    "GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SCHEMA_VERSION",
    "GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SHADOW_INELIGIBLE",
    "GCSIM_OPTIMIZER_INVENTORY_STAT_AXES",
    "GcsimOptimizerInventoryEligibilityEntry",
    "GcsimOptimizerInventoryEligibilityMask",
    "GcsimOptimizerInventoryFrontierCounters",
    "GcsimOptimizerInventoryFrontierError",
    "GcsimOptimizerInventoryFrontierGroupDiagnostic",
    "GcsimOptimizerInventoryFrontierGroupKey",
    "GcsimOptimizerInventoryFrontierResult",
    "GcsimOptimizerInventoryFrontierRow",
    "build_gcsim_optimizer_inventory_frontier",
]
