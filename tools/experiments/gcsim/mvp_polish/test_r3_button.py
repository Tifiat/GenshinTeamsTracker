"""No-engine checks of R3 real worker/launcher and existing owner wiring."""
from contextlib import nullcontext
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from . import r3_button as runner


class R3ButtonChecks(unittest.TestCase):
    def test_existing_owner_and_fresh_r2_inventory_guards(self):
        reference = json.loads(runner.PREVIOUS.read_bytes())['inventory']
        current = dict(reference)

        def owner(output):
            self.assertEqual(runner.base.OUT, runner.OUT)
            self.assertEqual(runner.base.CHILD, runner.CHILD)
            images, _, packet = runner.base.preflight()
            self.assertEqual(packet['parent_r2_source_image_sha256'], runner.source.R2_MAP)
            self.assertEqual(packet['permitted_arms'], ['off'])
            self.assertEqual(packet['r3_flags'], runner.FLAGS)
            self.assertGreater(len(images), 411)
            self.assertEqual(runner.base.gate.snapshot_active_inventory(), current)
            with self.assertRaises(ValueError):
                runner.base.run_arm(None, None, 'on')
            current['eligible_count'] -= 1
            with self.assertRaises(ValueError):
                runner.base.gate.snapshot_active_inventory()

        with patch.object(runner.base.gate, 'snapshot_active_inventory', side_effect=lambda **_: dict(current)), \
                patch.object(runner.base, 'prepare_and_wait', owner), \
                patch('subprocess.Popen', side_effect=AssertionError('no process')):
            runner.prepare(runner.OUT / 'never-created')

    def test_actual_worker_and_both_native_launch_flags(self):
        from tests.tools import test_optimizer_archetype_button_cases as button
        from run_workspace.gcsim import optimizer_go_session as session
        from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsRequest
        from ui.gcsim_browser.run_worker import GcsimBrowserSelectedOptimizerWorker

        class Fixture:
            def __init__(self, _): pass
            def run(self, result):
                worker = button.GcsimBrowserSelectedOptimizerWorker(GcsimOptimizerGoAllSetsRequest(
                    db_path='', selected_team={}, team_index=0, rotation_shell_text='',
                    **runner.base.OPTIONS, seeds=tuple(runner.base.SEEDS)))
                env = worker._session._optimizer_environment()
                for stage in ('validate-request', 'optimize-all-sets'):
                    session.start_optimizer_process(['fixture', stage], env=env)
                result.testsRun = 1

        with tempfile.TemporaryDirectory(prefix='r3-observer-') as temp:
            path = Path(temp)
            env = dict(runner.FLAGS, GTT_MECHANIC_TEST_CACHE_ENABLED='0', GTT_R1_SINGLE_NEUTRAL='1',
                       GTT_WHOLE_CHASCA_COUNTERS='1', GTT_R1_OBSERVATIONS=str(path / 'r1.json'),
                       GTT_R3_OBSERVATIONS=str(path / 'r3.json'))
            with patch.dict(os.environ, env), \
                    patch.object(runner.base.gate, 'install_child_adapter', return_value=nullcontext()), \
                    patch.object(button, 'GcsimBrowserSelectedOptimizerWorker', GcsimBrowserSelectedOptimizerWorker), \
                    patch.object(button, 'ArchetypeRealButtonExecutionTest', Fixture), \
                    patch.object(session, 'start_optimizer_process', return_value=SimpleNamespace()) as launch, \
                    patch('subprocess.Popen', side_effect=AssertionError('no engine')):
                runner.R3ButtonExecutionTest('test_one_case').test_one_case()
                self.assertEqual(launch.call_count, 2)
            observed = json.loads((path / 'r3.json').read_bytes())
            self.assertEqual([r['stage'] for r in observed], ['validate-request', 'optimize-all-sets'])
            self.assertTrue(all(r['r3_flags'] == runner.FLAGS for r in observed))

    def test_arm_injects_flags_and_refuses_duplicate(self):
        with tempfile.TemporaryDirectory(prefix='r3-arm-') as temp:
            path = Path(temp)
            owner = {'arms': [], 'packet': {'r3_flags': runner.FLAGS, 'r3_harness_files': {}}}
            target = path / 'owner.json'
            target.write_text(json.dumps(owner))

            def arm(*args):
                env = runner.base.gate.run_case._child_environment()
                self.assertEqual({k: env[k] for k in runner.FLAGS}, runner.FLAGS)
                self.assertEqual(env['GTT_R3_OBSERVATIONS'], str(path / 'off-r3-observations.json'))
                return 'joined'

            with patch.object(runner.base.gate.run_case, '_child_environment', return_value={}), \
                    patch.object(runner, '_run_arm', side_effect=arm):
                self.assertEqual(runner.checked_arm(path, path, 'off'), 'joined')
                owner['arms'] = [{'status': 'success'}]
                target.write_text(json.dumps(owner))
                with self.assertRaises(ValueError):
                    runner.checked_arm(path, path, 'off')


if __name__ == '__main__':
    unittest.main()
