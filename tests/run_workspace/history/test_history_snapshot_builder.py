"""Backend-only History Snapshot builder fixtures.

These tests pin the first live RunSession/right-panel-view-model adapter. The
fixtures are synthetic by design: they must not read account DBs, generated app
data, real assets, caches, Qt widgets, or network state.
"""

from __future__ import annotations

from dataclasses import replace
import tempfile
import unittest
from pathlib import Path

from run_workspace.history_snapshot import (
    HISTORY_RUN_TYPE_ABYSS,
    HISTORY_RUN_TYPE_DPS_DUMMY,
    HistorySnapshotBundleStore,
    history_snapshot_bundle_from_json_text,
    history_snapshot_bundle_to_json_text,
)
from run_workspace.history_snapshot_builder import (
    RESULT_TYPE_FACTUAL_DPS,
    RESULT_TYPE_SIM_DPS,
    WARNING_DPS_DUMMY_FACTUAL_INPUTS_NOT_IMPLEMENTED,
    WARNING_RIGHT_PANEL_SLOT_MISSING,
    HistorySnapshotBuildContext,
    build_history_snapshot_bundle,
)
from run_workspace.models import AbyssTimerState
from run_workspace.right_panel_prototype_view_model import (
    FACT_DPS_HP_MODE_SOLO,
    MODE_ABYSS,
    MODE_DPS_DUMMY,
    MODE_TABS,
    FactDpsEnemyTooltipViewModel,
    FactDpsTooltipViewModel,
    GcsimTooltipViewModel,
    RightPanelBonusSourceDisplayItem,
    RightPanelBuildMiniSetViewModel,
    RightPanelChamberRowViewModel,
    RightPanelDetailRowViewModel,
    RightPanelGcsimChamberResult,
    RightPanelGcsimStatusViewModel,
    RightPanelPrototypeViewModel,
    RightPanelSelectedDetailsViewModel,
    RightPanelSlotPrototypeViewModel,
    RightPanelTeamPrototypeViewModel,
)
from run_workspace.session import RunSessionController, RunSessionState
from run_workspace.team_card_view_model import TeamCardArtifactSummaryViewModel


