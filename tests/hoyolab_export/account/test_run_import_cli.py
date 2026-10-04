"""CLI receipt and replay contract fixtures; no browser or account database access."""
import asyncio
import io
import json
from pathlib import Path
import tempfile
import unittest
import uuid
import uuid
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from unittest.mock import AsyncMock, patch

from hoyolab_export import run_import
from hoyolab_export import import_store
from hoyolab_export.import_store import LegacyAccountBindingRequired


class RunImportCliTest(unittest.TestCase):
    def test_cli_passes_attempt_options_through_asyncio_run(self):
        output = io.StringIO()
        operation = AsyncMock(return_value={
            "attemptId": "attempt-123", "status": "committed", "pendingJobs": [],
            "manifest": {}, "warnings": [],
        })
        with patch.object(run_import.sys, "argv", [
            "run_import", "--attempt-id", "attempt-123", "--change-equipment",
        ]), patch.object(run_import, "import_run_lock", return_value=nullcontext()), \
                patch.object(run_import, "run_hoyolab_import", operation), \
                patch.object(run_import.asyncio, "run", wraps=asyncio.run) as run_async, \
                redirect_stdout(output):
            self.assertEqual(run_import.main(), 0)

        operation.assert_awaited_once_with(
            change_equipment=True, images_only=False, attempt_id="attempt-123",
            resume_attempt=None, adopt_legacy=False,
        )
        run_async.assert_called_once()
        self.assertIn("[HoYoLAB Import] Summary", output.getvalue())

    def test_legacy_binding_emits_staged_identity_and_distinct_exit_code(self):
        output, errors = io.StringIO(), io.StringIO()
        attempt = {"attempt_id": "saved-123", "account_uid": "123456789", "server": "os_usa"}
        operation = AsyncMock(side_effect=LegacyAccountBindingRequired("legacy rows need confirmation"))
        with patch.object(run_import.sys, "argv", [
            "run_import", "--resume-attempt", "saved-123", "--adopt-legacy",
        ]), patch.object(run_import, "import_run_lock", return_value=nullcontext()), \
                patch.object(run_import, "run_hoyolab_import", operation), \
                patch.object(run_import, "get_import_attempt", return_value=attempt) as get_attempt, \
                redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(run_import.main(), 3)

        get_attempt.assert_called_once_with(run_import.ARTIFACT_DB_PATH, "saved-123")
        operation.assert_awaited_once_with(
            change_equipment=False, images_only=False, attempt_id=None,
            resume_attempt="saved-123", adopt_legacy=True,
        )
        marker = next(line for line in output.getvalue().splitlines()
                      if line.startswith("[IMPORT_BINDING_REQUIRED] "))
        self.assertEqual(json.loads(marker.split(" ", 1)[1]), {
            "attempt_id": "saved-123", "account_uid": "123456789", "server": "os_usa",
        })

    def test_direct_cli_generates_attempt_id_before_legacy_binding_receipt(self):
        generated_id = uuid.UUID("b6e7d8c9-1023-4567-8901-23456789abcd")
        attempt = {"attempt_id": str(generated_id), "account_uid": "123456789", "server": "os_usa"}
        output = io.StringIO()
        operation = AsyncMock(side_effect=LegacyAccountBindingRequired("legacy rows need confirmation"))
        with patch.object(run_import.sys, "argv", ["run_import"]), \
                patch.object(run_import.uuid, "uuid4", return_value=generated_id), \
                patch.object(run_import, "import_run_lock", return_value=nullcontext()), \
                patch.object(run_import, "run_hoyolab_import", operation), \
                patch.object(run_import, "get_import_attempt", return_value=attempt) as get_attempt, \
                redirect_stdout(output), redirect_stderr(io.StringIO()):
            self.assertEqual(run_import.main(), 3)

        operation.assert_awaited_once_with(
            change_equipment=False, images_only=False, attempt_id=str(generated_id),
            resume_attempt=None, adopt_legacy=False,
        )
        get_attempt.assert_called_once_with(run_import.ARTIFACT_DB_PATH, str(generated_id))
        marker = next(line for line in output.getvalue().splitlines()
                      if line.startswith("[IMPORT_BINDING_REQUIRED] "))
        self.assertEqual(json.loads(marker.split(" ", 1)[1]), {
            "attempt_id": str(generated_id), "account_uid": "123456789", "server": "os_usa",
        })

    def test_resume_ignores_change_equipment_switch_from_the_cli(self):
        operation = AsyncMock(return_value={"warnings": []})
        with patch.object(run_import.sys, "argv", [
            "run_import", "--resume-attempt", "saved-123", "--change-equipment",
        ]), patch.object(run_import, "import_run_lock", return_value=nullcontext()), \
                patch.object(run_import, "run_hoyolab_import", operation), redirect_stdout(io.StringIO()):
            self.assertEqual(run_import.main(), 0)
        operation.assert_awaited_once_with(
            change_equipment=False, images_only=False, attempt_id=None,
            resume_attempt="saved-123", adopt_legacy=False,
        )

    def test_cli_rejects_incompatible_attempt_modes_and_unscoped_adoption(self):
        for argv in (
            ["run_import", "--images-only", "--attempt-id", "new-123"],
            ["run_import", "--adopt-legacy"],
        ):
            with self.subTest(argv=argv), patch.object(run_import.sys, "argv", argv), \
                    patch.object(run_import, "run_hoyolab_import") as operation, \
                    redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    run_import.main()
            self.assertEqual(raised.exception.code, 2)
            operation.assert_not_called()

    def test_direct_cli_generates_attempt_id_before_legacy_binding_receipt(self):
        generated_id = uuid.UUID("b6e7d8c9-1023-4567-8901-23456789abcd")
        attempt = {"attempt_id": str(generated_id), "account_uid": "123456789", "server": "os_usa"}
        output = io.StringIO()
        operation = AsyncMock(side_effect=LegacyAccountBindingRequired("legacy rows need confirmation"))
        with patch.object(run_import.sys, "argv", ["run_import"]), \
                patch.object(run_import.uuid, "uuid4", return_value=generated_id), \
                patch.object(run_import, "import_run_lock", return_value=nullcontext()), \
                patch.object(run_import, "run_hoyolab_import", operation), \
                patch.object(run_import, "get_import_attempt", return_value=attempt) as get_attempt, \
                redirect_stdout(output), redirect_stderr(io.StringIO()):
            self.assertEqual(run_import.main(), 3)

        operation.assert_awaited_once_with(
            change_equipment=False, images_only=False, attempt_id=str(generated_id),
            resume_attempt=None, adopt_legacy=False,
        )
        get_attempt.assert_called_once_with(run_import.ARTIFACT_DB_PATH, str(generated_id))
        marker = next(line for line in output.getvalue().splitlines()
                      if line.startswith("[IMPORT_BINDING_REQUIRED] "))
        self.assertEqual(json.loads(marker.split(" ", 1)[1]), {
            "attempt_id": str(generated_id), "account_uid": "123456789", "server": "os_usa",
        })

    def test_resume_ignores_change_equipment_switch_from_the_cli(self):
        operation = AsyncMock(return_value={"warnings": []})
        with patch.object(run_import.sys, "argv", [
            "run_import", "--resume-attempt", "saved-123", "--change-equipment",
        ]), patch.object(run_import, "import_run_lock", return_value=nullcontext()), \
                patch.object(run_import, "run_hoyolab_import", operation), redirect_stdout(io.StringIO()):
            self.assertEqual(run_import.main(), 0)
        operation.assert_awaited_once_with(
            change_equipment=False, images_only=False, attempt_id=None,
            resume_attempt="saved-123", adopt_legacy=False,
        )

    def test_cli_rejects_incompatible_attempt_modes_and_unscoped_adoption(self):
        for argv in (
            ["run_import", "--images-only", "--attempt-id", "new-123"],
            ["run_import", "--adopt-legacy"],
        ):
            with self.subTest(argv=argv), patch.object(run_import.sys, "argv", argv), \
                    patch.object(run_import, "run_hoyolab_import") as operation, \
                    redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    run_import.main()
            self.assertEqual(raised.exception.code, 2)
            operation.assert_not_called()

    def test_failed_core_does_not_emit_a_commit_receipt(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(run_import.sys, "argv", ["run_import", "--attempt-id", "failed-123"]), \
                patch.object(run_import, "import_run_lock", return_value=nullcontext()), \
                patch.object(run_import, "run_hoyolab_import",
                             new=AsyncMock(side_effect=run_import.HoYoLABImportError("core failed"))), \
                redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(run_import.main(), 2)
        self.assertNotIn("[IMPORT_COMMITTED]", output.getvalue())

    def test_read_only_recovery_lookups_leave_a_missing_database_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "not-created.db"
            self.assertIsNone(import_store.get_import_result(db_path, "attempt"))
            self.assertEqual(import_store.list_pending_import_attempts(db_path), [])
            self.assertIsNone(import_store.latest_committed_import(db_path))
            self.assertFalse(db_path.exists())


if __name__ == "__main__":
    unittest.main()
