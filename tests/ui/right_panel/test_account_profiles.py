from __future__ import annotations

from contextlib import ExitStack
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from localization import tr
from run_workspace.app_settings import get_app_bool_setting, read_app_settings, reset_app_settings
from ui.right_panel.settings import account_data, account_profiles


class AccountProfilesUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.temp_dir = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.settings_file = self.temp_dir / "settings.json"
        self.first_id = "a" * 32
        self.second_id = "b" * 32
        self.profiles = [
            {
                "id": self.first_id,
                "created_at": "2026-10-04T00:00:00+00:00",
                "imported": True,
                "metadata": {
                    "uid": "123456789",
                    "server": "os_usa",
                    "nickname": "Amber Main",
                    "adventure_rank": 60,
                    "world_level": 8,
                    "avatar_path": "assets/hoyolab/account/avatar.png",
                },
            },
            {
                "id": self.second_id,
                "created_at": "2026-10-04T00:00:00+00:00",
                "imported": True,
                "metadata": {
                    "uid": "987654321",
                    "server": "os_euro",
                    "nickname": "Amber Alt",
                    "adventure_rank": 55,
                    "world_level": 7,
                    "avatar_path": "assets/hoyolab/account/avatar.png",
                },
            },
        ]
        self.profile_roots = {
            self.first_id: self.temp_dir / "profiles" / self.first_id,
            self.second_id: self.temp_dir / "profiles" / self.second_id,
        }
        self.active_profile = self.profiles[0]

        # Keep all profile lookups and account-facing UI dependencies local.
        self.stack.enter_context(
            patch.object(account_profiles, "active_profile", return_value=self.active_profile)
        )
        self.stack.enter_context(
            patch.object(account_profiles, "list_profiles", return_value=self.profiles)
        )
        self.stack.enter_context(
            patch.object(
                account_profiles,
                "profile_root",
                side_effect=lambda profile_id: self.profile_roots[profile_id],
            )
        )
        for name, kwargs in (
            ("ensure_hoyolab_dirs", {}),
            ("get_auth_status", {"return_value": account_data.AuthStatus.NOT_LOGGED_IN}),
            ("has_local_hoyolab_profile", {"return_value": False}),
            ("get_import_result", {"return_value": None}),
            ("list_pending_import_attempts", {"return_value": []}),
            ("latest_committed_import", {"return_value": None}),
        ):
            self.stack.enter_context(patch.object(account_data, name, **kwargs))

    def _make_page(self) -> account_data.AccountDataPage:
        page = account_data.AccountDataPage(settings_file=self.settings_file)
        self.addCleanup(page._close_hoyolab_loader)
        self.addCleanup(page.close)
        return page

    def _write_avatar(self, profile_id: str) -> None:
        avatar = self.profile_roots[profile_id] / "assets" / "hoyolab" / "account" / "avatar.png"
        avatar.parent.mkdir(parents=True)
        Image.new("RGBA", (8, 8), (35, 145, 220, 255)).save(avatar)

    def test_selector_shows_account_identity_and_profile_avatars(self) -> None:
        self._write_avatar(self.first_id)
        self._write_avatar(self.second_id)
        page = self._make_page()
        selector = page.account_profiles

        current_caption = account_profiles.profile_caption(self.profiles[0])
        self.assertEqual(selector.selector.text(), current_caption)
        self.assertIn("Amber Main", current_caption)
        self.assertIn("123456789", current_caption)
        self.assertIn("60", current_caption)
        self.assertIn("8", current_caption)
        self.assertFalse(selector.selector.icon().isNull())

        selector._populate_menu()
        rows = [action.defaultWidget() for action in selector.menu.actions()]
        self.assertEqual(len(rows), 2)
        for profile, row in zip(self.profiles, rows):
            select = row.findChild(QPushButton, f"selectAccount_{profile['id']}")
            self.assertIsNotNone(select)
            self.assertEqual(select.text(), account_profiles.profile_caption(profile))
            self.assertFalse(select.icon().isNull())
        self.assertFalse(rows[0].findChild(QPushButton, f"selectAccount_{self.first_id}").isEnabled())
        self.assertTrue(rows[1].findChild(QPushButton, f"selectAccount_{self.second_id}").isEnabled())

    def test_login_and_import_buttons_dispatch_independent_actions(self) -> None:
        with patch.object(account_data.AccountDataPage, "login_requested", autospec=True) as login, \
                patch.object(account_data.AccountDataPage, "run_hoyolab_export", autospec=True) as run_import:
            page = self._make_page()
            page.btn_hoyolab_login.click()
            self.assertEqual(login.call_count, 1)
            self.assertEqual(run_import.call_count, 0)

            page.btn_hoyolab_export.click()
            self.assertEqual(login.call_count, 1)
            self.assertEqual(run_import.call_count, 1)

    def test_closing_login_only_refreshes_status_and_does_not_import(self) -> None:
        page = self._make_page()
        page._hoyolab_login_process = Mock(poll=Mock(return_value=0))
        with patch.object(account_data, "get_auth_status", return_value=account_data.AuthStatus.LOGGED_IN), \
                patch.object(page, "_start_hoyolab_import_process") as start:
            page.poll_hoyolab_login_browser()
            page.refresh_hoyolab_auth_status()
        start.assert_not_called()
        self.assertIsNone(page._hoyolab_login_process)
        self.assertTrue(page.btn_hoyolab_export.isEnabled())

    def test_open_login_blocks_import_refresh_and_export_without_new_dialogs(self) -> None:
        page = self._make_page()
        page._hoyolab_login_process = Mock(poll=Mock(return_value=None))
        with patch.object(page, "_start_hoyolab_import_process") as start, \
                patch.object(page, "ask_open_hoyolab_login") as ask, \
                patch.object(account_data.QFileDialog, "getSaveFileName") as export_dialog:
            page.login_requested()
            page.run_hoyolab_export()
            page.run_hoyolab_export(images_only=True)
            self.assertFalse(page.export_profile())
        start.assert_not_called()
        ask.assert_not_called()
        export_dialog.assert_not_called()

    def test_login_overlay_uses_the_same_explicit_import_instruction(self) -> None:
        overlay = account_data.HoYoLABLoginHintOverlay()
        self.addCleanup(overlay.close)
        self.assertEqual(overlay.body_label.text(), tr("accounts.login_hint"))
        overlay.retranslate_ui()
        self.assertEqual(overlay.body_label.text(), tr("accounts.login_hint"))

    def test_accepted_login_hint_suppression_persists_and_reset_restores_default(self) -> None:
        page = self._make_page()
        accepted_buttons = []

        def accept_with_suppression(box: QMessageBox) -> int:
            box.checkBox().setChecked(True)
            understood = next(
                button for button in box.buttons()
                if button.text() == tr("accounts.understood")
            )
            accepted_buttons.append(understood)
            understood.click()
            return 0

        with patch.object(QMessageBox, "exec", new=accept_with_suppression):
            self.assertTrue(page.ask_open_hoyolab_login())
        self.assertTrue(accepted_buttons)
        self.assertTrue(
            get_app_bool_setting(
                "hoyolab_login_hint_dismissed", settings_file=self.settings_file,
            )
        )
        self.assertTrue(read_app_settings(self.settings_file)["hoyolab_login_hint_dismissed"])

        with patch.object(QMessageBox, "exec", side_effect=AssertionError("suppressed hint reopened")):
            self.assertTrue(page.ask_open_hoyolab_login())

        effective = reset_app_settings(self.settings_file)
        self.assertFalse(effective["hoyolab_login_hint_dismissed"])
        self.assertFalse(
            get_app_bool_setting(
                "hoyolab_login_hint_dismissed", settings_file=self.settings_file,
            )
        )
        self.assertEqual(read_app_settings(self.settings_file), {})

        cancelled = []

        def cancel_hint(box: QMessageBox) -> int:
            cancel = next(
                button for button in box.buttons()
                if button.text() == tr("common.cancel")
            )
            cancelled.append(cancel)
            cancel.click()
            return 0

        with patch.object(QMessageBox, "exec", new=cancel_hint):
            self.assertFalse(page.ask_open_hoyolab_login())
        self.assertEqual(len(cancelled), 1)

    def test_confirmed_delete_emits_request_without_mutating_profile_selection(self) -> None:
        page = self._make_page()
        operations: list[tuple[str, str]] = []
        page.profile_operation_requested.connect(
            lambda operation, profile_id: operations.append((operation, profile_id))
        )
        profiles_before = list(self.profiles)
        active_before = self.active_profile

        page.account_profiles._populate_menu()
        row = next(
            action.defaultWidget()
            for action in page.account_profiles.menu.actions()
            if action.defaultWidget().findChild(
                QPushButton, f"deleteAccount_{self.second_id}"
            )
        )
        delete = row.findChild(QPushButton, f"deleteAccount_{self.second_id}")
        confirmed = []
        def accept_delete(box):
            confirmed.append(box.text())
            yes = next(button for button in box.buttons() if button.text() == tr("common.yes"))
            yes.click()
            return 0
        with patch.object(QMessageBox, "exec", new=accept_delete):
            delete.click()

        self.assertEqual(confirmed, [tr("accounts.delete_confirm")])
        self.assertEqual(operations, [("delete", self.second_id)])
        self.assertIs(self.active_profile, active_before)
        self.assertEqual(self.profiles, profiles_before)
        self.assertFalse(any(path.exists() for path in self.profile_roots.values()))


if __name__ == "__main__":
    unittest.main()
