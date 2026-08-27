from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import unittest

from run_workspace.gcsim.optimizer_anytime_candidates import (
    GcsimOptimizerDenseArtifact,
    GcsimOptimizerDenseArtifactCatalog,
    build_gcsim_optimizer_dense_artifact_catalog,
)
from run_workspace.gcsim.optimizer_artifact_database import (
    GcsimOptimizerArtifactRecord,
)
from run_workspace.gcsim.optimizer_inventory_frontier import (
    GCSIM_OPTIMIZER_INVENTORY_ADMISSION_REQUIRES_ACTIVE_SET,
    GCSIM_OPTIMIZER_INVENTORY_ADMISSION_UNCONDITIONAL,
    GCSIM_OPTIMIZER_INVENTORY_FRONTIER_RETAINED,
    GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SHADOW_INELIGIBLE,
    GCSIM_OPTIMIZER_INVENTORY_STAT_AXES,
    build_gcsim_optimizer_inventory_frontier,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimOptimizerFourStarEligibilityOverride,
)
from run_workspace.gcsim.optimizer_run_input import (
    GcsimOptimizerRunInput,
    build_gcsim_optimizer_run_input,
)

from ._optimizer_oracle_fixtures import (
    OracleAccountEnvironment,
    build_oracle_account_environment,
)


