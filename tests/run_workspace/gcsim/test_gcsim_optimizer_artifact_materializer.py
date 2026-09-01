from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import unittest

from run_workspace.gcsim.artifact_set_catalog import (
    GcsimArtifactSetCapability,
    GcsimArtifactSetCatalog,
)
from run_workspace.gcsim.optimizer_artifact_database import (
    GcsimOptimizerArtifactDatabaseInput,
    GcsimOptimizerArtifactRecord,
    GcsimOptimizerArtifactSubstat,
)
from run_workspace.gcsim.optimizer_artifact_materializer import (
    add_gcsim_optimizer_simulation_witness,
    compile_gcsim_optimizer_team_candidate,
    materialize_gcsim_optimizer_wearer_build,
)
from run_workspace.gcsim.optimizer_config_shell import (
    build_gcsim_optimizer_config_shell,
)
from run_workspace.gcsim.optimizer_engine_context import (
    GcsimOptimizerEngineContext,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerAccountAssignmentWitness,
    GcsimOptimizerAccountScope,
    GcsimOptimizerContractError,
    GcsimOptimizerOperation,
    GcsimOptimizerOperationRequest,
    GcsimOptimizerSetReference,
    GcsimOptimizerSourceSimulationIdentity,
    GcsimOptimizerWearerArtifactAssignment,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerSetPool,
    GcsimOptimizerWearerTarget,
    GcsimOptimizerWorkPlan,
    GcsimTwoPlusTwoTargetPackage,
)
from run_workspace.gcsim.optimizer_run_input import (
    build_gcsim_optimizer_relevant_artifact_sha256,
    build_gcsim_optimizer_run_input,
)


class GcsimOptimizerRunInputTests(unittest.TestCase):
    def test_relevant_hash_excludes_provenance_but_keeps_calculation_values(self) -> None:
        environment = _environment()
        changed_provenance = tuple(
            replace(
                artifact,
                raw_columns=tuple(
                    (
                        key,
                        "changed-source" if key == "import_source" else value,
                    )
                    for key, value in artifact.raw_columns
                ),
            )
            for artifact in environment.database.artifacts
        )
        provenance_database = replace(
            environment.database,
            artifact_database_input_sha256="a" * 64,
            artifacts=changed_provenance,
        )
        changed_value = list(environment.database.artifacts)
        changed_value[0] = replace(
            changed_value[0],
            main_property_value="+1",
            main_numeric_value=1.0,
        )
        value_database = replace(
            environment.database,
            artifact_database_input_sha256="b" * 64,
            artifacts=tuple(changed_value),
        )

        original_hash = build_gcsim_optimizer_relevant_artifact_sha256(
            environment.database
        )
        self.assertEqual(
            original_hash,
            build_gcsim_optimizer_relevant_artifact_sha256(
                provenance_database
            ),
        )
        self.assertNotEqual(
            original_hash,
            build_gcsim_optimizer_relevant_artifact_sha256(value_database),
        )
        self.assertTrue(environment.run_input_result.ready)
        self.assertEqual(
            environment.run_input_result.run_input.run_input_sha256,
            _environment().run_input_result.run_input.run_input_sha256,
        )

    def test_run_input_rejects_request_database_identity_mismatch(self) -> None:
        environment = _environment()
        result = build_gcsim_optimizer_run_input(
            request=environment.request,
            config_shell=environment.shell,
            artifact_database=replace(
                environment.database,
                artifact_database_input_sha256="a" * 64,
            ),
            engine_context=environment.engine,
        )

        self.assertFalse(result.ready)
        self.assertEqual(
            result.issues[0].code,
            "artifact_database_identity_mismatch",
        )


