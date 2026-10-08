"""Read the generated character registry from an explicitly selected source tree.

This narrow adapter never imports the engine, account catalog or app settings.
The caller supplies any audited semantics profile separately from this registry.
"""

from pathlib import Path
import re

from .syntax import Dialect


def _text(path: Path) -> str:
    if path.is_symlink() or path.stat().st_size > 256 * 1024:
        raise ValueError("Unsafe or oversized character registry")
    return path.read_text(encoding="utf-8")


def load_source_dialect(engine_root: Path, *, identity: str = "gcsl-syntax-v1") -> Dialect:
    """Read only two generated public files; fail on an unfamiliar source shape."""
    root = Path(engine_root)
    keys = _text(root / "pkg/core/keys/character.dm.go")
    shortcuts = _text(root / "pkg/shortcut/character.dm.go")
    constants = re.search(r"const\s*\((.*?)\n\)", keys, re.S)
    aliases = re.search(r"var CharNameToKey = map\[string\]keys.Char\s*\{(.*?)\n\}", shortcuts, re.S)
    if constants is None or aliases is None:
        raise ValueError("Unrecognized generated character registry")
    stable = dict(re.findall(r"^\s*([A-Za-z][A-Za-z0-9]*)[^\n/]*//\s*([a-z0-9_]+)\s*$", constants.group(1), re.M))
    rows = re.findall(r'"([a-z0-9_]+)"\s*:\s*keys\.([A-Za-z][A-Za-z0-9]*)\s*,', aliases.group(1))
    if not rows or len(rows) > 1024 or any(constant not in stable for _, constant in rows):
        raise ValueError("Incomplete generated character registry")
    return Dialect({alias: stable[constant] for alias, constant in rows}, identity=identity)
