"""Headless dispatch checks with fake execution; real engine smoke is user-owned."""

from datetime import date
from pathlib import Path
from threading import Event
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtTest import QTest

from run_workspace.abyss.source_data import AbyssFloorSourceData, AbyssPeriod
from tests.ui.pvp_browser._period_fixture import PERIOD_START_DATE, PERIOD_END_DATE, PERIOD_ID
from tests.ui.pvp_browser.test_pvp_artifacts import PvpBuildFixture
from tests.ui.gcsim_browser.test_gcsim_browser_run_worker import _chamber_payload


def _successful_payload(request, *, batch=False):
    def chamber_payload(chamber):
        payload = _chamber_payload(chamber, success=True, status="run_passed")
        payload["selection"].update(team_index=request.team_index, side=request.side,
                                    period_start=request.abyss_period_start, floor=request.abyss_floor)
        return payload
    if batch:
        return {"batch_status": "passed", "success": True,
                "chambers": [chamber_payload(chamber) for chamber in request.chambers]}
    return chamber_payload(request.chamber)


class PvpGcsimExecutionUiTest(PvpBuildFixture):
    def setUp(self):
        super().setUp()
        self.source = AbyssFloorSourceData(12, AbyssPeriod(PERIOD_START_DATE, PERIOD_END_DATE, "fixture"), {}, (), ())
        self.workspace._abyss_source_data_provider = lambda: self.source
        self.workspace._abyss_cache_dir = self.root / "fixture-abyss-cache"
        self.engine = "fixture-engine"
        self.engine_patch = patch("ui.pvp_browser.build_flow._selected_gcsim_engine_id", side_effect=lambda: self.engine)
        self.binding_patch = patch("ui.gcsim_browser.run_worker._active_run_binding", return_value=SimpleNamespace(
            engine_id=self.engine, artifact_registry="fixture-artifact.go", enemy_registry="fixture-enemy.go"))
        self.engine_patch.start()
        self.binding_patch.start()
        self.addCleanup(self.engine_patch.stop)
        self.addCleanup(self.binding_patch.stop)

    def wait_for_job(self, seat_context):
        deadline = monotonic() + 3
        while seat_context.gcsim_execution.busy and monotonic() < deadline:
            QTest.qWait(5)
        self.assertFalse(seat_context.gcsim_execution.busy)
        seat_context._poll_gcsim_run()

    def test_each_seat_routes_db_team_half_batch_and_result_without_changing_active_seat(self):
        calls = []

        def execute(request, **kwargs):
            calls.append((request, kwargs))
            Path(request.run_root, "fixture-output.txt").write_text("fixture", encoding="utf-8")
            return _successful_payload(request, batch=hasattr(request, "chambers"))

        with patch("ui.gcsim_browser.run_worker.run_gcsim_browser_selected_chamber", side_effect=execute), \
             patch("ui.gcsim_browser.run_worker.run_gcsim_browser_three_chambers", side_effect=execute):
            first = self.context.seat("player_1")
            self.workspace.open_build_gcsim("player_1")
            self.assertTrue(first.gcsim_browser.run_selected_button.isEnabled())
            first.gcsim_browser.run_selected_requested.emit(0, 2, "first rotation")
            self.wait_for_job(first)
            second = self.context.seat("player_2")
            self.workspace.open_build_gcsim("player_2")
            second.controller.selected_team_index = 1
            second.controller.selected_slot_index = 0
            second.add_or_replace_character(next(asset for asset in second.character_assets
                if str(asset["metadata"]["character"]["id"]) == second.picked_character_ids[1]))
            second.gcsim_browser.run_all_requested.emit(1, "second rotation")
            self.context.set_active_seat("player_1")
            self.wait_for_job(second)
            self.assertEqual(self.context.active_seat, "player_1")
            first_request, second_request = (call[0] for call in calls)
            self.assertEqual(first_request.db_path, str(first.db_path))
            self.assertEqual(second_request.db_path, str(second.db_path))
            self.assertEqual((first_request.team_index, first_request.side, first_request.chamber), (0, 1, 2))
            self.assertEqual((second_request.team_index, second_request.side, second_request.chambers), (1, 2, (1, 2, 3)))
            self.assertFalse(first_request.allow_account_equipment_fallback)
            self.assertFalse(second_request.allow_account_equipment_fallback)
            self.assertEqual(first_request.abyss_cache_dir, str(self.workspace._abyss_cache_dir))
            self.assertEqual(first_request.abyss_period_start, PERIOD_START_DATE)
            self.assertEqual(first_request.abyss_period_id, PERIOD_ID)
            self.assertEqual(second_request.expected_engine_id, self.engine)
            self.assertNotEqual(first_request.run_root, second_request.run_root)
            self.assertNotEqual(first_request.selected_team, second_request.selected_team)
            self.assertEqual(len(first.controller.session.state.abyss.gcsim_chamber_results), 1)
            self.assertEqual(len(second.controller.session.state.abyss.gcsim_chamber_results), 3)
            self.assertTrue(callable(calls[0][1]["artifact_runner"]))
        roots = [Path(request.run_root) for request, _ in calls]
        self.workspace.clear_active_draft()
        self.assertTrue(all(not root.exists() for root in roots))
        self.assert_sources_unchanged()

    def test_rotation_change_cancels_and_discards_late_success_for_only_its_seat(self):
        started, finish = Event(), Event()
        self.addCleanup(finish.set)

        def execute(request, **kwargs):
            started.set()
            finish.wait(2)
            return _successful_payload(request)

        with patch("ui.gcsim_browser.run_worker.run_gcsim_browser_selected_chamber", side_effect=execute):
            self.workspace.open_build_gcsim("player_1")
            first = self.context.seat("player_1")
            self.workspace.open_build_gcsim("player_2")
            second = self.context.seat("player_2")
            second.gcsim_browser.set_prepare_result_text("second unchanged")
            first.gcsim_browser.run_selected_requested.emit(0, 1, "old rotation")
            self.assertTrue(started.wait(2))
            root = first.gcsim_execution.output_root
            first.gcsim_browser.rotation_editor.setPlainText("new rotation")
            finish.set()
            self.wait_for_job(first)
            self.assertFalse(first.controller.session.state.abyss.gcsim_chamber_results)
            self.assertFalse(root.exists())
            self.assertEqual(second.gcsim_browser._last_result_text, "second unchanged")
        self.assert_sources_unchanged()

    def test_clear_and_profile_replacement_wait_for_pending_reader_then_clean_source(self):
        started, finish = Event(), Event()
        self.addCleanup(finish.set)

        def execute(request, **kwargs):
            started.set()
            finish.wait(2)
            self.assertTrue(Path(request.db_path).is_file())
            return _successful_payload(request)

        with patch("ui.gcsim_browser.run_worker.run_gcsim_browser_selected_chamber", side_effect=execute):
            self.workspace.open_build_gcsim("player_2")
            second = self.context.seat("player_2")
            provider = second.provider
            imported_root = provider.profile.db_path.parent
            second.gcsim_browser.run_selected_requested.emit(0, 1, "old rotation")
            self.assertTrue(started.wait(2))
            output = second.gcsim_execution.output_root
            self.workspace.clear_active_draft()
            self.assertTrue(self.workspace.import_profile_for_seat("player_2", provider.profile.path))
            self.assertTrue(provider.profile._closed)
            self.assertTrue(imported_root.is_dir())
            self.assert_sources_unchanged()
            finish.set()
            second.gcsim_execution.wait_closed(3)
            self.assertFalse(second.gcsim_execution.busy)
            self.assertFalse(imported_root.exists())
            self.assertFalse(output.exists())
            self.assertIsNone(self.workspace.build_flow_context)
        for path, original in self.source_bytes.items():
            if path.parent != imported_root:
                self.assertEqual(path.read_bytes(), original)
        self.assertEqual({path.name: path.read_bytes() for path in self.local_decks.iterdir()}, self.deck_bytes)

    def test_changed_authority_or_engine_discards_result_and_missing_cache_prevents_dispatch(self):
        first = self.context.seat("player_1")
        self.workspace.open_build_gcsim("player_1")
        with patch("ui.gcsim_browser.run_worker.run_gcsim_browser_selected_chamber",
                   side_effect=lambda request, **_: _successful_payload(request)) as execute:
            first.gcsim_browser.run_selected_requested.emit(0, 1, "rotation")
            self.engine = "changed-engine"
            self.wait_for_job(first)
            self.assertFalse(first.controller.session.state.abyss.gcsim_chamber_results)
            self.assertIn("GCSIM", first.gcsim_browser._last_result_text)
            self.engine = "fixture-engine"
            first.gcsim_browser.run_selected_requested.emit(0, 1, "rotation")
            self.workspace._today_provider = lambda: date(2026, 11, 1)
            self.wait_for_job(first)
            self.assertFalse(first.controller.session.state.abyss.gcsim_chamber_results)
            self.workspace._today_provider = lambda: date(2026, 10, 4)
            self.workspace._abyss_source_data_provider = lambda: None
            first.gcsim_browser.run_selected_requested.emit(0, 1, "rotation")
            self.assertEqual(execute.call_count, 2)
            first.sync_gcsim_browser_context()
            self.assertFalse(first.gcsim_browser.run_selected_button.isEnabled())
        self.assert_sources_unchanged()

    def test_completion_compares_full_period_and_cleanup_attempts_both_adapters(self):
        first = self.context.seat("player_1")
        self.workspace.open_build_gcsim("player_1")
        with patch("ui.gcsim_browser.run_worker.run_gcsim_browser_selected_chamber",
                   side_effect=lambda request, **_: _successful_payload(request)):
            first.gcsim_browser.run_selected_requested.emit(0, 1, "rotation")
            source = self.workspace.gcsim_run_source()
            first.run_source_provider = lambda: {**source, "abyss_period_id": "2026-10-01/2026-11-02"}
            self.wait_for_job(first)
            self.assertFalse(first.controller.session.state.abyss.gcsim_chamber_results)
            self.assertIsNone(first.gcsim_execution.output_root)
        first.gcsim_execution.close()
        preparation = Mock()
        first.gcsim_preparation = preparation
        first.gcsim_execution = Mock(close=Mock(side_effect=OSError("fixture cleanup failure")))
        try:
            with self.assertRaisesRegex(OSError, "fixture cleanup failure"):
                first.close_gcsim_preparation()
            preparation.close.assert_called_once()
            self.assertIsNone(first.gcsim_preparation)
            second_preparation = Mock()
            self.context.seat("player_2").gcsim_preparation = second_preparation
            with self.assertRaisesRegex(OSError, "fixture cleanup failure"):
                self.workspace._dispose_build_flow_context()
            second_preparation.close.assert_called_once()
            self.assertIsNone(self.workspace.build_flow_context)
            self.assertEqual(self.workspace.draft_workspace.build_browser_stack.count(), 0)
        finally:
            first.gcsim_execution = None
        self.assert_sources_unchanged()
