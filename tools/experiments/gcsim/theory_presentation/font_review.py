"""One capture-free font/readability review of a real Stage17 Theory row."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import threading


ASSEMBLY_SHA256 = "2a7d6110322f11d693151eab035b4dfc0b033cd8a5dbd99f3b1f39d8a1c7bc4e"
SNAPSHOT_PATH = "docs/optimizer-evidence/2026-10-11-theory-real-output/terminal-snapshot.json.gz"
EVIDENCE = "docs/optimizer-evidence/2026-10-11-theory-presentation"
SCRATCH = ".codex_tmp/theory-presentation-font-review"
GLYPHS = {"Latin_A": "A", "Cyrillic_T": "Т", "Cyrillic_D": "Д", "digit_1": "1", "percent": "%", "Unicode_minus": "−"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8"))


def _find_snapshot(value: object) -> dict:
    if isinstance(value, dict):
        if value.get("schema_kind") == "gtt_gcsim_optimizer_theory_result_v2" and value.get("schema_version") == 2 and value.get("status") == "success":
            return value
        for child in value.values():
            try:
                return _find_snapshot(child)
            except LookupError:
                pass
    elif isinstance(value, list):
        for child in value:
            try:
                return _find_snapshot(child)
            except LookupError:
                pass
    raise LookupError("Stage15 terminal snapshot contains no successful Theory snapshot")


@contextmanager
def _restore_cwd():
    previous = Path.cwd()
    try:
        yield
    finally:
        os.chdir(previous)


def _wait_for_release(timeout_seconds: int = 180) -> None:
    received: list[str] = []
    ready = threading.Event()

    def read_line() -> None:
        received.append(sys.stdin.readline())
        ready.set()

    threading.Thread(target=read_line, daemon=True).start()
    if not ready.wait(timeout_seconds):
        raise TimeoutError(f"preview RELEASE not received within {timeout_seconds}s")
    if not received or received[0].strip() != "RELEASE":
        raise ValueError("preview release token was not RELEASE")


def _probe(font, QFontInfo, QRawFont, QFontMetrics) -> dict:
    raw = QRawFont.fromFont(font)
    metrics = QFontMetrics(font)
    raw_support = {}
    metric_support = {}
    legacy_char_support = {}
    for key, char in GLYPHS.items():
        try:
            raw_support[key] = bool(raw.supportsCharacter(ord(char))) if raw.isValid() else False
        except (TypeError, RuntimeError):
            try:
                raw_support[key] = bool(raw.supportsCharacter(char)) if raw.isValid() else False
            except Exception:
                raw_support[key] = False
        try:
            legacy_char_support[key] = bool(metrics.inFont(char))
        except (TypeError, RuntimeError):
            legacy_char_support[key] = None
        # Probe Unicode codepoints directly. The deprecated QChar binding can
        # return a different result for Cyrillic/minus than this UCS4 API.
        metric_support[key] = bool(metrics.inFontUcs4(ord(char)))
    return {
        "requested_family": font.family(),
        "point_size": font.pointSizeF(),
        "pixel_size": font.pixelSize(),
        "resolved_family": QFontInfo(font).family(),
        "style": QFontInfo(font).styleName(),
        "raw_font_valid": raw.isValid(),
        "raw_font_supports": raw_support,
        "metrics_glyphs_present": metric_support,
        "legacy_qchar_infont": legacy_char_support,
        "metrics_api": "QFontMetrics.inFontUcs4",
        "all_glyphs_supported": raw.isValid() and all(raw_support.values()) and all(metric_support.values()),
    }


def _label_evidence(widget) -> dict:
    from PySide6.QtWidgets import QLabel

    nonempty = []
    replacements = 0
    cyrillic = set()
    roundtrip = True
    labels = widget.findChildren(QLabel)
    for label in labels:
        value = label.text()
        if not value:
            continue
        replacements += value.count("\ufffd")
        roundtrip = roundtrip and value.encode("utf-8").decode("utf-8") == value
        cyrillic.update(ord(char) for char in value if "\u0400" <= char <= "\u04ff")
        if len(nonempty) < 10:
            nonempty.append({"object_name": label.objectName(), "text": value[:180]})
    return {
        "label_count": len(labels),
        "nonempty_label_count": sum(bool(label.text()) for label in labels),
        "utf8_roundtrip_all": roundtrip,
        "replacement_character_count": replacements,
        "cyrillic_codepoint_count": len(cyrillic),
        "cyrillic_codepoints": [f"U+{codepoint:04X}" for codepoint in sorted(cyrillic)],
        "sample_production_labels": nonempty,
    }


def run(repo: Path, main: Path) -> tuple[dict, int]:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ.pop("QT_SCALE_FACTOR", None)
    os.environ.pop("GTT_UI_SCALE", None)
    sys.dont_write_bytecode = True
    repo, main = repo.resolve(), main.resolve()
    sys.path.insert(0, str(repo))
    from tools.experiments.gcsim.theory_presentation import package

    io = package.io
    initial_path = repo / EVIDENCE / "initial.json"
    manifest_path = repo / EVIDENCE / "package/manifest.json"
    initial_raw, manifest_raw = initial_path.read_bytes(), manifest_path.read_bytes()
    initial, manifest = json.loads(initial_raw), json.loads(manifest_raw)
    summary: dict = {
        "check_id": "font-review-03",
        "status": "running",
        "source": {"worker_head": initial["worker_head"], "manifest_sha256": _sha(manifest_raw), "initial_sha256": _sha(initial_raw)},
        "target": {}, "row": {}, "font": {}, "strings": {}, "palette": {}, "scale": {}, "preview": {}, "cleanup": {},
    }
    managed = None
    pins_before = None
    job_root = repo / SCRATCH
    try:
        summary["preview_transport"] = {"stdin_isatty": sys.stdin.isatty(), "requires_live_pty": True}
        if not sys.stdin.isatty():
            raise RuntimeError("preview review requires a live PTY before allocating scratch")
        pins_before = package.pins(repo, main, initial)
        summary["target"] = {"head": pins_before["target_head"], "pins_before_sha256": _canonical(pins_before)}
        if manifest.get("base_head") != pins_before["target_head"]:
            raise ValueError("Stage17 manifest base does not match the pinned main head")

        with io.managed_job(job_root) as managed, _restore_cwd():
            job = managed["path"]
            bundle, destination = job / "combined-payloads", job / "materialized"
            bundle.mkdir()
            combined = []
            payload_bytes = 0
            for patch in manifest["patches"]:
                logical = f"combined/{patch['path']}.patch"
                reference = manifest["payload_sources"].get(logical)
                if not isinstance(reference, dict):
                    raise ValueError("missing combined payload reference: " + logical)
                payload = package._read_payload(repo, reference)
                if _sha(payload) != patch["payload_sha256"]:
                    raise ValueError("combined payload hash mismatch: " + logical)
                target = bundle.joinpath(*Path(logical).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                payload_bytes += len(payload)
                combined.append({**patch, "payload": logical})
            if len(combined) != 76:
                raise ValueError(f"expected 76 combined payloads, found {len(combined)}")
            records = io.materialize_from_manifest(main, {**manifest, "patches": combined}, bundle, destination)
            assembly = _sha(json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            if assembly != ASSEMBLY_SHA256:
                raise ValueError("fresh assembly inventory differs from target-check-01")
            summary["target"].update({
                "assembly_records_sha256": assembly,
                "combined_payload_references": len(combined),
                "combined_payload_bytes": payload_bytes,
                "materialized_files": len(records),
            })

            compressed = (repo / SNAPSHOT_PATH).read_bytes()
            terminal = json.loads(gzip.decompress(compressed))
            candidate = _find_snapshot(terminal)
            sys.path.insert(0, str(destination))
            os.chdir(destination)
            # The freshly decoded retained snapshot is detached. Only its one
            # selected family is indexed below; no full13k validation/benchmark.
            snapshot = candidate
            original_hash = _canonical(snapshot)
            source_rows = snapshot.get("co_leaders")
            if not isinstance(source_rows, list) or not source_rows:
                raise ValueError("snapshot has no first co-leader row")
            source_row = source_rows[0]
            aliases = source_row.get("aliases")
            if not isinstance(aliases, list) or not aliases:
                raise ValueError("first co-leader has no actual alias")
            selected_alias = aliases[0]
            projected_row = {**source_row, "aliases": [selected_alias]}
            projection = {**snapshot, "co_leaders": [projected_row], "pending": []}
            summary["row"] = {
                "projection": "one-page visual projection of first real co-leader and its first published alias",
                "selected_alias_is_original_first_alias": projected_row["aliases"][0] == aliases[0],
                "fixed_reference_score": snapshot["reference_score"],
                "formula_score": source_row["formula_dps"],
                "phase": snapshot["phase"],
                "family_sha256": _canonical(source_row),
                "alias_tuple_key_sha256": _sha(selected_alias["tuple_key"].encode("utf-8")),
                "witness45_sha256": _canonical(source_row["witness45"]),
                "witness45_mains": source_row["witness45"]["Mains"],
                "allocation_main_stats_sha256": _canonical([row["main_stats"] for row in source_row["allocations"]]),
                "only_projection_changes": ["retain first co-leader", "retain its first actual alias", "omit other rows and aliases from this visual-only page"],
            }

            from localization import set_language
            import inspect
            kwargs = {"persist": False} if "persist" in inspect.signature(set_language).parameters else {}
            set_language("ru", **kwargs)
            from PySide6.QtCore import QSize
            from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontInfo, QPalette, QRawFont
            from PySide6.QtWidgets import QApplication, QWidget
            from PySide6.QtGui import QFontMetrics
            app = QApplication([])
            from ui.utils import ui_palette
            palette = app.palette()
            palette.setColor(QPalette.ColorRole.Window, QColor(ui_palette.UI_BG_APP))
            palette.setColor(QPalette.ColorRole.WindowText, QColor(ui_palette.UI_TEXT_PRIMARY))
            palette.setColor(QPalette.ColorRole.Base, QColor(ui_palette.UI_BG_PANEL))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(ui_palette.UI_BG_PANEL_RAISED))
            palette.setColor(QPalette.ColorRole.Text, QColor(ui_palette.UI_TEXT_PRIMARY))
            palette.setColor(QPalette.ColorRole.Button, QColor(ui_palette.UI_BG_BUTTON))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor(ui_palette.UI_TEXT_PRIMARY))
            app.setPalette(palette)
            summary["palette"] = {
                "source": "ui.utils.ui_palette",
                "roles": {"Window": ui_palette.UI_BG_APP, "WindowText": ui_palette.UI_TEXT_PRIMARY, "Base": ui_palette.UI_BG_PANEL,
                          "AlternateBase": ui_palette.UI_BG_PANEL_RAISED, "Text": ui_palette.UI_TEXT_PRIMARY,
                          "Button": ui_palette.UI_BG_BUTTON, "ButtonText": ui_palette.UI_TEXT_PRIMARY},
            }
            font_database = QFontDatabase()
            family_count_before = len(font_database.families())
            baseline = app.font()
            baseline_probe = _probe(baseline, QFontInfo, QRawFont, QFontMetrics)
            font_record = {"family_count_before": family_count_before, "baseline": baseline_probe, "application_font_loaded": False}
            summary["font"] = font_record
            if not baseline_probe["all_glyphs_supported"]:
                candidates = [Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/Arial.ttf")]
                font_path = next((path for path in candidates if path.is_file()), None)
                if font_path is None:
                    raise FileNotFoundError("neither approved local test font exists")
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
                font_record.update({"font_path": str(font_path), "font_sha256": _sha(font_path.read_bytes()),
                                    "application_font_id": font_id, "application_font_families": list(families)})
                if not families:
                    raise ValueError("Qt could not load the approved application-local font")
                test_font = QFont(baseline)
                test_font.setFamily(families[0])
                if test_font.pointSizeF() <= 0 and test_font.pixelSize() <= 0:
                    test_font.setPointSizeF(9.0)
                    font_record["test_only_missing_size_default_pt"] = 9.0
                try:
                    local_raw = QRawFont(str(font_path), 12.0)
                    font_record["local_file_raw_font"] = {
                        "valid": local_raw.isValid(),
                        "glyphs": {key: bool(local_raw.supportsCharacter(ord(char)))
                                   for key, char in GLYPHS.items()},
                    }
                except Exception as exc:
                    font_record["local_file_raw_font_error"] = f"{type(exc).__name__}: {exc}"
                app.setFont(test_font)
                font_record.update({"application_font_loaded": True, "font_path": str(font_path),
                                    "font_sha256": _sha(font_path.read_bytes()), "application_font_family": families[0]})

            widget_font = app.font()
            final_probe = _probe(widget_font, QFontInfo, QRawFont, QFontMetrics)
            font_record["family_count_after"] = len(font_database.families())
            font_record["render_font"] = final_probe
            summary["font"] = font_record
            if not final_probe["all_glyphs_supported"]:
                font_record["limitation"] = "At least one required glyph or resolution probe failed; render is diagnostic and does not establish readable acceptance."
            summary["scale"] = {
                "qt_qpa_platform": os.environ["QT_QPA_PLATFORM"],
                "qt_scale_factor_override": os.environ.get("QT_SCALE_FACTOR"),
                "gtt_ui_scale_override": os.environ.get("GTT_UI_SCALE"),
                "note": "Offscreen process used Qt's default scale; production monitor-width startup scaling was not exercised.",
            }

            from ui.gcsim_browser import theory_result
            from ui.gcsim_browser.optimizer_result import CompactOptimizerArtifactCard, OptimizerResultBuildsWidget
            pages = theory_result.TheoryResultPages(projection)
            if len(pages) != 1:
                raise ValueError("visual-only projection did not produce exactly one page")
            page = pages[0]
            if page.theory_context.reference != float(snapshot["reference_score"]) or page.formula_dps != str(source_row["formula_dps"]):
                raise ValueError("production page changed the source reference or score")
            if page.rows[0].artifacts[0].main_property_name != theory_result.theory_stat_label(source_row["witness45"]["Mains"][0][0]):
                raise ValueError("first card main does not match the first actual Witness45 main")
            host = QWidget()
            widget = OptimizerResultBuildsWidget(host)
            widget.set_pages(pages)
            widget.ensurePolished()
            widget.layout().activate()
            widget.table.layout().activate()
            app.processEvents()
            if widget._save_buttons or not widget._theory_noncrit_labels:
                raise ValueError("Theory projection has Save controls or lacks noncrit summaries")
            labels = _label_evidence(widget)
            summary["strings"] = labels
            if not labels["utf8_roundtrip_all"] or labels["replacement_character_count"] or not labels["cyrillic_codepoint_count"]:
                raise ValueError("production Russian labels are not intact UTF-8 Cyrillic text")
            size = widget.sizeHint().expandedTo(widget.minimumSizeHint()).expandedTo(widget.minimumSize())
            if size.width() <= 0 or size.height() <= 0:
                raise ValueError("production widget returned an invalid size hint")
            host.resize(size)
            widget.setGeometry(0, 0, size.width(), size.height())
            widget.layout().activate()
            widget.table.layout().activate()
            app.processEvents()
            preview = job / "theory-font-preview.png"
            if not widget.grab().save(str(preview)):
                raise ValueError("offscreen widget grab did not save the one preview")
            summary["preview"] = {"path": str(preview), "bytes": preview.stat().st_size,
                                  "widget_size_px": [widget.width(), widget.height()],
                                  "device_pixel_ratio": widget.devicePixelRatioF(), "physical_show_calls": 0,
                                  "catalog_icon_fallback": "No selected-team/catalog icon context was supplied; wire-key/flexible-piece fallback is expected."}
            summary["row"].update({"page_total_in_projection": len(pages), "page_total_label_is_projection_only": True,
                                   "card_count": len(widget.findChildren(CompactOptimizerArtifactCard)),
                                   "save_button_count": len(widget._save_buttons),
                                   "noncrit_label_count": len(widget._theory_noncrit_labels)})
            summary["guards"] = {"gzip_reads": 1, "copy_theory_snapshot_calls": 0, "family_index_rows": 1,
                                  "pending_index_rows": 0, "engine_calls": 0, "go_builds": 0,
                                  "database_calls": 0, "desktop_capture_calls": 0, "app_shell_instances": 0,
                                  "main_writes": 0, "account_or_runtime_writes": 0}
            if _canonical(snapshot) != original_hash:
                raise ValueError("full source snapshot changed while making its display projection")
            summary["row"]["source_snapshot_unchanged"] = True
            summary["status"] = "preview_ready"
            print("PREVIEW " + json.dumps({"path": summary["preview"]["path"], "size": summary["preview"]["widget_size_px"],
                  "font": final_probe["resolved_family"], "font_glyphs": final_probe["all_glyphs_supported"],
                  "strings": {"replacement_characters": labels["replacement_character_count"], "cyrillic_codepoints": labels["cyrillic_codepoint_count"],
                              "utf8_roundtrip": labels["utf8_roundtrip_all"]}}, ensure_ascii=False, separators=(",", ":")), flush=True)
            _wait_for_release()

        summary["cleanup"] = {"managed_cleanup_pass": bool(managed and managed.get("cleaned")),
                              "removed_bytes": managed.get("removed_bytes", 0) if managed else 0,
                              "job_root_empty": not job_root.exists() or not any(job_root.iterdir())}
        if not summary["cleanup"]["managed_cleanup_pass"] or not summary["cleanup"]["job_root_empty"]:
            raise ValueError("managed preview cleanup did not complete")
        pins_after = package.pins(repo, main, initial)
        summary["target"].update({"pins_after_sha256": _canonical(pins_after), "pins_unchanged": pins_before == pins_after})
        if pins_before != pins_after:
            raise ValueError("target/runtime pins changed during font review")
        summary["status"] = "pass"
        return summary, 0
    except BaseException as exc:
        summary["status"] = "fail"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        summary["cleanup"] = {"managed_cleanup_pass": bool(managed and managed.get("cleaned")),
                              "removed_bytes": managed.get("removed_bytes", 0) if managed else 0,
                              "cleanup_error": managed.get("cleanup_error") if managed else None,
                              "job_root_empty": not job_root.exists() or not any(job_root.iterdir())}
        try:
            pins_after = package.pins(repo, main, initial)
            summary["target"].update({"pins_after_sha256": _canonical(pins_after), "pins_unchanged": pins_before == pins_after})
        except BaseException as pin_error:
            summary["target"]["pins_after_error"] = f"{type(pin_error).__name__}: {pin_error}"
        return summary, 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--main", type=Path, required=True)
    args = parser.parse_args()
    summary, status = run(args.repo, args.main)
    print("FINAL " + json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")), flush=True)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
