import argparse
import asyncio
import json
import re
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

if __name__ == "__main__":
    import atexit
    from run_workspace.profile_control import profile_operation_lock
    _profile_operation_gate = profile_operation_lock()
    _profile_operation_gate.__enter__()
    atexit.register(lambda: _profile_operation_gate.__exit__(None, None, None))
    from run_workspace.profile_context import bootstrap_profile
    bootstrap_profile()

from .paths import HOYOLAB_DEBUG_DIR

from .artifact_db import ARTIFACT_DB_PATH
from .import_store import LegacyAccountBindingRequired, get_import_attempt
from .import_pipeline import HoYoLABImportError, run_hoyolab_import


@contextmanager
def import_run_lock(lock_path: Path | None = None):
    """OS-owned lock survives stale UI state and is released on process exit."""
    path = lock_path or HOYOLAB_DEBUG_DIR.parent / "hoyolab_import.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if sys.platform == "win32":
            import msvcrt
            acquire = lambda: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(lock, fcntl.LOCK_UN)
        try:
            acquire()
        except OSError as exc:
            raise HoYoLABImportError("Another HoYoLAB import is already running.") from exc
        try:
            yield
        finally:
            lock.seek(0)
            release()


def safe_exception_summary(exc: BaseException) -> str:
    text = str(exc).split("Call log:", 1)[0].strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > 600:
        text = text[:600] + "..."
    return text or type(exc).__name__


def main() -> int:
    parser = argparse.ArgumentParser(description="Import HoYoLAB account data")
    parser.add_argument("--change-equipment", action="store_true",
                        help="Apply currently observed equipment to local characters")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--images-only", action="store_true",
                      help="Download all account images again without importing data")
    mode.add_argument("--attempt-id", help="Stable ID for this newly captured import")
    mode.add_argument("--resume-attempt", help="Replay a saved import or finish committed enrichment")
    parser.add_argument("--adopt-legacy", action="store_true",
                        help="Bind existing account rows to the explicitly confirmed staged role")
    args = parser.parse_args()
    if args.adopt_legacy and not args.resume_attempt:
        parser.error("--adopt-legacy requires --resume-attempt")
    # A replay uses the equipment choice persisted with its source snapshot.
    # Suppress a stray CLI toggle instead of changing the staged operation.
    attempt_id = args.attempt_id
    if not args.images_only and not args.resume_attempt:
        attempt_id = attempt_id or str(uuid.uuid4())
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    try:
        with import_run_lock():
            result = asyncio.run(run_hoyolab_import(
                change_equipment=(
                    args.change_equipment and not args.images_only and not args.resume_attempt
                ),
                images_only=args.images_only,
                attempt_id=attempt_id,
                resume_attempt=args.resume_attempt,
                adopt_legacy=args.adopt_legacy,
            ))
    except LegacyAccountBindingRequired as exc:
        attempt_id = args.resume_attempt or attempt_id
        attempt = None
        if attempt_id:
            try:
                attempt = get_import_attempt(ARTIFACT_DB_PATH, attempt_id)
            except Exception:
                attempt = None
        binding = {
            "attempt_id": attempt_id,
            "account_uid": attempt.get("account_uid") if attempt else None,
            "server": attempt.get("server") if attempt else None,
        }
        print("[IMPORT_BINDING_REQUIRED] " + json.dumps(binding, ensure_ascii=False), flush=True)
        print(f"[HoYoLAB Import] {safe_exception_summary(exc)}", file=sys.stderr)
        return 3
    except HoYoLABImportError as exc:
        print(f"[HoYoLAB Import] {safe_exception_summary(exc)}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[HoYoLAB Import] Failed: {safe_exception_summary(exc)}", file=sys.stderr)
        return 1

    manifest = result.get("manifest") or {}
    print()
    print("[HoYoLAB Import] Summary")
    print("cards:", manifest.get("cardsCount"))
    print("matched characters:", manifest.get("matchedCharacters"))
    print("matched weapons:", manifest.get("matchedWeapons"))
    print("ok matches:", manifest.get("okMatches"))
    print("warning matches:", manifest.get("warningMatches"))
    artifact_summary = result.get("artifactSummary") or {}
    if artifact_summary:
        print("artifacts seen:", artifact_summary.get("relics_seen"))
        print("artifacts inserted:", artifact_summary.get("artifacts_inserted"))
        print("artifacts existing:", artifact_summary.get("artifacts_existing"))
    account_storage_summary = result.get("accountStorageSummary") or {}
    account_storage_error = result.get("accountStorageError")
    if account_storage_summary:
        print("account characters:", account_storage_summary.get("characters_seen"))
        print("account talents:", account_storage_summary.get("talents_seen"))
        print("account weapon stacks:", account_storage_summary.get("weapon_stacks_seen"))
        print("account sync warnings:", len(account_storage_summary.get("warnings") or []))
    elif account_storage_error:
        print("account SQLite sync warning:", account_storage_error)
    for warning in result.get("warnings") or []:
        print("[IMPORT_WARNING] " + json.dumps(warning, ensure_ascii=False), flush=True)
    print("manifest:", result.get("manifestPath"))
    if not args.images_only:
        print("character details:", result.get("characterDetailsPath"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
