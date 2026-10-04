from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools.experiments.gcsim.closeout_response import run


SLOTS = ("flower", "plume", "sands", "goblet", "circlet")
ACTORS = ("bennett", "chasca", "furina", "ororon")
MAIN_STATS = {
    "flower": ("hp", 1000.0),
    "plume": ("atk", 311.0),
    "sands": ("atk_percent", 0.466),
    "goblet": ("geo_damage_bonus", 0.466),
    "circlet": ("crit_damage", 0.622),
}


def _artifact(ident: int, slot: str, set_uid: str, *, main: str | None = None,
              crit_rate: float = 0.0, crit_damage: float = 0.0, rarity: int = 5) -> dict:
    main_key, main_value = MAIN_STATS[slot]
    return {
        "artifact_id": ident,
        "slot": slot,
        "set_uid": set_uid,
        "rarity": rarity,
        "main_stat": {"key": main or main_key, "value": main_value},
        "substats": [
            {"key": "crit_rate", "value": crit_rate},
            {"key": "crit_damage", "value": crit_damage},
        ],
    }


def fixture_request(*, include_goblets: bool = True) -> tuple[dict, dict]:
    artifacts = []
    assignments = []
    for actor_index, actor in enumerate(ACTORS):
        for slot_index, slot in enumerate(SLOTS):
            ident = actor_index * 5 + slot_index + 1
            set_uid = "chasca_package" if actor == "chasca" and slot != "goblet" else f"{actor}_off"
            artifacts.append(_artifact(ident, slot, set_uid))
            assignments.append({"wearer_key": actor, "slot": slot, "artifact_id": ident})

    # The plume with lower unweighted CR+CD wins under correct 2*CR+CD.
    artifacts.extend([
        _artifact(21, "plume", "chasca_package", crit_rate=0.30, crit_damage=0.10),
        _artifact(22, "plume", "chasca_package", crit_rate=0.0, crit_damage=0.60),
    ])
    if include_goblets:
        # The non-ATK goblet has the highest score overall; ATK main is preferred.
        artifacts.extend([
            _artifact(23, "goblet", "chasca_off_a", main="atk_percent", crit_rate=0.30),
            _artifact(24, "goblet", "chasca_off_b", main="atk_percent", crit_damage=0.50),
            _artifact(25, "goblet", "chasca_off_c", main="hydro_damage_bonus", crit_rate=0.50, crit_damage=0.50),
        ])
    request = {
        "schema_kind": "gtt_gcsim_optimizer_request_v1",
        "result_options": {"builds_per_group": 7, "fast_mode": False, "set_group_limit": 90},
        "stochastic": {"seeds": list(run.EXPECTED_SEEDS)},
        "artifacts": artifacts,
        "wearers": [
            {
                "wearer_key": actor,
                "current_artifacts": [
                    {"wearer_key": actor, "slot": slot, "artifact_id": actor_index * 5 + slot_index + 1}
                    for slot_index, slot in enumerate(SLOTS)
                ],
                "selected_sets": ([{"set_uid": "chasca_package", "count": 4}] if actor == "chasca" else []),
            }
            for actor_index, actor in enumerate(ACTORS)
        ],
        "legality": {"default_minimum_rarity": 5, "authorized_lower_rarity_artifact_ids": []},
    }
    top1 = {"artifacts": assignments}
    return request, top1


