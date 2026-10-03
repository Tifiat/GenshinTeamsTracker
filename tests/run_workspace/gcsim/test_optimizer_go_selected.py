from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from run_workspace.gcsim.optimizer_go_selected import (
    DEFAULT_OPTIMIZER_BINARY,
    DEFAULT_PRODUCT_TIMEOUT_MS,
    GcsimOptimizerGoSelectedRequest,
    GcsimOptimizerGoSelectedSession,
    GcsimOptimizerGoSelectedError,
    _bound_artifact_registry_source,
    _optimizer_result_options,
    _prepare_inputs,
    _TARGET_RE,
    _progress_row,
    _remaining_ms,
    _request_artifacts,
    _wait_process,
    format_gcsim_optimizer_go_selected_result,
)


class GcsimOptimizerGoSelectedTests(unittest.TestCase):
    def test_default_consumer_path_and_override_reach_preflight_and_process(self) -> None:
        from run_workspace.gcsim.optimizer_go_selected import PROJECT_ROOT

        default = GcsimOptimizerGoSelectedRequest("unused", {}, 0, "")
        self.assertEqual(Path(default.optimizer_binary_path).resolve(), DEFAULT_OPTIMIZER_BINARY.resolve())
        self.assertEqual(DEFAULT_OPTIMIZER_BINARY.resolve(),
                         (PROJECT_ROOT / "native/gcsim_optimizer/gtt-optimizer.exe").resolve())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "candidate.exe"
            binary.write_bytes(b"mock candidate")
            request = GcsimOptimizerGoSelectedRequest(
                "unused", {}, 0, "", optimizer_binary_path=str(binary))
            session = GcsimOptimizerGoSelectedSession(request)
            with patch("run_workspace.gcsim.optimizer_go_session.subprocess.Popen",
                       side_effect=RuntimeError("stop before launch")) as popen:
                with self.assertRaisesRegex(RuntimeError, "stop before launch"):
                    session._validate_optimizer_request(run_dir=root, started=time.monotonic())
                self.assertEqual(Path(popen.call_args.args[0][0]).resolve(), binary.resolve())
                self.assertEqual(popen.call_args.args[0][1], "validate-request")
                with self.assertRaisesRegex(RuntimeError, "stop before launch"):
                    session._run_go_optimizer(prepared={"request_sha256": "sha"}, compact={},
                                              run_dir=root, started=time.monotonic())
                self.assertEqual(Path(popen.call_args.args[0][0]).resolve(), binary.resolve())
                self.assertEqual(popen.call_args.args[0][1], "verify-fgbs")

    def test_selected_result_options_defaults_and_maximum_panel(self) -> None:
        default_request = GcsimOptimizerGoSelectedRequest(
            db_path="unused.db",
            selected_team={},
            team_index=0,
            rotation_shell_text="",
        )
        self.assertEqual(
            _optimizer_result_options(default_request, theory_mode=False),
            {"set_group_limit": 3, "builds_per_group": 2, "fast_mode": False},
        )

        maximum_request = GcsimOptimizerGoSelectedRequest(
            db_path="unused.db",
            selected_team={},
            team_index=0,
            rotation_shell_text="",
            set_group_limit=10,
            builds_per_group=101,
            expanded_limits=True,
            fast_mode=True,
        )
        self.assertEqual(
            _optimizer_result_options(maximum_request, theory_mode=False),
            {"set_group_limit": 10, "builds_per_group": 101,
             "fast_mode": True, "expanded_limits": True},
        )

        normal_maximum = GcsimOptimizerGoSelectedRequest(
            db_path="unused.db", selected_team={}, team_index=0,
            rotation_shell_text="", set_group_limit=5, builds_per_group=11,
        )
        self.assertEqual(
            _optimizer_result_options(normal_maximum, theory_mode=False)["builds_per_group"],
            11,
        )

    def test_selected_result_options_reject_invalid_types_and_bounds(self) -> None:
        for field, value in (
            ("set_group_limit", True),
            ("set_group_limit", 0),
            ("set_group_limit", 8),
            ("set_group_limit", 51),
            ("set_group_limit", 3.0),
            ("builds_per_group", False),
            ("builds_per_group", 0),
            ("builds_per_group", 12),
            ("builds_per_group", 51),
            ("builds_per_group", "2"),
            ("expanded_limits", 1),
            ("expanded_limits", None),
            ("fast_mode", 1),
            ("fast_mode", None),
        ):
            with self.subTest(field=field, value=value):
                kwargs = {"db_path": "unused.db", "selected_team": {}, "team_index": 0,
                          "rotation_shell_text": "", field: value}
                request = GcsimOptimizerGoSelectedRequest(**kwargs)
                with self.assertRaises(GcsimOptimizerGoSelectedError) as raised:
                    _prepare_inputs(request, Path("unused-run-dir"))
                self.assertEqual(raised.exception.code, "result_options_invalid")

        expanded_invalid = GcsimOptimizerGoSelectedRequest(
            db_path="unused.db", selected_team={}, team_index=0,
            rotation_shell_text="", expanded_limits=True, set_group_limit=0,
        )
        with self.assertRaises(GcsimOptimizerGoSelectedError) as raised:
            _optimizer_result_options(expanded_invalid, theory_mode=False)
        self.assertEqual(raised.exception.code, "result_options_invalid")

    def test_unlimited_timeout_is_zero_and_negative_timeout_is_invalid(self) -> None:
        self.assertEqual(DEFAULT_PRODUCT_TIMEOUT_MS, 0)
        self.assertEqual(_remaining_ms(time.monotonic(), 0), 0)
        with self.assertRaises(GcsimOptimizerGoSelectedError) as raised:
            _remaining_ms(time.monotonic(), -1)
        self.assertEqual(raised.exception.code, "timeout_invalid")

        request = GcsimOptimizerGoSelectedRequest(
            db_path="unused.db", selected_team={}, team_index=0,
            rotation_shell_text="", product_timeout_ms=-1,
        )
        with self.assertRaises(GcsimOptimizerGoSelectedError) as raised:
            _prepare_inputs(request, Path("unused-run-dir"))
        self.assertEqual(raised.exception.code, "timeout_invalid")

    def test_zero_timeout_waits_without_deadline(self) -> None:
        class CompletesAfterOnePoll:
            polls = 0

            def poll(self):
                self.polls += 1
                return None if self.polls == 1 else 0

        process = CompletesAfterOnePoll()
        with patch("run_workspace.gcsim.optimizer_go_session.time.sleep") as sleep, patch(
            "run_workspace.gcsim.optimizer_go_session._stop_process"
        ) as stop:
            _wait_process(process, cancel_event=threading.Event(), timeout_ms=0)
        sleep.assert_called_once_with(0.05)
        stop.assert_not_called()

    def test_request_finish_is_separate_from_cancel_and_persists_before_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            request = GcsimOptimizerGoSelectedRequest(
                db_path="unused.db", selected_team={}, team_index=0,
                rotation_shell_text="", run_root=temporary,
            )
            session = GcsimOptimizerGoSelectedSession(request)
            session.request_finish()
            self.assertTrue(session._finish_requested.is_set())
            self.assertFalse(session._cancelled.is_set())

            prepared = {"request_sha256": "request-sha", "request": {}}
            result = {"status": "success", "request_sha256": "request-sha"}

            def finish_during_prepare(*_args, **_kwargs):
                session.request_finish()
                return prepared

            with (
                patch("run_workspace.gcsim.optimizer_go_session.prepare_optimizer_inputs", side_effect=finish_during_prepare),
                patch.object(session, "_validate_optimizer_request"),
                patch.object(session, "_prepare_formula_inputs", return_value={}),
                patch.object(session, "_run_go_optimizer", return_value=result),
                patch("run_workspace.gcsim.optimizer_go_session.prune_go_optimizer_runs_best_effort", return_value={"status": "ok"}),
            ):
                payload = session.run()

            self.assertTrue((Path(payload["run_dir"]) / "finish-requested").is_file())
            self.assertTrue(payload["adapter_timings"]["finish_requested"])
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["error_code"], "finish_no_result")

    def test_active_finish_request_is_idempotent_and_does_not_stop_child(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            request = GcsimOptimizerGoSelectedRequest(
                db_path="unused.db", selected_team={}, team_index=0,
                rotation_shell_text="", run_root=temporary,
            )
            session = GcsimOptimizerGoSelectedSession(request)
            run_dir = Path(temporary) / "active-run"
            run_dir.mkdir()
            session._run_dir = run_dir

            class RunningProcess:
                def poll(self):
                    return None

            process = RunningProcess()
            session._register_process(process)
            with patch("run_workspace.gcsim.optimizer_go_session._stop_process") as stop:
                session.request_finish()
                session.request_finish()
            stop.assert_not_called()
            self.assertTrue((run_dir / "finish-requested").is_file())
            self.assertFalse(session._cancelled.is_set())

    def test_finish_after_completed_run_does_not_touch_result_or_create_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            request = GcsimOptimizerGoSelectedRequest("unused", {}, 0, "", run_root=temporary)
            session = GcsimOptimizerGoSelectedSession(request)
            prepared = {"request_sha256": "request-sha", "request": {}}
            with (
                patch("run_workspace.gcsim.optimizer_go_session.prepare_optimizer_inputs", return_value=prepared),
                patch.object(session, "_validate_optimizer_request"),
                patch.object(session, "_prepare_formula_inputs", return_value={}),
                patch.object(session, "_run_go_optimizer", return_value={"status": "success"}),
                patch("run_workspace.gcsim.optimizer_go_session.prune_go_optimizer_runs_best_effort",
                      return_value={"status": "ok"}),
            ):
                result = session.run()
            run_dir = Path(result["run_dir"])
            self.assertEqual(result["status"], "success")
            self.assertIsNone(session._run_dir)
            session.request_finish()
            self.assertTrue(session._finish_requested.is_set())
            self.assertFalse(session._cancelled.is_set())
            self.assertFalse((run_dir / "finish-requested").exists())
            self.assertEqual(result["status"], "success")

    def test_emergency_cancel_stops_only_registered_child_even_after_grace_timeout(self) -> None:
        class HungChild:
            def __init__(self):
                self.stopped = False
                self.graceful_attempts = 0
                self.kill_calls = 0

            def poll(self):
                return 1 if self.stopped else None

            def send_signal(self, _signal):
                self.graceful_attempts += 1

            def terminate(self):
                self.graceful_attempts += 1

            def wait(self, timeout):
                raise subprocess.TimeoutExpired("mock optimizer", timeout)

            def kill(self):
                self.kill_calls += 1
                self.stopped = True

        session = GcsimOptimizerGoSelectedSession(GcsimOptimizerGoSelectedRequest("unused", {}, 0, ""))
        owned, unrelated = HungChild(), HungChild()
        session._register_process(owned)
        session.cancel()
        self.assertTrue(session._cancelled.is_set())
        self.assertTrue(owned.stopped)
        self.assertEqual(owned.graceful_attempts, 1)
        self.assertEqual(owned.kill_calls, 1)
        self.assertFalse(unrelated.stopped)
        self.assertEqual(unrelated.graceful_attempts, 0)

    def test_selected_preflight_has_no_hidden_fifteen_second_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "gtt-optimizer.exe"
            binary.write_bytes(b"test executable placeholder")
            request = GcsimOptimizerGoSelectedRequest(
                db_path="unused.db", selected_team={}, team_index=0,
                rotation_shell_text="", optimizer_binary_path=str(binary),
            )
            session = GcsimOptimizerGoSelectedSession(request)
            process = SimpleNamespace(returncode=0)
            with patch(
                "run_workspace.gcsim.optimizer_go_session.subprocess.Popen",
                return_value=process,
            ), patch.object(session, "_register_process"), patch.object(
                session, "_unregister_process"
            ), patch(
                "run_workspace.gcsim.optimizer_go_session._wait_process"
            ) as wait:
                session._validate_optimizer_request(run_dir=root, started=time.monotonic())
            self.assertEqual(wait.call_args.kwargs["timeout_ms"], 0)

    def test_selected_command_carries_per_run_finish_marker(self) -> None:
        request = GcsimOptimizerGoSelectedRequest("unused", {}, 0, "")
        session = GcsimOptimizerGoSelectedSession(request)
        command = session._optimizer_command(Path("optimizer"), Path("run"))
        self.assertEqual(command[-2], "--finish-file")
        self.assertEqual(command[-1], str(Path("run") / "finish-requested"))

    def test_worker_exposes_request_finish_without_cancelling(self) -> None:
        from ui.gcsim_browser.run_worker import GcsimBrowserSelectedOptimizerWorker

        request = GcsimOptimizerGoSelectedRequest("unused", {}, 0, "")
        worker = GcsimBrowserSelectedOptimizerWorker(request)
        worker.request_finish()
        self.assertTrue(worker._session._finish_requested.is_set())
        self.assertFalse(worker._session._cancelled.is_set())

    def test_progress_records_finish_and_cancel_flags_separately(self) -> None:
        rows: list[dict] = []
        session = GcsimOptimizerGoSelectedSession(
            GcsimOptimizerGoSelectedRequest("unused", {}, 0, ""),
            progress_callback=rows.append,
        )
        session.request_finish()
        session._emit_progress(
            "request-sha", sequence=0, stage="loading_evidence",
            completed=0, total=2, started=time.monotonic(),
        )
        self.assertTrue(rows[0]["finish_requested"])
        self.assertFalse(rows[0]["cancellation_requested"])

    def test_theory_request_does_not_receive_selected_result_options(self) -> None:
        request = GcsimOptimizerGoSelectedRequest(
            db_path="unused.db",
            selected_team={},
            team_index=0,
            rotation_shell_text="",
            set_group_limit=99,
            builds_per_group=False,
            fast_mode="enabled",
        )
        self.assertIsNone(_optimizer_result_options(request, theory_mode=True))

    def test_optimizer_rejects_switch_after_button_request(self) -> None:
        request = GcsimOptimizerGoSelectedRequest(
            db_path="unused.db",
            selected_team={},
            team_index=0,
            rotation_shell_text="",
            expected_engine_id="previous",
        )
        with tempfile.TemporaryDirectory() as temporary, patch(
            "run_workspace.gcsim.optimizer_go_inputs.load_active_gcsim_optimizer_engine_context",
            return_value=SimpleNamespace(engine_id="selected"),
        ):
            with self.assertRaises(GcsimOptimizerGoSelectedError) as raised:
                _prepare_inputs(request, Path(temporary))
        self.assertEqual(raised.exception.code, "active_engine_changed")

    def test_artifact_registry_is_taken_from_bound_engine_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            selected = root / "selected" / "pkg" / "shortcut" / "artifact.dm.go"
            other = root / "other" / "pkg" / "shortcut" / "artifact.dm.go"
            for path in (selected, other):
                path.parent.mkdir(parents=True)
                path.write_text("package shortcut\n", encoding="utf-8")
            self.assertEqual(_bound_artifact_registry_source(root / "selected"), selected)

    def test_session_writes_bounded_adapter_stage_timings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            request = GcsimOptimizerGoSelectedRequest(
                db_path="unused.db",
                selected_team={},
                team_index=0,
                rotation_shell_text="",
                infinite_energy_enabled=True,
                run_root=temporary,
            )
            session = GcsimOptimizerGoSelectedSession(request)
            prepared = {"request_sha256": "request-sha", "request": {}}
            result = {
                "status": "success",
                "request_sha256": "request-sha",
                "fast_mode": True,
            }

            with (
                patch(
                    "run_workspace.gcsim.optimizer_go_session.prepare_optimizer_inputs",
                    return_value=prepared,
                ),
                patch.object(session, "_validate_optimizer_request"),
                patch.object(session, "_prepare_formula_inputs", return_value={}),
                patch.object(session, "_run_go_optimizer", return_value=result),
                patch(
                    "run_workspace.gcsim.optimizer_go_session."
                    "prune_go_optimizer_runs_best_effort",
                    return_value={"status": "ok"},
                ),
            ):
                payload = session.run()

            timing_path = Path(payload["run_dir"]) / "adapter-timings.json"
            timings = json.loads(timing_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["status"], "success")
        self.assertIs(payload["result"]["fast_mode"], True)
        self.assertEqual(
            timings["schema_kind"],
            "gtt_gcsim_optimizer_adapter_timings_v1",
        )
        self.assertEqual(timings["terminal_status"], "success")
        self.assertEqual(timings["mode"], "selected")
        for key in (
            "prepare_inputs_ms",
            "request_preflight_ms",
            "formula_inputs_ms",
            "optimizer_process_ms",
            "total_elapsed_ms",
        ):
            self.assertIsInstance(timings[key], float)
            self.assertGreaterEqual(timings[key], 0)

    def test_unmapped_set_piece_keeps_its_id_and_stats_as_an_offpiece(self) -> None:
        # Synthetic metadata only; actual stat conversion has its own tests.
        common = dict(position_key="goblet", rarity=5, level=20)
        items = [
            SimpleNamespace(artifact_id=1, default_eligible=True, gcsim_set_key="known", set_uid="Known", **common),
            SimpleNamespace(artifact_id=2, default_eligible=True, gcsim_set_key="", set_uid="UnmappedSet", **common),
            SimpleNamespace(artifact_id=3, default_eligible=False, gcsim_set_key="", set_uid="InvalidSet", **common),
        ]
        vector = SimpleNamespace(ready=True, stat_vector=SimpleNamespace(contributions=[
            SimpleNamespace(source_kind="main", gcsim_key="atk%", normalized_value="0.466"),
            SimpleNamespace(source_kind="substat", gcsim_key="em", normalized_value="42"),
        ]))
        snapshot = SimpleNamespace(wearers=[SimpleNamespace(wearer=SimpleNamespace(gcsim_character_key="actor"))])
        with patch("run_workspace.gcsim.optimizer_go_inputs.materialize_gcsim_optimizer_artifact_stat_vector", return_value=vector):
            rows = _request_artifacts(SimpleNamespace(artifacts=items), "actor", snapshot)
        self.assertEqual([row["artifact_id"] for row in rows], [1, 2])
        self.assertEqual(rows[1]["set_uid"], "unmappedset")
        self.assertEqual(rows[1]["main_stat"], rows[0]["main_stat"])
        self.assertEqual(rows[1]["substats"], rows[0]["substats"])

    def test_shared_jahoda_rotation_is_paste_ready_without_test_header(self) -> None:
        # User-facing sample, not engine defaults: prevent the supplied rotation
        # from passing a smoke only because a harness silently adds its target.
        from run_workspace.gcsim.config_assembly import audit_rotation_shell

        rotation = (
            Path(__file__).parents[2] / "fixtures" / "gcsim_optimizer_go_v1"
            / "flins_jahoda_no_burst_rotation.txt"
        ).read_text(encoding="utf-8")
        audit = audit_rotation_shell(rotation)
        self.assertTrue(audit.ready)
        self.assertEqual(audit.active_character_key, "ineffa")
        self.assertEqual(len(audit.target_placeholder_lines), 1)
        self.assertEqual(len(tuple(_TARGET_RE.finditer(rotation))), 1)
        self.assertFalse(audit.manual_block_lines)
        self.assertIn("options swap_delay=12 iteration=1000;", rotation)
        self.assertNotIn("ignore_burst_energy=", rotation)
        self.assertNotIn("jahoda burst", rotation)

    def test_selected_product_timeout_defaults_to_unlimited(self) -> None:
        self.assertEqual(DEFAULT_PRODUCT_TIMEOUT_MS, 0)

    def test_unbounded_dummy_error_is_localized(self) -> None:
        payload = {
            "success": False,
            "status": "failed",
            "error_code": "rotation_unbounded_dummy_target",
            "error": "internal fallback must not be shown",
            "run_dir": "C:/debug/run",
        }

        text = format_gcsim_optimizer_go_selected_result(payload)

        self.assertIn("while 1", text)
        self.assertNotIn("internal fallback", text)

    def test_formats_exact_winner_ids_and_measured_dps(self) -> None:
        payload = {
            "success": True,
            "status": "success",
            "run_dir": "C:/debug/run",
            "result": {
                "measured": {"dps": "148744.23", "standard_error": "68.32"},
                "formula_dps": "149000",
                "formula_residual": "-255.77",
                "winner": [
                    {"wearer_key": "furina", "slot": "flower", "artifact_id": 1301},
                    {"wearer_key": "furina", "slot": "plume", "artifact_id": 7},
                ],
                "warnings": ["measured_top_confidence_overlap"],
                "debug_receipt_path": "C:/debug/run/gob7-result.json",
            },
        }

        text = format_gcsim_optimizer_go_selected_result(payload)

        self.assertIn("Final DPS: 148744.23", text)
        self.assertIn("flower=1301", text)
        self.assertIn("plume=7", text)
        self.assertIn("measured_top_confidence_overlap", text)

    def test_formats_formula_only_result_without_measured_placeholders(self) -> None:
        payload = {
            "success": True,
            "status": "success",
            "run_dir": "C:/debug/run",
            "result": {
                "ranking_basis": "formula",
                "formula_dps": "148744.23",
                "winner": [],
                "warnings": [],
                "debug_receipt_path": "C:/debug/run/gob7-result.json",
            },
        }

        text = format_gcsim_optimizer_go_selected_result(payload)

        self.assertIn("Formula-only estimate: 148744.23", text)
        self.assertIn("Formula-only ranking", text)
        self.assertNotIn("Final DPS:", text)
        self.assertNotIn("Standard error:", text)

    def test_formats_finite_energy_requirement_and_margin(self) -> None:
        payload = {
            "success": True,
            "status": "success",
            "run_dir": "C:/debug/run",
            "result": {
                "measured": {"dps": "148744.23", "standard_error": "68.32"},
                "formula_dps": "149000",
                "formula_residual": "-255.77",
                "winner": [],
                "warnings": [],
                "energy": {
                    "feasible": True,
                    "maximum_shortage": "0",
                    "wearers": [
                        {
                            "wearer_key": "furina",
                            "artifact_er": "0.8868",
                            "required_artifact_er": "0.75",
                            "artifact_er_margin": "0.1368",
                        }
                    ],
                },
                "debug_receipt_path": "C:/debug/run/gob7-result.json",
            },
        }

        text = format_gcsim_optimizer_go_selected_result(payload)

        self.assertIn("furina", text)
        self.assertIn("88.7", text)
        self.assertIn("75.0", text)
        self.assertIn("+13.7", text)

    def test_product_adapter_does_not_import_legacy_search_services(self) -> None:
        source = (
            Path(__file__).parents[3]
            / "run_workspace"
            / "gcsim"
            / "optimizer_go_selected.py"
        ).read_text(encoding="utf-8")

        for forbidden in (
            "optimizer_anytime_selected_service",
            "optimizer_artifact_first_service",
            "gcsim_optimizer_v2",
            "selected_composition",
        ):
            self.assertNotIn(forbidden, source)

    def test_go_progress_sequence_is_offset_after_compact_capture(self) -> None:
        row = _progress_row(
            '{"schema_kind":"gtt_gcsim_optimizer_progress_v1","sequence":1}',
            sequence_offset=4,
        )

        self.assertIsNotNone(row)
        self.assertEqual(row["sequence"], 5)

    def test_compact_seed_panel_runs_in_parallel_but_keeps_seed_order(self) -> None:
        request = GcsimOptimizerGoSelectedRequest(
            db_path="unused.db",
            selected_team={},
            team_index=0,
            rotation_shell_text="",
            infinite_energy_enabled=False,
            seeds=(101, 202),
        )
        session = GcsimOptimizerGoSelectedSession(request)
        barrier = threading.Barrier(2, timeout=2)

        def fake_run_process(command, *, cwd, timeout_ms, stdout_path, stderr_path):
            seed = int(Path(str(command[-1])).stem.rsplit("-", 1)[-1])
            del cwd, timeout_ms, stdout_path, stderr_path
            barrier.wait()
            if seed == 101:
                time.sleep(0.02)
            (run_dir / f"compact-member-{seed}.json").write_text(
                f'{{"seed":"{seed}"}}', encoding="utf-8"
            )

        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            prepared = {
                "request_sha256": "request-sha",
                "request": {
                    "engine": {
                        "binary_path": "fake-engine",
                        "binding_sha256": "engine-sha",
                    },
                    "context": {
                        "trace_context_sha256": "context-sha",
                        "prepared_config": {"text": "target lvl=100 resist=0.1;"},
                    },
                },
            }
            with patch.object(session, "_run_process", side_effect=fake_run_process):
                compact = session._capture_compact_panel(
                    prepared=prepared,
                    run_dir=run_dir,
                    started=time.monotonic(),
                )
            captured_ignore_burst_energy = json.loads(
                (run_dir / "compact-request-101.json").read_text(encoding="utf-8")
            )["ignore_burst_energy"]

        self.assertEqual([int(row["seed"]) for row in compact["members"]], [101, 202])
        self.assertTrue(captured_ignore_burst_energy)


if __name__ == "__main__":
    unittest.main()
