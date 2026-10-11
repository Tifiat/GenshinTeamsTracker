"""Weapon roster constraints; inventory copies and assigned-team cost are separate.

The bounded prose fallback belongs only to the inspected exact Cup version.
Structured roster bounds always take precedence. No translated UI text is parsed.
"""
from __future__ import annotations

from decimal import Decimal
import re
from typing import Any, Mapping, Sequence


CUP_SOURCE = {
    "system_id": "6ac54cc57032007b0dd5e4f9",
    "root_id": "6953c08267a24684c387795c",
    "updated_at": "2026-10-06T19:34:41.433Z",
}
REGULATION_URL = "https://docs.google.com/document/d/1sBlA2ybrqqp35J66XbwejBx8S1z-Ehk-fwfd8asKhJI/edit?tab=t.0"
# The user quoted this concise statement; the parser also accepts the inspected
# original paragraph below. Neither is assembled from localized UI text.
CUP_WEAPON_TEXT = (
    "Регламент Abyss Fast Soup 23: оружие ≤155; общий пул 130 + 25 только для "
    "оружия стоимостью ≤14; оружие ≥15 не расходует эти 25."
)
CUP_WEAPON_PARAGRAPH = (
    "Баланс оружия. Максимальная стоимость ростера с оружием - 155 единиц.\n"
    "1. Термины:\n"
    "Дорогое оружие - это оружие стоимостью 15 и более очков.\n"
    "Дешевое оружие - это оружие стоимостью 14 и менее очков.\n"
    "2. На дорогое оружие можно потратить максимум 130 очков, оставшиеся 25 - только на дешевое.\n"
    "3. Дешевое оружие можно добавлять в ростер в счет стоимости, выделенной под дорогое оружие (130).\n"
    "4. Дорогое оружие не может быть выбрано в счет стоимости, выделенной под дешевое оружие (25)."
)
_BUDGET_TEXT = re.compile(
    r"(?:регламент [^:;]{1,128}: )?оружие (?:≤|<=)\s*(?P<maximum>\d+); "
    r"общий пул (?P<general>\d+)\s*\+\s*(?P<reserve>\d+) только для "
    r"оружия стоимостью (?:≤|<=)\s*(?P<cheap>\d+); "
    r"оружие (?:≥|>=)\s*(?P<expensive>\d+) не расходует эти (?P<repeat>\d+)\.?",
    re.IGNORECASE,
)
_BUDGET_PARAGRAPH = re.compile(
    r"(?:баланс оружия\. )?максимальная стоимость ростера с оружием\s*[-–—]\s*(?P<maximum>\d+) единиц\. "
    r"термины: дорогое оружие\s*[-–—]\s*это оружие стоимостью (?P<expensive>\d+) и более очков\. "
    r"дешевое оружие\s*[-–—]\s*это оружие стоимостью (?P<cheap>\d+) и менее очков\. "
    r"на дорогое оружие можно потратить максимум (?P<general>\d+) очков, "
    r"оставшиеся (?P<reserve>\d+)\s*[-–—]\s*только на дешевое\. "
    r"дешевое оружие можно добавлять в ростер в счет стоимости, выделенной под дорогое оружие "
    r"\((?P<repeat_general>\d+)\)\. дорогое оружие не может быть выбрано в счет стоимости, "
    r"выделенной под дешевое оружие \((?P<repeat>\d+)\)\.", re.IGNORECASE,
)


def parse_weapon_budget_text(text: str) -> dict[str, int]:
    """Recognize the supported two-pool rule, otherwise fail without guessing."""
    if not isinstance(text, str) or len(text) > 4096:
        raise ValueError("Unsupported weapon budget text")
    clean = " ".join(re.sub(r"(?m)^[ \t]*\d+\.[ \t]+", "", text).split()).replace("ё", "е")
    match = _BUDGET_TEXT.fullmatch(clean) or _BUDGET_PARAGRAPH.fullmatch(clean)
    if match is None:
        raise ValueError("Unsupported weapon budget text")
    values = {key: int(value) for key, value in match.groupdict().items()}
    if (values["general"] <= 0 or values["reserve"] <= 0
            or values["maximum"] != values["general"] + values["reserve"]
            or values["repeat"] != values["reserve"]
            or values.get("repeat_general", values["general"]) != values["general"]
            or values["expensive"] != values["cheap"] + 1):
        raise ValueError("Inconsistent weapon budget text")
    return {"minimum": 0, "maximum": values["maximum"],
            "general_pool": values["general"], "cheap_pool": values["reserve"],
            "cheap_max": values["cheap"], "expensive_min": values["expensive"]}


_CUP_LIMITS = parse_weapon_budget_text(CUP_WEAPON_PARAGRAPH)


def weapon_roster_policy(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    low, high = snapshot["bounds"]["engines"]["cost"]
    if low or high:
        return {"minimum": low, "maximum": high, "general_pool": None,
                "cheap_pool": None, "cheap_max": None, "expensive_min": None,
                "source_kind": "api", "source_title": snapshot["source"]["title"],
                "url": "", "checked_at": ""}
    if all(snapshot["source"].get(key) == value for key, value in CUP_SOURCE.items()):
        return {**_CUP_LIMITS, "source_kind": "regulation", "source_title": "Abyss Fast Soup 23",
                "url": REGULATION_URL, "checked_at": "2026-10-10"}
    return None


def _plain(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def build_weapon_roster_report(snapshot: Mapping[str, Any], weapon_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """One base/refinement price per selected roster entry, including zero prices."""
    policy = weapon_roster_policy(snapshot)
    known = Decimal(0)
    expensive = Decimal(0)
    unknown = unclassified = 0
    for row in weapon_rows:
        price = row["base_unit_cost"]
        if price is None:
            unknown += 1
            continue
        cost = Decimal(str(price))
        known += cost
        if policy and policy["expensive_min"] is not None:
            if cost >= Decimal(str(policy["expensive_min"])):
                expensive += cost
            elif cost > Decimal(str(policy["cheap_max"])):
                unclassified += 1
    total = None if unknown else _plain(known)
    expensive_total = None if unknown or unclassified else _plain(expensive)
    checks = []
    if policy:
        checks.append(_check("weapon_roster_cost", total, _plain(known),
                             policy["minimum"], policy["maximum"]))
        if policy["general_pool"] is not None:
            checks.append(_check("weapon_roster_expensive", expensive_total, _plain(expensive),
                                 0, policy["general_pool"]))
    return {"policy": policy, "total": total, "known_total": _plain(known),
            "unknown_price_count": unknown, "unclassified_count": unclassified,
            "expensive_total": expensive_total, "known_expensive_total": _plain(expensive),
            "checks": checks}


def _check(code: str, actual: int | float | None, known: int | float,
           minimum: int | float, maximum: int | float) -> dict[str, Any]:
    status = "unknown" if actual is None else "fail" if (
        actual < minimum or maximum > 0 and actual > maximum
    ) else "pass"
    return {"code": code, "actual": actual, "known_actual": known,
            "minimum": minimum, "maximum": maximum, "status": status}
