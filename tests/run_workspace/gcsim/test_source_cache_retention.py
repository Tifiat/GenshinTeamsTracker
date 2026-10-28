from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from run_workspace.gcsim.engine_store import GcsimEngineStore
from run_workspace.gcsim.source_acquisition import (
    OfficialGcsimSourceAcquisition,
    OfficialGcsimSourceRef,
)
from run_workspace.gcsim.source_cache_retention import retain_official_source_cache


class SourceCacheRetentionTest(unittest.TestCase):
    def test_dry_run_then_apply_bounds_completed_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "sources"
            versions = [_version(cache, f"v{number}", stamp=number) for number in range(4)]
            store = GcsimEngineStore(root / "store")
            dry = retain_official_source_cache(acquisition=versions[-1], store=store)
            self.assertEqual(dry.status, "dry_run")
            self.assertEqual(len(dry.deleted_paths), 4)
            self.assertTrue(all(Path(path).exists() for path in dry.deleted_paths))
            applied = retain_official_source_cache(acquisition=versions[-1], store=store, dry_run=False)
            self.assertEqual(applied.status, "pruned")
            self.assertEqual(applied.deleted_bytes, dry.deleted_bytes)
            self.assertTrue(all(not Path(path).exists() for path in applied.deleted_paths))
            self.assertTrue(versions[-1].source_dir.is_dir())

    def test_current_and_newest_survive_oversized_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "sources"
            current = _version(cache, "v-current", stamp=1)
            newest = _version(cache, "v-newest", stamp=2)
            result = retain_official_source_cache(
                acquisition=current, store=GcsimEngineStore(root / "store"),
                dry_run=False, keep_count=1, max_bytes=1,
            )
            self.assertEqual(result.status, "pruned")
            self.assertGreater(result.over_budget_bytes, 0)
            self.assertTrue(current.source_dir.exists())
            self.assertTrue(newest.source_dir.exists())

    def test_active_rollback_and_diagnostic_engine_sources_are_protected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "sources"
            versions = [_version(cache, f"v{number}", stamp=number) for number in range(5)]
            store = GcsimEngineStore(root / "store")
            for index, name in ((0, "active"), (1, "rollback"), (2, "diagnostic")):
                acq = versions[index]
                prepared = store.prepare_engine_update(
                    source_dir=acq.source_dir, source_label=name, engine_id=name,
                    metadata={"source_archive_path": str(acq.archive_path)},
                    activate=index < 2,
                )
                self.assertTrue(prepared.success)
            # Two activations leave the first as rollback; preserve a retained
            # diagnostic manifest even though it is outside the success folder.
            shutil.move(str(store.engines_dir / "diagnostic"), str(store.failed_dir / "diagnostic"))
            result = retain_official_source_cache(
                acquisition=versions[-1], store=store, dry_run=False,
                keep_count=2, max_bytes=1,
            )
            self.assertEqual(result.status, "pruned")
            for index in (0, 1, 2, 4):
                self.assertTrue(versions[index].source_dir.exists())
                self.assertTrue(versions[index].archive_path.exists())
            self.assertFalse(versions[3].source_dir.exists())

    def test_unknown_and_live_entries_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "sources"
            old = _version(cache, "v-old", stamp=1)
            current = _version(cache, "v-current", stamp=2)
            foreign = cache / "archives" / "unrelated.tmp"
            foreign.write_bytes(b"live")
            result = retain_official_source_cache(
                acquisition=current, store=GcsimEngineStore(root / "store"),
                dry_run=False, keep_count=1,
            )
            self.assertEqual(result.status, "skipped_unsafe")
            self.assertTrue(old.source_dir.exists())
            foreign.unlink()
            extracting = cache / "extracting" / "in-progress"
            extracting.mkdir(parents=True)
            result = retain_official_source_cache(
                acquisition=current, store=GcsimEngineStore(root / "store"),
                dry_run=False, keep_count=1,
            )
            self.assertEqual(result.status, "skipped_unsafe")
            self.assertTrue(old.source_dir.exists())

    def test_malformed_active_state_and_nested_link_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "sources"
            old = _version(cache, "v-old", stamp=1)
            current = _version(cache, "v-current", stamp=2)
            store = GcsimEngineStore(root / "store")
            store.root_dir.mkdir()
            store.active_state_path.write_text("{broken", encoding="utf-8")
            result = retain_official_source_cache(acquisition=current, store=store,
                                                  dry_run=False, keep_count=1)
            self.assertEqual(result.status, "skipped_unsafe")
            self.assertTrue(old.source_dir.exists())
            store.active_state_path.unlink()
            link = old.source_dir / "linked"
            try:
                link.symlink_to(root, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Directory links are unavailable")
            result = retain_official_source_cache(acquisition=current, store=store,
                                                  dry_run=False, keep_count=1)
            self.assertEqual(result.status, "skipped_unsafe")
            self.assertTrue(old.source_dir.exists())

    def test_external_archive_does_not_establish_cache_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = _version(root / "sources", "v-current", stamp=1)
            external = root / "external.zip"
            shutil.copyfile(current.archive_path, external)
            acquisition = OfficialGcsimSourceAcquisition(
                source_ref=current.source_ref, archive_path=external,
                source_dir=current.source_dir, cache_dir=current.cache_dir,
            )
            result = retain_official_source_cache(
                acquisition=acquisition, store=GcsimEngineStore(root / "store"), dry_run=False,
            )
            self.assertEqual(result.status, "skipped_unsafe")
            self.assertTrue(current.archive_path.exists())


def _version(cache: Path, tag: str, *, stamp: int) -> OfficialGcsimSourceAcquisition:
    archive = cache / "archives" / f"{tag}.zip"
    tree = cache / "expanded" / tag
    archive.parent.mkdir(parents=True, exist_ok=True)
    (tree / "cmd" / "gcsim").mkdir(parents=True)
    (tree / "pkg" / "simulator").mkdir(parents=True)
    (tree / "pkg" / "model").mkdir(parents=True)
    files = {
        "go.mod": "module github.com/genshinsim/gcsim\n",
        "cmd/gcsim/main.go": "package main\n",
        "pkg/simulator/simulator.go": "package simulator\n",
        "pkg/model/model.go": "package model\n",
    }
    with zipfile.ZipFile(archive, "w") as zipped:
        for relative, content in files.items():
            target = tree / relative
            target.write_text(content, encoding="utf-8")
            zipped.writestr(f"genshinsim-gcsim-{tag}/{relative}", content)
    os.utime(archive, (stamp, stamp))
    os.utime(tree, (stamp, stamp))
    ref = OfficialGcsimSourceRef(
        requested_release=tag, tag=tag, archive_url=f"https://example.invalid/{tag}.zip",
        html_url="", api_url="",
    )
    return OfficialGcsimSourceAcquisition(ref, archive, tree, cache)
