from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
from threading import Event, Thread
import unittest
from unittest.mock import patch

from run_workspace.pvp.gcsim_execution import (
    PvpCancellableArtifactRunner,
    PvpGcsimRunSession,
    close_pvp_gcsim_sessions,
)
from run_workspace.pvp.profile_package import ImportedPvpProfile, ImportedPvpProfileProvider
from ui.gcsim_browser.run_worker import GcsimBrowserRunRequest


def _request(*, db_path: str = "seat.sqlite", engine_id: str = "engine-a", side: int = 1):
    return GcsimBrowserRunRequest(
        db_path=db_path,
        selected_team={"slots": [{"character": {"id": 1001, "name": "First"}}]},
        team_index=0,
        chamber=1,
        side=side,
        rotation_shell_text="active first;",
        abyss_period_start="2026-06-01",
        abyss_floor=12,
        expected_engine_id=engine_id,
        allow_account_equipment_fallback=False,
    )


class _FakeProcess:
    def __init__(self, *, keep_running: bool = False, entered: Event | None = None) -> None:
        self.keep_running = keep_running
        self.entered = entered
        self.returncode: int | None = None
        self.kills = 0
        self.reaps = 0

    def communicate(self, timeout=None):
        if self.entered is not None:
            self.entered.set()
        if self.kills:
            self.reaps += 1
            self.returncode = -9
            return "", "killed"
        if self.keep_running:
            raise subprocess.TimeoutExpired(["fake-engine"], timeout)
        self.returncode = 0
        return "ok", ""

    def poll(self):
        return self.returncode

    def kill(self):
        self.kills += 1


