"""Play → two fresh drafts → results/PNG with disposable profiles only."""
from pathlib import Path
from unittest.mock import patch
import unittest

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from run_workspace.pvp.draft_options import DraftMatchOptions
from tests.ui.pvp_browser import test_preban_clock_flow as fixture_module
from tests.ui.pvp_browser.test_pvp_browser import _asset_character_id
from ui.right_panel.pvp.play.panel import PvpPlayRightPanel
from ui.right_panel.pvp.draft.panel import PvpDraftRightPanel


class TournamentSeriesFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_module.PrebanClockFlowTest.setUpClass()

    def setUp(self):
        self.fixture = fixture_module.PrebanClockFlowTest('test_timer_can_be_disabled_and_bad_penalties_block_start')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.workspace = self.fixture.workspace

    def finish_game(self, p1=30, p2=40):
        while not self.workspace.active_draft_session.controller.session_state.is_complete:
            self.assertTrue(self.workspace.apply_draft_card_click(self.fixture.action()))
        self.assertTrue(self.workspace.continue_to_assignment())
        for seat in ('player_1','player_2'):
            picked = self.workspace.active_draft_session.controller.session_state.picked_character_ids_for(seat)
            assets = {_asset_character_id(item):item for item in self.workspace._build_character_assets_for_seat(seat)}
            for index,cid in enumerate(picked):
                self.workspace.handle_build_slot_clicked(seat,index//4,index%4)
                self.assertTrue(self.workspace.handle_build_character_clicked(seat,assets[cid]))
                self.assertTrue(self.workspace.handle_build_weapon_clicked(seat,self.workspace.weapon_assets[0]))
            self.assertTrue(self.workspace.ready_build_seat(seat))
        for seat,elapsed in (('player_1',p1),('player_2',p2)):
            for index in range(3):
                self.workspace.set_timer_text(seat,index,f'9:{60-elapsed:02d}')
        self.assertTrue(self.workspace.finalize_match_result())

    def test_play_explicit_first_seat_and_two_fresh_drafts_alternate_without_swapping_profiles(self):
        play = PvpPlayRightPanel(self.workspace)
        self.addCleanup(play.close)
        play.first_seat_combo.setCurrentIndex(1)
        play.games_count_spin.setValue(2)
        play.start_button.click()
        original = self.workspace.active_draft_session
        self.assertEqual(original.controller.session_state.current_seat,'player_2')
        self.assertEqual(self.workspace.draft_clock_snapshot().active_seat,'player_2')
        self.assertFalse(self.workspace.start_next_series_game())
        self.finish_game()
        self.assertEqual(len(self.workspace.tournament_series.games),1)
        self.assertTrue(self.workspace.finalize_match_result())
        self.assertEqual(len(self.workspace.tournament_series.games),1)
        self.workspace.set_timer_text('player_1',0,'1:00')
        self.assertTrue(self.workspace.finalize_match_result())
        self.assertEqual(self.workspace.active_draft_session.controller.state.match_result.player_1_timers.total_elapsed_seconds,90)
        self.workspace._result_export_names = ('Alpha','Beta')
        panel = PvpDraftRightPanel(self.workspace)
        self.addCleanup(panel.close)
        self.assertFalse(panel.next_game_button.isHidden())
        panel.next_game_button.click()
        second = self.workspace.active_draft_session
        self.assertIsNot(second.controller,original.controller)
        self.assertEqual(second.controller.accepted_actions,())
        self.assertEqual(second.controller.session_state.current_seat,'player_1')
        self.assertEqual(second.controller.state.player_1_deck,original.controller.state.player_1_deck)
        self.assertEqual(second.controller.state.player_2_deck,original.controller.state.player_2_deck)
        self.assertEqual(second.controller.state.abyss_rules.content_hash,original.controller.state.abyss_rules.content_hash)
        self.assertEqual(self.workspace.restart_counts_by_seat,{'player_1':0,'player_2':0})
        self.assertEqual(self.workspace._result_export_names,('Alpha','Beta'))
        self.assertFalse(self.workspace.start_next_series_game())
        self.finish_game(40,30)
        self.assertTrue(self.workspace.tournament_series.complete)
        self.assertIsNone(self.workspace.tournament_series.winner_seat)
        self.assertTrue(panel.next_game_button.isHidden())
        output=Path(self.fixture.temp.name)/'series.png'
        with patch('ui.pvp_browser.window.QFileDialog.getSaveFileName',return_value=(str(output),'PNG')):
            self.assertTrue(self.workspace.export_match_result())
        image=QImage(str(output))
        self.assertFalse(image.isNull())
        self.assertGreater(image.height(),700)
        self.workspace.clear_active_draft()
        self.assertIsNone(self.workspace.tournament_series)
        self.assertFalse(self.workspace._draft_tick_timer.isActive())

    def test_cost_gap_prebans_keep_cheaper_seat_before_swapped_main_flow(self):
        self.fixture.save_rules(unequal=True)
        self.assertTrue(self.workspace.start_local_draft('local','second',
            match_options=DraftMatchOptions(first_seat='player_2')))
        self.assertEqual(self.workspace.draft_board_dict()['current_requirement']['active_seat'],'player_1')
        for _ in range(2):
            self.assertTrue(self.workspace.apply_draft_card_click(self.fixture.action()))
        self.assertEqual(self.workspace.draft_board_dict()['current_requirement']['active_seat'],'player_2')

    def test_alternation_can_be_disabled(self):
        self.assertTrue(self.workspace.start_local_draft('local','second',
            match_options=DraftMatchOptions(first_seat='player_2',games_count=2,alternate_first=False)))
        self.finish_game()
        self.assertTrue(self.workspace.start_next_series_game())
        self.assertEqual(self.workspace.draft_board_dict()['current_requirement']['active_seat'],'player_2')

    def test_short_setup_panel_can_scroll_to_start(self):
        panel=PvpPlayRightPanel(self.workspace)
        self.addCleanup(panel.close)
        panel.resize(354,480)
        panel.show()
        QApplication.instance().processEvents()
        self.assertGreater(panel.setup_scroll.verticalScrollBar().maximum(),0)
        panel.setup_scroll.ensureWidgetVisible(panel.start_button)
        QApplication.instance().processEvents()
        point=panel.start_button.mapTo(panel.setup_scroll.viewport(),panel.start_button.rect().center())
        self.assertTrue(panel.setup_scroll.viewport().rect().contains(point))
