"""Paired common-seed Chasca Obsidian/Hunter/VV and CR/CD control."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from run_workspace.gcsim.optimizer_benchmark import (
    GcsimOptimizerDebugTrace,
    write_gcsim_optimizer_debug_trace,
)
from run_workspace.gcsim.optimizer_engine_context import (
    load_active_gcsim_optimizer_engine_context,
)
from run_workspace.gcsim.optimizer_stat_response import (
    GcsimSetResponseChange,
    GcsimStatResponseChange,
    GcsimStatResponseChangeMode,
    GcsimStatResponseIntervention,
    GcsimStatResponseObjective,
    GcsimStatResponseRequest,
    GcsimStatResponseTarget,
    run_gcsim_stat_response,
)
from tools.experiments.gcsim_optimizer_canonical_benchmark import (
    CANONICAL_TARGET_SHA256,
    _canonical_target_payload,
)


CHASCA_SET_KEYS = (
    "obsidiancodex",
    "marechausseehunter",
    "viridescentvenerer",
)
CHASCA_CIRCLET_VALUES = (("cr", 0.311), ("cd", 0.622))
MASTER_SEED = 2026080101


def _neutralize_chasca(config_text: str) -> tuple[str, str]:
    lines = []
    removed_main = ""
    for raw_line in config_text.splitlines():
        line = raw_line.strip()
        if re.match(r"^chasca\s+add\s+set\b", line, re.IGNORECASE):
            continue
        if re.match(
            r"^chasca\s+add\s+stats\s+hp=4780\s+atk=311\b",
            line,
            re.IGNORECASE,
        ):
            match = re.search(r"\s(?P<axis>cr|cd)=(?P<value>0\.311|0\.622);$", line)
            if match is None:
                raise RuntimeError(
                    "Chasca main-stat line lacks a CR/CD circlet"
                )
            removed_main = match.group(0).strip(" ;")
            raw_line = raw_line[: match.start()] + ";"
        lines.append(raw_line)
    if not removed_main:
        raise RuntimeError("Chasca main-stat line was not found")
    neutral = "\n".join(lines).strip() + "\n"
    if re.search(
        r"^chasca\s+add\s+set\b",
        neutral,
        re.IGNORECASE | re.MULTILINE,
    ):
        raise RuntimeError("Chasca set neutralization failed")
    return neutral, removed_main


def _estimate_payload(value) -> dict[str, object]:
    return {
        "count": value.count,
        "mean": value.mean,
        "sample_sd": value.sample_sd,
        "standard_error": value.standard_error,
    }


def _summary_payload(value) -> dict[str, object]:
    return {
        "duration_seconds": _estimate_payload(value.duration_seconds),
        "team_expected_damage": _estimate_payload(
            value.team_expected_damage
        ),
        "team_expected_dps": _estimate_payload(value.team_expected_dps),
        "character_expected_dps": [
            _estimate_payload(item) for item in value.character_expected_dps
        ],
    }


def _observation_payload(value) -> dict[str, object]:
    return {
        "observation_id": value.observation_id,
        "summary": _summary_payload(value.summary),
        "paired_delta": (
            None
            if value.paired_delta is None
            else _summary_payload(value.paired_delta)
        ),
        "samples": [
            {
                "seed": item.seed,
                "duration_frames": item.duration_frames,
                "duration_seconds": item.duration_seconds,
                "team_expected_damage": item.team_expected_damage,
                "team_expected_dps": item.team_expected_dps,
                "character_expected_damage": list(
                    item.character_expected_damage
                ),
                "character_expected_dps": list(item.character_expected_dps),
            }
            for item in value.samples
        ],
    }


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-trace",
        type=Path,
        default=(
            PROJECT_ROOT
            / "debug"
            / "gcsim_optimizer_benchmarks"
            / "canonical-theoretical-4p-trace.json"
        ),
    )
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 1) - 1),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            PROJECT_ROOT
            / "debug"
            / "gcsim_optimizer_benchmarks"
            / "canonical-chasca-controlled-ab-trace.json"
        ),
    )
    args = parser.parse_args()
    if not 1 <= args.iterations <= 1024:
        parser.error("--iterations must be in 1..1024")
    if not 1 <= args.workers <= min(args.iterations, 64):
        parser.error("--workers must be in 1..min(iterations,64)")

    source = json.loads(args.source_trace.read_text(encoding="utf-8"))
    source_outcome = source["validation"]["evaluations"][0][
        "finalist_outcome"
    ]
    optimized_config = source_outcome["optimized_config_text"]
    neutral_config, removed_main = _neutralize_chasca(optimized_config)
    interventions = tuple(
        GcsimStatResponseIntervention(
            intervention_id=f"chasca/{set_key}/{circlet}",
            changes=(
                GcsimSetResponseChange(
                    character_index=1,
                    set_key=set_key,
                    set_count=4,
                ),
                GcsimStatResponseChange(
                    character_index=1,
                    stat=circlet,
                    mode=GcsimStatResponseChangeMode.ADD,
                    value=value,
                ),
            ),
        )
        for set_key in CHASCA_SET_KEYS
        for circlet, value in CHASCA_CIRCLET_VALUES
    )
    context = {
        "kind": "canonical_chasca_controlled_ab",
        "source_trace_identity_sha256": source["trace_identity_sha256"],
        "neutral_config_sha256": hashlib.sha256(
            neutral_config.encode("utf-8")
        ).hexdigest(),
        "target_sha256": CANONICAL_TARGET_SHA256,
        "master_seed": MASTER_SEED,
        "iterations": args.iterations,
        "workers": args.workers,
    }
    request = GcsimStatResponseRequest(
        context_sha256=_canonical_sha256(context),
        objective=GcsimStatResponseObjective.CLEAR_TIME,
        iterations=args.iterations,
        workers=args.workers,
        master_seed=MASTER_SEED,
        baseline_changes=(),
        interventions=interventions,
        ignore_burst_energy=True,
    )
    target_payload = _canonical_target_payload()
    with TemporaryDirectory(prefix="gtt-chasca-control-") as temporary:
        target_path = Path(temporary) / "gtt-wave-scenario.json"
        target_path.write_bytes(target_payload)
        target = GcsimStatResponseTarget(
            objective=GcsimStatResponseObjective.CLEAR_TIME,
            target_sha256=CANONICAL_TARGET_SHA256,
            wave_scenario_path=str(target_path),
        )
        result = run_gcsim_stat_response(
            engine_context=load_active_gcsim_optimizer_engine_context(),
            prepared_config_text=neutral_config,
            target=target,
            request=request,
            timeout_seconds=600.0,
        )

    ranked = sorted(
        (
            {
                "intervention_id": item.observation_id,
                "dps_mean": item.summary.team_expected_dps.mean,
                "dps_se": item.summary.team_expected_dps.standard_error,
                "paired_delta_mean": item.paired_delta.team_expected_dps.mean,
                "paired_delta_se": (
                    item.paired_delta.team_expected_dps.standard_error
                ),
                "chasca_dps_mean": item.summary.character_expected_dps[1].mean,
            }
            for item in result.interventions
        ),
        key=lambda item: (-item["dps_mean"], item["intervention_id"]),
    )
    top_dps = ranked[0]["dps_mean"]
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
        item["percent_of_top_1"] = 100.0 * item["dps_mean"] / top_dps

    payload = {
        "kind": "gcsim_optimizer_chasca_controlled_ab",
        "source_trace_identity_sha256": source["trace_identity_sha256"],
        "source_top_1": source["top_n"][0],
        "control_contract": {
            "fixed_allied_sets_mains_and_substats": True,
            "fixed_chasca_substat_rolls": True,
            "changed_dimensions": ["chasca_4p_set", "chasca_circlet_main"],
            "removed_source_circlet_main": removed_main,
            "common_seed_panel": True,
            "master_seed": MASTER_SEED,
            "iterations_per_variant": args.iterations,
            "workers": args.workers,
        },
        "neutral_config_text": neutral_config,
        "neutral_config_sha256": hashlib.sha256(
            neutral_config.encode("utf-8")
        ).hexdigest(),
        "target_payload_text": target_payload.decode("utf-8"),
        "target_sha256": CANONICAL_TARGET_SHA256,
        "request": request.to_dict(),
        "request_sha256": request.request_sha256,
        "seed_panel_sha256": result.seed_panel_sha256,
        "source": _observation_payload(result.source),
        "baseline": _observation_payload(result.baseline),
        "interventions": [
            _observation_payload(item) for item in result.interventions
        ],
        "ranking": ranked,
    }
    trace = GcsimOptimizerDebugTrace(
        payload=payload,
        trace_identity_sha256=_canonical_sha256(payload),
    )
    destination = write_gcsim_optimizer_debug_trace(trace, args.output)
    print(
        json.dumps(
            {
                "trace_path": str(destination),
                "trace_identity_sha256": trace.trace_identity_sha256,
                "ranking": ranked,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
