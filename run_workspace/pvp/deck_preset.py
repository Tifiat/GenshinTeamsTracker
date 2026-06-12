from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

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
)


PVP_DECK_PRESET_SCHEMA_VERSION = 1
PVP_DECK_PRESET_KIND = "gtt.pvp_deck_preset"
DEFAULT_PVP_DECK_PRESET_DIR = Path("data") / "pvp" / "decks"


class DeckPresetError(ValueError):
    """Raised when a PvP deck preset cannot be created, parsed, or saved."""


@dataclass(frozen=True, slots=True)
class PvpDeckPresetWeaponRef:
    weapon_fingerprint: str = ""
    weapon_id: str = ""
    weapon_type: str = ""
    rarity: int | None = None
    level: int | None = None
    refinement: int | None = None
    count: int | None = None

    @property
    def key(self) -> str:
        return self.weapon_fingerprint or weapon_stack_key(
            weapon_id=self.weapon_id,
            weapon_type=self.weapon_type,
            rarity=self.rarity,
            level=self.level,
            refinement=self.refinement,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "weapon_fingerprint": self.weapon_fingerprint,
            "weapon_id": self.weapon_id,
            "weapon_type": self.weapon_type,
            "rarity": self.rarity,
            "level": self.level,
            "refinement": self.refinement,
            "count": self.count,
        }


@dataclass(frozen=True, slots=True)
class PvpDeckPreset:
    deck_id: str
    name: str
    character_ids: tuple[str, ...] = ()
    weapon_refs: tuple[PvpDeckPresetWeaponRef, ...] = ()
    ruleset_id: str = FREE_DRAFT_V0_RULESET_ID
    schema_version: int = PVP_DECK_PRESET_SCHEMA_VERSION
    kind: str = PVP_DECK_PRESET_KIND
    created_at_utc: str = ""
    updated_at_utc: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "deck_id": self.deck_id,
            "name": self.name,
            "ruleset_id": self.ruleset_id,
            "character_ids": list(self.character_ids),
            "weapon_refs": [item.to_dict() for item in self.weapon_refs],
            "created_at_utc": self.created_at_utc,
            "updated_at_utc": self.updated_at_utc,
        }
        payload.update(dict(sorted(self.extra.items())))
        return payload


def create_deck_preset_from_account_assets(
    character_assets: Iterable[Mapping[str, Any]],
    weapon_assets: Iterable[Mapping[str, Any]],
    *,
    name: str = "",
    deck_id: str = "",
    now: datetime | None = None,
) -> PvpDeckPreset:
    character_ids = tuple(
        dict.fromkeys(
            character_id
            for character_id in (
                character_id_from_asset(asset) for asset in character_assets
            )
            if character_id
        )
    )
    weapon_refs = tuple(
        {
            ref.key: ref
            for ref in (
                weapon_ref_from_asset(asset) for asset in weapon_assets
            )
            if ref is not None and ref.key
        }.values()
    )
    if not character_ids and not weapon_refs:
        raise DeckPresetError("Cannot create a deck preset from an empty account.")

    stamp = _utc_stamp(now)
    resolved_deck_id = _safe_deck_id(deck_id) or f"deck-{uuid.uuid4().hex[:12]}"
    return PvpDeckPreset(
        deck_id=resolved_deck_id,
        name=_text(name) or "New Deck",
        character_ids=character_ids,
        weapon_refs=weapon_refs,
        created_at_utc=stamp,
        updated_at_utc=stamp,
    )


def rename_deck_preset(
    preset: PvpDeckPreset,
    name: str,
    *,
    now: datetime | None = None,
) -> PvpDeckPreset:
    return replace(
        preset,
        name=_text(name) or preset.name,
        updated_at_utc=_utc_stamp(now),
    )


def update_deck_preset_selection(
    preset: PvpDeckPreset,
    *,
    character_ids: Iterable[Any],
    weapon_refs: Iterable[PvpDeckPresetWeaponRef],
    now: datetime | None = None,
) -> PvpDeckPreset:
    unique_character_ids = tuple(
        dict.fromkeys(_text(item) for item in character_ids if _text(item))
    )
    unique_weapon_refs = tuple(
        {
            ref.key: ref
            for ref in weapon_refs
            if isinstance(ref, PvpDeckPresetWeaponRef) and ref.key
        }.values()
    )
    return replace(
        preset,
        character_ids=unique_character_ids,
        weapon_refs=unique_weapon_refs,
        updated_at_utc=_utc_stamp(now),
    )


def load_deck_preset(path: str | Path) -> PvpDeckPreset:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DeckPresetError(f"Invalid deck preset JSON: {exc.msg}.") from exc
    except OSError as exc:
        raise DeckPresetError(f"Cannot read deck preset: {exc}.") from exc
    return deck_preset_from_mapping(payload)


def load_deck_presets(
    directory: str | Path = DEFAULT_PVP_DECK_PRESET_DIR,
) -> list[PvpDeckPreset]:
    root = Path(directory)
    if not root.exists():
        return []
    presets: list[PvpDeckPreset] = []
    for path in sorted(root.glob("*.json")):
        try:
            preset = load_deck_preset(path)
        except DeckPresetError:
            continue
        presets.append(preset)
    presets.sort(key=lambda item: (item.name.casefold(), item.deck_id))
    return presets


