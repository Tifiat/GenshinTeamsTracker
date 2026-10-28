"""One ROOT-admitted uninstrumented confirmation of the corrected tree pass."""
from __future__ import annotations

from . import r5_python_costs as baseline

import gc
import json
from pathlib import Path
import time

import io
import unittest

from .r5_python import OUT, baseline_images, python_images, map_sha
from tools.managed_optimizer_experiment import managed_scratch


def main():
    output=OUT/'r5-python-tree-confirm-v3.json'
    log=output.with_suffix('.log')
    if output.exists() or log.exists():raise FileExistsError(output)
    before=baseline.base.preserved_state()
    engine=baseline.load_active_gcsim_optimizer_engine_context()
    original=baseline_images()
    old=baseline.legacy_module('_r5_legacy_tree_confirm',original['run_workspace/gcsim/tree_identity.py'])
    root=Path(engine.engine_root);binary=Path(engine.artifact_path)
    def control():
        return baseline._sha256_file(binary),old.directory_sha256(root,excluded_relative_paths=('gtt_engine_manifest.json',))
    def hybrid():
        requested={binary.relative_to(root).as_posix():''}
        tree=baseline.tree_identity.directory_sha256(root,excluded_relative_paths=('gtt_engine_manifest.json',),file_digests=requested)
        return requested[binary.relative_to(root).as_posix()],tree
    record={'schema':'r5_tree_confirmation_v3','engine_calls':0,'search_calls':0,
            'python_source_map_sha256':map_sha(python_images()),'rows':[],
            'order':['hybrid','baseline'],'instrumentation':'perf_counter/process_time only; no tracemalloc or file/read interception',
            'scope':'One ROOT-admitted corrected confirmation, reversed order relative to v1. Only the requested binary streams; ordinary files keep their old read. Current frozen pre-R5 Python control, not reconstructed R4 Python.'}
    stream=io.StringIO()
    with managed_scratch() as job:
        prefix='tools.experiments.gcsim.mvp_polish.test_r5_python.R5PythonTests.'
        suite=unittest.defaultTestLoader.loadTestsFromNames([prefix+'test_tree_streaming_scopes_and_only_requested_file_digest',prefix+'test_engine_context_existing_scope_checks'])
        tests=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        if not tests.wasSuccessful():raise ValueError('hybrid digest scope checks failed')
        record['focused_checks']=tests.testsRun
        for arm,work in (('hybrid',hybrid),('baseline',control)):
            gc.collect()
            wall=time.perf_counter();cpu=time.process_time()
            identities=work()
            cpu=time.process_time()-cpu;wall=time.perf_counter()-wall
            if identities!=(engine.artifact_sha256,engine.engine_tree_sha256):raise ValueError('binary/tree identities differ')
            record['rows'].append({'arm':arm,'wall_ms':wall*1000,'process_cpu_ms':cpu*1000,'binary_sha256':identities[0],'tree_sha256':identities[1]})
    record.update(job_removed=not job.exists(),protected_exact=baseline.base.preserved_state()==before,
                  python_source_unchanged=python_images()==baseline.IMAGE.images)
    if not record['protected_exact'] or not record['python_source_unchanged']:raise ValueError('source/protected state changed')
    baseline.IMAGE.verify()
    log.write_bytes(stream.getvalue().encode())
    output.write_bytes((json.dumps(record,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps(record))


if __name__=='__main__':main()
