from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .catalog_mapping import normalize_catalog_name


TOURNAMENT_RULESET_SCHEMA_VERSION = 1

WARNING_DUPLICATE_CHARACTER_COST = "duplicate_character_cost"
WARNING_DUPLICATE_WEAPON_COST = "duplicate_weapon_cost"
WARNING_MISSING_CHARACTER_NAME = "missing_character_name"
WARNING_MISSING_WEAPON_NAME = "missing_weapon_name"
WARNING_UNKNOWN_TIER_RESTRICTION_TYPE = "unknown_tier_restriction_type"
WARNING_UNSUPPORTED_SCRIPT_RULE = "unsupported_script_rule"
WARNING_CHARACTER_UNMATCHED = "character_unmatched"
WARNING_CHARACTER_AMBIGUOUS = "character_ambiguous"
WARNING_WEAPON_UNMATCHED = "weapon_unmatched"
WARNING_WEAPON_AMBIGUOUS = "weapon_ambiguous"

KNOWN_TIER_RESTRICTION_TYPES = {
    "SOMA_EQUIVALENTE",
    "QUANTIDADE_MINIMA",
    "QUANTIDADE_TIER",
}


@dataclass(frozen=True, slots=True)
class RulesetCharacterCost:
    name: str
    costs_by_constellation: dict[int, float] = field(default_factory=dict)
    character_id: str = ""
    element: str = ""
    rarity: int | None = None
    weapon_type: str = ""
    count_for_deck: bool = True
    level_95_extra_cost: float | None = None
    level_100_extra_cost: float | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "costs_by_constellation": {
                str(key): value
                for key, value in sorted(self.costs_by_constellation.items())
            },
            "character_id": self.character_id,
            "element": self.element,
            "rarity": self.rarity,
            "weapon_type": self.weapon_type,
            "count_for_deck": self.count_for_deck,
            "level_95_extra_cost": self.level_95_extra_cost,
            "level_100_extra_cost": self.level_100_extra_cost,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class RulesetWeaponCost:
    name: str
    costs_by_refinement: dict[int, float] = field(default_factory=dict)
    weapon_id: str = ""
    weapon_type: str = ""
    rarity: int | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "costs_by_refinement": {
                str(key): value
                for key, value in sorted(self.costs_by_refinement.items())
            },
            "weapon_id": self.weapon_id,
            "weapon_type": self.weapon_type,
            "rarity": self.rarity,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class RulesetWeaponOverride:
    weapon_name: str
    character_name: str
    costs_by_refinement: dict[int, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "weapon_name": self.weapon_name,
            "character_name": self.character_name,
            "costs_by_refinement": {
                str(key): value
                for key, value in sorted(self.costs_by_refinement.items())
            },
        }


@dataclass(frozen=True, slots=True)
class RulesetTierRestriction:
    restriction_type: str
    comparison_tier: str = ""
    value: float | None = None
    base_value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "restriction_type": self.restriction_type,
            "comparison_tier": self.comparison_tier,
            "value": self.value,
            "base_value": self.base_value,
        }


@dataclass(frozen=True, slots=True)
class RulesetTier:
    name: str
    points_start: float | None = None
    points_end: float | None = None
    color: str = ""
    restrictions: tuple[RulesetTierRestriction, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "points_start": self.points_start,
            "points_end": self.points_end,
            "color": self.color,
            "restrictions": [item.to_dict() for item in self.restrictions],
        }


