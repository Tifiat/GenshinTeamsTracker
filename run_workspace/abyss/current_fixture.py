"""Invalid/static Abyss HP fixture for the first Fact DPS vertical slice.

This module is intentionally a temporary/manual fixture, not the final Abyss
period parser or runtime cache.

It pins the 2026-05-16 Floor 12 data that was researched in
docs/handoff/ABYSS_HP_FIXTURE.md so the app can build and test the first
backend-only Fact DPS path without network, UI, persistence, history, or GCSIM.

Important: the enemy HP values in this file are now known to be invalid for at
least some current Abyss enemies. They came from the old GCSIM/AnimeGameData
base-HP/curve inspection path, which does not match direct current tower HP
sources such as Nanoka for every enemy.

Keep this file only as an app-plumbing/sample fixture:
- it proves that the right-panel Fact DPS calculation path can consume Abyss HP;
- it must not be treated as a factual HP source;
- parser/debug work must replace these HP values with direct tower-period HP.

Future work should replace this fixture with the real update pipeline:
HoYoLAB period -> Nanoka/direct tower HP -> matched Fandom/guide cross-check ->
monster_id/gcsim_key resolver -> source-backed HP totals.

Do not treat this file as proof that 2026-05-16 is always the current Abyss.
"""

from __future__ import annotations
from dataclasses import dataclass

CURRENT_HP_KIND = "current_3_75"
FALLBACK_HP_KIND = "fallback_2_5"


@dataclass(frozen=True, slots=True)
class AbyssEnemyFixture:
    source_name: str
    monster_id: str
    level: int
    normal_hp: int
    fallback_2_5_hp: int
    current_3_75_hp: int
    gcsim_key: str = ""
    hp_curve: str = ""
    notes: tuple[str, ...] = ()

    def hp_for_kind(self, hp_kind: str = CURRENT_HP_KIND) -> int:
        if hp_kind == CURRENT_HP_KIND:
            return self.current_3_75_hp
        if hp_kind == FALLBACK_HP_KIND:
            return self.fallback_2_5_hp
        raise ValueError(f"Unsupported HP kind: {hp_kind}")


@dataclass(frozen=True, slots=True)
class AbyssSideFixture:
    chamber_index: int
    side: int
    enemies: tuple[AbyssEnemyFixture, ...]
    normal_total_hp: int
    fallback_2_5_total_hp: int
    current_3_75_total_hp: int
    confidence: str
    notes: tuple[str, ...] = ()

    def total_hp_for_kind(self, hp_kind: str = CURRENT_HP_KIND) -> int:
        if hp_kind == CURRENT_HP_KIND:
            return self.current_3_75_total_hp
        if hp_kind == FALLBACK_HP_KIND:
            return self.fallback_2_5_total_hp
        raise ValueError(f"Unsupported HP kind: {hp_kind}")


@dataclass(frozen=True, slots=True)
class AbyssChamberFixture:
    chamber_index: int
    display_level: int
    first_half: AbyssSideFixture
    second_half: AbyssSideFixture

    def side(self, side: int) -> AbyssSideFixture:
        if side == 1:
            return self.first_half
        if side == 2:
            return self.second_half
        raise ValueError(f"Unsupported Abyss side: {side}")


@dataclass(frozen=True, slots=True)
class AbyssFloorFixture:
    floor_index: int
    floor_id: int
    period_id: str
    period_start: str
    period_end: str
    hp_multiplier_current: float
    hp_multiplier_fallback: float
    period_source: str
    lineup_source: str
    multiplier_source: str
    stat_source: str
    chambers: tuple[AbyssChamberFixture, ...]
    notes: tuple[str, ...] = ()

    def chamber(self, chamber_index: int) -> AbyssChamberFixture:
        for chamber in self.chambers:
            if chamber.chamber_index == chamber_index:
                return chamber
        raise ValueError(f"Unsupported Abyss chamber: {chamber_index}")

    def side(self, chamber_index: int, side: int) -> AbyssSideFixture:
        return self.chamber(chamber_index).side(side)


def _enemy(
    source_name: str,
    monster_id: int | str,
    *,
    level: int,
    normal_hp: int,
    fallback_2_5_hp: int,
    current_3_75_hp: int,
    gcsim_key: str = "",
    hp_curve: str = "",
    notes: tuple[str, ...] = (),
) -> AbyssEnemyFixture:
    return AbyssEnemyFixture(
        source_name=source_name,
        monster_id=str(monster_id),
        level=level,
        normal_hp=normal_hp,
        fallback_2_5_hp=fallback_2_5_hp,
        current_3_75_hp=current_3_75_hp,
        gcsim_key=gcsim_key,
        hp_curve=hp_curve,
        notes=notes,
    )


