from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from .abyss_sources import fetch_fandom_wikitext


MECHANICS_REPORT_SCHEMA_VERSION = 1

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"


class AbyssMechanicTag(str, Enum):
    SHIELD_CHECK = "shield_check"
    WARD_OR_BARRIER = "ward_or_barrier"
    PHASE_INVULNERABILITY = "phase_invulnerability"
    STATE_RES_OVERRIDE = "state_res_override"
    PARALYZE_WINDOW = "paralyze_window"
    TRUE_DAMAGE_HP_EVENT = "true_damage_hp_event"
    SUMMONS_OR_ADDS = "summons_or_adds"
    ELEMENTAL_REQUIREMENT = "elemental_requirement"
    REACTION_REQUIREMENT = "reaction_requirement"
    LUNAR_REQUIREMENT = "lunar_requirement"
    HIGH_MOBILITY = "high_mobility"
    MODE_SPECIFIC_STATS = "mode_specific_stats"
    WEAKPOINT_PARALYZE = "weakpoint_paralyze"
    BURROW_OR_DOWNTIME = "burrow_or_downtime"
    PHASE_THRESHOLD = "phase_threshold"


@dataclass(frozen=True, slots=True)
class AbyssEnemyMechanicsReport:
    schema_version: int = MECHANICS_REPORT_SCHEMA_VERSION
    enemy_name: str = ""
    source_page: str = ""
    structured_fields_found: tuple[str, ...] = ()
    structured_fields: dict[str, Any] = field(default_factory=dict)
    mechanic_tags: tuple[str, ...] = ()
    prose_only_notes: tuple[str, ...] = ()
    parser_confidence: str = CONFIDENCE_LOW
    ui_warning_recommendation: str = ""
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "enemy_name": self.enemy_name,
            "source_page": self.source_page,
            "structured_fields_found": list(self.structured_fields_found),
            "structured_fields": dict(self.structured_fields),
            "mechanic_tags": list(self.mechanic_tags),
            "prose_only_notes": list(self.prose_only_notes),
            "parser_confidence": self.parser_confidence,
            "ui_warning_recommendation": self.ui_warning_recommendation,
            "warnings": list(self.warnings),
        }


def parse_fandom_enemy_mechanics_wikitext(
    wikitext: str,
    *,
    enemy_name: str = "",
    source_page: str = "",
) -> AbyssEnemyMechanicsReport:
    fields = _extract_template_fields(wikitext)
    shield_data = _extract_elemental_shield_data(wikitext)
    if shield_data:
        fields["elemental_shield_data"] = shield_data

    tags = set(_tags_from_structured_fields(fields))
    tags.update(_tags_from_prose(wikitext))
    notes = _prose_notes(wikitext, tags)
    confidence = _confidence(fields, tags)
    return AbyssEnemyMechanicsReport(
        enemy_name=enemy_name,
        source_page=source_page,
        structured_fields_found=tuple(sorted(fields)),
        structured_fields=fields,
        mechanic_tags=tuple(sorted(tag.value for tag in tags)),
        prose_only_notes=tuple(notes),
        parser_confidence=confidence,
        ui_warning_recommendation=_ui_warning(tags),
    )


def build_abyss_mechanics_report(
    enemy_pages: Mapping[str, str],
) -> tuple[AbyssEnemyMechanicsReport, ...]:
    return tuple(
        parse_fandom_enemy_mechanics_wikitext(
            wikitext,
            enemy_name=enemy_name,
            source_page=enemy_name.replace(" ", "_"),
        )
        for enemy_name, wikitext in enemy_pages.items()
    )


