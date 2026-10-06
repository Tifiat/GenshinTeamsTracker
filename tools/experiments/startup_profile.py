"""Bounded, disposable timing of the two real startup entrypoints.

Manual use only. The accepted checkout supplies code/static assets; a temporary
physical copy supplies all mutable state. No saved profile is copied.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Iterator


SOURCE_ROOT = Path(__file__).resolve().parents[2]
PRODUCT_TOP = frozenset({"main.py", "ui", "run_workspace", "hoyolab_export", "localization", "assets", "data"})
BLOCKED_PARTS = frozenset({".git", ".venv", "__pycache__", "profile", "hoyolab", "debug", "docs", "tests", "tools"})
MARKER = "GTT_STARTUP_PROFILE:"


def selected_tracked_paths(lines: list[str]) -> list[Path]:
    """Allow only tracked product code/static files, never account material."""
    result = []
    for line in lines:
        path = Path(line.replace("\\", "/"))
        parts = path.parts
        if not parts or path.is_absolute() or ".." in parts or parts[0] not in PRODUCT_TOP:
            continue
        if any(part.lower() in BLOCKED_PARTS for part in parts[1:-1]):
            continue
        if parts[0] == "assets" and len(parts) > 1 and parts[1].lower() == "hoyolab":
            continue
        if parts[0] == "data" and parts[:2] != ("data", "static"):
            continue
        if path.suffix.lower() not in {".py", ".json", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".txt", ".qss", ".ttf", ".otf", ".ico"}:
            continue
        result.append(path)
    return result


def _is_link(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _assert_plain_path(path: Path, root: Path) -> None:
    if not path.absolute().is_relative_to(root.absolute()):
        raise RuntimeError("Copy path leaves the source root")
    node = path
    while node != root:
        if node.exists() and _is_link(node):
            raise RuntimeError("Source contains a link or junction")
        node = node.parent
    if _is_link(root):
        raise RuntimeError("Source root is a link or junction")


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _database_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for suffix in ("", "-wal", "-shm"):
        item = Path(str(path) + suffix)
        digest.update(suffix.encode("ascii"))
        if item.is_file():
            digest.update(bytes.fromhex(_hash(item)))
    return digest.hexdigest()


def tracked_inventory(source: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(source), "ls-files", "--cached", "-z"],
        capture_output=True, check=True,
    )
    return selected_tracked_paths(result.stdout.decode("utf-8", "surrogateescape").split("\0"))


def copy_product(source: Path, target: Path, paths: list[Path]) -> dict[str, str]:
    if target.exists() and any(target.iterdir()):
        raise RuntimeError("Snapshot target must be empty")
    fingerprints = {}
    for relative in paths:
        original = source / relative
        _assert_plain_path(original, source)
        if not original.is_file():
            raise RuntimeError("Tracked product file is missing")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
        if relative.as_posix() in {"main.py", "ui/app_shell_smoke.py"}:
            fingerprints[relative.as_posix()] = _hash(destination)
    if set(fingerprints) != {"main.py", "ui/app_shell_smoke.py"}:
        raise RuntimeError("Both launcher files are required")
    return fingerprints


def _copy_active_engine(source: Path, target: Path) -> dict[str, str] | None:
    """Copy exactly the source-selected installation, with its original pointer."""
    store = Path("data/gcsim/engines")
    pointer = source / store / "active_engine.json"
    if not pointer.exists():
        return None
    _assert_plain_path(pointer, source)
    state = json.loads(pointer.read_text(encoding="utf-8"))
    engine_id = state.get("active_engine_id")
    if state.get("schema_version") != 1 or not isinstance(engine_id, str) or not engine_id or any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in engine_id
    ) or engine_id in {".", ".."}:
        raise RuntimeError("Invalid active engine pointer")
    installation = source / store / "engines" / engine_id
    _assert_plain_path(installation, source)
    if not installation.is_dir():
        raise RuntimeError("Active engine installation is missing")
    copied_bytes = 0
    for directory, dirs, files in os.walk(installation):
        for name in dirs + files:
            _assert_plain_path(Path(directory) / name, source)
        copied_bytes += sum((Path(directory) / name).stat().st_size for name in files)
        if copied_bytes > 1024 * 1024 * 1024:
            raise RuntimeError("Active engine exceeds the probe's 1 GiB staging limit")
    destination = target / store / "engines" / engine_id
    shutil.copytree(installation, destination)
    target_pointer = target / store / "active_engine.json"
    target_pointer.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pointer, target_pointer)
    manifest = installation / "gtt_engine_manifest.json"
    return {"engine_id": engine_id, "staged_bytes": copied_bytes,
            "pointer_sha256": _hash(pointer),
            "manifest_sha256": _hash(manifest) if manifest.is_file() else "missing"}


def prepare_fixture(snapshot: Path) -> dict[str, str]:
    # These APIs take explicit fixture roots; importing them creates no account.
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))
    previous_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        from run_workspace.account_profiles import create_profile, update_profile_metadata
        from hoyolab_export.artifact_db import init_artifact_db
    finally:
        sys.dont_write_bytecode = previous_bytecode

    profile = create_profile(project_root=snapshot)
    update_profile_metadata(profile["id"], {"uid": "100000001", "server": "os_usa"},
                            imported=True, project_root=snapshot)
    database = snapshot / "data" / "profiles" / profile["id"] / "data" / "artifacts.db"
    init_artifact_db(database)
    registry = snapshot / "data" / "profiles" / "registry.json"
    return {"profile_id": profile["id"], "registry_sha256": _hash(registry),
            "database_sha256": _database_hash(database)}


def fixture_hashes(snapshot: Path, profile_id: str) -> dict[str, str]:
    locations = {
        "registry_sha256": snapshot / "data/profiles/registry.json",
        "database_sha256": snapshot / "data/profiles" / profile_id / "data/artifacts.db",
    }
    return {name: (_database_hash(path) if name == "database_sha256" else _hash(path))
            if path.is_file() else "missing" for name, path in locations.items()}


def _safe_cleanup(root: Path, parent: Path) -> None:
    root = root.absolute()
    parent = parent.absolute()
    if root.parent != parent or not root.name.startswith("gtt-startup-") or _is_link(root):
        raise RuntimeError("Refusing unsafe snapshot cleanup")
    for directory, dirs, files in os.walk(root):
        for name in dirs + files:
            if _is_link(Path(directory) / name):
                raise RuntimeError("Refusing cleanup of linked snapshot node")
    shutil.rmtree(root)


@contextmanager
def disposable_snapshot(parent: Path | None = None) -> Iterator[Path]:
    parent = (parent or Path(tempfile.gettempdir())).resolve()
    if not parent.is_dir() or _is_link(parent):
        raise RuntimeError("Temporary parent must be a plain directory")
    root = Path(tempfile.mkdtemp(prefix="gtt-startup-", dir=parent))
    try:
        yield root
    finally:
        _safe_cleanup(root, parent)


HOOK = r'''"""Temporary startup observer. Deliberately stdlib-only at import."""
import importlib.machinery
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import unquote, urlsplit

ROOT = Path(os.environ["GTT_PROBE_SNAPSHOT"]).resolve()
SOURCE = Path(os.environ["GTT_PROBE_SOURCE"]).resolve()
MODE = os.environ["GTT_PROBE_MODE"]
TARGET = os.environ["GTT_PROBE_TARGET"]
MARKER = "GTT_STARTUP_PROFILE:"
START = time.perf_counter_ns()
EVENTS = []
PATCHED = set()
SLOW_IMPORTS = 0
SUPERVISED_SPAWNS = 0

def emit(name, elapsed_ms=None, kind=None):
    now = time.perf_counter_ns()
    EVENTS.append({"event": name, "pid": os.getpid(), "clock_ns": now,
                   "at_ms": round((now-START)/1e6, 3),
                   **({"duration_ms": round(elapsed_ms, 3)} if elapsed_ms is not None else {}),
                   **({"kind": kind} if kind is not None else {})})
    print(MARKER + json.dumps(EVENTS[-1], separators=(",", ":")), flush=True)

emit("process_start")

def violate(kind):
    emit("guard_violation", kind=kind)
    raise RuntimeError("Startup probe blocked " + kind)

def normal_path(value, sqlite_uri=False):
    try:
        raw = os.fsdecode(value)
    except (TypeError, ValueError):
        return None
    if sqlite_uri:
        if raw == ":memory:":
            return None
        if raw.startswith("file:"):
            parsed = urlsplit(raw)
            if parsed.netloc not in {"", "localhost"}:
                violate("sqlite_uri_host")
            raw = unquote(parsed.path)
            if raw == ":memory:":
                return None
            if os.name == "nt" and len(raw) >= 3 and raw[0] == "/" and raw[2] == ":":
                raw = raw[1:]
    return Path(os.path.normpath(os.path.abspath(raw)))

def guarded_path(value, writing=False):
    path = normal_path(value)
    if path is None:
        return
    if path.is_relative_to(SOURCE):
        if writing:
            violate("source_write")
        relative = path.relative_to(SOURCE).parts
        if relative and relative[0].lower() in {"data", "debug", ".git"}:
            violate("source_private")
        if relative and relative[0].lower() in {"settings.json", "state.json", "runs_history.json"}:
            violate("source_account")
        if len(relative) >= 2 and relative[:2] in {("hoyolab_export", "profile"), ("assets", "hoyolab")}:
            violate("source_auth")

def allowed_child(executable, args, cwd):
    expected = (sys.executable, "-m", "ui.app_shell_smoke", "--profile-child")
    if isinstance(args, (list, tuple)):
        try:
            matched = tuple(os.fsdecode(item) for item in args) == expected
        except (TypeError, ValueError):
            return False
    elif isinstance(args, str) and os.name == "nt":
        matched = args == subprocess.list2cmdline(expected)
    else:
        return False
    if not matched or TARGET != "shell" or "--profile-child" in sys.argv or cwd is None:
        return False
    if normal_path(cwd) != ROOT:
        return False
    return executable is None or normal_path(executable) == normal_path(sys.executable)

def audit(event, args):
    global SUPERVISED_SPAWNS
    if event in {"open", "os.listdir", "os.scandir", "os.mkdir", "os.remove", "os.rmdir", "os.rename", "os.replace", "sqlite3.connect"}:
        if args:
            writing = event in {"os.mkdir", "os.remove", "os.rmdir", "os.rename", "os.replace"}
            if event == "open" and len(args) > 1:
                writing = (isinstance(args[1], str) and any(char in args[1] for char in "wax+")) or (
                    len(args) > 2 and isinstance(args[2], int) and bool(args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)))
            path = normal_path(args[0], sqlite_uri=event == "sqlite3.connect")
            if path is not None:
                guarded_path(path, writing=writing)
        if event in {"os.rename", "os.replace"} and len(args) > 1:
            guarded_path(args[1], writing=True)
    if event in {"socket.connect", "socket.connect_ex", "socket.bind", "socket.sendto",
                 "socket.sendmsg", "socket.getaddrinfo", "socket.gethostbyname",
                 "socket.gethostbyname_ex", "socket.gethostbyaddr", "socket.getnameinfo",
                 "urllib.Request"}:
        violate("network")
    if event == "subprocess.Popen":
        if len(args) < 3 or SUPERVISED_SPAWNS or not allowed_child(args[0], args[1], args[2]):
            violate("process")
        SUPERVISED_SPAWNS += 1
        emit("supervised_child_spawn")
    if event in {"os.system", "os.startfile", "os.exec", "os.spawn"}:
        violate("process")

sys.addaudithook(audit)

def timed_method(cls, name, label):
    method = getattr(cls, name, None)
    if method is None:
        return
    def wrapper(self, *args, **kwargs):
        begin = time.perf_counter_ns()
        try:
            return method(self, *args, **kwargs)
        finally:
            emit(label, (time.perf_counter_ns()-begin)/1e6)
    setattr(cls, name, wrapper)

def ready(window):
    from PySide6.QtCore import QTimer
    def first_tick():
        emit("first_ready_tick")
        QTimer.singleShot(500, window.close)
    QTimer.singleShot(0, first_tick)

def patch(module):
    name = module.__name__
    if name in PATCHED:
        return
    if name == "PySide6.QtCore":
        PATCHED.add(name)
        original = module.QProcess
        class GuardedProcess(original):
            def start(self, *args, **kwargs):
                violate("qt_process")
            def startCommand(self, *args, **kwargs):
                violate("qt_process")
            @staticmethod
            def startDetached(*args, **kwargs):
                violate("qt_process")
            @staticmethod
            def execute(*args, **kwargs):
                violate("qt_process")
        module.QProcess = GuardedProcess
    elif name == "PySide6.QtWidgets":
        PATCHED.add(name)
        if MODE == "detailed":
            original = module.QApplication
            class TimedApplication(original):
                def __init__(self, *args, **kwargs):
                    begin = time.perf_counter_ns()
                    super().__init__(*args, **kwargs)
                    emit("QApplication.__init__", (time.perf_counter_ns()-begin)/1e6)
            module.QApplication = TimedApplication
    elif name == "run_workspace.profile_control":
        PATCHED.add(name)
        if MODE == "detailed":
            for attr in ("profile_supervisor_lock", "profile_operation_lock"):
                original = getattr(module, attr)
                def make(original, label):
                    def wrapped(*args, **kwargs):
                        cm = original(*args, **kwargs)
                        class TimedContext:
                            def __enter__(self):
                                begin = time.perf_counter_ns()
                                try:
                                    return cm.__enter__()
                                finally:
                                    emit(label, (time.perf_counter_ns()-begin)/1e6)
                            def __exit__(self, *exc):
                                return cm.__exit__(*exc)
                        return TimedContext()
                    return wrapped
                setattr(module, attr, make(original, attr + ".acquire"))
    elif name == "run_workspace.profile_context":
        PATCHED.add(name)
        if MODE == "detailed":
            original = module.bootstrap_profile
            def wrapped(*args, **kwargs):
                begin = time.perf_counter_ns()
                try:
                    return original(*args, **kwargs)
                finally:
                    emit("bootstrap_profile", (time.perf_counter_ns()-begin)/1e6)
            module.bootstrap_profile = wrapped
    elif name == "ui.main_window":
        PATCHED.add(name)
        cls = module.App
        original_finish = cls._finish_initial_ui
        def finish(self, *args, **kwargs):
            begin = time.perf_counter_ns()
            result = original_finish(self, *args, **kwargs)
            if MODE == "detailed":
                emit("App._finish_initial_ui", (time.perf_counter_ns()-begin)/1e6)
            ready(self)
            return result
        cls._finish_initial_ui = finish
        if MODE == "detailed":
            for method in ("__init__", "build_left_panel", "build_right_panel", "load_state", "refresh_hoyolab_auth_status", "update_grids"):
                timed_method(cls, method, "App." + method)
            timed_method(cls, "show", "App.show")
    elif name == "ui.app_shell":
        PATCHED.add(name)
        cls = module.AppShell
        original_show = cls.show
        def show(self, *args, **kwargs):
            begin = time.perf_counter_ns()
            result = original_show(self, *args, **kwargs)
            if MODE == "detailed":
                emit("AppShell.show", (time.perf_counter_ns()-begin)/1e6)
            ready(self)
            return result
        cls.show = show
        if MODE == "detailed":
            timed_method(cls, "__init__", "AppShell.__init__")
            timed_method(module.LeftWorkspaceHost, "__init__", "LeftWorkspaceHost.__init__")
            for attr in ("load_active_virtual_roster_catalog", "load_active_virtual_artifact_set_choices"):
                original = getattr(module, attr)
                def make(original, label):
                    def wrapped(*args, **kwargs):
                        begin = time.perf_counter_ns()
                        try:
                            return original(*args, **kwargs)
                        finally:
                            emit(label, (time.perf_counter_ns()-begin)/1e6)
                    return wrapped
                setattr(module, attr, make(original, attr))

def install(loader_type):
    original = loader_type.exec_module
    def exec_module(self, module):
        global SLOW_IMPORTS
        begin = time.perf_counter_ns()
        result = original(self, module)
        elapsed = (time.perf_counter_ns()-begin)/1e6
        name = module.__name__
        major = name in {"ui.main_window", "ui.app_shell", "run_workspace.profile_control",
                         "run_workspace.profile_context", "PySide6.QtWidgets"}
        if MODE == "detailed" and (major or (
            SLOW_IMPORTS < 20 and elapsed >= 25 and name.startswith(
                ("ui.", "run_workspace.", "hoyolab_export.", "PySide6.Qt")))):
            emit("import:" + name, elapsed)
            if not major:
                SLOW_IMPORTS += 1
        patch(module)
        return result
    loader_type.exec_module = exec_module

install(importlib.machinery.SourceFileLoader)
install(importlib.machinery.ExtensionFileLoader)
'''


def parse_markers(output: str) -> tuple[list[dict], list[str]]:
    events, errors = [], []
    for line in output.splitlines():
        if not line.startswith(MARKER):
            continue
        try:
            item = json.loads(line[len(MARKER):])
            if not isinstance(item, dict) or not isinstance(item.get("event"), str) or not isinstance(item.get("pid"), int):
                raise ValueError("invalid event")
            events.append(item)
        except (json.JSONDecodeError, ValueError):
            errors.append("malformed_marker")
    return events, errors


def summarize_run(target: str, mode: str, returncode: int | None, wall_ms: float,
                  stdout: str, stderr: str, timed_out: bool, launch_ns: int = 0) -> dict:
    events, errors = parse_markers(stdout)
    ready = next((e for e in events if e["event"] == "first_ready_tick"), None)
    violations = [e.get("kind", "unknown") for e in events if e["event"] == "guard_violation"]
    starts = {e["pid"] for e in events if e["event"] == "process_start"}
    supervisor = next((e["pid"] for e in events if e["event"] == "supervised_child_spawn"), None)
    chain_ok = bool(ready and ready["pid"] in starts and
                    (target == "legacy" or
                     (supervisor in starts and supervisor != ready["pid"] and len(starts) == 2)))
    status = "PASS" if returncode == 0 and chain_ok and not timed_out and not errors and not violations else "INCOMPLETE"
    return {"target": target, "mode": mode, "status": status, "returncode": returncode,
            "timed_out": timed_out, "wall_ms": round(wall_ms, 3),
            "ready_child_ms": ready.get("at_ms") if ready else None,
            "launch_to_ready_ms": round((ready["clock_ns"]-launch_ns)/1e6, 3)
            if ready and launch_ns and isinstance(ready.get("clock_ns"), int) else None,
            "supervisor_pid": supervisor,
            "ready_pid": ready["pid"] if ready else None,
            "events": events, "marker_errors": errors, "guard_violations": violations,
            "stderr_tail": stderr[-500:] if status != "PASS" else ""}


def _stop_own_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, timeout=10, check=False)
    else:
        process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def run_once(snapshot: Path, hook_dir: Path, source: Path, python: Path,
             target: str, mode: str, timeout: int) -> dict:
    env = os.environ.copy()
    env.pop("GTT_ACCOUNT_PROFILE", None)
    env.pop("GTT_PROFILE_ACTION_FILE", None)
    env.pop("GTT_PROFILE_ACTION_ERROR", None)
    env.update({"GTT_PROBE_SNAPSHOT": str(snapshot), "GTT_PROBE_SOURCE": str(source),
                "GTT_PROBE_MODE": mode, "GTT_PROBE_TARGET": target,
                "QT_QPA_PLATFORM": "offscreen", "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": os.pathsep.join((str(hook_dir), str(snapshot)))})
    command = [str(python), "main.py"] if target == "legacy" else [str(python), "-m", "ui.app_shell_smoke"]
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    begin = time.perf_counter_ns()
    process = subprocess.Popen(command, cwd=snapshot, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, **kwargs)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _stop_own_tree(process)
        stdout, stderr = process.communicate(timeout=5)
    wall_ms = (time.perf_counter_ns()-begin)/1e6
    result = summarize_run(target, mode, process.returncode, wall_ms, stdout, stderr, timed_out, begin)
    result["launcher_pid"] = process.pid
    return result


def main(argv: list[str] | None = None) -> int:
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, default=SOURCE_ROOT / ".venv/Scripts/python.exe")
    parser.add_argument("--target", choices=("legacy", "shell", "both"), default="both")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--with-active-engine", action="store_true")
    args = parser.parse_args(argv)
    if args.timeout < 5 or args.timeout > 180 or args.repeats not in (1, 2, 3):
        parser.error("timeout must be 5..180 seconds and repeats 1..3")
    python = args.python.resolve(strict=True)
    source = SOURCE_ROOT.resolve(strict=True)
    if not source.joinpath("main.py").is_file():
        parser.error("source root has no main.py")
    report = {"source": str(source), "python": str(python), "repeats": args.repeats,
              "runs": [], "guard": "temporary physical source copy; source private paths/network/process guarded"}
    try:
        paths = tracked_inventory(source)
        for target in (("legacy", "shell") if args.target == "both" else (args.target,)):
            for _ in range(args.repeats):
                for mode in ("baseline", "detailed"):
                    with disposable_snapshot() as snapshot:
                        launchers = copy_product(source, snapshot, paths)
                        if "launchers_sha256" not in report:
                            report["launchers_sha256"] = launchers
                        elif report["launchers_sha256"] != launchers:
                            raise RuntimeError("Launcher changed while staging comparison")
                        engine = _copy_active_engine(source, snapshot) if args.with_active_engine else None
                        if "engine" not in report:
                            report["engine"] = engine
                        elif report["engine"] != engine:
                            raise RuntimeError("Active engine changed while staging comparison")
                        fixture = prepare_fixture(snapshot)
                        hook_dir = snapshot / "_startup_hook"
                        hook_dir.mkdir()
                        (hook_dir / "sitecustomize.py").write_text(HOOK, encoding="utf-8")
                        run = run_once(snapshot, hook_dir, source, python, target, mode, args.timeout)
                        after = fixture_hashes(snapshot, fixture["profile_id"])
                        run["fixture_before"] = fixture
                        run["fixture_changed"] = {key: fixture[key] != after[key]
                                                  for key in ("registry_sha256", "database_sha256")}
                        run["fixture_after"] = after
                        report["runs"].append(run)
    except Exception as exc:
        report["status"] = "INCOMPLETE"
        report["error"] = f"{type(exc).__name__}: {exc}"[:500]
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        return 1
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0 if all(run["status"] == "PASS" for run in report["runs"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
