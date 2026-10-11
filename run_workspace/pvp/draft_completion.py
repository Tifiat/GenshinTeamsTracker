"""Bounded, pure completion oracle for the executable local draft reducer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .schedule import (
    ACTION_BAN_CHARACTER,
    ACTION_IMMUNE_BAN_CHARACTER,
    ACTION_IMMUNE_CHARACTER,
    ACTION_IMMUNE_PICK_CHARACTER,
    ACTION_MIRROR_CHARACTER,
    ACTION_PICK_CHARACTER,
    ACTION_PREBAN_CHARACTER,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
)
from .session import DraftAction, DraftActionRejected, DraftSessionState, apply_draft_action


_BANS = frozenset((ACTION_BAN_CHARACTER, ACTION_PREBAN_CHARACTER))
_PREPARATION = frozenset((ACTION_PREBAN_CHARACTER, ACTION_IMMUNE_BAN_CHARACTER,
                          ACTION_IMMUNE_PICK_CHARACTER))
_PICKS = frozenset((ACTION_PICK_CHARACTER, ACTION_IMMUNE_CHARACTER))


@dataclass(frozen=True, slots=True)
class DraftCompletionReport:
    status: Literal["complete", "impossible", "unknown"]
    witness: tuple[DraftAction, ...] = ()


def draft_completion(
    state: DraftSessionState,
    *,
    require_ban_targets: bool = True,
    max_states: int = 2000,
) -> DraftCompletionReport:
    """Find a legal remaining action log or prove none exists for supported flows.

    Preparation is explored by reducer-equivalent target classes. After fixed
    preparation, a matching assigns all future ban/pick slots to character
    resources; a replayed witness is required before reporting completion.
    """
    if type(max_states) is not int or max_states < 1 or type(require_ban_targets) is not bool:
        raise ValueError("Invalid draft completion bound or ban policy.")
    remaining = _remaining(state)
    if any(kind == ACTION_MIRROR_CHARACTER for _, kind in remaining):
        return DraftCompletionReport("unknown")
    explored = 0

    def solve(current: DraftSessionState) -> DraftCompletionReport:
        nonlocal explored
        if explored >= max_states:
            return DraftCompletionReport("unknown")
        explored += 1
        slots = _remaining(current)
        if not slots:
            return DraftCompletionReport("complete" if current.is_complete else "unknown")
        kind = slots[0][1]
        if kind in _PREPARATION:
            candidates = _representative_targets(current, kind)
            if kind == ACTION_PREBAN_CHARACTER and not require_ban_targets:
                candidates = (None,)
            unknown = False
            for target in candidates:
                action = DraftAction(current.current_seat or "", kind,
                                     target or "", skip=target is None)
                try:
                    next_state = apply_draft_action(current, action)
                except DraftActionRejected:
                    continue
                result = solve(next_state)
                if result.status == "complete":
                    return DraftCompletionReport("complete", (action,) + result.witness)
                if result.status == "unknown":
                    unknown = True
            return DraftCompletionReport("unknown" if unknown else "impossible")
        if any(next_kind in _PREPARATION for _, next_kind in slots):
            return DraftCompletionReport("unknown")
        return _match_remaining(current, slots, require_ban_targets=require_ban_targets)

    return solve(state)


def _remaining(state: DraftSessionState) -> tuple[tuple[str, str], ...]:
    return tuple(
        (step.seat, item.action_type)
        for step_index, step in enumerate(state.schedule.steps)
        if step_index >= state.step_index
        for action_index, item in enumerate(step.actions)
        if step_index != state.step_index or action_index >= state.action_index
    )


def _representative_targets(state: DraftSessionState, kind: str) -> tuple[str, ...]:
    deck_1 = state.player_1_deck.character_ids
    deck_2 = state.player_2_deck.character_ids
    ids = deck_1 | deck_2
    picked_1 = set(state.player_1_picked_character_ids)
    picked_2 = set(state.player_2_picked_character_ids)
    banned = set(state.banned_character_ids)
    immune_ban = set(state.immune_ban_character_ids)
    protected = set(state.immune_pick_character_ids)
    eligible = set(state.immune_eligible_character_ids)
    absolute = set(state.absolute_immune_character_ids)
    if kind in (ACTION_IMMUNE_BAN_CHARACTER, ACTION_IMMUNE_PICK_CHARACTER):
        ids &= eligible
    elif kind == ACTION_PREBAN_CHARACTER and state.is_abyss_match:
        ids &= deck_2 if state.current_seat == SEAT_PLAYER_1 else deck_1
    mirror_used = {item.character_id for item in state.accepted_actions
                   if item.action_type == ACTION_MIRROR_CHARACTER}
    representatives: dict[tuple[bool, ...], str] = {}
    for character_id in sorted(ids):
        key = (
            character_id in deck_1,
            character_id in deck_2,
            character_id in eligible,
            character_id in absolute,
            character_id in banned,
            character_id in immune_ban,
            character_id in protected,
            character_id in picked_1,
            character_id in picked_2,
            character_id in mirror_used,
        )
        representatives.setdefault(key, character_id)
    return tuple(representatives.values())


def _match_remaining(
    state: DraftSessionState,
    slots: tuple[tuple[str, str], ...],
    *,
    require_ban_targets: bool,
) -> DraftCompletionReport:
    if any(kind not in _BANS | _PICKS for _, kind in slots):
        return DraftCompletionReport("unknown")
    if not require_ban_targets:
        mandatory = tuple((index, seat, kind) for index, (seat, kind) in enumerate(slots)
                          if kind not in _BANS)
    else:
        mandatory = tuple((index, seat, kind) for index, (seat, kind) in enumerate(slots))
    deck_1 = state.player_1_deck.character_ids
    deck_2 = state.player_2_deck.character_ids
    banned = set(state.banned_character_ids)
    picked_1 = set(state.player_1_picked_character_ids)
    picked_2 = set(state.player_2_picked_character_ids)
    absolute = set(state.absolute_immune_character_ids)
    protected = set(state.immune_pick_character_ids)
    mirror_used = {item.character_id for item in state.accepted_actions
                   if item.action_type == ACTION_MIRROR_CHARACTER}
    resources: list[tuple[str, str | None]] = []
    for character_id in sorted(deck_1 | deck_2):
        if character_id in banned:
            continue
        if character_id in absolute or character_id in protected:
            for seat, picked in ((SEAT_PLAYER_1, picked_1), (SEAT_PLAYER_2, picked_2)):
                if character_id not in picked:
                    resources.append((character_id, seat))
        elif (character_id not in picked_1 and character_id not in picked_2
              and character_id not in mirror_used):
            resources.append((character_id, None))
    neighbors: list[list[int]] = []
    for _, seat, kind in mandatory:
        own = deck_1 if seat == SEAT_PLAYER_1 else deck_2
        opponent = deck_2 if seat == SEAT_PLAYER_1 else deck_1
        allowed: list[int] = []
        for resource_index, (character_id, copy_seat) in enumerate(resources):
            if kind in _BANS:
                if (copy_seat is None and character_id in
                    (opponent if state.is_abyss_match else deck_1 | deck_2)):
                    allowed.append(resource_index)
            elif character_id in own and copy_seat in (None, seat):
                if character_id not in protected or kind == ACTION_IMMUNE_CHARACTER:
                    allowed.append(resource_index)
        if not allowed:
            return DraftCompletionReport("impossible")
        neighbors.append(allowed)
    owner: dict[int, int] = {}

    def augment(slot_index: int, visited: set[int]) -> bool:
        for resource_index in neighbors[slot_index]:
            if resource_index in visited:
                continue
            visited.add(resource_index)
            prior = owner.get(resource_index)
            if prior is None or augment(prior, visited):
                owner[resource_index] = slot_index
                return True
        return False

    for slot_index in range(len(mandatory)):
        if not augment(slot_index, set()):
            return DraftCompletionReport("impossible")
    assigned = {mandatory[slot_index][0]: resources[resource_index][0]
                for resource_index, slot_index in owner.items()}
    witness = tuple(
        DraftAction(seat, kind, assigned.get(index, ""),
                    skip=kind in _BANS and index not in assigned)
        for index, (seat, kind) in enumerate(slots)
    )
    current = state
    try:
        for action in witness:
            current = apply_draft_action(current, action)
    except DraftActionRejected:
        return DraftCompletionReport("unknown")
    if not current.is_complete:
        return DraftCompletionReport("unknown")
    return DraftCompletionReport("complete", witness)
