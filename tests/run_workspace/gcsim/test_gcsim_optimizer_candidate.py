from __future__ import annotations

import unittest

from run_workspace.gcsim.artifact_set_catalog import (
    GcsimArtifactSetCapability,
    GcsimArtifactSetCatalog,
)
from run_workspace.gcsim.optimizer_candidate import (
    OPTIMIZER_CANDIDATE_OFFPIECE_MISMATCH,
    OPTIMIZER_CANDIDATE_SET_CONFIG_INVALID,
    OPTIMIZER_CANDIDATE_SET_PARAMETERS_REQUIRED,
    OPTIMIZER_CANDIDATE_UNKNOWN_SET,
    OPTIMIZER_CANDIDATE_UNMODELED_4P,
    prepare_gcsim_four_piece_optimizer_candidate,
)
from run_workspace.gcsim.optimizer_config import GcsimFiveStarMainStatLayout


CONFIG = """furina char lvl=90/90 cons=0 talent=9,9,9;
furina add weapon="wolffang" refine=1 lvl=90/90;
furina add set="goldentroupe" count=4;
furina add stats hp=4780 atk=311 hp%=0.466 hydro%=0.466 cr=0.311;
bennett char lvl=90/90 cons=6 talent=9,12,13;
bennett add weapon="mistsplitterreforged" refine=1 lvl=90/90;
bennett add set="noblesseoblige" count=4;
bennett add stats hp=4780 atk=311 er=0.518 pyro%=0.466 cr=0.311;
options iteration=10 workers=4;
active furina;
"""


