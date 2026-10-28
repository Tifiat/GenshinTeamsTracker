"""One bounded active-lineage observer repair, GP-3 Navia coverage gate.

Run only in managed_optimizer_experiment.py. Reconstruct the ACTIVE source from
its exact archive/patch binding, amend consolidated patch0009, build through the
normal updater, test real Song response, then optionally promote transactionally.
All expanded trees/captures/caches are removed by the runner; stdout is the
minimal receipt to retain in the existing Go design. Retire with neutral research
helpers after installed observer/button acceptance. No account DB reads/writes.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.parametric_effects.install_neutral import (
    sha, export_delta, relocate_overlay, application_build_report, promote, PATCH_NAME, CONSUMER)
from tools.experiments.gcsim.parametric_effects.check_stat_queries import patch_paths
from tools.experiments.gcsim.parametric_effects.verify_candidates import owned_job
from tools.experiments.gcsim.parametric_effects.capture_equivalence import canonical_capture

# Deliberately saturated healing isolates hit attribution from the separately
# disclosed counterfactual healing-amount approximation. No damage crit/RNG proc.
CONFIG = '''kokomi char lvl=90/90 cons=0 talent=9,9,9;
kokomi add weapon="prototypeamber" refine=1 lvl=90/90;
kokomi add stats hp=1000000 atk=311 cr=-1 cd=0.5;
kaeya char lvl=90/90 cons=0 talent=9,9,9;
kaeya add weapon="coolsteel" refine=1 lvl=90/90;
kaeya add stats hp=4780 atk=311 cr=-1 cd=0.5;
amber char lvl=90/90 cons=0 talent=9,9,9;
amber add weapon="slingshot" refine=1 lvl=90/90;
amber add stats hp=4780 atk=311 cr=-1 cd=0.5;
lisa char lvl=90/90 cons=0 talent=9,9,9;
lisa add weapon="magicguide" refine=1 lvl=90/90;
lisa add stats hp=4780 atk=311 cr=-1 cd=0.5;
options iteration=1 duration=20 workers=1;
target lvl=90 hp=999999999 resist=0.1 radius=2 pos=0,2.4;
target lvl=90 hp=999999999 resist=0.1 radius=2 pos=0.5,2.4;
active kokomi;
kokomi skill;
wait(430);
for let i=0; i<12; i=i+1 { kaeya attack; wait(10); }
'''
CONTROL = CONFIG.replace('kokomi add stats', 'kokomi add set="songofdayspast" count=4;\nkokomi add stats')


def execute(command, *, cwd=ROOT, env=None, timeout=180):
    try:
        result = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or b''
        if isinstance(output, bytes): output=output.decode('utf-8',errors='replace')
        raise RuntimeError(f'Technical command timeout after {timeout}s; partial output: {output[-12000:]}') from exc
    if result.returncode:
        output=result.stdout + result.stderr
        raise RuntimeError(f"Command failed {command[0]}: {output[:7000]}\n...\n{output[-7000:]}")
    return result.stdout


def capture(executable: Path, job: Path, name: str, config: str, *, effects=False, trace=True, raw=False):
    cfg, out = job / (name + '.txt'), job / (name + '.json')
    cfg.write_text(config, encoding='utf-8', newline='\n')
    command = [executable, '-c', cfg, '-out', out]
    if trace:
        request = job / (name + '-request.json')
        request.write_text(json.dumps(dict(schema_version=1, context_sha256=sha(cfg), seed='742031889',
            iterations=1, workers=1, ignore_burst_energy=True, output_mode='' if raw else 'compact_ir_v1', include_effect_inputs=effects)), encoding='utf-8')
        command += ['-gtt-trace-equation', request]
    execute(command, timeout=60)
    return json.loads(out.read_bytes())


def require_identical_capture(expected, actual):
    """Keep the strict gate; print bounded semantic differences before cleanup."""
    differences = []
    missing = object()

    def short(value):
        if value is missing:
            return '<missing>'
        return repr(value)[:180]

    def visit(left, right, path):
        if len(differences) >= 8:
            return
        if not isinstance(left, (dict, list)) and type(left) is type(right) and left == right:
            return
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(left.keys() | right.keys()):
                visit(left.get(key, missing), right.get(key, missing), f'{path}.{key}')
                if len(differences) >= 8:
                    break
        elif isinstance(left, list) and isinstance(right, list):
            if len(left) != len(right):
                differences.append(f'{path}.length: {len(left)} -> {len(right)}')
            for index, (a, b) in enumerate(zip(left, right)):
                visit(a, b, f'{path}[{index}]')
                if len(differences) >= 8:
                    break
        else:
            differences.append(f'{path}: {short(left)} -> {short(right)}')

    visit(expected, actual, '$')
    if differences:
        raise ValueError('Relocated installed capture differs (first <=8 differences): '
                         + '; '.join(differences))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate', action='store_true')
    parser.add_argument('--probe-only', action='store_true')
    args = parser.parse_args()
    job = owned_job()
    from run_workspace.gcsim.engine_store import GcsimEngineStore, load_engine_manifest, _write_manifest
    from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
    from run_workspace.gcsim.source_acquisition import OfficialGcsimSourceRef, acquire_official_gcsim_source_from_archive
    from run_workspace.gcsim.engine_update import prepare_official_gcsim_engine_update
    from run_workspace.gcsim.patch_backends import GitApplyPatchBackend, ordered_file_stack_identity
    from run_workspace.gcsim.engine_compatibility import verify_engine_application_bundle
    from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources
    from run_workspace.gcsim.tree_identity import directory_sha256
    from run_workspace.gcsim.source_manifest_build import compute_patched_source_tree_sha256
    from run_workspace.gcsim.runtime_probe import _go_sandbox_env

    store = GcsimEngineStore()
    bound = load_active_gcsim_optimizer_engine_context()
    active = Path(bound.engine_root)
    old_manifest = load_engine_manifest(active)
    binding = json.loads((active / 'build/gtt-source-manifest-input.json').read_bytes())
    production = ROOT / 'run_workspace/gcsim/patch_stack'
    patches = sorted(production.glob('*.patch'))
    if ordered_file_stack_identity(production, patches)[1] != binding['patch_stack_sha256']:
        raise ValueError('Active source and production patches differ')
    if (active / 'pkg/gtttrace/hit_identity.go').exists():
        raise ValueError('Hit identity repair already present; do not redeploy')
    expected = dict(pointer=sha(store.active_state_path), consumer=sha(CONSUMER),
                    engine=bound.artifact_sha256, patch=sha(production / PATCH_NAME))
    go = shutil.which('go') or 'C:/Program Files/Go/bin/go.exe'
    previous_ordinary = capture(Path(bound.artifact_path), job, 'previous-song-ordinary', CONTROL, trace=False)
    if args.probe_only:
        capture(Path(bound.artifact_path),job,'probe-neutral',CONFIG,effects=True)
        sidecar=json.loads((job/'probe-neutral.json.effects.json').read_bytes())
        if set(sidecar['character_keys'])!={'amber','kaeya','lisa','sangonomiyakokomi'}:
            raise ValueError('Test scenario does not satisfy four-character panel contract')
        execute([CONSUMER,'validate-seed-member',job/'probe-neutral.json'])
        print('SONG_CONFIG_PROBE '+json.dumps(previous_ordinary['statistics']['dps']),flush=True)
        return
    print('HIT_IDENTITY_STAGE reconstruct active source', flush=True)
    acquisition = acquire_official_gcsim_source_from_archive(source_ref=OfficialGcsimSourceRef(
        binding['upstream_ref'], binding['upstream_ref'], '', '', '', binding['upstream_repo']),
        archive_path=old_manifest.metadata['source_archive_path'], cache_dir=job / 'upstream')
    if directory_sha256(acquisition.source_dir) != binding['pristine_source_tree_sha256']:
        raise ValueError('Archive is not the active pristine input')
    baseline = job / 'baseline-source'
    shutil.copytree(acquisition.source_dir, baseline)
    applied = GitApplyPatchBackend().apply(engine_dir=baseline, patch_stack_dir=production)
    if not applied.applied or compute_patched_source_tree_sha256(baseline) != compute_patched_source_tree_sha256(active):
        raise ValueError('Clean replay differs from ACTIVE source')
    fragment = Path(__file__).with_name('hit_identity.patch')
    paths = sorted(set(patch_paths((production / PATCH_NAME).read_text(encoding='utf-8')) + patch_paths(fragment.read_text(encoding='utf-8'))))
    changed = job / 'observer-delta'
    for name in paths:
        dst = changed / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if (active / name).is_file(): shutil.copy2(active / name, dst)
    execute(['git', 'apply', '--recount', '--unidiff-zero', '--directory', changed.relative_to(ROOT).as_posix(), fragment])
    # Diff against the source immediately BEFORE patch0009, consolidating rather
    # than leaving a second production observer patch or changing older layers.
    execute(['git', 'apply', '-R', '--directory', baseline.relative_to(ROOT).as_posix(), production / PATCH_NAME])
    stack = job / 'patch-stack'
    stack.mkdir()
    for path in patches: shutil.copy2(path, stack / path.name)
    delta = stack / PATCH_NAME
    delta.write_text(export_delta(baseline, changed, paths), encoding='utf-8', newline='\n')
    print('HIT_IDENTITY_STAGE build consumer and candidate engine', flush=True)
    native = ROOT / 'native/gcsim_optimizer'
    print(execute([go, 'test', '-p', '1', './...', '-count=1', '-timeout=120s'], cwd=native), flush=True)
    consumer = job / 'gtt-optimizer.exe'
    execute([go, 'build', '-trimpath', '-o', consumer, './cmd/gtt-optimizer'], cwd=native)
    report = prepare_official_gcsim_engine_update(release=binding['upstream_ref'], store_dir=job / 'engine-store',
        patch_stack_dir=stack, source_acquirer=lambda **_: acquisition, patch_backend=GitApplyPatchBackend(),
        build_artifact=True, activate=False, prune_engine_store=False, clean_go_build_cache=False,
        go_executable=go, go_work_dir=job/'go-runtime', runtime_probe_timeout_seconds=300)
    if not report.success: raise RuntimeError(report.error)
    engine = Path(report.engine_path)
    relocate_overlay(engine, engine.parent.parent / 'staging' / engine.name)
    manifest = load_engine_manifest(engine)
    error = verify_engine_application_bundle(engine, application_build_report(report, manifest.metadata), optimizer_binary=consumer)
    if error: raise RuntimeError(error)
    manifest = replace(manifest, metadata={**manifest.metadata, 'application_compatibility_status':'passed'},
        engine_tree_hash=directory_sha256(engine, excluded_relative_paths=('gtt_engine_manifest.json',)))
    _write_manifest(engine / 'gtt_engine_manifest.json', manifest)
    print('HIT_IDENTITY_STAGE real multi-target Song response', flush=True)
    # No set implementation or character source may differ from active.
    for folder in ('internal/artifacts', 'internal/characters'):
        if directory_sha256(active / folder) != directory_sha256(engine / folder):
            raise ValueError('Game mechanics source changed')
    print(execute([go,'test','-p','2','./pkg/gtttrace','./pkg/core/info','./pkg/enemy','./pkg/optimization/optstats',
        '-run','Test(HitIdentity|Neutral|GOB11A)','-count=1','-timeout=120s'],cwd=engine,
        env=_go_sandbox_env(job/'go-runtime'),timeout=600),flush=True)
    capture(engine / 'build/gtt-gcsim.exe', job, 'song-neutral', CONFIG, effects=True)
    control = capture(engine / 'build/gtt-gcsim.exe', job, 'song-control', CONTROL)
    capture(engine / 'build/gtt-gcsim.exe',job,'song-neutral-raw',CONFIG,raw=True)
    capture(engine / 'build/gtt-gcsim.exe',job,'song-control-raw',CONTROL,raw=True)
    ordinary = capture(engine / 'build/gtt-gcsim.exe', job, 'song-ordinary', CONTROL, trace=False)
    before, after = [row['statistics']['dps']['mean'] for row in (previous_ordinary,ordinary)]
    compact = sum(float(ch['baseline_damage']) for ch in control['channels']) / (control['duration_ms']/1000)
    if not math.isclose(before,after,rel_tol=1e-12,abs_tol=1e-9) or not math.isclose(after,compact,rel_tol=1e-12,abs_tol=1e-9):
        raise ValueError(f'Ordinary old/new/compact mismatch: {before}/{after}/{compact}')
    source_binding = dict(binary_path=str(engine/'build/gtt-gcsim.exe'),artifact_sha256=report.artifact_sha256,
        source_manifest_sha256=manifest.metadata['source_manifest_body_sha256'],capabilities=report.gtt_capabilities)
    source = prepare_all_set_effect_sources(engine,source_binding,include_neutral_rules=True)
    source_path=job/'rule-sources.json'
    source_path.write_text(json.dumps(source),encoding='utf-8')
    env=dict(os.environ,GTT_RULE_SOURCE_BUNDLE=str(source_path),GTT_HIT_IDENTITY_GATE=str(job))
    print(execute([go,'test','-p','1','./internal/seteffects','-run','TestLiveSong','-count=1','-v','-timeout=120s'],cwd=native,env=env),flush=True)
    print(execute([go,'test','-p','1','./internal/seteffects','-count=1','-timeout=120s'],cwd=native,env=env),flush=True)
    # Validate the full consumer against this engine's source, and rebuild the
    # actual binary again, not just the source-bound test executable.
    print(execute([go,'test','-p','1','./...','-count=1','-timeout=120s'],cwd=native,env=env),flush=True)
    execute([go,'build','-trimpath','-o',consumer,'./cmd/gtt-optimizer'],cwd=native)
    error=verify_engine_application_bundle(engine,application_build_report(report,manifest.metadata),optimizer_binary=consumer)
    if error: raise RuntimeError(error)
    if sha(store.active_state_path)!=expected['pointer'] or sha(CONSUMER)!=expected['consumer'] or sha(Path(bound.artifact_path))!=expected['engine']:
        raise ValueError('Active bundle changed during repair gate')
    if ordered_file_stack_identity(production,sorted(production.glob('*.patch')))[1]!=binding['patch_stack_sha256']:
        raise ValueError('Production patch stack changed during gate')
    print('HIT_IDENTITY_VALIDATED '+json.dumps(dict(engine_id=report.engine_id,
        engine_sha256=report.artifact_sha256, consumer_sha256=sha(consumer),
        source_manifest_sha256=source_binding['source_manifest_sha256'], patch_sha256=sha(delta),
        stack_sha256=ordered_file_stack_identity(stack,sorted(stack.glob('*.patch')))[1],
        ordinary_before=before, ordinary_after=after, compact=compact)),flush=True)
    def verify_installed(destination):
        # Exercise the installed path after relocation, not just staging bytes.
        installed=load_active_gcsim_optimizer_engine_context()
        if Path(installed.artifact_path).resolve()!= (destination/'build/gtt-gcsim.exe').resolve():
            raise ValueError('Active path differs from installed candidate')
        capture(Path(installed.artifact_path),job,'installed-song-neutral',CONFIG,effects=True)
        require_identical_capture(
            canonical_capture((job/'song-neutral.json').read_bytes(), (job/'song-neutral.json.effects.json').read_bytes()),
            canonical_capture((job/'installed-song-neutral.json').read_bytes(), (job/'installed-song-neutral.json.effects.json').read_bytes()))
    destination=promote(store,engine,consumer,delta,job,expected,verify_installed=verify_installed) if args.activate else engine
    print('HIT_IDENTITY_INSTALL '+json.dumps(dict(activated=args.activate,engine_id=report.engine_id,
        engine_sha256=report.artifact_sha256,consumer_sha256=sha(consumer),source_manifest_sha256=source_binding['source_manifest_sha256'],
        patch_sha256=sha(delta),stack_sha256=ordered_file_stack_identity(stack, sorted(stack.glob('*.patch')))[1],
        previous_engine_id=bound.engine_id,previous_consumer_sha256=expected['consumer'],installed_path=str(destination),
        config_sha256=hashlib.sha256(CONFIG.encode()).hexdigest(),ordinary_before=before,ordinary_after=after,compact=compact,
        game_mechanics_unchanged=True,ui_verified=False)),flush=True)


if __name__=='__main__': main()
