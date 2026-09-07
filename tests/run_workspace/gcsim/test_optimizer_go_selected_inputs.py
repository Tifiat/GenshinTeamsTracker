from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from run_workspace.gcsim.optimizer_go_selected_inputs import (
    enforce_gcsim_optimizer_mvp_energy_policy,
)


ROOT = Path(__file__).resolve().parents[3]


class GoSelectedInputBoundaryTests(unittest.TestCase):
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
