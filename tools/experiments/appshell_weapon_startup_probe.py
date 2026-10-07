"""Manual bounded A/B startup probe using only disposable synthetic account data.

Owns all gtt-startup-* copies through startup_profile.disposable_snapshot; no
account copy, persistent cache or engine execution. Prints a small JSON receipt.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import startup_profile as probe


ASSET_MODULES = (Path("ui/character_assets.py"), Path("hoyolab_export/asset_paths.py"))
ROOT_GUARD = '''
# This probe keeps its disposable copy inside the calling checkout. Permit only
# that exact physical subtree before applying the source-checkout guard.
_original_guarded_path = guarded_path
def guarded_path(value, writing=False):
    path = normal_path(value)
    if path is not None and path.is_relative_to(ROOT):
        return
    _original_guarded_path(value, writing=writing)
'''

EXTRA_HOOK = ROOT_GUARD + '''
_original_patch = patch
def patch(module):
    if module.__name__ == "ui.character_assets" and module.__name__ not in PATCHED:
        PATCHED.add(module.__name__)
        original_connect = module.connect_db
        counts = {"owner_select": 0, "equipment_schema": 0}
        def trace(sql):
            normalized = " ".join(sql.lower().split())
            if normalized.startswith("select") and "from account_character_equipped_weapons" in normalized:
                counts["owner_select"] += 1
            if normalized.startswith("create table if not exists account_character_equipped_weapons"):
                counts["equipment_schema"] += 1
        def connect(*args, **kwargs):
            conn = original_connect(*args, **kwargs)
            conn.set_trace_callback(trace)
            return conn
        module.connect_db = connect
        original_load = module.load_account_weapon_stack_asset_items
        def load(*args, **kwargs):
            before_counts = dict(counts)
            begin = time.perf_counter_ns()
            result = original_load(*args, **kwargs)
            emit("weapon_assets", (time.perf_counter_ns()-begin)/1e6,
                 kind={key: value-before_counts[key] for key, value in counts.items()})
            emit_digest("weapon_payload", result)
            return result
        module.load_account_weapon_stack_asset_items = load
        original_characters = module.load_account_character_asset_items
        def characters(*args, **kwargs):
            begin = time.perf_counter_ns()
            result = original_characters(*args, **kwargs)
            emit("character_assets", (time.perf_counter_ns()-begin)/1e6)
            emit_digest("character_payload", result)
            return result
        module.load_account_character_asset_items = characters
    _original_patch(module)

def emit_digest(label, result):
    import hashlib
    account = ROOT / "data/profiles" / os.environ["GTT_ACCOUNT_PROFILE"]
    def portable(value):
        if isinstance(value, (str, Path)):
            return str(value).replace(str(account), "<account>").replace(str(ROOT), "<project>")
        if isinstance(value, dict):
            return {key: portable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [portable(item) for item in value]
        return value
    payload = json.dumps(portable(result), sort_keys=True).encode()
    emit(label, kind=hashlib.sha256(payload).hexdigest())
'''

TEST_HOOK = ROOT_GUARD + '''
_original_patch = patch
def patch(module):
    # Keep the Qt process prohibition, without replacing widget show/ready.
    if module.__name__ == "PySide6.QtCore":
        _original_patch(module)
'''


def populate_fixture(snapshot: Path, profile_id: str) -> dict:
    """Fixed 78/77 roster; generated 200px RGBA art, no real account material."""
    from PIL import Image, ImageDraw
    account = snapshot / "data/profiles" / profile_id
    relative = Path("assets/hoyolab/startup-fixture")
    directory = account / relative
    directory.mkdir(parents=True)
    manifest = {"characterAssets": [], "weaponAssets": []}
    database = account / "data/artifacts.db"
    with closing(sqlite3.connect(database)) as conn:
        for index in range(78):
            character_id = 90000000 + index
            image_path = relative / f"character_{index}.png"
            _write_image(Image, ImageDraw, account / image_path, index)
            conn.execute("""INSERT INTO account_characters
                (character_id,name,element,rarity,level,constellation,weapon_type,
                 portrait_path,side_icon_path) VALUES (?,?, 'Pyro',5,90,0,1,?,?)""",
                (character_id, f"Synthetic {index:03}", str(image_path), str(image_path)))
            manifest["characterAssets"].append({"character": {"id": character_id},
                "crop": str(image_path), "portrait": str(image_path)})
        for index in range(77):
            image_path = relative / f"weapon_{index}.png"
            _write_image(Image, ImageDraw, account / image_path, index + 78)
            manifest["weaponAssets"].append({"weapon": {"id": 99000 + index},
                "crop": str(image_path), "icon": str(image_path)})
            conn.execute("""INSERT INTO account_weapon_observed_stacks
                (weapon_fingerprint,weapon_id,name,weapon_type,rarity,level,
                 refinement,icon_path,known_count) VALUES (?,?,?,1,5,90,1,?,2)""",
                (f"synthetic-{index}", 99000 + index, f"Weapon {index:03}", str(image_path)))
            conn.execute("""INSERT INTO account_character_equipped_weapons
                (character_id,weapon_fingerprint,updated_at) VALUES (?,?,?)""",
                (90000000 + index, f"synthetic-{index}", "2026-10-07T00:00:00Z"))
        conn.commit()
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    manifest_path = account / "data/hoyolab/crop_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return {"characters": 78, "weapons": 77, "equipped": 77,
            "image_count": 155, "image_size": [200, 200],
            "history": 0, "artifacts": 0, "saved_pvp_decks": 0}


def _write_image(image_module, draw_module, path: Path, index: int) -> None:
    image = image_module.new("RGBA", (200, 200))
    draw = draw_module.Draw(image)
    draw.rectangle((20, 10, 180, 195), fill=(index * 47 % 256, index * 83 % 256, 130, 255))
    image.save(path)


def fixture_tables(snapshot: Path, profile_id: str) -> dict:
    """Inspect only this generated fixture; identify normal startup DB changes."""
    database = snapshot / "data/profiles" / profile_id / "data/artifacts.db"
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        result = {}
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            rows = conn.execute(f"SELECT * FROM {quoted}").fetchall()
            payload = json.dumps(sorted(rows, key=repr), sort_keys=True, default=str).encode()
            result[table] = {"rows": len(rows), "sha256": hashlib.sha256(payload).hexdigest()}
        return result


def run_file(snapshot: Path, python: Path, timeout: int, tests: list[str] | None = None) -> dict:
    hooks = snapshot / "_startup_hook"
    hooks.mkdir()
    (hooks / "sitecustomize.py").write_text(probe.HOOK + (TEST_HOOK if tests else EXTRA_HOOK), encoding="utf-8")
    env = os.environ.copy()
    for key in ("GTT_ACCOUNT_PROFILE", "GTT_PROFILE_ACTION_FILE", "GTT_PROFILE_ACTION_ERROR"):
        env.pop(key, None)
    env.update({"GTT_PROBE_SNAPSHOT": str(snapshot), "GTT_PROBE_SOURCE": str(probe.SOURCE_ROOT),
                "GTT_PROBE_MODE": "detailed", "GTT_PROBE_TARGET": "shell",
                "QT_QPA_PLATFORM": "offscreen", "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": os.pathsep.join((str(hooks), str(snapshot)))})
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    begin = time.perf_counter_ns()
    command = [str(python), "-m", "unittest", *tests] if tests else [str(python), str(snapshot / "ui/app_shell_smoke.py")]
    process = subprocess.Popen(command,
        cwd=snapshot if tests else snapshot / "ui", env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, **options)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        probe._stop_own_tree(process)
        stdout, stderr = process.communicate(timeout=5)
    report = probe.summarize_run("shell", "detailed", process.returncode,
        (time.perf_counter_ns() - begin) / 1e6, stdout, stderr, timed_out, begin)
    if tests:
        report["status"] = "PASS" if process.returncode == 0 and not timed_out and not report["guard_violations"] else "INCOMPLETE"
        report["tests"] = tests
    report["stderr"] = stderr[-1000:]
    return report


def main() -> int:
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", default="77c2645")
    parser.add_argument("--pairs", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--tests", nargs="+", help="Run focused unittest names in a guarded disposable source copy")
    args = parser.parse_args()
    source = probe.SOURCE_ROOT
    python = source / ".venv/Scripts/python.exe"
    if args.tests:
        test_paths = subprocess.run(["git", "ls-files", "tests/*.py", "tests/**/*.py"],
            cwd=source, capture_output=True, text=True, check=True).stdout.splitlines()
        test_paths.append("tests/ui/character_assets/test_asset_loading_batch.py")
        with probe.disposable_snapshot(source) as snapshot:
            probe.copy_product(source, snapshot, probe.tracked_inventory(source) + sorted({Path(p) for p in test_paths}))
            report = run_file(snapshot, python, 60, args.tests)
        report["cleaned"] = not snapshot.exists()
        print(json.dumps(report))
        return 0 if report["status"] == "PASS" else 1
    baseline = {path: subprocess.run(["git", "show", f"{args.baseline_ref}:{path.as_posix()}"],
        cwd=source, capture_output=True, check=True).stdout for path in ASSET_MODULES}
    candidate = {path: (source / path).read_bytes() for path in ASSET_MODULES}
    report = {"baseline_ref": args.baseline_ref, "python": str(python), "runs": [],
              "cache": "fresh processes, no project pyc, uncontrolled/warm OS file cache",
              "data": "synthetic only; no active engine, History, artifacts or saved decks"}
    paths = probe.tracked_inventory(source)
    for index in range(args.pairs):
        order = ("before", "after") if index % 2 == 0 else ("after", "before")
        for variant in order:
            with probe.disposable_snapshot(source) as snapshot:
                probe.copy_product(source, snapshot, paths)
                for path, content in (baseline if variant == "before" else candidate).items():
                    (snapshot / path).write_bytes(content)
                fixture = probe.prepare_fixture(snapshot)
                report["fixture"] = populate_fixture(snapshot, fixture["profile_id"])
                before = probe.fixture_hashes(snapshot, fixture["profile_id"])
                tables_before = fixture_tables(snapshot, fixture["profile_id"])
                staged_bytes = sum(p.stat().st_size for p in snapshot.rglob("*") if p.is_file())
                result = run_file(snapshot, python, 60)
                result.update(variant=variant, staged_bytes=staged_bytes,
                              fixture_changed=before != probe.fixture_hashes(snapshot, fixture["profile_id"]))
                tables_after = fixture_tables(snapshot, fixture["profile_id"])
                result["changed_tables"] = {name: {"before": tables_before.get(name), "after": tables_after.get(name)}
                    for name in tables_before.keys() | tables_after.keys() if tables_before.get(name) != tables_after.get(name)}
                report["runs"].append(result)
            result["cleaned"] = not snapshot.exists()
            print(json.dumps({"variant": variant, "status": result["status"],
                "ready_ms": result["launch_to_ready_ms"], "events": [e for e in result["events"]
                if e["event"] == "weapon_assets"]}), file=sys.stderr, flush=True)
            if result["status"] != "PASS":
                print(json.dumps(report))
                return 1
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
