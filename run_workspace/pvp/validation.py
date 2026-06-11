from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .deck import DRAFT_DECK_KIND, DRAFT_DECK_SCHEMA_VERSION, DraftDeck
from .schedule import FreeDraftV0Config, default_free_draft_v0_config


ISSUE_SCHEMA_VERSION_INVALID = "schema_version_invalid"
ISSUE_KIND_INVALID = "kind_invalid"
ISSUE_MISSING_DECK_NAME = "missing_deck_name"
ISSUE_DUPLICATE_CHARACTER_ID = "duplicate_character_id"
ISSUE_MISSING_CHARACTER_ID = "missing_character_id"
ISSUE_MISSING_CHARACTER_DISPLAY_NAME = "missing_character_display_name"
ISSUE_MISSING_CHARACTER_WEAPON_TYPE = "missing_character_weapon_type"
ISSUE_INVALID_CHARACTER_RARITY = "invalid_character_rarity"
ISSUE_INVALID_CHARACTER_LEVEL = "invalid_character_level"
ISSUE_INVALID_CHARACTER_CONSTELLATION = "invalid_character_constellation"
ISSUE_UNSUPPORTED_TRAVELER_CHARACTER = "unsupported_traveler_character"
ISSUE_NOT_ENOUGH_CHARACTERS_FREE_DRAFT = "not_enough_characters_for_free_draft_v0"
ISSUE_DUPLICATE_WEAPON_STACK_KEY = "duplicate_weapon_stack_key"
ISSUE_MISSING_WEAPON_ID = "missing_weapon_id"
ISSUE_MISSING_WEAPON_DISPLAY_NAME = "missing_weapon_display_name"
ISSUE_MISSING_WEAPON_TYPE = "missing_weapon_type"
ISSUE_INVALID_WEAPON_RARITY = "invalid_weapon_rarity"
ISSUE_INVALID_WEAPON_LEVEL = "invalid_weapon_level"
ISSUE_INVALID_WEAPON_REFINEMENT = "invalid_weapon_refinement"
ISSUE_INVALID_WEAPON_COUNT = "invalid_weapon_count"

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

# Existing handoff/tests identify account Traveler as these ids. Full localized
# variant detection belongs to the future dedicated Traveler model.
UNSUPPORTED_TRAVELER_CHARACTER_IDS = frozenset({"10000005", "10000007"})


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    severity: str
    message: str = ""
    path: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "details": dict(sorted(self.details.items())),
        }


@dataclass(frozen=True, slots=True)
class DeckValidationReport:
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(item for item in self.issues if item.severity == SEVERITY_ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(item for item in self.issues if item.severity == SEVERITY_WARNING)

    @property
    def ready(self) -> bool:
        return not self.errors

    @property
    def status(self) -> str:
        return "ready" if self.ready else "invalid"

    def issue_codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "errors": [item.to_dict() for item in self.errors],
            "warnings": [item.to_dict() for item in self.warnings],
            "issues": [item.to_dict() for item in self.issues],
        }


@dataclass(frozen=True, slots=True)
class SimpleValidationReport:
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(item for item in self.issues if item.severity == SEVERITY_ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(item for item in self.issues if item.severity == SEVERITY_WARNING)

    @property
    def ready(self) -> bool:
        return not self.errors

    @property
    def status(self) -> str:
        return "ready" if self.ready else "invalid"

    def issue_codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "errors": [item.to_dict() for item in self.errors],
            "warnings": [item.to_dict() for item in self.warnings],
            "issues": [item.to_dict() for item in self.issues],
        }


