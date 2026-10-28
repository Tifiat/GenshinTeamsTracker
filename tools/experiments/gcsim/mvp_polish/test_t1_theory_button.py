"""Only the new Theory harness/uncrossed frozen R5 button seam; zero engine."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import t1_theory_button as t1


class T1HarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images,cls.row,cls.packet=t1.preflight()

    def test_exact_R5_Theory_commands_policy_and_history(self):
        from run_workspace.gcsim.optimizer_go_theory import GcsimOptimizerGoTheoryRequest
        from run_workspace.gcsim.optimizer_go_theory_session import GcsimOptimizerGoTheorySession
        from ui.gcsim_browser.run_worker import GcsimBrowserSelectedOptimizerWorker
        request=GcsimOptimizerGoTheoryRequest('unused',{},0,'')
        worker=GcsimBrowserSelectedOptimizerWorker(request)
        self.assertIsInstance(worker._session,GcsimOptimizerGoTheorySession)
        command=worker._session._optimizer_command(Path('owned.exe'),Path('run'))
        self.assertEqual(command[1],'optimize-theory')
        self.assertIn('--finish-file',command)
        self.assertIn('--theory-control-file',command)
        self.assertEqual(worker._session.request_validation_mode,'validate-theory-request')
        self.assertEqual(request.product_timeout_ms,0)
        self.assertIsNone(request.theory_options)
        self.assertEqual(self.packet['source_image_sha256'],'48f643c2e4c7f353806513c8e00f9f5efd31d5bfe615cdb93a038d9f84b9ae09')
        self.assertEqual(self.packet['r5_product_python_map_sha256'],'e3d71c217355830ca8e5cf21211a0d28fb8a924a4e53f955dfabd3bbec654569')
        t1.verify_sources(self.packet)
        history=json.loads(t1.HISTORY.read_bytes())
        self.assertEqual(history['case']['timings_ms']['button_click_to_terminal_ms'],105344)
        self.assertEqual(history['case']['config_join']['request_theory_options'] if 'request_theory_options' in history['case']['config_join'] else {},{})
        self.assertEqual(history['case']['config_join']['rotation_prepared_sha256'],self.packet['rotation_sha256'])

    def test_existing_first_verified_Finish_bridge_on_frozen_R5(self):
        from tests.tools.test_optimizer_archetype_button_cases import ArchetypeCaseDataTests
        # Real GUI-thread bridge, worker thread and reader thread; a synthetic
        # snapshot/session supplies the new seam without any optimizer process.
        ArchetypeCaseDataTests('test_theory_first_verified_snapshot_uses_reader_thread_and_actual_finish_route').debug()

    def test_single_arm_rejects_repeat_or_other_mode_before_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'owner.json').write_text(json.dumps({'arms':[{'arm':'off'}]}))
            with self.assertRaisesRegex(ValueError,'exactly one OFF'):
                t1.run_arm(root,root,'off',None,None,None,None,None)
            (root/'owner.json').write_text(json.dumps({'arms':[]}))
            with self.assertRaisesRegex(ValueError,'exactly one OFF'):
                t1.run_arm(root,root,'on',None,None,None,None,None)

    def test_history_and_late_harness_mutations_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'history.json';path.write_bytes(b'changed historical receipt')
            with patch.object(t1,'HISTORY',path):
                with self.assertRaisesRegex(ValueError,'historical reference changed'):
                    t1.verify_sources(self.packet)
        current=t1.r5.harness_files()
        with patch.object(t1.r5,'harness_files',return_value={**current,'tools/unlisted.py':'0'*64}):
            with self.assertRaisesRegex(ValueError,'actual harness source closure changed'):
                t1.actual_harness_coverage(self.packet)
        t1.actual_harness_coverage(self.packet)


if __name__=='__main__':unittest.main()
