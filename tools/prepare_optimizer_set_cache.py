"""Prepare the shipped, source-only optimizer set cache from the active engine.

Run under managed_optimizer_experiment.py. Source envelopes and build work stay
in its disposable job. The only retained product is the bounded cache under
native/gcsim_optimizer/set-rule-cache (or an explicit directory in that job).
No account, engine, rotation or equipment changes; no simulations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MAX_PROVENANCE_FILES = 512
MAX_PROVENANCE_BYTES = 64 * 1024 * 1024


def _is_reparse_point(info: os.stat_result) -> bool:
    return bool(getattr(info, 'st_file_attributes', 0) &
                getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))


def _require_regular_file(path: Path, info: os.stat_result) -> None:
    if stat.S_ISLNK(info.st_mode) or _is_reparse_point(info) or not stat.S_ISREG(info.st_mode):
        raise ValueError(f'Unsafe cache entry: {path}')


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _require_same_file(path: Path, expected: os.stat_result, actual: os.stat_result) -> None:
    _require_regular_file(path, actual)
    if _file_identity(expected) != _file_identity(actual):
        raise ValueError(f'Cache entry changed while collecting provenance: {path}')


def _read_cache_entry(path: Path, before: os.stat_result) -> bytes:
    _require_regular_file(path, before)
    flags = (os.O_RDONLY | getattr(os, 'O_BINARY', 0) |
             getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    descriptor = os.open(path, flags)
    try:
        with os.fdopen(descriptor, 'rb') as stream:
            descriptor = -1
            _require_same_file(path, before, os.fstat(stream.fileno()))
            _require_same_file(path, before, path.lstat())
            data = stream.read(before.st_size)
            _require_same_file(path, before, os.fstat(stream.fileno()))
            _require_same_file(path, before, path.lstat())
            if len(data) != before.st_size:
                raise ValueError(f'Cache entry changed while collecting provenance: {path}')
            return data
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def collect_provenance_entries(target: Path) -> tuple[dict[str, str], int]:
    """Hash bounded cache files without following links or special entries."""
    paths: list[Path] = []
    with os.scandir(target) as entries:
        for entry in entries:
            if entry.name.endswith('.gttast'):
                paths.append(Path(entry.path))
                if len(paths) > MAX_PROVENANCE_FILES:
                    raise ValueError(f'Cache provenance exceeds {MAX_PROVENANCE_FILES} files')

    files: dict[str, str] = {}
    total_bytes = 0
    for path in sorted(paths, key=lambda item: item.name):
        before = path.lstat()
        _require_regular_file(path, before)
        if before.st_size < 0 or total_bytes + before.st_size > MAX_PROVENANCE_BYTES:
            raise ValueError(f'Cache provenance exceeds {MAX_PROVENANCE_BYTES} bytes')
        data = _read_cache_entry(path, before)
        files[path.name] = hashlib.sha256(data).hexdigest()
        total_bytes += len(data)
    return files, total_bytes


def main() -> None:
    from tools.managed_optimizer_experiment import owned_job
    from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
    from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources
    from run_workspace.gcsim.optimizer_go_selected import DEFAULT_OPTIMIZER_BINARY

    job = owned_job()
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--request', required=True, type=Path, help='Saved request used only for engine binding')
    parser.add_argument('--binary', type=Path, default=Path(DEFAULT_OPTIMIZER_BINARY))
    parser.add_argument('--output', type=Path, default=ROOT / 'native/gcsim_optimizer/set-rule-cache')
    args = parser.parse_args()
    target = args.output.absolute()
    if target.resolve() != target:
        raise ValueError('Cache target must not contain links')
    shipped = ROOT / 'native/gcsim_optimizer/set-rule-cache'
    if target != shipped:
        target.relative_to(job)
    req = json.loads(args.request.read_text(encoding='utf-8'))
    engine = load_active_gcsim_optimizer_engine_context()
    binding = req['engine']
    if (binding['artifact_sha256'] != engine.artifact_sha256 or
            Path(binding['binary_path']).resolve() != Path(engine.artifact_path).resolve()):
        raise ValueError('Request does not bind the active application engine')
    sources = prepare_all_set_effect_sources(Path(engine.engine_root), binding, include_neutral_rules=True)
    source_file = job / 'cache-source-envelope.json'
    source_file.write_text(json.dumps(sources), encoding='utf-8')
    command = [str(args.binary.resolve(strict=True)), 'warm-set-cache',
        str(args.request.resolve(strict=True)), str(source_file), str(target)]
    output = subprocess.check_output(command, text=True)
    receipt = json.loads(output)
    stats = receipt['rule_parse_cache']
    if stats.get('errors', stats.get('Errors', 0)):
        # A repaired corrupt entry records its failed read. Verify the repaired
        # files once in a new process rather than rejecting a successful repair.
        # Repeated IO/decoding failure still fails closed, without a retry loop.
        output = subprocess.check_output(command, text=True)
        receipt = json.loads(output)
        repaired = receipt['rule_parse_cache']
        if repaired.get('errors', repaired.get('Errors', 0)):
            raise RuntimeError(f'Cache preparation failed: {output}')
        receipt['initial_repair_stats'] = stats
    provenance_files, provenance_bytes = collect_provenance_entries(target)
    if not provenance_files:
        raise RuntimeError('No source plans were prepared')
    receipt.update(schema_version=1, engine_id=engine.engine_id,
        consumer_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),
        files=provenance_files,
        bytes=provenance_bytes)
    # One bounded, replaceable provenance record; not part of cache/gameplay keys.
    tmp = target / 'provenance.json.tmp'
    try:
        if tmp.is_symlink() or (target / 'provenance.json').is_symlink():
            raise ValueError('Linked cache provenance')
        tmp.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        tmp.replace(target / 'provenance.json')
    finally:
        if tmp.is_file() and not tmp.is_symlink():
            tmp.unlink()
    summary = {k: v for k, v in receipt.items() if k not in ('files', 'schedule_requirements')}
    summary['schedule_requirements'] = [row for row in receipt.get('schedule_requirements', [])
        if any(tier.get('reasons') for tier in row['tiers'])]
    print(json.dumps(summary, sort_keys=True))


if __name__ == '__main__':
    main()
