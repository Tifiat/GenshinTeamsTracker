import asyncio
import gc
import re
import sys

from .import_pipeline import HoYoLABImportError, run_hoyolab_import


def safe_exception_summary(exc: BaseException) -> str:
    text = str(exc).split("Call log:", 1)[0].strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > 600:
        text = text[:600] + "..."
    return text or type(exc).__name__


def run_async(coro):
    loop = asyncio.new_event_loop()

    try:
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(coro)
        loop.run_until_complete(asyncio.sleep(0.5))
        gc.collect()
        return result
    finally:
        pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
        for task in pending:
            task.cancel()

        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(asyncio.sleep(0))
        gc.collect()
        asyncio.set_event_loop(None)
        loop.close()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    try:
        result = run_async(run_hoyolab_import())
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
    print("manifest:", result.get("manifestPath"))
    print("character details:", result.get("characterDetailsPath"))
    print("overlay:", result.get("overlayPath"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
