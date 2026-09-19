from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from run_workspace.gcsim.optimizer_go_selected import (
    DEFAULT_PRODUCT_TIMEOUT_MS,
    GcsimOptimizerGoSelectedRequest,
    GcsimOptimizerGoSelectedSession,
    _TARGET_RE,
    _progress_row,
    _request_artifacts,
    format_gcsim_optimizer_go_selected_result,
)


class GcsimOptimizerGoSelectedTests(unittest.TestCase):
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
            result = {"status": "success", "request_sha256": "request-sha"}

            with (
                patch(
                    "run_workspace.gcsim.optimizer_go_selected._prepare_inputs",
                    return_value=prepared,
                ),
                patch.object(session, "_validate_optimizer_request"),
                patch.object(session, "_prepare_formula_inputs", return_value={}),
                patch.object(session, "_run_go_optimizer", return_value=result),
                patch(
                    "run_workspace.gcsim.optimizer_go_selected."
                    "prune_go_optimizer_runs_best_effort",
                    return_value={"status": "ok"},
                ),
            ):
                payload = session.run()

            timing_path = Path(payload["run_dir"]) / "adapter-timings.json"
            timings = json.loads(timing_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["status"], "success")
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
        with patch("run_workspace.gcsim.optimizer_go_selected.materialize_gcsim_optimizer_artifact_stat_vector", return_value=vector):
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

    def test_working_UI_timeout_allows_six_minute_prototype_run(self) -> None:
        self.assertEqual(DEFAULT_PRODUCT_TIMEOUT_MS, 360_000)

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
