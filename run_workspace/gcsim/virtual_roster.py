"""Installed-GCSIM catalog and virtual run-slot contracts.

Virtual slots deliberately live outside the account/team state.  They are an
explicit input to GCSIM preparation, not an imported account character and not
an equipment owner.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import re
import sqlite3
from typing import Iterable

from hoyolab_export.artifact_db import normalize_artifact_set_lang
from hoyolab_export.paths import PROJECT_ROOT

from .artifact_set_catalog import (
    GcsimArtifactSetCatalogError,
    load_gcsim_artifact_set_catalog,
)
from .engine_store import GcsimEngineStore, GcsimEngineStoreError


_CATALOG_ENTRY_RE = re.compile(
    r"(?ms)^\s*keys\.(?P<enum>[A-Za-z0-9_]+):\s*\{\s*\n"
    r"(?P<body>.*?)(?=^\s*keys\.[A-Za-z0-9_]+:\s*\{|^\})"
)
_STRING_FIELD_RE = r'^\s*{field}:\s*"(?P<value>[^"]+)"'
_WEAPON_CLASS_RE = re.compile(
    r"(?m)^\s*WeaponClass:\s*model\.WeaponType_(?P<value>[A-Z0-9_]+)"
)

_WEAPON_TYPES = {
    "WEAPON_BOW": "bow",
    "WEAPON_CATALYST": "catalyst",
    "WEAPON_CLAYMORE": "claymore",
    "WEAPON_POLE": "polearm",
    "WEAPON_SPEAR": "polearm",
    "WEAPON_SWORD_ONE_HAND": "sword",
}

_MAX_ASCENSION_BY_MINIMUM_LEVEL = (
    (80, 6),
    (70, 5),
    (60, 4),
    (50, 3),
    (40, 2),
    (20, 1),
    (1, 0),
)

_MAX_TALENT_BY_ASCENSION = (1, 1, 2, 4, 6, 8, 10)


@dataclass(frozen=True, slots=True)
class GcsimCatalogCharacter:
    gcsim_key: str
    display_name: str
    weapon_type: str
    icon_name: str = ""
    icon_path: str = ""


@dataclass(frozen=True, slots=True)
class GcsimCatalogWeapon:
    gcsim_key: str
    display_name: str
    weapon_type: str
    icon_name: str = ""
    icon_path: str = ""


@dataclass(frozen=True, slots=True)
class GcsimVirtualArtifactSetChoice:
    """One engine-backed artifact set shown by the virtual build picker."""

    set_uid: str
    display_name: str
    gcsim_key: str
    two_piece_available: bool = True
    four_piece_available: bool = True
    icon_path: str = ""


@dataclass(frozen=True, slots=True)
class GcsimVirtualSetBonus:
    """Explicit virtual set-bonus package, separate from raw artifact stats."""

    set_uid: str
    display_name: str
    gcsim_key: str
    piece_count: int

    def __post_init__(self) -> None:
        if not self.set_uid.strip() or not self.gcsim_key.strip():
            raise ValueError("virtual set bonus requires stable set and GCSIM keys")
        if int(self.piece_count) not in {2, 4}:
            raise ValueError("virtual set bonus piece_count must be 2 or 4")

    def to_dict(self) -> dict[str, object]:
        return {
            "set_uid": self.set_uid,
            "display_name": self.display_name,
            "count": int(self.piece_count),
            "mapping": {
                "gcsim_key": self.gcsim_key,
                "source": "virtual_gcsim_set_selector",
                "ambiguous": False,
            },
        }


@dataclass(frozen=True, slots=True)
class GcsimVirtualRosterCatalog:
    engine_id: str
    characters: tuple[GcsimCatalogCharacter, ...]
    weapons: tuple[GcsimCatalogWeapon, ...]

    @classmethod
    def empty(cls) -> "GcsimVirtualRosterCatalog":
        return cls(engine_id="", characters=(), weapons=())


@dataclass(frozen=True, slots=True)
class GcsimVirtualSlotOverride:
    """A virtual character shown in a run slot and sent to GCSIM preparation."""

    team_index: int
    slot_index: int
    character_key: str
    character_name: str
    character_weapon_type: str
    character_icon_path: str = ""
    weapon_key: str = ""
    weapon_name: str = ""
    weapon_type: str = ""
    weapon_icon_path: str = ""
    constellation: int = 0
    refinement: int = 1
    character_level: int | None = None
    character_promote_level: int | None = None
    talent_normal: int | None = None
    talent_skill: int | None = None
    talent_burst: int | None = None
    weapon_level: int | None = None
    weapon_promote_level: int | None = None
    artifact_build_id: int | None = None
    artifact_build_name: str = ""
    artifact_set_bonuses: tuple[GcsimVirtualSetBonus, ...] = ()

    def __post_init__(self) -> None:
        if not self.character_key.strip():
            raise ValueError("character_key is required")
        if not 0 <= int(self.constellation) <= 6:
            raise ValueError("constellation must be between 0 and 6")
        if not 1 <= int(self.refinement) <= 5:
            raise ValueError("refinement must be between 1 and 5")
        if self.character_level is not None and not 1 <= int(self.character_level) <= 100:
            raise ValueError("character_level must be between 1 and 100")
        if self.character_level is not None:
            # A virtual profile has no account-side before/after-ascension bit.
            # Its single level control therefore always selects the highest legal
            # phase for that level (80 means 80/90, never an implicit 80/80).
            object.__setattr__(
                self,
                "character_promote_level",
                max_virtual_promote_level(self.character_level),
            )
        elif self.character_promote_level is not None:
            object.__setattr__(self, "character_promote_level", None)
        for name, value in (
            ("talent_normal", self.talent_normal),
            ("talent_skill", self.talent_skill),
            ("talent_burst", self.talent_burst),
        ):
            if value is not None and not 1 <= int(value) <= 15:
                raise ValueError(f"{name} must be between 1 and 15")
        if self.character_level is not None:
            maximum_talent = max_virtual_talent_level(self.character_level)
            for name, value in (
                ("talent_normal", self.talent_normal),
                ("talent_skill", self.talent_skill),
                ("talent_burst", self.talent_burst),
            ):
                if value is not None and int(value) > maximum_talent:
                    raise ValueError(
                        f"{name} exceeds the legal level {maximum_talent} "
                        f"for character level {self.character_level}"
                    )
        if self.weapon_level is not None and not 1 <= int(self.weapon_level) <= 90:
            raise ValueError("weapon_level must be between 1 and 90")
        if self.weapon_promote_level is not None and not 0 <= int(self.weapon_promote_level) <= 6:
            raise ValueError("weapon_promote_level must be between 0 and 6")
        if self.artifact_build_id is not None and int(self.artifact_build_id) <= 0:
            raise ValueError("artifact_build_id must be positive")
        normalized_bonuses = tuple(
            sorted(self.artifact_set_bonuses, key=lambda item: item.set_uid.casefold())
        )
        if len({item.set_uid.casefold() for item in normalized_bonuses}) != len(
            normalized_bonuses
        ):
            raise ValueError("virtual set bonuses must use distinct stable set keys")
        counts = tuple(item.piece_count for item in normalized_bonuses)
        if counts not in {(), (4,), (2,), (2, 2)}:
            raise ValueError("virtual set bonuses must be one 4p or two distinct 2p sets")
        object.__setattr__(self, "artifact_set_bonuses", normalized_bonuses)
        if (
            self.weapon_key
            and self.character_weapon_type
            and self.weapon_type
            and self.character_weapon_type != self.weapon_type
        ):
            raise ValueError("weapon type is incompatible with character")

    def with_weapon(self, weapon: GcsimCatalogWeapon | None) -> "GcsimVirtualSlotOverride":
        if weapon is None:
            return replace(
                self,
                weapon_key="",
                weapon_name="",
                weapon_type="",
                weapon_icon_path="",
                refinement=1,
                weapon_level=None,
                weapon_promote_level=None,
            )
        return replace(
            self,
            weapon_key=weapon.gcsim_key,
            weapon_name=weapon.display_name,
            weapon_type=weapon.weapon_type,
            weapon_icon_path=weapon.icon_path,
        )

    def moved_to(self, team_index: int, slot_index: int) -> "GcsimVirtualSlotOverride":
        """Move the whole virtual identity without changing profile data."""

        return replace(
            self,
            team_index=int(team_index),
            slot_index=int(slot_index),
        )

    @property
    def missing_core_profile_fields(self) -> tuple[str, ...]:
        missing: list[str] = []
        if self.character_level is None or self.character_promote_level is None:
            missing.append("character_level")
        if any(
            value is None
            for value in (self.talent_normal, self.talent_skill, self.talent_burst)
        ):
            missing.append("character_talents")
        if self.weapon_level is None or self.weapon_promote_level is None:
            missing.append("weapon_level")
        return tuple(missing)

    @property
    def missing_profile_fields(self) -> tuple[str, ...]:
        missing = list(self.missing_core_profile_fields)
        if self.artifact_build_id is None:
            missing.append("artifact_build")
        return tuple(missing)

    @property
    def theory_set_package_ready(self) -> bool:
        counts = tuple(item.piece_count for item in self.artifact_set_bonuses)
        return counts in {(4,), (2, 2)}

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "source": "virtual_gcsim_slot_override",
            "team_index": int(self.team_index),
            "slot_index": int(self.slot_index),
            "character": {
                "gcsim_key": self.character_key,
                "name": self.character_name,
                "weapon_type": self.character_weapon_type,
                "icon_path": self.character_icon_path,
                "constellation": int(self.constellation),
                "level": self.character_level,
                "promote_level": self.character_promote_level,
                "talents": {
                    "normal": self.talent_normal,
                    "skill": self.talent_skill,
                    "burst": self.talent_burst,
                    "source_order_confirmed": True,
                    "source": "virtual_gcsim_profile_editor",
                },
            },
            "weapon": (
                {
                    "gcsim_key": self.weapon_key,
                    "name": self.weapon_name,
                    "weapon_type": self.weapon_type,
                    "icon_path": self.weapon_icon_path,
                    "refinement": int(self.refinement),
                    "level": self.weapon_level,
                    "promote_level": self.weapon_promote_level,
                }
                if self.weapon_key
                else None
            ),
            "artifact_build_id": self.artifact_build_id,
            "artifact_build_name": self.artifact_build_name,
            "artifact_set_bonuses": [
                item.to_dict() for item in self.artifact_set_bonuses
            ],
            "profile_status": "ready" if not self.missing_profile_fields else "incomplete",
            "missing_profile_fields": list(self.missing_profile_fields),
        }


def load_active_virtual_roster_catalog(
    store: GcsimEngineStore | None = None,
) -> GcsimVirtualRosterCatalog:
    store = store or GcsimEngineStore()
    try:
        installation = store.get_active_engine()
    except GcsimEngineStoreError:
        return GcsimVirtualRosterCatalog.empty()
    if installation is None:
        return GcsimVirtualRosterCatalog.empty()
    character_path = installation.path / "pkg" / "catalog" / "character.dm.go"
    weapon_path = installation.path / "pkg" / "catalog" / "weapon.dm.go"
    try:
        character_source = character_path.read_text(encoding="utf-8")
        weapon_source = weapon_path.read_text(encoding="utf-8")
    except OSError:
        return GcsimVirtualRosterCatalog.empty()
    return GcsimVirtualRosterCatalog(
        engine_id=installation.engine_id,
        characters=tuple(parse_character_catalog(character_source)),
        weapons=tuple(parse_weapon_catalog(weapon_source)),
    )


def load_active_virtual_artifact_set_choices(
    db_path: str | Path,
    *,
    language: str,
    store: GcsimEngineStore | None = None,
) -> tuple[GcsimVirtualArtifactSetChoice, ...]:
    """Join the active engine capability catalog to localised project names."""

    store = store or GcsimEngineStore()
    try:
        installation = store.get_active_engine()
    except GcsimEngineStoreError:
        return ()
    if installation is None:
        return ()
    try:
        capabilities = load_gcsim_artifact_set_catalog(installation.path)
    except (GcsimArtifactSetCatalogError, OSError, ValueError):
        return ()

    preferred = normalize_artifact_set_lang(language)
    rows: tuple[sqlite3.Row, ...] = ()
    try:
        with sqlite3.connect(Path(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = tuple(
                conn.execute(
                    """
                    SELECT sets.set_uid,
                           sets.fallback_name,
                           preferred.name AS preferred_name,
                           english.name AS english_name
                    FROM artifact_sets AS sets
                    LEFT JOIN artifact_set_names AS preferred
                      ON preferred.set_uid = sets.set_uid AND preferred.lang = ?
                    LEFT JOIN artifact_set_names AS english
                      ON english.set_uid = sets.set_uid AND english.lang = 'en-us'
                    ORDER BY sets.set_uid
                    """,
                    (preferred,),
                ).fetchall()
            )
    except sqlite3.Error:
        rows = ()

    names_by_key: dict[str, tuple[str, str]] = {}
    for row in rows:
        set_uid = str(row["set_uid"] or "").strip()
        display_name = str(
            row["preferred_name"]
            or row["english_name"]
            or row["fallback_name"]
            or set_uid
        ).strip()
        for candidate in (set_uid, row["fallback_name"], row["english_name"]):
            normalized = _normalized_catalog_key(str(candidate or ""))
            if normalized:
                names_by_key.setdefault(normalized, (set_uid, display_name))

    choices: list[GcsimVirtualArtifactSetChoice] = []
    for item in capabilities.sets:
        if not item.two_piece_modeled:
            continue
        set_uid, display_name = names_by_key.get(
            _normalized_catalog_key(item.key),
            (item.key, item.key),
        )
        icon_path = PROJECT_ROOT / "assets" / "artifact_sets" / f"{set_uid}_1.png"
        choices.append(
            GcsimVirtualArtifactSetChoice(
                set_uid=set_uid,
                display_name=display_name,
                gcsim_key=item.key,
                two_piece_available=True,
                four_piece_available=bool(item.complete_four_piece_modeled),
                icon_path=str(icon_path) if icon_path.is_file() else "",
            )
        )
    return tuple(sorted(choices, key=lambda item: item.display_name.casefold()))


def parse_character_catalog(source: str) -> Iterable[GcsimCatalogCharacter]:
    for enum_name, body in _catalog_entries(source):
        key = _string_field(body, "Key")
        weapon_type = _weapon_type(body)
        if not key or not weapon_type:
            continue
        yield GcsimCatalogCharacter(
            gcsim_key=key,
            display_name=_display_name(key, enum_name),
            weapon_type=weapon_type,
            icon_name=_string_field(body, "IconName"),
        )


def parse_weapon_catalog(source: str) -> Iterable[GcsimCatalogWeapon]:
    for enum_name, body in _catalog_entries(source):
        key = _string_field(body, "Key")
        weapon_type = _weapon_type(body)
        if not key or not weapon_type:
            continue
        yield GcsimCatalogWeapon(
            gcsim_key=key,
            display_name=_display_name(key, enum_name),
            weapon_type=weapon_type,
            icon_name=_string_field(body, "ImageName"),
        )


def compatible_weapons(
    character: GcsimCatalogCharacter,
    weapons: Iterable[GcsimCatalogWeapon],
) -> tuple[GcsimCatalogWeapon, ...]:
    return tuple(item for item in weapons if item.weapon_type == character.weapon_type)


def max_virtual_promote_level(level: int) -> int:
    """Highest character ascension phase that can legally own ``level``.

    At an ascension boundary the virtual editor intentionally chooses the
    post-ascension state: 20 -> phase 1, ..., 80 -> phase 6.
    """

    normalized = int(level)
    if not 1 <= normalized <= 100:
        raise ValueError("character level must be between 1 and 100")
    for minimum_level, phase in _MAX_ASCENSION_BY_MINIMUM_LEVEL:
        if normalized >= minimum_level:
            return phase
    raise AssertionError("unreachable virtual ascension level")


def max_virtual_talent_level(level: int) -> int:
    """Maximum base N/E/Q level for the derived virtual ascension phase."""

    return _MAX_TALENT_BY_ASCENSION[max_virtual_promote_level(level)]


def _catalog_entries(source: str) -> Iterable[tuple[str, str]]:
    for match in _CATALOG_ENTRY_RE.finditer(source or ""):
        yield match.group("enum"), match.group("body")


def _string_field(body: str, field: str) -> str:
    match = re.search(_STRING_FIELD_RE.format(field=re.escape(field)), body, re.MULTILINE)
    return match.group("value").strip() if match else ""


def _weapon_type(body: str) -> str:
    match = _WEAPON_CLASS_RE.search(body)
    return _WEAPON_TYPES.get(match.group("value"), "") if match else ""


def _display_name(key: str, enum_name: str) -> str:
    # The installed engine catalog is the authority.  Keep its stable key visible;
    # enum casing merely makes the utilitarian picker easier to scan.
    return enum_name or key


def _normalized_catalog_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())
