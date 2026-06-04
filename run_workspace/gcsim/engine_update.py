"""Dev command for official GCSIM source update through the engine store.

This command is intentionally backend-only. It downloads official source,
prepares it through `GcsimEngineStore`, and records metadata, but it does not
build/run the GCSIM binary yet. Runtime readiness remains false until a later
task adds build and executable smoke checks.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

from .engine_store import (
    GcsimEngineStore,
    GcsimEngineUpdateResult,
    OverlayPatchBackend,
    PatchBackend,
)
from .source_acquisition import (
    DEFAULT_GCSIM_SOURCE_CACHE_DIR,
    GCSIM_UPSTREAM_REPO,
    OfficialGcsimSourceAcquisition,
    acquire_official_gcsim_source,
)


DEFAULT_GCSIM_PATCH_STACK_DIR = Path(__file__).resolve().parent / "patch_stack"
GCSIM_REQUIRED_SOURCE_PATHS = (
    "go.mod",
    "cmd/gcsim/main.go",
    "pkg/simulator",
    "pkg/model",
)


@dataclass(frozen=True, slots=True)
class GcsimOfficialEngineUpdateReport:
    success: bool
    activated: bool
    release: str
    engine_id: str | None
    previous_active_engine_id: str | None
    active_engine_id: str | None
    engine_path: str
    source_dir: str
    source_archive_path: str
    source_archive_url: str
    upstream_ref: str
    upstream_repo: str
    patch_backend: str
    patch_count: int
    patch_stack_path: str
    patch_stack_status: str
    check_status: str
    runtime_ready: bool
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "activated": self.activated,
            "release": self.release,
            "engine_id": self.engine_id,
            "previous_active_engine_id": self.previous_active_engine_id,
            "active_engine_id": self.active_engine_id,
            "engine_path": self.engine_path,
            "source_dir": self.source_dir,
            "source_archive_path": self.source_archive_path,
            "source_archive_url": self.source_archive_url,
            "upstream_ref": self.upstream_ref,
            "upstream_repo": self.upstream_repo,
            "patch_backend": self.patch_backend,
            "patch_count": self.patch_count,
            "patch_stack_path": self.patch_stack_path,
            "patch_stack_status": self.patch_stack_status,
            "check_status": self.check_status,
            "runtime_ready": self.runtime_ready,
            "error": self.error,
        }


def prepare_official_gcsim_engine_update(
    *,
    release: str = "latest",
    store_dir: str | Path | None = None,
    source_cache_dir: str | Path | None = None,
    patch_stack_dir: str | Path | None = None,
    engine_id: str | None = None,
    patch_backend: PatchBackend | None = None,
    source_acquirer: Callable[..., OfficialGcsimSourceAcquisition] | None = None,
) -> GcsimOfficialEngineUpdateReport:
    store = GcsimEngineStore(store_dir)
    previous_active = store.active_engine_id()
    acquirer = source_acquirer or acquire_official_gcsim_source
    try:
        acquisition = acquirer(
            release=release,
            cache_dir=source_cache_dir or DEFAULT_GCSIM_SOURCE_CACHE_DIR,
        )
    except Exception as exc:  # noqa: BLE001 - command/report boundary.
        return GcsimOfficialEngineUpdateReport(
            success=False,
            activated=False,
            release=str(release),
            engine_id=None,
            previous_active_engine_id=previous_active,
            active_engine_id=previous_active,
            engine_path="",
            source_dir="",
            source_archive_path="",
            source_archive_url="",
            upstream_ref="",
            upstream_repo=GCSIM_UPSTREAM_REPO,
            patch_backend=(patch_backend or OverlayPatchBackend()).name,
            patch_count=0,
            patch_stack_path="",
            patch_stack_status="not_started",
            check_status="source_acquisition_failed",
            runtime_ready=False,
            error=str(exc),
        )

    patch_stack = _resolve_patch_stack_dir(patch_stack_dir)
    patch_stack_status = "present" if patch_stack is not None else "absent_no_patches"
    backend = patch_backend or OverlayPatchBackend()
    metadata = _engine_manifest_metadata(
        acquisition=acquisition,
        requested_release=release,
        patch_stack=patch_stack,
        patch_stack_status=patch_stack_status,
    )
    update_result = store.prepare_engine_update(
        source_dir=acquisition.source_dir,
        patch_stack_dir=patch_stack,
        source_label=f"gcsim-{acquisition.source_ref.tag}",
        engine_id=engine_id,
        patch_backend=backend,
        capabilities=("official_source_layout", "gtt_patch_stack_boundary"),
        metadata=metadata,
        smoke_check=gcsim_source_layout_smoke_check,
    )
    return _report_from_update_result(
        release=release,
        store=store,
        acquisition=acquisition,
        patch_stack=patch_stack,
        patch_stack_status=patch_stack_status,
        update_result=update_result,
    )


def gcsim_source_layout_smoke_check(engine_dir: Path) -> str:
    missing = [
        relative
        for relative in GCSIM_REQUIRED_SOURCE_PATHS
        if not (engine_dir / relative).exists()
    ]
    if missing:
        return "GCSIM source layout check failed; missing: " + ", ".join(missing)
    return ""


def _engine_manifest_metadata(
    *,
    acquisition: OfficialGcsimSourceAcquisition,
    requested_release: str,
    patch_stack: Path | None,
    patch_stack_status: str,
) -> dict[str, str]:
    return {
        "upstream_repo": acquisition.source_ref.upstream_repo,
        "upstream_release_request": str(requested_release),
        "upstream_ref": acquisition.source_ref.tag,
        "upstream_source_archive_url": acquisition.source_ref.archive_url,
        "upstream_html_url": acquisition.source_ref.html_url,
        "upstream_api_url": acquisition.source_ref.api_url,
        "source_acquisition_status": "ok",
        "source_archive_path": str(acquisition.archive_path),
        "source_cache_dir": str(acquisition.cache_dir),
        "patch_stack_path": "" if patch_stack is None else str(patch_stack),
        "patch_stack_status": patch_stack_status,
        "check_status": "source_layout_passed",
        "runtime_ready": "false",
        "runtime_check_status": "not_run_no_build_step_yet",
    }


def _report_from_update_result(
    *,
    release: str,
    store: GcsimEngineStore,
    acquisition: OfficialGcsimSourceAcquisition,
    patch_stack: Path | None,
    patch_stack_status: str,
    update_result: GcsimEngineUpdateResult,
) -> GcsimOfficialEngineUpdateReport:
    active_engine_id = store.active_engine_id()
    check_status = (
        "source_layout_passed"
        if update_result.success
        else (update_result.error or "engine_update_failed")
    )
    return GcsimOfficialEngineUpdateReport(
        success=update_result.success,
        activated=update_result.activated,
        release=str(release),
        engine_id=update_result.engine_id,
        previous_active_engine_id=update_result.previous_active_engine_id,
        active_engine_id=active_engine_id,
        engine_path="" if update_result.engine_path is None else str(update_result.engine_path),
        source_dir=str(acquisition.source_dir),
        source_archive_path=str(acquisition.archive_path),
        source_archive_url=acquisition.source_ref.archive_url,
        upstream_ref=acquisition.source_ref.tag,
        upstream_repo=acquisition.source_ref.upstream_repo,
        patch_backend=update_result.patch_result.backend,
        patch_count=update_result.patch_result.patch_count,
        patch_stack_path="" if patch_stack is None else str(patch_stack),
        patch_stack_status=patch_stack_status,
        check_status=check_status,
        runtime_ready=False,
        error=update_result.error,
    )


def _resolve_patch_stack_dir(path: str | Path | None) -> Path | None:
    if path is not None:
        return Path(path)
    if DEFAULT_GCSIM_PATCH_STACK_DIR.exists():
        return DEFAULT_GCSIM_PATCH_STACK_DIR
    return None


def _format_report_text(report: GcsimOfficialEngineUpdateReport) -> str:
    lines = [
        "GCSIM engine source update",
        f"success={report.success} activated={report.activated}",
        f"release={report.release} upstream_ref={report.upstream_ref}",
        f"engine_id={report.engine_id or ''}",
        f"active_engine_id={report.active_engine_id or ''}",
        f"previous_active_engine_id={report.previous_active_engine_id or ''}",
        f"source_dir={report.source_dir}",
        f"archive={report.source_archive_path}",
        f"engine_path={report.engine_path}",
        (
            "patch="
            f"backend={report.patch_backend} count={report.patch_count} "
            f"stack_status={report.patch_stack_status}"
        ),
        (
            "checks="
            f"layout={report.check_status} runtime_ready={str(report.runtime_ready).lower()}"
        ),
    ]
    if report.error:
        lines.append(f"error={report.error}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch official genshinsim/gcsim source and prepare a local "
            "transactional GTT engine folder. This does not build/run GCSIM yet."
        )
    )
    parser.add_argument("--release", default="latest", help="GitHub release tag or 'latest'.")
    parser.add_argument("--store-dir", default=None, help="Optional engine store root.")
    parser.add_argument("--source-cache-dir", default=None, help="Optional source cache root.")
    parser.add_argument(
        "--patch-stack",
        default=None,
        help=(
            "Optional overlay patch-stack directory. If omitted, the command uses "
            "run_workspace/gcsim/patch_stack only when it exists."
        ),
    )
    parser.add_argument("--engine-id", default=None, help="Optional explicit engine id.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = prepare_official_gcsim_engine_update(
        release=args.release,
        store_dir=args.store_dir,
        source_cache_dir=args.source_cache_dir,
        patch_stack_dir=args.patch_stack,
        engine_id=args.engine_id,
    )
    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(_format_report_text(report))
    return 0 if report.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
