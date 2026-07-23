from __future__ import annotations

import unittest

from run_workspace.gcsim.optimizer_set_config import (
    OPTIMIZER_SET_CONFIG_ASSIGNMENT_MISMATCH,
    OPTIMIZER_SET_CONFIG_INVALID_SET_KEY,
    render_gcsim_four_piece_set_overrides,
)


CONFIG = """furina char lvl=90/90 cons=0 talent=9,9,9;
furina add weapon="wolffang" refine=1 lvl=90/90;
furina add set="goldentroupe" count=4;
furina add set="heartofdepth" count=1;
furina add stats hp=4780 atk=311 hp%=0.466 hydro%=0.466 cr=0.311;

bennett char lvl=90/90 cons=6 talent=9,12,13;
bennett add weapon="mistsplitterreforged" refine=1 lvl=90/90;
bennett add set="noblesseoblige" count=5;
bennett add stats hp=4780 atk=311 er=0.518 pyro%=0.466 cr=0.311;

options iteration=10 workers=4;
active furina;
"""


class GcsimOptimizerSetConfigTest(unittest.TestCase):
    def test_full_team_override_replaces_all_old_set_rows(self) -> None:
        result = render_gcsim_four_piece_set_overrides(
            CONFIG,
            {"furina": "flowerofparadiselost", "bennett": "instructor"},
        )

        self.assertTrue(result.ready)
        self.assertNotIn("goldentroupe", result.config_text)
        self.assertNotIn("heartofdepth", result.config_text)
        self.assertNotIn("noblesseoblige", result.config_text)
        self.assertEqual(result.config_text.count("furina add set="), 1)
        self.assertIn(
            'furina add set="flowerofparadiselost" count=4;\n'
            "furina add stats",
            result.config_text,
        )
        self.assertEqual(
            [item.character_key for item in result.assignments],
            ["furina", "bennett"],
        )

    def test_one_wearer_override_preserves_unassigned_character(self) -> None:
        result = render_gcsim_four_piece_set_overrides(
            CONFIG,
            {"furina": "marechausseehunter"},
            require_full_team=False,
        )

        self.assertTrue(result.ready)
        self.assertIn('furina add set="marechausseehunter" count=4;', result.config_text)
        self.assertIn('bennett add set="noblesseoblige" count=5;', result.config_text)

    def test_rejects_character_keys_that_collide_after_normalization(self) -> None:
        result = render_gcsim_four_piece_set_overrides(
            CONFIG,
            {
                "furina": "goldentroupe",
                " FURINA ": "heartofdepth",
                "bennett": "noblesseoblige",
            },
        )

        self.assertFalse(result.ready)
        self.assertEqual(result.status, OPTIMIZER_SET_CONFIG_ASSIGNMENT_MISMATCH)
        self.assertIn("ambiguous", result.issues[0].message)

    def test_full_team_requires_exact_character_coverage(self) -> None:
        result = render_gcsim_four_piece_set_overrides(
            CONFIG,
            {"furina": "goldentroupe"},
        )

        self.assertFalse(result.ready)
        self.assertEqual(result.status, OPTIMIZER_SET_CONFIG_ASSIGNMENT_MISMATCH)
        self.assertEqual(result.issues[0].character_key, "bennett")

    def test_set_key_is_fail_closed_against_config_injection(self) -> None:
        result = render_gcsim_four_piece_set_overrides(
            CONFIG,
            {"furina": 'gt" count=4; target hp=1', "bennett": "noblesse"},
        )

        self.assertFalse(result.ready)
        self.assertEqual(result.status, OPTIMIZER_SET_CONFIG_INVALID_SET_KEY)
        self.assertEqual(result.config_text, "")


if __name__ == "__main__":
    unittest.main()
