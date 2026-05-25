from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from hoyolab_export.character_trait_catalog import (
    CHARACTER_TRAIT_CATALOG_SCHEMA_VERSION,
    CharacterTraitCatalog,
    CharacterTraitTooltipReference,
    HOYOWIKI_HEXEREI_ENTRY_PAGE_ID,
    HOYOWIKI_HEXEREI_SOURCE_URL,
    HOYOWIKI_MOONSIGN_ENTRY_PAGE_ID,
    HOYOWIKI_MOONSIGN_SOURCE_URL,
    TRAIT_HEXEREI,
    TRAIT_MOONSIGN,
    TRAIT_STANDARD_5_STAR,
    character_trait_catalog_to_dict,
    entries_with_trait,
    extract_character_trait_entries_from_hoyowiki_page,
    get_hexerei_tooltip_sections,
    hexerei_tooltip_reference,
    init_character_trait_reference_storage,
    list_seed_character_traits,
    normalize_character_trait_name,
    parse_hexerei_sections_from_hoyowiki_page,
    refresh_character_trait_catalog,
    rebuild_character_trait_reference_from_catalog,
    traits_for_character_name,
    upsert_character_trait_tooltip_sections,
)


class CharacterTraitCatalogTest(unittest.TestCase):
    def test_seed_contains_moonsign_and_hexerei_character_groups(self) -> None:
        seed = list_seed_character_traits()
        moonsign = entries_with_trait(TRAIT_MOONSIGN, entries=seed)
        hexerei = entries_with_trait(TRAIT_HEXEREI, entries=seed)

        self.assertEqual(len(moonsign), 10)
        self.assertEqual(len(hexerei), 9)
        self.assertIn("Aino", {entry.name for entry in moonsign})
        self.assertIn("Sucrose", {entry.name for entry in hexerei})
        self.assertEqual(len(entries_with_trait(TRAIT_STANDARD_5_STAR, entries=seed)), 8)

    def test_lookup_normalizes_character_names(self) -> None:
        seed = list_seed_character_traits()
        self.assertEqual(
            traits_for_character_name("  AINO ", entries=seed),
            (TRAIT_MOONSIGN,),
        )
        self.assertEqual(traits_for_character_name("Sucrose", entries=seed), (TRAIT_HEXEREI,))
        self.assertIn(
            TRAIT_STANDARD_5_STAR,
            traits_for_character_name("Mona", entries=seed),
        )
        self.assertIn(
            TRAIT_STANDARD_5_STAR,
            traits_for_character_name("Traveler", entries=seed),
        )
        self.assertEqual(normalize_character_trait_name("Moon-Sign Aino"), "moon sign aino")

    def test_catalog_dict_is_reference_seed_not_bonus_model(self) -> None:
        data = character_trait_catalog_to_dict()

        self.assertEqual(data["schema_version"], CHARACTER_TRAIT_CATALOG_SCHEMA_VERSION)
        self.assertEqual(data["source_urls"][TRAIT_MOONSIGN], HOYOWIKI_MOONSIGN_SOURCE_URL)
        self.assertEqual(data["source_urls"][TRAIT_HEXEREI], HOYOWIKI_HEXEREI_SOURCE_URL)
        self.assertNotIn("bonuses", data)
        self.assertIn("does not define resonance bonuses", " ".join(data["notes"]))
        self.assertIn("tooltip_references", data)

    def test_hexerei_tooltip_reference_uses_cache_text_when_present(self) -> None:
        catalog = CharacterTraitCatalog(
            entries=(),
            tooltip_references=(
                CharacterTraitTooltipReference(
                    trait=TRAIT_HEXEREI,
                    title="Hexerei",
                    body="Shared localized Hexerei text",
                    source_url=HOYOWIKI_HEXEREI_SOURCE_URL,
                    source_entry_page_id=HOYOWIKI_HEXEREI_ENTRY_PAGE_ID,
                    member_text_by_name=(("Mona", "Mona localized Hexerei text"),),
                ),
            ),
        )

        reference = hexerei_tooltip_reference(catalog)

        self.assertEqual(reference.body, "Shared localized Hexerei text")
        self.assertEqual(reference.text_for_member(name="Mona"), "Mona localized Hexerei text")
        self.assertEqual(reference.source_entry_page_id, HOYOWIKI_HEXEREI_ENTRY_PAGE_ID)

    def test_hexerei_tooltip_reference_falls_back_to_source_metadata(self) -> None:
        reference = hexerei_tooltip_reference(CharacterTraitCatalog(entries=()))

        self.assertEqual(reference.title, "Hexerei")
        self.assertEqual(reference.source_url, HOYOWIKI_HEXEREI_SOURCE_URL)
        self.assertEqual(reference.source_entry_page_id, HOYOWIKI_HEXEREI_ENTRY_PAGE_ID)
        self.assertEqual(reference.body, "")

    def test_seed_entries_carry_hoyowiki_source_ids(self) -> None:
        seed = list_seed_character_traits()
        moonsign = entries_with_trait(TRAIT_MOONSIGN, entries=seed)[0]
        hexerei = entries_with_trait(TRAIT_HEXEREI, entries=seed)[0]

        self.assertEqual(moonsign.source_url, HOYOWIKI_MOONSIGN_SOURCE_URL)
        self.assertEqual(moonsign.source_entry_page_id, HOYOWIKI_MOONSIGN_ENTRY_PAGE_ID)
        self.assertEqual(hexerei.source_url, HOYOWIKI_HEXEREI_SOURCE_URL)
        self.assertEqual(hexerei.source_entry_page_id, HOYOWIKI_HEXEREI_ENTRY_PAGE_ID)

    def test_extracts_character_cards_from_hoyowiki_custom_entries(self) -> None:
        page = {
            "modules": [
                {
                    "components": [
                        {
                            "data": (
                                '{"data":"<custom-entry epid=\\"8397\\" '
                                'menuid=\\"2\\" name=\\"Aino\\" />'
                                '<custom-entry epid=\\"1\\" menuid=\\"99\\" '
                                'name=\\"Not Character\\" />"}'
                            )
                        }
                    ]
                }
            ]
        }

        entries = extract_character_trait_entries_from_hoyowiki_page(
            page,
            trait=TRAIT_MOONSIGN,
            source_url=HOYOWIKI_MOONSIGN_SOURCE_URL,
            source_entry_page_id=HOYOWIKI_MOONSIGN_ENTRY_PAGE_ID,
            source_section="Moonsign",
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "Aino")
        self.assertEqual(entries[0].source_character_entry_page_id, "8397")

    def test_refresh_writes_cache_from_fetcher(self) -> None:
        def fake_fetcher(entry_page_id: str, _language: str) -> dict:
            name = "Aino" if entry_page_id == HOYOWIKI_MOONSIGN_ENTRY_PAGE_ID else "Sucrose"
            return {
                "modules": [
                    {
                        "components": [
                            {
                                "data": (
                                    '{"data":"<custom-entry epid=\\"1\\" '
                                    f'menuid=\\"2\\" name=\\"{name}\\" />"}}'
                                )
                            }
                        ]
                    }
                ]
            }

        with TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "traits.json"

            catalog = refresh_character_trait_catalog(
                cache_path=cache_path,
                page_fetcher=fake_fetcher,
            )

            self.assertTrue(cache_path.exists())
            self.assertEqual(
                sorted((entry.name, entry.traits[0]) for entry in catalog.entries),
                [
                    ("Aino", TRAIT_MOONSIGN),
                    ("Dehya", TRAIT_STANDARD_5_STAR),
                    ("Diluc", TRAIT_STANDARD_5_STAR),
                    ("Jean", TRAIT_STANDARD_5_STAR),
                    ("Keqing", TRAIT_STANDARD_5_STAR),
                    ("Mona", TRAIT_STANDARD_5_STAR),
                    ("Qiqi", TRAIT_STANDARD_5_STAR),
                    ("Sucrose", TRAIT_HEXEREI),
                    ("Tighnari", TRAIT_STANDARD_5_STAR),
                    ("Traveler", TRAIT_STANDARD_5_STAR),
                ],
            )

    def test_parses_hexerei_tooltip_sections_from_en_us_custom_table(self) -> None:
        page = _hexerei_page(
            """
            <table><tr><td>
            <custom-entry epid="123" menuid="2" name="Mona" icon="mona.png"></custom-entry>
            <p>Mona's Secret Rite (Passive Talent)</p>
            <p>Passive body.</p>
            <p>Mona's Last Secret (Constellation 6)</p>
            <p>C6 body.</p>
            </td></tr></table>
            """
        )

        parsed = parse_hexerei_sections_from_hoyowiki_page(page, language="en-us")

        self.assertEqual([entry.name for entry in parsed.entries], ["Mona"])
        self.assertEqual(
            [(section.required_constellation, section.title, section.body) for section in parsed.sections],
            [
                (0, "Mona's Secret Rite", "Passive body."),
                (6, "Mona's Last Secret", "C6 body."),
            ],
        )

    def test_parses_current_en_us_hexerei_heading_shape(self) -> None:
        page = _hexerei_page(
            """
            <table><tr><td>
            <custom-entry epid="37" menuid="2" name="Mona"></custom-entry>
            <p>Complete</p>
            <p>Activate Hexerei: Secret Rite</p>
            <p>Passive body.</p>
            <p>Constellation Changes</p>
            <p>Constellation 1: C1 body.</p>
            <p>C1 continuation.</p>
            </td></tr></table>
            """
        )

        parsed = parse_hexerei_sections_from_hoyowiki_page(page, language="en-us")

        self.assertEqual(
            [(section.required_constellation, section.title, section.body) for section in parsed.sections],
            [
                (0, "Activate Hexerei: Secret Rite", "Passive body."),
                (1, "Constellation 1", "C1 body.\nC1 continuation."),
            ],
        )

    def test_parses_hexerei_tooltip_sections_from_ru_custom_table(self) -> None:
        page = _hexerei_page(
            """
            <table><tr><td>
            <custom-entry epid="123" menuid="2" name="Мона"></custom-entry>
            <p>Тайный ритуал (пассивный талант)</p>
            <p>Текст пассивки.</p>
            <p>Последний секрет (созвездие 4)</p>
            <p>Текст C4.</p>
            </td></tr></table>
            """
        )

        parsed = parse_hexerei_sections_from_hoyowiki_page(page, language="ru-ru")

        self.assertEqual(
            [(section.required_constellation, section.title, section.body) for section in parsed.sections],
            [
                (0, "Тайный ритуал", "Текст пассивки."),
                (4, "Последний секрет", "Текст C4."),
            ],
        )

    def test_hexerei_sqlite_sections_prefer_locale_and_filter_by_constellation(self) -> None:
        en_page = _hexerei_page(
            """
            <table><tr><td>
            <custom-entry epid="123" menuid="2" name="Mona"></custom-entry>
            <p>Passive Name (Passive Talent)</p><p>English passive.</p>
            <p>C4 Name (Constellation 4)</p><p>English C4.</p>
            <p>C6 Name (Constellation 6)</p><p>English C6.</p>
            </td></tr></table>
            """
        )
        ru_page = _hexerei_page(
            """
            <table><tr><td>
            <custom-entry epid="123" menuid="2" name="Мона"></custom-entry>
            <p>Пассивка (пассивный талант)</p><p>Русская пассивка.</p>
            <p>C4 RU (созвездие 4)</p><p>Русский C4.</p>
            </td></tr></table>
            """
        )
        en = parse_hexerei_sections_from_hoyowiki_page(en_page, language="en-us")
        ru = parse_hexerei_sections_from_hoyowiki_page(ru_page, language="ru-ru")

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_character_trait_reference_storage(conn)
        rebuild_character_trait_reference_from_catalog(
            conn,
            CharacterTraitCatalog(entries=en.entries),
        )
        upsert_character_trait_tooltip_sections(conn, en.sections, language="en-us")
        upsert_character_trait_tooltip_sections(conn, ru.sections, language="ru-ru")

        sections = get_hexerei_tooltip_sections(
            conn,
            character_entry_page_id="123",
            account_constellation=4,
            preferred_language="ru-ru",
        )

        self.assertEqual(
            [(section["required_constellation"], section["title"], section["body"]) for section in sections],
            [
                (0, "Пассивка", "Русская пассивка."),
                (4, "C4 RU", "Русский C4."),
            ],
        )
        self.assertNotIn("English C6", json.dumps(sections, ensure_ascii=False))


def _hexerei_page(html: str) -> dict:
    return {
        "modules": [
            {
                "components": [
                    {
                        "component_id": "customize",
                        "data": json.dumps({"data": html}, ensure_ascii=False),
                    }
                ]
            }
        ]
    }


if __name__ == "__main__":
    unittest.main()