def save_deck_preset(
    preset: PvpDeckPreset,
    directory: str | Path = DEFAULT_PVP_DECK_PRESET_DIR,
) -> Path:
    deck_id = _safe_deck_id(preset.deck_id)
    if not deck_id:
        raise DeckPresetError("Deck preset deck_id is required.")
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{deck_id}.json"
    path.write_text(deck_preset_to_json_text(preset), encoding="utf-8")
    return path


def delete_deck_preset(
    deck_id: str,
    directory: str | Path = DEFAULT_PVP_DECK_PRESET_DIR,
) -> bool:
    safe_id = _safe_deck_id(deck_id)
    if not safe_id:
        return False
    path = Path(directory) / f"{safe_id}.json"
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def deck_preset_to_json_text(preset: PvpDeckPreset, *, indent: int = 2) -> str:
    return json.dumps(preset.to_dict(), ensure_ascii=False, indent=indent) + "\n"


def deck_preset_from_mapping(payload: Mapping[str, Any]) -> PvpDeckPreset:
    if not isinstance(payload, Mapping):
        raise DeckPresetError("Deck preset JSON root must be an object.")
    schema_version = _optional_int(payload.get("schema_version"))
    if schema_version != PVP_DECK_PRESET_SCHEMA_VERSION:
        raise DeckPresetError(
            f"Deck preset schema_version must be {PVP_DECK_PRESET_SCHEMA_VERSION}."
        )
    kind = _text(payload.get("kind"))
    if kind != PVP_DECK_PRESET_KIND:
        raise DeckPresetError(f"Deck preset kind must be {PVP_DECK_PRESET_KIND!r}.")

    character_ids = payload.get("character_ids", [])
    if not isinstance(character_ids, list):
        raise DeckPresetError("Deck preset character_ids must be a list.")
    weapon_refs = payload.get("weapon_refs", [])
    if not isinstance(weapon_refs, list):
        raise DeckPresetError("Deck preset weapon_refs must be a list.")

    known = {
        "schema_version",
        "kind",
        "deck_id",
        "name",
        "ruleset_id",
        "character_ids",
        "weapon_refs",
        "created_at_utc",
        "updated_at_utc",
    }
    return PvpDeckPreset(
        schema_version=schema_version,
        kind=kind,
        deck_id=_safe_deck_id(payload.get("deck_id")),
        name=_text(payload.get("name")),
        ruleset_id=_text(payload.get("ruleset_id")) or FREE_DRAFT_V0_RULESET_ID,
        character_ids=tuple(
            dict.fromkeys(_text(item) for item in character_ids if _text(item))
        ),
        weapon_refs=tuple(
            {
                ref.key: ref
                for ref in (
                    deck_preset_weapon_ref_from_mapping(item)
                    for item in weapon_refs
                )
                if ref.key
            }.values()
        ),
        created_at_utc=_text(payload.get("created_at_utc")),
        updated_at_utc=_text(payload.get("updated_at_utc")),
        extra={str(key): value for key, value in payload.items() if key not in known},
    )


def deck_preset_weapon_ref_from_mapping(value: Any) -> PvpDeckPresetWeaponRef:
    if not isinstance(value, Mapping):
        raise DeckPresetError("Deck preset weapon_refs entries must be objects.")
    return PvpDeckPresetWeaponRef(
        weapon_fingerprint=_text(
            value.get("weapon_fingerprint")
            or value.get("source_key")
            or value.get("variant_key")
        ),
        weapon_id=_text(value.get("weapon_id") or value.get("id")),
        weapon_type=_text(value.get("weapon_type") or value.get("type_name")),
        rarity=_optional_int(value.get("rarity")),
        level=_optional_int(value.get("level")),
        refinement=_optional_int(value.get("refinement")),
        count=_optional_int(value.get("count") or value.get("known_count")),
    )


def deck_preset_to_draft_deck(
    preset: PvpDeckPreset,
    character_assets: Iterable[Mapping[str, Any]],
    weapon_assets: Iterable[Mapping[str, Any]],
    *,
    player_nickname: str = "",
) -> DraftDeck:
    character_by_id = {
        character_id_from_asset(asset): asset
        for asset in character_assets
        if character_id_from_asset(asset)
    }
    weapon_by_key: dict[str, Mapping[str, Any]] = {}
    for asset in weapon_assets:
        ref = weapon_ref_from_asset(asset)
        if ref is not None and ref.key:
            weapon_by_key[ref.key] = asset

    characters = tuple(
        draft_character_from_asset(
            character_id=character_id,
            asset=character_by_id.get(character_id),
        )
        for character_id in preset.character_ids
    )
    weapons = tuple(
        draft_weapon_stack_from_asset(
            ref=weapon_ref,
            asset=weapon_by_key.get(weapon_ref.key),
        )
        for weapon_ref in preset.weapon_refs
    )
    exported_at = _utc_stamp()
    return DraftDeck(
        schema_version=DRAFT_DECK_SCHEMA_VERSION,
        kind=DRAFT_DECK_KIND,
        deck_name=preset.name,
        ruleset_ref=DraftDeckRulesetRef(
            ruleset_id=preset.ruleset_id or FREE_DRAFT_V0_RULESET_ID,
            ruleset_name=FREE_DRAFT_V0_RULESET_NAME,
        ),
        player=DraftDeckPlayer(nickname=_text(player_nickname)),
        source=DraftDeckSource(
            app="GenshinTeamsTracker",
            language="",
            exported_at_utc=exported_at,
            extra={
                "preset_id": preset.deck_id,
                "preset_kind": preset.kind,
                "module": "run_workspace.pvp.deck_preset",
            },
        ),
        characters=characters,
        weapons=weapons,
    )


