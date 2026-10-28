"""Capture-free, frozen-target input preparation for one Theory study.

Run with ``python -I -B`` and pass the frozen assembly, Worker2 repository,
and a fresh leased job explicitly. Production modules are imported only from
the assembly; the public mode-matrix helper is loaded by file from the repo.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from datetime import datetime, timezone
from dataclasses import replace
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
from types import ModuleType
from typing import Any, Iterator, Mapping


sys.dont_write_bytecode = True

CASE = "chiori_lunar_crystallize"
RUN_ID = f"{CASE}_theory"
EXPECTED_ENGINE_ID = "gcsim-v2.45.0-20260927011932"
EXPECTED_ENGINE_ARTIFACT_SHA256 = "7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c"
EXPECTED_MANIFEST_SHA256 = "d00ed4463c535e136590548aad8e2d20f35a7efe8ca8bcb22a49b19c13ff1c86"
EXPECTED_RECEIPT_SHA256 = "fa7e194adddcfd45f3c65faa62bc3c7546f685fc8a2a44cfec5542c792c99f16"
EXPECTED_PROFILES_SHA256 = "75a210533da5b57689dd9c47483358a091877580d86d48120be999e7aab109a8"
EXPECTED_ROTATION_SHA256 = "f32110269626d50ac9fc3c7ad31119b9fa7a802d57d55013e4dd51eb44c7197d"
EXPECTED_MATRIX_SHA256 = "b9deaa77b4d7c37ee02b9ef33cac90cffa1044b51916fe2bf8f31b95e94b322a"
EXPECTED_SEEDS = (742_031_889, 742_031_890)
EXPECTED_PROFILE_ORDER = ("furina", "xilonen", "chiori", "columbina")
REQUIRED_CAPABILITIES = frozenset(
    {
        "gtt_compact_equation_v1",
        "gtt_trace_equation_v6",
        "gtt_effect_inputs_v1",
        "gtt_neutral_inputs_v1",
    }
)
MANIFEST_RELATIVE = Path("tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json")
MATRIX_RELATIVE = Path("tools/experiments/gcsim/mode_matrix/run_product_matrix.py")
RECEIPT_RELATIVE = Path(
    "docs/optimizer-evidence/2026-10-03-theory-current-matrix"
) / f"{RUN_ID}.json"
ROTATION_RELATIVE = Path(
    "tools/experiments/gcsim/mode_matrix/rotations"
) / f"{CASE}.txt"
PRODUCTION_MODULES = (
    "localization",
    "hoyolab_export.paths",
    "hoyolab_export.artifact_db",
    "hoyolab_export.account_storage",
    "hoyolab_export.account_equipment",
    "run_workspace.gcsim.engine_store",
    "run_workspace.gcsim.artifact_set_catalog",
    "run_workspace.gcsim.source_manifest_build",
    "run_workspace.gcsim.optimizer_go_contracts",
    "run_workspace.gcsim.optimizer_go_requests",
    "run_workspace.gcsim.optimizer_go_inputs",
    "run_workspace.gcsim.optimizer_go_all",
    "run_workspace.gcsim.optimizer_go_theory",
    "run_workspace.gcsim.optimizer_go_all_sources",
    "run_workspace.gcsim.optimizer_engine_context",
    "run_workspace.gcsim.virtual_roster",
    "ui.artifact_browser.queries",
)
PUBLIC_MATRIX_MODULE = "theory_full_output_pinned_public_matrix"
PUBLIC_INPUT_FUNCTIONS = (
    "_resolve_inside_root", "_virtual_selected_team", "_selected_team",
    "_request", "_expanded_manifest_entries",
)
JOB_NAME_RE = re.compile(r"^job-[0-9a-f]{32}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value))


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON value is not allowed: {value}")


def _read_object(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError(f"Pinned JSON input is too large: {path.name}")
    payload = json.loads(
        path.read_text(encoding="utf-8"), parse_constant=_reject_constant
    )
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return payload


def _assert_no_links(path: Path) -> None:
    """Reject symlink and junction components before resolving a fence path."""

    absolute = path.absolute()
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current = current / component
        if not current.exists() and not current.is_symlink():
            continue
        is_junction = getattr(current, "is_junction", lambda: False)
        if current.is_symlink() or is_junction():
            raise ValueError(f"Linked path is not allowed in the job fence: {current}")


def _require_inside(path: Path, root: Path, *, strict: bool = True) -> Path:
    resolved = path.resolve(strict=strict)
    resolved.relative_to(root.resolve(strict=True))
    return resolved


def _absolute_dir(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"--{label} must be an absolute path")
    _assert_no_links(path)
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"--{label} must name a directory")
    return resolved


def _job_paths(
    *, assembly_arg: str | Path, repo_arg: str | Path, job_arg: str | Path
) -> tuple[Path, Path, Path]:
    repo = _absolute_dir(repo_arg, "repo")
    if not (repo / "hoyolab_export").is_dir() or not (repo / "run_workspace").is_dir():
        raise ValueError("--repo is not the Worker2 repository root")
    job_input = Path(job_arg)
    if not job_input.is_absolute():
        raise ValueError("--job must be an absolute path")
    _assert_no_links(job_input)
    job = job_input.resolve(strict=True)
    expected_parent = repo / ".codex_tmp" / "theory-full-output"
    _assert_no_links(expected_parent)
    if job.parent != expected_parent.resolve(strict=True):
        raise ValueError("--job must be a direct child of repo/.codex_tmp/theory-full-output")
    if not JOB_NAME_RE.fullmatch(job.name):
        raise ValueError("--job must use the leased job-<UUID> directory name")
    if not job.is_dir():
        raise ValueError("--job must be an existing leased directory")
    lease = expected_parent / ".theory-release.lease"
    _assert_no_links(lease)
    if lease.read_bytes() != (job.name[4:] + "\n").encode("ascii"):
        raise ValueError("--job must match its current managed lease")
    if set(expected_parent.iterdir()) != {lease, job}:
        raise ValueError("Unexpected managed scratch members block preparation")

    assembly_input = Path(assembly_arg)
    if not assembly_input.is_absolute():
        raise ValueError("--assembly must be an absolute path")
    _assert_no_links(assembly_input)
    assembly = assembly_input.resolve(strict=True)
    if not assembly.is_dir() or assembly == repo:
        raise ValueError("--assembly must be a separate frozen target directory")
    _require_inside(assembly, job)
    for relative in (
        "hoyolab_export/paths.py",
        "run_workspace/gcsim/optimizer_go_inputs.py",
        "run_workspace/gcsim/optimizer_go_all_sources.py",
    ):
        if not (assembly / relative).is_file():
            raise FileNotFoundError(f"Frozen assembly is missing {relative}")
    return assembly, repo, job


def _repo_file(repo: Path, relative: Path) -> Path:
    raw_path = repo / relative
    _assert_no_links(raw_path)
    path = _require_inside(raw_path, repo)
    if not path.is_file():
        raise FileNotFoundError(f"Pinned input is missing: {relative.as_posix()}")
    return path


def _assert_sha256(label: str, path: Path, expected: str) -> str:
    actual = _sha256_file(path)
    if actual != expected:
        raise ValueError(f"Pinned {label} hash changed: {actual}")
    return actual


def _import_production_modules(assembly: Path, repo: Path) -> dict[str, ModuleType]:
    assembly_text = str(assembly)
    if assembly_text in sys.path:
        sys.path.remove(assembly_text)
    sys.path.insert(0, assembly_text)
    loaded = {name: importlib.import_module(name) for name in PRODUCTION_MODULES}
    _assert_production_origins(assembly, repo, loaded)
    return loaded


def _assert_production_origins(
    assembly: Path,
    repo: Path,
    loaded: Mapping[str, ModuleType] | None = None,
    *,
    external_files: tuple[Path, ...] = (),
) -> dict[str, dict[str, str]]:
    modules = loaded or {
        name: sys.modules[name]
        for name in PRODUCTION_MODULES
        if name in sys.modules
    }
    origins: dict[str, dict[str, str]] = {}
    for name in PRODUCTION_MODULES:
        module = modules.get(name)
        if module is None:
            raise RuntimeError(f"Production module was not loaded: {name}")
        raw_origin = getattr(module, "__file__", None)
        if not raw_origin:
            raise RuntimeError(f"Production module has no source origin: {name}")
        origin = Path(raw_origin).resolve(strict=True)
        origin.relative_to(assembly)
        origins[name] = {
            "origin": origin.relative_to(assembly).as_posix(),
            "sha256": _sha256_file(origin),
        }

    allowed_external = {Path(__file__).resolve(), *(path.resolve() for path in external_files)}
    project_prefixes = ("hoyolab_export", "run_workspace", "tools", "ui", "localization")
    for name, module in tuple(sys.modules.items()):
        raw_origin = getattr(module, "__file__", None)
        if raw_origin:
            origin = Path(raw_origin).resolve(strict=False)
            try:
                origin.relative_to(assembly)
            except ValueError:
                is_project_module = name in project_prefixes or name.startswith(
                    tuple(prefix + "." for prefix in project_prefixes)
                )
                if is_project_module:
                    raise ValueError(
                        f"Production module {name} was imported outside the frozen assembly"
                    )
                try:
                    origin.relative_to(repo)
                except ValueError:
                    continue
                if origin not in allowed_external:
                    raise ValueError(
                        f"Project module {name} was imported outside the frozen assembly"
                    )
        raw_paths = getattr(module, "__path__", None)
        if raw_paths:
            for raw_path in raw_paths:
                path = Path(raw_path).resolve(strict=False)
                try:
                    path.relative_to(assembly)
                except ValueError:
                    is_project_package = name in project_prefixes or name.startswith(
                        tuple(prefix + "." for prefix in project_prefixes)
                    )
                    if not is_project_package:
                        continue
                    raise ValueError(
                        f"Project package {name} resolves outside the frozen assembly"
                    )
    return origins


def _load_public_matrix(repo: Path, assembly: Path) -> ModuleType:
    matrix_path = _repo_file(repo, MATRIX_RELATIVE)
    _assert_sha256("public mode-matrix helper", matrix_path, EXPECTED_MATRIX_SHA256)
    # Execute unchanged public input functions only. The old full matrix
    # runner imports an intentionally removed research scratch dependency and
    # is outside this task. Its optimizer/session/run/output functions are not
    # loaded. Every input function remains bound to the pinned source file.
    parsed = ast.parse(matrix_path.read_text(encoding="utf-8"), filename=str(matrix_path))
    functions = [node for node in parsed.body
                 if isinstance(node, ast.FunctionDef) and node.name in PUBLIC_INPUT_FUNCTIONS]
    if {node.name for node in functions} != set(PUBLIC_INPUT_FUNCTIONS):
        raise ValueError("Pinned public input function projection is incomplete")
    virtual_roster = sys.modules["run_workspace.gcsim.virtual_roster"]
    theory = sys.modules["run_workspace.gcsim.optimizer_go_theory"]
    module = ModuleType(PUBLIC_MATRIX_MODULE)
    module.__file__ = str(matrix_path)
    module.__dict__.update(
        ROOT=repo, Path=Path, Mapping=Mapping, Any=Any,
        GcsimVirtualSlotOverride=virtual_roster.GcsimVirtualSlotOverride,
        load_active_virtual_roster_catalog=virtual_roster.load_active_virtual_roster_catalog,
        SESSION_TYPES={"theory": (theory.GcsimOptimizerGoTheoryRequest, theory.GcsimOptimizerGoTheorySession)},
    )
    module.input_projection_sha256 = _sha256_bytes(
        ast.dump(ast.Module(body=functions, type_ignores=[]), include_attributes=False).encode())
    sys.modules[PUBLIC_MATRIX_MODULE] = module
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(matrix_path), "exec"), module.__dict__)
    if Path(module.ROOT).resolve(strict=True) != repo:
        raise ValueError("Pinned mode-matrix helper resolved a different repository root")
    if Path(module.__file__).resolve(strict=True) != matrix_path:
        raise ValueError("Mode-matrix helper was not loaded from the pinned repo file")
    _assert_production_origins(
        assembly, repo, external_files=(matrix_path,)
    )
    return module


@contextmanager
def _block_subprocesses() -> Iterator[None]:
    original = subprocess.Popen

    def blocked(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("Subprocess creation is blocked during capture-free preparation")

    subprocess.Popen = blocked  # type: ignore[assignment]
    try:
        yield
    finally:
        replaced = subprocess.Popen is not blocked
        subprocess.Popen = original  # type: ignore[assignment]
        if replaced:
            raise RuntimeError("The subprocess execution guard was replaced during preparation")


@contextmanager
def _owned_environment(runtime_root: Path) -> Iterator[None]:
    temporary = runtime_root / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    roots = {
        "GTT_DATA_DIR": runtime_root / "data",
        "GTT_SCRATCH_DIR": runtime_root,
        "GTT_RULE_CACHE_DIR": runtime_root / "set-rule-cache",
        "GTT_RULE_BUNDLED_CACHE_DIR": runtime_root / "bundled-rule-cache",
        "TMP": temporary,
        "TEMP": temporary,
        "TMPDIR": temporary,
        "PYTHONDONTWRITEBYTECODE": Path("1"),
    }
    names = tuple(roots)
    before = {name: os.environ.get(name) for name in names}
    try:
        for name, value in roots.items():
            os.environ[name] = str(value)
        yield
    finally:
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _source_db_state(source_db: Path) -> dict[str, Any]:
    state: dict[str, Any] = {"database": _file_state(source_db)}
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{source_db}{suffix}")
        state[suffix[1:]] = _file_state(sidecar)
    wal = state["wal"]
    if wal["exists"] and wal["size"]:
        raise ValueError("Source database has a non-empty WAL; read-only backup is unsafe")
    return state


def _file_state(path: Path) -> dict[str, Any]:
    _assert_no_links(path)
    if not path.exists():
        return {"exists": False, "size": 0, "sha256": None}
    if not path.is_file():
        raise ValueError(f"Expected a regular input file: {path.name}")
    return {"exists": True, "size": path.stat().st_size, "sha256": _sha256_file(path)}


def _backup_source_db(source_db: Path, destination: Path) -> None:
    from contextlib import closing

    destination.parent.mkdir(parents=True, exist_ok=False)
    source_uri = source_db.as_uri() + "?mode=ro&immutable=1"
    with closing(sqlite3.connect(source_uri, uri=True)) as source, closing(
        sqlite3.connect(destination)
    ) as target:
        source.execute("PRAGMA query_only=ON")
        source.backup(target)
        target.commit()


def _copy_input_db(repo: Path, job: Path, db_relative: str) -> tuple[Path, dict[str, Any]]:
    relative = Path(db_relative)
    if relative.is_absolute():
        raise ValueError("Manifest database path must be repository-relative")
    source_db = _repo_file(repo, relative)
    _assert_no_links(source_db)
    before_clock = _utc_now()
    before = _source_db_state(source_db)
    copied_db = job / "private" / "artifacts.db"
    _require_inside(copied_db, job, strict=False)
    if copied_db.exists():
        raise FileExistsError("Leased job already contains a private database copy")
    _backup_source_db(source_db, copied_db)
    after_clock = _utc_now()
    after = _source_db_state(source_db)
    if after != before:
        raise ValueError("Worker source database or sidecars changed during read-only backup")
    return copied_db, {
        "source_path": relative.as_posix(),
        "source_before": before,
        "source_after": after,
        "source_before_utc": before_clock,
        "source_after_utc": after_clock,
        "copy_path": copied_db.relative_to(job).as_posix(),
        "copy_sha256": _sha256_file(copied_db),
        "copy_size": copied_db.stat().st_size,
        "source_open_mode": "read_only_sqlite_backup",
    }


def _active_engine(repo: Path, modules: Mapping[str, ModuleType]):
    store_module = modules["run_workspace.gcsim.engine_store"]
    context_module = modules["run_workspace.gcsim.optimizer_engine_context"]
    store_root_input = repo / "data" / "gcsim" / "engines"
    _assert_no_links(store_root_input)
    store_root = store_root_input.resolve(strict=True)
    store = store_module.GcsimEngineStore(store_root)
    if store.root_dir.resolve(strict=True) != store_root:
        raise ValueError("Engine storage root differs from the Worker2 read-only store")
    installation = store.get_active_engine()
    if installation is None:
        raise ValueError("Worker2 has no active GCSIM engine")
    _assert_no_links(Path(installation.path))
    engine_root = Path(installation.path).resolve(strict=True)
    engine_root.relative_to(store.engines_dir.resolve(strict=True))
    _assert_no_links(engine_root)
    context = context_module.build_gcsim_optimizer_engine_context(
        installation, require_resealed=True
    )
    if not context.trusted or context.issues:
        raise ValueError("Active Worker2 engine metadata did not verify as trusted")
    if context.engine_id != EXPECTED_ENGINE_ID:
        raise ValueError(f"Active engine id changed: {context.engine_id}")
    if context.artifact_sha256 != EXPECTED_ENGINE_ARTIFACT_SHA256:
        raise ValueError("Active engine artifact hash differs from the pinned engine")
    missing = sorted(REQUIRED_CAPABILITIES - frozenset(context.capabilities))
    if missing:
        raise ValueError("Active engine manifest lacks required capabilities: " + ", ".join(missing))
    engine_state = {
        "id": context.engine_id,
        "version": context.engine_version,
        "root": engine_root.relative_to(repo).as_posix(),
        "artifact_sha256": context.artifact_sha256,
        "engine_tree_sha256": context.engine_tree_sha256,
        "binding_sha256": context.binding_sha256,
        "catalog_fingerprint": context.catalog.source_fingerprint,
        "capabilities": sorted(context.capabilities),
        "manifest_artifact_sha256": context.manifest_artifact_sha256,
        "manifest_engine_tree_sha256": context.manifest_engine_tree_sha256,
        "store_state_sha256": _sha256_file(store.active_state_path),
        "manifest_sha256": _sha256_file(engine_root / store_module.MANIFEST_FILE_NAME),
        "source_manifest_file_sha256": _sha256_file(
            engine_root / "build" / "gtt-source-manifest-body.json"
        ),
    }
    return store, installation, context, engine_state


def _assert_engine_unchanged(
    store: Any, installation: Any, initial_context: Any, initial_state: Mapping[str, Any], repo: Path
) -> None:
    current_installation = store.get_active_engine()
    if current_installation is None or current_installation.engine_id != installation.engine_id:
        raise ValueError("Active Worker2 engine changed during preparation")
    context_module = sys.modules["run_workspace.gcsim.optimizer_engine_context"]
    current_context = context_module.build_gcsim_optimizer_engine_context(
        current_installation, require_resealed=True
    )
    if current_context.to_dict() != initial_context.to_dict():
        raise ValueError("Worker2 active engine metadata or public tree changed during preparation")
    current_root = Path(current_installation.path).resolve(strict=True)
    current_state = {
        "store_state_sha256": _sha256_file(store.active_state_path),
        "manifest_sha256": _sha256_file(
            current_root / sys.modules["run_workspace.gcsim.engine_store"].MANIFEST_FILE_NAME
        ),
        "source_manifest_file_sha256": _sha256_file(
            current_root / "build" / "gtt-source-manifest-body.json"
        ),
    }
    for key, value in current_state.items():
        if initial_state[key] != value:
            raise ValueError(f"Active engine {key} changed during preparation")
    Path(current_installation.path).resolve(strict=True).relative_to(repo.resolve(strict=True))


def _write_json(path: Path, payload: Any) -> bytes:
    data = _canonical_json(payload)
    path.write_bytes(data)
    return data


def _existing_job_outputs(job: Path) -> None:
    for name in ("request.json", "sources.json", "rarities.json", "set-labels.json", "prep-provenance.json"):
        target = job / name
        _assert_no_links(target)
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"Leased job output already exists: {name}")
    _assert_no_links(job / "private")
    _assert_no_links(job / "private" / "artifacts.db")
    if (job / "private" / "artifacts.db").exists():
        raise FileExistsError("Leased job already contains a private database copy")


def prepare_inputs(
    *, assembly: str | Path, repo: str | Path, job: str | Path
) -> dict[str, Any]:
    """Prepare pinned Chiori Theory inputs without executing an engine binary."""

    if sys.flags.isolated != 1 or not sys.dont_write_bytecode:
        raise RuntimeError("Input preparation must run under Python -I -B")
    frozen, worker_repo, leased_job = _job_paths(
        assembly_arg=assembly, repo_arg=repo, job_arg=job
    )
    _existing_job_outputs(leased_job)
    input_started = _utc_now()
    preparer_path = Path(__file__).resolve(strict=True)
    preparer_sha = _sha256_file(preparer_path)

    manifest_path = _repo_file(worker_repo, MANIFEST_RELATIVE)
    matrix_path = _repo_file(worker_repo, MATRIX_RELATIVE)
    receipt_path = _repo_file(worker_repo, RECEIPT_RELATIVE)
    manifest_sha = _assert_sha256("archetype manifest", manifest_path, EXPECTED_MANIFEST_SHA256)
    receipt_sha = _assert_sha256("historical receipt identity", receipt_path, EXPECTED_RECEIPT_SHA256)
    matrix_sha = _assert_sha256("public mode-matrix helper", matrix_path, EXPECTED_MATRIX_SHA256)
    manifest = _read_object(manifest_path)
    pinned_inputs_checked = _utc_now()

    runtime_metadata: dict[str, Any] = {}
    subprocess_guarded = False
    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=leased_job) as stage_name:
        stage = Path(stage_name)
        runtime_root = stage / "runtime"
        prep_dir = stage / "production-preparation"
        stage.mkdir(exist_ok=True)
        with _block_subprocesses():
            subprocess_guarded = True
            with _owned_environment(runtime_root):
                modules = _import_production_modules(frozen, worker_repo)
                matrix = _load_public_matrix(worker_repo, frozen)
                production_origins_before = _assert_production_origins(
                    frozen,
                    worker_repo,
                    modules,
                    external_files=(matrix_path,),
                )
                manifest_entries = matrix._expanded_manifest_entries(manifest)
                entries = [
                    row
                    for row in manifest_entries
                    if row.get("team") == CASE and row.get("mode") == "theory"
                ]
                if len(entries) != 1 or entries[0].get("id") != RUN_ID:
                    raise ValueError("Pinned manifest does not identify one Chiori Theory entry")
                entry = entries[0]
                profiles = entry.get("virtual_profiles")
                if not isinstance(profiles, list) or len(profiles) != 4:
                    raise ValueError("Pinned Chiori entry must contain four virtual profiles")
                profile_order = tuple(
                    str(row.get("character_key") or "").casefold()
                    for row in profiles
                    if isinstance(row, Mapping)
                )
                if profile_order != EXPECTED_PROFILE_ORDER:
                    raise ValueError("Pinned Chiori virtual profile order changed")
                profiles_sha = _canonical_sha256(profiles)
                if profiles_sha != EXPECTED_PROFILES_SHA256:
                    raise ValueError("Pinned Chiori virtual profile identity changed")
                if entry.get("infinite_energy") is not True:
                    raise ValueError("Chiori Theory input must explicitly use infinite energy")
                profiles_bound = _utc_now()

                rotation_relative = Path(str(entry.get("rotation_file") or ""))
                if rotation_relative.is_absolute():
                    raise ValueError("Manifest rotation path must be repository-relative")
                rotation_path = _repo_file(worker_repo, rotation_relative)
                if rotation_relative.as_posix() != ROTATION_RELATIVE.as_posix():
                    raise ValueError("Pinned manifest resolved an unexpected rotation path")
                rotation_sha = _assert_sha256(
                    "Chiori rotation", rotation_path, EXPECTED_ROTATION_SHA256
                )
                db_relative = str(manifest.get("db_path") or "")
                copied_db, database_provenance = _copy_input_db(
                    worker_repo, leased_job, db_relative
                )

                store, installation, engine_context, engine_state = _active_engine(
                    worker_repo, modules
                )
                virtual_roster = modules["run_workspace.gcsim.virtual_roster"]
                catalog = virtual_roster.load_active_virtual_roster_catalog(store)
                if catalog.engine_id != engine_context.engine_id:
                    raise ValueError("Virtual roster catalog differs from the active engine")
                # Public set names affect only presentation, never the request
                # or search. Read localized names from the disposable DB copy.
                set_labels = {}
                for choice in virtual_roster.load_active_virtual_artifact_set_choices(
                    copied_db, language="ru", store=store
                ):
                    set_labels[choice.gcsim_key] = choice.display_name
                    set_labels[choice.set_uid] = choice.display_name

                # The public helper reads the manifest's exact default profile
                # values. Give its catalog resolver the verified Worker2 store.
                matrix.load_active_virtual_roster_catalog = lambda: (
                    virtual_roster.load_active_virtual_roster_catalog(store)
                )
                run_root = leased_job / "runs"
                _require_inside(run_root, leased_job, strict=False)
                request = matrix._request(
                    entry, db_path=copied_db, run_root=run_root
                )
                request = replace(
                    request,
                    engine_store_dir=str(store.root_dir.resolve(strict=True)),
                    expected_engine_id=engine_context.engine_id,
                )
                if (
                    request.seeds != EXPECTED_SEEDS
                    or request.infinite_energy_enabled is not True
                    or request.theory_options is not None
                    or Path(request.db_path).resolve(strict=True) != copied_db.resolve(strict=True)
                    or Path(request.run_root).resolve(strict=False) != run_root.resolve(strict=False)
                ):
                    raise ValueError("Default target-preparation request identity changed")

                prep_dir.mkdir(parents=True, exist_ok=False)
                prep_started = _utc_now()
                prepared = modules["run_workspace.gcsim.optimizer_go_inputs"].prepare_optimizer_inputs(
                    request, prep_dir, mode="theory"
                )
                prep_finished = _utc_now()
                wire = prepared.get("request")
                if not isinstance(wire, dict):
                    raise ValueError("Production preparation did not return a request object")
                if _canonical_sha256(wire) != prepared.get("request_sha256"):
                    raise ValueError("Production request hash does not match its canonical bytes")
                production_request_path = prep_dir / "request.json"
                if _read_object(production_request_path) != wire:
                    raise ValueError("Production request file differs from the returned request")
                if (
                    wire.get("stochastic", {}).get("seeds") != list(EXPECTED_SEEDS)
                    or wire.get("theory_options") != {}
                    or wire.get("legality", {}).get("theory_search") is not True
                    or wire.get("engine", {}).get("artifact_sha256")
                    != EXPECTED_ENGINE_ARTIFACT_SHA256
                    or wire.get("artifacts") != []
                ):
                    raise ValueError("Prepared request differs from the bounded Theory defaults")
                wearers = wire.get("wearers")
                if not isinstance(wearers, list) or tuple(
                    row.get("wearer_key") for row in wearers if isinstance(row, Mapping)
                ) != tuple(sorted(EXPECTED_PROFILE_ORDER)):
                    raise ValueError("Prepared Theory wearer set or canonical order changed")
                if any(row.get("current_artifacts") != [] for row in wearers):
                    raise ValueError("Theory input unexpectedly contains saved allocations")
                default_main_order = {
                    row["wearer_key"]: [item["key"] for item in row["theory_baseline"]["main_stats"]]
                    for row in wearers
                }
                expected_mains = ["hp", "atk", "atk_percent", "atk_percent", "crit_rate"]
                if any(values != expected_mains for values in default_main_order.values()):
                    raise ValueError("Prepared Theory main-stat defaults changed")

                source_module = modules["run_workspace.gcsim.optimizer_go_all_sources"]
                source_bundle_started = _utc_now()
                sources = source_module.prepare_all_set_effect_sources(
                    engine_context.engine_root,
                    wire["engine"],
                    include_neutral_rules=True,
                )
                source_bundle_finished = _utc_now()
                neutral_names = tuple(source_module.NEUTRAL_RULE_LIBRARIES)
                rule_libraries = sources.get("rule_libraries")
                if not isinstance(rule_libraries, Mapping) or set(rule_libraries) != set(neutral_names):
                    raise ValueError("Verified public source bundle lacks the complete neutral library")
                if (
                    sources.get("engine_sha256") != engine_context.artifact_sha256
                    or sources.get("source_manifest_sha256")
                    != wire["engine"].get("source_manifest_sha256")
                    or sources.get("catalog_sha256") != engine_context.catalog.source_fingerprint
                ):
                    raise ValueError("Public source bundle does not match the verified active engine")

                rarities = {
                    row.key: row.max_rarity for row in engine_context.catalog.sets
                }
                if not rarities or len(rarities) != len(engine_context.catalog.sets):
                    raise ValueError("Verified active-engine rarity catalog is empty or ambiguous")
                contract_module = modules["run_workspace.gcsim.optimizer_go_contracts"]
                request_bytes = production_request_path.read_bytes()
                canonical_request = contract_module.canonical_json_bytes(wire)
                if (
                    _sha256_bytes(canonical_request) != prepared["request_sha256"]
                    or request_bytes != canonical_request + b"\n"
                ):
                    raise ValueError("Production request bytes differ from its canonical hash")
                source_bytes = _canonical_json(sources)
                rarity_bytes = _canonical_json(rarities)
                staged_files = {
                    "request.json": request_bytes,
                    "sources.json": source_bytes,
                    "rarities.json": rarity_bytes,
                    "set-labels.json": _canonical_json(set_labels),
                }
                for name, data in staged_files.items():
                    (stage / name).write_bytes(data)

                production_origins = _assert_production_origins(
                    frozen,
                    worker_repo,
                    modules,
                    external_files=(matrix_path,),
                )
                if production_origins != production_origins_before:
                    raise ValueError("Frozen production module bytes changed during preparation")
                if _sha256_file(preparer_path) != preparer_sha:
                    raise ValueError("Input preparation module changed during execution")
                _assert_engine_unchanged(
                    store, installation, engine_context, engine_state, worker_repo
                )
                matrix_after = _sha256_file(matrix_path)
                if matrix_after != matrix_sha:
                    raise ValueError("Pinned public mode-matrix helper changed during preparation")
                manifest_after = _sha256_file(manifest_path)
                receipt_after = _sha256_file(receipt_path)
                rotation_after = _sha256_file(rotation_path)
                if (manifest_after, receipt_after, rotation_after) != (
                    manifest_sha,
                    receipt_sha,
                    rotation_sha,
                ):
                    raise ValueError("Pinned public input files changed during preparation")
                database_after = _source_db_state(_repo_file(worker_repo, Path(db_relative)))
                if database_after != database_provenance["source_after"]:
                    raise ValueError("Worker source database or sidecars changed after preparation")
                input_finished = _utc_now()

                for name in staged_files:
                    os.replace(stage / name, leased_job / name)
                output_files = {
                    name: {
                        "path": name,
                        "sha256": _sha256_file(leased_job / name),
                        "size": (leased_job / name).stat().st_size,
                    }
                    for name in staged_files
                }
                private_db_record = {
                    "path": database_provenance["copy_path"],
                    "sha256": database_provenance["copy_sha256"],
                    "size": database_provenance["copy_size"],
                    "visibility": "leased_job_private",
                }
                runtime_metadata = {
                    "schema_version": 1,
                    "schema_kind": "gtt_theory_full_output_prep_provenance_v1",
                    "case": RUN_ID,
                    "mode": "theory",
                    "energy": "infinite",
                    "seed_panel": list(EXPECTED_SEEDS),
                    "ordinary_finalists": 0,
                    "capture_started": False,
                    "subprocess_creation_blocked": subprocess_guarded,
                    "saved_solution_reuse": False,
                    "input_clock_utc": {
                        "started": input_started,
                        "pinned_inputs_checked": pinned_inputs_checked,
                        "profiles_bound": profiles_bound,
                        "inputs_bound": input_finished,
                        "database_backup_started": database_provenance["source_before_utc"],
                        "database_backup_finished": database_provenance["source_after_utc"],
                    },
                    "preparation_clock_utc": {
                        "started": prep_started,
                        "finished": prep_finished,
                    },
                    "source_bundle_clock_utc": {
                        "started": source_bundle_started,
                        "finished": source_bundle_finished,
                    },
                    "fences": {
                        "job": leased_job.name,
                        "assembly": frozen.relative_to(leased_job).as_posix(),
                        "worker_repo": ".",
                        "source_database_copy_inside_job": True,
                        "engine_store_read_only_root": engine_state["root"],
                    },
                    "pinned_public_inputs": {
                        "matrix_helper": {
                            "path": MATRIX_RELATIVE.as_posix(),
                            "sha256": matrix_sha,
                        },
                        "manifest": {
                            "path": MANIFEST_RELATIVE.as_posix(),
                            "sha256": manifest_sha,
                        },
                        "historical_receipt_identity_only": {
                            "path": RECEIPT_RELATIVE.as_posix(),
                            "sha256": receipt_sha,
                            "parsed": False,
                        },
                        "profiles_sha256": profiles_sha,
                        "profile_order": list(profile_order),
                        "rotation": {
                            "path": rotation_relative.as_posix(),
                            "sha256": rotation_sha,
                        },
                    },
                    "external_module_origins": {
                        PUBLIC_MATRIX_MODULE: {
                            "origin": matrix_path.relative_to(worker_repo).as_posix(),
                            "sha256": matrix_sha,
                            "loaded": "exact_unchanged_input_function_projection_only",
                            "function_names": list(PUBLIC_INPUT_FUNCTIONS),
                            "projection_sha256": matrix.input_projection_sha256,
                        }
                    },
                    "production_module_origins": production_origins,
                    "engine": {
                        **engine_state,
                        "request_binding_sha256": wire["engine"].get("binding_sha256"),
                        "required_capabilities": sorted(REQUIRED_CAPABILITIES),
                    },
                    "request": {
                        "sha256": prepared["request_sha256"],
                        "engine_binding_sha256": wire["engine"].get("binding_sha256"),
                        "theory_options": wire.get("theory_options"),
                        "default_main_order": default_main_order,
                        "wearer_order": [row["wearer_key"] for row in wearers],
                    },
                    "sources": {
                        "sha256": output_files["sources.json"]["sha256"],
                        "allset_neutral": True,
                        "public_source_tree_verified": True,
                        "neutral_rule_libraries": list(neutral_names),
                        "engine_sha256": sources["engine_sha256"],
                        "source_manifest_sha256": sources["source_manifest_sha256"],
                        "catalog_sha256": sources["catalog_sha256"],
                    },
                    "rarities": {
                        "sha256": output_files["rarities.json"]["sha256"],
                        "set_count": len(rarities),
                    },
                    "public_set_labels": {
                        "sha256": output_files["set-labels.json"]["sha256"],
                        "language": "ru",
                        "mapping_keys": len(set_labels),
                        "source": "frozen_virtual_roster_join_with_disposable_database_copy",
                        "affects_numerical_request": False,
                    },
                    "source_database": {
                        **database_provenance,
                        "private_copy_record": private_db_record,
                    },
                    "generated_job_paths": [
                        *output_files.values(),
                        private_db_record,
                    ],
                    "preparer": {
                        "path": preparer_path.relative_to(worker_repo).as_posix(),
                        "sha256": preparer_sha,
                    },
                }
                _write_json(leased_job / "prep-provenance.json", runtime_metadata)
                runtime_metadata["prep_provenance_sha256"] = _sha256_file(
                    leased_job / "prep-provenance.json"
                )
    return runtime_metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembly", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--job", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = prepare_inputs(assembly=args.assembly, repo=args.repo, job=args.job)
    except Exception as exc:
        print(f"Theory input preparation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    summary = {
        "job": result["fences"]["job"],
        "case": result["case"],
        "engine_id": result["engine"]["id"],
        "request_sha256": result["request"]["sha256"],
        "files": result["generated_job_paths"],
        "prep_provenance_sha256": result["prep_provenance_sha256"],
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
