"""One selection-dependent options contract for all user block kinds."""

from dataclasses import dataclass

from .model import Document
from .conditions import Condition, PROFILE, recognize, set_condition
from .variants import VariantChoice, apply_variant, choices_for
from .semantics import Meaning, ScheduleChoice, analyze, name, number, set_cycle_count, set_schedule
from .writer import Writer


@dataclass(frozen=True)
class ContextProperty:
    key: str
    label_key: str
    value: object
    editor: str
    editable: bool = True
    choices: tuple[object, ...] = ()
    note_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class BlockContext:
    node_id: str
    kind: str
    properties: tuple[ContextProperty, ...] = ()
    commands: tuple[str, ...] = ()
    actor_key: str | None = None
    cycle_id: str | None = None
    source: str = ""


def context_for(document: Document, node_id: str, *, meaning: Meaning | None = None) -> BlockContext:
    meaning = meaning or analyze(document)
    current = meaning.nodes[node_id]
    source = Writer(document).emit(current) if not any(item.kind == "hole" for item in current.walk()) else ""
    cycle = meaning.cycles.get(node_id)
    if cycle is not None:
        fields = (ContextProperty("count", "rotation.option.cycle_count", cycle.count, "integer", cycle.limit_id is not None),)
        if current.kind == "while":
            fields += (_condition_property(document, current.get("condition")),)
        commands = ("add_action", "add_condition", "add_cycle") + (("add_schedule",) if cycle.counter is not None else ())
        return BlockContext(node_id, "cycle", fields, commands, cycle_id=node_id, source=source)
    schedule = meaning.schedules.get(node_id)
    if schedule is not None:
        owner = meaning.cycles[schedule.cycle_id]
        fields = (ContextProperty("schedule", "rotation.option.schedule", schedule.choice, "rotation_schedule"),
                  ContextProperty("cycle_count", "rotation.option.cycle_count", owner.count, "integer", False))
        return BlockContext(node_id, "schedule", fields, ("add_action", "add_condition"), cycle_id=owner.node_id, source=source)
    containing = next(meaning.ancestor_cycles(node_id), None)
    cycle_id = containing.node_id if containing else None
    line = next((item for item in (current, *meaning.ancestors(node_id)) if item.kind == "action_line"), None)
    actor = document.dialect.character_aliases.get(name(line.get("actor")), name(line.get("actor"))) if line else None
    if current.kind == "action":
        repeat = current.get("repeat")
        # Action repeats are syntax-limited int64 literals, not arithmetic
        # comparisons; the narrower exact-float range for cycles is irrelevant.
        fields = [ContextProperty("repeat", "rotation.option.action_repeat", int(repeat.get("value")) if repeat else 1, "integer")]
        if current.get("parameters"):
            # Dynamic expressions retain their nodes. No type/range is guessed
            # from prose and no personal mechanic is a new document container.
            fields.extend(ContextProperty("parameter." + name(entry.get("key")), "rotation.option.action_parameter", entry.get("value"), "expression", False)
                          for entry in current.get("parameters").get("entries"))
        variants = choices_for(document, actor, name(current.get("name")))
        if variants:
            fields.append(ContextProperty("variant", "rotation.option.variant", None, "action_variant", choices=variants,
                                          note_keys=("rotation.variant.explicit_edit",)))
        return BlockContext(node_id, "action", tuple(fields), ("personal_options",), actor, cycle_id, source)
    if current.kind == "action_line":
        return BlockContext(node_id, "character", (), ("add_action", "personal_options"), actor, cycle_id, source)
    if current.kind in {"if", "while"} or current.kind == "for" and current.get("initial") is None and current.get("post") is None and current.get("condition") is not None:
        return BlockContext(node_id, "condition" if current.kind == "if" else "conditional_loop", (_condition_property(document, current.get("condition")),),
                            ("add_action", "add_condition"), cycle_id=cycle_id, source=source)
    return BlockContext(node_id, current.kind, cycle_id=cycle_id, source=source)


def _condition_property(document, expression):
    choice = recognize(document, expression)
    editable = choice is not None or expression.kind == "hole" and document.dialect.identity == PROFILE
    return ContextProperty("condition", "rotation.option.condition", choice if editable else expression, "condition" if editable else "expression", editable,
                           note_keys=("rotation.condition.readiness_scope", "rotation.condition.timer_scope"))


def apply_context_edit(document: Document, node_id: str, property_key: str, value: object) -> Document:
    """The simple editable properties currently supported by the core."""
    context = context_for(document, node_id)
    field = next((item for item in context.properties if item.key == property_key), None)
    if field is None or not field.editable:
        raise ValueError("This property requires the detailed editor")
    if property_key == "condition" and isinstance(value, Condition):
        return set_condition(document, node_id, value)
    if property_key == "variant" and isinstance(value, VariantChoice):
        return apply_variant(document, node_id, value)
    if context.kind == "cycle" and property_key == "count":
        return set_cycle_count(document, node_id, value)
    if context.kind == "schedule" and property_key == "schedule" and isinstance(value, ScheduleChoice):
        return set_schedule(document, node_id, value)
    if context.kind == "action" and property_key == "repeat":
        if type(value) is not int or not 0 <= value <= 2**63 - 1:
            raise ValueError("Action repeat must be a nonnegative int64")
        action = document.find(node_id)
        return document.replace(node_id, action.changed(repeat=None if value == 1 else number(value)))
    raise ValueError("Unsupported property value")