class GcsimOptimizerInventoryFrontierTests(unittest.TestCase):
    def test_real_dense_catalog_freezes_one_mask_per_physical_piece(
        self,
    ) -> None:
        environment = build_oracle_account_environment()
        catalog = build_gcsim_optimizer_dense_artifact_catalog(
            environment.run_input
        )

        result = build_gcsim_optimizer_inventory_frontier(
            environment.run_input,
            catalog=catalog,
        )
        repeated = build_gcsim_optimizer_inventory_frontier(
            environment.run_input,
            catalog=catalog,
        )

        self.assertEqual(result.k_skyline_depth, 4)
        self.assertEqual(
            set(result.row_by_artifact_id),
            {item.artifact_id for item in catalog.artifacts},
        )
        shared = result.row_by_artifact_id[environment.shared_goblet_id]
        self.assertEqual(shared.eligibility.eligible_wearer_slots, (1, 2, 3, 4))
        self.assertEqual(
            {item.reason_code for item in shared.eligibility.entries},
            {"default_valid_5_star"},
        )
        self.assertEqual(
            {item.admission_kind for item in shared.eligibility.entries},
            {GCSIM_OPTIMIZER_INVENTORY_ADMISSION_UNCONDITIONAL},
        )
        alpha_set_piece = next(
            item
            for item in catalog.artifacts
            if item.record.set_uid == environment.set_refs[0].set_uid
        )
        alpha = result.row_by_artifact_id[alpha_set_piece.artifact_id]
        self.assertEqual(alpha.eligibility.eligible_wearer_slots, (1,))
        self.assertEqual(
            alpha.eligibility.entries[0].reason_code,
            "explicit_four_star_selected_set",
        )
        self.assertEqual(
            alpha.eligibility.entries[0].admission_kind,
            GCSIM_OPTIMIZER_INVENTORY_ADMISSION_REQUIRES_ACTIVE_SET,
        )
        self.assertEqual(
            alpha.eligibility.entries[0].required_active_set_uid,
            alpha_set_piece.record.set_uid,
        )
        self.assertEqual(result.identity_sha256, repeated.identity_sha256)
        self.assertEqual(result.to_dict(), repeated.to_dict())
        self.assertEqual(
            result.counters.source_artifact_count,
            len(environment.database.artifacts),
        )
        self.assertEqual(
            result.counters.dense_excluded_artifact_count,
            1,
        )

    def test_skyline_depth_is_advisory_and_never_hard_prunes_eligible_rows(
        self,
    ) -> None:
        environment = build_oracle_account_environment()
        records = tuple(
            _physical_record(
                environment,
                artifact_id=1_001 + index,
                set_uid="SyntheticChainSet",
            )
            for index in range(5)
        )
        run_input = _run_input_for_records(environment, records)
        catalog = _dense_catalog(
            run_input,
            {
                record.artifact_id: _stat_vector(
                    hp=float(5 - index),
                    **{"pyro%": 1.0},
                )
                for index, record in enumerate(records)
            },
            main_keys={record.artifact_id: "pyro%" for record in records},
        )

        result = build_gcsim_optimizer_inventory_frontier(
            run_input,
            catalog=catalog,
        )
        repeated = build_gcsim_optimizer_inventory_frontier(
            run_input,
            catalog=catalog,
        )
        rows = result.row_by_artifact_id
        ids = tuple(record.artifact_id for record in records)

        self.assertEqual(
            tuple(rows[artifact_id].skyline_depth for artifact_id in ids),
            (1, 2, 3, 4, 5),
        )
        self.assertEqual(
            tuple(item.artifact_id for item in result.retained_rows),
            ids,
        )
        self.assertFalse(result.shadow_reservoir)
        deeper = rows[ids[4]]
        self.assertEqual(
            deeper.disposition,
            GCSIM_OPTIMIZER_INVENTORY_FRONTIER_RETAINED,
        )
        self.assertEqual(deeper.dominance_chain_artifact_ids, ids)
        self.assertEqual(result.counters.depth_exceeded_artifact_count, 1)
        self.assertEqual(result.counters.max_observed_skyline_depth, 5)
        self.assertFalse(result.group_diagnostics[0].shadow_artifact_ids)
        self.assertEqual(result.identity_sha256, repeated.identity_sha256)
        self.assertEqual(result.to_dict(), repeated.to_dict())

        shallow = build_gcsim_optimizer_inventory_frontier(
            run_input,
            catalog=catalog,
            k_skyline_depth=1,
        )
        self.assertEqual(
            tuple(item.artifact_id for item in shallow.retained_rows),
            ids,
        )
        self.assertFalse(shallow.shadow_reservoir)
        self.assertEqual(shallow.counters.depth_exceeded_artifact_count, 4)

    def test_exact_stat_physical_copies_keep_full_multiplicity(self) -> None:
        environment = build_oracle_account_environment()
        records = tuple(
            _physical_record(
                environment,
                artifact_id=2_001 + index,
                set_uid="SyntheticCopySet",
            )
            for index in range(5)
        )
        run_input = _run_input_for_records(environment, records)
        vector = _stat_vector(hp=10.0, **{"pyro%": 1.0})
        catalog = _dense_catalog(
            run_input,
            {record.artifact_id: vector for record in records},
            main_keys={record.artifact_id: "pyro%" for record in records},
        )

        result = build_gcsim_optimizer_inventory_frontier(
            run_input,
            catalog=catalog,
            k_skyline_depth=1,
        )

        self.assertEqual(len(result.retained_rows), 5)
        self.assertFalse(result.shadow_reservoir)
        self.assertEqual(
            {item.skyline_depth for item in result.retained_rows},
            {1},
        )
        self.assertEqual(result.counters.identical_vector_class_count, 1)
        self.assertEqual(result.counters.identical_vector_extra_copy_count, 4)
        self.assertEqual(
            result.group_diagnostics[0].skyline_layers,
            ((1, tuple(record.artifact_id for record in records)),),
        )

    def test_set_uid_and_incomparable_main_vectors_never_false_dominate(
        self,
    ) -> None:
        environment = build_oracle_account_environment()
        records = (
            _physical_record(environment, 3_001, "ConcreteSetA"),
            _physical_record(environment, 3_002, "ConcreteSetB"),
            _physical_record(environment, 3_003, "ConcreteSetC"),
            _physical_record(environment, 3_004, "ConcreteSetC"),
        )
        run_input = _run_input_for_records(environment, records)
        catalog = _dense_catalog(
            run_input,
            {
                3_001: _stat_vector(hp=100.0, **{"pyro%": 1.0}),
                3_002: _stat_vector(hp=1.0, **{"pyro%": 1.0}),
                3_003: _stat_vector(**{"hp%": 50.0}),
                3_004: _stat_vector(**{"atk%": 50.0}),
            },
            main_keys={
                3_001: "pyro%",
                3_002: "pyro%",
                3_003: "hp%",
                3_004: "atk%",
            },
        )

        result = build_gcsim_optimizer_inventory_frontier(
            run_input,
            catalog=catalog,
            k_skyline_depth=1,
        )
        rows = result.row_by_artifact_id

        # Set A's much stronger vector may not eliminate the physical row from
        # concrete Set B.  Within Set C, HP% and ATK% mains are incomparable in
        # the full normalized vector and must share the first skyline layer.
        self.assertTrue(all(rows[artifact_id].retained for artifact_id in rows))
        self.assertEqual(rows[3_001].skyline_depth, 1)
        self.assertEqual(rows[3_002].skyline_depth, 1)
        self.assertNotEqual(
            rows[3_001].group.identity_sha256,
            rows[3_002].group.identity_sha256,
        )
        self.assertEqual(rows[3_003].skyline_depth, 1)
        self.assertEqual(rows[3_004].skyline_depth, 1)
        self.assertEqual(
            rows[3_003].group.identity_sha256,
            rows[3_004].group.identity_sha256,
        )
        set_c_diagnostic = next(
            item
            for item in result.group_diagnostics
            if item.group.concrete_set_uid == "ConcreteSetC"
        )
        self.assertEqual(set_c_diagnostic.skyline_layers, ((1, (3_003, 3_004)),))

    def test_eligibility_mask_reason_and_rarity_are_safe_group_boundaries(
        self,
    ) -> None:
        environment = build_oracle_account_environment()
        set_uid = environment.set_refs[0].set_uid
        records = (
            _physical_record(environment, 4_001, set_uid, rarity=4),
            _physical_record(environment, 4_002, set_uid, rarity=4),
            _physical_record(environment, 4_003, set_uid, rarity=4),
            _physical_record(environment, 4_004, set_uid, rarity=5),
        )
        overrides = (
            GcsimOptimizerFourStarEligibilityOverride(
                wearer=environment.wearers[0],
                allowed_set_uids=(set_uid,),
                allowed_artifact_ids=(4_001,),
            ),
            GcsimOptimizerFourStarEligibilityOverride(
                wearer=environment.wearers[1],
                allowed_artifact_ids=(4_003,),
            ),
        )
        run_input = _run_input_for_records(
            environment,
            records,
            four_star_overrides=overrides,
        )
        catalog = _dense_catalog(
            run_input,
            {
                4_001: _stat_vector(hp=1.0, **{"pyro%": 1.0}),
                4_002: _stat_vector(hp=100.0, **{"pyro%": 1.0}),
                4_003: _stat_vector(hp=1_000.0, **{"pyro%": 1.0}),
                4_004: _stat_vector(hp=10_000.0, **{"pyro%": 1.0}),
            },
            main_keys={artifact_id: "pyro%" for artifact_id in range(4_001, 4_005)},
        )

        result = build_gcsim_optimizer_inventory_frontier(
            run_input,
            catalog=catalog,
            k_skyline_depth=1,
        )
        rows = result.row_by_artifact_id

        self.assertEqual(rows[4_001].eligibility.eligible_wearer_slots, (1,))
        self.assertEqual(rows[4_002].eligibility.eligible_wearer_slots, (1,))
        self.assertEqual(rows[4_003].eligibility.eligible_wearer_slots, (1, 2))
        self.assertEqual(rows[4_004].eligibility.eligible_wearer_slots, (1, 2, 3, 4))
        self.assertEqual(
            rows[4_001].eligibility.entries[0].reason_code,
            "explicit_four_star_artifact_id",
        )
        self.assertEqual(
            rows[4_001].eligibility.entries[0].admission_kind,
            GCSIM_OPTIMIZER_INVENTORY_ADMISSION_UNCONDITIONAL,
        )
        self.assertFalse(
            rows[4_001].eligibility.entries[0].required_active_set_uid
        )
        self.assertEqual(
            rows[4_002].eligibility.entries[0].reason_code,
            "explicit_four_star_selected_set",
        )
        self.assertEqual(
            rows[4_002].eligibility.entries[0].admission_kind,
            GCSIM_OPTIMIZER_INVENTORY_ADMISSION_REQUIRES_ACTIVE_SET,
        )
        self.assertEqual(
            rows[4_002].eligibility.entries[0].required_active_set_uid,
            set_uid,
        )
        self.assertNotEqual(
            rows[4_001].group.identity_sha256,
            rows[4_002].group.identity_sha256,
        )
        self.assertNotEqual(
            rows[4_002].group.identity_sha256,
            rows[4_003].group.identity_sha256,
        )
        self.assertNotEqual(
            rows[4_003].group.identity_sha256,
            rows[4_004].group.identity_sha256,
        )
        self.assertEqual(len(result.group_diagnostics), 4)
        self.assertTrue(all(item.retained for item in rows.values()))
        self.assertTrue(
            all(
                item.disposition
                == GCSIM_OPTIMIZER_INVENTORY_FRONTIER_RETAINED
                for item in rows.values()
            )
        )

    def test_no_eligible_wearer_stays_explicitly_in_shadow_reservoir(
        self,
    ) -> None:
        environment = build_oracle_account_environment()
        records = (
            _physical_record(
                environment,
                5_001,
                "UnauthorizedFourStarSet",
                rarity=4,
            ),
        )
        run_input = _run_input_for_records(environment, records)
        catalog = _dense_catalog(
            run_input,
            {5_001: _stat_vector(hp=10.0, **{"pyro%": 1.0})},
            main_keys={5_001: "pyro%"},
        )

        result = build_gcsim_optimizer_inventory_frontier(
            run_input,
            catalog=catalog,
        )
        row = result.row_by_artifact_id[5_001]

        self.assertFalse(result.retained_rows)
        self.assertEqual(tuple(result.shadow_reservoir), (row,))
        self.assertEqual(row.eligibility.bit_mask, 0)
        self.assertEqual(row.eligibility.eligible_wearer_slots, ())
        self.assertIsNone(row.skyline_depth)
        self.assertEqual(
            row.disposition,
            GCSIM_OPTIMIZER_INVENTORY_FRONTIER_SHADOW_INELIGIBLE,
        )
        self.assertEqual(result.counters.ineligible_artifact_count, 1)
        self.assertEqual(result.counters.shadow_artifact_count, 1)
        self.assertEqual(
            result.group_diagnostics[0].shadow_artifact_ids,
            (5_001,),
        )
        self.assertIn("shadow_reservoir", result.to_dict())