@dataclass(frozen=True, slots=True)
class RulesetDraftConfig:
    challenge_type: str = ""
    deck_point_limit: float | None = None
    initial_bans: int | None = None
    extra_ban_interval: float | None = None
    joker_interval: int | None = None
    joker_limit: int | None = None
    weapon_ban_location: str = ""
    weapon_ban_count: int | None = None
    script_code: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "challenge_type": self.challenge_type,
            "deck_point_limit": self.deck_point_limit,
            "initial_bans": self.initial_bans,
            "extra_ban_interval": self.extra_ban_interval,
            "joker_interval": self.joker_interval,
            "joker_limit": self.joker_limit,
            "weapon_ban_location": self.weapon_ban_location,
            "weapon_ban_count": self.weapon_ban_count,
            "script_code_present": bool(self.script_code),
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class TournamentRulesetV1:
    schema_version: int = TOURNAMENT_RULESET_SCHEMA_VERSION
    name: str = ""
    source: str = ""
    source_url: str = ""
    language: str = ""
    notes: str = ""
    characters: tuple[RulesetCharacterCost, ...] = ()
    weapons: tuple[RulesetWeaponCost, ...] = ()
    weapon_overrides: tuple[RulesetWeaponOverride, ...] = ()
    tiers: tuple[RulesetTier, ...] = ()
    draft_config: RulesetDraftConfig = field(default_factory=RulesetDraftConfig)
    special_bans: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "source": self.source,
            "source_url": self.source_url,
            "language": self.language,
            "notes": self.notes,
            "characters": [item.to_dict() for item in self.characters],
            "weapons": [item.to_dict() for item in self.weapons],
            "weapon_overrides": [item.to_dict() for item in self.weapon_overrides],
            "tiers": [item.to_dict() for item in self.tiers],
            "draft_config": self.draft_config.to_dict(),
            "special_bans": list(self.special_bans),
        }


@dataclass(frozen=True, slots=True)
class RulesetValidationReport:
    total_characters: int
    total_weapons: int
    total_tiers: int
    warnings: dict[str, int] = field(default_factory=dict)
    examples: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_characters": self.total_characters,
            "total_weapons": self.total_weapons,
            "total_tiers": self.total_tiers,
            "warnings": dict(sorted(self.warnings.items())),
            "examples": {
                key: value
                for key, value in sorted(self.examples.items())
            },
        }


def load_tournament_ruleset_json(path: str | Path) -> TournamentRulesetV1:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Ruleset JSON root must be an object.")
    return tournament_ruleset_from_mapping(payload)


def load_tournament_ruleset_from_csv_paths(
    *,
    name: str,
    characters_csv: str | Path | None = None,
    weapons_csv: str | Path | None = None,
    tiers_csv: str | Path | None = None,
) -> TournamentRulesetV1:
    characters = (
        tuple(_character_cost_from_csv(row) for row in _read_csv(characters_csv))
        if characters_csv
        else ()
    )
    weapons = (
        tuple(_weapon_cost_from_csv(row) for row in _read_csv(weapons_csv))
        if weapons_csv
        else ()
    )
    tiers = (
        tuple(_tier_from_csv(row) for row in _read_csv(tiers_csv))
        if tiers_csv
        else ()
    )
    return TournamentRulesetV1(
        name=name,
        source="csv",
        characters=characters,
        weapons=weapons,
        tiers=tiers,
    )


def tournament_ruleset_from_mapping(payload: Mapping[str, Any]) -> TournamentRulesetV1:
    characters = tuple(
        _character_cost_from_mapping(item)
        for item in _list_value(payload, "characters", "personagens")
    )
    weapons, overrides = _weapons_and_overrides_from_mapping(payload)
    tiers = tuple(_tier_from_mapping(item) for item in _list_value(payload, "tiers"))
    return TournamentRulesetV1(
        name=_text(_first_present(payload, "name", "nome")),
        source=_text(payload.get("source")),
        source_url=_text(_first_present(payload, "source_url", "sourceUrl")),
        language=_text(payload.get("language")),
        notes=_text(payload.get("notes")),
        characters=characters,
        weapons=weapons,
        weapon_overrides=overrides,
        tiers=tiers,
        draft_config=_draft_config_from_mapping(payload),
        special_bans=tuple(_text(item) for item in _list_value(payload, "special_bans")),
    )