class HistorySnapshotBuilderTests(unittest.TestCase):
    def test_builds_minimal_abyss_bundle_from_session_and_right_panel_model(self) -> None:
        session = RunSessionController.empty()
        model = _right_panel_model(
            mode=MODE_ABYSS,
            teams=_teams_vm(team_count=2),
            chamber_rows=_chamber_rows(),
        )

        bundle = build_history_snapshot_bundle(session.state, model, _context())

        self.assertEqual(bundle.run_type, HISTORY_RUN_TYPE_ABYSS)
        self.assertIsNotNone(bundle.scenario.abyss)
        self.assertEqual(len(bundle.teams), 2)
        self.assertEqual([len(team.slots) for team in bundle.teams], [4, 4])
        self.assertIsNone(bundle.teams[0].slots[0].character)
        self.assertEqual(len(bundle.scenario.abyss.chambers), 3)
        self.assertEqual(bundle.scenario.abyss.total_elapsed_seconds, 0)

    def test_builds_minimal_dps_dummy_bundle_without_inventing_factual_inputs(self) -> None:
        session = RunSessionController.empty()
        session.set_mode(MODE_DPS_DUMMY)
        model = _right_panel_model(mode=MODE_DPS_DUMMY, teams=_teams_vm(team_count=1))

        bundle = build_history_snapshot_bundle(session.state, model, _context())

        self.assertEqual(bundle.run_type, HISTORY_RUN_TYPE_DPS_DUMMY)
        self.assertEqual(len(bundle.teams), 1)
        scenario = bundle.scenario.dps_dummy
        self.assertEqual(scenario.result_status, "pending_factual_inputs")
        self.assertIsNone(scenario.target_hp)
        self.assertIsNone(scenario.duration_seconds)
        self.assertIsNone(scenario.factual_damage)
        self.assertIsNone(scenario.factual_dps)
        self.assertIn(WARNING_DPS_DUMMY_FACTUAL_INPUTS_NOT_IMPLEMENTED, bundle.warnings)

    def test_ordered_teams_and_slots_are_preserved(self) -> None:
        session = RunSessionController.empty()
        session.team_state = session.team_state.set_character(
            1,
            3,
            {"id": "10000089", "name": "Furina"},
        )
        model = _right_panel_model(
            mode=MODE_ABYSS,
            teams=_teams_vm(
                team_count=2,
                overrides={(1, 3): _slot_vm(1, 3, character_title="Furina")},
            ),
            chamber_rows=_chamber_rows(),
        )

        bundle = build_history_snapshot_bundle(session.state, model, _context())

        self.assertEqual([team.team_index for team in bundle.teams], [0, 1])
        self.assertEqual([slot.slot_index for slot in bundle.teams[1].slots], [0, 1, 2, 3])
        self.assertEqual(bundle.teams[1].slots[3].character.name, "Furina")

    def test_supplied_team_slot_build_stat_and_bonus_data_survives(self) -> None:
        session = RunSessionController.empty()
        details = _rich_details()
        session.team_state = (
            session.team_state.set_character(0, 0, {"id": "10000050", "name": "Thoma"})
            .set_weapon(0, 0, {"id": "13501", "name": "Favonius Lance"})
            .set_artifact_build(0, 0, {"build_id": 42, "build_name": "Shield support"})
            .attach_character_details_data(0, 0, details)
        )
        model = _right_panel_model(
            mode=MODE_ABYSS,
            teams=_teams_vm(overrides={(0, 0): _rich_slot_vm()}),
            selected_details=_rich_selected_details(),
            chamber_rows=_chamber_rows(),
        )

        bundle = build_history_snapshot_bundle(session.state, model, _context())
        slot = bundle.teams[0].slots[0]

        self.assertEqual(slot.character.character_id, "10000050")
        self.assertEqual(slot.character.level, 90)
        self.assertEqual(slot.character.portrait_ref, "assets/characters/thoma.png")
        self.assertEqual(slot.weapon.weapon_fingerprint, "favonius_lance|90|5")
        self.assertEqual(slot.weapon.stat_rows[0].label, "Base ATK")
        self.assertEqual(slot.weapon.passive_effects, ("Generates particles on CRIT.",))
        self.assertEqual(slot.artifact_build.build_id, "42")
        self.assertEqual(slot.artifact_build.artifact_slots[0].main_stat.value, "46.6%")
        self.assertEqual(slot.artifact_build.active_set_bonuses[0].effects, ("Shield Strength +30%",))
        self.assertEqual(slot.artifact_build.crit_value, 42.4)
        self.assertEqual(slot.artifact_build.proc_count, 9)
        self.assertEqual(slot.stat_rows[0].label, "HP")
        self.assertEqual(slot.bonus_sources[0].source_kind, "artifact_set_static")
        self.assertIn("assets/weapons/favonius_lance.png", {ref.path for ref in bundle.asset_refs})

    def test_abyss_timers_and_elapsed_totals_are_mapped_from_session(self) -> None:
        session = RunSessionController.empty()
        session.state = replace(
            session.state,
            abyss=replace(
                session.state.abyss,
                timer_states=(
                    AbyssTimerState(team1_left_seconds=540, team2_left_seconds=510),
                ),
            ),
        )
        model = _right_panel_model(
            mode=MODE_ABYSS,
            teams=_teams_vm(team_count=2),
            chamber_rows=_chamber_rows(count=1),
        )

        bundle = build_history_snapshot_bundle(session.state, model, _context())
        timer = bundle.scenario.abyss.chambers[0].timer

        self.assertEqual(timer.team1_left_seconds, 540)
        self.assertEqual(timer.team2_left_seconds, 510)
        self.assertEqual(timer.normalized_team1_left_seconds, 540)
        self.assertEqual(timer.normalized_team2_left_seconds, 510)
        self.assertEqual(timer.team1_elapsed_seconds, 60)
        self.assertEqual(timer.team2_elapsed_seconds, 30)
        self.assertEqual(timer.total_elapsed_seconds, 90)
        self.assertEqual(bundle.scenario.abyss.total_elapsed_seconds, 90)

    def test_abyss_period_metadata_maps_from_build_context_without_gcsim(self) -> None:
        session = RunSessionController.empty()
        model = _right_panel_model(
            mode=MODE_ABYSS,
            teams=_teams_vm(team_count=2),
            chamber_rows=_chamber_rows(count=1),
        )

        bundle = build_history_snapshot_bundle(
            session.state,
            model,
            _context(
                abyss_period_start="2026-06-16",
                abyss_period_end="2026-07-01",
                abyss_floor=12,
                abyss_target_mode=FACT_DPS_HP_MODE_SOLO,
            ),
        )

        scenario = bundle.scenario.abyss
        self.assertEqual(scenario.period_start, "2026-06-16")
        self.assertEqual(scenario.period_end, "2026-07-01")
        self.assertEqual(scenario.floor, 12)
        self.assertEqual(scenario.target_mode, FACT_DPS_HP_MODE_SOLO)

    def test_factual_dps_tooltip_maps_to_factual_results_and_enemy_payload(self) -> None:
        session = RunSessionController.empty()
        tooltip = _fact_tooltip()
        model = _right_panel_model(
            mode=MODE_ABYSS,
            teams=_teams_vm(team_count=2),
            chamber_rows=(_chamber_row(1, factual_team1_tooltip=tooltip),),
        )

        bundle = build_history_snapshot_bundle(session.state, model, _context())
        side_result = bundle.scenario.abyss.chambers[0].side_results[0]
        factual_summary = [
            item
            for item in bundle.result_summaries
            if item.result_type == RESULT_TYPE_FACTUAL_DPS
        ][0]

        self.assertEqual(side_result.total_hp, 6_000_000)
        self.assertEqual(side_result.factual_dps, 100_000)
        self.assertEqual(side_result.hp_source, "Nanoka")
        self.assertEqual(factual_summary.payload["hp_mode"], FACT_DPS_HP_MODE_SOLO)
        self.assertEqual(bundle.scenario.abyss.chambers[0].enemies[0]["primary_display_name"], "Ruin Guard")
        self.assertIn("assets/enemies/ruin_guard.png", {ref.path for ref in bundle.asset_refs})

    def test_gcsim_runtime_result_maps_to_sim_summary_separate_from_factual_dps(self) -> None:
        session = RunSessionController.empty()
        session.gcsim_chamber_results = (_gcsim_result(),)
        model = _right_panel_model(
            mode=MODE_ABYSS,
            teams=_teams_vm(team_count=2),
            chamber_rows=(_chamber_row(1, factual_team1_tooltip=_fact_tooltip()),),
        )

        bundle = build_history_snapshot_bundle(session.state, model, _context())
        summary_types = {item.result_type for item in bundle.result_summaries}
        sim_summary = [
            item
            for item in bundle.result_summaries
            if item.result_type == RESULT_TYPE_SIM_DPS
        ][0]

        self.assertEqual(summary_types, {RESULT_TYPE_FACTUAL_DPS, RESULT_TYPE_SIM_DPS})
        self.assertEqual(sim_summary.dps, 123456.0)
        self.assertEqual(sim_summary.payload["status"], "run_passed")
        self.assertEqual(sim_summary.payload["config_path"], "runtime/config.txt")
        self.assertEqual(
            bundle.scenario.abyss.chambers[0].side_results[0].sim_result_ref,
            "sim:1:1:0",
        )

    def test_missing_optional_right_panel_slot_warns_without_crashing(self) -> None:
        session = RunSessionController.empty()
        session.team_state = session.team_state.set_character(
            0,
            0,
            {"id": "10000050", "name": "Thoma"},
        )
        model = _right_panel_model(
            mode=MODE_ABYSS,
            teams=(),
            chamber_rows=_chamber_rows(),
        )

        bundle = build_history_snapshot_bundle(session.state, model, _context())

        self.assertIn(WARNING_RIGHT_PANEL_SLOT_MISSING, bundle.warnings)
        self.assertIn(WARNING_RIGHT_PANEL_SLOT_MISSING, bundle.teams[0].slots[0].warnings)
        self.assertEqual(bundle.teams[0].slots[0].character.name, "Thoma")

    def test_built_bundle_roundtrips_through_store(self) -> None:
        session = RunSessionController.empty()
        model = _right_panel_model(
            mode=MODE_ABYSS,
            teams=_teams_vm(team_count=2),
            chamber_rows=_chamber_rows(),
        )
        bundle = build_history_snapshot_bundle(session.state, model, _context())

        with tempfile.TemporaryDirectory() as tmp:
            store = HistorySnapshotBundleStore(Path(tmp) / "history-root")
            store.write_bundle(bundle)
            read_back = store.read_bundle(bundle.bundle_id)

        self.assertEqual(read_back.to_dict(), bundle.to_dict())
        json_roundtrip = history_snapshot_bundle_from_json_text(
            history_snapshot_bundle_to_json_text(bundle)
        )
        self.assertEqual(json_roundtrip.to_dict(), bundle.to_dict())


