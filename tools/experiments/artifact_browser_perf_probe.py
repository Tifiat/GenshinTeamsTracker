"""Bounded offscreen first-open probe; no live DB writes or retained raw data.

Each invocation snapshots the calling checkout's DB through SQLite backup and
uses managed scratch for it, History and existing browser PNG caches. The job
is removed on success or failure. Output contains timing/counts, not SQL/rows.
Run fresh processes for comparisons; this measures UI construction, not clicks.
"""
from __future__ import annotations

import argparse
import cProfile
import json
import inspect
import os
from pathlib import Path
import pstats
import re
import sqlite3
import sys
import time
import textwrap
from collections import Counter
from contextlib import ExitStack, closing
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["GTT_PERF_LOG"] = "0"

from tools.managed_optimizer_experiment import managed_scratch


def _expand_snapshot(conn, *, artifact_factor: int, preset_factor: int) -> None:
    """Repeat source rows only inside an owned fixture; never invent imports."""
    conn.row_factory = sqlite3.Row

    def read(table):
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]

    def insert(table, rows):
        if not rows:
            return
        columns = list(rows[0])
        conn.executemany(
            f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            [tuple(row[column] for column in columns) for row in rows],
        )

    artifacts = read("artifacts")
    children = {table: read(table) for table in ("artifact_substats", "artifact_tag_links")}
    artifact_stride = max((row["id"] for row in artifacts), default=0)
    for replica in range(1, artifact_factor):
        offset = artifact_stride * replica
        insert("artifacts", [dict(row, id=row["id"] + offset,
                                  fingerprint=f"perf-fixture:{replica}:{row['id']}")
                             for row in artifacts])
        for table, rows in children.items():
            insert(table, [dict(row, artifact_id=row["artifact_id"] + offset) for row in rows])

    builds = read("artifact_builds")
    build_children = {table: read(table) for table in (
        "artifact_build_slots", "artifact_build_targets", "artifact_build_gcsim_targets",
    )}
    build_stride = max((row["id"] for row in builds), default=0)
    for replica in range(1, preset_factor):
        offset = build_stride * replica
        insert("artifact_builds", [dict(row, id=row["id"] + offset) for row in builds])
        for table, rows in build_children.items():
            insert(table, [dict(row, build_id=row["build_id"] + offset) for row in rows])
    conn.commit()
    if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise AssertionError("Expanded fixture violates a foreign key")


