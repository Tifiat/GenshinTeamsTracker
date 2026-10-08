"""Source-limited setup and editor-option checks for the parsed GCSL tree.

This is not an engine execution or full readiness verdict. Diagnostic codes and
details are machine values; presentation belongs to the caller.
"""

from __future__ import annotations

import math
import re
from typing import Mapping

from .model import Diagnostic, Document, Node, Span
from .options import CharacterOptions, EngineIdentity


_INT = re.compile(r"[0-9]+\Z")
_NUMBER = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")
_OPTION_INTS = frozenset({"iteration", "workers", "swap_delay", "attack_delay", "charge_delay", "skill_delay", "burst_delay", "jump_delay", "dash_delay", "aim_delay"})
_OPTION_BOOLS = frozenset({"debug", "defhalt", "hitlag", "ignore_burst_energy"})
_TARGET_NUMBERS = frozenset({"radius", "hp", "particle_threshold", "particle_drop_count"})
_TARGET_CONSTS = frozenset({"resist", "freeze_resist", "electro", "pyro", "cryo", "hydro", "anemo", "dendro", "geo", "physical", "frozen", "none"})


def _span(value: Node | None) -> Span:
    return value.span if isinstance(value, Node) and value.span is not None else Span(0, 0)


def _name(value: Node | None) -> str:
    return str(value.get("value", "")) if isinstance(value, Node) and value.kind == "name" else ""


def _diag(code: str, value: Node | None, *, severity: str = "error", **details: str) -> Diagnostic:
    return Diagnostic(code, _span(value), severity, tuple((key, str(item)) for key, item in details.items()))


def _values(setting: Node) -> tuple[Node, ...]:
    values = setting.get("values", ())
    return values if isinstance(values, tuple) else ()


def _one(setting: Node) -> Node | None:
    values = _values(setting)
    return values[0] if len(values) == 1 else None


def _is_integer(value: Node | None) -> bool:
    spelling = value.get("value") if isinstance(value, Node) and value.kind == "number" else None
    return isinstance(spelling, str) and len(spelling) <= 20 and bool(_INT.fullmatch(spelling)) and 0 <= int(spelling) <= 2**63 - 1


def _is_number(value: Node | None) -> bool:
    spelling = value.get("value") if isinstance(value, Node) and value.kind == "number" else None
    return isinstance(spelling, str) and len(spelling) <= 128 and bool(_NUMBER.fullmatch(spelling))


def _int64(value: int) -> int:
    return (value + 2**63) % 2**64 - 2**63


