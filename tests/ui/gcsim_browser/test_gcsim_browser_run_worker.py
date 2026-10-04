from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ui.gcsim_browser.run_worker import (
    ERROR_CANCELLED,
    ERROR_ARTIFACT_PREFLIGHT_FAILED,
    ERROR_CONFIG_PARSE_OR_ROTATION_ERROR,
    ERROR_GCSIM_RUNTIME_ERROR,
    ERROR_PREPARE_NOT_READY,
    WARNING_ABYSS_SOURCE_IDENTITY_MISSING,
    GcsimBrowserBatchRunRequest,
    GcsimBrowserDpsDummyRunRequest,
    GcsimBrowserRunRequest,
    classify_gcsim_browser_run_payload,
    format_gcsim_browser_batch_report,
    format_gcsim_browser_dps_dummy_report,
    format_gcsim_browser_run_report,
    right_panel_gcsim_result_from_browser_selected_payload,
    right_panel_gcsim_results_from_browser_batch_payload,
    run_gcsim_browser_dps_dummy,
    run_gcsim_browser_three_chambers,
    run_gcsim_browser_selected_chamber,
    _active_run_binding,
)


class GcsimBrowserRunWorkerTest(unittest.TestCase):
    def test_account_equipment_fallback_defaults_and_explicit_override(self) -> None:
        selected = GcsimBrowserRunRequest(
            db_path="fixture.db", selected_team=_selected_team(), team_index=0,
            chamber=1, side=1, rotation_shell_text="active chasca;",
        )
        batch = GcsimBrowserBatchRunRequest(
            db_path="fixture.db", selected_team=_selected_team(), team_index=0,
            side=1, rotation_shell_text="active chasca;",
        )
        dummy = GcsimBrowserDpsDummyRunRequest(
            db_path="fixture.db", selected_team=_selected_team(), team_index=0,
            rotation_shell_text="active chasca;",
        )
        self.assertTrue(selected.allow_account_equipment_fallback)
        self.assertTrue(batch.allow_account_equipment_fallback)
        self.assertTrue(dummy.allow_account_equipment_fallback)
        self.assertFalse(GcsimBrowserRunRequest(
            db_path="fixture.db", selected_team=_selected_team(), team_index=0,
            chamber=1, side=1, rotation_shell_text="active chasca;",
            allow_account_equipment_fallback=False,
        ).allow_account_equipment_fallback)

    def test_selected_forwards_fallback_and_optional_runner_with_fake_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            request = GcsimBrowserRunRequest(
                db_path="fixture.db", selected_team=_selected_team(), team_index=0,
                chamber=1, side=1, rotation_shell_text="active chasca;",
                abyss_period_start="2026-06-01", abyss_floor=12,
                run_root=temporary, expected_engine_id="engine-1",
                allow_account_equipment_fallback=False,
            )
            report = SimpleNamespace(ready=True)
            finished_report = SimpleNamespace(to_dict=lambda: {
                "ready": True, "smoke": {"success": True, "status": "run_passed"},
            })
            fake_runner = lambda *_args: None
            with (
                patch("ui.gcsim_browser.run_worker._active_run_binding", return_value=SimpleNamespace(
                    engine_id="engine-1", artifact_registry=Path(temporary) / "artifact.go",
                    enemy_registry=Path(temporary) / "enemy.go",
                )) as binding,
                patch("ui.gcsim_browser.run_worker.build_selected_team_full_config_report", return_value=report) as build,
                patch("ui.gcsim_browser.run_worker.run_selected_team_abyss_smoke", return_value={"success": True}) as smoke,
                patch("ui.gcsim_browser.run_worker.report_with_smoke", return_value=finished_report),
                patch("ui.gcsim_browser.run_worker.build_gcsim_readiness_summary", return_value=SimpleNamespace(blocked=False)),
            ):
                payload = run_gcsim_browser_selected_chamber(request, artifact_runner=fake_runner)
            self.assertTrue(payload["success"])
            binding.assert_called_once()
            self.assertFalse(build.call_args.kwargs["allow_account_equipment_fallback"])
            run_func = smoke.call_args.kwargs["artifact_run_func"]
            self.assertIs(run_func.keywords["runner"], fake_runner)
            self.assertEqual(run_func.keywords["expected_engine_id"], "engine-1")

    def test_selected_cancelled_before_output_allocation_or_binding(self) -> None:
        request = GcsimBrowserRunRequest(
            db_path="fixture.db", selected_team=_selected_team(), team_index=0,
            chamber=1, side=1, rotation_shell_text="active chasca;",
            abyss_period_start="2026-06-01", abyss_floor=12,
        )
        with (
            patch("ui.gcsim_browser.run_worker._new_run_dir") as allocate,
            patch("ui.gcsim_browser.run_worker._active_run_binding") as binding,
            patch("ui.gcsim_browser.run_worker.build_selected_team_full_config_report") as build,
        ):
            payload = run_gcsim_browser_selected_chamber(request, cancel_requested=lambda: True)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["status"], ERROR_CANCELLED)
        self.assertEqual(payload["error_category"], ERROR_CANCELLED)
        allocate.assert_not_called()
        binding.assert_not_called()
        build.assert_not_called()

    def test_selected_cancelled_after_binding_skips_config_and_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            request = GcsimBrowserRunRequest(
                db_path="fixture.db", selected_team=_selected_team(), team_index=0,
                chamber=1, side=1, rotation_shell_text="active chasca;",
                abyss_period_start="2026-06-01", abyss_floor=12, run_root=temporary,
            )
            cancelled = False

            def bind(*_args, **_kwargs):
                nonlocal cancelled
                cancelled = True
                return SimpleNamespace(engine_id="engine-1", artifact_registry=Path(temporary) / "artifact.go")

            with (
                patch("ui.gcsim_browser.run_worker._active_run_binding", side_effect=bind),
                patch("ui.gcsim_browser.run_worker.build_selected_team_full_config_report") as build,
                patch("ui.gcsim_browser.run_worker.run_selected_team_abyss_smoke") as smoke,
            ):
                payload = run_gcsim_browser_selected_chamber(
                    request, cancel_requested=lambda: cancelled,
                )
            self.assertEqual(payload["status"], ERROR_CANCELLED)
            build.assert_not_called()
            smoke.assert_not_called()

    def test_dps_dummy_forwards_account_equipment_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            request = GcsimBrowserDpsDummyRunRequest(
                db_path="fixture.db", selected_team=_selected_team(), team_index=0,
                rotation_shell_text="active chasca;", run_root=temporary,
                allow_account_equipment_fallback=False,
            )
            report = SimpleNamespace(ready=False, to_dict=lambda: {"ready": False})
            with (
                patch("ui.gcsim_browser.run_worker._active_run_binding", return_value=SimpleNamespace(
                    engine_id="engine-1", artifact_registry=Path(temporary) / "artifact.go",
                )),
                patch("ui.gcsim_browser.run_worker.build_selected_team_full_config_report", return_value=report) as build,
                patch("ui.gcsim_browser.run_worker.build_gcsim_readiness_summary", return_value=SimpleNamespace(blocked=False)),
            ):
                run_gcsim_browser_dps_dummy(request)
            self.assertFalse(build.call_args.kwargs["allow_account_equipment_fallback"])

    def test_batch_cancellation_stops_before_remaining_chambers(self) -> None:
        request = GcsimBrowserBatchRunRequest(
            db_path="fixture.db", selected_team=_selected_team(), team_index=0,
            side=1, rotation_shell_text="active chasca;", abyss_period_start="2026-06-01",
            abyss_floor=12, allow_account_equipment_fallback=False,
        )
        completed = []

        def fake_selected(chamber_request, **kwargs):
            completed.append(chamber_request)
            self.assertFalse(chamber_request.allow_account_equipment_fallback)
            self.assertIs(kwargs["artifact_runner"], fake_runner)
            return _chamber_payload(chamber_request.chamber, success=True, status="run_passed")

        fake_runner = lambda *_args: None
        with (
            patch("ui.gcsim_browser.run_worker._active_run_binding", return_value=SimpleNamespace(engine_id="engine-1")),
            patch("ui.gcsim_browser.run_worker.run_gcsim_browser_selected_chamber", side_effect=fake_selected) as selected,
        ):
            payload = run_gcsim_browser_three_chambers(
                request, artifact_runner=fake_runner, cancel_requested=lambda: bool(completed),
            )
        self.assertFalse(payload["success"])
        self.assertEqual(payload["batch_status"], ERROR_CANCELLED)
        self.assertEqual(payload["error_category"], ERROR_CANCELLED)
        self.assertEqual(len(payload["chambers"]), 1)
        self.assertEqual(selected.call_count, 1)

    def test_batch_cancelled_before_binding_has_no_chambers(self) -> None:
        request = GcsimBrowserBatchRunRequest(
            db_path="fixture.db", selected_team=_selected_team(), team_index=0,
            side=1, rotation_shell_text="active chasca;", abyss_period_start="2026-06-01",
            abyss_floor=12,
        )
        with (
            patch("ui.gcsim_browser.run_worker._active_run_binding") as binding,
            patch("ui.gcsim_browser.run_worker.run_gcsim_browser_selected_chamber") as selected,
        ):
            payload = run_gcsim_browser_three_chambers(request, cancel_requested=lambda: True)
        self.assertEqual(payload["batch_status"], ERROR_CANCELLED)
        self.assertEqual(payload["chambers"], [])
        binding.assert_not_called()
        selected.assert_not_called()

    def test_normal_run_registry_binding_uses_only_selected_engine(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            active_root = root / "selected"
            artifact = active_root / "pkg" / "shortcut" / "artifact.dm.go"
            monster = active_root / "pkg" / "shortcut" / "monster.dm.go"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("package shortcut\n", encoding="utf-8")
            monster.write_text("package shortcut\n", encoding="utf-8")
            with patch("ui.gcsim_browser.run_worker.GcsimEngineStore") as store_type:
                store_type.return_value.get_active_engine.return_value = SimpleNamespace(
                    engine_id="selected", path=active_root
                )
                binding = _active_run_binding("selected")
                self.assertEqual(binding.artifact_registry, artifact)
                self.assertEqual(binding.enemy_registry, monster)
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    _active_run_binding("previous")

    def test_classifies_prepare_not_ready(self) -> None:
        self.assertEqual(
            classify_gcsim_browser_run_payload({"ready": False, "issues": []}),
            ERROR_PREPARE_NOT_READY,
        )

    def test_classifies_rotation_error(self) -> None:
        payload = {
            "ready": False,
            "issues": [{"status": "shell_contains_manual_character_blocks"}],
        }

        self.assertEqual(
            classify_gcsim_browser_run_payload(payload),
            ERROR_CONFIG_PARSE_OR_ROTATION_ERROR,
        )

    def test_classifies_artifact_preflight_failure(self) -> None:
        payload = {
            "ready": True,
            "smoke": {
                "run_result": {
                    "artifact_preflight_status": "gtt_wave_scenario_contract_missing"
                }
            },
        }

        self.assertEqual(
            classify_gcsim_browser_run_payload(payload),
            ERROR_ARTIFACT_PREFLIGHT_FAILED,
        )

    def test_classifies_runtime_failure_after_preflight(self) -> None:
        payload = {
            "ready": True,
            "smoke": {
                "status": "run_failed",
                "run_result": {
                    "success": False,
                    "status": "run_failed",
                    "artifact_preflight_status": "gtt_wave_scenario_contract_ready",
                },
            },
        }

        self.assertEqual(
            classify_gcsim_browser_run_payload(payload),
            ERROR_GCSIM_RUNTIME_ERROR,
        )

    def test_classifies_dps_dummy_success(self) -> None:
        payload = {
            "ready": True,
            "dps_dummy_run": {
                "success": True,
                "status": "run_passed",
                "run_result": {"summary": {}},
            },
        }

        self.assertEqual(classify_gcsim_browser_run_payload(payload), "")

    def test_formats_selected_chamber_report(self) -> None:
        payload = {
            "ready": True,
            "status": "ready",
            "config_path": "C:/repo/data/gcsim/runs/run/config.txt",
            "error_category": "",
            "selection": {
                "team_label": "Team 2",
                "side": 2,
                "chamber": 3,
                "period_start": "2026-06-01",
                "floor": 12,
            },
            "smoke": {
                "status": "run_passed",
                "scenario_path": "C:/repo/data/gcsim/runs/run/gtt_wave_scenario.json",
                "enemy_mapping_method_counts": {"exact_normalized_name": 5},
                "scenario_summary": {
                    "wave_count": 5,
                    "target_count": 15,
                    "total_hp": 4430000,
                    "spawn_policy": "group_clear",
                },
                "run_result": {
                    "artifact_preflight_status": "gtt_wave_scenario_contract_ready",
                    "summary": {
                        "duration_mean": 51.5,
                        "dps_mean": 148000,
                        "total_damage_mean": 7666000,
                        "failed_actions": [
                            '{"skill_cd":{"mean":0.02,"max":0.13}}',
                        ],
                    },
                },
            },
        }

        text = format_gcsim_browser_run_report(payload)

        self.assertIn("Team: Team 2 / Side 2 / C3", text)
        self.assertIn("Abyss source: period_start=2026-06-01 floor=12", text)
        self.assertIn("Observed clear time: 51.5", text)
        self.assertIn("Avg total damage/run: 7.666e+06", text)
        self.assertNotIn("Total damage mean", text)
        self.assertIn("total_hp=4.43e+06", text)
        self.assertIn("Enemy mapping methods: exact_normalized_name:5", text)
        self.assertIn("Failed action buckets: 1:skill_cd", text)
        self.assertIn("DPS correctness claim: false", text)

    def test_formats_selected_chamber_separates_expected_notes(self) -> None:
        payload = {
            "ready": True,
            "status": "ready",
            "error_category": "",
            "selection": {
                "team_label": "Team 1",
                "side": 1,
                "chamber": 1,
                "period_start": "2026-06-01",
                "floor": 12,
            },
            "smoke": {"status": "run_passed", "run_result": {"summary": {}}},
            "warnings": [
                "dev_talent_order_skill_id_assumed",
                "artifact_set_auto_registry_mapping_not_curated",
                "runtime_warning",
            ],
        }

        text = format_gcsim_browser_run_report(payload)

        self.assertIn("Expected/dev notes:", text)
        self.assertIn("  - dev_talent_order_skill_id_assumed", text)
        self.assertIn("  - artifact_set_auto_registry_mapping_not_curated", text)
        self.assertIn("Real warnings/issues:", text)
        self.assertIn("  - runtime_warning", text)
        self.assertNotIn("\nWarnings:", text)

    def test_formats_selected_chamber_expected_notes_without_real_warning_section(self) -> None:
        payload = {
            "ready": True,
            "status": "ready",
            "error_category": "",
            "selection": {
                "team_label": "Team 1",
                "side": 1,
                "chamber": 1,
                "period_start": "2026-06-01",
                "floor": 12,
            },
            "smoke": {"status": "run_passed", "run_result": {"summary": {}}},
            "warnings": [
                "selected_runtime_team_adapter_boundary",
                "gcsim_boosted_energy_line_appended_no_existing_energy_line",
            ],
        }

        text = format_gcsim_browser_run_report(payload)

        self.assertIn("Expected/dev notes:", text)
        self.assertIn("  - selected_runtime_team_adapter_boundary", text)
        self.assertIn("  - gcsim_boosted_energy_line_appended_no_existing_energy_line", text)
        self.assertNotIn("Real warnings/issues:", text)
        self.assertNotIn("\nWarnings:", text)

    def test_formats_blocked_run_with_readiness_summary_not_raw_issue_wall(self) -> None:
        payload = {
            "ready": False,
            "status": "not_ready",
            "error_category": ERROR_PREPARE_NOT_READY,
            "selection": {
                "team_label": "Team 1",
                "side": 1,
                "chamber": 1,
                "period_start": "2026-06-01",
                "floor": 12,
            },
            "issues": [
                {
                    "status": "weapon_missing",
                    "field": "account_character_equipped_weapons",
                    "message": "Selected team slot has no current/equipped weapon.",
                }
            ],
            "readiness_summary": {
                "blocked": True,
                "groups": {
                    "missing_weapons": [
                        "Chasca: Selected team slot has no current/equipped weapon."
                    ]
                },
            },
        }

        text = format_gcsim_browser_run_report(payload)

        self.assertIn("Readiness summary:", text)
        self.assertIn("Missing weapons:", text)
        self.assertIn("Debug issue count: 1", text)
        self.assertNotIn("{'status': 'weapon_missing'", text)

    def test_missing_abyss_source_identity_does_not_use_backend_default(self) -> None:
        payload = run_gcsim_browser_selected_chamber(
            GcsimBrowserRunRequest(
                db_path="missing.db",
                selected_team=_selected_team(),
                team_index=0,
                chamber=1,
                side=1,
                rotation_shell_text="active chasca;",
            )
        )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_category"], ERROR_PREPARE_NOT_READY)
        self.assertIn(WARNING_ABYSS_SOURCE_IDENTITY_MISSING, payload["warnings"])
        self.assertIn("not using backend defaults", payload["error"])

    def test_batch_missing_abyss_source_identity_does_not_use_backend_default(self) -> None:
        payload = run_gcsim_browser_three_chambers(
            GcsimBrowserBatchRunRequest(
                db_path="missing.db",
                selected_team=_selected_team(),
                team_index=0,
                side=1,
                rotation_shell_text="active chasca;",
            )
        )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["batch_status"], "failed")
        self.assertIn(WARNING_ABYSS_SOURCE_IDENTITY_MISSING, payload["warnings"])
        self.assertEqual(payload["chambers"], [])

    def test_dps_dummy_run_path_does_not_require_abyss_source_identity(self) -> None:
        payload = run_gcsim_browser_dps_dummy(
            GcsimBrowserDpsDummyRunRequest(
                db_path="missing.db",
                selected_team=_selected_team(),
                team_index=0,
                rotation_shell_text="active chasca;",
            )
        )

        self.assertFalse(payload["success"])
        self.assertNotIn(WARNING_ABYSS_SOURCE_IDENTITY_MISSING, payload.get("warnings") or [])
        self.assertNotIn("Abyss source-data identity is missing", payload.get("error", ""))

    def test_formats_dps_dummy_report(self) -> None:
        payload = {
            "ready": True,
            "status": "ready",
            "config_path": "C:/repo/data/gcsim/runs/run/config.txt",
            "error_category": "",
            "selection": {"team_label": "Team 1"},
            "dps_dummy_run": {
                "status": "run_passed",
                "energy": {"mode": "boosted"},
                "dummy_target": {
                    "hp": "999999999",
                    "resist": "0.1",
                    "source": "rotation_shell/config",
                },
                "run_result": {
                    "artifact_preflight_status": "ready",
                    "summary": {
                        "dps_mean": 12345,
                        "total_damage_mean": 67890,
                    },
                },
            },
        }

        text = format_gcsim_browser_dps_dummy_report(payload)

        self.assertIn("Run DPS Dummy", text)
        self.assertIn("Abyss source: not used", text)
        self.assertIn("History persistence: disabled", text)
        self.assertIn("Energy mode: boosted", text)
        self.assertIn("Dummy target HP: 999999999", text)
        self.assertIn("Dummy target resist: 0.1", text)
        self.assertIn("DPS mean: 12345", text)
        self.assertIn("Avg total damage/run: 67890", text)
        self.assertNotIn("Total damage mean", text)

    def test_formats_batch_report(self) -> None:
        payload = {
            "batch_status": "partial_failed",
            "success": False,
            "selection": {
                "team_label": "Team 1",
                "side": 1,
                "period_start": "2026-06-01",
                "floor": 12,
            },
            "chambers": [
                _chamber_payload(1, success=True, status="run_passed"),
                _chamber_payload(
                    2,
                    success=False,
                    status="run_failed",
                    error_category=ERROR_GCSIM_RUNTIME_ERROR,
                    warnings=("runtime_warning",),
                ),
                _chamber_payload(3, success=True, status="run_passed"),
            ],
            "warnings": ["runtime_warning"],
        }

        text = format_gcsim_browser_batch_report(payload)

        self.assertIn("Run 3 chambers", text)
        self.assertIn("Team: Team 1 / Side 1", text)
        self.assertIn("Abyss source: period_start=2026-06-01 floor=12", text)
        self.assertIn("Batch status: partial_failed", text)
        self.assertIn("C1: status=run_passed", text)
        self.assertIn("C2: status=run_failed error_category=gcsim_runtime_error", text)
        self.assertIn("avg_total_damage_per_run=4.43e+06", text)
        self.assertNotIn("total_damage=", text)
        self.assertIn("scenario_hp=4.43e+06", text)
        self.assertIn("DPS correctness claim: false", text)

    def test_formats_batch_report_separates_expected_notes(self) -> None:
        payload = {
            "batch_status": "partial_failed",
            "success": False,
            "selection": {
                "team_label": "Team 1",
                "side": 1,
                "period_start": "2026-06-01",
                "floor": 12,
            },
            "chambers": [
                _chamber_payload(
                    1,
                    success=True,
                    status="run_passed",
                    warnings=("shell_target_placeholder_not_enemy_truth",),
                ),
                _chamber_payload(
                    2,
                    success=False,
                    status="run_failed",
                    error_category=ERROR_GCSIM_RUNTIME_ERROR,
                    warnings=(
                        "artifact_set_count_below_two_ignored",
                        "runtime_warning",
                    ),
                ),
            ],
            "warnings": [
                "shell_target_placeholder_not_enemy_truth",
                "artifact_set_count_below_two_ignored",
                "runtime_warning",
            ],
        }

        text = format_gcsim_browser_batch_report(payload)

        self.assertIn("Expected/dev notes:", text)
        self.assertIn("  - shell_target_placeholder_not_enemy_truth", text)
        self.assertIn("  - artifact_set_count_below_two_ignored", text)
        self.assertIn("Real warnings/issues:", text)
        self.assertIn("  - runtime_warning", text)
        self.assertIn("    notes=shell_target_placeholder_not_enemy_truth", text)
        self.assertIn("    notes=artifact_set_count_below_two_ignored", text)
        self.assertIn("    warnings=runtime_warning", text)
        self.assertNotIn("\nWarnings:", text)

    def test_batch_payload_converts_to_ordered_right_panel_runtime_results(self) -> None:
        payload = {
            "batch_status": "partial_failed",
            "selection": {
                "team_index": 0,
                "side": 1,
                "period_start": "2026-06-01",
                "floor": 12,
            },
            "chambers": [
                _chamber_payload(3, success=True, status="run_passed"),
                _chamber_payload(
                    1,
                    success=False,
                    status="run_failed",
                    error_category=ERROR_GCSIM_RUNTIME_ERROR,
                    warnings=("runtime_warning",),
                ),
                _chamber_payload(2, success=True, status="run_passed"),
            ],
        }

        results = right_panel_gcsim_results_from_browser_batch_payload(
            payload,
            rotation_hash="rotation-hash",
            target_mode="solo",
        )

        self.assertEqual([result.chamber for result in results], [1, 2, 3])
        self.assertEqual([result.side for result in results], [1, 1, 1])
        self.assertEqual(results[0].team_index, 0)
        self.assertEqual(results[0].status, "run_failed")
        self.assertEqual(results[0].error_category, ERROR_GCSIM_RUNTIME_ERROR)
        self.assertEqual(results[1].clear_time_seconds, 52)
        self.assertEqual(results[1].dps_mean, 100002)
        self.assertEqual(results[1].scenario_total_hp, 4430000)
        self.assertEqual(results[1].period_start, "2026-06-01")
        self.assertEqual(results[1].floor, 12)
        self.assertEqual(results[1].target_mode, "solo")
        self.assertEqual(results[1].rotation_hash, "rotation-hash")

    def test_selected_payload_converts_to_right_panel_runtime_result(self) -> None:
        payload = _chamber_payload(2, success=True, status="run_passed")
        payload["selection"]["team_index"] = 1
        payload["selection"]["side"] = 2
        payload["selection"]["target_mode"] = "multi"

        result = right_panel_gcsim_result_from_browser_selected_payload(
            payload,
            rotation_hash="rotation-hash",
            target_mode="solo",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.chamber, 2)
        self.assertEqual(result.team_index, 1)
        self.assertEqual(result.side, 2)
        self.assertEqual(result.status, "run_passed")
        self.assertEqual(result.clear_time_seconds, 52)
        self.assertEqual(result.dps_mean, 100002)
        self.assertEqual(result.total_damage_mean, 4430000)
        self.assertEqual(result.target_mode, "multi")
        self.assertEqual(result.rotation_hash, "rotation-hash")

    def test_selected_payload_without_smoke_does_not_convert_to_runtime_result(self) -> None:
        payload = _chamber_payload(1, success=False, status="run_failed")
        payload.pop("smoke")

        result = right_panel_gcsim_result_from_browser_selected_payload(
            payload,
            rotation_hash="rotation-hash",
            target_mode="solo",
        )

        self.assertIsNone(result)


def _chamber_payload(
    chamber: int,
    *,
    success: bool,
    status: str,
    error_category: str = "",
    warnings: tuple[str, ...] = (),
) -> dict:
    return {
        "success": success,
        "status": "ready",
        "error_category": error_category,
        "selection": {
            "team_label": "Team 1",
            "side": 1,
            "chamber": chamber,
            "period_start": "2026-06-01",
            "floor": 12,
        },
        "warnings": list(warnings),
        "smoke": {
            "status": status,
            "scenario_summary": {
                "wave_count": 2,
                "target_count": 2,
                "total_hp": 4430000,
            },
            "run_result": {
                "summary": {
                    "duration_mean": 50 + chamber,
                    "dps_mean": 100000 + chamber,
                    "total_damage_mean": 4430000,
                },
            },
        },
    }


def _selected_team() -> dict:
    return {
        "slots": [
            {
                "slot_index": 0,
                "character": {
                    "id": 10000104,
                    "name": "Chasca",
                },
            }
        ]
    }


if __name__ == "__main__":
    unittest.main()
