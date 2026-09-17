from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from run_workspace.gcsim.optimizer_go_selected_inputs import (
    enforce_gcsim_optimizer_mvp_energy_policy,
    selected_set_requirements,
    GcsimOptimizerGoSelectedInputError,
    SelectedBoundWearerInput,
)
from run_workspace.gcsim.optimizer_go_selected import _request_wearers


ROOT = Path(__file__).resolve().parents[3]


class GoSelectedInputBoundaryTests(unittest.TestCase):
    def test_selected_packages_keep_tiers_not_extra_piece(self) -> None:
        for source, expected in (
            ((("a", 4), ("x", 1)), (("a", 4),)),
            ((("a", 5),), (("a", 4),)),
            ((("a", 2), ("b", 2), ("x", 1)), (("a", 2), ("b", 2))),
            ((("b", 3), ("a", 2)), (("a", 2), ("b", 2))),
        ):
            self.assertEqual(selected_set_requirements(source), expected)
        for bad in ((("a", 3), ("b", 1), ("c", 1)), (("a", 2),),
                    (("a", 2), ("a", 2)), (("a", 4), ("b", 2))):
            with self.assertRaises(GcsimOptimizerGoSelectedInputError):
                selected_set_requirements(bad)

    def test_mixed_packages_transport_both_sets_and_preserve_four_piece_wire(self) -> None:
        wearers = (
            SelectedBoundWearerInput("actor_b", (), (), (("z", 3), ("a", 2))),
            SelectedBoundWearerInput("actor_a", (), (), (("four", 5),)),
        )
        rows = _request_wearers('actor_b add weapon="weapon_b";\nactor_a add weapon="weapon_a";', wearers)
        self.assertEqual(rows[0]["selected_set_uid"], "four")
        self.assertNotIn("selected_sets", rows[0])
        self.assertNotIn("selected_set_uid", rows[1])
        self.assertEqual(rows[1]["selected_sets"], [{"set_uid": "a", "count": 2}, {"set_uid": "z", "count": 2}])

    def test_energy_policy_is_idempotent(self) -> None:
        source = "options iteration=1 ignore_burst_energy=false;\ntarget lvl=100;\n"
        once = enforce_gcsim_optimizer_mvp_energy_policy(source)
        self.assertIn("ignore_burst_energy=true", once)
        self.assertEqual(enforce_gcsim_optimizer_mvp_energy_policy(once), once)

    def test_energy_policy_can_enable_real_burst_requirements(self) -> None:
        source = "options iteration=1 ignore_burst_energy=true;\ntarget lvl=100;\n"
        once = enforce_gcsim_optimizer_mvp_energy_policy(
            source,
            ignore_burst_energy=False,
        )
        self.assertIn("ignore_burst_energy=false", once)
        self.assertEqual(
            enforce_gcsim_optimizer_mvp_energy_policy(
                once,
                ignore_burst_energy=False,
            ),
            once,
        )

    def test_clean_selected_import_does_not_load_historical_trace_search(self) -> None:
        code = (
            "import json,sys; "
            "import run_workspace.gcsim.optimizer_go_selected; "
            "print(json.dumps(sorted(m for m in sys.modules "
            "if m.startswith('run_workspace.gcsim.trace_equation') "
            "or m.endswith('optimizer_main_response') "
            "or m.endswith('optimizer_stat_response'))))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout), [])


if __name__ == "__main__":
    unittest.main()