def validate_draft_deck(
    deck: DraftDeck,
    *,
    config: FreeDraftV0Config | None = None,
) -> DeckValidationReport:
    config = config or default_free_draft_v0_config()
    issues: list[ValidationIssue] = []

    if deck.schema_version != DRAFT_DECK_SCHEMA_VERSION:
        issues.append(_error(ISSUE_SCHEMA_VERSION_INVALID, path="schema_version"))
    if deck.kind != DRAFT_DECK_KIND:
        issues.append(_error(ISSUE_KIND_INVALID, path="kind"))
    if not deck.deck_name:
        issues.append(_error(ISSUE_MISSING_DECK_NAME, path="deck_name"))

    seen_characters: dict[str, int] = {}
    valid_character_ids: set[str] = set()
    for index, character in enumerate(deck.characters):
        path = f"characters[{index}]"
        if not character.character_id:
            issues.append(_error(ISSUE_MISSING_CHARACTER_ID, path=f"{path}.character_id"))
        elif character.character_id in seen_characters:
            issues.append(
                _error(
                    ISSUE_DUPLICATE_CHARACTER_ID,
                    path=f"{path}.character_id",
                    details={
                        "character_id": character.character_id,
                        "first_index": seen_characters[character.character_id],
                    },
                )
            )
        else:
            seen_characters[character.character_id] = index
            if not _is_unsupported_traveler(character.character_id, character.display_name):
                valid_character_ids.add(character.character_id)
        if not character.display_name:
            issues.append(
                _error(
                    ISSUE_MISSING_CHARACTER_DISPLAY_NAME,
                    path=f"{path}.display_name",
                )
            )
        if not character.weapon_type:
            issues.append(
                _error(
                    ISSUE_MISSING_CHARACTER_WEAPON_TYPE,
                    path=f"{path}.weapon_type",
                )
            )
        if not _int_in_range(character.rarity, 1, 5):
            issues.append(_error(ISSUE_INVALID_CHARACTER_RARITY, path=f"{path}.rarity"))
        if not _int_in_range(character.level, 1, 100):
            issues.append(_error(ISSUE_INVALID_CHARACTER_LEVEL, path=f"{path}.level"))
        if not _int_in_range(character.constellation, 0, 6):
            issues.append(
                _error(
                    ISSUE_INVALID_CHARACTER_CONSTELLATION,
                    path=f"{path}.constellation",
                )
            )
        if _is_unsupported_traveler(character.character_id, character.display_name):
            issues.append(
                _error(
                    ISSUE_UNSUPPORTED_TRAVELER_CHARACTER,
                    path=path,
                    details={
                        "character_id": character.character_id,
                        "display_name": character.display_name,
                    },
                )
            )

    if len(valid_character_ids) < config.minimum_characters_per_deck:
        issues.append(
            _error(
                ISSUE_NOT_ENOUGH_CHARACTERS_FREE_DRAFT,
                path="characters",
                details={
                    "minimum_required": config.minimum_characters_per_deck,
                    "actual_unique_non_traveler": len(valid_character_ids),
                },
            )
        )

    seen_weapon_stacks: dict[str, int] = {}
    for index, weapon in enumerate(deck.weapons):
        path = f"weapons[{index}]"
        if not weapon.weapon_id:
            issues.append(_error(ISSUE_MISSING_WEAPON_ID, path=f"{path}.weapon_id"))
        elif weapon.stack_key in seen_weapon_stacks:
            issues.append(
                _error(
                    ISSUE_DUPLICATE_WEAPON_STACK_KEY,
                    path=path,
                    details={
                        "weapon_stack_key": weapon.stack_key,
                        "first_index": seen_weapon_stacks[weapon.stack_key],
                    },
                )
            )
        else:
            seen_weapon_stacks[weapon.stack_key] = index
        if not weapon.display_name:
            issues.append(
                _error(
                    ISSUE_MISSING_WEAPON_DISPLAY_NAME,
                    path=f"{path}.display_name",
                )
            )
        if not weapon.weapon_type:
            issues.append(_error(ISSUE_MISSING_WEAPON_TYPE, path=f"{path}.weapon_type"))
        if not _int_in_range(weapon.rarity, 1, 5):
            issues.append(_error(ISSUE_INVALID_WEAPON_RARITY, path=f"{path}.rarity"))
        if not _int_in_range(weapon.level, 1, 100):
            issues.append(_error(ISSUE_INVALID_WEAPON_LEVEL, path=f"{path}.level"))
        if not _int_in_range(weapon.refinement, 1, 5):
            issues.append(
                _error(ISSUE_INVALID_WEAPON_REFINEMENT, path=f"{path}.refinement")
            )
        if weapon.count is None or weapon.count <= 0:
            issues.append(_error(ISSUE_INVALID_WEAPON_COUNT, path=f"{path}.count"))

    return DeckValidationReport(issues=tuple(issues))


def _error(
    code: str,
    *,
    path: str = "",
    details: Mapping[str, Any] | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=SEVERITY_ERROR,
        path=path,
        details=details or {},
    )


def _int_in_range(value: int | None, minimum: int, maximum: int) -> bool:
    return value is not None and minimum <= value <= maximum


def _is_unsupported_traveler(character_id: str, display_name: str) -> bool:
    if character_id in UNSUPPORTED_TRAVELER_CHARACTER_IDS:
        return True
    return "traveler" in display_name.strip().casefold()