class OptimizerCloseoutResponseTests(unittest.TestCase):
    def test_fast_flag_is_the_only_selection_change_on_synthetic_input(self) -> None:
        request, _ = fixture_request()
        before = copy.deepcopy(request)
        changed = run.request_for_fast_selection(request)
        self.assertEqual(run._differing_paths(before, changed), ["result_options.fast_mode"])
        self.assertEqual(changed["result_options"]["builds_per_group"], 7)
        self.assertEqual(tuple(changed["stochastic"]["seeds"]), run.EXPECTED_SEEDS)
        self.assertEqual(request, before)

    def test_frozen_request_loader_guards_with_temp_synthetic_json(self) -> None:
        request, _ = fixture_request()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "request.json"
            path.write_text(json.dumps(request), encoding="utf-8")
            with patch.object(run, "FROZEN_REQUEST_SHA256", run.digest_file(path)), patch.object(
                run, "EXPECTED_ARTIFACT_COUNT", len(request["artifacts"])
            ):
                self.assertEqual(run.load_frozen_request(path), request)

    def test_fast_selection_rejects_changed_inherited_build_count(self) -> None:
        request, _ = fixture_request()
        request["result_options"]["builds_per_group"] = 6
        with self.assertRaisesRegex(ValueError, "remain seven"):
            run.request_for_fast_selection(request)

    def test_challengers_are_legal_isolated_swaps_and_prioritize_atk_goblets(self) -> None:
        request, top1 = fixture_request()
        original = copy.deepcopy(request)
        cases = run.choose_changed_item_cases(request, top1)
        self.assertEqual([row["name"] for row in cases], ["top1", "chasca_plume", "chasca_goblet"])
        self.assertEqual(cases[1]["selection"]["artifact_id"], 21)
        self.assertEqual(cases[1]["selection"]["normalized_crit_mass_2cr_plus_cd"], 0.70)
        self.assertEqual(cases[2]["selection"]["artifact_id"], 23)
        self.assertEqual(cases[2]["selection"]["selected_main_stat"], "atk_percent")
        self.assertIn("atk_percent", cases[2]["stat_delta_vs_top1"])
        self.assertNotIn("hydro_damage_bonus", cases[2]["stat_delta_vs_top1"])

        for case, slot in zip(cases[1:], ("plume", "goblet"), strict=True):
            run.assert_isolated_swap(cases[0]["assignment"], case["assignment"], actor="chasca", slot=slot)
            run._require_legal_assignment(request, case["assignment"])
            self.assertEqual(len({row["artifact_id"] for row in case["assignment"]}), 20)
        self.assertEqual(request, original)

    def test_goblet_fallback_uses_highest_normalized_crit_distinct_main(self) -> None:
        request, top1 = fixture_request()
        for item in request["artifacts"]:
            if item["artifact_id"] in (23, 24):
                item["main_stat"]["key"] = "hp_percent"
        case = run.choose_changed_item_cases(request, top1)[2]
        self.assertEqual(case["selection"]["criterion"], "highest_normalized_crit_mass_legal_distinct_main_stat_fallback")
        self.assertEqual(case["selection"]["artifact_id"], 25)
        self.assertEqual(case["selection"]["baseline_main_stat"], "geo_damage_bonus")
        self.assertEqual(case["selection"]["selected_main_stat"], "hydro_damage_bonus")

    def test_missing_any_legal_goblet_challenger_fails_closed(self) -> None:
        request, top1 = fixture_request(include_goblets=False)
        with self.assertRaisesRegex(run.CloseoutError, "No legal distinct-main-stat"):
            run.choose_changed_item_cases(request, top1)

    def test_go_environment_drops_all_inherited_gtt_hooks(self) -> None:
        inherited = {
            "PATH": "safe-path",
            "GTT_NEUTRAL_CAPTURE_DIR": "old-capture",
            "GTT_NEUTRAL_TWO_SEEDS": "1",
            "GTT_MATRIX_CANDIDATE_RUN": "old-matrix",
            "GTT_OPTIMIZER_PROFILE": "1",
            "GTT_CLOSEOUT_REQUEST": "unowned",
        }
        with tempfile.TemporaryDirectory() as temporary:
            env = run._managed_go_environment(
                Path(temporary),
                base=inherited,
                closeout={"GTT_CLOSEOUT_CASES": "owned-cases.json"},
            )
            self.assertEqual(env["PATH"], "safe-path")
            self.assertEqual(env["GTT_CLOSEOUT_CASES"], "owned-cases.json")
            self.assertEqual({key for key in env if key.startswith("GTT_")}, {
                "GTT_CLOSEOUT_CASES", "GTT_RULE_CACHE_DIR", "GTT_RULE_BUNDLED_CACHE_DIR",
            })
            self.assertFalse(any(value.startswith("old-") or value == "1" for key, value in env.items()
                                 if key.startswith("GTT_")))
            with self.assertRaisesRegex(ValueError, r"GTT_CLOSEOUT_\*"):
                run._managed_go_environment(Path(temporary), base=inherited, closeout={"GTT_MATRIX_RUN": "bad"})

    def test_receipt_guards_enforce_containment_size_count_and_no_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            owner = Path(temporary) / "evidence"
            owner.mkdir()
            target = owner / "receipt.json"
            self.assertEqual(run.immutable_receipt_target(target, owner=owner), target)
            run.write_receipt(target, {"status": "offline-test"}, owner=owner)
            with self.assertRaises(FileExistsError):
                run.write_receipt(target, {"status": "must-not-overwrite"}, owner=owner)
            with self.assertRaises(ValueError):
                run.immutable_receipt_target(owner / "nested" / "escape.json", owner=owner)

        with tempfile.TemporaryDirectory() as temporary:
            owner = Path(temporary) / "evidence"
            owner.mkdir()
            (owner / "oversized.json").write_bytes(b"x" * (run.MAX_RECEIPT_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "byte budget"):
                run.immutable_receipt_target(owner / "new.json", owner=owner)

        with tempfile.TemporaryDirectory() as temporary:
            owner = Path(temporary) / "evidence"
            owner.mkdir()
            for index in range(run.MAX_RECEIPTS):
                (owner / f"{index}.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "count budget"):
                run.immutable_receipt_target(owner / "new.json", owner=owner)

    def test_case_envelope_keeps_selection_and_complete_stat_diffs(self) -> None:
        request, top1 = fixture_request()
        cases = run.choose_changed_item_cases(request, top1)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "cases.json"
            run._write_cases(path, cases, production_top1_formula_dps=123.5)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["production_top1_formula_dps"], 123.5)
        self.assertEqual(payload["cases"][2]["selection"]["artifact_id"], 23)
        self.assertEqual(payload["cases"][2]["stat_delta_vs_top1"], cases[2]["stat_delta_vs_top1"])

    def test_production_decimal_string_formula_dps_is_finite_and_parseable(self) -> None:
        self.assertEqual(run._finite_number("149971.6713624934", label="formula_dps"), 149971.6713624934)
        for value in ("NaN", "Infinity", True, None):
            with self.subTest(value=value), self.assertRaises(run.CloseoutError):
                run._finite_number(value, label="formula_dps")

    def test_config_predicate_only_go_command_precedes_selected_reference(self) -> None:
        events = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = root / "job"
            job.mkdir()
            native_copy = job / "repo" / "native" / "gcsim_optimizer"
            (native_copy / "cmd" / "gtt-optimizer").mkdir(parents=True)
            source = root / "predicate_test.go"
            source.write_text("package main\n", encoding="utf-8")

            def checks(_native_copy: Path, _job: Path) -> dict:
                events.append("native_checks")
                return {"vet": {"exit_code": 0}, "unit": {"exit_code": 0}}

            def fake_go(args, **_kwargs):
                events.append(("go", list(args)))
                return SimpleNamespace(returncode=0, stdout="ok\n")

            def selected(_request: dict, selected_job: Path):
                events.append("selected_reference")
                return {"rank": 1}, selected_job / "selected-reference"

            with patch.object(run, "GO_TEST_SOURCE", source), patch.object(
                run, "_run_go_checks", side_effect=checks
            ), patch.object(run.subprocess, "run", side_effect=fake_go), patch.object(
                run, "_selected_production_top1", side_effect=selected
            ):
                checks_result, predicate, top1, selected_dir = run._preflight_then_selected_top1(
                    native_copy, job, {"synthetic": True}
                )

        self.assertEqual(events[0], "native_checks")
        self.assertEqual(events[1], (
            "go",
            ["go", "test", "./cmd/gtt-optimizer", "-run", "^TestCloseoutConfigPredicates$", "-count=1"],
        ))
        self.assertEqual(events[2], "selected_reference")
        self.assertEqual(predicate["test"], "TestCloseoutConfigPredicates")
        self.assertEqual(predicate["status"], "passed")
        self.assertEqual(checks_result["injected_config_predicates"], predicate)
        self.assertEqual(top1, {"rank": 1})
        self.assertEqual(selected_dir, Path(temporary) / "job" / "selected-reference")

    def test_go_raw_regex_literals_have_single_escapes(self) -> None:
        source = run.GO_TEST_SOURCE.read_bytes()
        self.assertIn(rb"stats\b", source)
        self.assertNotIn(rb"stats\\b", source)
        self.assertIn(rb"\+params", source)
        self.assertNotIn(rb"\\+params", source)

    def test_preflight_failure_keeps_capture_count_zero_and_never_selects(self) -> None:
        progress = {
            "stage": "native_preflight",
            "actual_capture_members": 0,
            "capture_count_status": "known",
        }
        with patch.object(run, "_run_go_checks", return_value={"vet": {}, "unit": {}}), patch.object(
            run, "_compile_injected_test", side_effect=run.CloseoutError("predicate compile failed")
        ), patch.object(run, "_selected_production_top1") as selected:
            with self.assertRaisesRegex(run.CloseoutError, "predicate compile failed"):
                run._preflight_then_selected_top1(Path("native"), Path("job"), {}, progress=progress)
        selected.assert_not_called()
        self.assertEqual(progress["stage"], "native_preflight")
        self.assertEqual(progress["actual_capture_members"], 0)
        self.assertEqual(progress["capture_count_status"], "known")


if __name__ == "__main__":
    unittest.main()
