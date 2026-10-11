"""Read public Abyss rules into a research report, not an executable GTT ruleset.

No cookies, browser, account modules, source-script execution or disk cache.
Output goes to stdout; callers own any explicitly redirected research output.
See docs/handoff/PVP_ABYSS_SOURCE_AUDIT.md for field semantics and limitations.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import Any
from urllib.request import Request, urlopen

API = "https://abyss.darte.gg/api/abyss"
MAX_RESPONSE_BYTES = 4_000_000


def get_public_json(path: str) -> tuple[Any, str]:
    request = Request(API + path, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urlopen(request, timeout=25) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Public rules response exceeds research limit")
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _costs(values: Any, count: int) -> list[int | float]:
    if not isinstance(values, list) or len(values) != count:
        raise ValueError(f"Expected exactly {count} cost slots; source schema changed")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise ValueError("Cost slots must contain finite numbers")
    return list(values)


def _catalog(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        source_id = row["_id"]
        if source_id in result:
            raise ValueError("Duplicate source catalog id")
        result[source_id] = row
    return result


def normalize_source(system: dict[str, Any], agents: list[dict[str, Any]],
                     engines: list[dict[str, Any]]) -> dict[str, Any]:
    """Map known IDs/price slots; preserve declarations without claiming enforcement."""
    agent_map, engine_map = _catalog(agents), _catalog(engines)

    def game_id(source_id: str, catalog: dict[str, dict[str, Any]]) -> str:
        row = catalog.get(source_id)
        value = str(row.get("enkaId") or "") if row else ""
        if not value.isdigit():
            raise ValueError(f"Unmapped source id: {source_id}")
        return value

    def weapon_prices(row: dict[str, Any]) -> dict[str, Any]:
        values = _costs(row["costs"], 6)
        return {"costs_by_refinement": {str(i + 1): value for i, value in enumerate(values[:5])},
                "off_specialty_cost": values[5]}

    def character_ref(source_id: str) -> dict[str, Any]:
        return {"character_id": game_id(source_id, agent_map), "source_id": source_id,
                "source_attribute": agent_map[source_id].get("attribute")}

    characters = []
    for row in system["costs"]["agents"]:
        source_id = row["agent"]
        values = _costs(row["costs"], 9)
        characters.append({
            **character_ref(source_id),
            "name": agent_map[source_id].get("name", {}),
            "costs_by_constellation": {str(i): value for i, value in enumerate(values[:7])},
            "level_adjustment": {"percent": values[7], "flat": values[8],
                                 "starts_at": 95, "double_at": 100, "rounding": "ceil"},
            "disable_french_difference_cap": row.get("disableCostLimit", False),
            "specification_raw": row.get("specification"),
        })
    weapons = []
    for row in system["costs"]["engines"]:
        source_id = row["engine"]
        weapons.append({
            "weapon_id": game_id(source_id, engine_map),
            "name": engine_map[source_id].get("title", {}),
            **weapon_prices(row),
            "character_overrides": [{**character_ref(value["agent"]),
                                     **weapon_prices(value)} for value in row.get("bis", [])],
        })
    variants = {(row["character_id"], row["source_attribute"]) for row in characters}
    if len(variants) != len(characters) or len({row["weapon_id"] for row in weapons}) != len(weapons):
        raise ValueError("Duplicate mapped variant; an explicit source adapter is required")

    bundles = []
    for row in system["costs"].get("agentsBundles", []):
        bundles.append({"cost": row["cost"], "characters": [
            {**character_ref(value["agent"]),
             "constellation_min": value["mindscape"],
             "constellation_max": value.get("mindscapeMax")}
            for value in row["agents"]]})
    # Preserve complete source rule declarations. Required-agent IDs are the
    # only catalog IDs in these four observed rule types; tier numbers stay tiers.
    preset_rules = json.loads(json.dumps(system.get("preset", {}).get("rules", [])))
    for rule in preset_rules:
        if rule.get("type") == "required_agents":
            rule["agents"] = [character_ref(value) for value in rule["agents"]]

    return {
        "format": "abyss-source-research-v1",
        "execution_ready": False,
        "source": {"system_id": system["_id"], "root_id": system.get("root"),
                   "predecessor_id": system.get("ref"), "updated_at": system.get("updatedAt"),
                   "archived": system.get("archived")},
        "title": system["main"]["title"],
        "source_mode": system["main"].get("mode"),
        "cost_mode": system["costs"]["system"],
        "characters": characters, "weapons": weapons, "character_bundles": bundles,
        "tiers": system["costs"].get("tiers", []),
        "french_difference_cap": system["costs"].get("costLimit"),
        "draft_bounds_raw": system.get("draft", {}),
        "preset_rules_with_game_ids": preset_rules,
        "phases_raw": {key: system.get(key) for key in
                       ("phaseStage", "phasePicks", "phaseTeams", "phaseMatch")},
        "limitations": [
            "Not TournamentRulesetV1: percentage level costs need a model extension.",
            "Traveler variants retain source attributes; GTT currently excludes Traveler.",
            "Preset matching/reuse and zero-bound enforcement are not verified.",
            "Source-only declarations and phase references are preserved, not executed.",
            "Tournament document overrides/conflicts require a separate explicit layer.",
        ],
    }


def fetch_source(system_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{24}", system_id):
        raise ValueError("Use a system _id returned by the public list")
    system, system_hash = get_public_json(f"/draft_systems/{system_id}")
    if system.get("_id") != system_id:
        raise ValueError("Returned system version differs from the selected id")
    agents, agents_hash = get_public_json("/agents")
    engines, engines_hash = get_public_json("/engines")
    result = normalize_source(system, agents, engines)
    result["source"].update({
        "api_base": API, "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sha256": {"system": system_hash, "agents": agents_hash, "engines": engines_hash},
    })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--system-id", help="Exact public rules version to inspect")
    choice.add_argument("--list", action="store_true", help="List all public systems, including pagination")
    args = parser.parse_args()
    if args.system_id:
        result = fetch_source(args.system_id)
    else:
        result = []
        skip = 0
        while True:
            page, _ = get_public_json(f"/draft_systems?skip={skip}&limit=5")
            items = page["items"]
            for item in items:
                result.append({"system_id": item["_id"], "title": item["main"]["title"],
                               "root_id": item.get("root"), "updated_at": item.get("updatedAt")})
            skip += len(items)
            if skip >= page["count"]:
                break
            if not items or skip > 1000:
                raise ValueError("Public list pagination did not finish within research limit")
    print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