def _side(
    *,
    chamber_index: int,
    side: int,
    enemies: tuple[AbyssEnemyFixture, ...],
    normal_total_hp: int,
    fallback_2_5_total_hp: int,
    current_3_75_total_hp: int,
    confidence: str = "invalid_static_hp_fixture_for_ui_plumbing_only",
    notes: tuple[str, ...] = (),
) -> AbyssSideFixture:
    return AbyssSideFixture(
        chamber_index=chamber_index,
        side=side,
        enemies=enemies,
        normal_total_hp=normal_total_hp,
        fallback_2_5_total_hp=fallback_2_5_total_hp,
        current_3_75_total_hp=current_3_75_total_hp,
        confidence=confidence,
        notes=notes,
    )


CURRENT_ABYSS_FLOOR12_FIXTURE = AbyssFloorFixture(
    floor_index=12,
    floor_id=1129,
    period_id="2026-05-16",
    period_start="2026-05-16",
    period_end="2026-06-16",
    hp_multiplier_current=3.75,
    hp_multiplier_fallback=2.5,
    period_source="manual_fixture_matches_hoyolab_spiral_abyss_overview",
    lineup_source="fandom_spiral_abyss_floors_2026_05_16",
    multiplier_source="animegamedata_stage12_new2_text_hash_48688570",
    stat_source="invalid_old_gcsim_animegamedata_base_hp_curve_fixture",
    notes=(
        "This is an invalid/static fixture for UI plumbing, not the final parser/cache.",
        "Do not use these HP values as factual current Abyss enemy HP.",
        "Some values are known to disagree with direct tower HP data such as Nanoka.",
        "HoYoLAB period should become the runtime current-period authority.",
        "Nanoka/direct tower data should become the primary source for current HP.",
        "Fandom period page supplies observable lineup names and display levels as cross-check.",
        "AnimeGameData Stage12_New2 +275% is treated as current 3.75x estimate.",
        "Fandom Floor 12 2.5x remains a fallback/cross-check.",
    ),
    chambers=(
        AbyssChamberFixture(
            chamber_index=1,
            display_level=95,
            first_half=_side(
                chamber_index=1,
                side=1,
                enemies=(
                    _enemy(
                        "Super-Heavy Landrover: Mechanized Fortress",
                        "23090101",
                        level=95,
                        hp_curve="HP_2",
                        normal_hp=999_431,
                        fallback_2_5_hp=2_498_576,
                        current_3_75_hp=3_747_864,
                        gcsim_key="superheavylandrovermechanizedfortress",
                        notes=(
                            "Monster id variant should remain reviewable.",
                            "Abyss-specific RES states exist on Fandom enemy page.",
                        ),
                    ),
                ),
                normal_total_hp=999_431,
                fallback_2_5_total_hp=2_498_576,
                current_3_75_total_hp=3_747_864,
            ),
            second_half=_side(
                chamber_index=1,
                side=2,
                enemies=(
                    _enemy(
                        "Hydro Hilichurl Rogue",
                        "21040201",
                        level=95,
                        hp_curve="HP_2",
                        normal_hp=227_143,
                        fallback_2_5_hp=567_858,
                        current_3_75_hp=851_787,
                        gcsim_key="hydrohilichurlrogue",
                        notes=("Hydro RES 50%.",),
                    ),
                    _enemy(
                        "Lord of the Hidden Depths: Whisperer of Nightmares",
                        "22150101",
                        level=95,
                        hp_curve="HP_2",
                        normal_hp=1_226_574,
                        fallback_2_5_hp=3_066_435,
                        current_3_75_hp=4_599_652,
                        gcsim_key="lordofthehiddendepthswhispererofnightmares",
                        notes=(
                            "Do not use Stygian Onslaught HP for ordinary Abyss.",
                        ),
                    ),
                ),
                normal_total_hp=1_453_717,
                fallback_2_5_total_hp=3_634_293,
                current_3_75_total_hp=5_451_439,
            ),
        ),
        AbyssChamberFixture(
            chamber_index=2,
            display_level=98,
            first_half=_side(
                chamber_index=2,
                side=1,
                enemies=(
                    _enemy(
                        "Fatui Electro Cicin Mage",
                        "23030101",
                        level=98,
                        hp_curve="HP",
                        normal_hp=153_291,
                        fallback_2_5_hp=383_228,
                        current_3_75_hp=574_842,
                        gcsim_key="fatuielectrocicinmage",
                        notes=("Electro RES 50%; Physical RES -20%.",),
                    ),
                    _enemy(
                        "Ruin Drake: Earthguard",
                        "24030201",
                        level=98,
                        hp_curve="HP_2",
                        normal_hp=360_504,
                        fallback_2_5_hp=901_260,
                        current_3_75_hp=1_351_891,
                        gcsim_key="ruindrakeearthguard",
                        notes=("Physical RES 50%.",),
                    ),
                    _enemy(
                        "Primo Geovishap (Cryo)",
                        "26050301",
                        level=98,
                        hp_curve="HP",
                        normal_hp=919_747,
                        fallback_2_5_hp=2_299_367,
                        current_3_75_hp=3_449_051,
                        gcsim_key="primogeovishap",
                        notes=(
                            "Cryo variant must not be silently replaced by generic id.",
                        ),
                    ),
                ),
                normal_total_hp=1_433_542,
                fallback_2_5_total_hp=3_583_856,
                current_3_75_total_hp=5_375_784,
            ),
            second_half=_side(
                chamber_index=2,
                side=2,
                enemies=(
                    _enemy(
                        "Battle-Hardened Grounded Geoshroom",
                        "26120501",
                        level=98,
                        hp_curve="HP_2",
                        normal_hp=4_542_352,
                        fallback_2_5_hp=11_355_881,
                        current_3_75_hp=17_033_821,
                        gcsim_key="battlehardenedgroundedgeoshroom",
                        notes=("Yatta detail was stale/404 during research.",),
                    ),
                ),
                normal_total_hp=4_542_352,
                fallback_2_5_total_hp=11_355_881,
                current_3_75_total_hp=17_033_821,
            ),
        ),
        AbyssChamberFixture(
            chamber_index=3,
            display_level=100,
            first_half=_side(
                chamber_index=3,
                side=1,
                enemies=(
                    _enemy(
                        "Hexadecatonic Battle-Hardened Mandragora",
                        "20081201",
                        level=100,
                        hp_curve="HP_2",
                        normal_hp=3_549_441,
                        fallback_2_5_hp=8_873_603,
                        current_3_75_hp=13_310_405,
                        gcsim_key="hexadecatonicbattlehardenedmandragora",
                        notes=("Dendro RES 135%.",),
                    ),
                ),
                normal_total_hp=3_549_441,
                fallback_2_5_total_hp=8_873_603,
                current_3_75_total_hp=13_310_405,
            ),
            second_half=_side(
                chamber_index=3,
                side=2,
                enemies=(
                    _enemy(
                        "Ruin Guard",
                        "24010101",
                        level=100,
                        hp_curve="HP",
                        normal_hp=257_356,
                        fallback_2_5_hp=643_390,
                        current_3_75_hp=965_084,
                        gcsim_key="ruinguard",
                        notes=("Physical RES 70%.",),
                    ),
                    _enemy(
                        "Battle-Scarred Rock Crab",
                        "26162601",
                        level=100,
                        hp_curve="HP_2",
                        normal_hp=5_834_394,
                        fallback_2_5_hp=14_585_984,
                        current_3_75_hp=21_878_976,
                        gcsim_key="battlescarredrockcrab",
                        notes=("Yatta detail was stale/404 during research.",),
                    ),
                ),
                normal_total_hp=6_091_750,
                fallback_2_5_total_hp=15_229_374,
                current_3_75_total_hp=22_844_061,
            ),
        ),
    ),
)


def current_abyss_floor12_data() -> AbyssFloorFixture:
    """Return current Floor 12 Abyss data for Fact DPS calculations.

    Temporary implementation: this currently returns the static 2026-05-16
    fixture above. Its HP values are intentionally marked invalid/sample-only.
    Keep this public API name stable; future work should replace the
    implementation with the real HoYoLAB/Nanoka/Fandom/parser/cache pipeline
    without changing right-panel callers.
    """
    return CURRENT_ABYSS_FLOOR12_FIXTURE


def current_floor12_fixture() -> AbyssFloorFixture:
    return CURRENT_ABYSS_FLOOR12_FIXTURE