def validate_tournament_ruleset(
    ruleset: TournamentRulesetV1,
    *,
    character_catalog: Sequence[Mapping[str, Any]] | None = None,
    weapon_catalog: Sequence[Mapping[str, Any]] | None = None,
    examples_per_warning: int = 3,
) -> RulesetValidationReport:
    warnings: dict[str, int] = {}
    examples: dict[str, list[dict[str, Any]]] = {}

    _validate_names(
        ruleset.characters,
        key=lambda item: item.name,
        duplicate_warning=WARNING_DUPLICATE_CHARACTER_COST,
        missing_warning=WARNING_MISSING_CHARACTER_NAME,
        warnings=warnings,
        examples=examples,
        examples_per_warning=examples_per_warning,
    )
    _validate_names(
        ruleset.weapons,
        key=lambda item: item.name,
        duplicate_warning=WARNING_DUPLICATE_WEAPON_COST,
        missing_warning=WARNING_MISSING_WEAPON_NAME,
        warnings=warnings,
        examples=examples,
        examples_per_warning=examples_per_warning,
    )
    for tier in ruleset.tiers:
        for restriction in tier.restrictions:
            if restriction.restriction_type not in KNOWN_TIER_RESTRICTION_TYPES:
                _add_warning(
                    warnings,
                    examples,
                    WARNING_UNKNOWN_TIER_RESTRICTION_TYPE,
                    {
                        "tier": tier.name,
                        "restriction_type": restriction.restriction_type,
                    },
                    examples_per_warning=examples_per_warning,
                )
    if ruleset.draft_config.script_code:
        _add_warning(
            warnings,
            examples,
            WARNING_UNSUPPORTED_SCRIPT_RULE,
            {"ruleset": ruleset.name},
            examples_per_warning=examples_per_warning,
        )
    if character_catalog is not None:
        _validate_catalog_matches(
            [item.name for item in ruleset.characters if item.name],
            character_catalog,
            unmatched_warning=WARNING_CHARACTER_UNMATCHED,
            ambiguous_warning=WARNING_CHARACTER_AMBIGUOUS,
            warnings=warnings,
            examples=examples,
            examples_per_warning=examples_per_warning,
        )
    if weapon_catalog is not None:
        _validate_catalog_matches(
            [item.name for item in ruleset.weapons if item.name],
            weapon_catalog,
            unmatched_warning=WARNING_WEAPON_UNMATCHED,
            ambiguous_warning=WARNING_WEAPON_AMBIGUOUS,
            warnings=warnings,
            examples=examples,
            examples_per_warning=examples_per_warning,
        )
    return RulesetValidationReport(
        total_characters=len(ruleset.characters),
        total_weapons=len(ruleset.weapons),
        total_tiers=len(ruleset.tiers),
        warnings=warnings,
        examples=examples,
    )


def _character_cost_from_mapping(item: Mapping[str, Any]) -> RulesetCharacterCost:
    character = item.get("character") or item.get("personagem") or {}
    if not isinstance(character, Mapping):
        character = {}
    return RulesetCharacterCost(
        name=_text(_first_present(item, "name", "nome") or _first_present(character, "name", "nome")),
        character_id=_text(_first_present(item, "character_id") or character.get("id") or item.get("id")),
        element=_text(_first_present(item, "element", "elemento") or character.get("elemento")),
        rarity=_optional_int(_first_present(item, "rarity", "raridade") or character.get("raridade")),
        weapon_type=_text(_first_present(item, "weapon_type", "arma") or character.get("arma")),
        count_for_deck=_optional_bool(_first_present(item, "count_for_deck", "contarParaDeck"), default=True),
        costs_by_constellation=_number_map(item, "c", "valorC", 0, 6),
        level_95_extra_cost=_optional_float(_first_present(item, "level_95_extra_cost", "custoAdicionalNivel95")),
        level_100_extra_cost=_optional_float(_first_present(item, "level_100_extra_cost", "custoAdicionalNivel100")),
        notes=_text(item.get("notes")),
    )


def _weapon_cost_from_mapping(item: Mapping[str, Any]) -> RulesetWeaponCost:
    weapon = item.get("weapon") or item.get("arma") or {}
    if not isinstance(weapon, Mapping):
        weapon = {}
    return RulesetWeaponCost(
        name=_text(_first_present(item, "name", "nome") or _first_present(weapon, "name", "nome")),
        weapon_id=_text(_first_present(item, "weapon_id") or weapon.get("id") or item.get("id")),
        weapon_type=_text(_first_present(item, "weapon_type", "type", "tipo") or weapon.get("tipo")),
        rarity=_optional_int(_first_present(item, "rarity", "raridade") or weapon.get("raridade")),
        costs_by_refinement=_number_map(item, "r", "valorR", 1, 5),
        notes=_text(item.get("notes")),
    )


