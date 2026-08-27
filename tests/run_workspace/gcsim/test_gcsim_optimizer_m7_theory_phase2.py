from __future__ import annotations

import inspect
from pathlib import Path
import unittest

from tools.experiments.gcsim_optimizer_m7_theory_phase2 import (
    GcsimOptimizerM7TheoryPhase2ProtocolError,
    execute_gcsim_optimizer_m7_theory_phase2_protocol,
)


class GcsimOptimizerM7TheoryPhase2ProtocolTests(unittest.TestCase):
    def test_only_loads_prior_phases_then_persists_c2c2_before_freeze(self):
        calls = []
        def callback(name, value):
            def run(*_args): calls.append(name); return value
            return run
        result = execute_gcsim_optimizer_m7_theory_phase2_protocol(
            load_map=callback("load_map", "map"), load_four_piece=callback("load_4p", "4p"),
            run_two_plus_two=callback("run_2p2p", "result"),
            persist_two_plus_two=callback("persist_2p2p", "2p2p-checkpoint"),
            load_two_plus_two=callback("load_2p2p", "2p2p"),
            freeze_combined=callback("freeze", "freeze"), load_combined=callback("load_freeze", "loaded-freeze"),
        )
        self.assertEqual(calls, ["load_map", "load_4p", "run_2p2p", "persist_2p2p", "load_2p2p", "freeze", "load_freeze"])
        self.assertEqual(result.persisted_two_plus_two, "2p2p-checkpoint")
        parameters = inspect.signature(execute_gcsim_optimizer_m7_theory_phase2_protocol).parameters
        self.assertNotIn("build_map", parameters); self.assertNotIn("run_four_piece", parameters)

    def test_freeze_failure_preserves_completed_c2c2_checkpoint(self):
        with self.assertRaises(GcsimOptimizerM7TheoryPhase2ProtocolError) as raised:
            execute_gcsim_optimizer_m7_theory_phase2_protocol(
                load_map=lambda: "map", load_four_piece=lambda _map: "4p",
                run_two_plus_two=lambda _map: "result",
                persist_two_plus_two=lambda *_args: "immutable-2p2p",
                load_two_plus_two=lambda *_args: "2p2p",
                freeze_combined=lambda *_args: (_ for _ in ()).throw(RuntimeError("freeze failed")),
                load_combined=lambda *_args: self.fail("load must not run"),
            )
        self.assertEqual(raised.exception.persisted_two_plus_two, "immutable-2p2p")
        self.assertIn("theory_2p2p_persisted", raised.exception.events)

    def test_driver_has_no_exact_runner_or_response_runner_api(self):
        source = Path("tools/experiments/gcsim_optimizer_m7_theory_phase2.py").read_text(encoding="utf-8")
        self.assertNotIn("run_gcsim_stat_response", source)
        self.assertNotIn("run_gcsim_effect_observation", source)
        self.assertNotIn("discover_gcsim_optimizer_direct_stat_map", source)
        self.assertNotIn("discover_gcsim_optimizer_interaction_map", source)


if __name__ == "__main__": unittest.main()