def _context(
    **overrides: object,
) -> HistorySnapshotBuildContext:
    data = {
        "bundle_id": "builder-test-bundle",
        "created_at": "2026-06-13T12:00:00Z",
        "source": "unit_test",
        "content_language": "en-us",
        "account": {
            "account_uid": "700000001",
            "nickname": "Tester",
            "source": "fixture",
        },
    }
    data.update(overrides)
    return HistorySnapshotBuildContext(
        **data,
    )


def _right_panel_model(
    *,
    mode: str,
    teams: tuple[RightPanelTeamPrototypeViewModel, ...],
    selected_details: RightPanelSelectedDetailsViewModel | None = None,
    chamber_rows: tuple[RightPanelChamberRowViewModel, ...] = (),
) -> RightPanelPrototypeViewModel:
    return RightPanelPrototypeViewModel(
        mode=mode,
        mode_tabs=MODE_TABS,
        teams=teams,
        selected_details=selected_details or RightPanelSelectedDetailsViewModel(False),
        chamber_headers=(),
        chamber_rows=chamber_rows,
        total_seconds=sum(row.total_seconds for row in chamber_rows),
        gcsim_status=RightPanelGcsimStatusViewModel(status="GCSIM: not run"),
    )


def _teams_vm(
    *,
    team_count: int = 2,
    overrides: dict[tuple[int, int], RightPanelSlotPrototypeViewModel] | None = None,
) -> tuple[RightPanelTeamPrototypeViewModel, ...]:
    overrides = overrides or {}
    return tuple(
        RightPanelTeamPrototypeViewModel(
            team_index=team_index,
            slots=tuple(
                overrides.get((team_index, slot_index))
                or _slot_vm(team_index, slot_index)
                for slot_index in range(4)
            ),
        )
        for team_index in range(team_count)
    )


