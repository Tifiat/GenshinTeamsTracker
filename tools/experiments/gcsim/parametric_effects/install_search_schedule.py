"""Install the bounded neutral scheduling repair after native regressions.

Managed scratch owns candidate/cache/rollback bytes; stdout is the compact
receipt. Never rewrites the original matrix install.json or any GCSIM engine.
Retire with this matrix search-regression gate.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from tools.experiments.gcsim.parametric_effects.verify_candidates import owned_job
from tools.experiments.gcsim.parametric_effects.repair_hit_identity import execute
from tools.experiments.gcsim.parametric_effects.install_neutral import sha
from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context


def validate_active_source_oracle(job, engine, go, cwd):
    from run_workspace.gcsim.engine_store import load_engine_manifest
    from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources
    manifest=load_engine_manifest(engine.engine_root)
    binding=dict(binary_path=engine.artifact_path,artifact_sha256=engine.artifact_sha256,
        source_manifest_sha256=manifest.metadata['source_manifest_body_sha256'],capabilities=engine.capabilities)
    sources=prepare_all_set_effect_sources(engine.engine_root,binding,include_neutral_rules=True)
    path=job/'rule-sources.json'
    path.write_text(json.dumps(sources),encoding='utf-8')
    env=dict(os.environ,GTT_RULE_SOURCE_BUNDLE=str(path))
    print(execute([go,'test','-p','1','./internal/seteffects',
        '-run','Test(Rule|Neutral|Compact)',
        '-bench','Benchmark(Compact|RuleWorld)','-benchmem','-benchtime=200ms',
        '-count=1','-timeout=90s'],cwd=cwd,env=env,timeout=110),flush=True)
    print(execute([go,'test','-p','1','./internal/allsets','-run','TestNeutralCoordinatorOneCaptureInventoryOracle',
        '-count=1','-v','-timeout=60s'],cwd=cwd,env=env,timeout=90),flush=True)


def main():
    job=owned_job()
    binary=ROOT/'native/gcsim_optimizer/gtt-optimizer.exe'
    before=sha(binary)
    engine=load_active_gcsim_optimizer_engine_context()
    go=shutil.which('go') or r'C:\Program Files\Go\bin\go.exe'
    cwd=ROOT/'native/gcsim_optimizer'
    print(execute([go,'test','-p','1','./...','-count=1','-timeout=120s'],cwd=cwd,timeout=240),flush=True)
    validate_active_source_oracle(job,engine,go,cwd)
    candidate=job/'gtt-optimizer.exe'
    execute([go,'build','-trimpath','-o',candidate,'./cmd/gtt-optimizer'],cwd=cwd,timeout=90)
    active=load_active_gcsim_optimizer_engine_context()
    if active!=engine or sha(binary)!=before: raise ValueError('Installed engine/consumer changed during build')
    backup=job/'previous-optimizer.exe'
    shutil.copy2(binary,backup)
    expected=sha(candidate)
    try:
        shutil.copy2(candidate,binary)
        if sha(binary)!=expected: raise ValueError('Installed consumer differs from candidate')
    except BaseException:
        shutil.copy2(backup,binary)
        raise
    print('SEARCH_SCHEDULE_INSTALL '+json.dumps(dict(previous_optimizer_sha256=before,optimizer_sha256=expected,
        engine_id=engine.engine_id,engine_sha256=engine.artifact_sha256,engine_changed=False,native_suite='pass')),flush=True)


if __name__=='__main__': main()
