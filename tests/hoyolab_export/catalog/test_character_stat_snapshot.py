from __future__ import annotations

import unittest

from hoyolab_export.character_stat_snapshot import (
    SNAPSHOT_STATUS_PARTIAL,
    SNAPSHOT_STATUS_READY,
    SNAPSHOT_STATUS_UNSUPPORTED,
    VALUE_SELECTION_AFTER,
    VALUE_SELECTION_AMBIGUOUS,
    VALUE_SELECTION_BEFORE,
    VALUE_SELECTION_SINGLE,
    WARNING_ARTIFACT_SUMMARY_MISSING,
    WARNING_ASCENSION_PHASE_UNKNOWN,
    WARNING_CHARACTER_ASCENSION_PHASE_ASSUMED,
    WARNING_CHARACTER_STATS_UNAVAILABLE,
    WARNING_INTERPOLATION_NOT_IMPLEMENTED,
    WARNING_LEVEL_95_100_FALLBACK_TO_90,
    WARNING_LEVEL_ROW_UNAVAILABLE,
    WARNING_FINAL_TOTALS_NOT_COMPUTED,
    WARNING_TRAVELER_SPECIAL_DEFERRED,
    WARNING_WEAPON_PASSIVE_NOT_INCLUDED,
    build_weapon_stat_contribution,
    build_character_stat_snapshot,
)
from hoyolab_export.character_stats_catalog import (
    CharacterBaseStatRow,
    CharacterBaseStatsEntry,
    StatValuePair,
)
from hoyolab_export.weapon_stats_catalog import (
    WeaponAtkValuePair,
    WeaponBaseStatRow,
    WeaponReferenceField,
    WeaponReferenceInfo,
    WeaponStatsEntry,
)


def character_entry() -> CharacterBaseStatsEntry:
    return CharacterBaseStatsEntry(
        entry_page_id="14",
        name="Amber",
        lang="en-us",
        rows=(
            CharacterBaseStatRow(
                level_key="Lv.1",
                base_hp=StatValuePair(after="793"),
                base_atk=StatValuePair(after="19"),
                base_def=StatValuePair(after="50"),
                ascension_bonus_stat_type="ATK",
                ascension_bonus=StatValuePair(after="0.0%"),
            ),
            CharacterBaseStatRow(
                level_key="Lv.20",
                base_hp=StatValuePair(before="2038", after="2630"),
                base_atk=StatValuePair(before="48", after="62"),
                base_def=StatValuePair(before="129", after="167"),
                ascension_bonus_stat_type="ATK",
                ascension_bonus=StatValuePair(before="0.0%", after="6.0%"),
            ),
        ),
    )


def weapon_entry(with_passive: bool = False) -> WeaponStatsEntry:
    reference_info = WeaponReferenceInfo()
    if with_passive:
        reference_info = WeaponReferenceInfo(
            weapon_type="Bow",
            secondary_attribute="Energy Recharge",
            passive_fields=(
                WeaponReferenceField(
                    key="Windfall",
                    values=("CRIT Hits generate particles.",),
                ),
            ),
        )
    return WeaponStatsEntry(
        entry_page_id="2019",
        name="Favonius Warbow",
        lang="en-us",
        rows=(
            WeaponBaseStatRow(
                level_key="Lv.1",
                base_atk=WeaponAtkValuePair(after="41"),
                secondary_stat_type="Energy Recharge",
                secondary_stat_value="13.3%",
            ),
            WeaponBaseStatRow(
                level_key="Lv.20",
                base_atk=WeaponAtkValuePair(before="99", after="125"),
                secondary_stat_type="Energy Recharge",
                secondary_stat_value="23.6%",
            ),
        ),
        reference_info=reference_info,
    )


