from __future__ import annotations

from pathlib import Path
import statistics
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from ui.utils import character_card_layers
from ui.pvp_browser import window as pvp_browser_window
from run_workspace.pvp.deck import (
    DRAFT_DECK_KIND,
    DRAFT_DECK_SCHEMA_VERSION,
    DraftCharacter,
    DraftDeck,
)
from run_workspace.pvp.free_draft_controller import FreeDraftController
from run_workspace.pvp.free_draft_controller import FreeDraftControllerActionRejected
from run_workspace.pvp.schedule import ACTION_BAN_CHARACTER, ACTION_PICK_CHARACTER
from ui.pvp_browser.window import (
    PVP_DRAFT_STAGE_TIMERS_RESULTS,
    PVP_PAGE_DRAFT,
    PvpActiveDraftSession,
    PvpWorkspace,
)
from ui.right_panel.pvp.host import PvpRightPanelHost
from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()


class PvpDraftPerformanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_warmed_pick_ban_refresh_projects_once_and_skips_hidden_play_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace, controller = _workspace_with_synthetic_session(
                root,
                roster_count=78,
            )
            host = PvpRightPanelHost(workspace)
            workspace.resize(1120, 760)
            host.resize(390, 760)
            workspace.show()
            host.show()
            self.application.processEvents()

            self.assertIs(host.stack.currentWidget(), host.draft_panel)
            self.assertIs(workspace.draft_workspace._draft_board, workspace.draft_board_dict())
            shared_assets = workspace._shared_character_assets()
            asset_map = workspace.draft_workspace._character_assets_by_id
            portrait_map = workspace.draft_workspace._portrait_paths_by_character_id
            workspace._sync_draft_workspace()
            self.assertIs(workspace.draft_workspace._character_assets_by_id, asset_map)
            self.assertIs(workspace.draft_workspace._portrait_paths_by_character_id, portrait_map)

            checked_paths: list[Path] = []
            real_is_file = Path.is_file

            def counted_is_file(path: Path) -> bool:
                checked_paths.append(path)
                return real_is_file(path)

            with patch.object(Path, "is_file", counted_is_file):
                for _ in range(3):
                    self.assertIs(workspace._shared_character_assets(), shared_assets)
            self.assertEqual(checked_paths, [])

            current_board = workspace.draft_board_dict()
            legal_id = workspace.draft_workspace.legal_character_ids[0]
            rejected_payload = workspace.draft_workspace._draft_actions_by_character_id[
                legal_id
            ]
            with patch.object(
                controller,
                "apply_current_action",
                side_effect=FreeDraftControllerActionRejected(
                    "synthetic_rejection",
                    "Synthetic rejected backend action.",
                ),
            ):
                self.assertFalse(workspace.apply_draft_card_click(rejected_payload))
            self.assertIs(workspace.draft_board_dict(), current_board)

            refreshed_assets = workspace._shared_character_assets()
            workspace.refresh_account_data(emit_signal=False)
            self.assertIsNot(workspace._shared_character_assets(), refreshed_assets)

            deck_checks = Mock(wraps=workspace.deck_start_status)
            period_checks = Mock(wraps=workspace.period_admission)
            with (
                patch.object(workspace, "deck_start_status", deck_checks),
                patch.object(workspace, "period_admission", period_checks),
            ):
                metrics = _measure_warmed_actions(
                    workspace,
                    controller,
                    self.application,
                    action_limit=8,
                )

            self.assertIn(ACTION_BAN_CHARACTER, metrics["action_types"])
            self.assertIn(ACTION_PICK_CHARACTER, metrics["action_types"])
            self.assertEqual(metrics["projection_counts"], [1] * len(metrics["action_types"]))
            self.assertEqual(metrics["portrait_resolutions_by_action"], [0] * len(metrics["action_types"]))
            self.assertEqual(metrics["full_resets_by_action"], [0] * len(metrics["action_types"]))
            self.assertEqual(deck_checks.call_count, 0)
            self.assertEqual(period_checks.call_count, 0)
            self.assertGreaterEqual(len(metrics["timings_ms"][ACTION_BAN_CHARACTER]), 2)
            self.assertGreaterEqual(len(metrics["timings_ms"][ACTION_PICK_CHARACTER]), 2)
            self.assertLess(
                statistics.median(metrics["timings_ms"][ACTION_BAN_CHARACTER]),
                150.0,
            )
            self.assertLess(
                statistics.median(metrics["timings_ms"][ACTION_PICK_CHARACTER]),
                150.0,
            )
            print(
                "warmed draft action medians ms: "
                f"ban={statistics.median(metrics['timings_ms'][ACTION_BAN_CHARACTER]):.2f}, "
                f"pick={statistics.median(metrics['timings_ms'][ACTION_PICK_CHARACTER]):.2f}; "
                f"board projections/action={metrics['projection_counts']}; "
                f"pool full resets/action={metrics['full_resets_by_action']}; "
                f"pool incremental calls/action={metrics['incremental_calls_by_action']}"
            )

            host.hide()
            workspace.hide()
            host.deleteLater()
            workspace.deleteLater()
            self.application.processEvents()

    def test_timer_input_updates_locally_without_global_panel_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace, _controller = _workspace_with_synthetic_session(Path(temporary))
            workspace.draft_stage = PVP_DRAFT_STAGE_TIMERS_RESULTS
            workspace._sync_draft_workspace()
            workspace.set_page(PVP_PAGE_DRAFT)
            host = PvpRightPanelHost(workspace)
            timer_widget = workspace.draft_workspace._timers_result_widget
            self.assertIsNotNone(timer_widget)

            state_changes: list[None] = []
            workspace.state_changed.connect(lambda: state_changes.append(None))
            deck_checks = Mock(wraps=workspace.deck_start_status)
            period_checks = Mock(wraps=workspace.period_admission)
            with (
                patch.object(workspace, "deck_start_status", deck_checks),
                patch.object(workspace, "period_admission", period_checks),
            ):
                self.assertTrue(
                    timer_widget.set_timer_seconds_for_test("player_1", 0, 540)
                )
                self.application.processEvents()

            self.assertEqual(workspace.timer_texts_by_seat["player_1"][0], "09:00")
            self.assertIn("60", timer_widget.total_labels["player_1"].text())
            self.assertEqual(state_changes, [])
            self.assertEqual(deck_checks.call_count, 0)
            self.assertEqual(period_checks.call_count, 0)

            host.hide()
            workspace.hide()
            host.deleteLater()
            workspace.deleteLater()
            self.application.processEvents()

    def test_profile_switch_invalidates_cached_shared_portrait_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace, _controller = _workspace_with_synthetic_session(Path(temporary))
            workspace.clear_active_draft()
            previous_assets = workspace._shared_character_assets()
            remote_provider = _DisposableProfileProvider()
            workspace._profile_providers_by_seat["player_2"] = remote_provider
            workspace._shared_character_assets()

            workspace.use_local_profile_for_seat("player_2")

            self.assertTrue(remote_provider.closed)
            self.assertIsNot(workspace._shared_character_assets(), previous_assets)
            workspace.deleteLater()
            self.application.processEvents()

    def test_78_card_pool_resolves_each_distinct_layer_once_per_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace, _controller = _workspace_with_synthetic_session(
                Path(temporary),
                roster_count=78,
            )
            board = workspace.draft_board_dict()
            entries = board["unified_pool"]["entries"]
            self.assertEqual(len(entries), 78)
            self.assertEqual(len({entry["rarity"] for entry in entries}), 2)
            self.assertEqual(len({entry["element"] for entry in entries}), 7)

            rarity_layer_resolver = Mock(
                wraps=character_card_layers.character_background_path
            )
            element_layer_resolver = Mock(
                wraps=character_card_layers.filter_icon_path
            )
            with (
                patch.object(
                    character_card_layers,
                    "character_background_path",
                    rarity_layer_resolver,
                ),
                patch.object(
                    character_card_layers,
                    "filter_icon_path",
                    element_layer_resolver,
                ),
            ):
                for _index in range(2):
                    rarity_layer_resolver.reset_mock()
                    element_layer_resolver.reset_mock()
                    workspace.draft_workspace._build_unified_pool(board, False)
                    self.assertEqual(rarity_layer_resolver.call_count, 2)
                    self.assertEqual(element_layer_resolver.call_count, 7)

            workspace.deleteLater()
            self.application.processEvents()

    def test_unchanged_draft_state_does_not_repolish_pool_widgets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace, _controller = _workspace_with_synthetic_session(Path(temporary))
            with patch.object(pvp_browser_window, "_refresh_qss") as refresh_qss:
                workspace.draft_workspace.refresh()
            refresh_qss.assert_not_called()
            workspace.deleteLater()
            self.application.processEvents()


