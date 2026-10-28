"""Read-only independent checks of retained Stage15 archives and full tables."""
from __future__ import annotations

import argparse
import csv,gzip,hashlib,io,json,math,pathlib


def audit_public_outputs(root: pathlib.Path, receipt_name: str = "validation-06.json") -> dict:
    csv.field_size_limit(8*1024*1024)
    ev=root/"docs/optimizer-evidence/2026-10-11-theory-real-output"
    receipt=json.loads((ev/receipt_name).read_text(encoding="utf-8"))
    assert receipt["status"]=="PASS_REAL_TARGET_FULL_OUTPUT_ONE_TEAM"
    records=receipt["retained_public_files"]
    files={}
    for row in records:
        body=(ev/row["path"]).read_bytes()
        assert len(body)==row["bytes"] and hashlib.sha256(body).hexdigest()==row["sha256"],row["path"]
        if row["path"].endswith(".gz"):
            raw=gzip.decompress(body)
            assert len(raw)==row["raw_bytes"] and hashlib.sha256(raw).hexdigest()==row["raw_sha256"]
            files[row["path"][:-3]]=json.loads(raw)
        else: files[row["path"]]=body.decode("utf-8")
    phases=[]
    stats=("atk","atk_percent","crit_damage","crit_rate","def","def_percent","em","energy_recharge","hp","hp_percent")
    def check_witness(w,allocations):
        for a,allocation in enumerate(allocations):
            units=[0.0]*10
            upgrade=0.0
            for slot,(lines,ups) in enumerate(zip(w["Lines"][a],w["Upgrades"][a])):
                assert len(set(lines))==len(lines)==4
                assert len(ups)==4 and sum(ups)<=5+1e-9
                for coordinate,value in zip(lines,ups):
                    assert 0<=coordinate<10 and stats[coordinate]!=w["Mains"][a][slot]
                    assert value>=0 and abs(value*4-round(value*4))<1e-9
                    units[coordinate]+=1+value
                    upgrade+=value
            assert upgrade==25 and sum(units)==45
            assert [x["stat_key"] for x in allocation["substats"]]==list(stats)
            assert [x["roll_units"] for x in allocation["substats"]]==units
            assert list(allocation["main_stats"][k] for k in ("flower","plume","sands","goblet","circlet"))==w["Mains"][a]
            assert allocation["spent_roll_units"]==45 and allocation["unspent_roll_units"]==0
    for label in ("first","breadth","deep","terminal"):
        snap=files[label+"-snapshot.json"]; archive=files[label+"-archive.json"]
        families={f["family"]:f for f in archive["families"] if f["has_candidate"]}
        assert len(families)==sum(f["has_candidate"] for f in archive["families"])
        best=max(f["score"] for f in families.values())
        assert snap["reference_score"]==best
        published={f["family"]:f for f in snap["co_leaders"]+snap["pending"]}
        assert set(published)==set(families) and len(published)==len(snap["co_leaders"]+snap["pending"])
        co={k for k,f in families.items() if 100*(best-f["score"])/abs(best)<=3+1e-12}
        sensitivity={k for k,f in families.items() if 100*(best-f["score"])/abs(best)<=2+1e-12}
        assert co=={f["family"] for f in snap["co_leaders"]}
        aliases=set()
        for family,stored in families.items():
            shown=published[family]
            assert shown["formula_dps"]==stored["score"] and shown["witness45"]==stored["witness45"]
            assert abs(shown["deficit_percent"]-100*(best-stored["score"])/abs(best))<1e-9
            assert shown["refinement_level"]==stored["refinement_level"]
            source_aliases={x["map_key"]:x["value"] for x in stored["aliases"]}
            output_aliases={x["tuple_key"]:x for x in shown["aliases"]}
            assert source_aliases==output_aliases
            assert len(source_aliases)==len(stored["aliases"]) and len(output_aliases)==len(shown["aliases"])
            assert not aliases.intersection(source_aliases)
            aliases.update(source_aliases)
            check_witness(shown["witness45"],shown["allocations"])
        unavailable={x["map_key"]:x["value"] for x in archive["unavailable"]}
        assert unavailable=={x["tuple_key"]:x for x in snap["unavailable"]}
        visited={x["tuple_key"]:x["family"] for x in archive["visited"]}
        assert len(visited)==len(archive["visited"])
        assert set(visited)==aliases.union(unavailable) and not aliases.intersection(unavailable)
        product=math.prod(map(len,archive["domains"]))
        assert snap["domain_tuples"]==str(product)
        assert snap["unseen_tuples"]==str(product-len(visited))
        assert snap["total_found_families"]==len(families) and snap["total_found_tuples"]==len(aliases)
        assert snap["found_group_families"]==len(co)
        assert snap["found_group_tuples"]==sum(len(families[k]["aliases"]) for k in co)
        assert snap["sensitivity_group_families"]==len(sensitivity)
        assert snap["sensitivity_group_tuples"]==sum(len(families[k]["aliases"]) for k in sensitivity)
        assert snap["snapshot_version"]==archive["version"] and snap["finished_early"]==archive["finished_early"]
        phases.append({k:snap[k] for k in ("phase","snapshot_version","reference_score","total_found_families","total_found_tuples","found_group_families","found_group_tuples","sensitivity_group_families","sensitivity_group_tuples","unseen_tuples","domain_tuples","full_cartesian_covered","source_upper","outer_upper","active_branch_work")})
    table=files["full-table.json"]
    snap=files["terminal-snapshot.json"]
    assert table["source_snapshot"]==snap
    combos=table["combinations"]
    assert len({x["combination_id"] for x in combos})==len(combos)==snap["total_found_tuples"]
    expected={a["tuple_key"]: (f,a) for f in snap["co_leaders"]+snap["pending"] for a in f["aliases"]}
    for c in combos:
        f,a=expected[c["tuple_key"]]
        assert c["source_alias"]==a and c["packages"]==a["packages"] and c["context_sha256"]==a["context_sha256"]
        by_actor={x["wearer_key"]:i for i,x in enumerate(f["allocations"])}
        for actor in c["actors"]:
            i=by_actor[actor["wearer_key"]]
            noncrit={}
            for slot,(lines,ups) in enumerate(zip(f["witness45"]["Lines"][i],f["witness45"]["Upgrades"][i])):
                for coord,value in zip(lines,ups):
                    if stats[coord] not in ("crit_rate","crit_damage") and value:
                        noncrit[stats[coord]]=noncrit.get(stats[coord],0)+value
            assert actor["noncrit_upgrade_units"]==sum(noncrit.values())
            assert actor["noncrit_upgrade_by_stat"]==noncrit
            assert actor["initial_line_units"]==20 and actor["total_upgrade_units"]==25 and actor["total_roll_units"]==45
    csv_rows=list(csv.DictReader(io.StringIO(files["full-table.csv"])))
    tsv=list(csv.DictReader(io.StringIO(files["grouped-options.tsv"]),delimiter="\t"))
    assert len(csv_rows)==len(table["actor_rows"])+len(table["unavailable_actor_rows"])
    expected_csv={(c["combination_id"],a["wearer_key"]):c for c in combos for a in c["actors"]}
    for row in csv_rows:
        if row["publication_state"]=="unavailable": continue
        c=expected_csv[(row["combination_id"],row["wearer_key"])]
        assert json.loads(row["packages_json"])==c["packages"]
        actor=next(a for a in c["actors"] if a["wearer_key"]==row["wearer_key"])
        assert float(row["noncrit_upgrade_units"])==actor["noncrit_upgrade_units"]
        assert json.loads(row["noncrit_upgrade_by_stat_json"])==actor["noncrit_upgrade_by_stat"]
    assert len(tsv)==len(table["grouped_options"])
    reverse_memberships={}
    def signature(wearer,sets,mains,noncrit,total):
        return (wearer,json.dumps(sets,sort_keys=True,ensure_ascii=False),tuple(mains[k] for k in ("sands","goblet","circlet")),json.dumps(noncrit,sort_keys=True),total)
    for c in combos:
        for actor in c["actors"]:
            key=signature(actor["wearer_key"],actor["sets"],actor["table_mains"],actor["noncrit_upgrade_by_stat"],actor["noncrit_upgrade_units"])
            reverse_memberships.setdefault(key,set()).add(c["combination_id"])
    membership_count=0
    seen_options=set()
    for row in tsv:
        key=signature(row["wearer_key"],json.loads(row["sets_json"]),row,json.loads(row["noncrit_upgrade_by_stat_json"]),float(row["noncrit_upgrade_units"]))
        assert key not in seen_options
        seen_options.add(key)
        matches=reverse_memberships[key]
        assert matches==set(json.loads(row["combination_ids_json"]))
        membership_count+=len(matches)
    assert seen_options==set(reverse_memberships)
    assert {(r["combination_id"],r["wearer_key"]) for r in csv_rows if r["publication_state"]!="unavailable"}==set(expected_csv)
    assert membership_count==4*len(combos)
    best_combo=min((c for c in combos if c["family_formula_dps"]==snap["reference_score"]),key=lambda c:c["tuple_key"])
    co_combos=[c for c in combos if c["publication_state"]=="co_leader"]
    co_options={}
    for wearer in ("furina","xilonen","chiori","columbina"):
        options={json.dumps({"sets":a["sets"],"mains":a["table_mains"],"noncrit":a["noncrit_upgrade_by_stat"]},sort_keys=True,ensure_ascii=False)
                 for c in co_combos for a in c["actors"] if a["wearer_key"]==wearer}
        co_options[wearer]=len(options)
    out={"schema_kind":"gtt_theory_real_output_parent_audit_v1","status":"PASS_INDEPENDENT_PUBLIC_ARCHIVE_TABLE_AUDIT",
         "phases":phases,"retained_files":len(records),"retained_bytes":sum(r["bytes"] for r in records),
         "csv_rows":len(csv_rows),"grouped_options":len(tsv),"grouped_memberships":membership_count,
         "all_aliases_preserved":True,"no_cartesian_expansion":True,"noncrit_from_upgrades_only":True,
         "co_leader_options_by_wearer":co_options,"table_summary":table["summary"],"best_complete_combination":best_combo,
         "all_unavailable_preserved":len(snap["unavailable"]),"retention":"until_human_acceptance_or_authorized_consolidation",
         "ordinary_finalists":0,"energy_mode":"infinite","prediction_status":"formula_model_only"}
    return out



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[3])
    parser.add_argument("--receipt", default="validation-06.json")
    args = parser.parse_args()
    print(json.dumps(audit_public_outputs(args.root, args.receipt), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
