"""R1 gate connections with native process creation forbidden."""
from contextlib import nullcontext
import json
import itertools
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import managed_optimizer_experiment as managed
from . import r1_button as r1


class R1ButtonChecks(unittest.TestCase):
    def test_run_arm_freezes_inventory_and_consumes_retained_native_results(self):
        with managed.managed_scratch() as job:
            frozen_path = job / 'frozen.db'
            frozen_path.write_bytes(b'immutable inventory fixture')
            frozen = {'path': frozen_path, 'sha256': r1.gate._sha(frozen_path)}
            slots = ('flower', 'plume', 'sands', 'goblet', 'circlet')
            assignment = [list(range(i * 5 + 1, i * 5 + 6)) for i in range(4)]
            rows = [{'assignment': [assignment[i] for i in order], 'iterations': 500,
                     'measured_dps': 12345., 'standard_error': 4.}
                    for order in itertools.islice(itertools.permutations(range(4)), 9)]
            payload = {'result_options': r1.OPTIONS, 'stochastic': {'seeds': r1.SEEDS},
                'artifacts': [{'artifact_id': i+1, 'slot': slots[i % 5], 'set_uid': 'synthetic'} for i in range(20)],
                'wearers': [{'wearer_key': k} for k in ('chasca', 'furina', 'bennett', 'ororon')]}
            def fake_gate(**kwargs):
                self.assertEqual(kwargs['mode'], 'all_sets')
                self.assertEqual(kwargs['test_watchdog_seconds'], r1.WATCHDOG)
                self.assertEqual(r1.gate.CHILD_TEST, r1.CHILD)
                with r1.gate.run_case.managed_scratch(job / 'button-jobs') as child:
                    actual = r1.gate.snapshot_active_inventory(job=child)
                    self.assertEqual(actual['path'].read_bytes(), frozen_path.read_bytes())
                    env = r1.gate.run_case._child_environment(child, case_id='chasca_600_fixture', mode='all_sets',
                        lease_id='r1-zero', engine_store=job, optimizer_binary=job / 'fixture.exe')
                    self.assertEqual(env['GTT_R1_SINGLE_NEUTRAL'], '1')
                    self.assertFalse(any(k.startswith('GTT_C4_') for k in env))
                    run = child / 'saved-runs' / 'all_sets-fixture'
                    verification = run / 'verification'
                    verification.mkdir(parents=True)
                    (run / 'request.json').write_text(json.dumps(payload))
                    (verification / 'all-sets-result.json').write_text(json.dumps({'verification': {'candidates': rows},
                        'product_result': {'candidates': [{} for _ in rows]}}))
                    (verification / 'whole-search-counters.json').write_text(json.dumps({'Mode': 'wall_and_counts',
                        'CPUAvailable': False, 'SnapshotWallNS': 0, 'ProjectionValueWitness': '', 'Counts': {}, 'Phases': {}}))
                self.assertFalse(child.exists())
                return {'status': 'success', 'case': {'timings_ms': {'button_click_to_terminal_ms': 1}}}
            output = job / 'compact'
            output.mkdir()
            row = {'case_id': 'chasca_600_fixture', 'source_config_file': 'synthetic.json'}
            with patch.object(r1.gate, 'run_one', side_effect=fake_gate), \
                    patch.dict(os.environ, GTT_C4_LINEAGE_EXPORT='forbidden'), \
                    patch('subprocess.Popen', side_effect=AssertionError('native forbidden')):
                for arm in ('off', 'on'):
                    result = r1.run_arm(job, output, arm, frozen, row, job, job / 'fixture.exe', r1.WATCHDOG)
                    self.assertEqual(result['actual_simulated_finalists'], 9)
                    self.assertEqual(result['actual_published_finalists'], 9)
                    self.assertEqual(result['artifact_count'], 20)

    def test_nested_raw_moves_before_existing_cleanup_even_on_failure(self):
        with managed.managed_scratch() as job:
            for arm, fails in (('off', False), ('failed', True)):
                try:
                    with r1.retain_child_runs(job, arm, managed.managed_scratch) as factory:
                        with factory(job / 'button-jobs') as child:
                            run = child / 'saved-runs' / 'native'
                            run.mkdir(parents=True)
                            (run / 'evidence').write_bytes(b'raw source evidence')
                            (child / 'case-summary.json').write_text('{}')
                            if fails: raise RuntimeError('synthetic child failure')
                except RuntimeError:
                    self.assertTrue(fails)
                self.assertFalse(child.exists())
                self.assertEqual((job / 'raw' / arm / 'saved-runs/native/evidence').read_bytes(), b'raw source evidence')

    def test_actual_worker_and_both_launch_observers_without_engine(self):
        from tests.tools import test_optimizer_archetype_button_cases as button
        from run_workspace.gcsim import optimizer_go_session as session
        from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsRequest
        from ui.gcsim_browser.run_worker import GcsimBrowserSelectedOptimizerWorker
        class Fixture:
            def __init__(self, _): pass
            def run(self, result):
                worker = button.GcsimBrowserSelectedOptimizerWorker(GcsimOptimizerGoAllSetsRequest(
                    db_path='', selected_team={}, team_index=0, rotation_shell_text='',
                    **r1.OPTIONS, seeds=tuple(r1.SEEDS)))
                env = worker._session._optimizer_environment()
                for stage in ('validate-request', 'optimize-all-sets'):
                    session.start_optimizer_process(['fixture', stage], env=env)
                result.testsRun = 1
        with tempfile.TemporaryDirectory(prefix='r1-observer-') as temp:
            path = Path(temp) / 'observed.json'
            for enabled in ('0', '1'):
                with patch.dict(os.environ, GTT_MECHANIC_TEST_CACHE_ENABLED=enabled,
                        GTT_R1_SINGLE_NEUTRAL='1', GTT_WHOLE_CHASCA_COUNTERS='1', GTT_R1_OBSERVATIONS=str(path)), \
                        patch.object(r1.gate, 'install_child_adapter', return_value=nullcontext()), \
                        patch.object(button, 'GcsimBrowserSelectedOptimizerWorker', GcsimBrowserSelectedOptimizerWorker), \
                        patch.object(button, 'ArchetypeRealButtonExecutionTest', Fixture), \
                        patch.object(session, 'start_optimizer_process', return_value=SimpleNamespace()) as launch, \
                        patch('subprocess.Popen', side_effect=AssertionError('engine forbidden')):
                    r1.R1ButtonExecutionTest('test_one_case').test_one_case()
                    self.assertEqual(launch.call_count, 2)
                observed = json.loads(path.read_bytes())
                self.assertIs(observed['worker_request_cache_enabled'], enabled == '1')
                self.assertEqual([row['stage'] for row in observed['native_launch_environments']], ['validate-request', 'optimize-all-sets'])
                self.assertTrue(all(row['environment']['GTT_R1_SINGLE_NEUTRAL'] == '1' for row in observed['native_launch_environments']))


if __name__ == '__main__': unittest.main()
