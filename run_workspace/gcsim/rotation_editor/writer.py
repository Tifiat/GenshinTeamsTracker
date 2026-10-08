"""Source-preserving writes and generation from the same editor nodes."""

from __future__ import annotations

import re
from typing import Any

from .model import Document, Node, Span


class CodeGenerationError(ValueError):
    pass


def _word(value: str) -> str:
    if not value or value[0] == "-" or not all(c.isalpha() or c.isdecimal() or c in "_-%" for c in value):
        raise CodeGenerationError(f"Invalid GCSL name: {value!r}")
    return value


class Writer:
    def __init__(self, document: Document, *, preserve: bool = True):
        self.document, self.preserve = document, preserve

    def emit(self, n: Node) -> str:
        if not isinstance(n, Node):
            raise CodeGenerationError("A required node slot is missing")
        if n.kind == "hole":
            raise CodeGenerationError(f"Unfilled slot: {n.get('slot')}")
        origin = n.source_id == self.document.source_id and n.span is not None
        if origin and self.preserve and n.kind == n.original_kind:
            if n.fields == n.original_fields:
                return self.document.source[n.span.start:n.span.end]
            if n.kind in {"document", "block", "case_body"}:
                series = self.series(n)
                if series is not None:
                    return series
            patches = self.patches(n.original_fields or (), n.fields)
            if patches is not None:
                patches.sort(key=lambda item: item[0].start)
                cursor, parts = n.span.start, []
                for span, replacement in patches:
                    if span.start < cursor or not n.span.contains(span):
                        break
                    parts.append(self.document.source[cursor:span.start])
                    parts.append(self.emit(replacement))
                    cursor = span.end
                else:
                    parts.append(self.document.source[cursor:n.span.end])
                    return "".join(parts)
        text = self.canonical(n)
        if origin:
            # Structural edits can change separators. Retain comments not already
            # owned by emitted children, rather than silently dropping them.
            children = tuple(n.children())
            comments = [t.text for t in self.document.trivia if t.kind == "comment" and n.span.contains(t.span)
                        and not any(c.source_id == self.document.source_id and c.span and c.span.contains(t.span) for c in children)]
            if comments:
                text = "\n".join(comments) + "\n" + text
        return text

    def series(self, n: Node) -> str | None:
        """Keep unchanged statement trivia at its original child boundary."""
        old = dict(n.original_fields or ()).get("items")
        new = n.get("items")
        if old is None or new is None or any(key != "items" and value != n.get(key) for key, value in n.original_fields):
            return None
        if not old:
            return None
        if any(child.span is None or child.source_id != self.document.source_id for child in old):
            return None
        # List removal/replacement of the whole container falls back to the
        # canonical writer; insertion/reorder keep each retained child boundary.
        old_ids = {child.node_id for child in old}
        if not old_ids <= {child.node_id for child in new}:
            return None
        source = self.document.source
        lead = {old[0].node_id: ""}
        trailing = {child.node_id: "" for child in old}

        def split_inline(gap: str) -> tuple[str, str]:
            newline = gap.find("\n")
            first = gap if newline < 0 else gap[:newline]
            if first.lstrip(" \t\r").startswith(("#", "//")):
                end = len(gap) if newline < 0 else newline + 1
                return gap[:end], gap[end:]
            return "", gap

        for previous, current in zip(old, old[1:]):
            trailing[previous.node_id], lead[current.node_id] = split_inline(source[previous.span.end:current.span.start])
        trailing[old[-1].node_id], tail = split_inline(source[old[-1].span.end:n.span.end])
        parts = [source[n.span.start:old[0].span.start]]
        for child in new:
            if child.node_id in old_ids:
                parts.extend((lead[child.node_id], self.emit(child), trailing[child.node_id]))
            else:
                if parts and parts[-1] and not parts[-1].endswith("\n"):
                    parts.append("\n")
                text = self.emit(child)
                parts.extend((text, "" if text.endswith("\n") else "\n"))
        parts.append(tail)
        return "".join(parts)

    def patches(self, old: Any, new: Any) -> list[tuple[Span, Node]] | None:
        if old == new:
            return []
        if isinstance(old, Node) and isinstance(new, Node):
            if old.span is None or old.source_id != self.document.source_id:
                return None
            return [(old.span, new)]
        if isinstance(old, tuple) and isinstance(new, tuple) and len(old) == len(new):
            patches = []
            for before, after in zip(old, new):
                result = self.patches(before, after)
                if result is None:
                    return None
                patches.extend(result)
            return patches
        return None

    def canonical(self, n: Node) -> str:
        emit = self.emit
        kind = n.kind
        if kind in {"document", "case_body"}:
            return "\n".join(emit(item) for item in n.get("items"))
        if kind == "block":
            return "{\n" + "\n".join(emit(item) for item in n.get("items")) + "\n}"
        if kind == "name":
            return _word(n.get("value"))
        if kind == "number":
            value = n.get("value")
            if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", value):
                raise CodeGenerationError("Number requires an unsigned GCSL decimal spelling")
            return value
        if kind == "boolean":
            if n.get("value") not in {"true", "false"}:
                raise CodeGenerationError("Invalid boolean")
            return n.get("value")
        if kind == "string":
            # GCSIM keeps escape sequences literally, rather than JSON-decoding
            # them. The node deliberately stores the quoted GCSL lexeme.
            value = n.get("value")
            if not isinstance(value, str) or not re.fullmatch(r'"(?:[^"\\\n]|\\[^\n])*"', value):
                raise CodeGenerationError("String requires a quoted, single-line GCSL lexeme")
            return value
        if kind == "field":
            parts = n.get("path")
            if not parts or any(not p or p[0] in "0123456789" or not all(c.isalpha() or c.isdecimal() or c in "_-%" for c in p) for p in parts):
                raise CodeGenerationError("Invalid field path")
            return "." + ".".join(parts)
        if kind == "group":
            return "(" + emit(n.get("value")) + ")"
        if kind == "unary":
            if n.get("operator") not in {"!", "-"}:
                raise CodeGenerationError("Unknown unary operator")
            return n.get("operator") + "(" + emit(n.get("value")) + ")"
        if kind == "binary":
            from .syntax import PRECEDENCE
            if n.get("operator") not in PRECEDENCE:
                raise CodeGenerationError("Unknown binary operator")
            return "(" + emit(n.get("left")) + " " + n.get("operator") + " " + emit(n.get("right")) + ")"
        if kind == "call":
            return "(" + emit(n.get("function")) + ")(" + ", ".join(emit(a) for a in n.get("arguments")) + ")"
        if kind == "entry":
            return emit(n.get("key")) + "=" + emit(n.get("value"))
        if kind == "configured_name":
            return emit(n.get("name")) + emit(n.get("parameters"))
        if kind == "level_pair":
            return emit(n.get("base")) + "/" + emit(n.get("maximum"))
        if kind == "map":
            return "[" + ", ".join(emit(e) for e in n.get("entries")) + "]"
        if kind == "type":
            if n.get("value") not in {"number", "string", "map"}:
                raise CodeGenerationError("Unknown type")
            return n.get("value")
        if kind == "function_type":
            return "fn(" + ", ".join(emit(a) for a in n.get("arguments")) + ")" + (" " + emit(n.get("result")) if n.get("result") else "")
        if kind == "parameter":
            return emit(n.get("name")) + (" " + emit(n.get("annotation")) if n.get("annotation") else "")
        if kind == "function_expr":
            return ("fn" if n.get("anonymous", True) else "") + "(" + ", ".join(emit(p) for p in n.get("parameters")) + ")" + (" " + emit(n.get("result")) if n.get("result") else "") + " " + emit(n.get("body"))
        if kind == "function":
            return "fn " + emit(n.get("name")) + emit(n.get("function"))
        if kind == "active":
            return "active " + emit(n.get("actor")) + ";"
        if kind == "action_line":
            return emit(n.get("actor")) + " " + ", ".join(emit(a) for a in n.get("actions")) + ";"
        if kind == "action":
            action = emit(n.get("name"))
            if action not in self.document.dialect.actions:
                raise CodeGenerationError("Action is not part of the selected dialect")
            return action + (emit(n.get("parameters")) if n.get("parameters") else "") + (":" + emit(n.get("repeat")) if n.get("repeat") else "")
        if kind == "let":
            return "let " + emit(n.get("name")) + (" " + emit(n.get("annotation")) if n.get("annotation") else "") + " = " + emit(n.get("value")) + ";"
        if kind == "assign":
            return emit(n.get("name")) + " = " + emit(n.get("value")) + (";" if n.get("terminated", True) else "")
        if kind == "expression_stmt":
            return emit(n.get("value")) + ";"
        if kind == "return":
            return "return " + emit(n.get("value")) + ";"
        if kind == "control":
            if n.get("value") not in {"break", "continue", "fallthrough"}:
                raise CodeGenerationError("Unknown control statement")
            return n.get("value") + ";"
        if kind == "if":
            return "if " + emit(n.get("condition")) + " " + emit(n.get("then")) + (" else " + emit(n.get("otherwise")) if n.get("otherwise") else "")
        if kind == "while":
            return "while " + emit(n.get("condition")) + " " + emit(n.get("body"))
        if kind == "for":
            if n.get("condition") is None:
                if n.get("initial") is not None or n.get("post") is not None:
                    raise CodeGenerationError("GCSIM requires a condition in a nonempty for header")
                header = ""
            else:
                header = (emit(n.get("initial")).rstrip().removesuffix(";") + "; " if n.get("initial") else "") + emit(n.get("condition"))
                if n.get("post"):
                    header += "; " + emit(n.get("post")).rstrip().removesuffix(";")
            return "for " + header + " " + emit(n.get("body"))
        if kind == "switch":
            return "switch " + (emit(n.get("condition")) + " " if n.get("condition") else "") + "{\n" + "\n".join(emit(c) for c in n.get("cases")) + "\n}"
        if kind == "case":
            return ("case " + emit(n.get("condition")) if n.get("condition") else "default") + ":\n" + emit(n.get("body"))
        if kind == "setting":
            return ("+" if n.get("plus") else "") + emit(n.get("key")) + ("=" + ",".join(emit(v) for v in n.get("values")) if n.get("values") else "")
        if kind == "setup":
            prefix = (emit(n.get("actor")) + " " if n.get("actor") else "") + emit(n.get("directive"))
            if n.get("selector") and n.get("selector").get("value") not in {"weapon", "set"}:
                prefix += " " + emit(n.get("selector"))
            return prefix + " " + " ".join(emit(e) for e in n.get("entries")) + ";"
        if kind == "unknown" and n.span is not None and n.source_id == self.document.source_id:
            return self.document.source[n.span.start:n.span.end]
        raise CodeGenerationError(f"Unsupported node: {kind}")


def write(document: Document, *, preserve: bool = True) -> str:
    if any(child.kind == "hole" for child in document.root.walk()):
        raise CodeGenerationError("Document contains unfilled slots")
    return Writer(document, preserve=preserve).emit(document.root)
