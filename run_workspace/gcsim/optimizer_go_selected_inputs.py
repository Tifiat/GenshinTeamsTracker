"""Narrow, production-owned input boundary for the Go Selected optimizer.

This module intentionally contains only the current fixed-4p equipment snapshot,
the config/equipment identity check, and the optimizer energy policy.  It must
not import the historical Python search or trace-analysis packages.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
import math
from pathlib import Path
import re
import sqlite3
from typing import Any

from .optimizer_artifact_database import GcsimOptimizerArtifactDatabaseInput
from .optimizer_artifact_materializer import (
    materialize_gcsim_optimizer_artifact_stat_vector,
)
from .optimizer_go_contracts import canonical_sha256
from .optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimOptimizerWearerArtifactAssignment,
    GcsimOptimizerWearerIdentity,
)


SELECTED_EQUIPPED_SNAPSHOT_SCHEMA_VERSION = 1
SELECTED_EQUIPPED_SNAPSHOT_KIND = "gtt.optimizer.selected_equipped_snapshot"

_OPTIONS_RE = re.compile(r"(?im)^\s*options\b[^;]*;")
_STAT_TOKEN_RE = re.compile(r"(?P<key>[a-z]+%?)=(?P<value>[-+0-9.eE]+)")
_STATS_RE = re.compile(
    r"(?im)^\s*(?P<actor>[a-z0-9_]+)\s+add\s+stats\s+(?P<body>[^;]+);"
)
_SET_RE = re.compile(
    r'(?im)^\s*(?P<actor>[a-z0-9_]+)\s+add\s+set="(?P<set>[^"]+)"'
    r"\s+count=(?P<count>\d+);"
)


class GcsimOptimizerGoSelectedInputError(ValueError):
    """The prepared config and current equipment do not describe one state."""


@dataclass(frozen=True, slots=True)
class SelectedEquippedWearer:
    wearer: GcsimOptimizerWearerIdentity
    assignment: GcsimOptimizerWearerArtifactAssignment
    target_set_uid: str
    target_set_count: int
    set_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise GcsimOptimizerGoSelectedInputError("selected wearer is invalid")
        if not isinstance(self.assignment, GcsimOptimizerWearerArtifactAssignment):
            raise GcsimOptimizerGoSelectedInputError("selected assignment is invalid")
        if self.assignment.wearer != self.wearer:
            raise GcsimOptimizerGoSelectedInputError(
                "selected wearer/assignment mismatch"
            )
        if not self.target_set_uid or self.target_set_uid.strip() != self.target_set_uid:
            raise GcsimOptimizerGoSelectedInputError("selected target set is invalid")
        if self.target_set_count not in (4, 5):
            raise GcsimOptimizerGoSelectedInputError(
                "selected target set count must be four or five"
            )
        if (
            tuple(sorted(self.set_counts)) != self.set_counts
            or any(not uid or count <= 0 for uid, count in self.set_counts)
            or sum(count for _uid, count in self.set_counts) != 5
            or dict(self.set_counts).get(self.target_set_uid) != self.target_set_count
        ):
            raise GcsimOptimizerGoSelectedInputError(
                "selected equipped set counts are invalid"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "wearer": self.wearer.to_dict(),
            "assignment": self.assignment.to_dict(),
            "target_set_uid": self.target_set_uid,
            "target_set_count": self.target_set_count,
            "set_counts": dict(self.set_counts),
        }


@dataclass(frozen=True, slots=True)
class SelectedEquippedTeamSnapshot:
    artifact_database_input_sha256: str
    equipment_rows_sha256: str
    character_keys: tuple[str, ...]
    wearers: tuple[SelectedEquippedWearer, ...]
    engine_call_count: int = 0
    schema_version: int = SELECTED_EQUIPPED_SNAPSHOT_SCHEMA_VERSION
    kind: str = SELECTED_EQUIPPED_SNAPSHOT_KIND

    def __post_init__(self) -> None:
        if self.schema_version != SELECTED_EQUIPPED_SNAPSHOT_SCHEMA_VERSION:
            raise GcsimOptimizerGoSelectedInputError("snapshot schema mismatch")
        if self.kind != SELECTED_EQUIPPED_SNAPSHOT_KIND:
            raise GcsimOptimizerGoSelectedInputError("snapshot kind mismatch")
        _require_sha256(
            self.artifact_database_input_sha256,
            "artifact_database_input_sha256",
        )
        _require_sha256(self.equipment_rows_sha256, "equipment_rows_sha256")
        if (
            len(self.character_keys) != 4
            or len(set(self.character_keys)) != 4
            or any(not key or key != key.strip() for key in self.character_keys)
        ):
            raise GcsimOptimizerGoSelectedInputError(
                "snapshot requires four character keys"
            )
        if len(self.wearers) != 4:
            raise GcsimOptimizerGoSelectedInputError("snapshot requires four wearers")
        if tuple(row.wearer.team_slot for row in self.wearers) != (1, 2, 3, 4):
            raise GcsimOptimizerGoSelectedInputError("snapshot wearer order is invalid")
        if tuple(row.wearer.gcsim_character_key for row in self.wearers) != self.character_keys:
            raise GcsimOptimizerGoSelectedInputError(
                "snapshot character order mismatch"
            )
        artifact_ids = tuple(
            artifact_id
            for row in self.wearers
            for artifact_id in row.assignment.artifact_ids
        )
        if len(set(artifact_ids)) != 20:
            raise GcsimOptimizerGoSelectedInputError(
                "snapshot requires twenty globally distinct artifacts"
            )
        if self.engine_call_count != 0:
            raise GcsimOptimizerGoSelectedInputError(
                "snapshot cannot call the engine"
            )

    @property
    def snapshot_sha256(self) -> str:
        return canonical_sha256(self.to_dict(include_hash=False))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "artifact_database_input_sha256": self.artifact_database_input_sha256,
            "equipment_rows_sha256": self.equipment_rows_sha256,
            "character_keys": list(self.character_keys),
            "wearers": [row.to_dict() for row in self.wearers],
            "engine_call_count": 0,
        }
        if include_hash:
            value["snapshot_sha256"] = self.snapshot_sha256
        return value


@dataclass(frozen=True, slots=True)
class SelectedBoundWearerInput:
    actor_key: str
    artifact_ids_by_slot: tuple[tuple[str, int], ...]
    aggregate_artifact_stats: tuple[tuple[str, float], ...]
    active_sets: tuple[tuple[str, int], ...]

    @property
    def artifact_ids(self) -> tuple[int, ...]:
        return tuple(value for _slot, value in self.artifact_ids_by_slot)


def enforce_gcsim_optimizer_mvp_energy_policy(
    config: str,
    *,
    ignore_burst_energy: bool = True,
) -> str:
    """Apply the shared app energy mode to a Selected config idempotently."""

    if not isinstance(config, str) or not config.strip():
        raise GcsimOptimizerGoSelectedInputError(
            "optimizer config must be non-empty"
        )
    value = "true" if bool(ignore_burst_energy) else "false"
    options = _OPTIONS_RE.search(config)
    if options is None:
        return f"options ignore_burst_energy={value};\n" + config
    line = options.group(0)
    if re.search(r"(?i)\bignore_burst_energy\s*=", line):
        replacement = re.sub(
            r"(?i)\bignore_burst_energy\s*=\s*(?:true|false)",
            f"ignore_burst_energy={value}",
            line,
        )
    else:
        replacement = line[:-1].rstrip() + f" ignore_burst_energy={value};"
    return config[: options.start()] + replacement + config[options.end() :]


def load_selected_equipped_team_snapshot(
    database_path: str | Path,
    *,
    artifact_database: GcsimOptimizerArtifactDatabaseInput,
    character_keys: tuple[str, ...],
) -> SelectedEquippedTeamSnapshot:
    """Read the exact four current-equipment rows in one read-only transaction."""

    if not isinstance(artifact_database, GcsimOptimizerArtifactDatabaseInput):
        raise GcsimOptimizerGoSelectedInputError("artifact database is invalid")
    if len(character_keys) != 4 or len(set(character_keys)) != 4:
        raise GcsimOptimizerGoSelectedInputError(
            "snapshot requires four character keys"
        )
    path = Path(database_path).expanduser().resolve()
    if not path.is_file():
        raise GcsimOptimizerGoSelectedInputError("snapshot database does not exist")
    try:
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            rows = conn.execute(
                """
                SELECT characters.character_id, characters.gcsim_character_key,
                       equipped.slot_key, equipped.artifact_id
                FROM account_characters AS characters
                JOIN account_character_equipped_artifacts AS equipped
                  ON equipped.character_id = characters.character_id
                WHERE lower(characters.gcsim_character_key) IN (?, ?, ?, ?)
                ORDER BY lower(characters.gcsim_character_key),
                         equipped.slot_key, equipped.artifact_id
                """,
                tuple(key.casefold() for key in character_keys),
            ).fetchall()
            conn.rollback()
    except sqlite3.Error as exc:
        raise GcsimOptimizerGoSelectedInputError(
            f"selected equipment read failed: {exc}"
        ) from exc

    frozen_rows = tuple(
        (
            int(row["character_id"]),
            str(row["gcsim_character_key"]).casefold(),
            str(row["slot_key"]),
            int(row["artifact_id"]),
        )
        for row in rows
    )
    equipment_rows_sha256 = canonical_sha256(
        {
            "kind": "gtt.optimizer.selected_equipment_rows.v1",
            "rows": [list(row) for row in frozen_rows],
        }
    )
    by_key: dict[str, list[tuple[int, str, int]]] = {}
    for character_id, key, slot, artifact_id in frozen_rows:
        by_key.setdefault(key, []).append((character_id, slot, artifact_id))

    wearers: list[SelectedEquippedWearer] = []
    for team_slot, character_key in enumerate(character_keys, start=1):
        actor_rows = by_key.get(character_key.casefold(), [])
        character_ids = {row[0] for row in actor_rows}
        if len(character_ids) != 1:
            raise GcsimOptimizerGoSelectedInputError(
                f"selected actor {character_key!r} equipment owner is ambiguous"
            )
        slots = {slot: artifact_id for _id, slot, artifact_id in actor_rows}
        if set(slots) != set(GCSIM_OPTIMIZER_ARTIFACT_SLOTS):
            raise GcsimOptimizerGoSelectedInputError(
                f"selected actor {character_key!r} needs all five equipped slots"
            )
        wearer = GcsimOptimizerWearerIdentity(
            team_slot=team_slot,
            account_character_id=next(iter(character_ids)),
            gcsim_character_key=character_key.casefold(),
        )
        assignment = GcsimOptimizerWearerArtifactAssignment(
            wearer=wearer,
            artifact_ids_by_slot=slots,
        )
        artifacts = []
        for artifact_id in assignment.artifact_ids:
            artifact = artifact_database.artifact_by_id(artifact_id)
            if artifact is None:
                raise GcsimOptimizerGoSelectedInputError(
                    f"selected artifact {artifact_id} is absent from database"
                )
            artifacts.append(artifact)
        if any(
            artifact.position_key != slot
            for slot, artifact in zip(
                GCSIM_OPTIMIZER_ARTIFACT_SLOTS, artifacts, strict=True
            )
        ):
            raise GcsimOptimizerGoSelectedInputError(
                "selected equipped artifact slot mismatch"
            )
        counts = Counter(artifact.set_uid for artifact in artifacts)
        active_four_piece = sorted(uid for uid, count in counts.items() if count >= 4)
        if len(active_four_piece) != 1:
            raise GcsimOptimizerGoSelectedInputError(
                f"selected actor {character_key!r} needs one active 4p set"
            )
        target_uid = active_four_piece[0]
        wearers.append(
            SelectedEquippedWearer(
                wearer=wearer,
                assignment=assignment,
                target_set_uid=target_uid,
                target_set_count=counts[target_uid],
                set_counts=tuple(sorted(counts.items())),
            )
        )
    return SelectedEquippedTeamSnapshot(
        artifact_database_input_sha256=artifact_database.artifact_database_input_sha256,
        equipment_rows_sha256=equipment_rows_sha256,
        character_keys=tuple(key.casefold() for key in character_keys),
        wearers=tuple(wearers),
    )


def bind_selected_report_config_and_snapshot(
    payload: dict[str, Any],
    *,
    config_text: str,
    artifact_database: GcsimOptimizerArtifactDatabaseInput,
    snapshot: SelectedEquippedTeamSnapshot,
) -> tuple[SelectedBoundWearerInput, ...]:
    """Prove config, prepared report and current equipment describe one build."""

    characters = tuple(payload.get("characters", ()))
    if len(characters) != len(snapshot.wearers):
        raise GcsimOptimizerGoSelectedInputError(
            "prepared config/equipment wearer count mismatch"
        )
    config_stats = _config_stats(config_text)
    config_sets = _config_sets(config_text)
    bound: list[SelectedBoundWearerInput] = []
    slot_order = GCSIM_OPTIMIZER_ARTIFACT_SLOTS
    for character, selected in zip(characters, snapshot.wearers, strict=True):
        actor = str(character["mapping"]["gcsim_key"]).casefold()
        if actor != selected.wearer.gcsim_character_key:
            raise GcsimOptimizerGoSelectedInputError(
                "prepared config/equipment actor mismatch"
            )
        build = character.get("artifact_build") or {}
        prepared_ids = tuple(
            int(build.get("artifact_ids_by_pos", {}).get(str(index)))
            for index in range(1, 6)
        )
        snapshot_ids = tuple(
            selected.assignment.artifact_ids_by_slot[slot] for slot in slot_order
        )
        if prepared_ids != snapshot_ids:
            raise GcsimOptimizerGoSelectedInputError(
                f"prepared config artifact IDs differ for {actor}"
            )

        totals: dict[str, Decimal] = {}
        for slot, artifact_id in zip(slot_order, snapshot_ids, strict=True):
            artifact = artifact_database.artifact_by_id(artifact_id)
            if artifact is None or artifact.position_key != slot:
                raise GcsimOptimizerGoSelectedInputError(
                    f"same-context artifact {artifact_id} is missing or in wrong slot"
                )
            materialized = materialize_gcsim_optimizer_artifact_stat_vector(
                artifact, wearer=selected.wearer
            )
            if not materialized.ready or materialized.stat_vector is None:
                raise GcsimOptimizerGoSelectedInputError(
                    f"same-context artifact {artifact_id} did not materialize"
                )
            for stat_key, value in materialized.stat_vector.normalized_stats:
                totals[stat_key] = totals.get(stat_key, Decimal(0)) + Decimal(value)
        expected_stats = tuple(
            sorted((key, float(value)) for key, value in totals.items() if value != 0)
        )
        if not _stat_maps_close(dict(expected_stats), config_stats.get(actor, {})):
            raise GcsimOptimizerGoSelectedInputError(
                f"prepared config aggregate artifact stats differ for {actor}"
            )
        expected_sets = tuple(
            sorted(
                (
                    str(row["mapping"]["gcsim_key"]).casefold(),
                    int(row["count"]),
                )
                for row in build.get("set_counts", ())
                if int(row.get("count", 0)) >= 2
            )
        )
        if expected_sets != config_sets.get(actor, ()):
            raise GcsimOptimizerGoSelectedInputError(
                f"prepared config artifact sets differ for {actor}"
            )
        bound.append(
            SelectedBoundWearerInput(
                actor_key=actor,
                artifact_ids_by_slot=tuple(zip(slot_order, snapshot_ids, strict=True)),
                aggregate_artifact_stats=expected_stats,
                active_sets=expected_sets,
            )
        )
    return tuple(bound)


def _config_stats(config_text: str) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {}
    for match in _STATS_RE.finditer(config_text):
        actor = match.group("actor").casefold()
        values = {
            token.group("key").casefold(): float(token.group("value"))
            for token in _STAT_TOKEN_RE.finditer(match.group("body"))
        }
        if not values or actor in output:
            raise GcsimOptimizerGoSelectedInputError(
                "selected config has invalid add stats rows"
            )
        output[actor] = values
    return output


def _config_sets(config_text: str) -> dict[str, tuple[tuple[str, int], ...]]:
    output: dict[str, list[tuple[str, int]]] = {}
    for match in _SET_RE.finditer(config_text):
        output.setdefault(match.group("actor").casefold(), []).append(
            (match.group("set").casefold(), int(match.group("count")))
        )
    return {actor: tuple(sorted(rows)) for actor, rows in output.items()}


def _stat_maps_close(left: dict[str, float], right: dict[str, float]) -> bool:
    if set(left) != set(right):
        return False
    return all(
        math.isclose(left[key], right[key], rel_tol=0.0, abs_tol=1e-9)
        for key in left
    )


def _require_sha256(value: object, field_name: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise GcsimOptimizerGoSelectedInputError(
            f"{field_name} must be lowercase SHA-256"
        )


__all__ = [
    "GcsimOptimizerGoSelectedInputError",
    "SELECTED_EQUIPPED_SNAPSHOT_KIND",
    "SELECTED_EQUIPPED_SNAPSHOT_SCHEMA_VERSION",
    "SelectedBoundWearerInput",
    "SelectedEquippedTeamSnapshot",
    "SelectedEquippedWearer",
    "bind_selected_report_config_and_snapshot",
    "enforce_gcsim_optimizer_mvp_energy_policy",
    "load_selected_equipped_team_snapshot",
]
