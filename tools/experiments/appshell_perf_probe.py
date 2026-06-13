from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
import time
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TRUE_VALUES = {"1", "true", "yes", "on"}


def _configure_environment() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["GTT_PERF_LOG"] = "1"
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def _ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


def _pump(app: Any, duration_ms: int = 0) -> None:
    deadline = time.perf_counter() + max(0, int(duration_ms)) / 1000.0
    while time.perf_counter() < deadline:
        app.processEvents()
    app.processEvents()


def _format_key_values(prefix: str, **values: Any) -> str:
    parts = []
    for key, value in values.items():
        if isinstance(value, float):
            parts.append(f"{key}={value:.1f}ms")
        else:
            parts.append(f"{key}={value}")
    return f"{prefix} " + " ".join(parts)


class PixelProbe:
    def __init__(self) -> None:
        self.stats_count: dict[str, int] = defaultdict(int)
        self.stats_ms: dict[str, float] = defaultdict(float)
        self.load_count: dict[str, int] = defaultdict(int)
        self.load_ms: dict[str, float] = defaultdict(float)
        self._restore_callbacks: list[Callable[[], None]] = []

    def install(self) -> None:
        from ui.utils import pixel_icon_grid as pig

        original_refresh = pig.PixelIconGrid._refresh_prepared_pixmaps
        original_set_items = pig.PixelIconGrid.set_items
        original_update_item = pig.PixelIconGrid.update_item
        original_load = pig.load_hidpi_pixmap

        def surface(widget: Any) -> str:
            return str(getattr(widget, "_surface", type(widget).__name__))

        def wrapped_load(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            result = original_load(*args, **kwargs)
            elapsed = _ms(start)
            key = (
                f"{kwargs.get('surface') or '-'}:"
                f"hit={int(bool(getattr(result, 'cache_hit', False)))}"
            )
            self.load_count[key] += 1
            self.load_ms[key] += elapsed
            return result

        def wrapped_refresh(instance: Any, *args: Any, **kwargs: Any) -> Any:
            name = surface(instance)
            item_count = len(getattr(instance, "_items", ()))
            start = time.perf_counter()
            result = original_refresh(instance, *args, **kwargs)
            elapsed = _ms(start)
            self.stats_count[f"refresh:{name}"] += 1
            self.stats_count[f"refresh_items:{name}"] += item_count
            self.stats_ms[f"refresh:{name}"] += elapsed
            return result

        def wrapped_set_items(instance: Any, items: Any, *args: Any, **kwargs: Any) -> Any:
            name = surface(instance)
            self.stats_count[f"set_items:{name}"] += 1
            self.stats_count[f"set_items_count:{name}"] += len(items)
            start = time.perf_counter()
            result = original_set_items(instance, items, *args, **kwargs)
            self.stats_ms[f"set_items:{name}"] += _ms(start)
            return result

        def wrapped_update_item(instance: Any, item_id: str, **changes: Any) -> Any:
            name = surface(instance)
            self.stats_count[f"update_item:{name}"] += 1
            self.stats_count[
                f"update_item_changes:{name}:{','.join(sorted(changes))}"
            ] += 1
            start = time.perf_counter()
            result = original_update_item(instance, item_id, **changes)
            self.stats_ms[f"update_item:{name}"] += _ms(start)
            return result

        pig.load_hidpi_pixmap = wrapped_load
        pig.PixelIconGrid._refresh_prepared_pixmaps = wrapped_refresh
        pig.PixelIconGrid.set_items = wrapped_set_items
        pig.PixelIconGrid.update_item = wrapped_update_item

        self._restore_callbacks.extend(
            [
                lambda: setattr(pig, "load_hidpi_pixmap", original_load),
                lambda: setattr(
                    pig.PixelIconGrid,
                    "_refresh_prepared_pixmaps",
                    original_refresh,
                ),
                lambda: setattr(pig.PixelIconGrid, "set_items", original_set_items),
                lambda: setattr(pig.PixelIconGrid, "update_item", original_update_item),
            ]
        )

    def print_summary(self) -> None:
        for key in sorted(self.stats_count):
            if key.startswith(("refresh", "set_items", "update_item")):
                print(
                    _format_key_values(
                        "[PROBE_GRID]",
                        key=key,
                        count=self.stats_count[key],
                        total=self.stats_ms.get(key, 0.0),
                    ),
                    flush=True,
                )
        for key in sorted(self.load_count):
            print(
                _format_key_values(
                    "[PROBE_PIXMAP]",
                    key=key,
                    count=self.load_count[key],
                    total=self.load_ms[key],
                ),
                flush=True,
            )

    def restore(self) -> None:
        for callback in reversed(self._restore_callbacks):
            callback()
        self._restore_callbacks.clear()


class ArtifactTargetProbe:
    def __init__(self) -> None:
        self.module_import_ms = 0.0
        self.button_count = 0
        self.button_ms = 0.0
        self.ensure_count = 0
        self.ensure_ms = 0.0
        self._restore_callbacks: list[Callable[[], None]] = []

    def install(self) -> None:
        start = time.perf_counter()
        module = importlib.import_module("ui.artifact_browser.window")
        self.module_import_ms = _ms(start)
        cls = module.ArtifactBrowserWindow
        original_make = cls._make_build_target_button
        original_ensure = cls._ensure_build_target_buttons

        def wrapped_make(instance: Any, item: dict[str, Any]) -> Any:
            start = time.perf_counter()
            result = original_make(instance, item)
            self.button_count += 1
            self.button_ms += _ms(start)
            return result

        def wrapped_ensure(instance: Any) -> Any:
            start = time.perf_counter()
            result = original_ensure(instance)
            self.ensure_count += 1
            self.ensure_ms += _ms(start)
            return result

        cls._make_build_target_button = wrapped_make
        cls._ensure_build_target_buttons = wrapped_ensure
        self._restore_callbacks.extend(
            [
                lambda: setattr(cls, "_make_build_target_button", original_make),
                lambda: setattr(cls, "_ensure_build_target_buttons", original_ensure),
            ]
        )

    def print_summary(self) -> None:
        print(
            _format_key_values(
                "[PROBE_ARTIFACT_TARGET]",
                module_import=self.module_import_ms,
                buttons=self.button_count,
                button_total=self.button_ms,
                ensure_calls=self.ensure_count,
                ensure_total=self.ensure_ms,
            ),
            flush=True,
        )

    def restore(self) -> None:
        for callback in reversed(self._restore_callbacks):
            callback()
        self._restore_callbacks.clear()


@contextmanager
def installed_probe(probe: Any):
    probe.install()
    try:
        yield probe
    finally:
        probe.restore()


def _run_importtime() -> None:
    command = [
        sys.executable,
        "-X",
        "importtime",
        "-c",
        (
            "import os; "
            "os.environ.setdefault('QT_QPA_PLATFORM','offscreen'); "
            "import ui.app_shell"
        ),
    ]
    process = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    rows: list[tuple[float, float, str]] = []
    for line in process.stderr.splitlines():
        if not line.startswith("import time:"):
            continue
        payload = line.removeprefix("import time:").strip()
        parts = [part.strip() for part in payload.split("|")]
        if len(parts) != 3:
            continue
        try:
            self_ms = int(parts[0]) / 1000.0
            cumulative_ms = int(parts[1]) / 1000.0
        except ValueError:
            continue
        rows.append((cumulative_ms, self_ms, parts[2]))
    for cumulative_ms, self_ms, name in sorted(rows, reverse=True)[:25]:
        print(
            _format_key_values(
                "[PROBE_IMPORT]",
                cumulative=cumulative_ms,
                self=self_ms,
                module=name,
            ),
            flush=True,
        )
    print(f"[PROBE_IMPORT] returncode={process.returncode}", flush=True)


def _make_marker(marker_cls: Any, index: int = 0) -> Any:
    return marker_cls(
        team_index=0,
        slot_index=index % 4,
        slot_number=(index % 4) + 1,
        color="#35d07f",
    )


def _run_app_probe(args: argparse.Namespace) -> None:
    _configure_environment()

    from ui.utils.app_scaling import configure_startup_ui_scale

    scale_start = time.perf_counter()
    configure_startup_ui_scale()
    scale_ms = _ms(scale_start)

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    pixel_probe = PixelProbe()
    pixel_probe.install()
    artifact_probe = ArtifactTargetProbe()
    if args.mode in {"all", "artifact"}:
        artifact_probe.install()

    try:
        import_start = time.perf_counter()
        app_shell = importlib.import_module("ui.app_shell")
        app_shell_import_ms = _ms(import_start)

        construct_start = time.perf_counter()
        shell = app_shell.AppShell()
        construct_ms = _ms(construct_start)
        shell.resize(app_shell.APP_SHELL_MIN_WIDTH, app_shell.APP_SHELL_MIN_HEIGHT)

        show_start = time.perf_counter()
        shell.show()
        _pump(app, args.initial_events_ms)
        show_initial_ms = _ms(show_start)

        artifact_first_ms = 0.0
        artifact_repeat_ms = 0.0
        if args.mode in {"all", "artifact"}:
            first_start = time.perf_counter()
            shell.left_host.show_artifact_browser_workspace()
            _pump(app, args.artifact_events_ms)
            artifact_first_ms = _ms(first_start)

            repeat_start = time.perf_counter()
            shell.left_host.show_character_weapon_workspace()
            _pump(app, 50)
            shell.left_host.show_artifact_browser_workspace()
            _pump(app, 80)
            artifact_repeat_ms = _ms(repeat_start)

        marker_one_ms = 0.0
        marker_all_ms = 0.0
        if args.mode in {"all", "marker"}:
            workspace = shell.left_host.character_weapon_workspace
            ids = list(workspace.char_grid.item_ids())
            if ids:
                marker_start = time.perf_counter()
                workspace.set_character_selection_markers(
                    {ids[0]: _make_marker(app_shell.RosterSelectionMarker)},
                    affected_character_ids={ids[0]},
                )
                _pump(app, 50)
                marker_one_ms = _ms(marker_start)

                markers = {
                    item_id: _make_marker(app_shell.RosterSelectionMarker, index)
                    for index, item_id in enumerate(ids)
                }
                all_start = time.perf_counter()
                workspace.set_character_selection_markers(
                    markers,
                    affected_character_ids=set(ids),
                )
                _pump(app, 50)
                marker_all_ms = _ms(all_start)

        browser = shell.left_host.artifact_browser_workspace
        character_count = shell.left_host.character_weapon_workspace.char_grid.item_count()
        weapon_count = shell.left_host.character_weapon_workspace.weapon_grid.item_count()
        artifact_count = browser.model.rowCount() if browser is not None else 0
        print(
            _format_key_values(
                "[PROBE]",
                scale=scale_ms,
                app_shell_import=app_shell_import_ms,
                construct=construct_ms,
                show_initial=show_initial_ms,
                artifact_first=artifact_first_ms,
                artifact_repeat=artifact_repeat_ms,
                marker_one=marker_one_ms,
                marker_all=marker_all_ms,
                characters=character_count,
                weapons=weapon_count,
                artifacts=artifact_count,
            ),
            flush=True,
        )
        pixel_probe.print_summary()
        artifact_probe.print_summary()
        shell.close()
        _pump(app, 100)
    finally:
        artifact_probe.restore()
        pixel_probe.restore()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure AppShell startup and hot-path performance without mutating app data."
    )
    parser.add_argument(
        "--mode",
        choices=("all", "startup", "artifact", "marker"),
        default="all",
        help="Probe mode. 'all' runs startup, artifact, pixmap, and marker probes.",
    )
    parser.add_argument(
        "--importtime",
        action="store_true",
        help="Also run a separate python -X importtime summary for ui.app_shell.",
    )
    parser.add_argument("--initial-events-ms", type=int, default=350)
    parser.add_argument("--artifact-events-ms", type=int, default=150)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.importtime:
        _configure_environment()
        _run_importtime()
    _run_app_probe(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
