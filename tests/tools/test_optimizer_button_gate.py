import os
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.check_optimizer_buttons import button_gate_environment, run_button_gate
from tools.managed_optimizer_experiment import MANAGED_ROOT, managed_scratch, owned_job


class OptimizerButtonGateRunnerTests(unittest.TestCase):
    def test_environment_is_owned_and_cannot_disable_baseline(self):
        root = owned_job() / "runner-unit" if os.environ.get("GTT_SCRATCH_DIR") else MANAGED_ROOT
        with managed_scratch(root=root) as job:
            with patch.dict(os.environ, {"GTT_OPTIMIZER_BUTTON_BASELINE_CANDIDATE": "1"}):
                environment = button_gate_environment(job, Path("read-only-engine"), Path("consumer.exe"))
            self.assertEqual(environment["GTT_SCRATCH_DIR"], str(job))
            self.assertEqual(environment["GTT_OPTIMIZER_BUTTON_GATE"], "1")
            self.assertEqual(environment["GTT_OPTIMIZER_BUTTON_BASELINE_CANDIDATE"], "0")
            for name in ("TMP", "TEMP", "APPDATA", "LOCALAPPDATA", "GTT_RULE_CACHE_DIR"):
                self.assertTrue(Path(environment[name]).is_relative_to(job))
        self.assertFalse(job.exists())

    def test_missing_runtime_is_not_a_reason_to_fall_back(self):
        with self.assertRaises(FileNotFoundError):
            run_button_gate(Path("missing-test-engine-store"), Path("missing-test-consumer.exe"))
