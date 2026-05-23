from __future__ import annotations

import unittest

from hoyolab_export.catalog_mapping import map_character_catalog, map_weapon_catalog
from hoyolab_export.catalog_sanity import (
    STATUS_FUTURE_PENDING_STATS,
    STATUS_MALFORMED,
    STATUS_READY,
    STATUS_SPECIAL_DEFERRED,
    STATUS_STATS_UNAVAILABLE,
    WARNING_STATS_UNAVAILABLE,
    WARNING_TRAVELER_SPECIAL_DEFERRED,
    build_catalog_sanity_report,
    classify_character_stats_entry,
    classify_weapon_stats_entry,
)
from hoyolab_export.character_stats_catalog import (
    WARNING_MALFORMED_ASCENSION_COMPONENT,
    WARNING_NO_ASCENSION_ROWS,
    CharacterBaseStatRow,
    CharacterBaseStatsCatalog,
    CharacterBaseStatsEntry,
    StatValuePair,
)
from hoyolab_export.weapon_stats_catalog import (
    WeaponAtkValuePair,
    WeaponBaseStatRow,
    WeaponStatsCatalog,
    WeaponStatsEntry,
)


class CatalogSanityTest(unittest.TestCase):
    def test_character_with_rows_is_ready(self) -> None:
        entry = CharacterBaseStatsEntry(
            entry_page_id="14",
            name="Amber",
            lang="en-us",
            rows=(
                CharacterBaseStatRow(
                    level_key="Lv.1",
                    base_hp=StatValuePair(after="793"),
                    base_atk=StatValuePair(after="19"),
                    base_def=StatValuePair(after="50"),
                ),
            ),
        )

        sanity = classify_character_stats_entry(entry)

        self.assertEqual(sanity.status, STATUS_READY)

    def test_character_no_rows_is_future_pending_not_non_playable(self) -> None:
        entry = CharacterBaseStatsEntry(
            entry_page_id="9001",
            name="Prune",
            lang="en-us",
            rows=(),
            warnings=(WARNING_NO_ASCENSION_ROWS,),
        )

        sanity = classify_character_stats_entry(entry)

        self.assertEqual(sanity.status, STATUS_FUTURE_PENDING_STATS)
        self.assertIn(WARNING_STATS_UNAVAILABLE, sanity.warnings)
        self.assertNotEqual(sanity.status, "non_playable")

    def test_malformed_character_entry_stays_malformed(self) -> None:
        entry = CharacterBaseStatsEntry(
            entry_page_id="9002",
            name="Broken",
            lang="en-us",
            warnings=(WARNING_MALFORMED_ASCENSION_COMPONENT,),
        )

        sanity = classify_character_stats_entry(entry)

        self.assertEqual(sanity.status, STATUS_MALFORMED)

    def test_weapon_with_rows_is_ready(self) -> None:
        entry = WeaponStatsEntry(
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
            ),
        )

        sanity = classify_weapon_stats_entry(entry)

        self.assertEqual(sanity.status, STATUS_READY)

    def test_weapon_without_rows_is_stats_unavailable(self) -> None:
        entry = WeaponStatsEntry(
            entry_page_id="999",
            name="Future Weapon",
            lang="en-us",
            rows=(),
        )

        sanity = classify_weapon_stats_entry(entry)

        self.assertEqual(sanity.status, STATUS_STATS_UNAVAILABLE)
        self.assertIn(WARNING_STATS_UNAVAILABLE, sanity.warnings)

    def test_account_traveler_unmatched_is_special_deferred(self) -> None:
        mapping = map_character_catalog(
            [{"id": "10000007", "name": "Путешественница"}],
            [],
            account_language="ru-ru",
        )

        report = build_catalog_sanity_report(
            character_catalog=CharacterBaseStatsCatalog(entries=()),
            character_mapping=mapping,
        )

        account_entry = report.account_characters[0]
        self.assertEqual(account_entry.status, STATUS_SPECIAL_DEFERRED)
        self.assertIn(WARNING_TRAVELER_SPECIAL_DEFERRED, account_entry.warnings)

    def test_matched_account_character_without_rows_warns_without_crash(self) -> None:
        mapping = map_character_catalog(
            [{"id": "1", "name": "Future Hero"}],
            [{"entry_page_id": "9001", "name": "Future Hero"}],
            account_language="en-us",
        )
        catalog = CharacterBaseStatsCatalog(
            entries=(
                CharacterBaseStatsEntry(
                    entry_page_id="9001",
                    name="Future Hero",
                    lang="en-us",
                    rows=(),
                    warnings=(WARNING_NO_ASCENSION_ROWS,),
                ),
            )
        )

        report = build_catalog_sanity_report(
            character_catalog=catalog,
            character_mapping=mapping,
        )

        account_entry = report.account_characters[0]
        self.assertEqual(account_entry.status, STATUS_FUTURE_PENDING_STATS)
        self.assertIn(WARNING_STATS_UNAVAILABLE, account_entry.warnings)

    def test_summary_counts_are_correct(self) -> None:
        character_catalog = CharacterBaseStatsCatalog(
            entries=(
                CharacterBaseStatsEntry(
                    entry_page_id="14",
                    name="Amber",
                    lang="en-us",
                    rows=(
                        CharacterBaseStatRow(
                            level_key="Lv.1",
                            base_hp=StatValuePair(after="793"),
                        ),
                    ),
                ),
                CharacterBaseStatsEntry(
                    entry_page_id="9001",
                    name="Prune",
                    lang="en-us",
                    rows=(),
                    warnings=(WARNING_NO_ASCENSION_ROWS,),
                ),
            )
        )
        weapon_catalog = WeaponStatsCatalog(
            entries=(
                WeaponStatsEntry(
                    entry_page_id="2019",
                    name="Favonius Warbow",
                    lang="en-us",
                    rows=(
                        WeaponBaseStatRow(
                            level_key="Lv.1",
                            base_atk=WeaponAtkValuePair(after="41"),
                        ),
                    ),
                ),
            )
        )
        character_mapping = map_character_catalog(
            [{"id": "1", "name": "Amber"}],
            [{"entry_page_id": "14", "name": "Amber"}],
        )
        weapon_mapping = map_weapon_catalog(
            [{"id": "2", "name": "Favonius Warbow"}],
            [{"entry_page_id": "2019", "name": "Favonius Warbow"}],
        )

        data = build_catalog_sanity_report(
            character_catalog=character_catalog,
            weapon_catalog=weapon_catalog,
            character_mapping=character_mapping,
            weapon_mapping=weapon_mapping,
        ).to_dict()

        self.assertEqual(data["characters"]["statuses"][STATUS_READY], 1)
        self.assertEqual(data["characters"]["statuses"][STATUS_FUTURE_PENDING_STATS], 1)
        self.assertEqual(data["weapons"]["statuses"][STATUS_READY], 1)
        self.assertEqual(data["account_characters"]["statuses"][STATUS_READY], 1)
        self.assertEqual(data["account_weapons"]["statuses"][STATUS_READY], 1)


if __name__ == "__main__":
    unittest.main()