def _slot_vm(
    team_index: int,
    slot_index: int,
    *,
    character_title: str = "",
) -> RightPanelSlotPrototypeViewModel:
    is_empty = not character_title
    return RightPanelSlotPrototypeViewModel(
        team_index=team_index,
        slot_index=slot_index,
        is_empty=is_empty,
        is_selected=False,
        character_title=character_title,
        character_meta="",
        portrait_label=character_title[:2],
        portrait_path="",
        weapon_label="",
        weapon_square_label="",
        weapon_image_path="",
        weapon_tooltip="",
        build_label="",
        artifact_square_label="",
        artifact_image_path="",
        build_mini_sets=(),
        stat_badge="",
        warning_count=0,
        warning_tooltip="",
    )


def _rich_slot_vm() -> RightPanelSlotPrototypeViewModel:
    return RightPanelSlotPrototypeViewModel(
        team_index=0,
        slot_index=0,
        is_empty=False,
        is_selected=True,
        character_title="Thoma",
        character_meta="Lv.90 | C6 | Pyro",
        portrait_label="Th",
        portrait_path="assets/characters/thoma.png",
        weapon_label="Favonius Lance",
        weapon_square_label="FL",
        weapon_image_path="assets/weapons/favonius_lance.png",
        weapon_tooltip="Generates particles on CRIT.",
        build_label="Shield support",
        artifact_square_label="ART",
        artifact_image_path="assets/artifacts/sands.png",
        build_mini_sets=(
            RightPanelBuildMiniSetViewModel(
                set_uid="retracing_bolide",
                set_name="Retracing Bolide",
                piece_count=2,
                owned_count=2,
                icon_path="assets/sets/retracing_bolide.png",
            ),
        ),
        stat_badge="HP",
        warning_count=0,
        warning_tooltip="",
        artifact_summary=TeamCardArtifactSummaryViewModel(
            active_sets=("2p Retracing Bolide",),
            crit_value=42.4,
            proc_count=9,
            missing_positions=(1, 2, 4, 5),
            warnings=("artifact_build_incomplete",),
        ),
    )


def _rich_selected_details() -> RightPanelSelectedDetailsViewModel:
    return RightPanelSelectedDetailsViewModel(
        has_selection=True,
        team_index=0,
        slot_index=0,
        character_name="Thoma",
        character_level=90,
        constellation=6,
        element="Pyro",
        weapon_name="Favonius Lance",
        weapon_level=90,
        weapon_refinement=5,
        weapon_base_atk="565",
        weapon_secondary_label="ER",
        weapon_secondary_value="30.6%",
        weapon_icon_path="assets/weapons/favonius_lance.png",
        crit_value=42.4,
        active_sets=("2p Retracing Bolide",),
        stat_rows=(
            RightPanelDetailRowViewModel(label="HP", value="34,250", icon_label="HP"),
            RightPanelDetailRowViewModel(label="ER", value="221%", icon_label="ER"),
        ),
        bonus_sources=(
            RightPanelBonusSourceDisplayItem(
                source_kind="artifact_set_static",
                source_id="retracing_bolide:2",
                label="2p",
                icon_path="assets/sets/retracing_bolide.png",
                short_effects=("Shield Strength +30%",),
                tooltip_effects=("Shield Strength +30%",),
                tooltip_title="Retracing Bolide 2p",
                applied=True,
            ),
        ),
        weapon_tooltip="Generates particles on CRIT.",
    )


