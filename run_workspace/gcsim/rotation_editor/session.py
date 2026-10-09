"""In-memory editing/session state. The current draft never masquerades as old code."""

from __future__ import annotations

from typing import Mapping

from .model import Document, Node, shape
from .options import CharacterOptions, EngineIdentity
from .syntax import Dialect, parse
from .validation import validate_actions, validate_setup
from .writer import CodeGenerationError, write


class EditorSession:
    def __init__(self, source: str, dialect: Dialect, *, undo_limit: int = 50):
        if undo_limit < 1:
            raise ValueError("undo_limit must be positive")
        self.current = parse(source, dialect)
        self.last_complete = self.current if self.current.syntax_complete else None
        self._history: list[Document] = []
        self._redo: list[Document] = []
        self._undo_limit = undo_limit

    def _set(self, document: Document, *, parsed: bool = False) -> Document:
        self._history.append(self.current)
        self._redo.clear()
        del self._history[:-self._undo_limit]
        self.current = document
        if parsed and document.syntax_complete:
            self.last_complete = document
        return document

    def set_code(self, source: str) -> Document:
        return self._set(parse(source, self.current.dialect), parsed=True)

    def replace(self, node_id: str, replacement: Node) -> Document:
        return self._set(self.current.replace(node_id, replacement))

    def edit_structure(self, operation, *args) -> Document:
        """Apply a pure tree edit as one undo step, including incomplete slots."""
        return self._set(operation(self.current, *args))

    @property
    def can_undo(self) -> bool:
        return bool(self._history)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def edit_option(self, node_id: str, property_key: str, value: object) -> Document:
        from .context import apply_context_edit
        return self._set(apply_context_edit(self.current, node_id, property_key, value))

    def commit(self, *, character_options: Mapping[str, CharacterOptions] | None = None,
               expected_identity: EngineIdentity | None = None, require_options: bool = False) -> Document:
        """Reparse generated code and require the same shared structure."""
        if not self.current.syntax_complete:
            raise CodeGenerationError("Current draft has unsupported syntax or unfilled slots")
        code = write(self.current)
        parsed = parse(code, self.current.dialect)
        if not parsed.syntax_complete or shape(parsed.root) != shape(self.current.root):
            raise CodeGenerationError("Generated code does not round-trip to the edited document")
        diagnostics = list(validate_setup(parsed)) if parsed.dialect.identity == "gcsim-v2.45.0-gcsl" else []
        if character_options is not None or require_options:
            diagnostics.extend(validate_actions(parsed, character_options or {}, expected_identity, require_options))
        errors = [diagnostic.code for diagnostic in diagnostics if diagnostic.severity == "error"]
        if errors:
            raise CodeGenerationError("Generated code failed validation: " + ", ".join(dict.fromkeys(errors)))
        return self._set(parsed, parsed=True)

    def undo(self) -> Document:
        if self._history:
            self._redo.append(self.current)
            self.current = self._history.pop()
        return self.current

    def redo(self) -> Document:
        if self._redo:
            self._history.append(self.current)
            self.current = self._redo.pop()
        return self.current

    def code_text(self) -> str | None:
        """Current code projection, or no code while structured slots are empty."""
        try:
            return write(self.current)
        except CodeGenerationError:
            return None
