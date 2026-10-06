"""Isolated safety checks; these tests never launch either application."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[2] / "tools/experiments/startup_profile.py"
SPEC = importlib.util.spec_from_file_location("startup_profile", MODULE_PATH)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class StartupProfileTests(unittest.TestCase):
    def test_tracked_copy_excludes_private_and_unrelated_paths(self):
        paths = probe.selected_tracked_paths([
            "main.py", "ui/app_shell.py", "run_workspace/profile_context.py",
            "hoyolab_export/artifact_db.py", "localization/locales/en.json",
            "assets/artifact_sets/example.png", "data/static/artifact_set_catalog.json",
            "data/artifacts.db", "data/profiles/registry.json", "assets/hoyolab/private.png",
            "hoyolab_export/profile/Cookies", "docs/README.md", ".venv/Lib/site.py",
            "tools/experiments/old.py", "../outside.py", "run_workspace/__pycache__/x.pyc",
        ])
        self.assertEqual([path.as_posix() for path in paths], [
            "main.py", "ui/app_shell.py", "run_workspace/profile_context.py",
            "hoyolab_export/artifact_db.py", "localization/locales/en.json",
            "assets/artifact_sets/example.png", "data/static/artifact_set_catalog.json",
        ])

    def test_copy_cleanup_and_containment(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            source = parent / "source"
            source.mkdir()
            for name in ("main.py", "ui/app_shell_smoke.py"):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# fixture\n", encoding="utf-8")
            (source / "data").mkdir()
            (source / "data/secret.txt").write_text("secret", encoding="utf-8")
            with probe.disposable_snapshot(parent) as snapshot:
                hashes = probe.copy_product(source, snapshot,
                                            [Path("main.py"), Path("ui/app_shell_smoke.py")])
                self.assertEqual(len(hashes), 2)
                self.assertFalse((snapshot / "data").exists())
                self.assertTrue((snapshot / "main.py").is_file())
                copied = snapshot
            self.assertFalse(copied.exists())
            self.assertTrue((source / "data/secret.txt").exists())
            with self.assertRaises(RuntimeError):
                probe._safe_cleanup(source, parent)
            self.assertTrue(source.exists())

    def test_cleanup_retries_transient_windows_handle(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            snapshot = parent / "gtt-startup-retry"
            snapshot.mkdir()
            (snapshot / "artifacts.db").write_text("fixture", encoding="utf-8")
            real_rmtree = probe.shutil.rmtree
            attempts = 0

            def transient_lock(path, *args, **kwargs):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    error = PermissionError("transient handle")
                    error.winerror = 32
                    raise error
                return real_rmtree(path, *args, **kwargs)

            with mock.patch.object(probe.shutil, "rmtree", side_effect=transient_lock), \
                    mock.patch.object(probe.time, "sleep") as sleep:
                probe._safe_cleanup(snapshot, parent)
            self.assertEqual(attempts, 2)
            sleep.assert_called_once_with(probe._CLEANUP_RETRY_DELAYS[0])
            self.assertFalse(snapshot.exists())

    def test_cleanup_does_not_hide_nonsharing_permission_error(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            snapshot = parent / "gtt-startup-denied"
            snapshot.mkdir()
            (snapshot / "artifacts.db").write_text("fixture", encoding="utf-8")
            denied = PermissionError("access denied")
            with mock.patch.object(probe.shutil, "rmtree", side_effect=denied) as rmtree, \
                    mock.patch.object(probe.time, "sleep") as sleep:
                with self.assertRaises(PermissionError) as raised:
                    probe._safe_cleanup(snapshot, parent)
            self.assertIs(raised.exception, denied)
            rmtree.assert_called_once_with(snapshot)
            sleep.assert_not_called()

    def test_cleanup_propagates_persistent_windows_sharing_violation(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            snapshot = parent / "gtt-startup-persistent-lock"
            snapshot.mkdir()
            (snapshot / "artifacts.db").write_text("fixture", encoding="utf-8")
            locked = PermissionError("persistent handle")
            locked.winerror = 32
            with mock.patch.object(probe.shutil, "rmtree", side_effect=locked) as rmtree, \
                    mock.patch.object(probe.time, "sleep") as sleep:
                with self.assertRaises(PermissionError) as raised:
                    probe._safe_cleanup(snapshot, parent)
            self.assertIs(raised.exception, locked)
            self.assertEqual(rmtree.call_count, len(probe._CLEANUP_RETRY_DELAYS))
            self.assertEqual(sleep.call_args_list,
                             [mock.call(delay) for delay in probe._CLEANUP_RETRY_DELAYS[:-1]])

    def test_incomplete_marker_never_passes(self):
        report = probe.summarize_run("shell", "baseline", 0, 12.0,
                                     probe.MARKER + '{"event":"process_start","pid":1}', "", False)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertIsNone(report["launch_to_ready_ms"])
        report = probe.summarize_run("legacy", "detailed", 1, 12.0,
                                     probe.MARKER + "not-json", "failure", False)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["marker_errors"], ["malformed_marker"])
        self.assertEqual(report["stderr_tail"], "failure")
        swallowed = "\n".join(probe.MARKER + json.dumps(event) for event in (
            {"event": "process_start", "pid": 17},
            {"event": "guard_violation", "pid": 17, "kind": "network"},
            {"event": "first_ready_tick", "pid": 17, "at_ms": 10.0, "clock_ns": 20_000_000},
        ))
        report = probe.summarize_run("legacy", "baseline", 0, 15.0, swallowed, "", False, 10_000_000)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["guard_violations"], ["network"])

    def test_hook_is_stdlib_only_and_guards_paths_network_processes(self):
        compile(probe.HOOK, "sitecustomize.py", "exec")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            snapshot = root / "snapshot"
            hooks = root / "hooks"
            source.mkdir()
            snapshot.mkdir()
            hooks.mkdir()
            (source / "data").mkdir()
            (source / "data/secret.txt").write_text("private", encoding="utf-8")
            (source / ".venv").mkdir()
            (source / ".venv/dependency.py").write_text("# dependency", encoding="utf-8")
            (hooks / "sitecustomize.py").write_text(probe.HOOK, encoding="utf-8")
            code = r'''
import json, os, pathlib, socket, subprocess, sys, types
checks = {"no_qt": "PySide6.QtWidgets" not in sys.modules,
          "no_project": "ui.app_shell" not in sys.modules,
          "readonly_interpreter": pathlib.Path(os.environ["GTT_PROBE_SOURCE"], ".venv/dependency.py").read_text() == "# dependency"}
source = pathlib.Path(os.environ["GTT_PROBE_SOURCE"])
for name, function in {
    "private_read": lambda: (source / "data/secret.txt").read_text(),
    "dotdot_read": lambda: (source / "ui/../data/secret.txt").read_text(),
    "sqlite_uri": lambda: sys.audit("sqlite3.connect", (source / "data/secret.txt").as_uri() + "?mode=ro"),
    "source_write": lambda: (source / "new.txt").write_text("x"),
    "interpreter_write": lambda: (source / ".venv/dependency.py").write_text("x"),
    "network": lambda: socket.socket().connect(("127.0.0.1", 1)),
    "dns": lambda: sys.audit("socket.getaddrinfo", "example.invalid", 443, 0, 0, 0),
    "unexpected_process": lambda: subprocess.run([sys.executable, "-c", "pass"]),
}.items():
    try:
        function()
    except RuntimeError:
        checks[name] = True
    else:
        checks[name] = False
import sitecustomize
checks["known_child"] = sitecustomize.allowed_child(
    sys.executable, [sys.executable, "-m", "ui.app_shell_smoke", "--profile-child"],
    os.environ["GTT_PROBE_SNAPSHOT"])
known_args = [sys.executable, "-m", "ui.app_shell_smoke", "--profile-child"]
known_command = subprocess.list2cmdline(known_args) if os.name == "nt" else known_args
sys.audit("subprocess.Popen", None, known_command,
          os.environ["GTT_PROBE_SNAPSHOT"], {})
checks["known_child_audit"] = True
if os.name == "nt":
    checks["known_windows_commandline"] = sitecustomize.allowed_child(
        None, subprocess.list2cmdline(known_args), os.environ["GTT_PROBE_SNAPSHOT"])
checks["reject_second_child"] = False
try:
    sys.audit("subprocess.Popen", None, known_command,
              os.environ["GTT_PROBE_SNAPSHOT"], {})
except RuntimeError:
    checks["reject_second_child"] = True
checks["reject_extra_arg"] = not sitecustomize.allowed_child(
    None, known_args + ["--perf-log"], os.environ["GTT_PROBE_SNAPSHOT"])
checks["reject_wrong_cwd"] = not sitecustomize.allowed_child(
    None, known_args, os.environ["GTT_PROBE_SOURCE"])
class FakeProcess:
    def start(self): pass
    def startCommand(self): pass
    @staticmethod
    def startDetached(): pass
    @staticmethod
    def execute(): pass
fake_module = types.SimpleNamespace(__name__="PySide6.QtCore", QProcess=FakeProcess)
sitecustomize.patch(fake_module)
for name, function in {
    "qt_start": lambda: fake_module.QProcess().start(),
    "qt_command": lambda: fake_module.QProcess().startCommand(),
    "qt_detached": lambda: fake_module.QProcess.startDetached(),
    "qt_execute": lambda: fake_module.QProcess.execute(),
}.items():
    try:
        function()
    except RuntimeError:
        checks[name] = True
    else:
        checks[name] = False
print("CHECKS:" + json.dumps(checks))
'''
            env = os.environ.copy()
            env.update({"PYTHONPATH": str(hooks), "GTT_PROBE_SOURCE": str(source),
                        "GTT_PROBE_SNAPSHOT": str(snapshot), "GTT_PROBE_MODE": "baseline",
                        "GTT_PROBE_TARGET": "shell", "PYTHONDONTWRITEBYTECODE": "1"})
            process = subprocess.run([sys.executable, "-c", code], cwd=snapshot,
                                     env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(process.returncode, 0, process.stderr)
            checks = json.loads(next(line[7:] for line in process.stdout.splitlines()
                                     if line.startswith("CHECKS:")))
            self.assertTrue(all(checks.values()), checks)
            self.assertFalse((source / "new.txt").exists())


if __name__ == "__main__":
    unittest.main()
