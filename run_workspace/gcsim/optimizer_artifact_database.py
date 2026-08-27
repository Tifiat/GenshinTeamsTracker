"""Read-only all-row artifact database input for optimizer Milestone 1B.

The loader opens the existing unified SQLite database in URI ``mode=ro``,
performs one short read transaction, fetches every artifact and substat row,
then closes SQLite before validation.  Import provenance, equipment, presets,
locks, and locations never participate in membership or eligibility.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from types import MappingProxyType
from typing import TypeAlias
from urllib.parse import quote

from hoyolab_export.stat_normalization import STAT_MAPPINGS_BY_PROPERTY_TYPE

from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_product_contracts import (
    GcsimOptimizerFourStarEligibilityOverride,
    GcsimOptimizerIssue,
    GcsimOptimizerIssueScope,
    GcsimOptimizerWearerIdentity,
)


GCSIM_OPTIMIZER_ARTIFACT_DATABASE_SCHEMA_VERSION = 1
OPTIMIZER_ARTIFACT_DATABASE_READY = "ready"
OPTIMIZER_ARTIFACT_DATABASE_NOT_READY = "not_ready"

OPTIMIZER_ARTIFACT_SET_MAPPING_READY = "ready"
OPTIMIZER_ARTIFACT_SET_MAPPING_UNMAPPED = "unmapped"

GCSIM_OPTIMIZER_POSITION_BY_DB_POS = MappingProxyType(
    {
        1: "flower",
        2: "plume",
        3: "sands",
        4: "goblet",
        5: "circlet",
    }
)

_REQUIRED_ARTIFACT_COLUMNS = frozenset(
    {
        "id",
        "set_uid",
        "pos",
        "rarity",
        "level",
        "main_property_type",
        "main_property_name",
        "main_property_value",
    }
)
_REQUIRED_SUBSTAT_COLUMNS = frozenset(
    {
        "artifact_id",
        "slot_index",
        "property_type",
        "property_name",
        "value",
        "times",
    }
)

SqliteScalar: TypeAlias = None | int | float | str | bytes


@dataclass(frozen=True, slots=True)
class GcsimOptimizerArtifactSubstat:
    artifact_id: int
    slot_index: int
    property_type: int | None
    property_name: str | None
    stored_value: SqliteScalar
    numeric_value: float | None
    times: int | None
    raw_columns: tuple[tuple[str, SqliteScalar], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "slot_index": self.slot_index,
            "property_type": self.property_type,
            "property_name": self.property_name,
            "stored_value": _json_sqlite_value(self.stored_value),
            "numeric_value": self.numeric_value,
            "times": self.times,
            "raw_columns": {
                key: _json_sqlite_value(value)
                for key, value in self.raw_columns
            },
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerArtifactRecord:
    artifact_id: int
    set_uid: str
    gcsim_set_key: str
    set_mapping_status: str
    position: int | None
    position_key: str
    rarity: int | None
    level: int | None
    main_property_type: int | None
    main_property_name: str | None
    main_property_value: SqliteScalar
    main_numeric_value: float | None
    substats: tuple[GcsimOptimizerArtifactSubstat, ...]
    calculation_valid: bool
    default_eligible: bool
    issues: tuple[GcsimOptimizerIssue, ...]
    raw_columns: tuple[tuple[str, SqliteScalar], ...]

    def __post_init__(self) -> None:
        if self.set_mapping_status not in {
            OPTIMIZER_ARTIFACT_SET_MAPPING_READY,
            OPTIMIZER_ARTIFACT_SET_MAPPING_UNMAPPED,
        }:
            raise ValueError("unsupported artifact set mapping status")
        if self.default_eligible and (
            not self.calculation_valid or self.rarity != 5
        ):
            raise ValueError("default eligibility requires a valid 5-star artifact")

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "set_uid": self.set_uid,
            "gcsim_set_key": self.gcsim_set_key,
            "set_mapping_status": self.set_mapping_status,
            "position": self.position,
            "position_key": self.position_key,
            "rarity": self.rarity,
            "level": self.level,
            "main_property_type": self.main_property_type,
            "main_property_name": self.main_property_name,
            "main_property_value": _json_sqlite_value(
                self.main_property_value
            ),
            "main_numeric_value": self.main_numeric_value,
            "substats": [item.to_dict() for item in self.substats],
            "calculation_valid": self.calculation_valid,
            "default_eligible": self.default_eligible,
            "issues": [item.to_dict() for item in self.issues],
            "raw_columns": {
                key: _json_sqlite_value(value)
                for key, value in self.raw_columns
            },
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerArtifactDatabaseInput:
    database_path: str
    artifact_database_input_sha256: str
    engine_binding_sha256: str
    catalog_fingerprint: str
    artifact_columns: tuple[str, ...]
    substat_columns: tuple[str, ...]
    artifacts: tuple[GcsimOptimizerArtifactRecord, ...]
    raw_substat_row_count: int
    issues: tuple[GcsimOptimizerIssue, ...]
    schema_version: int = GCSIM_OPTIMIZER_ARTIFACT_DATABASE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_ARTIFACT_DATABASE_SCHEMA_VERSION:
            raise ValueError("unsupported optimizer artifact database schema")
        for field_name in (
            "artifact_database_input_sha256",
            "engine_binding_sha256",
            "catalog_fingerprint",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        artifact_ids = tuple(item.artifact_id for item in self.artifacts)
        if artifact_ids != tuple(sorted(artifact_ids)):
            raise ValueError("artifact records must use deterministic ID order")
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("artifact allocation IDs must be unique")
        if self.raw_substat_row_count != sum(
            len(item.substats) for item in self.artifacts
        ):
            raise ValueError("substat row count differs from attached rows")

    @property
    def eligible_5_star_artifact_ids(self) -> tuple[int, ...]:
        return tuple(
            item.artifact_id for item in self.artifacts if item.default_eligible
        )

    def artifact_by_id(
        self,
        artifact_id: int,
    ) -> GcsimOptimizerArtifactRecord | None:
        # ``artifacts`` is contractually sorted by unique physical ID.  Keep
        # lookup logarithmic because complete-assignment validation performs it
        # in the candidate hot path.
        left = 0
        right = len(self.artifacts)
        while left < right:
            middle = (left + right) // 2
            artifact = self.artifacts[middle]
            if artifact.artifact_id < artifact_id:
                left = middle + 1
            else:
                right = middle
        if left < len(self.artifacts):
            artifact = self.artifacts[left]
            if artifact.artifact_id == artifact_id:
                return artifact
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "database_path": self.database_path,
            "artifact_database_input_sha256": (
                self.artifact_database_input_sha256
            ),
            "engine_binding_sha256": self.engine_binding_sha256,
            "catalog_fingerprint": self.catalog_fingerprint,
            "artifact_columns": list(self.artifact_columns),
            "substat_columns": list(self.substat_columns),
            "artifacts": [item.to_dict() for item in self.artifacts],
            "raw_substat_row_count": self.raw_substat_row_count,
            "issues": [item.to_dict() for item in self.issues],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerArtifactDatabaseLoadResult:
    status: str
    ready: bool
    database_input: GcsimOptimizerArtifactDatabaseInput | None = None
    issues: tuple[GcsimOptimizerIssue, ...] = ()

    def __post_init__(self) -> None:
        if self.ready != (self.database_input is not None and not self.issues):
            raise ValueError("artifact database load readiness is incoherent")

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "ready": self.ready,
            "database_input": (
                None
                if self.database_input is None
                else self.database_input.to_dict()
            ),
            "issues": [item.to_dict() for item in self.issues],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerArtifactEligibility:
    artifact_id: int
    eligible: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "eligible": self.eligible,
            "reason": self.reason,
        }


def load_gcsim_optimizer_artifact_database_input(
    database_path: str | Path,
    *,
    engine_context: GcsimOptimizerEngineContext,
) -> GcsimOptimizerArtifactDatabaseLoadResult:
    """Load all artifact/substat rows without invoking write-capable helpers."""

    if not isinstance(engine_context, GcsimOptimizerEngineContext):
        return _load_not_ready(
            "engine_context_invalid",
            "engine_context must be a GcsimOptimizerEngineContext.",
        )
    if not engine_context.trusted or engine_context.issues:
        return _load_not_ready(
            "engine_context_untrusted",
            "Artifact database input requires a trusted optimizer engine.",
        )
    path = Path(database_path).expanduser().resolve()
    if not path.is_file():
        return _load_not_ready(
            "artifact_database_missing",
            f"Artifact database does not exist: {path}",
        )

    try:
        artifact_columns, substat_columns, artifact_rows, substat_rows = (
            _fetch_all_rows_readonly(path)
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        return _load_not_ready(
            "artifact_database_read_failed",
            f"Could not load optimizer artifact rows: {exc}",
        )

    raw_input_hash = _raw_database_input_sha256(
        artifact_columns=artifact_columns,
        substat_columns=substat_columns,
        artifact_rows=artifact_rows,
        substat_rows=substat_rows,
    )
    try:
        artifacts, row_issues = _validate_artifact_rows(
            artifact_rows,
            substat_rows,
            engine_context=engine_context,
        )
    except ValueError as exc:
        return _load_not_ready(
            "artifact_database_identity_invalid",
            str(exc),
        )
    database_input = GcsimOptimizerArtifactDatabaseInput(
        database_path=str(path),
        artifact_database_input_sha256=raw_input_hash,
        engine_binding_sha256=engine_context.binding_sha256,
        catalog_fingerprint=engine_context.catalog.source_fingerprint,
        artifact_columns=artifact_columns,
        substat_columns=substat_columns,
        artifacts=artifacts,
        raw_substat_row_count=len(substat_rows),
        issues=row_issues,
    )
    return GcsimOptimizerArtifactDatabaseLoadResult(
        status=OPTIMIZER_ARTIFACT_DATABASE_READY,
        ready=True,
        database_input=database_input,
    )


def evaluate_gcsim_optimizer_artifact_eligibility(
    artifact: GcsimOptimizerArtifactRecord,
    *,
    wearer: GcsimOptimizerWearerIdentity,
    four_star_override: (
        GcsimOptimizerFourStarEligibilityOverride | None
    ) = None,
    package_set_uids: Iterable[str] = (),
) -> GcsimOptimizerArtifactEligibility:
    """Evaluate default/explicit rarity admission for one wearer/package."""

    if not isinstance(artifact, GcsimOptimizerArtifactRecord):
        raise TypeError("artifact must be a GcsimOptimizerArtifactRecord")
    if not isinstance(wearer, GcsimOptimizerWearerIdentity):
        raise TypeError("wearer must be a GcsimOptimizerWearerIdentity")
    if not artifact.calculation_valid:
        return GcsimOptimizerArtifactEligibility(
            artifact.artifact_id,
            False,
            "artifact_calculation_invalid",
        )
    if artifact.rarity == 5:
        return GcsimOptimizerArtifactEligibility(
            artifact.artifact_id,
            True,
            "default_valid_5_star",
        )
    if artifact.rarity != 4:
        return GcsimOptimizerArtifactEligibility(
            artifact.artifact_id,
            False,
            "rarity_not_eligible",
        )
    if four_star_override is None:
        return GcsimOptimizerArtifactEligibility(
            artifact.artifact_id,
            False,
            "four_star_requires_explicit_authorization",
        )
    if four_star_override.wearer != wearer:
        return GcsimOptimizerArtifactEligibility(
            artifact.artifact_id,
            False,
            "four_star_override_wearer_mismatch",
        )
    if artifact.artifact_id in four_star_override.allowed_artifact_ids:
        return GcsimOptimizerArtifactEligibility(
            artifact.artifact_id,
            True,
            "explicit_four_star_artifact_id",
        )
    package_uids = frozenset(package_set_uids)
    if (
        artifact.set_uid in four_star_override.allowed_set_uids
        and artifact.set_uid in package_uids
    ):
        return GcsimOptimizerArtifactEligibility(
            artifact.artifact_id,
            True,
            "explicit_four_star_selected_set",
        )
    return GcsimOptimizerArtifactEligibility(
        artifact.artifact_id,
        False,
        "four_star_not_authorized_for_package",
    )


def _fetch_all_rows_readonly(
    path: Path,
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[tuple[tuple[str, SqliteScalar], ...], ...],
    tuple[tuple[tuple[str, SqliteScalar], ...], ...],
]:
    uri_path = quote(path.as_posix(), safe="/:")
    connection = sqlite3.connect(
        f"file:{uri_path}?mode=ro",
        uri=True,
        timeout=5.0,
    )
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        artifact_columns = _table_columns(connection, "artifacts")
        substat_columns = _table_columns(connection, "artifact_substats")
        missing_artifact = sorted(
            _REQUIRED_ARTIFACT_COLUMNS - set(artifact_columns)
        )
        missing_substat = sorted(
            _REQUIRED_SUBSTAT_COLUMNS - set(substat_columns)
        )
        if missing_artifact or missing_substat:
            raise ValueError(
                "optimizer artifact schema is incomplete; "
                f"artifacts missing={missing_artifact}, "
                f"artifact_substats missing={missing_substat}"
            )
        artifact_rows = tuple(
            _freeze_sqlite_row(row, artifact_columns)
            for row in connection.execute(
                "SELECT * FROM artifacts ORDER BY id ASC"
            ).fetchall()
        )
        substat_rows = tuple(
            _freeze_sqlite_row(row, substat_columns)
            for row in connection.execute(
                """
                SELECT *
                FROM artifact_substats
                ORDER BY artifact_id ASC, slot_index ASC
                """
            ).fetchall()
        )
        connection.rollback()
    finally:
        connection.close()
    return artifact_columns, substat_columns, artifact_rows, substat_rows


def _table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> tuple[str, ...]:
    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return tuple(str(row["name"]) for row in rows)


def _freeze_sqlite_row(
    row: sqlite3.Row,
    columns: tuple[str, ...],
) -> tuple[tuple[str, SqliteScalar], ...]:
    values: list[tuple[str, SqliteScalar]] = []
    for column in columns:
        value = row[column]
        if value is not None and not isinstance(
            value,
            (int, float, str, bytes),
        ):
            raise ValueError(
                f"unsupported SQLite value type in {column}: "
                f"{type(value).__name__}"
            )
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"non-finite SQLite value in {column}")
        values.append((column, value))
    return tuple(values)


def _raw_database_input_sha256(
    *,
    artifact_columns: tuple[str, ...],
    substat_columns: tuple[str, ...],
    artifact_rows: tuple[tuple[tuple[str, SqliteScalar], ...], ...],
    substat_rows: tuple[tuple[tuple[str, SqliteScalar], ...], ...],
) -> str:
    payload = {
        "schema_version": GCSIM_OPTIMIZER_ARTIFACT_DATABASE_SCHEMA_VERSION,
        "artifact_columns": list(artifact_columns),
        "substat_columns": list(substat_columns),
        "artifacts": [
            [
                [key, _json_sqlite_value(value)]
                for key, value in row
            ]
            for row in artifact_rows
        ],
        "artifact_substats": [
            [
                [key, _json_sqlite_value(value)]
                for key, value in row
            ]
            for row in substat_rows
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_artifact_rows(
    artifact_rows: tuple[tuple[tuple[str, SqliteScalar], ...], ...],
    substat_rows: tuple[tuple[tuple[str, SqliteScalar], ...], ...],
    *,
    engine_context: GcsimOptimizerEngineContext,
) -> tuple[
    tuple[GcsimOptimizerArtifactRecord, ...],
    tuple[GcsimOptimizerIssue, ...],
]:
    artifacts_by_id: dict[int, Mapping[str, SqliteScalar]] = {}
    frozen_by_id: dict[int, tuple[tuple[str, SqliteScalar], ...]] = {}
    for frozen in artifact_rows:
        row = dict(frozen)
        artifact_id = _strict_positive_int(row.get("id"))
        if artifact_id is None:
            raise ValueError(
                "every artifact row requires a positive integer allocation ID"
            )
        if artifact_id in artifacts_by_id:
            raise ValueError(f"duplicate artifact allocation ID {artifact_id}")
        artifacts_by_id[artifact_id] = row
        frozen_by_id[artifact_id] = frozen

    substats_by_artifact: dict[
        int,
        list[tuple[tuple[tuple[str, SqliteScalar], ...], Mapping[str, SqliteScalar]]],
    ] = {artifact_id: [] for artifact_id in artifacts_by_id}
    seen_substat_keys: set[tuple[int, int]] = set()
    for frozen in substat_rows:
        row = dict(frozen)
        artifact_id = _strict_positive_int(row.get("artifact_id"))
        slot_index = _strict_non_negative_int(row.get("slot_index"))
        if artifact_id is None or slot_index is None:
            raise ValueError("substat identity requires positive artifact_id and slot_index")
        if artifact_id not in artifacts_by_id:
            raise ValueError(f"orphan substat references artifact {artifact_id}")
        identity = (artifact_id, slot_index)
        if identity in seen_substat_keys:
            raise ValueError(f"duplicate substat identity {identity}")
        seen_substat_keys.add(identity)
        substats_by_artifact[artifact_id].append((frozen, row))

    records: list[GcsimOptimizerArtifactRecord] = []
    aggregate_issues: list[GcsimOptimizerIssue] = []
    for artifact_id in sorted(artifacts_by_id):
        row = artifacts_by_id[artifact_id]
        issues: list[GcsimOptimizerIssue] = []
        set_uid = _trimmed_text(row.get("set_uid"))
        if not set_uid:
            issues.append(
                _artifact_issue(
                    artifact_id,
                    "artifact_set_uid_missing",
                    "Artifact set_uid is required for optimizer identity.",
                )
            )
        position = _strict_positive_int(row.get("pos"))
        position_key = GCSIM_OPTIMIZER_POSITION_BY_DB_POS.get(
            position or -1,
            "",
        )
        if not position_key:
            issues.append(
                _artifact_issue(
                    artifact_id,
                    "artifact_position_invalid",
                    "Artifact position must be an integer from 1 through 5.",
                )
            )
        rarity = _strict_positive_int(row.get("rarity"))
        if rarity is None:
            issues.append(
                _artifact_issue(
                    artifact_id,
                    "artifact_rarity_invalid",
                    "Artifact rarity must be a positive integer.",
                )
            )
        level = _strict_non_negative_int(row.get("level"))
        if level is None:
            issues.append(
                _artifact_issue(
                    artifact_id,
                    "artifact_level_invalid",
                    "Artifact level must be a non-negative integer.",
                )
            )
        main_property_type = _strict_positive_int(
            row.get("main_property_type")
        )
        if main_property_type is None:
            issues.append(
                _artifact_issue(
                    artifact_id,
                    "artifact_main_property_type_missing",
                    "Artifact main property type is required.",
                )
            )
        elif main_property_type not in STAT_MAPPINGS_BY_PROPERTY_TYPE:
            issues.append(
                _artifact_issue(
                    artifact_id,
                    "artifact_main_property_type_unmapped",
                    "Artifact main property type has no GCSIM stat mapping.",
                )
            )
        main_numeric_value = _finite_numeric_stat(
            row.get("main_property_value")
        )
        if main_numeric_value is None:
            issues.append(
                _artifact_issue(
                    artifact_id,
                    "artifact_main_property_value_invalid",
                    "Artifact main property value must be a finite number.",
                )
            )

        substats: list[GcsimOptimizerArtifactSubstat] = []
        for frozen_substat, substat_row in substats_by_artifact[artifact_id]:
            slot_index = _strict_non_negative_int(
                substat_row.get("slot_index")
            )
            assert slot_index is not None
            property_type = _strict_positive_int(
                substat_row.get("property_type")
            )
            numeric_value = _finite_numeric_stat(substat_row.get("value"))
            times = _strict_non_negative_int(substat_row.get("times"))
            if property_type is None:
                issues.append(
                    _artifact_issue(
                        artifact_id,
                        "artifact_substat_property_type_missing",
                        f"Substat slot {slot_index} has no property type.",
                    )
                )
            elif property_type not in STAT_MAPPINGS_BY_PROPERTY_TYPE:
                issues.append(
                    _artifact_issue(
                        artifact_id,
                        "artifact_substat_property_type_unmapped",
                        f"Substat slot {slot_index} has no GCSIM stat mapping.",
                    )
                )
            if numeric_value is None:
                issues.append(
                    _artifact_issue(
                        artifact_id,
                        "artifact_substat_value_invalid",
                        f"Substat slot {slot_index} value must be finite.",
                    )
                )
            if substat_row.get("times") is not None and times is None:
                issues.append(
                    _artifact_issue(
                        artifact_id,
                        "artifact_substat_times_invalid",
                        f"Substat slot {slot_index} times must be non-negative.",
                    )
                )
            substats.append(
                GcsimOptimizerArtifactSubstat(
                    artifact_id=artifact_id,
                    slot_index=slot_index,
                    property_type=property_type,
                    property_name=_optional_text(
                        substat_row.get("property_name")
                    ),
                    stored_value=substat_row.get("value"),
                    numeric_value=numeric_value,
                    times=times,
                    raw_columns=frozen_substat,
                )
            )

        capability = engine_context.catalog.get(set_uid)
        if capability is not None and capability.registered:
            gcsim_set_key = capability.key.casefold()
            set_mapping_status = OPTIMIZER_ARTIFACT_SET_MAPPING_READY
        else:
            gcsim_set_key = ""
            set_mapping_status = OPTIMIZER_ARTIFACT_SET_MAPPING_UNMAPPED
            if set_uid:
                issues.append(
                    _artifact_issue(
                        artifact_id,
                        "artifact_set_unmapped",
                        "Concrete set_uid has no active registered GCSIM mapping; "
                        "the piece remains usable only as an offpiece.",
                    )
                )
        calculation_issue_codes = {
            issue.code for issue in issues if issue.code != "artifact_set_unmapped"
        }
        calculation_valid = not calculation_issue_codes
        record = GcsimOptimizerArtifactRecord(
            artifact_id=artifact_id,
            set_uid=set_uid,
            gcsim_set_key=gcsim_set_key,
            set_mapping_status=set_mapping_status,
            position=position,
            position_key=position_key,
            rarity=rarity,
            level=level,
            main_property_type=main_property_type,
            main_property_name=_optional_text(row.get("main_property_name")),
            main_property_value=row.get("main_property_value"),
            main_numeric_value=main_numeric_value,
            substats=tuple(substats),
            calculation_valid=calculation_valid,
            default_eligible=calculation_valid and rarity == 5,
            issues=tuple(issues),
            raw_columns=frozen_by_id[artifact_id],
        )
        records.append(record)
        aggregate_issues.extend(issues)
    return tuple(records), tuple(aggregate_issues)


def _artifact_issue(
    artifact_id: int,
    code: str,
    message: str,
) -> GcsimOptimizerIssue:
    return GcsimOptimizerIssue(
        code=code,
        scope=GcsimOptimizerIssueScope.ARTIFACT,
        message=message,
        artifact_id=artifact_id,
    )


def _load_not_ready(
    code: str,
    message: str,
) -> GcsimOptimizerArtifactDatabaseLoadResult:
    issue = GcsimOptimizerIssue(
        code=code,
        scope=GcsimOptimizerIssueScope.REQUEST,
        message=message,
    )
    return GcsimOptimizerArtifactDatabaseLoadResult(
        status=OPTIMIZER_ARTIFACT_DATABASE_NOT_READY,
        ready=False,
        issues=(issue,),
    )


def _strict_positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _strict_non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _finite_numeric_stat(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _trimmed_text(value: object) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _json_sqlite_value(value: SqliteScalar) -> object:
    if isinstance(value, bytes):
        return {"sqlite_blob_hex": value.hex()}
    return value


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


__all__ = [
    "GCSIM_OPTIMIZER_ARTIFACT_DATABASE_SCHEMA_VERSION",
    "GCSIM_OPTIMIZER_POSITION_BY_DB_POS",
    "GcsimOptimizerArtifactDatabaseInput",
    "GcsimOptimizerArtifactDatabaseLoadResult",
    "GcsimOptimizerArtifactEligibility",
    "GcsimOptimizerArtifactRecord",
    "GcsimOptimizerArtifactSubstat",
    "OPTIMIZER_ARTIFACT_DATABASE_NOT_READY",
    "OPTIMIZER_ARTIFACT_DATABASE_READY",
    "OPTIMIZER_ARTIFACT_SET_MAPPING_READY",
    "OPTIMIZER_ARTIFACT_SET_MAPPING_UNMAPPED",
    "evaluate_gcsim_optimizer_artifact_eligibility",
    "load_gcsim_optimizer_artifact_database_input",
]
