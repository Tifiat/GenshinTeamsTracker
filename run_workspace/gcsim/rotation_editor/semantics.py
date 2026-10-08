"""Recognized user blocks backed by the existing source tree.

Patterns are deliberately conservative. Recognition never rewrites an import;
explicit edits lower the same user concepts into the ordinary GCSL tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .model import Document, Node, conditional, node


# Comparisons in the selected evaluator convert integers to float64. Stay in
# the exactly represented range, including the final post increment.
MAX_EXACT = 2**53 - 2
BUILTINS = frozenset("f rand randnorm print wait sleep delay type execute_action set_target_pos set_player_pos set_default_target set_swap_icd set_particle_delay kill_target is_target_dead pick_up_crystallize set_starting_verdant_dew sin cos asin acos is_even set_on_tick".split())


def ungroup(value: Node | None) -> Node | None:
    while value is not None and value.kind == "group":
        value = value.get("value")
    return value


def name(value: Node | None) -> str | None:
    value = ungroup(value)
    return value.get("value") if value is not None and value.kind == "name" else None


def integer(value: Node | None) -> int | None:
    value = ungroup(value)
    if value is not None and value.kind == "unary" and value.get("operator") == "-":
        positive = integer(value.get("value"))
        return -positive if positive is not None else None
    if value is None or value.kind != "number":
        return None
    raw = value.get("value").lstrip("0") or "0"
    if not raw.isascii() or not raw.isdigit() or len(raw) > 16:
        return None
    result = int(raw)
    return result if result <= MAX_EXACT else None


def number(value: int) -> Node:
    return node("number", value=str(value)) if value >= 0 else node("unary", operator="-", value=node("number", value=str(-value)))


def binary(left: Node, operator: str, right: Node) -> Node:
    return node("binary", left=left, operator=operator, right=right)


def linear_offset(value: Node | None, counter: str) -> int | None:
    """Recognize counter + integer, without evaluating arbitrary expressions."""
    value = ungroup(value)
    if name(value) == counter:
        return 0
    if value is None or value.kind != "binary":
        return None
    left, right = value.get("left"), value.get("right")
    if value.get("operator") == "+":
        for variable, constant in ((left, right), (right, left)):
            offset, amount = linear_offset(variable, counter), integer(constant)
            if offset is not None and amount is not None:
                result = offset + amount
                return result if abs(result) <= MAX_EXACT else None
    if value.get("operator") == "-":
        offset, amount = linear_offset(left, counter), integer(right)
        if offset is not None and amount is not None:
            result = offset - amount
            return result if abs(result) <= MAX_EXACT else None
    return None


@dataclass(frozen=True)
class Cycle:
    node_id: str
    body_id: str
    counter: str | None
    start: int
    count: int | None
    limit_id: str | None = None
    inclusive: bool = False
    may_break: bool = False
    parent_cycle_id: str | None = None


@dataclass(frozen=True)
class ScheduleChoice:
    mode: str = "every"
    every: int = 1
    first: int = 1
    positions: tuple[int, ...] = ()

    def validate(self, count: int | None) -> None:
        if self.mode == "selected":
            if not self.positions or len(self.positions) > 256 or len(set(self.positions)) != len(self.positions):
                raise ValueError("Select distinct rotation numbers")
            if any(type(value) is not int or value < 1 or value > MAX_EXACT or count is not None and value > count for value in self.positions):
                raise ValueError("Selected rotation is outside the cycle")
        elif self.mode == "every":
            if any(type(value) is not int or not 1 <= value <= MAX_EXACT for value in (self.every, self.first)):
                raise ValueError("Interval and first rotation must be positive integers")
            if count is not None and self.first > count:
                raise ValueError("The schedule would not run in this cycle")
        else:
            raise ValueError("Unknown rotation schedule")

    def includes(self, ordinal: int) -> bool:
        return ordinal in self.positions if self.mode == "selected" else ordinal >= self.first and (ordinal - self.first) % self.every == 0


@dataclass(frozen=True)
class Schedule:
    node_id: str
    cycle_id: str
    choice: ScheduleChoice


def _own_break(value: Node, nested: int = 0) -> bool:
    if value.kind in {"function", "function_expr"}:
        return False
    if value.kind == "control" and value.get("value") == "break":
        return nested == 0
    if value.kind == "switch":
        # The selected evaluator consumes breaks from cases, but forwards
        # the default block's result to the enclosing loop.
        return any(_own_break(case.get("body"), nested + (case.get("condition") is not None)) for case in value.get("cases"))
    nested += value.kind in {"while", "for"}
    return any(_own_break(child, nested) for child in value.children())


class Meaning:
    """A disposable source-linked index, never a second editable document."""

    def __init__(self, document: Document):
        self.document = document
        self.nodes = {item.node_id: item for item in document.root.walk()}
        self.parents: dict[str, str] = {}
        for parent in self.nodes.values():
            for child in parent.children():
                self.parents[child.node_id] = parent.node_id
        self.bound_names = {name(item.get("name")) for item in self.nodes.values() if item.kind in {"assign", "let", "function", "parameter"}}
        self.callbacks = any(item.kind == "call" and name(item.get("function")) == "set_on_tick" for item in self.nodes.values())
        self.cycles: dict[str, Cycle] = {}
        self.schedules: dict[str, Schedule] = {}
        for item in document.root.walk():
            if item.kind in {"for", "while"}:
                cycle = self._cycle(item)
                if cycle is not None:
                    self.cycles[item.node_id] = cycle
            elif item.kind == "if":
                for cycle in self.ancestor_cycles(item.node_id):
                    if cycle.counter is None:
                        continue
                    choice = self._schedule(item.get("condition"), cycle)
                    if choice is not None:
                        self.schedules[item.node_id] = Schedule(item.node_id, cycle.node_id, choice)
                        break

    def ancestors(self, node_id: str) -> Iterable[Node]:
        while node_id in self.parents:
            node_id = self.parents[node_id]
            yield self.nodes[node_id]

    def ancestor_cycles(self, node_id: str) -> Iterable[Cycle]:
        for ancestor in self.ancestors(node_id):
            if ancestor.kind in {"function", "function_expr"}:
                break
            if ancestor.node_id in self.cycles:
                yield self.cycles[ancestor.node_id]

    def _cycle(self, value: Node) -> Cycle | None:
        body = value.get("body")
        parent = next(self.ancestor_cycles(value.node_id), None)
        parent_id = parent.node_id if parent else None
        condition = ungroup(value.get("condition"))
        forever = condition is None or integer(condition) == 1 or condition.kind == "boolean" and condition.get("value") == "true"
        if forever and value.get("initial") is None and value.get("post") is None:
            if any(child.kind in {"return", "unknown"} for child in body.walk()):
                return None
            return Cycle(value.node_id, body.node_id, None, 1, None, may_break=_own_break(body), parent_cycle_id=parent_id)
        if value.kind != "for" or self.callbacks:
            return None
        initial, post = value.get("initial"), value.get("post")
        if initial is None or initial.kind != "let" or initial.get("annotation") is not None or post is None:
            return None
        counter, start = name(initial.get("name")), integer(initial.get("value"))
        if counter is None or start is None or start < 0 or name(post.get("name")) != counter or linear_offset(post.get("value"), counter) != 1:
            return None
        if condition is None or condition.kind != "binary" or condition.get("operator") not in {"<", "<="} or name(condition.get("left")) != counter:
            return None
        limit = integer(condition.get("right"))
        if limit is None or limit < 0 or max(start, limit) >= MAX_EXACT:
            return None
        # The safe first family does not cross counter shadowing, closures,
        # user calls, callbacks or overrides of the action interpreter.
        for child in body.walk():
            if child.kind in {"unknown", "function", "function_expr", "return"}:
                return None
            if child.kind in {"assign", "let"} and name(child.get("name")) == counter:
                return None
            if child.kind == "action_line" and "execute_action" in self.bound_names:
                return None
            if child.kind == "call":
                called = name(child.get("function"))
                if called not in BUILTINS or called in self.bound_names or called == "set_on_tick":
                    return None
        inclusive = condition.get("operator") == "<="
        count = max(0, limit - start + int(inclusive))
        return Cycle(value.node_id, body.node_id, counter, start, count, condition.get("right").node_id, inclusive, _own_break(body), parent_id)

    def _schedule(self, value: Node, cycle: Cycle) -> ScheduleChoice | None:
        def safe_offset(expression: Node) -> int | None:
            offset = linear_offset(expression, cycle.counter)
            if offset is None:
                return None
            # Bound intermediate sums as well as the final value. Equality
            # in GCSL compares float64, even for integer expressions.
            last = cycle.start + max(0, cycle.count - 1)
            for part in expression.walk():
                intermediate = linear_offset(part, cycle.counter)
                if intermediate is not None and max(abs(cycle.start + intermediate), abs(last + intermediate)) > MAX_EXACT:
                    return None
            return offset

        value = ungroup(value)
        negate = value.kind == "unary" and value.get("operator") == "!"
        test = ungroup(value.get("value")) if negate else value
        if test.kind == "call" and name(test.get("function")) == "is_even" and "is_even" not in self.bound_names:
            args = test.get("arguments")
            offset = safe_offset(args[0]) if len(args) == 1 else None
            if offset is not None:
                first = 1 if (cycle.start + offset) % 2 == int(negate) else 2
                return ScheduleChoice(every=2, first=first)
        if negate:
            return None
        if value.kind == "boolean" and value.get("value") == "true":
            return ScheduleChoice()

        def selected(expression: Node) -> tuple[int, ...] | None:
            expression = ungroup(expression)
            if expression.kind == "binary" and expression.get("operator") == "||":
                left, right = selected(expression.get("left")), selected(expression.get("right"))
                return left + right if left is not None and right is not None else None
            if expression.kind == "binary" and expression.get("operator") == "==":
                for variable, constant in ((expression.get("left"), expression.get("right")), (expression.get("right"), expression.get("left"))):
                    offset, target = safe_offset(variable), integer(constant)
                    if offset is not None and target is not None:
                        return (target - offset - cycle.start + 1,)
            return None

        positions = selected(value)
        if positions is not None:
            choice = ScheduleChoice("selected", positions=tuple(sorted(set(positions))))
            try:
                choice.validate(cycle.count)
                return choice
            except ValueError:
                return None
        # Canonical every-Nth shape: ordinal >= first AND
        # (ordinal-first) == ((ordinal-first)/N)*N. No modulo exists in GCSL.
        first = None
        equality = value
        if value.kind == "binary" and value.get("operator") == "&&":
            guard, equality = ungroup(value.get("left")), ungroup(value.get("right"))
            if guard.kind != "binary" or guard.get("operator") != ">=" or safe_offset(guard.get("left")) != 1 - cycle.start:
                return None
            first = integer(guard.get("right"))
            if first is None or first < 1:
                return None
        if equality.kind != "binary" or equality.get("operator") != "==":
            return None
        for raw, multiplied in ((equality.get("left"), equality.get("right")), (equality.get("right"), equality.get("left"))):
            offset = safe_offset(raw)
            product = ungroup(multiplied)
            if offset is None or product.kind != "binary" or product.get("operator") != "*":
                continue
            divisor = integer(product.get("right"))
            divided = ungroup(product.get("left"))
            if divisor is None or divisor <= 0 or divided.kind != "binary" or divided.get("operator") != "/" or integer(divided.get("right")) != divisor or safe_offset(divided.get("left")) != offset:
                continue
            if first is not None and offset == 1 - cycle.start - first:
                return ScheduleChoice(every=divisor, first=first)
            if first is None and offset == 1 - cycle.start:
                return ScheduleChoice(every=divisor, first=divisor)
        return None


def analyze(document: Document) -> Meaning:
    return Meaning(document)


def _count(value: int) -> None:
    if type(value) is not int or not 1 <= value < MAX_EXACT:
        raise ValueError("Cycle count must be a positive exact integer")


def make_cycle(document: Document, count: int | None, body: Node | None = None) -> Node:
    """Create a user cycle using ordinary GCSL nodes; no hidden persisted model."""
    body = body if body is not None else node("hole", slot="body")
    if count is None:
        return node("while", condition=node("boolean", value="true"), body=body)
    _count(count)
    occupied = {name(item) for root in (document.root, body) for item in root.walk() if item.kind == "name"}
    counter = "_rotation"
    suffix = 1
    while counter in occupied or document.dialect.category(counter) != "identifier":
        counter = f"_rotation{suffix}"
        suffix += 1
    return node("for", initial=node("let", name=node("name", value=counter), annotation=None, value=number(1)),
                condition=binary(node("name", value=counter), "<=", number(count)),
                post=node("assign", name=node("name", value=counter), value=binary(node("name", value=counter), "+", number(1)), terminated=False), body=body)


def schedule_condition(cycle: Cycle, choice: ScheduleChoice) -> Node:
    choice.validate(cycle.count)
    if cycle.counter is None:
        raise ValueError("This cycle has no editable rotation counter")

    def ordinal() -> Node:
        counter = node("name", value=cycle.counter)
        return counter if cycle.start == 1 else binary(counter, "+", number(1 - cycle.start))

    if choice.mode == "selected":
        conditions = [binary(ordinal(), "==", number(position)) for position in sorted(choice.positions)]
        result = conditions[0]
        for condition in conditions[1:]:
            result = binary(result, "||", condition)
        return result
    if choice.every == choice.first == 1:
        return node("boolean", value="true")

    def offset() -> Node:
        return binary(ordinal(), "-", number(choice.first))

    multiple = binary(offset(), "==", binary(binary(offset(), "/", number(choice.every)), "*", number(choice.every)))
    return binary(binary(ordinal(), ">=", number(choice.first)), "&&", multiple)


def make_schedule(document: Document, cycle_id: str, choice: ScheduleChoice, body: Node | None = None) -> Node:
    cycle = analyze(document).cycles.get(cycle_id)
    if cycle is None:
        raise ValueError("Select a recognized cycle")
    return conditional(schedule_condition(cycle, choice), body)


def set_cycle_count(document: Document, cycle_id: str, count: int) -> Document:
    _count(count)
    meaning = analyze(document)
    cycle = meaning.cycles.get(cycle_id)
    if cycle is None or cycle.limit_id is None:
        raise ValueError("This cycle count cannot be changed through a simple option")
    for schedule in meaning.schedules.values():
        if schedule.cycle_id == cycle_id:
            schedule.choice.validate(count)
    limit = cycle.start + count - int(cycle.inclusive)
    if limit >= MAX_EXACT:
        raise ValueError("Cycle bound exceeds the exact integer range")
    return document.replace(cycle.limit_id, number(limit))


def set_schedule(document: Document, schedule_id: str, choice: ScheduleChoice) -> Document:
    meaning = analyze(document)
    schedule = meaning.schedules.get(schedule_id)
    if schedule is None:
        raise ValueError("Select a recognized rotation schedule")
    condition = document.find(schedule_id).get("condition")
    return document.replace(condition.node_id, schedule_condition(meaning.cycles[schedule.cycle_id], choice))
