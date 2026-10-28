"""Only the new Theory harness/uncrossed frozen R5 button seam; zero engine."""
from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
import tempfile
import time
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

    def test_composed_sentinel_adapter_and_constructor_failure_receipt(self):
        from tests.tools import test_optimizer_archetype_button_cases as button
        from run_workspace.gcsim.optimizer_go_theory import GcsimOptimizerGoTheoryRequest
        from run_workspace.gcsim import optimizer_go_session as session
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            snapshot=root/'snapshot';snapshot.write_bytes(b'no inventory read in construction test')
            env={'GTT_MECHANIC_EXPECTED_TOTAL':'604','GTT_MECHANIC_EXPECTED_ELIGIBLE':'597',
                 'GTT_MECHANIC_EXPECTED_SETS':'39','GTT_REAL_INVENTORY_SNAPSHOT':str(snapshot),
                 'GTT_MECHANIC_SNAPSHOT_SHA256':t1.sha(snapshot.read_bytes()),
                 'GTT_REAL_TEAM_SOURCE_CONFIG':str(snapshot),'GTT_MECHANIC_NATIVE_LOG_DIR':str(root/'native-logs'),
                 'GTT_MECHANIC_TEST_CACHE_ENABLED':'0','GTT_MVP_POLISH_RUN_ROOT':str(root),
                 'GTT_MVP_POLISH_MODE':'theory'}
            observations={'progress':[]}
            with patch.dict(os.environ,env), t1.base.gate.install_child_adapter(button), \
                 patch.object(session,'start_optimizer_process',side_effect=AssertionError('zero engine test')) as launch:
                wrapped=t1.observed_worker(button.GcsimBrowserSelectedOptimizerWorker,observations)
                class BoundedRealWorker(wrapped):
                    def __init__(self, request):
                        super().__init__(replace(request,product_timeout_ms=1))
                worker=BoundedRealWorker(GcsimOptimizerGoTheoryRequest('unused',{},0,''))
                self.assertEqual(worker._session.request.product_timeout_ms,0)
                self.assertEqual(observations['worker']['product_timeout_ms'],0)
                self.assertIs(observations['worker']['cache_enabled'],False)
                # Exercise the actual GUI click/pump and ordinary finalizer. An
                # invalid final session request must fail without waiting 60s.
                team={'slots':[{'character':{'name':key,'gcsim_character_key':key}}
                               for key in ('raiden','xingqiu','bennett','xiangling')]}
                harness=button.ArchetypeButtonHarness(None,team,{})
                summary={'status':'failed','errors':{}}
                started=time.monotonic()
                original_init=BoundedRealWorker.__init__
                def invalid_init(self, request):
                    original_init(self,replace(request,theory_options={'invalid':True}))
                try:
                    with patch('ui.app_shell._selected_gcsim_engine_id',return_value='synthetic-engine'), \
                         patch('ui.app_shell.GcsimBrowserSelectedOptimizerWorker',BoundedRealWorker), \
                         patch.object(BoundedRealWorker,'__init__',invalid_init), t1.fail_callback_errors(button):
                        try:
                            harness.click_one_mode('theory','raiden.attack',watchdog_ms=60000)
                        except ValueError as error:
                            self.assertEqual(str(error),'T1 actual Theory settings differ')
                            summary['errors']={'code':'real_button_test_exception','class':type(error).__name__}
                        else:
                            self.fail('constructor invariant was disabled')
                finally:
                    joined=button._finalize_test_harness(harness=harness,summary_path=root/'failed.json',
                                                        summary=summary,started=started)
                self.assertTrue(joined)
                self.assertLess(time.monotonic()-started,5)
                receipt=json.loads((root/'failed.json').read_bytes())
                self.assertEqual(receipt['status'],'failed')
                self.assertEqual(receipt['errors']['class'],'ValueError')
                launch.assert_not_called()

    def test_aborted_missing_case_keeps_original_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            result=t1.summarize(root,'off',{'status':'failed','error_code':'original_abort','case':None},root)
            self.assertEqual(result['error_code'],'original_abort')
            self.assertEqual(result['status'],'failed')
            self.assertIsNone(result['button_ms'])

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
