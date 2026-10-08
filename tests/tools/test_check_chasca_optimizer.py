"""Offline controls for the reviewed Chasca regression decision and cleanup."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests.support.chasca_optimizer_baseline import assert_chasca_button_baseline
from tools import check_chasca_optimizer as gate


class ChascaRegressionDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = json.loads(gate.BASELINE.read_bytes())
        candidate = json.loads(gate.CANDIDATE.read_bytes())
        cls.observation = {
            "status": "chasca_regression_observation_v1",
            "fixture": candidate["fixture"],
            "cases": [],
        }
        for case in candidate["cases"]:
            item = dict(case)
            expected = cls.baseline["cases"][case["mode"]]
            item.update(
                standard_error=expected["measured"]["standard_error"],
                iterations=500,
                input={
                    "artifact_count": 600, "wearer_count": 4,
                    "rotation_sha256": cls.baseline["fixture"]["rotation_sha256"],
                    "set_group_limit": expected["set_groups"],
                    "builds_per_group": expected["total_rows_per_group"],
                    "fast_mode": False,
                },
            )
            cls.observation["cases"].append(item)

    def test_accepted_candidate_and_single_case(self):
        assert_chasca_button_baseline(deepcopy(self.observation), self.baseline)
        one = deepcopy(self.observation)
        one["cases"] = [one["cases"][1]]
        assert_chasca_button_baseline(one, self.baseline, selected_case="selected")

    def test_fixture_fingerprint_and_winner_cannot_change(self):
        changed = deepcopy(self.observation)
        changed["fixture"]["content_fingerprints_sha256"] = "0" * 64
        with self.assertRaisesRegex(AssertionError, "fixture content_fingerprints"):
            assert_chasca_button_baseline(changed, self.baseline)
        changed = deepcopy(self.observation)
        changed["fixture"]["selected"][0]["baseline_artifact_ids"][0] = 1
        with self.assertRaisesRegex(AssertionError, "selected_builds_sha256"):
            assert_chasca_button_baseline(changed, self.baseline)
        changed = deepcopy(self.observation)
        changed["cases"][0]["winner_artifact_ids"][0] = changed["cases"][0]["winner_artifact_ids"][1]
        with self.assertRaisesRegex(AssertionError, "20 unique owned"):
            assert_chasca_button_baseline(changed, self.baseline)

    def test_measured_drop_and_gain_receive_distinct_decisions(self):
        for value, label in (("138000", "LOWER_QUALITY_REGRESSION"),
                             ("143000", "HIGHER_QUALITY_REVIEW_REQUIRED")):
            with self.subTest(value=value):
                changed = deepcopy(self.observation)
                changed["cases"][0]["measured_dps"] = value
                with self.assertRaisesRegex(AssertionError, label):
                    assert_chasca_button_baseline(changed, self.baseline)

    def test_changed_formula_and_valid_winner_do_not_override_measured_gate(self):
        changed = deepcopy(self.observation)
        # A nearby formula rank/winner may move without changing measured
        # quality; the separate small button gate still covers fast mode.
        changed["cases"][0]["formula_dps"] = "139120.5"
        changed["cases"][0]["winner_artifact_ids"][0] = 1
        changed["cases"][0]["measured_dps"] = "140800"
        assert_chasca_button_baseline(changed, self.baseline)

    def test_runtime_recheck_does_not_rebaseline(self):
        changed = deepcopy(self.observation)
        changed["cases"][1]["elapsed_seconds"] = 30.563001
        with self.assertRaisesRegex(AssertionError, "selected TIMING_RECHECK_REQUIRED"):
            assert_chasca_button_baseline(changed, self.baseline)

    def test_managed_cleanup_on_failure(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "managed"
            with self.assertRaisesRegex(RuntimeError, "synthetic child failure"):
                with gate.managed_scratch(root=root) as job:
                    (job / "sample.tmp").write_text("owned", encoding="utf-8")
                    raise RuntimeError("synthetic child failure")
            self.assertFalse(tuple(root.glob("job-*")))

    def test_public_json_fingerprint_ignores_crlf_conversion(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "public.json"
            path.write_bytes(b'{\n  "value": 1\n}\n')
            lf = gate._sha_lf(path)
            path.write_bytes(b'{\r\n  "value": 1\r\n}\r\n')
            self.assertEqual(gate._sha_lf(path), lf)


if __name__ == "__main__":
    unittest.main()