class PvpGcsimRunSessionTest(unittest.TestCase):
    def test_failed_cleanup_keeps_owned_reference_for_retry(self) -> None:
        session = PvpGcsimRunSession(provider=object())
        self.addCleanup(session.close)
        session.start(_request(), generation=1, batch=False, executor=lambda *_args, **_kwargs: {})
        session.wait_closed(2)
        root = session.output_root
        temporary = session._temporary
        with patch.object(temporary, "cleanup", side_effect=OSError("fixture denied cleanup")):
            with self.assertRaisesRegex(OSError, "fixture denied cleanup"):
                session.close()
            self.assertEqual(session.output_root, root)
            self.assertTrue(root.exists())
        session.close()
        self.assertIsNone(session.output_root)
        self.assertFalse(root.exists())

    def test_cleanup_does_not_follow_an_output_symlink_into_unowned_data(self) -> None:
        with tempfile.TemporaryDirectory() as external:
            sentinel = Path(external) / "unowned.txt"
            sentinel.write_text("keep", encoding="utf-8")
            session = PvpGcsimRunSession(provider=object())
            self.addCleanup(session.close)
            session.start(_request(), generation=1, batch=False, executor=lambda *_args, **_kwargs: {})
            session.wait_closed(2)
            root = session.output_root
            try:
                (root / "external-link").symlink_to(external, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"Host cannot create fixture symlinks: {exc.winerror if hasattr(exc, 'winerror') else exc.errno}")
            session.close()
            self.assertFalse(root.exists())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_capacity_is_bounded_across_cleared_matches_and_shutdown_reaps_old_jobs(self) -> None:
        sessions = [PvpGcsimRunSession(provider=object()) for _ in range(3)]
        entered = [Event(), Event()]

        def executor(index):
            def run(request, **kwargs):
                entered[index].set()
                while not kwargs["cancel_requested"]():
                    Event().wait(0.005)
                return {"success": False, "status": "cancelled"}
            return run

        try:
            for index in range(2):
                self.assertTrue(sessions[index].start(_request(), generation=index, batch=False, executor=executor(index)))
                self.assertTrue(entered[index].wait(1))
            roots = [session.output_root for session in sessions[:2]]
            self.assertFalse(sessions[2].start(_request(), generation=3, batch=False, executor=executor(0)))
            self.assertIsNone(sessions[2].output_root)
            # A match may already be closed; app shutdown still owns its reader.
            sessions[0].close()
            close_pvp_gcsim_sessions()
            self.assertTrue(all(not session.busy for session in sessions))
            self.assertTrue(all(not root.exists() for root in roots))
        finally:
            for session in sessions:
                session.close()
                session.wait_closed(2)

    def test_two_seats_snapshot_explicit_sources_and_reject_busy_start(self) -> None:
        entered = [Event(), Event()]
        release = [Event(), Event()]
        seen = []
        sessions = [PvpGcsimRunSession(provider=object()) for _ in range(2)]
        for session in sessions:
            self.addCleanup(session.close)
        requests = [
            _request(db_path="seat-one.sqlite", engine_id="engine-one", side=1),
            _request(db_path="seat-two.sqlite", engine_id="engine-two", side=2),
        ]

        def executor(index):
            def run(request, **kwargs):
                seen.append((index, request, kwargs))
                entered[index].set()
                if not release[index].wait(2):
                    raise AssertionError("test executor was not released")
                return {"success": True, "seat": index}
            return run

        try:
            self.assertTrue(sessions[0].start(requests[0], generation=11, batch=False, executor=executor(0)))
            self.assertTrue(sessions[1].start(requests[1], generation=22, batch=True, executor=executor(1)))
            self.assertTrue(all(item.wait(1) for item in entered))
            self.assertFalse(sessions[0].start(requests[0], generation=99, batch=False, executor=executor(0)))
            roots = [session.output_root for session in sessions]
            self.assertEqual(len(set(roots)), 2)
            self.assertTrue(all(root is not None and root.exists() for root in roots))
            requests[0].selected_team["slots"][0]["character"]["name"] = "Changed later"
        finally:
            for gate in release:
                gate.set()
            for session in sessions:
                session.wait_closed(2)

        try:
            self.assertEqual(len(seen), 2)
            for index, expected in enumerate(requests):
                result = sessions[index].take_result()
                self.assertIsNotNone(result)
                assert result is not None
                self.assertEqual(result.generation, (11, 22)[index])
                self.assertEqual(result.batch, bool(index))
                self.assertEqual(result.payload, {"success": True, "seat": index})
                self.assertEqual(result.request.db_path, expected.db_path)
                self.assertEqual(result.request.expected_engine_id, expected.expected_engine_id)
                self.assertEqual(result.request.side, expected.side)
                self.assertFalse(result.request.allow_account_equipment_fallback)
                self.assertEqual(result.request.run_root, str(roots[index]))
                self.assertEqual(result.request.selected_team["slots"][0]["character"]["name"], "First")
                self.assertIsNone(sessions[index].take_result())
        finally:
            for session in sessions:
                session.close()
                session.close()

    def test_new_run_replaces_latest_root_and_close_preserves_unowned_output(self) -> None:
        with tempfile.TemporaryDirectory() as external:
            sentinel = Path(external) / "unowned.txt"
            sentinel.write_text("keep", encoding="utf-8")
            session = PvpGcsimRunSession(provider=object())
            self.addCleanup(session.close)
            try:
                self.assertTrue(session.start(_request(), generation=1, batch=False,
                                              executor=lambda _request, **_kwargs: {"success": True}))
                session.wait_closed(2)
                first_root = session.output_root
                self.assertIsNotNone(first_root)
                assert first_root is not None
                (first_root / "owned.txt").write_text("remove", encoding="utf-8")
                self.assertTrue(session.start(_request(), generation=2, batch=False,
                                              executor=lambda _request, **_kwargs: {"success": True}))
                session.wait_closed(2)
                second_root = session.output_root
                self.assertFalse(first_root.exists())
                self.assertNotEqual(second_root, first_root)
                self.assertTrue(second_root is not None and second_root.exists())
                result = session.take_result()
                self.assertIsNotNone(result)
                assert result is not None
                self.assertEqual(result.generation, 2)
            finally:
                session.close()
                session.close()
            self.assertFalse(second_root.exists())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_cancel_waits_for_worker_then_cleans_owned_root(self) -> None:
        entered, release = Event(), Event()
        session = PvpGcsimRunSession(provider=object())
        self.addCleanup(session.close)
        external = tempfile.TemporaryDirectory()
        self.addCleanup(external.cleanup)
        sentinel = Path(external.name) / "unowned.txt"
        sentinel.write_text("keep", encoding="utf-8")

        def executor(_request, **kwargs):
            entered.set()
            if not release.wait(2):
                raise AssertionError("test executor was not released")
            self.assertTrue(kwargs["cancel_requested"]())
            return {"success": True}

        try:
            self.assertTrue(session.start(_request(), generation=3, batch=False, executor=executor))
            self.assertTrue(entered.wait(1))
            root = session.output_root
            self.assertIsNotNone(root)
            session.cancel()
            self.assertTrue(root.exists())
        finally:
            release.set()
            session.wait_closed(2)
        try:
            self.assertFalse(root.exists())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            result = session.take_result()
            self.assertIsNotNone(result)
            assert result is not None
            self.assertFalse(result.payload["success"])
            self.assertEqual(result.payload["status"], "cancelled")
        finally:
            session.close()

    def test_imported_source_lease_outlives_close_until_worker_release(self) -> None:
        with tempfile.TemporaryDirectory() as outer:
            imported_temp = tempfile.TemporaryDirectory(dir=outer)
            runtime_path = Path(imported_temp.name) / "runtime.sqlite"
            runtime_path.write_bytes(b"fixture")
            profile = ImportedPvpProfile(
                path=Path(outer) / "profile.gttpvp", manifest={}, deck_presets=(),
                db_path=runtime_path, source_db_path=runtime_path, _temp_dir=imported_temp,
            )
            provider = ImportedPvpProfileProvider(profile)
            entered, release = Event(), Event()
            session = PvpGcsimRunSession(provider=provider)
            self.addCleanup(session.close)

            def executor(_request, **_kwargs):
                entered.set()
                if not release.wait(2):
                    raise AssertionError("test executor was not released")
                self.assertTrue(runtime_path.exists())
                return {"success": True}

            try:
                self.assertTrue(session.start(_request(db_path=str(runtime_path)), generation=4,
                                              batch=False, executor=executor))
                self.assertTrue(entered.wait(1))
                profile.close()
                self.assertTrue(profile._closed)
                self.assertTrue(runtime_path.exists())
            finally:
                release.set()
                session.wait_closed(2)
                session.close()
            self.assertFalse(runtime_path.exists())
            profile.close()

    def test_imported_profile_release_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as outer:
            imported_temp = tempfile.TemporaryDirectory(dir=outer)
            runtime_path = Path(imported_temp.name) / "runtime.sqlite"
            runtime_path.write_bytes(b"fixture")
            profile = ImportedPvpProfile(
                path=Path(outer) / "profile.gttpvp", manifest={}, deck_presets=(),
                db_path=runtime_path, source_db_path=runtime_path, _temp_dir=imported_temp,
            )
            release = profile.retain_runtime()
            profile.close()
            self.assertTrue(profile._closed)
            self.assertTrue(runtime_path.exists())
            release()
            release()
            self.assertFalse(runtime_path.exists())

    def test_executor_exception_is_failed_payload(self) -> None:
        session = PvpGcsimRunSession(provider=object())
        self.addCleanup(session.close)
        try:
            def fail(_request, **_kwargs):
                raise RuntimeError("synthetic execution failure")
            self.assertTrue(session.start(_request(), generation=5, batch=False, executor=fail))
            session.wait_closed(2)
            result = session.take_result()
            self.assertIsNotNone(result)
            assert result is not None
            self.assertFalse(result.payload["success"])
            self.assertEqual(result.payload["error_category"], "gcsim_runtime_error")
            self.assertIn("synthetic execution failure", result.payload["error"])
        finally:
            session.close()