class CharacterStatSnapshotTest(unittest.TestCase):
    def test_ready_character_and_weapon_snapshot_with_artifact_summary(self) -> None:
        snapshot = build_character_stat_snapshot(
            account_character={
                "id": 1,
                "name": "Amber",
                "level": 1,
                "rarity": 4,
                "constellation": 6,
            },
            character_stats_entry=character_entry(),
            account_weapon={
                "id": 2,
                "name": "Favonius Warbow",
                "level": 1,
                "refinement": 5,
                "type_name": "bow",
            },
            weapon_stats_entry=weapon_entry(),
            artifact_summary={"stat_totals": {"crit_rate": "10.0%"}},
        )

        self.assertEqual(snapshot.status, SNAPSHOT_STATUS_READY)
        self.assertEqual(snapshot.character_base.base_hp.selected, "793")
        self.assertEqual(snapshot.weapon.base_atk.selected, "41")
        self.assertEqual(snapshot.weapon.secondary_stat_type, "Energy Recharge")
        self.assertIn(WARNING_FINAL_TOTALS_NOT_COMPUTED, snapshot.warnings)

    def test_character_ascension_bonus_is_separate_from_base_stats(self) -> None:
        snapshot = build_character_stat_snapshot(
            account_character={"id": 1, "name": "Amber", "level": 1},
            character_stats_entry=character_entry(),
            account_weapon={"id": 2, "name": "Favonius Warbow", "level": 1},
            weapon_stats_entry=weapon_entry(),
            artifact_summary={},
        )

        self.assertEqual(snapshot.character_base.base_atk.selected, "19")
        self.assertEqual(snapshot.character_base.ascension_bonus_stat_type, "ATK")
        self.assertEqual(snapshot.character_base.ascension_bonus.selected, "0.0%")

    def test_weapon_passive_text_is_warned_not_applied(self) -> None:
        snapshot = build_character_stat_snapshot(
            account_character={"id": 1, "name": "Amber", "level": 1},
            character_stats_entry=character_entry(),
            account_weapon={"id": 2, "name": "Favonius Warbow", "level": 1},
            weapon_stats_entry=weapon_entry(with_passive=True),
            artifact_summary={},
        )

        self.assertIn(WARNING_WEAPON_PASSIVE_NOT_INCLUDED, snapshot.warnings)
        self.assertFalse(hasattr(snapshot.weapon, "passive_stat_bonuses"))

    def test_character_without_promote_level_assumes_after_for_breakpoint(self) -> None:
        snapshot = build_character_stat_snapshot(
            account_character={"id": 1, "name": "Amber", "level": 20},
            character_stats_entry=character_entry(),
            account_weapon={
                "id": 2,
                "name": "Favonius Warbow",
                "level": 20,
                "promote_level": 1,
            },
            weapon_stats_entry=weapon_entry(),
            artifact_summary={},
        )

        self.assertEqual(snapshot.character_base.base_hp.selection, VALUE_SELECTION_AFTER)
        self.assertEqual(snapshot.character_base.base_hp.selected, "2630")
        self.assertIn(WARNING_CHARACTER_ASCENSION_PHASE_ASSUMED, snapshot.warnings)
        self.assertNotIn(WARNING_ASCENSION_PHASE_UNKNOWN, snapshot.character_base.warnings)

    def test_level_90_without_promote_level_uses_final_before_value(self) -> None:
        entry = CharacterBaseStatsEntry(
            entry_page_id="14",
            name="Amber",
            lang="en-us",
            rows=(
                CharacterBaseStatRow(
                    level_key="Lv.90",
                    base_hp=StatValuePair(before="9461"),
                    base_atk=StatValuePair(before="223"),
                    base_def=StatValuePair(before="601"),
                    ascension_bonus_stat_type="ATK",
                    ascension_bonus=StatValuePair(before="24.0%"),
                ),
            ),
        )
        snapshot = build_character_stat_snapshot(
            account_character={"id": 1, "name": "Amber", "level": 90},
            character_stats_entry=entry,
            account_weapon={"id": 2, "name": "Favonius Warbow", "level": 1},
            weapon_stats_entry=weapon_entry(),
            artifact_summary={},
        )

        self.assertEqual(snapshot.character_base.base_hp.selection, VALUE_SELECTION_SINGLE)
        self.assertEqual(snapshot.character_base.base_hp.selected, "9461")
        self.assertNotIn(WARNING_ASCENSION_PHASE_UNKNOWN, snapshot.character_base.warnings)

    def test_explicit_promote_level_overrides_character_default_policy(self) -> None:
        snapshot = build_character_stat_snapshot(
            account_character={
                "id": 1,
                "name": "Amber",
                "level": 20,
                "promote_level": 0,
            },
            character_stats_entry=character_entry(),
            account_weapon={"id": 2, "name": "Favonius Warbow", "level": 1},
            weapon_stats_entry=weapon_entry(),
            artifact_summary={},
        )

        self.assertEqual(snapshot.character_base.base_hp.selection, VALUE_SELECTION_BEFORE)
        self.assertEqual(snapshot.character_base.base_hp.selected, "2038")
        self.assertNotIn(WARNING_CHARACTER_ASCENSION_PHASE_ASSUMED, snapshot.warnings)

    def test_known_promote_level_selects_after_ascension_value(self) -> None:
        snapshot = build_character_stat_snapshot(
            account_character={
                "id": 1,
                "name": "Amber",
                "level": 20,
                "promote_level": 1,
            },
            character_stats_entry=character_entry(),
            account_weapon={
                "id": 2,
                "name": "Favonius Warbow",
                "level": 20,
                "promote_level": 1,
            },
            weapon_stats_entry=weapon_entry(),
            artifact_summary={},
        )

        self.assertEqual(snapshot.character_base.base_hp.selection, VALUE_SELECTION_AFTER)
        self.assertEqual(snapshot.character_base.base_hp.selected, "2630")
        self.assertEqual(snapshot.weapon.base_atk.selected, "125")

    def test_level_95_100_exact_row_uses_exact_row(self) -> None:
        for level in (95, 100):
            with self.subTest(level=level):
                entry = CharacterBaseStatsEntry(
                    entry_page_id="14",
                    name="Amber",
                    lang="en-us",
                    rows=(
                        CharacterBaseStatRow(
                            level_key=f"Lv.{level}",
                            base_hp=StatValuePair(after=str(9000 + level)),
                            base_atk=StatValuePair(after="230"),
                            base_def=StatValuePair(after="610"),
                            ascension_bonus_stat_type="ATK",
                            ascension_bonus=StatValuePair(after="24.0%"),
                        ),
                        CharacterBaseStatRow(
                            level_key="Lv.90",
                            base_hp=StatValuePair(before="9461"),
                            base_atk=StatValuePair(before="223"),
                            base_def=StatValuePair(before="601"),
                            ascension_bonus_stat_type="ATK",
                            ascension_bonus=StatValuePair(before="24.0%"),
                        ),
                    ),
                )
                snapshot = build_character_stat_snapshot(
                    account_character={"id": 1, "name": "Amber", "level": level},
                    character_stats_entry=entry,
                    account_weapon={"id": 2, "name": "Favonius Warbow", "level": 1},
                    weapon_stats_entry=weapon_entry(),
                    artifact_summary={},
                )

                self.assertEqual(snapshot.character_base.selected_level_key, f"Lv.{level}")
                self.assertEqual(snapshot.character_base.base_hp.selected, str(9000 + level))
                self.assertNotIn(WARNING_LEVEL_95_100_FALLBACK_TO_90, snapshot.warnings)

    def test_missing_95_100_row_falls_back_to_level_90_without_interpolation(self) -> None:
        entry = CharacterBaseStatsEntry(
            entry_page_id="14",
            name="Amber",
            lang="en-us",
            rows=(
                CharacterBaseStatRow(
                    level_key="Lv.90",
                    base_hp=StatValuePair(before="9461"),
                    base_atk=StatValuePair(before="223"),
                    base_def=StatValuePair(before="601"),
                    ascension_bonus_stat_type="ATK",
                    ascension_bonus=StatValuePair(before="24.0%"),
                ),
            ),
        )
        for level in (95, 100):
            with self.subTest(level=level):
                snapshot = build_character_stat_snapshot(
                    account_character={"id": 1, "name": "Amber", "level": level},
                    character_stats_entry=entry,
                    account_weapon={"id": 2, "name": "Favonius Warbow", "level": 1},
                    weapon_stats_entry=weapon_entry(),
                    artifact_summary={},
                )

                self.assertEqual(snapshot.character_base.selected_level_key, "Lv.90")
                self.assertEqual(snapshot.character_base.base_hp.selected, "9461")
                self.assertIn(WARNING_LEVEL_95_100_FALLBACK_TO_90, snapshot.warnings)
                self.assertNotIn(WARNING_LEVEL_ROW_UNAVAILABLE, snapshot.warnings)
                self.assertNotIn(WARNING_INTERPOLATION_NOT_IMPLEMENTED, snapshot.warnings)

    def test_weapon_without_promote_level_still_does_not_assume_phase(self) -> None:
        contribution = build_weapon_stat_contribution(
            weapon_entry(),
            account_level=20,
            promote_level=None,
            refinement=1,
        )

        self.assertEqual(contribution.base_atk.selection, VALUE_SELECTION_AMBIGUOUS)
        self.assertIn(WARNING_ASCENSION_PHASE_UNKNOWN, contribution.warnings)

    def test_traveler_is_unsupported_without_aliasing(self) -> None:
        snapshot = build_character_stat_snapshot(
            account_character={"id": 10000007, "name": "Traveler", "level": 90},
            character_stats_entry=character_entry(),
            account_weapon={"id": 2, "name": "Favonius Warbow", "level": 90},
            weapon_stats_entry=weapon_entry(),
        )

        self.assertEqual(snapshot.status, SNAPSHOT_STATUS_UNSUPPORTED)
        self.assertIsNone(snapshot.character_base)
        self.assertIn(WARNING_TRAVELER_SPECIAL_DEFERRED, snapshot.warnings)

    def test_future_pending_stats_returns_warning_without_crash(self) -> None:
        snapshot = build_character_stat_snapshot(
            account_character={"id": 3, "name": "Future Hero", "level": 1},
            character_stats_entry=CharacterBaseStatsEntry(
                entry_page_id="9001",
                name="Future Hero",
                lang="en-us",
                rows=(),
            ),
            account_weapon={"id": 2, "name": "Favonius Warbow", "level": 1},
            weapon_stats_entry=weapon_entry(),
            artifact_summary={},
        )

        self.assertEqual(snapshot.status, SNAPSHOT_STATUS_PARTIAL)
        self.assertIn(WARNING_CHARACTER_STATS_UNAVAILABLE, snapshot.warnings)

    def test_missing_artifact_summary_warns_but_snapshot_builds(self) -> None:
        snapshot = build_character_stat_snapshot(
            account_character={"id": 1, "name": "Amber", "level": 1},
            character_stats_entry=character_entry(),
            account_weapon={"id": 2, "name": "Favonius Warbow", "level": 1},
            weapon_stats_entry=weapon_entry(),
        )

        self.assertEqual(snapshot.status, SNAPSHOT_STATUS_PARTIAL)
        self.assertEqual(snapshot.character_base.base_hp.selection, VALUE_SELECTION_SINGLE)
        self.assertIn(WARNING_ARTIFACT_SUMMARY_MISSING, snapshot.warnings)


if __name__ == "__main__":
    unittest.main()
