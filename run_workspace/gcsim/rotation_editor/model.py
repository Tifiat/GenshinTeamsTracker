"""One source-linked tree for code, readable output and future structured edits."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Any, Iterator
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Span:
    """Half-open Python character offsets, not GCSIM UTF-8 byte offsets."""

    start: int
    end: int

    def contains(self, other: Span) -> bool:
        return self.start <= other.start <= other.end <= self.end


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    span: Span
    severity: str = "error"
    details: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    text: str
    span: Span


@dataclass(frozen=True, slots=True)
class Node:
    kind: str
    fields: tuple[tuple[str, Any], ...] = ()
    node_id: str = ""
    span: Span | None = None
    source_id: str | None = None
    original_kind: str | None = None
    original_fields: tuple[tuple[str, Any], ...] | None = None

    def __post_init__(self) -> None:
        if not self.node_id:
            object.__setattr__(self, "node_id", uuid4().hex)

    def get(self, name: str, default: Any = None) -> Any:
        return next((value for key, value in self.fields if key == name), default)

    def changed(self, **fields: Any) -> Node:
        unknown = fields.keys() - dict(self.fields).keys()
        if unknown:
            raise ValueError(f"Unknown slots for {self.kind}: {sorted(unknown)}")
        return replace(self, fields=tuple((key, fields.get(key, value)) for key, value in self.fields))

    def children(self) -> Iterator[Node]:
        for _, value in self.fields:
            if isinstance(value, Node):
                yield value
            elif isinstance(value, tuple):
                yield from (item for item in value if isinstance(item, Node))

    def walk(self) -> Iterator[Node]:
        pending = [self]
        while pending:
            current = pending.pop()
            yield current
            pending.extend(reversed(tuple(current.children())))


def node(kind: str, **fields: Any) -> Node:
    """Create an unattached typed construct; holes are explicit draft slots."""
    return Node(kind, tuple(fields.items()))


def shape(value: Any) -> Any:
    """Tree identity without source spelling, positions, IDs or redundant groups."""
    if isinstance(value, Node):
        if value.kind == "group":
            return shape(value.get("value"))
        return value.kind, tuple((key, shape(item)) for key, item in value.fields)
    if isinstance(value, tuple):
        return tuple(shape(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class Document:
    source: str
    root: Node
    dialect: Any
    diagnostics: tuple[Diagnostic, ...] = ()
    trivia: tuple[Token, ...] = ()

    @property
    def source_id(self) -> str:
        return sha256(self.source.encode("utf-8")).hexdigest()

    @property
    def syntax_complete(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics) and not any(
            n.kind in {"unknown", "hole"} for n in self.root.walk()
        )

    def find(self, node_id: str) -> Node:
        return next(n for n in self.root.walk() if n.node_id == node_id)

    def replace(self, node_id: str, replacement: Node) -> Document:
        """Edit the shared tree, retaining source provenance for a surgical write."""
        found = False
        replaced_span = None

        def visit(current: Node) -> Node:
            nonlocal found, replaced_span
            if current.node_id == node_id:
                found = True
                replaced_span = current.span
                return replace(replacement, node_id=current.node_id, span=current.span,
                               source_id=current.source_id, original_kind=current.original_kind,
                               original_fields=current.original_fields)
            fields = []
            for key, value in current.fields:
                if isinstance(value, Node):
                    value = visit(value)
                elif isinstance(value, tuple):
                    value = tuple(visit(item) if isinstance(item, Node) else item for item in value)
                fields.append((key, value))
            return replace(current, fields=tuple(fields))

        root = visit(self.root)
        if not found:
            raise KeyError(node_id)
        diagnostics = tuple(d for d in self.diagnostics if replaced_span is None or not replaced_span.contains(d.span))
        return replace(self, root=root, diagnostics=diagnostics)

    def position(self, span: Span) -> tuple[int, int]:
        return self.source.count("\n", 0, span.start) + 1, span.start - self.source.rfind("\n", 0, span.start)

    def byte_span(self, span: Span) -> Span:
        return Span(len(self.source[:span.start].encode("utf-8")), len(self.source[:span.end].encode("utf-8")))


def action(actor: str, name: str, *, parameters: Node | None = None, repeat: Node | None = None) -> Node:
    if not actor:
        raise ValueError("An explicit character selection is required")
    return node("action_line", actor=node("name", value=actor), actions=(
        node("action", name=node("name", value=name), parameters=parameters, repeat=repeat),
    ))


def conditional(condition: Node | None = None, then: Node | None = None, otherwise: Node | None = None) -> Node:
    return node("if", condition=condition or node("hole", slot="condition"),
                then=then or node("hole", slot="body"), otherwise=otherwise)


def loop(condition: Node | None = None, body: Node | None = None) -> Node:
    return node("while", condition=condition or node("hole", slot="condition"),
                body=body or node("hole", slot="body"))