def _workspace_with_synthetic_session(
    root: Path,
    *,
    roster_count: int = 24,
) -> tuple[PvpWorkspace, FreeDraftController]:
    root.mkdir(parents=True, exist_ok=True)
    portrait_path = root / "portrait.png"
    image = QImage(24, 24, QImage.Format.Format_ARGB32)
    image.fill(QColor("#c96b4f"))
    if not image.save(str(portrait_path)):
        raise AssertionError("Could not create the temporary portrait fixture")

    elements = ("Pyro", "Hydro", "Electro", "Cryo", "Anemo", "Geo", "Dendro")
    characters = tuple(
        DraftCharacter(
            character_id=str(20000000 + index),
            display_name=f"Synthetic {index}",
            element=elements[index % len(elements)],
            weapon_type="Sword",
            rarity=4 + (index % 2),
            level=90,
            constellation=6,
        )
        for index in range(roster_count)
    )
    deck_1 = DraftDeck(
        schema_version=DRAFT_DECK_SCHEMA_VERSION,
        kind=DRAFT_DECK_KIND,
        deck_name="Synthetic One",
        characters=characters,
    )
    deck_2 = DraftDeck(
        schema_version=DRAFT_DECK_SCHEMA_VERSION,
        kind=DRAFT_DECK_KIND,
        deck_name="Synthetic Two",
        characters=characters,
    )
    controller = FreeDraftController.from_decks(
        deck_1,
        deck_2,
        source_mode="synthetic_performance_fixture",
    )
    assets = [
        {
            "path": str(portrait_path),
            "filename": portrait_path.name,
            "metadata": {
                "character": {
                    "id": str(20000000 + index),
                    "name": f"Synthetic {index}",
                    "level": 90,
                    "rarity": 5,
                    "constellation": 6,
                    "element": "Pyro",
                    "weapon_type": 1,
                    "weapon_type_name": "Sword",
                    "portrait_path": str(portrait_path),
                }
            },
        }
        for index in range(roster_count)
    ]
    workspace = PvpWorkspace(
        db_path=root / "synthetic.sqlite",
        deck_dir=root / "decks",
        character_assets_provider=lambda: assets,
        weapon_assets_provider=lambda: [],
        abyss_period_provider=lambda: None,
        abyss_source_data_provider=lambda: None,
    )
    workspace.active_draft_session = PvpActiveDraftSession(
        player_1_deck_id="synthetic-one",
        player_1_deck_name=deck_1.deck_name,
        player_2_deck_id="synthetic-two",
        player_2_deck_name=deck_2.deck_name,
        controller=controller,
    )
    workspace.set_page(PVP_PAGE_DRAFT)
    return workspace, controller


