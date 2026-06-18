from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QWidget

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
        super().__init__(parent, db_path=db_path)
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
        self._pvp_weapon_assets = [dict(asset) for asset in weapon_assets]

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
                dict(asset)
                for asset in assets
                if _asset_weapon_keys(asset) & self._allowed_weapon_keys
            ],
            load_ms,
            source,
        )


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
    ready: bool = False
    last_error: str = ""

    def __post_init__(self) -> None:
        self.controller = AppShellController.empty(equipment_db_path=self.provider.db_path)
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
        self.sync_source_workspace(reload_grids=True)

    @property
    def db_path(self) -> Path:
        return Path(self.provider.db_path)

    def add_or_replace_character(self, asset: dict[str, Any]) -> bool:
        character_id = _asset_character_id(asset)
        if character_id not in set(self.picked_character_ids):
            return False
        changed = self.controller.add_or_replace_character(dict(asset))
        if changed:
            self.ready = False
            self.last_error = ""
            self.sync_source_workspace()
        return changed

    def toggle_slot_selection(self, team_index: int, slot_index: int) -> None:
        self.controller.toggle_slot_selection(int(team_index), int(slot_index))
        self.sync_source_workspace()

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
        self.sync_source_workspace()
        return True

    def sync_source_workspace(self, *, reload_grids: bool = False) -> None:
        self.source_workspace.set_character_selection_markers(
            self.controller.roster_selection_markers()
        )
        self.source_workspace.set_auto_weapon_type_filter(
            self.controller.selected_character_weapon_filter_key()
        )
        if reload_grids:
            self.source_workspace.refresh_asset_cache()
            self.source_workspace.update_grids()
        else:
            self.source_workspace.reload_characters()

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
        weapon.get("type"),
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
    return _weapon_stack_key_from_mapping(weapon)


def _weapon_stack_key_from_mapping(weapon: Mapping[str, Any]) -> str:
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


__all__ = [
    "PVP_BUILD_TEAM_COUNT",
    "PVP_BUILD_TEAM_SIZE",
    "PvpBuildFlowContext",
    "PvpScopedCharacterWeaponWorkspace",
    "PvpSeatBuildContext",
]