def _constant(value: Node | None, depth: int = 0) -> tuple[bool, int | float] | None:
    """Recognize selected source constant folding with int64 and float64 paths.

    The folded value is used only to classify numeric constants and zero
    divisors. It is never written to the document or used as a setup value.
    """
    if not isinstance(value, Node) or depth > 32:
        return None
    if _is_number(value):
        try:
            spelling = value.get("value")
            if _INT.fullmatch(spelling):
                integer = int(spelling)
                if integer <= 2**63 - 1:
                    return False, integer
            floating = float(spelling)
            return (True, floating) if math.isfinite(floating) else None
        except (ValueError, OverflowError):
            return None
    if value.kind == "boolean" and value.get("value") in {"true", "false"}:
        return False, 1 if value.get("value") == "true" else 0
    if value.kind == "group":
        return _constant(value.get("value"), depth + 1)
    if value.kind == "unary" and value.get("operator") in {"-", "!"}:
        operand = _constant(value.get("value"), depth + 1)
        if operand is None:
            return None
        is_float, number = operand
        if value.get("operator") == "!":
            return False, int(number == 0)
        result = -number if is_float else _int64(-number)
        return (is_float, result) if not is_float or math.isfinite(result) else None
    if value.kind == "binary" and value.get("operator") in {"+", "-", "*", "/", ">", ">=", "<", "<=", "==", "!=", "<>", "&&", "||"}:
        left, right = _constant(value.get("left"), depth + 1), _constant(value.get("right"), depth + 1)
        if left is None or right is None:
            return None
        left_float, lvalue = left
        right_float, rvalue = right
        operation = value.get("operator")
        if operation in {"&&", "||"}:
            return False, int((lvalue != 0 and rvalue != 0) if operation == "&&" else (lvalue != 0 or rvalue != 0))
        if operation in {">", ">=", "<", "<=", "==", "!=", "<>"}:
            lfloat, rfloat = float(lvalue), float(rvalue)
            comparisons = {">": lfloat > rfloat, ">=": lfloat >= rfloat, "<": lfloat < rfloat,
                           "<=": lfloat <= rfloat, "==": lfloat == rfloat,
                           "!=": lfloat != rfloat, "<>": lfloat != rfloat}
            return False, int(comparisons[operation])
        if operation == "/" and rvalue == 0:
            # Float division by zero yields nonfinite output in Go; keep the
            # validator conservative rather than accepting that as a number.
            return None
        if left_float or right_float:
            lfloat, rfloat = float(lvalue), float(rvalue)
            result = lfloat + rfloat if operation == "+" else lfloat - rfloat if operation == "-" else lfloat * rfloat if operation == "*" else lfloat / rfloat
            return (True, result) if math.isfinite(result) else None
        if operation == "+":
            result = lvalue + rvalue
        elif operation == "-":
            result = lvalue - rvalue
        elif operation == "*":
            result = lvalue * rvalue
        else:
            result = (abs(lvalue) // abs(rvalue)) * (-1 if (lvalue < 0) != (rvalue < 0) else 1)
        return False, _int64(result)
    return None


def _number_values(setting: Node, count: int, *, integer: bool = False, constant: bool = False) -> list[Diagnostic]:
    values = _values(setting)
    check = _is_integer if integer else (lambda value: _constant(value) is not None) if constant else _is_number
    if len(values) != count or any(not check(value) for value in values):
        return [_diag("rotation.setup.value_type", setting, key=_name(setting.get("key")), expected="integer" if integer else "numeric_constant" if constant else "number")]
    return []


def _identifier(value: Node | None, document: Document) -> bool:
    return isinstance(value, Node) and value.kind == "name" and document.dialect.category(_name(value)) == "identifier"


def _params_map(value: Node | None, *, integer: bool = False) -> bool:
    if not isinstance(value, Node) or value.kind != "map":
        return False
    entries = value.get("entries", ())
    if not isinstance(entries, tuple):
        return False
    return all(isinstance(entry, Node) and entry.kind == "entry" and _name(entry.get("key")) and
               (_is_integer(entry.get("value")) if integer else _constant(entry.get("value")) is not None)
               for entry in entries)


def _level_pair(value: Node | None) -> bool:
    if not isinstance(value, Node) or value.kind != "level_pair":
        return False
    base, maximum = value.get("base"), value.get("maximum")
    return _is_integer(base) and _is_integer(maximum) and int(base.get("value")) <= int(maximum.get("value"))


def _validate_options(document: Document, entries: tuple[Node, ...]) -> list[Diagnostic]:
    diagnostics = []
    for entry in entries:
        key, value = _name(entry.get("key")), _one(entry)
        if entry.get("plus"):
            diagnostics.append(_diag("rotation.setup.option_unknown", entry, key=key))
        elif key in _OPTION_INTS:
            diagnostics.extend(_number_values(entry, 1, integer=True))
        elif key == "duration":
            diagnostics.extend(_number_values(entry, 1))
        elif key in _OPTION_BOOLS:
            if not isinstance(value, Node) or value.kind != "boolean" or value.get("value") not in {"true", "false"}:
                diagnostics.append(_diag("rotation.setup.value_type", entry, key=key, expected="boolean"))
        elif key == "mode":
            if not _identifier(value, document):
                diagnostics.append(_diag("rotation.setup.value_type", entry, key=key, expected="identifier"))
        elif key == "frame_defaults":
            if not _identifier(value, document) or _name(value) != "human":
                diagnostics.append(_diag("rotation.setup.frame_defaults", entry, key=key))
        else:
            diagnostics.append(_diag("rotation.setup.option_unknown", entry, key=key))
    return diagnostics


def _validate_character(entries: tuple[Node, ...]) -> list[Diagnostic]:
    diagnostics = []
    for entry in entries:
        key = _name(entry.get("key"))
        if key == "lvl" and not entry.get("plus"):
            if not _level_pair(_one(entry)):
                diagnostics.append(_diag("rotation.setup.level_pair", entry, key=key))
        elif key == "cons" and not entry.get("plus"):
            diagnostics.extend(_number_values(entry, 1, integer=True))
        elif key == "talent" and not entry.get("plus"):
            diagnostics.extend(_number_values(entry, 3, integer=True))
        elif key == "params" and entry.get("plus"):
            if not _params_map(_one(entry)):
                diagnostics.append(_diag("rotation.setup.params_type", entry, key=key))
        elif entry.get("plus"):
            diagnostics.append(_diag("rotation.setup.character_plus_unknown", entry, key=key))
        else:
            diagnostics.append(_diag("rotation.setup.character_field_skipped", entry, severity="warning", key=key))
    return diagnostics


def _validate_add(document: Document, selector: str, entries: tuple[Node, ...], setup: Node) -> list[Diagnostic]:
    diagnostics = []
    first = entries[0] if entries else None
    if selector in {"weapon", "set"}:
        expected = first is not None and _name(first.get("key")) == selector
        value = _one(first) if first is not None else None
        if not expected or not isinstance(value, Node) or value.kind != "string":
            diagnostics.append(_diag("rotation.setup.quoted_key", first or setup, key=selector))
        keys = {"lvl", "refine", "params"} if selector == "weapon" else {"count", "params"}
        present = set()
        for entry in entries[1:]:
            key = _name(entry.get("key"))
            present.add(key)
            if key not in keys or entry.get("plus") != (key == "params"):
                diagnostics.append(_diag("rotation.setup.add_field_unknown", entry, key=key))
            elif key == "lvl":
                if not _level_pair(_one(entry)):
                    diagnostics.append(_diag("rotation.setup.level_pair", entry, key=key))
            elif key in {"refine", "count"}:
                diagnostics.extend(_number_values(entry, 1, integer=True))
            elif key == "params" and not _params_map(_one(entry)):
                diagnostics.append(_diag("rotation.setup.params_type", entry, key=key))
        if selector == "weapon":
            for required in ("lvl", "refine"):
                if required not in present:
                    diagnostics.append(_diag("rotation.setup.weapon_required", setup, key=required))
        elif "count" not in present:
            diagnostics.append(_diag("rotation.setup.set_count_default", setup, severity="warning"))
        return diagnostics
    if selector != "stats":
        return [_diag("rotation.setup.add_field_unknown", setup, key=selector)]
    random_mode = False
    for index, entry in enumerate(entries):
        key = _name(entry.get("key"))
        if entry.get("plus"):
            diagnostics.append(_diag("rotation.setup.add_field_unknown", entry, key=key))
            continue
        if key == "random" and not _values(entry):
            random_mode = True
            if index:
                diagnostics.append(_diag("rotation.setup.random_after_stats", entry, severity="warning"))
            continue
        if random_mode:
            if key == "rarity":
                diagnostics.extend(_number_values(entry, 1, integer=True))
            elif key in {"sand", "goblet", "circlet"}:
                value = _one(entry)
                if not isinstance(value, Node) or value.kind != "name" or _name(value) not in document.dialect.stats:
                    diagnostics.append(_diag("rotation.setup.value_type", entry, key=key, expected="stat"))
            else:
                diagnostics.append(_diag("rotation.setup.random_field_unknown", entry, key=key))
        elif key == "label":
            if not _identifier(_one(entry), document):
                diagnostics.append(_diag("rotation.setup.value_type", entry, key=key, expected="identifier"))
        elif key in document.dialect.stats:
            diagnostics.extend(_number_values(entry, 1, constant=True))
        else:
            diagnostics.append(_diag("rotation.setup.add_field_unknown", entry, key=key))
    return diagnostics


def _validate_target(document: Document, entries: tuple[Node, ...]) -> list[Diagnostic]:
    diagnostics = []
    level_seen = False
    for entry in entries:
        key, value = _name(entry.get("key")), _one(entry)
        if entry.get("plus"):
            diagnostics.append(_diag("rotation.setup.target_field_unknown", entry, key=key))
            continue
        if key == "lvl":
            if _is_integer(value) and 1 <= int(value.get("value")) <= 100:
                level_seen = True
            else:
                diagnostics.append(_diag("rotation.setup.target_level", entry, key=key))
        elif key == "type":
            if not level_seen:
                diagnostics.append(_diag("rotation.setup.target_level_before_type", entry))
            configured = isinstance(value, Node) and value.kind == "configured_name"
            name = value.get("name") if configured else value
            if not _identifier(name, document):
                diagnostics.append(_diag("rotation.setup.value_type", entry, key=key, expected="identifier"))
            if configured:
                params = value.get("parameters")
                param_entries = params.get("entries", ()) if isinstance(params, Node) and params.kind == "map" else None
                if not isinstance(param_entries, tuple) or any(not isinstance(item, Node) or item.kind != "entry" or not _name(item.get("key")) or not _is_number(item.get("value")) for item in param_entries):
                    diagnostics.append(_diag("rotation.setup.params_type", entry, key=key))
                else:
                    for item in param_entries:
                        param = _name(item.get("key"))
                        if param not in {"hp_mult", "particles"}:
                            diagnostics.append(_diag("rotation.setup.target_param_ignored", item, severity="warning", key=param))
                        elif param == "particles" and not _is_integer(item.get("value")):
                            diagnostics.append(_diag("rotation.setup.value_type", item, key=param, expected="integer"))
        elif key == "pos":
            diagnostics.extend(_number_values(entry, 2, constant=True))
        elif key in _TARGET_CONSTS:
            diagnostics.extend(_number_values(entry, 1, constant=True))
        elif key in _TARGET_NUMBERS:
            diagnostics.extend(_number_values(entry, 1))
        elif key == "particle_element":
            if not isinstance(value, Node) or value.kind != "name" or _name(value) not in document.dialect.elements:
                diagnostics.append(_diag("rotation.setup.value_type", entry, key=key, expected="element"))
        else:
            diagnostics.append(_diag("rotation.setup.target_field_unknown", entry, key=key))
    return diagnostics


def _validate_event(document: Document, directive: str, selector: str, entries: tuple[Node, ...]) -> list[Diagnostic]:
    diagnostics = []
    if selector not in {"", "once", "every"}:
        return [_diag("rotation.setup.event_selector", entries[0] if entries else None, key=selector)]
    if not selector and entries:
        diagnostics.append(_diag("rotation.setup.event_selector", entries[0]))
    for entry in entries:
        key = _name(entry.get("key"))
        if entry.get("plus"):
            diagnostics.append(_diag("rotation.setup.event_field_unknown", entry, key=key))
            continue
        if key in {"once", "every"} and not _values(entry):
            diagnostics.append(_diag("rotation.setup.event_field_unknown", entry, key=key))
            continue
        if key == "interval":
            diagnostics.extend(_number_values(entry, 1 if selector == "once" else 2, integer=True))
        elif key == "amount":
            diagnostics.extend(_number_values(entry, 1 if directive == "energy" else 2, integer=directive == "energy"))
        elif key == "element" and directive == "hurt":
            value = _one(entry)
            if not isinstance(value, Node) or value.kind != "name" or _name(value) not in document.dialect.elements:
                diagnostics.append(_diag("rotation.setup.value_type", entry, key=key, expected="element"))
        else:
            diagnostics.append(_diag("rotation.setup.event_field_unknown", entry, key=key))
    return diagnostics


def validate_setup(document: Document) -> tuple[Diagnostic, ...]:
    """Check selected v2.45 setup envelopes; rotation-only shells are allowed."""
    diagnostics: list[Diagnostic] = []
    for setup in document.root.get("items", ()):
        if not isinstance(setup, Node) or setup.kind != "setup":
            continue
        directive, selector = _name(setup.get("directive")), _name(setup.get("selector"))
        entries = tuple(entry for entry in setup.get("entries", ()) if isinstance(entry, Node))
        if directive == "options":
            diagnostics.extend(_validate_options(document, entries))
        elif directive == "char":
            diagnostics.extend(_validate_character(entries))
        elif directive == "add":
            diagnostics.extend(_validate_add(document, selector, entries, setup))
        elif directive == "target":
            diagnostics.extend(_validate_target(document, entries))
        elif directive in {"energy", "hurt"}:
            diagnostics.extend(_validate_event(document, directive, selector, entries))
    return tuple(diagnostics)


def validate_actions(
    document: Document,
    character_options: Mapping[str, CharacterOptions],
    expected_identity: EngineIdentity | None = None,
    require_options: bool = False,
) -> tuple[Diagnostic, ...]:
    """Validate future editor action choices against supplied docs metadata."""
    diagnostics: list[Diagnostic] = []
    action_lines = [item for item in document.root.walk() if item.kind == "action_line"]
    overrides = [item for item in document.root.walk() if item.kind == "assign" and _name(item.get("name")) == "execute_action"]
    if action_lines and overrides:
        return (_diag("rotation.action.custom_handler", overrides[0], severity="warning"),)
    for line in action_lines:
        alias = _name(line.get("actor"))
        actor = document.dialect.character_aliases.get(alias, alias)
        descriptor = character_options.get(actor)
        for action in line.get("actions", ()):
            if not isinstance(action, Node) or action.kind != "action":
                continue
            name = _name(action.get("name"))
            if descriptor is None or descriptor.origin == "unavailable":
                diagnostics.append(_diag("rotation.action.options_unavailable", action, severity="error" if require_options else "warning", actor=actor))
                continue
            if descriptor.character_key != actor or expected_identity is not None and descriptor.identity != expected_identity:
                diagnostics.append(_diag("rotation.action.options_stale", action, actor=actor))
                continue
            documented = next((option for option in descriptor.actions if option.name == name), None)
            if documented is None:
                diagnostics.append(_diag("rotation.action.undocumented", action, severity="error" if require_options else "warning", actor=actor, action=name))
            elif documented.invalid:
                diagnostics.append(_diag("rotation.action.invalid", action, actor=actor, action=name))
            elif documented.note:
                diagnostics.append(_diag("rotation.action.note", action, severity="warning", actor=actor, action=name))
            parameters = action.get("parameters")
            if isinstance(parameters, Node) and parameters.kind == "map":
                registered = {option.key for option in descriptor.parameters if option.action == name}
                for entry in parameters.get("entries", ()):
                    if not isinstance(entry, Node):
                        continue
                    key = _name(entry.get("key"))
                    if registered and key not in registered:
                        diagnostics.append(_diag("rotation.action.param_invalid", entry, actor=actor, action=name, key=key))
                    elif not registered:
                        diagnostics.append(_diag("rotation.action.param_undocumented", entry, severity="error" if require_options else "warning", actor=actor, action=name, key=key))
    return tuple(diagnostics)
