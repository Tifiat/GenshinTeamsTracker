from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


DRAFT_DECK_SCHEMA_VERSION = 1
DRAFT_DECK_KIND = "gtt.pvp_deck"
FREE_DRAFT_V0_RULESET_ID = "free_draft_v0"
FREE_DRAFT_V0_RULESET_NAME = "Free Draft v0"


class DeckLoadError(ValueError):
    """Raised when a deck JSON payload cannot be parsed as the v0 deck contract."""


@dataclass(frozen=True, slots=True)
class DraftDeckRulesetRef:
    ruleset_id: str = FREE_DRAFT_V0_RULESET_ID
    ruleset_name: str = FREE_DRAFT_V0_RULESET_NAME
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "ruleset_id": self.ruleset_id,
            "ruleset_name": self.ruleset_name,
        }
        payload.update(dict(sorted(self.extra.items())))
        return payload


@dataclass(frozen=True, slots=True)
class DraftDeckSource:
    app: str = ""
    language: str = "en"
    exported_at_utc: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "app": self.app,
            "language": self.language,
            "exported_at_utc": self.exported_at_utc,
        }
        payload.update(dict(sorted(self.extra.items())))
        return payload


@dataclass(frozen=True, slots=True)
class DraftDeckPlayer:
    nickname: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {"nickname": self.nickname}
        payload.update(dict(sorted(self.extra.items())))
        return payload


@dataclass(frozen=True, slots=True)
class DraftCharacter:
    character_id: str
    display_name: str
    element: str
    weapon_type: str
    rarity: int | None
    level: int | None
    constellation: int | None
    cost: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "display_name": self.display_name,
            "element": self.element,
            "weapon_type": self.weapon_type,
            "rarity": self.rarity,
            "level": self.level,
            "constellation": self.constellation,
            "cost": self.cost,
        }


