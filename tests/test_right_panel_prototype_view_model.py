from __future__ import annotations

import json
import unittest

from run_workspace.right_panel_prototype_view_model import (
    MODE_ABYSS,
    MODE_DPS_DUMMY,
    build_fake_right_panel_prototype_state,
    build_right_panel_prototype_view_model,
)
from run_workspace.team_builder import create_empty_team_builder_state


class RightPanelPrototypeViewModelTest(unittest.TestCase):
    def test_abyss_model_has_two_four_slot_rows_without_team_headers(self) -> None:
        state = build_fake_right_panel_prototype_state()

        model = build_right_panel_prototype_view_model(state, mode=MODE_ABYSS)

        self.assertEqual(model.schema_version, 6)
        self.assertEqual(model.mode, MODE_ABYSS)
        self.assertEqual(len(model.teams), 2)
        self.assertEqual([len(team.slots) for team in model.teams], [4, 4])
        self.assertEqual(model.mode_tabs, ("Abyss", "DPS Dummy"))
        self.assertIn("Fact T1 DPS", model.chamber_headers)
        self.assertIn("Sim T2 DPS", model.chamber_headers)
        self.assertNotIn("title", model.teams[0].to_dict())

    def test_filled_slot_keeps_compact_regions_and_warning_count(self) -> None:
        state = build_fake_right_panel_prototype_state()

        model = build_right_panel_prototype_view_model(
            state,
            selected_team_index=0,
            selected_slot_index=0,
        )
        slot = model.teams[0].slots[0]
        slot_dict = slot.to_dict()

        self.assertFalse(slot.is_empty)
        self.assertEqual(slot.character_title, "Thoma")
        self.assertEqual(slot.portrait_label, "TH")
        self.assertEqual(slot.portrait_path, "")
        self.assertIn("Favonius Lance", slot.weapon_label)
        self.assertEqual(slot.weapon_square_label, "FL")
        self.assertEqual(slot.build_label, "Build #20: test111")
        self.assertEqual([item.piece_count for item in slot.build_mini_sets], [2, 2])
        self.assertEqual(slot.build_mini_sets[0].set_name, "Silken Moon")
        self.assertEqual(slot.stat_badge, "ER/PYRO")
        self.assertEqual(slot.warning_count, 1)
        self.assertIn("имеющиеся артефакты всё равно считаются", slot.warning_tooltip)
        self.assertNotIn("warnings", slot_dict)
        self.assertNotIn("warnings", slot_dict["artifact_summary"])

    def test_empty_slot_placeholder_exists(self) -> None:
        state = build_fake_right_panel_prototype_state()

        model = build_right_panel_prototype_view_model(state)
        slot = model.teams[1].slots[3]

        self.assertTrue(slot.is_empty)
        self.assertEqual(slot.character_title, "Empty slot")
        self.assertEqual(slot.portrait_label, "+")
        self.assertEqual(slot.stat_badge, "EMPTY")

    def test_slot_warning_count_hides_decorative_model_warnings(self) -> None:
        state = create_empty_team_builder_state(team_count=1)
        state = state.set_character(
            0,
            0,
            {"id": "10000024", "name": "Beidou", "level": 70, "element": "Electro"},
        )
        state = state.attach_character_details_data(
            0,
            0,
            {
                "account_character": {"id": "10000024", "name": "Beidou"},
                "warnings": (
                    "account_weapon_identity_no_source_instance_id",
                    "account_weapon_observed_stack_not_full_inventory",
                    "final_totals_not_computed",
                    "set_bonus_formulas_not_included",
                    "conditional_set_bonuses_not_included",
                ),
            },
        )

        model = build_right_panel_prototype_view_model(state)
        slot = model.teams[0].slots[0]

        self.assertEqual(slot.warning_count, 0)
        self.assertEqual(slot.warning_tooltip, "")

    def test_filled_slot_without_selected_build_uses_equip_placeholder(self) -> None:
        state = create_empty_team_builder_state(team_count=1)
        state = state.set_character(
            0,
            0,
            {
                "id": "10000034",
                "name": "Noelle",
                "level": 90,
                "element": "Geo",
                "constellation": 6,
            },
        )
        state = state.set_weapon(
            0,
            0,
            {"id": "12401", "name": "Favonius Greatsword", "level": 90, "refinement": 5},
        )
        state = state.attach_character_details_data(
            0,
            0,
            {
                "account_character": {
                    "id": "10000034",
                    "name": "Noelle",
                    "level": 90,
                    "element": "Geo",
                    "constellation": 6,
                },
                "account_weapon": {
                    "id": "12401",
                    "name": "Favonius Greatsword",
                    "level": 90,
                    "refinement": 5,
                },
                "account_stat_sheet": {
                    "base_properties": [
                        {"property_type": 2000, "base": "12071", "add": "20000", "final": "32071"},
                        {"property_type": 2001, "base": "699", "add": "20000", "final": "20699"},
                        {"property_type": 2002, "base": "799", "add": "20000", "final": "20799"},
                    ],
                    "extra_properties": [
                        {"property_type": 20, "base": "99.9%", "add": "", "final": "99.9%"},
                        {"property_type": 22, "base": "199.9%", "add": "", "final": "199.9%"},
                        {"property_type": 23, "base": "199.9%", "add": "", "final": "199.9%"},
                    ],
                    "weapon": {
                        "main_property": {"property_type": 4, "base": "", "add": "", "final": "454"},
                        "sub_property": {"property_type": 23, "base": "", "add": "", "final": "61.3%"},
                    },
                },
            },
        )

        model = build_right_panel_prototype_view_model(state)
        slot = model.teams[0].slots[0]

        self.assertFalse(slot.is_empty)
        self.assertEqual(slot.build_label, "")
        self.assertEqual(slot.artifact_square_label, "Equip")
        self.assertEqual(slot.build_mini_sets, ())
        self.assertEqual(slot.stat_badge, "NO BUILD")
        self.assertTrue(model.selected_details.has_selection)
        self.assertIn(
            {"label": "HP", "value": "12071", "icon_label": "HP"},
            [row.to_dict() for row in model.selected_details.stat_rows],
        )
        self.assertNotIn(
            {"label": "HP", "value": "32071", "icon_label": "HP"},
            [row.to_dict() for row in model.selected_details.stat_rows],
        )

    def test_build_mini_stack_is_data_driven_from_active_set_metadata(self) -> None:
        state = create_empty_team_builder_state(team_count=1)
        state = state.set_character(0, 0, {"id": "1", "name": "First"})
        state = state.set_artifact_build(0, 0, {"build_id": 1, "build_name": "Four Piece"})
        state = state.attach_character_details_data(
            0,
            0,
            {
                "account_character": {"id": "1", "name": "First"},
                "selected_build": {"build_id": 1, "build_name": "Four Piece"},
                "stat_snapshot": {
                    "artifact": {
                        "summary": {
                            "active_set_bonuses": [
                                {
                                    "set_uid": "NoblesseOblige",
                                    "set_name": "Noblesse Oblige",
                                    "piece_count": 4,
                                    "owned_count": 4,
                                }
                            ],
                        }
                    }
                },
            },
        )
        state = state.set_character(0, 1, {"id": "2", "name": "Second"})
        state = state.set_artifact_build(0, 1, {"build_id": 2, "build_name": "No Bonus"})
        state = state.attach_character_details_data(
            0,
            1,
            {
                "account_character": {"id": "2", "name": "Second"},
                "selected_build": {"build_id": 2, "build_name": "No Bonus"},
                "stat_snapshot": {"artifact": {"summary": {"active_set_bonuses": []}}},
            },
        )

        model = build_right_panel_prototype_view_model(state)
        first = model.teams[0].slots[0]
        second = model.teams[0].slots[1]

        self.assertEqual(len(first.build_mini_sets), 1)
        self.assertEqual(first.build_mini_sets[0].set_uid, "NoblesseOblige")
        self.assertEqual(first.build_mini_sets[0].piece_count, 4)
        self.assertEqual(second.build_mini_sets, ())

    def test_stat_badge_uses_selected_build_sands_and_goblet_slots(self) -> None:
        state = create_empty_team_builder_state(team_count=1)
        state = state.set_character(
            0,
            0,
            {"id": "10000050", "name": "Thoma", "element": "Pyro"},
        )
        state = state.set_artifact_build(0, 0, {"build_id": 20, "build_name": "test111"})
        state = state.attach_character_details_data(
            0,
            0,
            {
                "account_character": {"id": "10000050", "name": "Thoma", "element": "Pyro"},
                "display_stats": ["HP 22173", "ER 142.7%"],
                "stat_snapshot": {
                    "artifact": {
                        "summary": {
                            "slots": [
                                {"pos": 3, "main_property_type": 23, "main_property_name": "ER"},
                                {"pos": 4, "main_property_type": 28, "main_property_name": "EM"},
                            ],
                            "active_set_bonuses": [],
                            "missing_positions": [],
                        }
                    }
                },
            },
        )

        model = build_right_panel_prototype_view_model(state)
        slot = model.teams[0].slots[0]

        self.assertEqual(slot.stat_badge, "ER/EM")
        self.assertNotEqual(slot.stat_badge, "HP/PYRO")

    def test_stat_badge_does_not_invent_missing_build_main_stats(self) -> None:
        state = create_empty_team_builder_state(team_count=1)
        state = state.set_character(0, 0, {"id": "1", "name": "Partial", "element": "Pyro"})
        state = state.set_artifact_build(0, 0, {"build_id": 2, "build_name": "Partial Build"})
        state = state.attach_character_details_data(
            0,
            0,
            {
                "account_character": {"id": "1", "name": "Partial", "element": "Pyro"},
                "display_stats": ["HP 10000"],
                "stat_snapshot": {
                    "artifact": {
                        "summary": {
                            "slots": [
                                {"pos": 3, "main_property_type": 23, "main_property_name": "ER"},
                            ],
                            "missing_positions": [4],
                        }
                    }
                },
            },
        )

        model = build_right_panel_prototype_view_model(state)
        slot = model.teams[0].slots[0]

        self.assertEqual(slot.stat_badge, "ER/-")
        self.assertNotEqual(slot.stat_badge, "HP/PYRO")

    def test_chamber_rows_align_timers_and_dps_placeholders(self) -> None:
        state = build_fake_right_panel_prototype_state()

        model = build_right_panel_prototype_view_model(state, mode=MODE_ABYSS)
        first = model.chamber_rows[0]

        self.assertEqual(first.chamber_label, "C1")
        self.assertEqual(first.team1_time, "09:47")
        self.assertEqual(first.team1_seconds, 13)
        self.assertEqual(first.team2_time, "09:25")
        self.assertEqual(first.team2_seconds, 22)
        self.assertEqual(first.factual_team1, "-")
        self.assertEqual(first.factual_team2, "-")
        self.assertEqual(first.sim_team1, "not run")
        self.assertEqual(first.sim_team2, "not run")
        self.assertEqual(model.total_seconds, 635)
        self.assertEqual(
            model.chamber_headers,
            (
                "Ch.",
                "T1",
                "T2",
                "Fact T1 DPS",
                "Fact T2 DPS",
                "Sim T1 DPS",
                "Sim T2 DPS",
            ),
        )

    def test_selected_details_are_structured_rows_not_text_dump(self) -> None:
        state = build_fake_right_panel_prototype_state()

        model = build_right_panel_prototype_view_model(
            state,
            selected_team_index=1,
            selected_slot_index=0,
        )
        details = model.selected_details

        self.assertTrue(details.has_selection)
        self.assertEqual(details.team_index, 1)
        self.assertEqual(details.slot_index, 0)
        self.assertEqual(details.character_name, "Raiden Shogun")
        self.assertEqual(details.character_level, 90)
        self.assertEqual(details.constellation, 2)
        self.assertEqual(details.weapon_name, "Engulfing Lightning")
        self.assertEqual(details.weapon_level, 90)
        self.assertEqual(details.weapon_refinement, 1)
        self.assertIn("4p Emblem", details.active_sets)
        self.assertIn(
            {"label": "ER", "value": "270%", "icon_label": "ER"},
            [row.to_dict() for row in details.stat_rows],
        )
        self.assertEqual(details.crit_value, 201.8)
        details_dict = details.to_dict()
        self.assertNotIn("metric_rows", details_dict)
        self.assertNotIn("proc_count", details_dict)
        self.assertNotIn("missing_positions", details_dict)
        self.assertNotIn("build_name", details_dict)

    def test_selected_details_hide_raw_warnings_and_omit_zero_stats(self) -> None:
        state = build_fake_right_panel_prototype_state()

        model = build_right_panel_prototype_view_model(
            state,
            selected_team_index=0,
            selected_slot_index=0,
        )
        details_dict = model.selected_details.to_dict()
        details_json = json.dumps(details_dict, ensure_ascii=False)

        self.assertNotIn("warnings", details_dict)
        self.assertNotIn("warning_count", details_dict)
        self.assertNotIn("warning_tooltip", details_dict)
        self.assertNotIn("final_totals_not_computed", details_json)
        self.assertNotIn("gcsim_config_generation_not_implemented", details_json)
        self.assertNotIn(
            {"label": "DEF", "value": "0", "icon_label": "DEF"},
            details_dict["stat_rows"],
        )

    def test_selected_details_expose_available_snapshot_stats_and_portrait_path(self) -> None:
        state = create_empty_team_builder_state(team_count=1)
        state = state.set_character(
            0,
            0,
            {
                "id": "10000050",
                "name": "Thoma",
                "level": 70,
                "element": "Pyro",
                "constellation": 6,
            },
        )
        state = state.set_weapon(
            0,
            0,
            {"id": "13407", "name": "Favonius Lance", "level": 70, "refinement": 5},
        )
        state = state.set_artifact_build(0, 0, {"build_id": 20, "build_name": "test111"})
        state = state.attach_character_details_data(
            0,
            0,
            {
                "status": "ready",
                "portrait_path": "assets/hoyolab/characters/char_057.png",
                "weapon_image_path": "assets/hoyolab/weapons/weapon_025.png",
                "artifact_image_path": "assets/artifact_sets/EmblemOfSeveredFate_1.png",
                "build_mini_sets": [
                    {
                        "set_uid": "EmblemOfSeveredFate",
                        "set_name": "Emblem of Severed Fate",
                        "piece_count": 2,
                        "owned_count": 2,
                        "icon_path": "assets/artifact_sets/EmblemOfSeveredFate_1.png",
                    },
                    {
                        "set_uid": "SilkenMoonsSerenade",
                        "set_name": "Silken Moon",
                        "piece_count": 2,
                        "owned_count": 2,
                        "icon_path": "assets/artifact_sets/SilkenMoonsSerenade_1.png",
                    },
                ],
                "account_character": {
                    "id": "10000050",
                    "name": "Thoma",
                    "level": 70,
                    "element": "Pyro",
                    "constellation": 6,
                },
                "account_weapon": {
                    "id": "13407",
                    "name": "Favonius Lance",
                    "level": 70,
                    "refinement": 5,
                },
                "account_stat_sheet": {
                    "base_properties": [
                        {"property_type": 2000, "base": "8440", "add": "13732", "final": "22173"},
                        {"property_type": 2001, "base": "594", "add": "550", "final": "1143"},
                        {"property_type": 2002, "base": "613", "add": "274", "final": "887"},
                    ],
                    "extra_properties": [
                        {"property_type": 28, "base": "187", "add": "", "final": "187"},
                        {"property_type": 20, "base": "54.8%", "add": "", "final": "54.8%"},
                        {"property_type": 22, "base": "63.2%", "add": "", "final": "63.2%"},
                        {"property_type": 23, "base": "142.7%", "add": "", "final": "142.7%"},
                    ],
                    "element_properties": [
                        {"property_type": 40, "base": "46.6%", "add": "", "final": "46.6%"},
                        {"property_type": 42, "base": "0.0%", "add": "", "final": "0.0%"},
                    ],
                    "selected_properties": [],
                    "weapon": {
                        "main_property": {"property_type": 4, "base": "", "add": "", "final": "999"},
                        "sub_property": {"property_type": 23, "base": "", "add": "", "final": "99.9%"},
                        "desc": "Reference text",
                    },
                },
                "stat_snapshot": {
                    "character_base": {
                        "base_hp": {"selected": "8440"},
                        "base_atk": {"selected": "165"},
                        "base_def": {"selected": "0"},
                        "ascension_bonus_stat_type": "ATK",
                        "ascension_bonus": {"selected": "18.0%"},
                    },
                    "weapon": {
                        "base_atk": {"selected": "429"},
                        "secondary_stat_type": "Energy Recharge",
                        "secondary_stat_value": "25.2%",
                    },
                    "artifact": {
                        "summary": {
                            "slots": [
                                {"pos": 3, "main_property_type": 23, "main_property_name": "ER"},
                                {"pos": 4, "main_property_type": 28, "main_property_name": "EM"},
                            ],
                            "stat_totals": [
                                {"property_type": 20, "raw_value": 31.1},
                                {"property_type": 22, "raw_value": 33.4},
                                {"property_type": 28, "raw_value": 187},
                            ],
                            "crit_value": 95.6,
                        }
                    },
                },
            },
        )

        model = build_right_panel_prototype_view_model(state)
        slot = model.teams[0].slots[0]
        detail_rows = [row.to_dict() for row in model.selected_details.stat_rows]

        self.assertEqual(slot.portrait_path, "assets/hoyolab/characters/char_057.png")
        self.assertEqual(slot.weapon_image_path, "assets/hoyolab/weapons/weapon_025.png")
        self.assertEqual([item.piece_count for item in slot.build_mini_sets], [2, 2])
        self.assertEqual(
            slot.build_mini_sets[0].icon_path,
            "assets/artifact_sets/EmblemOfSeveredFate_1.png",
        )
        self.assertEqual(slot.stat_badge, "ER/EM")
        self.assertEqual(model.selected_details.weapon_base_atk, "429")
        self.assertEqual(model.selected_details.weapon_secondary_label, "ER")
        self.assertEqual(model.selected_details.weapon_secondary_value, "25.2%")
        self.assertIn({"label": "HP", "value": "8440", "icon_label": "HP"}, detail_rows)
        self.assertIn({"label": "ATK", "value": "701", "icon_label": "ATK"}, detail_rows)
        self.assertIn({"label": "DEF", "value": "613", "icon_label": "DEF"}, detail_rows)
        self.assertIn({"label": "EM", "value": "187", "icon_label": "EM"}, detail_rows)
        self.assertIn(
            {"label": "Crit Rate", "value": "36.1%", "icon_label": "CR"},
            detail_rows,
        )
        self.assertIn(
            {"label": "Crit DMG", "value": "83.4%", "icon_label": "CD"},
            detail_rows,
        )
        self.assertIn({"label": "ER", "value": "125.2%", "icon_label": "ER"}, detail_rows)
        self.assertNotIn({"label": "HP", "value": "22173", "icon_label": "HP"}, detail_rows)
        self.assertNotIn({"label": "ATK", "value": "1143", "icon_label": "ATK"}, detail_rows)
        self.assertNotIn({"label": "DEF", "value": "887", "icon_label": "DEF"}, detail_rows)
        self.assertNotIn({"label": "Pyro DMG", "value": "46.6%", "icon_label": "PYRO"}, detail_rows)
        self.assertNotIn(
            {"label": "Hydro DMG", "value": "0.0%", "icon_label": "HYD"},
            detail_rows,
        )
        self.assertNotIn({"label": "Base HP", "value": "8440", "icon_label": "HP"}, detail_rows)
        self.assertNotIn({"label": "Weapon ATK", "value": "429", "icon_label": "WATK"}, detail_rows)
        self.assertNotIn({"label": "Art CR", "value": "31.1%", "icon_label": "ACR"}, detail_rows)

    def test_selected_details_expose_bonus_source_items_and_toggle_state(self) -> None:
        state = create_empty_team_builder_state(team_count=1)
        state = state.set_character(0, 0, {"id": "1", "name": "Bonus Tester"})
        state = state.set_weapon(0, 0, {"id": "13407", "name": "Static Spear"})
        state = state.set_artifact_build(0, 0, {"build_id": 1, "build_name": "Static Build"})
        state = state.attach_character_details_data(
            0,
            0,
            {
                "account_character": {"id": "1", "name": "Bonus Tester", "base_hp": 1000},
                "account_weapon": {
                    "id": "13407",
                    "name": "Static Spear",
                    "level": 70,
                    "refinement": 2,
                    "base_atk": 429,
                    "icon_path": "assets/hoyolab/weapons/static_spear.png",
                },
                "stat_snapshot": {
                    "artifact": {
                        "summary": {
                            "active_set_bonuses": [
                                {
                                    "set_uid": "EmblemOfSeveredFate",
                                    "set_name": "Emblem of Severed Fate",
                                    "piece_count": 2,
                                    "owned_count": 2,
                                    "icon_path": "assets/artifact_sets/EmblemOfSeveredFate_1.png",
                                }
                            ]
                        }
                    }
                },
                "artifact_set_display_stat_effects": [
                    {
                        "set_uid": "EmblemOfSeveredFate",
                        "pieces_required": 2,
                        "stat_key": "ENERGY_RECHARGE",
                        "value": 20,
                        "value_type": "percent_points",
                        "description": "Energy Recharge +20%",
                    }
                ],
                "weapon_display_stat_effects": [
                    {
                        "weapon_id": 13407,
                        "refinement": 2,
                        "stat_key": "HP_PERCENT",
                        "value": 20,
                        "value_type": "percent_points",
                    }
                ],
                "weapon_passive_reference": {
                    "passive_name": "Static passive",
                    "passive_text": "Increases HP by 20%.",
                    "language": "en-us",
                },
            },
        )

        enabled_model = build_right_panel_prototype_view_model(state)
        disabled_model = build_right_panel_prototype_view_model(
            state,
            external_bonuses_enabled=False,
        )

        self.assertEqual(
            [
                (item.source_kind, item.short_effects, item.applied)
                for item in enabled_model.selected_details.bonus_sources
            ],
            [
                ("artifact_set_static", ("ER +20%",), True),
                ("weapon_passive_static", ("HP +20%",), True),
            ],
        )
        self.assertFalse(disabled_model.selected_details.external_bonuses_enabled)
        self.assertTrue(
            all(not item.applied for item in disabled_model.selected_details.bonus_sources)
        )
        self.assertEqual(
            disabled_model.selected_details.bonus_sources[0].not_applied_reason,
            "Внешние бонусы отключены",
        )
        weapon_bonus = enabled_model.selected_details.bonus_sources[1]
        self.assertEqual(weapon_bonus.tooltip_title, "Static Spear R2")
        self.assertIn("Lv.70", weapon_bonus.tooltip_body)
        self.assertIn("ATK 429", weapon_bonus.tooltip_body)
        self.assertIn("Static passive", weapon_bonus.tooltip_body)
        self.assertNotIn("Effects:", weapon_bonus.tooltip_body)
        self.assertIn("Static Spear", enabled_model.selected_details.weapon_tooltip)
        self.assertEqual(
            enabled_model.selected_details.weapon_icon_path,
            "assets/hoyolab/weapons/static_spear.png",
        )
        self.assertIn("Static passive", enabled_model.selected_details.weapon_tooltip)
        self.assertIn("Lv.70", enabled_model.selected_details.weapon_tooltip)
        self.assertIn("ATK 429", enabled_model.selected_details.weapon_tooltip)
        self.assertNotIn("Effects:", enabled_model.selected_details.weapon_tooltip)
        self.assertNotIn("Rarity:", enabled_model.selected_details.weapon_tooltip)

    def test_weapon_tooltip_uses_passive_reference_not_weapon_flavor_description(self) -> None:
        state = create_empty_team_builder_state()
        state = state.set_character(
            0,
            0,
            {"id": "10000050", "name": "Thoma", "element": "Pyro"},
        )
        state = state.set_weapon(
            0,
            0,
            {
                "id": 13407,
                "name": "Favonius Lance",
                "rarity": 4,
                "level": 70,
                "refinement": 5,
                "description": "A polearm made in the style of the Knights of Favonius.",
            },
        )
        state = state.attach_character_details_data(
            0,
            0,
            {
                "account_weapon": {
                    "id": 13407,
                    "name": "Favonius Lance",
                    "rarity": 4,
                    "level": 70,
                    "refinement": 5,
                    "description": "A polearm made in the style of the Knights of Favonius.",
                },
                "weapon_passive_reference": {
                    "passive_name": "Windfall",
                    "passive_text": "CRIT Hits have a chance to generate Elemental Particles.",
                    "language": "en-us",
                },
            },
        )

        model = build_right_panel_prototype_view_model(state)
        tooltip = model.selected_details.weapon_tooltip

        self.assertIn("Favonius Lance R5", tooltip)
        self.assertIn("Windfall", tooltip)
        self.assertIn("Elemental Particles", tooltip)
        self.assertNotIn("A polearm made", tooltip)
        self.assertNotIn("Rarity:", tooltip)

    def test_dps_dummy_model_shows_one_team_and_single_chamber_row(self) -> None:
        state = build_fake_right_panel_prototype_state()

        model = build_right_panel_prototype_view_model(state, mode=MODE_DPS_DUMMY)

        self.assertEqual(model.mode, MODE_DPS_DUMMY)
        self.assertEqual(len(model.teams), 1)
        self.assertEqual(model.chamber_rows[0].chamber_label, "Dummy")
        self.assertEqual(model.chamber_rows[0].factual_team1, "128k")
        self.assertEqual(model.chamber_rows[0].sim_team1, "not run")
        self.assertIn("GCSIM", model.gcsim_status.status)

    def test_model_does_not_depend_on_legacy_image_path_slots(self) -> None:
        state = build_fake_right_panel_prototype_state()

        model = build_right_panel_prototype_view_model(state)

        self.assertFalse(
            _contains_forbidden_key(
                model.to_dict(),
                {"image_path", "icon", "local_path", "warnings"},
            )
        )


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, dict):
        return any(
            key in forbidden or _contains_forbidden_key(item, forbidden)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


if __name__ == "__main__":
    unittest.main()
