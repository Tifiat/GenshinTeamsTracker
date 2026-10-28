"""Make small response regressions from real baseline/fresh engine captures.

This does not calculate expected damage. It selects a channel, retains its
ancestor graph and copies the expected number from the changed engine capture.
"""
from pathlib import Path
import argparse
import copy
import json


def slice_member(member, index):
    channel = copy.deepcopy(member["channels"][index])
    nodes = {n["node_id"]: n for n in member["nodes"]}
    keep = set()
    pending = [channel["root_node_id"]]
    while pending:
        key = pending.pop()
        if key in keep:
            continue
        keep.add(key)
        pending.extend(v["node_id"] for v in nodes[key]["inputs"])
    keys = sorted(keep)
    rename = {key: i + 1 for i, key in enumerate(keys)}
    selected = []
    for key in keys:
        node = copy.deepcopy(nodes[key])
        node["node_id"] = rename[key]
        for edge in node["inputs"]:
            edge["node_id"] = rename[edge["node_id"]]
        selected.append(node)
    channel["root_node_id"] = rename[channel["root_node_id"]]
    return dict(seed=member["seed"], duration_ms=member["duration_ms"], topology_sha256=member["topology_sha256"], nodes=selected, channels=[channel], opaque_boundaries=[])


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--matrix", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    load = lambda name: json.loads((args.matrix / name).read_text(encoding="utf-8"))
    jobs = load("jobs.json")
    response = {r["changed"]: r for r in load("response.json")}
    definitions = [
        ("gaming_melt", "gaming", None), ("lunar_crystallize", None, "reaction"),
        ("spread", "kukishinobu", None), ("spread", "tighnari", None),
        ("aggravate", "keqing", None), ("vaporize", "xiangling", None),
        ("burgeon", "thoma", "reaction"), ("burning", "kinich", None),
        ("physical", "freminet", None), ("bloom", "nahida", "direct"),
        ("bloom", "kukishinobu", "reaction"), ("chasca", "chasca", None),
        ("flins_1", None, "reaction"), ("flins_2", None, "reaction"),
    ]
    samples = []
    for case, actor, kind in definitions:
        changes = [j for j in jobs if j["case"] == case and not j["baseline"] and response[j["output"]].get("aligned") and response[j["output"]].get("mismatched_hits") == 0]
        assert changes, case
        base = load(changes[0]["base"])
        fresh = [(j, load(j["output"])) for j in changes]
        eligible = [i for i, c in enumerate(base["channels"]) if (actor is None or c["actor_key"] == actor) and (kind is None or c["kind"] == kind)]
        def influence(i):
            return max(abs(float(f["channels"][i]["baseline_damage"]) - float(base["channels"][i]["baseline_damage"])) for _, f in fresh)
        index = max(eligible, key=influence)
        assert influence(index) > 0, (case, actor, "no demonstrated response")
        samples.append(dict(case="-".join(filter(None, (case, actor, kind))), original_channel=base["channels"][index]["channel_id"], member=slice_member(base, index), checks=[dict(deltas=j["deltas"], engine_expected_damage=f["channels"][index]["baseline_damage"]) for j, f in fresh]))
    args.out.write_text(json.dumps(dict(schema_version=1, scope="Bounded source-derived response slices; fresh engine oracle, not universal dependency coverage", samples=samples), indent=2), encoding="utf-8")
    print(json.dumps(dict(samples=len(samples), nodes=sum(len(s["member"]["nodes"]) for s in samples), bytes=args.out.stat().st_size)))


if __name__ == "__main__":
    main()
