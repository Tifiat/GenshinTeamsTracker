import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any


def stable_hash(data: Any) -> str:
    encoded = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_stat_value_for_fingerprint(value: Any) -> str:
    text = str(value if value is not None else "").strip().replace("%", "").replace(",", ".")
    if not text:
        return ""

    try:
        decimal = Decimal(text)
    except InvalidOperation:
        return text

    normalized = format(decimal.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def artifact_content_fingerprint(
    *,
    set_uid: str | None,
    pos: Any,
    rarity: Any,
    level: Any,
    main_property_type: Any,
    main_property_value: Any,
    substats: list[dict[str, Any]],
) -> str:
    contents = _normalized_artifact_contents(
        pos=pos,
        rarity=rarity,
        level=level,
        main_property_type=main_property_type,
        main_property_value=main_property_value,
        substats=substats,
    )

    payload = {
        "set_uid": str(set_uid or "").strip(),
        **contents,
    }

    return stable_hash(payload)


def artifact_source_content_fingerprint(
    *,
    set_id: Any,
    pos: Any,
    rarity: Any,
    level: Any,
    main_property_type: Any,
    main_property_value: Any,
    substats: list[dict[str, Any]],
) -> str | None:
    """Fingerprint source-observed contents without requiring a canonical set UID."""
    normalized_set_id = _int_or_none(set_id)
    if normalized_set_id is None:
        return None

    payload = {
        "source_set_id": normalized_set_id,
        **_normalized_artifact_contents(
            pos=pos,
            rarity=rarity,
            level=level,
            main_property_type=main_property_type,
            main_property_value=main_property_value,
            substats=substats,
        ),
    }
    return stable_hash(payload)


def _normalized_artifact_contents(
    *,
    pos: Any,
    rarity: Any,
    level: Any,
    main_property_type: Any,
    main_property_value: Any,
    substats: list[dict[str, Any]],
) -> dict[str, Any]:
    fingerprint_substats = []
    for substat in substats:
        property_type = _int_or_none(substat.get("property_type"))
        if property_type is None:
            continue
        fingerprint_substats.append(
            {
                "property_type": property_type,
                "value": normalize_stat_value_for_fingerprint(substat.get("value")),
            }
        )

    return {
        "pos": _int_or_none(pos),
        "rarity": _int_or_none(rarity),
        "level": _int_or_none(level),
        "main_property": {
            "property_type": _int_or_none(main_property_type),
            "value": normalize_stat_value_for_fingerprint(main_property_value),
        },
        "substats": sorted(
            fingerprint_substats,
            key=lambda item: (
                item["property_type"],
                item["value"],
            ),
        ),
    }