def _physical_record(
    environment: OracleAccountEnvironment,
    artifact_id: int,
    set_uid: str,
    *,
    rarity: int = 5,
) -> GcsimOptimizerArtifactRecord:
    template = environment.database.artifact_by_id(
        environment.shared_goblet_id
    )
    assert template is not None
    return replace(
        template,
        artifact_id=artifact_id,
        set_uid=set_uid,
        rarity=rarity,
        level=20 if rarity == 5 else 16,
        default_eligible=rarity == 5,
        substats=tuple(
            replace(item, artifact_id=artifact_id)
            for item in template.substats
        ),
    )


def _run_input_for_records(
    environment: OracleAccountEnvironment,
    records: tuple[GcsimOptimizerArtifactRecord, ...],
    *,
    four_star_overrides: tuple[
        GcsimOptimizerFourStarEligibilityOverride, ...
    ] = (),
) -> GcsimOptimizerRunInput:
    ordered = tuple(sorted(records, key=lambda item: item.artifact_id))
    database_sha256 = _sha256(
        [
            {
                "artifact_id": item.artifact_id,
                "set_uid": item.set_uid,
                "rarity": item.rarity,
            }
            for item in ordered
        ]
    )
    database = replace(
        environment.database,
        database_path="inventory-frontier-fixture.db",
        artifact_database_input_sha256=database_sha256,
        artifacts=ordered,
        raw_substat_row_count=sum(len(item.substats) for item in ordered),
        issues=(),
    )
    request = replace(
        environment.request,
        artifact_database_input_sha256=database_sha256,
        four_star_overrides=four_star_overrides,
    )
    result = build_gcsim_optimizer_run_input(
        request=request,
        config_shell=environment.shell,
        artifact_database=database,
        engine_context=environment.engine,
    )
    assert result.ready and result.run_input is not None, result.issues
    return result.run_input


