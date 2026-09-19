from __future__ import annotations

import unittest

from run_workspace.gcsim.optimizer_rotation_policy import (
    ROTATION_AUTO_BOUNDED_WARNING,
    normalize_optimizer_rotation_shell,
)


class OptimizerRotationPolicyTests(unittest.TestCase):
    def test_pinned_dummy_infinite_loop_becomes_duration_mode(self) -> None:
        source = (
            "options swap_delay=12 iteration=1000;\n"
            "target lvl=100 resist=0.1 hp=999999999;\n"
            "active furina;\n"
            "while 1 { furina skill; }\n"
        )

        result = normalize_optimizer_rotation_shell(source)

        self.assertTrue(result.changed)
        self.assertEqual(result.source_text, source)
        self.assertEqual(result.duration_seconds, 90)
        self.assertEqual(result.warning_code, ROTATION_AUTO_BOUNDED_WARNING)
        self.assertIn("duration=90", result.optimizer_text)
        self.assertNotIn("hp=999999999", result.optimizer_text)
        self.assertIn("while 1", result.optimizer_text)

    def test_explicit_duration_is_preserved(self) -> None:
        source = (
            "options iteration=1000 duration=75;\n"
            "target lvl=100 hp=999999999;\n"
            "while true { wait(60); }\n"
        )

        result = normalize_optimizer_rotation_shell(source)

        self.assertTrue(result.changed)
        self.assertEqual(result.duration_seconds, 75)
        self.assertEqual(result.optimizer_text.count("duration=75"), 1)
        self.assertNotIn("duration=90", result.optimizer_text)

    def test_finite_or_non_pinned_inputs_are_not_changed(self) -> None:
        inputs = (
            "options iteration=1; target hp=999999999; for let i=0; i<2; i=i+1 { wait(1); }",
            "options iteration=1; target hp=1000; while 1 { wait(1); }",
            'options iteration=1; target hp=999999999; let x string = "while 1 {"; wait(1);',
            "options iteration=1; target hp=999999999; # while 1 {\nwait(1);",
        )

        for source in inputs:
            with self.subTest(source=source):
                result = normalize_optimizer_rotation_shell(source)
                self.assertFalse(result.changed)
                self.assertEqual(result.optimizer_text, source)


if __name__ == "__main__":
    unittest.main()
