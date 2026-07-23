"""Equal-investment screening profiles for the pinned GCSIM optimizer.

The upstream substat optimizer is too expensive to run for every set/wearer
probe.  Cheap farming-search simulations still need comparable artifact
investment, however; simulating main stats alone would systematically inflate
sets that provide raw stats and would miss counterintuitive HP/EM/DEF scaling.

This module mirrors the *allocation envelope* of GCSIM v2.42.2 without copying
its damage logic:

* two fixed rolls of every supported substat;
* twenty liquid rolls with a per-stat cap of ten;
* two fewer liquid rolls and a four-percent rarity multiplier per four-star
  set piece, matching ``pkg/optimization/substats.go``;
* reduced liquid capacity when a slot already owns the same main stat.

Profiles only redistribute that fixed roll budget.  They never create free
positive stats.  Final candidates must still be rerun through upstream
``-substatOptim`` before they can be ranked as validated finalists.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from math import floor, isclose, isfinite
from types import MappingProxyType
import re
from typing import Iterable, Mapping, Sequence

from .config_structure import (
    build_gcsim_structural_view,
    find_gcsim_statement_terminator,
    has_noncanonical_gcsim_line_separator,
    is_canonical_gcsim_statement_row,
)
from .farming_search import (
    PROFILE_BASELINE,
    StatAxis,
    StatProfile,
    StatProfileBank,
    StatWeight,
    generate_stat_profile_bank,
)
from .optimizer_config import (
    ARTIFACT_MAIN_STAT_SLOTS,
    GcsimFiveStarMainStatLayout,
    render_five_star_main_stat_line,
    render_four_star_set_main_stat_line,
)


GCSIM_SCREENING_PROFILE_CONTRACT = "gcsim-v2.42.2-kqm-envelope-v1"
DEFAULT_TOTAL_LIQUID_SUBSTATS = 20
DEFAULT_INDIVIDUAL_LIQUID_CAP = 10
DEFAULT_FIXED_SUBSTATS_COUNT = 2
FOUR_STAR_LIQUID_ROLL_PENALTY = 2
FOUR_STAR_RARITY_PENALTY = 0.04

# Order is intentionally stable and becomes part of deterministic allocation
# tie-breaking and serialized candidate identity.
GCSIM_SUBSTAT_ROLL_VALUES: Mapping[str, float] = MappingProxyType(
    {
        "atk%": 0.0496,
        "cr": 0.0331,
        "cd": 0.0662,
        "em": 19.82,
        "er": 0.0551,
        "hp%": 0.0496,
        "def%": 0.062,
        "atk": 16.54,
        "def": 19.68,
        "hp": 253.94,
    }
)

GCSIM_SCREENING_STAT_AXES: tuple[StatAxis, ...] = tuple(
    StatAxis(key=key, probe_delta=value, unit="one_max_roll")
    for key, value in GCSIM_SUBSTAT_ROLL_VALUES.items()
)
GCSIM_BALANCED_REFERENCE_WEIGHTS: tuple[StatWeight, ...] = tuple(
    StatWeight(
        axis_key=axis.key,
        weight=1.0 / len(GCSIM_SCREENING_STAT_AXES),
    )
    for axis in GCSIM_SCREENING_STAT_AXES
)

_CHARACTER_LINE_RE = re.compile(
    r"^\s*(?P<character>[A-Za-z0-9_]+)\s+char\b[^;]*;",
    re.IGNORECASE,
)
_STATS_LINE_RE = re.compile(
    r"^\s*(?P<character>[A-Za-z0-9_]+)\s+add\s+stats\b[^;]*;",
    re.IGNORECASE,
)
_SCREENING_SENSITIVE_STATEMENT_RE = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z0-9_]+\s+"
    r"(?:char\b|add\s+stats\b)",
    re.IGNORECASE,
)
_OPTIONS_STATEMENT_RE = re.compile(
    r"(?<![A-Za-z0-9_])options\b",
    re.IGNORECASE,
)
_RUNTIME_OPTION_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:iteration|workers)\s*=\s*[^\s;]+",
    re.IGNORECASE,
)
_PINNED_CHARACTER_RE = re.compile(r"^[a-z]+$")


class GcsimScreeningProfileError(ValueError):
    """Raised when a cheap-screen config cannot be rendered safely."""


@dataclass(frozen=True, slots=True)
class GcsimSubstatRollCount:
    axis_key: str
    fixed_rolls: int
    liquid_rolls: int
    liquid_cap: int
    roll_value: float
    rarity_modifier: float

    def __post_init__(self) -> None:
        if self.axis_key not in GCSIM_SUBSTAT_ROLL_VALUES:
            raise ValueError(f"unsupported GCSIM substat axis: {self.axis_key!r}")
        for field_name in ("fixed_rolls", "liquid_rolls", "liquid_cap"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.liquid_rolls > self.liquid_cap:
            raise ValueError("liquid_rolls cannot exceed liquid_cap")
        for field_name in ("roll_value", "rarity_modifier"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isfinite(value) or value <= 0:
                raise ValueError(f"{field_name} must be finite and positive")

    @property
    def total_rolls(self) -> int:
        return self.fixed_rolls + self.liquid_rolls

    @property
    def effective_roll_value(self) -> float:
        return self.roll_value * self.rarity_modifier


@dataclass(frozen=True, slots=True)
class GcsimScreeningStatAllocation:
    profile_id: str
    four_star_piece_count: int
    fixed_substats_count: int
    total_liquid_substats: int
    rarity_modifier: float
    rolls: tuple[GcsimSubstatRollCount, ...]
    investment_signature: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "rolls", tuple(self.rolls))
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise ValueError("profile_id must be a non-empty string")
        if (
            not isinstance(self.investment_signature, str)
            or not self.investment_signature.strip()
        ):
            raise ValueError("investment_signature must be a non-empty string")
        for field_name in (
            "four_star_piece_count",
            "fixed_substats_count",
            "total_liquid_substats",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if (
            isinstance(self.rarity_modifier, bool)
            or not isfinite(self.rarity_modifier)
            or self.rarity_modifier <= 0
        ):
            raise ValueError("rarity_modifier must be finite and positive")
        if tuple(item.axis_key for item in self.rolls) != tuple(GCSIM_SUBSTAT_ROLL_VALUES):
            raise ValueError("screening allocation must cover every pinned axis in order")
        if sum(item.liquid_rolls for item in self.rolls) != self.total_liquid_substats:
            raise ValueError("screening allocation changed the liquid roll budget")
        if any(item.liquid_rolls > item.liquid_cap for item in self.rolls):
            raise ValueError("screening allocation exceeds a liquid substat cap")

    @property
    def liquid_rolls_by_axis(self) -> tuple[tuple[str, int], ...]:
        return tuple((item.axis_key, item.liquid_rolls) for item in self.rolls)

    def render_stats_line(self, character_key: str) -> str:
        key = _validated_character_key(character_key)
        rendered = " ".join(
            f"{item.axis_key}={_format_number(item.effective_roll_value)}*{item.total_rolls}"
            for item in self.rolls
        )
        return f"{key} add stats {rendered};"


@dataclass(frozen=True, slots=True)
class GcsimScreeningCharacterProfile:
    character_key: str
    profile_id: str
    allocation: GcsimScreeningStatAllocation
    main_stat_line: str
    substat_line: str


@dataclass(frozen=True, slots=True)
class GcsimScreeningConfigRenderResult:
    config_text: str
    characters: tuple[GcsimScreeningCharacterProfile, ...]
    investment_signature: str


def build_default_gcsim_screening_profile_bank(
    *,
    include_axis_pairs: bool = False,
    axis_pair_limit: int | None = None,
) -> StatProfileBank:
    """Return the pinned generic response bank without character hardcodes."""

    return generate_stat_profile_bank(
        GCSIM_SCREENING_STAT_AXES,
        include_baseline=True,
        # The baseline already *is* the balanced reference allocation. Keeping
        # a second balanced id would render byte-identical configs and waste one
        # real simulation per state while defeating probe-key deduplication.
        include_balanced=False,
        include_single_axis=True,
        include_axis_pairs=include_axis_pairs,
        axis_pair_limit=axis_pair_limit,
    )


def build_gcsim_screening_investment_signature(
    *,
    reference_weights: Sequence[StatWeight] = GCSIM_BALANCED_REFERENCE_WEIGHTS,
    total_liquid_substats: int = DEFAULT_TOTAL_LIQUID_SUBSTATS,
    individual_liquid_cap: int = DEFAULT_INDIVIDUAL_LIQUID_CAP,
    fixed_substats_count: int = DEFAULT_FIXED_SUBSTATS_COUNT,
) -> str:
    """Return the content identity of one equal-investment envelope.

    Candidate rarity, main-stat layout, and profile direction deliberately do
    not enter this digest: they are candidate inputs evaluated under the same
    pinned allocation policy.  Any knob that changes the comparable roll
    envelope or spill reference does enter it.
    """

    _require_plain_int(
        total_liquid_substats,
        field_name="total_liquid_substats",
        minimum=0,
    )
    _require_plain_int(
        individual_liquid_cap,
        field_name="individual_liquid_cap",
        minimum=0,
    )
    _require_plain_int(
        fixed_substats_count,
        field_name="fixed_substats_count",
        minimum=0,
    )
    reference = _normalized_weights(
        reference_weights,
        axis_keys=tuple(GCSIM_SUBSTAT_ROLL_VALUES),
        field_name="reference_weights",
    )
    return _screening_investment_signature(
        reference_weights=reference,
        total_liquid_substats=total_liquid_substats,
        individual_liquid_cap=individual_liquid_cap,
        fixed_substats_count=fixed_substats_count,
    )


def allocate_gcsim_screening_substats(
    layout: GcsimFiveStarMainStatLayout,
    profile: StatProfile,
    *,
    four_star_piece_count: int = 0,
    reference_weights: Sequence[StatWeight] = GCSIM_BALANCED_REFERENCE_WEIGHTS,
    total_liquid_substats: int = DEFAULT_TOTAL_LIQUID_SUBSTATS,
    individual_liquid_cap: int = DEFAULT_INDIVIDUAL_LIQUID_CAP,
    fixed_substats_count: int = DEFAULT_FIXED_SUBSTATS_COUNT,
) -> GcsimScreeningStatAllocation:
    """Project one profile into a legal, equal-budget integer roll allocation."""

    normalized_layout = _validated_layout(layout)
    if not isinstance(profile, StatProfile):
        raise GcsimScreeningProfileError("profile must be a StatProfile")
    _require_plain_int(
        four_star_piece_count,
        field_name="four_star_piece_count",
        minimum=0,
        maximum=len(ARTIFACT_MAIN_STAT_SLOTS),
    )
    _require_plain_int(
        total_liquid_substats,
        field_name="total_liquid_substats",
        minimum=0,
    )
    _require_plain_int(
        individual_liquid_cap,
        field_name="individual_liquid_cap",
        minimum=0,
    )
    _require_plain_int(
        fixed_substats_count,
        field_name="fixed_substats_count",
        minimum=0,
    )

    axis_keys = tuple(GCSIM_SUBSTAT_ROLL_VALUES)
    reference = _normalized_weights(
        reference_weights,
        axis_keys=axis_keys,
        field_name="reference_weights",
    )
    if profile.kind == PROFILE_BASELINE:
        target = reference
    else:
        target = _normalized_weights(
            profile.weights,
            axis_keys=axis_keys,
            field_name=f"profile {profile.profile_id!r}",
        )
    investment_signature = build_gcsim_screening_investment_signature(
        reference_weights=tuple(
            StatWeight(axis_key=key, weight=value)
            for key, value in reference.items()
            if value > 0
        ),
        total_liquid_substats=total_liquid_substats,
        individual_liquid_cap=individual_liquid_cap,
        fixed_substats_count=fixed_substats_count,
    )

    main_counts = _substat_main_counts(normalized_layout)
    capacities = {
        key: individual_liquid_cap - fixed_substats_count * main_counts[key]
        for key in axis_keys
    }
    if any(value < 0 for value in capacities.values()):
        raise GcsimScreeningProfileError(
            "main-stat layout makes a liquid substat cap negative"
        )

    liquid_budget = max(
        total_liquid_substats
        - FOUR_STAR_LIQUID_ROLL_PENALTY * four_star_piece_count,
        0,
    )
    if sum(capacities.values()) < liquid_budget:
        raise GcsimScreeningProfileError(
            "liquid substat budget exceeds the available per-stat capacities"
        )
    liquid_counts = {key: 0 for key in axis_keys}
    remaining = _allocate_weighted_rolls(
        liquid_budget,
        counts=liquid_counts,
        capacities=capacities,
        weights=target,
        axis_order=axis_keys,
    )
    if remaining:
        remaining = _allocate_weighted_rolls(
            remaining,
            counts=liquid_counts,
            capacities=capacities,
            weights=reference,
            axis_order=axis_keys,
        )
    if remaining:
        remaining = _allocate_weighted_rolls(
            remaining,
            counts=liquid_counts,
            capacities=capacities,
            weights={key: 1.0 for key in axis_keys},
            axis_order=axis_keys,
        )
    if remaining:
        raise GcsimScreeningProfileError(
            "could not place every liquid roll inside the configured caps"
        )

    rarity_modifier = 1.0 - FOUR_STAR_RARITY_PENALTY * four_star_piece_count
    if rarity_modifier <= 0:
        raise GcsimScreeningProfileError("four-star rarity modifier is not positive")
    return GcsimScreeningStatAllocation(
        profile_id=profile.profile_id,
        four_star_piece_count=four_star_piece_count,
        fixed_substats_count=fixed_substats_count,
        total_liquid_substats=liquid_budget,
        rarity_modifier=rarity_modifier,
        rolls=tuple(
            GcsimSubstatRollCount(
                axis_key=key,
                fixed_rolls=fixed_substats_count,
                liquid_rolls=liquid_counts[key],
                liquid_cap=capacities[key],
                roll_value=GCSIM_SUBSTAT_ROLL_VALUES[key],
                rarity_modifier=rarity_modifier,
            )
            for key in axis_keys
        ),
        investment_signature=investment_signature,
    )


def render_gcsim_screening_profile_config(
    config_text: str,
    *,
    main_stat_layouts: Mapping[str, GcsimFiveStarMainStatLayout],
    profiles: Mapping[str, StatProfile],
    four_star_offpiece_slots: Mapping[str, str] | None = None,
    reference_weights: Sequence[StatWeight] = GCSIM_BALANCED_REFERENCE_WEIGHTS,
) -> GcsimScreeningConfigRenderResult:
    """Append one pinned screening-substat row after each exact main-stat row.

    ``config_text`` must already be produced by the fixed-candidate renderer.
    Exact main-line verification prevents accidentally stacking a screening
    allocation on top of account artifacts or an older optimizer output.
    """

    text = str(config_text or "")
    if not text.strip():
        raise GcsimScreeningProfileError("config_text must not be empty")
    if has_noncanonical_gcsim_line_separator(text):
        raise GcsimScreeningProfileError(
            "canonical semicolon-terminated rows require LF or CRLF"
        )
    structural_view = build_gcsim_structural_view(text)
    for match in _SCREENING_SENSITIVE_STATEMENT_RE.finditer(structural_view):
        terminator = find_gcsim_statement_terminator(
            structural_view,
            match.end(),
        )
        if not is_canonical_gcsim_statement_row(
            structural_view,
            token_start=match.start(),
            terminator_index=terminator,
        ):
            raise GcsimScreeningProfileError(
                "character and add-stats statements must each occupy one "
                "canonical semicolon-terminated row"
            )
    normalized_layouts = _normalize_character_mapping(
        main_stat_layouts,
        field_name="main_stat_layouts",
    )
    normalized_profiles = _normalize_character_mapping(
        profiles,
        field_name="profiles",
    )
    normalized_offpieces = _normalize_character_mapping(
        four_star_offpiece_slots or {},
        field_name="four_star_offpiece_slots",
    )

    lines = text.splitlines(keepends=True)
    character_order: list[str] = []
    declared_counts: dict[str, int] = {}
    stats_indices: dict[str, list[int]] = {}
    for index, line in enumerate(lines):
        character_match = _CHARACTER_LINE_RE.match(line)
        if character_match:
            key = character_match.group("character")
            if key not in declared_counts:
                character_order.append(key)
            declared_counts[key] = declared_counts.get(key, 0) + 1
        stats_match = _STATS_LINE_RE.match(line)
        if stats_match:
            stats_indices.setdefault(stats_match.group("character"), []).append(index)

    if not character_order:
        raise GcsimScreeningProfileError("config contains no character declarations")
    expected_keys = set(character_order)
    for key in character_order:
        _validated_character_key(key)
        if declared_counts[key] != 1:
            raise GcsimScreeningProfileError(
                f"character {key!r} must be declared exactly once"
            )
    _require_exact_character_keys(
        normalized_layouts,
        expected_keys=expected_keys,
        field_name="main_stat_layouts",
    )
    _require_exact_character_keys(
        normalized_profiles,
        expected_keys=expected_keys,
        field_name="profiles",
    )
    unknown_offpieces = set(normalized_offpieces).difference(expected_keys)
    if unknown_offpieces:
        raise GcsimScreeningProfileError(
            "four_star_offpiece_slots contains unknown characters: "
            f"{tuple(sorted(unknown_offpieces))!r}"
        )
    orphan_stats = set(stats_indices).difference(expected_keys)
    if orphan_stats:
        raise GcsimScreeningProfileError(
            f"config contains orphan add-stats rows: {tuple(sorted(orphan_stats))!r}"
        )

    insertions: dict[int, str] = {}
    rendered_characters: list[GcsimScreeningCharacterProfile] = []
    for key in character_order:
        indices = stats_indices.get(key, [])
        if len(indices) != 1:
            raise GcsimScreeningProfileError(
                f"character {key!r} must have exactly one main-stat row before screening"
            )
        layout = _validated_layout(normalized_layouts[key])
        offpiece_slot = str(normalized_offpieces.get(key, "") or "").strip()
        if offpiece_slot:
            if offpiece_slot not in ARTIFACT_MAIN_STAT_SLOTS:
                raise GcsimScreeningProfileError(
                    f"invalid four-star offpiece slot for {key!r}: {offpiece_slot!r}"
                )
            expected_main_line = render_four_star_set_main_stat_line(
                key,
                layout,
                offpiece_slot=offpiece_slot,
            )
            four_star_piece_count = 4
        else:
            expected_main_line = render_five_star_main_stat_line(key, layout)
            four_star_piece_count = 0
        actual_main_line = lines[indices[0]].strip()
        if actual_main_line != expected_main_line:
            raise GcsimScreeningProfileError(
                f"character {key!r} main-stat row does not match the pinned candidate renderer"
            )
        allocation = allocate_gcsim_screening_substats(
            layout,
            normalized_profiles[key],
            four_star_piece_count=four_star_piece_count,
            reference_weights=reference_weights,
        )
        substat_line = allocation.render_stats_line(key)
        source_line = lines[indices[0]]
        if source_line.endswith("\r\n"):
            insertion = substat_line + "\r\n"
        elif source_line.endswith("\n"):
            insertion = substat_line + "\n"
        else:
            insertion = "\n" + substat_line
        insertions[indices[0]] = insertion
        rendered_characters.append(
            GcsimScreeningCharacterProfile(
                character_key=key,
                profile_id=normalized_profiles[key].profile_id,
                allocation=allocation,
                main_stat_line=expected_main_line,
                substat_line=substat_line,
            )
        )

    output: list[str] = []
    for index, line in enumerate(lines):
        output.append(line)
        insertion = insertions.get(index)
        if insertion is not None:
            output.append(insertion)
    investment_signatures = {
        item.allocation.investment_signature
        for item in rendered_characters
    }
    if len(investment_signatures) != 1:
        raise GcsimScreeningProfileError(
            "rendered characters do not share one screening investment envelope"
        )
    return GcsimScreeningConfigRenderResult(
        config_text="".join(output),
        characters=tuple(rendered_characters),
        investment_signature=next(iter(investment_signatures)),
    )


def apply_gcsim_screening_runtime_options(
    config_text: str,
    *,
    iterations: int,
    workers: int,
) -> str:
    """Pin the cheap-run iteration and worker budget on one options line."""

    _require_plain_int(iterations, field_name="iterations", minimum=1)
    _require_plain_int(workers, field_name="workers", minimum=1)
    text = str(config_text or "")
    if has_noncanonical_gcsim_line_separator(text):
        raise GcsimScreeningProfileError(
            "screening options must use canonical LF or CRLF rows"
        )
    structural_view = build_gcsim_structural_view(text)
    matches = tuple(_OPTIONS_STATEMENT_RE.finditer(structural_view))
    if len(matches) != 1:
        raise GcsimScreeningProfileError(
            "screening config must contain exactly one options statement"
        )
    match = matches[0]
    terminator = find_gcsim_statement_terminator(structural_view, match.end())
    if not is_canonical_gcsim_statement_row(
        structural_view,
        token_start=match.start(),
        terminator_index=terminator,
    ):
        raise GcsimScreeningProfileError(
            "screening options statement must occupy one canonical row"
        )
    body = _RUNTIME_OPTION_RE.sub(
        " ",
        structural_view[match.end() : terminator],
    )
    body = " ".join(body.split())
    runtime = f"iteration={iterations} workers={workers}"
    replacement = text[match.start() : match.end()]
    if body:
        replacement += f" {body}"
    replacement += f" {runtime};"
    return text[: match.start()] + replacement + text[terminator + 1 :]


def _allocate_weighted_rolls(
    requested: int,
    *,
    counts: dict[str, int],
    capacities: Mapping[str, int],
    weights: Mapping[str, float],
    axis_order: Sequence[str],
) -> int:
    remaining = requested
    order_index = {key: index for index, key in enumerate(axis_order)}
    while remaining > 0:
        eligible = tuple(
            key
            for key in axis_order
            if weights.get(key, 0.0) > 0 and counts[key] < capacities[key]
        )
        if not eligible:
            break
        weight_total = sum(weights[key] for key in eligible)
        ideal = {
            key: remaining * weights[key] / weight_total
            for key in eligible
        }
        allocated = 0
        for key in eligible:
            amount = min(
                capacities[key] - counts[key],
                int(floor(ideal[key])),
            )
            if amount > 0:
                counts[key] += amount
                allocated += amount
        remaining -= allocated
        if remaining <= 0:
            break
        eligible = tuple(
            key for key in eligible if counts[key] < capacities[key]
        )
        if not eligible:
            continue
        # Hamilton remainder with stable source-axis tie-breaking.  Recompute on
        # the next loop after each bounded batch so saturated axes redistribute.
        ranked = sorted(
            eligible,
            key=lambda key: (
                -(ideal[key] - floor(ideal[key])),
                order_index[key],
            ),
        )
        for key in ranked:
            if remaining <= 0:
                break
            if counts[key] >= capacities[key]:
                continue
            counts[key] += 1
            remaining -= 1
        if allocated == 0 and not ranked:
            break
    return remaining


def _substat_main_counts(
    layout: GcsimFiveStarMainStatLayout,
) -> dict[str, int]:
    counts = {key: 0 for key in GCSIM_SUBSTAT_ROLL_VALUES}
    for key in ("hp", "atk", layout.sands, layout.goblet, layout.circlet):
        if key in counts:
            counts[key] += 1
    return counts


def _normalized_weights(
    values: Iterable[StatWeight],
    *,
    axis_keys: Sequence[str],
    field_name: str,
) -> dict[str, float]:
    allowed = set(axis_keys)
    result = {key: 0.0 for key in axis_keys}
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, StatWeight):
            raise GcsimScreeningProfileError(
                f"{field_name} values must be StatWeight instances"
            )
        key = str(item.axis_key or "").strip()
        if key in seen:
            raise GcsimScreeningProfileError(
                f"{field_name} contains duplicate axis {key!r}"
            )
        seen.add(key)
        if key not in allowed:
            raise GcsimScreeningProfileError(
                f"{field_name} contains unsupported axis {key!r}"
            )
        value = float(item.weight)
        if not isfinite(value) or value <= 0:
            raise GcsimScreeningProfileError(
                f"{field_name} weights must be finite and positive"
            )
        result[key] = value
    total = sum(result.values())
    if total <= 0:
        raise GcsimScreeningProfileError(f"{field_name} must not be empty")
    return {key: value / total for key, value in result.items()}


def _normalize_character_mapping(
    values: Mapping[str, object],
    *,
    field_name: str,
) -> dict[str, object]:
    if not isinstance(values, Mapping):
        raise GcsimScreeningProfileError(f"{field_name} must be a mapping")
    normalized: dict[str, object] = {}
    for raw_key, value in values.items():
        key = str(raw_key or "").strip()
        _validated_character_key(key)
        folded = key.casefold()
        if folded in normalized:
            raise GcsimScreeningProfileError(
                f"{field_name} contains a normalized key collision for {key!r}"
            )
        normalized[folded] = value
    return normalized


def _require_exact_character_keys(
    values: Mapping[str, object],
    *,
    expected_keys: set[str],
    field_name: str,
) -> None:
    actual = set(values)
    if actual != expected_keys:
        raise GcsimScreeningProfileError(
            f"{field_name} must cover exactly the config characters; "
            f"missing={tuple(sorted(expected_keys - actual))!r}, "
            f"extra={tuple(sorted(actual - expected_keys))!r}"
        )


def _validated_character_key(value: str) -> str:
    key = str(value or "").strip()
    if not _PINNED_CHARACTER_RE.fullmatch(key):
        raise GcsimScreeningProfileError(
            "pinned optimizer character keys must contain lowercase ASCII letters only"
        )
    return key


def _validated_layout(
    value: GcsimFiveStarMainStatLayout,
) -> GcsimFiveStarMainStatLayout:
    if not isinstance(value, GcsimFiveStarMainStatLayout):
        raise GcsimScreeningProfileError(
            "screening layouts must be GcsimFiveStarMainStatLayout values"
        )
    # Reuse the public exact renderer as the legality validator.
    try:
        render_five_star_main_stat_line("probe", value)
    except ValueError as exc:
        raise GcsimScreeningProfileError(str(exc)) from exc
    return value


def _require_plain_int(
    value: int,
    *,
    field_name: str,
    minimum: int,
    maximum: int | None = None,
) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GcsimScreeningProfileError(f"{field_name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        maximum_text = "" if maximum is None else f" and <= {maximum}"
        raise GcsimScreeningProfileError(
            f"{field_name} must be >= {minimum}{maximum_text}"
        )


def _format_number(value: float) -> str:
    if not isfinite(value):
        raise GcsimScreeningProfileError("rendered stat value must be finite")
    if isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-15):
        return "0"
    return format(value, ".6g")


def _screening_investment_signature(
    *,
    reference_weights: Mapping[str, float],
    total_liquid_substats: int,
    individual_liquid_cap: int,
    fixed_substats_count: int,
) -> str:
    payload = {
        "contract": GCSIM_SCREENING_PROFILE_CONTRACT,
        "roll_values": [
            [key, GCSIM_SUBSTAT_ROLL_VALUES[key]]
            for key in GCSIM_SUBSTAT_ROLL_VALUES
        ],
        "reference_weights": [
            [key, reference_weights[key]]
            for key in GCSIM_SUBSTAT_ROLL_VALUES
        ],
        "total_liquid_substats": total_liquid_substats,
        "individual_liquid_cap": individual_liquid_cap,
        "fixed_substats_count": fixed_substats_count,
        "four_star_liquid_roll_penalty": FOUR_STAR_LIQUID_ROLL_PENALTY,
        "four_star_rarity_penalty": FOUR_STAR_RARITY_PENALTY,
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return f"{GCSIM_SCREENING_PROFILE_CONTRACT}:{digest}"


__all__ = [
    "DEFAULT_FIXED_SUBSTATS_COUNT",
    "DEFAULT_INDIVIDUAL_LIQUID_CAP",
    "DEFAULT_TOTAL_LIQUID_SUBSTATS",
    "FOUR_STAR_LIQUID_ROLL_PENALTY",
    "FOUR_STAR_RARITY_PENALTY",
    "GCSIM_BALANCED_REFERENCE_WEIGHTS",
    "GCSIM_SCREENING_PROFILE_CONTRACT",
    "GCSIM_SCREENING_STAT_AXES",
    "GCSIM_SUBSTAT_ROLL_VALUES",
    "GcsimScreeningCharacterProfile",
    "GcsimScreeningConfigRenderResult",
    "GcsimScreeningProfileError",
    "GcsimScreeningStatAllocation",
    "GcsimSubstatRollCount",
    "allocate_gcsim_screening_substats",
    "apply_gcsim_screening_runtime_options",
    "build_default_gcsim_screening_profile_bank",
    "build_gcsim_screening_investment_signature",
    "render_gcsim_screening_profile_config",
]
