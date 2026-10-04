"""Independent tooltip facts, reviewed against HoYoWiki on 2026-10-04.

These expectations are deliberately separate from the catalog/importer and the
renderers. They describe numbers, mechanics and piece boundaries, not HTML or a
verbatim copy of a translated paragraph. Extend this list when an imported
inventory has no witness. The first owned witness is enough for a local check.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import re
from typing import Callable, Iterable
import warnings


class TooltipCoverageWarning(UserWarning):
    """The available account cannot exercise a known semantic witness."""


@dataclass(frozen=True)
class BonusFacts:
    percentages: tuple[int, ...]
    terms: tuple[str, ...]


@dataclass(frozen=True)
class KnownSet:
    uid: str
    name: str
    source: str
    facts: dict[str, dict[int, BonusFacts]]


KNOWN_SETS = (
    KnownSet("EmblemOfSeveredFate", "Emblem of Severed Fate",
             "https://wiki.hoyolab.com/pc/genshin/entry/2090", {
        "en-us": {2: BonusFacts((20,), (r"energy recharge",)),
                  4: BonusFacts((25, 75), (r"elemental burst", r"energy recharge", r"max(?:imum)?"))},
        "ru-ru": {2: BonusFacts((20,), (r"восстановлени[яе] энергии",)),
                  4: BonusFacts((25, 75), (r"взрыва стихи", r"восстановлени[яе] энергии", r"максимум"))},
        "pt-pt": {2: BonusFacts((20,), (r"recarga de energia",)),
                  4: BonusFacts((25, 75), (r"supremo", r"recarga de energia", r"máximo"))},
    }),
    KnownSet("DeepwoodMemories", "Deepwood Memories",
             "https://wiki.hoyolab.com/pc/genshin/entry/2672", {
        "en-us": {2: BonusFacts((15,), (r"dendro", r"dmg|damage")),
                  4: BonusFacts((30,), (r"elemental skills?", r"bursts?", r"dendro res", r"\b8\s*s\b", r"not on the field|off.field"))},
        "ru-ru": {2: BonusFacts((15,), (r"дендро", r"урон")),
                  4: BonusFacts((30,), (r"элементальн\w* навык", r"взрыв\w* стихи", r"дендро сопротивление", r"\b8\s*сек", r"не на поле боя"))},
        "pt-pt": {2: BonusFacts((15,), (r"dendro", r"dano")),
                  4: BonusFacts((30,), (r"habilidades? elementa", r"supremos?", r"res dendro", r"\b8\s*s\b", r"não estiver em campo"))},
    }),
    KnownSet("NoblesseOblige", "Noblesse Oblige",
             "https://wiki.hoyolab.com/pc/genshin/entry/2075", {
        "en-us": {2: BonusFacts((20,), (r"elemental burst",)),
                  4: BonusFacts((20,), (r"elemental burst", r"all party members", r"atk", r"\b12\s*s\b", r"cannot stack"))},
        "ru-ru": {2: BonusFacts((20,), (r"взрыва стихи",)),
                  4: BonusFacts((20,), (r"взрыва стихи", r"силу атаки", r"всех членов отряда", r"\b12\s*сек", r"не складывается"))},
        "pt-pt": {2: BonusFacts((20,), (r"supremo",)),
                  4: BonusFacts((20,), (r"supremo", r"atq", r"todos os membros da equipe", r"\b12\s*s\b", r"não pode ser acumulado"))},
    }),
)

# HoYoWiki serves Portuguese under pt-pt; imported catalogs can also use the
# application's pt-br spelling. Both must satisfy the same Portuguese facts,
# rather than accepting English text accidentally saved with a Portuguese tag.
for _candidate in KNOWN_SETS:
    _candidate.facts["pt-br"] = dict(_candidate.facts["pt-pt"])


def first_available_witness(
    available: Iterable[str], check: Callable[[KnownSet], None],
) -> str | None:
    """Absence advances; the FIRST present witness must pass (never skip damage)."""
    available = set(available)
    for candidate in KNOWN_SETS:
        if candidate.uid in available:
            check(candidate)
            return candidate.uid
    warnings.warn(
        "No known artifact set in the imported inventory; extend the tooltip "
        "autotest with an available set (дописать автотест тултипов).",
        TooltipCoverageWarning, stacklevel=2,
    )
    return None


class _BonusRows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[int, str]] = []
        self.cells: list[str] = []
        self.in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.cells = []
        elif tag == "td":
            self.cells.append("")
            self.in_cell = True
        elif tag in {"br", "p"} and self.in_cell:
            self.cells[-1] += " "

    def handle_data(self, data):
        if self.in_cell:
            self.cells[-1] += data

    def handle_endtag(self, tag):
        if tag == "td":
            self.in_cell = False
        elif tag == "tr" and len(self.cells) == 2:
            self.rows.append((int(self.cells[0].strip()), self.cells[1]))


def assert_bonus_tooltip(text: str, candidate: KnownSet, languages: dict[int, str], *, pieces=4):
    parser = _BonusRows()
    parser.feed(text)
    expected_pieces = (2, 4) if pieces >= 4 else (2,)
    assert tuple(row[0] for row in parser.rows) == expected_pieces, (
        f"{candidate.uid}: missing, duplicate or misplaced bonus rows: {parser.rows!r}"
    )
    for piece_count, body in parser.rows:
        language = languages[piece_count]
        assert language in candidate.facts, f"Add a {language} tooltip witness for {candidate.uid}"
        facts = candidate.facts[language][piece_count]
        plain = re.sub(r"\s+", " ", body).strip()
        assert "<" not in plain and "&lt;" not in plain, f"Leaked markup: {plain}"
        percentages = tuple(int(n) for n in re.findall(r"(\d+)\s*%", plain))
        assert percentages == facts.percentages, (
            f"{candidate.uid}/{piece_count}p/{language}: expected percentages "
            f"{facts.percentages}, got {percentages}: {plain}"
        )
        for pattern in facts.terms:
            assert re.search(pattern, plain, re.IGNORECASE), (
                f"{candidate.uid}/{piece_count}p/{language}: missing fact {pattern!r}: {plain}"
            )
