import hashlib
from pathlib import Path
import os
import stat
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools.prepare_optimizer_set_cache import collect_provenance_entries


class PrepareOptimizerSetCacheTest(unittest.TestCase):
    def test_collects_sorted_hashes_and_byte_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / 'b.gttast').write_bytes(b'plan-b')
            (target / 'a.gttast').write_bytes(b'plan-a')
            (target / 'ignored.txt').write_bytes(b'ignored')

            files, total = collect_provenance_entries(target)

            self.assertEqual(files, {
                'a.gttast': hashlib.sha256(b'plan-a').hexdigest(),
                'b.gttast': hashlib.sha256(b'plan-b').hexdigest(),
            })
            self.assertEqual(total, len(b'plan-a') + len(b'plan-b'))

    def test_rejects_nonregular_entry_and_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            cache_entry = target / 'plan.gttast'
            cache_entry.mkdir()
            receipt = target / 'provenance.json'
            receipt.write_text('previous receipt', encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'Unsafe cache entry'):
                collect_provenance_entries(target)

            self.assertTrue(cache_entry.is_dir())
            self.assertEqual(receipt.read_text(encoding='utf-8'), 'previous receipt')

    def test_rejects_symlink_before_open_and_preserves_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'cache'
            target.mkdir()
            precious = root / 'precious.gttast'
            precious.write_bytes(b'keep these bytes')
            link = target / 'linked.gttast'
            try:
                link.symlink_to(precious)
            except OSError as error:
                self.skipTest(f'Symlink creation unavailable: {error}')

            with patch('tools.prepare_optimizer_set_cache.os.open') as open_file:
                with self.assertRaisesRegex(ValueError, 'Unsafe cache entry'):
                    collect_provenance_entries(target)
            open_file.assert_not_called()
            self.assertEqual(precious.read_bytes(), b'keep these bytes')
            self.assertTrue(link.is_symlink())

    def test_rejects_reparse_point_before_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            entry = target / 'plan.gttast'
            entry.write_bytes(b'keep')
            original_lstat = Path.lstat
            actual = original_lstat(entry)
            reparse = SimpleNamespace(st_mode=actual.st_mode, st_file_attributes=0x400)

            def lstat_with_reparse(path, *args, **kwargs):
                if path == entry:
                    return reparse
                return original_lstat(path, *args, **kwargs)

            with patch.object(Path, 'lstat', lstat_with_reparse), \
                    patch('tools.prepare_optimizer_set_cache.os.open') as open_file:
                with self.assertRaisesRegex(ValueError, 'Unsafe cache entry'):
                    collect_provenance_entries(target)
            open_file.assert_not_called()
            self.assertEqual(entry.read_bytes(), b'keep')

    def test_rechecks_file_identity_after_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            entry = target / 'plan.gttast'
            entry.write_bytes(b'plan')
            before = entry.lstat()
            changed = SimpleNamespace(
                st_dev=before.st_dev,
                st_ino=before.st_ino + 1,
                st_mode=stat.S_IFREG | 0o600,
                st_size=before.st_size,
                st_mtime_ns=before.st_mtime_ns,
                st_ctime_ns=before.st_ctime_ns,
                st_file_attributes=0,
            )

            with patch('tools.prepare_optimizer_set_cache.os.fstat', side_effect=[before, changed]):
                with self.assertRaisesRegex(ValueError, 'changed while collecting provenance'):
                    collect_provenance_entries(target)

            self.assertEqual(entry.read_bytes(), b'plan')

    def test_enforces_file_count_and_byte_budgets_before_excess_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / 'a.gttast').write_bytes(b'aa')
            (target / 'b.gttast').write_bytes(b'bb')
            (target / 'c.gttast').write_bytes(b'cc')

            with patch('tools.prepare_optimizer_set_cache.MAX_PROVENANCE_FILES', 2), \
                    patch('tools.prepare_optimizer_set_cache.os.open') as open_file:
                with self.assertRaisesRegex(ValueError, 'exceeds 2 files'):
                    collect_provenance_entries(target)
            open_file.assert_not_called()

            with patch('tools.prepare_optimizer_set_cache.MAX_PROVENANCE_FILES', 512), \
                    patch('tools.prepare_optimizer_set_cache.MAX_PROVENANCE_BYTES', 3):
                with self.assertRaisesRegex(ValueError, 'exceeds 3 bytes'):
                    collect_provenance_entries(target)
            self.assertEqual((target / 'a.gttast').read_bytes(), b'aa')
            self.assertEqual((target / 'b.gttast').read_bytes(), b'bb')
            self.assertEqual((target / 'c.gttast').read_bytes(), b'cc')


if __name__ == '__main__':
    unittest.main()
