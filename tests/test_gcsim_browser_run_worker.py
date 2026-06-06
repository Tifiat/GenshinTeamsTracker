from __future__ import annotations

import unittest

from ui.gcsim_browser.run_worker import (
    ERROR_ARTIFACT_PREFLIGHT_FAILED,
    ERROR_CONFIG_PARSE_OR_ROTATION_ERROR,
    ERROR_GCSIM_RUNTIME_ERROR,
    ERROR_PREPARE_NOT_READY,
    classify_gcsim_browser_run_payload,
    format_gcsim_browser_run_report,
)


class GcsimBrowserRunWorkerTest(unittest.TestCase):
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

    def test_formats_selected_chamber_report(self) -> None:
        payload = {
            "ready": True,
            "status": "ready",
            "config_path": "C:/repo/data/gcsim/runs/run/config.txt",
            "error_category": "",
            "selection": {"team_label": "Team 2", "side": 2, "chamber": 3},
            "smoke": {
                "status": "run_passed",
                "scenario_path": "C:/repo/data/gcsim/runs/run/gtt_wave_scenario.json",
                "enemy_mapping_method_counts": {"exact_normalized_name": 5},
                "scenario_summary": {
                    "wave_count": 5,
                    "target_count": 15,
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
        self.assertIn("Observed clear time: 51.5", text)
        self.assertIn("Enemy mapping methods: exact_normalized_name:5", text)
        self.assertIn("Failed action buckets: 1:skill_cd", text)
        self.assertIn("DPS correctness claim: false", text)


if __name__ == "__main__":
    unittest.main()
