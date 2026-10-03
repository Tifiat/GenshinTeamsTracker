"""Bounded source-copy probe of direct n=1 set captures on a saved Chasca run.

Run only inside managed_optimizer_experiment.py. This never installs an engine,
changes the product route, or treats one seed as All Sets response acceptance.
Four captures are the hard limit: saved neutral control plus three 4p changes.
The source-copy Go helper measures the actual one-member formula compiler; its
build time is separately recorded and never counted as per-capture compile time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.managed_optimizer_experiment import owned_job
from tools.experiments.gcsim.parametric_effects.capture_equivalence import (
    canonical_capture, encoded,
)

SAVED_NAME = "all_sets-20260927-212145-2c1cb70d"
SEED = 742031889
CASES = (
    ("neutral", "", "", "control"),
    ("golden_troupe", "furina", "goldentroupe", "tag_or_field_guard"),
    ("emblem", "furina", "emblemofseveredfate", "stat_dependent"),
    ("marechaussee", "furina", "marechausseehunter", "event_dependent"),
)
SLOT_ORDER = ("flower", "plume", "sands", "goblet", "circlet")
GO_TEST = r'''package evaluator

import (
    "encoding/json"
    "fmt"
    "os"
    "sort"
    "testing"
    "time"

    "genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestDirectCaptureProbe(t *testing.T) {
    var input struct {
        Actors []string `json:"actors"`
        SourceSHA string `json:"source_sha"`
        Cases []struct {
            Name string `json:"name"`
            Member string `json:"member"`
            Effects string `json:"effects"`
            ConfigSHA string `json:"config_sha"`
            Seed uint64 `json:"seed"`
        } `json:"cases"`
    }
    data, err := os.ReadFile(os.Getenv("GTT_DIRECT_CAPTURE_MANIFEST"))
    if err != nil { t.Fatal(err) }
    if err := json.Unmarshal(data, &input); err != nil { t.Fatal(err) }
    if len(input.Cases) != 5 || len(input.Actors) != 4 { t.Fatal("bounded case panel required") }
    sorted := append([]string(nil), input.Actors...)
    sort.Strings(sorted)
    for _, item := range input.Cases {
        start := time.Now()
        memberBytes, err := os.ReadFile(item.Member)
        if err != nil { t.Fatal(err) }
        effectBytes, err := os.ReadFile(item.Effects)
        if err != nil { t.Fatal(err) }
        loadMS := float64(time.Since(start)) / float64(time.Millisecond)
        start = time.Now()
        member, err := contracts.DecodeSeedMember(memberBytes)
        if err != nil { t.Fatal(err) }
        var effects contracts.EffectInputsOutput
        if err := json.Unmarshal(effectBytes, &effects); err != nil { t.Fatal(err) }
        decodeMS := float64(time.Since(start)) / float64(time.Millisecond)
        if member.Seed != item.Seed || effects.Seed != fmt.Sprint(item.Seed) ||
           effects.MemberContentSHA256 != contracts.TextSHA256(string(memberBytes)) ||
           effects.ContextSHA256 != item.ConfigSHA || effects.InputConfigSHA256 != item.ConfigSHA ||
           effects.SourceManifestBodySHA256 != input.SourceSHA {
            t.Fatalf("capture binding mismatch: %s", item.Name)
        }
        start = time.Now()
        panel, err := CompileMembers(sorted, []uint64{item.Seed}, []contracts.IRSeedMember{member})
        compileMS := float64(time.Since(start)) / float64(time.Millisecond)
        if err != nil { t.Fatalf("%s: %v", item.Name, err) }
        if panel == nil { t.Fatalf("empty compiled panel: %s", item.Name) }
        row := map[string]any{"name": item.Name, "load_ms": loadMS, "decode_ms": decodeMS,
            "compile_ms": compileMS, "nodes": len(member.Nodes), "channels": len(member.Channels),
            "member_bytes": len(memberBytes), "effect_bytes": len(effectBytes)}
        result, err := json.Marshal(row)
        if err != nil { t.Fatal(err) }
        fmt.Println("DIRECT_CAPTURE_COMPILE " + string(result))
    }
}
'''


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_bytes())


def saved_inputs(saved: Path) -> tuple[dict, dict, Path, bytes, bytes]:
    if saved.name != SAVED_NAME or saved.parent != (ROOT / "data/gcsim/optimizer-go-runs").resolve():
        raise ValueError("Only the named saved Chasca capture is in scope")
    request = read_json(saved / "request.json")
    sources = read_json(saved / "set-sources.json")
    if request["engine"]["artifact_sha256"] != sources["engine_sha256"] or request["engine"]["source_manifest_sha256"] != sources["source_manifest_sha256"]:
        raise ValueError("Saved engine and source envelope differ")
    if len(request["wearers"]) != 4 or len(request["artifacts"]) == 0:
        raise ValueError("Saved inventory is incomplete")
    matches = sorted((saved / "verification/contexts").glob(f"context-*/seed-{SEED}/config.txt"))
    if len(matches) != 1:
        raise ValueError("One exact saved neutral seed is required")
    original = matches[0].parent
    config = matches[0].read_bytes()
    member = (original / "member.json").read_bytes()
    effects = (original / "member.json.effects.json").read_bytes()
    if sha(config) != read_json(original / "capture-request.json")["context_sha256"]:
        raise ValueError("Saved neutral config binding changed")
    if read_json(original / "member.json")["seed"] != SEED:
        raise ValueError("Saved neutral seed changed")
    sidecar = json.loads(effects)
    if sidecar["member_content_sha256"] != sha(member) or sidecar["source_manifest_body_sha256"] != sources["source_manifest_sha256"] or sidecar.get("neutral") is None:
        raise ValueError("Saved neutral evidence is unbound")
    return request, sources, original, member, effects


def four_piece_witness(request: dict, actor: str, set_uid: str) -> list[int]:
    others = {a["artifact_id"] for wearer in request["wearers"] if wearer["wearer_key"] != actor for a in wearer["current_artifacts"]}
    by_slot: dict[str, list[int]] = {}
    for item in request["artifacts"]:
        if item["set_uid"] == set_uid and item["artifact_id"] not in others:
            by_slot.setdefault(item["slot"], []).append(item["artifact_id"])
    available = [slot for slot in SLOT_ORDER if by_slot.get(slot)]
    if len(available) < 4:
        raise ValueError(f"Saved inventory cannot witness four {set_uid} slots")
    return [min(by_slot[slot]) for slot in available[:4]]


def changed_config(neutral: str, actor: str, set_uid: str) -> str:
    if re.search(r'(?m)^\w+ add set=', neutral):
        raise ValueError("Baseline already has an active set")
    anchor = re.compile(rf'(?m)^{re.escape(actor)} add stats [^\r\n]+;$')
    matches = list(anchor.finditer(neutral))
    if len(matches) != 1:
        raise ValueError("Expected one saved actor stat row")
    at = matches[0].start()
    return neutral[:at] + f'{actor} add set="{set_uid}" count=4;\n' + neutral[at:]


def simple_two_piece_sources(sources: dict) -> list[dict]:
    # Only these two source bodies have the simple unconditional stat shape.
    # This is a verified source observation, not a claim about all 2p tiers.
    output = []
    for key, symbol, stat, amount in (
        ("emblemofseveredfate", "ER", "er", "0.20"),
        ("tenacityofthemillelith", "HPP", "hp%", "0.20"),
    ):
        item = next((row for row in sources["items"] if row["key"] == key), None)
        if item is None:
            raise ValueError(f"Missing 2p source: {key}")
        matches = [(name, body) for name, body in item["sources"].items()
                   if f"m[attributes.{symbol}] = {amount}" in body["text"]]
        if len(matches) != 1:
            raise ValueError(f"2p source shape changed: {key}")
        name, body = matches[0]
        text = body["text"]
        if sha(text.encode()) != body["sha256"]:
            raise ValueError(f"2p source bytes changed: {key}")
        segment = text.split("if count >= 2 {", 1)[1].split("if count >= 4 {", 1)[0]
        required = (f"m[attributes.{symbol}] = {amount}", "char.AddStatMod(",
                    f"AffectedStat: attributes.{symbol}", "Amount: func() []float64 {", "return m")
        if not all(token in segment for token in required) or "if " in segment:
            raise ValueError(f"2p source is no longer unconditional: {key}")
        output.append({"set_uid": key, "coordinate": stat, "amount": amount,
                       "source_path": name, "source_sha256": body["sha256"],
                       "scope": "source-only simple stat tier; no capture"})
    return output


def channel_shape(member: dict) -> list[tuple]:
    return [(c["channel_id"], c["kind"], c["actor_key"], c["attack_tag"], c["damage_type"], c["hit_count"]) for c in member["channels"]]


def port_shape(sidecar: dict) -> dict:
    return {
        "effect": [(p["event_id"], p["kind"], p["owner"], p["attack_tag"]) for p in sidecar["effect_inputs"]],
        "resistance": [(p["hit_id"], p["target_key"], p["element"]) for p in sidecar["resistance_inputs"]],
    }


def capture(engine: Path, job: Path, name: str, config: str, source_sha: str, actors: list[str]) -> dict:
    directory = job / name
    directory.mkdir(mode=0o700)
    config_path, request_path, member_path = directory / "config.txt", directory / "capture-request.json", directory / "member.json"
    config_bytes = config.encode("utf-8")
    config_sha = sha(config_bytes)
    request = {"schema_version": 1, "output_mode": "compact_ir_v1", "context_sha256": config_sha,
               "seed": str(SEED), "iterations": 1, "workers": 1, "ignore_burst_energy": True,
               "include_effect_inputs": True}
    config_path.write_bytes(config_bytes)
    request_path.write_text(json.dumps(request, separators=(",", ":")), encoding="utf-8")
    command = [str(engine), "-c", str(config_path), "-out", str(member_path), "-gtt-trace-equation", str(request_path)]
    env = dict(os.environ, GOMAXPROCS="1")
    start = time.perf_counter()
    result = subprocess.run(command, cwd=directory, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    process_ms = 1000 * (time.perf_counter() - start)
    if result.returncode:
        raise RuntimeError(f"{name} compact capture exited {result.returncode}")
    start = time.perf_counter()
    member_bytes = member_path.read_bytes()
    effect_path = Path(str(member_path) + ".effects.json")
    effect_bytes = effect_path.read_bytes()
    if len(member_bytes) > 100_000_000 or len(effect_bytes) > 100_000_000:
        raise ValueError("Capture exceeded the bounded byte envelope")
    member, effects = json.loads(member_bytes), json.loads(effect_bytes)
    decode_ms = 1000 * (time.perf_counter() - start)
    if member["seed"] != SEED or effects["seed"] != str(SEED) or effects["member_content_sha256"] != sha(member_bytes) or effects["context_sha256"] != config_sha or effects["input_config_sha256"] != config_sha or effects["source_manifest_body_sha256"] != source_sha or effects["character_keys"] != actors:
        raise ValueError(f"{name} capture/sidecar binding mismatch")
    return {"name": name, "member": str(member_path), "effects": str(effect_path), "config_sha": config_sha,
            "seed": SEED, "process_ms": process_ms, "python_decode_ms": decode_ms,
            "member_sha256": sha(member_bytes), "effect_sha256": sha(effect_bytes),
            "member_bytes": len(member_bytes), "effect_bytes": len(effect_bytes),
            "member_data": member, "effects_data": effects}


def compile_source_copy(job: Path, actors: list[str], source_sha: str, captures: list[dict]) -> tuple[float, list[dict], str]:
    source = ROOT / "native/gcsim_optimizer"
    copy = job / "native"
    for original in source.rglob("*.go"):
        if original.name.endswith("_test.go"):
            continue
        target = copy / original.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
    for name in ("go.mod", "go.sum"):
        if (source / name).is_file():
            shutil.copy2(source / name, copy / name)
    helper = copy / "internal/evaluator/direct_capture_probe_test.go"
    helper.write_text(GO_TEST, encoding="utf-8")
    manifest = job / "compile-manifest.json"
    manifest.write_text(json.dumps({"actors": actors, "source_sha": source_sha,
                                    "cases": [{k: v for k, v in row.items() if k in {"name", "member", "effects", "config_sha", "seed"}} for row in captures]}), encoding="utf-8")
    go = shutil.which("go") or "C:/Program Files/Go/bin/go.exe"
    if not Path(go).is_file() and shutil.which(go) is None:
        raise RuntimeError("Go toolchain unavailable")
    env = dict(os.environ, GTT_DIRECT_CAPTURE_MANIFEST=str(manifest), GOPROXY="off")
    start = time.perf_counter()
    result = subprocess.run([go, "test", "./internal/evaluator", "-run=^TestDirectCaptureProbe$", "-count=1", "-v", "-timeout=180s"],
                            cwd=copy, env=env, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=240)
    build_and_test_ms = 1000 * (time.perf_counter() - start)
    if result.returncode:
        raise RuntimeError(f"source-copy formula compiler exited {result.returncode}: " + (result.stdout + result.stderr)[-250:])
    rows = [json.loads(line.split("DIRECT_CAPTURE_COMPILE ", 1)[1]) for line in result.stdout.splitlines() if "DIRECT_CAPTURE_COMPILE " in line]
    if len(rows) != len(captures) or [r["name"] for r in rows] != [r["name"] for r in captures]:
        raise ValueError("source-copy compiler did not return all four cases")
    files = sorted(p for p in copy.rglob("*.go") if p.is_file())
    source_sha = sha(b"".join(str(p.relative_to(copy)).encode() + b"\0" + p.read_bytes() for p in files))
    return build_and_test_ms, rows, source_sha


def run_probe(args: argparse.Namespace, job: Path, stage: dict[str, str]) -> None:
    stage["name"] = "saved_inputs"
    saved = args.saved_run.resolve(strict=True)
    receipt = args.receipt.resolve()
    evidence = (ROOT / "docs/optimizer-evidence/2026-09-28-bonus-hypotheses").resolve()
    if receipt.parent != evidence or receipt.exists():
        raise ValueError("Expected a new receipt under the bounded bonus evidence folder")
    request, sources, original, saved_member, saved_effects = saved_inputs(saved)
    stage["name"] = "active_engine_guard"
    from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
    active = load_active_gcsim_optimizer_engine_context()
    engine = Path(request["engine"]["binary_path"]).resolve(strict=True)
    if engine != Path(active.artifact_path).resolve(strict=True) or active.artifact_sha256 != request["engine"]["artifact_sha256"] or sha(engine.read_bytes()) != active.artifact_sha256 or not active.trusted:
        raise ValueError("Saved capture engine is not the trusted active engine")
    installed = ROOT / "native/gcsim_optimizer/gtt-optimizer.exe"
    baseline_receipt = read_json(ROOT / "docs/optimizer-evidence/2026-09-28-preparation-hypotheses/baseline.json")
    installed_sha = baseline_receipt["installed_sha256"]
    if sha(installed.read_bytes()) != installed_sha:
        raise ValueError("Installed optimizer differs from the saved baseline identity")
    if sources["catalog_sha256"] != active.catalog.source_fingerprint:
        raise ValueError("Saved source catalog differs from the active engine")
    two_piece = simple_two_piece_sources(sources)
    names = {item["key"] for item in sources["items"]}
    actors = json.loads(saved_effects)["character_keys"]
    neutral = (original / "config.txt").read_text(encoding="utf-8")
    if len(actors) != 4 or len(CASES) != 4 or sha(neutral.encode()) != sha((original / "config.txt").read_bytes()):
        raise ValueError("Neutral source frame changed")
    stage["name"] = "inventory_cases"
    cases = []
    for name, actor, set_uid, category in CASES:
        witness = []
        if set_uid:
            if set_uid not in names or actor not in actors:
                raise ValueError("Effect is absent from saved source/team")
            witness = four_piece_witness(request, actor, set_uid)
        text = changed_config(neutral, actor, set_uid) if set_uid else neutral
        cases.append({"name": name, "actor": actor, "set_uid": set_uid, "category": category,
                      "inventory_witness_ids": witness, "config": text})
    # The saved neutral seed is retained as a distinct compiler/reference case.
    capture_root = job / "direct-capture"
    capture_root.mkdir(mode=0o700)
    rows = [{"name": "saved_neutral", "member": str(original / "member.json"),
             "effects": str(original / "member.json.effects.json"),
             "config_sha": sha((original / "config.txt").read_bytes()), "seed": SEED}]
    completed = []
    baseline_equal = False
    for item in cases:
        stage["name"] = "capture:" + item["name"]
        result = capture(engine, capture_root, item["name"], item["config"], sources["source_manifest_sha256"], actors)
        result.update({k: item[k] for k in ("actor", "set_uid", "category", "inventory_witness_ids")})
        completed.append(result)
        # Retain compact process cost even if the later compiler control fails.
        stage.setdefault("completed_captures", []).append({k: result[k] for k in
            ("name", "process_ms", "python_decode_ms", "member_bytes", "effect_bytes")})
        rows.append(result)
        if item["name"] == "neutral":
            stage["name"] = "baseline_semantics"
            saved_canonical = canonical_capture(saved_member, saved_effects)
            fresh_canonical = canonical_capture(Path(result["member"]).read_bytes(), Path(result["effects"]).read_bytes())
            baseline_equal = sha(encoded(saved_canonical)) == sha(encoded(fresh_canonical))
            if not baseline_equal:
                raise ValueError("Fresh n=1 baseline differs from the exact saved neutral capture")
    if sha(engine.read_bytes()) != active.artifact_sha256:
        raise RuntimeError("Active engine bytes changed during capture")
    if sha(installed.read_bytes()) != installed_sha:
        raise RuntimeError("Installed optimizer bytes changed during capture")
    stage["name"] = "alignment"
    fresh = completed[0]
    baseline_member, baseline_effects = fresh["member_data"], fresh["effects_data"]
    for result in completed[1:]:
        member, effects = result["member_data"], result["effects_data"]
        result["alignment"] = {
            "duration_equal": member["duration_ms"] == baseline_member["duration_ms"],
            "ordered_channels_equal": channel_shape(member) == channel_shape(baseline_member),
            "effect_port_identity_equal": port_shape(effects)["effect"] == port_shape(baseline_effects)["effect"],
            "resistance_port_identity_equal": port_shape(effects)["resistance"] == port_shape(baseline_effects)["resistance"],
            "topology_sha_equal": member["topology_sha256"] == baseline_member["topology_sha256"],
            "schedule_scope": "channels/port identities only; changed-set event tape is not certified",
        }
    stage["name"] = "source_copy_compile"
    build_ms, compiled, source_copy_sha = compile_source_copy(job, sorted(actors), sources["source_manifest_sha256"], rows)
    by_name = {row["name"]: row for row in compiled}
    for row in completed:
        row["compile"] = by_name[row["name"]]
        del row["member_data"], row["effects_data"], row["member"], row["effects"], row["config_sha"], row["seed"]
    report = {"schema_version": 1, "scope": "saved Chasca one-seed source-copy cost probe; no product acceptance",
              "saved_run": SAVED_NAME, "seed": SEED, "active_engine_sha256": active.artifact_sha256,
              "source_manifest_sha256": sources["source_manifest_sha256"],
              "saved_neutral_semantically_equal": baseline_equal,
              "compiler_source_copy_sha256": source_copy_sha,
              "compiler_build_and_test_ms": build_ms,
              "saved_neutral_compile": by_name["saved_neutral"],
              "source_only_simple_2p": two_piece,
              "captures": completed,
              "note": "Raw artifact stats remain the saved neutral frame; four real inventory IDs witness each 4p, but this isolates effects rather than rendering a physical build. N=1 is not product response acceptance. Conditional/resource 2p tiers require source reasoning, not a static-stat shortcut."}
    stage["name"] = "final_identity"
    after = load_active_gcsim_optimizer_engine_context()
    if (after.engine_id, after.artifact_sha256, after.binding_sha256) != (active.engine_id, active.artifact_sha256, active.binding_sha256):
        raise RuntimeError("Active engine pointer changed during probe")
    if sha(installed.read_bytes()) != installed_sha:
        raise RuntimeError("Installed optimizer bytes changed during probe")
    stage["name"] = "receipt"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with receipt.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print("DIRECT_CAPTURE_RESULT " + json.dumps({"receipt": str(receipt), "same_saved_neutral": baseline_equal,
                                                 "cases": [{"name": r["name"], "process_ms": r["process_ms"],
                                                            "compile_ms": r["compile"]["compile_ms"],
                                                 "alignment": r.get("alignment")} for r in completed]}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--saved-run", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    job = owned_job()
    stage = {"name": "startup"}
    try:
        run_probe(args, job, stage)
    except Exception as exc:
        receipt = args.receipt.resolve()
        evidence = (ROOT / "docs/optimizer-evidence/2026-09-28-bonus-hypotheses").resolve()
        if receipt.parent == evidence and not receipt.exists():
            receipt.parent.mkdir(parents=True, exist_ok=True)
            with receipt.open("x", encoding="utf-8") as output:
                json.dump({"schema_version": 1, "status": "failed", "stage": stage["name"],
                           "failure_type": type(exc).__name__, "message": str(exc)[:500],
                           "completed_captures": stage.get("completed_captures", [])}, output,
                          ensure_ascii=False, indent=2)
        raise


if __name__ == "__main__":
    main()
