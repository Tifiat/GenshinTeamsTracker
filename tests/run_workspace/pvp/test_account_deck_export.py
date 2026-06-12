from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from run_workspace.pvp.account_deck_export import (
    ISSUE_CHARACTER_DISPLAY_NAME_MISSING,
    ISSUE_CHARACTER_MISSING_ID,
    ISSUE_CHARACTER_TRAVELER_SKIPPED,
    ISSUE_WEAPON_INVALID_COUNT,
    ISSUE_WEAPON_MISSING_ID,
    AccountDeckCharacterRow,
    AccountDeckExportOptions,
    AccountDeckWeaponStackRow,
    FakeAccountDeckDataProvider,
    export_free_draft_deck_from_account,
)
from run_workspace.pvp.account_deck_export_smoke import (
    format_account_deck_export_smoke_report,
    run_account_deck_export_smoke,
)
from run_workspace.pvp.validation import (
    ISSUE_MISSING_CHARACTER_DISPLAY_NAME,
    validate_draft_deck,
)


class AccountDeckExportTests(unittest.TestCase):
    def test_valid_fake_account_exports_valid_free_draft_deck(self) -> None:
        report = export_free_draft_deck_from_account(
            _provider(),
            options=AccountDeckExportOptions(
                deck_name="Fixture Account Deck",
                nickname="fixture",
                language="en",
                exported_at_utc="2026-06-12T00:00:00Z",
            ),
        )

        self.assertTrue(report.validation_report.ready)
        self.assertEqual(report.deck.deck_name, "Fixture Account Deck")
        self.assertEqual(report.deck.player.nickname, "fixture")
        self.assertEqual(report.counts.characters_exported, 12)
        self.assertEqual(report.counts.weapons_exported, 5)
        self.assertEqual(report.deck.ruleset_ref.ruleset_id, "free_draft_v0")
        self.assertNotIn("artifacts", report.deck.to_dict())

    def test_character_level_constellation_and_identity_are_preserved(self) -> None:
        report = export_free_draft_deck_from_account(_provider())

        character = report.deck.character_by_id["test_char_01"]

        self.assertEqual(character.level, 81)
        self.assertEqual(character.constellation, 1)
        self.assertEqual(character.weapon_type, "SWORD")

    def test_traveler_and_missing_character_id_are_skipped_and_reported(self) -> None:
        provider = _provider(
            extra_characters=(
                AccountDeckCharacterRow(
                    "10000007",
                    "Traveler",
                    element="ANEMO",
                    weapon_type=1,
                    rarity=5,
                    level=90,
                    constellation=6,
                ),
                AccountDeckCharacterRow(
                    "",
                    "No Stable Id",
                    element="PYRO",
                    weapon_type=1,
                    rarity=4,
                    level=80,
                    constellation=0,
                ),
            )
        )

        report = export_free_draft_deck_from_account(provider)

        self.assertTrue(report.validation_report.ready)
        self.assertEqual(report.counts.traveler_entries_skipped, 1)
        self.assertEqual(report.counts.entries_skipped_missing_id, 1)
        self.assertNotIn("10000007", report.deck.character_ids)
        self.assertIn(ISSUE_CHARACTER_TRAVELER_SKIPPED, report.issue_codes())
        self.assertIn(ISSUE_CHARACTER_MISSING_ID, report.issue_codes())

    def test_missing_character_display_fallback_is_reported_without_id_loss(self) -> None:
        characters = list(_characters())
        characters[0] = AccountDeckCharacterRow(
            "test_char_01",
            "",
            element="PYRO",
            weapon_type=1,
            rarity=5,
            level=90,
            constellation=0,
        )
        provider = FakeAccountDeckDataProvider(
            characters=tuple(characters),
            weapon_stacks=_weapons(),
        )

        report = export_free_draft_deck_from_account(provider)

        self.assertIn("test_char_01", report.deck.character_ids)
        self.assertFalse(report.validation_report.ready)
        self.assertIn(ISSUE_CHARACTER_DISPLAY_NAME_MISSING, report.issue_codes())
        self.assertIn(
            ISSUE_MISSING_CHARACTER_DISPLAY_NAME,
            report.validation_report.issue_codes(),
        )

    def test_catalog_english_name_is_used_as_display_fallback(self) -> None:
        characters = list(_characters())
        characters[0] = AccountDeckCharacterRow(
            "test_char_01",
            "",
            element="PYRO",
            weapon_type=1,
            rarity=5,
            level=90,
            constellation=0,
            catalog_english_name="English Fallback",
        )
        provider = FakeAccountDeckDataProvider(
            characters=tuple(characters),
            weapon_stacks=_weapons(),
        )

        report = export_free_draft_deck_from_account(provider)

        self.assertTrue(report.validation_report.ready)
        self.assertEqual(
            report.deck.character_by_id["test_char_01"].display_name,
            "English Fallback",
        )

    def test_weapon_stacks_merge_and_invalid_rows_are_reported(self) -> None:
        provider = _provider(
            weapon_stacks=(
                AccountDeckWeaponStackRow(
                    "weapon_sword",
                    "Sword Copy",
                    weapon_type=1,
                    rarity=4,
                    level=90,
                    refinement=5,
                    count=1,
                ),
                AccountDeckWeaponStackRow(
                    "weapon_sword",
                    "Sword Copy",
                    weapon_type=1,
                    rarity=4,
                    level=90,
                    refinement=5,
                    count=2,
                ),
                AccountDeckWeaponStackRow(
                    "weapon_sword",
                    "Sword R1",
                    weapon_type=1,
                    rarity=4,
                    level=90,
                    refinement=1,
                    count=1,
                ),
                AccountDeckWeaponStackRow(
                    "weapon_sword",
                    "Sword Lv80",
                    weapon_type=1,
                    rarity=4,
                    level=80,
                    refinement=5,
                    count=1,
                ),
                AccountDeckWeaponStackRow(
                    "weapon_bad_count",
                    "Bad Count",
                    weapon_type=12,
                    rarity=4,
                    level=90,
                    refinement=5,
                    count=0,
                ),
                AccountDeckWeaponStackRow(
                    "",
                    "No Id",
                    weapon_type=12,
                    rarity=4,
                    level=90,
                    refinement=5,
                    count=1,
                ),
            ),
        )

        report = export_free_draft_deck_from_account(provider)

        self.assertTrue(report.validation_report.ready)
        self.assertEqual(report.counts.weapons_exported, 3)
        self.assertEqual(report.counts.weapon_stack_rows_merged, 1)
        self.assertEqual(report.counts.entries_skipped_missing_id, 1)
        self.assertEqual(report.counts.entries_skipped_unsupported_shape, 1)
        self.assertIn(ISSUE_WEAPON_INVALID_COUNT, report.issue_codes())
        self.assertIn(ISSUE_WEAPON_MISSING_ID, report.issue_codes())
        sword_r5 = [
            item
            for item in report.deck.weapons
            if item.weapon_id == "weapon_sword"
            and item.level == 90
            and item.refinement == 5
        ][0]
        self.assertEqual(sword_r5.count, 3)

    def test_exported_deck_validates_through_existing_report(self) -> None:
        report = export_free_draft_deck_from_account(_provider())

        validation = validate_draft_deck(report.deck)

        self.assertTrue(validation.ready)
        self.assertEqual(validation.to_dict(), report.validation_report.to_dict())

    def test_smoke_dry_run_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "deck.json"

            smoke = run_account_deck_export_smoke(
                provider=_provider(),
                write=False,
                output_path=output_path,
            )
            text = format_account_deck_export_smoke_report(smoke)

            self.assertTrue(smoke.ready)
            self.assertFalse(smoke.wrote_file)
            self.assertFalse(output_path.exists())
            self.assertIn("dry-run, no files written", text)
            self.assertIn("Validation: ready=true", text)