def _weapon_override_from_mapping(
    weapon_name: str,
    item: Mapping[str, Any],
) -> RulesetWeaponOverride:
    character = item.get("character") or item.get("personagem") or {}
    if not isinstance(character, Mapping):
        character = {}
    return RulesetWeaponOverride(
        weapon_name=weapon_name,
        character_name=_text(_first_present(item, "character_name", "name", "nome") or _first_present(character, "name", "nome")),
        costs_by_refinement=_number_map(item, "r", "valorR", 1, 5),
    )


def _weapons_and_overrides_from_mapping(
    payload: Mapping[str, Any],
) -> tuple[tuple[RulesetWeaponCost, ...], tuple[RulesetWeaponOverride, ...]]:
    weapons: list[RulesetWeaponCost] = []
    overrides: list[RulesetWeaponOverride] = []
    for item in _list_value(payload, "weapons", "armas"):
        weapon = _weapon_cost_from_mapping(item)
        weapons.append(weapon)
        for override in _list_value(item, "character_overrides", "personagens"):
            overrides.append(_weapon_override_from_mapping(weapon.name, override))
    for item in _list_value(payload, "weapon_overrides"):
        overrides.append(
            RulesetWeaponOverride(
                weapon_name=_text(_first_present(item, "weapon_name", "weapon")),
                character_name=_text(_first_present(item, "character_name", "character")),
                costs_by_refinement=_number_map(item, "r", "valorR", 1, 5),
            )
        )
    return tuple(weapons), tuple(overrides)


def _tier_from_mapping(item: Mapping[str, Any]) -> RulesetTier:
    return RulesetTier(
        name=_text(_first_present(item, "name", "nome")),
        points_start=_optional_float(_first_present(item, "points_start", "pontuacaoInicio")),
        points_end=_optional_float(_first_present(item, "points_end", "pontuacaoFim")),
        color=_text(_first_present(item, "color", "cor")),
        restrictions=tuple(
            _tier_restriction_from_mapping(restriction)
            for restriction in _list_value(item, "restrictions", "restricoes")
        ),
    )


def _tier_restriction_from_mapping(item: Mapping[str, Any]) -> RulesetTierRestriction:
    comparison = item.get("comparison_tier") or item.get("tierComparacao") or {}
    if isinstance(comparison, Mapping):
        comparison_name = _text(_first_present(comparison, "name", "nome"))
    else:
        comparison_name = _text(comparison)
    return RulesetTierRestriction(
        restriction_type=_text(_first_present(item, "restriction_type", "tipo")),
        comparison_tier=comparison_name,
        value=_optional_float(_first_present(item, "value", "valorComparacao")),
        base_value=_optional_float(_first_present(item, "base_value", "valorBase")),
    )


def _draft_config_from_mapping(payload: Mapping[str, Any]) -> RulesetDraftConfig:
    raw = payload.get("draft_config") or payload.get("configuracao") or {}
    if not isinstance(raw, Mapping):
        raw = {}
    script = raw.get("script") or {}
    script_code = ""
    if isinstance(script, Mapping):
        script_code = _text(_first_present(script, "code", "codigo"))
    elif script:
        script_code = _text(script)
    if not script_code:
        script_code = _text(_first_present(raw, "script_code", "codigoScript"))
    return RulesetDraftConfig(
        challenge_type=_text(_first_present(raw, "challenge_type", "desafio")),
        deck_point_limit=_optional_float(_first_present(raw, "deck_point_limit", "limitePontosPersonagens")),
        initial_bans=_optional_int(_first_present(raw, "initial_bans", "baseBansIniciais")),
        extra_ban_interval=_optional_float(_first_present(raw, "extra_ban_interval", "intervaloPontos")),
        joker_interval=_optional_int(_first_present(raw, "joker_interval", "intervaloJoker")),
        joker_limit=_optional_int(_first_present(raw, "joker_limit", "maxJokers")),
        weapon_ban_location=_text(_first_present(raw, "weapon_ban_location", "localBanArma")),
        weapon_ban_count=_optional_int(_first_present(raw, "weapon_ban_count", "quantidadeBansArma")),
        script_code=script_code,
        notes=_text(raw.get("notes")),
    )


