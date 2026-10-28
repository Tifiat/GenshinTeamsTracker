"""Focused R5 risks against the exact Python image; no engine/search/UI run."""
from __future__ import annotations

from collections import deque
from contextlib import closing
import hashlib
import importlib
import importlib.resources
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from .r5_python import (
    ROOT, EXCLUDED_SOURCE_DIRS, baseline_images, install_image,
    product_python_paths, sha, ProductImageFinder, python_images, mapping,
)

import sys
IMAGE = next((item for item in sys.meta_path if isinstance(item,ProductImageFinder)),None)
if IMAGE is None: IMAGE=install_image()
elif IMAGE.pins!=mapping(python_images()): raise ValueError('test Python image differs')

from run_workspace.gcsim import optimizer_artifact_database as artifacts
from run_workspace.gcsim import optimizer_go_selected_inputs as selected
from run_workspace.gcsim import optimizer_go_inputs as inputs
from run_workspace.gcsim import optimizer_go_all_sources as sources
from run_workspace.gcsim import optimizer_go_session as process_session
from run_workspace.gcsim import tree_identity
from run_workspace.gcsim.source_manifest_build import canonical_json, compute_patched_source_tree_sha256
from run_workspace.gcsim.optimizer_go_selected import GcsimOptimizerGoSelectedRequest, GcsimOptimizerGoSelectedSession
from tests.run_workspace.gcsim.test_optimizer_go_selected_inputs import (
    _create_selected_snapshot_database, _selected_snapshot_engine_context,
)


