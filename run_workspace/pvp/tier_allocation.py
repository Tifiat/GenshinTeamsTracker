"""Bounded, exact allocation of physical Abyss tier support.

This module interprets only one level of ``requires`` and ``equals``. An
``equals`` group is a possible resource for one requirement slot; its members
cannot be spent again, including in a different equals group. Search results
are conclusive only after exhaustive search or a full-coverage witness.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import math
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class _Member:
    index: int
    character_id: str
    source_id: str
    cost: int | float
    tier: int
    specification: int | None
    bit: int


@dataclass(frozen=True)
class _Option:
    mask: int
    members: tuple[int, ...]
    equals_rule_index: int | None
    cost: int | float


class _Unknown(Exception):
    pass


def _integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def _number(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _criterion(value: Any) -> tuple[int, int | None]:
    if not isinstance(value, Mapping) or set(value) not in ({"tier"}, {"tier", "specification"}):
        raise _Unknown("unsupported criterion")
    tier = value["tier"]
    specification = value.get("specification")
    if not _integer(tier) or (specification is not None and not _integer(specification)):
        raise _Unknown("unsupported criterion")
    return tier, specification


def allocate_requirements(
    character_rows: Sequence[Mapping[str, Any]],
    preset_rules: Sequence[Mapping[str, Any]],
    *,
    equivalents_any_role: bool = True,
    max_states: int = 30_000,
    max_options: int = 30_000,
) -> dict[str, Any]:
    """Allocate all selected tier targets without reusing physical support.

    ``pass`` has a full witness; ``fail`` has an exhaustive proof that no full
    allocation exists. ``unknown`` includes malformed/unsupported inputs and
    search-budget exhaustion. In that case any reported assignment is only a
    feasible provisional witness. Objective: maximize complete target-rule
    instances, then slots filled on incomplete instances. Ties follow tier
    descending and stable character/source identity, independent of deck order.
    """
    empty = {"status": "unknown", "complete": False, "reason": "unsupported input",
             "rules": [], "equals": []}
    try:
        if (type(equivalents_any_role) is not bool or not _integer(max_states) or max_states == 0
                or not _integer(max_options) or max_options == 0
                or not isinstance(character_rows, (list, tuple))
                or not isinstance(preset_rules, (list, tuple))):
            raise _Unknown("unsupported input")
        members: list[_Member] = []
        seen_indexes: set[int] = set()
        seen_character_ids: set[str] = set()
        seen_source_ids: set[str] = set()
        for ordinal, row in enumerate(character_rows):
            if not isinstance(row, Mapping):
                raise _Unknown("unsupported character row")
            index, cid, sid = row.get("index"), row.get("character_id"), row.get("source_id")
            cost, tier, specification = row.get("cost"), row.get("tier"), row.get("specification")
            outside_tiers = tier is None and row.get("tier_status") == "outside"
            if (not _integer(index) or index in seen_indexes or not isinstance(cid, str) or not cid
                    or cid in seen_character_ids or not isinstance(sid, str) or not sid
                    or sid in seen_source_ids or not _number(cost)
                    or (not _integer(tier) and not outside_tiers)
                    or (specification is not None and not _integer(specification))):
                raise _Unknown("unknown character identity, cost, tier, or role")
            seen_indexes.add(index)
            seen_character_ids.add(cid)
            seen_source_ids.add(sid)
            # A priced character outside every declared band (e.g. cost 0 with
            # T0 starting at 1) is known not to match any tier requirement. It
            # stays in roster/budget checks, but is neither a target nor support.
            # Missing/ambiguous tier data must still stay unknown above.
            if outside_tiers:
                continue
            members.append(_Member(index, cid, sid, cost, tier, specification, 1 << ordinal))
        if len(character_rows) > 100:
            raise _Unknown("character limit exceeded")
        members.sort(key=lambda m: (m.character_id, m.source_id, m.index))
        # The bit is an identity, not a position in the sorted array.
        by_index = {m.index: m for m in members}
        requires: list[tuple[int, int, tuple[tuple[int, int | None], ...]]] = []
        equals: list[tuple[int, int, tuple[tuple[int, int | None], ...], int | float]] = []
        for rule_index, rule in enumerate(preset_rules):
            if not isinstance(rule, Mapping):
                raise _Unknown("unsupported rule")
            kind = rule.get("type")
            if kind in ("required_agents", "max_count"):
                continue  # Those independent declarations belong to evaluate_deck.
            if kind not in ("requires", "equals") or set(rule) not in (
                    {"type", "from", "to"}, {"type", "from", "to", "from_cost"}):
                raise _Unknown("unsupported rule shape")
            if not _integer(rule["to"]) or not isinstance(rule["from"], list) or not rule["from"]:
                raise _Unknown("unsupported rule shape")
            criteria = tuple(_criterion(value) for value in rule["from"])
            if any(tier >= rule["to"] for tier, _ in criteria):
                raise _Unknown("recursive or non-descending tier rule")
            if kind == "requires":
                if "from_cost" in rule:
                    raise _Unknown("unsupported requires cost threshold")
                requires.append((rule_index, rule["to"], criteria))
            else:
                threshold = rule.get("from_cost", 0)
                if not _number(threshold):
                    raise _Unknown("unknown equals cost threshold")
                equals.append((rule_index, rule["to"], criteria, threshold))

        equals_targets = {tier for _, tier, _, _ in equals}
        if any(from_tier in equals_targets for _, _, criteria, _ in equals
               for from_tier, _ in criteria):
            raise _Unknown("recursive equals chain")
        required_targets = {tier for _, tier, _ in requires}
        if (any(tier in required_targets for _, _, criteria in requires for tier, _ in criteria)
                or any(tier in required_targets for _, _, criteria, _ in equals for tier, _ in criteria)):
            raise _Unknown("nested requirement chain")

        # A direct physical matching is cheap and often settles the deck. It
        # also avoids enumerating irrelevant or very numerous equals groups.
        target_items: list[tuple[int, int, int, tuple[tuple[int, int | None], ...]]] = []
        for rule_index, tier, criteria in requires:
            for m in members:
                if m.tier == tier:
                    target_items.append((rule_index, tier, m.index, criteria))
                    if len(target_items) > max_options:
                        raise _Unknown("budget")
        target_items.sort(key=lambda item: (-item[1], by_index[item[2]].character_id,
                                            by_index[item[2]].source_id, item[0], item[2]))
        if sum(len(item[3]) + 1 for item in target_items) > 400:
            raise _Unknown("budget")

        direct_slots = [(i, j, tier, role) for i, (_, _, _, criteria) in enumerate(target_items)
                        for j, (tier, role) in enumerate(criteria)]
        demanded_tiers = {tier for _, _, tier, role in direct_slots
                          if role is None or equivalents_any_role}
        exact_tiers = {tier for _, _, tier, role in direct_slots if role is not None}
        exact_tiers.update(tier for _, eq_to, criteria, _ in equals if eq_to in demanded_tiers
                           for tier, role in criteria if role is not None)
        role_uncertain = any(m.tier in exact_tiers and m.specification is None for m in members)
        direct_candidates = [[m for m in members if m.tier == tier and
                              (role is None or m.specification == role)]
                             for _, _, tier, role in direct_slots]
        match_by_bit: dict[int, int] = {}

        def direct_match(slot: int, seen: set[int]) -> bool:
            for member in direct_candidates[slot]:
                if member.bit in seen:
                    continue
                seen.add(member.bit)
                prior = match_by_bit.get(member.bit)
                if prior is None or direct_match(prior, seen):
                    match_by_bit[member.bit] = slot
                    return True
            return False

        direct_full = all(direct_match(slot, set()) for slot in range(len(direct_slots)))
        best: list[list[_Option | None]] = [[None] * len(item[3]) for item in target_items]
        if direct_full:
            for bit, slot in match_by_bit.items():
                i, j, _, _ = direct_slots[slot]
                member = next(m for m in members if m.bit == bit)
                best[i][j] = _Option(bit, (member.index,), None, member.cost)

        # Generate only demanded virtual tiers. Repeated criteria walk physical
        # members in ascending order, so k identical slots use combinations,
        # not n**k permutations.
        option_count = 0
        options_truncated = False
        decimal_costs = {m.index: Decimal(str(m.cost)) for m in members}
        eq_groups: dict[int, list[_Option]] = {}
        for eq_index, eq_to, criteria, threshold in equals if not direct_full else ():
            if eq_to not in demanded_tiers:
                continue
            precise_threshold = Decimal(str(threshold))
            pools = [[m for m in members if m.tier == tier and
                      (specification is None or m.specification == specification)]
                     for tier, specification in criteria]
            groups: dict[tuple[int, ...], _Option] = {}
            chosen: list[_Member] = []
            last_for_criterion: dict[tuple[int, int | None], int] = {}

            def add_group(slot: int, mask: int) -> None:
                nonlocal option_count, options_truncated
                if options_truncated:
                    return
                option_count += 1
                if option_count > max_options:
                    options_truncated = True
                    return
                if slot == len(criteria):
                    precise_cost = sum((decimal_costs[m.index] for m in chosen), Decimal(0))
                    if precise_cost < precise_threshold:
                        return
                    try:
                        cost = (int(precise_cost) if precise_cost == precise_cost.to_integral_value()
                                else float(precise_cost))
                    except (OverflowError, ValueError):
                        raise _Unknown("equals cost overflow") from None
                    if not _number(cost):
                        raise _Unknown("equals cost overflow")
                    key = tuple(sorted(m.index for m in chosen))
                    groups[key] = _Option(mask, key, eq_index, cost)
                    return
                criterion = criteria[slot]
                lower = last_for_criterion.get(criterion, -1) + 1
                for position in range(lower, len(pools[slot])):
                    member = pools[slot][position]
                    if member.bit & mask:
                        continue
                    previous = last_for_criterion.get(criterion)
                    last_for_criterion[criterion] = position
                    chosen.append(member)
                    add_group(slot + 1, mask | member.bit)
                    chosen.pop()
                    if previous is None:
                        del last_for_criterion[criterion]
                    else:
                        last_for_criterion[criterion] = previous
                    if options_truncated:
                        return

            add_group(0, 0)
            eq_groups[eq_index] = sorted(groups.values(), key=lambda option: tuple(
                (by_index[index].character_id, by_index[index].source_id, index)
                for index in option.members))

        # An equals group is one virtual unit of its target tier. It is never
        # recursively expanded into another equals group.
        slot_options: list[list[list[_Option]]] = []
        slot_entry_count = 0
        for _, _, _, criteria in target_items if not direct_full else ():
            target_slots: list[list[_Option]] = []
            for tier, specification in criteria:
                direct = [_Option(m.bit, (m.index,), None, m.cost) for m in members
                          if m.tier == tier and (specification is None or m.specification == specification)]
                virtual = [option for eq_index, eq_to, _, _ in equals if eq_to == tier
                           and (specification is None or equivalents_any_role)
                           for option in eq_groups.get(eq_index, ())]
                available = max(0, max_options - slot_entry_count)
                if len(direct) + len(virtual) > available:
                    options_truncated = True
                    direct, virtual = (direct + virtual)[:available], []
                slot_entry_count += len(direct) + len(virtual)
                target_slots.append(direct + virtual)
            slot_options.append(target_slots)

        best_score = (-1, -1)
        current: list[list[_Option | None]] = [[None] * len(item[3]) for item in target_items]
        states = 0
        memo: dict[tuple[int, int], tuple[int, int]] = {}
        full_found = False

        def search_target(target: int, used: int, covered: int, partial_filled: int) -> None:
            nonlocal states, best_score, best, full_found
            states += 1
            if states > max_states:
                raise _Unknown("budget")
            if covered + len(target_items) - target < best_score[0]:
                return
            if target == len(target_items):
                score = (covered, partial_filled)
                if score > best_score:
                    best_score = score
                    best = [row.copy() for row in current]
                if covered == len(target_items):
                    full_found = True
                return
            key = (target, used)
            score = (covered, partial_filled)
            if memo.get(key, (-1, -1)) >= score:
                return
            memo[key] = score
            options_for_target = slot_options[target]

            def search_slot(slot: int, mask: int, filled: int) -> None:
                nonlocal states
                states += 1
                if states > max_states:
                    raise _Unknown("budget")
                if slot == len(options_for_target):
                    done = filled == len(options_for_target)
                    search_target(target + 1, mask, covered + int(done),
                                  partial_filled + (0 if done else filled))
                    return
                for option in options_for_target[slot]:
                    if not (option.mask & mask):
                        current[target][slot] = option
                        search_slot(slot + 1, mask | option.mask, filled + 1)
                        if full_found:
                            return
                current[target][slot] = None
                search_slot(slot + 1, mask, filled)

            search_slot(0, used, 0)

        reason = "exhaustive allocation"
        complete = True
        if direct_full:
            full_found = True
        else:
            try:
                search_target(0, 0, 0, 0)
            except _Unknown as exc:
                reason = str(exc)
                complete = False
            if options_truncated and not full_found:
                reason = "budget"
                complete = False

        rule_results = []
        for rule_index, tier, criteria in requires:
            selected_items = [i for i, item in enumerate(target_items) if item[0] == rule_index]
            assignments = []
            for i in selected_items:
                selected_slots = best[i]
                assignments.append({"target_index": target_items[i][2],
                                    "complete": all(option is not None for option in selected_slots),
                                    "slots": [None if option is None else {
                                        "member_indexes": list(option.members),
                                        "equals_rule_index": option.equals_rule_index,
                                        "cost": option.cost} for option in selected_slots]})
            rule_results.append({"rule_index": rule_index, "selected": len(selected_items),
                                 "covered": sum(item["complete"] for item in assignments),
                                 "slots": [{"tier": slot_tier, **({"specification": spec} if spec is not None else {}),
                                            "required": len(selected_items),
                                            "filled": sum(best[i][j] is not None for i in selected_items)}
                                           for j, (slot_tier, spec) in enumerate(criteria)],
                                 "assignments": assignments})
        equals_results = []
        for eq_index, _, _, _ in equals:
            groups = [list(option.members) for row in best for option in row
                      if option is not None and option.equals_rule_index == eq_index]
            equals_results.append({"rule_index": eq_index, "used": len(groups), "groups": groups})
        all_covered = sum(row["covered"] for row in rule_results) == len(target_items)
        if all_covered and (full_found or complete):
            return {"status": "pass", "complete": True, "reason": "full allocation",
                    "rules": rule_results, "equals": equals_results}
        if complete and role_uncertain:
            complete = False
            reason = "unknown character role"
        return {"status": "fail" if complete else "unknown", "complete": complete,
                "reason": reason, "rules": rule_results, "equals": equals_results}
    except _Unknown as exc:
        return {**empty, "reason": str(exc)}
