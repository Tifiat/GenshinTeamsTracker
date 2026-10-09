"""Compare editor generation to the selected GCSIM parser, without simulation.

Explicit --engine-root is required. Only public test inputs are used. Go's
ordinary build cache is used; module/network updates are disabled. The helper
does not load a GTT engine executable, evaluator, settings or account database.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from run_workspace.gcsim.rotation_editor import node, parse, write
from run_workspace.gcsim.rotation_editor.semantics import ScheduleChoice, analyze, make_cycle, make_schedule, number, schedule_condition, set_cycle_count
from tests.run_workspace.gcsim.test_rotation_editor import DIALECT, PUBLIC_CASES
from tests.run_workspace.gcsim.test_rotation_conditions import CONDITION_CASES, with_condition
from tests.run_workspace.gcsim.test_rotation_variants import VARIANT_CASES, plan_document
from run_workspace.gcsim.rotation_editor.variants import apply_variant, VariantChoice
from run_workspace.gcsim.rotation_editor.conditions import compile_condition, recognize
from run_workspace.gcsim.rotation_editor.conditions import Condition, make_if
from run_workspace.gcsim.rotation_editor.editing import Selection, insert, move, remove, wrap
from run_workspace.gcsim.rotation_editor.model import action
from run_workspace.gcsim.rotation_editor.readable import render
from tests.run_workspace.gcsim.test_rotation_editor import translator


def user_block_pairs() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Generated blocks plus independently expected constant predicates.

    The upstream parser folds literal arithmetic with its own GCSL constants.
    This checks schedule truth values without invoking a battle evaluator.
    """
    generated, predicates = [], []
    schedules = (
        (ScheduleChoice(), {1, 2, 3, 4, 5, 6}),
        (ScheduleChoice(every=2, first=2), {2, 4, 6}),
        (ScheduleChoice(every=3, first=1), {1, 4}),
        (ScheduleChoice(every=3, first=3), {3, 6}),
        (ScheduleChoice('selected', positions=(1, 4)), {1, 4}),
    )
    body = node('block', items=parse('furina skill, dash, burst;', DIALECT).root.get('items'))
    base = parse('active furina;', DIALECT)
    made = make_cycle(base, 4, body)
    draft = base.replace(base.root.node_id, base.root.changed(items=base.root.get('items') + (made,)))
    generated.append((write(draft), write(draft, preserve=False)))
    for start in (0, 1, 3):
        document = parse(f'active furina; for let i={start}; i<{start+6}; i=i+1 {{ furina skill; }}', DIALECT)
        cycle = next(iter(analyze(document).cycles.values()))
        changed = set_cycle_count(document, cycle.node_id, 8)
        generated.append((write(changed), write(changed, preserve=False)))
        for choice, expected in schedules:
            block = make_schedule(document, cycle.node_id, choice, body)
            changed = document.replace(cycle.body_id, node('block', items=(block,)))
            generated.append((write(changed), write(changed, preserve=False)))
            condition = schedule_condition(cycle, choice)
            for ordinal in range(1, 7):
                # Substitute only the generated counter leaves, not text.
                # Normalize truth through the engine's unary operators: its
                # parsed `true` retains an unused FloatVal unlike folded 1.
                truth = node('unary', operator='!', value=node('unary', operator='!', value=condition))
                expression = document.replace(document.root.node_id, node('document', items=(node('let', name=node('name', value='result'), annotation=None, value=truth),)))
                for item in tuple(expression.root.walk()):
                    if item.kind == 'name' and item.get('value') == cycle.counter:
                        expression = expression.replace(item.node_id, number(start + ordinal - 1))
                actual = write(expression, preserve=False)
                predicates.append((actual, f'let result={int(ordinal in expected)}+0;'))
    return generated, predicates