class PvpCancellableArtifactRunnerTest(unittest.TestCase):
    def test_success_forwards_process_inputs_and_does_not_kill(self) -> None:
        process = _FakeProcess()
        calls = []

        def factory(command, **kwargs):
            calls.append((command, kwargs))
            return process

        runner = PvpCancellableArtifactRunner(Event(), process_factory=factory)
        result = runner(["fake-engine", "-c", "config.txt"], Path("scratch"), {"A": "B"}, 1)
        self.assertEqual(result.returncode, 0)
        self.assertEqual((result.stdout, result.stderr), ("ok", ""))
        self.assertEqual(process.kills, 0)
        self.assertEqual(calls[0][0], ["fake-engine", "-c", "config.txt"])
        self.assertEqual(calls[0][1]["cwd"], str(Path("scratch")))
        self.assertEqual(calls[0][1]["env"], {"A": "B"})
        self.assertEqual(calls[0][1]["stdout"], subprocess.PIPE)
        self.assertEqual(calls[0][1]["stderr"], subprocess.PIPE)
        self.assertTrue(calls[0][1]["text"])
        self.assertEqual(calls[0][1]["creationflags"],
                         subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    def test_precancel_never_spawns(self) -> None:
        cancellation = Event()
        cancellation.set()
        calls = []
        runner = PvpCancellableArtifactRunner(
            cancellation, process_factory=lambda *_args, **_kwargs: calls.append(1),
        )
        with self.assertRaisesRegex(OSError, "cancelled"):
            runner(["fake-engine"], Path("scratch"), {}, 1)
        self.assertEqual(calls, [])

    def test_midcancel_kills_and_reaps(self) -> None:
        cancellation, entered = Event(), Event()
        process = _FakeProcess(keep_running=True, entered=entered)
        runner = PvpCancellableArtifactRunner(cancellation, process_factory=lambda *_args, **_kwargs: process)
        failures = []

        def run():
            try:
                runner(["fake-engine"], Path("scratch"), {}, 2)
            except Exception as exc:
                failures.append(exc)

        thread = Thread(target=run, daemon=True)
        thread.start()
        self.assertTrue(entered.wait(1))
        cancellation.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], OSError)
        self.assertEqual(process.kills, 1)
        self.assertGreaterEqual(process.reaps, 1)

    def test_timeout_kills_and_reaps(self) -> None:
        process = _FakeProcess(keep_running=True)
        runner = PvpCancellableArtifactRunner(Event(), process_factory=lambda *_args, **_kwargs: process)
        with self.assertRaises(subprocess.TimeoutExpired):
            runner(["fake-engine"], Path("scratch"), {}, 0)
        self.assertEqual(process.kills, 1)
        self.assertGreaterEqual(process.reaps, 1)


if __name__ == "__main__":
    unittest.main()