class GcsimOptimizerArtifactMaterializerTests(unittest.TestCase):
    def test_exact_five_piece_build_preserves_zero_and_parameters(self) -> None:
        environment = _environment()
        run_input = environment.run_input_result.run_input
        wearer = environment.wearers[0]
        assignment = _assignment(environment, wearer_index=0, copy=0)
        target = _four_piece_target(environment, wearer_index=0)

        result = materialize_gcsim_optimizer_wearer_build(
            run_input,
            assignment=assignment,
            target=target,
        )

        self.assertTrue(result.ready)
        build = result.build
        assert build is not None
        self.assertEqual(
            tuple(slot for slot, _artifact in build.artifacts_by_slot),
            GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
        )
        self.assertIn(
            'alpha add set="setalpha" count=5 +params=[stacks=4];',
            build.rendered_lines,
        )
        stats_line = build.rendered_lines[-1]
        self.assertIn("hp=0", stats_line)
        self.assertIn("atk=311", stats_line)
        self.assertIn("atk%=0.466", stats_line)
        self.assertIn("pyro%=0.466", stats_line)
        self.assertIn("cr=0.311", stats_line)
        zero = next(
            item
            for item in build.stat_contributions
            if item.source_kind == "main" and item.artifact_slot == "flower"
        )
        self.assertEqual(zero.stored_value, "+0")
        self.assertEqual(zero.normalized_value, "0")
        self.assertNotIn("set_bonus", build.to_dict())

    def test_three_plus_two_has_one_canonical_package_identity(self) -> None:
        environment = _environment()
        run_input = environment.run_input_result.run_input
        wearer = environment.wearers[0]
        assignment = _pair_assignment(environment, wearer_index=0)
        primary, secondary = environment.pool_refs[0]
        target_ab = GcsimOptimizerWearerTarget(
            wearer,
            GcsimTwoPlusTwoTargetPackage(primary, secondary),
        )
        target_ba = GcsimOptimizerWearerTarget(
            wearer,
            GcsimTwoPlusTwoTargetPackage(secondary, primary),
        )

        first = materialize_gcsim_optimizer_wearer_build(
            run_input,
            assignment=assignment,
            target=target_ab,
        )
        second = materialize_gcsim_optimizer_wearer_build(
            run_input,
            assignment=assignment,
            target=target_ba,
        )

        self.assertTrue(first.ready)
        self.assertTrue(second.ready)
        self.assertEqual(
            first.build.wearer_build_identity_sha256,
            second.build.wearer_build_identity_sha256,
        )
        self.assertEqual(
            dict(first.build.set_counts),
            {"SecondaryAlpha": 2, "SetAlpha": 3},
        )
        self.assertEqual(
            {item.count for item in first.build.active_sets},
            {2, 3},
        )

    def test_missing_duplicate_and_wrong_slots_fail_closed(self) -> None:
        environment = _environment()
        wearer = environment.wearers[0]
        valid = dict(
            _assignment(environment, wearer_index=0, copy=0).artifact_ids_by_slot
        )
        missing = dict(valid)
        missing.pop("circlet")
        duplicate = dict(valid)
        duplicate["circlet"] = duplicate["flower"]

        with self.assertRaises(GcsimOptimizerContractError):
            GcsimOptimizerWearerArtifactAssignment(wearer, missing)
        with self.assertRaises(GcsimOptimizerContractError):
            GcsimOptimizerWearerArtifactAssignment(wearer, duplicate)

        swapped = dict(valid)
        swapped["flower"], swapped["plume"] = (
            swapped["plume"],
            swapped["flower"],
        )
        result = materialize_gcsim_optimizer_wearer_build(
            environment.run_input_result.run_input,
            assignment=GcsimOptimizerWearerArtifactAssignment(
                wearer,
                swapped,
            ),
            target=_four_piece_target(environment, wearer_index=0),
        )

        self.assertFalse(result.ready)
        self.assertEqual(
            sum(
                item.code == "artifact_slot_mismatch"
                for item in result.diagnostics
            ),
            2,
        )

    def test_unknown_stat_type_fails_instead_of_being_dropped(self) -> None:
        environment = _environment()
        artifact_id = environment.ids[(0, 0, "primary", "flower")]
        changed = tuple(
            replace(
                artifact,
                main_property_type=999,
                calculation_valid=True,
                default_eligible=True,
            )
            if artifact.artifact_id == artifact_id
            else artifact
            for artifact in environment.database.artifacts
        )
        database = replace(environment.database, artifacts=changed)
        run_input_result = build_gcsim_optimizer_run_input(
            request=environment.request,
            config_shell=environment.shell,
            artifact_database=database,
            engine_context=environment.engine,
        )

        result = materialize_gcsim_optimizer_wearer_build(
            run_input_result.run_input,
            assignment=_assignment(environment, wearer_index=0, copy=0),
            target=_four_piece_target(environment, wearer_index=0),
        )

        self.assertFalse(result.ready)
        self.assertIn(
            "artifact_stat_type_unmapped",
            {item.code for item in result.diagnostics},
        )

    def test_missing_set_parameters_use_engine_default_with_notice(self) -> None:
        environment = _environment(with_parameters=False)
        result = materialize_gcsim_optimizer_wearer_build(
            environment.run_input_result.run_input,
            assignment=_assignment(environment, wearer_index=0, copy=0),
            target=_four_piece_target(environment, wearer_index=0),
        )

        self.assertTrue(result.ready)
        self.assertNotIn("+params", result.build.rendered_lines[0])
        self.assertIn(
            "set_parameters_defaulted",
            {item.code for item in result.diagnostics},
        )

    def test_full_team_replacement_and_simulation_witness_dedup(self) -> None:
        environment = _environment()
        run_input = environment.run_input_result.run_input
        targets = tuple(
            _four_piece_target(environment, wearer_index=index)
            for index in range(4)
        )
        first_witness = _witness(environment, copy=0)
        second_witness = _witness(environment, copy=1)

        first = compile_gcsim_optimizer_team_candidate(
            run_input,
            assignment_witness=first_witness,
            targets=targets,
            execution_identity_sha256="e" * 64,
        )
        second = compile_gcsim_optimizer_team_candidate(
            run_input,
            assignment_witness=second_witness,
            targets=targets,
            execution_identity_sha256="e" * 64,
        )

        self.assertTrue(first.ready)
        self.assertTrue(second.ready)
        first_candidate = first.candidate
        second_candidate = second.candidate
        assert first_candidate is not None
        assert second_candidate is not None
        self.assertNotEqual(
            first_candidate.physical_assignment_sha256,
            second_candidate.physical_assignment_sha256,
        )
        self.assertEqual(
            first_candidate.compiled_config_sha256,
            second_candidate.compiled_config_sha256,
        )
        self.assertEqual(
            first_candidate.simulation_sha256,
            second_candidate.simulation_sha256,
        )
        self.assertNotIn(
            "gtt_optimizer_artifact_block",
            first_candidate.config_text,
        )
        self.assertNotIn("hp=999999;", first_candidate.config_text)
        self.assertNotIn(
            'alpha add set="setalpha" count=4',
            first_candidate.config_text,
        )
        self.assertEqual(
            first_candidate.config_text.count(" add stats "),
            4,
        )
        self.assertIn("active alpha;", first_candidate.config_text)
        self.assertIn("alpha skill;", first_candidate.config_text)

        bucket = add_gcsim_optimizer_simulation_witness(
            None,
            first_candidate,
            max_stored_witnesses=1,
        )
        bucket = add_gcsim_optimizer_simulation_witness(
            bucket,
            second_candidate,
            max_stored_witnesses=1,
        )
        self.assertEqual(len(bucket.stored_witnesses), 1)
        self.assertEqual(bucket.observed_assignment_count, 2)


