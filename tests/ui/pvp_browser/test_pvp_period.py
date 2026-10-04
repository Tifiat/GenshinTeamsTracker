from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from localization import tr
from run_workspace.pvp.deck_preset import PvpDeckPreset, save_deck_preset, weapon_ref_from_asset
from run_workspace.pvp.profile_package import export_pvp_profile_package
from tests.ui.pvp_browser._period_fixture import (
    PERIOD_END_DATE,
    PERIOD_ID,
    PERIOD_START_DATE,
    fixture_period_provider_kwargs,
    fixture_period_ref,
    fixture_profile_options,
)
from tests.ui.pvp_browser.test_pvp_browser import (
    _asset_character_id,
    _create_test_asset_images,
    _seed_pvp_build_db,
    _valid_character_assets,
    _weapon_asset,
)
from ui.pvp_browser.window import PvpWorkspace
from ui.right_panel.pvp.play.panel import PvpPlayRightPanel


_DEFAULT_PERIOD_REF = object()


class PvpPeriodGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_missing_official_period_blocks_play_without_changing_deck_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace, _package = _workspace_fixture(root, period_ref=None)
            self.addCleanup(workspace.close)
            panel = PvpPlayRightPanel(workspace)

            self.assertEqual(workspace.period_admission().status, "period_missing")
            self.assertTrue(
                workspace.deck_start_status("local", player_label="Player 1", seat="player_1").ready
            )
            self.assertFalse(workspace.can_start_local_draft("local", "local"))
            self.assertFalse(panel.start_button.isEnabled())
            self.assertEqual(
                panel.status_label.text(),
                tr("app_shell.pvp.period.unavailable"),
            )
            self.assertFalse(workspace.start_local_draft("local", "local"))
            self.assertIsNone(workspace.active_draft_session)
            self.assertTrue(workspace.period_admission_text())
            blocked_export = root / "blocked.gttpvp"
            self.assertFalse(workspace.decks_workspace.export_profile(blocked_export))
            self.assertEqual(
                workspace.decks_workspace._last_status,
                tr("app_shell.pvp.period.unavailable"),
            )
            self.assertFalse(blocked_export.exists())
            panel.close()

    def test_stale_profile_metadata_fails_until_reexported_for_current_period(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace, package = _workspace_fixture(root)
            self.addCleanup(workspace.close)
            panel = PvpPlayRightPanel(workspace)
            self.addCleanup(panel.close)

            stale_id = "2026-09-01/2026-10-01"
            _export_profile(root, package, period_id=stale_id)
            self.assertTrue(workspace.import_profile_for_seat("player_2", package))
            self.assertEqual(
                workspace.period_admission().status,
                "profile_period_id_mismatch",
            )
            self.assertTrue(
                workspace.deck_start_status("remote", player_label="Player 2", seat="player_2").ready
            )
            self.assertFalse(workspace.can_start_local_draft("local", "remote"))
            self.assertFalse(panel.start_button.isEnabled())

            _export_profile(root, package, period_id=PERIOD_ID)
            self.assertTrue(workspace.import_profile_for_seat("player_2", package))
            self.assertTrue(workspace.period_admission().ready)
            self.assertEqual(workspace.period_admission().period_id, PERIOD_ID)
            self.assertTrue(workspace.can_start_local_draft("local", "remote"))
            self.assertTrue(panel.start_button.isEnabled())
            self.assertTrue(workspace.start_local_draft("local", "remote"))

    def test_mismatched_current_and_expired_official_periods_fail_closed(self) -> None:
        cases = (
            (
                fixture_period_ref(start_date="2026-10-02", end_date="2026-11-02"),
                "profile_period_id_mismatch",
            ),
            (
                fixture_period_ref(start_date="2026-09-01", end_date=PERIOD_START_DATE),
                "period_not_current",
            ),
        )
        for ref, expected_status in cases:
            with self.subTest(expected_status=expected_status), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                workspace, package = _workspace_fixture(root, period_ref=ref)
                self.addCleanup(workspace.close)
                self.assertTrue(workspace.import_profile_for_seat("player_2", package))
                decision = workspace.period_admission()
                self.assertFalse(decision.ready)
                self.assertEqual(decision.status, expected_status)
                self.assertFalse(workspace.can_start_local_draft("local", "remote"))
                self.assertFalse(workspace.start_local_draft("local", "remote"))
                self.assertIsNone(workspace.active_draft_session)
                if expected_status == "period_not_current":
                    blocked_export = root / "expired.gttpvp"
                    self.assertFalse(workspace.decks_workspace.export_profile(blocked_export))
                    self.assertEqual(
                        workspace.decks_workspace._last_status,
                        tr("app_shell.pvp.period.expired"),
                    )
                    self.assertFalse(blocked_export.exists())

    def test_current_local_and_imported_profiles_share_exported_period_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace, package = _workspace_fixture(root)
            self.addCleanup(workspace.close)
            self.assertTrue(workspace.import_profile_for_seat("player_2", package))

            decision = workspace.period_admission()
            local_metadata = workspace.seat_profile_provider("player_1").metadata
            profile = workspace.seat_profile_provider("player_2").profile
            self.assertTrue(decision.ready)
            self.assertEqual(decision.period_id, PERIOD_ID)
            self.assertEqual(local_metadata["abyss_period_id"], PERIOD_ID)
            self.assertEqual(profile.manifest["abyss_period_id"], PERIOD_ID)
            self.assertEqual(profile.manifest["abyss_period_id"], f"{PERIOD_START_DATE}/{PERIOD_END_DATE}")
            self.assertTrue(
                workspace.deck_start_status("local", player_label="Player 1", seat="player_1").ready
            )
            self.assertTrue(
                workspace.deck_start_status("remote", player_label="Player 2", seat="player_2").ready
            )
            self.assertTrue(workspace.can_start_local_draft("local", "remote"))


def _workspace_fixture(
    root: Path,
    *,
    period_ref=_DEFAULT_PERIOD_REF,
) -> tuple[PvpWorkspace, Path]:
    portrait_path, weapon_path = _create_test_asset_images(str(root))
    characters = _valid_character_assets(24, image_path=portrait_path)
    weapons = [
        _weapon_asset(
            "11401",
            "Fixture sword",
            weapon_type=1,
            weapon_type_name="Sword",
            known_count=24,
            image_path=weapon_path,
        )
    ]
    db_path = root / "account.sqlite"
    deck_dir = root / "decks"
    _seed_pvp_build_db(db_path, characters=characters, weapons=weapons)
    save_deck_preset(
        PvpDeckPreset(
            deck_id="local",
            name="Local",
            character_ids=tuple(_asset_character_id(asset) for asset in characters),
            weapon_refs=tuple(weapon_ref_from_asset(asset) for asset in weapons),
        ),
        deck_dir,
    )
    remote_decks = root / "remote-decks"
    save_deck_preset(
        PvpDeckPreset(
            deck_id="remote",
            name="Remote",
            character_ids=tuple(_asset_character_id(asset) for asset in characters),
            weapon_refs=tuple(weapon_ref_from_asset(asset) for asset in weapons),
        ),
        remote_decks,
    )
    package = root / "remote.gttpvp"
    _export_profile(root, package, period_id=PERIOD_ID, db_path=db_path, deck_dir=remote_decks,
                    characters=characters, portrait_path=portrait_path)
    providers = (
        fixture_period_provider_kwargs()
        if period_ref is _DEFAULT_PERIOD_REF
        else fixture_period_provider_kwargs(period_ref)
    )
    workspace = PvpWorkspace(
        **providers,
        db_path=db_path,
        deck_dir=deck_dir,
        character_assets_provider=lambda: characters,
        weapon_assets_provider=lambda: weapons,
    )
    return workspace, package


def _export_profile(
    root: Path,
    package: Path,
    *,
    period_id: str,
    db_path: Path | None = None,
    deck_dir: Path | None = None,
    characters: list[dict] | None = None,
    portrait_path: str | None = None,
) -> None:
    if db_path is None:
        db_path = root / "account.sqlite"
    if deck_dir is None:
        deck_dir = root / "remote-decks"
    if characters is None:
        characters = _valid_character_assets(24, image_path=str(root / "portrait.png"))
    asset_path = portrait_path or str(root / "portrait.png")
    export_pvp_profile_package(
        package,
        db_path=db_path,
        deck_dir=deck_dir,
        options=fixture_profile_options(period_id),
        character_asset_paths={_asset_character_id(asset): asset_path for asset in characters},
    )


if __name__ == "__main__":
    unittest.main()
