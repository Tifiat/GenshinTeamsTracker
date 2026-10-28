"""One bounded offscreen performance check for the Stage17 Theory pages."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import threading
from time import perf_counter_ns
from unittest.mock import patch


EXPECTED_FAMILIES = 694
EXPECTED_PAGES = 13149
EXPECTED_ASSEMBLY = "2a7d6110322f11d693151eab035b4dfc0b033cd8a5dbd99f3b1f39d8a1c7bc4e"
STAGE15_SNAPSHOT = "docs/optimizer-evidence/2026-10-11-theory-real-output/terminal-snapshot.json.gz"
MANIFEST = "docs/optimizer-evidence/2026-10-11-theory-presentation/package/manifest.json"
INITIAL = "docs/optimizer-evidence/2026-10-11-theory-presentation/initial.json"
SCRATCH = ".codex_tmp/theory-presentation-benchmark"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8"))


def _find_snapshot(value: object, path: str = "$") -> tuple[dict, str]:
    if isinstance(value, dict):
        if (
            value.get("schema_kind") == "gtt_gcsim_optimizer_theory_result_v2"
            and value.get("schema_version") == 2
            and value.get("status") == "success"
        ):
            return value, path
        for key, child in value.items():
            try:
                return _find_snapshot(child, f"{path}.{key}")
            except LookupError:
                pass
    elif isinstance(value, list):
        for index, child in enumerate(value):
            try:
                return _find_snapshot(child, f"{path}[{index}]")
            except LookupError:
                pass
    raise LookupError("terminal snapshot contains no successful Theory snapshot")


def _tuple_keys(value: object):
    if isinstance(value, dict):
        key = value.get("tuple_key")
        if isinstance(key, str) and key:
            yield key
        for child in value.values():
            yield from _tuple_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _tuple_keys(child)


def _wait_for_release(timeout_seconds: int = 180) -> None:
    line: list[str] = []
    ready = threading.Event()

    def read_line() -> None:
        line.append(sys.stdin.readline())
        ready.set()

    threading.Thread(target=read_line, daemon=True).start()
    if not ready.wait(timeout_seconds):
        raise TimeoutError(f"preview release token not received within {timeout_seconds}s")
    if not line or line[0].strip() != "RELEASE":
        raise ValueError("preview release token was not RELEASE")


def _elapsed(start: int) -> float:
    return round((perf_counter_ns() - start) / 1_000_000, 3)


@contextmanager
def _restore_working_directory():
    previous = Path.cwd()
    try:
        yield
    finally:
        # Windows cannot remove the process's current directory. Restore before
        # the surrounding managed-job cleaner runs, including on exceptions.
        os.chdir(previous)


def run(repo: Path, main: Path) -> tuple[dict, int]:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    sys.dont_write_bytecode = True
    repo, main = repo.resolve(), main.resolve()
    sys.path.insert(0, str(repo))

    from tools.experiments.gcsim.theory_presentation import package

    io = package.io
    evidence = repo / "docs/optimizer-evidence/2026-10-11-theory-presentation"
    initial_raw = (evidence / "initial.json").read_bytes()
    initial = json.loads(initial_raw)
    manifest_raw = (evidence / "package/manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    summary: dict = {
        "status": "running",
        "source": {
            "worker_head": initial["worker_head"],
            "manifest_sha256": _sha(manifest_raw),
            "initial_sha256": _sha(initial_raw),
        },
        "target": {},
        "counts": {},
        "timings_ms": {},
        "guards": {},
        "cleanup": {},
    }
    managed: dict | None = None
    pins_before = None
    try:
        pins_before = package.pins(repo, main, initial)
        summary["target"] = {"head": pins_before["target_head"], "pins_before_sha256": _canonical(pins_before)}
        if manifest.get("base_head") != pins_before["target_head"]:
            raise ValueError("Stage17 base head does not match the current pinned main Git head")

        job_root = repo / SCRATCH
        with io.managed_job(job_root) as managed, _restore_working_directory():
            job = managed["path"]
            bundle = job / "combined-payloads"
            destination = job / "materialized"
            bundle.mkdir()

            combined_patches = []
            combined_bytes = 0
            for row in manifest["patches"]:
                logical = f"combined/{row['path']}.patch"
                record = manifest["payload_sources"].get(logical)
                if not isinstance(record, dict):
                    raise ValueError("combined payload reference is missing: " + logical)
                payload = package._read_payload(repo, record)
                if _sha(payload) != row["payload_sha256"]:
                    raise ValueError("combined payload does not match manifest patch: " + logical)
                payload_path = bundle / Path(*Path(logical).parts)
                payload_path.parent.mkdir(parents=True, exist_ok=True)
                payload_path.write_bytes(payload)
                combined_bytes += len(payload)
                combined_patches.append({**row, "payload": logical})
            if len(combined_patches) != 76:
                raise ValueError(f"expected 76 combined references, got {len(combined_patches)}")

            replay_manifest = {
                **manifest,
                "patches": combined_patches,
            }
            started = perf_counter_ns()
            replay_records = io.materialize_from_manifest(
                main, replay_manifest, bundle, destination,
            )
            summary["timings_ms"]["materialize"] = _elapsed(started)
            inventory_hash = _sha(json.dumps(replay_records, sort_keys=True, separators=(",", ":")).encode())
            summary["target"]["assembly_records_sha256"] = inventory_hash
            if inventory_hash != EXPECTED_ASSEMBLY:
                raise ValueError("benchmark assembly differs from the verified target inventory")
            summary["counts"].update({
                "combined_payload_references": len(combined_patches),
                "combined_payload_bytes": combined_bytes,
                "materialized_files": len(replay_records),
                "materialized_base_files": len(manifest["base_files"]),
            })

            snapshot_path = repo / STAGE15_SNAPSHOT
            started = perf_counter_ns()
            compressed = snapshot_path.read_bytes()
            summary["timings_ms"]["gzip_file_read"] = _elapsed(started)
            started = perf_counter_ns()
            decoded = gzip.decompress(compressed)
            summary["timings_ms"]["gzip_decompress"] = _elapsed(started)
            started = perf_counter_ns()
            terminal = json.loads(decoded)
            summary["timings_ms"]["json_parse"] = _elapsed(started)
            candidate, snapshot_path_in_json = _find_snapshot(terminal)
            candidate_hash_before = _canonical(candidate)
            summary["source"].update({
                "terminal_snapshot_sha256": _sha(compressed),
                "terminal_snapshot_compressed_bytes": len(compressed),
                "terminal_snapshot_json_bytes": len(decoded),
                "snapshot_path": snapshot_path_in_json,
            })

            sys.path.insert(0, str(destination))
            os.chdir(destination)
            from localization import set_language
            import inspect

            language_parameters = inspect.signature(set_language).parameters
            language_kwargs = {"persist": False} if "persist" in language_parameters else {}
            set_language("ru", **language_kwargs)

            from PySide6.QtCore import QCoreApplication, QEvent
            from PySide6.QtWidgets import QApplication, QWidget
            from run_workspace.gcsim.optimizer_go_theory_session import copy_theory_snapshot
            from ui.gcsim_browser import optimizer_result, theory_result
            from ui.gcsim_browser.optimizer_result import (
                CompactOptimizerArtifactCard, OptimizerResultBuildsWidget,
            )

            started = perf_counter_ns()
            snapshot = copy_theory_snapshot(candidate)
            summary["timings_ms"]["copy_theory_snapshot"] = _elapsed(started)
            snapshot_hash_before = _canonical(snapshot)

            started = perf_counter_ns()
            pages = theory_result.TheoryResultPages(snapshot)
            summary["timings_ms"]["index"] = _elapsed(started)
            entries = pages.index.entries
            family_count = len({id(entry.row) for entry in entries})
            page_count = len(pages)
            indexed_keys = {entry.alias["tuple_key"] for entry in entries}
            pending_keys = set(_tuple_keys(snapshot.get("pending", ())))
            included_pending = len(indexed_keys & pending_keys)
            summary["counts"].update({
                "scored_families": family_count,
                "co_leader_families": len(snapshot.get("co_leaders", ())),
                "pending_rows": len(snapshot.get("pending", ())),
                "indexed_pages": page_count,
                "unique_indexed_tuple_keys": len(indexed_keys),
                "valid_pending_aliases_in_index": included_pending,
            })
            if family_count != EXPECTED_FAMILIES:
                raise ValueError(f"expected {EXPECTED_FAMILIES} scored families, got {family_count}")
            if page_count != EXPECTED_PAGES:
                raise ValueError(f"expected {EXPECTED_PAGES} alias pages, got {page_count}")
            if not math.isclose(pages.index.reference, float(snapshot["reference_score"]), rel_tol=0.0, abs_tol=1e-9):
                raise ValueError("fixed page reference differs from the published snapshot reference")
            if included_pending <= 0:
                raise ValueError("no eligible pending alias is present in the page index")

            started = perf_counter_ns()
            first_page = pages[0]
            summary["timings_ms"]["first_page"] = _elapsed(started)
            if first_page.theory_context.reference != pages.index.reference:
                raise ValueError("first page relative-DPS reference differs from the fixed index reference")

            app = QApplication.instance() or QApplication([])
            host = QWidget()
            host.resize(1100, 650)
            widget = OptimizerResultBuildsWidget(host)
            widget.setGeometry(0, 0, 1100, 650)
            widget.ensurePolished()
            blocker = AssertionError("a non-Theory optimizer or inventory path ran while paging")
            blocked_targets: list[tuple[object, str]] = [
                (optimizer_result, "build_optimizer_result_pages"),
            ]
            app_shell = None
            try:
                import ui.app_shell as app_shell
                for name in ("build_optimizer_result_pages", "list_all_artifacts"):
                    if callable(getattr(app_shell, name, None)):
                        blocked_targets.append((app_shell, name))
                shell_type = getattr(app_shell, "AppShell", None)
                if shell_type is not None and callable(getattr(shell_type, "list_all_artifacts", None)):
                    blocked_targets.append((shell_type, "list_all_artifacts"))
            except Exception:
                # The standalone page widget has no AppShell dependency.
                pass
            from ui.gcsim_browser import run_worker
            for name, worker_type in vars(run_worker).items():
                if isinstance(worker_type, type) and "Worker" in name and callable(getattr(worker_type, "run", None)):
                    blocked_targets.append((worker_type, "run"))
            session_module = __import__(
                "run_workspace.gcsim.optimizer_go_theory_session", fromlist=["_LegacyTheorySession"],
            )
            for name, session_type in vars(session_module).items():
                if "TheorySession" in name and isinstance(session_type, type) and callable(getattr(session_type, "run", None)):
                    blocked_targets.append((session_type, "run"))

            unique_targets = []
            seen_targets = set()
            for target, name in blocked_targets:
                identity = (id(target), name)
                if identity not in seen_targets:
                    seen_targets.add(identity)
                    unique_targets.append((target, name))
            summary["guards"]["blocked_callables"] = [name for _, name in unique_targets]

            original_builder = theory_result.build_theory_page
            with patch.object(theory_result, "build_theory_page", wraps=original_builder) as builder_spy:
                with __import__("contextlib").ExitStack() as guards:
                    for target, name in unique_targets:
                        guards.enter_context(patch.object(target, name, side_effect=blocker))
                    started = perf_counter_ns()
                    widget.set_pages(pages)
                    widget.layout().activate()
                    widget.table.layout().activate()
                    app.processEvents()
                    summary["timings_ms"]["first_qt_20_card_render"] = _elapsed(started)

                    first_entry = pages.index.entries[0]
                    _verify_page(first_page, first_entry, theory_result.theory_stat_label)
                    _verify_rows(widget, first_page)
                    first_cards = len(widget.findChildren(CompactOptimizerArtifactCard))
                    all_first_cards = _all_card_count(app, CompactOptimizerArtifactCard)
                    if first_cards != 20 or all_first_cards != 20:
                        raise ValueError(f"first page rendered {first_cards} current / {all_first_cards} total cards, expected 20")

                    positions = [((i + 1) * (page_count - 1)) // 12 for i in range(12)]
                    navigation_ms = []
                    current = widget.current_page_index
                    for target in positions:
                        started = perf_counter_ns()
                        widget._change_page(target - current)
                        app.processEvents()
                        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                        app.processEvents()
                        navigation_ms.append(_elapsed(started))
                        current = target
                        page = pages[target]
                        _verify_page(page, pages.index.entries[target], theory_result.theory_stat_label)
                        _verify_rows(widget, page)
                        cards = len(widget.findChildren(CompactOptimizerArtifactCard))
                        all_cards = _all_card_count(app, CompactOptimizerArtifactCard)
                        if cards != 20 or all_cards != 20:
                            raise ValueError(f"page {target + 1} retained {cards} current / {all_cards} total cards, expected 20")
                        if pages._cached_index != target:
                            raise ValueError("Theory page cache retained a page other than the current page")
                        if page.theory_context.reference != pages.index.reference:
                            raise ValueError("relative-DPS reference drifted during navigation")
                    summary["timings_ms"]["navigation_12_positions"] = navigation_ms
                    summary["counts"].update({
                        "navigation_positions": len(positions),
                        "last_navigation_page": positions[-1] + 1,
                        "maximum_current_cards": 20,
                        "first_page_cards": first_cards,
                    })
                    if positions[-1] != page_count - 1:
                        raise ValueError("last page was not included in spread navigation")
                    if not widget._theory_noncrit_labels or widget._save_buttons:
                        raise ValueError("Theory page did not replace Save actions with noncrit summaries")
                    if builder_spy.call_count != 12:
                        raise ValueError(f"expected 12 spread-navigation page builds, got {builder_spy.call_count}")
                    summary["counts"]["theory_page_build_calls"] = builder_spy.call_count
                    summary["guards"].update({
                        "forbidden_paths_called": 0,
                        "save_buttons": len(widget._save_buttons),
                        "noncrit_summary_labels": len(widget._theory_noncrit_labels),
                    })

                    widget._change_page(-widget.current_page_index)
                    app.processEvents()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                    app.processEvents()
                    widget.resize(1100, 650)
                    widget.layout().activate()
                    app.processEvents()
                    preview = job / "theory-page-preview.png"
                    if not widget.grab().save(str(preview)):
                        raise ValueError("offscreen widget grab could not save the preview PNG")
                    summary["preview"] = {
                        "path": str(preview),
                        "bytes": preview.stat().st_size,
                        "widget_size": [widget.width(), widget.height()],
                    }
                    summary["counts"]["theory_page_build_calls"] = builder_spy.call_count
                    if builder_spy.call_count != 13:
                        raise ValueError(f"expected 13 observed lazy page builds after preview reset, got {builder_spy.call_count}")

            candidate_hash_after = _canonical(candidate)
            snapshot_hash_after = _canonical(snapshot)
            if candidate_hash_before != candidate_hash_after or snapshot_hash_before != snapshot_hash_after:
                raise ValueError("input snapshot canonical hash changed during the render check")
            summary["guards"].update({
                "copy_calls": 1,
                "input_snapshot_unchanged": True,
                "copied_snapshot_unchanged": True,
                "desktop_capture_calls": 0,
                "engine_calls": 0,
                "database_calls": 0,
                "main_writes": 0,
                "account_or_runtime_writes": 0,
                "go_builds": 0,
            })
            summary["source"]["input_snapshot_canonical_sha256"] = candidate_hash_before
            summary["source"]["copied_snapshot_canonical_sha256"] = snapshot_hash_before
            summary["status"] = "preview_ready"
            print("PREVIEW " + json.dumps({
                "path": summary["preview"]["path"],
                "bytes": summary["preview"]["bytes"],
                "size": summary["preview"]["widget_size"],
                "counts": summary["counts"],
                "timings_ms": summary["timings_ms"],
            }, sort_keys=True, separators=(",", ":")), flush=True)
            _wait_for_release()

        summary["cleanup"] = {
            "cleaned": bool(managed and managed.get("cleaned")),
            "removed_bytes": managed.get("removed_bytes", 0) if managed else 0,
            "root_empty": not job_root.exists() or not any(job_root.iterdir()),
        }
        if not summary["cleanup"]["cleaned"] or not summary["cleanup"]["root_empty"]:
            raise ValueError("managed benchmark job was not fully cleaned")
        pins_after = package.pins(repo, main, initial)
        summary["target"]["pins_after_sha256"] = _canonical(pins_after)
        summary["target"]["pins_unchanged"] = pins_before == pins_after
        if pins_before != pins_after:
            raise ValueError("main/runtime pins changed during the benchmark")
        summary["status"] = "pass"
        return summary, 0
    except BaseException as exc:
        summary["status"] = "fail"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        summary["cleanup"] = {
            "cleaned": bool(managed and managed.get("cleaned")),
            "removed_bytes": managed.get("removed_bytes", 0) if managed else 0,
            "cleanup_error": managed.get("cleanup_error") if managed else None,
        }
        try:
            pins_after = package.pins(repo, main, initial)
            summary["target"]["pins_after_sha256"] = _canonical(pins_after)
            summary["target"]["pins_unchanged"] = pins_before == pins_after
        except BaseException as pin_error:
            summary["target"]["pins_after_error"] = f"{type(pin_error).__name__}: {pin_error}"
        return summary, 1


def _verify_page(page, entry, stat_label) -> None:
    witness = entry.row["witness45"]
    if page.theory_context is None:
        raise ValueError("Theory page has no fixed-reference context")
    if page.theory_context.reference <= 0:
        raise ValueError("Theory page reference is not positive")
    if len(page.rows) != len(witness["Mains"]):
        raise ValueError("Theory page row count differs from witness actors")
    for actor, row in enumerate(page.rows):
        if not row.hypothetical or row.can_save or row.slots:
            raise ValueError("Theory artifact row is not hypothetical and unsaveable")
        if len(row.artifacts) != 5:
            raise ValueError("Theory witness did not render five artifact cards per actor")
        for slot, artifact in enumerate(row.artifacts):
            if artifact.main_property_name != stat_label(witness["Mains"][actor][slot]):
                raise ValueError("displayed artifact main does not match its joint witness")

        expected: dict[str, float] = {}
        allocation = entry.row["allocations"][actor]
        for slot, lines in enumerate(witness["Lines"][actor]):
            for line, coordinate in enumerate(lines):
                stat = allocation["substats"][coordinate]
                key = stat["stat_key"]
                if key not in {"crit_rate", "crit_damage"}:
                    expected[key] = expected.get(key, 0.0) + witness["Upgrades"][actor][slot][line]
        expected = {key: value for key, value in expected.items() if value}
        observed = dict(row.noncrit_upgrade_units)
        if set(observed) != set(expected) or any(
            not math.isclose(observed[key], value, rel_tol=0.0, abs_tol=1e-9)
            for key, value in expected.items()
        ):
            raise ValueError("noncrit upgrade summary differs from Witness45 upgrades")


def _verify_rows(widget, page) -> None:
    if any(not row.hypothetical or row.can_save or row.slots for row in page.rows):
        raise ValueError("Theory page exposes saveable or inventory-backed rows")
    if len(widget._theory_noncrit_labels) != len(page.rows):
        raise ValueError("Theory noncrit summary labels do not cover all actors")
    if widget._save_buttons:
        raise ValueError("Theory page exposed a Save button")


def _all_card_count(app, card_type) -> int:
    return sum(isinstance(widget, card_type) for widget in app.allWidgets())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--main", type=Path, required=True)
    args = parser.parse_args()
    summary, status = run(args.repo, args.main)
    print("FINAL " + json.dumps(summary, sort_keys=True, separators=(",", ":")), flush=True)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
