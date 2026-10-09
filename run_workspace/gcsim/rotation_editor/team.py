"""Explicit selected-team boundary; never infer membership from rotation code."""

from dataclasses import dataclass
from collections.abc import Callable, Mapping
from contextlib import closing
from pathlib import Path
import sqlite3

from .model import Diagnostic, Document, Span


@dataclass(frozen=True)
class TeamMember:
    key: str
    name: str
    source_id: str = ""
    constellation: int | None = None
    weapon: str | None = None
    refinement: int | None = None


@dataclass(frozen=True)
class TeamContext:
    scope: str
    members: tuple[TeamMember, ...] = ()
    unresolved: tuple[str, ...] = ()

    @property
    def keys(self):
        return tuple(member.key for member in self.members)

    @property
    def binding(self):
        return self.scope, tuple((member.key, member.source_id, member.constellation) for member in self.members), self.unresolved

    @property
    def search_binding(self):
        return self.binding, tuple((member.weapon, member.refinement) for member in self.members)


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def from_selected_team(payload: Mapping, *, scope: str,
                       lookup: Callable[[str], Mapping] | None = None) -> TeamContext:
    """Virtual keys are explicit; fresh stored account mapping wins snapshots."""
    members, unresolved = [], []
    for slot in payload.get("slots", ()):
        virtual = _mapping(_mapping(slot).get("gcsim_virtual_override"))
        if virtual:
            character = _mapping(virtual.get("character"))
            key = str(character.get("gcsim_key") or "")
            source_id = "virtual:" + key
            constellation = character.get("constellation")
            weapon = _mapping(virtual.get("weapon"))
            weapon_key = str(weapon.get("gcsim_key") or "") or None
        else:
            details = _mapping(_mapping(slot).get("character_details_data"))
            character = _mapping(details.get("account_character")) or _mapping(_mapping(slot).get("character"))
            if not character:
                continue
            source_id = str(character.get("character_id") or character.get("id") or "")
            # With a supplied authoritative reader, missing/ambiguous DB rows
            # cannot be overridden by an old snapshot's guessed identity.
            identity = _mapping(lookup(source_id)) if lookup else character
            key = str(identity.get("gcsim_character_key") or "") if identity.get("gcsim_character_key_status") == "ready" else ""
            constellation = character.get("constellation")
            weapon = _mapping(details.get("account_weapon")) or _mapping(_mapping(slot).get("weapon"))
            weapon_key = (str(weapon.get("gcsim_weapon_key") or "") or None) if weapon.get("gcsim_weapon_key_status") == "ready" else None
        if not key:
            unresolved.append(source_id or str(slot.get("slot_index", "")))
            continue
        amount = constellation if type(constellation) is int and 0 <= constellation <= 6 else None
        refinement = weapon.get("refinement")
        refinement = refinement if type(refinement) is int and 1 <= refinement <= 5 else None
        members.append(TeamMember(key, str(character.get("name") or key), source_id, amount, weapon_key, refinement))
    if len(members) > 4 or len({item.key for item in members}) != len(members):
        return TeamContext(scope, (), tuple(unresolved) + ("duplicate_or_oversized_team",))
    return TeamContext(scope, tuple(members), tuple(unresolved))


def load_selected_team(payload: Mapping, *, scope: str, database: Path) -> TeamContext:
    """At most four identity lookups; mode=ro prevents creation or migration."""
    rows = {}
    account_ids = []
    for slot in payload.get("slots", ()):
        if _mapping(slot).get("gcsim_virtual_override"):
            continue
        details = _mapping(_mapping(slot).get("character_details_data"))
        character = _mapping(details.get("account_character")) or _mapping(_mapping(slot).get("character"))
        value = str(character.get("character_id") or character.get("id") or "")
        if value:
            account_ids.append(value)
    if account_ids and len(account_ids) <= 4:
        try:
            with closing(sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True, timeout=0.25)) as conn:
                conn.row_factory = sqlite3.Row
                for value in account_ids:
                    row = conn.execute("SELECT character_id, gcsim_character_key, gcsim_character_key_status FROM account_characters WHERE character_id=? LIMIT 1", (value,)).fetchone()
                    if row:
                        rows[value] = dict(row)
        except (OSError, sqlite3.Error):
            rows.clear()
    return from_selected_team(payload, scope=scope, lookup=lambda value: rows.get(value, {}))


def validate_team(document: Document, allowed_actors) -> tuple[Diagnostic, ...]:
    allowed = {document.dialect.character_aliases.get(key, key) for key in allowed_actors}
    diagnostics = []
    for item in document.root.walk():
        actor = None
        if item.kind in {"action_line", "active", "setup"} and item.get("actor"):
            actor = item.get("actor").get("value")
        elif item.kind == "field":
            path = item.get("path")
            if path and path[0] in document.dialect.character_aliases:
                actor = path[0]
            elif len(path) == 3 and path[:2] == ("keys", "char"):
                actor = path[2]
        if actor is not None:
            stable = document.dialect.character_aliases.get(actor, actor)
            if stable not in allowed:
                diagnostics.append(Diagnostic("rotation.team.outside", item.span or Span(0, 0), details=(("actor", stable),)))
    return tuple(diagnostics)
