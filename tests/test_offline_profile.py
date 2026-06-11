from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import zipfile
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from hoyolab_export import offline_profile


class OfflineProfileTest(unittest.TestCase):
    def test_account_language_is_profile_data_and_restorable(self) -> None:
        self.assertIn(
            offline_profile.HOYOLAB_DATA_DIR / "account_language.json",
            offline_profile.PROFILE_DATA_FILES,
        )
        self.assertIn(
            "data/hoyolab/account_language.json",
            offline_profile.RESTORABLE_FILES,
        )

    def test_export_import_round_trip_preserves_account_language(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data" / "hoyolab"
            assets_dir = root / "assets" / "hoyolab"
            debug_dir = root / "debug" / "hoyolab"
            character_assets_dir = assets_dir / "characters"
            weapon_assets_dir = assets_dir / "weapons"
            artifact_assets_dir = assets_dir / "artifacts"
            export_state_path = data_dir / "offline_export_state.json"
            artifact_db_path = root / "data" / "artifacts.db"

            profile_data_files = (
                data_dir / "account_language.json",
                data_dir / "account_characters.json",
                data_dir / "account_weapons.json",
                data_dir / "crop_manifest.json",
                data_dir / "account_character_details.json",
            )
            restorable_files = {
                path.relative_to(root).as_posix() for path in profile_data_files
            }
            restorable_files.add("data/artifacts.db")

            def ensure_dirs() -> None:
                for folder in (
                    data_dir,
                    character_assets_dir,
                    weapon_assets_dir,
                    artifact_assets_dir,
                    debug_dir,
                ):
                    folder.mkdir(parents=True, exist_ok=True)

            def clear_current_data() -> None:
                for folder in (data_dir, assets_dir, debug_dir):
                    folder.mkdir(parents=True, exist_ok=True)
                    for child in folder.iterdir():
                        if child.is_dir():
                            shutil.rmtree(child)
                        else:
                            child.unlink()
                ensure_dirs()

            with ExitStack() as stack:
                stack.enter_context(
                    mock.patch.object(offline_profile, "PROJECT_ROOT", root)
                )
                stack.enter_context(
                    mock.patch.object(offline_profile, "HOYOLAB_DATA_DIR", data_dir)
                )
                stack.enter_context(
                    mock.patch.object(
                        offline_profile,
                        "PROFILE_DATA_FILES",
                        profile_data_files,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        offline_profile,
                        "PROFILE_ASSET_DIRS",
                        (character_assets_dir, weapon_assets_dir, artifact_assets_dir),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        offline_profile,
                        "RESTORABLE_FILES",
                        restorable_files,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        offline_profile,
                        "ARTIFACT_DB_PATH",
                        artifact_db_path,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        offline_profile,
                        "PROFILE_EXPORT_STATE_FILE",
                        export_state_path,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        offline_profile,
                        "ensure_hoyolab_dirs",
                        ensure_dirs,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        offline_profile,
                        "clear_hoyolab_current_data",
                        clear_current_data,
                    )
                )

                ensure_dirs()
                expected_language = {"contentLanguage": "ru-ru", "uiLanguage": "ru-ru"}
                (data_dir / "account_language.json").write_text(
                    json.dumps(expected_language),
                    encoding="utf-8",
                )
                (data_dir / "account_characters.json").write_text(
                    "[]",
                    encoding="utf-8",
                )

                zip_path = root / "profile.zip"
                export_result = offline_profile.export_offline_profile(zip_path)

                self.assertIn(
                    "data/hoyolab/account_language.json",
                    export_result["includedFiles"],
                )
                with zipfile.ZipFile(zip_path, "r") as archive:
                    self.assertIn(
                        "data/hoyolab/account_language.json",
                        archive.namelist(),
                    )

                (data_dir / "account_language.json").write_text(
                    json.dumps({"contentLanguage": "en-us"}),
                    encoding="utf-8",
                )

                import_result = offline_profile.import_offline_profile(zip_path)

                self.assertIn(
                    "data/hoyolab/account_language.json",
                    import_result["restoredFiles"],
                )
                restored_language = json.loads(
                    (data_dir / "account_language.json").read_text(encoding="utf-8")
                )
                self.assertEqual(restored_language, expected_language)


if __name__ == "__main__":
    unittest.main()