class R5PythonTests(unittest.TestCase):
    def test_lazy_import_pin_mutation_and_missing_rejection(self):
        name = 'run_workspace/gcsim/_r5_lazy_fixture.py'
        module = 'run_workspace.gcsim._r5_lazy_fixture'
        import sys
        raw = b'VALUE = "pinned before lazy import"\n'
        IMAGE.images[name] = raw
        IMAGE.pins[name] = sha(raw)
        try:
            self.assertEqual(importlib.import_module(module).VALUE, 'pinned before lazy import')
            self.assertEqual(IMAGE.imports[name], sha(raw))
            sys.modules.pop(module)
            IMAGE.images[name] = b'raise AssertionError("must not execute mutated bytes")\n'
            with self.assertRaisesRegex(ImportError, 'image changed'):
                importlib.import_module(module)
            with self.assertRaisesRegex(ValueError, 'image mutated'):
                IMAGE.verify()
            with self.assertRaisesRegex(ImportError, 'absent from frozen'):
                importlib.import_module('run_workspace.gcsim._r5_missing_fixture')
        finally:
            sys.modules.pop(module, None)
            IMAGE.images.pop(name); IMAGE.pins.pop(name); IMAGE.imports.pop(name, None)
        IMAGE.verify()

    def test_preimport_rejected_and_package_resources_keep_original_paths(self):
        with self.assertRaisesRegex(RuntimeError, 'before product imports'):
            install_image()
        package = importlib.import_module('hoyolab_export')
        self.assertEqual(Path(package.__file__).resolve(), ROOT / 'hoyolab_export/__init__.py')
        resource = importlib.resources.files(package).joinpath('stat_normalization.py')
        self.assertTrue(resource.is_file())
        self.assertEqual(resource.read_bytes(), (ROOT / 'hoyolab_export/stat_normalization.py').read_bytes())
        self.assertFalse(any(set(Path(name).parts) & EXCLUDED_SOURCE_DIRS for name in product_python_paths()))
        self.assertEqual(Path(IMAGE.find_spec('main').origin), ROOT / 'main.py')
        with self.assertRaisesRegex(ImportError, 'Excluded product'):
            IMAGE.find_spec('hoyolab_export.profile._r5_must_not_enter')

    def test_inventory_equipment_one_view_and_legacy_parity(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / 'synthetic.db'
            _create_selected_snapshot_database(db)
            engine = _selected_snapshot_engine_context()
            for keys, virtual in ((('actor1','actor2','actor3','actor4'), ()),
                                  (('actor1','virtual','actor3','actor4'), ('virtual',))):
                old = artifacts.load_gcsim_optimizer_artifact_database_input(db, engine_context=engine)
                expected = selected.load_selected_equipped_team_snapshot(
                    db, artifact_database=old.database_input, character_keys=keys, virtual_character_keys=virtual)
                with patch.object(artifacts, '_fetch_all_rows_from_connection', wraps=artifacts._fetch_all_rows_from_connection) as fetch, \
                     patch.object(artifacts, '_raw_database_input_sha256', wraps=artifacts._raw_database_input_sha256) as digest:
                    got, snapshot = selected._load_selected_inventory_snapshot(
                        db, engine_context=engine, character_keys=keys, virtual_character_keys=virtual)
                self.assertEqual(got, old)
                self.assertEqual(snapshot, expected)
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(digest.call_count, 1)

    def test_concurrent_wal_change_cannot_mix_inventory_and_equipment(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / 'synthetic.db'
            _create_selected_snapshot_database(db)
            with closing(sqlite3.connect(db)) as writer:
                writer.execute('PRAGMA journal_mode=WAL')
            engine = _selected_snapshot_engine_context()
            keys = ('actor1','actor2','actor3','actor4')
            before = artifacts.load_gcsim_optimizer_artifact_database_input(db, engine_context=engine)
            original = artifacts._fetch_all_rows_from_connection
            def change_after_inventory(connection):
                rows = original(connection)
                with closing(sqlite3.connect(db)) as writer:
                    with writer:
                        writer.execute("UPDATE artifacts SET main_property_value='4781' WHERE id=1")
                        writer.execute("UPDATE account_character_equipped_artifacts SET artifact_id=2 WHERE character_id=101 AND slot_key='flower'")
                return rows
            with patch.object(artifacts, '_fetch_all_rows_from_connection', side_effect=change_after_inventory):
                got, snapshot = selected._load_selected_inventory_snapshot(db, engine_context=engine, character_keys=keys)
            self.assertEqual(got.database_input, before.database_input)
            self.assertEqual(snapshot.wearers[0].assignment.artifact_ids[0], 1)
            # The independently supplied-inventory API still rejects drift.
            with self.assertRaisesRegex(selected.GcsimOptimizerGoSelectedInputError, 'inventory changed'):
                selected.load_selected_equipped_team_snapshot(db, artifact_database=before.database_input, character_keys=keys)

    def test_real_prepare_source_adapter_keeps_wire_and_skips_first_full_report(self):
        from tests.run_workspace.gcsim.test_optimizer_go_all_sources import AllSetSourceBindingTests
        seen = []
        def team(**kwargs):
            seen.append(inputs.build_selected_team_full_config_report.call_count)
            return inputs.build_selected_team_full_config_report.return_value.team
        def combined(*args, **kwargs):
            return inputs.load_gcsim_optimizer_artifact_database_input(), inputs.load_selected_equipped_team_snapshot()
        with patch.object(inputs, 'build_selected_team_payload', side_effect=team), \
             patch.object(inputs, '_load_selected_inventory_snapshot', side_effect=combined):
            case = AllSetSourceBindingTests('test_real_request_preparation_connects_to_all_sets_source_validation')
            case.test_real_request_preparation_connects_to_all_sets_source_validation()
        self.assertGreaterEqual(len(seen), 4)
        self.assertEqual(seen, list(range(len(seen))))

    def test_tree_streaming_scopes_and_only_requested_file_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            files = {'build/owned.bin': b'binary' * 500001, 'source.go': b'package test\r\n',
                     'gtt_engine_manifest.json': b'metadata', 'another.txt': b'other'}
            for name, raw in files.items():
                p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(raw)
            expected = hashlib.sha256()
            for name, raw in sorted(files.items()):
                if name == 'gtt_engine_manifest.json': continue
                expected.update(name.encode()); expected.update(b'\0'); expected.update(raw); expected.update(b'\0')
            selected_hash = {'build/owned.bin': ''}
            got = tree_identity.directory_sha256(root, excluded_relative_paths=('gtt_engine_manifest.json',), file_digests=selected_hash)
            self.assertEqual(got, expected.hexdigest())
            self.assertEqual(selected_hash, {'build/owned.bin': sha(files['build/owned.bin'])})
            patched = compute_patched_source_tree_sha256(root)
            (root / 'build/owned.bin').write_bytes(b'changed binary')
            self.assertEqual(patched, compute_patched_source_tree_sha256(root))
            self.assertNotEqual(got, tree_identity.directory_sha256(root, excluded_relative_paths=('gtt_engine_manifest.json',)))

    def test_engine_context_existing_scope_checks(self):
        from tests.run_workspace.gcsim.test_gcsim_optimizer_engine_context import GcsimOptimizerEngineContextTest
        for name in ('test_resealed_context_uses_store_tree_identity_on_windows',
                     'test_resealed_context_binds_tree_catalog_and_artifact'):
            GcsimOptimizerEngineContextTest(name).debug()

    def test_source_repository_read_once_parity_and_mutations(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            binary = root / 'build/gtt-gcsim.exe'; binary.parent.mkdir(); binary.write_bytes(b'not executed')
            names = {'pkg/core/attributes/stats.go','pkg/core/attributes/element.go',
                     'pkg/core/attacks/attack.go','pkg/enemy/damage.go','internal/artifacts/test/test.go',
                     *sources.NEUTRAL_RULE_LIBRARIES}
            for name in names:
                path = root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(b'package test\r\n')
            (root/'go.mod').write_bytes(b'module test\n')
            manifest = {'patched_source_tree_sha256': compute_patched_source_tree_sha256(root)}
            (root/'build/gtt-source-manifest-body.json').write_text(json.dumps(manifest))
            binding = {'binary_path': str(binary), 'artifact_sha256': sha(binary.read_bytes()),
                       'source_manifest_sha256': sha(canonical_json(manifest).encode()),
                       'capabilities':['gtt_effect_inputs_v1']}
            catalog = SimpleNamespace(source_fingerprint='a'*64,sets=[SimpleNamespace(
                max_rarity=5,key='test',two_piece_modeled=True,four_piece_modeled=True,
                source_files=['internal/artifacts/test/test.go'])])
            legacy = ModuleType('run_workspace.gcsim._r5_legacy_sources')
            legacy.__package__='run_workspace.gcsim'
            exec(compile(baseline_images()['run_workspace/gcsim/optimizer_go_all_sources.py'], '<frozen R4-era Python baseline>', 'exec'), legacy.__dict__)
            counts=[]; original=Path.read_bytes
            opens=[]; original_open=Path.open
            def opened(path,*args,**kwargs):
                opens.append(path)
                return original_open(path,*args,**kwargs)
            def read(path):
                counts.append(path)
                return original(path)
            with patch.object(sources,'load_gcsim_artifact_set_catalog',return_value=catalog), \
                 patch.object(legacy,'load_gcsim_artifact_set_catalog',return_value=catalog):
                with patch.object(Path,'read_bytes',read), patch.object(Path,'open',opened):
                    old = legacy.prepare_all_set_effect_sources(root,binding,include_neutral_rules=True,include_source_repository=True)
                old_reads=counts.count(root/'pkg/core/attributes/stats.go'); old_module_opens=opens.count(root/'go.mod'); counts.clear(); opens.clear()
                with patch.object(Path,'read_bytes',read), patch.object(Path,'open',opened):
                    got = sources.prepare_all_set_effect_sources(root,binding,include_neutral_rules=True,include_source_repository=True)
                self.assertEqual(got,old)
                self.assertEqual(counts.count(root/'pkg/core/attributes/stats.go'),1)
                self.assertEqual(old_reads,2)
                self.assertEqual(old_module_opens,2)
                self.assertEqual(opens.count(root/'go.mod'),1)
                with self.assertRaisesRegex(ValueError,'binary changed'):
                    sources.prepare_all_set_effect_sources(root,{**binding,'artifact_sha256':'0'*64})
                (root/'pkg/core/attributes/stats.go').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'sources differ'):
                    sources.prepare_all_set_effect_sources(root,binding)

    def test_stderr_bounded_complete_log_and_finish_marker_on_long_line(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); binary=root/'dummy.exe';binary.write_bytes(b'never executed')
            request=GcsimOptimizerGoSelectedRequest('unused',{},0,'',optimizer_binary_path=binary)
            session=GcsimOptimizerGoSelectedSession(request)
            lines=['old discarded diagnostic\n']+['x'*3000+'\n' for _ in range(40)]
            lines.append('finish_no_result:'+'z'*10000+' last diagnostic\n')
            done=threading.Event()
            class Stream:
                def __iter__(self):
                    yield from lines
                    done.set()
            process=SimpleNamespace(stderr=Stream(),returncode=3)
            observed=[]
            class Tail(deque):
                def append(self,item):
                    super().append(item)
                    observed.append((len(self),sum(len(row[0]) for row in self)))
            def wait(*args,**kwargs):
                if not done.wait(5):raise AssertionError('stderr reader stalled')
            with patch.object(process_session,'deque',Tail), \
                 patch.object(process_session,'start_optimizer_process',return_value=process), \
                 patch.object(process_session,'_wait_process',side_effect=wait), \
                 patch.object(session,'_register_process'), patch.object(session,'_unregister_process') as unregister, \
                 patch.object(session,'_optimizer_environment',return_value={}):
                with self.assertRaises(process_session.GcsimOptimizerGoError) as error:
                    session._run_go_optimizer(prepared={},compact={},run_dir=root,started=time.monotonic())
            self.assertEqual(error.exception.code,'finish_no_result')
            self.assertTrue(all(count<=8 and chars<=8*2048 for count,chars in observed))
            self.assertLess(len(str(error.exception)),8*2048+250)
            self.assertEqual((root/'optimizer-progress.jsonl').read_text(),''.join(lines))
            unregister.assert_called_once_with(process)

    def test_existing_cancel_finish_and_reader_flags(self):
        from tests.run_workspace.gcsim.test_optimizer_go_selected import GcsimOptimizerGoSelectedTests
        for name in ('test_request_finish_is_separate_from_cancel_and_persists_before_run',
                     'test_active_finish_request_is_idempotent_and_does_not_stop_child',
                     'test_emergency_cancel_stops_only_registered_child_even_after_grace_timeout',
                     'test_progress_records_finish_and_cancel_flags_separately'):
            GcsimOptimizerGoSelectedTests(name).debug()

    def test_existing_adapter_binary_override_and_stage_timing(self):
        from tests.run_workspace.gcsim.test_optimizer_go_selected import GcsimOptimizerGoSelectedTests
        for name in ('test_default_consumer_path_and_override_reach_preflight_and_process',
                     'test_session_writes_bounded_adapter_stage_timings'):
            GcsimOptimizerGoSelectedTests(name).debug()


if __name__ == '__main__':
    unittest.main()
