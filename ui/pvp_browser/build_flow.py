from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from hoyolab_export.account_equipment import EquipmentChangeResult, EquipmentError
from hoyolab_export.artifact_db import ARTIFACT_DB_PATH
from run_workspace.pvp.deck_preset import DEFAULT_PVP_DECK_PRESET_DIR
from run_workspace.pvp.profile_package import (
    LocalPvpProfileProvider,
    PvpProfileProvider,
)
from run_workspace.pvp.session import (
    CharacterWeaponAssignment,
    PlayerTeamAssignment,
    PlayerWeaponAssignment,
    TeamAssignment,
    validate_team_assignment,
    validate_weapon_assignment,
)
from run_workspace.pvp.weapon_identity import (
    WeaponObservedStackRef,
    weapon_observed_stack_key,
    weapon_observed_stack_ref_from_asset,
)
from run_workspace.right_panel_prototype_view_model import MODE_ABYSS
from run_workspace.team_builder import TeamBuilderSlotState
from ui.app_shell import AppShellController, CharacterWeaponWorkspace


PVP_BUILD_TEAM_COUNT = 2
PVP_BUILD_TEAM_SIZE = 4
_WEAPON_TYPE_BY_ID = {
    1: "SWORD",
    10: "CATALYST",
    11: "CLAYMORE",
    12: "BOW",
    13: "POLEARM",
}
_WEAPON_TYPE_ALIASES = {
    "sword": "SWORD",
    "one_handed_sword": "SWORD",
    "одноручный_меч": "SWORD",
    "одноручное": "SWORD",
    "одноручное_оружие": "SWORD",
    "claymore": "CLAYMORE",
    "двуручный_меч": "CLAYMORE",
    "двуручное": "CLAYMORE",
    "двуручное_оружие": "CLAYMORE",
    "bow": "BOW",
    "лук": "BOW",
    "стрелковое": "BOW",
    "стрелковое_оружие": "BOW",
    "catalyst": "CATALYST",
    "катализатор": "CATALYST",
    "polearm": "POLEARM",
    "древковое": "POLEARM",
    "древковое_оружие": "POLEARM",
    "копье": "POLEARM",
    "копьё": "POLEARM",
}


