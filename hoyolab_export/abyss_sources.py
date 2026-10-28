from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen


FANDOM_API_URL = "https://genshin-impact.fandom.com/api.php"

SIDE_FIRST = "first"
SIDE_SECOND = "second"

WARNING_ENEMY_DATA_UNAVAILABLE = "enemy_data_unavailable"
WARNING_FLOOR_SECTION_NOT_FOUND = "floor_section_not_found"
WARNING_HP_ESTIMATE_UNAVAILABLE = "hp_estimate_unavailable"

CONFIDENCE_FANDOM_FLOOR_SCALING_ESTIMATE = "fandom_floor_scaling_estimate"
CONFIDENCE_SOURCE_LIKE_PERIOD_MULTIPLIER = "source_like_period_multiplier"
CONFIDENCE_UNAVAILABLE = "unavailable"

FLOOR_12_FALLBACK_MULTIPLIER = 2.5
FLOOR_12_STAGE12_NEW2_MULTIPLIER = 3.75


@dataclass(frozen=True, slots=True)
class AbyssPeriodRef:
    source_url: str
    page_title: str = ""
    floor: int = 12
    lang: str = "en"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "page_title": self.page_title,
            "floor": self.floor,
            "lang": self.lang,
        }


@dataclass(frozen=True, slots=True)
class KnownAbyssEnemyStats:
    display_name: str
    monster_id: str
    source_key: str
    level: int
    normal_hp: float
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AbyssHpEstimate:
    confidence: str
    multiplier: float | None = None
    hp: float | None = None
    source: str = ""
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "multiplier": self.multiplier,
            "hp": self.hp,
            "source": self.source,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class AbyssEnemyOccurrence:
    chamber_index: int
    side: str
    wave_index: int
    name: str
    count: int = 1
    level: int | None = None
    normalized_name: str = ""
    monster_id: str = ""
    source_key: str = ""
    hp_estimates: tuple[AbyssHpEstimate, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "chamber_index": self.chamber_index,
            "side": self.side,
            "wave_index": self.wave_index,
            "name": self.name,
            "count": self.count,
            "level": self.level,
            "normalized_name": self.normalized_name,
            "monster_id": self.monster_id,
            "source_key": self.source_key,
            "hp_estimates": [estimate.to_dict() for estimate in self.hp_estimates],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class AbyssChamberSideReport:
    chamber_index: int
    side: str
    level: int | None = None
    enemies: tuple[AbyssEnemyOccurrence, ...] = ()
    total_hp_estimates: tuple[AbyssHpEstimate, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "chamber_index": self.chamber_index,
            "side": self.side,
            "level": self.level,
            "enemies": [enemy.to_dict() for enemy in self.enemies],
            "total_hp_estimates": [
                estimate.to_dict()
                for estimate in self.total_hp_estimates
            ],
            "warnings": list(self.warnings),
        }


def page_title_from_fandom_url(url: str) -> str:
    path = urlparse(url).path
    marker = "/wiki/"
    if marker not in path:
        return path.strip("/")
    return unquote(path.split(marker, 1)[1])


def fetch_fandom_wikitext(page_title: str, *, timeout: int = 30) -> str:
    encoded = quote(page_title, safe="/:")
    url = (
        f"{FANDOM_API_URL}?action=parse&page={encoded}"
        "&prop=wikitext&format=json"
    )
    request = Request(
        url,
        headers={"User-Agent": "GenshinTeamsTracker abyss report"},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    try:
        return str(payload["parse"]["wikitext"]["*"])
    except KeyError as exc:
        raise RuntimeError(f"Unexpected Fandom parse response for {page_title}") from exc


def normalize_enemy_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^a-z0-9]+", "", text)


def parse_abyss_period_wikitext(
    wikitext: str,
    *,
    period_ref: AbyssPeriodRef | None = None,
    floor: int = 12,
) -> tuple[AbyssChamberSideReport, ...]:
    section, section_warnings = extract_floor_section(wikitext, floor=floor)
    levels = _parse_level_fields(section)
    enemy_fields = _parse_enemy_fields(section)
    reports: list[AbyssChamberSideReport] = []
    for chamber_index in sorted(enemy_fields):
        for side_number, side_name in ((1, SIDE_FIRST), (2, SIDE_SECOND)):
            raw = enemy_fields[chamber_index].get(side_number)
            if not raw:
                continue
            level = levels.get(chamber_index)
            enemies = _parse_enemy_occurrences(
                raw,
                chamber_index=chamber_index,
                side=side_name,
                level=level,
            )
            reports.append(
                AbyssChamberSideReport(
                    chamber_index=chamber_index,
                    side=side_name,
                    level=level,
                    enemies=enemies,
                    warnings=tuple(section_warnings),
                )
            )
    return tuple(reports)


def build_chamber_side_report_with_hp(
    report: AbyssChamberSideReport,
    *,
    known_enemies: dict[str, KnownAbyssEnemyStats] | None = None,
) -> AbyssChamberSideReport:
    known_enemies = known_enemies or CURRENT_FLOOR_12_KNOWN_ENEMIES
    enemies = tuple(
        _attach_hp_estimates(enemy, known_enemies=known_enemies)
        for enemy in report.enemies
    )
    totals = _total_estimates(enemies)
    warnings = list(report.warnings)
    for enemy in enemies:
        warnings.extend(enemy.warnings)
    if any(estimate.confidence == CONFIDENCE_UNAVAILABLE for estimate in totals):
        warnings.append(WARNING_HP_ESTIMATE_UNAVAILABLE)
    return AbyssChamberSideReport(
        chamber_index=report.chamber_index,
        side=report.side,
        level=report.level,
        enemies=enemies,
        total_hp_estimates=totals,
        warnings=tuple(_dedupe(warnings)),
    )


def build_current_floor_12_fixture_reports_from_wikitext(
    wikitext: str,
    *,
    period_url: str = "",
) -> tuple[AbyssChamberSideReport, ...]:
    period_ref = AbyssPeriodRef(
        source_url=period_url,
        page_title=page_title_from_fandom_url(period_url) if period_url else "",
        floor=12,
    )
    parsed = parse_abyss_period_wikitext(wikitext, period_ref=period_ref, floor=12)
    return tuple(build_chamber_side_report_with_hp(report) for report in parsed)


def extract_floor_section(wikitext: str, *, floor: int) -> tuple[str, list[str]]:
    pattern = re.compile(
        rf"(?ims)^==+\s*Floor\s+{floor}\s*==+\s*(.*?)(?=^==+\s*Floor\s+\d+\s*==+|\Z)"
    )
    match = pattern.search(wikitext)
    if match:
        return match.group(1), []
    return wikitext, [WARNING_FLOOR_SECTION_NOT_FOUND]


def _parse_level_fields(section: str) -> dict[int, int]:
    result: dict[int, int] = {}
    for match in re.finditer(r"(?m)^\s*\|\s*level(\d+)\s*=\s*(\d+)", section):
        result[int(match.group(1))] = int(match.group(2))
    return result


def _parse_enemy_fields(section: str) -> dict[int, dict[int, str]]:
    result: dict[int, dict[int, str]] = {}
    pattern = re.compile(
        r"(?m)^\s*\|\s*enemies(\d+)_(\d+)\s*=\s*(.+?)\s*$"
    )
    for match in pattern.finditer(section):
        chamber_index = int(match.group(1))
        side_number = int(match.group(2))
        result.setdefault(chamber_index, {})[side_number] = match.group(3).strip()
    return result


def _parse_enemy_occurrences(
    raw: str,
    *,
    chamber_index: int,
    side: str,
    level: int | None,
) -> tuple[AbyssEnemyOccurrence, ...]:
    waves = [part.strip() for part in re.split(r"\s*//\s*", raw) if part.strip()]
    if not waves:
        waves = [raw]
    result: list[AbyssEnemyOccurrence] = []
    for wave_index, wave in enumerate(waves, start=1):
        for name, count in _parse_wave_enemy_names(wave):
            result.append(
                AbyssEnemyOccurrence(
                    chamber_index=chamber_index,
                    side=side,
                    wave_index=wave_index,
                    name=name,
                    count=count,
                    level=level,
                    normalized_name=normalize_enemy_name(name),
                )
            )
    return tuple(result)


def _parse_wave_enemy_names(wave: str) -> list[tuple[str, int]]:
    text = _strip_wiki_markup(wave)
    parts = [
        part.strip()
        for part in re.split(r"\s*(?:<br\s*/?>|\n|;)\s*", text)
        if part.strip()
    ]
    if not parts:
        parts = [text]
    result: list[tuple[str, int]] = []
    for part in parts:
        count = 1
        count_match = re.search(r"(?:\*|x|×)\s*(\d+)\s*$", part, flags=re.I)
        if count_match:
            count = int(count_match.group(1))
            part = part[: count_match.start()].strip()
        part = part.strip(" -")
        if part:
            result.append((part, count))
    return result


def _strip_wiki_markup(value: str) -> str:
    text = re.sub(r"<!--.*?-->", "", value)
    text = re.sub(r"\[\[[^|\]]+\|([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\{\{[^{}|]+\|([^{}]+)\}\}", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    return text.strip()


def _attach_hp_estimates(
    enemy: AbyssEnemyOccurrence,
    *,
    known_enemies: dict[str, KnownAbyssEnemyStats],
) -> AbyssEnemyOccurrence:
    known = known_enemies.get(enemy.normalized_name)
    if known is None:
        unavailable = AbyssHpEstimate(
            confidence=CONFIDENCE_UNAVAILABLE,
            warnings=(WARNING_ENEMY_DATA_UNAVAILABLE,),
        )
        return AbyssEnemyOccurrence(
            chamber_index=enemy.chamber_index,
            side=enemy.side,
            wave_index=enemy.wave_index,
            name=enemy.name,
            count=enemy.count,
            level=enemy.level,
            normalized_name=enemy.normalized_name,
            hp_estimates=(unavailable,),
            warnings=(WARNING_ENEMY_DATA_UNAVAILABLE,),
        )
    hp = known.normal_hp * enemy.count
    estimates = (
        AbyssHpEstimate(
            confidence=CONFIDENCE_FANDOM_FLOOR_SCALING_ESTIMATE,
            multiplier=FLOOR_12_FALLBACK_MULTIPLIER,
            hp=hp * FLOOR_12_FALLBACK_MULTIPLIER,
            source="Fandom Enemy/Level_Scaling Floor 12 fallback",
        ),
        AbyssHpEstimate(
            confidence=CONFIDENCE_SOURCE_LIKE_PERIOD_MULTIPLIER,
            multiplier=FLOOR_12_STAGE12_NEW2_MULTIPLIER,
            hp=hp * FLOOR_12_STAGE12_NEW2_MULTIPLIER,
            source="AnimeGameData LevelEntity_Monster_HpUp_Stage12_New2",
        ),
    )
    return AbyssEnemyOccurrence(
        chamber_index=enemy.chamber_index,
        side=enemy.side,
        wave_index=enemy.wave_index,
        name=enemy.name,
        count=enemy.count,
        level=enemy.level or known.level,
        normalized_name=enemy.normalized_name,
        monster_id=known.monster_id,
        source_key=known.source_key,
        hp_estimates=estimates,
        warnings=known.notes,
    )


def _total_estimates(
    enemies: Iterable[AbyssEnemyOccurrence],
) -> tuple[AbyssHpEstimate, ...]:
    buckets: dict[tuple[str, float | None, str], float] = {}
    unavailable = False
    for enemy in enemies:
        for estimate in enemy.hp_estimates:
            if estimate.hp is None:
                unavailable = True
                continue
            key = (estimate.confidence, estimate.multiplier, estimate.source)
            buckets[key] = buckets.get(key, 0.0) + estimate.hp
    result = [
        AbyssHpEstimate(
            confidence=confidence,
            multiplier=multiplier,
            hp=hp,
            source=source,
        )
        for (confidence, multiplier, source), hp in sorted(buckets.items())
    ]
    if unavailable:
        result.append(
            AbyssHpEstimate(
                confidence=CONFIDENCE_UNAVAILABLE,
                warnings=(WARNING_HP_ESTIMATE_UNAVAILABLE,),
            )
        )
    return tuple(result)


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _known_enemy(
    display_name: str,
    monster_id: str,
    source_key: str,
    level: int,
    normal_hp: float,
    *notes: str,
) -> tuple[str, KnownAbyssEnemyStats]:
    return (
        normalize_enemy_name(display_name),
        KnownAbyssEnemyStats(
            display_name=display_name,
            monster_id=monster_id,
            source_key=source_key,
            level=level,
            normal_hp=normal_hp,
            notes=tuple(notes),
        ),
    )


CURRENT_FLOOR_12_KNOWN_ENEMIES = dict(
    [
        _known_enemy(
            "Super-Heavy Landrover: Mechanized Fortress",
            "23090101",
            "superheavylandrovermechanizedfortress",
            95,
            999430.5333333333,
            "landrover_abyss_state_res",
        ),
        _known_enemy(
            "Hydro Hilichurl Rogue",
            "21040201",
            "hydrohilichurlrogue",
            95,
            227143.2,
        ),
        _known_enemy(
            "Lord of the Hidden Depths: Whisperer of Nightmares",
            "22150101",
            "lordofthehiddendepthswhispererofnightmares",
            95,
            1226573.8666666667,
            "do_not_use_stygian_stats_by_default",
        ),
        _known_enemy(
            "Fatui Electro Cicin Mage",
            "23030101",
            "fatuielectrocicinmage",
            98,
            153291.2,
        ),
        _known_enemy(
            "Ruin Drake: Earthguard",
            "24030201",
            "ruindrakeearthguard",
            98,
            360504.26666666666,
        ),
        _known_enemy(
            "Primo Geovishap (Cryo)",
            "26050301",
            "primogeovishapcryo",
            98,
            919746.8,
            "cryo_variant_id_required",
        ),
        _known_enemy(
            "Battle-Hardened Grounded Geoshroom",
            "26120501",
            "battlehardenedgroundedgeoshroom",
            98,
            4542352.4,
            "newer_enemy_yatta_gap",
        ),
        _known_enemy(
            "Hexadecatonic Battle-Hardened Mandragora",
            "20081201",
            "hexadecatonicbattlehardenedmandragora",
            100,
            3549441.3333333335,
            "mode_specific_stats",
        ),
        _known_enemy(
            "Ruin Guard",
            "24010101",
            "ruinguard",
            100,
            257356.0,
        ),
        _known_enemy(
            "Battle-Scarred Rock Crab",
            "26162601",
            "battlescarredrockcrab",
            100,
            5834393.6,
            "newer_enemy_yatta_gap",
        ),
    ]
)