@dataclass(frozen=True)
class _Environment:
    engine: GcsimOptimizerEngineContext
    wearers: tuple[GcsimOptimizerWearerIdentity, ...]
    pool_refs: tuple[tuple[GcsimOptimizerSetReference, ...], ...]
    request: GcsimOptimizerOperationRequest
    shell: object
    database: GcsimOptimizerArtifactDatabaseInput
    run_input_result: object
    ids: dict[tuple[int, int, str, str], int]


def _environment(*, with_parameters: bool = True) -> _Environment:
    wearers = tuple(
        GcsimOptimizerWearerIdentity(
            team_slot=index,
            account_character_id=10_000 + index,
            gcsim_character_key=key,
        )
        for index, key in enumerate(
            ("alpha", "beta", "gamma", "delta"),
            start=1,
        )
    )
    capabilities: list[GcsimArtifactSetCapability] = []
    pool_refs: list[tuple[GcsimOptimizerSetReference, ...]] = []
    for label in ("alpha", "beta", "gamma", "delta"):
        primary_key = f"set{label}"
        secondary_key = f"secondary{label}"
        capabilities.extend(
            (
                _capability(primary_key, parameterized=True),
                _capability(secondary_key),
            )
        )
        parameters = {"stacks": 4} if with_parameters else {}
        pool_refs.append(
            (
                _set_ref(f"Set{label.title()}", primary_key, parameters),
                _set_ref(f"Secondary{label.title()}", secondary_key, {}),
            )
        )
    catalog = GcsimArtifactSetCatalog(
        source_root="test",
        source_fingerprint="4" * 64,
        sets=tuple(capabilities),
    )
    engine = GcsimOptimizerEngineContext(
        engine_id="engine",
        engine_root="test",
        engine_version="v1",
        optimizer_contract_version="gcsim-v2.42.2",
        artifact_path="gcsim",
        artifact_sha256="1" * 64,
        engine_tree_sha256="2" * 64,
        catalog=catalog,
        manifest_artifact_sha256="1" * 64,
        manifest_engine_tree_sha256="2" * 64,
        binding_sha256="3" * 64,
        trusted=True,
    )
    config = _source_config(
        wearers,
        tuple(pool_refs),
        with_parameters=with_parameters,
    )
    source = GcsimOptimizerSourceSimulationIdentity(
        engine_id="engine",
        engine_version="v1",
        optimizer_contract_version="gcsim-v2.42.2",
        artifact_sha256="1" * 64,
        engine_tree_sha256="2" * 64,
        engine_binding_sha256="3" * 64,
        catalog_fingerprint="4" * 64,
        prepared_config_sha256=hashlib.sha256(config.encode()).hexdigest(),
        rotation_sha256="6" * 64,
        target_sha256="7" * 64,
        simulation_options_sha256="8" * 64,
        wearers=wearers,
    )
    request = GcsimOptimizerOperationRequest(
        operation=GcsimOptimizerOperation.ACCOUNT_ARTIFACTS,
        source_simulation=source,
        work_plan=GcsimOptimizerWorkPlan(
            operation=GcsimOptimizerOperation.ACCOUNT_ARTIFACTS,
            plan_id="quality_first",
            plan_version=1,
            parameters={},
        ),
        account_scope=GcsimOptimizerAccountScope.SELECTED_SET_POOLS,
        selected_set_pools=tuple(
            GcsimOptimizerWearerSetPool(wearer, refs)
            for wearer, refs in zip(wearers, pool_refs, strict=True)
        ),
        include_2p2p=True,
        artifact_database_input_sha256="9" * 64,
    )
    shell_result = build_gcsim_optimizer_config_shell(
        config,
        source_simulation=source,
        engine_context=engine,
    )
    assert shell_result.ready
    artifacts, ids = _artifact_records(tuple(pool_refs))
    database = GcsimOptimizerArtifactDatabaseInput(
        database_path="test.db",
        artifact_database_input_sha256="9" * 64,
        engine_binding_sha256="3" * 64,
        catalog_fingerprint="4" * 64,
        artifact_columns=(
            "id",
            "set_uid",
            "pos",
            "rarity",
            "level",
            "main_property_type",
            "main_property_name",
            "main_property_value",
            "import_source",
        ),
        substat_columns=(
            "artifact_id",
            "slot_index",
            "property_type",
            "property_name",
            "value",
            "times",
        ),
        artifacts=artifacts,
        raw_substat_row_count=len(artifacts),
        issues=(),
    )
    run_input_result = build_gcsim_optimizer_run_input(
        request=request,
        config_shell=shell_result.shell,
        artifact_database=database,
        engine_context=engine,
    )
    assert run_input_result.ready
    return _Environment(
        engine=engine,
        wearers=wearers,
        pool_refs=tuple(pool_refs),
        request=request,
        shell=shell_result.shell,
        database=database,
        run_input_result=run_input_result,
        ids=ids,
    )


