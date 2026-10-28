"""Offscreen Theory controls; synthetic snapshots, no engine or account writes."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextCursor

from localization import tr
from run_workspace.gcsim.optimizer_go_selected import GcsimOptimizerGoSelectedRequest
from run_workspace.gcsim.optimizer_go_theory import GcsimOptimizerGoTheoryRequest
from run_workspace.gcsim.optimizer_go_theory_session import (
    GcsimOptimizerGoTheorySession, format_gcsim_optimizer_go_theory_session_result,
)
from tests.run_workspace.gcsim.test_optimizer_go_theory_session import _snapshot
from tests.run_workspace.gcsim.theory_output_fixture import (
    EXPECTED_GROUP_TUPLES, EXPECTED_PENDING_TUPLES,
    REQUEST_SHA, no_verified_snapshot, output_snapshot,
)
from ui.app_shell import AppShell
from ui.gcsim_browser.run_worker import GcsimBrowserSelectedOptimizerWorker
from ui.gcsim_browser.window import GcsimBrowserWorkspace


_APP = QApplication.instance() or QApplication([])


def _workspace() -> GcsimBrowserWorkspace:
    workspace = GcsimBrowserWorkspace()
    workspace._optimizer_mode = "theory"
    workspace.set_optimizer_busy(True)
    return workspace


class TheorySessionUiTests(unittest.TestCase):
    def test_first_result_shows_compact_summary_and_every_alias(self) -> None:
        workspace = _workspace()
        source = output_snapshot()
        workspace.update_optimizer_progress({"stage": "first_light", "sequence": 1, "theory_snapshot": source})
        self.assertTrue(workspace._optimizer_busy)
        self.assertFalse(workspace._optimizer_finalizing)
        self.assertTrue(workspace._optimizer_elapsed_clock.isValid())
        self.assertTrue(workspace.optimizer_finish_button.isEnabled())
        self.assertTrue(workspace.optimizer_theory_breadth_button.isEnabled())
        self.assertTrue(workspace.optimizer_theory_deep_button.isEnabled())
        text = workspace.optimizer_result.toPlainText()
        self.assertEqual(
            text,
            format_gcsim_optimizer_go_theory_session_result(
                {"success": True, "result": source}, include_rows=False,
            ).strip(),
        )
        self.assertNotIn("choice-", text)
        pages = workspace.optimizer_result_builds._pages
        self.assertEqual(
            tuple(entry.alias["tuple_key"] for entry in pages.index),
            EXPECTED_GROUP_TUPLES + EXPECTED_PENDING_TUPLES,
        )
        self.assertEqual(len(pages), len(EXPECTED_GROUP_TUPLES) + len(EXPECTED_PENDING_TUPLES))
        self.assertEqual(sum(len(row.artifacts) for row in pages[0].rows), 20)
        self.assertTrue(all(row.hypothetical and not row.can_save for row in pages[0].rows))
        self.assertIn(tr("gcsim.optimizer.theory_session.checkpoint"), workspace.optimizer_progress_label.text())

    def test_continuations_are_version_bound_and_never_chain(self) -> None:
        workspace = _workspace()
        requests = []
        workspace.optimizer_theory_continue_requested.connect(lambda action, version: requests.append((action, version)))
        workspace.update_optimizer_progress({"stage": "first_light", "theory_snapshot": _snapshot()})
        previous_text = workspace.optimizer_result.toPlainText()
        workspace.optimizer_theory_breadth_button.click()
        workspace.optimizer_theory_deep_button.click()
        self.assertEqual(requests, [("breadth", 1)])
        self.assertEqual(workspace.optimizer_result.toPlainText(), previous_text)
        self.assertFalse(workspace.optimizer_theory_breadth_button.isEnabled())
        self.assertFalse(workspace.optimizer_theory_deep_button.isEnabled())
        workspace.update_optimizer_progress({"stage": "breadth_light", "theory_snapshot": _snapshot(2, phase="breadth_light")})
        self.assertEqual(requests, [("breadth", 1)])
        self.assertFalse(workspace.optimizer_theory_breadth_button.isEnabled())
        self.assertTrue(workspace.optimizer_theory_deep_button.isEnabled())
        workspace.optimizer_theory_deep_button.click()
        self.assertEqual(requests, [("breadth", 1), ("deep", 2)])
        workspace.update_optimizer_progress({"stage": "deep_baseline", "theory_snapshot": _snapshot(3, phase="deep_baseline")})
        self.assertFalse(workspace.optimizer_theory_breadth_button.isEnabled())
        self.assertFalse(workspace.optimizer_theory_deep_button.isEnabled())

    def test_verification_progress_disables_only_continuation_controls(self) -> None:
        workspace = _workspace()
        snapshot = _snapshot(families=3)
        snapshot["verification"]["in_progress"] = True
        workspace.update_optimizer_progress({"stage": "first_light", "theory_snapshot": snapshot})
        self.assertFalse(workspace.optimizer_theory_breadth_button.isEnabled())
        self.assertFalse(workspace.optimizer_theory_deep_button.isEnabled())
        self.assertTrue(workspace.optimizer_finish_button.isEnabled())
        self.assertTrue(workspace.optimizer_cancel_button.isEnabled())
        self.assertEqual(
            workspace.optimizer_progress_label.text(),
            tr("gcsim.optimizer.theory_session.checking"),
        )

    def test_same_search_publication_keeps_pending_command_until_phase_acknowledges(self) -> None:
        workspace = _workspace()
        requests = []
        workspace.optimizer_theory_continue_requested.connect(lambda action, version: requests.append((action, version)))
        workspace.update_optimizer_progress({"stage": "first_light", "theory_snapshot": _snapshot(families=3)})
        workspace.optimizer_theory_breadth_button.click()
        self.assertEqual(requests, [("breadth", 1)])
        streamed = _snapshot(1, families=3, publication_version=2)
        streamed["verification"]["in_progress"] = True
        workspace.update_optimizer_progress({"stage": "first_light", "theory_snapshot": streamed})
        self.assertEqual(workspace._optimizer_theory_snapshot["publication_version"], 2)
        self.assertTrue(workspace._optimizer_theory_command_pending)
        self.assertFalse(workspace.optimizer_theory_deep_button.isEnabled())
        self.assertTrue(workspace.optimizer_finish_button.isEnabled())
        self.assertTrue(workspace.optimizer_cancel_button.isEnabled())

        acknowledged = _snapshot(2, phase="breadth_light", families=3, publication_version=3)
        workspace.update_optimizer_progress({"stage": "breadth_light", "theory_snapshot": acknowledged})
        self.assertFalse(workspace._optimizer_theory_command_pending)
        self.assertTrue(workspace.optimizer_theory_deep_button.isEnabled())

    def test_stale_and_mutated_input_cannot_change_displayed_snapshot(self) -> None:
        workspace = _workspace()
        source = _snapshot()
        workspace.update_optimizer_progress({"stage": "first_light", "theory_snapshot": source})
        expected = deepcopy(workspace._optimizer_theory_snapshot)
        text = workspace.optimizer_result.toPlainText()
        source["co_leaders"].clear()
        stale = _snapshot(2)
        stale["session_id"] = "unrelated-session"
        workspace.update_optimizer_progress({"stage": "breadth_light", "sequence": 999, "theory_snapshot": stale})
        workspace.update_optimizer_progress({"stage": "breadth_light", "theory_snapshot": _snapshot()})
        self.assertEqual(workspace._optimizer_theory_snapshot, expected)
        self.assertEqual(workspace.optimizer_result.toPlainText(), text)
        workspace.update_optimizer_progress({"stage": "breadth_light", "sequence": 2, "theory_snapshot": _snapshot(2, phase="breadth_light")})
        self.assertEqual(workspace._optimizer_theory_snapshot["snapshot_version"], 2)

    def test_newer_publication_cannot_rewind_search_phase(self) -> None:
        workspace = _workspace()
        first = _snapshot(1)
        workspace.update_optimizer_progress({"stage": "first_light", "theory_snapshot": first})
        breadth = _snapshot(2, phase="breadth_light", publication_version=2)
        workspace.update_optimizer_progress({"stage": "breadth_light", "theory_snapshot": breadth})
        displayed = deepcopy(workspace._optimizer_theory_snapshot)
        text = workspace.optimizer_result.toPlainText()

        workspace.update_optimizer_progress({
            "stage": "first_light",
            "theory_snapshot": _snapshot(3, phase="first_light", publication_version=3),
        })

        self.assertEqual(workspace._optimizer_theory_snapshot, displayed)
        self.assertEqual(workspace.optimizer_result.toPlainText(), text)

    def test_finish_and_cancel_disable_theory_resumes_immediately(self) -> None:
        for action in ("finish", "cancel"):
            workspace = _workspace()
            workspace.update_optimizer_progress({"stage": "first_light", "theory_snapshot": _snapshot()})
            before = workspace.optimizer_result.toPlainText()
            signal_calls = []
            signal = workspace.optimizer_finish_requested if action == "finish" else workspace.optimizer_cancel_requested
            signal.connect(lambda: signal_calls.append(True))
            button = workspace.optimizer_finish_button if action == "finish" else workspace.optimizer_cancel_button
            button.click()
            self.assertEqual(signal_calls, [True])
            self.assertFalse(workspace.optimizer_finish_button.isEnabled())
            self.assertFalse(workspace.optimizer_theory_breadth_button.isEnabled())
            self.assertFalse(workspace.optimizer_theory_deep_button.isEnabled())
            self.assertEqual(workspace.optimizer_result.toPlainText(), before)
            workspace.update_optimizer_progress({"stage": "breadth_light", "theory_snapshot": _snapshot(2, phase="breadth_light")})
            self.assertFalse(workspace.optimizer_theory_deep_button.isEnabled())
            if action == "cancel":
                self.assertEqual(workspace.optimizer_progress_label.text(), tr("gcsim.optimizer.theory_session.cancelling"))

    def test_worker_selects_v3_session_and_other_modes_do_not_resume(self) -> None:
        worker = GcsimBrowserSelectedOptimizerWorker(GcsimOptimizerGoTheoryRequest("unused", {}, 0, "rotation"))
        self.assertIsInstance(worker._session, GcsimOptimizerGoTheorySession)
        worker.request_finish()
        self.assertTrue(worker._session._finish_requested.is_set())
        selected = GcsimBrowserSelectedOptimizerWorker(GcsimOptimizerGoSelectedRequest("unused", {}, 0, "rotation"))
        self.assertFalse(selected.request_continuation("breadth", snapshot_version=1))
        selected.request_finish()
        self.assertTrue(selected._session._finish_requested.is_set())

    def test_shell_routes_continuation_and_theory_uses_lazy_pages_without_inventory(self) -> None:
        workspace = _workspace()
        workspace.update_optimizer_progress({"stage": "first_light", "theory_snapshot": _snapshot()})
        worker = MagicMock(spec=GcsimBrowserSelectedOptimizerWorker)
        worker.request_continuation.return_value = True
        shell = SimpleNamespace(
            _gcsim_browser_run_worker=worker,
            left_host=SimpleNamespace(gcsim_browser_workspace=workspace),
        )
        AppShell._on_gcsim_optimizer_theory_continue_requested(shell, "deep", 1)
        worker.request_continuation.assert_called_once_with("deep", snapshot_version=1)
        with patch("ui.app_shell.build_optimizer_result_pages") as build_pages, patch("ui.app_shell.list_all_artifacts") as inventory:
            terminal_snapshot = _snapshot(2)
            AppShell._on_gcsim_optimizer_selected_finished(shell, {"mode": "theory", "success": True, "status": "success", "result": terminal_snapshot})
        build_pages.assert_not_called()
        inventory.assert_not_called()
        self.assertIn(
            terminal_snapshot["co_leaders"][-1]["aliases"][0]["tuple_key"],
            {entry.alias["tuple_key"] for entry in workspace.optimizer_result_builds._pages.index},
        )


class TheoryOutputUiTests(unittest.TestCase):
    def _workspace(self) -> GcsimBrowserWorkspace:
        workspace = _workspace()
        self.addCleanup(workspace.deleteLater)
        self.addCleanup(workspace.close)
        return workspace

    def _terminal_handoff(self, workspace: GcsimBrowserWorkspace, payload: dict) -> None:
        shell = SimpleNamespace(left_host=SimpleNamespace(gcsim_browser_workspace=workspace))
        with patch("ui.app_shell.build_optimizer_result_pages") as pages, patch("ui.app_shell.list_all_artifacts") as inventory:
            AppShell._on_gcsim_optimizer_selected_finished(shell, payload)
        pages.assert_not_called()
        inventory.assert_not_called()

    def test_compact_text_scroll_keeps_all_aliases_and_full_underlying_snapshot(self) -> None:
        workspace = self._workspace()
        source = output_snapshot()
        expected = deepcopy(source)
        workspace.update_optimizer_progress({"stage": "first_light", "theory_snapshot": source})
        self.assertEqual(_APP.platformName(), "offscreen")
        self.assertFalse(workspace.isVisible())
        editor = workspace.optimizer_result
        self.assertEqual(editor.maximumBlockCount(), 0)
        text = editor.toPlainText()
        self.assertEqual(
            text,
            format_gcsim_optimizer_go_theory_session_result(
                {"success": True, "result": expected}, include_rows=False,
            ).strip(),
        )
        self.assertNotIn("choice-", text)
        pages = workspace.optimizer_result_builds._pages
        self.assertEqual(
            tuple(entry.alias["tuple_key"] for entry in pages.index),
            EXPECTED_GROUP_TUPLES + EXPECTED_PENDING_TUPLES,
        )
        self.assertEqual(len(workspace.optimizer_result_builds._rows), 4)
        editor.resize(400, 150)
        editor.moveCursor(QTextCursor.MoveOperation.End)
        editor.verticalScrollBar().setValue(editor.verticalScrollBar().maximum())
        editor.moveCursor(QTextCursor.MoveOperation.Start)
        editor.verticalScrollBar().setValue(0)
        self.assertEqual(editor.toPlainText(), text)
        self.assertIs(workspace.optimizer_result_builds._pages, pages)
        self.assertEqual(workspace.optimizer_result_builds.current_page_index, 0)
        self.assertEqual(workspace._optimizer_theory_snapshot, expected)
        source["co_leaders"][0]["aliases"][0]["packages"][0]["sets"].clear()
        source["co_leaders"][0]["allocations"][0]["substats"].clear()
        source["provenance"]["model"]["seeds"].clear()
        self.assertEqual(workspace._optimizer_theory_snapshot, expected)
        self.assertEqual(editor.toPlainText(), text)

    def test_no_verified_terminal_result_never_creates_recommendation_pages(self) -> None:
        workspace = self._workspace()
        snapshot = no_verified_snapshot()
        payload = {
            "mode": "theory", "success": False, "status": "no_verified_result",
            "error_code": "no_verified_result", "retained_snapshot": snapshot,
        }
        self._terminal_handoff(workspace, payload)
        terminal = workspace._optimizer_theory_terminal_payload
        self.assertFalse(terminal["success"])
        self.assertEqual(terminal["status"], "no_verified_result")
        self.assertNotIn("result", terminal)
        self.assertEqual(workspace._optimizer_theory_snapshot, snapshot)
        self.assertEqual(len(workspace.optimizer_result_builds._pages), 0)
        self.assertEqual(workspace.optimizer_result_builds._rows, {})
        self.assertTrue(workspace.optimizer_result.toPlainText().startswith(
            tr("gcsim.optimizer.theory_session.no_verified_result")
        ))
        self.assertEqual(workspace._optimizer_elapsed_terminal_stage, "finish_no_result")

    def test_outer_success_cannot_promote_an_empty_no_verified_snapshot(self) -> None:
        workspace = self._workspace()
        snapshot = no_verified_snapshot()
        self._terminal_handoff(workspace, {
            "mode": "theory", "success": True, "status": "success", "result": snapshot,
        })

        terminal = workspace._optimizer_theory_terminal_payload

        self.assertFalse(terminal["success"])
        self.assertEqual(terminal["status"], "no_verified_result")
        self.assertEqual(terminal["error_code"], "no_verified_result")
        self.assertNotIn("result", terminal)
        self.assertEqual(terminal["retained_snapshot"], snapshot)
        self.assertEqual(len(workspace.optimizer_result_builds._pages), 0)

    def test_finish_handoff_retains_terminal_version_and_freezes_earlier_snapshots(self) -> None:
        workspace = self._workspace()
        workspace.update_optimizer_progress({"stage": "first_light", "theory_snapshot": output_snapshot()})
        early = workspace._optimizer_theory_snapshot
        workspace.update_optimizer_progress({"stage": "breadth_light", "theory_snapshot": output_snapshot(2, phase="breadth_light")})
        breadth = workspace._optimizer_theory_snapshot
        workspace.optimizer_finish_button.click()
        terminal = output_snapshot(3, phase="breadth_light", finished_early=True)
        payload = {"mode": "theory", "success": True, "status": "success", "result": terminal}
        frozen_payload = deepcopy(payload)
        self._terminal_handoff(workspace, payload)
        self.assertEqual(payload, frozen_payload)
        self.assertEqual(workspace._optimizer_theory_snapshot, terminal)
        self.assertEqual(workspace._optimizer_theory_terminal_payload, payload)
        self.assertEqual(early, output_snapshot())
        self.assertEqual(breadth, output_snapshot(2, phase="breadth_light"))
        self.assertIn(tr("gcsim.optimizer.search_finished_by_user"), workspace.optimizer_result.toPlainText())
        self.assertEqual(workspace._optimizer_elapsed_terminal_stage, "completed")
        self.assertFalse(workspace.optimizer_theory_deep_button.isEnabled())
        payload["result"]["co_leaders"][0]["witness45"]["Upgrades"][0][0][0] = 999
        self.assertEqual(workspace._optimizer_theory_snapshot, frozen_payload["result"])
        text = workspace.optimizer_result.toPlainText()
        workspace.set_optimizer_busy(False)
        workspace.update_optimizer_progress({"stage": "first_light", "theory_snapshot": output_snapshot(4)})
        self.assertEqual(workspace._optimizer_theory_snapshot, frozen_payload["result"])
        self.assertEqual(workspace.optimizer_result.toPlainText(), text)
        workspace.set_optimizer_busy(True)
        self.assertIsNone(workspace._optimizer_theory_terminal_payload)
        self.assertIsNone(workspace._optimizer_theory_snapshot)

    def test_cancel_and_error_keep_complete_retained_snapshot_without_success(self) -> None:
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                workspace = self._workspace()
                workspace.update_optimizer_progress({"stage": "first_light", "theory_snapshot": output_snapshot()})
                early = workspace._optimizer_theory_snapshot
                if cancelled:
                    workspace.optimizer_cancel_button.click()
                retained = output_snapshot(2, phase="breadth_light")
                payload = {
                    "mode": "theory", "success": False,
                    "status": "cancelled" if cancelled else "success",
                    "error_code": "cancelled" if cancelled else "fixture_failure",
                    "error": "synthetic terminal failure", "retained_snapshot": retained,
                    "result": output_snapshot(3, phase="deep_baseline"),
                    "adapter_timings": {"terminal_status": "success"},
                }
                frozen = deepcopy(payload)
                self._terminal_handoff(workspace, payload)
                self.assertEqual(payload, frozen)
                terminal = workspace._optimizer_theory_terminal_payload
                self.assertEqual((terminal["success"], terminal["status"]), (False, "cancelled" if cancelled else "failed"))
                self.assertNotIn("result", terminal)
                self.assertEqual(terminal["retained_snapshot"], retained)
                self.assertEqual(workspace._optimizer_theory_snapshot, retained)
                self.assertEqual(early, output_snapshot())
                text = workspace.optimizer_result.toPlainText()
                self.assertTrue(text.startswith(tr("gcsim.optimizer.theory_cancelled" if cancelled else "gcsim.optimizer.theory_failed")))
                self.assertIn(tr("gcsim.optimizer.theory_session.retained"), text)
                self.assertNotIn(tr("gcsim.optimizer.theory_session.title"), text)
                self.assertEqual(workspace._optimizer_elapsed_terminal_stage, "cancelled" if cancelled else "failed")
                self.assertFalse(workspace.optimizer_theory_breadth_button.isEnabled())
                self.assertFalse(workspace.optimizer_theory_deep_button.isEnabled())
                retained["provenance"]["domain"]["wearers"].clear()
                workspace.update_optimizer_progress({"stage": "deep_baseline", "theory_snapshot": output_snapshot(4, phase="deep_baseline")})
                self.assertEqual(workspace._optimizer_theory_snapshot, frozen["retained_snapshot"])
                self.assertEqual(workspace.optimizer_result.toPlainText(), text)

    def test_stale_invalid_and_foreign_terminal_success_retain_previous_result_as_failure(self) -> None:
        for defect in ("stale", "foreign", "malformed"):
            with self.subTest(defect=defect):
                workspace = self._workspace()
                workspace.update_optimizer_progress({"stage": "first_light", "theory_snapshot": output_snapshot()})
                terminal = output_snapshot(1 if defect == "stale" else 2, phase="deep_baseline")
                if defect == "foreign":
                    terminal["request_sha256"] = "foreign-request"
                if defect == "malformed":
                    terminal["co_leaders"][0]["aliases"].clear()
                payload = {"mode": "theory", "success": True, "status": "success", "result": terminal}
                frozen = deepcopy(payload)
                self._terminal_handoff(workspace, payload)
                self.assertEqual(payload, frozen)
                self.assertEqual(workspace._optimizer_theory_snapshot, output_snapshot())
                normalized = workspace._optimizer_theory_terminal_payload
                self.assertEqual((normalized["success"], normalized["status"]), (False, "failed"))
                self.assertNotIn("result", normalized)
                self.assertEqual(normalized["retained_snapshot"], output_snapshot())
                self.assertEqual(workspace._optimizer_elapsed_terminal_stage, "failed")
                self.assertTrue(workspace.optimizer_result.toPlainText().startswith(tr("gcsim.optimizer.theory_failed")))

    def test_cancel_after_python_handoff_retains_new_terminal_rows_without_success(self) -> None:
        workspace = self._workspace()
        workspace.update_optimizer_progress({"stage": "first_light", "theory_snapshot": output_snapshot()})
        early = workspace._optimizer_theory_snapshot
        workspace.optimizer_cancel_button.click()
        terminal = output_snapshot(2, phase="deep_baseline")
        terminal["pending"][0]["aliases"][0]["tuple_key"] = "terminal-only-pending-choice"
        payload = {"mode": "theory", "success": True, "status": "success", "result": terminal}
        frozen = deepcopy(payload)
        self._terminal_handoff(workspace, payload)
        self.assertEqual(payload, frozen)
        normalized = workspace._optimizer_theory_terminal_payload
        self.assertEqual((normalized["success"], normalized["status"]), (False, "cancelled"))
        self.assertNotIn("result", normalized)
        self.assertEqual(normalized["retained_snapshot"], terminal)
        self.assertEqual(workspace._optimizer_theory_snapshot, terminal)
        self.assertEqual(early, output_snapshot())
        self.assertEqual(workspace._optimizer_elapsed_terminal_stage, "cancelled")
        text = workspace.optimizer_result.toPlainText()
        self.assertIn(
            "terminal-only-pending-choice",
            {entry.alias["tuple_key"] for entry in workspace.optimizer_result_builds._pages.index},
        )
        self.assertTrue(text.startswith(tr("gcsim.optimizer.theory_cancelled")))
        self.assertIn(tr("gcsim.optimizer.theory_session.retained"), text)
        self.assertNotIn(tr("gcsim.optimizer.theory_session.title"), text)

    def test_same_version_retained_payload_cannot_rewrite_an_immutable_snapshot(self) -> None:
        workspace = self._workspace()
        previous = output_snapshot(2, phase="breadth_light")
        workspace.update_optimizer_progress({"stage": "breadth_light", "theory_snapshot": previous})
        retained = deepcopy(previous)
        retained["provenance"]["model"]["seeds"] = [999]
        self._terminal_handoff(workspace, {
            "mode": "theory", "success": False, "status": "failed", "error_code": "fixture_error",
            "retained_snapshot": retained,
        })
        self.assertEqual(workspace._optimizer_theory_snapshot, previous)
        self.assertEqual(workspace._optimizer_theory_terminal_payload["retained_snapshot"], previous)

    def test_worker_signal_seam_preserves_complete_progress_and_terminal_output(self) -> None:
        workspace = self._workspace()
        worker = GcsimBrowserSelectedOptimizerWorker(GcsimOptimizerGoTheoryRequest("unused", {}, 0, "rotation"))
        shell = SimpleNamespace(left_host=SimpleNamespace(gcsim_browser_workspace=workspace))
        progress = []
        finished = []
        worker.progress.connect(progress.append)
        worker.progress.connect(workspace.update_optimizer_progress)
        worker.finished.connect(finished.append)
        worker.finished.connect(lambda value: AppShell._on_gcsim_optimizer_selected_finished(shell, value))

        def synthetic_run():
            worker._session._expected_request_sha256 = REQUEST_SHA
            worker._session._consume_progress({"request_sha256": REQUEST_SHA, "stage": "first_light", "theory_snapshot": output_snapshot()})
            worker._session._consume_progress({"request_sha256": REQUEST_SHA, "stage": "breadth_light", "theory_snapshot": output_snapshot(2, phase="breadth_light")})
            return {"success": True, "status": "success", "result": output_snapshot(3, phase="deep_baseline")}

        with patch.object(worker._session, "run", side_effect=synthetic_run), patch("ui.app_shell.build_optimizer_result_pages") as pages, patch("ui.app_shell.list_all_artifacts") as inventory:
            worker.run()
        self.assertEqual([event["theory_snapshot"]["snapshot_version"] for event in progress], [1, 2])
        self.assertEqual(progress[0]["theory_snapshot"], output_snapshot())
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0]["mode"], "theory")
        self.assertEqual(workspace._optimizer_theory_snapshot, output_snapshot(3, phase="deep_baseline"))
        theory_pages = workspace.optimizer_result_builds._pages
        self.assertEqual(
            tuple(entry.alias["tuple_key"] for entry in theory_pages.index),
            EXPECTED_GROUP_TUPLES + EXPECTED_PENDING_TUPLES,
        )
        self.assertEqual(sum(len(row.artifacts) for row in theory_pages[0].rows), 20)
        pages.assert_not_called()
        inventory.assert_not_called()

    @unittest.skipUnless(os.environ.get("GTT_THEORY_OUTPUT_EXPORT"), "Native public output export not supplied.")
    def test_managed_native_output_uses_the_same_compact_summary_surface(self) -> None:
        source = json.loads(Path(os.environ["GTT_THEORY_OUTPUT_EXPORT"]).read_text(encoding="utf-8"))
        workspace = self._workspace()
        workspace.update_optimizer_progress({"stage": source["phase"], "theory_snapshot": source})
        self.assertEqual(workspace._optimizer_theory_snapshot, source)
        self.assertEqual(
            workspace.optimizer_result.toPlainText(),
            format_gcsim_optimizer_go_theory_session_result(
                {"success": True, "result": source}, include_rows=False,
            ).strip(),
        )
        self.assertGreater(len(source["co_leaders"]), 5)
        self.assertEqual(workspace.optimizer_result.maximumBlockCount(), 0)
        self.assertFalse(workspace.isVisible())


if __name__ == "__main__":
    unittest.main()
