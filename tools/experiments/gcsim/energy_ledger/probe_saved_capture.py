"""Capture and summarize one saved rotation's engine energy ledger."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from tools.managed_optimizer_experiment import managed_scratch
from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256, text_sha256
from run_workspace.gcsim.optimizer_go_selected_inputs import enforce_gcsim_optimizer_mvp_energy_policy


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--optimizer", type=Path)
    parser.add_argument("--verify-controls", action="store_true")
    args = parser.parse_args()
    source = args.source_run.resolve()
    config = source / "prepared-config.txt"
    requests = sorted(source.glob("compact-request-*.json"))
    if not config.is_file() or not requests:
        raise SystemExit("saved config or compact request is missing")

    with managed_scratch() as scratch:
        source_request = json.loads((source / "request.json").read_text(encoding="utf-8"))
        finite_config = enforce_gcsim_optimizer_mvp_energy_policy(
            config.read_text(encoding="utf-8"), ignore_burst_energy=False
        )
        finite_config_path = scratch / "prepared-config.txt"
        finite_config_path.write_text(finite_config, encoding="utf-8")
        trace_context_sha256 = canonical_sha256({
            "kind": "gtt.energy_ledger_probe.v1",
            "prepared_config_sha256": text_sha256(finite_config),
            "seeds": source_request["stochastic"]["seeds"],
        })
        outputs = []
        for index, seed in enumerate(source_request["stochastic"]["seeds"]):
            request = scratch / f"compact-request-{seed}.json"
            request.write_text(json.dumps({
                "schema_version": 1,
                "context_sha256": trace_context_sha256,
                "seed": str(seed),
                "iterations": 1,
                "workers": 1,
                "ignore_burst_energy": True,
                "output_mode": "compact_ir_v1",
            }), encoding="utf-8")
            output = scratch / f"energy-member-{index}.json"
            completed = subprocess.run(
                [
                    str(args.engine.resolve()),
                    "-c",
                    str(finite_config_path),
                    "-out",
                    str(output),
                    "-gtt-trace-equation",
                    str(request),
                ],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr[-4000:])
            outputs.append(output)
        member = json.loads(outputs[0].read_text(encoding="utf-8"))
        ledger = member.get("energy_ledger") or {}
        events = ledger.get("events") or []
        summary = {
            "initial_states": ledger.get("initial_states"),
            "event_count": len(events),
            "burst_count": sum(row.get("kind") == "burst" for row in events),
            "particle_count": sum(row.get("kind") == "particle" for row in events),
            "flat_count": sum(row.get("kind") == "flat" for row in events),
            "first_events": events[:3],
            "uncertainty_codes": ledger.get("uncertainty_codes"),
        }
        if args.optimizer:
            completed = subprocess.run(
                [str(args.optimizer.resolve()), "audit-energy-ledger", str(source / "request.json"), *(str(path) for path in outputs)],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr[-4000:])
            summary["assessment"] = json.loads(completed.stdout)
        if args.verify_controls:
            if not args.optimizer:
                raise RuntimeError("--verify-controls requires --optimizer")
            candidate = args.engine.resolve()
            request_payload = source_request
            request_payload["context"]["prepared_config"] = {
                "text": finite_config, "sha256": text_sha256(finite_config)
            }
            request_payload["context"]["context_sha256"] = canonical_sha256({
                "prepared_config_sha256": request_payload["context"]["prepared_config"]["sha256"],
                "rotation_sha256": request_payload["context"]["rotation"]["sha256"],
                "target_sha256": request_payload["context"]["target"]["sha256"],
            })
            request_payload["context"]["trace_context_sha256"] = trace_context_sha256
            request_payload["engine"]["binary_path"] = str(candidate).replace("\\", "/")
            request_payload["engine"]["artifact_sha256"] = hashlib.sha256(candidate.read_bytes()).hexdigest()
            capabilities = set(request_payload["engine"]["capabilities"])
            capabilities.add("gtt_energy_ledger_v1")
            request_payload["engine"]["capabilities"] = sorted(capabilities)
            request_payload["engine"]["binding_sha256"] = canonical_sha256({
                "kind": "gtt.standalone_engine_binding.v1",
                "artifact_sha256": request_payload["engine"]["artifact_sha256"],
                "source_manifest_sha256": request_payload["engine"]["source_manifest_sha256"],
                "patch_manifest_sha256": request_payload["engine"]["patch_manifest_sha256"],
            })
            request_path = scratch / "request.json"
            request_path.write_text(json.dumps(request_payload), encoding="utf-8")
            compact = {
                "schema_version": 1,
                "schema_kind": "gtt_gcsim_optimizer_compact_ir_v1",
                "request_sha256": canonical_sha256(request_payload),
                "engine_binding_sha256": request_payload["engine"]["binding_sha256"],
                "context_sha256": trace_context_sha256,
                "members": [json.loads(path.read_text(encoding="utf-8")) for path in outputs],
            }
            compact_path = scratch / "compact.json"
            compact_path.write_text(json.dumps(compact), encoding="utf-8")
            verify_root = scratch / "verification"
            completed = subprocess.run(
                [str(args.optimizer.resolve()), "verify-fgbs", str(request_path), str(compact_path), str(verify_root), "controls"],
                cwd=ROOT, text=True, encoding="utf-8", errors="replace",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300, check=False,
            )
            summary["verify_controls"] = {
                "returncode": completed.returncode,
                "stderr_tail": completed.stderr[-2000:],
            }
            if completed.returncode == 0:
                wrapper = json.loads(completed.stdout)
                product = wrapper["product_result"]
                summary["verify_controls"].update({
                    "status": product["status"],
                    "measured_dps": product["measured"]["dps"],
                    "energy": product.get("energy"),
                })
            else:
                failed_rows = []
                for result_path in verify_root.rglob("result.json"):
                    try:
                        result_payload = json.loads(result_path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    details = result_payload.get("character_details") or []
                    failures = (result_payload.get("statistics") or {}).get("failed_actions") or []
                    if len(details) != len(failures):
                        continue
                    failed_rows.append({
                        "characters": [
                            {
                                "name": detail.get("name"),
                                "artifact_er": (detail.get("stats") or [None] * 8)[7],
                                "insufficient_energy": (failure.get("insufficient_energy") or {}).get("max"),
                            }
                            for detail, failure in zip(details, failures)
                        ]
                    })
                summary["verify_controls"]["failed_results"] = failed_rows
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
