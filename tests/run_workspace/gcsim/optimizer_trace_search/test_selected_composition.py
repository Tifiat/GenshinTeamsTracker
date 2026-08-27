from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from run_workspace.gcsim.optimizer_artifact_materializer import (
    materialize_gcsim_optimizer_artifact_stat_vector,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimOptimizerWearerArtifactAssignment,
    GcsimOptimizerWearerIdentity,
)
from run_workspace.gcsim.optimizer_trace_search import (
    SelectedCompleteAssignment,
    build_selected_complete_assignment,
    compile_selected_composition_scoring_session,
    score_selected_complete_assignment,
    score_selected_complete_assignments,
)
from run_workspace.gcsim.optimizer_trace_selected_candidates import (
    SelectedEquippedTeamSnapshot,
    SelectedEquippedWearer,
)
from run_workspace.gcsim.trace_equation import (
    ArtifactStatValue,
    ArtifactStatVector,
    SupportAwareFastObjective,
    SupportAwareFastScore,
    TraceContractError,
)
from tests.run_workspace.gcsim.test_gcsim_optimizer_artifact_materializer import (
    _environment,
)
class SelectedCompositionTests(unittest.TestCase):
    def test_complete_physical_assignments_score_without_product_authority(self) -> None:
        database, snapshot, incumbent_assignments, alternative = _physical_fixture()
        incumbent_vector = _artifact_vector(database, incumbent_assignments)
        objective = _objective(snapshot)
        session = compile_selected_composition_scoring_session(
            database,
            snapshot=snapshot,
            objective=objective,
        )
        incumbent = build_selected_complete_assignment(
            database,
            snapshot=snapshot,
            assignments=incumbent_assignments,
        )
        changed = build_selected_complete_assignment(
            database,
            snapshot=snapshot,
            assignments=alternative,
        )

        with patch(
            "run_workspace.gcsim.optimizer_trace_search.selected_composition."
            "evaluate_support_aware_fast_objective",
            side_effect=_fake_evaluate,
        ):
            batch = score_selected_complete_assignments(
                session,
                (incumbent, changed),
                candidate_limit=2,
            )

        self.assertEqual(len(batch.scores), 2)
        self.assertEqual(batch.engine_call_count, 0)
        self.assertFalse(batch.authoritative)
        self.assertFalse(batch.prune_authority)
        self.assertEqual(batch.support_cache_entries, 1)
        self.assertEqual(batch.support_cache_misses, 1)
        self.assertEqual(batch.support_cache_hits, 1)
        incumbent_score = next(row for row in batch.scores if row.candidate.is_incumbent)
        self.assertEqual(
            incumbent_score.artifact_vector_sha256,
            incumbent_vector.vector_sha256,
        )
        self.assertAlmostEqual(incumbent_score.score.expected_delta, 0.0)

    def test_global_reuse_and_broken_four_piece_are_rejected(self) -> None:
        database, snapshot, incumbent_assignments, _alternative = _physical_fixture()
        reused_maps = [dict(row.artifact_ids_by_slot) for row in incumbent_assignments]
        reused_maps[1]["flower"] = reused_maps[0]["flower"]
        reused = tuple(
            GcsimOptimizerWearerArtifactAssignment(
                wearer=row.wearer,
                artifact_ids_by_slot=reused_maps[index],
            )
            for index, row in enumerate(incumbent_assignments)
        )
        with self.assertRaises(TraceContractError):
            build_selected_complete_assignment(
                database,
                snapshot=snapshot,
                assignments=reused,
            )

        broken_maps = [dict(row.artifact_ids_by_slot) for row in incumbent_assignments]
        for slot in ("flower", "plume"):
            broken_maps[0][slot] = _artifact_id(
                database,
                copy=1,
                wearer_index=0,
                set_kind="secondary",
                slot=slot,
            )
        broken = tuple(
            GcsimOptimizerWearerArtifactAssignment(
                wearer=row.wearer,
                artifact_ids_by_slot=broken_maps[index],
            )
            for index, row in enumerate(incumbent_assignments)
        )
        with self.assertRaises(TraceContractError):
            build_selected_complete_assignment(
                database,
                snapshot=snapshot,
                assignments=broken,
            )

    def test_forged_physical_identity_is_rejected_at_score_boundary(self) -> None:
        database, snapshot, incumbent_assignments, _alternative = _physical_fixture()
        objective = _objective(snapshot)
        session = compile_selected_composition_scoring_session(
            database,
            snapshot=snapshot,
            objective=objective,
        )
        incumbent = build_selected_complete_assignment(
            database,
            snapshot=snapshot,
            assignments=incumbent_assignments,
        )
        forged = replace(incumbent, physical_assignment_sha256="f" * 64)

        with patch(
            "run_workspace.gcsim.optimizer_trace_search.selected_composition."
            "evaluate_support_aware_fast_objective",
            side_effect=_fake_evaluate,
        ):
            with self.assertRaises(TraceContractError):
                score_selected_complete_assignment(session, forged)

    def test_candidate_limit_stops_consuming_the_input_stream(self) -> None:
        database, snapshot, incumbent_assignments, alternative = _physical_fixture()
        session = compile_selected_composition_scoring_session(
            database,
            snapshot=snapshot,
            objective=_objective(snapshot),
        )
        incumbent = build_selected_complete_assignment(
            database,
            snapshot=snapshot,
            assignments=incumbent_assignments,
        )
        changed = build_selected_complete_assignment(
            database,
            snapshot=snapshot,
            assignments=alternative,
        )

        def candidates():
            yield incumbent
            yield changed
            yield incumbent
            raise AssertionError("candidate stream consumed past the hard limit")

        with self.assertRaisesRegex(TraceContractError, "limit exceeded"):
            score_selected_complete_assignments(
                session,
                candidates(),
                candidate_limit=2,
            )