def _artifact_records(
    pool_refs: tuple[tuple[GcsimOptimizerSetReference, ...], ...],
) -> tuple[
    tuple[GcsimOptimizerArtifactRecord, ...],
    dict[tuple[int, int, str, str], int],
]:
    main_types = (2, 5, 6, 40, 20)
    main_names = ("HP", "ATK", "ATK%", "Pyro DMG", "CRIT Rate")
    main_values = ("+0", "311", "46.6%", "46.6%", "31.1%")
    artifacts: list[GcsimOptimizerArtifactRecord] = []
    ids: dict[tuple[int, int, str, str], int] = {}
    artifact_id = 1
    for copy in (0, 1):
        for wearer_index, refs in enumerate(pool_refs):
            for set_kind, set_ref in (
                ("primary", refs[0]),
                ("secondary", refs[1]),
            ):
                for position, slot in enumerate(
                    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
                    start=1,
                ):
                    ids[(copy, wearer_index, set_kind, slot)] = artifact_id
                    substat = GcsimOptimizerArtifactSubstat(
                        artifact_id=artifact_id,
                        slot_index=0,
                        property_type=20,
                        property_name="CRIT Rate",
                        stored_value="+0",
                        numeric_value=0.0,
                        times=0,
                        raw_columns=(
                            ("artifact_id", artifact_id),
                            ("slot_index", 0),
                            ("property_type", 20),
                            ("property_name", "CRIT Rate"),
                            ("value", "+0"),
                            ("times", 0),
                        ),
                    )
                    artifacts.append(
                        GcsimOptimizerArtifactRecord(
                            artifact_id=artifact_id,
                            set_uid=set_ref.set_uid,
                            gcsim_set_key=set_ref.gcsim_set_key,
                            set_mapping_status="ready",
                            position=position,
                            position_key=slot,
                            rarity=5,
                            level=20,
                            main_property_type=main_types[position - 1],
                            main_property_name=main_names[position - 1],
                            main_property_value=main_values[position - 1],
                            main_numeric_value=float(
                                main_values[position - 1].rstrip("%")
                            ),
                            substats=(substat,),
                            calculation_valid=True,
                            default_eligible=True,
                            issues=(),
                            raw_columns=(
                                ("id", artifact_id),
                                ("set_uid", set_ref.set_uid),
                                ("pos", position),
                                ("rarity", 5),
                                ("level", 20),
                                (
                                    "main_property_type",
                                    main_types[position - 1],
                                ),
                                (
                                    "main_property_name",
                                    main_names[position - 1],
                                ),
                                (
                                    "main_property_value",
                                    main_values[position - 1],
                                ),
                                ("import_source", "any-source"),
                            ),
                        )
                    )
                    artifact_id += 1
    return tuple(artifacts), ids


