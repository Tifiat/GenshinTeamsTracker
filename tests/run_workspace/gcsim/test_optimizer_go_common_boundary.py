"""Shared adapter ownership and unchanged transport checks; no engine calls."""

from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from run_workspace.gcsim.optimizer_go_all import (
    GcsimOptimizerGoAllSetsRequest, GcsimOptimizerGoAllSetsSession,
)
from run_workspace.gcsim.optimizer_go_contracts import canonical_json_bytes, write_canonical
from run_workspace.gcsim.optimizer_go_inputs import (
    VIRTUAL_ARTIFACT_POLICY_BY_MODE, prepare_optimizer_inputs,
)
from run_workspace.gcsim.optimizer_go_requests import GcsimOptimizerGoError, GcsimOptimizerGoRequest
from run_workspace.gcsim.optimizer_go_selected import (
    GcsimOptimizerGoSelectedError, GcsimOptimizerGoSelectedRequest,
    GcsimOptimizerGoSelectedSession, _write_canonical,
)
from run_workspace.gcsim.optimizer_go_session import GcsimOptimizerGoSession
from run_workspace.gcsim.optimizer_go_theory import (
    GcsimOptimizerGoTheoryRequest, GcsimOptimizerGoTheorySession,
)
from run_workspace.gcsim.optimizer_go_theory_session import (
    GcsimOptimizerGoTheorySession as VerifiedTheorySession,
)
from run_workspace.gcsim.selected_team_config import (
    VIRTUAL_ARTIFACT_POLICY_OWNED_BUILD,
    VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE,
    VIRTUAL_ARTIFACT_POLICY_THEORY_BASELINE,
)


class CommonGoBoundaryTests(unittest.TestCase):
    def test_legacy_public_types_and_writer_are_aliases_not_implementations(self):
        self.assertIs(GcsimOptimizerGoSelectedRequest, GcsimOptimizerGoRequest)
        self.assertIs(GcsimOptimizerGoSelectedError, GcsimOptimizerGoError)
        self.assertIs(_write_canonical, write_canonical)
        selected = asdict(GcsimOptimizerGoSelectedRequest("unused", {}, 0, "rotation"))
        all_sets = asdict(GcsimOptimizerGoAllSetsRequest("unused", {}, 0, "rotation"))
        self.assertEqual(selected, all_sets)
        theory = asdict(GcsimOptimizerGoTheoryRequest("unused", {}, 0, "rotation"))
        self.assertIsNone(theory.pop("theory_options"))
        self.assertEqual(theory.pop("product_timeout_ms"), 0)
        self.assertEqual(selected.pop("product_timeout_ms"), 0)
        self.assertEqual(selected, theory)

    def test_source_modes_and_capture_inheritance_are_separate(self):
        self.assertEqual(VIRTUAL_ARTIFACT_POLICY_BY_MODE, {
            "selected": VIRTUAL_ARTIFACT_POLICY_OWNED_BUILD,
            "all_sets": VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE,
            "theory": VIRTUAL_ARTIFACT_POLICY_THEORY_BASELINE,
        })
        self.assertTrue(issubclass(GcsimOptimizerGoSelectedSession, GcsimOptimizerGoSession))
        self.assertTrue(issubclass(GcsimOptimizerGoAllSetsSession, GcsimOptimizerGoSession))
        self.assertFalse(issubclass(GcsimOptimizerGoAllSetsSession, GcsimOptimizerGoSelectedSession))
        self.assertFalse(hasattr(GcsimOptimizerGoAllSetsSession, "_capture_compact_panel"))

    def test_only_verified_theory_session_accepts_no_verified_terminal_status(self):
        request = GcsimOptimizerGoRequest("unused", {}, 0, "rotation")
        selected = GcsimOptimizerGoSelectedSession(request)
        all_sets = GcsimOptimizerGoAllSetsSession(request)
        theory = VerifiedTheorySession(GcsimOptimizerGoTheoryRequest("unused", {}, 0, "rotation"))
        for inventory_session in (selected, all_sets):
            self.assertTrue(inventory_session._accept_optimizer_result_status("success"))
            self.assertFalse(inventory_session._accept_optimizer_result_status("no_verified_result"))
        self.assertTrue(theory._accept_optimizer_result_status("success"))
        self.assertTrue(theory._accept_optimizer_result_status("no_verified_result"))

    def test_all_three_sessions_pass_mode_to_the_common_preparation(self):
        for mode, request_type, session_type in (
            ("selected", GcsimOptimizerGoSelectedRequest, GcsimOptimizerGoSelectedSession),
            ("all_sets", GcsimOptimizerGoAllSetsRequest, GcsimOptimizerGoAllSetsSession),
            ("theory", GcsimOptimizerGoTheoryRequest, GcsimOptimizerGoTheorySession),
        ):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                request = request_type("unused", {}, 0, "rotation", run_root=temporary)
                session = session_type(request)
                with (
                    patch("run_workspace.gcsim.optimizer_go_session.prepare_optimizer_inputs",
                          return_value={"request_sha256": "unchanged-sha"}) as prepare,
                    patch.object(session, "_validate_optimizer_request"),
                    patch.object(session, "_prepare_formula_inputs", return_value={}),
                    patch.object(session, "_run_go_optimizer", return_value={"status": "success"}),
                    patch("run_workspace.gcsim.optimizer_go_session.prune_go_optimizer_runs_best_effort",
                          return_value={"status": "ok"}),
                ):
                    payload = session.run()
                self.assertTrue(payload["success"], payload)
                prepare.assert_called_once_with(request, Path(payload["run_dir"]), mode=mode)
                self.assertEqual(payload["mode"], mode)
                self.assertEqual(payload["request_sha256"], "unchanged-sha")

    def test_invalid_mode_fails_before_engine_or_inventory_access(self):
        request = GcsimOptimizerGoRequest("unused", {}, 0, "rotation")
        with patch("run_workspace.gcsim.optimizer_go_inputs.load_active_gcsim_optimizer_engine_context") as engine:
            with self.assertRaises(GcsimOptimizerGoError) as caught:
                prepare_optimizer_inputs(request, Path("unused"), mode="unknown")
        self.assertEqual(caught.exception.code, "optimizer_mode_invalid")
        engine.assert_not_called()

    def test_shared_writer_preserves_canonical_bytes_and_final_newline(self):
        payload = {"unicode": "\u2028\u2029Ж", "value": "0.466", "nested": {"b": [], "a": True}}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "request.json"
            write_canonical(path, payload)
            self.assertEqual(path.read_bytes(), canonical_json_bytes(payload) + b"\n")