def condition_variant_pairs() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    generated, truths = [], []
    for choice in VARIANT_CASES:
        document, _ = plan_document(choice)
        code = write(document)
        generated.append((code, write(parse(code, DIALECT), preserve=False)))
    for source, choice in CONDITION_CASES:
        document = with_condition(source)
        block = document.root.get('items')[1]
        changed = document.replace(block.get('condition').node_id, compile_condition(document, choice))
        code = write(changed)
        generated.append((code, write(parse(code, DIALECT), preserve=False)))
    cases = (
        ('.furina.energy >= .furina.energymax', {'furina.energy': '59', 'furina.energymax': '60'}, False),
        ('.furina.energy >= .furina.energymax', {'furina.energy': '60', 'furina.energymax': '60'}, True),
        ('.furina.hpratio < .5', {'furina.hpratio': '.49'}, True),
        ('.furina.hpratio < .5', {'furina.hpratio': '.5'}, False),
        ('!.furina.status.favonius-cd', {'furina.status.favonius-cd': '0'}, True),
        ('!.furina.status.favonius-cd', {'furina.status.favonius-cd': '1'}, False),
        ('.furina.onfield == 0', {'furina.onfield': '1'}, False),
        ('.furina.onfield == 0', {'furina.onfield': '0'}, True),
        ('.furina.burst.ready >= 1', {'furina.burst.ready': '1'}, True),
        ('.furina.burst.ready >= 1', {'furina.burst.ready': '0'}, False),
        ('.chasca.cons < 6', {'chasca.cons': '5'}, True),
        ('.chasca.cons < 6', {'chasca.cons': '6'}, False),
        ('(.furina.onfield || .chasca.nightsoul.state) && .furina.energy >= 60',
         {'furina.onfield': '0', 'chasca.nightsoul.state': '1', 'furina.energy': '60'}, True),
        ('(.furina.onfield || .chasca.nightsoul.state) && .furina.energy >= 60',
         {'furina.onfield': '1', 'chasca.nightsoul.state': '0', 'furina.energy': '59'}, False),
        ('(.furina.onfield || .chasca.nightsoul.state) && .furina.energy >= 60',
         {'furina.onfield': '0', 'chasca.nightsoul.state': '0', 'furina.energy': '60'}, False),
        ('!.furina.ousia', {'furina.ousia': '0'}, True),
        ('!.furina.ousia', {'furina.ousia': '1'}, False),
    )
    for source, fields, expected in cases:
        document = with_condition(source)
        original = document.root.get('items')[1].get('condition')
        choice = recognize(document, original)
        assert choice is not None, source
        for condition in (original, compile_condition(document, choice)):
            truth = node('unary', operator='!', value=node('unary', operator='!', value=condition))
            literal_doc = document.replace(document.root.node_id, node('document', items=(node('let', name=node('name', value='result'), annotation=None, value=truth),)))
            for field in tuple(literal_doc.root.walk()):
                if field.kind == 'field':
                    literal_doc = literal_doc.replace(field.node_id, node('number', value=fields['.'.join(field.get('path'))]))
            truths.append((write(literal_doc, preserve=False), f'let result={int(expected)}+0;'))
    return generated, truths


