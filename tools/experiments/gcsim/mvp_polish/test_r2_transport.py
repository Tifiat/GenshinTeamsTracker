"""Actual Go product -> worker/session readback -> AppShell text/page functions."""
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsRequest
from ui.gcsim_browser.run_worker import GcsimBrowserSelectedOptimizerWorker
from ui.gcsim_browser.optimizer_result import build_optimizer_result_pages
from ui.artifact_browser.models import ArtifactItem
from . import r2_staged_finalists as source
from .r2_result_text import format_staged_result

_APP = QApplication.instance() or QApplication([])


class R2TransportChecks(unittest.TestCase):
    def test_actual_mixed_wire_worker_and_display(self):
        from run_workspace.gcsim import optimizer_go_session as module
        import ui.app_shell as shell
        fixture = json.loads((source.OUT / 'mixed-ui-fixture-v1.json').read_bytes())
        request, wrapper = fixture['request'], fixture['wrapper']
        product = wrapper['product_result']
        class Process:
            returncode = 0
            stderr = io.StringIO('')
            def wait(self, timeout=None): return 0
            def poll(self): return 0
        with tempfile.TemporaryDirectory(prefix='r2-transport-') as temporary:
            root = Path(temporary)
            binary = root / 'never-execute.exe'
            binary.write_bytes(b'fixture boundary')
            worker = GcsimBrowserSelectedOptimizerWorker(GcsimOptimizerGoAllSetsRequest(
                db_path='', selected_team={}, team_index=0, rotation_shell_text='', optimizer_binary_path=str(binary)))
            session = worker._session
            def launch(*args, **kwargs):
                json.dump(wrapper, kwargs['stdout']);kwargs['stdout'].flush()
                return Process()
            with patch.object(module, 'start_optimizer_process', side_effect=launch), \
                    patch.object(session, '_register_process'), patch.object(session, '_unregister_process'), \
                    patch('subprocess.Popen', side_effect=AssertionError('real process forbidden')):
                result = session._run_go_optimizer(prepared={'request_sha256': product['request_sha256']},
                    compact={}, run_dir=root, started=time.monotonic())
            self.assertEqual(result, product)
            self.assertEqual([c['measured']['iterations'] for c in result['candidates']], [500, 100])
            self.assertEqual([c['measured']['standard_error'] for c in result['candidates']], ['1', '2'])
            payload = {'status': 'success', 'result': result, 'mode': 'all_sets', 'run_dir': str(root)}
            team = {'slots': [{'character': {'id': i+1, 'name': w['wearer_key']},
                'character_details_data': {'account_character': {'id': i+1, 'name': w['wearer_key'],
                    'gcsim_character_key': w['wearer_key']}}} for i, w in enumerate(request['wearers'])]}
            slots = ('flower', 'plume', 'sands', 'goblet', 'circlet')
            artifacts = [ArtifactItem(id=a['artifact_id'], name='Synthetic', set_id=1, set_uid=a['set_uid'],
                set_name='Synthetic', pos=slots.index(a['slot'])+1, pos_name=a['slot'], rarity=5, level=20,
                main_property_type=3, main_property_name='HP%', main_property_value='46.6%', substats=[])
                for a in request['artifacts']]
            pages = build_optimizer_result_pages(payload, team, artifacts)
            self.assertEqual(len(pages), 1)
            self.assertEqual(pages[0].measured_dps, '110')
            replacements = [item for row in pages[0].rows for item in row.replacements]
            self.assertEqual(len(replacements), 1)
            self.assertEqual(replacements[0].dps_delta, -30.)
            with patch.object(shell, 'format_gcsim_optimizer_go_selected_result', format_staged_result):
                text = shell.format_gcsim_optimizer_go_selected_result(payload)
            self.assertIn('#1: n500, SE 1', text)
            self.assertIn('#2: n100, SE 2', text)
            self.assertEqual(payload['result']['candidates'][1]['measured']['iterations'], 100)

    def test_unconfirmed_winner_rejected_in_experiment_text(self):
        with self.assertRaises(ValueError):
            format_staged_result({'status': 'success', 'result': {'measured': {'iterations': 100}, 'candidates': []}})


if __name__ == '__main__': unittest.main()
