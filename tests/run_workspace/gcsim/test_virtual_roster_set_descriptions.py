from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from run_workspace.gcsim.virtual_roster import (
    GcsimVirtualArtifactSetChoice,
    load_active_virtual_artifact_set_choices,
)


class GcsimVirtualArtifactSetDescriptionTest(unittest.TestCase):
    @staticmethod
    def _store():
        return SimpleNamespace(
            get_active_engine=lambda: SimpleNamespace(path=Path("engine-root"))
        )

    @staticmethod
    def _capabilities(*items):
        return SimpleNamespace(sets=items)

    def test_descriptions_use_local_uid_and_hoyolab_language_then_english(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "artifacts.db"
            language_dir = root / "hoyolab"
            language_dir.mkdir()
            (language_dir / "account_language.json").write_text(
                json.dumps({"contentLanguage": "fr-FR"}), encoding="utf-8"
            )
            with closing(sqlite3.connect(db_path)) as conn:
                conn.executescript(
                    """
                    CREATE TABLE artifact_sets (
                        set_uid TEXT NOT NULL,
                        fallback_name TEXT NOT NULL
                    );
                    CREATE TABLE artifact_set_names (
                        set_uid TEXT NOT NULL,
                        lang TEXT NOT NULL,
                        name TEXT NOT NULL
                    );
                    CREATE TABLE artifact_set_bonus_descriptions (
                        set_uid TEXT NOT NULL,
                        lang TEXT NOT NULL,
                        piece_count INTEGER NOT NULL,
                        description TEXT NOT NULL
                    );
                    INSERT INTO artifact_sets VALUES ('uid-local', 'noblesseoblige');
                    INSERT INTO artifact_set_names VALUES ('uid-local', 'en-us', 'Noblesse Oblige');
                    INSERT INTO artifact_set_bonus_descriptions VALUES ('uid-local', 'fr-fr', 2, 'Bonus deux pièces');
                    INSERT INTO artifact_set_bonus_descriptions VALUES ('uid-local', 'en-us', 2, 'Two-piece fallback');
                    INSERT INTO artifact_set_bonus_descriptions VALUES ('uid-local', 'en-us', 4, 'Four-piece fallback');
                    """
                )
                conn.commit()

            capabilities = self._capabilities(
                SimpleNamespace(
                    key="noblesseoblige",
                    two_piece_modeled=True,
                    complete_four_piece_modeled=True,
                )
            )
            with (
                patch(
                    "run_workspace.gcsim.virtual_roster.HOYOLAB_DATA_DIR",
                    language_dir,
                ),
                patch(
                    "run_workspace.gcsim.virtual_roster.load_gcsim_artifact_set_catalog",
                    return_value=capabilities,
                ),
            ):
                choices = load_active_virtual_artifact_set_choices(
                    db_path,
                    language="en-us",
                    store=self._store(),
                )

        self.assertEqual(len(choices), 1)
        choice = choices[0]
        self.assertEqual(choice.set_uid, "uid-local")
        self.assertEqual(choice.gcsim_key, "noblesseoblige")
        self.assertEqual(choice.two_piece_description, "Bonus deux pièces")
        self.assertEqual(choice.four_piece_description, "Four-piece fallback")
        self.assertTrue(choice.two_piece_available)
        self.assertTrue(choice.four_piece_available)

    def test_missing_local_uid_mapping_or_description_table_keeps_empty_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "artifacts.db"
            with closing(sqlite3.connect(db_path)) as conn:
                conn.executescript(
                    """
                    CREATE TABLE artifact_sets (
                        set_uid TEXT NOT NULL,
                        fallback_name TEXT NOT NULL
                    );
                    CREATE TABLE artifact_set_names (
                        set_uid TEXT NOT NULL,
                        lang TEXT NOT NULL,
                        name TEXT NOT NULL
                    );
                    """
                )
                conn.commit()

            capabilities = self._capabilities(
                SimpleNamespace(
                    key="unmappedset",
                    two_piece_modeled=True,
                    complete_four_piece_modeled=False,
                )
            )
            with (
                patch(
                    "run_workspace.gcsim.virtual_roster.HOYOLAB_DATA_DIR",
                    Path(temp_dir) / "hoyolab",
                ),
                patch(
                    "run_workspace.gcsim.virtual_roster.load_gcsim_artifact_set_catalog",
                    return_value=capabilities,
                ),
            ):
                choices = load_active_virtual_artifact_set_choices(
                    db_path,
                    language="en-us",
                    store=self._store(),
                )

        self.assertEqual(len(choices), 1)
        choice = choices[0]
        self.assertEqual(choice.set_uid, "unmappedset")
        self.assertEqual(choice.gcsim_key, "unmappedset")
        self.assertTrue(choice.two_piece_available)
        self.assertFalse(choice.four_piece_available)
        self.assertEqual(choice.two_piece_description, "")
        self.assertEqual(choice.four_piece_description, "")

        legacy_choice = GcsimVirtualArtifactSetChoice("uid", "Name", "engine-key")
        self.assertEqual(legacy_choice.two_piece_description, "")
        self.assertEqual(legacy_choice.four_piece_description, "")


if __name__ == "__main__":
    unittest.main()
