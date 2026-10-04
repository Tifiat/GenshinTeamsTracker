"""One cancellable GCSIM job and one retained output directory per PvP seat.

The canonical browser workers still generate configs and interpret engine results.
This owner supplies isolated scratch, cancellation and source-provider lifetime.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import os
from pathlib import Path
import subprocess
import tempfile
from threading import BoundedSemaphore, Event, RLock, Thread
from time import monotonic
from typing import Any, Callable, Mapping, Sequence
from weakref import WeakSet


_RUN_CAPACITY = BoundedSemaphore(2)
_SESSIONS: WeakSet = WeakSet()


def close_pvp_gcsim_sessions() -> None:
    """Reap also cancelled jobs from a match already cleared before app exit."""
    sessions = tuple(_SESSIONS)
    cleanup_error = None
    for session in sessions:
        try:
            session.close()
        except Exception as exc:
            cleanup_error = cleanup_error or exc
    deadline = monotonic() + 5.0
    for session in sessions:
        session.wait_closed(max(0.0, deadline - monotonic()))
    if cleanup_error is not None:
        raise cleanup_error


class PvpCancellableArtifactRunner:
    def __init__(self, cancellation: Event, *, process_factory=None) -> None:
        self.cancellation = cancellation
        self.process_factory = process_factory or subprocess.Popen

    def __call__(self, command: Sequence[str], cwd: Path, env: Mapping[str, str],
                 timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        if self.cancellation.is_set():
            raise OSError("PvP GCSIM run cancelled.")
        process = self.process_factory(
            list(command), cwd=str(cwd), env=dict(env), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        started = monotonic()
        try:
            while True:
                if self.cancellation.is_set():
                    raise OSError("PvP GCSIM run cancelled.")
                remaining = timeout_seconds - (monotonic() - started)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(list(command), timeout_seconds)
                try:
                    stdout, stderr = process.communicate(timeout=min(0.1, remaining))
                    return subprocess.CompletedProcess(list(command), process.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if process.poll() is None:
                process.kill()
            # Reap the owned process and drain pipes before scratch/source cleanup.
            process.communicate()


@dataclass(frozen=True, slots=True)
class PvpGcsimJobResult:
    generation: int
    request: Any
    batch: bool
    payload: dict[str, Any]


class PvpGcsimRunSession:
    def __init__(self, *, provider: Any) -> None:
        self.provider = provider
        self._lock = RLock()
        self._cancel = Event()
        self._busy = False
        self._closed = False
        self._discard = False
        self._temporary: Any = None
        self._result: PvpGcsimJobResult | None = None
        self._thread: Thread | None = None
        _SESSIONS.add(self)

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy

    @property
    def output_root(self) -> Path | None:
        with self._lock:
            return Path(self._temporary.name) if self._temporary is not None else None

    def start(self, request: Any, *, generation: int, batch: bool,
              executor: Callable[..., dict[str, Any]]) -> bool:
        with self._lock:
            if self._closed or self._busy:
                return False
            self._cleanup()
            if not _RUN_CAPACITY.acquire(blocking=False):
                return False
            retain = getattr(self.provider, "retain_runtime", None)
            release = lambda: None
            try:
                release = retain() if callable(retain) else release
                self._temporary = tempfile.TemporaryDirectory(prefix="gtt-pvp-gcsim-run-")
                request = replace(request, selected_team=deepcopy(request.selected_team),
                                  run_root=self._temporary.name)
                self._cancel = Event()
                self._discard = False
                self._result = None
                self._busy = True
                self._thread = Thread(
                    target=self._execute, args=(request, generation, batch, executor, release),
                    name="pvp-gcsim-seat", daemon=True,
                )
                self._thread.start()
            except Exception:
                self._busy = False
                try:
                    self._cleanup()
                finally:
                    try:
                        release()
                    finally:
                        _RUN_CAPACITY.release()
                raise
            return True

    def _execute(self, request: Any, generation: int, batch: bool,
                 executor: Callable[..., dict[str, Any]], release: Callable[[], None]) -> None:
        try:
            payload = dict(executor(request, artifact_runner=PvpCancellableArtifactRunner(self._cancel),
                                    cancel_requested=self._cancel.is_set))
        except Exception as exc:
            payload = {"success": False, "error": str(exc), "error_category": "gcsim_runtime_error"}
        finally:
            try:
                release()
            except Exception as exc:
                payload = {"success": False, "error": str(exc), "error_category": "cleanup_failed"}
        with self._lock:
            if self._cancel.is_set():
                payload = {"success": False, "status": "cancelled", "error_category": "cancelled"}
            if self._closed or self._discard:
                try:
                    self._cleanup()
                except Exception as exc:
                    payload = {"success": False, "error": str(exc), "error_category": "cleanup_failed"}
            if not self._closed:
                self._result = PvpGcsimJobResult(generation, request, batch, dict(payload))
            self._busy = False
            _RUN_CAPACITY.release()

    def take_result(self) -> PvpGcsimJobResult | None:
        with self._lock:
            result, self._result = self._result, None
            return result

    def cancel(self) -> None:
        with self._lock:
            self._cancel.set()
            self._discard = True
            if not self._busy:
                self._result = None
                self._cleanup()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._cancel.set()
            self._result = None
            if not self._busy:
                self._cleanup()

    def wait_closed(self, timeout: float = 5.0) -> None:
        """Application shutdown may wait briefly after requesting cancellation."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _cleanup(self) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None
