"""Adapter-only checks; no database, gameplay, engine or live app mutations."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from run_workspace.gcsim.optimizer_go_all import (
    GcsimOptimizerGoAllSetsRequest, GcsimOptimizerGoAllSetsSession,
)
from run_workspace.gcsim.optimizer_go_selected import GcsimOptimizerGoSelectedError


class AllSetsAdapterTests(unittest.TestCase):
    def test_source_transport_is_one_go_call_not_python_capture_loop(self):
        request = GcsimOptimizerGoAllSetsRequest("unused", {}, 0, "rotation")
        self.assertEqual(request.product_timeout_ms, 600_000)
        session = GcsimOptimizerGoAllSetsSession(request)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            binary = folder / "build" / "gtt-gcsim.exe"
            prepared = {"request": {"engine": {"binary_path": str(binary)}}}
            with patch("run_workspace.gcsim.optimizer_go_all.prepare_all_set_effect_sources", return_value={"schema_version": 1}) as source, patch.object(session, "_capture_compact_panel", side_effect=AssertionError("Python capture is forbidden")):
                self.assertEqual(session._prepare_formula_inputs(prepared=prepared, run_dir=folder, started=0), {})
                source.assert_called_once_with(folder, prepared["request"]["engine"])
            self.assertEqual(json.loads((folder / "set-sources.json").read_text()), {"schema_version": 1})
            self.assertIn("optimize-all-sets", session._optimizer_command(binary, folder))
            self.assertNotIn("verify-fgbs", session._optimizer_command(binary, folder))

    def test_missing_observer_is_explicit_no_raw_only_fallback(self):
        session = GcsimOptimizerGoAllSetsSession(GcsimOptimizerGoAllSetsRequest("unused", {}, 0, ""))
        with tempfile.TemporaryDirectory() as tmp, patch("run_workspace.gcsim.optimizer_go_all.prepare_all_set_effect_sources", side_effect=ValueError("capability absent")):
            with self.assertRaises(GcsimOptimizerGoSelectedError) as failure:
                session._prepare_formula_inputs(prepared={"request": {"engine": {"binary_path": str(Path(tmp) / "build/gtt-gcsim.exe")}}}, run_dir=Path(tmp), started=0)
            self.assertEqual(failure.exception.code, "all_sets_source_unavailable")
            self.assertFalse((Path(tmp) / "set-sources.json").exists())