def _dense_catalog(
    run_input: GcsimOptimizerRunInput,
    vectors: dict[int, tuple[float, ...]],
    *,
    main_keys: dict[int, str],
) -> GcsimOptimizerDenseArtifactCatalog:
    rows: list[GcsimOptimizerDenseArtifact] = []
    for bit_index, record in enumerate(run_input.artifact_database.artifacts):
        vector = vectors[record.artifact_id]
        main_key = main_keys[record.artifact_id]
        main_index = GCSIM_OPTIMIZER_INVENTORY_STAT_AXES.index(main_key)
        rows.append(
            GcsimOptimizerDenseArtifact(
                record=record,
                stats=vector,
                substats=tuple(0.0 for _axis in vector),
                main_key=main_key,
                main_value=vector[main_index],
                content_fingerprint=_sha256(
                    {
                        "artifact_id": record.artifact_id,
                        "set_uid": record.set_uid,
                        "main_key": main_key,
                        "stats": vector,
                    }
                ),
                bit_mask=1 << bit_index,
            )
        )
    return GcsimOptimizerDenseArtifactCatalog(
        artifacts=tuple(rows),
        excluded_counts=(),
        source_artifact_count=len(rows),
        identity_sha256=_sha256(
            [
                [item.artifact_id, item.content_fingerprint]
                for item in rows
            ]
        ),
    )


def _stat_vector(**values: float) -> tuple[float, ...]:
    return tuple(
        float(values.get(axis, 0.0))
        for axis in GCSIM_OPTIMIZER_INVENTORY_STAT_AXES
    )


def _sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    unittest.main()
