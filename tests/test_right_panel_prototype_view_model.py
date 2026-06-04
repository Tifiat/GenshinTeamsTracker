from __future__ import annotations

import json
import unittest
from dataclasses import replace

from run_workspace.right_panel_prototype_view_model import (
    MODE_ABYSS,
    MODE_DPS_DUMMY,
    _format_hexerei_sections_for_tooltip,
    _hexerei_member_tooltip,
    _hexerei_source_tooltip_text,
    build_abyss_chamber_rows,
    build_fake_right_panel_prototype_state,
    build_right_panel_prototype_view_model,
)
from run_workspace.abyss.source_data import (
    load_abyss_floor12_source_data,
    rebuild_abyss_floor_source_data_with_rows,
)
from run_workspace.models import AbyssTimerState
from run_workspace.team_builder import create_empty_team_builder_state
from tests.abyss.test_source_data import (
    composition_report,
    fandom_row,
    nanoka_report,
    nanoka_row,
)


class RightPanelPrototypeViewModelTest(unittest.TestCase):
    def test_abyss_model_has_two_four_slot_rows_without_team_headers(self) -> None:
        state = build_fake_right_panel_prototype_state()

        model = build_right_panel_prototype_view_model(state, mode=MODE_ABYSS)

        self.assertEqual(model.schema_version, 7)
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
        self.assertEqual(
            first.build_mini_sets[0].icon_path,
            "assets/artifact_sets/NoblesseOblige_1.png",
        )
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

    def test_abyss_chamber_rows_show_cached_source_data_factual_dps_when_elapsed_exists(self) -> None:
        source_data = load_abyss_floor12_source_data(
            "2026-05-16",
            "119",
            composition_report=composition_report(
                "2026-05-16",
                [
                    fandom_row(
                        "Team 1 Enemy",
                        chamber=1,
                        side=1,
                        wave=1,
                        count=3,
                        level=100,
                    ),
                    fandom_row(
                        "Team 2 Enemy",
                        chamber=1,
                        side=2,
                        wave=1,
                        count=4,
                        level=100,
                    ),
                ],
            ),
            nanoka_report=nanoka_report(
                "119",
                [
                    nanoka_row(
                        "Team 1 Enemy",
                        chamber=1,
                        side=1,
                        hp=1_200_000,
                        monster_id="team1",
                        level=100,
                    ),
                    nanoka_row(
                        "Team 2 Enemy",
                        chamber=1,
                        side=2,
                        hp=900_000,
                        monster_id="team2",
                        level=100,
                    ),
                ],
            ),
        )
        rows = build_abyss_chamber_rows(
            (
                AbyssTimerState(
                    team1_left_seconds=480,
                    team2_left_seconds=300,
                ),
            ),
            abyss_source_data=source_data,
        )

        row = rows[0]

        self.assertEqual(row.chamber_label, "C1")
        self.assertEqual(row.team1_seconds, 120)
        self.assertEqual(row.team2_seconds, 180)
        self.assertEqual(row.factual_team1, "10,000")
        self.assertEqual(row.factual_team2, "5,000")
        self.assertEqual(row.sim_team1, "not run")
        self.assertEqual(row.sim_team2, "not run")
        self.assertEqual(source_data.side_summary(1, 1).multi_target_hp, 3_600_000)

    def test_abyss_factual_dps_tooltip_carries_formula_and_enemy_breakdown(self) -> None:
        source_data = load_abyss_floor12_source_data(
            "2026-05-16",
            "119",
            composition_report=composition_report(
                "2026-05-16",
                [
                    fandom_row(
                        "Primo Geovishap (Cryo)",
                        chamber=1,
                        side=1,
                        wave=1,
                        count=2,
                        level=100,
                    ),
                ],
            ),
            nanoka_report=nanoka_report(
                "119",
                [
                    nanoka_row(
                        "Primo Geovishap",
                        chamber=1,
                        side=1,
                        hp=3_747_864,
                        monster_id="primo",
                        level=100,
                    ),
                ],
            ),
        )
        source_data = rebuild_abyss_floor_source_data_with_rows(
            source_data,
            (
                replace(
                    source_data.enemy_rows[0],
                    cached_icon_path="C:/cache/abyss/primo.png",
                ),
            ),
        )

        rows = build_abyss_chamber_rows(
            (AbyssTimerState(team1_left_seconds=540, team2_left_seconds=540),),
            abyss_source_data=source_data,
        )

        row = rows[0]
        tooltip = row.factual_team1_tooltip
        self.assertIsNotNone(tooltip)
        assert tooltip is not None
        self.assertEqual(row.factual_team1, "62,464")
        self.assertEqual(tooltip.title, "Floor 12 / C1 / Team 1")
        self.assertEqual(tooltip.total_solo_hp, 3_747_864)
        self.assertEqual(tooltip.elapsed_seconds, 60)
        self.assertEqual(tooltip.calculated_dps, 62_464)
        self.assertEqual(tooltip.unavailable_reason, "")
        self.assertEqual(tooltip.hp_source_label, "Nanoka resolved HP")
        self.assertEqual(len(tooltip.enemies), 1)
        enemy = tooltip.enemies[0]
        self.assertEqual(enemy.primary_display_name, "Primo Geovishap (Cryo)")
        self.assertEqual(enemy.matched_nanoka_display_name, "Primo Geovishap")
        self.assertEqual(enemy.enemy_count, 2)
        self.assertEqual(enemy.hp_used, 3_747_864)
        self.assertEqual(enemy.cached_icon_path, "C:/cache/abyss/primo.png")
        self.assertTrue(enemy.selected_for_solo)

    def test_abyss_chamber_rows_keep_factual_dps_unavailable_for_zero_elapsed(self) -> None:
        source_data = load_abyss_floor12_source_data(
            "2026-05-16",
            "119",
            composition_report=composition_report(
                "2026-05-16",
                [fandom_row("Enemy", chamber=1, side=1, wave=1, level=100)],
            ),
            nanoka_report=nanoka_report(
                "119",
                [
                    nanoka_row(
                        "Enemy",
                        chamber=1,
                        side=1,
                        hp=500_000,
                        monster_id="enemy",
                        level=100,
                    )
                ],
            ),
        )
        rows = build_abyss_chamber_rows(
            (
                AbyssTimerState(
                    team1_left_seconds=600,
                    team2_left_seconds=600,
                ),
            ),
            abyss_source_data=source_data,
        )

        row = rows[0]

        self.assertEqual(row.team1_seconds, 0)
        self.assertEqual(row.team2_seconds, 0)
        self.assertEqual(row.factual_team1, "-")
        self.assertEqual(row.factual_team2, "-")
        self.assertIsNotNone(row.factual_team1_tooltip)
        assert row.factual_team1_tooltip is not None
        self.assertEqual(
            row.factual_team1_tooltip.unavailable_reason,
            "Elapsed time is zero.",
        )
        self.assertEqual(row.factual_team1_tooltip.total_solo_hp, 500_000)

    def test_abyss_chamber_rows_keep_factual_dps_unavailable_without_cached_source_data(self) -> None:
        rows = build_abyss_chamber_rows(
            (
                AbyssTimerState(
                    team1_left_seconds=480,
                    team2_left_seconds=300,
                ),
            ),
            abyss_source_data=None,
        )

        row = rows[0]

        self.assertEqual(row.team1_seconds, 120)
        self.assertEqual(row.team2_seconds, 180)
        self.assertEqual(row.factual_team1, "-")
        self.assertEqual(row.factual_team2, "-")
        self.assertIsNotNone(row.factual_team1_tooltip)
        assert row.factual_team1_tooltip is not None
        self.assertEqual(
            row.factual_team1_tooltip.unavailable_reason,
            "Abyss source-data cache is unavailable.",
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
        artifact_bonus = enabled_model.selected_details.bonus_sources[0]
        self.assertEqual(artifact_bonus.tooltip_title, "Emblem of Severed Fate 2p")
        self.assertEqual(artifact_bonus.tooltip_body, "Energy Recharge +20%")
        self.assertNotIn("Effects:", artifact_bonus.tooltip_body)
        self.assertNotIn("Emblem of Severed Fate (2p)", artifact_bonus.tooltip_body)
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

    def test_elemental_resonance_chips_apply_direct_display_stats(self) -> None:
        cases = [
            ("Pyro", ("Pyro", "Pyro"), "elemental_resonance", "ATK +25%", "ATK", "375"),
            ("Hydro", ("Hydro", "Hydro"), "elemental_resonance", "HP +25%", "HP", "1250"),
            ("Cryo", ("Cryo", "Cryo"), "elemental_resonance", "CR +15%", "Crit Rate", "20%"),
            ("Geo", ("Pyro", "Geo", "Geo"), "elemental_resonance", "Pyro +15%", "Pyro DMG", "15%"),
        ]
        for _name, elements, source_kind, chip_label, stat_label, stat_value in cases:
            with self.subTest(elements=elements):
                state = _state_with_characters(elements)
                model = build_right_panel_prototype_view_model(state)

                chips = [
                    item
                    for item in model.selected_details.bonus_sources
                    if item.source_kind == source_kind
                ]
                rows = {row.label: row.value for row in model.selected_details.stat_rows}

                self.assertTrue(any(chip_label in item.short_effects for item in chips))
                self.assertEqual(rows[stat_label], stat_value)

    def test_dendro_resonance_uses_simplified_team_element_rule(self) -> None:
        cases = [
            (("Dendro", "Dendro"), "EM +50", "50"),
            (("Dendro", "Dendro", "Hydro"), "EM +80", "80"),
            (("Dendro", "Dendro", "Electro"), "EM +100", "100"),
            (("Dendro", "Dendro", "Hydro", "Pyro"), "EM +100", "100"),
        ]
        for elements, chip_label, em_value in cases:
            with self.subTest(elements=elements):
                state = _state_with_characters(elements)
                model = build_right_panel_prototype_view_model(state)
                chips = [
                    item
                    for item in model.selected_details.bonus_sources
                    if item.source_kind == "elemental_resonance"
                ]
                rows = {row.label: row.value for row in model.selected_details.stat_rows}

                self.assertTrue(any(chip_label in item.short_effects for item in chips))
                self.assertEqual(rows["EM"], em_value)

    def test_external_bonus_toggle_disables_elemental_resonance_stats(self) -> None:
        state = _state_with_characters(("Pyro", "Pyro"))

        model = build_right_panel_prototype_view_model(state, external_bonuses_enabled=False)
        rows = {row.label: row.value for row in model.selected_details.stat_rows}
        resonance = next(
            item for item in model.selected_details.bonus_sources
            if item.source_kind == "elemental_resonance"
        )

        self.assertEqual(rows["ATK"], "300")
        self.assertFalse(resonance.applied)
        self.assertEqual(resonance.not_applied_reason, "Внешние бонусы отключены")

    def test_moonsign_chip_is_lunar_indicator_not_normal_stat_row(self) -> None:
        state = _state_with_characters(
            ("Hydro", "Pyro", "Cryo"),
            traits_by_slot={0: ("moonsign",), 1: ("moonsign",)},
            base_by_slot={
                0: {"base_hp": 100000, "base_atk": 100, "base_def": 100},
                1: {"base_hp": 1000, "base_atk": 10000, "base_def": 100},
                2: {"base_hp": 1000, "base_atk": 100, "base_def": 100},
            },
        )

        model = build_right_panel_prototype_view_model(state)
        moonsign = next(
            item for item in model.selected_details.bonus_sources
            if item.source_kind == "moonsign"
        )
        rows = {row.label: row.value for row in model.selected_details.stat_rows}

        self.assertEqual(moonsign.short_effects, ("Lunar +36%",))
        self.assertIn("36%", moonsign.tooltip_body)
        self.assertIn("Hydro 0: Hydro HP 100000", moonsign.tooltip_body)
        self.assertIn("Pyro 1: Pyro ATK 10100", moonsign.tooltip_body)
        self.assertNotIn("Lunar", rows)

    def test_moonsign_reads_stats_after_direct_external_bonuses(self) -> None:
        state = _state_with_characters(
            ("Pyro", "Pyro", "Pyro"),
            traits_by_slot={0: ("moonsign",), 1: ("moonsign",)},
        )

        enabled_model = build_right_panel_prototype_view_model(state)
        disabled_model = build_right_panel_prototype_view_model(
            state,
            external_bonuses_enabled=False,
        )
        enabled = next(
            item for item in enabled_model.selected_details.bonus_sources
            if item.source_kind == "moonsign"
        )
        disabled = next(
            item for item in disabled_model.selected_details.bonus_sources
            if item.source_kind == "moonsign"
        )

        self.assertEqual(enabled.short_effects, ("Lunar +10.1%",))
        self.assertIn("Pyro 0: Pyro ATK 375", enabled.tooltip_body)
        self.assertEqual(disabled.short_effects, ("Lunar +8.1%",))
        self.assertFalse(disabled.applied)

    def test_moonsign_requires_two_moonsign_members(self) -> None:
        state = _state_with_characters(
            ("Hydro", "Pyro"),
            traits_by_slot={0: ("moonsign",)},
        )

        model = build_right_panel_prototype_view_model(state)

        self.assertFalse(
            any(item.source_kind == "moonsign" for item in model.selected_details.bonus_sources)
        )

    def test_moonsign_is_zero_without_non_moonsign_teammate(self) -> None:
        state = _state_with_characters(
            ("Hydro", "Pyro"),
            traits_by_slot={0: ("moonsign",), 1: ("moonsign",)},
        )

        model = build_right_panel_prototype_view_model(state)
        moonsign = next(
            item for item in model.selected_details.bonus_sources
            if item.source_kind == "moonsign"
        )

        self.assertEqual(moonsign.short_effects, ("Lunar +0%",))
        self.assertTrue(moonsign.applied)
        self.assertEqual(moonsign.not_applied_reason, "")
        self.assertIn("Moonsign", moonsign.tooltip_body)
        self.assertIn("0%", moonsign.tooltip_body)

    def test_hexerei_requires_two_members(self) -> None:
        state = _state_with_characters(
            ("Electro", "Pyro"),
            traits_by_slot={0: ("hexerei",)},
        )

        model = build_right_panel_prototype_view_model(state)

        self.assertFalse(
            any(item.source_kind == "hexerei" for item in model.selected_details.bonus_sources)
        )

    def test_hexerei_chip_is_display_only_for_two_members(self) -> None:
        state = _state_with_characters(
            ("Electro", "Pyro"),
            traits_by_slot={0: ("hexerei",), 1: ("hexerei",)},
        )

        model = build_right_panel_prototype_view_model(state)
        hexerei = next(
            item for item in model.selected_details.bonus_sources
            if item.source_kind == "hexerei"
        )
        rows = {row.label: row.value for row in model.selected_details.stat_rows}

        self.assertEqual(hexerei.label, "Hexerei")
        self.assertEqual(hexerei.short_effects, ())
        self.assertNotIn("Source:", hexerei.tooltip_body)
        self.assertNotIn("Member tooltips use cached", hexerei.tooltip_body)
        self.assertEqual(len(hexerei.character_tooltips), len(hexerei.character_icons))
        self.assertNotIn("Hexerei", rows)

    def test_hexerei_source_tooltip_uses_localized_ru_copy(self) -> None:
        title, body = _hexerei_source_tooltip_text("Мона, Сахароза", language="ru-ru")

        self.assertEqual(title, "Ведьмовство")
        self.assertNotIn("Участники:", body)
        self.assertIn("Справочный бонус отряда", body)
        self.assertNotIn("Source:", body)
        self.assertNotIn("Display/reference", body)

    def test_hexerei_source_tooltip_unknown_locale_falls_back_to_en(self) -> None:
        title, body = _hexerei_source_tooltip_text("Mona, Sucrose", language="xx-xx")

        self.assertEqual(title, "Hexerei")
        self.assertNotIn("Members:", body)
        self.assertIn("Display-only team reference", body)
        self.assertNotIn("Source:", body)

    def test_hexerei_source_tooltip_uses_portuguese_locale(self) -> None:
        title, body = _hexerei_source_tooltip_text("Mona, Sucrose", language="pt-br")

        self.assertEqual(title, "Hexerei")
        self.assertIn("Referência visual de bônus de equipe", body)
        self.assertIn("Não afeta os atributos", body)

    def test_hexerei_member_formatter_keeps_constellation_on_first_body_line(self) -> None:
        text = _format_hexerei_sections_for_tooltip(
            (
                {
                    "required_constellation": 0,
                    "section_index": 0,
                    "title": "Decorative Passive Title",
                    "body": "First body line.\nSecond paragraph.",
                },
            )
        )

        self.assertIn("C0: First body line.", text)
        self.assertNotIn("C0:\nFirst body line.", text)
        self.assertIn("Second paragraph.", text)
        self.assertNotIn("Decorative Passive Title", text)

    def test_hexerei_member_formatter_orders_mona_c4_and_hides_c6_when_filtered(self) -> None:
        text = _format_hexerei_sections_for_tooltip(
            (
                {
                    "required_constellation": 4,
                    "section_index": 0,
                    "title": "Пророчество забвения",
                    "body": "C4 body.",
                },
                {
                    "required_constellation": 0,
                    "section_index": 0,
                    "title": "Ведьмин ритуал кануна",
                    "body": "C0 body.",
                },
                {
                    "required_constellation": 2,
                    "section_index": 0,
                    "title": "Лунная цепь",
                    "body": "C2 body.",
                },
                {
                    "required_constellation": 1,
                    "section_index": 0,
                    "title": "Пророчество потопа",
                    "body": "C1 body.",
                },
            )
        )
        tooltip = _hexerei_member_tooltip(
            "Мона",
            text,
            source_url="https://wiki.hoyolab.com/pc/genshin/entry/9347",
            missing_text="missing",
            constellation=4,
        )

        self.assertLess(tooltip.index("C0:"), tooltip.index("C1:"))
        self.assertLess(tooltip.index("C1:"), tooltip.index("C2:"))
        self.assertLess(tooltip.index("C2:"), tooltip.index("C4:"))
        self.assertNotIn("C6:", tooltip)
        self.assertNotIn("Source:", tooltip)
        self.assertNotIn("Пророчество", tooltip)
        self.assertNotIn("Ведьмин ритуал", tooltip)

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


def _state_with_characters(
    elements: tuple[str, ...],
    *,
    traits_by_slot: dict[int, tuple[str, ...]] | None = None,
    base_by_slot: dict[int, dict[str, float]] | None = None,
):
    state = create_empty_team_builder_state(team_count=1)
    traits_by_slot = traits_by_slot or {}
    base_by_slot = base_by_slot or {}
    for index, element in enumerate(elements):
        base = {
            "base_hp": 1000.0,
            "base_atk": 200.0,
            "base_def": 500.0,
            **base_by_slot.get(index, {}),
        }
        character = {
            "id": str(10000000 + index),
            "name": f"{element} {index}",
            "element": element,
            "traits": list(traits_by_slot.get(index, ())),
            **base,
        }
        state = state.set_character(0, index, character)
        state = state.set_weapon(
            0,
            index,
            {"id": str(11000 + index), "name": "Test Weapon", "base_atk": 100},
        )
        state = state.attach_character_details_data(
            0,
            index,
            {
                "account_character": character,
                "account_weapon": {"name": "Test Weapon", "base_atk": 100},
            },
        )
    return state


if __name__ == "__main__":
    unittest.main()
