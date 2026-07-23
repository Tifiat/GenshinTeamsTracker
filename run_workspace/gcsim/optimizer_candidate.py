"""Validated composition of set and main-stat optimizer candidate configs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .artifact_set_catalog import GcsimArtifactSetCatalog
from .optimizer_config import (
    GcsimFiveStarMainStatLayout,
    GcsimOptimizerConfigRenderResult,
    render_gcsim_four_star_set_optimizer_config,
    render_gcsim_substat_optimizer_config,
)
from .optimizer_set_config import (
    GcsimOptimizerSetConfigResult,
    render_gcsim_four_piece_set_overrides,
)


OPTIMIZER_CANDIDATE_READY = "ready"
OPTIMIZER_CANDIDATE_SET_CONFIG_INVALID = "set_config_invalid"
OPTIMIZER_CANDIDATE_MAIN_STATS_INVALID = "main_stats_invalid"
OPTIMIZER_CANDIDATE_UNKNOWN_SET = "unknown_set"
OPTIMIZER_CANDIDATE_UNMODELED_4P = "unmodeled_four_piece"
OPTIMIZER_CANDIDATE_RARITY_MISMATCH = "set_rarity_mismatch"
OPTIMIZER_CANDIDATE_OFFPIECE_MISMATCH = "offpiece_mismatch"
OPTIMIZER_CANDIDATE_SET_PARAMETERS_REQUIRED = "set_parameters_required"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerCandidateIssue:
    status: str
    field: str
    message: str = ""
    character_key: str = ""
    set_key: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "status": self.status,
            "field": self.field,
            "message": self.message,
            "character_key": self.character_key,
            "set_key": self.set_key,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerCandidateConfigResult:
    status: str
    ready: bool
    config_text: str = ""
    set_config: GcsimOptimizerSetConfigResult | None = None
    main_stats_config: GcsimOptimizerConfigRenderResult | None = None
    issues: tuple[GcsimOptimizerCandidateIssue, ...] = ()
    source_notes: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "config_text": self.config_text,
            "set_config": None if self.set_config is None else self.set_config.to_dict(),
            "main_stats_config": (
                None if self.main_stats_config is None else self.main_stats_config.to_dict()
            ),
            "issues": [issue.to_dict() for issue in self.issues],
            "source_notes": dict(self.source_notes),
        }


def prepare_gcsim_four_piece_optimizer_candidate(
    config_text: str,
    *,
    set_assignments: Mapping[str, str],
    main_stat_layouts: Mapping[
        str,
        GcsimFiveStarMainStatLayout | Mapping[str, Any],
    ],
    set_catalog: GcsimArtifactSetCatalog,
    four_star_offpiece_slots: Mapping[str, str] | None = None,
    require_full_team: bool = True,
) -> GcsimOptimizerCandidateConfigResult:
    """Prepare one catalog-validated theoretical 4p team candidate."""

    set_result = render_gcsim_four_piece_set_overrides(
        config_text,
        set_assignments,
        require_full_team=require_full_team,
    )
    if not set_result.ready:
        return GcsimOptimizerCandidateConfigResult(
            status=OPTIMIZER_CANDIDATE_SET_CONFIG_INVALID,
            ready=False,
            set_config=set_result,
            source_notes={"catalog_fingerprint": set_catalog.source_fingerprint},
        )
    normalized_sets = {
        assignment.character_key: assignment.set_key
        for assignment in set_result.assignments
    }
    normalized_offpieces: dict[str, str] = {}
    issues: list[GcsimOptimizerCandidateIssue] = []
    for raw_character, raw_slot in (four_star_offpiece_slots or {}).items():
        character_key = str(raw_character or "").strip().casefold()
        slot = str(raw_slot or "").strip().casefold()
        if character_key in normalized_offpieces:
            issues.append(
                GcsimOptimizerCandidateIssue(
                    OPTIMIZER_CANDIDATE_OFFPIECE_MISMATCH,
                    f"four_star_offpiece_slots.{character_key}",
                    (
                        "More than one off-piece key normalizes to the same "
                        "character; the slot choice is ambiguous."
                    ),
                    character_key,
                    normalized_sets.get(character_key, ""),
                )
            )
            continue
        normalized_offpieces[character_key] = slot

    required_four_star_characters: set[str] = set()
    for character_key, set_key in normalized_sets.items():
        capability = set_catalog.get(set_key)
        if capability is None:
            issues.append(
                GcsimOptimizerCandidateIssue(
                    OPTIMIZER_CANDIDATE_UNKNOWN_SET,
                    f"set_assignments.{character_key}",
                    "Artifact set is absent from the engine-scoped catalog.",
                    character_key,
                    set_key,
                )
            )
            continue
        if not capability.complete_four_piece_modeled:
            issues.append(
                GcsimOptimizerCandidateIssue(
                    OPTIMIZER_CANDIDATE_UNMODELED_4P,
                    f"set_assignments.{character_key}",
                    (
                        "Artifact set is not a completely modeled four-piece "
                        "package (both 2p and 4p tiers are required)."
                    ),
                    character_key,
                    set_key,
                )
            )
        elif not capability.optimizer_four_piece_ready:
            issues.append(
                GcsimOptimizerCandidateIssue(
                    OPTIMIZER_CANDIDATE_SET_PARAMETERS_REQUIRED,
                    f"set_assignments.{character_key}",
                    (
                        "Artifact set requires an explicit frozen parameter "
                        "policy that Phase-1 does not implement: "
                        + ", ".join(capability.parameter_keys)
                    ),
                    character_key,
                    set_key,
                )
            )
        if capability.max_rarity == 4:
            required_four_star_characters.add(character_key)
        elif capability.max_rarity != 5:
            issues.append(
                GcsimOptimizerCandidateIssue(
                    OPTIMIZER_CANDIDATE_RARITY_MISMATCH,
                    f"set_assignments.{character_key}",
                    f"Unsupported artifact set max rarity: {capability.max_rarity}.",
                    character_key,
                    set_key,
                )
            )

    supplied_offpiece_characters = set(normalized_offpieces)
    for character_key in sorted(required_four_star_characters - supplied_offpiece_characters):
        issues.append(
            GcsimOptimizerCandidateIssue(
                OPTIMIZER_CANDIDATE_OFFPIECE_MISMATCH,
                f"four_star_offpiece_slots.{character_key}",
                "A four-star-only 4p set requires one explicit five-star off-piece slot.",
                character_key,
                normalized_sets.get(character_key, ""),
            )
        )
    for character_key in sorted(supplied_offpiece_characters - required_four_star_characters):
        issues.append(
            GcsimOptimizerCandidateIssue(
                OPTIMIZER_CANDIDATE_OFFPIECE_MISMATCH,
                f"four_star_offpiece_slots.{character_key}",
                "Off-piece rarity override is allowed only for a four-star-only set.",
                character_key,
                normalized_sets.get(character_key, ""),
            )
        )
    if issues:
        return GcsimOptimizerCandidateConfigResult(
            status=issues[0].status,
            ready=False,
            set_config=set_result,
            issues=tuple(issues),
            source_notes={"catalog_fingerprint": set_catalog.source_fingerprint},
        )
    if normalized_offpieces:
        main_result = render_gcsim_four_star_set_optimizer_config(
            set_result.config_text,
            main_stat_layouts,
            normalized_offpieces,
        )
    else:
        main_result = render_gcsim_substat_optimizer_config(
            set_result.config_text,
            main_stat_layouts,
        )
    if not main_result.ready:
        return GcsimOptimizerCandidateConfigResult(
            status=OPTIMIZER_CANDIDATE_MAIN_STATS_INVALID,
            ready=False,
            set_config=set_result,
            main_stats_config=main_result,
            source_notes={"catalog_fingerprint": set_catalog.source_fingerprint},
        )
    return GcsimOptimizerCandidateConfigResult(
        status=OPTIMIZER_CANDIDATE_READY,
        ready=True,
        config_text=main_result.config_text,
        set_config=set_result,
        main_stats_config=main_result,
        source_notes={
            "catalog_fingerprint": set_catalog.source_fingerprint,
            "set_domain": "optimizer_ready_complete_4p_without_set_params",
            "four_star_offpiece_slots": dict(normalized_offpieces),
        },
    )
