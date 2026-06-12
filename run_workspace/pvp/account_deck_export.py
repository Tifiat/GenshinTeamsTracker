"""Backend-only PvP deck export from account runtime storage.

This module is intentionally separated from UI/AppShell code and from raw
HoYoLAB account dumps. Production export reads the narrow SQLite runtime
adapters documented in `ACCOUNT_SQLITE_STORAGE.md`; tests can provide fake rows
through the same provider boundary.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from .deck import (
    DRAFT_DECK_KIND,
    DRAFT_DECK_SCHEMA_VERSION,
    FREE_DRAFT_V0_RULESET_ID,
    FREE_DRAFT_V0_RULESET_NAME,
    DraftCharacter,
    DraftDeck,
    DraftDeckPlayer,
    DraftDeckRulesetRef,
    DraftDeckSource,
    DraftWeaponStack,
    draft_deck_to_json_text,
)
from .validation import (
    DeckValidationReport,
    UNSUPPORTED_TRAVELER_CHARACTER_IDS,
    validate_draft_deck,
)


APP_NAME = "GenshinTeamsTracker"
DEFAULT_DECK_NAME = "Local Account Free Draft Deck"
DEFAULT_OUTPUT_DIR = Path("data") / "pvp" / "decks"

ISSUE_NO_ACCOUNT_CHARACTERS = "no_account_characters"
ISSUE_NO_ACCOUNT_WEAPON_STACKS = "no_account_weapon_stacks"
ISSUE_CHARACTER_MISSING_ID = "character_missing_id"
ISSUE_CHARACTER_TRAVELER_SKIPPED = "character_traveler_skipped"
ISSUE_CHARACTER_DISPLAY_NAME_MISSING = "character_display_name_missing"
ISSUE_CHARACTER_ELEMENT_MISSING = "character_element_missing"
ISSUE_CHARACTER_WEAPON_TYPE_MISSING = "character_weapon_type_missing"
ISSUE_CHARACTER_RARITY_MISSING = "character_rarity_missing"
ISSUE_CHARACTER_LEVEL_MISSING = "character_level_missing"
ISSUE_CHARACTER_CONSTELLATION_MISSING = "character_constellation_missing"
ISSUE_WEAPON_MISSING_ID = "weapon_missing_id"
ISSUE_WEAPON_INVALID_COUNT = "weapon_invalid_count"
ISSUE_WEAPON_DISPLAY_NAME_MISSING = "weapon_display_name_missing"
ISSUE_WEAPON_TYPE_MISSING = "weapon_type_missing"
ISSUE_WEAPON_RARITY_MISSING = "weapon_rarity_missing"
ISSUE_WEAPON_LEVEL_MISSING = "weapon_level_missing"
ISSUE_WEAPON_REFINEMENT_MISSING = "weapon_refinement_missing"
ISSUE_WEAPON_DUPLICATE_STACK_MERGED = "weapon_duplicate_stack_merged"
ISSUE_WEAPON_DUPLICATE_DISPLAY_NAME_MISMATCH = (
    "weapon_duplicate_display_name_mismatch"
)
ISSUE_SOURCE_DB_MISSING = "source_db_missing"

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

_WEAPON_TYPE_BY_HOYOLAB_ID = {
    1: "SWORD",
    10: "CATALYST",
    11: "CLAYMORE",
    12: "BOW",
    13: "POLEARM",
}
_WEAPON_TYPE_ALIASES = {
    "sword": "SWORD",
    "one_handed_sword": "SWORD",
    "claymore": "CLAYMORE",
    "bow": "BOW",
    "catalyst": "CATALYST",
    "polearm": "POLEARM",
}


class AccountDeckDataProvider(Protocol):
    """Small fakeable boundary for account deck export inputs."""

    def load_account_deck_data(self) -> "AccountDeckSourceData":
        """Return already-local account rows and privacy-safe source metadata."""


@dataclass(frozen=True, slots=True)
class AccountDeckCharacterRow:
    character_id: str
    display_name: str
    element: str = ""
    weapon_type: str | int | None = None
    weapon_type_name: str = ""
    rarity: int | None = None
    level: int | None = None
    constellation: int | None = None
    catalog_english_name: str = ""
    source_status: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AccountDeckWeaponStackRow:
    weapon_id: str
    display_name: str
    weapon_type: str | int | None = None
    weapon_type_name: str = ""
    rarity: int | None = None
    level: int | None = None
    refinement: int | None = None
    count: int | None = None
    catalog_english_name: str = ""
    source_status: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AccountDeckSourceData:
    characters: tuple[AccountDeckCharacterRow, ...] = ()
    weapon_stacks: tuple[AccountDeckWeaponStackRow, ...] = ()
    source_summary: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "characters_count": len(self.characters),
            "weapon_stacks_count": len(self.weapon_stacks),
            "source_summary": dict(sorted(self.source_summary.items())),
        }


@dataclass(frozen=True, slots=True)
class AccountDeckExportOptions:
    deck_name: str = DEFAULT_DECK_NAME
    nickname: str = ""
    language: str = "unknown"
    exported_at_utc: str = ""


@dataclass(frozen=True, slots=True)
class AccountDeckExportIssue:
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
class AccountDeckExportCounts:
    characters_seen: int = 0
    weapon_stacks_seen: int = 0
    characters_exported: int = 0
    weapons_exported: int = 0
    traveler_entries_skipped: int = 0
    entries_skipped_missing_id: int = 0
    entries_skipped_unsupported_shape: int = 0
    weapon_stack_rows_merged: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "characters_seen": self.characters_seen,
            "weapon_stacks_seen": self.weapon_stacks_seen,
            "characters_exported": self.characters_exported,
            "weapons_exported": self.weapons_exported,
            "traveler_entries_skipped": self.traveler_entries_skipped,
            "entries_skipped_missing_id": self.entries_skipped_missing_id,
            "entries_skipped_unsupported_shape": self.entries_skipped_unsupported_shape,
            "weapon_stack_rows_merged": self.weapon_stack_rows_merged,
        }


@dataclass(frozen=True, slots=True)
class AccountDeckExportReport:
    deck: DraftDeck
    validation_report: DeckValidationReport
    issues: tuple[AccountDeckExportIssue, ...]
    counts: AccountDeckExportCounts
    source_summary: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.validation_report.ready

    def issue_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "deck": self.deck.to_dict(),
            "validation_report": self.validation_report.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
            "counts": self.counts.to_dict(),
            "source_summary": dict(sorted(self.source_summary.items())),
        }


class LocalAccountSQLiteDeckDataProvider:
    """Production provider over current local account SQLite runtime tables."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else None

    @property
    def db_path(self) -> Path:
        if self._db_path is not None:
            return self._db_path
        from hoyolab_export.account_storage import DEFAULT_ACCOUNT_DB_PATH

        return Path(DEFAULT_ACCOUNT_DB_PATH)

    def load_account_deck_data(self) -> AccountDeckSourceData:
        db_path = self.db_path
        source_summary: dict[str, Any] = {
            "provider": "local_account_sqlite",
            "character_source": "account_characters",
            "weapon_source": "account_weapon_observed_stacks",
            "db_exists": db_path.exists(),
        }
        if not db_path.exists():
            return AccountDeckSourceData(source_summary=source_summary)

        from hoyolab_export.account_storage import (
            list_account_characters,
            list_account_weapon_observed_stacks,
        )
        from hoyolab_export.artifact_db import connect_db

        with closing(connect_db(db_path)) as conn:
            character_records = list_account_characters(conn)
            weapon_records = list_account_weapon_observed_stacks(conn)

        return AccountDeckSourceData(
            characters=tuple(
                AccountDeckCharacterRow(
                    character_id=record.character_id,
                    display_name=record.name,
                    element=record.element,
                    weapon_type=record.weapon_type,
                    weapon_type_name=record.weapon_type_name,
                    rarity=record.rarity,
                    level=record.level,
                    constellation=record.constellation,
                    catalog_english_name=record.catalog_english_name,
                    source_status=record.source_status,
                    warnings=record.warnings,
                )
                for record in character_records
            ),
            weapon_stacks=tuple(
                AccountDeckWeaponStackRow(
                    weapon_id=record.weapon_id,
                    display_name=record.name,
                    weapon_type=record.weapon_type,
                    weapon_type_name=record.weapon_type_name,
                    rarity=record.rarity,
                    level=record.level,
                    refinement=record.refinement,
                    count=record.known_count,
                    catalog_english_name=record.catalog_english_name,
                    source_status=record.source_status,
                    warnings=record.warnings,
                )
                for record in weapon_records
            ),
            source_summary={
                **source_summary,
                "characters_read": len(character_records),
                "weapon_stacks_read": len(weapon_records),
            },
        )


