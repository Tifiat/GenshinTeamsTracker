from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from run_workspace.gcsim.engine_compatibility import REQUIRED_BUNDLE_CAPABILITIES, verify_engine_application_bundle


class EngineCompatibilityTest(unittest.TestCase):
    def probe(self, *, mutate_build=None, mutate_result=None, consumer_failure=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            executable, consumer = root / "engine.exe", root / "consumer.exe"
            executable.write_bytes(b"engine")
            consumer.write_bytes(b"consumer")
            build = SimpleNamespace(source_manifest_required=True, source_manifest_ready=True,
                gtt_capabilities=tuple(REQUIRED_BUNDLE_CAPABILITIES), gtt_sequential_waves="true",
                artifact_path=str(executable), artifact_sha256=hashlib.sha256(b"engine").hexdigest())
            if mutate_build:
                mutate_build(build)
            calls = []
            def runner(command, cwd):
                calls.append(command)
                if command[0] == str(consumer):
                    if consumer_failure:
                        raise ValueError("consumer rejected schema")
                    return
                output = Path(command[command.index("-out") + 1])
                if "-gtt-trace-equation" in command:
                    value = {"duration_ms": 1000, "channels": [{"baseline_damage": "100", "response_coordinates": ["bennett.atk_flat"]}], "opaque_boundaries": []}
                elif "-gtt-wave-scenario" in command:
                    scenario = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
                    self.assertEqual(len(scenario["waves"]), 2)
                    for wave in scenario["waves"]:
                        self.assertEqual(wave["targets"][0]["type"], "dummy")
                    value = {"statistics": {"duration": {"mean": 2}}}
                else:
                    value = {"statistics": {"iterations": 1, "dps": {"mean": 100, "sd": 0}}}
                if mutate_result:
                    mutate_result(command, value)
                output.write_text(json.dumps(value), encoding="utf-8")
            with patch("run_workspace.gcsim.engine_compatibility.load_gcsim_artifact_set_catalog", return_value=SimpleNamespace(sets=("synthetic",))):
                error = verify_engine_application_bundle(root, build, optimizer_binary=consumer, runner=runner)
            return error, calls

    def test_complete_bundle_invokes_consumer_and_three_engine_smokes(self):
        error, calls = self.probe()
        self.assertEqual(error, "")
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[2][1], "validate-seed-member")

    def test_capability_or_generator_loss_stops_before_simulation(self):
        for mutate in (lambda b: setattr(b, "gtt_capabilities", ("gtt_engine_marker",)),
                       lambda b: setattr(b, "source_manifest_required", False),
                       lambda b: setattr(b, "gtt_sequential_waves", "false")):
            error, calls = self.probe(mutate_build=mutate)
            self.assertTrue(error)
            self.assertEqual(calls, [])

    def test_compact_consumer_failure_stops_before_wave_test(self):
        error, calls = self.probe(consumer_failure=True)
        self.assertIn("consumer rejected", error)
        self.assertEqual(len(calls), 3)

    def test_independent_damage_mismatch_rejected(self):
        def mutate(command, value):
            if "channels" in value:
                value["channels"][0]["baseline_damage"] = "200"
        error, _ = self.probe(mutate_result=mutate)
        self.assertIn("mismatch", error)

    def test_missing_ordinary_number_is_not_zero(self):
        def mutate(command, value):
            if "statistics" in value and "dps" in value["statistics"]:
                del value["statistics"]["dps"]["sd"]
        error, calls = self.probe(mutate_result=mutate)
        self.assertTrue(error)
        self.assertEqual(len(calls), 1)

    def test_all_frozen_smoke_is_not_a_success(self):
        def mutate(command, value):
            if "channels" in value:
                value["channels"][0]["response_coordinates"] = []
        error, _ = self.probe(mutate_result=mutate)
        self.assertIn("lost all artifact", error)
