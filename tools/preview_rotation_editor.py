"""Read-only terminal preview of the isolated rotation editor core.

Uses a public fixture by default. No application startup, settings, profiles,
network, cache writes or simulation. The default public example injects its
four fixture names; other files fall back to stable engine keys. Application
integration must inject names from prepared project records.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "run_workspace/gcsim/smoke_fixtures/rotation_chasca_ororon_furina_bennett.txt"
sys.path.insert(0, str(ROOT))

from run_workspace.gcsim.rotation_editor import parse, write
from run_workspace.gcsim.rotation_editor.options import EngineIdentity, load_local_tables, read_character_options
from run_workspace.gcsim.rotation_editor.readable import render
from run_workspace.gcsim.rotation_editor.source import load_source_dialect
from run_workspace.gcsim.rotation_editor.validation import validate_setup
from run_workspace.gcsim.rotation_editor.conditions import Condition, make_if, make_while
from run_workspace.gcsim.rotation_editor.model import action, node
from run_workspace.gcsim.rotation_editor.variants import VariantChoice, plan_variant


def example_document(dialect):
    """Public model demonstration, constructed by the same future button API."""
    document = parse("active furina;", dialect)
    condition = Condition("all", children=(Condition("energy_full", "furina"),
        Condition("any", children=(Condition("hp_percent", "furina", operator="<", value="50"), Condition("mode", "chasca", "nightsoul")))))
    items = [document.root.get("items")[0], make_if(document, condition, node("block", items=(action("furina", "burst"),)))]
    no_favonius_cd = Condition("not", children=(Condition("effect", "furina", "favonius-cd"),))
    items.append(make_while(document, no_favonius_cd, node("block", items=(action("furina", "attack"),))))
    for choice in (VariantChoice("bennett.skill_hold", 2), VariantChoice("chasca.nightsoul_aim", 6), VariantChoice("furina.pneuma_skill")):
        items.extend(plan_variant(document, choice).block.get("items"))
    return document.replace(document.root.node_id, document.root.changed(items=tuple(items)))


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--engine-root", type=Path, required=True)
    cli.add_argument("--file", type=Path, default=FIXTURE)
    cli.add_argument("--language", choices=("ru", "en", "pt-br"), default="ru")
    cli.add_argument("--audited-v245", action="store_true", help="Explicitly opt into the audited v2.45 field descriptions")
    cli.add_argument("--canonical", action="store_true")
    cli.add_argument("--details", action="store_true", help="Also show simulation setup details")
    cli.add_argument("--examples", action="store_true", help="Build public condition/variant examples in memory (requires --audited-v245)")
    cli.add_argument("--character", help="Also show selected character action/parameter/condition metadata")
    args = cli.parse_args()
    if args.examples and (not args.audited_v245 or args.file.resolve() != FIXTURE.resolve()):
        cli.error("--examples requires --audited-v245 and cannot be combined with a custom --file")
    dialect = load_source_dialect(args.engine_root, identity="gcsim-v2.45.0-gcsl" if args.audited_v245 else "gcsl-syntax-v1")
    if args.file.stat().st_size > 2 * 1024 * 1024:
        cli.error("Rotation exceeds the 2 MiB preview limit")
    document = example_document(dialect) if args.examples else parse(args.file.read_text(encoding="utf-8"), dialect)
    locale = json.loads((ROOT / "localization/locales" / f"{args.language}.json").read_text(encoding="utf-8"))
    names = json.loads(FIXTURE.with_name("rotation_editor_names.json").read_text(encoding="utf-8"))[args.language] if args.file.resolve() == FIXTURE.resolve() else {}
    readable = render(document, lambda key, **fields: locale[key].format(**fields), resolve_name=names.get)
    print(readable.text(include_details=args.details))
    diagnostics = document.diagnostics + (validate_setup(document) if args.audited_v245 else ())
    if diagnostics:
        print(json.dumps([{"code": item.code, "severity": item.severity, "position": document.position(item.span), "details": dict(item.details)} for item in diagnostics], ensure_ascii=False), file=sys.stderr)
    if args.character:
        tables = load_local_tables(args.engine_root)
        descriptor = read_character_options(EngineIdentity(args.engine_root.name, "explicit-local-preview"), args.character, *(table or {} for table in tables))
        print(json.dumps({"character": descriptor.character_key, "actions": [{"name": item.name, "invalid": item.invalid, "note": item.note} for item in descriptor.actions], "parameters": [{"action": item.action, "key": item.key, "description": item.description} for item in descriptor.parameters], "condition_fields": [{"key": item.key, "description": item.description} for item in descriptor.fields], "warnings": descriptor.warnings}, ensure_ascii=False, indent=2))
    if args.canonical:
        print(write(document, preserve=False))
    return 0 if document.syntax_complete and not any(item.severity == "error" for item in diagnostics) else 1


if __name__ == "__main__":
    raise SystemExit(main())