class PvpScopedCharacterWeaponWorkspace(CharacterWeaponWorkspace):
    """Existing AppShell character/weapon source, narrowed to one PvP seat."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        seat: str,
        db_path: str | Path = ARTIFACT_DB_PATH,
        allowed_character_ids: Iterable[str] = (),
        allowed_weapon_keys: Iterable[str] = (),
        character_assets: Iterable[dict[str, Any]] = (),
        weapon_assets: Iterable[dict[str, Any]] = (),
    ) -> None:
        super().__init__(parent, db_path=db_path, show_section_titles=False)
        self.seat = str(seat)
        self.setObjectName("PvpScopedCharacterWeaponWorkspace")
        self.setProperty("pvpScopedSourceWorkspace", True)
        self.setProperty("seat", self.seat)
        self._allowed_character_ids = {
            _text(character_id)
            for character_id in allowed_character_ids
            if _text(character_id)
        }
        self._allowed_weapon_keys = {
            _text(key)
            for key in allowed_weapon_keys
            if _text(key)
        }
        self._pvp_character_assets = [dict(asset) for asset in character_assets]
        self._pvp_weapon_assets = [
            _strip_asset_owner_badges(asset)
            for asset in weapon_assets
        ]

    def _character_asset_items(self) -> tuple[list[dict], float, str]:
        if self._pvp_character_assets:
            return (
                [
                    dict(asset)
                    for asset in self._pvp_character_assets
                    if _asset_character_id(asset) in self._allowed_character_ids
                ],
                0.0,
                "pvp_scoped_assets",
            )
        assets, load_ms, source = super()._character_asset_items()
        return (
            [
                dict(asset)
                for asset in assets
                if _asset_character_id(asset) in self._allowed_character_ids
            ],
            load_ms,
            source,
        )

    def _weapon_asset_items(self) -> tuple[list[dict], float, str]:
        if self._pvp_weapon_assets:
            return (
                [
                    dict(asset)
                    for asset in self._pvp_weapon_assets
                    if _asset_weapon_keys(asset) & self._allowed_weapon_keys
                ],
                0.0,
                "pvp_scoped_assets",
            )
        assets, load_ms, source = super()._weapon_asset_items()
        return (
            [
                _strip_asset_owner_badges(asset)
                for asset in assets
                if _asset_weapon_keys(asset) & self._allowed_weapon_keys
            ],
            load_ms,
            source,
        )

    def set_pvp_weapon_assets(
        self,
        assets: Iterable[dict[str, Any]],
        *,
        reload_grid: bool = True,
    ) -> None:
        self._pvp_weapon_assets = [dict(asset) for asset in assets]
        self.refresh_weapon_asset_cache()
        if reload_grid:
            self.reload_weapons()

    def update_grids(self) -> None:
        self._initial_grid_built = True
        super().update_grids()


@dataclass(slots=True)
class PvpRuntimeEquipmentState:
    """Per-seat temporary PvP equipment state over provider source data."""

    seat: str
    allowed_character_ids: set[str]
    allowed_weapon_keys: set[str]
    weapon_assets_by_key: dict[str, dict[str, Any]]
    known_count_by_key: dict[str, int]
    weapons_by_character: dict[str, dict[str, Any]] = field(default_factory=dict)
    characters_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_assets(
        cls,
        *,
        seat: str,
        allowed_character_ids: Iterable[str],
        allowed_weapon_keys: Iterable[str],
        weapon_assets: Iterable[dict[str, Any]],
    ) -> "PvpRuntimeEquipmentState":
        allowed = {_text(key) for key in allowed_weapon_keys if _text(key)}
        assets_by_key: dict[str, dict[str, Any]] = {}
        counts_by_key: dict[str, int] = {}
        for asset in weapon_assets:
            weapon = _asset_metadata_mapping(asset, "weapon")
            keys = _asset_weapon_keys(asset) & allowed
            if not keys:
                continue
            clean_asset = _strip_asset_owner_badges(asset)
            known_count = max(
                1,
                _optional_int(
                    _mapping(clean_asset.get("metadata")).get("known_count")
                    or weapon.get("known_count")
                )
                or 1,
            )
            for key in keys:
                assets_by_key[key] = clean_asset
                counts_by_key[key] = known_count
        return cls(
            seat=_text(seat),
            allowed_character_ids={
                _text(character_id)
                for character_id in allowed_character_ids
                if _text(character_id)
            },
            allowed_weapon_keys=allowed,
            weapon_assets_by_key=assets_by_key,
            known_count_by_key=counts_by_key,
        )

    def assign_weapon_to_character(
        self,
        character_id: str,
        character: Mapping[str, Any],
        weapon: Mapping[str, Any],
    ) -> tuple[EquipmentChangeResult, dict[str, Any] | None]:
        character_id = _text(character_id)
        if character_id not in self.allowed_character_ids:
            raise EquipmentError(f"PvP character is not in this seat pool: {character_id!r}")
        weapon_key = _matching_allowed_weapon_key(weapon, self.allowed_weapon_keys)
        if weapon_key not in self.allowed_weapon_keys:
            raise EquipmentError(f"PvP weapon is not in this seat pool: {weapon_key!r}")
        self.characters_by_id[character_id] = dict(character)
        current = self.weapons_by_character.get(character_id)
        current_key = _weapon_stack_key_from_mapping(current or {})
        if current_key == weapon_key:
            self.weapons_by_character.pop(character_id, None)
            return (
                EquipmentChangeResult(
                    operation="unequip_weapon",
                    changed=True,
                    message="pvp_scoped",
                    affected_character_ids=(int(character_id),),
                    affected_weapon_fingerprints=(weapon_key,),
                ),
                None,
            )

        known_count = max(1, self.known_count_by_key.get(weapon_key, 1))
        owners = [
            owner_id
            for owner_id, equipped in self.weapons_by_character.items()
            if _weapon_stack_key_from_mapping(equipped) == weapon_key
            and owner_id != character_id
        ]
        affected_character_ids = {character_id}
        if len(owners) >= known_count:
            if len(owners) != 1:
                raise EquipmentError(f"No available PvP copy for weapon stack {weapon_key!r}")
            previous_owner = owners[0]
            self.weapons_by_character.pop(previous_owner, None)
            affected_character_ids.add(previous_owner)

        self.weapons_by_character[character_id] = _pvp_weapon_ref(weapon, weapon_key)
        return (
            EquipmentChangeResult(
                operation="equip_weapon",
                changed=True,
                message="pvp_scoped",
                affected_character_ids=tuple(
                    int(value)
                    for value in sorted(affected_character_ids)
                    if value.isdigit()
                ),
                affected_weapon_fingerprints=(weapon_key,),
            ),
            dict(self.weapons_by_character[character_id]),
        )

    def weapon_for_character(
        self,
        character_id: str,
        _character: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        weapon = self.weapons_by_character.get(_text(character_id))
        return dict(weapon) if weapon else None

    def artifact_ids_for_character(self, _character_id: str) -> dict[str, int]:
        return {}

    def weapon_assets_with_owner_badges(
        self,
        assets: Iterable[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            self._weapon_asset_with_owner_badges(_strip_asset_owner_badges(asset))
            for asset in assets
        ]

    def _weapon_asset_with_owner_badges(self, asset: dict[str, Any]) -> dict[str, Any]:
        keys = _asset_weapon_keys(asset)
        owners = [
            character_id
            for character_id, weapon in self.weapons_by_character.items()
            if _weapon_stack_key_from_mapping(weapon) in keys
        ]
        if not owners:
            return asset
        metadata = dict(_mapping(asset.get("metadata")))
        metadata["owner_badges"] = [
            badge
            for character_id in owners
            for badge in [self._owner_badge(character_id)]
            if badge
        ]
        metadata["extra_owner_count"] = max(0, len(metadata["owner_badges"]) - 1)
        asset["metadata"] = metadata
        return asset

    def _owner_badge(self, character_id: str) -> dict[str, Any]:
        character = self.characters_by_id.get(_text(character_id), {})
        side_icon_path = _text(
            character.get("side_icon_path")
            or character.get("local_side_icon_path")
            or character.get("portrait_path")
            or character.get("local_portrait_path")
        )
        return {
            "character_id": _text(character_id),
            "name": _text(character.get("name")) or _text(character_id),
            "side_icon_path": side_icon_path,
        }


@dataclass(slots=True, weakref_slot=True)
class PvpSeatBuildContext:
    seat: str
    provider: PvpProfileProvider
    picked_character_ids: tuple[str, ...]
    allowed_weapon_keys: tuple[str, ...]
    character_assets: tuple[dict[str, Any], ...] = ()
    weapon_assets: tuple[dict[str, Any], ...] = ()
    parent: QWidget | None = None
    controller: AppShellController = field(init=False)
    source_workspace: PvpScopedCharacterWeaponWorkspace = field(init=False)
    equipment_state: PvpRuntimeEquipmentState = field(init=False)
    _weapon_filter_timer: QTimer = field(init=False, repr=False)
    ready: bool = False
    last_error: str = ""

    def __post_init__(self) -> None:
        self.equipment_state = PvpRuntimeEquipmentState.from_assets(
            seat=self.seat,
            allowed_character_ids=self.picked_character_ids,
            allowed_weapon_keys=self.allowed_weapon_keys,
            weapon_assets=self.weapon_assets,
        )
        self.controller = AppShellController.empty(
            equipment_db_path=self.provider.db_path,
            equipment_state=self.equipment_state,
        )
        self.controller.set_mode(MODE_ABYSS)
        self.source_workspace = PvpScopedCharacterWeaponWorkspace(
            self.parent,
            seat=self.seat,
            db_path=self.provider.db_path,
            allowed_character_ids=self.picked_character_ids,
            allowed_weapon_keys=self.allowed_weapon_keys,
            character_assets=self.character_assets,
            weapon_assets=self.weapon_assets,
        )
        self.source_workspace.character_clicked.connect(self.add_or_replace_character)
        self.source_workspace.weapon_clicked.connect(self.assign_weapon_to_selected_slot)
        self._weapon_filter_timer = QTimer(self.source_workspace)
        self._weapon_filter_timer.setSingleShot(True)
        self._weapon_filter_timer.timeout.connect(self._apply_deferred_weapon_filter)
        self.sync_source_workspace(reload_grids=True)

    @property
    def db_path(self) -> Path:
        return Path(self.provider.db_path)

    def add_or_replace_character(self, asset: dict[str, Any]) -> bool:
        character_id = _asset_character_id(asset)
        if character_id not in set(self.picked_character_ids):
            return False
        before_markers = self.controller.roster_selection_markers()
        result = self.controller.add_or_replace_character_fast(dict(asset))
        if result.changed:
            self.ready = False
            self.last_error = ""
            if result.added:
                self.controller.hydrate_persistent_equipment_for_slot(
                    result.team_index,
                    result.slot_index,
                    result.character_id,
                )
            self.sync_source_workspace(
                affected_character_ids=_changed_marker_ids(
                    before_markers,
                    self.controller.roster_selection_markers(),
                ),
                sync_weapon_filter=False,
            )
            self.schedule_weapon_filter_sync()
        return result.changed

    def swap_slots(
        self,
        source_team_index: int,
        source_slot_index: int,
        target_team_index: int,
        target_slot_index: int,
    ) -> bool:
        before_markers = self.controller.roster_selection_markers()
        changed = self.controller.swap_slots(
            source_team_index,
            source_slot_index,
            target_team_index,
            target_slot_index,
        )
        if changed:
            self.ready = False
            self.last_error = ""
            self.sync_source_workspace(
                affected_character_ids=_changed_marker_ids(
                    before_markers,
                    self.controller.roster_selection_markers(),
                ),
                sync_weapon_filter=False,
            )
            self.schedule_weapon_filter_sync()
        return changed

    def toggle_slot_selection(self, team_index: int, slot_index: int) -> None:
        self.controller.toggle_slot_selection(int(team_index), int(slot_index))
        self.sync_source_workspace(sync_weapon_filter=False)
        self.schedule_weapon_filter_sync()

    def assign_weapon_to_selected_slot(self, asset: dict[str, Any]) -> bool:
        if not (_asset_weapon_keys(asset) & set(self.allowed_weapon_keys)):
            return False
        changed = self.controller.assign_weapon_to_selected_slot(dict(asset))
        if not changed:
            self.last_error = self.controller.last_equipment_error
            self.sync_source_workspace()
            return False
        self.ready = False
        self.last_error = ""
        self.sync_source_workspace(refresh_weapons=True)
        return True

    def sync_source_workspace(
        self,
        *,
        reload_grids: bool = False,
        refresh_weapons: bool = False,
        affected_character_ids: set[str] | None = None,
        sync_weapon_filter: bool = True,
    ) -> None:
        self.source_workspace.set_pvp_weapon_assets(
            self.equipment_state.weapon_assets_with_owner_badges(self.weapon_assets),
            reload_grid=False,
        )
        self.source_workspace.set_character_selection_markers(
            self.controller.roster_selection_markers(),
            affected_character_ids=affected_character_ids,
        )
        if sync_weapon_filter:
            self.source_workspace.set_auto_weapon_type_filter(
                self.controller.selected_character_weapon_filter_key()
            )
        if reload_grids:
            self.source_workspace.refresh_asset_cache()
            self.source_workspace.update_grids()
        elif refresh_weapons:
            self.source_workspace.reload_weapons()
        else:
            self.source_workspace.weapon_area.viewport().update()

    def schedule_weapon_filter_sync(self, delay_ms: int = 80) -> None:
        self._weapon_filter_timer.start(max(0, int(delay_ms)))

    def _apply_deferred_weapon_filter(self) -> None:
        self.source_workspace.set_auto_weapon_type_filter(
            self.controller.selected_character_weapon_filter_key()
        )

    def right_panel_model(self):
        return self.controller.right_panel_model(load_abyss_source_data=False)

    def team_assignment(self) -> PlayerTeamAssignment:
        teams: list[TeamAssignment] = []
        for team_index in range(PVP_BUILD_TEAM_COUNT):
            try:
                team = self.controller.state.team(team_index)
            except IndexError:
                teams.append(TeamAssignment(team_index=team_index, character_ids=()))
                continue
            teams.append(
                TeamAssignment(
                    team_index=team_index,
                    character_ids=tuple(
                        character_id
                        for character_id in (
                            _slot_character_id(slot)
                            for slot in team.slots[:PVP_BUILD_TEAM_SIZE]
                        )
                        if character_id
                    ),
                )
            )
        return PlayerTeamAssignment(seat=self.seat, teams=tuple(teams))

    def weapon_assignment(self) -> PlayerWeaponAssignment:
        assignments: list[CharacterWeaponAssignment] = []
        for team_index in range(PVP_BUILD_TEAM_COUNT):
            try:
                team = self.controller.state.team(team_index)
            except IndexError:
                continue
            for slot in team.slots[:PVP_BUILD_TEAM_SIZE]:
                character_id = _slot_character_id(slot)
                stack_key = _slot_weapon_stack_key(slot)
                if character_id and stack_key:
                    assignments.append(
                        CharacterWeaponAssignment(
                            character_id=character_id,
                            weapon_stack_key=stack_key,
                        )
                    )
        return PlayerWeaponAssignment(
            seat=self.seat,
            assignments=tuple(sorted(assignments, key=lambda item: item.character_id)),
        )

    def filled_character_count(self) -> int:
        return sum(
            1
            for team in self.controller.state.teams[:PVP_BUILD_TEAM_COUNT]
            for slot in team.slots[:PVP_BUILD_TEAM_SIZE]
            if _slot_character_id(slot)
        )

    def filled_weapon_count(self) -> int:
        return sum(
            1
            for team in self.controller.state.teams[:PVP_BUILD_TEAM_COUNT]
            for slot in team.slots[:PVP_BUILD_TEAM_SIZE]
            if _slot_character_id(slot) and _slot_weapon_stack_key(slot)
        )

    def ready_candidate(self) -> bool:
        return (
            self.filled_character_count() == PVP_BUILD_TEAM_COUNT * PVP_BUILD_TEAM_SIZE
            and self.filled_weapon_count() == PVP_BUILD_TEAM_COUNT * PVP_BUILD_TEAM_SIZE
        )


@dataclass(slots=True)
class PvpBuildFlowContext:
    seats: dict[str, PvpSeatBuildContext]
    active_seat: str = "player_1"
    collapsed_seats: set[str] = field(default_factory=lambda: {"player_2"})

    @classmethod
    def from_draft_session(
        cls,
        session: Any,
        *,
        db_path: str | Path = ARTIFACT_DB_PATH,
        deck_dir: str | Path | None = None,
        character_assets: Iterable[dict[str, Any]] = (),
        weapon_assets: Iterable[dict[str, Any]] = (),
        providers_by_seat: Mapping[str, PvpProfileProvider] | None = None,
        character_assets_by_seat: Mapping[
            str, Iterable[dict[str, Any]]
        ] | None = None,
        weapon_assets_by_seat: Mapping[
            str, Iterable[dict[str, Any]]
        ] | None = None,
        parent: QWidget | None = None,
    ) -> "PvpBuildFlowContext":
        board = session.board_dict()
        character_assets_tuple = tuple(dict(asset) for asset in character_assets)
        weapon_assets_tuple = tuple(dict(asset) for asset in weapon_assets)
        providers_by_seat = dict(providers_by_seat or {})
        character_assets_by_seat = dict(character_assets_by_seat or {})
        weapon_assets_by_seat = dict(weapon_assets_by_seat or {})
        seats: dict[str, PvpSeatBuildContext] = {}
        for seat in ("player_1", "player_2"):
            provider = providers_by_seat.get(seat) or LocalPvpProfileProvider(
                source_db_path=db_path,
                deck_dir=deck_dir or DEFAULT_PVP_DECK_PRESET_DIR,
            )
            deck = session.controller.session_state.deck_for(seat)
            picked = _picked_character_ids(board, seat)
            allowed_weapon_keys = tuple(
                dict.fromkeys(
                    key
                    for stack in deck.weapons
                    for key in _draft_weapon_stack_keys(stack)
                    if key
                )
            )
            seats[seat] = PvpSeatBuildContext(
                seat=seat,
                provider=provider,
                picked_character_ids=picked,
                allowed_weapon_keys=allowed_weapon_keys,
                character_assets=tuple(
                    dict(asset)
                    for asset in character_assets_by_seat.get(
                        seat,
                        character_assets_tuple,
                    )
                ),
                weapon_assets=tuple(
                    dict(asset)
                    for asset in weapon_assets_by_seat.get(
                        seat,
                        weapon_assets_tuple,
                    )
                ),
                parent=parent,
            )
        return cls(seats=seats)

    def seat(self, seat: str) -> PvpSeatBuildContext | None:
        return self.seats.get(str(seat))

    def set_active_seat(self, seat: str) -> None:
        if seat in self.seats:
            self.active_seat = seat

    def toggle_collapsed(self, seat: str) -> None:
        if seat not in self.seats:
            return
        if seat in self.collapsed_seats:
            self.collapsed_seats.remove(seat)
        else:
            self.collapsed_seats.add(seat)

    def ready_candidate(self, seat: str) -> bool:
        context = self.seat(seat)
        return bool(context and context.ready_candidate())

    def commit_ready(self, seat: str, draft_controller: Any) -> bool:
        context = self.seat(seat)
        if context is None:
            return False
        team_assignment = context.team_assignment()
        team_report = validate_team_assignment(
            draft_controller.session_state,
            team_assignment,
        )
        if not team_report.ready:
            context.last_error = ",".join(team_report.issue_codes())
            context.ready = False
            return False
        weapon_assignment = context.weapon_assignment()
        weapon_report = validate_weapon_assignment(
            draft_controller.session_state,
            team_assignment,
            weapon_assignment,
        )
        if not weapon_report.ready:
            context.last_error = ",".join(weapon_report.issue_codes())
            context.ready = False
            return False
        draft_controller.set_team_assignment(team_assignment)
        draft_controller.set_weapon_assignment(weapon_assignment)
        context.ready = True
        context.last_error = ""
        return True

    def both_ready(self) -> bool:
        return bool(self.seats) and all(context.ready for context in self.seats.values())

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "active_seat": self.active_seat,
            "collapsed_seats": sorted(self.collapsed_seats),
            "seats": {
                seat: {
                    "ready": context.ready,
                    "ready_candidate": context.ready_candidate(),
                    "characters": context.filled_character_count(),
                    "weapons": context.filled_weapon_count(),
                    "last_error": context.last_error,
                }
                for seat, context in self.seats.items()
            },
        }


def _picked_character_ids(board: Mapping[str, Any], seat: str) -> tuple[str, ...]:
    unified_pool = _mapping(board.get("unified_pool"))
    result_zones = _mapping(unified_pool.get("result_zones"))
    picked = _mapping(result_zones.get(seat)).get("picked")
    if not isinstance(picked, list):
        return ()
    return tuple(_text(character_id) for character_id in picked if _text(character_id))


def _draft_weapon_stack_keys(stack: Any) -> tuple[str, ...]:
    keys = [
        _text(getattr(stack, "stack_key", "")),
        weapon_observed_stack_key(
            weapon_id=getattr(stack, "weapon_id", ""),
            weapon_type=getattr(stack, "weapon_type", ""),
            rarity=getattr(stack, "rarity", None),
            level=getattr(stack, "level", None),
            refinement=getattr(stack, "refinement", None),
        ),
    ]
    return tuple(dict.fromkeys(key for key in keys if key))


def _asset_character_id(asset: Mapping[str, Any]) -> str:
    return _text(_asset_metadata_mapping(asset, "character").get("id"))


def _asset_weapon_keys(asset: Mapping[str, Any]) -> set[str]:
    ref = weapon_observed_stack_ref_from_asset(asset)
    if ref is None:
        return set()
    keys = {_text(ref.key)}
    metadata = _mapping(asset.get("metadata"))
    weapon = _mapping(metadata.get("weapon"))
    for weapon_type in (
        ref.weapon_type,
        weapon.get("weapon_type_name"),
        weapon.get("type_name"),
        weapon.get("weapon_type"),
        weapon.get("type"),
        *_canonical_weapon_type_candidates(weapon),
    ):
        key = weapon_observed_stack_key(
            weapon_id=ref.weapon_id,
            weapon_type=weapon_type,
            rarity=ref.rarity,
            level=ref.level,
            refinement=ref.refinement,
        )
        if key:
            keys.add(key)
    return {key for key in keys if key}


def _strip_asset_owner_badges(asset: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(asset)
    metadata = dict(_mapping(item.get("metadata")))
    metadata.pop("owner_badges", None)
    metadata.pop("extra_owner_count", None)
    item["metadata"] = metadata
    return item


def _pvp_weapon_ref(weapon: Mapping[str, Any], weapon_key: str) -> dict[str, Any]:
    result = dict(weapon)
    if weapon_key:
        result["pvp_weapon_stack_key"] = weapon_key
        result.setdefault("variant_key", weapon_key)
        result.setdefault("source_key", _text(weapon.get("source_key")) or weapon_key)
    return result


def _changed_marker_ids(before: Mapping[str, Any], after: Mapping[str, Any]) -> set[str]:
    return {
        character_id
        for character_id in set(before) | set(after)
        if before.get(character_id) != after.get(character_id)
    }


def _slot_character_id(slot: TeamBuilderSlotState) -> str:
    if slot.character is None:
        return ""
    return _text(slot.character.id)


def _slot_weapon_stack_key(slot: TeamBuilderSlotState) -> str:
    details = _mapping(slot.character_details_data)
    weapon = _mapping(details.get("account_weapon"))
    if not weapon and slot.weapon is not None:
        weapon = slot.weapon.to_dict()
    if not weapon:
        return ""
    pvp_key = _text(weapon.get("pvp_weapon_stack_key"))
    if pvp_key:
        return pvp_key
    return _weapon_stack_key_from_mapping(weapon)


def _weapon_stack_key_from_mapping(weapon: Mapping[str, Any]) -> str:
    pvp_key = _text(weapon.get("pvp_weapon_stack_key"))
    if pvp_key:
        return pvp_key
    key = weapon_observed_stack_key(
        weapon_id=weapon.get("weapon_id") or weapon.get("id"),
        weapon_type=(
            weapon.get("weapon_type_name")
            or weapon.get("type_name")
            or weapon.get("weapon_type")
            or weapon.get("type")
        ),
        rarity=weapon.get("rarity"),
        level=weapon.get("level"),
        refinement=weapon.get("refinement"),
    )
    if key:
        return key
    ref = WeaponObservedStackRef(
        weapon_fingerprint=_text(
            weapon.get("weapon_fingerprint")
            or weapon.get("source_key")
            or weapon.get("variant_key")
        ),
        weapon_id=_text(weapon.get("weapon_id") or weapon.get("id")),
        weapon_type=_text(
            weapon.get("weapon_type") or weapon.get("type_name") or weapon.get("type")
        ),
        rarity=_optional_int(weapon.get("rarity")),
        level=_optional_int(weapon.get("level")),
        refinement=_optional_int(weapon.get("refinement")),
    )
    return ref.key


def _matching_allowed_weapon_key(
    weapon: Mapping[str, Any],
    allowed_weapon_keys: Iterable[str],
) -> str:
    allowed = {_text(key) for key in allowed_weapon_keys if _text(key)}
    for key_name in (
        "pvp_weapon_stack_key",
        "variant_key",
        "source_key",
        "weapon_fingerprint",
    ):
        key = _text(weapon.get(key_name))
        if key in allowed:
            return key

    weapon_id = weapon.get("weapon_id") or weapon.get("id")
    for weapon_type in (
        weapon.get("weapon_type_name"),
        weapon.get("type_name"),
        weapon.get("weapon_type"),
        weapon.get("type"),
        *_canonical_weapon_type_candidates(weapon),
    ):
        key = weapon_observed_stack_key(
            weapon_id=weapon_id,
            weapon_type=weapon_type,
            rarity=weapon.get("rarity"),
            level=weapon.get("level"),
            refinement=weapon.get("refinement"),
        )
        if key in allowed:
            return key
    return _weapon_stack_key_from_mapping(weapon)


def _canonical_weapon_type_candidates(weapon: Mapping[str, Any]) -> tuple[str, ...]:
    candidates: list[str] = []
    for key in ("weapon_type", "type"):
        type_id = _optional_int(weapon.get(key))
        if type_id in _WEAPON_TYPE_BY_ID:
            candidates.append(_WEAPON_TYPE_BY_ID[type_id])
    for key in ("weapon_type_name", "type_name", "weapon_type", "type"):
        token = _normalized_token(weapon.get(key))
        if token in _WEAPON_TYPE_ALIASES:
            candidates.append(_WEAPON_TYPE_ALIASES[token])
    return tuple(dict.fromkeys(candidate for candidate in candidates if candidate))


def _asset_metadata_mapping(asset: Mapping[str, Any], key: str) -> dict[str, Any]:
    return _mapping(_mapping(asset.get("metadata")).get(key))


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_token(value: Any) -> str:
    return _text(value).casefold().replace("-", "_").replace(" ", "_")


__all__ = [
    "PVP_BUILD_TEAM_COUNT",
    "PVP_BUILD_TEAM_SIZE",
    "PvpBuildFlowContext",
    "PvpScopedCharacterWeaponWorkspace",
    "PvpSeatBuildContext",
]
