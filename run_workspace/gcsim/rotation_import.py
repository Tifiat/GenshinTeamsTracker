"""Extract a database program without adopting its builds or combat setup."""

from dataclasses import dataclass

from .optimizer_rotation_policy import normalize_optimizer_rotation_shell
from .rotation_editor import parse
from .rotation_editor.team import validate_team


@dataclass(frozen=True)
class ImportedRotation:
    source: str
    program: str
    source_setup: str
    notices: tuple[str, ...]


class RotationImportError(ValueError):
    pass


def prepare_rotation(config, current_shell, dialect, team_keys):
    """Cut only parsed setup spans; keep functions, comments and execution order.

    The current browser owns combat setup. Its existing high-HP dummy needs
    duration mode for an unbounded imported loop; use the already established
    90-second policy, explicitly reported to the importer before acceptance.
    Unknown syntax and initial character params are never silently discarded.
    """
    document = parse(config, dialect)
    current = parse(current_shell, dialect)
    if not document.syntax_complete or not current.syntax_complete:
        raise RotationImportError("rotation.import.syntax")
    if validate_team(document, team_keys):
        raise RotationImportError("rotation.editor.team_outside")
    setups = tuple(item for item in document.root.get("items") if item.kind == "setup")
    setup_ids = {item.node_id for item in setups}
    if any(item.kind == "setup" and item.node_id not in setup_ids for item in document.root.walk()):
        raise RotationImportError("rotation.import.setup_dependency")
    for setup in setups:
        if setup.get("directive").get("value") == "char" and any(
                entry.get("key").get("value") == "params" for entry in setup.get("entries")):
            raise RotationImportError("rotation.import.initial_state")
    if not any(item.kind == "active" for item in document.root.get("items")):
        raise RotationImportError("rotation.import.active_missing")
    program = config
    for item in reversed(setups):
        program = program[:item.span.start] + program[item.span.end:]
    program = program.strip()
    # Whitespace left by removed declarations is harmless; collapse only the
    # prefix, never arbitrary blank lines inside preserved functions/comments.
    environment = tuple(item for item in current.root.get("items")
                        if item.kind == "setup" and item.get("actor") is None)
    # Setup referencing old rotation variables cannot survive program replacement.
    for setup in environment:
        for entry in setup.get("entries"):
            if any(part.kind in {"call", "field", "variable"} for value in entry.get("values") for part in value.walk()):
                raise RotationImportError("rotation.import.setup_dependency")
    shell = "\n".join(current_shell[item.span.start:item.span.end] for item in environment)
    combined = shell + "\n\n" + program + "\n"
    normalized = normalize_optimizer_rotation_shell(combined)
    try:
        complete = parse(normalized.optimizer_text, dialect).syntax_complete
    except (ValueError, RecursionError) as error:
        raise RotationImportError("rotation.import.syntax") from error
    if not complete:
        raise RotationImportError("rotation.import.syntax")
    notices = ["rotation.import.own_setup"]
    if normalized.changed:
        notices.append("rotation.import.duration_mode")
    # All original setup remains available in a separate read-only preview.
    source_setup = "\n".join(config[item.span.start:item.span.end] for item in setups)
    return ImportedRotation(normalized.optimizer_text, program, source_setup, tuple(notices))
