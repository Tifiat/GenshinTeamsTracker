"""Adapter-only checks; no database, gameplay, engine or live app mutations."""
from contextlib import nullcontext
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from run_workspace.gcsim.optimizer_go_all import (
    GcsimOptimizerGoAllSetsRequest, GcsimOptimizerGoAllSetsSession,
)
from run_workspace.gcsim.optimizer_go_selected import (
    DEFAULT_OPTIMIZER_BINARY,
    GcsimOptimizerGoSelectedError,
    GcsimOptimizerGoSelectedRequest,
    _prepare_inputs,
)
from run_workspace.gcsim.selected_team_config import (
    VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE,
)


class AllSetsAdapterTests(unittest.TestCase):
    def test_default_installed_consumer_and_override_reach_all_sets_boundaries(self):
        default = GcsimOptimizerGoAllSetsRequest("unused", {}, 0, "")
        self.assertEqual(Path(default.optimizer_binary_path).resolve(), DEFAULT_OPTIMIZER_BINARY.resolve())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "candidate.exe"
            binary.write_bytes(b"mock candidate")
            request = GcsimOptimizerGoAllSetsRequest(
                "unused", {}, 0, "", optimizer_binary_path=str(binary))
            session = GcsimOptimizerGoAllSetsSession(request)
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
                self.assertEqual(popen.call_args.args[0][1], "optimize-all-sets")

    def test_rule_cache_paths_are_shared_but_experiments_are_disposable(self):
        from run_workspace.gcsim.optimizer_go_selected import PROJECT_ROOT
        session = GcsimOptimizerGoAllSetsSession(GcsimOptimizerGoAllSetsRequest("unused", {}, 0, ""))
        with patch.dict(os.environ, {}, clear=True):
            env = session._optimizer_environment()
            self.assertEqual(Path(env["GTT_RULE_CACHE_DIR"]), PROJECT_ROOT / "data/gcsim/set-rule-cache")
            self.assertEqual(Path(env["GTT_RULE_BUNDLED_CACHE_DIR"]), PROJECT_ROOT / "native/gcsim_optimizer/set-rule-cache")
        with patch.dict(os.environ, {"GTT_SCRATCH_DIR": "owned-job"}, clear=True):
            self.assertEqual(Path(session._optimizer_environment()["GTT_RULE_CACHE_DIR"]), Path("owned-job/set-rule-cache"))
        with patch.dict(os.environ, {"GTT_RULE_CACHE_DIR": "explicit-runtime", "GTT_RULE_BUNDLED_CACHE_DIR": "explicit-bundle"}, clear=True):
            env = session._optimizer_environment()
            self.assertEqual(env["GTT_RULE_CACHE_DIR"], "explicit-runtime")
            self.assertEqual(env["GTT_RULE_BUNDLED_CACHE_DIR"], "explicit-bundle")

    def test_neutral_rules_are_gated_by_mode_energy_and_engine(self):
        for mode, infinite, capability, expected in (
            ("all_sets", True, True, True), ("all_sets", False, True, False),
            ("theory", True, True, False), ("all_sets", True, False, False),
        ):
            with self.subTest(mode=mode, infinite=infinite, capability=capability), tempfile.TemporaryDirectory() as tmp:
                request = GcsimOptimizerGoAllSetsRequest("unused", {}, 0, "", infinite_energy_enabled=infinite)
                session = GcsimOptimizerGoAllSetsSession(request)
                session.run_mode = mode
                folder = Path(tmp)
                engine = {"binary_path": str(folder / "build/gtt-gcsim.exe"),
                          "capabilities": ["gtt_neutral_inputs_v1"] if capability else []}
                with patch("run_workspace.gcsim.optimizer_go_all.prepare_all_set_effect_sources", return_value={}) as source:
                    session._prepare_formula_inputs(prepared={"request": {"engine": engine}}, run_dir=folder, started=0)
                    source.assert_called_once_with(folder, engine, include_neutral_rules=expected)

    def test_virtual_slots_use_read_only_inventory_baseline_policy(self):
        self.assertEqual(
            GcsimOptimizerGoAllSetsSession.virtual_artifact_policy,
            VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE,
        )

    def test_run_uses_shared_explicit_mode_preparation_without_engine_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            request = GcsimOptimizerGoAllSetsRequest(
                "unused", {}, 0, "rotation", run_root=str(Path(tmp) / "runs")
            )
            session = GcsimOptimizerGoAllSetsSession(request)
            run_dir = Path(tmp) / "run"
            prepared = {"request_sha256": "a" * 64, "request": {}}
            with (
                patch(
                    "run_workspace.gcsim.optimizer_go_session._new_run_dir",
                    return_value=run_dir,
                ),
                patch(
                    "run_workspace.gcsim.optimizer_go_session.run_directory_lease",
                    return_value=nullcontext(),
                ),
                patch(
                    "run_workspace.gcsim.optimizer_go_session.prepare_optimizer_inputs",
                    return_value=prepared,
                ) as prepare_inputs,
                patch.object(session, "_validate_optimizer_request"),
                patch.object(session, "_prepare_formula_inputs", return_value={}),
                patch.object(session, "_run_go_optimizer", return_value={"ok": True}),
                patch(
                    "run_workspace.gcsim.optimizer_go_session.prune_go_optimizer_runs_best_effort",
                    return_value={},
                ),
            ):
                result = session.run()

            prepare_inputs.assert_called_once_with(
                request,
                run_dir,
                mode="all_sets",
            )
            self.assertTrue(result["success"])

    def test_shared_preparation_rebuilds_all_sets_config_from_snapshot_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            actor_rows = [
                {
                    "mapping": {
                        "gcsim_key": f"actor{index}",
                        "source": "account_sqlite_resolved_character_key",
                    }
                }
                for index in range(1, 5)
            ]
            initial_report = SimpleNamespace(
                team=SimpleNamespace(
                    payload={"characters": actor_rows},
                    characters=tuple(SimpleNamespace(slot_index=index) for index in range(4)),
                )
            )
            config_text = "\n".join(
                [
                    *(f"actor{index} char lvl=90/90 cons=0 talent=9,9,9;" for index in range(1, 5)),
                    *(f'actor{index} add weapon="weapon{index}";' for index in range(1, 5)),
                    *(f"actor{index} add stats atk=311;" for index in range(1, 5)),
                    "target lvl=100 hp=1000000 resist=0;",
                ]
            )
            final_report = SimpleNamespace(
                team=SimpleNamespace(payload={"characters": actor_rows}),
                full_config=SimpleNamespace(
                    assembly=SimpleNamespace(config_text=config_text)
                ),
            )
            selected_team = {"slots": [{"character": {"id": str(99 + i)}} for i in range(1, 5)]}
            snapshot = SimpleNamespace(
                equipment_rows_sha256="b" * 64,
                snapshot_sha256="c" * 64,
                wearers=(),
            )
            database = SimpleNamespace(artifact_database_input_sha256="a" * 64)
            engine_context = SimpleNamespace(
                engine_id="engine-1",
                capabilities=("gtt_compact_equation_v1", "gtt_trace_equation_v6"),
                engine_root=run_dir,
                artifact_path=run_dir / "gcsim",
                artifact_sha256="d" * 64,
            )
            copied_team = {"slots": [{"snapshot_copy": True}]}
            request = GcsimOptimizerGoSelectedRequest(
                db_path="unused.db",
                selected_team=selected_team,
                team_index=0,
                rotation_shell_text="target lvl=100 hp=1000000 resist=0;",
                run_root=str(run_dir / "runs"),
            )
            with (
                patch(
                    "run_workspace.gcsim.optimizer_go_inputs.load_active_gcsim_optimizer_engine_context",
                    return_value=engine_context,
                ),
                patch(
                    "run_workspace.gcsim.optimizer_go_inputs._bound_artifact_registry_source",
                    return_value=run_dir / "artifact.dm.go",
                ),
                patch(
                    "run_workspace.gcsim.optimizer_go_inputs.normalize_optimizer_rotation_shell",
                    return_value=SimpleNamespace(
                        source_text=request.rotation_shell_text,
                        optimizer_text=request.rotation_shell_text,
                        changed=False,
                        warning_code="",
                        duration_seconds=0,
                    ),
                ),
                patch(
                    "run_workspace.gcsim.optimizer_go_inputs.build_selected_team_full_config_report",
                    side_effect=(initial_report, final_report),
                ) as build_report,
                patch(
                    "run_workspace.gcsim.optimizer_go_inputs.load_gcsim_optimizer_artifact_database_input",
                    return_value=SimpleNamespace(
                        ready=True, database_input=database, issues=()
                    ),
                ),
                patch(
                    "run_workspace.gcsim.optimizer_go_inputs.load_selected_equipped_team_snapshot",
                    return_value=snapshot,
                ),
                patch(
                    "run_workspace.gcsim.optimizer_go_inputs.selected_team_with_equipped_snapshot_artifacts",
                    return_value=copied_team,
                ) as copy_team,
                patch(
                    "run_workspace.gcsim.optimizer_go_inputs._require_prepared_report"
                ),
                patch(
                    "run_workspace.gcsim.optimizer_go_inputs.bind_selected_report_config_and_snapshot",
                    return_value=(),
                ) as bind,
                patch(
                    "run_workspace.gcsim.optimizer_go_inputs._request_wearers",
                    return_value=[],
                ),
                patch(
                    "run_workspace.gcsim.optimizer_go_inputs._request_artifacts",
                    return_value=[],
                ),
                patch(
                    "run_workspace.gcsim.optimizer_go_inputs.load_engine_manifest",
                    side_effect=RuntimeError("stop after input binding"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "stop after input binding"):
                    _prepare_inputs(
                        request,
                        run_dir,
                        virtual_artifact_policy=VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE,
                    )

            copy_team.assert_called_once_with(
                selected_team,
                artifact_database=database,
                snapshot=snapshot,
            )
            self.assertEqual(build_report.call_count, 2)
            self.assertIs(build_report.call_args.kwargs["selected_team"], copied_team)
            bind.assert_called_once()

    def test_source_transport_is_one_go_call_not_python_capture_loop(self):
        request = GcsimOptimizerGoAllSetsRequest("unused", {}, 0, "rotation")
        self.assertEqual(request.product_timeout_ms, 0)
        session = GcsimOptimizerGoAllSetsSession(request)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            binary = folder / "build" / "gtt-gcsim.exe"
            prepared = {"request": {"engine": {"binary_path": str(binary)}}}
            with patch("run_workspace.gcsim.optimizer_go_all.prepare_all_set_effect_sources", return_value={"schema_version": 1}) as source, patch.object(session, "_capture_compact_panel", create=True, side_effect=AssertionError("Python capture is forbidden")):
                self.assertEqual(session._prepare_formula_inputs(prepared=prepared, run_dir=folder, started=0), {})
                source.assert_called_once_with(folder, prepared["request"]["engine"], include_neutral_rules=False)
            self.assertEqual(json.loads((folder / "set-sources.json").read_text()), {"schema_version": 1})
            self.assertIn("optimize-all-sets", session._optimizer_command(binary, folder))
            self.assertNotIn("verify-fgbs", session._optimizer_command(binary, folder))
            command = session._optimizer_command(binary, folder)
            self.assertEqual(command[-2], "--finish-file")
            self.assertEqual(command[-1], str(folder / "finish-requested"))

    def test_missing_observer_is_explicit_no_raw_only_fallback(self):
        session = GcsimOptimizerGoAllSetsSession(GcsimOptimizerGoAllSetsRequest("unused", {}, 0, ""))
        with tempfile.TemporaryDirectory() as tmp, patch("run_workspace.gcsim.optimizer_go_all.prepare_all_set_effect_sources", side_effect=ValueError("capability absent")):
            with self.assertRaises(GcsimOptimizerGoSelectedError) as failure:
                session._prepare_formula_inputs(prepared={"request": {"engine": {"binary_path": str(Path(tmp) / "build/gtt-gcsim.exe")}}}, run_dir=Path(tmp), started=0)
            self.assertEqual(failure.exception.code, "all_sets_source_unavailable")
            self.assertFalse((Path(tmp) / "set-sources.json").exists())
