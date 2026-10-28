"""One bounded read-only R5 preparation comparison, without simulations."""
from __future__ import annotations

from .r5_python import install_image, baseline_images, python_images, OUT, sha, map_sha
IMAGE = install_image()

from contextlib import closing
import gc
import json
from pathlib import Path
import sqlite3
import time
import tracemalloc
import argparse
from types import ModuleType
from unittest.mock import patch
from urllib.parse import quote

from tools.managed_optimizer_experiment import managed_scratch
from . import r1_button as base
from run_workspace.gcsim import optimizer_artifact_database as artifacts
from run_workspace.gcsim import optimizer_go_selected_inputs as selected
from run_workspace.gcsim import optimizer_go_all_sources as sources
from run_workspace.gcsim import tree_identity
from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context, _sha256_file
from run_workspace.gcsim.source_manifest_build import canonical_json


def legacy_module(name, source):
    module=ModuleType('run_workspace.gcsim.'+name)
    module.__package__='run_workspace.gcsim'
    exec(compile(source,'<prospective pre-R5 Python source>','exec'),module.__dict__)
    return module


def cost(work):
    gc.collect()
    reads={'opens':0,'binary_bytes_read':0,'text_characters_read':0}
    opened=Path.open
    class Reader:
        def __init__(self,handle): self.handle=handle
        def __enter__(self): self.handle.__enter__(); return self
        def __exit__(self,*args): return self.handle.__exit__(*args)
        def __getattr__(self,name): return getattr(self.handle,name)
        def read(self,*args,**kwargs):
            data=self.handle.read(*args,**kwargs)
            reads['binary_bytes_read' if isinstance(data,bytes) else 'text_characters_read']+=len(data)
            return data
        def readinto(self,buffer):
            count=self.handle.readinto(buffer)
            reads['binary_bytes_read']+=count
            return count
    def open_counted(path,*args,**kwargs):
        reads['opens']+=1
        return Reader(opened(path,*args,**kwargs))
    tracemalloc.start()
    wall=time.perf_counter(); cpu=time.process_time()
    with patch.object(Path,'open',open_counted): value=work()
    cpu=time.process_time()-cpu; wall=time.perf_counter()-wall
    current,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
    return value,{'wall_ms':wall*1000,'process_cpu_ms':cpu*1000,
                 'traced_peak_bytes':peak,'traced_retained_bytes':current,**reads,
                 'scope':'Instrumentation included; one sample, local Python process CPU only.'}


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--tree-only',action='store_true')
    args=parser.parse_args()
    output=OUT/('r5-python-tree-costs-v2.json' if args.tree_only else 'r5-python-costs-v1.json')
    if output.exists(): raise FileExistsError(output)
    before=base.preserved_state()
    engine=load_active_gcsim_optimizer_engine_context()
    if engine.artifact_sha256!='f1e076b7fa9d292d0bab83aed9d3db0ec917437b288dcc6798cd69f4718f9b93':
        raise ValueError('producer differs from R4')
    original=baseline_images()
    old_tree=legacy_module('_r5_legacy_tree',original['run_workspace/gcsim/tree_identity.py'])
    old_sources=legacy_module('_r5_legacy_sources',original['run_workspace/gcsim/optimizer_go_all_sources.py'])
    root=Path(engine.engine_root);binary=Path(engine.artifact_path)
    record={'schema':'r5_python_saved_input_costs_v1','engine_calls':0,'search_calls':0,
            'python_baseline_map_sha256':map_sha(original),'python_candidate_map_sha256':map_sha(python_images()),
            'producer_sha256':engine.artifact_sha256,
            'limit':'Prospectively frozen current Python baseline, not a reconstructed R4 Python identity. Retained current inputs only; no full-button or universal speed claim.'}
    with managed_scratch() as job:
        live_db,_profile,_=base.gate._active_source(base.ROOT)
        snapshot=job/'inventory.db'
        with closing(sqlite3.connect(f"file:{quote(Path(live_db).as_posix(),safe='/:')}?mode=ro",uri=True)) as source, \
             closing(sqlite3.connect(snapshot)) as target:
            source.backup(target)
        keys=('bennett','chasca','furina','ororon')
        def two_reads():
            loaded=artifacts.load_gcsim_optimizer_artifact_database_input(snapshot,engine_context=engine)
            if not loaded.ready: raise ValueError(loaded.issues)
            snap=selected.load_selected_equipped_team_snapshot(snapshot,artifact_database=loaded.database_input,
                    character_keys=keys,virtual_character_keys=keys)
            return loaded,snap
        def one_view():
            return selected._load_selected_inventory_snapshot(snapshot,engine_context=engine,
                    character_keys=keys,virtual_character_keys=keys)
        if not args.tree_only:
            old,old_cost=cost(two_reads)
            new,new_cost=cost(one_view)
            if old!=new:raise ValueError('inventory/equipment cost outputs differ')
            database=new[0].database_input
            if len(database.artifacts)!=604 or database.artifact_database_input_sha256!='32e4a8352f1b17173f1f088845cdd8ca0a600499231ffd46b24ee9e79387f60b':
                raise ValueError('saved full-account inventory input differs')
            record['inventory_snapshot']={'before':old_cost,'after':new_cost,'artifacts':604,
                'input_sha256':database.artifact_database_input_sha256,'equipment_sha256':new[1].equipment_rows_sha256,
                'transaction_count_before':2,'transaction_count_after':1,'inventory_hash_count_before':2,'inventory_hash_count_after':1,
                'scope':'Same owned saved full inventory, four explicit service-only virtual baselines; not a full config or UI timing.'}
        def two_hash_passes():
            return _sha256_file(binary),old_tree.directory_sha256(root,excluded_relative_paths=('gtt_engine_manifest.json',))
        def same_stream():
            requested={binary.relative_to(root).as_posix():''}
            digest=tree_identity.directory_sha256(root,excluded_relative_paths=('gtt_engine_manifest.json',),file_digests=requested)
            return requested[binary.relative_to(root).as_posix()],digest
        old,old_cost=cost(two_hash_passes)
        new,new_cost=cost(same_stream)
        if old!=new or old!=(engine.artifact_sha256,engine.engine_tree_sha256):
            raise ValueError('distinct binary/tree digest scopes differ')
        record['binary_and_store_tree']={'before':old_cost,'after':new_cost,'binary_bytes':binary.stat().st_size,
            'binary_sha256':new[0],'store_tree_sha256':new[1],
            'retained':'The later source-stage integrity recheck remains; files are mutable across preparation stages.'}
        manifest=json.loads((root/'build/gtt-source-manifest-body.json').read_bytes())
        binding={'binary_path':str(binary),'artifact_sha256':engine.artifact_sha256,
                 'source_manifest_sha256':sha(canonical_json(manifest).encode()),'capabilities':engine.capabilities}
        if not args.tree_only:
            old,old_cost=cost(lambda:old_sources.prepare_all_set_effect_sources(root,binding,include_neutral_rules=True,include_source_repository=True))
            new,new_cost=cost(lambda:sources.prepare_all_set_effect_sources(root,binding,include_neutral_rules=True,include_source_repository=True))
            if old!=new:raise ValueError('source envelopes differ')
            record['source_envelope']={'before':old_cost,'after':new_cost,'canonical_sha256':sha(canonical_json(new).encode()),
                'repository_files':len(new['rule_repository']['files']),'repository_text_bytes':sum(len(v['text'].encode()) for v in new['rule_repository']['files'].values()),
                'retained':'Catalog and later mutable-stage validation scopes remain distinct; existing required repository supplies source text/go.mod bytes.'}
    record.update(job_removed=not job.exists(),protected_exact=base.preserved_state()==before,
                  python_source_unchanged=python_images()==IMAGE.images,imported_product_sources=IMAGE.verify(),
                  first_full_report={'before':2,'after':1,'scope':'Call-count/wire parity checked separately; no isolated real-config speed claim.'})
    if not record['protected_exact'] or not record['python_source_unchanged']:raise ValueError('owned input/source protection changed')
    output.write_bytes((json.dumps(record,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps({k:v for k,v in record.items() if k!='imported_product_sources'}))


if __name__=='__main__':main()
