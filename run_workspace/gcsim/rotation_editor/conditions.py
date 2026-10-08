"""Pure, source-linked condition choices for human blocks and code generation.

Choices are temporary property values. The only persisted/editable document
remains the GCSL tree. Unsupported expressions keep their original nodes.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Callable

from .model import Document, Node, conditional, loop, node
from .semantics import binary, ungroup


PROFILE = "gcsim-v2.45.0-gcsl"
COMPARISONS = frozenset(("==", "!=", "<", "<=", ">", ">="))
REVERSE = {"==": "==", "!=": "!=", "<>": "!=", "<": ">", "<=": ">=", ">": "<", ">=": "<="}
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,127}\Z")


@dataclass(frozen=True)
class Condition:
    kind: str
    actor: str = ""
    subject: str = ""
    operator: str = ">="
    value: str = ""
    children: tuple["Condition", ...] = ()


def decimal(value: str) -> Decimal | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        result = Decimal(value)
    except InvalidOperation:
        return None
    return result if result.is_finite() and abs(result) <= 10**12 and result.as_tuple().exponent >= -12 else None


def literal(value: Node | None) -> Decimal | None:
    value = ungroup(value)
    if value is not None and value.kind == "boolean":
        return Decimal(value.get("value") == "true")
    return decimal(value.get("value")) if value is not None and value.kind == "number" else None


def spelling(value: Decimal) -> str:
    return format(value.normalize(), "f")


def actor_token(document: Document, actor: str) -> str:
    aliases = document.dialect.character_aliases
    if actor in aliases:
        return actor
    alias = next((key for key, stable in aliases.items() if stable == actor), None)
    if alias is None:
        raise ValueError("Select a character available in this dialect")
    return alias


def _field(document: Document, value: Node | None) -> tuple[str, tuple[str, ...]] | None:
    value = ungroup(value)
    if value is None or value.kind != "field":
        return None
    path = value.get("path")
    if len(path) == 2 and path[0] == "status":
        return "", path
    if len(path) >= 2 and path[0] in document.dialect.character_aliases:
        return document.dialect.character_aliases[path[0]], path[1:]
    return None


def _flag(document: Document, value: Node) -> Condition | None:
    field = _field(document, value)
    if field is None:
        return None
    actor, tail = field
    if tail == ("onfield",):
        return Condition("on_field", actor)
    if len(tail) == 2 and tail[0] in {"skill", "burst"} and tail[1] == "ready":
        return Condition("action_ready", actor, tail[0])
    if len(tail) == 2 and tail[0] == "status" and _KEY.fullmatch(tail[1]):
        return Condition("effect", actor, tail[1])
    if actor == "chasca" and tail == ("nightsoul", "state"):
        return Condition("mode", actor, "nightsoul")
    if actor == "furina" and tail == ("ousia",):
        return Condition("mode", actor, "ousia")
    return None


def recognize(document: Document, value: Node, *, depth: int = 0) -> Condition | None:
    if document.dialect.identity != PROFILE or depth > 32:
        return None
    value = ungroup(value)
    if value.kind == "boolean":
        return Condition("constant", value=value.get("value"))
    flag = _flag(document, value)
    if flag is not None:
        return flag
    if value.kind == "unary" and value.get("operator") == "!":
        child = recognize(document, value.get("value"), depth=depth + 1)
        return Condition("not", children=(child,)) if child is not None else None
    if value.kind != "binary":
        return None
    operator = value.get("operator")
    if operator in {"&&", "||"}:
        children = tuple(recognize(document, value.get(side), depth=depth + 1) for side in ("left", "right"))
        return Condition("all" if operator == "&&" else "any", children=children) if all(child is not None for child in children) else None
    if operator not in REVERSE:
        return None
    operator = "!=" if operator == "<>" else operator
    left, right = value.get("left"), value.get("right")
    first, second = _field(document, left), _field(document, right)
    if first and second and first[0] == second[0] and first[1] == ("energy",) and second[1] == ("energymax",) and operator == ">=":
        return Condition("energy_full", first[0])
    if first and second and first[0] == second[0] and second[1] == ("energy",) and first[1] == ("energymax",) and operator == "<=":
        return Condition("energy_full", first[0])
    if first is None and second is not None:
        left, right, first = right, left, second
        operator = REVERSE[operator]
    amount = literal(right)
    if first is None or amount is None:
        return None
    actor, tail = first
    flag = _flag(document, left)
    if flag is not None:
        # Remaining duration is nonnegative; boolean fields are exactly 0/1.
        positive = amount == 0 and operator in {"!=", ">"}
        negative = amount == 0 and operator in {"==", "<="}
        if flag.kind != "effect":
            positive |= amount == 1 and operator in {"==", ">="}
            negative |= amount == 1 and operator in {"!=", "<"}
        if positive or negative:
            return flag if positive else Condition("not", children=(flag,))
    if tail == ("energy",) and amount >= 0:
        return Condition("energy", actor, operator=operator, value=spelling(amount))
    if tail == ("cons",) and amount == amount.to_integral_value() and 0 <= amount <= 6:
        return Condition("constellations", actor, operator=operator, value=spelling(amount))
    if tail == ("hpratio",) and 0 <= amount <= 1:
        return Condition("hp_percent", actor, operator=operator, value=spelling(amount * 100))
    return None


def compile_condition(document: Document, choice: Condition, *, depth: int = 0) -> Node:
    if document.dialect.identity != PROFILE:
        raise ValueError("Condition meanings require the audited dialect")
    if not isinstance(choice, Condition) or depth > 32:
        raise ValueError("Invalid or excessively nested condition")
    if choice.kind in {"all", "any", "not"}:
        if choice.kind == "not":
            if len(choice.children) != 1:
                raise ValueError("Not requires one condition")
            return node("unary", operator="!", value=compile_condition(document, choice.children[0], depth=depth + 1))
        if not 2 <= len(choice.children) <= 32:
            raise ValueError("And/or requires 2 to 32 conditions")
        children = [compile_condition(document, child, depth=depth + 1) for child in choice.children]
        result = children[0]
        for child in children[1:]:
            result = binary(result, "&&" if choice.kind == "all" else "||", child)
        return result
    if choice.children:
        raise ValueError("A simple condition cannot contain nested conditions")
    if choice.kind == "constant" and choice.value in {"true", "false"}:
        return node("boolean", value=choice.value)
    actor = actor_token(document, choice.actor) if choice.actor else ""
    def field(*tail: str) -> Node:
        if not actor:
            raise ValueError("Select an explicit character")
        return node("field", path=(actor, *tail))
    if choice.kind == "effect":
        if not _KEY.fullmatch(choice.subject):
            raise ValueError("Select an exact effect key")
        return field("status", choice.subject) if actor else node("field", path=("status", choice.subject))
    if choice.kind == "on_field":
        return field("onfield")
    if choice.kind == "action_ready" and choice.subject in {"skill", "burst"}:
        return field(choice.subject, "ready")
    if choice.kind == "energy_full":
        return binary(field("energy"), ">=", field("energymax"))
    if choice.kind in {"energy", "hp_percent", "constellations"} and choice.operator in COMPARISONS:
        amount = decimal(choice.value)
        if amount is None or amount < 0 or choice.kind == "hp_percent" and amount > 100:
            raise ValueError("Invalid condition threshold")
        if choice.kind == "constellations" and (amount != amount.to_integral_value() or amount > 6):
            raise ValueError("Constellation count must be an integer from 0 to 6")
        threshold = amount / 100 if choice.kind == "hp_percent" else amount
        if decimal(spelling(threshold)) is None:
            raise ValueError("Threshold exceeds supported decimal precision")
        return binary(field({"hp_percent": "hpratio", "energy": "energy", "constellations": "cons"}[choice.kind]), choice.operator, node("number", value=spelling(threshold)))
    stable = document.dialect.character_aliases.get(actor)
    if choice.kind == "mode" and (stable, choice.subject) in {("chasca", "nightsoul"), ("furina", "ousia")}:
        return field("nightsoul", "state") if stable == "chasca" else field("ousia")
    raise ValueError("Unsupported condition choice")


def make_if(document: Document, choice: Condition | None = None, body: Node | None = None, otherwise: Node | None = None) -> Node:
    return conditional(compile_condition(document, choice) if choice is not None else None, body, otherwise)


def make_while(document: Document, choice: Condition | None = None, body: Node | None = None) -> Node:
    return loop(compile_condition(document, choice) if choice is not None else None, body)


def set_condition(document: Document, block_id: str, choice: Condition) -> Document:
    current = document.find(block_id)
    if current.kind not in {"if", "while", "for"} or current.get("condition") is None:
        raise ValueError("Select a conditional block")
    if current.kind == "for" and (current.get("initial") is not None or current.get("post") is not None):
        raise ValueError("Counted loops use cycle properties")
    return document.replace(current.get("condition").node_id, compile_condition(document, choice))


def describe(choice: Condition, translate: Callable, resolve_name: Callable, *, parent: str = "") -> str:
    tr = translate
    if choice.kind in {"all", "any"}:
        text = tr("rotation.condition." + choice.kind).join(describe(child, tr, resolve_name, parent=choice.kind) for child in choice.children)
        return "(" + text + ")" if parent and parent != choice.kind else text
    if choice.kind == "not":
        child = choice.children[0]
        if child.kind in {"effect", "on_field", "action_ready", "energy_full", "mode"}:
            return _simple_text(child, tr, resolve_name, negative=True)
        return tr("rotation.condition.not", condition=describe(child, tr, resolve_name))
    return _simple_text(choice, tr, resolve_name)


def _simple_text(choice: Condition, tr: Callable, resolve_name: Callable, *, negative: bool = False) -> str:
    actor = resolve_name(choice.actor) or choice.actor
    suffix = ".no" if negative else ".yes"
    if choice.kind == "constant":
        return tr("rotation.condition.always" if choice.value == "true" else "rotation.condition.never")
    if choice.kind in {"energy", "hp_percent", "constellations"}:
        relation = tr("rotation.condition.compare." + {"==": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}[choice.operator])
        return tr("rotation.condition." + choice.kind, actor=actor, relation=relation, value=choice.value)
    if choice.kind == "mode":
        return tr("rotation.condition.mode." + choice.subject + suffix, actor=actor)
    if choice.kind == "effect":
        if choice.actor and choice.subject == "favonius-cd":
            return tr("rotation.condition.favonius" + suffix, actor=actor)
        effect = tr("rotation.favonius_cd") if choice.subject == "favonius-cd" else choice.subject
        return tr("rotation.condition." + ("effect" if choice.actor else "global_effect") + suffix, actor=actor, effect=effect)
    return tr("rotation.condition." + choice.kind + suffix, actor=actor, action=tr("rotation.action." + choice.subject) if choice.kind == "action_ready" else "")