def _provider(
    *,
    extra_characters: tuple[AccountDeckCharacterRow, ...] = (),
    weapon_stacks: tuple[AccountDeckWeaponStackRow, ...] | None = None,
) -> FakeAccountDeckDataProvider:
    return FakeAccountDeckDataProvider(
        characters=_characters() + extra_characters,
        weapon_stacks=weapon_stacks if weapon_stacks is not None else _weapons(),
        source_summary={"fixture": True},
    )


def _characters() -> tuple[AccountDeckCharacterRow, ...]:
    weapon_types = (1, 12, 13, 11, 10)
    elements = ("Pyro", "Hydro", "Electro", "Cryo", "Geo")
    return tuple(
        AccountDeckCharacterRow(
            character_id=f"test_char_{index:02d}",
            display_name=f"Character {index:02d}",
            element=elements[(index - 1) % len(elements)],
            weapon_type=weapon_types[(index - 1) % len(weapon_types)],
            rarity=5 if index % 2 else 4,
            level=80 + index,
            constellation=index % 7,
        )
        for index in range(1, 13)
    )


def _weapons() -> tuple[AccountDeckWeaponStackRow, ...]:
    return (
        AccountDeckWeaponStackRow(
            "weapon_sword",
            "Sword",
            1,
            rarity=4,
            level=90,
            refinement=5,
            count=8,
        ),
        AccountDeckWeaponStackRow(
            "weapon_bow",
            "Bow",
            12,
            rarity=4,
            level=90,
            refinement=5,
            count=8,
        ),
        AccountDeckWeaponStackRow(
            "weapon_polearm",
            "Polearm",
            13,
            rarity=4,
            level=90,
            refinement=5,
            count=8,
        ),
        AccountDeckWeaponStackRow(
            "weapon_claymore",
            "Claymore",
            11,
            rarity=4,
            level=90,
            refinement=5,
            count=8,
        ),
        AccountDeckWeaponStackRow(
            "weapon_catalyst",
            "Catalyst",
            10,
            rarity=4,
            level=90,
            refinement=5,
            count=8,
        ),
    )


if __name__ == "__main__":
    unittest.main()
