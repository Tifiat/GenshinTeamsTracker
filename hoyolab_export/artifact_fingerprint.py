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
    text = str(value or "").strip().replace("%", "").replace(",", ".")
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

    payload = {
        "set_uid": str(set_uid or "").strip(),
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

    return stable_hash(payload)