def _physical_fixture():
    environment = _environment()
    keys = ("furina", "beta", "gamma", "delta")
    wearers = tuple(
        GcsimOptimizerWearerIdentity(
            team_slot=index,
            account_character_id=20_000 + index,
            gcsim_character_key=key,
        )
        for index, key in enumerate(keys, start=1)
    )
    assignments = tuple(
        GcsimOptimizerWearerArtifactAssignment(
            wearer=wearer,
            artifact_ids_by_slot={
                slot: environment.ids[(0, index, "primary", slot)]
                for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
            },
        )
        for index, wearer in enumerate(wearers)
    )
    selected = tuple(
        SelectedEquippedWearer(
            wearer=wearer,
            assignment=assignments[index],
            target_set_uid=environment.pool_refs[index][0].set_uid,
            target_set_count=5,
            set_counts=((environment.pool_refs[index][0].set_uid, 5),),
        )
        for index, wearer in enumerate(wearers)
    )
    snapshot = SelectedEquippedTeamSnapshot(
        artifact_database_input_sha256=(
            environment.database.artifact_database_input_sha256
        ),
        equipment_rows_sha256="e" * 64,
        character_keys=keys,
        wearers=selected,
    )
    alternative_rows = list(assignments)
    alternative_rows[0] = GcsimOptimizerWearerArtifactAssignment(
        wearer=wearers[0],
        artifact_ids_by_slot={
            slot: environment.ids[(1, 0, "primary", slot)]
            for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
        },
    )
    return environment.database, snapshot, assignments, tuple(alternative_rows)


def _artifact_id(
    database,
    *,
    copy: int,
    wearer_index: int,
    set_kind: str,
    slot: str,
) -> int:
    set_prefix = "secondary" if set_kind == "secondary" else "set"
    wearer_label = ("alpha", "beta", "gamma", "delta")[wearer_index]
    set_key = f"{set_prefix}{wearer_label}"
    candidates = tuple(
        row.artifact_id
        for row in database.artifacts
        if row.position_key == slot and row.gcsim_set_key == set_key
    )
    return candidates[copy]


def _artifact_vector(database, assignments) -> ArtifactStatVector:
    totals: dict[tuple[str, str], Decimal] = {}
    for assignment in assignments:
        actor = assignment.wearer.gcsim_character_key
        for artifact_id in assignment.artifact_ids:
            artifact = database.artifact_by_id(artifact_id)
            assert artifact is not None
            result = materialize_gcsim_optimizer_artifact_stat_vector(
                artifact,
                wearer=assignment.wearer,
            )
            assert result.ready and result.stat_vector is not None
            for stat, value in result.stat_vector.normalized_stats:
                coordinate = (actor, stat)
                totals[coordinate] = totals.get(coordinate, Decimal(0)) + Decimal(value)
    return ArtifactStatVector.build(
        tuple(
            ArtifactStatValue(actor, stat, float(value))
            for (actor, stat), value in totals.items()
            if value > 0
        )
    )


def _objective(snapshot) -> SupportAwareFastObjective:
    control = SimpleNamespace(
        standard=SimpleNamespace(character_keys=snapshot.character_keys)
    )
    return SupportAwareFastObjective(
        objective_sha256="a" * 64,
        control=control,
        direct_fast=SimpleNamespace(baseline_damage=100.0),
        support_coordinates=(),
    )


def _fake_evaluate(objective, vector, *, cache) -> SupportAwareFastScore:
    key = ()
    cache_hit = key in cache.entries
    if cache_hit:
        cache.hit_count += 1
    else:
        cache.entries[key] = object()
        cache.miss_count += 1
    return SupportAwareFastScore(
        objective_sha256=objective.objective_sha256,
        artifact_vector_sha256=vector.vector_sha256,
        baseline_damage=100.0,
        candidate_damage=100.0,
        expected_delta=0.0,
        baseline_dps=10.0,
        candidate_dps=10.0,
        candidate_damage_by_actor=(("furina", 100.0),),
        support_correction_damage=0.0,
        support_changed_hit_count=0,
        support_cache_hit=cache_hit,
        support_cache_entry_count=len(cache.entries),
        uncertainty_codes=(),
    )


if __name__ == "__main__":
    unittest.main()
