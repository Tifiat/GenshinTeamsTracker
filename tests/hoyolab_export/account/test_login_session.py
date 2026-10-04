"""Managed login process coordination without opening a browser or profile."""
from __future__ import annotations

from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from hoyolab_export import auth, login_session


class LoginSessionTest(unittest.TestCase):
    def test_helper_holds_operation_gate_until_browser_exits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "hoyolab_export" / "profile"
            entered = threading.Event()
            browser_waiting = threading.Event()
            release_browser = threading.Event()
            exited = threading.Event()
            gate_held = threading.Event()
            outcome: list[int] = []

            @contextmanager
            def gate():
                gate_held.set()
                entered.set()
                try:
                    yield
                finally:
                    gate_held.clear()
                    exited.set()

            class Browser:
                def wait(self) -> int:
                    self_test.assertTrue(gate_held.is_set())
                    browser_waiting.set()
                    self_test.assertTrue(release_browser.wait(5))
                    return 0

            self_test = self
            with patch.object(login_session, "profile_operation_lock", side_effect=gate), \
                 patch("run_workspace.profile_context.bootstrap_profile", return_value=root), \
                 patch.object(auth, "_open_login_browser_direct", return_value=Browser()) as launch, \
                 patch("builtins.print"):
                worker = threading.Thread(
                    target=lambda: outcome.append(login_session._coordinate_login(
                        profile, 1280, 900, 10, 20,
                    ))
                )
                worker.start()
                self.assertTrue(entered.wait(5))
                self.assertTrue(browser_waiting.wait(5))
                self.assertTrue(gate_held.is_set())
                self.assertFalse(exited.is_set())
                launch.assert_called_once_with(profile, 1280, 900, 10, 20, quiet=True)
                release_browser.set()
                worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(outcome, [0])
            self.assertTrue(exited.is_set())

    def test_managed_api_waits_for_ready_handshake_and_returns_helper(self) -> None:
        class Helper:
            def __init__(self) -> None:
                self.stdout = io.StringIO(json.dumps({"ready": True}) + "\n")

        process = Helper()
        with patch.dict(os.environ, {"GTT_ACCOUNT_PROFILE": "a" * 32}), \
             patch.object(auth.subprocess, "Popen", return_value=process) as popen:
            returned = auth.open_login_browser("fixture/profile", x=-20, y=30)
        self.assertIs(returned, process)
        self.assertTrue(process.stdout.closed)
        args = popen.call_args.args[0]
        self.assertEqual(args[1:4], ["-u", "-m", "hoyolab_export.login_session"])
        self.assertEqual(args[-4:], ["1280", "900", "-20", "30"])

    def test_legacy_api_keeps_direct_launch(self) -> None:
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(auth, "_open_login_browser_direct", return_value=object()) as direct:
            auth.open_login_browser("fixture/profile")
        direct.assert_called_once_with("fixture/profile", 1280, 900, None, None)

    def test_helper_rejects_another_profiles_browser_path_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            @contextmanager
            def gate():
                yield

            with patch.object(login_session, "profile_operation_lock", side_effect=gate), \
                 patch("run_workspace.profile_context.bootstrap_profile", return_value=root), \
                 patch.object(auth, "_open_login_browser_direct") as launch:
                with self.assertRaisesRegex(RuntimeError, "differs"):
                    login_session._coordinate_login(root / "other" / "profile", 1280, 900, None, None)
                launch.assert_not_called()

    def test_ui_pipe_closing_does_not_release_browser_lease_early(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            held = False
            waited = False

            @contextmanager
            def gate():
                nonlocal held
                held = True
                try:
                    yield
                finally:
                    held = False

            class Browser:
                def wait(self) -> int:
                    nonlocal waited
                    self_test.assertTrue(held)
                    waited = True
                    return 0

            self_test = self
            with patch.object(login_session, "profile_operation_lock", side_effect=gate), \
                 patch("run_workspace.profile_context.bootstrap_profile", return_value=root), \
                 patch.object(auth, "_open_login_browser_direct", return_value=Browser()), \
                 patch("builtins.print", side_effect=BrokenPipeError):
                self.assertEqual(login_session._coordinate_login(
                    root / "hoyolab_export" / "profile", 1280, 900, None, None,
                ), 0)
            self.assertTrue(waited)
            self.assertFalse(held)


if __name__ == "__main__":
    unittest.main()
