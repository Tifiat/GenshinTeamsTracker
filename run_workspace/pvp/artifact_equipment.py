"""Match-local artifact ownership over an existing, read-only seat inventory."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from hoyolab_export.account_equipment import (
    ARTIFACT_SLOT_KEYS, EquipmentChangeResult, EquipmentError, artifact_slot_key_from_pos,
)


@dataclass(slots=True)
class PvpArtifactEquipment:
    source_db_path: Path
    allowed_character_ids: frozenset[str]
    _slots_by_character: dict[str, dict[str, int]] = field(default_factory=dict, init=False)

    def artifact_ids_for_character(self, character_id: str | int) -> dict[str, int]:
        return dict(self._slots_by_character.get(str(character_id), {}))

    def get_equipped_artifact_owner(self, artifact_id: int) -> int | None:
        for character_id, slots in self._slots_by_character.items():
            if artifact_id in slots.values():
                return int(character_id)
        return None

    def toggle_artifact(self, character_id: str | int, artifact_id: int) -> EquipmentChangeResult:
        character_id = self._character_id(character_id)
        positions = self._validate_artifacts((artifact_id,))
        slot_key = positions[artifact_id]
        desired = self.artifact_ids_for_character(character_id)
        if desired.get(slot_key) == artifact_id:
            desired.pop(slot_key)
        else:
            desired[slot_key] = artifact_id
        return self._replace_slots(character_id, desired, operation="toggle_artifact")

    def apply_artifact_preset(
        self, character_id: str | int, slots_by_pos: Mapping[int, int],
    ) -> EquipmentChangeResult:
        character_id = self._character_id(character_id)
        desired = {artifact_slot_key_from_pos(pos): artifact_id for pos, artifact_id in slots_by_pos.items()}
        if len(desired) != len(slots_by_pos) or len(set(desired.values())) != len(desired):
            raise EquipmentError("Invalid duplicate PvP artifact preset slots.")
        actual = self._validate_artifacts(desired.values())
        if any(actual[artifact_id] != slot_key for slot_key, artifact_id in desired.items()):
            raise EquipmentError("PvP artifact preset references the wrong slot.")
        # Validate every reference before replacing any ownership.
        return self._replace_slots(character_id, desired, operation="apply_build_preset")

    def _character_id(self, value: str | int) -> str:
        character_id = str(value)
        if character_id not in self.allowed_character_ids:
            raise EquipmentError("PvP artifact target is outside this player's picked pool.")
        return character_id

    def _validate_artifacts(self, artifact_ids: Iterable[int]) -> dict[int, str]:
        ids = tuple(artifact_ids)
        if any(type(value) is not int or value <= 0 for value in ids):
            raise EquipmentError("Invalid PvP artifact id.")
        if not ids:
            return {}
        try:
            with closing(sqlite3.connect(self.source_db_path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
                rows = conn.execute(
                    "SELECT id, pos FROM artifacts WHERE id IN (" + ",".join("?" for _ in ids) + ")", ids,
                ).fetchall()
        except sqlite3.Error as exc:
            raise EquipmentError("PvP artifact inventory is unavailable.") from exc
        if {row[0] for row in rows} != set(ids):
            raise EquipmentError("PvP artifact is absent from this player's inventory.")
        return {row[0]: artifact_slot_key_from_pos(row[1]) for row in rows}

    def _replace_slots(
        self, character_id: str, desired: dict[str, int], *, operation: str,
    ) -> EquipmentChangeResult:
        before = {key: dict(slots) for key, slots in self._slots_by_character.items()}
        next_state = {key: dict(slots) for key, slots in before.items()}
        target = next_state.setdefault(character_id, {})
        for slot_key in ARTIFACT_SLOT_KEYS:
            old_id, new_id = target.get(slot_key), desired.get(slot_key)
            if old_id == new_id:
                continue
            target.pop(slot_key, None)
            if new_id is None:
                continue
            previous_owner = next((owner for owner, slots in next_state.items()
                                   if owner != character_id and slots.get(slot_key) == new_id), None)
            if previous_owner is not None:
                next_state[previous_owner].pop(slot_key)
                if old_id is not None:
                    next_state[previous_owner][slot_key] = old_id
            target[slot_key] = new_id
        next_state = {key: slots for key, slots in next_state.items() if slots}
        affected = {key for key in set(before) | set(next_state) if before.get(key, {}) != next_state.get(key, {})}
        artifact_ids = {
            artifact_id for key in affected
            for slots in (before.get(key, {}), next_state.get(key, {}))
            for artifact_id in slots.values()
        }
        self._slots_by_character = next_state
        return EquipmentChangeResult(
            operation=operation, changed=bool(affected), message="pvp_scoped",
            affected_character_ids=tuple(sorted(int(key) for key in affected)),
            affected_artifact_ids=tuple(sorted(artifact_ids)),
        )


__all__ = ["PvpArtifactEquipment"]