def draft_character_from_asset(
    *,
    character_id: str,
    asset: Mapping[str, Any] | None,
) -> DraftCharacter:
    character = _asset_mapping(asset, "character")
    return DraftCharacter(
        character_id=_text(character_id),
        display_name=_text(character.get("name") or character.get("display_name")),
        element=_text(character.get("element") or character.get("element_name")),
        weapon_type=_weapon_type_text(character),
        rarity=_optional_int(character.get("rarity")),
        level=_optional_int(character.get("level")),
        constellation=_optional_int(character.get("constellation")),
    )


def draft_weapon_stack_from_asset(
    *,
    ref: PvpDeckPresetWeaponRef,
    asset: Mapping[str, Any] | None,
) -> DraftWeaponStack:
    weapon = _asset_mapping(asset, "weapon")
    metadata = _mapping(asset.get("metadata")) if isinstance(asset, Mapping) else {}
    return DraftWeaponStack(
        weapon_id=_text(weapon.get("id") or weapon.get("weapon_id") or ref.weapon_id),
        display_name=_text(weapon.get("name") or weapon.get("display_name")),
        weapon_type=_weapon_type_text(weapon) or ref.weapon_type,
        rarity=_optional_int(weapon.get("rarity")) or ref.rarity,
        level=_optional_int(weapon.get("level")) or ref.level,
        refinement=_optional_int(weapon.get("refinement")) or ref.refinement,
        count=(
            _optional_int(weapon.get("known_count"))
            or _optional_int(metadata.get("known_count"))
            or ref.count
        ),
    )


def character_id_from_asset(asset: Mapping[str, Any]) -> str:
    return _text(_asset_mapping(asset, "character").get("id"))


def weapon_ref_from_asset(
    asset: Mapping[str, Any],
) -> PvpDeckPresetWeaponRef | None:
    metadata = _mapping(asset.get("metadata"))
    weapon = _mapping(metadata.get("weapon"))
    weapon_id = _text(weapon.get("id") or weapon.get("weapon_id"))
    weapon_fingerprint = _text(
        weapon.get("weapon_fingerprint")
        or weapon.get("source_key")
        or weapon.get("variant_key")
        or metadata.get("weapon_fingerprint")
    )
    weapon_type = _weapon_type_identity_text(weapon)
    rarity = _optional_int(weapon.get("rarity"))
    level = _optional_int(weapon.get("level"))
    refinement = _optional_int(weapon.get("refinement"))
    count = _optional_int(weapon.get("known_count")) or _optional_int(
        metadata.get("known_count")
    )
    ref = PvpDeckPresetWeaponRef(
        weapon_fingerprint=weapon_fingerprint,
        weapon_id=weapon_id,
        weapon_type=weapon_type,
        rarity=rarity,
        level=level,
        refinement=refinement,
        count=count,
    )
    if not ref.key:
        return None
    return ref


def weapon_stack_key(
    *,
    weapon_id: Any,
    weapon_type: Any,
    rarity: Any,
    level: Any,
    refinement: Any,
) -> str:
    if not _text(weapon_id):
        return ""
    return "|".join(
        (
            _text(weapon_id),
            _text(weapon_type).casefold(),
            _text(rarity),
            _text(level),
            _text(refinement),
        )
    )


def _asset_mapping(
    asset: Mapping[str, Any] | None,
    key: str,
) -> dict[str, Any]:
    if not isinstance(asset, Mapping):
        return {}
    return _mapping(_mapping(asset.get("metadata")).get(key))


def _weapon_type_text(payload: Mapping[str, Any]) -> str:
    for key in ("type_name", "weapon_type_name", "weapon_type", "type"):
        value = _text(payload.get(key))
        if value:
            return value
    return ""


def _weapon_type_identity_text(payload: Mapping[str, Any]) -> str:
    for key in ("weapon_type", "type"):
        value = _text(payload.get(key))
        if value:
            return value
    for key in ("type_name", "weapon_type_name"):
        value = _text(payload.get(key))
        if value:
            return value
    return ""


def _safe_deck_id(value: Any) -> str:
    raw = _text(value)
    allowed = "".join(
        char
        for char in raw
        if char.isascii() and (char.isalnum() or char in {"-", "_"})
    )
    return allowed[:80]


def _utc_stamp(now: datetime | None = None) -> str:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()
