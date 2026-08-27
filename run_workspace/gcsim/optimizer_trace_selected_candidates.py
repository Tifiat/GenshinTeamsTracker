"""Zero-engine Selected inputs derived from current equipped fixed-4p builds.

This adapter reuses only stable read/materialization contracts.  It does not
call a legacy optimizer, inspect owner/lock provenance for eligibility, execute
GCSIM, or construct multi-slot search proposals.  The first bounded corpus is
the incumbent plus every legal single-piece substitution that preserves each
wearer's currently active four-piece set.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import sqlite3

from .optimizer_artifact_database import (
    GcsimOptimizerArtifactDatabaseInput,
    GcsimOptimizerArtifactRecord,
)
from .optimizer_artifact_materializer import (
    materialize_gcsim_optimizer_artifact_stat_vector,
)
from .optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimOptimizerWearerArtifactAssignment,
    GcsimOptimizerWearerIdentity,
)
from .trace_equation import (
    ArtifactStatReplacement,
    CandidateDependencyIndex,
    CandidateStatCoordinate,
    FrozenBoundaryScore,
    StateEvidenceTrace,
    TraceContractError,
    UncertaintyShortlistPlan,
    UncertaintyShortlistPolicy,
    build_uncertainty_shortlist_plan,
    canonical_sha256,
    compile_candidate_dependency_index,
    score_with_frozen_boundaries,
)


SELECTED_EQUIPPED_SNAPSHOT_SCHEMA_VERSION = 1
SELECTED_EQUIPPED_SNAPSHOT_KIND = "gtt.optimizer.selected_equipped_snapshot"
SELECTED_CANDIDATE_INPUT_SCHEMA_VERSION = 1
SELECTED_CANDIDATE_INPUT_KIND = "gtt.optimizer.selected_candidate_input"
SELECTED_CANDIDATE_CORPUS_SCHEMA_VERSION = 1
SELECTED_CANDIDATE_CORPUS_KIND = "gtt.optimizer.selected_candidate_corpus"
SELECTED_SCORED_CORPUS_SCHEMA_VERSION = 1
SELECTED_SCORED_CORPUS_KIND = "gtt.optimizer.selected_scored_corpus"


@dataclass(frozen=True, slots=True)
class SelectedEquippedWearer:
    wearer: GcsimOptimizerWearerIdentity
    assignment: GcsimOptimizerWearerArtifactAssignment
    target_set_uid: str
    target_set_count: int
    set_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.wearer, GcsimOptimizerWearerIdentity):
            raise TraceContractError("selected equipped wearer identity is invalid")
        if not isinstance(self.assignment, GcsimOptimizerWearerArtifactAssignment):
            raise TraceContractError("selected equipped assignment is invalid")
        if self.assignment.wearer != self.wearer:
            raise TraceContractError("selected equipped wearer/assignment mismatch")
        _trimmed(self.target_set_uid, "target_set_uid")
        if self.target_set_count not in (4, 5):
            raise TraceContractError("selected target set count must be four or five")
        if (
            tuple(sorted(self.set_counts)) != self.set_counts
            or any(not uid or count <= 0 for uid, count in self.set_counts)
            or sum(count for _uid, count in self.set_counts) != 5
        ):
            raise TraceContractError("selected equipped set counts are invalid")
        if dict(self.set_counts).get(self.target_set_uid) != self.target_set_count:
            raise TraceContractError("selected target set count mismatch")

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
            raise TraceContractError("selected equipped snapshot schema mismatch")
        if self.kind != SELECTED_EQUIPPED_SNAPSHOT_KIND:
            raise TraceContractError("selected equipped snapshot kind mismatch")
        _sha256(
            self.artifact_database_input_sha256,
            "artifact_database_input_sha256",
        )
        _sha256(self.equipment_rows_sha256, "equipment_rows_sha256")
        if (
            not isinstance(self.character_keys, tuple)
            or len(self.character_keys) != 4
            or len(set(self.character_keys)) != 4
            or any(not key or key != key.strip() for key in self.character_keys)
        ):
            raise TraceContractError("selected snapshot requires four character keys")
        if (
            not isinstance(self.wearers, tuple)
            or len(self.wearers) != 4
            or any(not isinstance(row, SelectedEquippedWearer) for row in self.wearers)
        ):
            raise TraceContractError("selected snapshot requires four wearers")
        if tuple(row.wearer.team_slot for row in self.wearers) != (1, 2, 3, 4):
            raise TraceContractError("selected snapshot wearer order is invalid")
        if tuple(row.wearer.gcsim_character_key for row in self.wearers) != (
            self.character_keys
        ):
            raise TraceContractError("selected snapshot character order mismatch")
        artifact_ids = tuple(
            artifact_id
            for row in self.wearers
            for artifact_id in row.assignment.artifact_ids
        )
        if len(set(artifact_ids)) != 20:
            raise TraceContractError(
                "selected snapshot requires twenty globally distinct artifacts"
            )
        if self.engine_call_count != 0:
            raise TraceContractError("selected snapshot cannot call the engine")

    @property
    def snapshot_sha256(self) -> str:
        return canonical_sha256(self.to_dict(include_hash=False))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        row: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "artifact_database_input_sha256": (
                self.artifact_database_input_sha256
            ),
            "equipment_rows_sha256": self.equipment_rows_sha256,
            "character_keys": list(self.character_keys),
            "wearers": [item.to_dict() for item in self.wearers],
            "engine_call_count": 0,
        }
        if include_hash:
            row["snapshot_sha256"] = self.snapshot_sha256
        return row


@dataclass(frozen=True, slots=True)
class SelectedCandidateInput:
    snapshot_sha256: str
    representative_assignments: tuple[
        GcsimOptimizerWearerArtifactAssignment, ...
    ]
    physical_assignment_sha256: str
    equivalent_physical_assignment_sha256s: tuple[str, ...]
    replacements: tuple[ArtifactStatReplacement, ...]
    is_incumbent: bool
    changed_wearer_key: str
    changed_slot: str
    engine_call_count: int = 0
    schema_version: int = SELECTED_CANDIDATE_INPUT_SCHEMA_VERSION
    kind: str = SELECTED_CANDIDATE_INPUT_KIND

    def __post_init__(self) -> None:
        if self.schema_version != SELECTED_CANDIDATE_INPUT_SCHEMA_VERSION:
            raise TraceContractError("selected candidate input schema mismatch")
        if self.kind != SELECTED_CANDIDATE_INPUT_KIND:
            raise TraceContractError("selected candidate input kind mismatch")
        _sha256(self.snapshot_sha256, "snapshot_sha256")
        _sha256(self.physical_assignment_sha256, "physical_assignment_sha256")
        if (
            not isinstance(self.representative_assignments, tuple)
            or len(self.representative_assignments) != 4
            or any(
                not isinstance(row, GcsimOptimizerWearerArtifactAssignment)
                for row in self.representative_assignments
            )
        ):
            raise TraceContractError("selected candidate assignments are invalid")
        if tuple(
            row.wearer.team_slot for row in self.representative_assignments
        ) != (1, 2, 3, 4):
            raise TraceContractError("selected candidate assignment order is invalid")
        artifact_ids = tuple(
            artifact_id
            for row in self.representative_assignments
            for artifact_id in row.artifact_ids
        )
        if len(set(artifact_ids)) != 20:
            raise TraceContractError("selected candidate reuses a physical artifact")
        if (
            not isinstance(self.equivalent_physical_assignment_sha256s, tuple)
            or tuple(sorted(set(self.equivalent_physical_assignment_sha256s)))
            != self.equivalent_physical_assignment_sha256s
            or self.physical_assignment_sha256
            not in self.equivalent_physical_assignment_sha256s
        ):
            raise TraceContractError("selected equivalent assignments are invalid")
        for value in self.equivalent_physical_assignment_sha256s:
            _sha256(value, "equivalent physical assignment SHA-256")
        if (
            not isinstance(self.replacements, tuple)
            or any(not isinstance(row, ArtifactStatReplacement) for row in self.replacements)
        ):
            raise TraceContractError("selected candidate replacements are invalid")
        keys = tuple((row.actor_key, row.stat_key) for row in self.replacements)
        if keys != tuple(sorted(set(keys))):
            raise TraceContractError("selected candidate replacements are not canonical")
        if not isinstance(self.is_incumbent, bool):
            raise TraceContractError("selected candidate incumbent flag is invalid")
        if self.is_incumbent:
            if self.replacements or self.changed_wearer_key or self.changed_slot:
                raise TraceContractError("selected incumbent must have no change")
        else:
            _trimmed(self.changed_wearer_key, "changed_wearer_key")
            if self.changed_slot not in GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
                raise TraceContractError("selected candidate changed slot is invalid")
        if self.engine_call_count != 0:
            raise TraceContractError("selected candidate input cannot call the engine")

    @property
    def equivalent_physical_assignment_count(self) -> int:
        return len(self.equivalent_physical_assignment_sha256s)

    @property
    def candidate_input_sha256(self) -> str:
        return canonical_sha256(self.to_dict(include_hash=False))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        row: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "snapshot_sha256": self.snapshot_sha256,
            "representative_assignments": [
                item.to_dict() for item in self.representative_assignments
            ],
            "physical_assignment_sha256": self.physical_assignment_sha256,
            "equivalent_physical_assignment_sha256s": list(
                self.equivalent_physical_assignment_sha256s
            ),
            "equivalent_physical_assignment_count": (
                self.equivalent_physical_assignment_count
            ),
            "replacements": [item.to_dict() for item in self.replacements],
            "is_incumbent": self.is_incumbent,
            "changed_wearer_key": self.changed_wearer_key,
            "changed_slot": self.changed_slot,
            "engine_call_count": 0,
        }
        if include_hash:
            row["candidate_input_sha256"] = self.candidate_input_sha256
        return row


@dataclass(frozen=True, slots=True)
class SelectedCandidateCorpus:
    snapshot: SelectedEquippedTeamSnapshot
    candidate_limit: int
    enumerated_physical_candidate_count: int
    candidates: tuple[SelectedCandidateInput, ...]
    incumbent_candidate_input_sha256: str
    engine_call_count: int = 0
    schema_version: int = SELECTED_CANDIDATE_CORPUS_SCHEMA_VERSION
    kind: str = SELECTED_CANDIDATE_CORPUS_KIND

    def __post_init__(self) -> None:
        if self.schema_version != SELECTED_CANDIDATE_CORPUS_SCHEMA_VERSION:
            raise TraceContractError("selected candidate corpus schema mismatch")
        if self.kind != SELECTED_CANDIDATE_CORPUS_KIND:
            raise TraceContractError("selected candidate corpus kind mismatch")
        if not isinstance(self.snapshot, SelectedEquippedTeamSnapshot):
            raise TraceContractError("selected candidate corpus snapshot is invalid")
        _positive_int(self.candidate_limit, "candidate_limit")
        _positive_int(
            self.enumerated_physical_candidate_count,
            "enumerated_physical_candidate_count",
        )
        if self.enumerated_physical_candidate_count > self.candidate_limit:
            raise TraceContractError("selected physical corpus exceeds its limit")
        if not isinstance(self.candidates, tuple) or not self.candidates:
            raise TraceContractError("selected candidate corpus is empty")
        if any(not isinstance(row, SelectedCandidateInput) for row in self.candidates):
            raise TraceContractError("selected candidate corpus rows are invalid")
        identities = tuple(row.candidate_input_sha256 for row in self.candidates)
        if len(identities) != len(set(identities)):
            raise TraceContractError("selected candidate inputs are duplicated")
        incumbents = tuple(row for row in self.candidates if row.is_incumbent)
        if len(incumbents) != 1:
            raise TraceContractError("selected corpus requires exactly one incumbent")
        _sha256(
            self.incumbent_candidate_input_sha256,
            "incumbent_candidate_input_sha256",
        )
        if incumbents[0].candidate_input_sha256 != (
            self.incumbent_candidate_input_sha256
        ):
            raise TraceContractError("selected incumbent identity mismatch")
        if sum(
            row.equivalent_physical_assignment_count for row in self.candidates
        ) != self.enumerated_physical_candidate_count:
            raise TraceContractError("selected physical/stat corpus count mismatch")
        if self.engine_call_count != 0:
            raise TraceContractError("selected candidate corpus cannot call the engine")

    @property
    def stat_candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def corpus_sha256(self) -> str:
        return canonical_sha256(self.to_dict(include_hash=False))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        row: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "snapshot": self.snapshot.to_dict(),
            "candidate_limit": self.candidate_limit,
            "enumerated_physical_candidate_count": (
                self.enumerated_physical_candidate_count
            ),
            "stat_candidate_count": self.stat_candidate_count,
            "candidates": [item.to_dict() for item in self.candidates],
            "incumbent_candidate_input_sha256": (
                self.incumbent_candidate_input_sha256
            ),
            "engine_call_count": 0,
        }
        if include_hash:
            row["corpus_sha256"] = self.corpus_sha256
        return row


@dataclass(frozen=True, slots=True)
class SelectedScoredCandidate:
    candidate_input: SelectedCandidateInput
    score: FrozenBoundaryScore

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_input, SelectedCandidateInput):
            raise TraceContractError("selected scored candidate input is invalid")
        if not isinstance(self.score, FrozenBoundaryScore):
            raise TraceContractError("selected scored candidate score is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_input": self.candidate_input.to_dict(),
            "score": self.score.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SelectedScoredCorpus:
    corpus_sha256: str
    scored_candidates: tuple[SelectedScoredCandidate, ...]
    dependency_slice_count: int
    shortlist_plan: UncertaintyShortlistPlan
    engine_call_count: int = 0
    schema_version: int = SELECTED_SCORED_CORPUS_SCHEMA_VERSION
    kind: str = SELECTED_SCORED_CORPUS_KIND

    def __post_init__(self) -> None:
        if self.schema_version != SELECTED_SCORED_CORPUS_SCHEMA_VERSION:
            raise TraceContractError("selected scored corpus schema mismatch")
        if self.kind != SELECTED_SCORED_CORPUS_KIND:
            raise TraceContractError("selected scored corpus kind mismatch")
        _sha256(self.corpus_sha256, "corpus_sha256")
        if not isinstance(self.scored_candidates, tuple) or not self.scored_candidates:
            raise TraceContractError("selected scored corpus is empty")
        if any(
            not isinstance(row, SelectedScoredCandidate)
            for row in self.scored_candidates
        ):
            raise TraceContractError("selected scored rows are invalid")
        _nonnegative_int(self.dependency_slice_count, "dependency_slice_count")
        if not isinstance(self.shortlist_plan, UncertaintyShortlistPlan):
            raise TraceContractError("selected shortlist plan is invalid")
        score_ids = {
            row.score.candidate_sha256 for row in self.scored_candidates
        }
        if any(
            request.candidate_sha256 not in score_ids
            for request in self.shortlist_plan.requests
        ):
            raise TraceContractError("selected shortlist references unknown score")
        if self.engine_call_count != 0:
            raise TraceContractError("selected scoring cannot call the engine")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "corpus_sha256": self.corpus_sha256,
            "scored_candidate_count": len(self.scored_candidates),
            "dependency_slice_count": self.dependency_slice_count,
            "shortlist_plan": self.shortlist_plan.to_dict(),
            "scored_candidates": [
                item.to_dict() for item in self.scored_candidates
            ],
            "engine_call_count": 0,
        }


def load_selected_equipped_team_snapshot(
    database_path: str | Path,
    *,
    artifact_database: GcsimOptimizerArtifactDatabaseInput,
    character_keys: tuple[str, ...],
) -> SelectedEquippedTeamSnapshot:
    """Read current equipment for the exact four trace actors in one RO txn."""

    if not isinstance(artifact_database, GcsimOptimizerArtifactDatabaseInput):
        raise TraceContractError("selected snapshot artifact database is invalid")
    if (
        not isinstance(character_keys, tuple)
        or len(character_keys) != 4
        or len(set(character_keys)) != 4
    ):
        raise TraceContractError("selected snapshot requires four character keys")
    path = Path(database_path).expanduser().resolve()
    if not path.is_file():
        raise TraceContractError("selected snapshot database does not exist")
    uri = f"file:{path.as_posix()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            rows = conn.execute(
                """
                SELECT
                    characters.character_id,
                    characters.gcsim_character_key,
                    equipped.slot_key,
                    equipped.artifact_id
                FROM account_characters AS characters
                JOIN account_character_equipped_artifacts AS equipped
                  ON equipped.character_id = characters.character_id
                WHERE lower(characters.gcsim_character_key) IN (?, ?, ?, ?)
                ORDER BY
                    lower(characters.gcsim_character_key),
                    equipped.slot_key,
                    equipped.artifact_id
                """,
                tuple(key.casefold() for key in character_keys),
            ).fetchall()
            conn.rollback()
    except sqlite3.Error as exc:
        raise TraceContractError(
            f"selected equipped snapshot read failed: {exc}"
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
            raise TraceContractError(
                f"selected actor {character_key!r} equipment owner is ambiguous"
            )
        slots = {slot: artifact_id for _id, slot, artifact_id in actor_rows}
        if set(slots) != set(GCSIM_OPTIMIZER_ARTIFACT_SLOTS):
            raise TraceContractError(
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
        artifacts = tuple(
            _required_artifact(artifact_database, artifact_id)
            for artifact_id in assignment.artifact_ids
        )
        if any(
            artifact.position_key != slot
            for slot, artifact in zip(
                GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
                artifacts,
                strict=True,
            )
        ):
            raise TraceContractError("selected equipped artifact slot mismatch")
        counts = Counter(artifact.set_uid for artifact in artifacts)
        active_four_piece = sorted(
            uid for uid, count in counts.items() if count >= 4
        )
        if len(active_four_piece) != 1:
            raise TraceContractError(
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
        artifact_database_input_sha256=(
            artifact_database.artifact_database_input_sha256
        ),
        equipment_rows_sha256=equipment_rows_sha256,
        character_keys=tuple(key.casefold() for key in character_keys),
        wearers=tuple(wearers),
    )


def build_selected_single_swap_corpus(
    artifact_database: GcsimOptimizerArtifactDatabaseInput,
    *,
    snapshot: SelectedEquippedTeamSnapshot,
    candidate_limit: int,
) -> SelectedCandidateCorpus:
    """Enumerate the complete incumbent + legal one-piece fixed-4p corpus."""

    if not isinstance(artifact_database, GcsimOptimizerArtifactDatabaseInput):
        raise TraceContractError("selected corpus artifact database is invalid")
    if not isinstance(snapshot, SelectedEquippedTeamSnapshot):
        raise TraceContractError("selected corpus snapshot is invalid")
    if snapshot.artifact_database_input_sha256 != (
        artifact_database.artifact_database_input_sha256
    ):
        raise TraceContractError("selected corpus database identity mismatch")
    _positive_int(candidate_limit, "candidate_limit")

    current_assignments = tuple(row.assignment for row in snapshot.wearers)
    current_ids = {
        artifact_id
        for assignment in current_assignments
        for artifact_id in assignment.artifact_ids
    }
    vector_cache: dict[tuple[str, int], dict[str, Decimal]] = {}
    baseline_totals = tuple(
        _assignment_stat_totals(
            artifact_database,
            selected.assignment,
            vector_cache=vector_cache,
        )
        for selected in snapshot.wearers
    )

    physical_rows: list[
        tuple[
            tuple[GcsimOptimizerWearerArtifactAssignment, ...],
            str,
            str,
            str,
            tuple[ArtifactStatReplacement, ...],
            bool,
        ]
    ] = []
    incumbent_sha = _physical_assignment_sha256(snapshot, current_assignments)
    physical_rows.append(
        (current_assignments, incumbent_sha, "", "", (), True)
    )

    eligible_by_slot: dict[str, tuple[GcsimOptimizerArtifactRecord, ...]] = {
        slot: tuple(
            artifact
            for artifact in artifact_database.artifacts
            if artifact.default_eligible and artifact.position_key == slot
        )
        for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
    }
    for wearer_index, selected in enumerate(snapshot.wearers):
        current_assignment = selected.assignment
        current_set_counts = Counter(dict(selected.set_counts))
        for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
            current_artifact_id = current_assignment.artifact_ids_by_slot[slot]
            current_artifact = _required_artifact(
                artifact_database,
                current_artifact_id,
            )
            unavailable_ids = current_ids - {current_artifact_id}
            for artifact in eligible_by_slot[slot]:
                if (
                    artifact.artifact_id == current_artifact_id
                    or artifact.artifact_id in unavailable_ids
                ):
                    continue
                candidate_counts = current_set_counts.copy()
                candidate_counts[current_artifact.set_uid] -= 1
                if candidate_counts[current_artifact.set_uid] <= 0:
                    del candidate_counts[current_artifact.set_uid]
                candidate_counts[artifact.set_uid] += 1
                if candidate_counts[selected.target_set_uid] < 4:
                    continue
                changed_assignment = GcsimOptimizerWearerArtifactAssignment(
                    wearer=selected.wearer,
                    artifact_ids_by_slot={
                        **dict(current_assignment.artifact_ids_by_slot),
                        slot: artifact.artifact_id,
                    },
                )
                assignments = list(current_assignments)
                assignments[wearer_index] = changed_assignment
                assignment_tuple = tuple(assignments)
                physical_sha256 = _physical_assignment_sha256(
                    snapshot,
                    assignment_tuple,
                )
                candidate_totals = _assignment_stat_totals(
                    artifact_database,
                    changed_assignment,
                    vector_cache=vector_cache,
                )
                replacements = _stat_replacements(
                    selected.wearer.gcsim_character_key,
                    baseline_totals[wearer_index],
                    candidate_totals,
                )
                physical_rows.append(
                    (
                        assignment_tuple,
                        physical_sha256,
                        selected.wearer.gcsim_character_key,
                        slot,
                        replacements,
                        False,
                    )
                )
                if len(physical_rows) > candidate_limit:
                    raise TraceContractError(
                        "selected complete single-swap corpus exceeds candidate_limit"
                    )

    grouped: dict[
        tuple[tuple[str, str, float, float], ...],
        list[
            tuple[
                tuple[GcsimOptimizerWearerArtifactAssignment, ...],
                str,
                str,
                str,
                tuple[ArtifactStatReplacement, ...],
                bool,
            ]
        ],
    ] = {}
    for row in physical_rows:
        key = tuple(
            (
                item.actor_key,
                item.stat_key,
                item.baseline_artifact_value,
                item.candidate_artifact_value,
            )
            for item in row[4]
        )
        grouped.setdefault(key, []).append(row)

    candidates: list[SelectedCandidateInput] = []
    for rows in grouped.values():
        rows.sort(key=lambda row: (not row[5], row[1]))
        chosen = rows[0]
        equivalent = tuple(sorted(row[1] for row in rows))
        candidate = SelectedCandidateInput(
            snapshot_sha256=snapshot.snapshot_sha256,
            representative_assignments=chosen[0],
            physical_assignment_sha256=chosen[1],
            equivalent_physical_assignment_sha256s=equivalent,
            replacements=chosen[4],
            is_incumbent=chosen[5],
            changed_wearer_key=chosen[2],
            changed_slot=chosen[3],
        )
        candidates.append(candidate)
    candidates.sort(
        key=lambda row: (not row.is_incumbent, row.candidate_input_sha256)
    )
    incumbent = next(row for row in candidates if row.is_incumbent)
    return SelectedCandidateCorpus(
        snapshot=snapshot,
        candidate_limit=candidate_limit,
        enumerated_physical_candidate_count=len(physical_rows),
        candidates=tuple(candidates),
        incumbent_candidate_input_sha256=incumbent.candidate_input_sha256,
    )


def score_selected_candidate_corpus(
    trace: StateEvidenceTrace,
    corpus: SelectedCandidateCorpus,
    *,
    policy: UncertaintyShortlistPolicy,
    fidelity_sha256: str,
    seed_panel_sha256: str,
    dependency_index: CandidateDependencyIndex | None = None,
) -> SelectedScoredCorpus:
    """Score a real Selected corpus and freeze, but never execute, finalists."""

    if not isinstance(trace, StateEvidenceTrace):
        raise TraceContractError("selected scoring requires V6 state evidence")
    if not isinstance(corpus, SelectedCandidateCorpus):
        raise TraceContractError("selected scoring corpus is invalid")
    if trace.terminal_trace.request.character_keys != corpus.snapshot.character_keys:
        raise TraceContractError("selected scoring trace/team identity mismatch")

    if dependency_index is None:
        dependency_index = compile_candidate_dependency_index(trace)
    elif dependency_index.trace_evidence_sha256 != trace.evidence_sha256:
        raise TraceContractError("selected dependency index trace identity mismatch")
    slice_cache = {}
    scored: list[SelectedScoredCandidate] = []
    for candidate in corpus.candidates:
        coordinates = tuple(
            sorted(
                {
                    CandidateStatCoordinate(row.actor_key, row.stat_key)
                    for row in candidate.replacements
                    if row.baseline_artifact_value != row.candidate_artifact_value
                }
            )
        )
        dependency_slice = None
        if coordinates:
            dependency_slice = slice_cache.get(coordinates)
            if dependency_slice is None:
                dependency_slice = dependency_index.slice(coordinates)
                slice_cache[coordinates] = dependency_slice
        score = score_with_frozen_boundaries(
            trace,
            candidate.replacements,
            candidate_dependency_slice=dependency_slice,
        )
        scored.append(
            SelectedScoredCandidate(
                candidate_input=candidate,
                score=score,
            )
        )
    plan = build_uncertainty_shortlist_plan(
        tuple(row.score for row in scored),
        policy=policy,
        fidelity_sha256=fidelity_sha256,
        seed_panel_sha256=seed_panel_sha256,
    )
    return SelectedScoredCorpus(
        corpus_sha256=corpus.corpus_sha256,
        scored_candidates=tuple(scored),
        dependency_slice_count=len(slice_cache),
        shortlist_plan=plan,
    )


def _assignment_stat_totals(
    artifact_database: GcsimOptimizerArtifactDatabaseInput,
    assignment: GcsimOptimizerWearerArtifactAssignment,
    *,
    vector_cache: dict[tuple[str, int], dict[str, Decimal]],
) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
        artifact_id = assignment.artifact_ids_by_slot[slot]
        cache_key = (assignment.wearer.gcsim_character_key, artifact_id)
        vector = vector_cache.get(cache_key)
        if vector is None:
            artifact = _required_artifact(artifact_database, artifact_id)
            result = materialize_gcsim_optimizer_artifact_stat_vector(
                artifact,
                wearer=assignment.wearer,
            )
            if not result.ready or result.stat_vector is None:
                codes = ",".join(item.code for item in result.diagnostics)
                raise TraceContractError(
                    f"selected artifact {artifact_id} stat materialization failed: {codes}"
                )
            vector = {
                key: Decimal(value)
                for key, value in result.stat_vector.normalized_stats
            }
            vector_cache[cache_key] = vector
        for key, value in vector.items():
            totals[key] = totals.get(key, Decimal(0)) + value
    return totals


def _stat_replacements(
    actor_key: str,
    baseline: dict[str, Decimal],
    candidate: dict[str, Decimal],
) -> tuple[ArtifactStatReplacement, ...]:
    rows = []
    for stat_key in sorted(set(baseline) | set(candidate)):
        left = baseline.get(stat_key, Decimal(0))
        right = candidate.get(stat_key, Decimal(0))
        if left == right:
            continue
        rows.append(
            ArtifactStatReplacement(
                actor_key=actor_key,
                stat_key=stat_key,
                baseline_artifact_value=float(left),
                candidate_artifact_value=float(right),
            )
        )
    return tuple(rows)


def _physical_assignment_sha256(
    snapshot: SelectedEquippedTeamSnapshot,
    assignments: tuple[GcsimOptimizerWearerArtifactAssignment, ...],
) -> str:
    return canonical_sha256(
        {
            "kind": "gtt.optimizer.selected_physical_assignment.v1",
            "snapshot_sha256": snapshot.snapshot_sha256,
            "assignments": [row.to_dict() for row in assignments],
        }
    )


def _required_artifact(
    artifact_database: GcsimOptimizerArtifactDatabaseInput,
    artifact_id: int,
) -> GcsimOptimizerArtifactRecord:
    artifact = artifact_database.artifact_by_id(artifact_id)
    if artifact is None:
        raise TraceContractError(
            f"selected artifact {artifact_id} is absent from frozen database"
        )
    return artifact


def _trimmed(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise TraceContractError(f"{field_name} must be trimmed text")


def _positive_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TraceContractError(f"{field_name} must be a positive integer")


def _nonnegative_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TraceContractError(f"{field_name} must be a non-negative integer")


def _sha256(value: object, field_name: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise TraceContractError(f"{field_name} must be lowercase SHA-256")


__all__ = [
    "SELECTED_CANDIDATE_CORPUS_KIND",
    "SELECTED_CANDIDATE_CORPUS_SCHEMA_VERSION",
    "SELECTED_CANDIDATE_INPUT_KIND",
    "SELECTED_CANDIDATE_INPUT_SCHEMA_VERSION",
    "SELECTED_EQUIPPED_SNAPSHOT_KIND",
    "SELECTED_EQUIPPED_SNAPSHOT_SCHEMA_VERSION",
    "SELECTED_SCORED_CORPUS_KIND",
    "SELECTED_SCORED_CORPUS_SCHEMA_VERSION",
    "SelectedCandidateCorpus",
    "SelectedCandidateInput",
    "SelectedEquippedTeamSnapshot",
    "SelectedEquippedWearer",
    "SelectedScoredCandidate",
    "SelectedScoredCorpus",
    "build_selected_single_swap_corpus",
    "load_selected_equipped_team_snapshot",
    "score_selected_candidate_corpus",
]
