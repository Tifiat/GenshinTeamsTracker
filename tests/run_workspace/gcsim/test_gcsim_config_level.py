from __future__ import annotations

import unittest

from run_workspace.gcsim.config_level import (
    STATUS_MISSING_LEVEL,
    STATUS_READY,
    WARNING_PROMOTE_LEVEL_MISSING_ASSUMED_AFTER_ASCENSION,
    resolve_gcsim_level_text,
)


class GcsimConfigLevelTest(unittest.TestCase):
    def test_breakpoint_levels_use_promote_phase(self) -> None:
        cases = (
            (80, 5, "80/80"),
            (80, 6, "80/90"),
            (70, 4, "70/70"),
            (70, 5, "70/80"),
        )

        for level, promote, expected in cases:
            with self.subTest(level=level, promote=promote):
                result = resolve_gcsim_level_text(level, promote)

                self.assertEqual(result.status, STATUS_READY)
                self.assertEqual(result.gcsim_level_text, expected)

    def test_final_cap_levels_do_not_require_promote_level(self) -> None:
        cases = (
            (90, "90/90"),
            (95, "95/95"),
            (100, "100/100"),
        )

        for level, expected in cases:
            with self.subTest(level=level):
                result = resolve_gcsim_level_text(level, None)

                self.assertEqual(result.status, STATUS_READY)
                self.assertEqual(result.gcsim_level_text, expected)

    def test_missing_promote_level_on_breakpoint_is_assumed_after_ascension(self) -> None:
        result = resolve_gcsim_level_text(80, None)

        self.assertEqual(result.status, STATUS_READY)
        self.assertEqual(result.gcsim_level_text, "80/90")
        self.assertIn(
            WARNING_PROMOTE_LEVEL_MISSING_ASSUMED_AFTER_ASCENSION,
            result.warnings,
        )

    def test_missing_level_is_controlled_missing(self) -> None:
        result = resolve_gcsim_level_text(None, None)

        self.assertEqual(result.status, STATUS_MISSING_LEVEL)
        self.assertEqual(result.gcsim_level_text, "")


if __name__ == "__main__":
    unittest.main()