@dataclass(frozen=True, slots=True)
class DraftWeaponStack:
    weapon_id: str
    display_name: str
    weapon_type: str
    rarity: int | None
    level: int | None
    refinement: int | None
    count: int | None
    cost: float | None = None

    @property
    def stack_key(self) -> str:
        """Natural exact-stack key; not a unique weapon instance id."""

        return "|".join(
            (
                self.weapon_id,
                _normalized_token(self.weapon_type),
                str(self.rarity or ""),
                str(self.level or ""),
                str(self.refinement or ""),
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "weapon_id": self.weapon_id,
            "display_name": self.display_name,
            "weapon_type": self.weapon_type,
            "rarity": self.rarity,
            "level": self.level,
            "refinement": self.refinement,
            "count": self.count,
            "cost": self.cost,
        }


@dataclass(frozen=True, slots=True)
class DraftDeck:
    schema_version: int
    kind: str
    deck_name: str
    ruleset_ref: DraftDeckRulesetRef = field(default_factory=DraftDeckRulesetRef)
    player: DraftDeckPlayer = field(default_factory=DraftDeckPlayer)
    source: DraftDeckSource = field(default_factory=DraftDeckSource)
    characters: tuple[DraftCharacter, ...] = ()
    weapons: tuple[DraftWeaponStack, ...] = ()

    @property
    def character_ids(self) -> set[str]:
        return {item.character_id for item in self.characters if item.character_id}

    @property
    def character_by_id(self) -> dict[str, DraftCharacter]:
        return {
            item.character_id: item
            for item in self.characters
            if item.character_id
        }

    @property
    def weapon_stack_by_key(self) -> dict[str, DraftWeaponStack]:
        return {
            item.stack_key: item
            for item in self.weapons
            if item.weapon_id
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "deck_name": self.deck_name,
            "ruleset_ref": self.ruleset_ref.to_dict(),
            "player": self.player.to_dict(),
            "source": self.source.to_dict(),
            "characters": [item.to_dict() for item in self.characters],
            "weapons": [item.to_dict() for item in self.weapons],
        }


def load_draft_deck(path: str | Path) -> DraftDeck:
    return load_draft_deck_from_json_text(Path(path).read_text(encoding="utf-8"))


def load_draft_deck_from_json_text(text: str) -> DraftDeck:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DeckLoadError(f"Invalid draft deck JSON: {exc.msg}.") from exc
    return draft_deck_from_mapping(payload)


def draft_deck_from_mapping(payload: Mapping[str, Any]) -> DraftDeck:
    if not isinstance(payload, Mapping):
        raise DeckLoadError("Draft deck JSON root must be an object.")

    schema_version = _optional_int(payload.get("schema_version"))
    if schema_version != DRAFT_DECK_SCHEMA_VERSION:
        raise DeckLoadError(
            f"Draft deck schema_version must be {DRAFT_DECK_SCHEMA_VERSION}."
        )
    kind = _text(payload.get("kind"))
    if kind != DRAFT_DECK_KIND:
        raise DeckLoadError(f"Draft deck kind must be {DRAFT_DECK_KIND!r}.")

    characters = payload.get("characters", [])
    if not isinstance(characters, list):
        raise DeckLoadError("Draft deck characters must be a list.")
    weapons = payload.get("weapons", [])
    if not isinstance(weapons, list):
        raise DeckLoadError("Draft deck weapons must be a list.")

    return DraftDeck(
        schema_version=schema_version,
        kind=kind,
        deck_name=_text(payload.get("deck_name")),
        ruleset_ref=_ruleset_ref_from_mapping(payload.get("ruleset_ref")),
        player=_player_from_mapping(payload.get("player")),
        source=_source_from_mapping(payload.get("source")),
        characters=tuple(_character_from_mapping(item) for item in characters),
        weapons=tuple(_weapon_stack_from_mapping(item) for item in weapons),
    )


def draft_deck_to_json_text(deck: DraftDeck, *, indent: int = 2) -> str:
    return json.dumps(deck.to_dict(), ensure_ascii=False, indent=indent) + "\n"


def _ruleset_ref_from_mapping(value: Any) -> DraftDeckRulesetRef:
    payload = value if isinstance(value, Mapping) else {}
    known = {"ruleset_id", "ruleset_name"}
    return DraftDeckRulesetRef(
        ruleset_id=_text(payload.get("ruleset_id")) or FREE_DRAFT_V0_RULESET_ID,
        ruleset_name=_text(payload.get("ruleset_name")) or FREE_DRAFT_V0_RULESET_NAME,
        extra={str(key): item for key, item in payload.items() if key not in known},
    )


def _source_from_mapping(value: Any) -> DraftDeckSource:
    payload = value if isinstance(value, Mapping) else {}
    known = {"app", "language", "exported_at_utc"}
    return DraftDeckSource(
        app=_text(payload.get("app")),
        language=_text(payload.get("language")) or "en",
        exported_at_utc=_text(payload.get("exported_at_utc")),
        extra={str(key): item for key, item in payload.items() if key not in known},
    )


def _player_from_mapping(value: Any) -> DraftDeckPlayer:
    payload = value if isinstance(value, Mapping) else {}
    known = {"nickname"}
    return DraftDeckPlayer(
        nickname=_text(payload.get("nickname")),
        extra={str(key): item for key, item in payload.items() if key not in known},
    )


def _character_from_mapping(value: Any) -> DraftCharacter:
    if not isinstance(value, Mapping):
        raise DeckLoadError("Draft deck character entries must be objects.")
    return DraftCharacter(
        character_id=_text(value.get("character_id")),
        display_name=_text(value.get("display_name")),
        element=_text(value.get("element")),
        weapon_type=_text(value.get("weapon_type")),
        rarity=_optional_int(value.get("rarity")),
        level=_optional_int(value.get("level")),
        constellation=_optional_int(value.get("constellation")),
        cost=_optional_float(value.get("cost")),
    )


def _weapon_stack_from_mapping(value: Any) -> DraftWeaponStack:
    if not isinstance(value, Mapping):
        raise DeckLoadError("Draft deck weapon entries must be objects.")
    return DraftWeaponStack(
        weapon_id=_text(value.get("weapon_id")),
        display_name=_text(value.get("display_name")),
        weapon_type=_text(value.get("weapon_type")),
        rarity=_optional_int(value.get("rarity")),
        level=_optional_int(value.get("level")),
        refinement=_optional_int(value.get("refinement")),
        count=_optional_int(value.get("count")),
        cost=_optional_float(value.get("cost")),
    )


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_token(value: Any) -> str:
    return _text(value).casefold()
