"""Manual, local transfer of one accepted GCSIM runtime bundle.

The CLI always targets the checkout containing this module. It copies only the
two selected engine installations and the standalone optimizer executable.
Preview is the default; no account registry, download, build or Git state is used.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from types import SimpleNamespace

from .engine_compatibility import REQUIRED_BUNDLE_CAPABILITIES, verify_engine_application_bundle
from .engine_store import (
    GcsimEngineStore, GcsimEngineStoreError, GcsimPatchResult, MANIFEST_FILE_NAME,
    load_engine_manifest,
)
from .tree_identity import directory_sha256
from ..profile_control import profile_operation_lock, profile_supervisor_lock


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ACTIVE_ID = "gcsim-v2.45.0-20260927011932"
ROLLBACK_ID = "gcsim-v2.45.0-20260926234622"
CONSUMER_RELATIVE = Path("native/gcsim_optimizer/gtt-optimizer.exe")
STORE_RELATIVE = Path("data/gcsim/engines")
BACKUP_SUFFIX = ".runtime-sync.rollback"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RuntimeBundleSyncError(RuntimeError):
    """A transfer precondition or compatibility gate failed."""


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _plain_ancestors(path: Path) -> None:
    for node in (path, *path.parents):
        if _is_reparse(node):
            raise RuntimeBundleSyncError(f"Link or reparse path refused: {node}")


def _plain_tree(root: Path) -> None:
    _plain_ancestors(root)
    if not root.is_dir():
        raise RuntimeBundleSyncError(f"Engine installation is missing: {root}")
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in (*dirs, *files):
            node = Path(parent) / name
            if _is_reparse(node):
                raise RuntimeBundleSyncError(f"Link or reparse node refused: {node}")
            if not (node.is_dir() or node.is_file()):
                raise RuntimeBundleSyncError(f"Special engine node refused: {node}")


def _contained_file(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if (not relative or candidate.is_absolute() or candidate.drive
            or ".." in candidate.parts or candidate == Path(".")):
        raise RuntimeBundleSyncError(f"Engine metadata path is unsafe: {relative!r}")
    path = root / candidate
    if root.resolve() not in path.resolve().parents:
        raise RuntimeBundleSyncError(f"Engine metadata path escapes installation: {relative!r}")
    _plain_ancestors(path)
    if not path.is_file():
        raise RuntimeBundleSyncError(f"Engine metadata file is missing: {path}")
    return path


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_digest(value: str, label: str) -> str:
    if not SHA256.fullmatch(value):
        raise RuntimeBundleSyncError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _source_body_digest(engine: Path, metadata: dict[str, str]) -> None:
    from .source_manifest_codec import decode_source_manifest_body, source_manifest_body_sha256

    body_path = _contained_file(engine, metadata.get("source_manifest_body_relative_path", ""))
    try:
        body = decode_source_manifest_body(body_path.read_bytes())
    except (OSError, ValueError, RuntimeError) as exc:
        raise RuntimeBundleSyncError(f"Invalid source manifest body: {engine.name}") from exc
    expected = _expected_digest(metadata.get("source_manifest_body_sha256", ""), "source body hash")
    if source_manifest_body_sha256(body) != expected:
        raise RuntimeBundleSyncError(f"Source manifest body changed: {engine.name}")
    try:
        info = json.loads(metadata["gtt_info_stdout"])
    except (KeyError, ValueError) as exc:
        raise RuntimeBundleSyncError(f"Recorded GTT runtime info is missing: {engine.name}") from exc
    if (not isinstance(info, dict) or info.get("source_manifest_body_sha256") != expected
            or info.get("source_manifest_compiler_version") != metadata.get("source_manifest_compiler_version")):
        raise RuntimeBundleSyncError(f"Recorded runtime/source binding differs: {engine.name}")


def _verified_engine(engine: Path, *, engine_id: str, expected_artifact_sha: str,
                     reference_manifest=None):
    _plain_tree(engine)
    try:
        manifest = load_engine_manifest(engine)
    except (GcsimEngineStoreError, KeyError, ValueError, TypeError) as exc:
        raise RuntimeBundleSyncError(str(exc)) from exc
    if manifest.engine_id != engine_id:
        raise RuntimeBundleSyncError(f"Engine ID mismatch: {engine}")
    metadata = dict(manifest.metadata)
    artifact = _contained_file(engine, metadata.get("artifact_relative_path", ""))
    actual_artifact_sha = _digest(artifact)
    if (actual_artifact_sha != expected_artifact_sha
            or metadata.get("artifact_sha256") != expected_artifact_sha):
        raise RuntimeBundleSyncError(f"Engine artifact hash mismatch: {engine_id}")
    actual_tree_sha = directory_sha256(engine, excluded_relative_paths=(MANIFEST_FILE_NAME,))
    if actual_tree_sha != manifest.engine_tree_hash:
        raise RuntimeBundleSyncError(f"Engine tree hash mismatch: {engine_id}")
    if metadata.get("source_manifest_required") != "true" or metadata.get("source_manifest_ready") != "true":
        raise RuntimeBundleSyncError(f"Required source manifest is not ready: {engine_id}")
    try:
        caps = json.loads(metadata.get("gtt_capabilities", ""))
    except ValueError as exc:
        raise RuntimeBundleSyncError(f"Invalid recorded capabilities: {engine_id}") from exc
    if (not isinstance(caps, list) or not all(isinstance(item, str) for item in caps)
            or not REQUIRED_BUNDLE_CAPABILITIES.issubset(caps)
            or metadata.get("gtt_sequential_waves") != "true"):
        raise RuntimeBundleSyncError(f"Required application capabilities are missing: {engine_id}")
    _source_body_digest(engine, metadata)
    if reference_manifest is not None:
        actual = manifest.to_dict()
        expected = reference_manifest.to_dict()
        for volatile in ("source_path", "prepared_at_utc"):
            actual.pop(volatile)
            expected.pop(volatile)
        if actual != expected:
            raise RuntimeBundleSyncError(f"Same engine ID has conflicting manifest provenance: {engine_id}")
    return manifest, artifact


def _checked_root(path: str | Path) -> Path:
    root = Path(path).expanduser().absolute()
    _plain_ancestors(root)
    if not root.is_dir():
        raise RuntimeBundleSyncError(f"Checkout root is missing: {root}")
    return root.resolve()


def _checked_consumer(path: Path) -> str | None:
    _plain_ancestors(path)
    if not _exists(path):
        return None
    if not path.is_file():
        raise RuntimeBundleSyncError(f"Consumer is not a regular file: {path}")
    return _digest(path)


def _backup_paths(consumer: Path) -> tuple[Path, Path]:
    backup = consumer.with_name(consumer.name + BACKUP_SUFFIX)
    return backup, backup.with_name(backup.name + ".json")


def _backup_state(consumer: Path, current_sha: str | None) -> dict | None:
    backup, receipt_path = _backup_paths(consumer)
    backup_sha = _checked_consumer(backup)
    _plain_ancestors(receipt_path)
    if backup_sha is None and not _exists(receipt_path):
        return None
    if backup_sha is None or not receipt_path.is_file():
        raise RuntimeBundleSyncError("Consumer rollback slot is occupied without a complete receipt")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeBundleSyncError("Consumer rollback receipt is unreadable") from exc
    if (not isinstance(receipt, dict) or receipt.get("schema_version") != 1
            or receipt.get("kind") != "gtt_runtime_bundle_consumer_rollback"
            or receipt.get("backup_sha256") != backup_sha
            or receipt.get("current_sha256") != current_sha):
        raise RuntimeBundleSyncError("Consumer rollback slot is unknown or differs from its receipt")
    return receipt


class _CopyBundleBackend:
    """Strip the copied root manifest before the store hashes the engine tree."""

    name = "runtime_bundle_copy"

    def apply(self, *, engine_dir: Path, patch_stack_dir: Path | None) -> GcsimPatchResult:
        (engine_dir / MANIFEST_FILE_NAME).unlink()
        return GcsimPatchResult.success(backend=self.name)


def _stage_copy(source: Path, directory: Path, *, suffix: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".runtime-sync-", suffix=suffix, dir=directory)
    os.close(descriptor)
    staged = Path(name)
    try:
        shutil.copy2(source, staged)
        if _digest(staged) != _digest(source):
            raise RuntimeBundleSyncError(f"Staged file differs from source: {source.name}")
        return staged
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def _stage_json(payload: dict, directory: Path) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".runtime-sync-", suffix=".json", dir=directory)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        return staged
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def _probe_runtime_metadata(artifact: Path, manifest) -> str:
    metadata = manifest.metadata
    for flag, recorded in (("-version", "artifact_version_stdout"), ("-gtt-info", "gtt_info_stdout")):
        result = subprocess.run([str(artifact), flag], capture_output=True, text=True,
                                timeout=20, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            return f"{artifact.name} {flag} failed: {result.stderr[-500:]}"
        observed = result.stdout.strip()
        if flag == "-version":
            if observed != str(metadata.get(recorded, "")).strip():
                return f"{artifact.name} version differs from accepted manifest"
        else:
            try:
                info = json.loads(observed)
                accepted = json.loads(metadata.get(recorded, ""))
            except ValueError:
                return f"{artifact.name} returned invalid GTT info"
            if info != accepted:
                return f"{artifact.name} GTT info differs from accepted manifest"
    return ""


def _compatibility(engine: Path, artifact: Path, manifest, consumer: Path) -> None:
    metadata = manifest.metadata
    build = SimpleNamespace(
        source_manifest_required=metadata.get("source_manifest_required") == "true",
        source_manifest_ready=metadata.get("source_manifest_ready") == "true",
        gtt_capabilities=tuple(json.loads(metadata.get("gtt_capabilities", "[]"))),
        gtt_sequential_waves=metadata.get("gtt_sequential_waves", "false"),
        artifact_path=str(artifact), artifact_sha256=metadata["artifact_sha256"],
    )
    try:
        problem = _probe_runtime_metadata(artifact, manifest)
        if not problem:
            problem = verify_engine_application_bundle(engine, build, optimizer_binary=consumer)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        problem = str(exc)
    if problem:
        raise RuntimeBundleSyncError(f"Compatibility failed for {manifest.engine_id}: {problem}")


def _install_engine(store: GcsimEngineStore, source: Path, manifest) -> Path:
    result = store.prepare_engine_update(
        source_dir=source, source_label=manifest.source_label, engine_id=manifest.engine_id,
        patch_backend=_CopyBundleBackend(), capabilities=manifest.capabilities,
        metadata=manifest.metadata, activate=False,
    )
    if not result.success or result.engine_path is None:
        raise RuntimeBundleSyncError(f"Engine store copy failed for {manifest.engine_id}: {result.error}")
    destination = result.engine_path
    if result.manifest is None or result.manifest.engine_tree_hash != manifest.engine_tree_hash:
        raise RuntimeBundleSyncError(f"Copied engine tree differs: {manifest.engine_id}")
    staged = _stage_copy(source / MANIFEST_FILE_NAME, destination, suffix=".json")
    try:
        os.replace(staged, destination / MANIFEST_FILE_NAME)
    finally:
        staged.unlink(missing_ok=True)
    return destination


def _promote_consumer(consumer: Path, staged: Path, new_sha: str, old_sha: str | None) -> None:
    if _digest(staged) != new_sha or _checked_consumer(consumer) != old_sha:
        raise RuntimeBundleSyncError("Consumer changed while preparing promotion")
    if old_sha is None:
        os.replace(staged, consumer)
        return
    backup, receipt_path = _backup_paths(consumer)
    if _exists(backup) or _exists(receipt_path):
        raise RuntimeBundleSyncError("Consumer rollback slot is already occupied")
    backup_temp = _stage_copy(consumer, consumer.parent, suffix=".exe")
    receipt_temp = _stage_json({"schema_version": 1,
                                "kind": "gtt_runtime_bundle_consumer_rollback",
                                "current_sha256": new_sha, "backup_sha256": old_sha}, consumer.parent)
    installed_backup = False
    try:
        os.replace(backup_temp, backup)
        installed_backup = True
        os.replace(receipt_temp, receipt_path)
        os.replace(staged, consumer)
    except BaseException:
        if installed_backup and _checked_consumer(consumer) == old_sha:
            backup.unlink(missing_ok=True)
            receipt_path.unlink(missing_ok=True)
        raise
    finally:
        backup_temp.unlink(missing_ok=True)
        receipt_temp.unlink(missing_ok=True)


def _swap_consumer(consumer: Path, receipt: dict) -> None:
    backup, receipt_path = _backup_paths(consumer)
    old_current = receipt["current_sha256"]
    old_backup = receipt["backup_sha256"]
    if _checked_consumer(consumer) != old_current or _checked_consumer(backup) != old_backup:
        raise RuntimeBundleSyncError("Consumer changed before rollback")
    temporary: list[Path] = []
    recovery_current: Path | None = None
    recovery_backup: Path | None = None
    recovery_receipt: Path | None = None
    try:
        staged_current = _stage_copy(backup, consumer.parent, suffix=".exe")
        temporary.append(staged_current)
        staged_backup = _stage_copy(consumer, consumer.parent, suffix=".exe")
        temporary.append(staged_backup)
        recovery_current = _stage_copy(consumer, consumer.parent, suffix=".exe")
        temporary.append(recovery_current)
        recovery_backup = _stage_copy(backup, consumer.parent, suffix=".exe")
        temporary.append(recovery_backup)
        recovery_receipt = _stage_copy(receipt_path, consumer.parent, suffix=".json")
        temporary.append(recovery_receipt)
        staged_receipt = _stage_json({**receipt, "current_sha256": old_backup,
                                      "backup_sha256": old_current}, consumer.parent)
        temporary.append(staged_receipt)
        os.replace(staged_current, consumer)
        os.replace(staged_backup, backup)
        os.replace(staged_receipt, receipt_path)
    except BaseException:
        if recovery_current is not None and _checked_consumer(consumer) != old_current:
            os.replace(recovery_current, consumer)
        if recovery_backup is not None and _checked_consumer(backup) != old_backup:
            os.replace(recovery_backup, backup)
        if recovery_receipt is not None:
            os.replace(recovery_receipt, receipt_path)
        raise
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)


def _accept_consumer(consumer: Path, receipt: dict, expected_sha: str) -> None:
    """Drop only a verified owned rollback after explicit current acceptance."""
    backup, receipt_path = _backup_paths(consumer)
    if (_checked_consumer(consumer) != expected_sha
            or receipt["current_sha256"] != expected_sha
            or _backup_state(consumer, expected_sha) != receipt):
        raise RuntimeBundleSyncError("Current consumer or retained backup changed before acceptance")
    recovery_receipt = _stage_copy(receipt_path, consumer.parent, suffix=".json")
    try:
        receipt_path.unlink()
        try:
            backup.unlink()
        except BaseException:
            os.replace(recovery_receipt, receipt_path)
            raise
    finally:
        recovery_receipt.unlink(missing_ok=True)


def sync_runtime_bundle(reference_root: str | Path, *, expected_active_sha256: str,
                        expected_rollback_sha256: str, expected_consumer_sha256: str,
                        apply: bool = False, rollback_consumer: bool = False,
                        accept_consumer: bool = False) -> dict:
    """Preview or apply the accepted bundle to this module's own checkout."""
    if rollback_consumer and accept_consumer:
        raise RuntimeBundleSyncError("Choose consumer rollback or acceptance, not both")
    active_sha = _expected_digest(expected_active_sha256, "active engine hash")
    rollback_sha = _expected_digest(expected_rollback_sha256, "rollback engine hash")
    consumer_sha = _expected_digest(expected_consumer_sha256, "consumer hash")
    reference = _checked_root(reference_root)
    target = _checked_root(PROJECT_ROOT)
    if reference != target and (reference in target.parents or target in reference.parents):
        raise RuntimeBundleSyncError("Reference and target checkouts overlap")
    ref_store = GcsimEngineStore(reference / STORE_RELATIVE)
    for path in (reference / "data", reference / "data/gcsim", ref_store.root_dir,
                 ref_store.engines_dir, ref_store.active_state_path, reference / "native",
                 reference / "native/gcsim_optimizer"):
        _plain_ancestors(path)
    try:
        ref_state = ref_store._active_state()
    except GcsimEngineStoreError as exc:
        raise RuntimeBundleSyncError(str(exc)) from exc
    if (ref_state.get("active_engine_id"), ref_state.get("rollback_engine_id")) != (ACTIVE_ID, ROLLBACK_ID):
        raise RuntimeBundleSyncError("Reference pointer does not select the accepted active/rollback pair")
    reference_engines = {}
    for engine_id, expected in ((ROLLBACK_ID, rollback_sha), (ACTIVE_ID, active_sha)):
        path = ref_store.engines_dir / engine_id
        manifest, artifact = _verified_engine(path, engine_id=engine_id,
                                               expected_artifact_sha=expected)
        reference_engines[engine_id] = (path, manifest, artifact)
    ref_consumer = reference / CONSUMER_RELATIVE
    if _checked_consumer(ref_consumer) != consumer_sha:
        raise RuntimeBundleSyncError("Reference optimizer consumer hash differs from expected")

    def inspect_target() -> tuple[GcsimEngineStore, dict, dict, str | None, dict | None]:
        store = GcsimEngineStore(target / STORE_RELATIVE)
        for path in (target / "data", target / "data/gcsim", store.root_dir,
                     store.engines_dir, store.staging_dir, store.failed_dir,
                     store.active_state_path, target / "native",
                     target / "native/gcsim_optimizer"):
            _plain_ancestors(path)
        pointer_temp = store.active_state_path.with_name(store.active_state_path.name + ".tmp")
        if _exists(pointer_temp):
            raise RuntimeBundleSyncError("Target active-pointer temporary slot is occupied")
        try:
            state = store._active_state()
        except GcsimEngineStoreError as exc:
            raise RuntimeBundleSyncError(str(exc)) from exc
        active, rollback = state.get("active_engine_id"), state.get("rollback_engine_id")
        if active not in (None, ACTIVE_ID, ROLLBACK_ID) or rollback not in (None, ACTIVE_ID, ROLLBACK_ID):
            raise RuntimeBundleSyncError("Target pointer has an unexpected active or rollback engine")
        if active is None and rollback is not None:
            raise RuntimeBundleSyncError("Target pointer has rollback without an active engine")
        installed = {}
        for engine_id, expected in ((ROLLBACK_ID, rollback_sha), (ACTIVE_ID, active_sha)):
            path = store.engines_dir / engine_id
            if _exists(path):
                installed[engine_id] = _verified_engine(path, engine_id=engine_id,
                    expected_artifact_sha=expected,
                    reference_manifest=reference_engines[engine_id][1])
            elif _exists(store.staging_dir / engine_id) or _exists(store.failed_dir / engine_id):
                raise RuntimeBundleSyncError(f"Engine ID has occupied staging/failed slot: {engine_id}")
        if active and active not in installed:
            raise RuntimeBundleSyncError("Target active engine installation is missing")
        if rollback and rollback not in installed:
            raise RuntimeBundleSyncError("Target rollback engine installation is missing")
        current_sha = _checked_consumer(target / CONSUMER_RELATIVE)
        receipt = _backup_state(target / CONSUMER_RELATIVE, current_sha)
        return store, state, installed, current_sha, receipt

    store, state, installed, current_sha, receipt = inspect_target()
    missing = [engine_id for engine_id in (ROLLBACK_ID, ACTIVE_ID) if engine_id not in installed]
    pointer_ready = (state.get("active_engine_id"), state.get("rollback_engine_id")) == (ACTIVE_ID, ROLLBACK_ID)
    consumer_change = current_sha != consumer_sha
    if consumer_change and receipt is not None and not rollback_consumer:
        raise RuntimeBundleSyncError("A verified consumer rollback already occupies the bounded slot")
    if rollback_consumer and receipt is None:
        raise RuntimeBundleSyncError("No verified consumer rollback is retained")
    if rollback_consumer and state.get("active_engine_id") not in installed:
        raise RuntimeBundleSyncError("No verified active engine for consumer rollback")
    if accept_consumer and (receipt is None or current_sha != consumer_sha or missing or not pointer_ready):
        raise RuntimeBundleSyncError("No accepted current consumer with a verified rollback exists")
    plan = {
        "mode": "apply" if apply else "preview", "reference": str(reference),
        "target": str(target), "reference_self": reference == target,
        "active_engine_id": ACTIVE_ID, "rollback_engine_id": ROLLBACK_ID,
        "active_sha256": active_sha, "rollback_sha256": rollback_sha,
        "consumer_sha256": consumer_sha, "target_consumer_sha256": current_sha,
        "retained_consumer_sha256": receipt["backup_sha256"] if receipt else None,
        "engines_to_install": missing, "engine_install_count": len(missing),
        "consumer_to_install": consumer_change and not rollback_consumer,
        "pointer_to_set": not pointer_ready, "consumer_rollback": rollback_consumer,
        "consumer_acceptance": accept_consumer,
    }
    if reference == target:
        if rollback_consumer or accept_consumer:
            raise RuntimeBundleSyncError("Reference installation is read-only")
        if not pointer_ready or consumer_change or missing:
            raise RuntimeBundleSyncError("Reference checkout is not the accepted installed bundle")
        plan["status"] = "verified_reference_noop"
        return plan
    if not apply:
        plan["status"] = "preview"
        return plan

    # Recheck after both own-checkout gates are held; preview creates no locks.
    with ExitStack() as locks:
        locks.enter_context(profile_supervisor_lock(project_root=target))
        locks.enter_context(profile_operation_lock(project_root=target))
        store, state, installed, current_sha, receipt = inspect_target()
        if accept_consumer:
            if (receipt is None or current_sha != consumer_sha
                    or set(installed) != {ACTIVE_ID, ROLLBACK_ID}
                    or (state.get("active_engine_id"), state.get("rollback_engine_id")) != (ACTIVE_ID, ROLLBACK_ID)):
                raise RuntimeBundleSyncError("Consumer acceptance state changed")
            _accept_consumer(target / CONSUMER_RELATIVE, receipt, consumer_sha)
            plan["status"] = "consumer_accepted"
            plan["retained_consumer_sha256"] = None
            return plan
        if rollback_consumer:
            if receipt is None:
                raise RuntimeBundleSyncError("Consumer rollback disappeared")
            active_entry = installed.get(state.get("active_engine_id"))
            if active_entry is None:
                raise RuntimeBundleSyncError("No verified active engine for consumer rollback")
            retained = _backup_paths(target / CONSUMER_RELATIVE)[0]
            staged_retained = _stage_copy(retained, retained.parent, suffix=".exe")
            try:
                _compatibility(store.engines_dir / state["active_engine_id"],
                               active_entry[1], active_entry[0], staged_retained)
            finally:
                staged_retained.unlink(missing_ok=True)
            _swap_consumer(target / CONSUMER_RELATIVE, receipt)
            plan["status"] = "consumer_rolled_back"
            plan["target_consumer_sha256"] = receipt["backup_sha256"]
            plan["retained_consumer_sha256"] = receipt["current_sha256"]
            return plan
        if current_sha != consumer_sha and receipt is not None:
            raise RuntimeBundleSyncError("Consumer rollback slot became occupied")
        if current_sha == consumer_sha and not missing and pointer_ready:
            plan["status"] = "already_installed"
            return plan
        target_consumer = target / CONSUMER_RELATIVE
        staged_consumer = None
        try:
            if current_sha != consumer_sha:
                target_consumer.parent.mkdir(parents=True, exist_ok=True)
                staged_consumer = _stage_copy(ref_consumer, target_consumer.parent, suffix=".exe")
                if _digest(staged_consumer) != consumer_sha:
                    raise RuntimeBundleSyncError("Staged consumer differs from accepted hash")
            for engine_id in missing:
                path, manifest, _ = reference_engines[engine_id]
                _install_engine(store, path, manifest)
            checked = {}
            for engine_id, expected in ((ROLLBACK_ID, rollback_sha), (ACTIVE_ID, active_sha)):
                checked[engine_id] = _verified_engine(store.engines_dir / engine_id,
                    engine_id=engine_id, expected_artifact_sha=expected,
                    reference_manifest=reference_engines[engine_id][1])
            candidate_consumer = staged_consumer or target_consumer
            for engine_id in (ROLLBACK_ID, ACTIVE_ID):
                manifest, artifact = checked[engine_id]
                _compatibility(store.engines_dir / engine_id, artifact, manifest, candidate_consumer)
            pointer_was_present = _exists(store.active_state_path)
            pointer_recovery = (_stage_copy(store.active_state_path, store.root_dir,
                                            suffix=".json") if not pointer_ready and pointer_was_present else None)
            try:
                if staged_consumer is not None:
                    _promote_consumer(target_consumer, staged_consumer, consumer_sha, current_sha)
                # Store activation is atomic. Make rollback first, then active.
                if not pointer_ready:
                    if state.get("active_engine_id") != ROLLBACK_ID:
                        store.activate_engine(ROLLBACK_ID)
                    store.activate_engine(ACTIVE_ID)
            except BaseException:
                if not pointer_ready:
                    if pointer_recovery is None:
                        store.active_state_path.unlink(missing_ok=True)
                    else:
                        os.replace(pointer_recovery, store.active_state_path)
                    store.active_state_path.with_name(store.active_state_path.name + ".tmp").unlink(missing_ok=True)
                if staged_consumer is not None and _checked_consumer(target_consumer) == consumer_sha:
                    if current_sha is None:
                        target_consumer.unlink(missing_ok=True)
                    else:
                        backup, receipt_path = _backup_paths(target_consumer)
                        if _checked_consumer(backup) != current_sha:
                            raise RuntimeBundleSyncError("Activation failed and consumer recovery is unavailable")
                        os.replace(backup, target_consumer)
                        receipt_path.unlink(missing_ok=True)
                raise
            finally:
                if pointer_recovery is not None:
                    pointer_recovery.unlink(missing_ok=True)
            plan["status"] = "installed"
            plan["target_consumer_sha256"] = consumer_sha
            plan["retained_consumer_sha256"] = current_sha if current_sha != consumer_sha else (receipt["backup_sha256"] if receipt else None)
            return plan
        finally:
            if staged_consumer is not None:
                staged_consumer.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", required=True, type=Path)
    parser.add_argument("--expected-active-sha256", required=True)
    parser.add_argument("--expected-rollback-sha256", required=True)
    parser.add_argument("--expected-consumer-sha256", required=True)
    parser.add_argument("--apply", action="store_true", help="perform the guarded local transfer")
    parser.add_argument("--rollback-consumer", action="store_true",
                        help="swap the current consumer with its verified retained predecessor")
    parser.add_argument("--accept-consumer", action="store_true",
                        help="explicitly accept current consumer and remove its verified retained predecessor")
    args = parser.parse_args(argv)
    try:
        result = sync_runtime_bundle(args.reference_root,
            expected_active_sha256=args.expected_active_sha256,
            expected_rollback_sha256=args.expected_rollback_sha256,
            expected_consumer_sha256=args.expected_consumer_sha256,
            apply=args.apply, rollback_consumer=args.rollback_consumer,
            accept_consumer=args.accept_consumer)
    except (RuntimeBundleSyncError, GcsimEngineStoreError, OSError, ValueError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
