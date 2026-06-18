from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path

from hoyolab_export.artifact_db import connect_db, init_db
from run_workspace.pvp import (
    PVP_PROFILE_DB_NAME,
    PVP_PROFILE_DECKS_NAME,
    PVP_PROFILE_EXTENSION,
    PVP_PROFILE_MANIFEST_NAME,
    ImportedPvpProfileProvider,
    LocalPvpProfileProvider,
    PvpDeckPreset,
    PvpProfilePackageError,
    PvpProfilePackageOptions,
    WeaponObservedStackRef,
    export_pvp_profile_package,
    import_pvp_profile_package,
    save_deck_preset,
)


class PvpProfilePackageTest(unittest.TestCase):
    def test_export_creates_versioned_package_and_filtered_account_slice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "artifacts.db"
            deck_dir = root / "decks"
            _create_account_db(db_path)
            _write_deck_presets(deck_dir)

            report = export_pvp_profile_package(
                root / "player-one",
                deck_dir=deck_dir,
                db_path=db_path,
                options=PvpProfilePackageOptions(
                    nickname="Local",
                    player_label="Player 1",
                    created_at_utc="2026-06-18T00:00:00Z",
                ),
            )

            self.assertEqual(report.path.suffix, PVP_PROFILE_EXTENSION)
            self.assertEqual(report.counts["deck_count"], 2)
            self.assertEqual(report.counts["character_count"], 2)
            self.assertEqual(report.counts["weapon_stack_count"], 2)

            with zipfile.ZipFile(report.path, "r") as archive:
                names = set(archive.namelist())
                self.assertEqual(
                    names,
                    {
                        PVP_PROFILE_MANIFEST_NAME,
                        PVP_PROFILE_DECKS_NAME,
                        PVP_PROFILE_DB_NAME,
                    },
                )
                self.assertNotIn("cookies", " ".join(names).casefold())
                manifest = json.loads(
                    archive.read(PVP_PROFILE_MANIFEST_NAME).decode("utf-8")
                )
                self.assertEqual(manifest["nickname"], "Local")
                self.assertEqual(manifest["player_label"], "Player 1")

            with import_pvp_profile_package(report.path) as profile:
                self.assertTrue(profile.db_path.exists())
                self.assertEqual(len(profile.deck_presets), 2)
                self.assertEqual(profile.manifest["format"], report.manifest["format"])

                conn = sqlite3.connect(profile.db_path)
                try:
                    character_ids = {
                        str(row[0])
                        for row in conn.execute(
                            "SELECT character_id FROM account_characters"
                        )
                    }
                    weapon_fingerprints = {
                        row[0]
                        for row in conn.execute(
                            "SELECT weapon_fingerprint FROM account_weapon_observed_stacks"
                        )
                    }
                finally:
                    conn.close()

                self.assertEqual(character_ids, {"1001", "1002"})
                self.assertEqual(weapon_fingerprints, {"fp-a", "fp-b"})

            self.assertFalse(profile.db_path.exists())

    def test_import_provider_exposes_temp_db_and_decks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "artifacts.db"
            deck_dir = root / "decks"
            _create_account_db(db_path)
            _write_deck_presets(deck_dir)
            report = export_pvp_profile_package(
                root / "profile.gttpvp",
                deck_dir=deck_dir,
                db_path=db_path,
            )

            profile = import_pvp_profile_package(report.path)
            try:
                provider = ImportedPvpProfileProvider(profile)
                self.assertEqual(provider.db_path, profile.db_path)
                self.assertEqual(len(provider.load_deck_presets()), 2)
            finally:
                provider.close()

            self.assertFalse(profile.db_path.exists())

    def test_local_provider_returns_supplied_db_path_without_copying(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "local.db"
            deck_dir = root / "decks"
            db_path.write_bytes(b"")
            _write_deck_presets(deck_dir)

            provider = LocalPvpProfileProvider(
                source_db_path=db_path,
                deck_dir=deck_dir,
            )

            self.assertEqual(provider.db_path, db_path)
            self.assertEqual(len(provider.load_deck_presets()), 2)

    def test_import_rejects_unsafe_zip_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package_path = Path(temp_dir) / "bad.gttpvp"
            with zipfile.ZipFile(package_path, "w") as archive:
                archive.writestr("../evil.txt", "no")

            with self.assertRaises(PvpProfilePackageError):
                import_pvp_profile_package(package_path)

    def test_import_rejects_unsupported_manifest_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package_path = Path(temp_dir) / "bad.gttpvp"
            with zipfile.ZipFile(package_path, "w") as archive:
                archive.writestr(
                    PVP_PROFILE_MANIFEST_NAME,
                    json.dumps(
                        {
                            "format": "genshin-teams-tracker-pvp-profile",
                            "version": 999,
                        }
                    ),
                )
                archive.writestr(
                    PVP_PROFILE_DECKS_NAME,
                    json.dumps(
                        {
                            "schema_version": 1,
                            "kind": "gtt.pvp_profile_decks",
                            "decks": [],
                        }
                    ),
                )
                archive.writestr(PVP_PROFILE_DB_NAME, b"")

            with self.assertRaises(PvpProfilePackageError):
                import_pvp_profile_package(package_path)


def _write_deck_presets(deck_dir: Path) -> None:
    save_deck_preset(
        PvpDeckPreset(
            deck_id="deck-a",
            name="Deck A",
            character_ids=("1001", "1002"),
            weapon_refs=(
                WeaponObservedStackRef(weapon_fingerprint="fp-a"),
                WeaponObservedStackRef(weapon_fingerprint="fp-b"),
            ),
        ),
        deck_dir,
    )
    save_deck_preset(
        PvpDeckPreset(
            deck_id="deck-b",
            name="Deck B",
            character_ids=("1001",),
            weapon_refs=(WeaponObservedStackRef(weapon_fingerprint="fp-a"),),
        ),
        deck_dir,
    )


def _create_account_db(db_path: Path) -> None:
    with closing(connect_db(db_path)) as conn:
        init_db(conn)
        for character_id, name in (
            (1001, "Keqing"),
            (1002, "Mona"),
            (1003, "Diluc"),
        ):
            conn.execute(
                """
                INSERT INTO account_characters (
                    character_id,
                    name,
                    element,
                    rarity,
                    level,
                    constellation,
                    weapon_type,
                    weapon_type_name
                )
                VALUES (?, ?, 'Electro', 5, 90, 0, 1, 'Sword')
                """,
                (character_id, name),
            )
            conn.execute(
                """
                INSERT INTO account_character_talents (
                    character_id,
                    skill_id,
                    skill_type,
                    name,
                    level
                )
                VALUES (?, 1, 1, 'Normal Attack', 9)
                """,
                (character_id,),
            )
            conn.execute(
                """
                INSERT INTO character_identity (
                    character_id,
                    region_key,
                    updated_at
                )
                VALUES (?, 'liyue', '2026-06-18T00:00:00Z')
                """,
                (character_id,),
            )

        for fingerprint, weapon_id, name in (
            ("fp-a", 11501, "Sword A"),
            ("fp-b", 12501, "Bow B"),
            ("fp-c", 13501, "Polearm C"),
        ):
            conn.execute(
                """
                INSERT INTO account_weapon_observed_stacks (
                    weapon_fingerprint,
                    weapon_id,
                    name,
                    weapon_type,
                    weapon_type_name,
                    rarity,
                    level,
                    refinement,
                    known_count
                )
                VALUES (?, ?, ?, 1, 'Sword', 5, 90, 1, 1)
                """,
                (fingerprint, weapon_id, name),
            )
        conn.commit()


if __name__ == "__main__":
    unittest.main()