@dataclass(frozen=True, slots=True)
class FakeAccountDeckDataProvider:
    """Test/dev provider for deterministic account deck export scenarios."""

    characters: tuple[AccountDeckCharacterRow, ...] = ()
    weapon_stacks: tuple[AccountDeckWeaponStackRow, ...] = ()
    source_summary: Mapping[str, Any] = field(default_factory=dict)

    def load_account_deck_data(self) -> AccountDeckSourceData:
        return AccountDeckSourceData(
            characters=self.characters,
            weapon_stacks=self.weapon_stacks,
            source_summary={
                "provider": "fake_account_deck_data",
                **dict(self.source_summary),
            },
        )


def export_free_draft_deck_from_account(
    provider: AccountDeckDataProvider,
    *,
    options: AccountDeckExportOptions | None = None,
) -> AccountDeckExportReport:
    options = options or AccountDeckExportOptions()
    source_data = provider.load_account_deck_data()
    issues: list[AccountDeckExportIssue] = []

    if source_data.source_summary.get("db_exists") is False:
        issues.append(
            _issue(
                ISSUE_SOURCE_DB_MISSING,
                SEVERITY_ERROR,
                "Account SQLite runtime database was not found.",
                path="source",
            )
        )
    if not source_data.characters:
        issues.append(
            _issue(
                ISSUE_NO_ACCOUNT_CHARACTERS,
                SEVERITY_ERROR,
                "No imported account characters were available for PvP export.",
                path="characters",
            )
        )
    if not source_data.weapon_stacks:
        issues.append(
            _issue(
                ISSUE_NO_ACCOUNT_WEAPON_STACKS,
                SEVERITY_WARNING,
                "No observed account weapon stacks were available for PvP export.",
                path="weapons",
            )
        )

    characters, character_counts = _export_characters(source_data.characters, issues)
    weapons, weapon_counts = _export_weapon_stacks(source_data.weapon_stacks, issues)

    deck = DraftDeck(
        schema_version=DRAFT_DECK_SCHEMA_VERSION,
        kind=DRAFT_DECK_KIND,
        deck_name=_text(options.deck_name) or DEFAULT_DECK_NAME,
        ruleset_ref=DraftDeckRulesetRef(
            ruleset_id=FREE_DRAFT_V0_RULESET_ID,
            ruleset_name=FREE_DRAFT_V0_RULESET_NAME,
        ),
        player=DraftDeckPlayer(nickname=_text(options.nickname)),
        source=DraftDeckSource(
            app=APP_NAME,
            language=_text(options.language) or "unknown",
            exported_at_utc=_text(options.exported_at_utc) or _utc_now(),
            extra={
                "source_type": "local_account_runtime",
                "character_source": "account_characters",
                "weapon_source": "account_weapon_observed_stacks",
                "privacy": "artifacts_auth_paths_raw_dumps_excluded",
            },
        ),
        characters=characters,
        weapons=weapons,
    )
    validation_report = validate_draft_deck(deck)
    counts = AccountDeckExportCounts(
        characters_seen=len(source_data.characters),
        weapon_stacks_seen=len(source_data.weapon_stacks),
        characters_exported=len(characters),
        weapons_exported=len(weapons),
        traveler_entries_skipped=character_counts["traveler_entries_skipped"],
        entries_skipped_missing_id=(
            character_counts["entries_skipped_missing_id"]
            + weapon_counts["entries_skipped_missing_id"]
        ),
        entries_skipped_unsupported_shape=weapon_counts[
            "entries_skipped_unsupported_shape"
        ],
        weapon_stack_rows_merged=weapon_counts["weapon_stack_rows_merged"],
    )
    return AccountDeckExportReport(
        deck=deck,
        validation_report=validation_report,
        issues=tuple(issues),
        counts=counts,
        source_summary=source_data.source_summary,
    )


