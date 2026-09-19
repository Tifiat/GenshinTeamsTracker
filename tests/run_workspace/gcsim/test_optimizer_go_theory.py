"""Theory product adapter checks; no engine or live UI mutation."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from run_workspace.gcsim.optimizer_go_theory import (
    GCSIM_OPTIMIZER_GO_THEORY_RESULT_KIND,
    GcsimOptimizerGoTheoryRequest,
    GcsimOptimizerGoTheorySession,
    format_gcsim_optimizer_go_theory_result,
    theory_available,
)
from run_workspace.gcsim.optimizer_go_all import (
    GcsimOptimizerGoAllSetsRequest,
    GcsimOptimizerGoAllSetsSession,
)
from run_workspace.gcsim.optimizer_go_selected import (
    GcsimOptimizerGoSelectedError,
    GcsimOptimizerGoSelectedRequest,
    _report_issue_statuses,
    _request_theory_wearers,
)
from run_workspace.gcsim.selected_team_config import (
    VIRTUAL_ARTIFACT_POLICY_THEORY_BASELINE,
)


class TheoryAdapterTests(unittest.TestCase):
    def test_serialized_preparation_issues_are_read_as_mappings(self) -> None:
        issues = (
            {"status": "virtual_gcsim_profile_incomplete", "field": "character"},
            {"status": "character_block_not_ready", "field": "character.blocks[2]"},
        )

        self.assertEqual(
            _report_issue_statuses(issues),
            {"virtual_gcsim_profile_incomplete", "character_block_not_ready"},
        )

    def test_every_optimizer_mode_inherits_the_same_finite_energy_control(self) -> None:
        for request_type in (
            GcsimOptimizerGoSelectedRequest,
            GcsimOptimizerGoAllSetsRequest,
            GcsimOptimizerGoTheoryRequest,
        ):
            request = request_type(
                "unused", {}, 0, "rotation", infinite_energy_enabled=False
            )
            self.assertFalse(request.infinite_energy_enabled, request_type.__name__)

    def test_request_and_session_have_distinct_product_contract(self) -> None:
        request = GcsimOptimizerGoTheoryRequest("unused", {}, 0, "rotation")
        self.assertEqual(request.product_timeout_ms, 360_000)
        session = GcsimOptimizerGoTheorySession(request)
        self.assertEqual(session.run_mode, "theory")
        self.assertEqual(session.result_schema_kind, GCSIM_OPTIMIZER_GO_THEORY_RESULT_KIND)
        self.assertEqual(session.result_filename, "theory-result.json")
        self.assertEqual(session.request_validation_mode, "validate-theory-request")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            command = session._optimizer_command(folder / "gtt-optimizer.exe", folder)
        self.assertEqual(command[1], "optimize-theory")
        self.assertTrue(command[2].endswith("request.json"))
        self.assertTrue(command[3].endswith("set-sources.json"))
        self.assertTrue(command[4].endswith("theory"))

    def test_theory_wearers_are_neutral_and_inventory_independent(self) -> None:
        characters = []
        config_lines = []
        for index, actor in enumerate(("actor_a", "actor_b", "actor_c", "actor_d")):
            characters.append(
                {
                    "mapping": {"gcsim_key": actor},
                    "artifact_build": {
                        "source_kind": "theory_neutral_baseline",
                        "baseline_main_stats": {
                            "flower": "hp",
                            "plume": "atk",
                            "sands": "atk_percent",
                            "goblet": "atk_percent",
                            "circlet": "crit_rate",
                        },
                    },
                }
            )
            config_lines.append(f'{actor} add weapon="weapon_{index}" refine=1 lvl=90/90;')

        wearers = _request_theory_wearers(
            {"characters": characters}, config_text="\n".join(config_lines)
        )

        self.assertEqual(len(wearers), 4)
        self.assertTrue(all(row["current_artifacts"] == [] for row in wearers))
        self.assertTrue(all("selected_set_uid" not in row for row in wearers))
        self.assertTrue(all("selected_sets" not in row for row in wearers))
        self.assertTrue(all(len(row["theory_baseline"]["main_stats"]) == 5 for row in wearers))

    def test_availability_is_the_verified_all_sets_capability(self) -> None:
        with patch("run_workspace.gcsim.optimizer_go_theory.all_sets_available", return_value=True):
            self.assertTrue(theory_available())

    def test_session_preparation_uses_theory_only_virtual_artifact_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            request = GcsimOptimizerGoTheoryRequest(
                "unused.db", {}, 0, "active chiori;", run_root=temporary
            )
            session = GcsimOptimizerGoTheorySession(request)
            with (
                patch(
                    "run_workspace.gcsim.optimizer_go_selected._prepare_inputs",
                    return_value={"request_sha256": "request-sha", "request": {}},
                ) as prepare,
                patch.object(session, "_validate_optimizer_request"),
                patch.object(session, "_prepare_formula_inputs", return_value={}),
                patch.object(
                    session,
                    "_run_go_optimizer",
                    return_value={"status": "success", "request_sha256": "request-sha"},
                ),
                patch(
                    "run_workspace.gcsim.optimizer_go_selected."
                    "prune_go_optimizer_runs_best_effort",
                    return_value={"status": "ok"},
                ),
            ):
                payload = session.run()

        self.assertTrue(payload["success"])
        self.assertEqual(
            prepare.call_args.kwargs["virtual_artifact_policy"],
            VIRTUAL_ARTIFACT_POLICY_THEORY_BASELINE,
        )

    def test_finite_energy_theory_fails_before_formula_search(self) -> None:
        request = GcsimOptimizerGoTheoryRequest(
            "unused.db", {}, 0, "active chiori;", infinite_energy_enabled=False
        )
        session = GcsimOptimizerGoTheorySession(request)
        with patch.object(
            GcsimOptimizerGoAllSetsSession, "_prepare_formula_inputs"
        ) as capture:
            with self.assertRaises(GcsimOptimizerGoSelectedError) as raised:
                session._prepare_formula_inputs(prepared={}, run_dir=Path("unused"), started=0)
        self.assertEqual(raised.exception.code, "theory_finite_energy_unsupported")
        capture.assert_not_called()
        text = format_gcsim_optimizer_go_theory_result(
            {"success": False, "error_code": raised.exception.code}
        )
        self.assertIn("Теория пока не учитывает", text)

    def test_formatter_explains_non_owned_result_and_allocations(self) -> None:
        text = format_gcsim_optimizer_go_theory_result(
            {
                "success": True,
                "status": "success",
                "result": {
                    "coverage": {
                        "catalog_sets": 42,
                        "packages_considered": 3608,
                        "contexts_evaluated": 8,
                    },
                    "candidates": [
                        {
                            "rank": 1,
                            "formula_dps": 265235.3,
                            "undistinguished_set_slots": ["ineffa"],
                            "packages": [
                                {
                                    "wearer_key": "flins",
                                    "sets": [{"set_uid": "nightoftheskysunveiling", "count": 4}],
                                }
                            ],
                            "allocations": [
                                {
                                    "wearer_key": "flins",
                                    "main_stats": {
                                        "sands": "atk_percent",
                                        "goblet": "atk_percent",
                                        "circlet": "crit_damage",
                                    },
                                    "substats": [
                                        {"stat_key": "crit_rate", "roll_units": 8.5}
                                    ],
                                }
                            ],
                        }
                    ],
                    "warnings": ["bounded_set_shortlist_not_global_optimum"],
                    "debug_receipt_path": "receipt.json",
                },
            }
        )
        self.assertIn("farming target", text)
        self.assertIn("42 sets, 3608 packages", text)
        self.assertIn("nightoftheskysunveiling 4p", text)
        self.assertIn("atk_percent/atk_percent/crit_damage", text)
        self.assertIn("crit_rate≈8.5 rolls", text)
        self.assertIn("ineffa", text)
        self.assertIn("bounded_set_shortlist_not_global_optimum", text)

    def test_formatter_keeps_the_backend_top_five(self) -> None:
        candidates = [
            {
                "rank": rank,
                "formula_dps": 100_000 - rank,
                "packages": [],
                "allocations": [],
            }
            for rank in range(1, 7)
        ]
        text = format_gcsim_optimizer_go_theory_result(
            {
                "success": True,
                "status": "success",
                "result": {"coverage": {}, "candidates": candidates},
            }
        )
        self.assertIn("Top-5", text)
        self.assertNotIn("Top-6", text)

if __name__ == "__main__":
    unittest.main()
