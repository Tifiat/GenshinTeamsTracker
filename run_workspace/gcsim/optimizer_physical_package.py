"""Shadow artifact-first derivation of a strict package from five physical IDs.

This module has no service/UI integration.  It converts one already chosen
five-slot physical assignment into the existing product-contract target, or a
typed fail-closed rejection.  Set packages are outputs of the physical counts;
they are never supplied as search targets here.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from .artifact_set_catalog import GcsimArtifactSetCapability
from .optimizer_artifact_database import (
    GcsimOptimizerArtifactEligibility,
    GcsimOptimizerArtifactRecord,
    evaluate_gcsim_optimizer_artifact_eligibility,
)
from .optimizer_artifact_materializer import (
    validate_gcsim_optimizer_set_parameters,
    validate_gcsim_optimizer_target_set_capability,
)
from .optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerFourStarEligibilityOverride,
    GcsimOptimizerSetReference,
    GcsimOptimizerTargetPackage,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerTarget,
    GcsimTwoPlusTwoTargetPackage,
)


class GcsimOptimizerPhysicalPackageRejectionReason(str, Enum):
    ARTIFACT_COUNT_INVALID = "artifact_count_invalid"
    ARTIFACT_ID_DUPLICATED = "artifact_id_duplicated"
    ARTIFACT_SLOT_COVERAGE_INVALID = "artifact_slot_coverage_invalid"
    SET_COUNT_SHAPE_UNSUPPORTED = "set_count_shape_unsupported"
    TWO_PLUS_TWO_NOT_ENABLED = "two_plus_two_not_enabled"
    SET_REFERENCE_MISSING = "set_reference_missing"
    SET_REFERENCE_AMBIGUOUS = "set_reference_ambiguous"
    TWO_PLUS_TWO_GCSIM_KEY_COLLISION = "two_plus_two_gcsim_key_collision"
    SET_CAPABILITY_AMBIGUOUS = "set_capability_ambiguous"
    SET_CAPABILITY_UNAVAILABLE = "set_capability_unavailable"
    FOUR_PIECE_UNMODELED = "four_piece_unmodeled"
    TWO_PIECE_UNMODELED = "two_piece_unmodeled"
    ARTIFACT_INELIGIBLE = "artifact_ineligible"
    ACTIVE_SET_MAPPING_INVALID = "active_set_mapping_invalid"
    ACTIVE_SET_REFERENCE_MISMATCH = "active_set_reference_mismatch"
    SET_PARAMETER_KEY_INVALID = "set_parameter_key_invalid"
    SET_PARAMETER_VALUE_INVALID = "set_parameter_value_invalid"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerPhysicalPackageRejection:
    reason: GcsimOptimizerPhysicalPackageRejectionReason
    message: str
    artifact_ids: tuple[int, ...]
    set_counts: tuple[tuple[str, int], ...]
    set_uid: str = ""
    materializer_code: str = ""
    eligibility: GcsimOptimizerArtifactEligibility | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.reason,
            GcsimOptimizerPhysicalPackageRejectionReason,
        ):
            raise TypeError("physical package rejection reason must be typed")
        if not self.message:
            raise ValueError("physical package rejection message is required")
        artifact_ids = tuple(self.artifact_ids)
        set_counts = tuple(self.set_counts)
        if (
            artifact_ids != tuple(sorted(artifact_ids))
            or any(
                isinstance(item, bool) or not isinstance(item, int) or item <= 0
                for item in artifact_ids
            )
        ):
            raise ValueError("rejection artifact_ids must be sorted positive integers")
        if (
            set_counts != tuple(sorted(set_counts))
            or len({set_uid for set_uid, _count in set_counts}) != len(set_counts)
            or any(
                not isinstance(set_uid, str)
                or not set_uid
                or set_uid != set_uid.strip()
                or isinstance(count, bool)
                or not isinstance(count, int)
                or count <= 0
                for set_uid, count in set_counts
            )
        ):
            raise ValueError("rejection set_counts must be sorted unique positive rows")
        if self.eligibility is not None and (
            not isinstance(self.eligibility, GcsimOptimizerArtifactEligibility)
            or self.eligibility.artifact_id not in artifact_ids
            or self.eligibility.eligible
        ):
            raise ValueError("rejection eligibility must identify a rejected artifact")
        object.__setattr__(self, "artifact_ids", artifact_ids)
        object.__setattr__(self, "set_counts", set_counts)

    def to_dict(self) -> dict[str, object]:
        return {
            "reason": self.reason.value,
            "message": self.message,
            "artifact_ids": list(self.artifact_ids),
            "set_counts": dict(self.set_counts),
            "set_uid": self.set_uid,
            "materializer_code": self.materializer_code,
            "eligibility": (
                None if self.eligibility is None else self.eligibility.to_dict()
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerPhysicalPackageDerivationResult:
    ready: bool
    target: GcsimOptimizerWearerTarget | None
    rejection: GcsimOptimizerPhysicalPackageRejection | None
    artifact_ids: tuple[int, ...]
    set_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if self.ready != (self.target is not None and self.rejection is None):
            raise ValueError("physical package derivation result is incoherent")
        if not self.ready and self.rejection is None:
            raise ValueError("failed physical package derivation needs a rejection")
        artifact_ids = tuple(self.artifact_ids)
        set_counts = tuple(self.set_counts)
        if artifact_ids != tuple(sorted(artifact_ids)) or set_counts != tuple(
            sorted(set_counts)
        ):
            raise ValueError("physical package evidence must be deterministic")
        if self.ready:
            if (
                not isinstance(self.target, GcsimOptimizerWearerTarget)
                or len(artifact_ids) != len(GCSIM_OPTIMIZER_ARTIFACT_SLOTS)
                or len(set(artifact_ids)) != len(artifact_ids)
                or sum(count for _set_uid, count in set_counts)
                != len(GCSIM_OPTIMIZER_ARTIFACT_SLOTS)
            ):
                raise ValueError("ready physical package evidence is incomplete")
        else:
            assert self.rejection is not None
            if (
                self.rejection.artifact_ids != artifact_ids
                or self.rejection.set_counts != set_counts
            ):
                raise ValueError("rejection evidence differs from result evidence")
        object.__setattr__(self, "artifact_ids", artifact_ids)
        object.__setattr__(self, "set_counts", set_counts)

    @property
    def package(self) -> GcsimOptimizerTargetPackage | None:
        return None if self.target is None else self.target.package

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "target": None if self.target is None else self.target.to_dict(),
            "rejection": (
                None if self.rejection is None else self.rejection.to_dict()
            ),
            "artifact_ids": list(self.artifact_ids),
            "set_counts": dict(self.set_counts),
        }


def derive_gcsim_optimizer_target_from_physical_artifacts(
    *,
    wearer: GcsimOptimizerWearerIdentity,
    artifacts: Sequence[GcsimOptimizerArtifactRecord],
    set_refs: Sequence[GcsimOptimizerSetReference],
    set_capabilities: Sequence[GcsimArtifactSetCapability],
    include_2p2p: bool,
    four_star_override: GcsimOptimizerFourStarEligibilityOverride | None = None,
) -> GcsimOptimizerPhysicalPackageDerivationResult:
    """Derive one strict 4p/2p+2p target solely from five selected artifacts."""

    if not isinstance(wearer, GcsimOptimizerWearerIdentity):
        raise TypeError("wearer must be typed")
    if not isinstance(include_2p2p, bool):
        raise TypeError("include_2p2p must be boolean")
    if four_star_override is not None and not isinstance(
        four_star_override,
        GcsimOptimizerFourStarEligibilityOverride,
    ):
        raise TypeError("four_star_override must be typed or None")

    physical = tuple(artifacts)
    if any(not isinstance(item, GcsimOptimizerArtifactRecord) for item in physical):
        raise TypeError("artifacts must contain typed physical artifact records")
    refs = tuple(set_refs)
    if any(not isinstance(item, GcsimOptimizerSetReference) for item in refs):
        raise TypeError("set_refs must contain typed set references")
    capabilities = tuple(set_capabilities)
    if any(
        not isinstance(item, GcsimArtifactSetCapability)
        for item in capabilities
    ):
        raise TypeError("set_capabilities must contain typed capabilities")

    artifact_ids = tuple(sorted(item.artifact_id for item in physical))
    if len(physical) != len(GCSIM_OPTIMIZER_ARTIFACT_SLOTS):
        return _rejected(
            GcsimOptimizerPhysicalPackageRejectionReason.ARTIFACT_COUNT_INVALID,
            "A physical wearer assignment must contain exactly five artifacts.",
            artifact_ids=artifact_ids,
        )
    if len(set(artifact_ids)) != len(artifact_ids):
        return _rejected(
            GcsimOptimizerPhysicalPackageRejectionReason.ARTIFACT_ID_DUPLICATED,
            "A physical artifact ID cannot fill more than one wearer slot.",
            artifact_ids=artifact_ids,
        )
    slot_counts = Counter(item.position_key for item in physical)
    if slot_counts != Counter(GCSIM_OPTIMIZER_ARTIFACT_SLOTS):
        return _rejected(
            GcsimOptimizerPhysicalPackageRejectionReason.ARTIFACT_SLOT_COVERAGE_INVALID,
            "The five physical artifacts must cover every canonical slot once.",
            artifact_ids=artifact_ids,
        )

    physical = tuple(
        sorted(
            physical,
            key=lambda item: GCSIM_OPTIMIZER_ARTIFACT_SLOTS.index(
                item.position_key
            ),
        )
    )
    counts = Counter(item.set_uid for item in physical)
    set_counts = tuple(sorted(counts.items()))
    four_piece_uids = tuple(
        sorted(set_uid for set_uid, count in counts.items() if count >= 4)
    )
    active_two_piece_uids = tuple(
        sorted(set_uid for set_uid, count in counts.items() if count >= 2)
    )
    if len(four_piece_uids) == 1:
        package_uids = four_piece_uids
        package_kind = "4p"
    elif len(active_two_piece_uids) == 2:
        package_uids = active_two_piece_uids
        package_kind = "2p2p"
        if not include_2p2p:
            return _rejected(
                GcsimOptimizerPhysicalPackageRejectionReason.TWO_PLUS_TWO_NOT_ENABLED,
                "The physical assignment derives a 2p+2p package, but it is disabled.",
                artifact_ids=artifact_ids,
                set_counts=set_counts,
            )
    else:
        return _rejected(
            GcsimOptimizerPhysicalPackageRejectionReason.SET_COUNT_SHAPE_UNSUPPORTED,
            "Physical set counts do not form a supported 4p or 2p+2p package.",
            artifact_ids=artifact_ids,
            set_counts=set_counts,
        )

    selected_refs: list[GcsimOptimizerSetReference] = []
    for set_uid in package_uids:
        matching_refs = tuple(item for item in refs if item.set_uid == set_uid)
        if not matching_refs:
            return _rejected(
                GcsimOptimizerPhysicalPackageRejectionReason.SET_REFERENCE_MISSING,
                "An active physical set has no modeled set reference.",
                artifact_ids=artifact_ids,
                set_counts=set_counts,
                set_uid=set_uid,
            )
        if len(matching_refs) != 1:
            return _rejected(
                GcsimOptimizerPhysicalPackageRejectionReason.SET_REFERENCE_AMBIGUOUS,
                "An active physical set has multiple concrete set references.",
                artifact_ids=artifact_ids,
                set_counts=set_counts,
                set_uid=set_uid,
            )
        selected_refs.append(matching_refs[0])

    if package_kind == "4p":
        package: GcsimOptimizerTargetPackage = GcsimFourPieceTargetPackage(
            selected_refs[0]
        )
    else:
        if (
            selected_refs[0].gcsim_set_key.casefold()
            == selected_refs[1].gcsim_set_key.casefold()
        ):
            return _rejected(
                (
                    GcsimOptimizerPhysicalPackageRejectionReason
                    .TWO_PLUS_TWO_GCSIM_KEY_COLLISION
                ),
                (
                    "Different concrete set UIDs mapping to one GCSIM key "
                    "cannot form 2p+2p."
                ),
                artifact_ids=artifact_ids,
                set_counts=set_counts,
            )
        package = GcsimTwoPlusTwoTargetPackage(
            selected_refs[0],
            selected_refs[1],
        )
    target = GcsimOptimizerWearerTarget(wearer=wearer, package=package)

    for set_ref in selected_refs:
        matching_capabilities = tuple(
            item
            for item in capabilities
            if item.key.casefold() == set_ref.gcsim_set_key.casefold()
        )
        if len(matching_capabilities) > 1:
            return _rejected(
                GcsimOptimizerPhysicalPackageRejectionReason.SET_CAPABILITY_AMBIGUOUS,
                "A modeled GCSIM set key has multiple frozen capabilities.",
                artifact_ids=artifact_ids,
                set_counts=set_counts,
                set_uid=set_ref.set_uid,
            )
        capability = (
            None if not matching_capabilities else matching_capabilities[0]
        )
        capability_validation = validate_gcsim_optimizer_target_set_capability(
            package,
            capability,
        )
        if not capability_validation.ready:
            return _rejected(
                _capability_rejection_reason(capability_validation.code),
                capability_validation.message,
                artifact_ids=artifact_ids,
                set_counts=set_counts,
                set_uid=set_ref.set_uid,
                materializer_code=capability_validation.code,
            )

    for artifact in physical:
        eligibility = evaluate_gcsim_optimizer_artifact_eligibility(
            artifact,
            wearer=wearer,
            four_star_override=four_star_override,
            package_set_uids=package_uids,
        )
        if not eligibility.eligible:
            return _rejected(
                GcsimOptimizerPhysicalPackageRejectionReason.ARTIFACT_INELIGIBLE,
                "A selected physical artifact is not eligible for this wearer/package.",
                artifact_ids=artifact_ids,
                set_counts=set_counts,
                set_uid=artifact.set_uid,
                materializer_code=eligibility.reason,
                eligibility=eligibility,
            )

    selected_ref_by_uid = {item.set_uid: item for item in selected_refs}
    for set_uid in package_uids:
        pieces = tuple(item for item in physical if item.set_uid == set_uid)
        mapped_keys = {
            item.gcsim_set_key for item in pieces if item.gcsim_set_key
        }
        if (
            any(item.set_mapping_status != "ready" for item in pieces)
            or len(mapped_keys) != 1
        ):
            return _rejected(
                GcsimOptimizerPhysicalPackageRejectionReason.ACTIVE_SET_MAPPING_INVALID,
                "Every active physical set piece must share one validated GCSIM key.",
                artifact_ids=artifact_ids,
                set_counts=set_counts,
                set_uid=set_uid,
                materializer_code="active_set_mapping_invalid",
            )
        set_ref = selected_ref_by_uid[set_uid]
        if set_ref.gcsim_set_key not in mapped_keys:
            return _rejected(
                (
                    GcsimOptimizerPhysicalPackageRejectionReason
                    .ACTIVE_SET_REFERENCE_MISMATCH
                ),
                "The modeled set reference differs from the physical set mapping.",
                artifact_ids=artifact_ids,
                set_counts=set_counts,
                set_uid=set_uid,
                materializer_code="active_set_reference_mismatch",
            )

    capability_by_key = {
        item.key.casefold(): item for item in capabilities
    }
    for set_ref in selected_refs:
        parameter_validation = validate_gcsim_optimizer_set_parameters(
            set_ref,
            capability_by_key[set_ref.gcsim_set_key.casefold()],
        )
        if parameter_validation.issues:
            issue = parameter_validation.issues[0]
            return _rejected(
                _parameter_rejection_reason(issue.code),
                issue.message,
                artifact_ids=artifact_ids,
                set_counts=set_counts,
                set_uid=set_ref.set_uid,
                materializer_code=issue.code,
            )

    return GcsimOptimizerPhysicalPackageDerivationResult(
        ready=True,
        target=target,
        rejection=None,
        artifact_ids=artifact_ids,
        set_counts=set_counts,
    )


def _capability_rejection_reason(
    materializer_code: str,
) -> GcsimOptimizerPhysicalPackageRejectionReason:
    return {
        "target_set_unmapped": (
            GcsimOptimizerPhysicalPackageRejectionReason.SET_CAPABILITY_UNAVAILABLE
        ),
        "target_four_piece_unmodeled": (
            GcsimOptimizerPhysicalPackageRejectionReason.FOUR_PIECE_UNMODELED
        ),
        "target_two_piece_unmodeled": (
            GcsimOptimizerPhysicalPackageRejectionReason.TWO_PIECE_UNMODELED
        ),
    }[materializer_code]


def _parameter_rejection_reason(
    materializer_code: str,
) -> GcsimOptimizerPhysicalPackageRejectionReason:
    return {
        "set_parameter_key_invalid": (
            GcsimOptimizerPhysicalPackageRejectionReason.SET_PARAMETER_KEY_INVALID
        ),
        "set_parameter_value_invalid": (
            GcsimOptimizerPhysicalPackageRejectionReason.SET_PARAMETER_VALUE_INVALID
        ),
    }[materializer_code]


def _rejected(
    reason: GcsimOptimizerPhysicalPackageRejectionReason,
    message: str,
    *,
    artifact_ids: tuple[int, ...],
    set_counts: tuple[tuple[str, int], ...] = (),
    set_uid: str = "",
    materializer_code: str = "",
    eligibility: GcsimOptimizerArtifactEligibility | None = None,
) -> GcsimOptimizerPhysicalPackageDerivationResult:
    rejection = GcsimOptimizerPhysicalPackageRejection(
        reason=reason,
        message=message,
        artifact_ids=artifact_ids,
        set_counts=set_counts,
        set_uid=set_uid,
        materializer_code=materializer_code,
        eligibility=eligibility,
    )
    return GcsimOptimizerPhysicalPackageDerivationResult(
        ready=False,
        target=None,
        rejection=rejection,
        artifact_ids=artifact_ids,
        set_counts=set_counts,
    )


__all__ = [
    "GcsimOptimizerPhysicalPackageDerivationResult",
    "GcsimOptimizerPhysicalPackageRejection",
    "GcsimOptimizerPhysicalPackageRejectionReason",
    "derive_gcsim_optimizer_target_from_physical_artifacts",
]
