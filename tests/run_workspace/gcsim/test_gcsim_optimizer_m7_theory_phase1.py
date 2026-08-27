from __future__ import annotations

import unittest

from tools.experiments.gcsim_optimizer_m7_theory_phase1 import (
    GcsimOptimizerM7TheoryPhase1ProtocolError,
    execute_gcsim_optimizer_m7_theory_phase1_protocol,
)


class GcsimOptimizerM7TheoryPhase1ProtocolTests(unittest.TestCase):
    def test_map_is_persisted_and_fresh_loaded_before_complete_4p_checkpoint(self):
        events = []

        def callback(name, result):
            def run(*_args):
                events.append(name)
                return result
            return run

        result = execute_gcsim_optimizer_m7_theory_phase1_protocol(
            build_map=callback("build_map", "built"),
            persist_map=callback("persist_map", "map-artifact"),
            load_map=callback("load_map", "loaded-map"),
            run_four_piece=callback("run_4p", "complete-search"),
            persist_four_piece=callback("persist_4p", "4p-artifact"),
            load_four_piece=callback("load_4p", "loaded-4p"),
        )
        self.assertEqual(events, [
            "build_map", "persist_map", "load_map", "run_4p", "persist_4p", "load_4p",
        ])
        self.assertEqual(result.persisted_map, "map-artifact")
        self.assertEqual(result.loaded_search, "loaded-4p")

    def test_failure_after_map_persistence_preserves_map_and_never_enters_later_phases(self):
        calls = []

        def fail_search(_loaded):
            calls.append("run_4p")
            raise TimeoutError("bounded failure")

        with self.assertRaises(GcsimOptimizerM7TheoryPhase1ProtocolError) as raised:
            execute_gcsim_optimizer_m7_theory_phase1_protocol(
                build_map=lambda: calls.append("build_map") or "built",
                persist_map=lambda _built: calls.append("persist_map") or "immutable-map",
                load_map=lambda _persisted: calls.append("load_map") or "loaded",
                run_four_piece=fail_search,
                persist_four_piece=lambda *_args: calls.append("persist_4p"),
                load_four_piece=lambda *_args: calls.append("load_4p"),
            )
        self.assertEqual(raised.exception.persisted_map, "immutable-map")
        self.assertEqual(calls, ["build_map", "persist_map", "load_map", "run_4p"])
        self.assertNotIn("persist_4p", calls)


if __name__ == "__main__":
    unittest.main()
