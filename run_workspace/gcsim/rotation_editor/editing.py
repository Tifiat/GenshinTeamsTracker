"""Structural edits on source nodes, including projected character windows.

A readable window is a range in an existing statement list, never a new AST.
"""

from dataclasses import dataclass

from .model import Document, Node, node
from .readable import ReadableNode
from .semantics import analyze


@dataclass(frozen=True)
class Selection:
    node_id: str
    kind: str = ""
    member_ids: tuple[str, ...] = ()

    @classmethod
    def from_view(cls, view: ReadableNode):
        def walk(item):
            yield item.node_id
            for child in item.children:
                yield from walk(child)
        return cls(view.node_id, view.kind, tuple(walk(view)))


def _location(document: Document, selection: Selection):
    """Return owner/list/index range; grouped windows include hidden swaps."""
    meaning = analyze(document)
    selected = document.find(selection.node_id)
    for parent in meaning.ancestors(selected.node_id):
        for field, value in parent.fields:
            if not isinstance(value, tuple) or selected not in value:
                continue
            start = value.index(selected)
            end = start + 1
            if selection.kind == "window":
                for member_id in selection.member_ids:
                    for candidate in (meaning.nodes[member_id], *meaning.ancestors(member_id)):
                        if candidate in value:
                            end = max(end, value.index(candidate) + 1)
                            break
            return parent, field, start, end
    raise ValueError("Select an editable statement or action")


def _items(document, parent, field, values):
    return document.replace(parent.node_id, parent.changed(**{field: tuple(values)}))


def remove(document: Document, selection: Selection) -> Document:
    selected = document.find(selection.node_id)
    if selected.kind in {"block", "case_body"}:
        return document.replace(selected.node_id, selected.changed(items=()))
    parent, field, start, end = _location(document, selection)
    values = parent.get(field)
    if field == "actions" and len(values) == end - start:
        return remove(document, Selection(parent.node_id))
    return _items(document, parent, field, values[:start] + values[end:])


def move(document: Document, selection: Selection, direction: int) -> Document:
    if direction not in {-1, 1}:
        raise ValueError("Move one neighboring block at a time")
    parent, field, start, end = _location(document, selection)
    values = parent.get(field)
    if direction == -1:
        if start == 0:
            raise ValueError("Already first in this block")
        changed = values[:start - 1] + values[start:end] + values[start - 1:start] + values[end:]
    else:
        if end == len(values):
            raise ValueError("Already last in this block")
        changed = values[:start] + values[end:end + 1] + values[start:end] + values[end + 1:]
    return _items(document, parent, field, changed)


def insert(document: Document, selection: Selection | None, statement: Node) -> Document:
    """Containers receive children; leaves receive a following sibling."""
    current = document.find(selection.node_id) if selection else document.root
    if current.kind in {"document", "block", "case_body"}:
        return _items(document, current, "items", current.get("items") + (statement,))
    if current.kind == "hole" and current.get("slot") == "body":
        return document.replace(current.node_id, node("block", items=(statement,)))
    if current.kind in {"for", "while", "if"} and selection.kind != "window":
        body = current.get("then" if current.kind == "if" else "body")
        return insert(document, Selection(body.node_id), statement)
    parent, field, start, end = _location(document, selection)
    if field == "actions":
        # Split a multi-action line at the clicked action. Retain the original
        # parent for the first segment and source-linked action children.
        actions = parent.get("actions")
        head = parent.changed(actions=actions[:end])
        tail = node("action_line", actor=parent.get("actor"), actions=actions[end:]) if end < len(actions) else None
        owner, slot, position, stop = _location(document, Selection(parent.node_id))
        values = owner.get(slot)
        return _items(document, owner, slot, values[:position] + (head, statement) + ((tail,) if tail else ()) + values[stop:])
    values = parent.get(field)
    return _items(document, parent, field, values[:end] + (statement,) + values[end:])


def wrap(document: Document, selection: Selection, container: Node) -> Document:
    """Wrap an explicit selected range, e.g. an action in a new condition."""
    parent, field, start, end = _location(document, selection)
    values = parent.get(field)
    members = values[start:end]
    if field == "actions":
        members = (node("action_line", actor=parent.get("actor"), actions=members),)
    slot = "then" if container.kind == "if" else "body"
    if container.kind not in {"if", "while", "for"}:
        raise ValueError("Select a condition or cycle template")
    container = container.changed(**{slot: node("block", items=members)})
    if field != "actions":
        return _items(document, parent, field, values[:start] + (container,) + values[end:])
    owner, slot, position, stop = _location(document, Selection(parent.node_id))
    lines = []
    if start:
        lines.append(parent.changed(actions=values[:start]))
    lines.append(container)
    if end < len(values):
        lines.append(node("action_line", actor=parent.get("actor"), actions=values[end:]))
    siblings = owner.get(slot)
    return _items(document, owner, slot, siblings[:position] + tuple(lines) + siblings[stop:])
