"""N0 exact-byte archival proof before deletion; synthetic files only."""
import json
from pathlib import Path
import tempfile
import shutil
import unittest
import zipfile

from tools.archive_optimizer_evidence import prepare_archive, verify_before_cleanup


class EvidenceArchiveTest(unittest.TestCase):
    def fixture(self, root):
        source = root / "research"
        source.mkdir()
        (source / "latest.json").write_text('{"proof": 42}')
        (source / "old").mkdir()
        (source / "old" / "superseded.json").write_text("obsolete")
        plan = dict(delete_directories=[dict(path="research/old")],
                    archive_directories=[dict(path="research")], archive_path="evidence.zip",
                    archive_manifest_path="receipt.json", archive_max_bytes=10000,
                    owner="test", lifecycle="temporary unittest")
        return source, plan

    def test_roundtrip_is_lossless_keeps_sources_and_excludes_obsolete_children(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, plan = self.fixture(root)
            result = prepare_archive(root, plan)
            self.assertEqual(result["archived_files"], 1)
            self.assertTrue((source / "latest.json").exists())
            with zipfile.ZipFile(root / "evidence.zip") as archive:
                self.assertEqual(archive.read("research/latest.json"), (source / "latest.json").read_bytes())
                self.assertNotIn("research/old/superseded.json", archive.namelist())
            verify_before_cleanup(root, plan)
            with self.assertRaises(ValueError):
                prepare_archive(root, plan)
            shutil.rmtree(source)  # simulate one successfully cleaned fixture root
            verify_before_cleanup(root, plan)  # retry is safe after partial cleanup

    def test_changed_sources_or_archive_block_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, plan = self.fixture(root)
            prepare_archive(root, plan)
            (source / "latest.json").write_text("changed")
            with self.assertRaisesRegex(ValueError, "Source changed"):
                verify_before_cleanup(root, plan)
            (root / "evidence.zip").write_bytes(b"broken")
            with self.assertRaisesRegex(ValueError, "Archive hash"):
                verify_before_cleanup(root, plan)

    def test_budget_failure_removes_only_new_partial_not_original_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, plan = self.fixture(root)
            plan["archive_max_bytes"] = 1
            with self.assertRaisesRegex(ValueError, "budget"):
                prepare_archive(root, plan)
            self.assertFalse((root / "evidence.zip.partial").exists())
            self.assertFalse((root / "receipt.json").exists())
            self.assertTrue((source / "latest.json").exists())

    def test_existing_partial_is_not_overwritten_or_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, plan = self.fixture(root)
            partial = root / "evidence.zip.partial"
            partial.write_text("keep")
            with self.assertRaises(FileExistsError):
                prepare_archive(root, plan)
            self.assertEqual(partial.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
