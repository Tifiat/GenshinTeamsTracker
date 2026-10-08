from copy import deepcopy
import unittest

from tests.support.optimizer_button_baseline import assert_button_baseline, assert_button_runtime


class OptimizerButtonBaselineTests(unittest.TestCase):
    def setUp(self):
        self.engine = {"engine_id": "test", "artifact_sha256": "a", "binding_sha256": "b"}
        self.measured = {"dps": "1000", "standard_error": "2", "iterations": 500}
        self.baseline = {"schema": "gtt_optimizer_button_baseline_v1", "fixture_sha256": "f",
                         "engine": self.engine, "cases": {
                             "selected_fast": {"formula_dps": "900"},
                             "selected_verified": {"formula_dps": "900", "measured": self.measured}}}
        self.observation = {"mode": "selected", "fast_mode": False, "fixture_sha256": "f",
                            "engine": dict(self.engine), "formula_dps": "900",
                            "measured": deepcopy(self.measured)}

    def test_formula_and_simulator_need_not_match(self):
        assert_button_baseline(self.observation, self.baseline)

    def test_exactly_five_extra_seconds_is_allowed(self):
        assert_button_runtime(15000, 10000)

    def test_speed_failure_requests_isolated_idle_recheck(self):
        with self.assertRaisesRegex(AssertionError, "TIMING_RECHECK_REQUIRED"):
            assert_button_runtime(15001, 10000)

    def test_invalid_time_is_not_a_pass(self):
        with self.assertRaisesRegex(AssertionError, "Invalid button runtime"):
            assert_button_runtime(-1, 10000)

    def test_sampling_noise_does_not_fail(self):
        self.observation["measured"]["dps"] = "1005"
        assert_button_baseline(self.observation, self.baseline)

    def test_real_measured_change_fails_in_either_direction(self):
        for value in ("800", "1200"):
            with self.subTest(value=value), self.assertRaisesRegex(AssertionError, "sampling error"):
                self.observation["measured"]["dps"] = value
                assert_button_baseline(self.observation, self.baseline)

    def test_formula_change_requires_review_in_either_direction(self):
        for value in ("899", "901"):
            with self.subTest(value=value), self.assertRaisesRegex(AssertionError, "formula DPS"):
                self.observation["formula_dps"] = value
                assert_button_baseline(self.observation, self.baseline)

    def test_nonfinite_formula_fails_explicitly(self):
        for value in ("NaN", "Infinity"):
            with self.subTest(value=value), self.assertRaisesRegex(AssertionError, "Invalid formula"):
                self.observation["formula_dps"] = value
                assert_button_baseline(self.observation, self.baseline)

    def test_changed_fixture_or_engine_is_not_blessed(self):
        for field in ("fixture_sha256", "engine_id", "artifact_sha256", "binding_sha256"):
            row = deepcopy(self.observation)
            (row if field == "fixture_sha256" else row["engine"])[field] = "changed"
            with self.subTest(field=field), self.assertRaisesRegex(AssertionError, "review"):
                assert_button_baseline(row, self.baseline)

    def test_fast_mode_has_no_finalist_measurement(self):
        self.observation["fast_mode"] = True
        with self.assertRaisesRegex(AssertionError, "Fast mode"):
            assert_button_baseline(self.observation, self.baseline)
        self.observation["measured"] = None
        assert_button_baseline(self.observation, self.baseline)

    def test_missing_or_invalid_verified_measurement_fails(self):
        for value in (None, {"dps": "1000", "standard_error": "-1", "iterations": 500},
                      {"dps": "1000", "standard_error": "2", "iterations": 32}):
            with self.subTest(value=value), self.assertRaises(AssertionError):
                self.observation["measured"] = value
                assert_button_baseline(self.observation, self.baseline)
