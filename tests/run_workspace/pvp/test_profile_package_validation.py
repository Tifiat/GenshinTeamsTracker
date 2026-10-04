from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import warnings
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from PIL import Image, PngImagePlugin

from run_workspace.pvp.profile_package import (
    PVP_PROFILE_ASSETS_NAME, PVP_PROFILE_DB_NAME, PVP_PROFILE_DECKS_NAME,
    PVP_PROFILE_MANIFEST_NAME, PVP_PROFILE_VERSION, ImportedPvpProfileProvider,
    PvpProfilePackageError, PvpProfilePackageOptions, export_pvp_profile_package,
    import_pvp_profile_package,
)
from tests.run_workspace.pvp.test_profile_package import _create_account_db, _write_deck_presets


class PortableProfileValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.db = self.root / "source.sqlite"
        self.decks = self.root / "decks"
        _create_account_db(self.db)
        _write_deck_presets(self.decks)
        self.image = self.root / "neutral.png"
        info = PngImagePlugin.PngInfo()
        info.add_text("private_provenance", "cookie-secret-do-not-export")
        Image.new("RGBA", (72, 72), (30, 90, 170, 255)).save(self.image, pnginfo=info)
        self.package = self.root / "profile.gttpvp"
        self.managed = self.root / "managed"
        self.managed.mkdir()
        self.source_hash = hashlib.sha256(self.db.read_bytes()).hexdigest()
        export_pvp_profile_package(self.package, db_path=self.db, deck_dir=self.decks,
            character_asset_paths={str(i): self.image for i in range(1001, 1025)})
        with zipfile.ZipFile(self.package) as archive:
            self.members = {name: archive.read(name) for name in archive.namelist()}

    def test_package_is_autonomous_and_strips_bitmap_metadata(self) -> None:
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), self.source_hash)
        self.db.unlink()
        self.image.unlink()
        with import_pvp_profile_package(self.package, temp_root=self.managed) as profile:
            self.assertNotEqual(profile.source_db_path, profile.db_path)
            paths = set(profile.character_asset_paths.values())
            self.assertEqual(len(paths), 1)
            with Image.open(next(iter(paths))) as image:
                self.assertEqual(image.info, {})
                self.assertEqual(image.getpixel((0, 0)), (30, 90, 170, 255))
            with closing(sqlite3.connect(profile.source_db_path)) as conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(account_characters)")}
                self.assertNotIn("portrait_path", columns)
                self.assertNotIn("source_metadata_json", columns)
            provider = ImportedPvpProfileProvider(profile)
            runtime = provider.db_path
        self.assertFalse(runtime.exists())
        self.assertEqual(list(self.managed.iterdir()), [])
        with self.assertRaises(PvpProfilePackageError):
            provider.load_deck_presets()

    def test_import_rejects_content_hash_mismatch_and_cleans_temp(self) -> None:
        self._reject({PVP_PROFILE_DB_NAME: b"corrupt"}, update_hashes=False)

    def test_package_preserves_selected_weapon_derived_rows_without_source(self) -> None:
        with closing(sqlite3.connect(self.db)) as conn:
            conn.executemany(
                """INSERT INTO weapon_display_stat_effects
                   (weapon_id,refinement,stat_key,value,value_type) VALUES (?,?,?,?,?)""",
                [
                    (11501, 1, "ATK_PERCENT", 12.0, "percent_points"),
                    (11501, 2, "ATK_PERCENT", 15.0, "percent_points"),
                    (13501, 1, "CRIT_RATE", 5.0, "percent_points"),
                ],
            )
            conn.executemany(
                """INSERT INTO weapon_passive_tooltips
                   (weapon_id,lang,passive_name,passive_text) VALUES (?,?,?,?)""",
                [
                    (11501, "en-us", "Passive", "ATK is increased by 12%."),
                    (13501, "en-us", "Unrelated", "Exclude this."),
                ],
            )
            conn.commit()
        source_bytes = self.db.read_bytes()
        report = export_pvp_profile_package(
            self.package, db_path=self.db, deck_dir=self.decks,
            character_asset_paths={str(i): self.image for i in range(1001, 1025)},
        )
        self.assertEqual(self.db.read_bytes(), source_bytes)
        self.assertEqual(report.counts["weapon_effect_count"], 1)
        self.assertEqual(report.counts["weapon_tooltip_count"], 1)
        self.db.unlink()
        self.image.unlink()
        with import_pvp_profile_package(self.package, temp_root=self.managed) as profile:
            with closing(sqlite3.connect(profile.db_path)) as conn:
                self.assertEqual(conn.execute(
                    "SELECT weapon_id,refinement,stat_key,value FROM weapon_display_stat_effects"
                ).fetchall(), [(11501, 1, "ATK_PERCENT", 12.0)])
                self.assertEqual(conn.execute(
                    "SELECT weapon_id,lang,passive_name,passive_text FROM weapon_passive_tooltips"
                ).fetchall(), [(11501, "en-us", "Passive", "ATK is increased by 12%.")])

    def test_package_rejects_tampered_weapon_rows_after_hash_update(self) -> None:
        statements = (
            ("INSERT INTO weapon_display_stat_effects VALUES (13501,1,'ATK_PERCENT',12,'percent_points')", ()),
            ("INSERT INTO weapon_display_stat_effects VALUES (11501,1,'UNKNOWN_STAT',12,'percent_points')", ()),
            ("INSERT INTO weapon_display_stat_effects VALUES (11501,1,'ATK_PERCENT',?,'percent_points')", (float("inf"),)),
            ("INSERT INTO weapon_passive_tooltips VALUES (13501,'en-us','Passive','Unrelated')", ()),
            ("INSERT INTO weapon_passive_tooltips VALUES (11501,'en-us','Passive',?)", (r"C:\private\secret",)),
        )
        for statement, values in statements:
            with self.subTest(statement=statement):
                database = self.root / "tampered-weapon.sqlite"
                database.write_bytes(self.members[PVP_PROFILE_DB_NAME])
                with closing(sqlite3.connect(database)) as conn:
                    conn.execute(statement, values)
                    conn.commit()
                self._reject({PVP_PROFILE_DB_NAME: database.read_bytes()})

    def test_invalid_source_weapon_effect_preserves_published_package(self) -> None:
        original_package = self.package.read_bytes()
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                """INSERT INTO weapon_display_stat_effects
                   (weapon_id,refinement,stat_key,value,value_type)
                   VALUES (11501,1,'UNKNOWN_STAT',12,'percent_points')"""
            )
            conn.commit()
        source_bytes = self.db.read_bytes()
        with self.assertRaises(PvpProfilePackageError):
            export_pvp_profile_package(
                self.package, db_path=self.db, deck_dir=self.decks,
                character_asset_paths={str(i): self.image for i in range(1001, 1025)},
            )
        self.assertEqual(self.db.read_bytes(), source_bytes)
        self.assertEqual(self.package.read_bytes(), original_package)

    def test_prior_development_profile_version_requires_reexport(self) -> None:
        manifest = json.loads(self.members[PVP_PROFILE_MANIFEST_NAME])
        manifest["version"] = PVP_PROFILE_VERSION - 1
        manifest["schema_version"] = PVP_PROFILE_VERSION - 1
        self._reject({PVP_PROFILE_MANIFEST_NAME: _bytes(manifest)}, update_hashes=False)

    def test_default_export_uses_transparent_source_portrait(self) -> None:
        portrait = self.root / "source-portrait.png"
        bitmap = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
        bitmap.paste((40, 170, 90, 255), (8, 8, 64, 64))
        bitmap.save(portrait)
        with patch("run_workspace.pvp.profile_assets.character_variant_path",
                   side_effect=lambda _id, variant: portrait if variant == "portrait" else self.image) as lookup:
            export_pvp_profile_package(self.package, db_path=self.db, deck_dir=self.decks)
        lookup.assert_any_call("1001", "portrait")
        portrait.unlink()
        with import_pvp_profile_package(self.package, temp_root=self.managed) as profile:
            with Image.open(profile.character_asset_paths["1001"]) as exported:
                self.assertEqual(exported.getpixel((0, 0)), (0, 0, 0, 0))
                self.assertEqual(exported.getpixel((30, 30)), (40, 170, 90, 255))

    def test_rejects_bad_database_even_with_recomputed_hash(self) -> None:
        self._reject({PVP_PROFILE_DB_NAME: b"not a sqlite database"})

    def test_default_weapon_export_resolves_active_account_assets_after_migration(self) -> None:
        relative = Path("assets/hoyolab/weapons/fixture.png")
        active = self.root / "data" / "profiles" / "profile-a"
        other = self.root / "data" / "profiles" / "profile-b"
        public_relative = Path("assets/public/fixture.png")
        active_color = (30, 170, 70, 255)
        public_color = (70, 90, 190, 255)
        for path, color in (
            (active / relative, active_color),
            (self.root / relative, (200, 30, 30, 255)),
            (other / relative, (200, 70, 20, 255)),
            (self.root / public_relative, public_color),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (72, 72), color).save(path)

        with (
            patch("run_workspace.profile_context.PROJECT_ROOT", self.root),
            patch("run_workspace.profile_context.ACCOUNT_ROOT", active),
            patch("run_workspace.profile_context.PROFILE_ID", "profile-a"),
        ):
            for stored_path, expected in (
                (relative, active_color),
                (self.root / relative, active_color),
                (active / relative, active_color),
                (other / relative, None),
                (public_relative, public_color),
            ):
                with self.subTest(stored_path=stored_path):
                    with closing(sqlite3.connect(self.db)) as conn:
                        conn.execute(
                            "UPDATE account_weapon_observed_stacks SET icon_path = ? WHERE weapon_id = 11501",
                            (str(stored_path),),
                        )
                        conn.commit()
                    source_bytes = self.db.read_bytes()
                    export_pvp_profile_package(
                        self.package, db_path=self.db, deck_dir=self.decks,
                        character_asset_paths={str(i): self.image for i in range(1001, 1025)},
                    )
                    self.assertEqual(self.db.read_bytes(), source_bytes)
                    with zipfile.ZipFile(self.package) as archive:
                        assets = json.loads(archive.read(PVP_PROFILE_ASSETS_NAME))
                    with import_pvp_profile_package(self.package, temp_root=self.managed) as profile:
                        is_placeholder = "11501" in assets["placeholders"]["weapons"]
                        self.assertEqual(is_placeholder, expected is None)
                        if expected is not None:
                            with Image.open(profile.weapon_asset_paths["11501"]) as exported:
                                self.assertEqual(exported.getpixel((0, 0)), expected)
                                self.assertEqual(exported.info, {})

    def test_rejects_extra_schema_objects_and_dangling_references(self) -> None:
        for sql in (
            "CREATE TABLE cookie_dump (secret TEXT)",
            "CREATE VIEW fake_profile AS SELECT * FROM account_characters",
            "CREATE TRIGGER bad AFTER INSERT ON account_characters BEGIN DELETE FROM account_characters; END",
            "UPDATE account_character_talents SET character_id = 9999 WHERE character_id = 1001",
        ):
            with self.subTest(sql=sql):
                database = self.root / "tampered.sqlite"
                database.write_bytes(self.members[PVP_PROFILE_DB_NAME])
                with closing(sqlite3.connect(database)) as conn:
                    conn.execute(sql)
                    conn.commit()
                self._reject({PVP_PROFILE_DB_NAME: database.read_bytes()})

    def test_rejects_unknown_duplicate_illegal_decks_and_private_fields(self) -> None:
        for change in (
            lambda deck: deck["character_ids"].__setitem__(0, "9999"),
            lambda deck: deck["character_ids"].append(deck["character_ids"][0]),
            lambda deck: deck.__setitem__("character_ids", ["1001"]),
            lambda deck: deck.__setitem__("ruleset_id", "unknown_ruleset"),
            lambda deck: deck.__setitem__("cookie", "private"),
            lambda deck: deck["weapon_refs"][0].__setitem__("weapon_fingerprint", "unknown-stack"),
            lambda deck: deck["weapon_refs"].append(dict(deck["weapon_refs"][0])),
        ):
            payload = json.loads(self.members[PVP_PROFILE_DECKS_NAME])
            change(payload["decks"][0])
            with self.subTest(payload=payload["decks"][0]):
                self._reject({PVP_PROFILE_DECKS_NAME: _bytes(payload)})

    def test_rejects_missing_unknown_and_invalid_assets(self) -> None:
        payload = json.loads(self.members[PVP_PROFILE_ASSETS_NAME])
        bitmap = payload["characters"]["1001"]
        invalid = dict(payload)
        invalid["characters"] = {**payload["characters"], "1001": "assets/" + "0" * 64 + ".png"}
        self._reject({PVP_PROFILE_ASSETS_NAME: _bytes(invalid)})
        invalid["characters"] = {**payload["characters"], "9999": bitmap}
        self._reject({PVP_PROFILE_ASSETS_NAME: _bytes(invalid)})
        self._reject({bitmap: b"not a bitmap"})
        self._reject({}, omit={bitmap})

    def test_rejects_noncanonical_bitmaps_even_with_matching_hashes(self) -> None:
        for mode, size, comment in (
            ("RGB", (72, 72), False),
            ("RGBA", (2049, 1), False),
            ("RGBA", (72, 72), True),
            ("RGBA", (72, 72), "after_pixels"),
        ):
            buffer = io.BytesIO()
            info = PngImagePlugin.PngInfo()
            if comment == "after_pixels":
                info.add(b"tEXt", b"private\x00cookie-secret-do-not-export", after_idat=True)
            elif comment:
                info.add_text("private", "cookie-secret-do-not-export")
            Image.new(mode, size).save(buffer, format="PNG", pnginfo=info)
            data = buffer.getvalue()
            new_member = "assets/" + hashlib.sha256(data).hexdigest() + ".png"
            payload = json.loads(self.members[PVP_PROFILE_ASSETS_NAME])
            old_member = payload["characters"]["1001"]
            payload["characters"] = {key: new_member for key in payload["characters"]}
            with self.subTest(mode=mode, size=size, comment=comment):
                self._reject({new_member: data, PVP_PROFILE_ASSETS_NAME: _bytes(payload)}, omit={old_member})

    def test_rejects_duplicate_members_traversal_and_unsupported_compression(self) -> None:
        bad = self.root / "bad.gttpvp"
        for name in ("../escape.txt", "assets\\escape.png", "assets/", "unexpected.json"):
            with self.subTest(name=name):
                with zipfile.ZipFile(bad, "w") as archive:
                    for member, data in self.members.items():
                        archive.writestr(member, data)
                    archive.writestr(name, b"x")
                self._assert_rejected(bad)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(bad, "w") as archive:
                for member, data in self.members.items():
                    archive.writestr(member, data)
                archive.writestr(PVP_PROFILE_MANIFEST_NAME, self.members[PVP_PROFILE_MANIFEST_NAME])
        self._assert_rejected(bad)
        with zipfile.ZipFile(bad, "w", compression=zipfile.ZIP_BZIP2) as archive:
            for member, data in self.members.items():
                archive.writestr(member, data)
        self._assert_rejected(bad)

    def test_rejects_total_member_and_compression_limits(self) -> None:
        for name, limit in (("MAX_PROFILE_BYTES", 10), ("MAX_PROFILE_MEMBER_BYTES", 10), ("MAX_PROFILE_MEMBERS", 1), ("MAX_PROFILE_COMPRESSION_RATIO", 1)):
            with self.subTest(limit=name), patch("run_workspace.pvp.profile_package." + name, limit):
                self._assert_rejected(self.package)

    def test_export_failure_preserves_output_and_no_temp_directories(self) -> None:
        before = self.package.read_bytes()
        contents = set(self.root.iterdir())
        with self.assertRaises(PvpProfilePackageError):
            export_pvp_profile_package(self.package, db_path=self.db, deck_dir=self.decks,
                character_asset_paths={"1001": self.root / "missing.png"})
        self.assertEqual(self.package.read_bytes(), before)
        self.assertEqual(set(self.root.iterdir()), contents)

    def test_valid_profile_text_metadata_round_trips_unchanged(self) -> None:
        source_bytes = self.db.read_bytes()
        options = PvpProfilePackageOptions(
            nickname="Traveler - North Star",
            player_label="Player 1",
            locale="en-us",
            abyss_period_id="2026-01",
        )
        report = export_pvp_profile_package(
            self.package, db_path=self.db, deck_dir=self.decks, options=options,
            character_asset_paths={str(i): self.image for i in range(1001, 1025)},
        )
        self.assertEqual(self.db.read_bytes(), source_bytes)
        for key in ("nickname", "player_label", "locale", "abyss_period_id"):
            self.assertEqual(report.manifest[key], getattr(options, key))
        with import_pvp_profile_package(self.package, temp_root=self.managed) as profile:
            provider = ImportedPvpProfileProvider(profile)
            self.assertEqual(dict(provider.metadata), {
                key: getattr(options, key)
                for key in ("nickname", "player_label", "locale", "abyss_period_id")
            })
            self.assertEqual(profile.deck_presets[0].name, "Deck A")
        self.assertEqual(list(self.managed.iterdir()), [])

    def test_absolute_path_metadata_is_rejected_on_export_and_import(self) -> None:
        path_values = (
            r"C:\Users\private\account.sqlite",
            r"\\server\share\account.sqlite",
            "/home/private/account.sqlite",
        )
        original_package = self.package.read_bytes()
        original_source = self.db.read_bytes()
        original_contents = set(self.root.iterdir())

        for value in path_values:
            with self.subTest(export_value=value):
                with self.assertRaises(PvpProfilePackageError):
                    export_pvp_profile_package(
                        self.package, db_path=self.db, deck_dir=self.decks,
                        options=PvpProfilePackageOptions(nickname=value),
                        character_asset_paths={str(i): self.image for i in range(1001, 1025)},
                    )
                self.assertEqual(self.db.read_bytes(), original_source)
                self.assertEqual(self.package.read_bytes(), original_package)
                self.assertEqual(set(self.root.iterdir()), original_contents)

        for value in path_values:
            manifest = json.loads(self.members[PVP_PROFILE_MANIFEST_NAME])
            manifest["nickname"] = value
            with self.subTest(import_manifest_value=value):
                self._reject({PVP_PROFILE_MANIFEST_NAME: _bytes(manifest)})

            decks = json.loads(self.members[PVP_PROFILE_DECKS_NAME])
            decks["decks"][0]["name"] = value
            with self.subTest(import_deck_value=value):
                self._reject({PVP_PROFILE_DECKS_NAME: _bytes(decks)})

    def test_rejects_unknown_manifest_fields_counts_and_duplicate_json(self) -> None:
        for change in (
            lambda data: data.__setitem__("cookies", "private"),
            lambda data: data["counts"].__setitem__("character_count", 1),
            lambda data: data.__setitem__("version", 1),
        ):
            manifest = json.loads(self.members[PVP_PROFILE_MANIFEST_NAME])
            change(manifest)
            self._reject({PVP_PROFILE_MANIFEST_NAME: _bytes(manifest)}, update_hashes=False)
        self._reject({PVP_PROFILE_MANIFEST_NAME: b'{"format":"first","format":"second"}'}, update_hashes=False)

    def _reject(self, changes: dict[str, bytes], *, update_hashes: bool = True, omit: set[str] = frozenset()) -> None:
        members = {**self.members, **changes}
        for member in omit:
            members.pop(member)
        if update_hashes:
            manifest = json.loads(members[PVP_PROFILE_MANIFEST_NAME])
            manifest["files"] = {
                name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                for name, data in members.items() if name != PVP_PROFILE_MANIFEST_NAME
            }
            members[PVP_PROFILE_MANIFEST_NAME] = _bytes(manifest)
        bad = self.root / "bad.gttpvp"
        with zipfile.ZipFile(bad, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member, data in members.items():
                archive.writestr(member, data)
        self._assert_rejected(bad)

    def _assert_rejected(self, path: Path) -> None:
        with self.assertRaises(PvpProfilePackageError):
            import_pvp_profile_package(path, temp_root=self.managed)
        self.assertEqual(list(self.managed.iterdir()), [])


def _bytes(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


if __name__ == "__main__":
    unittest.main()
