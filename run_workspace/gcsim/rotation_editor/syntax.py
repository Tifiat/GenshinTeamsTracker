"""Lossless GCSL frontend; grammar follows the audited v2.45.0 parser.

It preserves syntax instead of lowering actions to execute_action or folding
constants. A successful parse is not a simulator/type/readiness verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
from types import MappingProxyType
from typing import Mapping

from .model import Diagnostic, Document, Node, Span, Token


ACTIONS = frozenset("skill burst attack charge high_plunge low_plunge aim dash jump walk swap".split())
KEYWORDS = frozenset("let while if else fn switch case default break continue fallthrough return for options add char stats weapon set lvl refine cons talent count params label until active target particle_threshold particle_drop_count particle_element resist energy hurt".split())
STATS = frozenset("def% def hp hp% atk atk% er em cr cd heal pyro% hydro% cryo% electro% anemo% geo% phys% dendro% atkspd% dmg%".split())
ELEMENTS = frozenset("electro pyro cryo hydro frozen anemo dendro geo physical none".split())
PRECEDENCE = {"||": 1, "&&": 2, "==": 3, "!=": 3, "<>": 3, ">": 4, ">=": 4, "<": 4, "<=": 4, "+": 5, "-": 5, "*": 6, "/": 6}


@dataclass(frozen=True, slots=True)
class Dialect:
    character_aliases: Mapping[str, str]
    # Rich mechanics descriptions require an explicitly audited profile.
    identity: str = "gcsl-syntax-v1"
    actions: frozenset[str] = ACTIONS
    keywords: frozenset[str] = KEYWORDS
    stats: frozenset[str] = STATS
    elements: frozenset[str] = ELEMENTS

    def __post_init__(self) -> None:
        object.__setattr__(self, "character_aliases", MappingProxyType(dict(self.character_aliases)))

    def category(self, word: str) -> str:
        if word in self.keywords:
            return "keyword"
        if word in {"true", "false"}:
            return "boolean"
        if word in self.stats:
            return "stat"
        if word in self.elements:
            return "element"
        if word in self.character_aliases:
            return "character"
        if word in self.actions:
            return "action"
        return "identifier"


def _word_char(char: str) -> bool:
    return char.isalpha() or char.isdecimal() or char in "_-%"


def tokenize(source: str, dialect: Dialect) -> tuple[tuple[Token, ...], tuple[Token, ...]]:
    tokens, trivia = [], []
    pos = 0
    while pos < len(source):
        start, char = pos, source[pos]
        if char in " \t\r\n":
            pos += 1
            while pos < len(source) and source[pos] in " \t\r\n":
                pos += 1
            trivia.append(Token("whitespace", source[start:pos], Span(start, pos)))
            continue
        if char == "#" or source.startswith("//", pos):
            pos = source.find("\n", pos)
            if pos < 0:
                pos = len(source)
            trivia.append(Token("comment", source[start:pos], Span(start, pos)))
            continue
        if char == '"':
            pos += 1
            closed = False
            while pos < len(source) and source[pos] != "\n":
                if source[pos] == "\\":
                    if pos + 1 >= len(source) or source[pos + 1] == "\n":
                        break
                    pos += 2
                elif source[pos] == '"':
                    pos += 1
                    closed = True
                    break
                else:
                    pos += 1
            tokens.append(Token("string" if closed else "error", source[start:pos], Span(start, pos)))
            continue
        if char.isascii() and char.isdigit() or char == "." and pos + 1 < len(source) and source[pos + 1].isascii() and source[pos + 1].isdigit():
            while pos < len(source) and source[pos].isascii() and source[pos].isdigit():
                pos += 1
            if pos < len(source) and source[pos] == ".":
                pos += 1
                while pos < len(source) and source[pos].isascii() and source[pos].isdigit():
                    pos += 1
            tokens.append(Token("number", source[start:pos], Span(start, pos)))
            continue
        if char == ".":
            pos += 1
            while pos < len(source) and _word_char(source[pos]):
                pos += 1
            tokens.append(Token("field" if pos > start + 1 else "symbol", source[start:pos], Span(start, pos)))
            continue
        # A leading '-' is an operator; inside a word it is part of the name,
        # exactly as in GCSIM ('i-1' is a name, 'i - 1' is subtraction).
        if _word_char(char) and char != "-":
            pos += 1
            while pos < len(source) and _word_char(source[pos]):
                pos += 1
            word = source[start:pos]
            tokens.append(Token(dialect.category(word), word, Span(start, pos)))
            continue
        pair = source[pos:pos + 2]
        if pair in {"==", "!=", "<>", ">=", "<=", "&&", "||"}:
            pos += 2
        else:
            pos += 1
        text = source[start:pos]
        tokens.append(Token("symbol" if text in PRECEDENCE or text in "=;:,()[]{}!" else "error", text, Span(start, pos)))
    tokens.append(Token("eof", "", Span(len(source), len(source))))
    return tuple(tokens), tuple(trivia)


class ParseFailure(Exception):
    def __init__(self, token: Token, expected: str):
        self.token, self.expected = token, expected


class Parser:
    def __init__(self, source: str, dialect: Dialect):
        self.source, self.dialect = source, dialect
        self.tokens, self.trivia = tokenize(source, dialect)
        self.source_id = sha256(source.encode("utf-8")).hexdigest()
        self.pos = 0
        self.diagnostics: list[Diagnostic] = []

    @property
    def current(self) -> Token:
        return self.tokens[self.pos]

    def take(self, text: str | None = None, kind: str | None = None) -> Token:
        token = self.current
        if text is not None and token.text != text or kind is not None and token.kind != kind:
            raise ParseFailure(token, text or kind or "token")
        if token.kind == "eof":
            raise ParseFailure(token, text or kind or "token")
        self.pos += 1
        return token

    def accept(self, text: str) -> bool:
        if self.current.text == text:
            self.pos += 1
            return True
        return False

    def make(self, kind: str, start: int, **fields: object) -> Node:
        end = self.tokens[self.pos - 1].span.end if self.pos else start
        items = tuple(fields.items())
        return Node(kind, items, span=Span(start, end), source_id=self.source_id,
                    original_kind=kind, original_fields=items)

    def name(self, *, kind: str | None = None) -> Node:
        token = self.take(kind=kind)
        return self.make("name", token.span.start, value=token.text)

    def fail(self, expected: str) -> None:
        raise ParseFailure(self.current, expected)

    def safe_statement(self, top: bool) -> Node:
        start_index, start = self.pos, self.current.span.start
        try:
            return self.statement(top)
        except (ParseFailure, RecursionError) as failure:
            token = failure.token if isinstance(failure, ParseFailure) else self.current
            expected = failure.expected if isinstance(failure, ParseFailure) else "shallower nesting"
            self.diagnostics.append(Diagnostic("rotation.syntax", token.span, details=(("expected", expected), ("found", token.text or "EOF"))))
            self.pos = start_index
            depth = 0
            while self.current.kind != "eof":
                text = self.current.text
                if text == "}" and depth == 0 and not top:
                    break
                self.pos += 1
                if text == "{":
                    depth += 1
                elif text == "}":
                    depth -= 1
                    if depth <= 0:
                        break
                elif text == ";" and depth == 0:
                    break
            if self.pos == start_index and self.current.kind != "eof":
                self.pos += 1
            return self.make("unknown", start)

    def document(self) -> Document:
        items = []
        while self.current.kind != "eof":
            items.append(self.safe_statement(True))
        root = self.make("document", 0, items=tuple(items))
        # The document includes trailing whitespace/comments even with no nodes.
        from dataclasses import replace
        root = replace(root, span=Span(0, len(self.source)))
        return Document(self.source, root, self.dialect, tuple(self.diagnostics), self.trivia)

    def statement(self, top: bool = False, *, semi: bool = True) -> Node:
        start, token = self.current.span.start, self.current
        word = token.text
        if top and word == "active":
            self.take()
            actor = self.name(kind="character")
            self.take(";")
            return self.make("active", start, actor=actor)
        if top and (word in {"options", "target", "energy", "hurt"} or token.kind == "character" and self.tokens[self.pos + 1].text in {"char", "add"}):
            return self.setup()
        if word == "{":
            return self.block()
        if word == "if":
            self.take()
            condition, then = self.expression(), self.block()
            otherwise = None
            if self.accept("else"):
                if self.current.text not in {"if", "{"}:
                    self.fail("if or block")
                otherwise = self.statement()
            return self.make("if", start, condition=condition, then=then, otherwise=otherwise)
        if word == "while":
            self.take()
            condition, body = self.expression(), self.block()
            return self.make("while", start, condition=condition, body=body)
        if word == "for":
            self.take()
            initial = condition = post = None
            if self.current.text != "{":
                if self.current.text == "let" or self.current.kind == "identifier" and self.tokens[self.pos + 1].text == "=":
                    initial = self.statement(semi=True)
                condition = self.expression()
                if self.accept(";") and self.current.text != "{":
                    post = self.assignment()
            body = self.block()
            return self.make("for", start, initial=initial, condition=condition, post=post, body=body)
        if word == "switch":
            self.take()
            condition = None if self.current.text == "{" else self.expression()
            self.take("{")
            cases = []
            while self.current.text != "}":
                case_start = self.current.span.start
                case_kind = self.take().text
                if case_kind not in {"case", "default"}:
                    raise ParseFailure(self.tokens[self.pos - 1], "case or default")
                test = self.expression() if case_kind == "case" else None
                colon = self.take(":")
                items = []
                while self.current.text not in {"case", "default", "}"} and self.current.kind != "eof":
                    items.append(self.safe_statement(False))
                body = self.make("case_body", colon.span.end, items=tuple(items))
                cases.append(self.make("case", case_start, condition=test, body=body))
            self.take("}")
            return self.make("switch", start, condition=condition, cases=tuple(cases))
        if word == "fn":
            self.take()
            name = self.name(kind="identifier")
            function = self.function(self.current.span.start, anonymous=False)
            return self.make("function", start, name=name, function=function)
        if token.kind == "character":
            actor = self.name(kind="character")
            actions = []
            while True:
                action_start = self.current.span.start
                name = self.name(kind="action")
                parameters = self.mapping() if self.current.text == "[" else None
                repeat = None
                if self.accept(":"):
                    count = self.take(kind="number")
                    if not count.text.isascii() or not count.text.isdigit() or len(count.text.lstrip("0")) > 19 or len(count.text.lstrip("0")) == 19 and count.text.lstrip("0") > "9223372036854775807":
                        raise ParseFailure(count, "integer repeat count")
                    repeat = self.make("number", count.span.start, value=count.text)
                actions.append(self.make("action", action_start, name=name, parameters=parameters, repeat=repeat))
                if not self.accept(","):
                    break
            self.take(";")
            return self.make("action_line", start, actor=actor, actions=tuple(actions))
        if word == "let":
            self.take()
            name = self.name(kind="identifier")
            annotation = self.type_expr() if self.current.text != "=" else None
            self.take("=")
            value = self.expression()
            kind, fields = "let", {"name": name, "annotation": annotation, "value": value}
        elif word in {"break", "continue", "fallthrough"}:
            self.take()
            kind, fields = "control", {"value": word}
        elif word == "return":
            self.take()
            kind, fields = "return", {"value": self.expression()}
        elif token.kind == "identifier" and self.tokens[self.pos + 1].text == "=":
            result = self.assignment()
            if semi:
                self.take(";")
                result = self.make("assign", start, name=result.get("name"), value=result.get("value"), terminated=True)
            return result
        else:
            kind, fields = "expression_stmt", {"value": self.expression()}
        if semi:
            self.take(";")
        return self.make(kind, start, **fields)

    def assignment(self) -> Node:
        start = self.current.span.start
        name = self.name(kind="identifier")
        self.take("=")
        return self.make("assign", start, name=name, value=self.expression(), terminated=False)

    def block(self) -> Node:
        start = self.take("{").span.start
        items = []
        while self.current.text != "}":
            if self.current.kind == "eof":
                self.fail("}")
            items.append(self.safe_statement(False))
        self.take("}")
        return self.make("block", start, items=tuple(items))

    def type_expr(self) -> Node:
        start, word = self.current.span.start, self.current.text
        if word in {"number", "string", "map"}:
            self.take(kind="identifier")
            return self.make("type", start, value=word)
        self.take("fn")
        self.take("(")
        arguments = []
        if self.current.text != ")":
            while True:
                arguments.append(self.type_expr())
                if not self.accept(","):
                    break
        self.take(")")
        result = self.type_expr() if self.current.text in {"number", "string", "map", "fn"} else None
        return self.make("function_type", start, arguments=tuple(arguments), result=result)

    def function(self, start: int, *, anonymous: bool = True) -> Node:
        self.take("(")
        parameters = []
        if self.current.text != ")":
            while True:
                parameter_start = self.current.span.start
                name = self.name(kind="identifier")
                annotation = self.type_expr() if self.current.text not in {",", ")"} else None
                parameters.append(self.make("parameter", parameter_start, name=name, annotation=annotation))
                if not self.accept(","):
                    break
        self.take(")")
        result = self.type_expr() if self.current.text != "{" else None
        body = self.block()
        return self.make("function_expr", start, parameters=tuple(parameters), result=result, body=body, anonymous=anonymous)

    def expression(self, minimum: int = 0, *, stop_at_param_flag: bool = False) -> Node:
        start, token = self.current.span.start, self.current
        if token.kind in {"number", "boolean", "string"}:
            self.take()
            if token.kind == "number" and not math.isfinite(float(token.text)):
                raise ParseFailure(token, "finite float64 or int64 number")
            left = self.make(token.kind, start, value=token.text)
        elif token.kind == "identifier":
            left = self.name(kind="identifier")
        elif token.kind == "field":
            parts = []
            while self.current.kind == "field":
                parts.append(self.take().text[1:])
            left = self.make("field", start, path=tuple(parts))
        elif token.text in {"!", "-"}:
            self.take()
            left = self.make("unary", start, operator=token.text, value=self.expression(7, stop_at_param_flag=stop_at_param_flag))
        elif token.text == "(":
            self.take()
            value = self.expression()
            self.take(")")
            left = self.make("group", start, value=value)
        elif token.text == "[":
            left = self.mapping()
        elif token.text == "fn":
            self.take()
            left = self.function(start)
        else:
            self.fail("expression")
        while True:
            if stop_at_param_flag and self.current.text == "+" and self.tokens[self.pos + 1].text == "params":
                break
            if self.current.text == "(" and minimum < 8:
                self.take()
                arguments = []
                if self.current.text != ")":
                    while True:
                        arguments.append(self.expression())
                        if not self.accept(","):
                            break
                self.take(")")
                left = self.make("call", start, function=left, arguments=tuple(arguments))
                continue
            precedence = PRECEDENCE.get(self.current.text, 0)
            if precedence <= minimum:
                break
            operator = self.take().text
            right = self.expression(precedence, stop_at_param_flag=stop_at_param_flag)
            left = self.make("binary", start, left=left, operator=operator, right=right)
        return left

    def mapping(self) -> Node:
        start = self.take("[").span.start
        entries = []
        if self.current.text != "]":
            while True:
                entry_start = self.current.span.start
                key = self.name(kind="identifier")
                self.take("=")
                value = self.expression()
                entries.append(self.make("entry", entry_start, key=key, value=value))
                if not self.accept(","):
                    break
        self.take("]")
        return self.make("map", start, entries=tuple(entries))

    def setup(self) -> Node:
        """Retain ordered setup entries; semantic validation stays a separate layer.

        This accepts the declarative envelope, not every directive's value rules.
        It does not flatten level/talent tuples or mistake setup for runtime code.
        """
        start = self.current.span.start
        actor = self.name(kind="character") if self.current.kind == "character" else None
        directive = self.name()
        selector = None
        if directive.get("value") == "add":
            if self.current.text not in {"weapon", "set", "stats"}:
                self.fail("weapon, set or stats")
            selector = self.name()
        elif directive.get("value") in {"energy", "hurt"}:
            if self.current.text in {"every", "once"}:
                selector = self.name(kind="identifier")
            elif self.current.text != ";":
                self.fail("every, once or ;")
        entries = []
        if selector is not None and selector.get("value") in {"weapon", "set"}:
            self.take("=")
            value = self.expression(stop_at_param_flag=True)
            entries.append(self.make("setting", selector.span.start, key=selector, values=(value,), plus=False))
        while self.current.text != ";":
            if self.current.kind == "eof":
                self.fail(";")
            entry_start = self.current.span.start
            plus = self.accept("+")
            if self.current.text == "random":
                random = self.name()
                entries.append(self.make("setting", entry_start, key=random, values=(), plus=plus))
                continue
            if self.current.kind not in {"identifier", "keyword", "stat", "element"}:
                self.fail("setting key")
            key = self.name()
            self.take("=")
            # Bare setup labels/elements (human, slimes, physical, ...) are
            # not script identifiers. They must remain distinct literal names.
            values = []
            if key.get("value") == "lvl" and actor is not None and (directive.get("value") == "char" or selector is not None and selector.get("value") == "weapon"):
                value_start = self.current.span.start
                base = self.take(kind="number")
                base_node = self.make("number", base.span.start, value=base.text)
                self.take("/")
                maximum = self.take(kind="number")
                maximum_node = self.make("number", maximum.span.start, value=maximum.text)
                values.append(self.make("level_pair", value_start, base=base_node, maximum=maximum_node))
                entries.append(self.make("setting", entry_start, key=key, values=tuple(values), plus=plus))
                continue
            while True:
                if self.current.kind in {"identifier", "keyword", "stat", "element", "character", "action"}:
                    value_start = self.current.span.start
                    value = self.name()
                    if self.current.text == "[":
                        value = self.make("configured_name", value_start, name=value, parameters=self.mapping())
                    values.append(value)
                else:
                    values.append(self.expression(stop_at_param_flag=True))
                if not self.accept(","):
                    break
            entries.append(self.make("setting", entry_start, key=key, values=tuple(values), plus=plus))
        self.take(";")
        return self.make("setup", start, actor=actor, directive=directive, selector=selector, entries=tuple(entries))


def parse(source: str, dialect: Dialect) -> Document:
    if not isinstance(source, str):
        raise TypeError("GCSL source must be text")
    if len(source.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("Rotation exceeds the 2 MiB editor input limit")
    return Parser(source, dialect).document()
