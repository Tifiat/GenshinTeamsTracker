"""Audited action variants with explicit generated prerequisite blocks.

Import inspection is read-only. Only an explicit builder/edit request creates
preparation or guards, and those remain visible ordinary GCSL nodes.
"""

from dataclasses import dataclass

from .conditions import Condition, PROFILE, actor_token, make_if
from .model import Document, Node, action, node
from .semantics import analyze, integer, name


@dataclass(frozen=True)
class Variant:
    key: str
    actor: str
    action: str
    label_key: str
    parameter: str = ""
    values: tuple[int, ...] = ()
    default: int | None = None
    requirement_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class VariantChoice:
    key: str
    value: int | None = None
    preparation: str = "ensure"


@dataclass(frozen=True)
class VariantPlan:
    variant: Variant
    block: Node
    note_keys: tuple[str, ...]


VARIANTS = (
    Variant("bennett.skill_hold", "bennett", "skill", "rotation.variant.bennett", "hold", (0, 1, 2), 0),
    Variant("chasca.nightsoul_aim", "chasca", "aim", "rotation.variant.chasca", "bullets", (1, 2, 3, 4, 5, 6), 6,
            ("rotation.variant.requires_nightsoul", "rotation.variant.chasca_c6")),
    Variant("furina.ousia_skill", "furina", "skill", "rotation.variant.furina_ousia", requirement_keys=("rotation.variant.requires_ousia",)),
    Variant("furina.pneuma_skill", "furina", "skill", "rotation.variant.furina_pneuma", requirement_keys=("rotation.variant.requires_pneuma",)),
)


def choices_for(document: Document, actor: str, action_name: str) -> tuple[Variant, ...]:
    if document.dialect.identity != PROFILE:
        return ()
    stable = document.dialect.character_aliases.get(actor, actor)
    return tuple(item for item in VARIANTS if item.actor == stable and item.action == action_name)


def _block(*items: Node) -> Node:
    return node("block", items=tuple(items))


def _parameters(key: str, value: int) -> Node:
    return node("map", entries=(node("entry", key=node("name", value=key), value=node("number", value=str(value))),))


def _not(choice: Condition) -> Condition:
    return choice.children[0] if choice.kind == "not" else Condition("not", children=(choice,))


def plan_variant(document: Document, choice: VariantChoice, *, actor: str | None = None) -> VariantPlan:
    if document.dialect.identity != PROFILE or not isinstance(choice, VariantChoice):
        raise ValueError("Variants require the audited dialect and an explicit choice")
    variant = next((item for item in VARIANTS if item.key == choice.key), None)
    if variant is None or choice.preparation not in {"ensure", "guard"}:
        raise ValueError("Unknown variant or preparation policy")
    meaning = analyze(document)
    if "execute_action" in meaning.bound_names or variant.actor == "furina" and "wait" in meaning.bound_names:
        raise ValueError("Custom action/wait handlers require a detailed edit")
    token = actor_token(document, actor or variant.actor)
    if document.dialect.character_aliases[token] != variant.actor:
        raise ValueError("Variant belongs to a different character")
    amount = variant.default if choice.value is None else choice.value
    if variant.parameter:
        if type(amount) is not int or amount not in variant.values:
            raise ValueError("Variant parameter is outside the audited choices")
    elif choice.value is not None:
        raise ValueError("This variant has no numeric parameter")
    parameters = _parameters(variant.parameter, amount) if variant.parameter else None
    selected = action(token, variant.action, parameters=parameters)
    if variant.actor == "bennett":
        return VariantPlan(variant, _block(selected), ())
    if variant.actor == "chasca":
        mode = Condition("mode", token, "nightsoul")
        steps = []
        if choice.preparation == "ensure":
            steps.append(make_if(document, _not(mode), _block(action(token, "skill"))))
        steps.append(make_if(document, mode, _block(selected)))
        block = _block(*steps)
        notes = ["rotation.variant.dispatch_boundary"]
        if amount < 6:
            # No GCSL field proves absence of C6 instant charge at its expiry
            # frame: a timer can read zero while the status is still active.
            # Keep the conservative restriction explicit in generated code.
            allowed = Condition("constellations", token, operator="<", value="6")
            block = _block(make_if(document, allowed, block))
            notes.append("rotation.variant.chasca_partial_c0_c5")
        return VariantPlan(variant, block, tuple(notes))
    mode = Condition("mode", token, "ousia")
    desired = mode if variant.key == "furina.ousia_skill" else _not(mode)
    steps = []
    if choice.preparation == "ensure":
        # Furina changes alignment one frame after CanQueueAfter. The wait is
        # explicit and exceeds that boundary; reread before selecting the skill.
        wait = node("expression_stmt", value=node("call", function=node("name", value="wait"), arguments=(node("number", value="2"),)))
        steps.append(make_if(document, _not(desired), _block(action(token, "charge"), wait)))
    steps.append(make_if(document, desired, _block(selected)))
    notes = (("rotation.variant.furina_switch_wait",) if choice.preparation == "ensure" else ()) + ("rotation.variant.dispatch_boundary",)
    return VariantPlan(variant, _block(*steps), notes)


def apply_variant(document: Document, action_id: str, choice: VariantChoice) -> Document:
    meaning = analyze(document)
    current = document.find(action_id)
    if current.kind != "action":
        raise ValueError("Select an action")
    line = next((item for item in meaning.ancestors(action_id) if item.kind == "action_line"), None)
    if line is None:
        raise ValueError("Action has no explicit character")
    actor = name(line.get("actor"))
    if choice.key not in {item.key for item in choices_for(document, actor, name(current.get("name")))}:
        raise ValueError("Variant is not available for this action")
    if current.get("repeat") is not None and integer(current.get("repeat")) != 1:
        raise ValueError("Select a single action; repeated variant preparation needs an explicit loop")
    variant = next(item for item in VARIANTS if item.key == choice.key)
    entries = current.get("parameters").get("entries") if current.get("parameters") else ()
    if any(name(entry.get("key")) != variant.parameter for entry in entries):
        raise ValueError("Extra parameters require a detailed edit; they cannot be silently discarded")
    plan = plan_variant(document, choice, actor=actor)
    actions = line.get("actions")
    index = next(i for i, item in enumerate(actions) if item.node_id == action_id)
    before, after = actions[:index], actions[index + 1:]
    items = ((_line(actor, before),) if before else ()) + plan.block.get("items") + ((_line(actor, after),) if after else ())
    return document.replace(line.node_id, _block(*items))


def _line(actor: str, actions: tuple[Node, ...]) -> Node:
    return node("action_line", actor=node("name", value=actor), actions=actions)
