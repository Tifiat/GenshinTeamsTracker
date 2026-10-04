"""Observable import work, independent of elapsed time and account contents."""
from copy import deepcopy
import json
import sys
import threading
import time


JOB_PHASES = {
    "projections": ("saving",),
    "assets": ("download", "render", "saving"),
    "references": ("catalogs", "names", "bonuses", "mapping", "saving"),
    "side_icons": ("download",),
    "abyss": ("period", "sources", "hp", "icons", "saving"),
}


class ImportProgress:
    """Publish bounded snapshots; callbacks may arrive from worker threads.

    The bar counts completed work, not predicted remaining seconds. Every job
    retains its own phase/counter so parallel operations cannot replace each
    other's status. Terminal failures are displayed as pending recovery.
    """

    def __init__(self, attempt_id, *, images_only=False, emit=None, clock=time.monotonic):
        self.attempt_id = attempt_id
        self.images_only = images_only
        self._emit = emit or self._print
        self._clock = clock
        self._last_emit = float("-inf")
        self._lock = threading.Lock()
        kinds = ("assets",) if images_only else JOB_PHASES
        self.jobs = {
            kind: {"phase": JOB_PHASES[kind][0], "completed": 0, "total": 0,
                   "fraction": 0.0, "state": "waiting", "steps": {
                       phase: {"completed": 0, "total": 0, "state": "waiting"}
                       for phase in JOB_PHASES[kind]}}
            for kind in kinds
        }

    @staticmethod
    def _print(payload):
        sys.stdout.write("[IMPORT_PROGRESS] " + json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def update(self, kind, phase, completed=0, total=0, *, state="running"):
        with self._lock:
            if kind not in self.jobs or phase not in JOB_PHASES[kind]:
                return
            previous = self.jobs[kind]
            if previous["state"] in {"complete", "pending"}:
                return
            phases = JOB_PHASES[kind]
            # Independent phases may overlap (enemy stats and icons). Keep
            # counters for each instead of letting the latest report erase it.
            step = previous["steps"][phase]
            total = max(0, int(total))
            completed = min(total, max(0, int(completed)))
            if total == step["total"]:
                completed = max(step["completed"], completed)
            previous["steps"][phase] = {
                "completed": completed, "total": total,
                "state": "complete" if ((total and completed == total)
                                         or (not total and phase in {"hp", "icons"})) else "running",
            }
            fraction = sum(item["completed"] / item["total"] if item["total"] else
                           (1 if item["state"] == "complete" else 0)
                           for item in previous["steps"].values()) / len(phases)
            self.jobs[kind] = {
                "phase": phase, "completed": completed, "total": total,
                "fraction": max(previous["fraction"], fraction), "state": state,
                "steps": previous["steps"],
            }
            self._publish(force=phase != previous["phase"] or state != previous["state"])

    def finish(self, kind, *, pending=False):
        with self._lock:
            self.jobs[kind]["state"] = "pending" if pending else "complete"
            self.jobs[kind]["fraction"] = 1.0
            self._publish(force=True)

    def callback(self, kind):
        return lambda phase, completed=0, total=0: self.update(kind, phase, completed, total)

    def _publish(self, *, force=False):
        now = self._clock()
        if not force and now - self._last_emit < 0.1:
            return
        self._last_emit = now
        fraction = sum(job["fraction"] for job in self.jobs.values()) / len(self.jobs)
        payload = {"attempt_id": self.attempt_id, "jobs": deepcopy(self.jobs),
                   "progress": (0.03 if self.images_only else 0.20) +
                               (0.95 if self.images_only else 0.78) * fraction}
        try:
            self._emit(payload)
        except Exception:
            # A broken progress consumer cannot change import correctness.
            pass
