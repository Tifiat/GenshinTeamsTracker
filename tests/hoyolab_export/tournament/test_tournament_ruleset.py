import tempfile
import unittest
from pathlib import Path

from hoyolab_export.tournament_ruleset import (
    WARNING_CHARACTER_AMBIGUOUS,
    WARNING_CHARACTER_UNMATCHED,
    WARNING_DUPLICATE_CHARACTER_COST,
    WARNING_DUPLICATE_WEAPON_COST,
    WARNING_MISSING_CHARACTER_NAME,
    WARNING_UNKNOWN_TIER_RESTRICTION_TYPE,
    WARNING_UNSUPPORTED_SCRIPT_RULE,
    WARNING_WEAPON_UNMATCHED,
    load_tournament_ruleset_from_csv_paths,
    tournament_ruleset_from_mapping,
    validate_tournament_ruleset,
)
from hoyolab_export.tournament_ruleset_report import build_ruleset_validation_report


class TournamentRulesetTests(unittest.TestCase):
    def test_parse_normalized_ruleset(self):
        ruleset = tournament_ruleset_from_mapping(
            {
                "schema_version": 1,
                "name": "Local test",
                "characters": [
                    {
                        "character_id": "10000021",
                        "name": "Amber",
                        "rarity": 4,
                        "weapon_type": "BOW",
                        "costs_by_constellation": {"0": 1, "6": 3},
                        "level_95_extra_cost": 1,
                        "level_100_extra_cost": 2,
                    }
                ],
                "weapons": [
                    {
                        "weapon_id": "fav-warbow",
                        "name": "Favonius Warbow",
                        "weapon_type": "BOW",
                        "rarity": 4,
                        "costs_by_refinement": {"1": 1, "5": 2},
                    }
                ],
                "tiers": [
                    {
                        "name": "Tier 0",
                        "points_start": 0,
                        "points_end": 14,
                        "restrictions": [
                            {
                                "restriction_type": "QUANTIDADE_TIER",
                                "comparison_tier": "Tier 1",
                                "value": 1,
                            }
                        ],
                    }
                ],
                "draft_config": {
                    "challenge_type": "ABISMO",
                    "deck_point_limit": 70,
                    "initial_bans": 3,
                    "weapon_ban_location": "SEM_BAN",
                },
            }
        )

        self.assertEqual(ruleset.characters[0].character_id, "10000021")
        self.assertEqual(ruleset.characters[0].costs_by_constellation[6], 3.0)
        self.assertEqual(ruleset.weapons[0].weapon_id, "fav-warbow")
        self.assertEqual(ruleset.weapons[0].costs_by_refinement[5], 2.0)
        self.assertEqual(ruleset.draft_config.deck_point_limit, 70.0)
        self.assertEqual(ruleset.tiers[0].restrictions[0].restriction_type, "QUANTIDADE_TIER")

    def test_parse_gentor_like_ruleset_shape(self):
        ruleset = tournament_ruleset_from_mapping(
            {
                "nome": "Gentor-like test",
                "personagens": [
                    {
                        "id": "row-1",
                        "personagem": {
                            "id": "char-amber",
                            "nome": "Amber",
                            "elemento": "PYRO",
                            "raridade": 4,
                            "arma": "BOW",
                        },
                        "valorC0": 1,
                        "valorC6": 3,
                        "custoAdicionalNivel95": 1,
                        "custoAdicionalNivel100": 2,
                    }
                ],
                "armas": [
                    {
                        "id": "row-w1",
                        "arma": {
                            "id": "weapon-1",
                            "nome": "Favonius Warbow",
                            "tipo": "BOW",
                            "raridade": 4,
                        },
                        "valorR1": 1,
                        "valorR5": 2,
                        "personagens": [
                            {
                                "personagem": {"nome": "Amber"},
                                "valorR1": 0,
                                "valorR5": 1,
                            }
                        ],
                    }
                ],
                "tiers": [
                    {
                        "nome": "Tier 0",
                        "pontuacaoInicio": 0,
                        "pontuacaoFim": 10,
                        "restricoes": [
                            {
                                "tipo": "SOMA_EQUIVALENTE",
                                "tierComparacao": {"nome": "Tier 1"},
                                "valorComparacao": 2,
                            }
                        ],
                    }
                ],
                "configuracao": {
                    "desafio": "ABISMO",
                    "limitePontosPersonagens": 70,
                    "baseBansIniciais": 2,
                    "localBanArma": "ANTES_PICK",
                    "quantidadeBansArma": 1,
                    "script": {"codigo": "custom draft script"},
                },
            }
        )

        self.assertEqual(ruleset.name, "Gentor-like test")
        self.assertEqual(ruleset.characters[0].character_id, "char-amber")
        self.assertEqual(ruleset.characters[0].costs_by_constellation[6], 3.0)
        self.assertEqual(ruleset.weapons[0].weapon_id, "weapon-1")
        self.assertEqual(ruleset.weapon_overrides[0].character_name, "Amber")
        self.assertEqual(ruleset.draft_config.weapon_ban_location, "ANTES_PICK")
        self.assertTrue(ruleset.draft_config.script_code)

    def test_validation_reports_duplicates_missing_unknown_and_scripts(self):
        ruleset = tournament_ruleset_from_mapping(
            {
                "name": "Validation test",
                "characters": [
                    {"name": "Amber", "c0": 1},
                    {"name": "Amber", "c0": 2},
                    {"name": "", "c0": 3},
                ],
                "weapons": [
                    {"name": "Favonius Warbow", "r1": 1},
                    {"name": "Favonius Warbow", "r1": 2},
                ],
                "tiers": [
                    {
                        "name": "Odd",
                        "restrictions": [{"restriction_type": "CUSTOM_SCRIPT_ONLY"}],
                    }
                ],
                "draft_config": {"script_code": "not used"},
            }
        )

        report = validate_tournament_ruleset(ruleset)
        self.assertEqual(report.warnings[WARNING_DUPLICATE_CHARACTER_COST], 1)
        self.assertEqual(report.warnings[WARNING_MISSING_CHARACTER_NAME], 1)
        self.assertEqual(report.warnings[WARNING_DUPLICATE_WEAPON_COST], 1)
        self.assertEqual(report.warnings[WARNING_UNKNOWN_TIER_RESTRICTION_TYPE], 1)
        self.assertEqual(report.warnings[WARNING_UNSUPPORTED_SCRIPT_RULE], 1)

    def test_validation_reports_catalog_unmatched_and_ambiguous(self):
        ruleset = tournament_ruleset_from_mapping(
            {
                "characters": [{"name": "Amber"}, {"name": "Noelle"}],
                "weapons": [{"name": "Favonius Warbow"}],
            }
        )

        report = validate_tournament_ruleset(
            ruleset,
            character_catalog=[
                {"name": "Amber", "entry_page_id": "1"},
                {"name": "Amber", "entry_page_id": "2"},
            ],
            weapon_catalog=[],
        )
        self.assertEqual(report.warnings[WARNING_CHARACTER_AMBIGUOUS], 1)
        self.assertEqual(report.warnings[WARNING_CHARACTER_UNMATCHED], 1)
        self.assertEqual(report.warnings[WARNING_WEAPON_UNMATCHED], 1)

    def test_load_csv_ruleset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            characters_csv = temp_path / "characters.csv"
            weapons_csv = temp_path / "weapons.csv"
            tiers_csv = temp_path / "tiers.csv"
            characters_csv.write_text(
                "name,c0,c6,level_95_extra_cost\nAmber,1,3,1\n",
                encoding="utf-8",
            )
            weapons_csv.write_text(
                "name,r1,r5,weapon_type\nFavonius Warbow,1,2,BOW\n",
                encoding="utf-8",
            )
            tiers_csv.write_text(
                "name,points_start,points_end\nTier 0,0,10\n",
                encoding="utf-8",
            )

            ruleset = load_tournament_ruleset_from_csv_paths(
                name="CSV test",
                characters_csv=characters_csv,
                weapons_csv=weapons_csv,
                tiers_csv=tiers_csv,
            )

        self.assertEqual(ruleset.characters[0].name, "Amber")
        self.assertEqual(ruleset.characters[0].costs_by_constellation[6], 3.0)
        self.assertEqual(ruleset.weapons[0].costs_by_refinement[5], 2.0)
        self.assertEqual(ruleset.tiers[0].name, "Tier 0")

    def test_validation_report_shape_is_sanitized(self):
        ruleset = tournament_ruleset_from_mapping(
            {
                "name": "Report test",
                "characters": [{"name": "Amber", "c0": 1}],
                "draft_config": {"script_code": "local custom script"},
            }
        )

        report = build_ruleset_validation_report(ruleset)

        self.assertEqual(report["ruleset"]["name"], "Report test")
        self.assertTrue(report["ruleset"]["script_code_present"])
        self.assertNotIn("local custom script", str(report))
        self.assertEqual(
            report["validation"]["warnings"][WARNING_UNSUPPORTED_SCRIPT_RULE],
            1,
        )


if __name__ == "__main__":
    unittest.main()
