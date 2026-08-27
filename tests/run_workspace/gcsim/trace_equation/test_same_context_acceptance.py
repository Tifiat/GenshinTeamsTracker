from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.trace_equation.same_context_acceptance import (
    DEFAULT_GCSIM_ITERATIONS,
    build_current_same_context_acceptance_input,
    run_same_context_acceptance,
)


ROOT = Path(__file__).resolve().parents[4]
RUN_LIVE = os.environ.get("GTT_RUN_REAL_GCSIM_ACCEPTANCE") == "1"


class SameContextAcceptanceIntegrationTest(unittest.TestCase):
    @unittest.skipUnless(
        RUN_LIVE,
        "set GTT_RUN_REAL_GCSIM_ACCEPTANCE=1 for the real n=1000 gate",
    )
    def test_current_artifacts_fast_matches_real_gcsim_n1000(self) -> None:
        store = Path(
            os.environ.get(
                "GTT_REAL_GCSIM_STORE",
                ROOT / ".codex_tmp" / "forwarded_attack_v1_store",
            )
        )
        acceptance_input = build_current_same_context_acceptance_input(
            engine_store_dir=store,
            database_path=ROOT / "data" / "artifacts.db",
        )
        self.assertEqual(len(acceptance_input.artifact_ids), 20)
        self.assertEqual(len(set(acceptance_input.artifact_ids)), 20)
        self.assertEqual(acceptance_input.iterations, DEFAULT_GCSIM_ITERATIONS)

        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_same_context_acceptance(
                acceptance_input,
                run_dir=Path(temp_dir) / "live-acceptance",
            )

        self.assertEqual(
            result.trace_source_config_sha256,
            acceptance_input.engine_source_config_sha256,
        )
        self.assertEqual(result.gcsim_iterations, DEFAULT_GCSIM_ITERATIONS)
        self.assertTrue(result.passed, result.to_dict())


if __name__ == "__main__":
    unittest.main()
