from __future__ import annotations

import unittest

from run_workspace.gcsim.config_talents import (
    TALENT_METHOD_CAPPED_AFTER_NORMALIZATION,
    TALENT_METHOD_CONSTELLATION_BONUS_REMOVED,
    WARNING_CONSTELLATION_TALENT_BONUS_NOT_RESOLVED,
    WARNING_POST_NORMALIZATION_TALENT_LEVEL_CAPPED_TO_GCSIM_RANGE,
    prepare_gcsim_talent_levels,
)


def talents(normal: int, skill: int, burst: int) -> list[dict]:
    return [
        {"slot": "normal", "skill_id": 1, "name": "Favonius Bladework", "level": normal},
        {"slot": "skill", "skill_id": 2, "name": "Breastplate", "level": skill},
        {"slot": "burst", "skill_id": 5, "name": "Sweeping Time", "level": burst},
    ]


class GcsimConfigTalentsTest(unittest.TestCase):
    def test_noelle_like_c3_c5_displayed_levels_are_reduced_to_base(self) -> None:
        result = prepare_gcsim_talent_levels(
            talents(10, 13, 13),
            [
                {
                    "pos": 3,
                    "is_actived": True,
                    "effect": "Increases <color=#FFD780FF>Breastplate</color> by 3.",
                },
                {
                    "pos": 5,
                    "is_actived": True,
                    "effect": "Increases <color=#FFD780FF>Sweeping Time</color> by 3.",
                },
            ],
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.to_talent_input_dict()["normal"], 10)
        self.assertEqual(result.to_talent_input_dict()["skill"], 10)
        self.assertEqual(result.to_talent_input_dict()["burst"], 10)
        self.assertEqual(result.talents[1].parsed_constellation_bonus, 3)
        self.assertEqual(result.talents[2].parsed_constellation_bonus, 3)
        self.assertEqual(
            result.talents[1].method,
            TALENT_METHOD_CONSTELLATION_BONUS_REMOVED,
        )

    def test_one_boosted_talent_is_reduced(self) -> None:
        result = prepare_gcsim_talent_levels(
            talents(6, 9, 13),
            [
                {
                    "pos": 5,
                    "is_actived": True,
                    "effect": "Level of <color=#FFD780FF>Sweeping Time</color> +3.",
                }
            ],
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.to_talent_input_dict()["burst"], 10)
        self.assertEqual(result.talents[2].parsed_constellation_bonus, 3)

    def test_unmatched_active_c3_c5_warns_and_caps_if_needed(self) -> None:
        result = prepare_gcsim_talent_levels(
            talents(6, 13, 9),
            [
                {
                    "pos": 3,
                    "is_actived": True,
                    "effect": "Level of <color=#FFD780FF>Unknown Skill</color> +3.",
                }
            ],
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.to_talent_input_dict()["skill"], 10)
        self.assertIn(WARNING_CONSTELLATION_TALENT_BONUS_NOT_RESOLVED, result.warnings)
        self.assertIn(
            WARNING_POST_NORMALIZATION_TALENT_LEVEL_CAPPED_TO_GCSIM_RANGE,
            result.warnings,
        )
        self.assertEqual(result.talents[1].method, TALENT_METHOD_CAPPED_AFTER_NORMALIZATION)

    def test_post_normalization_level_above_ten_is_capped(self) -> None:
        result = prepare_gcsim_talent_levels(talents(6, 11, 9), [])

        self.assertTrue(result.ready)
        self.assertEqual(result.to_talent_input_dict()["skill"], 10)
        self.assertIn(
            WARNING_POST_NORMALIZATION_TALENT_LEVEL_CAPPED_TO_GCSIM_RANGE,
            result.warnings,
        )

    def test_inactive_c3_c5_does_not_affect_levels(self) -> None:
        result = prepare_gcsim_talent_levels(
            talents(6, 13, 9),
            [
                {
                    "pos": 3,
                    "is_actived": False,
                    "effect": "Level of <color=#FFD780FF>Breastplate</color> +3.",
                }
            ],
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.to_talent_input_dict()["skill"], 10)
        self.assertEqual(result.talents[1].parsed_constellation_bonus, 0)
        self.assertIn(
            WARNING_POST_NORMALIZATION_TALENT_LEVEL_CAPPED_TO_GCSIM_RANGE,
            result.warnings,
        )

    def test_helper_never_outputs_talent_above_ten(self) -> None:
        result = prepare_gcsim_talent_levels(talents(99, 99, 99), [])

        self.assertTrue(result.ready)
        levels = [
            result.to_talent_input_dict()["normal"],
            result.to_talent_input_dict()["skill"],
            result.to_talent_input_dict()["burst"],
        ]
        self.assertEqual(levels, [10, 10, 10])
        self.assertTrue(all(level <= 10 for level in levels))


if __name__ == "__main__":
    unittest.main()
