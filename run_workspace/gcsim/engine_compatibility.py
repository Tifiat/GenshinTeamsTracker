"""Bounded application-bundle checks before installing a built engine.

Fixtures are intentionally tiny compatibility tests, not optimizer search,
account data or gameplay heuristics. Every output is isolated and discarded.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

from .artifact_set_catalog import load_gcsim_artifact_set_catalog

REQUIRED_BUNDLE_CAPABILITIES = frozenset({
    "gtt_engine_marker", "gtt_source_manifest_v1", "gtt_trace_equation_v6",
    "gtt_compact_equation_v1", "gtt_wave_scenario_payload",
    "gtt_effect_inputs_v1",
})
DEFAULT_CONSUMER = Path(__file__).resolve().parents[2] / "native/gcsim_optimizer/gtt-optimizer.exe"
SMOKE_CONFIG = '''bennett char lvl=90/90 cons=0 talent=1,1,1;
bennett add weapon="favoniussword" refine=1 lvl=90/90;
bennett add stats hp=4780 atk=311 atk%=0.466 phys%=0.466 cr=-1 cd=0.50;
options iteration=1 duration=4 workers=1;
target lvl=100 hp=999999999 resist=0.1 radius=2 pos=0,2.4;
active bennett;
bennett attack;
wait(120);
'''


def verify_engine_application_bundle(engine_dir, build, *, optimizer_binary=None, runner=None) -> str:
    """Return a diagnostic on failure; never activate or mutate an installation."""
    if not build.source_manifest_required or not build.source_manifest_ready:
        return "required source-manifest generator/binding is absent"
    missing = sorted(REQUIRED_BUNDLE_CAPABILITIES - set(build.gtt_capabilities))
    if missing or build.gtt_sequential_waves != "true":
        return "required application capabilities missing: " + ", ".join(missing or ["sequential_waves"])
    engine_dir = Path(engine_dir).resolve()
    consumer = Path(optimizer_binary or DEFAULT_CONSUMER).resolve()
    if not consumer.is_file():
        return "standalone optimizer consumer is missing; prepare it before engine activation"
    try:
        catalog = load_gcsim_artifact_set_catalog(engine_dir)
        if not catalog.sets:
            return "application artifact catalog is empty"
        executable = Path(build.artifact_path).resolve()
        before_engine = _digest(executable)
        if before_engine != build.artifact_sha256:
            return "built executable changed before compatibility checks"
        before_consumer = _digest(consumer)
        run = runner or _run
        with tempfile.TemporaryDirectory(prefix="gtt-compat-") as temp:
            root = Path(temp)
            config = root / "config.txt"
            config.write_text(SMOKE_CONFIG, encoding="utf-8")
            ordinary = root / "ordinary.json"
            run([str(executable), "-c", str(config), "-out", str(ordinary)], root)
            stats = json.loads(ordinary.read_text(encoding="utf-8"))["statistics"]
            if stats["iterations"] != 1:
                raise ValueError("ordinary smoke iteration count changed")
            mean = _number(stats["dps"]["mean"])
            _number(stats["dps"]["sd"])
            if mean <= 0:
                raise ValueError("ordinary smoke produced no damage")
            request = root / "request.json"
            request.write_text(json.dumps({"schema_version": 1, "context_sha256": hashlib.sha256(SMOKE_CONFIG.encode()).hexdigest(),
                "ignore_burst_energy": True, "iterations": 1, "workers": 1,
                "output_mode": "compact_ir_v1", "seed": "742031889"}), encoding="utf-8")
            compact = root / "compact.json"
            run([str(executable), "-c", str(config), "-out", str(compact), "-gtt-trace-equation", str(request)], root)
            # Invoke the ACTUAL consumer, not a copied Python version of its IR validator.
            run([str(consumer), "validate-seed-member", str(compact)], root)
            member = json.loads(compact.read_text(encoding="utf-8"))
            if not member["channels"] or not any(c["response_coordinates"] for c in member["channels"]):
                raise ValueError("ordinary smoke formula lost all artifact dependencies")
            if any(b["reason_code"] in {"terminal_formula_baseline_mismatch", "terminal_observation_incomplete"} for b in member["opaque_boundaries"]):
                raise ValueError("ordinary smoke terminal formula is inconsistent")
            seconds = _number(member["duration_ms"]) / 1000
            if seconds <= 0:
                raise ValueError("compact smoke duration is invalid")
            formula_dps = sum(_number(float(c["baseline_damage"])) for c in member["channels"]) / seconds
            if not math.isclose(formula_dps, mean, rel_tol=1e-7, abs_tol=1e-7):
                raise ValueError(f"independent ordinary/compact smoke mismatch: {mean} vs {formula_dps}")
            waves_config = root / "waves.txt"
            waves_config.write_text(SMOKE_CONFIG.replace("duration=4", "duration=10").replace("bennett attack;\nwait(120);", "kill_target(1);\nwait(60);\nkill_target(2);\nwait(60);"), encoding="utf-8")
            scenario = root / "waves.json"
            scenario.write_text(json.dumps({"schema_version": 1, "spawn_policy": "group_clear", "waves": [
                {"targets": [{"type": "dummy", "hp": 1000, "level": 95}]},
                {"targets": [{"type": "dummy", "hp": 1000, "level": 95}]}]}), encoding="utf-8")
            wave_result = root / "wave-result.json"
            run([str(executable), "-c", str(waves_config), "-out", str(wave_result), "-gtt-wave-scenario", str(scenario)], root)
            duration = _number(json.loads(wave_result.read_text(encoding="utf-8"))["statistics"]["duration"]["mean"])
            if not 1 < duration < 3:
                raise ValueError("sequential two-target smoke did not finish at the expected stage")
        if _digest(executable) != before_engine or _digest(consumer) != before_consumer:
            return "engine or optimizer consumer changed during compatibility checks"
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
        return f"application compatibility check failed: {exc}"
    return ""


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("missing or invalid finite nonnegative result number")
    return float(value)


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _run(command, cwd):
    result = subprocess.run(command, cwd=cwd, env={**os.environ, "GOMAXPROCS": "1"},
        capture_output=True, text=True, timeout=60, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise ValueError(f"{Path(command[0]).name} compatibility probe failed: {result.stderr[-1500:]}")
