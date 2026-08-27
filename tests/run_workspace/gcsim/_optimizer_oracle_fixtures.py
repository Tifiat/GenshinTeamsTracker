"""Small deterministic fixtures shared by Milestone 3 oracle tests.

The account inventory is intentionally artificial: four wearer-scoped 4-star
sets isolate each per-wearer domain, one 5-star goblet is globally contested,
and one duplicate circlet gives two physical assignments the same simulator
text.  It must never be replaced with live account data.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from run_workspace.gcsim.artifact_set_catalog import (
    GcsimArtifactSetCapability,
    GcsimArtifactSetCatalog,
)
from run_workspace.gcsim.optimizer_artifact_database import (
    GcsimOptimizerArtifactDatabaseInput,
    GcsimOptimizerArtifactRecord,
    GcsimOptimizerArtifactSubstat,
)
from run_workspace.gcsim.optimizer_config_shell import (
    GcsimOptimizerConfigShell,
    build_gcsim_optimizer_config_shell,
)
from run_workspace.gcsim.optimizer_engine_context import (
    GcsimOptimizerEngineContext,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerAccountScope,
    GcsimOptimizerFourStarEligibilityOverride,
    GcsimOptimizerOperation,
    GcsimOptimizerOperationRequest,
    GcsimOptimizerSetReference,
    GcsimOptimizerSourceSimulationIdentity,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerSetPool,
    GcsimOptimizerWearerTarget,
    GcsimOptimizerWorkPlan,
)
from run_workspace.gcsim.optimizer_run_input import (
    GcsimOptimizerRunInput,
    build_gcsim_optimizer_run_input,
)


@dataclass(frozen=True, slots=True)
class OracleAccountEnvironment:
    engine: GcsimOptimizerEngineContext
    wearers: tuple[GcsimOptimizerWearerIdentity, ...]
    set_refs: tuple[GcsimOptimizerSetReference, ...]
    targets: tuple[GcsimOptimizerWearerTarget, ...]
    request: GcsimOptimizerOperationRequest
    source_config_text: str
    shell: GcsimOptimizerConfigShell
    database: GcsimOptimizerArtifactDatabaseInput
    run_input: GcsimOptimizerRunInput
    shared_goblet_id: int
    duplicate_alpha_circlet_ids: tuple[int, int]
    malformed_artifact_id: int


def build_oracle_account_environment() -> OracleAccountEnvironment:
    wearers = tuple(
        GcsimOptimizerWearerIdentity(
            team_slot=index,
            account_character_id=20_000 + index,
            gcsim_character_key=key,
        )
        for index, key in enumerate(
            ("alpha", "beta", "gamma", "delta"),
            start=1,
        )
    )
    set_refs = tuple(
        GcsimOptimizerSetReference(
            set_uid=f"OracleSet{key.title()}",
            gcsim_set_key=f"oracleset{key}",
            engine_binding_sha256="3" * 64,
            catalog_fingerprint="4" * 64,
        )
        for key in ("alpha", "beta", "gamma", "delta")
    )
    capabilities = tuple(
        GcsimArtifactSetCapability(
            key=set_ref.gcsim_set_key,
            package_name=set_ref.gcsim_set_key,
            key_constant=set_ref.set_uid,
            max_rarity=4,
            registered=True,
            has_two_piece_code=True,
            has_four_piece_code=True,
            two_piece_modeled=True,
            four_piece_modeled=True,
        )
        for set_ref in set_refs
    )
    catalog = GcsimArtifactSetCatalog(
        source_root="oracle-fixture",
        source_fingerprint="4" * 64,
        sets=capabilities,
    )
    engine = GcsimOptimizerEngineContext(
        engine_id="oracle-engine",
        engine_root="oracle-fixture",
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
    artifacts, own_offpiece_ids, shared_goblet_id, duplicates, malformed_id = (
        _artifact_records(set_refs)
    )
    database = GcsimOptimizerArtifactDatabaseInput(
        database_path="oracle-fixture.db",
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
        raw_substat_row_count=sum(len(item.substats) for item in artifacts),
        issues=(),
    )
    config = _source_config(wearers, set_refs)
    source = GcsimOptimizerSourceSimulationIdentity(
        engine_id=engine.engine_id,
        engine_version=engine.engine_version,
        optimizer_contract_version=engine.optimizer_contract_version,
        artifact_sha256=engine.artifact_sha256,
        engine_tree_sha256=engine.engine_tree_sha256,
        engine_binding_sha256=engine.binding_sha256,
        catalog_fingerprint=catalog.source_fingerprint,
        prepared_config_sha256=hashlib.sha256(config.encode("utf-8")).hexdigest(),
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
            plan_id="reduced_oracle",
            plan_version=1,
            parameters={"domain": "synthetic_four_piece"},
        ),
        account_scope=GcsimOptimizerAccountScope.SELECTED_SET_POOLS,
        selected_set_pools=tuple(
            GcsimOptimizerWearerSetPool(wearer, (set_ref,))
            for wearer, set_ref in zip(wearers, set_refs, strict=True)
        ),
        four_star_overrides=tuple(
            GcsimOptimizerFourStarEligibilityOverride(
                wearer=wearer,
                allowed_set_uids=(set_ref.set_uid,),
                allowed_artifact_ids=own_offpiece_ids[index],
            )
            for index, (wearer, set_ref) in enumerate(
                zip(wearers, set_refs, strict=True)
            )
        ),
        artifact_database_input_sha256=(
            database.artifact_database_input_sha256
        ),
    )
    shell_result = build_gcsim_optimizer_config_shell(
        config,
        source_simulation=source,
        engine_context=engine,
    )
    assert shell_result.ready and shell_result.shell is not None
    run_input_result = build_gcsim_optimizer_run_input(
        request=request,
        config_shell=shell_result.shell,
        artifact_database=database,
        engine_context=engine,
    )
    assert run_input_result.ready and run_input_result.run_input is not None
    targets = tuple(
        GcsimOptimizerWearerTarget(
            wearer=wearer,
            package=GcsimFourPieceTargetPackage(set_ref),
        )
        for wearer, set_ref in zip(wearers, set_refs, strict=True)
    )
    return OracleAccountEnvironment(
        engine=engine,
        wearers=wearers,
        set_refs=set_refs,
        targets=targets,
        request=request,
        source_config_text=config,
        shell=shell_result.shell,
        database=database,
        run_input=run_input_result.run_input,
        shared_goblet_id=shared_goblet_id,
        duplicate_alpha_circlet_ids=duplicates,
        malformed_artifact_id=malformed_id,
    )


def _artifact_records(
    set_refs: tuple[GcsimOptimizerSetReference, ...],
) -> tuple[
    tuple[GcsimOptimizerArtifactRecord, ...],
    tuple[tuple[int, ...], ...],
    int,
    tuple[int, int],
    int,
]:
    artifacts: list[GcsimOptimizerArtifactRecord] = []
    own_offpiece_ids: list[tuple[int, ...]] = []
    artifact_id = 1
    alpha_circlet_ids: list[int] = []
    for wearer_index, set_ref in enumerate(set_refs):
        for position, slot in enumerate(
            GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
            start=1,
        ):
            artifacts.append(
                _artifact(
                    artifact_id,
                    set_uid=set_ref.set_uid,
                    position=position,
                    slot=slot,
                    rarity=4,
                    substat_value="0%",
                    gcsim_set_key=set_ref.gcsim_set_key,
                    set_mapping_status="ready",
                )
            )
            artifact_id += 1
        wearer_offpieces: list[int] = []
        for position, slot in enumerate(
            GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
            start=1,
        ):
            wearer_offpieces.append(artifact_id)
            artifacts.append(
                _artifact(
                    artifact_id,
                    set_uid=f"Offpiece{wearer_index}{position}",
                    position=position,
                    slot=slot,
                    rarity=4,
                    substat_value=f"{position}%",
                )
            )
            if wearer_index == 0 and slot == "circlet":
                alpha_circlet_ids.append(artifact_id)
            artifact_id += 1
        if wearer_index == 0:
            # A second physical circlet with byte-identical simulator stats.
            wearer_offpieces.append(artifact_id)
            artifacts.append(
                _artifact(
                    artifact_id,
                    set_uid="OffpieceAlphaCircletDuplicate",
                    position=5,
                    slot="circlet",
                    rarity=4,
                    substat_value="5%",
                )
            )
            alpha_circlet_ids.append(artifact_id)
            artifact_id += 1
        own_offpiece_ids.append(tuple(wearer_offpieces))

    shared_goblet_id = artifact_id
    artifacts.append(
        _artifact(
            shared_goblet_id,
            set_uid="SharedContestedGoblet",
            position=4,
            slot="goblet",
            rarity=5,
            substat_property_type=28,
            substat_property_name="Elemental Mastery",
            substat_value="100",
        )
    )
    artifact_id += 1
    malformed_id = artifact_id
    malformed = _artifact(
        malformed_id,
        set_uid="Malformed",
        position=3,
        slot="sands",
        rarity=5,
        substat_value="99%",
    )
    artifacts.append(
        GcsimOptimizerArtifactRecord(
            artifact_id=malformed.artifact_id,
            set_uid=malformed.set_uid,
            gcsim_set_key=malformed.gcsim_set_key,
            set_mapping_status=malformed.set_mapping_status,
            position=malformed.position,
            position_key=malformed.position_key,
            rarity=malformed.rarity,
            level=malformed.level,
            main_property_type=None,
            main_property_name=None,
            main_property_value=None,
            main_numeric_value=None,
            substats=malformed.substats,
            calculation_valid=False,
            default_eligible=False,
            issues=(),
            raw_columns=malformed.raw_columns,
        )
    )
    return (
        tuple(sorted(artifacts, key=lambda item: item.artifact_id)),
        tuple(own_offpiece_ids),
        shared_goblet_id,
        tuple(alpha_circlet_ids),
        malformed_id,
    )


def _artifact(
    artifact_id: int,
    *,
    set_uid: str,
    position: int,
    slot: str,
    rarity: int,
    substat_value: str,
    gcsim_set_key: str = "",
    set_mapping_status: str = "unmapped",
    substat_property_type: int = 20,
    substat_property_name: str = "CRIT Rate",
) -> GcsimOptimizerArtifactRecord:
    main_types = (2, 5, 6, 40, 20)
    main_names = ("HP", "ATK", "ATK%", "Pyro DMG", "CRIT Rate")
    main_values = ("3571", "232", "34.8%", "34.8%", "23.2%")
    substat = GcsimOptimizerArtifactSubstat(
        artifact_id=artifact_id,
        slot_index=0,
        property_type=substat_property_type,
        property_name=substat_property_name,
        stored_value=substat_value,
        numeric_value=float(substat_value.rstrip("%")),
        times=1,
        raw_columns=(
            ("artifact_id", artifact_id),
            ("slot_index", 0),
            ("property_type", substat_property_type),
            ("property_name", substat_property_name),
            ("value", substat_value),
            ("times", 1),
        ),
    )
    return GcsimOptimizerArtifactRecord(
        artifact_id=artifact_id,
        set_uid=set_uid,
        gcsim_set_key=gcsim_set_key,
        set_mapping_status=set_mapping_status,
        position=position,
        position_key=slot,
        rarity=rarity,
        level=16 if rarity == 4 else 20,
        main_property_type=main_types[position - 1],
        main_property_name=main_names[position - 1],
        main_property_value=main_values[position - 1],
        main_numeric_value=float(main_values[position - 1].rstrip("%")),
        substats=(substat,),
        calculation_valid=True,
        default_eligible=rarity == 5,
        issues=(),
        raw_columns=(
            ("id", artifact_id),
            ("set_uid", set_uid),
            ("pos", position),
            ("rarity", rarity),
            ("level", 16 if rarity == 4 else 20),
            ("main_property_type", main_types[position - 1]),
            ("main_property_name", main_names[position - 1]),
            ("main_property_value", main_values[position - 1]),
        ),
    )


def _source_config(
    wearers: tuple[GcsimOptimizerWearerIdentity, ...],
    set_refs: tuple[GcsimOptimizerSetReference, ...],
) -> str:
    lines: list[str] = []
    for wearer, set_ref in zip(wearers, set_refs, strict=True):
        key = wearer.gcsim_character_key
        lines.extend(
            (
                f"{key} char lvl=90/90 cons=0 talent=9,9,9;",
                f'{key} add weapon="dullblade" refine=1 lvl=90/90;',
                f'{key} add set="{set_ref.gcsim_set_key}" count=4;',
                f"{key} add stats hp=999999;",
                "",
            )
        )
    lines.extend(
        (
            "options iteration=10 workers=1 swap_delay=12;",
            "target lvl=100 resist=0.1 hp=999999999;",
            "active alpha;",
            "alpha skill;",
            "",
        )
    )
    return "\n".join(lines)
