"""Common immutable input preparation with explicit mode selection.

No search/formula evaluation belongs here. Schema-v1 identity inputs are kept.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .config_assembly import ASSEMBLY_SHELL_UNBOUNDED_DUMMY_ROTATION
from .engine_store import load_engine_manifest
from .optimizer_artifact_database import load_gcsim_optimizer_artifact_database_input
from .optimizer_artifact_materializer import materialize_gcsim_optimizer_artifact_stat_vector
from .optimizer_engine_context import GcsimOptimizerEngineContextError, load_active_gcsim_optimizer_engine_context
from .optimizer_go_contracts import (
    GCSIM_OPTIMIZER_GO_SCHEMA_VERSION, GCSIM_OPTIMIZER_GO_REQUEST_KIND,
    GCSIM_OPTIMIZER_GO_STRATEGY_ID, canonical_sha256, text_sha256,
    write_canonical, write_diagnostic_json as _write_json,
)
from .optimizer_go_requests import (
    GcsimOptimizerGoError, GcsimOptimizerGoRequest,
    REQUIRED_ENGINE_CAPABILITIES, FINITE_ENERGY_ENGINE_CAPABILITY,
    DEFAULT_DEVELOPMENT_TIMEOUT_MS,
)
from .optimizer_go_selected_inputs import (
    GcsimOptimizerGoSelectedInputError, bind_selected_report_config_and_snapshot,
    enforce_gcsim_optimizer_mvp_energy_policy, load_selected_equipped_team_snapshot,
    selected_virtual_inventory_baseline_summaries,
    selected_team_with_equipped_snapshot_artifacts, selected_set_requirements,
)
from .optimizer_product_contracts import GCSIM_OPTIMIZER_ARTIFACT_SLOTS, GcsimOptimizerWearerIdentity
from .optimizer_rotation_policy import normalize_optimizer_rotation_shell
from .selected_team_config import (
    build_selected_team_full_config_report, VIRTUAL_ARTIFACT_POLICY_OWNED_BUILD,
    VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE,
    VIRTUAL_ARTIFACT_POLICY_THEORY_BASELINE,
)
from .settings import GcsimRunSettings
from .source_manifest_build import canonical_json as canonical_source_manifest_json


VIRTUAL_ARTIFACT_POLICY_BY_MODE = {
    "selected": VIRTUAL_ARTIFACT_POLICY_OWNED_BUILD,
    "all_sets": VIRTUAL_ARTIFACT_POLICY_OPTIMIZER_INVENTORY_BASELINE,
    "theory": VIRTUAL_ARTIFACT_POLICY_THEORY_BASELINE,
}


_CHARACTER_RE = re.compile(r"(?im)^\s*([a-z0-9_]+)\s+char\b")
_WEAPON_RE = re.compile(
    r'(?im)^\s*(?P<actor>[a-z0-9_]+)\s+add\s+weapon="(?P<weapon>[^"]+)"'
)
_TARGET_RE = re.compile(r"(?im)^\s*target\b[^;]*;")


def _report_issue_statuses(issues: Any) -> set[str]:
    """Read serialized full-config issues without assuming dataclass instances."""

    statuses: set[str] = set()
    for issue in issues or ():
        if isinstance(issue, Mapping):
            status = issue.get("status")
        else:
            status = getattr(issue, "status", None)
        if status:
            statuses.add(str(status))
    return statuses


_STAT_KEY = {
    "hp": "hp",
    "atk": "atk",
    "def": "def",
    "hp%": "hp_percent",
    "atk%": "atk_percent",
    "def%": "def_percent",
    "em": "em",
    "er": "energy_recharge",
    "cr": "crit_rate",
    "cd": "crit_damage",
    "pyro%": "pyro_damage_bonus",
    "hydro%": "hydro_damage_bonus",
    "electro%": "electro_damage_bonus",
    "cryo%": "cryo_damage_bonus",
    "anemo%": "anemo_damage_bonus",
    "geo%": "geo_damage_bonus",
    "dendro%": "dendro_damage_bonus",
    "phys%": "physical_damage_bonus",
    "heal": "healing_bonus",
}

def _bound_artifact_registry_source(engine_root: Path) -> Path:
    shortcut_root = engine_root / "pkg" / "shortcut"
    for name in ("artifact.dm.go", "artifacts.go"):
        path = shortcut_root / name
        if path.is_file():
            return path
    raise GcsimOptimizerGoError(
        "active_engine_artifact_registry_missing",
        f"Selected GCSIM engine artifact registry is missing: {shortcut_root}",
    )


def _optimizer_result_options(
    request: GcsimOptimizerGoRequest,
    *,
    theory_mode: bool,
) -> dict[str, int | bool] | None:
    """Validate Selected/All result controls; Theory keeps its fixed contract."""

    if theory_mode:
        return None
    if type(request.expanded_limits) is not bool:
        raise GcsimOptimizerGoError(
            "result_options_invalid", "expanded_limits must be a boolean."
        )
    from run_workspace.gcsim.settings import optimizer_output_limits
    group_max, build_max = optimizer_output_limits(request.fast_mode, request.expanded_limits)
    for name, limit in (("set_group_limit", group_max), ("builds_per_group", build_max)):
        value = getattr(request, name)
        if type(value) is not int or not 1 <= value <= limit:
            raise GcsimOptimizerGoError(
                "result_options_invalid",
                f"{name} must be an integer from 1 through {limit}.",
            )
    if type(request.fast_mode) is not bool:
        raise GcsimOptimizerGoError(
            "result_options_invalid", "fast_mode must be a boolean."
        )
    options = {
        "set_group_limit": request.set_group_limit,
        "builds_per_group": request.builds_per_group,
        "fast_mode": request.fast_mode,
    }
    # Go's canonical request serializer omits the optional false value. Keep
    # the default request bytes identical while sending true for the expanded
    # contract.
    if request.expanded_limits:
        options["expanded_limits"] = True
    return options


def prepare_optimizer_inputs(
    request: GcsimOptimizerGoRequest,
    run_dir: Path,
    *,
    mode: str,
) -> dict[str, Any]:
    try:
        virtual_artifact_policy = VIRTUAL_ARTIFACT_POLICY_BY_MODE[mode]
    except KeyError as exc:
        raise GcsimOptimizerGoError("optimizer_mode_invalid", f"Unknown optimizer mode: {mode!r}.") from exc
    theory_mode = mode == "theory"
    inventory_baseline_mode = mode == "all_sets"
    result_options = _optimizer_result_options(request, theory_mode=theory_mode)
    if len(request.seeds) < 2 or len(set(request.seeds)) != len(request.seeds):
        raise GcsimOptimizerGoError(
            "seed_panel_invalid", "Selected requires at least two unique seeds."
        )
    if type(request.product_timeout_ms) is not int or request.product_timeout_ms < 0:
        raise GcsimOptimizerGoError(
            "timeout_invalid", "Selected timeout must be a non-negative integer."
        )
    try:
        engine_context = load_active_gcsim_optimizer_engine_context(
            store_dir=request.engine_store_dir
        )
    except GcsimOptimizerEngineContextError as exc:
        raise GcsimOptimizerGoError(
            "optimizer_engine_unavailable",
            f"Active GCSIM engine cannot run Selected: {exc}",
        ) from exc
    if request.expected_engine_id and engine_context.engine_id != request.expected_engine_id:
        raise GcsimOptimizerGoError(
            "active_engine_changed",
            f"Selected GCSIM engine changed from {request.expected_engine_id} "
            f"to {engine_context.engine_id} before optimizer preparation.",
        )
    capabilities = frozenset(engine_context.capabilities)
    required_capabilities = set(REQUIRED_ENGINE_CAPABILITIES)
    if not request.infinite_energy_enabled:
        required_capabilities.add(FINITE_ENERGY_ENGINE_CAPABILITY)
    missing = sorted(required_capabilities - capabilities)
    if missing:
        raise GcsimOptimizerGoError(
            "optimizer_engine_capability_missing",
            "Active GCSIM engine cannot run Selected; missing: " + ", ".join(missing),
        )
    artifact_registry_source = _bound_artifact_registry_source(
        Path(engine_context.engine_root)
    )
    rotation_policy = normalize_optimizer_rotation_shell(request.rotation_shell_text)
    rotation_path = run_dir / "rotation.from-ui.txt"
    rotation_path.write_text(rotation_policy.source_text, encoding="utf-8")
    effective_rotation_path = rotation_path
    if rotation_policy.changed:
        effective_rotation_path = run_dir / "rotation.optimizer-normalized.txt"
        effective_rotation_path.write_text(
            rotation_policy.optimizer_text,
            encoding="utf-8",
        )
        _write_json(
            run_dir / "rotation-normalization.json",
            {
                "schema_version": 1,
                "schema_kind": "gtt_optimizer_rotation_normalization_v1",
                "reason": rotation_policy.warning_code,
                "duration_seconds": rotation_policy.duration_seconds,
                "source_sha256": text_sha256(rotation_policy.source_text),
                "optimizer_sha256": text_sha256(rotation_policy.optimizer_text),
                "editor_text_changed": False,
            },
        )
    report = build_selected_team_full_config_report(
        db_path=request.db_path,
        selected_team=request.selected_team,
        team_index=max(0, int(request.team_index)),
        rotation_shell_path=effective_rotation_path,
        run_dir=run_dir,
        write_config=False,
        artifact_set_registry_source=artifact_registry_source,
        run_settings=GcsimRunSettings(boosted_energy_enabled=False),
        virtual_artifact_policy=virtual_artifact_policy,
    )
    if theory_mode:
        _require_prepared_report(report, theory_mode=True)
        config_text = enforce_gcsim_optimizer_mvp_energy_policy(
            report.full_config.assembly.config_text,
            ignore_burst_energy=bool(request.infinite_energy_enabled),
        )
        character_keys = tuple(
            match.group(1).casefold() for match in _CHARACTER_RE.finditer(config_text)
        )
        if len(character_keys) != 4 or len(set(character_keys)) != 4:
            raise GcsimOptimizerGoError(
                "selected_team_requires_four_characters",
                "Selected requires exactly four distinct prepared characters.",
            )
        request_wearers = _request_theory_wearers(
            report.team.payload,
            config_text=config_text,
        )
        theory_anchor_sha256 = canonical_sha256(
            {
                "kind": "gtt.optimizer.theory_neutral_anchor.v2",
                "wearers": request_wearers,
            }
        )
        snapshot = None
        request_artifacts: list[dict[str, Any]] = []
        artifact_input_sha256 = theory_anchor_sha256
        snapshot_equipment_sha256 = theory_anchor_sha256
        snapshot_sha256 = theory_anchor_sha256
    else:
        loaded = load_gcsim_optimizer_artifact_database_input(
            request.db_path, engine_context=engine_context
        )
        if not loaded.ready or loaded.database_input is None:
            raise GcsimOptimizerGoError(
                "artifact_database_not_ready",
                f"Artifact database cannot be used by Selected: {loaded.issues!r}",
            )
        database = loaded.database_input
        prepared_characters = tuple(
            row
            for row in report.team.payload.get("characters", ())
            if isinstance(row, Mapping)
        )
        character_keys = tuple(
            str(
                (row.get("mapping") if isinstance(row.get("mapping"), Mapping) else {}).get(
                    "gcsim_key"
                )
                or ""
            ).casefold()
            for row in prepared_characters
        )
        if len(character_keys) != 4 or len(set(character_keys)) != 4 or any(
            not key for key in character_keys
        ):
            raise GcsimOptimizerGoError(
                "selected_team_requires_four_characters",
                "Selected requires exactly four distinct prepared characters.",
            )
        virtual_row_list: list[tuple[int, str]] = []
        for detail, character in zip(
            getattr(report.team, "characters", ()),
            report.team.payload.get("characters", ()),
            strict=True,
        ):
            if not isinstance(character, Mapping):
                continue
            mapping = character.get("mapping")
            if not isinstance(mapping, Mapping):
                continue
            if mapping.get("source") != "virtual_gcsim_slot_override":
                continue
            virtual_row_list.append(
                (
                    detail.slot_index,
                    str(mapping.get("gcsim_key") or "").casefold(),
                )
            )
        virtual_rows = tuple(virtual_row_list)
        virtual_keys = tuple(key for _slot, key in virtual_rows if key)
        try:
            snapshot = load_selected_equipped_team_snapshot(
                request.db_path,
                artifact_database=database,
                character_keys=character_keys,
                virtual_character_keys=virtual_keys if inventory_baseline_mode else (),
            )
        except GcsimOptimizerGoSelectedInputError as exc:
            code = (
                "virtual_inventory_baseline_unavailable"
                if inventory_baseline_mode and virtual_keys
                else "selected_equipment_not_ready"
            )
            raise GcsimOptimizerGoError(code, str(exc)) from exc
        baselines_by_slot: dict[int, dict[str, Any]] = {}
        if inventory_baseline_mode and virtual_rows:
            try:
                summaries_by_key = selected_virtual_inventory_baseline_summaries(
                    database,
                    snapshot=snapshot,
                )
            except GcsimOptimizerGoSelectedInputError as exc:
                raise GcsimOptimizerGoError(
                    "virtual_inventory_baseline_unavailable", str(exc)
                ) from exc
            baselines_by_slot = {
                slot_index: summaries_by_key[key]
                for slot_index, key in virtual_rows
                if key in summaries_by_key
            }
            if len(baselines_by_slot) != len(virtual_rows):
                raise GcsimOptimizerGoError(
                    "virtual_inventory_baseline_unavailable",
                    "Could not materialize every virtual character baseline.",
                )
        try:
            snapshot_selected_team = selected_team_with_equipped_snapshot_artifacts(
                request.selected_team,
                artifact_database=database,
                snapshot=snapshot,
            )
        except GcsimOptimizerGoSelectedInputError as exc:
            raise GcsimOptimizerGoError(
                "selected_equipment_not_ready", str(exc)
            ) from exc
        report = build_selected_team_full_config_report(
            db_path=request.db_path,
            selected_team=snapshot_selected_team,
            team_index=max(0, int(request.team_index)),
            rotation_shell_path=effective_rotation_path,
            run_dir=run_dir,
            write_config=False,
            artifact_set_registry_source=artifact_registry_source,
            run_settings=GcsimRunSettings(boosted_energy_enabled=False),
            virtual_artifact_policy=virtual_artifact_policy,
            virtual_artifact_baselines=baselines_by_slot,
        )
        _require_prepared_report(report, theory_mode=False)
        config_text = enforce_gcsim_optimizer_mvp_energy_policy(
            report.full_config.assembly.config_text,
            ignore_burst_energy=bool(request.infinite_energy_enabled),
        )
        rebuilt_character_keys = tuple(
            match.group(1).casefold()
            for match in _CHARACTER_RE.finditer(config_text)
        )
        if rebuilt_character_keys != character_keys:
            raise GcsimOptimizerGoError(
                "selected_snapshot_identity_changed",
                "Current equipment snapshot changed the prepared team identity.",
            )
        wearers = bind_selected_report_config_and_snapshot(
            report.team.payload,
            config_text=config_text,
            artifact_database=database,
            snapshot=snapshot,
        )
        request_wearers = _request_wearers(config_text, wearers)
        request_artifacts = _request_artifacts(
            database,
            character_keys[0],
            snapshot,
        )
        artifact_input_sha256 = database.artifact_database_input_sha256
        snapshot_equipment_sha256 = snapshot.equipment_rows_sha256
        snapshot_sha256 = snapshot.snapshot_sha256
    target_matches = tuple(match.group(0).strip() for match in _TARGET_RE.finditer(config_text))
    if len(target_matches) != 1:
        raise GcsimOptimizerGoError(
            "selected_target_invalid", "Selected requires exactly one DPS target line."
        )
    target_text = target_matches[0] + "\n"
    engine_manifest = load_engine_manifest(Path(engine_context.engine_root))
    source_manifest_path = Path(engine_context.engine_root) / "build" / "gtt-source-manifest-body.json"
    if not source_manifest_path.is_file():
        raise GcsimOptimizerGoError(
            "source_manifest_missing", "Selected engine source manifest is missing."
        )
    # The engine embeds the canonical JSON body hash, not the on-disk hash
    # (the build writer appends a platform-dependent line ending).
    try:
        source_manifest_body = json.loads(source_manifest_path.read_bytes())
        source_manifest_sha256 = hashlib.sha256(
            canonical_source_manifest_json(source_manifest_body).encode("utf-8")
        ).hexdigest()
    except (OSError, ValueError, TypeError) as exc:
        raise GcsimOptimizerGoError(
            "source_manifest_invalid", "Selected engine source manifest is invalid."
        ) from exc
    patch_manifest_sha256 = str(
        engine_manifest.patch_metadata.get("patch_stack_sha256", "") or ""
    ).casefold()
    if not _is_sha256(patch_manifest_sha256):
        raise GcsimOptimizerGoError(
            "patch_manifest_missing", "Selected engine patch identity is missing."
        )
    engine_binding_sha256 = canonical_sha256(
        {
            "kind": "gtt.standalone_engine_binding.v1",
            "artifact_sha256": engine_context.artifact_sha256,
            "source_manifest_sha256": source_manifest_sha256,
            "patch_manifest_sha256": patch_manifest_sha256,
        }
    )
    trace_context_sha256 = canonical_sha256(
        {
            "kind": "gtt.optimizer.selected.trace_context.v1",
            "engine_binding_sha256": engine_binding_sha256,
            "artifact_database_input_sha256": artifact_input_sha256,
            "equipment_rows_sha256": snapshot_equipment_sha256,
            "snapshot_sha256": snapshot_sha256,
            "prepared_config_sha256": text_sha256(config_text),
            "rotation_sha256": text_sha256(rotation_policy.optimizer_text),
            "target_sha256": text_sha256(target_text),
            "seeds": list(request.seeds),
            "ignore_burst_energy": bool(request.infinite_energy_enabled),
        }
    )
    context = {
        "prepared_config": _source_text(config_text),
        "rotation": _source_text(rotation_policy.optimizer_text),
        "target": _source_text(target_text),
    }
    context["context_sha256"] = canonical_sha256(
        {
            "prepared_config_sha256": context["prepared_config"]["sha256"],
            "rotation_sha256": context["rotation"]["sha256"],
            "target_sha256": context["target"]["sha256"],
        }
    )
    context["trace_context_sha256"] = trace_context_sha256
    request_payload = {
        "schema_version": GCSIM_OPTIMIZER_GO_SCHEMA_VERSION,
        "schema_kind": GCSIM_OPTIMIZER_GO_REQUEST_KIND,
        "strategy_id": GCSIM_OPTIMIZER_GO_STRATEGY_ID,
        "engine": {
            "binary_path": str(Path(engine_context.artifact_path).resolve()).replace("\\", "/"),
            "artifact_sha256": engine_context.artifact_sha256,
            "binding_sha256": engine_binding_sha256,
            "source_manifest_sha256": source_manifest_sha256,
            "patch_manifest_sha256": patch_manifest_sha256,
            "capabilities": sorted(capabilities),
        },
        "context": context,
        "wearers": request_wearers,
        "artifacts": request_artifacts,
        "legality": {
            "fixed_four_piece": True,
            "max_off_set_pieces_per_wearer": 1,
            "globally_unique_artifact_ids": True,
            "default_minimum_rarity": 5,
            "authorized_lower_rarity_artifact_ids": [],
        },
        "stochastic": {
            "mode": "equal_weight_fixed_panel_v1",
            "seeds": sorted(request.seeds),
        },
        "budgets": {
            "product_timeout_ms": int(request.product_timeout_ms),
            "development_timeout_ms": (
                0
                if request.product_timeout_ms == 0
                else max(DEFAULT_DEVELOPMENT_TIMEOUT_MS, int(request.product_timeout_ms))
            ),
        },
        "cancellation": {"mode": "process_interrupt_v1"},
    }
    if result_options is not None:
        request_payload["result_options"] = result_options
    if theory_mode:
        request_payload["legality"]["fixed_four_piece"] = False
        request_payload["legality"]["max_off_set_pieces_per_wearer"] = 0
        request_payload["legality"]["theory_search"] = True
    elif any("selected_sets" in row for row in request_payload["wearers"]):
        request_payload["legality"]["fixed_four_piece"] = False
        request_payload["legality"]["fixed_set_packages"] = True
    request_sha256 = canonical_sha256(request_payload)
    write_canonical(run_dir / "request.json", request_payload)
    return {
        "request": request_payload,
        "request_sha256": request_sha256,
        "snapshot": snapshot,
        "adapter_warnings": (
            (
                {
                    "code": rotation_policy.warning_code,
                    "duration_seconds": rotation_policy.duration_seconds,
                },
            )
            if rotation_policy.changed
            else ()
        ),
    }


def _require_prepared_report(report: Any, *, theory_mode: bool) -> None:
    if report.ready and not report.issues:
        return
    issue_statuses = _report_issue_statuses(report.issues)
    if ASSEMBLY_SHELL_UNBOUNDED_DUMMY_ROTATION in issue_statuses:
        raise GcsimOptimizerGoError(
            "rotation_unbounded_dummy_target",
            (
                "The rotation uses while 1 with the pinned high-HP dummy. "
                "Use a finite loop/action list so the optimizer can capture "
                "one complete rotation schedule."
            ),
        )
    if theory_mode and "virtual_gcsim_profile_incomplete" in issue_statuses:
        raise GcsimOptimizerGoError(
            "theory_profile_incomplete",
            "Complete the virtual character and weapon profile before running Theory.",
        )
    raise GcsimOptimizerGoError(
        "selected_config_not_ready",
        "Current team cannot be prepared for "
        f"{'Theory' if theory_mode else 'Selected'}: {report.issues!r}",
    )


def _request_wearers(config_text: str, wearers: tuple[Any, ...]) -> list[dict[str, Any]]:
    weapons = {
        match.group("actor").casefold(): match.group("weapon").casefold()
        for match in _WEAPON_RE.finditer(config_text)
    }
    output = []
    for wearer in sorted(wearers, key=lambda row: row.actor_key):
        selected = selected_set_requirements(wearer.active_sets)
        output.append(
            {
                "wearer_key": wearer.actor_key,
                "weapon_key": weapons[wearer.actor_key],
                **({"selected_set_uid": selected[0][0]} if len(selected) == 1 else {
                    "selected_sets": [{"set_uid": uid, "count": count} for uid, count in selected]
                }),
                "current_artifacts": [
                    {
                        "wearer_key": wearer.actor_key,
                        "slot": slot,
                        "artifact_id": artifact_id,
                    }
                    for slot, artifact_id in wearer.artifact_ids_by_slot
                ],
            }
        )
    return output


def _request_theory_wearers(
    payload: Mapping[str, Any],
    *,
    config_text: str,
) -> list[dict[str, Any]]:
    """Build one inventory-independent neutral Theory anchor for every wearer."""

    weapons = {
        match.group("actor").casefold(): match.group("weapon").casefold()
        for match in _WEAPON_RE.finditer(config_text)
    }
    characters = tuple(
        item for item in payload.get("characters") or () if isinstance(item, Mapping)
    )
    if len(characters) != 4:
        raise GcsimOptimizerGoError(
            "theory_team_requires_four_characters",
            "Theory requires exactly four prepared character profiles.",
        )
    output: list[dict[str, Any]] = []
    for character in characters:
        mapping = character.get("mapping") if isinstance(character.get("mapping"), Mapping) else {}
        actor = str(mapping.get("gcsim_key") or "").strip().casefold()
        build = character.get("artifact_build") if isinstance(character.get("artifact_build"), Mapping) else {}
        if not actor or actor not in weapons or not build:
            raise GcsimOptimizerGoError(
                "theory_profile_incomplete",
                "Theory requires a complete character profile and a compatible weapon.",
            )
        wearer: dict[str, Any] = {
            "wearer_key": actor,
            "weapon_key": weapons[actor],
        }
        source_kind = str(build.get("source_kind") or "")
        if source_kind != "theory_neutral_baseline":
            raise GcsimOptimizerGoError(
                "theory_baseline_invalid",
                f"Theory did not prepare a neutral artifact baseline for {actor}.",
            )
        mains = build.get("baseline_main_stats")
        if not isinstance(mains, Mapping):
            raise GcsimOptimizerGoError(
                "theory_baseline_invalid",
                "The Theory stat baseline is incomplete.",
            )
        normalized_mains = []
        normalized_values = {
            "flower": ("hp", "4780"),
            "plume": ("atk", "311"),
            "sands": ("atk_percent", "0.466"),
            "goblet": ("atk_percent", "0.466"),
            "circlet": ("crit_rate", "0.311"),
        }
        for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
            expected_key, value = normalized_values[slot]
            if str(mains.get(slot) or "") != expected_key:
                raise GcsimOptimizerGoError(
                    "theory_baseline_invalid",
                    "The Theory stat baseline does not match its prepared config.",
                )
            normalized_mains.append({"slot": slot, "key": expected_key, "value": value})
        wearer["current_artifacts"] = []
        wearer["theory_baseline"] = {"main_stats": normalized_mains}
        output.append(wearer)
    sorted_output = sorted(output, key=lambda row: row["wearer_key"])
    if len({row["wearer_key"] for row in sorted_output}) != 4:
        raise GcsimOptimizerGoError(
            "theory_team_requires_four_characters",
            "Theory requires four distinct GCSIM character keys.",
        )
    return sorted_output


def _request_artifacts(
    database: Any,
    reference_actor: str,
    snapshot: Any,
    *,
    reference_wearer: GcsimOptimizerWearerIdentity | None = None,
) -> list[dict[str, Any]]:
    reference = reference_wearer
    if reference is None:
        reference = next(
            row.wearer
            for row in snapshot.wearers
            if row.wearer.gcsim_character_key == reference_actor
        )
    artifacts: list[dict[str, Any]] = []
    for artifact in database.artifacts:
        if not artifact.default_eligible:
            continue
        materialized = materialize_gcsim_optimizer_artifact_stat_vector(
            artifact, wearer=reference
        )
        if not materialized.ready or materialized.stat_vector is None:
            raise GcsimOptimizerGoError(
                "artifact_materialization_failed",
                f"Artifact {artifact.artifact_id} cannot be materialized.",
            )
        main = [row for row in materialized.stat_vector.contributions if row.source_kind == "main"]
        substats = [
            row for row in materialized.stat_vector.contributions if row.source_kind == "substat"
        ]
        if len(main) != 1:
            raise GcsimOptimizerGoError(
                "artifact_main_stat_invalid", f"Artifact {artifact.artifact_id} has invalid main stat."
            )
        artifacts.append(
            {
                "artifact_id": artifact.artifact_id,
                "slot": artifact.position_key,
                # Unregistered sets still provide ordinary off-piece stats.
                # Keep their concrete identity; only the verified set catalog
                # can nominate an active 4p/2+2 package in the Go search.
                "set_uid": (artifact.gcsim_set_key or artifact.set_uid).casefold(),
                "rarity": artifact.rarity,
                "level": artifact.level,
                "main_stat": {
                    "key": _go_stat_key(main[0].gcsim_key),
                    "value": main[0].normalized_value,
                },
                "substats": sorted(
                    (
                        {
                            "key": _go_stat_key(row.gcsim_key),
                            "value": row.normalized_value,
                        }
                        for row in substats
                    ),
                    key=lambda row: row["key"],
                ),
            }
        )
    return artifacts


def _source_text(text: str) -> dict[str, str]:
    return {"text": text, "sha256": text_sha256(text)}


def _go_stat_key(value: str) -> str:
    try:
        return _STAT_KEY[value]
    except KeyError as exc:
        raise GcsimOptimizerGoError(
            "artifact_stat_unsupported", f"Unsupported artifact stat {value!r}."
        ) from exc


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)