def run(profile_enabled: bool, *, artifact_factor: int = 1, preset_factor: int = 1,
        actions: bool = False, reference_child_show: bool = False) -> dict:
    from PySide6.QtWidgets import QApplication
    from ui.app_shell import LeftWorkspaceHost
    from ui.artifact_browser import window as browser_module
    from ui.artifact_browser import queries as queries_module
    from ui.utils import pixmap_utils

    app = QApplication.instance() or QApplication([])
    sql_counts = Counter()
    measured = False
    connection_count = 0
    method_counts = Counter()
    method_seconds = Counter()
    original_connect = sqlite3.connect

    def traced_connect(*args, **kwargs):
        nonlocal connection_count
        database = args[0] if args else kwargs.get("database")
        if database != ":memory:" and Path(database).resolve() != snapshot.resolve():
            raise AssertionError("Probe attempted a connection outside its owned snapshot")
        conn = original_connect(*args, **kwargs)
        if measured:
            connection_count += 1
        def trace(statement):
            if measured:
                operation = statement.lstrip().split(None, 1)[0].upper()
                sql_counts[operation] += 1
                table = re.search(r"\b(?:FROM|INTO|UPDATE)\s+([a-zA-Z_][a-zA-Z_0-9]*)", statement, re.I)
                if table:
                    sql_counts[f"{operation}:{table.group(1)}"] += 1
        conn.set_trace_callback(trace)
        return conn

    def timed(original, name):
        def wrapper(*args, **kwargs):
            if not measured:
                return original(*args, **kwargs)
            start = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                method_counts[name] += 1
                method_seconds[name] += time.perf_counter() - start
        return wrapper

    with managed_scratch() as scratch, ExitStack() as patches:
        snapshot = scratch / "artifacts.db"
        with closing(original_connect((ROOT / "data/artifacts.db").as_uri() + "?mode=ro", uri=True)) as source:
            with closing(original_connect(snapshot)) as destination:
                source.backup(destination)
        with closing(original_connect(snapshot)) as conn:
            _expand_snapshot(conn, artifact_factor=artifact_factor, preset_factor=preset_factor)
            counts = {table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                      for table in ("artifacts", "artifact_builds", "account_characters")}
            target = conn.execute(
                "SELECT targets.character_id, chars.name FROM artifact_build_targets AS targets "
                "JOIN account_characters AS chars ON chars.character_id=targets.character_id "
                "WHERE targets.target_type='character' GROUP BY targets.character_id "
                "ORDER BY count(*) DESC, targets.character_id LIMIT 1"
            ).fetchone()
            alternate = conn.execute(
                "SELECT character_id, name FROM account_characters WHERE character_id != ? "
                "ORDER BY character_id LIMIT 1", (target[0] if target else -1,),
            ).fetchone()
        patches.enter_context(patch("sqlite3.connect", new=traced_connect))
        for constant in ("BUILD_ROW_BONUS_CACHE_DIR", "BUILD_TARGET_PREVIEW_ICON_CACHE_DIR", "BUILD_TARGET_PREVIEW_STRIP_CACHE_DIR"):
            patches.enter_context(patch.object(browser_module, constant, new=scratch / constant))
        cls = browser_module.ArtifactBrowserWindow
        if reference_child_show:
            # A memory-only comparison with the previous redundant child-show loop.
            source = textwrap.dedent(inspect.getsource(cls.refresh_build_preset_list))
            needle = "        row.show()\n"
            if source.count(needle) != 1:
                raise AssertionError("Reference refresh shape changed")
            source = source.replace(needle, needle +
                                    "        for child in row.findChildren(QWidget):\n            child.show()\n")
            namespace = dict(vars(browser_module))
            exec(compile(source, "<previous-child-show>", "exec"), namespace)
            patches.enter_context(patch.object(cls, "refresh_build_preset_list", new=namespace["refresh_build_preset_list"]))
        for name in ("__init__", "load_build_target_items", "refresh_build_target_list", "_make_build_target_button",
                     "load_build_presets", "refresh_build_preset_list", "_make_build_preset_row",
                     "update_build_panel", "apply_current_filters", "_refresh_applied_build_preset",
                     "_current_equipment_slots_for_operation_target", "update_build_summary",
                     "refresh_current_equipment_markers"):
            patches.enter_context(patch.object(cls, name, new=timed(getattr(cls, name), name)))
        for name in ("load_artifact_browser_store_data", "_fetch_artifacts", "_load_substats", "_load_tags"):
            patches.enter_context(patch.object(queries_module, name, new=timed(getattr(queries_module, name), name)))
        patches.enter_context(patch.object(pixmap_utils, "trim_transparent_pixmap", new=timed(pixmap_utils.trim_transparent_pixmap, "trim_transparent_pixmap")))
        host = LeftWorkspaceHost(artifact_db_path=snapshot, history_snapshot_root=scratch / "history")
        if target:
            host.set_artifact_right_panel_operation_target({"character_id": target[0], "character_name": target[1]})
        host.resize(1250, 800)
        host.show()
        app.processEvents()
        profiler = cProfile.Profile() if profile_enabled else None
        try:
            measured = True
            start = time.perf_counter()
            if profiler:
                profiler.enable()
            host.show_artifact_browser_workspace()
            construction_ms = (time.perf_counter() - start) * 1000
            app.processEvents()
            elapsed_ms = (time.perf_counter() - start) * 1000
            if profiler:
                profiler.disable()
            measured = False
            result = {
                "profiled": profile_enabled,
                "construction_ms": round(construction_ms, 3), "first_open_ms": round(elapsed_ms, 3),
                "inventory_counts": counts,
                "fixture_factors": {"artifacts": artifact_factor, "presets": preset_factor},
                "reference_child_show": reference_child_show,
                "connections": connection_count, "sql_counts": dict(sql_counts),
                "methods": {name: {"calls": method_counts[name], "total_ms": round(seconds * 1000, 3)}
                            for name, seconds in method_seconds.items()},
            }
            if profiler:
                stats = pstats.Stats(profiler)
                functions = sorted(stats.stats.items(), key=lambda item: item[1][3], reverse=True)[:35]
                result["profile_top"] = [
                    {"function": f"{Path(key[0]).name}:{key[1]}:{key[2]}", "calls": value[1],
                     "self_ms": round(value[2]*1000, 3), "cumulative_ms": round(value[3]*1000, 3)}
                    for key, value in functions
                ]
            if actions:
                browser = host.ensure_artifact_browser_workspace()
                # Explicit conflict consent applies only to this disposable DB.
                patches.enter_context(patch.object(cls, "confirm_preset_equipment_conflicts", new=lambda *args: True))
                phases = {}

                def phase(name, callback):
                    nonlocal measured, connection_count
                    sql_counts.clear()
                    method_counts.clear()
                    method_seconds.clear()
                    connection_count = 0
                    measured = True
                    started = time.perf_counter()
                    action_profile = cProfile.Profile() if profile_enabled else None
                    try:
                        if action_profile:
                            action_profile.enable()
                        callback()
                        synchronous_ms = (time.perf_counter() - started) * 1000
                        app.processEvents()
                        elapsed_ms = (time.perf_counter() - started) * 1000
                        if action_profile:
                            action_profile.disable()
                        phases[name] = {
                            "synchronous_ms": round(synchronous_ms, 3),
                            "with_render_ms": round(elapsed_ms, 3),
                            "connections": connection_count, "sql_counts": dict(sql_counts),
                            "methods": {key: {"calls": method_counts[key], "total_ms": round(seconds * 1000, 3)}
                                        for key, seconds in method_seconds.items()},
                        }
                        if action_profile:
                            functions = sorted(pstats.Stats(action_profile).stats.items(),
                                               key=lambda item: item[1][3], reverse=True)[:15]
                            phases[name]["profile_top"] = [
                                {"function": f"{Path(key[0]).name}:{key[1]}:{key[2]}", "calls": value[1],
                                 "self_ms": round(value[2] * 1000, 3), "cumulative_ms": round(value[3] * 1000, 3)}
                                for key, value in functions
                            ]
                    finally:
                        if action_profile:
                            action_profile.disable()
                        measured = False

                if target and alternate:
                    phase("switch_target", lambda: host.set_artifact_right_panel_operation_target(
                        {"character_id": alternate[0], "character_name": alternate[1]}))
                    phase("switch_back", lambda: host.set_artifact_right_panel_operation_target(
                        {"character_id": target[0], "character_name": target[1]}))
                if target:
                    target_key = f"character:{target[0]}"
                    choices = [preset for preset in browser.build_presets
                               if target_key in browser.target_keys_from_targets(preset.get("targets") or [])]
                    if choices:
                        preset_id = max(choices, key=lambda preset: len(preset.get("slots") or []))["id"]
                        phase("preview_preset", lambda: browser.select_build_preset(preset_id))
                        phase("deselect_preset", lambda: browser.select_build_preset(preset_id))
                        browser.select_build_preset(preset_id)
                        app.processEvents()
                        phase("apply_preset", browser.apply_selected_build_preset_to_current_equipment)
                        free_artifact = next((artifact.id for artifact in browser.store.artifacts_by_id.values()
                                              if artifact.pos == browser.current_pos and artifact.owner_character_id is None), None)
                        if free_artifact is not None:
                            phase("equip_artifact", lambda: browser.equip_clicked_artifact(free_artifact))
                result["actions"] = phases
        finally:
            measured = False
            if profiler:
                profiler.disable()
            host.close()
            host.deleteLater()
            app.processEvents()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--artifact-factor", type=int, choices=(1, 4, 8), default=1)
    parser.add_argument("--preset-factor", type=int, choices=(1, 4, 8), default=1)
    parser.add_argument("--actions", action="store_true")
    parser.add_argument("--reference-child-show", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.profile, artifact_factor=args.artifact_factor,
                         preset_factor=args.preset_factor, actions=args.actions,
                         reference_child_show=args.reference_child_show), ensure_ascii=False, indent=2))
