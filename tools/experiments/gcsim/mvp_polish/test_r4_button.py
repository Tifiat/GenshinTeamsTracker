"""R4 no-engine worker/launcher, owner and frozen-input checks."""
from contextlib import nullcontext
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from . import r4_button as runner


class R4ButtonChecks(unittest.TestCase):
    def test_owner_scope_inputs_and_production_region_unchanged(self):
        reference = json.loads(runner.PREVIOUS.read_bytes())['inventory']
        current = dict(reference)

        def owner(output):
            images, _, packet = runner.base.preflight()
            self.assertEqual(runner.base.OUT, runner.OUT)
            self.assertEqual(runner.base.CHILD, runner.CHILD)
            self.assertEqual(packet['r4_flags'], runner.FLAGS)
            self.assertEqual(packet['parent_r3_source_image_sha256'], runner.source.R3_MAP)
            self.assertEqual(packet['permitted_arms'], ['off'])
            parent = runner.source.parent.native_images()
            for name in ('internal/formula/region_binding.go', 'internal/formula/theory_fork.go'):
                self.assertEqual(images[name], parent[name])
            self.assertFalse(any('r4_region' in k or 'r4_saved_regions' in k for k in images))
            self.assertEqual(runner.base.gate.snapshot_active_inventory(), current)
            with self.assertRaises(ValueError):
                runner.base.run_arm(None, None, 'on')
            current['set_domain_count'] -= 1
            with self.assertRaises(ValueError):
                runner.base.gate.snapshot_active_inventory()

        with patch.object(runner.base.gate, 'snapshot_active_inventory', side_effect=lambda **_: dict(current)), \
                patch.object(runner.base, 'prepare_and_wait', owner), \
                patch('subprocess.Popen', side_effect=AssertionError('no process')):
            runner.prepare(runner.OUT / 'never-created-r4')

    def test_actual_worker_both_native_launches_and_flags(self):
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

        with tempfile.TemporaryDirectory(prefix='r4-observer-') as temp:
            path = Path(temp)
            env = dict(runner.FLAGS, GTT_MECHANIC_TEST_CACHE_ENABLED='0', GTT_R1_SINGLE_NEUTRAL='1',
                       GTT_WHOLE_CHASCA_COUNTERS='1', **{f'GTT_R{i}_OBSERVATIONS': str(path / f'r{i}.json') for i in (1, 3, 4)})
            with patch.dict(os.environ, env), \
                    patch.object(runner.base.gate, 'install_child_adapter', return_value=nullcontext()), \
                    patch.object(button, 'GcsimBrowserSelectedOptimizerWorker', GcsimBrowserSelectedOptimizerWorker), \
                    patch.object(button, 'ArchetypeRealButtonExecutionTest', Fixture), \
                    patch.object(session, 'start_optimizer_process', return_value=SimpleNamespace()) as launch, \
                    patch('subprocess.Popen', side_effect=AssertionError('no engine')):
                runner.R4ButtonExecutionTest('test_one_case').test_one_case()
                self.assertEqual(launch.call_count, 2)
            observed = json.loads((path / 'r4.json').read_bytes())
            self.assertEqual([r['stage'] for r in observed], ['validate-request', 'optimize-all-sets'])
            self.assertTrue(all(r['flags'] == runner.FLAGS and r['dirty_frontier'] == 'excluded' for r in observed))

    def test_flags_injected_and_rejected_module_and_repeat_blocked(self):
        with tempfile.TemporaryDirectory(prefix='r4-arm-') as temp:
            path = Path(temp)
            owner = {'arms': [], 'packet': {'r4_flags': runner.FLAGS, 'r3_harness_files': {}, 'r4_harness_files': {}}}
            target = path / 'owner.json'; target.write_text(json.dumps(owner))

            def arm(*args):
                env = runner.base.gate.run_case._child_environment()
                self.assertEqual({k: env[k] for k in runner.FLAGS}, runner.FLAGS)
                self.assertNotIn('GTT_R4_DIRTY_REGIONS', env)
                self.assertEqual(env['GTT_R4_OBSERVATIONS'], str(path / 'off-r4-observations.json'))
                return 'joined'

            with patch.object(runner.base.gate.run_case, '_child_environment', return_value={'GTT_R4_DIRTY_REGIONS': '1'}), \
                    patch.object(runner, '_run_arm', side_effect=arm):
                self.assertEqual(runner.checked_arm(path, path, 'off'), 'joined')
                owner['arms'] = [{'status': 'success'}]; target.write_text(json.dumps(owner))
                with self.assertRaises(ValueError):
                    runner.checked_arm(path, path, 'off')


if __name__ == '__main__':
    unittest.main()
