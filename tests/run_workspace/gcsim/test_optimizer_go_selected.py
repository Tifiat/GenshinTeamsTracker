from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from run_workspace.gcsim.optimizer_go_selected import (
    DEFAULT_PRODUCT_TIMEOUT_MS,
    GcsimOptimizerGoSelectedRequest,
    GcsimOptimizerGoSelectedSession,
    _progress_row,
    format_gcsim_optimizer_go_selected_result,
)


class GcsimOptimizerGoSelectedTests(unittest.TestCase):
    def test_working_UI_timeout_allows_six_minute_prototype_run(self) -> None:
        self.assertEqual(DEFAULT_PRODUCT_TIMEOUT_MS, 360_000)

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

        self.assertEqual([int(row["seed"]) for row in compact["members"]], [101, 202])


if __name__ == "__main__":
    unittest.main()
