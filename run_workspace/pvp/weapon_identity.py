from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .deck import DraftWeaponStack


@dataclass(frozen=True, slots=True)
class WeaponObservedStackRef:
    """PvP reference to one account observed weapon stack, not a copy id."""

    weapon_fingerprint: str = ""
    weapon_id: str = ""
    weapon_type: str = ""
    rarity: int | None = None
    level: int | None = None
    refinement: int | None = None
    count: int | None = None

    @property
    def key(self) -> str:
        return self.weapon_fingerprint or weapon_observed_stack_key(
            weapon_id=self.weapon_id,
            weapon_type=self.weapon_type,
            rarity=self.rarity,
            level=self.level,
            refinement=self.refinement,
        )

    @property
    def known_count(self) -> int | None:
        return self.count

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


def weapon_observed_stack_ref_from_asset(
    asset: Mapping[str, Any],
) -> WeaponObservedStackRef | None:
    metadata = _mapping(asset.get("metadata")) if isinstance(asset, Mapping) else {}
    weapon = _mapping(metadata.get("weapon"))
    if not weapon and isinstance(asset, Mapping):
        weapon = _mapping(asset.get("weapon"))

    weapon_id = _text(weapon.get("weapon_id") or weapon.get("id"))
    weapon_fingerprint = _text(
        weapon.get("weapon_fingerprint")
        or weapon.get("source_key")
        or weapon.get("variant_key")
        or metadata.get("weapon_fingerprint")
        or metadata.get("source_key")
    )
    ref = WeaponObservedStackRef(
        weapon_fingerprint=weapon_fingerprint,
        weapon_id=weapon_id,
        weapon_type=_weapon_type_identity_text(weapon),
        rarity=_optional_int(weapon.get("rarity")),
        level=_optional_int(weapon.get("level")),
        refinement=_optional_int(weapon.get("refinement")),
        count=_first_optional_int(weapon.get("known_count"), metadata.get("known_count")),
    )
    if not ref.key:
        return None
    return ref


def weapon_observed_stack_refs_from_assets(
    assets: Iterable[Mapping[str, Any]],
) -> tuple[WeaponObservedStackRef, ...]:
    return dedupe_weapon_observed_stack_refs(
        ref
        for ref in (weapon_observed_stack_ref_from_asset(asset) for asset in assets)
        if ref is not None
    )


def dedupe_weapon_observed_stack_refs(
    refs: Iterable[WeaponObservedStackRef],
) -> tuple[WeaponObservedStackRef, ...]:
    return tuple(
        {
            ref.key: ref
            for ref in refs
            if isinstance(ref, WeaponObservedStackRef) and ref.key
        }.values()
    )


def weapon_observed_stack_ref_from_mapping(value: Any) -> WeaponObservedStackRef:
    if not isinstance(value, Mapping):
        raise ValueError("Weapon observed stack ref entries must be objects.")
    return WeaponObservedStackRef(
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
        count=_first_optional_int(value.get("count"), value.get("known_count")),
    )


def draft_weapon_stack_from_observed_ref(
    *,
    ref: WeaponObservedStackRef,
    asset: Mapping[str, Any] | None,
) -> DraftWeaponStack:
    weapon = _asset_mapping(asset, "weapon")
    metadata = _mapping(asset.get("metadata")) if isinstance(asset, Mapping) else {}
    return DraftWeaponStack(
        weapon_id=_text(weapon.get("id") or weapon.get("weapon_id") or ref.weapon_id),
        display_name=_text(weapon.get("name") or weapon.get("display_name")),
        weapon_type=_weapon_type_text(weapon) or ref.weapon_type,
        rarity=_first_optional_int(weapon.get("rarity"), ref.rarity),
        level=_first_optional_int(weapon.get("level"), ref.level),
        refinement=_first_optional_int(weapon.get("refinement"), ref.refinement),
        count=_first_optional_int(
            weapon.get("known_count"),
            metadata.get("known_count"),
            ref.count,
        ),
    )


def weapon_observed_stack_key(
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


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_optional_int(*values: Any) -> int | None:
    for value in values:
        result = _optional_int(value)
        if result is not None:
            return result
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


__all__ = [
    "WeaponObservedStackRef",
    "dedupe_weapon_observed_stack_refs",
    "draft_weapon_stack_from_observed_ref",
    "weapon_observed_stack_key",
    "weapon_observed_stack_ref_from_asset",
    "weapon_observed_stack_ref_from_mapping",
    "weapon_observed_stack_refs_from_assets",
]