def _rich_details() -> dict[str, object]:
    return {
        "account_character": {
            "id": "10000050",
            "name": "Thoma",
            "level": 90,
            "element": "Pyro",
            "rarity": 4,
            "constellation": 6,
            "icon_path": "assets/characters/thoma.png",
        },
        "account_weapon": {
            "id": "13501",
            "name": "Favonius Lance",
            "level": 90,
            "promote_level": 6,
            "rarity": 4,
            "refinement": 5,
            "weapon_type": "Polearm",
            "weapon_fingerprint": "favonius_lance|90|5",
            "icon_path": "assets/weapons/favonius_lance.png",
        },
        "selected_build": {
            "build_id": 42,
            "build_name": "Shield support",
            "source": "current_equipment",
        },
        "stat_snapshot": {
            "artifact": {
                "summary": {
                    "slots": [
                        {
                            "pos": 3,
                            "artifact_id": 100,
                            "name": "Sands of Eon",
                            "set_uid": "retracing_bolide",
                            "set_name": "Retracing Bolide",
                            "set_icon_path": "assets/sets/retracing_bolide.png",
                            "rarity": 5,
                            "level": 20,
                            "main_property_name": "HP",
                            "main_property_value": "46.6%",
                            "substats": [
                                {
                                    "label": "Energy Recharge",
                                    "value": "11.0%",
                                    "key": "ER",
                                },
                            ],
                        },
                    ],
                    "active_set_bonuses": [
                        {
                            "set_uid": "retracing_bolide",
                            "set_name": "Retracing Bolide",
                            "piece_count": 2,
                            "owned_count": 2,
                        },
                    ],
                    "crit_value": 42.4,
                    "proc_count": 9,
                    "missing_positions": [1, 2, 4, 5],
                },
                "warnings": ["artifact_build_incomplete"],
            },
        },
        "artifact_set_display_stat_effects": [
            {
                "set_uid": "retracing_bolide",
                "pieces_required": 2,
                "label": "Shield Strength +30%",
            },
        ],
    }


def _chamber_rows(count: int = 3) -> tuple[RightPanelChamberRowViewModel, ...]:
    return tuple(_chamber_row(index) for index in range(1, count + 1))


def _chamber_row(
    chamber_index: int,
    *,
    factual_team1_tooltip: FactDpsTooltipViewModel | None = None,
    sim_team1_tooltip: GcsimTooltipViewModel | None = None,
) -> RightPanelChamberRowViewModel:
    return RightPanelChamberRowViewModel(
        chamber_label=f"C{chamber_index}",
        team1_time="10:00",
        team1_seconds=0,
        team2_time="10:00",
        team2_seconds=0,
        factual_team1="-" if factual_team1_tooltip is None else "100,000",
        factual_team2="-",
        sim_team1="not run",
        sim_team2="not run",
        total_seconds=0,
        timer_editable=True,
        factual_team1_tooltip=factual_team1_tooltip,
        sim_team1_tooltip=sim_team1_tooltip,
    )


def _fact_tooltip() -> FactDpsTooltipViewModel:
    return FactDpsTooltipViewModel(
        title="Fact DPS / F12 / C1 / Team 1",
        formula="HP / time",
        total_hp=6_000_000,
        total_solo_hp=6_000_000,
        total_multi_target_hp=7_000_000,
        hp_mode=FACT_DPS_HP_MODE_SOLO,
        hp_mode_label="Solo",
        elapsed_seconds=60,
        calculated_dps=100_000,
        hp_source_label="Nanoka",
        enemies=(
            FactDpsEnemyTooltipViewModel(
                wave=1,
                primary_display_name="Ruin Guard",
                enemy_count=1,
                display_level=95,
                matched_nanoka_display_name="Ruin Guard",
                hp_used=6_000_000,
                hp_source="nanoka",
                match_method="id",
                match_confidence="high",
                cached_icon_path="assets/enemies/ruin_guard.png",
                selected_for_solo=True,
            ),
        ),
    )


def _gcsim_result() -> RightPanelGcsimChamberResult:
    return RightPanelGcsimChamberResult(
        chamber=1,
        team_index=0,
        side=1,
        status="run_passed",
        clear_time_seconds=48.5,
        dps_mean=123456.0,
        total_damage_mean=5_987_616.0,
        scenario_total_hp=6_000_000.0,
        config_path="runtime/config.txt",
        scenario_path="runtime/scenario.json",
        mode=MODE_ABYSS,
        period_start="2026-06-01",
        floor=12,
        target_mode=FACT_DPS_HP_MODE_SOLO,
        rotation_hash="rotation-1",
    )


if __name__ == "__main__":
    unittest.main()