def _source_config(
    wearers: tuple[GcsimOptimizerWearerIdentity, ...],
    pool_refs: tuple[tuple[GcsimOptimizerSetReference, ...], ...],
    *,
    with_parameters: bool,
) -> str:
    lines: list[str] = []
    for wearer, refs in zip(wearers, pool_refs, strict=True):
        suffix = " +params=[stacks=4]" if with_parameters else ""
        lines.extend(
            (
                f"{wearer.gcsim_character_key} char lvl=90/90 cons=0 talent=9,9,9;",
                (
                    f'{wearer.gcsim_character_key} add weapon="dullblade" '
                    "refine=1 lvl=90/90;"
                ),
                (
                    f'{wearer.gcsim_character_key} add set="'
                    f'{refs[0].gcsim_set_key}" count=4{suffix};'
                ),
                f"{wearer.gcsim_character_key} add stats hp=999999;",
                "",
            )
        )
    lines.extend(
        (
            "options iteration=1000 swap_delay=12;",
            "target lvl=100 resist=0.1 hp=999999999;",
            "active alpha;",
            "alpha skill;",
            "",
        )
    )
    return "\n".join(lines)


def _assignment(
    environment: _Environment,
    *,
    wearer_index: int,
    copy: int,
) -> GcsimOptimizerWearerArtifactAssignment:
    return GcsimOptimizerWearerArtifactAssignment(
        wearer=environment.wearers[wearer_index],
        artifact_ids_by_slot={
            slot: environment.ids[
                (copy, wearer_index, "primary", slot)
            ]
            for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
        },
    )


def _pair_assignment(
    environment: _Environment,
    *,
    wearer_index: int,
) -> GcsimOptimizerWearerArtifactAssignment:
    return GcsimOptimizerWearerArtifactAssignment(
        wearer=environment.wearers[wearer_index],
        artifact_ids_by_slot={
            slot: environment.ids[
                (
                    0,
                    wearer_index,
                    "primary" if index < 3 else "secondary",
                    slot,
                )
            ]
            for index, slot in enumerate(GCSIM_OPTIMIZER_ARTIFACT_SLOTS)
        },
    )


def _four_piece_target(
    environment: _Environment,
    *,
    wearer_index: int,
) -> GcsimOptimizerWearerTarget:
    return GcsimOptimizerWearerTarget(
        environment.wearers[wearer_index],
        GcsimFourPieceTargetPackage(
            environment.pool_refs[wearer_index][0]
        ),
    )


def _witness(
    environment: _Environment,
    *,
    copy: int,
) -> GcsimOptimizerAccountAssignmentWitness:
    return GcsimOptimizerAccountAssignmentWitness(
        request_sha256=environment.request.request_sha256,
        artifact_database_input_sha256=(
            environment.database.artifact_database_input_sha256
        ),
        wearer_assignments=tuple(
            _assignment(environment, wearer_index=index, copy=copy)
            for index in range(4)
        ),
    )


def _set_ref(
    set_uid: str,
    set_key: str,
    parameters: dict[str, int],
) -> GcsimOptimizerSetReference:
    return GcsimOptimizerSetReference(
        set_uid=set_uid,
        gcsim_set_key=set_key,
        engine_binding_sha256="3" * 64,
        catalog_fingerprint="4" * 64,
        set_parameters=parameters,
    )


def _capability(
    key: str,
    *,
    parameterized: bool = False,
) -> GcsimArtifactSetCapability:
    return GcsimArtifactSetCapability(
        key=key,
        package_name=key,
        key_constant=key.title(),
        max_rarity=5,
        registered=True,
        has_two_piece_code=True,
        has_four_piece_code=True,
        two_piece_modeled=True,
        four_piece_modeled=True,
        parameter_keys=("stacks",) if parameterized else (),
    )


if __name__ == "__main__":
    unittest.main()