def structural_pairs() -> list[tuple[str, str]]:
    pairs = []
    source = "active furina; furina skill, dash, burst; chasca skill;"
    document = parse(source, DIALECT)
    dash = document.root.get("items")[1].get("actions")[1]
    pairs.append((write(insert(document, Selection(dash.node_id), action("bennett", "burst"))),
        "active furina; furina skill, dash; bennett burst; furina burst; chasca skill;"))
    pairs.append((write(wrap(document, Selection(dash.node_id), make_if(document, Condition("energy_full", "furina")))),
        "active furina; furina skill; if .furina.energy >= .furina.energymax { furina dash; } furina burst; chasca skill;"))
    pairs.append((write(move(document, Selection(dash.node_id), -1)),
        "active furina; furina dash, skill, burst; chasca skill;"))
    document = parse("active furina; furina swap; furina skill; if .furina.onfield { furina burst; } chasca skill;", DIALECT)
    window = Selection.from_view(render(document, translator()).items[0])
    pairs.append((write(remove(document, window)), "active furina; chasca skill;"))
    pairs.append((write(wrap(document, window, make_if(document, Condition("energy_full", "furina")))),
        "active furina; if .furina.energy >= .furina.energymax { furina swap; furina skill; if .furina.onfield { furina burst; } } chasca skill;"))
    document = parse("active furina; furina skill; chasca burst;", DIALECT)
    selected = document.root.get("items")[1].get("actions")[0]
    pairs.append((write(remove(document, Selection(selected.node_id))), "active furina; chasca burst;"))
    document = parse("active furina; if .furina.onfield { furina skill; } else { chasca skill; }", DIALECT)
    branch = document.root.get("items")[1].get("then")
    pairs.append((write(remove(document, Selection(branch.node_id))),
        "active furina; if .furina.onfield {} else { chasca skill; }"))
    document = parse("active chasca; chasca aim:4;", DIALECT)
    selected = next(item for item in document.root.walk() if item.kind == "action")
    changed = apply_variant(document, selected.node_id, VariantChoice("chasca.nightsoul_aim", 6))
    pairs.append((write(changed), "active chasca; { for let _rotation=1; _rotation<=4; _rotation=_rotation+1 { if !.chasca.nightsoul.state { chasca skill; } if .chasca.nightsoul.state { chasca aim[bullets=6]; } } }"))
    document = parse("active chasca; chasca dash, aim, jump;", DIALECT)
    selected = next(item for item in document.root.walk() if item.kind == "action" and item.get("name").get("value") == "aim")
    changed = apply_variant(document, selected.node_id, VariantChoice("chasca.nightsoul_aim", 4))
    changed = apply_variant(changed, selected.node_id, VariantChoice("chasca.nightsoul_aim", 6))
    pairs.append((write(changed), "active chasca; { chasca dash; if !.chasca.nightsoul.state { chasca skill; } if .chasca.nightsoul.state { chasca aim[bullets=6]; } chasca jump; }"))
    return pairs


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--engine-root", type=Path, required=True)
    selected = args.parse_args().engine_root.resolve()
    if not (selected / "go.mod").is_file() or not (selected / "pkg/gcs/parser/parse.go").is_file():
        args.error("--engine-root must be an explicit public GCSIM source module")
    go = shutil.which("go")
    if not go:
        args.error("Go is required only for this development parser comparison")
    sources = list(PUBLIC_CASES)
    sources.append((ROOT / "run_workspace/gcsim/smoke_fixtures/rotation_chasca_ororon_furina_bennett.txt").read_text(encoding="utf-8"))
    pairs = [(source, write(parse(source, DIALECT), preserve=False)) for source in sources]
    generated_pairs, predicates = user_block_pairs()
    advanced, condition_truths = condition_variant_pairs()
    edits = structural_pairs()
    pairs.extend(generated_pairs)
    pairs.extend(predicates)
    pairs.extend(advanced)
    pairs.extend(condition_truths)
    pairs.extend(edits)
    payload = "".join(json.dumps({"source": text}) + "\n" for pair in pairs for text in pair)
    environment = dict(os.environ, GOPROXY="off", GOSUMDB="off", GOTOOLCHAIN="local", GOFLAGS="-mod=readonly", GOWORK="off")
    result = subprocess.run([go, "run", str(ROOT / "tools/gcsim_rotation_parse_oracle.go")], cwd=selected,
                            env=environment, input=payload, capture_output=True, text=True,
                            encoding="utf-8", timeout=120)
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        return 1
    outputs = [json.loads(line) for line in result.stdout.splitlines()]
    if len(outputs) != len(pairs) * 2:
        print("FAIL: parser returned an unexpected number of records", file=sys.stderr)
        return 1
    failures = []
    for index, pair in enumerate(pairs):
        original, generated = outputs[2 * index:2 * index + 2]
        if original.get("error") or generated.get("error"):
            failures.append({"case": index + 1, "source_error": original.get("error"), "generated_error": generated.get("error"), "source": pair[0], "generated": pair[1]})
        elif original.get("tree") != generated.get("tree") or original.get("config") != generated.get("config"):
            failures.append({"case": index + 1, "different_tree": original.get("tree") != generated.get("tree"), "different_config": original.get("config") != generated.get("config"), "source": pair[0], "generated": pair[1]})
    if failures:
        print(json.dumps(failures, ensure_ascii=False, indent=2))
        return 1
    print(f"PASS: {len(sources)} public source pairs, {len(generated_pairs)} generated block pairs and {len(predicates)} schedule truth checks match upstream parsed trees and configuration.")
    print(f"PASS: {len(advanced)} condition/variant code pairs and {len(condition_truths)} condition truth checks match the same upstream parser.")
    print(f"PASS: {len(edits)} structural editor changes match independently written expected GCSL in the same parser.")
    print("Parser-only comparison: per-character runtime registration, execution and UI are not exercised.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