def export_free_draft_deck_from_local_account(
    *,
    options: AccountDeckExportOptions | None = None,
    db_path: str | Path | None = None,
) -> AccountDeckExportReport:
    return export_free_draft_deck_from_account(
        LocalAccountSQLiteDeckDataProvider(db_path),
        options=options,
    )


def write_account_draft_deck(
    deck: DraftDeck,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(draft_deck_to_json_text(deck), encoding="utf-8")
    return path


def default_account_deck_output_path(
    *,
    exported_at_utc: str | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> Path:
    stamp = _filename_timestamp(exported_at_utc or _utc_now())
    return Path(output_dir) / f"free_draft_account_deck_{stamp}.json"


def _export_characters(
    rows: tuple[AccountDeckCharacterRow, ...],
    issues: list[AccountDeckExportIssue],
) -> tuple[tuple[DraftCharacter, ...], dict[str, int]]:
    characters: list[DraftCharacter] = []
    skipped_missing_id = 0
    skipped_traveler = 0

    for index, row in enumerate(rows):
        path = f"characters[{index}]"
        character_id = _text(row.character_id)
        display_name = _text(row.display_name) or _text(row.catalog_english_name)
        if not character_id:
            skipped_missing_id += 1
            issues.append(
                _issue(
                    ISSUE_CHARACTER_MISSING_ID,
                    SEVERITY_ERROR,
                    "Account character row has no stable character id and was skipped.",
                    path=path,
                )
            )
            continue
        if _is_unsupported_traveler(character_id, display_name):
            skipped_traveler += 1
            issues.append(
                _issue(
                    ISSUE_CHARACTER_TRAVELER_SKIPPED,
                    SEVERITY_WARNING,
                    "Traveler is unsupported in PvP v0 and was skipped.",
                    path=path,
                    details={"character_id": character_id},
                )
            )
            continue

        element = _canonical_element(row.element)
        weapon_type = _canonical_weapon_type(row.weapon_type, row.weapon_type_name)
        if not display_name:
            issues.append(
                _field_issue(
                    ISSUE_CHARACTER_DISPLAY_NAME_MISSING,
                    path=f"{path}.display_name",
                    entity_id=character_id,
                )
            )
        if not element:
            issues.append(
                _field_issue(
                    ISSUE_CHARACTER_ELEMENT_MISSING,
                    path=f"{path}.element",
                    entity_id=character_id,
                )
            )
        if not weapon_type:
            issues.append(
                _field_issue(
                    ISSUE_CHARACTER_WEAPON_TYPE_MISSING,
                    path=f"{path}.weapon_type",
                    entity_id=character_id,
                )
            )
        if row.rarity is None:
            issues.append(
                _field_issue(
                    ISSUE_CHARACTER_RARITY_MISSING,
                    path=f"{path}.rarity",
                    entity_id=character_id,
                )
            )
        if row.level is None:
            issues.append(
                _field_issue(
                    ISSUE_CHARACTER_LEVEL_MISSING,
                    path=f"{path}.level",
                    entity_id=character_id,
                )
            )
        if row.constellation is None:
            issues.append(
                _field_issue(
                    ISSUE_CHARACTER_CONSTELLATION_MISSING,
                    path=f"{path}.constellation",
                    entity_id=character_id,
                )
            )

        characters.append(
            DraftCharacter(
                character_id=character_id,
                display_name=display_name,
                element=element,
                weapon_type=weapon_type,
                rarity=row.rarity,
                level=row.level,
                constellation=row.constellation,
                cost=None,
            )
        )

    return (
        tuple(characters),
        {
            "entries_skipped_missing_id": skipped_missing_id,
            "traveler_entries_skipped": skipped_traveler,
        },
    )


def _export_weapon_stacks(
    rows: tuple[AccountDeckWeaponStackRow, ...],
    issues: list[AccountDeckExportIssue],
) -> tuple[tuple[DraftWeaponStack, ...], dict[str, int]]:
    merged: dict[tuple[str, str, int | None, int | None, int | None], DraftWeaponStack] = {}
    order: list[tuple[str, str, int | None, int | None, int | None]] = []
    skipped_missing_id = 0
    skipped_invalid_shape = 0
    merged_rows = 0

    for index, row in enumerate(rows):
        path = f"weapons[{index}]"
        weapon_id = _text(row.weapon_id)
        display_name = _text(row.display_name) or _text(row.catalog_english_name)
        weapon_type = _canonical_weapon_type(row.weapon_type, row.weapon_type_name)
        count = row.count

        if not weapon_id:
            skipped_missing_id += 1
            issues.append(
                _issue(
                    ISSUE_WEAPON_MISSING_ID,
                    SEVERITY_ERROR,
                    "Account weapon stack row has no stable weapon id and was skipped.",
                    path=path,
                )
            )
            continue
        if count is None or count <= 0:
            skipped_invalid_shape += 1
            issues.append(
                _issue(
                    ISSUE_WEAPON_INVALID_COUNT,
                    SEVERITY_ERROR,
                    "Account weapon stack count must be positive and was skipped.",
                    path=f"{path}.count",
                    details={"weapon_id": weapon_id, "count": count},
                )
            )
            continue

        if not display_name:
            issues.append(
                _field_issue(
                    ISSUE_WEAPON_DISPLAY_NAME_MISSING,
                    path=f"{path}.display_name",
                    entity_id=weapon_id,
                )
            )
        if not weapon_type:
            issues.append(
                _field_issue(
                    ISSUE_WEAPON_TYPE_MISSING,
                    path=f"{path}.weapon_type",
                    entity_id=weapon_id,
                )
            )
        if row.rarity is None:
            issues.append(
                _field_issue(
                    ISSUE_WEAPON_RARITY_MISSING,
                    path=f"{path}.rarity",
                    entity_id=weapon_id,
                )
            )
        if row.level is None:
            issues.append(
                _field_issue(
                    ISSUE_WEAPON_LEVEL_MISSING,
                    path=f"{path}.level",
                    entity_id=weapon_id,
                )
            )
        if row.refinement is None:
            issues.append(
                _field_issue(
                    ISSUE_WEAPON_REFINEMENT_MISSING,
                    path=f"{path}.refinement",
                    entity_id=weapon_id,
                )
            )

        key = (weapon_id, weapon_type, row.rarity, row.level, row.refinement)
        stack = DraftWeaponStack(
            weapon_id=weapon_id,
            display_name=display_name,
            weapon_type=weapon_type,
            rarity=row.rarity,
            level=row.level,
            refinement=row.refinement,
            count=count,
            cost=None,
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = stack
            order.append(key)
            continue

        merged_rows += 1
        if existing.display_name != stack.display_name:
            issues.append(
                _issue(
                    ISSUE_WEAPON_DUPLICATE_DISPLAY_NAME_MISMATCH,
                    SEVERITY_WARNING,
                    "Duplicate weapon stack rows had different display names; the first was kept.",
                    path=path,
                    details={"weapon_id": weapon_id},
                )
            )
        else:
            issues.append(
                _issue(
                    ISSUE_WEAPON_DUPLICATE_STACK_MERGED,
                    SEVERITY_WARNING,
                    "Duplicate identical weapon stack row was merged by count.",
                    path=path,
                    details={"weapon_id": weapon_id},
                )
            )
        merged[key] = DraftWeaponStack(
            weapon_id=existing.weapon_id,
            display_name=existing.display_name,
            weapon_type=existing.weapon_type,
            rarity=existing.rarity,
            level=existing.level,
            refinement=existing.refinement,
            count=(existing.count or 0) + count,
            cost=None,
        )

    return (
        tuple(merged[key] for key in order),
        {
            "entries_skipped_missing_id": skipped_missing_id,
            "entries_skipped_unsupported_shape": skipped_invalid_shape,
            "weapon_stack_rows_merged": merged_rows,
        },
    )


def _canonical_element(value: Any) -> str:
    token = _text(value)
    return token.upper() if token else ""


def _canonical_weapon_type(type_value: Any, type_name: Any = "") -> str:
    type_id = _optional_int(type_value)
    if type_id in _WEAPON_TYPE_BY_HOYOLAB_ID:
        return _WEAPON_TYPE_BY_HOYOLAB_ID[type_id]
    for value in (type_name, type_value):
        token = _normalized_token(value)
        if token in _WEAPON_TYPE_ALIASES:
            return _WEAPON_TYPE_ALIASES[token]
    text = _text(type_name) or _text(type_value)
    return text.upper() if text else ""


def _field_issue(code: str, *, path: str, entity_id: str) -> AccountDeckExportIssue:
    return _issue(
        code,
        SEVERITY_WARNING,
        "Required deck metadata was missing in account runtime storage.",
        path=path,
        details={"id": entity_id},
    )


def _issue(
    code: str,
    severity: str,
    message: str,
    *,
    path: str = "",
    details: Mapping[str, Any] | None = None,
) -> AccountDeckExportIssue:
    return AccountDeckExportIssue(
        code=code,
        severity=severity,
        message=message,
        path=path,
        details=details or {},
    )


def _is_unsupported_traveler(character_id: str, display_name: str) -> bool:
    if character_id in UNSUPPORTED_TRAVELER_CHARACTER_IDS:
        return True
    return "traveler" in display_name.strip().casefold()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def _filename_timestamp(value: str) -> str:
    return (
        _text(value)
        .replace(":", "")
        .replace("-", "")
        .replace("+0000", "Z")
        .replace("+00:00", "Z")
        .replace(".", "")
    )


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalized_token(value: Any) -> str:
    return _text(value).replace(" ", "_").replace("-", "_").casefold()


def _text(value: Any) -> str:
    return str(value or "").strip()