class _DisposableProfileProvider:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _measure_warmed_actions(
    workspace: PvpWorkspace,
    controller: FreeDraftController,
    application: QApplication,
    *,
    action_limit: int,
) -> dict[str, object]:
    timings_ms: dict[str, list[float]] = {
        ACTION_BAN_CHARACTER: [],
        ACTION_PICK_CHARACTER: [],
    }
    projection_counts: list[int] = []
    action_types: list[str] = []
    original_projection = controller.to_board_dict
    pool_grid = workspace.draft_workspace.pool_grid
    if pool_grid is None:
        raise AssertionError("Synthetic draft pool grid was not created")
    full_set_calls = Mock(wraps=pool_grid.set_items)
    incremental_calls = Mock(wraps=pool_grid.set_items_incremental)
    portrait_resolver = Mock(wraps=pvp_browser_window._asset_image_path)
    full_resets_by_action: list[int] = []
    incremental_by_action: list[int] = []
    portrait_resolutions_by_action: list[int] = []
    with patch.object(controller, "to_board_dict", wraps=original_projection) as projection:
        with (
            patch.object(pool_grid, "set_items", full_set_calls),
            patch.object(pool_grid, "set_items_incremental", incremental_calls),
            patch.object(pvp_browser_window, "_asset_image_path", portrait_resolver),
        ):
            for _index in range(action_limit):
                board = workspace.draft_board_dict()
                requirement = board.get("current_requirement") or {}
                action_type = str(requirement.get("expected_action_type") or "")
                self_legal_ids = workspace.draft_workspace.legal_character_ids
                if not action_type or not self_legal_ids:
                    break
                projection.reset_mock()
                full_set_calls.reset_mock()
                incremental_calls.reset_mock()
                portrait_resolver.reset_mock()
                started = time.perf_counter_ns()
                clicked = workspace.draft_workspace.click_legal_character_for_test(
                    self_legal_ids[0]
                )
                application.processEvents()
                elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
                if not clicked:
                    raise AssertionError(f"Synthetic {action_type} card click failed")
                action_types.append(action_type)
                if action_type in timings_ms:
                    timings_ms[action_type].append(elapsed_ms)
                projection_counts.append(projection.call_count)
                full_resets_by_action.append(full_set_calls.call_count)
                incremental_by_action.append(incremental_calls.call_count)
                portrait_resolutions_by_action.append(portrait_resolver.call_count)
    return {
        "action_types": action_types,
        "projection_counts": projection_counts,
        "full_resets_by_action": full_resets_by_action,
        "incremental_calls_by_action": incremental_by_action,
        "portrait_resolutions_by_action": portrait_resolutions_by_action,
        "timings_ms": timings_ms,
    }


if __name__ == "__main__":
    unittest.main()
