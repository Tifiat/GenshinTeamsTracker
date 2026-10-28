"""Lazy hypothetical Theory cards from one validated immutable publication.

No inventory, model or engine lookup occurs here. Set/character display metadata
is the workspace's existing catalog context; unknown names retain their wire key.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import html
import re
from typing import Any

from localization import tr
from run_workspace.gcsim.artifact_investment_rules import (
    ARTIFACT_MAIN_STAT_SLOTS, five_star_main_stat_value,
)
from run_workspace.gcsim.optimizer_theory_presentation import (
    GO_TO_CONFIG_STAT, TheoryResultIndex, noncrit_upgrades, theory_score_display,
)
from ui.artifact_browser.models import ArtifactItem, ArtifactSubstat
from ui.artifact_browser import stat_types as stats
from .optimizer_result import (
    OptimizerResultBuildRow, OptimizerResultPage, TheoryPageContext,
    _existing_project_path, _mapping, _normalized_key,
)


WIRE_PROPERTY_TYPES = {
    "hp": stats.HP_FLAT, "hp_percent": stats.HP_PERCENT,
    "atk": stats.ATK_FLAT, "atk_percent": stats.ATK_PERCENT,
    "def": stats.DEF_FLAT, "def_percent": stats.DEF_PERCENT,
    "crit_rate": stats.CRIT_RATE, "crit_damage": stats.CRIT_DAMAGE,
    "energy_recharge": stats.ENERGY_RECHARGE, "em": stats.ELEMENTAL_MASTERY,
    "healing_bonus": stats.HEALING_BONUS,
    "physical_damage_bonus": stats.PHYSICAL_DAMAGE,
    "pyro_damage_bonus": stats.PYRO_DAMAGE, "hydro_damage_bonus": stats.HYDRO_DAMAGE,
    "electro_damage_bonus": stats.ELECTRO_DAMAGE, "cryo_damage_bonus": stats.CRYO_DAMAGE,
    "anemo_damage_bonus": stats.ANEMO_DAMAGE, "geo_damage_bonus": stats.GEO_DAMAGE,
    "dendro_damage_bonus": stats.DENDRO_DAMAGE,
}
_FLAT_PROPERTIES = {stats.HP_FLAT, stats.ATK_FLAT, stats.DEF_FLAT, stats.ELEMENTAL_MASTERY}


def theory_stat_label(wire_key: str) -> str:
    return tr(stats.STAT_LABEL_KEYS[WIRE_PROPERTY_TYPES[wire_key]])


def _stat_value(value: float, property_type: int) -> str:
    percent = property_type not in _FLAT_PROPERTIES
    text = f"{value * (100 if percent else 1):.6f}".rstrip("0").rstrip(".")
    return text + ("%" if percent else "")


def _team_metadata(team: Mapping[str, Any] | None) -> dict[str, dict]:
    output = {}
    for slot in _mapping(team).get("slots") or ():
        slot = _mapping(slot)
        character = _mapping(slot.get("character"))
        account = _mapping(_mapping(slot.get("character_details_data")).get("account_character")) or character
        key = _normalized_key(account.get("gcsim_character_key")) or _normalized_key(character.get("name"))
        if key:
            output[key] = {**character, **account}
    return output


class TheoryResultPages(Sequence[OptimizerResultPage]):
    """Only a small alias index and the currently constructed page are retained."""

    lazy_pages = True

    def __init__(self, snapshot: Mapping[str, Any], *, selected_team=None, set_choices=(), characters=()) -> None:
        self.index = TheoryResultIndex(snapshot)
        self.phase = str(snapshot.get("phase") or "")
        self._team = _team_metadata(selected_team)
        for character in characters:
            self._team.setdefault(character.gcsim_key, {
                "name": character.display_name, "portrait_path": character.icon_path,
            })
        self._sets = {}
        for choice in set_choices:
            self._sets[choice.gcsim_key] = choice
            self._sets[choice.set_uid] = choice
        self._cached_index = -1
        self._cached_page: OptimizerResultPage | None = None

    def __len__(self) -> int:
        return len(self.index)

    def __getitem__(self, position):
        if isinstance(position, slice):
            return tuple(self[i] for i in range(*position.indices(len(self))))
        if type(position) is not int:
            raise TypeError("Theory page index must be an integer")
        if position < 0:
            position += len(self)
        if not 0 <= position < len(self):
            raise IndexError(position)
        if position != self._cached_index:
            self._cached_page = build_theory_page(self, position)
            self._cached_index = position
        return self._cached_page

    def refresh_display(self) -> None:
        self._cached_index = -1
        self._cached_page = None

    def replacement_label(self, target: int, current: int) -> str:
        before = {row["wearer_key"]: row["main_stats"] for row in self.index[current].row["allocations"]}
        changes = []
        for allocation in self.index[target].row["allocations"]:
            wearer = allocation["wearer_key"]
            name = self._team.get(wearer, {}).get("name") or wearer
            for slot in ARTIFACT_MAIN_STAT_SLOTS:
                old, new = before[wearer][slot], allocation["main_stats"][slot]
                if old != new:
                    changes.append(f"{name} {tr('gcsim.optimizer.slot.' + slot)}: {theory_stat_label(old)} → {theory_stat_label(new)}")
        score = theory_score_display(self.index[target].score, self.index.reference)
        if score is None:
            return tr("gcsim.optimizer.theory_display.main_variant_no_reference").format(
                number=target + 1, changes="; ".join(changes),
                dps=_display_dps(self.index[target].score),
            )
        return tr("gcsim.optimizer.theory_display.main_variant").format(
            number=target + 1, changes="; ".join(changes), dps=score.dps_text,
        )


def build_theory_page(pages: TheoryResultPages, position: int) -> OptimizerResultPage:
    entry = pages.index[position]
    row, witness = entry.row, entry.row["witness45"]
    packages = {item["wearer_key"]: item["sets"] for item in entry.alias["packages"]}
    rows = []
    for actor, allocation in enumerate(row["allocations"]):
        wearer = allocation["wearer_key"]
        metadata = pages._team.get(wearer, {})
        # Exact bonus counts occupy four slots at most. Remaining pieces are
        # flexible, with no invented additional set bonus or inventory identity.
        set_counts = {item["set_uid"]: item["count"] for item in packages[wearer]}
        set_units = [item["set_uid"] for item in packages[wearer] for _ in range(item["count"])]
        set_units += [""] * (5 - len(set_units))
        artifacts = []
        set_bonus_descriptions = []
        for slot, slot_key in enumerate(ARTIFACT_MAIN_STAT_SLOTS):
            wire = witness["Mains"][actor][slot]
            property_type = WIRE_PROPERTY_TYPES[wire]
            choice = pages._sets.get(set_units[slot])
            set_bonus_descriptions.append(
                _theory_set_bonus_description(choice, set_counts.get(set_units[slot], 0))
            )
            set_name = choice.display_name if choice else set_units[slot] or tr("gcsim.optimizer.theory_display.flexible_piece")
            icon = _existing_project_path(choice.icon_path) if choice else None
            if icon and icon.stem.endswith("_1"):
                piece_icon = icon.with_name(icon.stem[:-1] + str(slot + 1) + icon.suffix)
                if piece_icon.is_file():
                    icon = piece_icon
            substats = []
            for line, coordinate in enumerate(witness["Lines"][actor][slot]):
                stat = allocation["substats"][coordinate]
                units = 1 + witness["Upgrades"][actor][slot][line]
                unit_value = stat["stat_value"] / stat["roll_units"]
                sub_type = WIRE_PROPERTY_TYPES[stat["stat_key"]]
                substats.append(ArtifactSubstat(
                    slot_index=line + 1, property_type=sub_type,
                    property_name=theory_stat_label(stat["stat_key"]),
                    value=_stat_value(unit_value * units, sub_type), times=None,
                ))
            artifacts.append(ArtifactItem(
                id=-(1 + position * 20 + actor * 5 + slot),
                name=tr("gcsim.optimizer.theory_display.hypothetical"),
                set_id=None, set_uid=set_units[slot], set_name=set_name,
                pos=slot + 1, pos_name=tr("gcsim.optimizer.slot." + slot_key),
                rarity=5, level=20, main_property_type=property_type,
                main_property_name=theory_stat_label(wire),
                main_property_value=_stat_value(
                    five_star_main_stat_value(slot_key, GO_TO_CONFIG_STAT[wire]), property_type,
                ), icon_path=icon, substats=substats,
            ))
        rows.append(OptimizerResultBuildRow(
            wearer_key=wearer, character_id=None,
            character_name=str(metadata.get("name") or wearer),
            character_icon_path=_existing_project_path(
                metadata.get("local_side_icon_path") or metadata.get("side_icon_path")
                or metadata.get("local_portrait_path") or metadata.get("portrait_path")
            ), artifacts=tuple(artifacts), slots=(), hypothetical=True,
            noncrit_upgrade_units=noncrit_upgrades(row, actor),
            theory_piece_upgrades=tuple(tuple(part) for part in witness["Upgrades"][actor]),
            theory_set_bonus_descriptions=tuple(set_bonus_descriptions),
        ))
    return OptimizerResultPage(
        rank=position + 1, measured_dps=str(entry.score), rows=tuple(rows), ranking_basis="gcsim",
        formula_dps=str(row["formula_dps"]), theory_context=TheoryPageContext(
            position=position, total=len(pages), reference=pages.index.reference,
            score=entry.score, tuple_key=entry.alias["tuple_key"],
            phase=pages.phase, refinement_level=entry.refinement_level,
            replacement_indices=pages.index.replacement_indices(position),
            uncertainty=tuple(entry.alias.get("uncertainty") or ()),
        ),
    )


def _display_dps(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def _theory_set_bonus_description(choice: Any, piece_count: int) -> str:
    if choice is None or piece_count not in {2, 4}:
        return ""
    fields = ((2, "two_piece_description"),)
    if piece_count == 4:
        fields += ((4, "four_piece_description"),)
    blocks = []
    for count, field in fields:
        text = _clean_bonus_description(getattr(choice, field, ""))
        if not text:
            continue
        label = tr(
            "gcsim.optimizer.theory_display.two_piece_bonus"
            if count == 2 else "gcsim.optimizer.theory_display.four_piece_bonus"
        )
        blocks.append(f"{html.escape(label)}<br>{html.escape(text).replace(chr(10), '<br>')}")
    return "<br><br>".join(blocks)


def _clean_bonus_description(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"</p>\s*<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?p[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()