def _character_cost_from_csv(row: Mapping[str, Any]) -> RulesetCharacterCost:
    return _character_cost_from_mapping(row)


def _weapon_cost_from_csv(row: Mapping[str, Any]) -> RulesetWeaponCost:
    return _weapon_cost_from_mapping(row)


def _tier_from_csv(row: Mapping[str, Any]) -> RulesetTier:
    return _tier_from_mapping(row)


def _read_csv(path: str | Path | None) -> list[dict[str, str]]:
    if path is None:
        return []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _validate_names(
    items: Sequence[Any],
    *,
    key,
    duplicate_warning: str,
    missing_warning: str,
    warnings: dict[str, int],
    examples: dict[str, list[dict[str, Any]]],
    examples_per_warning: int,
) -> None:
    seen: dict[str, str] = {}
    for item in items:
        name = key(item)
        normalized = normalize_catalog_name(name)
        if not normalized:
            _add_warning(
                warnings,
                examples,
                missing_warning,
                {"item": getattr(item, "to_dict", lambda: {})()},
                examples_per_warning=examples_per_warning,
            )
            continue
        if normalized in seen:
            _add_warning(
                warnings,
                examples,
                duplicate_warning,
                {"name": name, "previous": seen[normalized]},
                examples_per_warning=examples_per_warning,
            )
        else:
            seen[normalized] = name


def _validate_catalog_matches(
    names: Sequence[str],
    catalog: Sequence[Mapping[str, Any]],
    *,
    unmatched_warning: str,
    ambiguous_warning: str,
    warnings: dict[str, int],
    examples: dict[str, list[dict[str, Any]]],
    examples_per_warning: int,
) -> None:
    catalog_by_name: dict[str, list[Mapping[str, Any]]] = {}
    for item in catalog:
        normalized = normalize_catalog_name(_first_present(item, "name", "nome"))
        if normalized:
            catalog_by_name.setdefault(normalized, []).append(item)
    for name in names:
        candidates = catalog_by_name.get(normalize_catalog_name(name), [])
        if not candidates:
            _add_warning(
                warnings,
                examples,
                unmatched_warning,
                {"name": name},
                examples_per_warning=examples_per_warning,
            )
        elif len(candidates) > 1:
            _add_warning(
                warnings,
                examples,
                ambiguous_warning,
                {"name": name, "candidate_count": len(candidates)},
                examples_per_warning=examples_per_warning,
            )


def _add_warning(
    warnings: dict[str, int],
    examples: dict[str, list[dict[str, Any]]],
    warning: str,
    example: dict[str, Any],
    *,
    examples_per_warning: int,
) -> None:
    warnings[warning] = warnings.get(warning, 0) + 1
    bucket = examples.setdefault(warning, [])
    if len(bucket) < examples_per_warning:
        bucket.append(example)


def _number_map(
    item: Mapping[str, Any],
    normalized_prefix: str,
    gentor_prefix: str,
    start: int,
    end: int,
) -> dict[int, float]:
    result: dict[int, float] = {}
    nested = item.get("costs_by_constellation") or item.get("costs_by_refinement")
    if isinstance(nested, Mapping):
        for raw_key, raw_value in nested.items():
            index = _cost_index(raw_key, normalized_prefix)
            value = _optional_float(raw_value)
            if index is not None and start <= index <= end and value is not None:
                result[index] = value
    for index in range(start, end + 1):
        for key in (
            f"{normalized_prefix}{index}",
            f"{normalized_prefix.upper()}{index}",
            f"{gentor_prefix}{index}",
        ):
            value = _optional_float(item.get(key))
            if value is not None:
                result[index] = value
                break
    return dict(sorted(result.items()))


def _cost_index(value: Any, prefix: str) -> int | None:
    text = str(value).strip().casefold()
    if text.isdigit():
        return int(text)
    if text.startswith(prefix.casefold()) and text[len(prefix) :].isdigit():
        return int(text[len(prefix) :])
    return None


def _list_value(payload: Mapping[str, Any], *keys: str) -> list[Mapping[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    return []


def _first_present(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return value
    return None


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


def _optional_bool(value: Any, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() not in {"false", "0", "no", "n"}


def _text(value: Any) -> str:
    return str(value or "").strip()
