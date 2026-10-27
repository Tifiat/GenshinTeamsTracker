"""Focused R2 configuration, mixed gear extraction and anomaly export wiring."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import r2_button as runner


class R2ButtonChecks(unittest.TestCase):
    def test_existing_owner_hooks_off_only_and_inventory_match(self):
        previous = json.loads(runner.PREVIOUS.read_bytes())['inventory']
        current = dict(previous)
        def fake_snapshot(**_): return dict(current)
        def fake_owner(output):
            self.assertEqual(runner.base.OUT, runner.OUT)
            self.assertEqual(runner.base.CHILD, runner.CHILD)
            images, _, packet = runner.base.preflight()
            self.assertEqual(len(images), 411)
            self.assertEqual(packet['parent_r1_source_image_sha256'], runner.source.R1_MAP)
            self.assertEqual(packet['permitted_arms'], ['off'])
            self.assertEqual(runner.base.gate.snapshot_active_inventory(), current)
            with self.assertRaises(ValueError): runner.base.run_arm(None, None, 'on')
            current['eligible_count'] -= 1
            with self.assertRaises(ValueError): runner.base.gate.snapshot_active_inventory()
        with patch.object(runner.base.gate, 'snapshot_active_inventory', fake_snapshot), \
                patch.object(runner.base, 'prepare_and_wait', fake_owner), \
                patch('subprocess.Popen', side_effect=AssertionError('no process')):
            runner.prepare(runner.OUT / 'never-created')

    def test_mixed_gear_extraction_keeps_real_counts_and_r1_default(self):
        fixture = json.loads((runner.OUT / 'mixed-ui-fixture-v1.json').read_bytes())
        with self.assertRaises(ValueError): runner.base.transport.measured_rows(fixture['request'], fixture['wrapper'])
        rows = runner.base.transport.measured_rows(fixture['request'], fixture['wrapper'], allowed_iterations=(100, 500))
        self.assertEqual([r['measurement']['iterations'] for r in rows], [500, 100])
        self.assertTrue(all(len(r['gear']) == 4 for r in rows))

    def test_failed_result_exports_partial_stages(self):
        with tempfile.TemporaryDirectory(prefix='r2-partial-') as temp:
            job = Path(temp)
            raw = job / 'raw/off/verification/final-staged'
            raw.mkdir(parents=True)
            stage = {'status': 'failed', 'stages': [{'iterations': 100, 'error': 'synthetic identity rejection'}]}
            (raw / 'verification-stages.json').write_text(json.dumps(stage))
            result = runner.summarize(job, 'off', {'status': 'failed', 'error_code': 'synthetic'}, job)
            exported = json.loads((job / 'off-details.json').read_bytes())
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(exported['partial_stages'], [stage])


if __name__ == '__main__': unittest.main()
