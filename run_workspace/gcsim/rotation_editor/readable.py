"""Structured readable projection with source links and conservative actor flow.

Texts come through the injected project translator; names through an injected
stable-key resolver. This module never loads account settings or a name DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from .model import Diagnostic, Document, Node, Span
from .writer import Writer


SYSTEM_FUNCTIONS = frozenset("f rand randnorm print wait sleep delay type execute_action set_target_pos set_player_pos set_default_target set_swap_icd set_particle_delay kill_target is_target_dead pick_up_crystallize set_starting_verdant_dew sin cos asin acos is_even set_on_tick".split())
Translate = Callable[..., str]
ActorState = frozenset[str] | None


@dataclass(frozen=True, slots=True)
class ReadableNode:
    kind: str
    text: str
    node_id: str
    span: Span | None
    children: tuple[ReadableNode, ...] = ()
    actor_key: str | None = None

    def lines(self, indent: int = 0) -> list[str]:
        result = ["  " * indent + self.text] if self.text else []
        for child in self.children:
            result.extend(child.lines(indent + (1 if self.text else 0)))
        return result


@dataclass(frozen=True, slots=True)
class ReadableDocument:
    items: tuple[ReadableNode, ...]
    diagnostics: tuple[Diagnostic, ...]
    syntax_complete: bool

    def text(self) -> str:
        return "\n".join(line for item in self.items for line in item.lines())


class Renderer:
    def __init__(self, document: Document, translate: Translate, *,
                 resolve_name: Callable[[str], str | None] | None = None,
                 field_descriptions: Mapping[str, str] | None = None):
        self.document, self.tr = document, translate
        self.resolve_name = resolve_name or (lambda key: None)
        self.field_descriptions = field_descriptions or {}
        self.writer = Writer(document)
        self.assigned = {n.get("name").get("value") for n in document.root.walk() if n.kind == "assign"}
        self.action_override = "execute_action" in self.assigned

    def name(self, key: str) -> str:
        return self.resolve_name(key) or key

    def view(self, n: Node, text: str, children: tuple[ReadableNode, ...] = (), *, kind: str | None = None, actor: str | None = None) -> ReadableNode:
        return ReadableNode(kind or n.kind, text, n.node_id, n.span, children, actor)

    def builtin(self, call: Node, bound: frozenset[str]) -> str | None:
        function = call.get("function")
        while function.kind == "group":
            function = function.get("value")
        name = function.get("value") if function.kind == "name" else None
        return name if name in SYSTEM_FUNCTIONS and name not in self.assigned and name not in bound else None

    def changes_actor(self, n: Node, bound: frozenset[str]) -> bool:
        if n.kind in {"function", "function_expr"}:
            return False
        return (n.kind == "call" and self.builtin(n, bound) in {None, "execute_action", "set_on_tick"}
                or any(self.changes_actor(child, bound) for child in n.children()))

    def ends_sequence(self, n: Node) -> bool:
        """Recognize unconditional local control flow, without executing tests."""
        if n.kind in {"return", "control"}:
            return True
        if n.kind in {"block", "case_body"}:
            return any(self.ends_sequence(child) for child in n.get("items"))
        if n.kind == "if" and n.get("otherwise"):
            return self.ends_sequence(n.get("then")) and self.ends_sequence(n.get("otherwise"))
        return False

    def expression(self, n: Node, bound: frozenset[str] = frozenset()) -> str:
        tr, expr = self.tr, lambda child: self.expression(child, bound)
        kind = n.kind
        if kind == "hole":
            return tr("rotation.hole." + n.get("slot"))
        if kind in {"name", "number", "string"}:
            return n.get("value")
        if kind == "boolean":
            return tr("rotation." + n.get("value"))
        if kind == "group":
            return "(" + expr(n.get("value")) + ")"
        if kind == "field":
            path = n.get("path")
            raw = "." + ".".join(path)
            # These interpretations are tied to the audited language version.
            if self.document.dialect.identity == "gcsim-v2.45.0-gcsl":
                if len(path) == 1 and path[0] in {"stam", "state", "previous-char", "previous-action", "airborne", "dew", "verdant-dew", "moonridge-dew"}:
                    return tr("rotation.field." + path[0])
                if len(path) == 2 and path[0] == "status":
                    return tr("rotation.field.global_status", effect=path[1])
                if path and path[0] in self.document.dialect.character_aliases:
                    actor = self.name(self.document.dialect.character_aliases[path[0]])
                    if len(path) == 2 and path[1] in {"energy", "energymax", "hp", "hpmax", "hpratio", "onfield", "bol", "bolratio", "cons", "normal", "id", "weapon"}:
                        return tr("rotation.field." + path[1], actor=actor)
                    if len(path) == 3 and path[1] in {"infusion", "tags", "stats", "sets"}:
                        label = {"infusion": "infusion", "tags": "tag", "stats": "stat", "sets": "set"}[path[1]]
                        return tr("rotation.field." + label, actor=actor, effect=path[2])
                    if path[0] == "chasca" and len(path) == 3 and path[1] == "nightsoul" and path[2] in {"state", "points", "duration"}:
                        return tr("rotation.field.nightsoul." + path[2], actor=actor)
                    if len(path) == 3 and path[1] in {"status", "mods"}:
                        effect = tr("rotation.favonius_cd") if path[2] == "favonius-cd" else path[2]
                        return tr("rotation.field.duration", actor=actor, effect=effect)
                    if len(path) == 3 and path[1] in self.document.dialect.actions and path[2] in {"ready", "cd", "charge"}:
                        return tr("rotation.field.action_" + path[2], actor=actor, action=tr("rotation.action." + path[1]))
                    if len(path) == 2 and self.document.dialect.character_aliases[path[0]] == "chasca" and path[1] in {f"bullet{i}" for i in range(1, 7)}:
                        return tr("rotation.field.bullet", actor=actor, index=path[1][-1])
                    if len(path) == 2 and self.document.dialect.character_aliases[path[0]] == "furina" and path[1] in {"fanfare", "ousia", "c6-count"}:
                        return tr("rotation.field.furina." + path[1], actor=actor)
            if raw in self.field_descriptions:
                return tr("rotation.field.documented", code=raw, description=self.field_descriptions[raw])
            return tr("rotation.field.raw", code=raw)
        if kind == "unary":
            return (tr("rotation.not") if n.get("operator") == "!" else "−") + " (" + expr(n.get("value")) + ")"
        if kind == "binary":
            operator = {"&&": tr("rotation.and"), "||": tr("rotation.or"), "<>": "≠", "!=": "≠", "==": "="}.get(n.get("operator"), n.get("operator"))
            return "(" + expr(n.get("left")) + " " + operator + " " + expr(n.get("right")) + ")"
        if kind == "call":
            builtin = self.builtin(n, bound)
            arguments = tuple(expr(arg) for arg in n.get("arguments"))
            if builtin in {"wait", "sleep", "delay"} and len(arguments) == 1:
                return tr("rotation.call." + ("wait" if builtin == "sleep" else builtin), frames=arguments[0])
            if builtin == "f" and not arguments:
                return tr("rotation.field.f")
            if builtin and self.document.dialect.identity == "gcsim-v2.45.0-gcsl":
                return tr("rotation.builtin", description=tr("rotation.builtin." + builtin), function=builtin, arguments=", ".join(arguments))
            return tr("rotation.call", function=expr(n.get("function")), arguments=", ".join(arguments))
        if kind == "entry":
            return expr(n.get("key")) + " = " + expr(n.get("value"))
        if kind == "map":
            entries = n.get("entries")
            last = {entry.get("key").get("value"): index for index, entry in enumerate(entries)}
            return "[" + "; ".join(expr(entry) if last[entry.get("key").get("value")] == index else tr("rotation.overwritten", value=expr(entry)) for index, entry in enumerate(entries)) + "]"
        if kind == "function_expr":
            text = tr("rotation.function_value", arguments=", ".join(expr(p) for p in n.get("parameters")))
            return text + (tr("rotation.result_type", value=expr(n.get("result"))) if n.get("result") else "")
        if kind in {"type", "function_type"}:
            return self.writer.emit(n)
        if kind == "parameter":
            return expr(n.get("name")) + (": " + expr(n.get("annotation")) if n.get("annotation") else "")
        if kind == "configured_name":
            return expr(n.get("name")) + expr(n.get("parameters"))
        return self.writer.emit(n)

    def action_text(self, actor: str, n: Node, bound: frozenset[str]) -> str:
        action = n.get("name").get("value")
        text = self.tr("rotation.action." + action)
        if n.get("parameters"):
            entries = n.get("parameters").get("entries")
            last = {entry.get("key").get("value"): index for index, entry in enumerate(entries)}
            for index, entry in enumerate(entries):
                key, value = entry.get("key").get("value"), self.expression(entry.get("value"), bound)
                literal = entry.get("value")
                while literal.kind == "group":
                    literal = literal.get("value")
                known = self.document.dialect.identity == "gcsim-v2.45.0-gcsl"
                label = None
                if known and actor == "bennett" and action == "skill" and key == "hold" and literal.kind == "number" and literal.get("value") in {"0", "1", "2"}:
                    label = self.tr("rotation.bennett.hold." + literal.get("value"))
                elif known and actor == "chasca" and action == "aim" and key == "bullets":
                    label = self.tr("rotation.chasca.bullets", value=value)
                elif known and key == "travel":
                    label = self.tr("rotation.parameter.travel", value=value)
                part = label or self.tr("rotation.parameter", parameter=key, value=value)
                text += "; " + (self.tr("rotation.overwritten", value=part) if last[key] != index else part)
        if n.get("repeat"):
            text = self.tr("rotation.repeat", action=text, count=self.expression(n.get("repeat"), bound))
        return text

    def sequence(self, items: tuple[Node, ...], state: ActorState, bound: frozenset[str] = frozenset()) -> tuple[tuple[ReadableNode, ...], ActorState]:
        output: list[ReadableNode] = []
        window_items: list[ReadableNode] = []
        window_actor: str | None = None
        window_anchor: Node | None = None

        def flush() -> None:
            nonlocal window_actor, window_anchor
            if window_anchor is not None:
                output.append(self.view(window_anchor, self.tr("rotation.window", actor=self.name(window_actor)), tuple(window_items), kind="window", actor=window_actor))
            window_items.clear()
            window_actor = window_anchor = None

        def append(view: ReadableNode, owner: Node, actor: str | None) -> None:
            nonlocal window_actor, window_anchor
            if actor is None:
                flush()
                output.append(view)
                return
            if window_actor != actor:
                flush()
                window_actor, window_anchor = actor, owner
            if view.text:
                window_items.append(view)

        def sole(current: ActorState) -> str | None:
            return next(iter(current)) if current and len(current) == 1 else None

        def union(a: ActorState, b: ActorState) -> ActorState:
            return a | b if a is not None and b is not None else None

        for index, n in enumerate(items):
            if n.kind == "active":
                # Initial active is a global setting; its final occurrence was
                # resolved before traversing the executable order.
                continue
            if n.kind == "action_line":
                actor = self.document.dialect.character_aliases.get(n.get("actor").get("value"), n.get("actor").get("value"))
                for action in n.get("actions"):
                    if action.get("repeat") and not action.get("repeat").get("value").lstrip("0"):
                        append(self.view(action, self.tr("rotation.zero_repeat", actor=self.name(actor), action=self.action_text(actor, action, bound))), n, sole(state))
                        continue
                    if self.action_override:
                        flush()
                        output.append(self.view(action, self.tr("rotation.overridden_action", actor=self.name(actor), action=self.action_text(actor, action, bound))))
                        state = None
                    else:
                        text = self.action_text(actor, action, bound)
                        simple_swap = action.get("name").get("value") == "swap" and action.get("parameters") is None and action.get("repeat") is None
                        append(self.view(action, "" if simple_swap else text), n, actor)
                        state = frozenset({actor})
                continue
            if n.kind in {"if", "while", "for", "switch", "block", "function"}:
                flush()
                if n.kind == "if":
                    incoming = None if self.changes_actor(n.get("condition"), bound) else state
                    if n.get("then").kind == "hole":
                        yes, yes_state = (self.view(n.get("then"), self.expression(n.get("then"), bound)),), None
                    else:
                        yes, yes_state = self.sequence(n.get("then").get("items", ()), incoming, bound)
                    branches = [self.view(n.get("then"), self.tr("rotation.then"), yes, kind="branch")]
                    no_state = incoming
                    if n.get("otherwise"):
                        other = n.get("otherwise")
                        no, no_state = self.sequence(other.get("items") if other.kind == "block" else (other,), incoming, bound)
                        branches.append(self.view(other, self.tr("rotation.else"), no, kind="branch"))
                    output.append(self.view(n, self.tr("rotation.if", condition=self.expression(n.get("condition"), bound)), tuple(branches)))
                    state = union(yes_state, no_state)
                elif n.kind in {"while", "for"}:
                    # Zero iterations and later iterations are both possible.
                    body = n.get("body")
                    actors = {self.document.dialect.character_aliases[c.get("actor").get("value")] for c in body.walk() if c.kind == "action_line"}
                    loop_state = union(state, frozenset(actors)) if actors else state
                    if self.changes_actor(n, bound) or self.action_override:
                        loop_state = None
                    loop_bound = bound
                    if n.kind == "for" and n.get("initial") and n.get("initial").kind == "let":
                        loop_bound |= {n.get("initial").get("name").get("value")}
                    if body.kind == "hole":
                        children = (self.view(body, self.expression(body, loop_bound)),)
                    else:
                        children, _ = self.sequence(body.get("items", ()), loop_state, loop_bound)
                    condition = self.expression(n.get("condition"), loop_bound) if n.get("condition") else self.tr("rotation.true")
                    if n.kind == "for":
                        pieces = []
                        if n.get("initial"):
                            pieces.append(self.view(n.get("initial"), self.tr("rotation.initialize", value=self.simple(n.get("initial"), bound))))
                        pieces.append(self.view(body, self.tr("rotation.body"), children))
                        if n.get("post"):
                            pieces.append(self.view(n.get("post"), self.tr("rotation.after_iteration", value=self.simple(n.get("post"), loop_bound))))
                        children = tuple(pieces)
                    output.append(self.view(n, self.tr("rotation.loop", condition=condition), children))
                    state = loop_state
                elif n.kind == "switch":
                    branches, possible = [], state
                    defaults = [case.node_id for case in n.get("cases") if case.get("condition") is None]
                    for case in n.get("cases"):
                        children, end = self.sequence(case.get("body").get("items"), None, bound)
                        label = self.tr("rotation.case", value=self.expression(case.get("condition"), bound)) if case.get("condition") else self.tr("rotation.default")
                        if case.get("condition") is None and case.node_id != defaults[-1]:
                            label = self.tr("rotation.overwritten", value=label)
                        branches.append(self.view(case, label, children))
                        possible = union(possible, end)
                    test = self.expression(n.get("condition"), bound) if n.get("condition") else self.tr("rotation.first_true")
                    output.append(self.view(n, self.tr("rotation.switch", value=test), tuple(branches)))
                    state = possible
                elif n.kind == "function":
                    fn = n.get("function")
                    parameters = frozenset(p.get("name").get("value") for p in fn.get("parameters"))
                    children, _ = self.sequence(fn.get("body").get("items"), None, bound | parameters)
                    label = self.tr("rotation.function", name=n.get("name").get("value"), arguments=", ".join(self.expression(p, bound) for p in fn.get("parameters")))
                    if fn.get("result"):
                        label += self.tr("rotation.result_type", value=self.expression(fn.get("result"), bound))
                    output.append(self.view(n, label, children))
                    bound |= {n.get("name").get("value")}
                else:
                    children, state = self.sequence(n.get("items"), state, bound)
                    output.append(self.view(n, self.tr("rotation.scope"), children))
                if self.ends_sequence(n):
                    if index + 1 < len(items):
                        tail, _ = self.sequence(items[index + 1:], None, bound)
                        output.append(self.view(items[index + 1], self.tr("rotation.unreachable_branches"), tail, kind="unreachable"))
                    state = None
                    break
                continue
            if n.kind == "setup":
                flush()
                output.append(self.view(n, self.tr("rotation.setup", value=self.writer.emit(n))))
                continue
            text = self.simple(n, bound)
            details = []
            # Anonymous function values have bodies too; a short textual label
            # must never make that code disappear from the readable projection.
            def anonymous_values(value: Node):
                if value.kind == "function_expr" and value.get("anonymous", True):
                    yield value
                    return
                for child in value.children():
                    yield from anonymous_values(child)

            for value in anonymous_values(n):
                if value.kind == "function_expr" and value.get("anonymous", True):
                    parameters = frozenset(p.get("name").get("value") for p in value.get("parameters"))
                    children, _ = self.sequence(value.get("body").get("items"), None, bound | parameters)
                    details.append(self.view(value, self.expression(value, bound), children))
            append(self.view(n, text, tuple(details)), n, sole(state))
            if n.kind in {"unknown", "hole", "control"} or self.changes_actor(n, bound):
                flush()
                state = None
            if n.kind == "let":
                bound |= {n.get("name").get("value")}
            if n.kind in {"return", "control"}:
                flush()
                if index + 1 < len(items):
                    tail, _ = self.sequence(items[index + 1:], None, bound)
                    output.append(self.view(items[index + 1], self.tr("rotation.unreachable", control=text), tail, kind="unreachable"))
                state = None
                break
        flush()
        return tuple(output), state

    def simple(self, n: Node, bound: frozenset[str]) -> str:
        if n.kind in {"let", "assign"}:
            annotation = self.expression(n.get("annotation"), bound) if n.get("annotation") else ""
            return self.tr("rotation." + n.kind, name=n.get("name").get("value"), value=self.expression(n.get("value"), bound), annotation=annotation)
        if n.kind == "return":
            return self.tr("rotation.return", value=self.expression(n.get("value"), bound))
        if n.kind == "control":
            return self.tr("rotation.control." + n.get("value"))
        if n.kind == "expression_stmt":
            return self.expression(n.get("value"), bound)
        if n.kind == "hole":
            return self.tr("rotation.hole." + n.get("slot"))
        if n.kind == "unknown":
            return self.tr("rotation.unknown", code=self.writer.emit(n))
        return self.tr("rotation.setup", value=self.writer.emit(n))

    def render(self) -> ReadableDocument:
        active = [n for n in self.document.root.get("items") if n.kind == "active"]
        initial = self.document.dialect.character_aliases[active[-1].get("actor").get("value")] if active else None
        items, _ = self.sequence(self.document.root.get("items"), frozenset({initial}) if initial else None)
        if not initial:
            items = (self.view(self.document.root, self.tr("rotation.missing_active"), kind="diagnostic"),) + items
        return ReadableDocument(items, self.document.diagnostics, self.document.syntax_complete)


def render(document: Document, translate: Translate, **kwargs: object) -> ReadableDocument:
    return Renderer(document, translate, **kwargs).render()