def _extract_template_fields(wikitext: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for match in re.finditer(r"(?m)^\s*\|\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$", wikitext):
        key = match.group(1).strip()
        value = _clean_value(match.group(2))
        if not value:
            continue
        existing = result.get(key)
        if existing is None:
            result[key] = value
        elif isinstance(existing, list):
            existing.append(value)
        else:
            result[key] = [existing, value]
    return result


def _extract_elemental_shield_data(wikitext: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for match in re.finditer(r"\{\{\s*Elemental Shield Data\s*\|([^{}]+)\}\}", wikitext, flags=re.I):
        parts = [part.strip() for part in match.group(1).split("|")]
        if not parts:
            continue
        result.append(
            {
                "element": parts[0],
                "gauge": parts[1] if len(parts) > 1 else "",
                "source": match.group(0),
            }
        )
    return result


def _tags_from_structured_fields(fields: Mapping[str, Any]) -> set[AbyssMechanicTag]:
    tags: set[AbyssMechanicTag] = set()
    lower_values = " ".join(str(value).casefold() for value in fields.values())
    keys = set(fields)
    if "elemental_shield_data" in fields or "shield" in lower_values:
        tags.add(AbyssMechanicTag.SHIELD_CHECK)
    if "ward" in lower_values or "barrier" in lower_values:
        tags.add(AbyssMechanicTag.WARD_OR_BARRIER)
    if any(key.startswith("ability") for key in keys):
        if "summon" in lower_values:
            tags.add(AbyssMechanicTag.SUMMONS_OR_ADDS)
    if _has_res_state_key(keys) or "spiral abyss" in lower_values:
        tags.add(AbyssMechanicTag.STATE_RES_OVERRIDE)
    if fields.get("weakpoint"):
        tags.add(AbyssMechanicTag.WEAKPOINT_PARALYZE)
    if _has_mode_specific_text(lower_values):
        tags.add(AbyssMechanicTag.MODE_SPECIFIC_STATS)
    return tags


def _tags_from_prose(wikitext: str) -> set[AbyssMechanicTag]:
    text = _clean_value(wikitext).casefold()
    tags: set[AbyssMechanicTag] = set()
    if re.search(r"\b(shield|ward|barrier|deepdark)\b", text):
        tags.add(AbyssMechanicTag.WARD_OR_BARRIER)
    if re.search(r"\bimmune|immunity|invulnerable|untargetable|cannot be killed\b", text):
        tags.add(AbyssMechanicTag.PHASE_INVULNERABILITY)
    if re.search(r"\bparaly[sz]ed|stunned|downed|diminished|knock", text):
        tags.add(AbyssMechanicTag.PARALYZE_WINDOW)
    if re.search(r"\btrue .*damage|current hp|max hp|maximum hp", text):
        tags.add(AbyssMechanicTag.TRUE_DAMAGE_HP_EVENT)
    if re.search(r"\bsummon|cicin|slime|fisher|mini mandragora|seed", text):
        tags.add(AbyssMechanicTag.SUMMONS_OR_ADDS)
    if re.search(r"\bpyro|hydro|electro|cryo|dendro|anemo|geo|elemental", text):
        tags.add(AbyssMechanicTag.ELEMENTAL_REQUIREMENT)
    if re.search(r"\bbloom|burgeon|hyperbloom|reaction", text):
        tags.add(AbyssMechanicTag.REACTION_REQUIREMENT)
    if "lunar" in text:
        tags.add(AbyssMechanicTag.LUNAR_REQUIREMENT)
    if re.search(r"\bburrow|flying|fly|dash|spin|mobile|movement", text):
        tags.add(AbyssMechanicTag.HIGH_MOBILITY)
    if "burrow" in text:
        tags.add(AbyssMechanicTag.BURROW_OR_DOWNTIME)
    if re.search(r"\b20% hp|threshold|phase", text):
        tags.add(AbyssMechanicTag.PHASE_THRESHOLD)
    if _has_mode_specific_text(text):
        tags.add(AbyssMechanicTag.MODE_SPECIFIC_STATS)
    return tags


def _prose_notes(
    wikitext: str,
    tags: set[AbyssMechanicTag],
) -> list[str]:
    notes: list[str] = []
    if AbyssMechanicTag.PHASE_INVULNERABILITY in tags:
        notes.append("Prose mentions immunity, invulnerability, or damage-gated state.")
    if AbyssMechanicTag.TRUE_DAMAGE_HP_EVENT in tags:
        notes.append("Prose mentions HP-based or true damage event.")
    if AbyssMechanicTag.SUMMONS_OR_ADDS in tags:
        notes.append("Prose mentions summons/adds or extra targets.")
    if AbyssMechanicTag.MODE_SPECIFIC_STATS in tags:
        notes.append("Page appears to contain mode-specific sections; keep blocks separate.")
    return notes


def _confidence(
    fields: Mapping[str, Any],
    tags: set[AbyssMechanicTag],
) -> str:
    if fields and tags:
        return CONFIDENCE_HIGH
    if fields or tags:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def _ui_warning(tags: set[AbyssMechanicTag]) -> str:
    if not tags:
        return ""
    fragments: list[str] = []
    if AbyssMechanicTag.WARD_OR_BARRIER in tags or AbyssMechanicTag.SHIELD_CHECK in tags:
        fragments.append("shield/ward checks")
    if AbyssMechanicTag.PHASE_INVULNERABILITY in tags or AbyssMechanicTag.BURROW_OR_DOWNTIME in tags:
        fragments.append("forced downtime/invulnerability")
    if AbyssMechanicTag.STATE_RES_OVERRIDE in tags:
        fragments.append("state-specific RES")
    if AbyssMechanicTag.TRUE_DAMAGE_HP_EVENT in tags:
        fragments.append("HP-based true/fixed damage")
    if AbyssMechanicTag.SUMMONS_OR_ADDS in tags:
        fragments.append("summons/adds")
    if AbyssMechanicTag.MODE_SPECIFIC_STATS in tags:
        fragments.append("mode-specific stat blocks")
    return "Factual HP/time DPS ignores or simplifies: " + ", ".join(fragments) + "."


def _has_res_state_key(keys: Iterable[str]) -> bool:
    for key in keys:
        if key == "res_title":
            return True
        if re.search(r"(?:^resglobal|_res)\d+$", key):
            return True
    return False


def _has_mode_specific_text(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "spiral abyss",
            "local legend",
            "stygian",
            "battle-hardened",
            "battle-scarred",
        )
    )


def _clean_value(value: str) -> str:
    text = re.sub(r"<!--.*?-->", "", str(value), flags=re.S)
    text = re.sub(r"\[\[[^|\]]+\|([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a sanitized mechanics report for Fandom enemy pages.",
    )
    parser.add_argument(
        "--page",
        action="append",
        default=[],
        help="Fandom page title. Can be passed multiple times.",
    )
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args(argv)

    reports = [
        parse_fandom_enemy_mechanics_wikitext(
            fetch_fandom_wikitext(page),
            enemy_name=page.replace("_", " "),
            source_page=page,
        ).to_dict()
        for page in args.page
    ]
    print(json.dumps({"reports": reports}, ensure_ascii=False, indent=args.indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
