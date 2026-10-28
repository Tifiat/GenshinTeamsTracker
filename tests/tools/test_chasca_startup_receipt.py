"""Bounded Chasca startup receipts; replay dependencies are fully mocked."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.experiments.gcsim.parametric_effects import recheck_chasca_startup as replay


class ChascaStartupReceiptTests(unittest.TestCase):
    def test_attempt_paths_are_fixed_and_invalid_attempts_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = [replay.receipt_path_for_attempt(attempt, root=root) for attempt in (1, 2, 3)]
            self.assertEqual(len(set(paths)), 3)
            self.assertTrue(all(path.parent == paths[0].parent for path in paths))
            for attempt in (0, 4, True, '1'):
                with self.subTest(attempt=attempt), self.assertRaises(ValueError):
                    replay.receipt_path_for_attempt(attempt, root=root)

    def test_cli_rejects_invalid_attempt_before_allocating_scratch(self):
        with patch.object(replay.sys, 'argv', ['recheck_chasca_startup.py', '--attempt', '4']), \
             patch.object(replay, 'owned_job') as owned_job:
            with self.assertRaises(SystemExit):
                replay.main()
        owned_job.assert_not_called()

    def test_receipt_is_immutable_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = replay.receipt_path_for_attempt(1, root=root)
            path.parent.mkdir(parents=True)
            replay.save_receipt(1, {'success': False, 'error': 'first result'}, root=root)
            original = path.read_bytes()
            with self.assertRaises(FileExistsError):
                replay.save_receipt(1, {'success': True}, root=root)
            self.assertEqual(path.read_bytes(), original)

    def test_size_limit_includes_exact_boundary_and_refuses_oversize_before_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root_path = replay.receipt_path_for_attempt(1, root=root)
            root_path.parent.mkdir(parents=True)
            receipt = {'success': True}
            encoded = (json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
            with patch.object(replay, 'MAX_RECEIPT_BYTES', len(encoded)):
                saved = replay.save_receipt(1, receipt, root=root)
            self.assertEqual(saved.read_bytes(), encoded)

            oversize_path = replay.receipt_path_for_attempt(2, root=root)
            with patch.object(replay, 'MAX_RECEIPT_BYTES', len(encoded) - 1), self.assertRaises(ValueError):
                replay.save_receipt(2, receipt, root=root)
            self.assertFalse(oversize_path.exists())
            self.assertEqual(replay.MAX_RECEIPT_BYTES, 2 * 1024 * 1024)

    def _run_mock_replay(self, root: Path, attempt: int, *, fail: bool):
        saved = root / 'saved'
        saved.mkdir()
        original = {
            'engine': {'id': 'saved-engine'},
            'context': {
                'prepared_config': {'text': 'saved config'},
                'rotation': ['saved rotation'],
                'target': {'level': 93},
                'context_sha256': 'saved-context-hash',
            },
            'budgets': {'product_timeout_ms': 1234},
            'gameplay_input': 'preserve-me',
        }
        (saved / 'request.json').write_text(json.dumps(original), encoding='utf-8')
        (saved / 'selected-result.json').write_text(json.dumps({'winner': 'before'}), encoding='utf-8')

        job = root / 'scratch-job'
        job.mkdir()
        engine_root = root / 'engine'
        health_capture = engine_root / 'pkg/gttsourcegen/health_field_capture.go'
        health_capture.parent.mkdir(parents=True)
        health_capture.write_text('// fixture marker', encoding='utf-8')
        binary = root / 'optimizer.exe'
        binary.write_bytes(b'fake optimizer binary')

        class Engine:
            def __init__(self):
                self.engine_root = engine_root
                self.engine_id = 'active-engine'
                self.artifact_sha256 = 'active-engine-sha'

        class FakeRequest:
            def __init__(self, **kwargs):
                self.optimizer_binary_path = str(binary)

        class FakeSession:
            def __init__(self, request, progress_callback=None):
                pass

            def _validate_optimizer_request(self, **kwargs):
                pass

            def _prepare_formula_inputs(self, **kwargs):
                pass

            def _run_go_optimizer(self, *, run_dir, **kwargs):
                if fail:
                    raise RuntimeError('simulated optimizer failure')
                (Path(run_dir) / 'optimizer-output.json').write_text(
                    json.dumps({'verification': {'winner': 'after'}, 'product_result': {'status': 'ok'}}),
                    encoding='utf-8')

        def fake_write_json(path, value):
            path.write_text(json.dumps(value), encoding='utf-8')

        receipt_path = replay.receipt_path_for_attempt(attempt, root=root)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        replacements = {
            'ROOT': root,
            'SAVED': saved,
            'owned_job': lambda: job,
            'write_json': fake_write_json,
            'rebind_request': lambda request, active_root: request,
            'canonical_sha256': lambda request: 'canonical-request-hash',
            'load_active_gcsim_optimizer_engine_context': lambda: Engine(),
            'GcsimOptimizerGoAllSetsRequest': FakeRequest,
            'GcsimOptimizerGoAllSetsSession': FakeSession,
        }
        with patch.multiple(replay, **replacements), \
             patch.object(replay.sys, 'argv', ['recheck_chasca_startup.py', '--attempt', str(attempt)]):
            if fail:
                with self.assertRaisesRegex(RuntimeError, 'simulated optimizer failure'):
                    replay.main()
            else:
                replay.main()
        return json.loads(receipt_path.read_text(encoding='utf-8'))

    def test_successful_replay_receipt_is_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt = self._run_mock_replay(Path(temp), 1, fail=False)
        self.assertTrue(receipt['success'])
        self.assertEqual(receipt['after']['verification']['winner'], 'after')

    def test_exception_receipt_is_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt = self._run_mock_replay(Path(temp), 2, fail=True)
        self.assertFalse(receipt['success'])
        self.assertEqual(receipt['error'], 'simulated optimizer failure')
        self.assertIn('replay_wall_seconds', receipt)


if __name__ == '__main__':
    unittest.main()