class GcsimOptimizerCandidateTest(unittest.TestCase):
    def test_composes_modeled_mixed_rarity_team_candidate(self) -> None:
        result = prepare_gcsim_four_piece_optimizer_candidate(
            CONFIG,
            set_assignments={"furina": "goldentroupe", "bennett": "instructor"},
            main_stat_layouts=_layouts(),
            set_catalog=_catalog(),
            four_star_offpiece_slots={"bennett": "goblet"},
        )

        self.assertTrue(result.ready)
        self.assertIn('furina add set="goldentroupe" count=4;', result.config_text)
        self.assertIn('bennett add set="instructor" count=4;', result.config_text)
        self.assertIn(
            "furina add stats hp=4780 atk=311 hp%=0.466 hydro%=0.466 cr=0.311;",
            result.config_text,
        )
        self.assertIn(
            "bennett add stats hp=3571 atk=232 er=0.387 pyro%=0.466 cr=0.232;",
            result.config_text,
        )

    def test_rejects_unknown_and_unmodeled_sets(self) -> None:
        unknown = prepare_gcsim_four_piece_optimizer_candidate(
            CONFIG,
            set_assignments={"furina": "future", "bennett": "instructor"},
            main_stat_layouts=_layouts(),
            set_catalog=_catalog(),
            four_star_offpiece_slots={"bennett": "goblet"},
        )
        unmodeled = prepare_gcsim_four_piece_optimizer_candidate(
            CONFIG,
            set_assignments={"furina": "defenderswill", "bennett": "instructor"},
            main_stat_layouts=_layouts(),
            set_catalog=_catalog(),
            four_star_offpiece_slots={"furina": "flower", "bennett": "goblet"},
        )

        self.assertEqual(unknown.status, OPTIMIZER_CANDIDATE_UNKNOWN_SET)
        self.assertEqual(unmodeled.status, OPTIMIZER_CANDIDATE_UNMODELED_4P)

    def test_requires_offpiece_exactly_for_four_star_only_set(self) -> None:
        missing = prepare_gcsim_four_piece_optimizer_candidate(
            CONFIG,
            set_assignments={"furina": "goldentroupe", "bennett": "instructor"},
            main_stat_layouts=_layouts(),
            set_catalog=_catalog(),
        )
        extra = prepare_gcsim_four_piece_optimizer_candidate(
            CONFIG,
            set_assignments={"furina": "goldentroupe", "bennett": "noblesse"},
            main_stat_layouts=_layouts(),
            set_catalog=_catalog(),
            four_star_offpiece_slots={"furina": "flower"},
        )

        self.assertEqual(missing.status, OPTIMIZER_CANDIDATE_OFFPIECE_MISMATCH)
        self.assertEqual(extra.status, OPTIMIZER_CANDIDATE_OFFPIECE_MISMATCH)

    def test_rejects_normalized_set_and_offpiece_key_collisions(self) -> None:
        set_collision = prepare_gcsim_four_piece_optimizer_candidate(
            CONFIG,
            set_assignments={
                "furina": "goldentroupe",
                " FURINA ": "noblesse",
                "bennett": "instructor",
            },
            main_stat_layouts=_layouts(),
            set_catalog=_catalog(),
            four_star_offpiece_slots={"bennett": "goblet"},
        )
        offpiece_collision = prepare_gcsim_four_piece_optimizer_candidate(
            CONFIG,
            set_assignments={"furina": "goldentroupe", "bennett": "instructor"},
            main_stat_layouts=_layouts(),
            set_catalog=_catalog(),
            four_star_offpiece_slots={"bennett": "goblet", " BENNETT ": "flower"},
        )

        self.assertEqual(set_collision.status, OPTIMIZER_CANDIDATE_SET_CONFIG_INVALID)
        self.assertEqual(offpiece_collision.status, OPTIMIZER_CANDIDATE_OFFPIECE_MISMATCH)
        self.assertIn("ambiguous", offpiece_collision.issues[0].message)

    def test_rejects_parameterized_set_until_policy_is_frozen(self) -> None:
        capabilities = (*_catalog().sets, _capability("husk", max_rarity=5, parameters=("stacks",)))
        catalog = GcsimArtifactSetCatalog(
            source_root="fixture",
            source_fingerprint="p" * 64,
            sets=capabilities,
        )

        result = prepare_gcsim_four_piece_optimizer_candidate(
            CONFIG,
            set_assignments={"furina": "husk", "bennett": "noblesse"},
            main_stat_layouts=_layouts(),
            set_catalog=catalog,
        )

        self.assertEqual(result.status, OPTIMIZER_CANDIDATE_SET_PARAMETERS_REQUIRED)

    def test_rejects_hidden_stats_statement_before_candidate_rendering(self) -> None:
        for poisoned in (
            CONFIG.replace(
                'furina add weapon="wolffang" refine=1 lvl=90/90;',
                'furina add weapon="wolffang" refine=1 lvl=90/90; '
                "furina add stats cr=1;",
            ),
            CONFIG.replace(
                "furina add stats hp=4780",
                "furina add\n stats cr=1;\nfurina add stats hp=4780",
            ),
            CONFIG.replace(
                "furina add stats hp=4780",
                "furina add\u2028 stats cr=1;\nfurina add stats hp=4780",
            ),
        ):
            with self.subTest(poisoned=poisoned):
                result = prepare_gcsim_four_piece_optimizer_candidate(
                    poisoned,
                    set_assignments={
                        "furina": "goldentroupe",
                        "bennett": "instructor",
                    },
                    main_stat_layouts=_layouts(),
                    set_catalog=_catalog(),
                    four_star_offpiece_slots={"bennett": "goblet"},
                )

                self.assertEqual(
                    result.status,
                    OPTIMIZER_CANDIDATE_SET_CONFIG_INVALID,
                )
                self.assertFalse(result.ready)


def _layouts() -> dict[str, GcsimFiveStarMainStatLayout]:
    return {
        "furina": GcsimFiveStarMainStatLayout("hp%", "hydro%", "cr"),
        "bennett": GcsimFiveStarMainStatLayout("er", "pyro%", "cr"),
    }


def _catalog() -> GcsimArtifactSetCatalog:
    capabilities = (
        _capability("goldentroupe", max_rarity=5),
        _capability("noblesse", max_rarity=5),
        _capability("instructor", max_rarity=4),
        _capability("defenderswill", max_rarity=4, modeled=False),
    )
    return GcsimArtifactSetCatalog(
        source_root="fixture",
        source_fingerprint="f" * 64,
        sets=capabilities,
        _by_key={item.key: item for item in capabilities},
    )


def _capability(
    key: str,
    *,
    max_rarity: int,
    modeled: bool = True,
    parameters: tuple[str, ...] = (),
) -> GcsimArtifactSetCapability:
    return GcsimArtifactSetCapability(
        key=key,
        package_name=key,
        key_constant=key.title(),
        max_rarity=max_rarity,
        registered=True,
        has_two_piece_code=True,
        has_four_piece_code=True,
        two_piece_modeled=True,
        four_piece_modeled=modeled,
        parameter_keys=parameters,
    )


if __name__ == "__main__":
    unittest.main()
