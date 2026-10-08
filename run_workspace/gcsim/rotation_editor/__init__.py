"""Isolated rotation document core. Importing it opens no settings or accounts."""

from .model import Diagnostic, Document, Node, Span, node
from .syntax import Dialect, parse
from .writer import CodeGenerationError, write

__all__ = ("CodeGenerationError", "Diagnostic", "Dialect", "Document", "Node", "Span", "node", "parse", "write")
