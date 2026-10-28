"""Bounded Chasca health-query repair of the exact active engine lineage.

Managed runner owns every generated tree/cache/capture. Source fragments are
reviewable experiment inputs, consolidated into patch0009 only after gates.
No ordinary artifact/character mechanics edits or account writes. Retire with
the Chasca startup acceptance probes; retain only the dated compact receipt.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.parametric_effects.install_neutral import (
    sha, export_delta, relocate_overlay, application_build_report, promote, PATCH_NAME, CONSUMER)
from tools.experiments.gcsim.parametric_effects.verify_candidates import owned_job
from tools.experiments.gcsim.parametric_effects.repair_hit_identity import execute, capture, require_identical_capture
from tools.experiments.gcsim.parametric_effects.capture_equivalence import canonical_capture

SAVED = ROOT / 'data/gcsim/optimizer-go-runs/all_sets-20260926-222806-1d2eda4d'


def paths_in(text):
    paths = re.findall(r'^diff --git a/(\S+) b/\1$', text, re.MULTILINE)
    if not paths or len(paths) != len(set(paths)):
        raise ValueError('Missing/duplicate patch target')
    for name in paths:
        if (not (name.startswith('pkg/') or name.startswith('internal/template/character/'))
                or Path(name).is_absolute() or '..' in Path(name).parts or '\\' in name):
            raise ValueError('Patch escaped observer scope')
    return paths


def rebind_request(original, engine):
    """Keep gameplay, inventory, constraints and budgets; replace engine identity."""
    from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256
    from run_workspace.gcsim.engine_store import load_engine_manifest
    from run_workspace.gcsim.optimizer_engine_context import _manifest_capabilities
    from run_workspace.gcsim.source_manifest_build import canonical_json
    req = json.loads(json.dumps(original))
    manifest = load_engine_manifest(engine)
    body = json.loads((engine / 'build/gtt-source-manifest-body.json').read_bytes())
    binding = dict(binary_path=(engine/'build/gtt-gcsim.exe').as_posix(),
        artifact_sha256=sha(engine/'build/gtt-gcsim.exe'),
        source_manifest_sha256=hashlib.sha256(canonical_json(body).encode()).hexdigest(),
        patch_manifest_sha256=manifest.patch_metadata['patch_stack_sha256'],
        capabilities=sorted(_manifest_capabilities(manifest)))
    binding['binding_sha256'] = canonical_sha256(dict(kind='gtt.standalone_engine_binding.v1',
        **{k: binding[k] for k in ('artifact_sha256','source_manifest_sha256','patch_manifest_sha256')}))
    req['engine'] = binding
    req['context']['trace_context_sha256'] = canonical_sha256(dict(
        kind='gtt.saved_request.engine_rebind.v1', original=original['context']['trace_context_sha256'],
        engine_binding_sha256=binding['binding_sha256']))
    return req


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')), encoding='utf-8')


def initial_gate(engine, consumer, go, job, original):
    from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources
    req = rebind_request(original, engine)
    run = job / 'initial-gate'
    run.mkdir()
    write_json(run/'request.json',req)
    sources = prepare_all_set_effect_sources(engine,req['engine'],include_neutral_rules=True)
    write_json(run/'set-sources.json',sources)
    config = req['context']['prepared_config']['text']
    neutral = re.sub(r'^\w+ add set="[a-z0-9_]+" count=\d+;\s*$', '', config, flags=re.MULTILINE)
    if neutral == config:
        raise ValueError('Saved initial config has no set declarations')
    for seed in req['stochastic']['seeds']:
        folder=run/'verification/contexts/context-health'/f'seed-{seed}'
        folder.mkdir(parents=True)
        cfg=folder/'config.txt'
        cfg.write_text(neutral, encoding='utf-8', newline='\n')
        trace_req=folder/'trace-request.json'
        write_json(trace_req, dict(schema_version=1,context_sha256=sha(cfg),seed=str(seed),iterations=1,
            workers=1,ignore_burst_energy=True,output_mode='compact_ir_v1',include_effect_inputs=True))
        execute([engine/'build/gtt-gcsim.exe','-c',cfg,'-out',folder/'member.json','-gtt-trace-equation',trace_req],timeout=90)
        execute([consumer,'validate-seed-member',folder/'member.json'])
    env=dict(os.environ,GTT_SAVED_INITIAL_RUN=str(run),GTT_REQUIRE_INITIAL_COMPLETE='1',GTT_RULE_SOURCE_BUNDLE=str(run/'set-sources.json'))
    output=execute([go,'test','-p','1','./internal/seteffects','-run','TestSavedInitialPackageDiagnosis','-count=1','-v','-timeout=120s'],cwd=ROOT/'native/gcsim_optimizer',env=env)
    print(output,flush=True)
    return run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate',action='store_true')
    parser.add_argument('--test-only',action='store_true')
    parser.add_argument('--sourcegen-only',action='store_true')
    args=parser.parse_args()
    run_repair(args, fragment_names=('health_query_identity.patch','health_stats_origin.patch'),
        installed_marker='pkg/gttsourcegen/health_field_capture.go',
        original_provider=lambda job: (json.loads((SAVED/'request.json').read_bytes()), sha(SAVED/'request.json')))


def run_repair(args, *, fragment_names, installed_marker, original_provider, label='HEALTH',
               control_config_override=None, capture_inspector=None, use_installed_consumer=False):
    """Shared bounded observer gate; callers supply one exact retained case."""
    if sum((args.activate,args.test_only,args.sourcegen_only))>1: raise ValueError('Choose one gate mode')
    job=owned_job()
    from run_workspace.gcsim.engine_store import GcsimEngineStore,load_engine_manifest,_write_manifest
    from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
    from run_workspace.gcsim.patch_backends import GitApplyPatchBackend,ordered_file_stack_identity
    from run_workspace.gcsim.tree_identity import directory_sha256
    from run_workspace.gcsim.source_manifest_build import compute_patched_source_tree_sha256
    from run_workspace.gcsim.source_acquisition import OfficialGcsimSourceRef,acquire_official_gcsim_source_from_archive
    from run_workspace.gcsim.engine_update import prepare_official_gcsim_engine_update
    from run_workspace.gcsim.engine_compatibility import verify_engine_application_bundle
    from run_workspace.gcsim.runtime_probe import _go_sandbox_env
    bound=load_active_gcsim_optimizer_engine_context()
    active=Path(bound.engine_root)
    if (active/installed_marker).exists():raise ValueError('Repair already installed')
    production=ROOT/'run_workspace/gcsim/patch_stack'
    patches=sorted(production.glob('*.patch'))
    binding=json.loads((active/'build/gtt-source-manifest-input.json').read_bytes())
    if ordered_file_stack_identity(production,patches)[1]!=binding['patch_stack_sha256']:raise ValueError('Active patch binding changed')
    fragments=[Path(__file__).with_name(n) for n in fragment_names]
    fragment_hashes={str(path):sha(path) for path in fragments}
    fragment_paths=sorted({p for f in fragments for p in paths_in(f.read_text(encoding='utf-8'))})
    paths=sorted(set(paths_in((production/PATCH_NAME).read_text(encoding='utf-8'))+fragment_paths))
    changed=job/'observer-delta'
    for name in paths:
        dst=changed/name
        dst.parent.mkdir(parents=True,exist_ok=True)
        if (active/name).is_file():shutil.copy2(active/name,dst)
    for fragment in fragments:
        execute(['git','apply','--recount','--unidiff-zero','--directory',changed.relative_to(ROOT).as_posix(),fragment])
    go=shutil.which('go') or 'C:/Program Files/Go/bin/go.exe'
    overlay=job/'unit-overlay.json'
    write_json(overlay,{'Replace':{str(active/n):str(changed/n) if (changed/n).exists() else '' for n in fragment_paths}})
    print(label+' stage: focused source/compiler tests',flush=True)
    print(execute([go,'test','-overlay='+str(overlay),'-p','2','./pkg/gttsourcegen','./pkg/core/info','./pkg/gttcompact','./pkg/optimization',
        '-run','Test(TypedHealth|Health|V6Health|GTTStats|Neutral|SourceBonus|NoStatSnapshot)','-count=1','-timeout=120s'],cwd=active,timeout=240),flush=True)
    if args.test_only:return
    if args.sourcegen_only:
        print(execute([go,'run','-overlay='+str(overlay),'./cmd/gtt-source-manifest',
            '-root',active,'-binding-in',active/'build/gtt-source-manifest-input.json',
            '-json-out',job/'source-body.json','-go-out',job/'generated_manifest.go',
            '-overlay-out',job/'source-overlay.json','-overlay-dir',job/'source-overlay'],cwd=active,timeout=300),flush=True)
        return
    store=GcsimEngineStore()
    expected=dict(pointer=sha(store.active_state_path),consumer=sha(CONSUMER),engine=bound.artifact_sha256,patch=sha(production/PATCH_NAME))
    original, original_sha = original_provider(job)
    print(label+' stage: clean active lineage reconstruction',flush=True)
    old_manifest=load_engine_manifest(active)
    acquisition=acquire_official_gcsim_source_from_archive(source_ref=OfficialGcsimSourceRef(
        binding['upstream_ref'],binding['upstream_ref'],'','','',binding['upstream_repo']),
        archive_path=old_manifest.metadata['source_archive_path'],cache_dir=job/'upstream')
    if directory_sha256(acquisition.source_dir)!=binding['pristine_source_tree_sha256']:raise ValueError('Archive binding mismatch')
    baseline=job/'baseline-source'
    shutil.copytree(acquisition.source_dir,baseline)
    applied=GitApplyPatchBackend().apply(engine_dir=baseline,patch_stack_dir=production)
    if not applied.applied or compute_patched_source_tree_sha256(baseline)!=compute_patched_source_tree_sha256(active):raise ValueError('Active source replay mismatch')
    execute(['git','apply','-R','--directory',baseline.relative_to(ROOT).as_posix(),production/PATCH_NAME])
    stack=job/'patch-stack'
    stack.mkdir()
    for path in patches:shutil.copy2(path,stack/path.name)
    delta=stack/PATCH_NAME
    delta.write_text(export_delta(baseline,changed,paths),encoding='utf-8',newline='\n')
    native=ROOT/'native/gcsim_optimizer'
    consumer=job/'gtt-optimizer.exe'
    if use_installed_consumer:
        shutil.copy2(CONSUMER,consumer)
    else:
        execute([go,'build','-trimpath','-o',consumer,'./cmd/gtt-optimizer'],cwd=native)
    print(label+' stage: candidate engine build',flush=True)
    def diagnostic_runner(command,cwd,env,timeout):
        result=subprocess.run(command,cwd=cwd,env=env,timeout=timeout,capture_output=True,text=True,encoding='utf-8')
        if result.returncode:
            print(label+' build diagnostic: '+(result.stdout+result.stderr)[-16000:],flush=True)
        return result
    report=prepare_official_gcsim_engine_update(release=binding['upstream_ref'],store_dir=job/'engine-store',patch_stack_dir=stack,
        source_acquirer=lambda **_:acquisition,patch_backend=GitApplyPatchBackend(),build_artifact=True,activate=False,
        prune_engine_store=False,clean_go_build_cache=False,go_executable=go,go_work_dir=job/'go-runtime',runtime_probe_timeout_seconds=300,
        artifact_build_runner=diagnostic_runner)
    if not report.success:raise RuntimeError(report.error)
    engine=Path(report.engine_path)
    relocate_overlay(engine,engine.parent.parent/'staging'/engine.name)
    manifest=load_engine_manifest(engine)
    error=verify_engine_application_bundle(engine,application_build_report(report,manifest.metadata),optimizer_binary=consumer)
    if error:raise RuntimeError(error)
    manifest=replace(manifest,metadata={**manifest.metadata,'application_compatibility_status':'passed'},
        engine_tree_hash=directory_sha256(engine,excluded_relative_paths=('gtt_engine_manifest.json',)))
    _write_manifest(engine/'gtt_engine_manifest.json',manifest)
    for folder in ('internal/artifacts','internal/characters'):
        if directory_sha256(active/folder)!=directory_sha256(engine/folder):raise ValueError('Ordinary mechanics source changed')
    print(execute([go,'test','-p','2','./pkg/gttsourcegen','./pkg/core/info','./pkg/gttcompact','./internal/template/character',
        '-count=1','-timeout=180s'],cwd=engine,env=_go_sandbox_env(job/'go-runtime'),timeout=600),flush=True)
    print(execute([go,'test','-p','2','./pkg/optimization','-run','TestHealthSourceBonus','-count=1','-timeout=120s'],
        cwd=engine,env=_go_sandbox_env(job/'go-runtime'),timeout=300),flush=True)
    print(label+' stage: exact initial packages, two neutral seeds and observed damage invariance',flush=True)
    gate=initial_gate(engine,consumer,go,job,original)
    if capture_inspector is not None:
        capture_inspector(engine, job, gate)
    config=control_config_override or original['context']['prepared_config']['text']
    previous=capture(Path(bound.artifact_path),job,'old-observer-control',config)
    control=capture(engine/'build/gtt-gcsim.exe',job,'new-observer-control',config)
    damages=lambda m:[{k:c[k] for k in ('channel_id','actor_key','kind','attack_tag','damage_type','hit_count','baseline_damage')} for c in m['channels']]
    if previous['duration_ms']!=control['duration_ms'] or damages(previous)!=damages(control):raise ValueError('Old/new observed gameplay differs')
    print(execute([go,'test','-p','1','./...','-count=1','-timeout=180s'],cwd=native,
        env=dict(os.environ,GTT_RULE_SOURCE_BUNDLE=str(gate/'set-sources.json')),timeout=360),flush=True)
    reference=next((gate/'verification/contexts').glob('context-*/seed-742031889'))
    neutral=(reference/'config.txt').read_text(encoding='utf-8')
    def verify_installed(destination):
        installed=load_active_gcsim_optimizer_engine_context()
        if Path(installed.artifact_path).resolve()!=(destination/'build/gtt-gcsim.exe').resolve():raise ValueError('Wrong installed path')
        capture(Path(installed.artifact_path),job,'installed-observer-neutral',neutral,effects=True)
        require_identical_capture(canonical_capture((reference/'member.json').read_bytes(),(reference/'member.json.effects.json').read_bytes()),
            canonical_capture((job/'installed-observer-neutral.json').read_bytes(),(job/'installed-observer-neutral.json.effects.json').read_bytes()))
    if any(sha(Path(path))!=digest for path,digest in fragment_hashes.items()):
        raise ValueError('Repair inputs changed during the gate; do not promote an obsolete candidate')
    if sha(Path(bound.artifact_path))!=expected['engine']:
        raise ValueError('Previous active executable changed during the gate')
    destination=promote(store,engine,consumer,delta,job,expected,verify_installed=verify_installed) if args.activate else engine
    print(label+'_INSTALL '+json.dumps(dict(activated=args.activate,engine_id=report.engine_id,engine_sha256=report.artifact_sha256,
        consumer_sha256=sha(consumer),source_manifest_sha256=manifest.metadata['source_manifest_body_sha256'],patch_sha256=sha(delta),
        stack_sha256=ordered_file_stack_identity(stack,sorted(stack.glob('*.patch')))[1],previous_engine_id=bound.engine_id,
        installed_path=str(destination),original_request_sha256=original_sha,ui_verified=False,
        old_new_observed_damage_identical=True,control_config_override=control_config_override is not None,
        consumer_reused=use_installed_consumer,original_packages_complete=True)),flush=True)


if __name__=='__main__':main()
