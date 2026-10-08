"""Real button -> worker -> preparation -> native search -> selected GCSIM gate.

Run explicitly with GTT_OPTIMIZER_BUTTON_GATE=1 in managed scratch. No worker,
session, preparation, Popen or result is mocked. The public SQLite fixture and
output roots are isolated; ordinary suite wiring tests remain cheap.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from run_workspace.gcsim.engine_store import GcsimEngineStore
from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
from run_workspace.gcsim.optimizer_go_requests import DEFAULT_OPTIMIZER_BINARY
from run_workspace.gcsim.settings import GcsimOptimizerSettings
from ui.app_shell import AppShell
from ui.gcsim_browser.window import GcsimBrowserWorkspace
from tests.support.optimizer_button_baseline import assert_button_baseline


_APP = QApplication.instance() or QApplication([])


class ButtonHarness(QWidget):
    """Actual AppShell launch/finish methods with a disposable data controller."""
    def __init__(self, db_path, team, paths):
        super().__init__()
        self.paths = paths
        self.payloads = []
        self.controller = SimpleNamespace(
            equipment_db_path=db_path,
            gcsim_boosted_energy_enabled=True,
            gcsim_browser_selected_team=lambda _index: team,
        )
        self.workspace = GcsimBrowserWorkspace(self)
        self.left_host = SimpleNamespace(gcsim_browser_workspace=self.workspace)
        self._gcsim_browser_run_worker = None
        self._gcsim_browser_run_thread = None
        self._gcsim_browser_run_rotation_text = ""
        self._gcsim_optimizer_selected_team = None
        self.workspace.optimizer_selected_requested.connect(
            lambda index, rotation: AppShell._on_gcsim_optimizer_requested(
                self, index, rotation, mode="selected"))
        self.workspace.optimizer_all_sets_requested.connect(
            lambda index, rotation: AppShell._on_gcsim_optimizer_requested(
                self, index, rotation, mode="all_sets"))
        self.workspace.set_optimizer_all_sets_available(True)

    def _gcsim_optimizer_runtime_paths(self):
        return self.paths

    def _on_gcsim_optimizer_selected_finished(self, payload):
        self.payloads.append(payload)
        AppShell._on_gcsim_optimizer_selected_finished(self, payload)

    def _clear_gcsim_run_worker_refs(self):
        AppShell._clear_gcsim_run_worker_refs(self)

    def click_and_wait(self, mode, rotation, fast_mode):
        self.payloads.clear()
        self.workspace.rotation_editor.setPlainText(rotation)
        button = (self.workspace.optimizer_selected_button if mode == "selected"
                  else self.workspace.optimizer_all_sets_button)
        if not button.isEnabled():
            raise AssertionError(f"{mode} button is disabled")
        # Only settings input is fixed; all execution and output are real.
        with patch("ui.app_shell.effective_gcsim_optimizer_settings",
                   return_value=GcsimOptimizerSettings(1, 1, fast_mode, False)):
            started = time.monotonic()
            button.click()
            deadline = time.monotonic() + 120
            while not self.payloads or self._gcsim_browser_run_thread is not None:
                _APP.processEvents()
                if time.monotonic() >= deadline:
                    worker, thread = self._gcsim_browser_run_worker, self._gcsim_browser_run_thread
                    if worker is not None:
                        worker.cancel()
                    if thread is not None:
                        thread.quit()
                        thread.wait(15_000)
                    raise AssertionError(f"{mode} button/backend exceeded the fixture watchdog")
                time.sleep(0.005)
        self.last_elapsed_ms = round((time.monotonic() - started) * 1000)
        if len(self.payloads) != 1:
            raise AssertionError(f"{mode} returned {len(self.payloads)} terminal results")
        return self.payloads[0]


class OptimizerButtonHarnessTests(unittest.TestCase):
    def test_completion_uses_application_unlocking_callback(self):
        harness = ButtonHarness(None, {}, {})
        try:
            harness.workspace.set_optimizer_busy(True)
            harness._gcsim_browser_run_rotation_text = "temporary rotation"
            harness._clear_gcsim_run_worker_refs()
            self.assertTrue(harness.workspace.optimizer_selected_button.isEnabled())
            self.assertTrue(harness.workspace.optimizer_all_sets_button.isEnabled())
            self.assertFalse(harness.workspace._optimizer_busy)
            self.assertEqual(harness._gcsim_browser_run_rotation_text, "")
        finally:
            harness.close()
            harness.deleteLater()
            _APP.processEvents()


@unittest.skipUnless(os.environ.get("GTT_OPTIMIZER_BUTTON_GATE") == "1",
                     "explicit managed real-backend button gate")
class OptimizerButtonBackendTests(unittest.TestCase):
    def test_ready_modes_launch_and_match_frozen_fixture(self):
        from tests.support.optimizer_button_fixture import create_button_smoke_fixture
        from tools.managed_optimizer_experiment import owned_job

        job = owned_job()
        fixture_root = job / "button-fixture"
        fixture_root.mkdir()
        db_path, team, rotation, fixture_sha = create_button_smoke_fixture(fixture_root)
        store_path = os.environ["GTT_OPTIMIZER_BUTTON_ENGINE_STORE"]
        installed = GcsimEngineStore(store_path).get_active_engine()
        self.assertIsNotNone(installed, "selected engine is required; no fallback")
        engine_context = load_active_gcsim_optimizer_engine_context(store_dir=store_path)
        binary = Path(os.environ.get("GTT_OPTIMIZER_BUTTON_TEST_BINARY", str(DEFAULT_OPTIMIZER_BINARY)))
        self.assertTrue(binary.is_file(), "the chosen native consumer must exist")
        deep = job / ("profile-layout-" + "a" * 70) / ("saved-runs-" + "b" * 70)
        deep.mkdir(parents=True)
        paths = {"run_root": str(deep), "engine_store_dir": store_path,
                 "optimizer_binary_path": str(binary)}
        harness = ButtonHarness(db_path, team, paths)
        measurements = []
        selected_case = os.environ.get("GTT_OPTIMIZER_BUTTON_CASE", "")
        known_cases = {mode + suffix for mode in ("selected", "all_sets")
                       for suffix in ("_fast", "_verified")}
        self.assertTrue(not selected_case or selected_case in known_cases, "unknown button test case")
        try:
            for fast in (True, False):
                for mode in ("selected", "all_sets"):
                    case = mode + ("_fast" if fast else "_verified")
                    if selected_case and selected_case != case:
                        continue
                    with self.subTest(mode=mode, fast=fast):
                        payload = harness.click_and_wait(mode, rotation, fast)
                        self.assertTrue(payload.get("success"), payload.get("error"))
                        self.assertEqual(payload.get("status"), "success")
                        self.assertEqual(payload.get("mode"), mode)
                        result = payload["result"]
                        self.assertEqual(result.get("status"), "success")
                        winner = result["winner"]
                        ids = [row["artifact_id"] for row in winner]
                        self.assertEqual(len(ids), 20)
                        self.assertEqual(len(set(ids)), 20)
                        self.assertTrue(set(ids).issubset(set(range(1, 21))))
                        estimate = Decimal(result["formula_dps"])
                        self.assertTrue(estimate.is_finite() and estimate > 0)
                        measurement = result.get("measured")
                        if not fast:
                            self.assertIsNotNone(measurement)
                            self.assertGreater(Decimal(measurement["dps"]), 0)
                        request = json.loads((Path(payload["run_dir"]) / "request.json").read_bytes())
                        self.assertEqual(request["engine"]["artifact_sha256"], engine_context.artifact_sha256)
                        self.assertEqual(request["context"]["rotation"]["text"], rotation)
                        self.assertEqual(request["result_options"]["fast_mode"], fast)
                        self.assertEqual(len(request["artifacts"]), 20)
                        self.assertGreater(len(str(Path(payload["run_dir"]))), 260)
                        self.assertTrue(harness.workspace.optimizer_result.toPlainText())
                        pages = harness.workspace.optimizer_result_builds._pages
                        self.assertTrue(pages, "successful output must include build cards")
                        self.assertEqual(len(pages[0].rows), 4)
                        self.assertEqual(sum(len(row.slots) for row in pages[0].rows), 20)
                        observation = {"mode": mode, "fast_mode": fast,
                            "formula_dps": result["formula_dps"], "measured": measurement,
                            "winner_sha256": hashlib.sha256(json.dumps(winner, sort_keys=True).encode()).hexdigest(),
                            "engine": {**request["engine"], "engine_id": engine_context.engine_id},
                            "fixture_sha256": fixture_sha, "elapsed_ms": harness.last_elapsed_ms}
                        if os.environ.get("GTT_OPTIMIZER_BUTTON_BASELINE_CANDIDATE") != "1":
                            baseline_path = Path(__file__).resolve().parents[2] / "fixtures/gcsim_optimizer_go_v1/button_smoke_baseline_v1.json"
                            assert_button_baseline(observation, json.loads(baseline_path.read_bytes()))
                        measurements.append(observation)
        finally:
            harness.close()
            harness.deleteLater()
            _APP.processEvents()
        # The managed runner publishes bounded evidence only after all assertions.
        (job / "button-gate-measurements.json").write_text(
            json.dumps(measurements, sort_keys=True, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
