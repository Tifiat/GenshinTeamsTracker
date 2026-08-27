from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from run_workspace.gcsim.optimizer_stat_response import (
    GCSIM_STAT_RESPONSE_ARTIFACT_AXES,
    GcsimStatResponseError,
    GcsimStatResponseObjective,
    GcsimStatResponseRequest,
    GcsimStatResponseTarget,
    build_gcsim_stat_response_probe_request,
    build_gcsim_stat_response_crit_relevance_request,
    derive_gcsim_optimizer_anytime_profiles_from_stat_response,
    enforce_gcsim_optimizer_mvp_energy_policy,
    parse_gcsim_stat_response_result,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimOptimizerWearerIdentity,
)


class GcsimOptimizerStatResponseTests(unittest.TestCase):
    def test_probe_panel_uses_equal_synthetic_baseline_and_bounded_batch(self) -> None:
        request = build_gcsim_stat_response_probe_request(
            context_sha256="a" * 64,
            objective=GcsimStatResponseObjective.CLEAR_TIME,
            iterations=8,
            workers=4,
        )

        self.assertTrue(request.ignore_burst_energy)
        self.assertEqual(
            len(request.baseline_changes),
            4 * len(GCSIM_STAT_RESPONSE_ARTIFACT_AXES),
        )
        self.assertEqual(len(request.interventions), 100)
        self.assertLessEqual(len(request.interventions), 256)
        for character_index in range(4):
            panel = {
                item.stat: item.value
                for item in request.baseline_changes
                if item.character_index == character_index
            }
            self.assertEqual(set(panel), set(GCSIM_STAT_RESPONSE_ARTIFACT_AXES))
            self.assertEqual(panel["cr"], 0.95)
            self.assertTrue(all(value == 0 for key, value in panel.items() if key != "cr"))
        self.assertIn("c1/main/hydro%", {item.intervention_id for item in request.interventions})
        self.assertIn("c2/main/electro%", {item.intervention_id for item in request.interventions})
        self.assertIn("c0/crit/drop", {item.intervention_id for item in request.interventions})

    def test_explicit_comparison_seed_overrides_context_derived_seed(self) -> None:
        first = build_gcsim_stat_response_probe_request(
            context_sha256="a" * 64,
            objective=GcsimStatResponseObjective.DPS,
            master_seed=42,
        )
        second = build_gcsim_stat_response_probe_request(
            context_sha256="b" * 64,
            objective=GcsimStatResponseObjective.DPS,
            master_seed=42,
        )

        self.assertEqual(first.master_seed, 42)
        self.assertEqual(second.master_seed, 42)

    def test_mvp_contract_rejects_honest_energy_response(self) -> None:
        original = build_gcsim_stat_response_probe_request(
            context_sha256="b" * 64,
            objective=GcsimStatResponseObjective.DPS,
        )
        with self.assertRaisesRegex(GcsimStatResponseError, "ignore burst energy"):
            GcsimStatResponseRequest(
                context_sha256=original.context_sha256,
                objective=original.objective,
                iterations=original.iterations,
                workers=original.workers,
                master_seed=original.master_seed,
                baseline_changes=original.baseline_changes,
                interventions=original.interventions,
                ignore_burst_energy=False,
            )

    def test_clear_time_target_requires_exact_selected_scenario_bytes(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "scenario.json"
            path.write_text('{"schema_version":1}\n', encoding="utf-8")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            target = GcsimStatResponseTarget(
                objective=GcsimStatResponseObjective.CLEAR_TIME,
                target_sha256=digest,
                wave_scenario_path=str(path),
            )
            self.assertEqual(target.wave_scenario_path, str(path.resolve()))
            with self.assertRaisesRegex(GcsimStatResponseError, "differs"):
                GcsimStatResponseTarget(
                    objective=GcsimStatResponseObjective.CLEAR_TIME,
                    target_sha256="c" * 64,
                    wave_scenario_path=str(path),
                )

    def test_parser_rejects_unknown_fields_and_misaligned_seed_panels(self) -> None:
        payload = _result_payload()
        parsed = parse_gcsim_stat_response_result(payload)
        self.assertEqual(parsed.character_keys, ("a", "b", "c", "d"))
        changed = json.loads(json.dumps(payload))
        changed["unexpected"] = True
        with self.assertRaisesRegex(GcsimStatResponseError, "fields"):
            parse_gcsim_stat_response_result(changed)
        changed = json.loads(json.dumps(payload))
        changed["interventions"][0]["samples"][0]["seed"] = "12"
        with self.assertRaisesRegex(GcsimStatResponseError, "seed panels"):
            parse_gcsim_stat_response_result(changed)

    def test_profiles_keep_only_measured_main_directions(self) -> None:
        request = build_gcsim_stat_response_probe_request(
            context_sha256="d" * 64,
            objective=GcsimStatResponseObjective.DPS,
            iterations=1,
            workers=1,
        )
        deltas = {
            "c0/main/hp%": 1_200.0,
            "c0/main/hydro%": 1_000.0,
            "c0/roll/hp%": 120.0,
            "c0/roll/cd": 80.0,
            "c0/crit/drop": -2_000.0,
            "c1/main/electro%": 900.0,
            "c1/roll/atk%": 50.0,
        }
        payload = _complete_result_payload(request, deltas)
        result = parse_gcsim_stat_response_result(payload)
        wearers = tuple(
            GcsimOptimizerWearerIdentity(
                team_slot=index,
                account_character_id=None,
                gcsim_character_key=key,
            )
            for index, key in enumerate(("furina", "ororon", "bennett", "chasca"), 1)
        )

        profiles = derive_gcsim_optimizer_anytime_profiles_from_stat_response(
            result,
            wearers,
        )
        self.assertTrue(
            all(
                profile.profile_id.replace("_", "").isalnum()
                and profile.profile_id == profile.profile_id.casefold()
                for profile in profiles
            )
        )
        furina = next(
            item
            for item in profiles
            if item.wearer == wearers[0] and item.profile_id == "balanced"
        )
        ororon = next(
            item
            for item in profiles
            if item.wearer == wearers[1] and item.profile_id == "balanced"
        )

        self.assertGreater(furina.main_score_index[("goblet", "hp%")], 0)
        self.assertGreater(furina.main_score_index[("goblet", "hydro%")], 0)
        self.assertEqual(furina.main_score_index[("goblet", "atk%")], 0)
        self.assertIn(
            ("goblet", "atk%", "negligible"),
            furina.main_classifications,
        )
        self.assertGreater(ororon.main_score_index[("goblet", "electro%")], 0)
        self.assertEqual(ororon.main_score_index[("goblet", "cryo%")], 0)

    def test_uncertain_main_is_not_classified_as_negligible(self) -> None:
        request = build_gcsim_stat_response_probe_request(
            context_sha256="9" * 64,
            objective=GcsimStatResponseObjective.DPS,
            iterations=1,
            workers=1,
        )
        result = parse_gcsim_stat_response_result(
            _complete_result_payload(
                request,
                {"c0/main/atk%": (0.5, 1.0)},
            )
        )
        wearers = tuple(
            GcsimOptimizerWearerIdentity(
                team_slot=index,
                account_character_id=None,
                gcsim_character_key=key,
            )
            for index, key in enumerate(
                ("furina", "ororon", "bennett", "chasca"), start=1
            )
        )

        profile = next(
            item
            for item in derive_gcsim_optimizer_anytime_profiles_from_stat_response(
                result,
                wearers,
            )
            if item.wearer == wearers[0] and item.profile_id == "balanced"
        )

        self.assertEqual(profile.main_score_index[("goblet", "atk%")], 0)
        self.assertIn(
            ("goblet", "atk%", "uncertain"),
            profile.main_classifications,
        )
        self.assertIn("atk%", profile.retained_main_axes_by_slot["goblet"])

    def test_profile_derivation_rejects_character_order_mismatch(self) -> None:
        request = build_gcsim_stat_response_probe_request(
            context_sha256="8" * 64,
            objective=GcsimStatResponseObjective.DPS,
            iterations=1,
            workers=1,
        )
        result = parse_gcsim_stat_response_result(
            _complete_result_payload(request, {})
        )
        wearers = tuple(
            GcsimOptimizerWearerIdentity(
                team_slot=index,
                account_character_id=None,
                gcsim_character_key=key,
            )
            for index, key in enumerate(
                ("ororon", "furina", "bennett", "chasca"), start=1
            )
        )
        with self.assertRaisesRegex(GcsimStatResponseError, "character order"):
            derive_gcsim_optimizer_anytime_profiles_from_stat_response(
                result,
                wearers,
            )

    def test_optimizer_energy_policy_is_local_and_idempotent(self) -> None:
        source = "options iteration=10 ignore_burst_energy=false;\nactive furina;\n"
        once = enforce_gcsim_optimizer_mvp_energy_policy(source)
        twice = enforce_gcsim_optimizer_mvp_energy_policy(once)
        self.assertIn("ignore_burst_energy=true", once)
        self.assertNotIn("ignore_burst_energy=false", once)
        self.assertEqual(once, twice)

    def test_crit_relevance_pass_uses_a_complete_synthetic_team(self) -> None:
        first_request = build_gcsim_stat_response_probe_request(
            context_sha256="f" * 64,
            objective=GcsimStatResponseObjective.DPS,
            iterations=1,
            workers=1,
        )
        first = parse_gcsim_stat_response_result(
            _complete_result_payload(
                first_request,
                {
                    "c0/main/hp%": 1_000.0,
                    "c0/main/hydro%": 900.0,
                    "c0/roll/hp%": 100.0,
                    "c0/roll/cd": 80.0,
                    "c0/crit/drop": -1_000.0,
                },
            )
        )

        request = build_gcsim_stat_response_crit_relevance_request(
            first,
            iterations=4,
            workers=2,
        )

        self.assertEqual(len(request.interventions), 4)
        c0 = {
            item.stat: item.value
            for item in request.baseline_changes
            if item.character_index == 0
        }
        self.assertEqual(c0["hp"], 4_780.0)
        self.assertEqual(c0["atk"], 311.0)
        self.assertEqual(c0["cr"], 0.95)
        self.assertGreater(c0["hp%"], 0)
        self.assertGreater(c0["cd"], 0)


def _result_payload() -> dict[str, object]:
    source = _observation("source", paired=False)
    baseline = _observation("baseline", paired=True)
    intervention = _observation("c0/main/atk%", paired=True)
    return {
        "schema_version": 2,
        "context_sha256": "a" * 64,
        "request_sha256": "b" * 64,
        "objective": "clear_time",
        "ignore_burst_energy": True,
        "character_keys": ["a", "b", "c", "d"],
        "seed_panel_sha256": "c" * 64,
        "source": source,
        "baseline": baseline,
        "interventions": [intervention],
    }


def _complete_result_payload(
    request: GcsimStatResponseRequest,
    deltas: dict[str, float | tuple[float, float]],
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "context_sha256": request.context_sha256,
        "request_sha256": request.request_sha256,
        "objective": request.objective.value,
        "ignore_burst_energy": True,
        "character_keys": ["furina", "ororon", "bennett", "chasca"],
        "seed_panel_sha256": "e" * 64,
        "source": _observation("source", paired=False),
        "baseline": _observation("baseline", paired=True),
        "interventions": [
            _observation(
                item.intervention_id,
                paired=True,
                paired_mean=(
                    deltas.get(item.intervention_id, 0.0)[0]
                    if isinstance(deltas.get(item.intervention_id, 0.0), tuple)
                    else deltas.get(item.intervention_id, 0.0)
                ),
                paired_standard_error=(
                    deltas.get(item.intervention_id, 0.0)[1]
                    if isinstance(deltas.get(item.intervention_id, 0.0), tuple)
                    else 0.0
                ),
            )
            for item in request.interventions
        ],
    }


def _observation(
    observation_id: str,
    *,
    paired: bool,
    paired_mean: float = 100.0,
    paired_standard_error: float = 0.0,
) -> dict[str, object]:
    result: dict[str, object] = {
        "id": observation_id,
        "samples": [
            {
                "seed": "11",
                "duration_frames": 600,
                "duration_seconds": 10.0,
                "team_expected_damage": 1000.0,
                "team_expected_dps": 100.0,
                "character_expected_damage": [400.0, 300.0, 200.0, 100.0],
                "character_expected_dps": [40.0, 30.0, 20.0, 10.0],
            }
        ],
        "summary": _summary(),
    }
    if paired:
        result["paired_delta"] = _summary(
            paired_mean,
            standard_error=paired_standard_error,
        )
    return result


def _summary(
    mean: float = 100.0,
    *,
    standard_error: float = 0.0,
) -> dict[str, object]:
    return {
        "duration_seconds": _estimate(10.0),
        "team_expected_damage": _estimate(1000.0),
        "team_expected_dps": _estimate(mean, standard_error=standard_error),
        "character_expected_dps": [
            _estimate(40.0),
            _estimate(30.0),
            _estimate(20.0),
            _estimate(10.0),
        ],
    }


def _estimate(mean: float, *, standard_error: float = 0.0) -> dict[str, object]:
    return {
        "count": 1,
        "mean": mean,
        "sample_sd": 0.0,
        "standard_error": standard_error,
    }


if __name__ == "__main__":
    unittest.main()
