"""Pinned public Abyss rules and conservative, pure draft-deck evaluation.

Only allowlisted public rule fields enter the snapshot. An evaluation describes
known prices and declarations; it does not claim server constraint parity.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
import math
import re
from typing import Any, Mapping

from .deck import DraftDeck


FORMAT = "gtt.pvp.abyss_rules.v1"
SOURCE_FAMILY = "abyss.darte.gg"
MAX_SNAPSHOT_BYTES = 250_000
_SOURCE_ID = re.compile(r"[0-9a-f]{24}\Z")
_ELEMENT_ATTRIBUTE = {
    "ANEMO": 11, "CRYO": 12, "DENDRO": 13, "ELECTRO": 14,
    "GEO": 15, "HYDRO": 16, "PYRO": 17,
}


class AbyssRulesError(ValueError):
    """The source or saved snapshot cannot safely be interpreted."""


class AbyssUnsupportedCostError(AbyssRulesError):
    code = "abyss_cost_mode_unsupported"


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AbyssRulesError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise AbyssRulesError(f"{label} must be a list")
    return value


def _text(value: Any, label: str, *, optional: bool = False) -> str:
    if optional and value is None:
        return ""
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise AbyssRulesError(f"{label} must be nonempty text")
    return value.strip()


def _source_id(value: Any, label: str) -> str:
    result = _text(value, label)
    if not _SOURCE_ID.fullmatch(result):
        raise AbyssRulesError(f"{label} must be a 24-character source id")
    return result


def _names(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    source = _object(value, "character names")
    result = {}
    for language in ("en", "ru"):
        name = source.get(language)
        if name is not None:
            result[language] = _text(name, f"{language} character name")
    return result


def _preflight(value: Any, depth: int = 0, nodes: list[int] | None = None) -> None:
    """Bound untrusted saved JSON before walking individual contract fields."""
    if nodes is None:
        nodes = [0]
    nodes[0] += 1
    if depth > 12 or nodes[0] > 20_000:
        raise AbyssRulesError("Abyss snapshot exceeds structure limit")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 64:
                raise AbyssRulesError("Invalid snapshot key")
            _preflight(item, depth + 1, nodes)
    elif isinstance(value, list):
        for item in value:
            _preflight(item, depth + 1, nodes)
    elif value is None or type(value) is bool:
        return
    elif type(value) is str:
        if len(value) > 512:
            raise AbyssRulesError("Snapshot text exceeds limit")
    elif type(value) in (int, float):
        if not math.isfinite(value):
            raise AbyssRulesError("Snapshot contains nonfinite number")
    else:
        raise AbyssRulesError("Snapshot contains unsupported value")


def _number(value: Any, label: str) -> int | float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise AbyssRulesError(f"{label} must be a finite number")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise AbyssRulesError(f"{label} must be an integer >= {minimum}")
    return value


def _slots(value: Any, count: int, label: str) -> list[int | float]:
    rows = _list(value, label)
    if len(rows) != count:
        raise AbyssRulesError(f"{label} requires {count} slots")
    return [_number(item, label) for item in rows]


def _ref(source_id: Any, catalog: Mapping[str, Mapping[str, Any]], label: str) -> dict[str, Any]:
    source_id = _source_id(source_id, label)
    row = catalog.get(source_id)
    if row is None:
        raise AbyssRulesError(f"Unmapped {label}: {source_id}")
    game_id = str(row.get("enkaId") or "")
    if not game_id.isdigit():
        raise AbyssRulesError(f"Invalid game id for {label}: {source_id}")
    return {"source_id": source_id, "game_id": game_id,
            "attribute": _integer(row.get("attribute"), f"{label} attribute")}


def _catalog(rows: Any, label: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for value in _list(rows, label):
        row = _object(value, label)
        key = _source_id(row.get("_id"), f"{label} id")
        if key in result:
            raise AbyssRulesError(f"Duplicate {label} id")
        result[key] = row
    return result


def _bounds(source: Mapping[str, Any], group: str) -> dict[str, list[int | float]]:
    result = {}
    for kind in ("minMaxCosts", "minMaxCount"):
        values = _slots(_object(source.get(kind), kind).get(group), 2, f"{kind}.{group}")
        if kind == "minMaxCount":
            values = [_integer(value, f"{kind}.{group}") for value in values]
        result["cost" if kind == "minMaxCosts" else "count"] = values
    return result


def _normalise_source(system: Any, agents: Any, engines: Any,
                      sha256: Mapping[str, str] | None, fetched_at: str) -> dict[str, Any]:
    system = _object(system, "system")
    agent_catalog = _catalog(agents, "agent catalog")
    engine_catalog = _catalog(engines, "engine catalog")
    costs = _object(system.get("costs"), "costs")
    if costs.get("system") != "DEFAULT":
        raise AbyssUnsupportedCostError("Unsupported Abyss cost mode")
    draft = _object(system.get("draft"), "draft")
    preset = _object(system.get("preset"), "preset")
    hashes = dict(sha256 or {})
    if any(key not in ("system", "agents", "engines") for key in hashes):
        raise AbyssRulesError("Unsupported source hash key")
    if any(not isinstance(value, str) or len(value) != 64 or
           any(char not in "0123456789abcdef" for char in value) for value in hashes.values()):
        raise AbyssRulesError("Source hashes must be lowercase SHA256")
    system_id = _source_id(system.get("_id"), "system id")
    raw_root = system.get("root")
    source = {
        "family": SOURCE_FAMILY,
        "system_id": system_id,
        "root_id": _source_id(raw_root, "root id") if raw_root else system_id,
        "root_id_from_source": bool(raw_root),
        "predecessor_id": _source_id(system.get("ref"), "predecessor id") if system.get("ref") else "",
        "title": _text(_object(system.get("main"), "main").get("title"), "title"),
        "updated_at": _text(system.get("updatedAt"), "updatedAt"),
        "fetched_at": fetched_at,
        "sha256": hashes,
    }
    characters = []
    seen_variants: set[tuple[str, int]] = set()
    seen_sources: set[str] = set()
    for value in _list(costs.get("agents"), "character prices"):
        row = _object(value, "character price")
        ref = _ref(row.get("agent"), agent_catalog, "character")
        if ref["source_id"] in seen_sources or (ref["game_id"], ref["attribute"]) in seen_variants:
            raise AbyssRulesError("Duplicate character source or variant")
        seen_sources.add(ref["source_id"])
        seen_variants.add((ref["game_id"], ref["attribute"]))
        slots = _slots(row.get("costs"), 9, "character prices")
        specification = row.get("specification")
        if specification is not None:
            specification = _integer(specification, "character specification")
        disable_cap = row.get("disableCostLimit", False)
        if type(disable_cap) is not bool:
            raise AbyssRulesError("disableCostLimit must be boolean")
        characters.append({**ref, "names": _names(agent_catalog[ref["source_id"]].get("name")),
                           "constellation_costs": slots[:7],
                           "level_percent": slots[7], "level_flat": slots[8],
                           "specification": specification, "disable_french_cap": disable_cap})
    weapons = []
    seen_weapon_ids: set[str] = set()
    for value in _list(costs.get("engines"), "weapon prices"):
        row = _object(value, "weapon price")
        source_id = _source_id(row.get("engine"), "weapon source id")
        catalog_row = engine_catalog.get(source_id)
        if catalog_row is None:
            raise AbyssRulesError(f"Unmapped weapon: {source_id}")
        game_id = str(catalog_row.get("enkaId") or "")
        if not game_id.isdigit() or game_id in seen_weapon_ids:
            raise AbyssRulesError("Invalid or duplicate weapon game id")
        seen_weapon_ids.add(game_id)
        slots = _slots(row.get("costs"), 6, "weapon prices")
        overrides = []
        seen_override_ids: set[str] = set()
        for value in _list(row.get("bis", []), "weapon overrides"):
            override = _object(value, "weapon override")
            ref = _ref(override.get("agent"), agent_catalog, "override character")
            if ref["source_id"] in seen_override_ids:
                raise AbyssRulesError("Duplicate weapon override")
            seen_override_ids.add(ref["source_id"])
            overrides.append({**ref, "refinement_costs": _slots(override.get("costs"), 6, "override costs")[:5]})
        weapons.append({"source_id": source_id, "game_id": game_id,
                        "refinement_costs": slots[:5], "off_specialty_cost": slots[5],
                        "character_overrides": overrides})
    bundles = []
    for value in _list(costs.get("agentsBundles", []), "character bundles"):
        row = _object(value, "character bundle")
        members = []
        for item in _list(row.get("agents"), "bundle members"):
            member = _object(item, "bundle member")
            ref = _ref(member.get("agent"), agent_catalog, "bundle character")
            low = _integer(member.get("mindscape"), "bundle constellation minimum")
            high = member.get("mindscapeMax")
            if high is not None:
                high = _integer(high, "bundle constellation maximum")
                if high < low:
                    raise AbyssRulesError("Bundle maximum is below minimum")
            if low > 6 or high is not None and high > 6:
                raise AbyssRulesError("Bundle constellation exceeds C6")
            members.append({**ref, "constellation_min": low, "constellation_max": high})
        if not members:
            raise AbyssRulesError("Empty character bundle")
        bundles.append({"cost": _number(row.get("cost"), "bundle cost"), "members": members})
    tiers = []
    for item in _list(costs.get("tiers"), "tiers"):
        row = _object(item, "tier")
        low = _number(row.get("minCost"), "tier minimum")
        high = _number(row.get("maxCost"), "tier maximum")
        if high < low:
            raise AbyssRulesError("Tier maximum is below minimum")
        tiers.append({"tier": _integer(row.get("tier"), "tier"), "min_cost": low, "max_cost": high})
    rules = []
    for item in _list(preset.get("rules"), "preset rules"):
        row = _object(item, "preset rule")
        kind = _text(row.get("type"), "preset rule type")
        if kind in ("requires", "equals"):
            criteria = []
            for value in _list(row.get("from"), "rule criteria"):
                criterion = _object(value, "rule criterion")
                entry = {"tier": _integer(criterion.get("agent"), "criterion tier")}
                if criterion.get("specification") is not None:
                    entry["specification"] = _integer(criterion["specification"], "criterion specification")
                criteria.append(entry)
            rule = {"type": kind, "from": criteria, "to": _integer(row.get("to"), "target tier")}
            if row.get("fromCost") is not None:
                rule["from_cost"] = _number(row["fromCost"], "rule cost threshold")
        elif kind == "required_agents":
            rule = {"type": kind, "characters": [_ref(value, agent_catalog, "required character")
                                                    for value in _list(row.get("agents"), "required agents")]}
        elif kind == "max_count":
            rule = {"type": kind, "count": _integer(row.get("count"), "maximum count")}
        else:
            raise AbyssRulesError(f"Unsupported preset rule: {kind}")
        rules.append(rule)
    dd_ids = []
    for value in _list(preset.get("ddAgents", []), "DD characters"):
        game_id = str(value)
        if not game_id.isdigit():
            raise AbyssRulesError("Invalid DD character id")
        dd_ids.append(game_id)
    cap = costs.get("costLimit")
    if cap is not None:
        cap = _number(cap, "French difference cap")
    return {"format": FORMAT, "source": source, "characters": characters,
            "weapons": weapons, "bundles": bundles, "tiers": tiers,
            "french_difference_cap": cap,
            "bounds": {group: _bounds(draft, group) for group in ("agents", "engines")},
            "preset_rules": rules, "dd_character_ids": dd_ids}


@dataclass(frozen=True, slots=True)
class AbyssRuleset:
    """Immutable serialized snapshot; accessors return fresh decoded values."""

    _json: str

    @classmethod
    def from_source(cls, system: Mapping[str, Any], agents: list[Mapping[str, Any]],
                    engines: list[Mapping[str, Any]], *, sha256: Mapping[str, str] | None = None,
                    fetched_at: str = "") -> "AbyssRuleset":
        return cls.from_dict(_normalise_source(system, agents, engines, sha256, fetched_at))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AbyssRuleset":
        _preflight(payload)
        data = _object(payload, "Abyss snapshot")
        if data.get("format") != FORMAT:
            raise AbyssRulesError("Unsupported Abyss snapshot format")
        if set(data) != {"format", "source", "characters", "weapons", "bundles", "tiers",
                         "french_difference_cap", "bounds", "preset_rules", "dd_character_ids"}:
            raise AbyssRulesError("Unexpected or missing Abyss snapshot fields")
        source = _object(data["source"], "source")
        if set(source) != {"family", "system_id", "root_id", "root_id_from_source", "predecessor_id", "title",
                           "updated_at", "fetched_at", "sha256"} or source["family"] != SOURCE_FAMILY:
            raise AbyssRulesError("Invalid Abyss source metadata")
        for key in ("system_id", "root_id"):
            _source_id(source[key], key)
        if type(source["root_id_from_source"]) is not bool or (
                not source["root_id_from_source"] and source["root_id"] != source["system_id"]):
            raise AbyssRulesError("Invalid root provenance")
        for key in ("title", "updated_at"):
            _text(source[key], key)
        if source["predecessor_id"]:
            _source_id(source["predecessor_id"], "predecessor id")
        for key in ("predecessor_id", "fetched_at"):
            if not isinstance(source[key], str):
                raise AbyssRulesError(f"Invalid {key}")
        hashes = _object(source["sha256"], "source hashes")
        if any(key not in ("system", "agents", "engines") or not isinstance(value, str)
               or len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
               for key, value in hashes.items()):
            raise AbyssRulesError("Invalid source hashes")
        # Validate saved, untrusted snapshots as strictly as fresh source projections.
        seen_char_sources: set[str] = set()
        seen_char_variants: set[tuple[str, int]] = set()
        character_identity: dict[str, tuple[str, int]] = {}
        for item in _list(data["characters"], "characters"):
            row = _object(item, "character")
            if set(row) != {"source_id", "game_id", "attribute", "names", "constellation_costs",
                            "level_percent", "level_flat", "specification", "disable_french_cap"}:
                raise AbyssRulesError("Invalid character fields")
            source_id = _source_id(row["source_id"], "character source id")
            game_id = _text(row["game_id"], "character game id")
            names = _object(row["names"], "character names")
            if any(key not in ("en", "ru") for key in names) or dict(names) != _names(names):
                raise AbyssRulesError("Invalid character names")
            attribute = _integer(row["attribute"], "character attribute")
            if not game_id.isdigit() or source_id in seen_char_sources or (game_id, attribute) in seen_char_variants:
                raise AbyssRulesError("Invalid or duplicate character identity")
            seen_char_sources.add(source_id)
            seen_char_variants.add((game_id, attribute))
            character_identity[source_id] = (game_id, attribute)
            _slots(row["constellation_costs"], 7, "constellation prices")
            _number(row["level_percent"], "level percent")
            _number(row["level_flat"], "level flat")
            if row["specification"] is not None:
                _integer(row["specification"], "specification")
            if type(row["disable_french_cap"]) is not bool:
                raise AbyssRulesError("Invalid French cap exemption")
        seen_weapon_ids: set[str] = set()
        for item in _list(data["weapons"], "weapons"):
            row = _object(item, "weapon")
            if set(row) != {"source_id", "game_id", "refinement_costs", "off_specialty_cost", "character_overrides"}:
                raise AbyssRulesError("Invalid weapon fields")
            _source_id(row["source_id"], "weapon source id")
            game_id = _text(row["game_id"], "weapon game id")
            if not game_id.isdigit() or game_id in seen_weapon_ids:
                raise AbyssRulesError("Invalid or duplicate weapon identity")
            seen_weapon_ids.add(game_id)
            _slots(row["refinement_costs"], 5, "refinement prices")
            _number(row["off_specialty_cost"], "off-specialty price")
            override_sources: set[str] = set()
            for value in _list(row["character_overrides"], "weapon overrides"):
                override = _object(value, "weapon override")
                if set(override) != {"source_id", "game_id", "attribute", "refinement_costs"}:
                    raise AbyssRulesError("Invalid weapon override fields")
                oid = _source_id(override["source_id"], "override source id")
                if oid in override_sources or oid not in seen_char_sources:
                    raise AbyssRulesError("Invalid or duplicate weapon override reference")
                override_sources.add(oid)
                if (_text(override["game_id"], "override game id"),
                    _integer(override["attribute"], "override attribute")) != character_identity[oid]:
                    raise AbyssRulesError("Weapon override identity mismatch")
                _slots(override["refinement_costs"], 5, "override prices")
        for value in _list(data["bundles"], "bundles"):
            row = _object(value, "bundle")
            if set(row) != {"cost", "members"}:
                raise AbyssRulesError("Invalid bundle fields")
            _number(row["cost"], "bundle cost")
            if not _list(row["members"], "bundle members"):
                raise AbyssRulesError("Empty bundle")
            for value in row["members"]:
                member = _object(value, "bundle member")
                if set(member) != {"source_id", "game_id", "attribute", "constellation_min", "constellation_max"}:
                    raise AbyssRulesError("Invalid bundle member fields")
                member_id = _source_id(member["source_id"], "bundle source id")
                if member_id not in seen_char_sources:
                    raise AbyssRulesError("Unknown bundle character")
                if (_text(member["game_id"], "bundle game id"),
                    _integer(member["attribute"], "bundle attribute")) != character_identity[member_id]:
                    raise AbyssRulesError("Bundle character identity mismatch")
                low = _integer(member["constellation_min"], "bundle minimum")
                high = member["constellation_max"]
                if low > 6 or high is not None and (_integer(high, "bundle maximum") > 6 or high < low):
                    raise AbyssRulesError("Invalid bundle constellation range")
        for value in _list(data["tiers"], "tiers"):
            row = _object(value, "tier")
            if set(row) != {"tier", "min_cost", "max_cost"}:
                raise AbyssRulesError("Invalid tier fields")
            _integer(row["tier"], "tier number")
            if _number(row["max_cost"], "tier maximum") < _number(row["min_cost"], "tier minimum"):
                raise AbyssRulesError("Invalid tier range")
        if data["french_difference_cap"] is not None:
            _number(data["french_difference_cap"], "French difference cap")
        bounds = _object(data["bounds"], "bounds")
        if set(bounds) != {"agents", "engines"}:
            raise AbyssRulesError("Invalid bound groups")
        for group in bounds.values():
            group = _object(group, "bound group")
            if set(group) != {"cost", "count"}:
                raise AbyssRulesError("Invalid bound fields")
            _slots(group["cost"], 2, "cost bounds")
            for value in _slots(group["count"], 2, "count bounds"):
                _integer(value, "count bound")
        for value in _list(data["preset_rules"], "preset rules"):
            row = _object(value, "preset rule")
            kind = row.get("type")
            if kind in ("requires", "equals"):
                if set(row) not in ({"type", "from", "to"}, {"type", "from", "to", "from_cost"}):
                    raise AbyssRulesError("Invalid tier rule fields")
                _integer(row["to"], "target tier")
                if "from_cost" in row:
                    _number(row["from_cost"], "cost threshold")
                for criterion in _list(row["from"], "rule criteria"):
                    criterion = _object(criterion, "criterion")
                    if set(criterion) not in ({"tier"}, {"tier", "specification"}):
                        raise AbyssRulesError("Invalid criterion fields")
                    _integer(criterion["tier"], "criterion tier")
                    if "specification" in criterion:
                        _integer(criterion["specification"], "criterion specification")
            elif kind == "required_agents":
                if set(row) != {"type", "characters"}:
                    raise AbyssRulesError("Invalid required-agent fields")
                for value in _list(row["characters"], "required agents"):
                    ref = _object(value, "required character")
                    if set(ref) != {"source_id", "game_id", "attribute"} or _source_id(ref["source_id"], "required source id") not in seen_char_sources:
                        raise AbyssRulesError("Invalid required character")
                    if (_text(ref["game_id"], "required game id"),
                        _integer(ref["attribute"], "required attribute")) != character_identity[ref["source_id"]]:
                        raise AbyssRulesError("Required character identity mismatch")
            elif kind == "max_count":
                if set(row) != {"type", "count"}:
                    raise AbyssRulesError("Invalid count-rule fields")
                _integer(row["count"], "maximum count")
            else:
                raise AbyssRulesError("Unsupported preset rule")
        for value in _list(data["dd_character_ids"], "DD characters"):
            if not isinstance(value, str) or not value.isdigit():
                raise AbyssRulesError("Invalid DD character id")
        encoded = json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("ascii")) > MAX_SNAPSHOT_BYTES:
            raise AbyssRulesError("Abyss snapshot exceeds size limit")
        return cls(encoded)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._json)

    @property
    def source(self) -> dict[str, Any]:
        return self.to_dict()["source"]

    @property
    def system_id(self) -> str:
        return self.source["system_id"]

    @property
    def root_id(self) -> str:
        return self.source["root_id"]

    @property
    def title(self) -> str:
        return self.source["title"]

    @property
    def updated_at(self) -> str:
        return self.source["updated_at"]

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self._json.encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class AbyssIssue:
    code: str
    severity: str
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity, "details": dict(self.details)}


@dataclass(frozen=True, slots=True)
class AbyssDeckReport:
    system_id: str
    source_hash: str
    character_rows: tuple[Mapping[str, Any], ...]
    weapon_rows: tuple[Mapping[str, Any], ...]
    character_base_total: int | float | None
    bundle_adjustment_total: int | float | None
    character_total: int | float | None
    weapon_total: int | float | None
    character_count: int
    weapon_count: int | None
    tier_counts: Mapping[str, int]
    bundle_candidates: tuple[Mapping[str, Any], ...]
    declarations: tuple[Mapping[str, Any], ...]
    issues: tuple[AbyssIssue, ...]

    @property
    def complete(self) -> bool:
        return not any(issue.severity == "review" for issue in self.issues)

    @property
    def ready(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, Any]:
        return {"system_id": self.system_id, "source_hash": self.source_hash,
                "character_rows": list(self.character_rows), "weapon_rows": list(self.weapon_rows),
                "character_base_total": self.character_base_total,
                "bundle_adjustment_total": self.bundle_adjustment_total,
                "character_total": self.character_total, "weapon_total": self.weapon_total,
                "character_count": self.character_count, "weapon_count": self.weapon_count,
                "tier_counts": dict(self.tier_counts), "bundle_candidates": list(self.bundle_candidates),
                "declarations": list(self.declarations), "issues": [issue.to_dict() for issue in self.issues],
                "complete": self.complete, "ready": self.ready}


def _priced(base: int | float, percent: int | float, flat: int | float, level: int) -> int | float:
    if level < 95:
        return base
    multiplier = 2 if level >= 100 else 1
    result = (Decimal(str(base)) * (1 + Decimal(str(percent)) * multiplier / 100)
              + Decimal(str(flat)) * multiplier).to_integral_value(rounding=ROUND_CEILING)
    return int(result)


def _tier(cost: int | float, tiers: list[dict[str, Any]]) -> int | None:
    matches = [row["tier"] for row in tiers if row["min_cost"] <= cost <= row["max_cost"]]
    return matches[0] if len(matches) == 1 else None


def evaluate_deck(deck: DraftDeck, rules: AbyssRuleset) -> AbyssDeckReport:
    """Evaluate known declarations without inventing weapon assignment or rule reuse."""
    data = rules.to_dict()
    issues: list[AbyssIssue] = []

    def add(code: str, severity: str = "error", **details: Any) -> None:
        issues.append(AbyssIssue(code, severity, details))

    by_game: dict[str, list[dict[str, Any]]] = {}
    for row in data["characters"]:
        by_game.setdefault(row["game_id"], []).append(row)
    character_rows = []
    selected: dict[str, dict[str, Any]] = {}
    character_base_total: int | float | None = 0
    tier_counts: dict[str, int] = {}
    for index, item in enumerate(deck.characters):
        candidates = by_game.get(item.character_id, [])
        attribute = _ELEMENT_ATTRIBUTE.get(item.element.upper()) if item.element else None
        if len(candidates) > 1 and attribute is not None:
            candidates = [row for row in candidates if row["attribute"] == attribute]
        if not candidates:
            add("character_unmapped", index=index, character_id=item.character_id, element=item.element)
        elif len(candidates) > 1:
            add("character_variant_ambiguous", "review", index=index, character_id=item.character_id,
                source_ids=[row["source_id"] for row in candidates])
        source = candidates[0] if len(candidates) == 1 else None
        cost = tier = None
        if source is not None:
            if item.constellation is None or not 0 <= item.constellation <= 6:
                add("character_constellation_unknown", index=index, character_id=item.character_id)
            if item.level is None or not 1 <= item.level <= 100:
                add("character_level_unknown", index=index, character_id=item.character_id)
            if item.constellation is not None and 0 <= item.constellation <= 6 and item.level is not None and 1 <= item.level <= 100:
                cost = _priced(source["constellation_costs"][item.constellation],
                               source["level_percent"], source["level_flat"], item.level)
                tier = _tier(cost, data["tiers"])
                if tier is None:
                    add("character_tier_unmapped", "review", index=index, character_id=item.character_id, cost=cost)
                else:
                    key = str(tier)
                    tier_counts[key] = tier_counts.get(key, 0) + 1
            if source["source_id"] in selected:
                add("duplicate_character", index=index, source_id=source["source_id"])
            selected[source["source_id"]] = {"constellation": item.constellation, "cost": cost,
                                              "tier": tier, "specification": source["specification"]}
        if cost is None:
            character_base_total = None
        elif character_base_total is not None:
            character_base_total += cost
        character_rows.append({"index": index, "character_id": item.character_id,
                               "source_id": source["source_id"] if source else None,
                               "names": source["names"] if source else {},
                               "cost": cost, "tier": tier,
                               "specification": source["specification"] if source else None})

    by_weapon = {row["game_id"]: row for row in data["weapons"]}
    weapon_rows = []
    weapon_total: int | float | None = 0
    weapon_count: int | None = 0
    for index, item in enumerate(deck.weapons):
        source = by_weapon.get(item.weapon_id)
        if source is None:
            add("weapon_unmapped", index=index, weapon_id=item.weapon_id)
        if item.count is None or item.count < 1:
            add("weapon_count_unknown", index=index, weapon_id=item.weapon_id)
            weapon_count = None
        elif weapon_count is not None:
            weapon_count += item.count
        if item.refinement is None or not 1 <= item.refinement <= 5:
            add("weapon_refinement_unknown", index=index, weapon_id=item.weapon_id)
        base = None
        resolved = None
        candidates: list[int | float] = []
        if source is not None and item.refinement is not None and 1 <= item.refinement <= 5:
            r = item.refinement - 1
            base = source["refinement_costs"][r]
            candidates = [base, source["off_specialty_cost"]] + [
                row["refinement_costs"][r] for row in source["character_overrides"]]
            if source["off_specialty_cost"] == 0 and not source["character_overrides"]:
                resolved = base
            else:
                add("weapon_assignment_needed", "review", index=index, weapon_id=item.weapon_id)
        if resolved is None or item.count is None or item.count < 1:
            weapon_total = None
        elif weapon_total is not None:
            weapon_total += resolved * item.count
        weapon_rows.append({"index": index, "weapon_id": item.weapon_id,
                            "source_id": source["source_id"] if source else None,
                            "count": item.count, "base_unit_cost": base, "resolved_unit_cost": resolved,
                            "possible_unit_min": min(candidates) if candidates else None,
                            "possible_unit_max": max(candidates) if candidates else None})

    bundle_candidates = []
    for index, bundle in enumerate(data["bundles"]):
        present = True
        uncertain = False
        for member in bundle["members"]:
            chosen = selected.get(member["source_id"])
            if chosen is None:
                present = False
                break
            constellation = chosen["constellation"]
            if constellation is None:
                uncertain = True
            elif constellation < member["constellation_min"] or (
                    member["constellation_max"] is not None and constellation > member["constellation_max"]):
                present = False
                break
        if present:
            bundle_candidates.append({"index": index, "cost": bundle["cost"],
                                      "members": bundle["members"], "match": "uncertain" if uncertain else "matched"})
    if bundle_candidates:
        add("bundle_application_unverified", "review", candidate_indexes=[row["index"] for row in bundle_candidates])
    bundle_adjustment_total: int | float | None = None
    if not any(row["match"] == "uncertain" for row in bundle_candidates):
        bundle_adjustment_total = sum(row["cost"] for row in bundle_candidates)
    character_total = (character_base_total + bundle_adjustment_total
                       if character_base_total is not None and bundle_adjustment_total is not None else None)

    declarations = []
    for index, rule in enumerate(data["preset_rules"]):
        kind = rule["type"]
        if kind == "required_agents":
            missing = [row for row in rule["characters"] if row["source_id"] not in selected]
            if missing:
                add("required_characters_missing", rule_index=index,
                    source_ids=[row["source_id"] for row in missing])
            declarations.append({"index": index, "type": kind, "required": rule["characters"],
                                 "missing_source_ids": [row["source_id"] for row in missing]})
        elif kind == "max_count":
            if len(deck.characters) > rule["count"]:
                add("max_character_count_exceeded", rule_index=index, maximum=rule["count"],
                    actual=len(deck.characters))
            declarations.append({"index": index, **rule})
        else:
            declarations.append({"index": index, **rule})
            add("tier_combination_unverified", "review", rule_index=index, type=kind)

    for group, total, count in (("agents", character_total, len(deck.characters)),
                                ("engines", weapon_total, weapon_count)):
        for metric, actual in (("cost", total), ("count", count)):
            lower, upper = data["bounds"][group][metric]
            if actual is not None and lower > 0 and actual < lower:
                add("bound_minimum_unmet", group=group, metric=metric, minimum=lower, actual=actual)
            if upper > 0 and actual is not None and actual > upper:
                add("bound_maximum_exceeded", group=group, metric=metric, maximum=upper, actual=actual)
            if upper == 0:
                add("zero_upper_bound_unverified", "review", group=group, metric=metric)
    if data["french_difference_cap"] not in (None, 0):
        add("french_difference_cap_unverified", "review", cap=data["french_difference_cap"])
    return AbyssDeckReport(rules.system_id, rules.content_hash, tuple(character_rows),
                           tuple(weapon_rows), character_base_total, bundle_adjustment_total,
                           character_total, weapon_total, len(deck.characters),
                           weapon_count, tier_counts, tuple(bundle_candidates), tuple(declarations), tuple(issues))
